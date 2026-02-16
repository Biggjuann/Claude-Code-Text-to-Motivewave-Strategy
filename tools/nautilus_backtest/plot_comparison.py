"""Multi-strategy equity curve comparison chart."""

import sys
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0"]
BG_COLORS = ["#BBDEFB", "#FFE0B2", "#C8E6C9", "#F8BBD0", "#E1BEE7"]


def parse_pnl(df):
    pnls = df["realized_pnl"].apply(
        lambda x: float(str(x).replace(" USD", "").replace(",", ""))
    )
    dates = pd.to_datetime(df["ts_closed"])
    return dates, pnls


def stats_line(pnls, label):
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    wr = len(wins) / len(pnls) * 100 if len(pnls) else 0
    gw = wins.sum() if len(wins) else 0
    gl = abs(losses.sum()) if len(losses) else 0
    pf = gw / gl if gl > 0 else 0
    sh = (pnls.mean() / pnls.std()) * np.sqrt(252) if len(pnls) > 1 and pnls.std() > 0 else 0
    eq = pnls.cumsum()
    mdd = (eq - eq.cummax()).min()
    return (f"{label}: {eq.iloc[-1]:,.0f} P&L | {len(pnls)} trades | "
            f"{wr:.1f}% WR | PF {pf:.2f} | Sharpe {sh:.2f} | MaxDD {mdd:,.0f}")


def plot_comparison(csv_files: list[str], labels: list[str], title: str = None, output_path: str = None):
    """Plot N equity curves + drawdowns on the same axes."""
    series_data = []
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        dates, pnls = parse_pnl(df)
        equity = pnls.cumsum()
        dd = equity - equity.cummax()
        series_data.append((dates, pnls, equity, dd))

    if title is None:
        title = "Strategy Comparison"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), height_ratios=[3, 1], sharex=True)

    for i, (dates, pnls, equity, dd) in enumerate(series_data):
        color = COLORS[i % len(COLORS)]
        label = labels[i]
        ax1.plot(dates, equity, linewidth=1.2, label=label, color=color)
        ax1.fill_between(dates, equity, alpha=0.06, color=color)
        ax2.fill_between(dates, dd, 0, color=color, alpha=0.3, label=label)

    ax1.axhline(y=0, color="black", linewidth=0.5)
    ax1.set_ylabel("Cumulative P&L ($)")
    ax1.set_title(title)
    ax1.legend(loc="upper left", fontsize=10)
    ax1.grid(True, alpha=0.3)

    # Stats annotations
    for i, (dates, pnls, equity, dd) in enumerate(series_data):
        bg = BG_COLORS[i % len(BG_COLORS)]
        line = stats_line(pnls, labels[i])
        y_pos = 0.95 - i * 0.07
        ax1.text(0.02, y_pos, line, transform=ax1.transAxes, fontsize=8,
                 verticalalignment="top", bbox=dict(boxstyle="round", facecolor=bg, alpha=0.7))

    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="lower left", fontsize=9)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    if output_path:
        chart_path = Path(output_path)
    else:
        chart_path = Path(csv_files[0]).parent.parent / "comparison_equity.png"
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(chart_path), dpi=150)
    plt.close(fig)
    print(f"Comparison chart saved to {chart_path}")
    return chart_path


if __name__ == "__main__":
    import subprocess
    # Usage: python plot_comparison.py csv1,csv2,csv3 label1,label2,label3 [output_path]
    csv_files = sys.argv[1].split(",") if len(sys.argv) > 1 else ["results/brianstonk/positions.csv", "results/positions.csv"]
    labels = sys.argv[2].split(",") if len(sys.argv) > 2 else ["BrianStonk", "IFVG Retest"]
    output = sys.argv[3] if len(sys.argv) > 3 else None
    chart = plot_comparison(csv_files, labels, output_path=output)
    subprocess.Popen(["cmd", "/c", "start", "", str(chart)], creationflags=0x08000000)
