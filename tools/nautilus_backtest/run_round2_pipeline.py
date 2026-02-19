"""
Round 2: 8 New Momentum/Trend Strategies Pipeline.

Phase 1: Quick 2024-2026 validation with default params
Phase 2: Parameter grid optimization on FULL 2010-2026 span
Phase 3: 8-window regime robustness test for optimized strategies
Phase 4: Final scoreboard + charts

Usage:
    python -u run_round2_pipeline.py
"""

import sys
import time
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from instrument import create_es_instrument
from data_loader import load_es_bars

# Import all 8 Round 2 strategies
from prev_day_hl_strategy import PrevDayHLStrategy, PrevDayHLConfig
from ema_bounce_strategy import EMABounceStrategy, EMABounceConfig
from atr_trail_strategy import ATRTrailStrategy, ATRTrailConfig
from nr_breakout_strategy import NRBreakoutStrategy, NRBreakoutConfig
from ema_cross_strategy import EMACrossStrategy, EMACrossConfig
from hh_breakout_strategy import HHBreakoutStrategy, HHBreakoutConfig
from first_pullback_strategy import FirstPullbackStrategy, FirstPullbackConfig
from trend_accel_strategy import TrendAccelStrategy, TrendAccelConfig


ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
STARTING_CAPITAL = 25_000.0
CONTRACTS = 10
SIM = Venue("SIM")

RESULTS_DIR = Path(__file__).parent / "results" / "round2_pipeline"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

WINDOWS = [
    ("2010-01-01", "2012-01-01"),
    ("2012-01-01", "2014-01-01"),
    ("2014-01-01", "2016-01-01"),
    ("2016-01-01", "2018-01-01"),
    ("2018-01-01", "2020-01-01"),
    ("2020-01-01", "2022-01-01"),
    ("2022-01-01", "2024-01-01"),
    ("2024-01-01", "2026-01-01"),
]


# ==================== Strategy Factory Functions ====================

def make_prev_day_hl(es, bar_type, tag, **params):
    defaults = dict(atr_period=14, stop_atr_mult=1.5, target_rr=3.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = PrevDayHLConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return PrevDayHLStrategy(config=config)


def make_ema_bounce(es, bar_type, tag, **params):
    defaults = dict(ema_period=21, atr_period=14, touch_atr_mult=0.5, target_rr=3.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = EMABounceConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return EMABounceStrategy(config=config)


def make_atr_trail(es, bar_type, tag, **params):
    defaults = dict(atr_period=14, entry_atr_mult=1.5, stop_atr_mult=1.0, trail_atr_mult=2.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = ATRTrailConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return ATRTrailStrategy(config=config)


def make_nr_breakout(es, bar_type, tag, **params):
    defaults = dict(lookback=4, target_rr=2.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = NRBreakoutConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return NRBreakoutStrategy(config=config)


def make_ema_cross(es, bar_type, tag, **params):
    defaults = dict(fast_period=9, slow_period=21, atr_period=14,
                    stop_atr_mult=1.5, target_rr=3.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = EMACrossConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return EMACrossStrategy(config=config)


def make_hh_breakout(es, bar_type, tag, **params):
    defaults = dict(lookback=20, atr_period=14, stop_atr_mult=1.5, target_rr=3.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = HHBreakoutConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return HHBreakoutStrategy(config=config)


def make_first_pullback(es, bar_type, tag, **params):
    defaults = dict(breakout_lookback=20, target_rr=3.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = FirstPullbackConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return FirstPullbackStrategy(config=config)


def make_trend_accel(es, bar_type, tag, **params):
    defaults = dict(ema_period=21, atr_period=14, accel_mult=1.5, target_rr=3.0,
                    entry_start=935, entry_end=1530, max_trades_per_day=1)
    defaults.update(params)
    config = TrendAccelConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return TrendAccelStrategy(config=config)


STRATEGIES = {
    "PrevDayHL":    (make_prev_day_hl,    "Previous Day H/L Breakout"),
    "EMABounce":    (make_ema_bounce,     "EMA Bounce (trend continuation)"),
    "ATRTrail":     (make_atr_trail,      "ATR Trailing Momentum"),
    "NRBreakout":   (make_nr_breakout,    "Narrow Range Breakout (NR4)"),
    "EMACross":     (make_ema_cross,      "Dual EMA Crossover"),
    "HHBreakout":   (make_hh_breakout,    "Higher High/Lower Low Breakout"),
    "FirstPB":      (make_first_pullback, "First Pullback After Breakout"),
    "TrendAccel":   (make_trend_accel,    "Trend Acceleration"),
}

PARAM_GRIDS = {
    "PrevDayHL": [
        dict(stop_atr_mult=1.0, target_rr=2.0),
        dict(stop_atr_mult=1.5, target_rr=2.0),
        dict(stop_atr_mult=1.5, target_rr=3.0),
        dict(stop_atr_mult=2.0, target_rr=3.0),
        dict(stop_atr_mult=1.0, target_rr=3.0),
        dict(stop_atr_mult=1.5, target_rr=4.0),
        dict(stop_atr_mult=2.0, target_rr=2.0),
    ],
    "EMABounce": [
        dict(ema_period=10, touch_atr_mult=0.3, target_rr=2.0),
        dict(ema_period=21, touch_atr_mult=0.5, target_rr=2.0),
        dict(ema_period=21, touch_atr_mult=0.5, target_rr=3.0),
        dict(ema_period=21, touch_atr_mult=0.3, target_rr=3.0),
        dict(ema_period=50, touch_atr_mult=0.5, target_rr=3.0),
        dict(ema_period=10, touch_atr_mult=0.5, target_rr=3.0),
        dict(ema_period=21, touch_atr_mult=0.8, target_rr=2.0),
        dict(ema_period=21, touch_atr_mult=0.5, target_rr=4.0),
    ],
    "ATRTrail": [
        dict(entry_atr_mult=1.5, stop_atr_mult=1.0, trail_atr_mult=2.0),
        dict(entry_atr_mult=2.0, stop_atr_mult=1.0, trail_atr_mult=2.0),
        dict(entry_atr_mult=1.5, stop_atr_mult=1.5, trail_atr_mult=2.5),
        dict(entry_atr_mult=2.0, stop_atr_mult=1.5, trail_atr_mult=3.0),
        dict(entry_atr_mult=1.5, stop_atr_mult=1.0, trail_atr_mult=3.0),
        dict(entry_atr_mult=1.0, stop_atr_mult=1.0, trail_atr_mult=2.0),
        dict(entry_atr_mult=2.0, stop_atr_mult=0.5, trail_atr_mult=2.0),
        dict(entry_atr_mult=1.5, stop_atr_mult=0.5, trail_atr_mult=1.5),
    ],
    "NRBreakout": [
        dict(lookback=3, target_rr=2.0),
        dict(lookback=4, target_rr=2.0),
        dict(lookback=4, target_rr=3.0),
        dict(lookback=5, target_rr=2.0),
        dict(lookback=7, target_rr=2.0),
        dict(lookback=4, target_rr=4.0),
        dict(lookback=3, target_rr=3.0),
    ],
    "EMACross": [
        dict(fast_period=5, slow_period=13, target_rr=2.0),
        dict(fast_period=9, slow_period=21, target_rr=2.0),
        dict(fast_period=9, slow_period=21, target_rr=3.0),
        dict(fast_period=13, slow_period=34, target_rr=3.0),
        dict(fast_period=5, slow_period=21, target_rr=3.0),
        dict(fast_period=9, slow_period=21, stop_atr_mult=1.0, target_rr=3.0),
        dict(fast_period=9, slow_period=21, stop_atr_mult=2.0, target_rr=3.0),
        dict(fast_period=9, slow_period=50, target_rr=3.0),
    ],
    "HHBreakout": [
        dict(lookback=10, target_rr=2.0),
        dict(lookback=20, target_rr=2.0),
        dict(lookback=20, target_rr=3.0),
        dict(lookback=30, target_rr=3.0),
        dict(lookback=10, target_rr=3.0),
        dict(lookback=20, stop_atr_mult=1.0, target_rr=3.0),
        dict(lookback=20, stop_atr_mult=2.0, target_rr=3.0),
        dict(lookback=40, target_rr=3.0),
    ],
    "FirstPB": [
        dict(breakout_lookback=10, target_rr=2.0),
        dict(breakout_lookback=20, target_rr=2.0),
        dict(breakout_lookback=20, target_rr=3.0),
        dict(breakout_lookback=30, target_rr=3.0),
        dict(breakout_lookback=10, target_rr=3.0),
        dict(breakout_lookback=20, target_rr=4.0),
        dict(breakout_lookback=40, target_rr=3.0),
    ],
    "TrendAccel": [
        dict(accel_mult=1.0, target_rr=2.0),
        dict(accel_mult=1.5, target_rr=2.0),
        dict(accel_mult=1.5, target_rr=3.0),
        dict(accel_mult=2.0, target_rr=3.0),
        dict(accel_mult=1.5, ema_period=10, target_rr=3.0),
        dict(accel_mult=1.5, ema_period=50, target_rr=3.0),
        dict(accel_mult=2.0, target_rr=4.0),
        dict(accel_mult=1.0, target_rr=3.0),
    ],
}


# ==================== Backtest Runner ====================

def run_backtest(factory_fn, es, bar_type, bars, tag, **params):
    """Run one backtest. Returns metrics dict."""
    engine_config = BacktestEngineConfig(
        trader_id=f"R2-{tag[:12]}",
        logging=LoggingConfig(log_level="ERROR"),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)
    engine.add_venue(
        venue=SIM, oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN, base_currency=USD,
        starting_balances=[Money(STARTING_CAPITAL, USD)],
    )
    engine.add_instrument(es)
    engine.add_data(bars)

    result = {"trades": 0, "pnl": 0, "win_rate": 0, "pf": 0, "sharpe": 0, "max_dd": 0}

    try:
        strategy = factory_fn(es, bar_type, tag, **params)
        engine.add_strategy(strategy)
        engine.run()
    except Exception as e:
        print(f"ERROR: {e}")
        engine.reset()
        engine.dispose()
        return result

    positions_report = engine.trader.generate_positions_report()
    if positions_report is not None and not positions_report.empty:
        if "realized_pnl" in positions_report.columns:
            pnls = positions_report["realized_pnl"].apply(
                lambda x: float(str(x).replace(" USD", "").replace(",", ""))
            )
            total_pnl = pnls.sum()
            wins = pnls[pnls > 0]
            losses = pnls[pnls <= 0]
            win_rate = len(wins) / len(pnls) * 100 if len(pnls) > 0 else 0
            gross_wins = wins.sum() if len(wins) > 0 else 0
            gross_losses = abs(losses.sum()) if len(losses) > 0 else 0
            pf = gross_wins / gross_losses if gross_losses > 0 else 0

            equity = pnls.cumsum()
            peak = equity.cummax()
            max_dd = (equity - peak).min()
            sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252) if len(pnls) > 1 and pnls.std() > 0 else 0

            result = {
                "trades": len(pnls), "pnl": total_pnl, "win_rate": win_rate,
                "pf": pf, "sharpe": sharpe, "max_dd": max_dd,
            }

    engine.reset()
    engine.dispose()
    return result


# ==================== Main Pipeline ====================

def main():
    t0 = time.time()
    print("=" * 100)
    print("ROUND 2: MOMENTUM/TREND STRATEGY PIPELINE")
    print(f"Strategies: {', '.join(STRATEGIES.keys())}")
    print("=" * 100)

    es = create_es_instrument(venue=SIM, multiplier=50)

    # ==================== PHASE 1 ====================
    print(f"\n{'='*80}")
    print("PHASE 1: Quick Validation — 2024-2026 (default params)")
    print(f"{'='*80}")

    print("Loading 2024-2026 data...")
    bars_val, bt_val = load_es_bars(
        zip_path=ES_ZIP_PATH, instrument=es,
        start_date="2024-01-01", end_date="2026-01-01", bar_minutes=5,
    )
    print(f"  {len(bars_val):,} bars loaded")

    phase1_results = {}
    for name, (factory_fn, desc) in STRATEGIES.items():
        sys.stdout.write(f"  {name:<12} ... ")
        sys.stdout.flush()
        r = run_backtest(factory_fn, es, bt_val, bars_val, f"V1{name[:4]}")
        phase1_results[name] = r
        status = "PASS" if r["pf"] > 1.0 else ("MARGINAL" if r["pf"] > 0.8 else "FAIL")
        print(f"{status} PF={r['pf']:.2f} PnL=${r['pnl']:>10,.0f} "
              f"WR={r['win_rate']:.0f}% Sharpe={r['sharpe']:.2f} Trades={r['trades']}")

    viable = [n for n, r in phase1_results.items() if r["pf"] >= 0.8 and r["trades"] >= 10]
    dead = [n for n in STRATEGIES if n not in viable]

    print(f"\nViable for optimization ({len(viable)}): {', '.join(viable)}")
    if dead:
        print(f"Eliminated ({len(dead)}): {', '.join(dead)}")

    p1_df = pd.DataFrame([{"strategy": n, **r} for n, r in phase1_results.items()])
    p1_df.to_csv(RESULTS_DIR / "phase1_validation.csv", index=False)

    # ==================== PHASE 2 ====================
    print(f"\n{'='*80}")
    print("PHASE 2: Parameter Optimization — FULL 2010-2026")
    print(f"{'='*80}")

    print("Loading full 2010-2026 data...")
    bars_full, bt_full = load_es_bars(
        zip_path=ES_ZIP_PATH, instrument=es,
        start_date="2010-01-01", end_date="2026-01-01", bar_minutes=5,
    )
    print(f"  {len(bars_full):,} bars loaded (16 years)")

    best_params = {}
    all_opt_results = []

    for name in viable:
        factory_fn = STRATEGIES[name][0]
        grid = PARAM_GRIDS.get(name, [{}])
        print(f"\n  {name}: testing {len(grid)} combos on 2010-2026...")

        best_score = -999
        best_combo = {}
        best_result = None

        for idx, params in enumerate(grid):
            tag = f"O2{name[:3]}{idx:02d}"
            sys.stdout.write(f"    [{idx+1}/{len(grid)}] {params} ... ")
            sys.stdout.flush()
            r = run_backtest(factory_fn, es, bt_full, bars_full, tag, **params)
            r["strategy"] = name
            r["params"] = str(params)
            all_opt_results.append(r)

            print(f"PF={r['pf']:.2f} PnL=${r['pnl']:>8,.0f} Sh={r['sharpe']:.2f} T={r['trades']}")

            score = r["sharpe"] + (1.0 if r["pf"] > 1.0 else 0) + (0.5 if r["trades"] >= 20 else 0)
            if score > best_score:
                best_score = score
                best_combo = params
                best_result = r

        best_params[name] = best_combo
        print(f"  -> Best: {best_combo} -> PF={best_result['pf']:.2f} Sharpe={best_result['sharpe']:.2f}")

    del bars_full, bt_full

    opt_df = pd.DataFrame(all_opt_results)
    opt_df.to_csv(RESULTS_DIR / "phase2_optimization.csv", index=False)

    regime_candidates = [n for n in viable
                         if any(r["pf"] > 1.0 and r["strategy"] == n for r in all_opt_results)]
    if not regime_candidates:
        regime_candidates = viable

    print(f"\nRegime candidates ({len(regime_candidates)}): {', '.join(regime_candidates)}")
    for n in regime_candidates:
        print(f"  {n}: {best_params[n]}")

    # ==================== PHASE 3 ====================
    print(f"\n{'='*80}")
    print("PHASE 3: Regime Robustness — 8 x 2-year windows")
    print(f"{'='*80}")

    window_data = {}
    for idx, (start, end) in enumerate(WINDOWS):
        label = f"{start[:4]}-{end[:4]}"
        sys.stdout.write(f"  Loading {label}... ")
        sys.stdout.flush()
        bars, bar_type = load_es_bars(
            zip_path=ES_ZIP_PATH, instrument=es,
            start_date=start, end_date=end, bar_minutes=5,
        )
        window_data[idx] = (bars, bar_type, start, end, label)
        print(f"{len(bars):,} bars")

    all_regime_results = []
    total_tests = len(regime_candidates) * len(WINDOWS)
    test_num = 0

    for name in regime_candidates:
        factory_fn = STRATEGIES[name][0]
        params = best_params.get(name, {})
        print(f"\n  {name} (params={params}):")

        for widx in range(len(WINDOWS)):
            bars, bar_type, start, end, label = window_data[widx]
            test_num += 1
            tag = f"R3{name[:3]}{widx:02d}"

            sys.stdout.write(f"    [{test_num}/{total_tests}] {label}... ")
            sys.stdout.flush()

            r = run_backtest(factory_fn, es, bar_type, bars, tag, **params)
            r["strategy"] = name
            r["start"] = start
            r["end"] = end
            r["params"] = str(params)
            all_regime_results.append(r)

            status = "PASS" if r["pf"] > 1.0 else "FAIL"
            print(f"{status} PF={r['pf']:.2f} PnL=${r['pnl']:>10,.0f} "
                  f"WR={r['win_rate']:.0f}% Sh={r['sharpe']:.2f} T={r['trades']}")

    regime_df = pd.DataFrame(all_regime_results)
    regime_df.to_csv(RESULTS_DIR / "phase3_regime_results.csv", index=False)

    # ==================== PHASE 4: Scoreboard ====================
    print(f"\n\n{'='*120}")
    print("ROUND 2 FINAL SCOREBOARD")
    print(f"{'='*120}")

    print(f"\n--- Phase 1: Quick Validation (2024-2026) ---")
    print(f"{'Strategy':<12} {'PF':>6} {'Sharpe':>7} {'PnL':>12} {'WR%':>6} {'Trades':>7} {'Status'}")
    print("-" * 65)
    for name, r in sorted(phase1_results.items(), key=lambda x: x[1]["sharpe"], reverse=True):
        status = "PASS" if r["pf"] > 1.0 else ("MARGINAL" if r["pf"] > 0.8 else "FAIL")
        print(f"{name:<12} {r['pf']:>5.2f} {r['sharpe']:>6.2f} ${r['pnl']:>10,.0f} "
              f"{r['win_rate']:>5.1f}% {r['trades']:>6} {status}")

    print(f"\n--- Phase 2: Best Optimized Parameters ---")
    for name in regime_candidates:
        print(f"  {name:<12}: {best_params.get(name, {})}")

    if all_regime_results:
        print(f"\n--- Phase 3: Regime Robustness ---")
        scoreboard = []
        for name in regime_candidates:
            sdf = regime_df[regime_df["strategy"] == name]
            if sdf.empty:
                continue
            profitable = (sdf["pf"] > 1.0).sum()
            total = len(sdf)
            scoreboard.append({
                "Strategy": name,
                "Pass": profitable,
                "Total": total,
                "Pass%": profitable / total * 100 if total > 0 else 0,
                "Avg_PF": sdf["pf"].mean(),
                "Avg_Sharpe": sdf["sharpe"].mean(),
                "Total_PnL": sdf["pnl"].sum(),
                "Avg_WR": sdf["win_rate"].mean(),
                "Worst_PF": sdf["pf"].min(),
                "Best_PF": sdf["pf"].max(),
                "Avg_Trades": sdf["trades"].mean(),
                "Params": str(best_params.get(name, {})),
            })

        sb = pd.DataFrame(scoreboard).sort_values("Avg_Sharpe", ascending=False)

        print(f"\n{'Strategy':<12} {'Pass':>6} {'Avg PF':>7} {'Avg Sh':>7} {'Total PnL':>13} "
              f"{'Avg WR%':>8} {'Worst PF':>9} {'Best PF':>8} {'Avg Trd':>8}")
        print("-" * 100)
        for _, r in sb.iterrows():
            print(f"{r['Strategy']:<12} {r['Pass']:.0f}/{r['Total']:.0f}  "
                  f"{r['Avg_PF']:>6.2f} {r['Avg_Sharpe']:>6.2f} "
                  f"${r['Total_PnL']:>11,.0f} {r['Avg_WR']:>7.1f}% "
                  f"{r['Worst_PF']:>8.2f} {r['Best_PF']:>7.2f} {r['Avg_Trades']:>7.0f}")

        sb.to_csv(RESULTS_DIR / "scoreboard.csv", index=False)

        for name in regime_candidates:
            sdf = regime_df[regime_df["strategy"] == name]
            if sdf.empty:
                continue
            print(f"\n  --- {name} ---")
            for _, r in sdf.iterrows():
                status = "PASS" if r["pf"] > 1.0 else "FAIL"
                print(f"    {r['start'][:4]}-{r['end'][:4]} "
                      f"PF={r['pf']:.2f} PnL=${r['pnl']:>10,.0f} "
                      f"WR={r['win_rate']:.0f}% Sh={r['sharpe']:.2f} T={r['trades']} {status}")

        # ==================== Charts ====================
        print("\nGenerating charts...")

        strat_names = regime_candidates
        window_labels = [f"{s[:4]}-{e[:4]}" for s, e in WINDOWS]

        # PF Heatmap
        fig, ax = plt.subplots(figsize=(14, max(6, len(strat_names) * 0.8 + 2)))
        pf_matrix = np.full((len(strat_names), len(WINDOWS)), np.nan)
        for _, r in regime_df.iterrows():
            if r["strategy"] in strat_names:
                si = strat_names.index(r["strategy"])
                wi = next(i for i, (s, e) in enumerate(WINDOWS) if s == r["start"])
                pf_matrix[si, wi] = r["pf"]

        im = ax.imshow(pf_matrix, aspect="auto", cmap="RdYlGn", vmin=0.5, vmax=2.0)
        ax.set_xticks(range(len(WINDOWS)))
        ax.set_xticklabels(window_labels, rotation=45, ha="right", fontsize=10)
        ax.set_yticks(range(len(strat_names)))
        ax.set_yticklabels(strat_names, fontsize=10)
        for i in range(len(strat_names)):
            for j in range(len(WINDOWS)):
                val = pf_matrix[i, j]
                if not np.isnan(val):
                    color = "white" if val < 0.8 or val > 1.8 else "black"
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                            fontsize=9, fontweight="bold", color=color)
        fig.colorbar(im, ax=ax, label="Profit Factor", shrink=0.8)
        ax.set_title("Round 2 — Regime PF Heatmap", fontsize=14, fontweight="bold")
        fig.tight_layout()
        heatmap_path = RESULTS_DIR / "regime_heatmap_pf.png"
        fig.savefig(str(heatmap_path), dpi=150)
        plt.close(fig)

        # Scoreboard bar chart
        fig, axes = plt.subplots(1, 3, figsize=(18, max(6, len(sb) * 0.6 + 2)))
        sb_sorted = sb.sort_values(["Pass%", "Avg_Sharpe"], ascending=[False, False])

        ax = axes[0]
        colors = ["green" if p >= 75 else "orange" if p >= 50 else "red" for p in sb_sorted["Pass%"]]
        ax.barh(range(len(sb_sorted)), sb_sorted["Pass%"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(sb_sorted)))
        ax.set_yticklabels(sb_sorted["Strategy"], fontsize=10)
        ax.set_xlabel("Profitable Periods (%)")
        ax.set_title("Pass Rate")
        ax.axvline(75, color="green", linestyle="--", alpha=0.5)
        ax.axvline(50, color="orange", linestyle="--", alpha=0.5)
        ax.set_xlim(0, 105)
        for i, (pct, p, t) in enumerate(zip(sb_sorted["Pass%"], sb_sorted["Pass"], sb_sorted["Total"])):
            ax.text(pct + 1, i, f"{int(p)}/{int(t)}", va="center", fontsize=9)
        ax.grid(True, alpha=0.3, axis="x")
        ax.invert_yaxis()

        ax = axes[1]
        colors = ["green" if s > 0.5 else "orange" if s > 0 else "red" for s in sb_sorted["Avg_Sharpe"]]
        ax.barh(range(len(sb_sorted)), sb_sorted["Avg_Sharpe"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(sb_sorted)))
        ax.set_yticklabels(sb_sorted["Strategy"], fontsize=10)
        ax.set_xlabel("Average Sharpe")
        ax.set_title("Avg Sharpe")
        ax.axvline(0, color="black", linewidth=0.5)
        ax.grid(True, alpha=0.3, axis="x")
        ax.invert_yaxis()

        ax = axes[2]
        colors = ["green" if p > 0 else "red" for p in sb_sorted["Total_PnL"]]
        ax.barh(range(len(sb_sorted)), sb_sorted["Total_PnL"] / 1000, color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(sb_sorted)))
        ax.set_yticklabels(sb_sorted["Strategy"], fontsize=10)
        ax.set_xlabel("Total P&L ($K)")
        ax.set_title("Total P&L")
        ax.axvline(0, color="black", linewidth=0.5)
        ax.grid(True, alpha=0.3, axis="x")
        ax.invert_yaxis()

        fig.suptitle("Round 2 — Regime Robustness Scoreboard", fontsize=14, fontweight="bold")
        fig.tight_layout()
        score_path = RESULTS_DIR / "scoreboard_chart.png"
        fig.savefig(str(score_path), dpi=150)
        plt.close(fig)

        # Sharpe heatmap
        fig, ax = plt.subplots(figsize=(14, max(6, len(strat_names) * 0.8 + 2)))
        sharpe_matrix = np.full((len(strat_names), len(WINDOWS)), np.nan)
        for _, r in regime_df.iterrows():
            if r["strategy"] in strat_names:
                si = strat_names.index(r["strategy"])
                wi = next(i for i, (s, e) in enumerate(WINDOWS) if s == r["start"])
                sharpe_matrix[si, wi] = r["sharpe"]
        im = ax.imshow(sharpe_matrix, aspect="auto", cmap="RdYlGn", vmin=-1.0, vmax=3.0)
        ax.set_xticks(range(len(WINDOWS)))
        ax.set_xticklabels(window_labels, rotation=45, ha="right", fontsize=10)
        ax.set_yticks(range(len(strat_names)))
        ax.set_yticklabels(strat_names, fontsize=10)
        for i in range(len(strat_names)):
            for j in range(len(WINDOWS)):
                val = sharpe_matrix[i, j]
                if not np.isnan(val):
                    color = "white" if val < -0.5 or val > 2.5 else "black"
                    ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                            fontsize=9, fontweight="bold", color=color)
        fig.colorbar(im, ax=ax, label="Sharpe Ratio", shrink=0.8)
        ax.set_title("Round 2 — Regime Sharpe Heatmap", fontsize=14, fontweight="bold")
        fig.tight_layout()
        sharpe_path = RESULTS_DIR / "regime_heatmap_sharpe.png"
        fig.savefig(str(sharpe_path), dpi=150)
        plt.close(fig)

        print(f"\nCharts saved to {RESULTS_DIR}/")
        for p in [heatmap_path, score_path]:
            subprocess.Popen(["cmd", "/c", "start", "", str(p)], creationflags=0x08000000)

    # ==================== Winners ====================
    print(f"\n{'='*100}")
    print("ROUND 2 WINNERS")
    print(f"{'='*100}")

    if all_regime_results:
        winners = sb[sb["Pass%"] >= 62.5]
        if not winners.empty:
            print("\nStrategies passing 5+ of 8 regime windows:")
            for _, w in winners.iterrows():
                print(f"  {w['Strategy']:<12} -- {w['Pass']:.0f}/8 PASS, "
                      f"Avg PF={w['Avg_PF']:.2f}, Avg Sharpe={w['Avg_Sharpe']:.2f}, "
                      f"Total PnL=${w['Total_PnL']:>,.0f}")
                print(f"    Best params: {best_params.get(w['Strategy'], {})}")
        else:
            print("\nNo strategy passed 5+ windows. Top results:")
            for _, w in sb.head(3).iterrows():
                print(f"  {w['Strategy']:<12} -- {w['Pass']:.0f}/8, "
                      f"Avg PF={w['Avg_PF']:.2f}, Sharpe={w['Avg_Sharpe']:.2f}")

    elapsed = time.time() - t0
    print(f"\n\nTotal pipeline time: {elapsed/60:.1f} minutes")
    print("ROUND 2 PIPELINE COMPLETE.")


if __name__ == "__main__":
    main()
