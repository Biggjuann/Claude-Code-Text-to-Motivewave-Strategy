"""
New 8 Strategy Pipeline — Validate, Optimize, Regime Test.

Phase 1: Quick 2024-2026 validation with default params (eliminate dead strategies)
Phase 2: Parameter grid optimization on FULL 2010-2026 span (avoid overfitting)
Phase 3: 8-window regime robustness test for optimized strategies
Phase 4: Final scoreboard + charts

Usage:
    python -u run_new8_pipeline.py
"""

import sys
import time
import itertools
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

# Import all 8 new strategies
from inside_bar_strategy import InsideBarStrategy, InsideBarConfig
from gap_fade_strategy import GapFadeStrategy, GapFadeConfig
from three_bar_momentum_strategy import ThreeBarStrategy, ThreeBarConfig
from opening_drive_strategy import OpeningDriveStrategy, OpeningDriveConfig
from keltner_breakout_strategy import KeltnerStrategy, KeltnerConfig
from engulfing_strategy import EngulfingStrategy, EngulfingConfig
from exhaustion_reversal_strategy import ExhaustionStrategy, ExhaustionConfig
from vwap_mr_strategy import VWAPMRStrategy, VWAPMRConfig


ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
STARTING_CAPITAL = 25_000.0
CONTRACTS = 10
SIM = Venue("SIM")

RESULTS_DIR = Path(__file__).parent / "results" / "new8_pipeline"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Regime windows
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

def make_inside_bar(es, bar_type, tag, **params):
    defaults = dict(target_rr=2.0, max_trades_per_day=1, entry_start=935, entry_end=1530)
    defaults.update(params)
    config = InsideBarConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return InsideBarStrategy(config=config)


def make_gap_fade(es, bar_type, tag, **params):
    defaults = dict(gap_threshold_pts=5.0, stop_mult=1.0, use_rr_target=False,
                    target_rr=2.0, max_trades_per_day=1, entry_start=935, entry_end=945)
    defaults.update(params)
    config = GapFadeConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return GapFadeStrategy(config=config)


def make_three_bar(es, bar_type, tag, **params):
    defaults = dict(consecutive=3, min_body_pct=50.0, target_rr=2.0,
                    max_trades_per_day=1, entry_start=935, entry_end=1530)
    defaults.update(params)
    config = ThreeBarConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return ThreeBarStrategy(config=config)


def make_opening_drive(es, bar_type, tag, **params):
    defaults = dict(body_pct_threshold=60.0, range_mult=1.0, range_lookback=20,
                    target_rr=2.0, max_trades_per_day=1)
    defaults.update(params)
    config = OpeningDriveConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return OpeningDriveStrategy(config=config)


def make_keltner(es, bar_type, tag, **params):
    defaults = dict(ema_period=20, atr_period=14, kelt_mult=2.0, target_rr=2.0,
                    max_trades_per_day=1, entry_start=935, entry_end=1530)
    defaults.update(params)
    config = KeltnerConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return KeltnerStrategy(config=config)


def make_engulfing(es, bar_type, tag, **params):
    defaults = dict(min_body_pct=50.0, target_rr=2.0,
                    max_trades_per_day=1, entry_start=935, entry_end=1530)
    defaults.update(params)
    config = EngulfingConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return EngulfingStrategy(config=config)


def make_exhaustion(es, bar_type, tag, **params):
    defaults = dict(consecutive_bars=5, target_rr=2.0,
                    max_trades_per_day=1, entry_start=935, entry_end=1530)
    defaults.update(params)
    config = ExhaustionConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return ExhaustionStrategy(config=config)


def make_vwap_mr(es, bar_type, tag, **params):
    defaults = dict(deviation_mult=2.0, atr_period=14, stop_buffer_pts=2.0,
                    use_rr_target=False, target_rr=2.0,
                    max_trades_per_day=1, entry_start=1000, entry_end=1500)
    defaults.update(params)
    config = VWAPMRConfig(
        instrument_id=es.id, bar_type=bar_type,
        contracts=CONTRACTS, eod_time=1640,
        order_id_tag=tag, **defaults,
    )
    return VWAPMRStrategy(config=config)


# Strategy registry
STRATEGIES = {
    "InsideBar":   (make_inside_bar,  "Inside Bar Breakout"),
    "GapFade":     (make_gap_fade,    "Gap Fade (mean reversion)"),
    "ThreeBar":    (make_three_bar,   "3-Bar Momentum"),
    "OpenDrive":   (make_opening_drive, "Opening Drive"),
    "Keltner":     (make_keltner,     "Keltner Channel Breakout"),
    "Engulfing":   (make_engulfing,   "Engulfing Reversal"),
    "Exhaustion":  (make_exhaustion,  "Exhaustion Reversal"),
    "VWAP_MR":     (make_vwap_mr,     "VWAP Mean Reversion"),
}


# Parameter grids for optimization (kept small for speed)
PARAM_GRIDS = {
    "InsideBar": [
        dict(target_rr=1.5),
        dict(target_rr=2.0),
        dict(target_rr=3.0),
        dict(target_rr=2.0, max_trades_per_day=2),
        dict(target_rr=3.0, max_trades_per_day=2),
        dict(target_rr=2.0, entry_end=1400),
    ],
    "GapFade": [
        dict(gap_threshold_pts=3.0),
        dict(gap_threshold_pts=5.0),
        dict(gap_threshold_pts=8.0),
        dict(gap_threshold_pts=5.0, stop_mult=0.5),
        dict(gap_threshold_pts=5.0, stop_mult=1.5),
        dict(gap_threshold_pts=3.0, use_rr_target=True, target_rr=2.0),
        dict(gap_threshold_pts=5.0, use_rr_target=True, target_rr=3.0),
        dict(gap_threshold_pts=3.0, entry_end=1000),
    ],
    "ThreeBar": [
        dict(consecutive=2, target_rr=2.0),
        dict(consecutive=3, target_rr=2.0),
        dict(consecutive=3, target_rr=3.0),
        dict(consecutive=4, target_rr=2.0),
        dict(consecutive=3, min_body_pct=30.0),
        dict(consecutive=3, min_body_pct=70.0),
        dict(consecutive=2, target_rr=3.0),
        dict(consecutive=3, max_trades_per_day=2),
    ],
    "OpenDrive": [
        dict(body_pct_threshold=50.0, target_rr=2.0),
        dict(body_pct_threshold=60.0, target_rr=2.0),
        dict(body_pct_threshold=60.0, target_rr=3.0),
        dict(body_pct_threshold=70.0, target_rr=2.0),
        dict(body_pct_threshold=50.0, range_mult=1.5),
        dict(body_pct_threshold=60.0, range_mult=0.8),
        dict(body_pct_threshold=50.0, target_rr=1.5),
    ],
    "Keltner": [
        dict(ema_period=10, kelt_mult=1.5, target_rr=2.0),
        dict(ema_period=20, kelt_mult=2.0, target_rr=2.0),
        dict(ema_period=20, kelt_mult=1.5, target_rr=2.0),
        dict(ema_period=20, kelt_mult=2.0, target_rr=3.0),
        dict(ema_period=30, kelt_mult=2.0, target_rr=2.0),
        dict(ema_period=20, kelt_mult=2.5, target_rr=2.0),
        dict(ema_period=10, kelt_mult=2.0, target_rr=3.0),
        dict(ema_period=20, kelt_mult=1.5, target_rr=3.0),
    ],
    "Engulfing": [
        dict(min_body_pct=30.0, target_rr=2.0),
        dict(min_body_pct=50.0, target_rr=2.0),
        dict(min_body_pct=50.0, target_rr=3.0),
        dict(min_body_pct=70.0, target_rr=2.0),
        dict(min_body_pct=30.0, target_rr=3.0),
        dict(min_body_pct=50.0, max_trades_per_day=2),
        dict(min_body_pct=30.0, max_trades_per_day=2),
    ],
    "Exhaustion": [
        dict(consecutive_bars=3, target_rr=2.0),
        dict(consecutive_bars=4, target_rr=2.0),
        dict(consecutive_bars=5, target_rr=2.0),
        dict(consecutive_bars=5, target_rr=3.0),
        dict(consecutive_bars=6, target_rr=2.0),
        dict(consecutive_bars=4, target_rr=3.0),
        dict(consecutive_bars=3, target_rr=3.0),
        dict(consecutive_bars=4, max_trades_per_day=2),
    ],
    "VWAP_MR": [
        dict(deviation_mult=1.5, stop_buffer_pts=2.0),
        dict(deviation_mult=2.0, stop_buffer_pts=2.0),
        dict(deviation_mult=2.5, stop_buffer_pts=2.0),
        dict(deviation_mult=2.0, stop_buffer_pts=1.0),
        dict(deviation_mult=2.0, stop_buffer_pts=3.0),
        dict(deviation_mult=1.5, use_rr_target=True, target_rr=2.0),
        dict(deviation_mult=2.0, use_rr_target=True, target_rr=3.0),
        dict(deviation_mult=1.5, entry_start=935, entry_end=1530),
    ],
}


# ==================== Backtest Runner ====================

def run_backtest(factory_fn, es, bar_type, bars, tag, **params):
    """Run one backtest. Returns metrics dict."""
    engine_config = BacktestEngineConfig(
        trader_id=f"P-{tag[:12]}",
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
    print("NEW 8 STRATEGY PIPELINE — VALIDATE → OPTIMIZE → REGIME TEST")
    print(f"Strategies: {', '.join(STRATEGIES.keys())}")
    print("=" * 100)

    es = create_es_instrument(venue=SIM, multiplier=50)

    # ==================== PHASE 1: Quick Validation (2024-2026) ====================
    print(f"\n{'='*80}")
    print("PHASE 1: Quick Validation — 2024-01-01 to 2026-01-01 (default params)")
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

    # Keep strategies with PF >= 0.8 (marginal or better) for optimization
    viable = [n for n, r in phase1_results.items() if r["pf"] >= 0.8 and r["trades"] >= 10]
    dead = [n for n in STRATEGIES if n not in viable]

    print(f"\nViable for optimization ({len(viable)}): {', '.join(viable)}")
    if dead:
        print(f"Eliminated ({len(dead)}): {', '.join(dead)}")

    # Save phase 1 results
    p1_df = pd.DataFrame([
        {"strategy": n, **r} for n, r in phase1_results.items()
    ])
    p1_df.to_csv(RESULTS_DIR / "phase1_validation.csv", index=False)

    # ==================== PHASE 2: Parameter Optimization (FULL 2010-2026) ====================
    print(f"\n{'='*80}")
    print("PHASE 2: Parameter Optimization — FULL 2010-2026 (avoid overfitting)")
    print(f"{'='*80}")

    print("Loading full 2010-2026 data for optimization...")
    bars_full, bt_full = load_es_bars(
        zip_path=ES_ZIP_PATH, instrument=es,
        start_date="2010-01-01", end_date="2026-01-01", bar_minutes=5,
    )
    print(f"  {len(bars_full):,} bars loaded (16 years)")

    best_params = {}  # strategy_name → best params dict
    all_opt_results = []

    for name in viable:
        factory_fn = STRATEGIES[name][0]
        grid = PARAM_GRIDS.get(name, [{}])
        print(f"\n  {name}: testing {len(grid)} parameter combos on 2010-2026...")

        best_pf = -1
        best_sharpe = -999
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

            # Pick best by Sharpe (with PF > 1.0 preferred)
            score = r["sharpe"] + (1.0 if r["pf"] > 1.0 else 0) + (0.5 if r["trades"] >= 20 else 0)
            if score > best_sharpe:
                best_sharpe = score
                best_pf = r["pf"]
                best_combo = params
                best_result = r

        best_params[name] = best_combo
        print(f"  → Best: {best_combo} → PF={best_pf:.2f} Sharpe={best_result['sharpe']:.2f}")

    # Free full-span data to save memory before regime tests
    del bars_full, bt_full

    # Save optimization results
    opt_df = pd.DataFrame(all_opt_results)
    opt_df.to_csv(RESULTS_DIR / "phase2_optimization.csv", index=False)

    # Filter: only regime-test strategies that achieved PF > 1.0 in optimization
    regime_candidates = [n for n in viable
                         if any(r["pf"] > 1.0 and r["strategy"] == n for r in all_opt_results)]
    if not regime_candidates:
        # Fall back to any viable strategy
        regime_candidates = viable

    print(f"\nRegime test candidates ({len(regime_candidates)}): {', '.join(regime_candidates)}")
    print(f"Best params: ")
    for n in regime_candidates:
        print(f"  {n}: {best_params[n]}")

    # ==================== PHASE 3: Regime Robustness Test (8 windows) ====================
    print(f"\n{'='*80}")
    print("PHASE 3: Regime Robustness Test — 8 × 2-year windows (2010-2026)")
    print(f"{'='*80}")

    # Pre-load data for all windows
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

    # Save regime results
    regime_df = pd.DataFrame(all_regime_results)
    regime_df.to_csv(RESULTS_DIR / "phase3_regime_results.csv", index=False)

    # ==================== PHASE 4: Final Scoreboard ====================
    print(f"\n\n{'='*120}")
    print("FINAL SCOREBOARD — NEW 8 STRATEGIES")
    print(f"{'='*120}")

    # Phase 1 summary
    print(f"\n--- Phase 1: Quick Validation (2024-2026, defaults) ---")
    print(f"{'Strategy':<12} {'PF':>6} {'Sharpe':>7} {'PnL':>12} {'WR%':>6} {'Trades':>7} {'Status'}")
    print("-" * 65)
    for name, r in sorted(phase1_results.items(), key=lambda x: x[1]["sharpe"], reverse=True):
        status = "PASS" if r["pf"] > 1.0 else ("MARGINAL" if r["pf"] > 0.8 else "FAIL")
        print(f"{name:<12} {r['pf']:>5.2f} {r['sharpe']:>6.2f} ${r['pnl']:>10,.0f} "
              f"{r['win_rate']:>5.1f}% {r['trades']:>6} {status}")

    # Best params
    print(f"\n--- Phase 2: Best Optimized Parameters ---")
    for name in regime_candidates:
        p = best_params.get(name, {})
        print(f"  {name:<12}: {p if p else '(defaults)'}")

    # Regime scoreboard
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

        # Per-strategy detail
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

        # 1. Regime PF Heatmap
        strat_names = regime_candidates
        window_labels = [f"{s[:4]}-{e[:4]}" for s, e in WINDOWS]

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
        ax.set_title("New 8 Strategies — Regime PF Heatmap", fontsize=14, fontweight="bold")
        fig.tight_layout()
        heatmap_path = RESULTS_DIR / "regime_heatmap_pf.png"
        fig.savefig(str(heatmap_path), dpi=150)
        plt.close(fig)

        # 2. Scoreboard bar chart
        fig, axes = plt.subplots(1, 3, figsize=(18, max(6, len(sb) * 0.6 + 2)))
        sb_sorted = sb.sort_values(["Pass%", "Avg_Sharpe"], ascending=[False, False])

        # Pass rate
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

        # Avg Sharpe
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

        # Total P&L
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

        fig.suptitle("New 8 Strategies — Regime Robustness Scoreboard", fontsize=14, fontweight="bold")
        fig.tight_layout()
        score_path = RESULTS_DIR / "scoreboard_chart.png"
        fig.savefig(str(score_path), dpi=150)
        plt.close(fig)

        # 3. Sharpe heatmap
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
        ax.set_title("New 8 Strategies — Regime Sharpe Heatmap", fontsize=14, fontweight="bold")
        fig.tight_layout()
        sharpe_path = RESULTS_DIR / "regime_heatmap_sharpe.png"
        fig.savefig(str(sharpe_path), dpi=150)
        plt.close(fig)

        print(f"\nCharts saved to {RESULTS_DIR}/")
        print(f"  - {heatmap_path.name}")
        print(f"  - {score_path.name}")
        print(f"  - {sharpe_path.name}")

        # Open charts
        for p in [heatmap_path, score_path]:
            subprocess.Popen(["cmd", "/c", "start", "", str(p)], creationflags=0x08000000)

    # ==================== Winners Summary ====================
    print(f"\n{'='*100}")
    print("WINNERS SUMMARY")
    print(f"{'='*100}")

    if all_regime_results:
        winners = sb[sb["Pass%"] >= 62.5]  # 5/8 or better
        if not winners.empty:
            print("\nStrategies passing 5+ of 8 regime windows:")
            for _, w in winners.iterrows():
                print(f"  {w['Strategy']:<12} — {w['Pass']:.0f}/8 PASS, "
                      f"Avg PF={w['Avg_PF']:.2f}, Avg Sharpe={w['Avg_Sharpe']:.2f}, "
                      f"Total PnL=${w['Total_PnL']:>,.0f}")
                print(f"    Best params: {best_params.get(w['Strategy'], {})}")
        else:
            print("\nNo strategy passed 5+ regime windows. Best results:")
            for _, w in sb.head(3).iterrows():
                print(f"  {w['Strategy']:<12} — {w['Pass']:.0f}/8 PASS, "
                      f"Avg PF={w['Avg_PF']:.2f}, Avg Sharpe={w['Avg_Sharpe']:.2f}")
    else:
        print("\nNo regime tests were run (no viable strategies).")

    elapsed = time.time() - t0
    print(f"\n\nTotal pipeline time: {elapsed/60:.1f} minutes")
    print("PIPELINE COMPLETE.")


if __name__ == "__main__":
    main()
