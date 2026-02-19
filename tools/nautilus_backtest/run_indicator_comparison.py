"""Compare the 4 indicator-driven strategies + SPY benchmark."""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot_comparison import plot_comparison, parse_pnl, stats_line

RESULTS_DIR = Path(__file__).parent / "results"
STARTING_CAPITAL = 25_000.0

STRATEGIES = [
    ("williams_r", "Williams %R"),
    ("donchian", "Donchian Channel"),
    ("bollinger_mr", "Bollinger MR"),
    ("atr_breakout", "ATR Breakout"),
]

COLORS = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0", "#607D8B"]
BG_COLORS = ["#BBDEFB", "#FFE0B2", "#C8E6C9", "#F8BBD0", "#E1BEE7", "#CFD8DC"]


def main():
    csv_files = []
    labels = []
    for folder, label in STRATEGIES:
        csv_path = RESULTS_DIR / folder / "positions.csv"
        if csv_path.exists():
            csv_files.append(str(csv_path))
            labels.append(label)
        else:
            print(f"Warning: {csv_path} not found, skipping {label}")

    if not csv_files:
        print("No results found!")
        return

    # Load all strategy data
    series_data = []
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        dates, pnls = parse_pnl(df)
        equity = pnls.cumsum()
        dd = equity - equity.cummax()
        series_data.append((dates, pnls, equity, dd))

    # Get date range from first strategy
    all_dates = pd.concat([s[0] for s in series_data])
    start_date = all_dates.min().strftime("%Y-%m-%d")
    end_date = all_dates.max().strftime("%Y-%m-%d")

    # SPY benchmark
    print(f"Downloading SPY data ({start_date} to {end_date})...")
    spy = yf.download("SPY", start=start_date, end=end_date, progress=False)
    if spy is not None and len(spy) > 0:
        spy_close = spy["Close"].squeeze()
        spy_return = (spy_close / spy_close.iloc[0] - 1) * STARTING_CAPITAL
        spy_dates = spy_close.index.tz_localize(None)
    else:
        spy_dates = None
        spy_return = None
        print("Warning: Could not download SPY data")

    # Build chart
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 11), height_ratios=[3, 1], sharex=True)

    for i, (dates, pnls, equity, dd) in enumerate(series_data):
        color = COLORS[i % len(COLORS)]
        label = labels[i]
        ax1.plot(dates, equity, linewidth=1.3, label=label, color=color)
        ax1.fill_between(dates, equity, alpha=0.05, color=color)
        ax2.fill_between(dates, dd, 0, color=color, alpha=0.25, label=label)

    # SPY overlay
    if spy_dates is not None:
        ax1.plot(spy_dates, spy_return, linewidth=1.5, label="SPY Buy & Hold",
                 color="#607D8B", linestyle="--", alpha=0.8)

    ax1.axhline(y=0, color="black", linewidth=0.5)
    ax1.set_ylabel("Cumulative P&L ($)")
    ax1.set_title(f"Indicator-Driven Strategies Comparison — {start_date} to {end_date} (ES x10, 5-min, $25K)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Stats annotations
    for i, (dates, pnls, equity, dd) in enumerate(series_data):
        bg = BG_COLORS[i % len(BG_COLORS)]
        line = stats_line(pnls, labels[i])
        y_pos = 0.95 - i * 0.065
        ax1.text(0.02, y_pos, line, transform=ax1.transAxes, fontsize=7.5,
                 verticalalignment="top", bbox=dict(boxstyle="round", facecolor=bg, alpha=0.7))

    # SPY stats
    if spy_return is not None:
        spy_final = spy_return.iloc[-1]
        spy_line = f"SPY Buy & Hold: {spy_final:,.0f} return on ${STARTING_CAPITAL:,.0f}"
        y_pos = 0.95 - len(series_data) * 0.065
        ax1.text(0.02, y_pos, spy_line, transform=ax1.transAxes, fontsize=7.5,
                 verticalalignment="top", bbox=dict(boxstyle="round", facecolor="#CFD8DC", alpha=0.7))

    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="lower left", fontsize=8)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    chart_path = RESULTS_DIR / "comparison_indicator_strategies.png"
    fig.savefig(str(chart_path), dpi=150)
    plt.close(fig)
    print(f"\nComparison chart saved to {chart_path}")

    subprocess.Popen(["cmd", "/c", "start", "", str(chart_path)], creationflags=0x08000000)


if __name__ == "__main__":
    main()
