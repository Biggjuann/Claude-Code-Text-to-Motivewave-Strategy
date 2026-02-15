"""
Walk-Forward Testing Framework for IFVG Retest Strategy.

Rolls through time windows: optimize parameters in-sample (IS),
validate on out-of-sample (OOS), stitch OOS results for true
out-of-sample performance.

Usage:
    python walk_forward.py --start 2022-01-01 --end 2026-01-01 --mes --contracts 10 --vix-filter
    python walk_forward.py --start 2022-01-01 --end 2026-01-01 --metric profit_factor --workers 4
    python walk_forward.py --param-grid custom_grid.json
"""

import argparse
import itertools
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from instrument import create_es_instrument
from data_loader import load_es_dataframe, wrangle_bars_from_df
from ifvg_strategy import IFVGRetestStrategy, IFVGRetestConfig
from regime_calculator import load_daily_vix

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
VIX_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\VIX_full_1min_ttewdg8.zip"
STARTING_CAPITAL = 25_000.0

# Default parameter grid
DEFAULT_GRID = {
    "shadow_threshold_pct": [20, 30, 40],
    "tp1_points": [15, 20, 25, 30],
    "trail_points": [10, 15, 20],
    "stop_buffer_ticks": [20, 40, 60],
    "be_trigger_pts": [8, 10, 15],
}

# Fixed baseline params (from current best single-pass)
BASELINE_PARAMS = {
    "shadow_threshold_pct": 30,
    "tp1_points": 20,
    "trail_points": 15,
    "stop_buffer_ticks": 40,
    "be_trigger_pts": 10,
}


# ==================== Data Structures ====================

@dataclass
class WindowResult:
    window_num: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    best_params: dict
    is_metric: float
    oos_metric: float
    wfe: float
    is_stats: dict
    oos_stats: dict
    oos_pnls: list = field(default_factory=list)
    oos_trade_dates: list = field(default_factory=list)
    baseline_oos_stats: dict = field(default_factory=dict)
    baseline_oos_pnls: list = field(default_factory=list)


# ==================== Window Generation ====================

def generate_windows(start: str, end: str, is_months: int, oos_months: int):
    """Generate walk-forward windows as (is_start, is_end, oos_start, oos_end) tuples."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    windows = []
    is_start = start_dt

    while True:
        is_end = is_start + relativedelta(months=is_months)
        oos_start = is_end
        oos_end = oos_start + relativedelta(months=oos_months)

        if oos_end > end_dt:
            oos_end = end_dt
            if oos_start >= end_dt:
                break
            if (oos_end - oos_start).days < 20:
                break

        windows.append((
            is_start.strftime("%Y-%m-%d"),
            is_end.strftime("%Y-%m-%d"),
            oos_start.strftime("%Y-%m-%d"),
            oos_end.strftime("%Y-%m-%d"),
        ))

        is_start = is_start + relativedelta(months=oos_months)

        if oos_end >= end_dt:
            break

    return windows


# ==================== Parameter Grid ====================

def build_param_grid(overrides: dict = None) -> list:
    """Build list of parameter dicts from grid values."""
    grid = DEFAULT_GRID.copy()
    if overrides:
        grid.update(overrides)

    keys = sorted(grid.keys())
    values = [grid[k] for k in keys]
    combos = list(itertools.product(*values))

    return [dict(zip(keys, combo)) for combo in combos]


# ==================== Single Backtest ====================

def run_single_backtest(
    bars,
    bar_type,
    instrument,
    params: dict,
    vix_lookup: dict,
    vix_filter: bool,
    starting_capital: float,
    contracts: int,
    log_level: str = "ERROR",
) -> dict:
    """
    Run one backtest with given parameters. Returns metrics dict.

    Creates a fresh engine, runs, extracts results, disposes.
    """
    engine_config = BacktestEngineConfig(
        trader_id="BACKTESTER-WF",
        logging=LoggingConfig(log_level=log_level),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

    SIM = Venue("SIM")
    engine.add_venue(
        venue=SIM,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(starting_capital, USD)],
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)

    strategy_config = IFVGRetestConfig(
        instrument_id=instrument.id,
        bar_type=bar_type,
        enable_long=True,
        enable_short=True,
        contracts=contracts,
        shadow_threshold_pct=params.get("shadow_threshold_pct", 30),
        tp1_points=params.get("tp1_points", 20),
        trail_points=params.get("trail_points", 15),
        stop_buffer_ticks=params.get("stop_buffer_ticks", 40),
        be_trigger_pts=params.get("be_trigger_pts", 10),
        vix_filter_enabled=vix_filter,
        order_id_tag="001",
    )
    strategy = IFVGRetestStrategy(config=strategy_config, vix_lookup=vix_lookup)
    engine.add_strategy(strategy)

    engine.run()

    result = _extract_metrics(engine)

    engine.reset()
    engine.dispose()

    return result


def _extract_metrics(engine) -> dict:
    """Extract performance metrics from a completed backtest engine."""
    positions_report = engine.trader.generate_positions_report()

    empty = {
        "total_pnl": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "sharpe": 0.0,
        "calmar": 0.0,
        "max_dd": 0.0,
        "num_trades": 0,
        "pnls": [],
        "trade_dates": [],
    }
    if positions_report is None or positions_report.empty:
        return empty

    pnls = positions_report["realized_pnl"].apply(
        lambda x: float(str(x).replace(" USD", "").replace(",", ""))
    )

    if len(pnls) == 0:
        return empty

    total_pnl = pnls.sum()
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    win_rate = len(wins) / len(pnls) * 100
    gross_wins = wins.sum() if len(wins) > 0 else 0
    gross_losses = abs(losses.sum()) if len(losses) > 0 else 0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else (
        10.0 if gross_wins > 0 else 0.0  # cap at 10 to prevent inf corrupting optimization
    )

    equity = pnls.cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd = drawdown.min()

    sharpe = 0.0
    if len(pnls) > 1 and pnls.std() > 0:
        sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252)

    calmar = 0.0
    if max_dd < 0:
        calmar = total_pnl / abs(max_dd)

    trade_dates = []
    if "ts_closed" in positions_report.columns:
        trade_dates = positions_report["ts_closed"].tolist()
    elif "ts_last" in positions_report.columns:
        trade_dates = positions_report["ts_last"].tolist()

    return {
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_dd": max_dd,
        "num_trades": len(pnls),
        "pnls": pnls.tolist(),
        "trade_dates": trade_dates,
    }


def get_metric_value(stats: dict, metric: str) -> float:
    """Extract the optimization metric value from stats dict."""
    return stats.get(metric, stats.get("total_pnl", 0.0))


# ==================== Multiprocessing Worker ====================

# Module-level state for worker processes (set by _init_worker)
_worker_state = {}


def _init_worker(es_zip_path, vix_zip_path, multiplier, vix_filter, starting_capital, contracts, log_level):
    """Initialize a worker process: load data once, cache config."""
    global _worker_state
    _worker_state = {
        "df": load_es_dataframe(es_zip_path),
        "vix_lookup": load_daily_vix(vix_zip_path) if vix_filter else {},
        "multiplier": multiplier,
        "vix_filter": vix_filter,
        "starting_capital": starting_capital,
        "contracts": contracts,
        "log_level": log_level,
        "bars_cache": {},  # keyed by (is_start, is_end)
    }


def _run_combo_in_worker(args):
    """Worker function: run one parameter combo on cached data."""
    params, is_start, is_end = args
    s = _worker_state

    cache_key = (is_start, is_end)
    if cache_key not in s["bars_cache"]:
        SIM = Venue("SIM")
        instrument = create_es_instrument(venue=SIM, multiplier=s["multiplier"])
        bars, bar_type = wrangle_bars_from_df(s["df"], instrument, is_start, is_end)
        s["bars_cache"][cache_key] = (bars, bar_type, instrument)

    bars, bar_type, instrument = s["bars_cache"][cache_key]

    if not bars:
        return params, {"total_pnl": 0, "sharpe": 0, "num_trades": 0, "pnls": [], "trade_dates": []}

    stats = run_single_backtest(
        bars=bars,
        bar_type=bar_type,
        instrument=instrument,
        params=params,
        vix_lookup=s["vix_lookup"],
        vix_filter=s["vix_filter"],
        starting_capital=s["starting_capital"],
        contracts=s["contracts"],
        log_level=s["log_level"],
    )
    return params, stats


# ==================== Optimization ====================

def optimize_window_serial(
    df, instrument, is_start, is_end, param_grid, vix_lookup,
    vix_filter, starting_capital, contracts, metric, log_level="ERROR",
):
    """Run all parameter combos on IS data serially."""
    bars, bar_type = wrangle_bars_from_df(df, instrument, is_start, is_end)
    if not bars:
        print(f"    WARNING: No bars for IS {is_start} to {is_end}")
        return BASELINE_PARAMS.copy(), {"total_pnl": 0, "sharpe": 0, "num_trades": 0}

    best_metric = -float("inf")
    best_params = None
    best_stats = None
    total = len(param_grid)
    t0 = time.time()

    for i, params in enumerate(param_grid):
        stats = run_single_backtest(
            bars=bars, bar_type=bar_type, instrument=instrument,
            params=params, vix_lookup=vix_lookup, vix_filter=vix_filter,
            starting_capital=starting_capital, contracts=contracts, log_level=log_level,
        )
        val = get_metric_value(stats, metric)
        if val > best_metric:
            best_metric = val
            best_params = params.copy()
            best_stats = stats

        # Progress with ETA
        elapsed = time.time() - t0
        secs_per_bt = elapsed / (i + 1)
        eta = (total - i - 1) * secs_per_bt
        print(f"    IS {i+1}/{total} ({secs_per_bt:.0f}s/bt, ETA {eta/60:.0f}m)   ", end="\r")

    print()
    return best_params, best_stats


def optimize_window_parallel(
    is_start, is_end, param_grid, metric, pool, num_workers=1,
):
    """Run all parameter combos on IS data using a process pool."""
    total = len(param_grid)
    futures = []
    for params in param_grid:
        f = pool.submit(_run_combo_in_worker, (params, is_start, is_end))
        futures.append(f)

    best_metric = -float("inf")
    best_params = None
    best_stats = None
    t0 = time.time()
    done_count = 0

    for future in as_completed(futures):
        params, stats = future.result()
        done_count += 1
        val = get_metric_value(stats, metric)
        if val > best_metric:
            best_metric = val
            best_params = params.copy()
            best_stats = stats

        elapsed = time.time() - t0
        secs_per_bt = elapsed / done_count
        eta = (total - done_count) * secs_per_bt / max(1, num_workers)
        print(f"    IS {done_count}/{total} ({secs_per_bt:.0f}s/bt, ETA {eta/60:.0f}m)   ", end="\r")

    print()
    if best_params is None:
        return BASELINE_PARAMS.copy(), {"total_pnl": 0, "sharpe": 0, "num_trades": 0}
    return best_params, best_stats


def test_oos(
    df, instrument, oos_start, oos_end, params, vix_lookup,
    vix_filter, starting_capital, contracts, log_level="ERROR",
):
    """Run single backtest on OOS period with given params."""
    bars, bar_type = wrangle_bars_from_df(df, instrument, oos_start, oos_end)
    if not bars:
        print(f"    WARNING: No bars for OOS {oos_start} to {oos_end}")
        return {"total_pnl": 0, "sharpe": 0, "num_trades": 0, "pnls": [], "trade_dates": []}

    return run_single_backtest(
        bars=bars, bar_type=bar_type, instrument=instrument,
        params=params, vix_lookup=vix_lookup, vix_filter=vix_filter,
        starting_capital=starting_capital, contracts=contracts, log_level=log_level,
    )


# ==================== Reporting ====================

def print_summary(results: list, metric: str):
    """Print walk-forward summary table."""
    print()
    print("=" * 110)
    print("WALK-FORWARD RESULTS")
    print("=" * 110)

    header = (
        f"{'Win':>3}  {'IS Period':<23}  {'OOS Period':<23}  "
        f"{'Best Params':<35}  {'IS '+metric:>10}  {'OOS '+metric:>10}  {'WFE':>6}"
    )
    print(header)
    print("-" * 110)

    wfes = []
    oos_pnls_all = []

    for r in results:
        params_str = (
            f"thr={r.best_params['shadow_threshold_pct']:.0f},"
            f"tp1={r.best_params['tp1_points']:.0f},"
            f"trail={r.best_params['trail_points']:.0f},"
            f"sb={r.best_params['stop_buffer_ticks']:.0f},"
            f"be={r.best_params['be_trigger_pts']:.0f}"
        )

        is_val = r.is_metric
        oos_val = r.oos_metric
        if metric in ("sharpe", "calmar", "profit_factor"):
            is_str = f"{is_val:>10.2f}"
            oos_str = f"{oos_val:>10.2f}"
        else:
            is_str = f"${is_val:>9,.0f}"
            oos_str = f"${oos_val:>9,.0f}"

        wfe_str = f"{r.wfe:>6.2f}" if r.wfe != 0 else "   N/A"

        print(
            f"{r.window_num:>3}  {r.is_start+' - '+r.is_end:<23}  "
            f"{r.oos_start+' - '+r.oos_end:<23}  "
            f"{params_str:<35}  {is_str}  {oos_str}  {wfe_str}"
        )

        if r.wfe != 0:
            wfes.append(r.wfe)
        oos_pnls_all.extend(r.oos_pnls)

    print("=" * 110)

    # Stitched OOS metrics
    stitched_pnl = sum(oos_pnls_all)
    avg_wfe = np.mean(wfes) if wfes else 0
    stitched_sharpe = 0.0
    if len(oos_pnls_all) > 1:
        pnl_arr = np.array(oos_pnls_all)
        if pnl_arr.std() > 0:
            stitched_sharpe = (pnl_arr.mean() / pnl_arr.std()) * np.sqrt(252)

    print(f"\nAvg WFE: {avg_wfe:.2f}   Stitched OOS P&L: ${stitched_pnl:,.0f}   "
          f"Stitched OOS Sharpe: {stitched_sharpe:.2f}   "
          f"Stitched OOS Trades: {len(oos_pnls_all)}")

    # Baseline comparison
    all_baseline_pnls = []
    for r in results:
        all_baseline_pnls.extend(r.baseline_oos_pnls)
    if all_baseline_pnls:
        baseline_total = sum(all_baseline_pnls)
        baseline_sharpe = 0.0
        if len(all_baseline_pnls) > 1:
            bl_arr = np.array(all_baseline_pnls)
            if bl_arr.std() > 0:
                baseline_sharpe = (bl_arr.mean() / bl_arr.std()) * np.sqrt(252)
        print(f"Baseline Fixed-Param OOS P&L: ${baseline_total:,.0f}   "
              f"Baseline OOS Sharpe: {baseline_sharpe:.2f}   "
              f"Baseline OOS Trades: {len(all_baseline_pnls)}")


def plot_results(results: list, output_dir: Path):
    """Plot stitched OOS equity curve vs baseline."""
    fig, ax = plt.subplots(figsize=(14, 7))

    all_oos_pnls = []
    for r in results:
        all_oos_pnls.extend(r.oos_pnls)
    if not all_oos_pnls:
        print("No OOS trades to plot.")
        return None

    oos_equity = np.cumsum(all_oos_pnls)
    ax.plot(range(len(oos_equity)), oos_equity, "b-", linewidth=1.5,
            label=f"Walk-Forward OOS (${oos_equity[-1]:,.0f})")

    all_baseline_pnls = []
    for r in results:
        all_baseline_pnls.extend(r.baseline_oos_pnls)
    if all_baseline_pnls:
        baseline_equity = np.cumsum(all_baseline_pnls)
        ax.plot(range(len(baseline_equity)), baseline_equity, "r--", linewidth=1.2,
                label=f"Fixed Params OOS (${baseline_equity[-1]:,.0f})")

    # Window boundaries
    trade_idx = 0
    for r in results:
        trade_idx += len(r.oos_pnls)
        if trade_idx < len(oos_equity):
            ax.axvline(x=trade_idx, color="gray", linestyle=":", alpha=0.5)

    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative P&L ($)")
    ax.set_title("Walk-Forward OOS Equity Curve vs Fixed-Param Baseline")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color="black", linewidth=0.5)

    chart_path = output_dir / "walk_forward_equity.png"
    fig.tight_layout()
    fig.savefig(str(chart_path), dpi=150)
    plt.close(fig)
    print(f"\nChart saved to {chart_path}")
    return chart_path


def save_results_csv(results: list, output_dir: Path):
    """Save per-window results to CSV."""
    rows = []
    for r in results:
        row = {
            "window": r.window_num,
            "is_start": r.is_start,
            "is_end": r.is_end,
            "oos_start": r.oos_start,
            "oos_end": r.oos_end,
            "is_metric": r.is_metric,
            "oos_metric": r.oos_metric,
            "wfe": r.wfe,
            "oos_pnl": r.oos_stats.get("total_pnl", 0),
            "oos_sharpe": r.oos_stats.get("sharpe", 0),
            "oos_trades": r.oos_stats.get("num_trades", 0),
            "oos_win_rate": r.oos_stats.get("win_rate", 0),
            "baseline_oos_pnl": r.baseline_oos_stats.get("total_pnl", 0),
        }
        row.update({f"param_{k}": v for k, v in r.best_params.items()})
        rows.append(row)

    csv_path = output_dir / "walk_forward_results.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(f"Results CSV saved to {csv_path}")


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(description="Walk-Forward Test: IFVG Retest Strategy")
    parser.add_argument("--start", default="2022-01-01", help="Overall start date YYYY-MM-DD")
    parser.add_argument("--end", default="2026-01-01", help="Overall end date YYYY-MM-DD")
    parser.add_argument("--is-months", type=int, default=12, help="In-sample window months")
    parser.add_argument("--oos-months", type=int, default=3, help="Out-of-sample window months")
    parser.add_argument("--metric", default="sharpe",
                        choices=["sharpe", "profit_factor", "total_pnl", "calmar"],
                        help="Optimization metric")
    parser.add_argument("--contracts", type=int, default=2)
    parser.add_argument("--mes", action="store_true", help="Use MES ($5/point)")
    parser.add_argument("--vix-filter", action="store_true", help="Enable VIX hysteresis filter")
    parser.add_argument("--log-level", default="ERROR",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--param-grid", type=str, default=None,
                        help="JSON file with custom grid overrides")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel worker processes (default: 1 = serial)")
    args = parser.parse_args()

    print("=" * 60)
    print("IFVG RETEST — WALK-FORWARD TESTING")
    print("=" * 60)
    print(f"Period: {args.start} to {args.end}")
    print(f"Windows: IS={args.is_months}mo, OOS={args.oos_months}mo")
    print(f"Metric: {args.metric}")
    instrument_label = f"{'MES' if args.mes else 'ES'} x {args.contracts}"
    print(f"Instrument: {instrument_label}")
    print(f"VIX Filter: {'ON' if args.vix_filter else 'OFF'}")
    print(f"Workers: {args.workers}")

    # 1. Generate windows
    windows = generate_windows(args.start, args.end, args.is_months, args.oos_months)
    print(f"\nGenerated {len(windows)} walk-forward windows:")
    for i, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
        print(f"  {i+1}: IS {is_s} -> {is_e}  |  OOS {oos_s} -> {oos_e}")

    if not windows:
        print("ERROR: No valid windows generated. Check date range and window sizes.")
        sys.exit(1)

    # 2. Build param grid
    grid_overrides = None
    if args.param_grid:
        with open(args.param_grid) as f:
            grid_overrides = json.load(f)
    param_grid = build_param_grid(grid_overrides)
    print(f"\nParameter grid: {len(param_grid)} combinations")

    # Runtime estimate (~57s/bt for 12-month IS on this machine, scales linearly)
    backtests_per_window = len(param_grid) + 2  # grid + OOS optimized + OOS baseline
    total_backtests = backtests_per_window * len(windows)
    est_secs_per_bt = 57 * (args.is_months / 12)  # scale by IS window size
    effective_workers = max(1, args.workers)
    est_total = total_backtests * est_secs_per_bt / effective_workers
    print(f"Estimated runtime: ~{est_total/3600:.1f} hours "
          f"({total_backtests} backtests, ~{est_secs_per_bt:.0f}s/bt, {effective_workers} workers)")

    # 3. Load data (main process always loads for OOS runs)
    print("\n--- Loading data (one-time) ---")
    t0 = time.time()

    multiplier = 5 if args.mes else 50
    SIM = Venue("SIM")
    instrument = create_es_instrument(venue=SIM, multiplier=multiplier)

    df = load_es_dataframe(ES_ZIP_PATH)

    vix_lookup = {}
    if args.vix_filter:
        print("Loading VIX data for filter...")
        vix_lookup = load_daily_vix(VIX_ZIP_PATH)

    data_load_time = time.time() - t0
    print(f"Data loaded in {data_load_time:.1f}s\n")

    # 4. Set up process pool (if parallel)
    pool = None
    if args.workers > 1:
        print(f"Starting {args.workers} worker processes (each loads data independently)...")
        pool = ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=_init_worker,
            initargs=(ES_ZIP_PATH, VIX_ZIP_PATH, multiplier, args.vix_filter,
                      STARTING_CAPITAL, args.contracts, args.log_level),
        )

    # 5. Walk-forward loop
    results = []
    total_start = time.time()

    try:
        for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
            win_num = i + 1
            print(f"\n{'='*60}")
            print(f"WINDOW {win_num}/{len(windows)}")
            print(f"  IS:  {is_start} -> {is_end}")
            print(f"  OOS: {oos_start} -> {oos_end}")
            print(f"{'='*60}")

            win_start = time.time()

            # 5a. Optimize on IS
            print(f"  Optimizing on IS ({len(param_grid)} combos)...")
            if pool is not None:
                best_params, is_stats = optimize_window_parallel(
                    is_start, is_end, param_grid, args.metric, pool, args.workers,
                )
            else:
                best_params, is_stats = optimize_window_serial(
                    df, instrument, is_start, is_end, param_grid, vix_lookup,
                    args.vix_filter, STARTING_CAPITAL, args.contracts,
                    args.metric, args.log_level,
                )

            is_metric_val = get_metric_value(is_stats, args.metric)
            print(f"  Best IS params: {best_params}")
            print(f"  IS {args.metric}: {is_metric_val:.4f} | "
                  f"IS P&L: ${is_stats.get('total_pnl', 0):,.0f} | "
                  f"IS trades: {is_stats.get('num_trades', 0)}")

            # 5b. Test on OOS with optimized params
            print(f"  Testing OOS with best params...")
            oos_stats = test_oos(
                df, instrument, oos_start, oos_end, best_params,
                vix_lookup, args.vix_filter, STARTING_CAPITAL,
                args.contracts, args.log_level,
            )
            oos_metric_val = get_metric_value(oos_stats, args.metric)

            # 5c. Baseline OOS with fixed params
            print(f"  Testing OOS with baseline params...")
            baseline_stats = test_oos(
                df, instrument, oos_start, oos_end, BASELINE_PARAMS,
                vix_lookup, args.vix_filter, STARTING_CAPITAL,
                args.contracts, args.log_level,
            )

            # WFE
            wfe = 0.0
            if is_metric_val > 0:
                wfe = oos_metric_val / is_metric_val

            win_time = time.time() - win_start
            print(f"  OOS {args.metric}: {oos_metric_val:.4f} | "
                  f"OOS P&L: ${oos_stats.get('total_pnl', 0):,.0f} | "
                  f"OOS trades: {oos_stats.get('num_trades', 0)} | "
                  f"WFE: {wfe:.2f}")
            print(f"  Window time: {win_time/60:.1f}m")

            # Elapsed / remaining estimate
            elapsed = time.time() - total_start
            rate = (i + 1) / elapsed
            remaining = (len(windows) - i - 1) / rate if rate > 0 else 0
            print(f"  Overall: {elapsed/60:.0f}m elapsed, ~{remaining/60:.0f}m remaining")

            results.append(WindowResult(
                window_num=win_num,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
                best_params=best_params,
                is_metric=is_metric_val,
                oos_metric=oos_metric_val,
                wfe=wfe,
                is_stats=is_stats,
                oos_stats=oos_stats,
                oos_pnls=oos_stats.get("pnls", []),
                oos_trade_dates=oos_stats.get("trade_dates", []),
                baseline_oos_stats=baseline_stats,
                baseline_oos_pnls=baseline_stats.get("pnls", []),
            ))
    finally:
        if pool is not None:
            pool.shutdown(wait=False)

    total_time = time.time() - total_start
    print(f"\nTotal walk-forward time: {total_time/60:.1f} minutes")

    # 6. Summary + chart
    print_summary(results, args.metric)

    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    save_results_csv(results, output_dir)
    chart_path = plot_results(results, output_dir)

    if chart_path:
        import subprocess
        subprocess.Popen(["cmd", "/c", "start", "", str(chart_path)],
                         creationflags=0x08000000)


if __name__ == "__main__":
    main()
