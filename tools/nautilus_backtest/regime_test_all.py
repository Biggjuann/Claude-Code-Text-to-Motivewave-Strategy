"""
Multi-Strategy Regime Robustness Test.

Tests all 10 backtested strategies across 8 two-year windows (2010-2026)
to identify which strategies are genuinely robust vs. overfit to recent data.

Uses each strategy's default/deployed parameters with 10 contracts normalized.
"""

import sys
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

# Import all strategies
from ifvg_strategy import IFVGRetestStrategy, IFVGRetestConfig
from brianstonk_strategy import BrianStonkStrategy, BrianStonkConfig
from magicline_strategy import MagicLineStrategy, MagicLineConfig
from swingreclaim_strategy import SwingReclaimStrategy, SwingReclaimConfig
from jadecap_strategy import JadeCapStrategy, JadeCapConfig
from lb_short_strategy import LBShortStrategy, LBShortConfig
from williams_r_strategy import WilliamsRStrategy, WilliamsRConfig
from donchian_strategy import DonchianStrategy, DonchianConfig
from bollinger_mr_strategy import BollingerMRStrategy, BollingerMRConfig
from atr_breakout_strategy import ATRBreakoutStrategy, ATRBreakoutConfig
from displacement_strategy import DisplacementStrategy, DisplacementConfig


ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
STARTING_CAPITAL = 25_000.0
RESULTS_DIR = Path(__file__).parent / "results" / "regime_test_all"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SIM = Venue("SIM")

# 2-year regime windows
WINDOWS = [
    ("2010-01-01", "2012-01-01"),  # Post-GFC recovery
    ("2012-01-01", "2014-01-01"),  # Low vol grind up
    ("2014-01-01", "2016-01-01"),  # Mixed / China scare
    ("2016-01-01", "2018-01-01"),  # Trump rally
    ("2018-01-01", "2020-01-01"),  # Vol spike + trade wars
    ("2020-01-01", "2022-01-01"),  # COVID crash + recovery
    ("2022-01-01", "2024-01-01"),  # Bear market + recovery
    ("2024-01-01", "2026-01-01"),  # Recent
]

CONTRACTS = 10  # Normalized for fair comparison


# ==================== Strategy Factory Functions ====================

def make_ifvg(es, bar_type, tag):
    config = IFVGRetestConfig(
        instrument_id=es.id, bar_type=bar_type,
        enable_long=True, enable_short=True,
        shadow_threshold_pct=20.0, max_wait_bars=20,
        max_trades_day=3, contracts=CONTRACTS,
        stop_buffer_ticks=40, stop_max_pts=40.0,
        be_enabled=True, be_trigger_pts=10.0,
        tp1_points=25.0, tp1_pct=50, trail_points=10.0,
        eod_time=1640, order_id_tag=tag,
    )
    return IFVGRetestStrategy(config=config)


def make_brianstonk(es, bar_type, tag):
    config = BrianStonkConfig(
        instrument_id=es.id, bar_type=bar_type,
        enable_long=True, enable_short=True,
        enable_breaker=True, enable_ifvg=True, enable_ob=True, enable_unicorn=False,
        trade_start=930, trade_end=1530,
        max_trades_day=6, cooldown_minutes=5, forced_flat_time=1555,
        require_intraday_align=False, htf_filter_mode=1, intraday_ma_period=21,
        pivot_left=2, pivot_right=2,
        require_draw_target=True, use_session_liquidity=True, use_swing_liquidity=True,
        ob_min_candles=2, ob_mean_threshold=True,
        breaker_require_sweep=True, breaker_require_displacement=True,
        tight_breaker_threshold=10.0, fvg_min_gap=2.0, fvg_ce_respect=True,
        stop_default=20.0, stop_min=18.0, stop_max=25.0, stop_override_to_structure=True,
        be_enabled=True, be_trigger_pts=10.0,
        contracts=CONTRACTS, target_r=1.0,
        partial_enabled=False, runner_enabled=True,
        eod_time=1555, order_id_tag=tag,
    )
    return BrianStonkStrategy(config=config)


def make_magicline(es, bar_type, tag):
    config = MagicLineConfig(
        instrument_id=es.id, bar_type=bar_type,
        length=20, touch_tolerance_ticks=4, zone_buffer_pts=1.0,
        came_from_pts=5.0, came_from_lookback=10,
        ema_filter_enabled=True, ema_period=21,
        trade_session_enabled=True, trade_start=200, trade_end=1600,
        max_trades_per_day=3, stoploss_mode=1, stop_buffer_ticks=20,
        contracts=CONTRACTS, be_enabled=True, be_trigger_pts=10.0,
        tp1_r=3.0, tp2_r=10.0, partial_enabled=True, partial_pct=25,
        eod_time=1640, order_id_tag=tag,
    )
    return MagicLineStrategy(config=config)


def make_swingreclaim(es, bar_type, tag):
    config = SwingReclaimConfig(
        instrument_id=es.id, bar_type=bar_type,
        enable_long=True, enable_short=True,
        strength=45, reclaim_window=20,
        max_trades_day=3, session_enabled=False,
        contracts=CONTRACTS, stop_buffer_ticks=4,
        stop_min_pts=2.0, stop_max_pts=40.0,
        be_enabled=True, be_trigger_pts=10.0,
        tp1_points=20.0, tp1_pct=50, trail_points=15.0,
        eod_time=1640, order_id_tag=tag,
    )
    return SwingReclaimStrategy(config=config)


def make_jadecap(es, bar_type, tag):
    config = JadeCapConfig(
        instrument_id=es.id, bar_type=bar_type,
        setup_mode=1, enable_long=True, enable_short=True,
        trade_window_always_on=True, trade_start=1800, trade_end=1230,
        kill_zone_preset=3, kz_custom_start=100, kz_custom_end=1130,
        eod_close_enabled=True, eod_close_time=1640,
        max_trades_per_day=1, max_trades_per_side=1,
        one_trade_at_a_time=True, allow_opposite_side=True,
        contracts=CONTRACTS,
        mmbm_ssl_ref=0, mmsm_bsl_ref=0,
        liq_session_start=2000, liq_session_end=0,
        mmbm_pwl_enabled=False, mmbm_major_swing_enabled=True,
        mmsm_pwh_enabled=True, mmsm_major_swing_high_enabled=True,
        major_swing_lookback=500, require_deeper_liq=True,
        sweep_min_ticks=2, require_close_back=True,
        pivot_strength=10, entry_model=1, fvg_min_ticks=2,
        max_bars_to_fill=30, confirmation_strictness=0, require_mss_close=True,
        stoploss_enabled=True, stoploss_mode=0, stoploss_ticks=40,
        exit_model=2, rr_multiple=3.0, partial_enabled=True, partial_pct=25,
        order_id_tag=tag,
    )
    return JadeCapStrategy(config=config)


def make_lb_short(es, bar_type, tag):
    config = LBShortConfig(
        instrument_id=es.id, bar_type=bar_type,
        length=20, rth_start=930, rth_end=1600, eod_time=1640,
        max_trades_per_day=1, contracts=CONTRACTS,
        stop_buffer_ticks=20, be_enabled=True, be_trigger_pts=10.0,
        tp1_pts=15.0, partial_pct=25, trail_pts=5.0,
        ema_filter_enabled=True, ema_period=50,
        order_id_tag=tag,
    )
    return LBShortStrategy(config=config)


def make_williams(es, bar_type, tag):
    config = WilliamsRConfig(
        instrument_id=es.id, bar_type=bar_type,
        entry_mult=0.60, stop_mult=0.30, target_rr=3.0,
        entry_start=935, entry_end=1530,
        max_trades_per_day=1, eod_time=1640,
        contracts=CONTRACTS, order_id_tag=tag,
    )
    return WilliamsRStrategy(config=config)


def make_donchian(es, bar_type, tag):
    config = DonchianConfig(
        instrument_id=es.id, bar_type=bar_type,
        or_end_time=945, atr_period=14,
        atr_stop_mult=0.50, atr_tp_mult=0.0,
        trend_filter_enabled=True, trend_lookback=5,
        max_trades_per_day=1, entry_end=1300, eod_time=1640,
        contracts=CONTRACTS, order_id_tag=tag,
    )
    return DonchianStrategy(config=config)


def make_bollinger_mr(es, bar_type, tag):
    config = BollingerMRConfig(
        instrument_id=es.id, bar_type=bar_type,
        displacement_pct=0.0035, adr_period=14,
        adr_stop_mult=1.5, adr_tp_mult=0.0, tp_at_first_bar=True,
        trend_filter_enabled=False, entry_start=940, entry_end=1300,
        max_trades_per_day=1, eod_time=1640,
        contracts=CONTRACTS, order_id_tag=tag,
    )
    return BollingerMRStrategy(config=config)


def make_pivot_mr(es, bar_type, tag):
    config = ATRBreakoutConfig(
        instrument_id=es.id, bar_type=bar_type,
        atr_period=14, atr_stop_mult=1.5,
        entry_start=935, entry_end=1300,
        max_trades_per_day=1, eod_time=1640,
        trend_filter_enabled=True, trend_filter_days=5,
        contracts=CONTRACTS, order_id_tag=tag,
    )
    return ATRBreakoutStrategy(config=config)


def make_displacement(es, bar_type, tag):
    config = DisplacementConfig(
        instrument_id=es.id, bar_type=bar_type,
        lookback=10, displacement_mult=2.0, target_rr=3.0,
        trail_after_rr=0.0, trail_points=0.0,
        max_trades_per_day=1, entry_end=1530, eod_time=1640,
        contracts=CONTRACTS, order_id_tag=tag,
    )
    return DisplacementStrategy(config=config)


# Strategy registry: name → (factory_func, description)
STRATEGIES = {
    "IFVG":          (make_ifvg,         "IFVG Retest (3-bar zone retest)"),
    "BrianStonk":    (make_brianstonk,   "BrianStonk ICT (OB/BR/IFVG multi-entry)"),
    "MagicLine":     (make_magicline,    "MagicLine (long-only LB bounce)"),
    "SwingReclaim":  (make_swingreclaim, "Swing Reclaim (break-then-reclaim)"),
    "JadeCap":       (make_jadecap,      "JadeCap ICT (sweep→MSS→FVG)"),
    "LB_Short":      (make_lb_short,     "LB Short (short-only LB break)"),
    "Williams_VB":   (make_williams,     "Williams VB (range breakout)"),
    "ORB":           (make_donchian,     "Opening Range Breakout"),
    "Bollinger_MR":  (make_bollinger_mr, "First-Bar Mean Reversion"),
    "Pivot_MR":      (make_pivot_mr,     "Pivot Point Mean Reversion"),
    "Displacement":  (make_displacement, "Displacement Candle (2x range)"),
}


# ==================== Backtest Runner ====================

def run_one(strategy_name, factory_fn, es, bar_type, bars, window_idx, start, end):
    """Run one strategy on one window. Returns metrics dict or None."""
    tag = f"{strategy_name[:4]}{window_idx:02d}"

    engine_config = BacktestEngineConfig(
        trader_id=f"REG-{tag}",
        logging=LoggingConfig(log_level="ERROR"),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

    engine.add_venue(
        venue=SIM,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(STARTING_CAPITAL, USD)],
    )
    engine.add_instrument(es)
    engine.add_data(bars)

    try:
        strategy = factory_fn(es, bar_type, tag)
        engine.add_strategy(strategy)
        engine.run()
    except Exception as e:
        print(f"    ERROR: {e}")
        engine.reset()
        engine.dispose()
        return None

    result = {
        "strategy": strategy_name, "start": start, "end": end,
        "trades": 0, "pnl": 0, "win_rate": 0, "pf": 0,
        "sharpe": 0, "max_dd": 0, "roi": 0, "calmar": 0,
    }

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
            roi = (total_pnl / STARTING_CAPITAL) * 100
            calmar = abs(total_pnl / max_dd) if max_dd != 0 else 0

            result.update({
                "trades": len(pnls), "pnl": total_pnl, "win_rate": win_rate,
                "pf": pf, "sharpe": sharpe, "max_dd": max_dd,
                "roi": roi, "calmar": calmar,
            })

    engine.reset()
    engine.dispose()
    return result


# ==================== Main ====================

def main():
    print("=" * 100)
    print("MULTI-STRATEGY REGIME ROBUSTNESS TEST")
    print(f"Testing {len(STRATEGIES)} strategies x {len(WINDOWS)} windows = {len(STRATEGIES)*len(WINDOWS)} backtests")
    print(f"All strategies use {CONTRACTS} contracts, $25K starting capital")
    print("=" * 100)

    es = create_es_instrument(venue=SIM, multiplier=50)

    # Pre-load bars for each window (load once, reuse across strategies)
    window_data = {}
    for idx, (start, end) in enumerate(WINDOWS):
        label = f"{start[:4]}-{end[:4]}"
        print(f"\nLoading data for {label}...")
        bars, bar_type = load_es_bars(
            zip_path=ES_ZIP_PATH,
            instrument=es,
            start_date=start,
            end_date=end,
            bar_minutes=5,
        )
        window_data[idx] = (bars, bar_type, start, end, label)
        print(f"  {len(bars):,} 5-min bars loaded")

    all_results = []
    total_tests = len(STRATEGIES) * len(WINDOWS)
    test_num = 0

    for strat_name, (factory_fn, desc) in STRATEGIES.items():
        print(f"\n{'='*80}")
        print(f"STRATEGY: {strat_name} — {desc}")
        print(f"{'='*80}")

        for widx in range(len(WINDOWS)):
            bars, bar_type, start, end, label = window_data[widx]
            test_num += 1

            sys.stdout.write(f"  [{test_num}/{total_tests}] {label}... ")
            sys.stdout.flush()

            result = run_one(strat_name, factory_fn, es, bar_type, bars, widx, start, end)
            if result is None:
                print("SKIPPED (error)")
                continue

            all_results.append(result)
            r = result
            status = "PASS" if r["pf"] > 1.0 else "FAIL"
            print(f"{status} PF={r['pf']:.2f} PnL=${r['pnl']:>10,.0f} "
                  f"WR={r['win_rate']:.0f}% Sharpe={r['sharpe']:.2f} "
                  f"DD=${r['max_dd']:>10,.0f} Trades={r['trades']}")

    # ==================== Summary ====================
    df = pd.DataFrame(all_results)
    df.to_csv(RESULTS_DIR / "regime_results_all.csv", index=False)

    print(f"\n\n{'='*120}")
    print("REGIME ROBUSTNESS SCOREBOARD")
    print(f"{'='*120}")

    # Per-strategy summary
    scoreboard = []
    for strat_name in STRATEGIES:
        sdf = df[df["strategy"] == strat_name]
        if sdf.empty:
            continue
        profitable = (sdf["pf"] > 1.0).sum()
        total = len(sdf)
        scoreboard.append({
            "Strategy": strat_name,
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
        })

    sb = pd.DataFrame(scoreboard).sort_values("Avg_Sharpe", ascending=False)

    print(f"\n{'Strategy':<15} {'Pass':>6} {'Avg PF':>7} {'Avg Sh':>7} {'Total PnL':>13} "
          f"{'Avg WR%':>8} {'Worst PF':>9} {'Best PF':>8} {'Avg Trd':>8}")
    print("-" * 100)
    for _, r in sb.iterrows():
        print(f"{r['Strategy']:<15} {r['Pass']:.0f}/{r['Total']:.0f}  "
              f"{r['Avg_PF']:>6.2f} {r['Avg_Sharpe']:>6.2f} "
              f"${r['Total_PnL']:>11,.0f} {r['Avg_WR']:>7.1f}% "
              f"{r['Worst_PF']:>8.2f} {r['Best_PF']:>7.2f} {r['Avg_Trades']:>7.0f}")

    sb.to_csv(RESULTS_DIR / "scoreboard.csv", index=False)

    # ==================== Per-strategy detailed table ====================
    for strat_name in STRATEGIES:
        sdf = df[df["strategy"] == strat_name].copy()
        if sdf.empty:
            continue
        print(f"\n--- {strat_name} ---")
        print(f"{'Period':<12} {'Trades':>7} {'PnL':>12} {'WR%':>6} {'PF':>6} "
              f"{'Sharpe':>7} {'MaxDD':>12} {'Status'}")
        for _, r in sdf.iterrows():
            status = "PASS" if r["pf"] > 1.0 else "FAIL"
            print(f"{r['start'][:4]}-{r['end'][:4]:<7} {r['trades']:>7.0f} "
                  f"${r['pnl']:>10,.0f} {r['win_rate']:>5.1f}% {r['pf']:>5.2f} "
                  f"{r['sharpe']:>6.2f} ${r['max_dd']:>10,.0f}  {status}")

    # ==================== Charts ====================
    print("\nGenerating charts...")

    strat_names = list(STRATEGIES.keys())
    window_labels = [f"{s[:4]}-{e[:4]}" for s, e in WINDOWS]

    # 1. Heatmap: PF by strategy × window
    fig, ax = plt.subplots(figsize=(16, 10))
    pf_matrix = np.full((len(strat_names), len(WINDOWS)), np.nan)
    for _, r in df.iterrows():
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
    ax.set_title("Regime Robustness Heatmap — Profit Factor by Strategy x Period",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    heatmap_path = RESULTS_DIR / "regime_heatmap_pf.png"
    fig.savefig(str(heatmap_path), dpi=150)
    plt.close(fig)

    # 2. Heatmap: Sharpe by strategy × window
    fig, ax = plt.subplots(figsize=(16, 10))
    sharpe_matrix = np.full((len(strat_names), len(WINDOWS)), np.nan)
    for _, r in df.iterrows():
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
    ax.set_title("Regime Robustness Heatmap — Sharpe Ratio by Strategy x Period",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    sharpe_path = RESULTS_DIR / "regime_heatmap_sharpe.png"
    fig.savefig(str(sharpe_path), dpi=150)
    plt.close(fig)

    # 3. Scoreboard bar chart: Pass rate + Avg Sharpe
    fig, axes = plt.subplots(1, 3, figsize=(20, 8))

    # Sort by pass rate then avg sharpe
    sb_sorted = sb.sort_values(["Pass%", "Avg_Sharpe"], ascending=[False, False])

    # Pass rate
    ax = axes[0]
    colors = ["green" if p >= 75 else "orange" if p >= 50 else "red" for p in sb_sorted["Pass%"]]
    bars = ax.barh(range(len(sb_sorted)), sb_sorted["Pass%"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(sb_sorted)))
    ax.set_yticklabels(sb_sorted["Strategy"], fontsize=10)
    ax.set_xlabel("Profitable Periods (%)")
    ax.set_title("Regime Pass Rate")
    ax.axvline(75, color="green", linestyle="--", alpha=0.5, linewidth=1)
    ax.axvline(50, color="orange", linestyle="--", alpha=0.5, linewidth=1)
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
    ax.set_xlabel("Average Sharpe Ratio")
    ax.set_title("Avg Sharpe Across Regimes")
    ax.axvline(0, color="black", linewidth=0.5)
    ax.grid(True, alpha=0.3, axis="x")
    ax.invert_yaxis()

    # Total P&L
    ax = axes[2]
    colors = ["green" if p > 0 else "red" for p in sb_sorted["Total_PnL"]]
    ax.barh(range(len(sb_sorted)), sb_sorted["Total_PnL"] / 1000, color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(sb_sorted)))
    ax.set_yticklabels(sb_sorted["Strategy"], fontsize=10)
    ax.set_xlabel("Total P&L (\\$K)")
    ax.set_title("Total P&L Across All Regimes")
    ax.axvline(0, color="black", linewidth=0.5)
    ax.grid(True, alpha=0.3, axis="x")
    ax.invert_yaxis()

    fig.suptitle("Multi-Strategy Regime Robustness Scoreboard", fontsize=14, fontweight="bold")
    fig.tight_layout()
    score_path = RESULTS_DIR / "scoreboard_chart.png"
    fig.savefig(str(score_path), dpi=150)
    plt.close(fig)

    # 4. P&L heatmap
    fig, ax = plt.subplots(figsize=(16, 10))
    pnl_matrix = np.full((len(strat_names), len(WINDOWS)), np.nan)
    for _, r in df.iterrows():
        si = strat_names.index(r["strategy"])
        wi = next(i for i, (s, e) in enumerate(WINDOWS) if s == r["start"])
        pnl_matrix[si, wi] = r["pnl"] / 1000  # in $K

    max_abs = max(abs(np.nanmin(pnl_matrix)), abs(np.nanmax(pnl_matrix)))
    im = ax.imshow(pnl_matrix, aspect="auto", cmap="RdYlGn", vmin=-max_abs, vmax=max_abs)
    ax.set_xticks(range(len(WINDOWS)))
    ax.set_xticklabels(window_labels, rotation=45, ha="right", fontsize=10)
    ax.set_yticks(range(len(strat_names)))
    ax.set_yticklabels(strat_names, fontsize=10)

    for i in range(len(strat_names)):
        for j in range(len(WINDOWS)):
            val = pnl_matrix[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > max_abs * 0.7 else "black"
                ax.text(j, i, f"{val:.0f}K", ha="center", va="center",
                        fontsize=8, fontweight="bold", color=color)

    fig.colorbar(im, ax=ax, label="P&L (\\$K)", shrink=0.8)
    ax.set_title("Regime P&L Heatmap — \\$ Thousands by Strategy x Period",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    pnl_path = RESULTS_DIR / "regime_heatmap_pnl.png"
    fig.savefig(str(pnl_path), dpi=150)
    plt.close(fig)

    print(f"\nCharts saved to {RESULTS_DIR}/")
    print(f"  - {heatmap_path.name}")
    print(f"  - {sharpe_path.name}")
    print(f"  - {score_path.name}")
    print(f"  - {pnl_path.name}")

    # Open key charts
    subprocess.Popen(["cmd", "/c", "start", "", str(heatmap_path)], creationflags=0x08000000)
    subprocess.Popen(["cmd", "/c", "start", "", str(score_path)], creationflags=0x08000000)
    subprocess.Popen(["cmd", "/c", "start", "", str(pnl_path)], creationflags=0x08000000)


if __name__ == "__main__":
    main()
