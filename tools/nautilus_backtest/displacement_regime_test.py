"""
Displacement Candle Strategy — Multi-Regime Robustness Test.

Runs the best config (2.5x, 3:1 RR, 30-bar LB, 1 trade/day)
across every 2-year window from 2008 to 2026 to check for overfitting.
"""

import subprocess
import sys
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
from displacement_strategy import DisplacementStrategy, DisplacementConfig

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
STARTING_CAPITAL = 25_000.0
RESULTS_DIR = Path(__file__).parent / "results" / "displacement_regimes"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Best config from optimization
BEST_CONFIG = {
    "displacement_mult": 2.0,
    "target_rr": 3.0,
    "lookback": 10,
    "max_trades": 1,
}

# 2-year windows
WINDOWS = [
    ("2010-01-01", "2012-01-01"),  # Post-GFC recovery
    ("2012-01-01", "2014-01-01"),  # Low vol grind up
    ("2014-01-01", "2016-01-01"),  # Mixed / China scare
    ("2016-01-01", "2018-01-01"),  # Trump rally
    ("2018-01-01", "2020-01-01"),  # Vol spike + trade wars
    ("2020-01-01", "2022-01-01"),  # COVID crash + recovery
    ("2022-01-01", "2024-01-01"),  # Bear market + recovery
    ("2024-01-01", "2026-01-01"),  # Recent (optimized on)
]


def run_window(start: str, end: str, bars_1min, es, idx: int):
    """Run backtest for one 2-year window."""
    from data_loader import load_es_bars

    SIM = Venue("SIM")

    # Load bars for this window
    bars, bar_type = load_es_bars(
        zip_path=ES_ZIP_PATH,
        instrument=es,
        start_date=start,
        end_date=end,
        bar_minutes=5,
    )

    if len(bars) < 1000:
        print(f"  Skipping {start}-{end}: only {len(bars)} bars")
        return None

    engine_config = BacktestEngineConfig(
        trader_id=f"REGIME-{idx:03d}",
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

    strategy_config = DisplacementConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        lookback=BEST_CONFIG["lookback"],
        displacement_mult=BEST_CONFIG["displacement_mult"],
        target_rr=BEST_CONFIG["target_rr"],
        trail_after_rr=0.0,
        trail_points=0.0,
        max_trades_per_day=BEST_CONFIG["max_trades"],
        entry_end=1530,
        eod_time=1640,
        contracts=10,
        dollars_per_contract=0.0,
        order_id_tag=f"R{idx:02d}",
    )
    strategy = DisplacementStrategy(config=strategy_config)
    engine.add_strategy(strategy)

    engine.run()

    positions_report = engine.trader.generate_positions_report()
    result = {
        "start": start, "end": end, "bars": len(bars),
        "trades": 0, "pnl": 0, "win_rate": 0, "pf": 0,
        "sharpe": 0, "max_dd": 0, "avg_win": 0, "avg_loss": 0,
        "roi": 0, "calmar": 0,
    }

    pnl_series = None

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
                "trades": len(pnls),
                "pnl": total_pnl,
                "win_rate": win_rate,
                "pf": pf,
                "sharpe": sharpe,
                "max_dd": max_dd,
                "avg_win": wins.mean() if len(wins) > 0 else 0,
                "avg_loss": losses.mean() if len(losses) > 0 else 0,
                "roi": roi,
                "calmar": calmar,
            })
            pnl_series = pnls

    engine.reset()
    engine.dispose()

    return result, pnl_series


def main():
    print("=" * 80)
    print("DISPLACEMENT CANDLE — MULTI-REGIME ROBUSTNESS TEST")
    print(f"Config: {BEST_CONFIG['displacement_mult']}x displacement, "
          f"{BEST_CONFIG['target_rr']}:1 RR, {BEST_CONFIG['lookback']}-bar LB, "
          f"{BEST_CONFIG['max_trades']} trade/day")
    print("=" * 80)

    # Pre-create instrument
    SIM = Venue("SIM")
    es = create_es_instrument(venue=SIM, multiplier=50)

    results = []
    all_pnl_series = {}

    for idx, (start, end) in enumerate(WINDOWS):
        label = f"{start[:4]}-{end[:4]}"
        print(f"\n[{idx+1}/{len(WINDOWS)}] Testing {label}...")

        out = run_window(start, end, None, es, idx)
        if out is None:
            continue

        result, pnl_series = out
        results.append(result)
        if pnl_series is not None:
            all_pnl_series[label] = pnl_series

        r = result
        status = "PROFITABLE" if r["pf"] > 1.0 else "UNPROFITABLE"
        print(f"  {status}: PF={r['pf']:.2f}, PnL=${r['pnl']:>10,.0f}, "
              f"WR={r['win_rate']:.1f}%, Sharpe={r['sharpe']:.2f}, "
              f"MaxDD=${r['max_dd']:>10,.0f}, Trades={r['trades']}")

    # Summary table
    df = pd.DataFrame(results)
    df.to_csv(RESULTS_DIR / "regime_results.csv", index=False)

    print(f"\n\n{'='*100}")
    print(f"REGIME ROBUSTNESS SUMMARY")
    print(f"{'='*100}")
    print(f"{'Period':<15} {'Trades':>7} {'PnL':>12} {'WR%':>7} {'PF':>6} {'Sharpe':>7} "
          f"{'MaxDD':>12} {'ROI%':>8} {'Calmar':>7} {'Status'}")
    print("-" * 100)

    profitable_count = 0
    for _, r in df.iterrows():
        status = "PASS" if r["pf"] > 1.0 else "FAIL"
        if r["pf"] > 1.0:
            profitable_count += 1
        print(f"{r['start'][:4]}-{r['end'][:4]:<10} {r['trades']:>7.0f} ${r['pnl']:>10,.0f} "
              f"{r['win_rate']:>6.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
              f"${r['max_dd']:>10,.0f} {r['roi']:>7.1f}% {r['calmar']:>6.2f}  {status}")

    print("-" * 100)
    print(f"Profitable periods: {profitable_count}/{len(df)} ({profitable_count/len(df)*100:.0f}%)")
    print(f"Avg PF across all periods: {df['pf'].mean():.2f}")
    print(f"Avg Sharpe across all periods: {df['sharpe'].mean():.2f}")
    print(f"Total P&L (all periods): ${df['pnl'].sum():,.0f}")
    print(f"Worst single period: {df.loc[df['pf'].idxmin(), 'start'][:4]}-{df.loc[df['pf'].idxmin(), 'end'][:4]} (PF={df['pf'].min():.2f})")
    print(f"Best single period: {df.loc[df['pf'].idxmax(), 'start'][:4]}-{df.loc[df['pf'].idxmax(), 'end'][:4]} (PF={df['pf'].max():.2f})")

    # ===== Chart: PF by period =====
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    periods = [f"{r['start'][:4]}-{r['end'][:4]}" for _, r in df.iterrows()]

    # 1. Profit Factor by period
    ax = axes[0, 0]
    colors = ["green" if pf > 1.0 else "red" for pf in df["pf"]]
    ax.bar(range(len(df)), df["pf"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.axhline(1.0, color="red", linestyle="--", linewidth=1)
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Profit Factor")
    ax.set_title("Profit Factor by 2-Year Period")
    ax.grid(True, alpha=0.3, axis="y")

    # 2. P&L by period
    ax = axes[0, 1]
    colors = ["green" if p > 0 else "red" for p in df["pnl"]]
    ax.bar(range(len(df)), df["pnl"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("P&L (\\$)")
    ax.set_title("Total P&L by 2-Year Period")
    ax.grid(True, alpha=0.3, axis="y")

    # 3. Sharpe by period
    ax = axes[1, 0]
    colors = ["green" if s > 0 else "red" for s in df["sharpe"]]
    ax.bar(range(len(df)), df["sharpe"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="red", linestyle="--", linewidth=1)
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Sharpe Ratio")
    ax.set_title("Sharpe Ratio by 2-Year Period")
    ax.grid(True, alpha=0.3, axis="y")

    # 4. Win Rate + Trades by period
    ax = axes[1, 1]
    ax.bar(range(len(df)), df["win_rate"], color="steelblue", alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.axhline(50, color="red", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Win Rate (%)")
    ax.set_title("Win Rate by 2-Year Period")
    ax.grid(True, alpha=0.3, axis="y")
    for i, t in enumerate(df["trades"]):
        ax.text(i, df["win_rate"].iloc[i] + 1, f"n={int(t)}", ha="center", fontsize=8)

    fig.suptitle(f"Displacement Candle — Regime Robustness (2.0x, 3:1 RR, 10-bar LB)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    chart_path = RESULTS_DIR / "regime_robustness.png"
    fig.savefig(str(chart_path), dpi=150)
    plt.close(fig)
    print(f"\nRegime chart saved to {chart_path}")

    # ===== Chart: Overlaid equity curves =====
    fig, ax = plt.subplots(figsize=(14, 7))
    for label, pnls in all_pnl_series.items():
        equity = pnls.cumsum().values
        ax.plot(range(len(equity)), equity, linewidth=1.2, label=label)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative P&L (\\$)")
    ax.set_title("Displacement Candle — Equity Curves Across Regimes")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    equity_path = RESULTS_DIR / "regime_equity_curves.png"
    fig.savefig(str(equity_path), dpi=150)
    plt.close(fig)
    print(f"Equity curves chart saved to {equity_path}")

    # Open both charts
    subprocess.Popen(["cmd", "/c", "start", "", str(chart_path)], creationflags=0x08000000)
    subprocess.Popen(["cmd", "/c", "start", "", str(equity_path)], creationflags=0x08000000)


if __name__ == "__main__":
    main()
