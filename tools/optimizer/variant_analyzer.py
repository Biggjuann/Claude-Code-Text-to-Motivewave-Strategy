"""
Variant Performance Analyzer
Analyzes log files and separates performance by variant based on TP ratios.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Trade:
    """A single trade from the logs."""
    entry_price: float = 0.0
    lb_at_entry: float = 0.0
    initial_stop: float = 0.0
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    exit_type: str = ""
    pnl_points: float = 0.0
    risk_points: float = 0.0
    variant: str = "unknown"


def identify_variant(trade: Trade) -> str:
    """
    Identify which variant a trade came from based on TP ratios.

    V1 (Higher R): TP1=1.5R, TP2=3.0R
    Original/V2/V3: TP1=1.0R, TP2=2.0R

    V2 (Late BE) and V3 (Wide Zone) can't be distinguished from Original by logs alone.
    """
    if trade.risk_points <= 0:
        return "unknown"

    tp1_r = (trade.tp1_price - trade.entry_price) / trade.risk_points
    tp2_r = (trade.tp2_price - trade.entry_price) / trade.risk_points

    # V1 has ~1.5R TP1 and ~3R TP2
    if 1.3 < tp1_r < 1.7 and 2.7 < tp2_r < 3.3:
        return "V1_HIGHER_R"
    # Original/V2/V3 have ~1R TP1 and ~2R TP2
    elif 0.8 < tp1_r < 1.2 and 1.8 < tp2_r < 2.2:
        return "STANDARD_R"  # Original, V2, or V3
    else:
        return f"custom_tp1={tp1_r:.1f}_tp2={tp2_r:.1f}"


def parse_log_with_variants(log_path: str) -> List[Trade]:
    """Parse a log file and classify trades by variant."""
    trades = []

    # Patterns
    entry_signal = re.compile(r"INFO Magic Line: === LONG ENTRY SIGNAL ===")
    entry_details = re.compile(r"INFO Magic Line: Entry: ([\d.]+) \| LB: ([\d.]+)")
    stop_pattern = re.compile(r"INFO Magic Line: Stop: ([\d.]+) \((\d+) ticks buffer\)")
    tp_pattern = re.compile(r"INFO Magic Line: TP1: ([\d.]+) \| TP2: ([\d.]+)")

    initial_stop_hit = re.compile(r"INFO Magic Line: === INITIAL STOP HIT ===")
    be_stop_hit = re.compile(r"INFO Magic Line: === BREAKEVEN STOP HIT ===")
    trail_exit = re.compile(r"INFO Magic Line: === TRAIL EXIT ===")
    tp2_hit = re.compile(r"INFO Magic Line: === TP2 HIT ===")
    eod_flatten = re.compile(r"INFO Magic Line: === EOD FLATTEN ===")
    time_exit = re.compile(r"INFO Magic Line: === TIME EXIT ===")

    current_trade: Optional[Trade] = None

    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # New entry
            if entry_signal.search(line):
                if current_trade and current_trade.exit_type == "":
                    current_trade.exit_type = "UNKNOWN"
                    current_trade.variant = identify_variant(current_trade)
                    trades.append(current_trade)
                current_trade = Trade()
                continue

            if current_trade is None:
                continue

            # Entry details
            match = entry_details.search(line)
            if match and current_trade.entry_price == 0:
                current_trade.entry_price = float(match.group(1))
                current_trade.lb_at_entry = float(match.group(2))
                continue

            # Stop
            match = stop_pattern.search(line)
            if match and current_trade.initial_stop == 0:
                current_trade.initial_stop = float(match.group(1))
                current_trade.risk_points = current_trade.entry_price - current_trade.initial_stop
                continue

            # TP levels
            match = tp_pattern.search(line)
            if match and current_trade.tp1_price == 0:
                current_trade.tp1_price = float(match.group(1))
                current_trade.tp2_price = float(match.group(2))
                current_trade.variant = identify_variant(current_trade)
                continue

            # Exit types
            if initial_stop_hit.search(line):
                current_trade.exit_type = "INITIAL_STOP"
                current_trade.pnl_points = current_trade.initial_stop - current_trade.entry_price
                trades.append(current_trade)
                current_trade = None
            elif be_stop_hit.search(line):
                current_trade.exit_type = "BREAKEVEN_STOP"
                current_trade.pnl_points = 0
                trades.append(current_trade)
                current_trade = None
            elif trail_exit.search(line):
                current_trade.exit_type = "TRAIL_EXIT"
                trades.append(current_trade)
                current_trade = None
            elif tp2_hit.search(line):
                current_trade.exit_type = "TP2"
                current_trade.pnl_points = current_trade.tp2_price - current_trade.entry_price
                trades.append(current_trade)
                current_trade = None
            elif eod_flatten.search(line):
                current_trade.exit_type = "EOD"
                trades.append(current_trade)
                current_trade = None
            elif time_exit.search(line):
                current_trade.exit_type = "TIME_EXIT"
                trades.append(current_trade)
                current_trade = None

    if current_trade:
        if current_trade.exit_type == "":
            current_trade.exit_type = "OPEN"
        trades.append(current_trade)

    return trades


def analyze_by_variant(trades: List[Trade]) -> Dict[str, Dict]:
    """Analyze performance grouped by variant."""
    variants = {}

    for trade in trades:
        v = trade.variant
        if v not in variants:
            variants[v] = {"trades": [], "pnl": 0, "wins": 0, "losses": 0, "be": 0}

        variants[v]["trades"].append(trade)
        variants[v]["pnl"] += trade.pnl_points

        if trade.pnl_points > 0.01:
            variants[v]["wins"] += 1
        elif trade.pnl_points < -0.01:
            variants[v]["losses"] += 1
        else:
            variants[v]["be"] += 1

    # Calculate stats
    results = {}
    for v, data in variants.items():
        total = len(data["trades"])
        wins = data["wins"]
        losses = data["losses"]

        gross_profit = sum(t.pnl_points for t in data["trades"] if t.pnl_points > 0)
        gross_loss = abs(sum(t.pnl_points for t in data["trades"] if t.pnl_points < 0))

        results[v] = {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": data["be"],
            "win_rate": wins / total * 100 if total > 0 else 0,
            "total_pnl": data["pnl"],
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            "avg_win": gross_profit / wins if wins > 0 else 0,
            "avg_loss": -gross_loss / losses if losses > 0 else 0,
        }

        # Exit distribution
        exit_dist = {}
        for t in data["trades"]:
            exit_dist[t.exit_type] = exit_dist.get(t.exit_type, 0) + 1
        results[v]["exit_distribution"] = exit_dist

    return results


def print_comparison_report(results: Dict[str, Dict]):
    """Print a formatted comparison report."""
    print("=" * 80)
    print("VARIANT A/B TEST COMPARISON")
    print("=" * 80)

    # Sort by P&L
    sorted_variants = sorted(results.items(), key=lambda x: x[1]["total_pnl"], reverse=True)

    print(f"\n{'Variant':<20} {'Trades':>8} {'Wins':>6} {'Win%':>7} {'P&L':>12} {'PF':>8}")
    print("-" * 80)

    for name, stats in sorted_variants:
        print(f"{name:<20} {stats['total_trades']:>8} {stats['wins']:>6} "
              f"{stats['win_rate']:>6.1f}% {stats['total_pnl']:>+11.2f} "
              f"{stats['profit_factor']:>8.2f}")

    print("-" * 80)

    # Winner
    if sorted_variants:
        winner = sorted_variants[0]
        print(f"\nBEST PERFORMER: {winner[0]}")
        print(f"  Total P&L: {winner[1]['total_pnl']:+.2f} points")
        print(f"  Win Rate: {winner[1]['win_rate']:.1f}%")
        print(f"  Profit Factor: {winner[1]['profit_factor']:.2f}")

    # Detail for each
    print("\n" + "=" * 80)
    print("DETAILED BREAKDOWN BY VARIANT")
    print("=" * 80)

    for name, stats in sorted_variants:
        print(f"\n--- {name} ---")
        print(f"  Trades: {stats['total_trades']} (W:{stats['wins']} L:{stats['losses']} BE:{stats['breakeven']})")
        print(f"  P&L: {stats['total_pnl']:+.2f} pts | Gross Profit: {stats['gross_profit']:.2f} | Gross Loss: {stats['gross_loss']:.2f}")
        print(f"  Win Rate: {stats['win_rate']:.1f}% | Profit Factor: {stats['profit_factor']:.2f}")
        print(f"  Avg Win: {stats['avg_win']:+.2f} pts | Avg Loss: {stats['avg_loss']:+.2f} pts")
        print(f"  Exit Types: {stats['exit_distribution']}")


if __name__ == "__main__":
    log_dir = Path(r"C:\Users\jung_\AppData\Roaming\MotiveWave\output")

    print(f"Analyzing logs from: {log_dir}")
    print()

    all_trades = []
    for log_file in sorted(log_dir.glob("output*.txt")):
        try:
            trades = parse_log_with_variants(str(log_file))
            if trades:
                print(f"  {log_file.name}: {len(trades)} trades")
                all_trades.extend(trades)
        except Exception as e:
            print(f"  Error parsing {log_file.name}: {e}")

    print(f"\nTotal trades parsed: {len(all_trades)}")

    if all_trades:
        results = analyze_by_variant(all_trades)
        print_comparison_report(results)
