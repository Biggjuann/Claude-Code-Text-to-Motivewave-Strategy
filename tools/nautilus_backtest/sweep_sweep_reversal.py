"""
DDR (Displacement-Doji-Reversal) — Systematic Parameter Sweep.

Sweeps displacement_mult × doji_max_body_pct × target_rr.
Loads data ONCE, then runs all variants in-process.

Usage:
    python -u sweep_sweep_reversal.py
"""

import sys
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from instrument import create_es_instrument
from data_loader import load_es_bars
from sweep_reversal_strategy import SweepReversalStrategy, SweepReversalConfig

ES_ZIP = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
VIX_ZIP = r"C:\Users\jung_\Downloads\Backtesting data\VIX_full_1min_ttewdg8.zip"
CAPITAL = 25_000.0
START = "2022-01-01"
END = "2026-01-01"
BAR_MIN = 5


def run_one(bars, bt, es, params: dict, vix_lookup: dict = None) -> dict:
    """Run a single backtest and return metrics."""
    engine = BacktestEngine(config=BacktestEngineConfig(
        trader_id="BACKTESTER-025",
        logging=LoggingConfig(log_level="ERROR"),
        risk_engine=RiskEngineConfig(bypass=True),
    ))
    SIM = Venue("SIM")
    engine.add_venue(
        venue=SIM, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=USD, starting_balances=[Money(CAPITAL, USD)],
    )
    engine.add_instrument(es)
    engine.add_data(bars)

    cfg = SweepReversalConfig(
        instrument_id=es.id, bar_type=bt,
        order_id_tag="025",
        **params,
    )
    engine.add_strategy(SweepReversalStrategy(cfg, vix_lookup=vix_lookup))
    engine.run()

    pr = engine.trader.generate_positions_report()
    result = {
        "trades": 0, "pf": 0.0, "sharpe": 0.0, "wr": 0.0,
        "pnl": 0.0, "mdd": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
    }

    if pr is not None and not pr.empty:
        pnls = pr["realized_pnl"].apply(
            lambda x: float(str(x).replace(" USD", "").replace(",", ""))
        )
        w = pnls[pnls > 0]
        lo = pnls[pnls <= 0]
        result["trades"] = len(pnls)
        result["wr"] = len(w) / len(pnls) * 100 if len(pnls) > 0 else 0
        result["pnl"] = pnls.sum()
        result["pf"] = (
            w.sum() / abs(lo.sum())
            if len(lo) > 0 and lo.sum() != 0
            else (99.0 if len(w) > 0 else 0.0)
        )
        eq = pnls.cumsum()
        result["mdd"] = (eq - eq.cummax()).min()
        result["sharpe"] = (
            (pnls.mean() / pnls.std()) * np.sqrt(252) if pnls.std() > 0 else 0
        )
        result["avg_win"] = w.mean() if len(w) > 0 else 0
        result["avg_loss"] = lo.mean() if len(lo) > 0 else 0

    engine.reset()
    engine.dispose()
    return result


def main():
    print(f"Loading data {START} → {END} ({BAR_MIN}m)...")
    t0 = time.time()
    SIM = Venue("SIM")
    es = create_es_instrument(venue=SIM, multiplier=50)
    bars, bt = load_es_bars(ES_ZIP, es, START, END, BAR_MIN)
    print(f"  {len(bars):,} bars loaded in {time.time() - t0:.1f}s")

    # Load VIX for filtered runs
    print("Loading VIX data...")
    from regime_calculator import load_daily_vix
    vix_lookup = load_daily_vix(VIX_ZIP)
    print(f"  {len(vix_lookup):,} VIX days loaded\n")

    # ============ PARAMETER GRID ============
    displacement_mults = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
    doji_max_body_pcts = [20.0, 30.0]
    target_rrs = [2.0, 3.0]

    configs = []

    # --- Group 1: Short-only + VIX 15-20 (proven best regime) ---
    for dm, doji, rr in product(displacement_mults, doji_max_body_pcts, target_rrs):
        label = f"S_vix_dm{dm}_doji{int(doji)}_rr{rr}"
        configs.append((label, {
            "displacement_mult": dm,
            "doji_max_body_pct": doji,
            "target_rr": rr,
            "direction": "short",
            "vix_filter_enabled": True,
            "vix_min": 15.0,
            "vix_max": 20.0,
        }, vix_lookup))

    # --- Group 2: Both directions, no VIX filter ---
    for dm, doji, rr in product(displacement_mults, doji_max_body_pcts, target_rrs):
        label = f"B_noVix_dm{dm}_doji{int(doji)}_rr{rr}"
        configs.append((label, {
            "displacement_mult": dm,
            "doji_max_body_pct": doji,
            "target_rr": rr,
            "direction": "both",
            "vix_filter_enabled": False,
        }, None))

    total = len(configs)
    print(f"Running {total} configurations...\n")
    header = f"{'#':>3} {'Label':<40} {'Trades':>6} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'P&L':>10} {'MDD':>10}"
    print(header)
    print("-" * len(header))

    results = []
    for i, (label, params, vix) in enumerate(configs):
        t1 = time.time()
        r = run_one(bars, bt, es, params, vix_lookup=vix)
        dt = time.time() - t1
        pf_str = f"{r['pf']:.2f}" if r["pf"] < 50 else "INF"
        print(
            f"{i+1:>3} {label:<40} {r['trades']:>6} {r['wr']:>5.1f}% "
            f"{pf_str:>6} {r['sharpe']:>7.2f} ${r['pnl']:>9,.0f} "
            f"${r['mdd']:>9,.0f}  [{dt:.1f}s]"
        )
        sys.stdout.flush()
        results.append({"label": label, **params, **r})

    # ============ RANKED OUTPUT ============
    # Sort by Sharpe (primary), min 10 trades
    ranked = sorted(results, key=lambda x: x["sharpe"] if x["trades"] >= 10 else -999, reverse=True)

    print("\n" + "=" * 100)
    print("TOP 15 RESULTS (by Sharpe, min 10 trades)")
    print("=" * 100)
    print(f"{'#':>3} {'Label':<40} {'Trades':>6} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'P&L':>10} {'MDD':>10}")
    print("-" * 100)
    shown = 0
    for r in ranked:
        if r["trades"] < 10:
            continue
        pf_str = f"{r['pf']:.2f}" if r["pf"] < 50 else "INF"
        print(
            f"{shown+1:>3} {r['label']:<40} {r['trades']:>6} {r['wr']:>5.1f}% "
            f"{pf_str:>6} {r['sharpe']:>7.2f} ${r['pnl']:>9,.0f} "
            f"${r['mdd']:>9,.0f}"
        )
        shown += 1
        if shown >= 15:
            break

    # Check for strong results
    hits = [r for r in results if r["pf"] >= 1.5 and r["sharpe"] >= 1.0 and r["trades"] >= 15]
    if hits:
        print(f"\n>>> {len(hits)} CONFIGURATIONS HIT TARGET (PF>=1.5 & Sharpe>=1.0 & Trades>=15) <<<")
        for h in sorted(hits, key=lambda x: x["sharpe"], reverse=True)[:5]:
            print(f"  {h['label']}: PF={h['pf']:.2f} Sharpe={h['sharpe']:.2f} Trades={h['trades']} P&L=${h['pnl']:,.0f}")
    else:
        print("\nNo configurations hit target (PF>=1.5 & Sharpe>=1.0 & Trades>=15).")

    # Save full results
    out_csv = Path(__file__).parent / "results" / "sweep_ddr.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(out_csv, index=False)
    print(f"\nFull results saved to {out_csv}")

    # ============ AUTO-RUN BEST VARIANT ============
    best = None
    for r in ranked:
        if r["trades"] >= 15:
            best = r
            break

    if best and best["sharpe"] > 0:
        print(f"\n{'='*60}")
        print(f"AUTO-RUNNING BEST: {best['label']}")
        print(f"  Sharpe={best['sharpe']:.2f} PF={best['pf']:.2f} Trades={best['trades']}")
        print(f"{'='*60}")

        # Build param dict for best
        best_params = {
            "displacement_mult": best.get("displacement_mult", 2.0),
            "doji_max_body_pct": best.get("doji_max_body_pct", 25.0),
            "target_rr": best.get("target_rr", 3.0),
            "direction": best.get("direction", "both"),
            "vix_filter_enabled": best.get("vix_filter_enabled", False),
            "vix_min": best.get("vix_min", 15.0),
            "vix_max": best.get("vix_max", 20.0),
        }
        best_vix = vix_lookup if best_params["vix_filter_enabled"] else None

        # Full backtest with output
        engine = BacktestEngine(config=BacktestEngineConfig(
            trader_id="BACKTESTER-025",
            logging=LoggingConfig(log_level="INFO"),
            risk_engine=RiskEngineConfig(bypass=True),
        ))
        SIM2 = Venue("SIM")
        engine.add_venue(
            venue=SIM2, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
            base_currency=USD, starting_balances=[Money(CAPITAL, USD)],
        )
        engine.add_instrument(es)
        engine.add_data(bars)

        cfg = SweepReversalConfig(
            instrument_id=es.id, bar_type=bt,
            order_id_tag="025",
            **best_params,
        )
        engine.add_strategy(SweepReversalStrategy(cfg, vix_lookup=best_vix))
        engine.run()

        pr = engine.trader.generate_positions_report()
        fr = engine.trader.generate_order_fills_report()

        if pr is not None and not pr.empty:
            out_dir = Path(__file__).parent / "results" / "ddr_best"
            out_dir.mkdir(parents=True, exist_ok=True)
            pr.to_csv(out_dir / "positions.csv")
            if fr is not None and not fr.empty:
                fr.to_csv(out_dir / "fills.csv")

            # Equity curve
            from plot_equity import plot_equity
            title = f"DDR Best — {best['label']} ({START} to {END})"
            chart_path = plot_equity(str(out_dir / "positions.csv"), title)
            import subprocess
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(chart_path)],
                creationflags=0x08000000,
            )

            # Margin analysis
            try:
                from margin_analyzer import (
                    analyze_margin, print_margin_report,
                    plot_margin_analysis, save_margin_summary,
                )
                margin_result = analyze_margin(
                    fills_csv=str(out_dir / "fills.csv"),
                    positions_csv=str(out_dir / "positions.csv"),
                    bars=bars,
                    starting_capital=CAPITAL,
                    multiplier=50,
                )
                print_margin_report(margin_result, label="DDR Best")
                save_margin_summary(margin_result, str(out_dir))
                margin_chart = plot_margin_analysis(
                    margin_result, str(out_dir),
                    title=f"Margin Analysis — DDR Best ({best['label']})",
                )
                if margin_chart:
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", str(margin_chart)],
                        creationflags=0x08000000,
                    )
            except Exception as e:
                print(f"\nWarning: Margin analysis failed: {e}")

            print(f"\nBest variant results saved to {out_dir}")

        engine.reset()
        engine.dispose()


if __name__ == "__main__":
    main()
