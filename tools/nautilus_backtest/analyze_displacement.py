"""
Displacement Candle Strategy — Full Analysis Suite.

Generates: equity+DD, monthly P&L, distribution+DOW, rolling stats,
duration+scatter, monthly heatmap.
"""

import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

RESULTS_DIR = Path(__file__).parent / "results" / "displacement_best"
POSITIONS_CSV = RESULTS_DIR / "positions.csv"
STARTING_CAPITAL = 25_000.0


def load_pnls():
    df = pd.read_csv(POSITIONS_CSV)
    df["pnl"] = df["realized_pnl"].apply(
        lambda x: float(str(x).replace(" USD", "").replace(",", ""))
    )
    df["ts_opened"] = pd.to_datetime(df["ts_opened"])
    df["ts_closed"] = pd.to_datetime(df["ts_closed"])
    df["duration_min"] = (df["ts_closed"] - df["ts_opened"]).dt.total_seconds() / 60
    df["date"] = df["ts_closed"].dt.date
    df["month"] = df["ts_closed"].dt.to_period("M")
    df["dow"] = df["ts_closed"].dt.day_name()
    df["year"] = df["ts_closed"].dt.year
    df["month_num"] = df["ts_closed"].dt.month
    return df


def chart1_equity_dd(df):
    """Equity curve + drawdown."""
    pnls = df["pnl"]
    dates = df["ts_closed"]
    equity = pnls.cumsum()
    peak = equity.cummax()
    dd = equity - peak

    total_pnl = equity.iloc[-1]
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    win_rate = len(wins) / len(pnls) * 100
    gross_wins = wins.sum()
    gross_losses = abs(losses.sum())
    pf = gross_wins / gross_losses if gross_losses > 0 else 0
    sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252) if pnls.std() > 0 else 0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[3, 1], sharex=True)

    ax1.plot(dates, equity, "b-", linewidth=1.2)
    ax1.fill_between(dates, equity, alpha=0.12, color="blue")
    ax1.axhline(y=0, color="black", linewidth=0.5)
    ax1.set_ylabel("Cumulative P&L ($)")
    ax1.set_title("Displacement Candle (2.5x, 3:1 RR, 30-bar LB) — Equity Curve")
    ax1.grid(True, alpha=0.3)

    stats = (f"P&L: \\${total_pnl:,.0f} | Sharpe: {sharpe:.2f} | WR: {win_rate:.1f}% | "
             f"PF: {pf:.2f} | Trades: {len(pnls)} | MaxDD: \\${dd.min():,.0f}")
    ax1.text(0.02, 0.95, stats, transform=ax1.transAxes, fontsize=9,
             verticalalignment="top", bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    ax2.fill_between(dates, dd, 0, color="red", alpha=0.4)
    ax2.set_ylabel("Drawdown ($)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    path = RESULTS_DIR / "chart_equity_dd.png"
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return path


def chart2_monthly_pnl(df):
    """Monthly P&L bar chart."""
    monthly = df.groupby("month")["pnl"].sum()

    fig, ax = plt.subplots(figsize=(14, 6))
    colors = ["green" if v >= 0 else "red" for v in monthly.values]
    x_labels = [str(m) for m in monthly.index]
    bars = ax.bar(range(len(monthly)), monthly.values, color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_ylabel("P&L ($)")
    ax.set_title("Displacement — Monthly P&L")
    ax.grid(True, alpha=0.3, axis="y")

    pos_months = sum(1 for v in monthly.values if v >= 0)
    tot_months = len(monthly)
    ax.text(0.02, 0.95, f"Positive months: {pos_months}/{tot_months} ({pos_months/tot_months*100:.0f}%%)",
            transform=ax.transAxes, fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.tight_layout()
    path = RESULTS_DIR / "chart_monthly_pnl.png"
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return path


def chart3_distribution_dow(df):
    """P&L distribution + day-of-week breakdown."""
    pnls = df["pnl"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Distribution histogram
    ax1.hist(pnls, bins=50, color="steelblue", edgecolor="black", linewidth=0.5, alpha=0.8)
    ax1.axvline(pnls.mean(), color="red", linestyle="--", label=f"Mean: ${pnls.mean():,.0f}")
    ax1.axvline(pnls.median(), color="green", linestyle="--", label=f"Median: ${pnls.median():,.0f}")
    ax1.set_xlabel("Trade P&L ($)")
    ax1.set_ylabel("Frequency")
    ax1.set_title("P&L Distribution")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    # Day of week
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    dow_pnl = df.groupby("dow")["pnl"].agg(["sum", "count", "mean"])
    dow_pnl = dow_pnl.reindex(dow_order)
    colors = ["green" if v >= 0 else "red" for v in dow_pnl["sum"].values]
    ax2.bar(range(len(dow_pnl)), dow_pnl["sum"].values, color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax2.set_xticks(range(len(dow_pnl)))
    ax2.set_xticklabels([d[:3] for d in dow_order], fontsize=9)
    ax2.set_ylabel("Total P&L ($)")
    ax2.set_title("P&L by Day of Week")
    ax2.grid(True, alpha=0.3, axis="y")
    ax2.axhline(0, color="black", linewidth=0.5)

    for i, (_, row) in enumerate(dow_pnl.iterrows()):
        ax2.text(i, row["sum"], f"n={int(row['count'])}", ha="center", va="bottom" if row["sum"] >= 0 else "top", fontsize=8)

    fig.tight_layout()
    path = RESULTS_DIR / "chart_distribution_dow.png"
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return path


def chart4_rolling_stats(df):
    """Rolling 30-trade win rate, PF, and Sharpe."""
    pnls = df["pnl"]
    dates = df["ts_closed"]
    window = 30

    rolling_wr = pnls.rolling(window).apply(lambda x: (x > 0).sum() / len(x) * 100)
    rolling_pf = pnls.rolling(window).apply(
        lambda x: x[x > 0].sum() / abs(x[x <= 0].sum()) if abs(x[x <= 0].sum()) > 0 else 0
    )
    rolling_sharpe = pnls.rolling(window).apply(
        lambda x: (x.mean() / x.std()) * np.sqrt(252) if x.std() > 0 else 0
    )

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    axes[0].plot(dates, rolling_wr, "b-", linewidth=1)
    axes[0].axhline(50, color="red", linestyle="--", alpha=0.5)
    axes[0].set_ylabel("Win Rate (%)")
    axes[0].set_title(f"Rolling {window}-Trade Statistics")
    axes[0].grid(True, alpha=0.3)
    axes[0].set_ylim(0, 100)

    axes[1].plot(dates, rolling_pf, "g-", linewidth=1)
    axes[1].axhline(1.0, color="red", linestyle="--", alpha=0.5)
    axes[1].set_ylabel("Profit Factor")
    axes[1].grid(True, alpha=0.3)
    axes[1].set_ylim(0, 5)

    axes[2].plot(dates, rolling_sharpe, "purple", linewidth=1)
    axes[2].axhline(0, color="red", linestyle="--", alpha=0.5)
    axes[2].set_ylabel("Sharpe Ratio")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    path = RESULTS_DIR / "chart_rolling_stats.png"
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return path


def chart5_duration_scatter(df):
    """Trade duration vs P&L scatter plot."""
    fig, ax = plt.subplots(figsize=(14, 6))

    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] <= 0]

    ax.scatter(wins["duration_min"], wins["pnl"], c="green", alpha=0.5, s=20, label=f"Wins ({len(wins)})")
    ax.scatter(losses["duration_min"], losses["pnl"], c="red", alpha=0.5, s=20, label=f"Losses ({len(losses)})")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("Trade Duration (minutes)")
    ax.set_ylabel("P&L ($)")
    ax.set_title("Trade Duration vs P&L")
    ax.legend()
    ax.grid(True, alpha=0.3)

    avg_win_dur = wins["duration_min"].mean() if len(wins) > 0 else 0
    avg_loss_dur = losses["duration_min"].mean() if len(losses) > 0 else 0
    ax.text(0.02, 0.95, f"Avg Win Dur: {avg_win_dur:.0f}min | Avg Loss Dur: {avg_loss_dur:.0f}min",
            transform=ax.transAxes, fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.tight_layout()
    path = RESULTS_DIR / "chart_duration_scatter.png"
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return path


def chart6_monthly_heatmap(df):
    """Monthly P&L heatmap (year x month)."""
    pivot = df.pivot_table(values="pnl", index="year", columns="month_num", aggfunc="sum", fill_value=0)

    fig, ax = plt.subplots(figsize=(14, 4))
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto",
                   vmin=-max(abs(pivot.values.min()), abs(pivot.values.max())),
                   vmax=max(abs(pivot.values.min()), abs(pivot.values.max())))

    ax.set_xticks(range(len(pivot.columns)))
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ax.set_xticklabels([month_labels[m-1] for m in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if val != 0:
                text_color = "white" if abs(val) > pivot.values.max() * 0.6 else "black"
                ax.text(j, i, f"\\${val:,.0f}", ha="center", va="center", fontsize=7, color=text_color)

    ax.set_title("Monthly P&L Heatmap")
    plt.colorbar(im, ax=ax, label="P&L ($)")

    fig.tight_layout()
    path = RESULTS_DIR / "chart_monthly_heatmap.png"
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return path


def main():
    print("Loading positions data...")
    df = load_pnls()
    print(f"  {len(df)} trades loaded")

    charts = []
    print("\nGenerating charts...")

    charts.append(chart1_equity_dd(df))
    print("  1/6 Equity + Drawdown")

    charts.append(chart2_monthly_pnl(df))
    print("  2/6 Monthly P&L")

    charts.append(chart3_distribution_dow(df))
    print("  3/6 Distribution + DOW")

    charts.append(chart4_rolling_stats(df))
    print("  4/6 Rolling Stats")

    charts.append(chart5_duration_scatter(df))
    print("  5/6 Duration + Scatter")

    charts.append(chart6_monthly_heatmap(df))
    print("  6/6 Monthly Heatmap")

    print(f"\nAll charts saved to {RESULTS_DIR}")

    # Open all charts
    for c in charts:
        subprocess.Popen(["cmd", "/c", "start", "", str(c)], creationflags=0x08000000)

    # === Text Assessment ===
    pnls = df["pnl"]
    equity = pnls.cumsum()
    peak = equity.cummax()
    dd = equity - peak
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    gross_wins = wins.sum()
    gross_losses = abs(losses.sum())
    pf = gross_wins / gross_losses if gross_losses > 0 else 0
    sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252) if pnls.std() > 0 else 0
    roi = (equity.iloc[-1] / STARTING_CAPITAL) * 100

    monthly = df.groupby("month")["pnl"].sum()
    pos_months = sum(1 for v in monthly.values if v >= 0)
    max_consec_loss = 0
    curr_streak = 0
    for p in pnls:
        if p <= 0:
            curr_streak += 1
            max_consec_loss = max(max_consec_loss, curr_streak)
        else:
            curr_streak = 0

    max_consec_win = 0
    curr_streak = 0
    for p in pnls:
        if p > 0:
            curr_streak += 1
            max_consec_win = max(max_consec_win, curr_streak)
        else:
            curr_streak = 0

    calmar = abs(equity.iloc[-1] / dd.min()) if dd.min() != 0 else 0

    print(f"""
{'='*60}
DISPLACEMENT CANDLE STRATEGY — FULL ASSESSMENT
{'='*60}

Configuration:
  Displacement Mult: 2.5x
  Lookback: 30 bars
  Target R:R: 3:1
  Max Trades/Day: 1
  Entry Window: 9:35-15:30 ET
  EOD Flatten: 16:40 ET
  Bar Size: 5-min
  Instrument: ES x10

Performance Summary:
  Period: 2024-01-01 to 2026-01-01 (2 years)
  Total P&L: ${equity.iloc[-1]:>12,.0f}
  ROI: {roi:>10.1f}%
  Starting Capital: ${STARTING_CAPITAL:>10,.0f}
  Final Equity: ${STARTING_CAPITAL + equity.iloc[-1]:>10,.0f}

Risk Metrics:
  Sharpe Ratio: {sharpe:>10.2f}
  Profit Factor: {pf:>10.2f}
  Calmar Ratio: {calmar:>10.2f}
  Max Drawdown: ${dd.min():>10,.0f}
  Max DD %: {dd.min()/(STARTING_CAPITAL + peak.iloc[peak.values.argmax()])*100:>10.1f}%

Trade Statistics:
  Total Trades: {len(pnls):>10}
  Win Rate: {len(wins)/len(pnls)*100:>10.1f}%
  Avg Win: ${wins.mean():>10,.0f}
  Avg Loss: ${losses.mean():>10,.0f}
  Largest Win: ${wins.max():>10,.0f}
  Largest Loss: ${losses.min():>10,.0f}
  Avg Win/Avg Loss: {abs(wins.mean()/losses.mean()):>10.2f}
  Max Consec Wins: {max_consec_win:>10}
  Max Consec Losses: {max_consec_loss:>10}

Monthly:
  Positive Months: {pos_months}/{len(monthly)} ({pos_months/len(monthly)*100:.0f}%)
  Best Month: ${monthly.max():>10,.0f}
  Worst Month: ${monthly.min():>10,.0f}
  Avg Month: ${monthly.mean():>10,.0f}

Duration:
  Avg Trade Duration: {df['duration_min'].mean():>8.0f} min
  Avg Win Duration: {df.loc[wins.index, 'duration_min'].mean():>8.0f} min
  Avg Loss Duration: {df.loc[losses.index, 'duration_min'].mean():>8.0f} min
""")


if __name__ == "__main__":
    main()
