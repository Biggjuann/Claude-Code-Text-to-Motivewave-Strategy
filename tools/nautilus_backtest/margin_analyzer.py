"""Margin analysis engine for AMP Futures backtesting.

Post-backtest analysis: walks bar data and fill history to detect
margin violations based on AMP Futures margin requirements.

AMP Margin Rules:
  - Day trade margin: ES=$400, MES=$40 (applies during all trading hours)
  - Accounts > $100K: day trade margins doubled
  - Around major economic events: 25% of exchange margin required per contract
    (ES=$6,647, MES=$665)
  - Exchange margin (ES=$26,586, MES=$2,659) only for overnight holds — not
    applicable since all strategies flatten before session close
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytz

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from economic_calendar import load_economic_events, get_elevated_margin_windows, is_elevated_margin

ET = pytz.timezone("America/New_York")
UTC = pytz.utc

# AMP Futures margin requirements
MARGINS = {
    "ES": {"day_trade": 400, "exchange": 26_586, "elevated": 6_647},
    "MES": {"day_trade": 40, "exchange": 2_659, "elevated": 665},
}


@dataclass
class MarginViolation:
    timestamp: datetime
    timestamp_et: datetime
    equity: float
    required_margin: float
    shortfall: float
    contracts: int
    margin_type: str  # "day_trade", "exchange", "elevated"
    event_type: str   # None or "FOMC", "NFP", etc.
    bar_price: float


@dataclass
class MarginAnalysisResult:
    total_bars: int
    total_bars_in_position: int
    violations: list
    max_shortfall: float
    worst_violation_time: datetime
    margin_calls: int
    pct_bars_in_violation: float
    elevated_margin_violations: int
    equity_series: pd.DataFrame  # timestamp_et, equity, required_margin, position_qty
    summary: dict = field(default_factory=dict)


def bars_to_dataframe(bars) -> pd.DataFrame:
    """Convert NautilusTrader Bar objects to pandas DataFrame.

    Returns DataFrame indexed by UTC timestamp with columns: open, high, low, close.
    """
    records = []
    for bar in bars:
        ts_utc = pd.Timestamp(bar.ts_event, unit="ns", tz=UTC)
        records.append({
            "timestamp": ts_utc,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
        })
    df = pd.DataFrame(records)
    df = df.set_index("timestamp").sort_index()
    return df


def parse_fills(fills_csv: str) -> pd.DataFrame:
    """Parse fills.csv into a clean fill timeline.

    Returns DataFrame with columns: timestamp, side, qty, price.
    """
    df = pd.read_csv(fills_csv)

    records = []
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts_last"])
        if ts.tzinfo is None:
            ts = ts.tz_localize(UTC)
        records.append({
            "timestamp": ts,
            "side": row["side"],
            "qty": float(row["filled_qty"]),
            "price": float(row["avg_px"]),
        })

    result = pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)
    return result


def build_position_timeline(fills_df: pd.DataFrame) -> list[dict]:
    """Reconstruct position state changes from fills (NETTING mode).

    Returns list of dicts: {timestamp, net_qty, direction, avg_entry_price}.
    Positive net_qty = long, negative = short, 0 = flat.
    """
    timeline = []
    net_qty = 0.0
    avg_entry = 0.0

    for _, fill in fills_df.iterrows():
        ts = fill["timestamp"]
        side = fill["side"]
        qty = fill["qty"]
        price = fill["price"]

        if side == "BUY":
            if net_qty < 0:
                # Closing short (partial or full)
                close_qty = min(qty, abs(net_qty))
                net_qty += close_qty
                remaining = qty - close_qty
                if remaining > 0:
                    # Flipped to long
                    avg_entry = price
                    net_qty += remaining
            else:
                # Adding to long or opening long
                if net_qty == 0:
                    avg_entry = price
                else:
                    avg_entry = (avg_entry * net_qty + price * qty) / (net_qty + qty)
                net_qty += qty
        else:  # SELL
            if net_qty > 0:
                # Closing long (partial or full)
                close_qty = min(qty, net_qty)
                net_qty -= close_qty
                remaining = qty - close_qty
                if remaining > 0:
                    # Flipped to short
                    avg_entry = price
                    net_qty -= remaining
            else:
                # Adding to short or opening short
                if net_qty == 0:
                    avg_entry = price
                else:
                    avg_entry = (avg_entry * abs(net_qty) + price * qty) / (abs(net_qty) + qty)
                net_qty -= qty

        direction = "LONG" if net_qty > 0 else ("SHORT" if net_qty < 0 else "FLAT")
        timeline.append({
            "timestamp": ts,
            "net_qty": net_qty,
            "direction": direction,
            "avg_entry_price": avg_entry,
        })

    return timeline


def get_margin_requirement(
    contracts: int,
    instrument: str,
    timestamp_et: datetime,
    equity: float,
    windows: list[tuple],
    timestamp_utc=None,
) -> tuple:
    """Compute required margin for the given position at a point in time.

    All strategies flatten before session close, so exchange margin never applies.
    During economic events, AMP requires 25% of exchange margin per contract.

    Returns (required_margin, margin_type, event_type).
    """
    if contracts == 0:
        return 0.0, "none", None

    margins = MARGINS.get(instrument, MARGINS["ES"])
    abs_contracts = abs(contracts)

    # Check elevated margin (economic events) — 25% of exchange margin
    if timestamp_utc is not None:
        elevated, event_type, _ = is_elevated_margin(timestamp_utc, windows)
        if elevated:
            required = margins["elevated"] * abs_contracts
            return required, "elevated", event_type

    # Day trade margin (applies during all trading hours)
    base = margins["day_trade"]
    # Double for accounts > $100K
    if equity > 100_000:
        base *= 2
    required = base * abs_contracts

    return required, "day_trade", None


def analyze_margin(
    fills_csv: str,
    positions_csv: str,
    bars: list,
    starting_capital: float,
    multiplier: int,
    instrument: str = None,
) -> MarginAnalysisResult:
    """Main margin analysis entry point.

    Args:
        fills_csv: Path to fills.csv from backtest
        positions_csv: Path to positions.csv from backtest
        bars: NautilusTrader Bar objects (already in memory)
        starting_capital: Starting account balance
        multiplier: Contract multiplier ($50 for ES, $5 for MES)
        instrument: "ES" or "MES" (auto-detected from multiplier if None)
    """
    if instrument is None:
        instrument = "MES" if multiplier <= 5 else "ES"

    # 1. Parse fills and build position timeline
    fills_df = parse_fills(fills_csv)
    timeline = build_position_timeline(fills_df)

    if not timeline:
        return MarginAnalysisResult(
            total_bars=len(bars), total_bars_in_position=0,
            violations=[], max_shortfall=0, worst_violation_time=None,
            margin_calls=0, pct_bars_in_violation=0,
            elevated_margin_violations=0, equity_series=pd.DataFrame(),
            summary={"status": "PASS", "reason": "No trades"},
        )

    # 2. Convert bars to DataFrame with ET timestamps
    bar_df = bars_to_dataframe(bars)
    bar_df["timestamp_et"] = bar_df.index.tz_convert(ET)

    # 3. Parse positions for realized P&L tracking
    pos_df = pd.read_csv(positions_csv)
    realized_pnls = []
    for _, row in pos_df.iterrows():
        ts_closed = pd.Timestamp(row["ts_closed"])
        if ts_closed.tzinfo is None:
            ts_closed = ts_closed.tz_localize(UTC)
        pnl = float(str(row["realized_pnl"]).replace(" USD", "").replace(",", ""))
        realized_pnls.append({"timestamp": ts_closed, "realized_pnl": pnl})
    realized_df = pd.DataFrame(realized_pnls).sort_values("timestamp").reset_index(drop=True)

    # 4. Load economic calendar and compute elevated margin windows
    events = load_economic_events()
    start_str = bar_df.index[0].strftime("%Y-%m-%d")
    end_str = bar_df.index[-1].strftime("%Y-%m-%d")
    windows = get_elevated_margin_windows(events, start_str, end_str)

    # 5. Walk bars chronologically
    violations = []
    equity_records = []
    bars_in_position = 0
    cumulative_realized = 0.0
    realized_idx = 0

    # Build a position lookup: for each bar, find the most recent position state
    # Convert timeline to a list of (timestamp, net_qty, avg_entry)
    tl_timestamps = [t["timestamp"] for t in timeline]
    tl_net_qty = [t["net_qty"] for t in timeline]
    tl_avg_entry = [t["avg_entry_price"] for t in timeline]

    current_pos_idx = -1  # index into timeline
    current_net_qty = 0.0
    current_avg_entry = 0.0

    for bar_ts, bar_row in bar_df.iterrows():
        bar_ts_utc = bar_ts
        bar_ts_et = bar_row["timestamp_et"]
        bar_close = bar_row["close"]

        # Advance position timeline up to this bar
        while (current_pos_idx + 1 < len(tl_timestamps) and
               tl_timestamps[current_pos_idx + 1] <= bar_ts_utc):
            current_pos_idx += 1
            current_net_qty = tl_net_qty[current_pos_idx]
            current_avg_entry = tl_avg_entry[current_pos_idx]

        # Advance realized P&L up to this bar
        while (realized_idx < len(realized_df) and
               realized_df.iloc[realized_idx]["timestamp"] <= bar_ts_utc):
            cumulative_realized += realized_df.iloc[realized_idx]["realized_pnl"]
            realized_idx += 1

        # Compute equity
        abs_qty = abs(current_net_qty)
        if abs_qty > 0:
            bars_in_position += 1
            # Unrealized P&L from current position
            if current_net_qty > 0:  # Long
                unrealized = (bar_close - current_avg_entry) * abs_qty * multiplier
            else:  # Short
                unrealized = (current_avg_entry - bar_close) * abs_qty * multiplier
            equity = starting_capital + cumulative_realized + unrealized
        else:
            equity = starting_capital + cumulative_realized
            unrealized = 0.0

        # Get margin requirement
        contracts_int = int(round(abs_qty))
        required, margin_type, event_type = get_margin_requirement(
            contracts_int, instrument, bar_ts_et, equity, windows,
            timestamp_utc=bar_ts_utc,
        )

        # Record equity series
        equity_records.append({
            "timestamp_utc": bar_ts_utc,
            "timestamp_et": bar_ts_et,
            "equity": equity,
            "required_margin": required,
            "position_qty": current_net_qty,
            "margin_type": margin_type,
            "bar_close": bar_close,
        })

        # Check for violation
        if abs_qty > 0 and equity < required:
            shortfall = equity - required
            violations.append(MarginViolation(
                timestamp=bar_ts_utc,
                timestamp_et=bar_ts_et,
                equity=equity,
                required_margin=required,
                shortfall=shortfall,
                contracts=contracts_int,
                margin_type=margin_type,
                event_type=event_type,
                bar_price=bar_close,
            ))

    # 6. Aggregate results
    equity_series = pd.DataFrame(equity_records)

    max_shortfall = min((v.shortfall for v in violations), default=0.0)
    worst_time = None
    if violations:
        worst = min(violations, key=lambda v: v.shortfall)
        worst_time = worst.timestamp_et

    elevated_violations = sum(1 for v in violations if v.margin_type == "elevated")
    pct_violation = (len(violations) / bars_in_position * 100) if bars_in_position > 0 else 0

    # Count distinct margin call "events" (cluster violations within 1 hour)
    margin_calls = 0
    if violations:
        margin_calls = 1
        last_call_time = violations[0].timestamp
        for v in violations[1:]:
            if (v.timestamp - last_call_time).total_seconds() > 3600:
                margin_calls += 1
                last_call_time = v.timestamp

    status = "PASS" if margin_calls == 0 else "*** FAIL ***"

    summary = {
        "status": status,
        "instrument": instrument,
        "multiplier": multiplier,
        "starting_capital": starting_capital,
        "margin_calls": margin_calls,
        "total_violations": len(violations),
        "elevated_violations": elevated_violations,
        "max_shortfall": max_shortfall,
    }

    return MarginAnalysisResult(
        total_bars=len(bar_df),
        total_bars_in_position=bars_in_position,
        violations=violations,
        max_shortfall=max_shortfall,
        worst_violation_time=worst_time,
        margin_calls=margin_calls,
        pct_bars_in_violation=pct_violation,
        elevated_margin_violations=elevated_violations,
        equity_series=equity_series,
        summary=summary,
    )


def print_margin_report(result: MarginAnalysisResult, label: str = ""):
    """Print formatted margin analysis report to console."""
    s = result.summary
    instrument = s.get("instrument", "ES")
    margins = MARGINS.get(instrument, MARGINS["ES"])

    print()
    print("=" * 60)
    print(f"MARGIN ANALYSIS{(' — ' + label) if label else ''}")
    print("=" * 60)

    status_str = s["status"]
    if result.margin_calls > 0:
        status_str += f" ({result.margin_calls} margin call{'s' if result.margin_calls != 1 else ''})"
    print(f"Status:  {status_str}")

    print(f"Instrument: {instrument} (${s['multiplier']}/pt) | "
          f"Day: ${margins['day_trade']:,} | Elevated (25% exch): ${margins['elevated']:,}")
    print(f"Starting Capital: ${s['starting_capital']:,.0f} | "
          f"Bars in Position: {result.total_bars_in_position:,} / {result.total_bars:,} "
          f"({result.total_bars_in_position / result.total_bars * 100:.1f}%)")

    if not result.violations:
        print("\nNo margin violations detected.")
        print("=" * 60)
        return

    print(f"\n--- Margin Violations ({len(result.violations):,} bars, "
          f"{result.pct_bars_in_violation:.1f}% of position bars) ---")

    # Show distinct margin call events (first violation in each cluster)
    shown = []
    if result.violations:
        shown.append(result.violations[0])
        last_time = result.violations[0].timestamp
        for v in result.violations[1:]:
            if (v.timestamp - last_time).total_seconds() > 3600:
                shown.append(v)
                last_time = v.timestamp

    header = f"{'#':<3} {'Timestamp (ET)':<22} {'Equity':>10} {'Required':>10} {'Shortfall':>10} {'Type':<10} {'Event'}"
    print(header)
    for i, v in enumerate(shown[:20], 1):
        ts_str = v.timestamp_et.strftime("%Y-%m-%d %H:%M")
        event_str = v.event_type or ""
        print(f"{i:<3} {ts_str:<22} ${v.equity:>9,.0f} ${v.required_margin:>9,.0f} "
              f"${v.shortfall:>9,.0f} {v.margin_type:<10} {event_str}")

    if len(shown) > 20:
        print(f"  ... and {len(shown) - 20} more margin call events")

    all_elevated = all(v.margin_type == "elevated" for v in result.violations)
    if all_elevated and result.elevated_margin_violations > 0:
        print(f"\nMax Shortfall: ${result.max_shortfall:,.0f} | All violations during economic events.")
    else:
        print(f"\nMax Shortfall: ${result.max_shortfall:,.0f} | "
              f"Elevated: {result.elevated_margin_violations} | "
              f"Day/Exchange: {len(result.violations) - result.elevated_margin_violations}")

    print("=" * 60)


def save_margin_summary(result: MarginAnalysisResult, output_dir: str) -> Path:
    """Save margin analysis summary as JSON for dashboard consumption."""
    s = result.summary
    instrument = s.get("instrument", "ES")
    margins = MARGINS.get(instrument, MARGINS["ES"])

    data = {
        "status": "PASS" if result.margin_calls == 0 else "FAIL",
        "instrument": instrument,
        "multiplier": s["multiplier"],
        "starting_capital": s["starting_capital"],
        "day_trade_margin": margins["day_trade"],
        "elevated_margin": margins["elevated"],
        "margin_calls": result.margin_calls,
        "total_violations": len(result.violations),
        "elevated_violations": result.elevated_margin_violations,
        "max_shortfall": round(result.max_shortfall, 2),
        "total_bars": result.total_bars,
        "bars_in_position": result.total_bars_in_position,
        "pct_bars_in_violation": round(result.pct_bars_in_violation, 2),
    }

    # Top 10 margin call events (first violation per cluster)
    if result.violations:
        events = [result.violations[0]]
        last_time = result.violations[0].timestamp
        for v in result.violations[1:]:
            if (v.timestamp - last_time).total_seconds() > 3600:
                events.append(v)
                last_time = v.timestamp
        data["top_violations"] = [
            {
                "timestamp_et": v.timestamp_et.strftime("%Y-%m-%d %H:%M"),
                "equity": round(v.equity, 2),
                "required": round(v.required_margin, 2),
                "shortfall": round(v.shortfall, 2),
                "type": v.margin_type,
                "event": v.event_type,
            }
            for v in events[:10]
        ]

    out_path = Path(output_dir) / "margin_summary.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    return out_path


def plot_margin_analysis(
    result: MarginAnalysisResult,
    output_dir: str,
    title: str = "Margin Analysis",
) -> Path:
    """Generate 3-panel margin analysis chart.

    Panel 1: Equity vs margin requirement line
    Panel 2: Position size over time
    Panel 3: Margin cushion (equity - required)
    """
    df = result.equity_series
    if df.empty:
        return None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Filter to bars where we're in a position (for panels 1 & 3)
    in_pos = df[df["position_qty"] != 0].copy()

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), height_ratios=[3, 1, 2], sharex=True)

    dates_all = pd.to_datetime(df["timestamp_et"])

    # --- Panel 1: Equity + Margin Requirement ---
    ax1.plot(dates_all, df["equity"], "b-", linewidth=0.8, label="Account Equity", alpha=0.9)

    # Plot margin requirement only when in position
    if not in_pos.empty:
        dates_pos = pd.to_datetime(in_pos["timestamp_et"])
        ax1.plot(dates_pos, in_pos["required_margin"], "r--", linewidth=0.7, label="Required Margin", alpha=0.7)

        # Fill green where equity > required, red where equity < required
        equity_pos = in_pos["equity"].values
        req_pos = in_pos["required_margin"].values
        ax1.fill_between(dates_pos, equity_pos, req_pos,
                         where=equity_pos >= req_pos,
                         facecolor="green", alpha=0.1, interpolate=True)
        ax1.fill_between(dates_pos, equity_pos, req_pos,
                         where=equity_pos < req_pos,
                         facecolor="red", alpha=0.3, interpolate=True)

    # Mark violations
    if result.violations:
        v_dates = [pd.Timestamp(v.timestamp_et) for v in result.violations]
        v_equity = [v.equity for v in result.violations]
        # Only plot a subset of markers to avoid clutter
        step = max(1, len(v_dates) // 50)
        ax1.scatter(v_dates[::step], v_equity[::step], color="red", marker="v", s=30, zorder=5, label="Violation")

    # Shade elevated margin windows
    from economic_calendar import load_economic_events, get_elevated_margin_windows
    events = load_economic_events()
    start_str = df["timestamp_utc"].iloc[0].strftime("%Y-%m-%d")
    end_str = df["timestamp_utc"].iloc[-1].strftime("%Y-%m-%d")
    windows = get_elevated_margin_windows(events, start_str, end_str)
    for w_start, w_end, _, _ in windows:
        w_start_et = w_start.astimezone(ET)
        w_end_et = w_end.astimezone(ET)
        ax1.axvspan(w_start_et, w_end_et, alpha=0.05, color="orange")

    ax1.set_ylabel("Dollars ($)")
    ax1.set_title(title)
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)

    # Stats text
    s = result.summary
    stats_text = (
        f"Status: {s['status']} | Margin Calls: {result.margin_calls} | "
        f"Max Shortfall: ${result.max_shortfall:,.0f} | "
        f"Elevated Violations: {result.elevated_margin_violations}"
    )
    ax1.text(0.02, 0.95, stats_text, transform=ax1.transAxes, fontsize=8,
             verticalalignment="top", bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # --- Panel 2: Position Size ---
    ax2.fill_between(dates_all, df["position_qty"], 0, alpha=0.4,
                     where=df["position_qty"] > 0, facecolor="green", label="Long")
    ax2.fill_between(dates_all, df["position_qty"], 0, alpha=0.4,
                     where=df["position_qty"] < 0, facecolor="red", label="Short")
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.set_ylabel("Contracts")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(True, alpha=0.3)

    # --- Panel 3: Margin Cushion ---
    cushion = df["equity"] - df["required_margin"]
    # Only show cushion when in position
    cushion_masked = cushion.where(df["position_qty"] != 0, 0)
    ax3.fill_between(dates_all, cushion_masked, 0,
                     where=cushion_masked >= 0, facecolor="green", alpha=0.3)
    ax3.fill_between(dates_all, cushion_masked, 0,
                     where=cushion_masked < 0, facecolor="red", alpha=0.4)
    ax3.axhline(y=0, color="black", linewidth=1)
    ax3.set_ylabel("Margin Cushion ($)")
    ax3.set_xlabel("Date (ET)")
    ax3.grid(True, alpha=0.3)

    fig.tight_layout()
    chart_path = output_path / "margin_analysis.png"
    fig.savefig(str(chart_path), dpi=150)
    plt.close(fig)
    print(f"Margin chart saved to {chart_path}")
    return chart_path
