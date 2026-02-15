"""Generate equity curve chart from backtest positions.csv."""

import sys
import subprocess
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_equity(positions_csv: str, title: str = None):
    df = pd.read_csv(positions_csv)
    pnls = df["realized_pnl"].apply(
        lambda x: float(str(x).replace(" USD", "").replace(",", ""))
    )
    dates = pd.to_datetime(df["ts_closed"])

    equity = pnls.cumsum()
    peak = equity.cummax()
    dd = equity - peak

    # Stats
    total_pnl = equity.iloc[-1]
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    win_rate = len(wins) / len(pnls) * 100
    gross_wins = wins.sum() if len(wins) > 0 else 0
    gross_losses = abs(losses.sum()) if len(losses) > 0 else 0
    pf = gross_wins / gross_losses if gross_losses > 0 else 0
    sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252) if len(pnls) > 1 and pnls.std() > 0 else 0

    if title is None:
        title = "IFVG Retest Strategy — Equity Curve"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[3, 1], sharex=True)

    # Equity curve
    ax1.plot(dates, equity, "b-", linewidth=1)
    ax1.fill_between(dates, equity, alpha=0.15, color="blue")
    ax1.axhline(y=0, color="black", linewidth=0.5)
    ax1.set_ylabel("Cumulative P&L ($)")
    ax1.set_title(title)
    ax1.grid(True, alpha=0.3)

    stats_text = (
        f"Total P&L: ${total_pnl:,.0f}  |  Sharpe: {sharpe:.2f}  |  "
        f"Win Rate: {win_rate:.1f}%  |  PF: {pf:.2f}  |  Trades: {len(pnls)}"
    )
    ax1.text(0.02, 0.95, stats_text, transform=ax1.transAxes, fontsize=9,
             verticalalignment="top", bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # Drawdown
    ax2.fill_between(dates, dd, 0, color="red", alpha=0.4)
    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)
    ax2.text(0.02, 0.05, f"Max DD: ${dd.min():,.0f}", transform=ax2.transAxes, fontsize=9,
             verticalalignment="bottom", bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.5))

    fig.tight_layout()
    chart_path = Path(positions_csv).parent / "equity_curve.png"
    fig.savefig(str(chart_path), dpi=150)
    plt.close(fig)
    print(f"Chart saved to {chart_path}")
    return chart_path


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "results/positions.csv"
    title = sys.argv[2] if len(sys.argv) > 2 else None
    chart = plot_equity(csv_path, title)
    subprocess.Popen(["cmd", "/c", "start", "", str(chart)], creationflags=0x08000000)
