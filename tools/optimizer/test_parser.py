"""
Test parser to debug P&L calculation against MotiveWave's actual values.

MotiveWave shows for the most recent run:
- Original: $1,037.50 realized, $8,343.75 total
- V1: $200.00 realized, $2,556.25 total
- V2: $1,037.50 realized, $4,143.75 total
- V3: $200.00 realized, $2,425.00 total
"""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional

ES_POINT_VALUE = 50.0  # $50 per point for ES

@dataclass
class Trade:
    variant: str = ""
    entry_price: float = 0.0
    stop_price: float = 0.0
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    contracts: int = 0
    exit_type: str = ""
    exit_price: float = 0.0
    partial_taken: bool = False
    partial_price: float = 0.0
    partial_qty: int = 0
    pnl_points: float = 0.0


def parse_newest_log():
    """Parse only the newest log file."""
    log_dir = Path(r"C:\Users\jung_\AppData\Roaming\MotiveWave\output")
    log_files = sorted(log_dir.glob("output*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not log_files:
        print("No log files found")
        return

    newest = log_files[0]
    print(f"Parsing: {newest.name}\n")

    # Track trades per variant
    trades: Dict[str, List[Trade]] = {
        "ML-V1": [],
        "ML-V2": [],
        "ML-V3": [],
    }

    current: Dict[str, Optional[Trade]] = {
        "ML-V1": None,
        "ML-V2": None,
        "ML-V3": None,
    }

    with open(newest, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            for variant in ["ML-V1", "ML-V2", "ML-V3"]:
                # Entry signal
                if f"{variant}: === LONG ENTRY SIGNAL ===" in line:
                    if current[variant] and current[variant].exit_type == "":
                        current[variant].exit_type = "UNKNOWN"
                        current[variant].pnl_points = 0
                        trades[variant].append(current[variant])
                    current[variant] = Trade(variant=variant)
                    continue

                if current[variant] is None:
                    continue

                t = current[variant]

                # Entry details
                match = re.search(rf"{variant}: Entry: ([\d.]+) \| LB:", line)
                if match and t.entry_price == 0:
                    t.entry_price = float(match.group(1))
                    continue

                # Stop
                match = re.search(rf"{variant}: Stop: ([\d.]+)", line)
                if match and t.stop_price == 0:
                    t.stop_price = float(match.group(1))
                    continue

                # TP levels
                match = re.search(rf"{variant}: TP1: ([\d.]+) \| TP2: ([\d.]+)", line)
                if match and t.tp1_price == 0:
                    t.tp1_price = float(match.group(1))
                    t.tp2_price = float(match.group(2))
                    continue

                # Contracts
                match = re.search(rf"{variant}: Contracts: (\d+)", line)
                if match and t.contracts == 0:
                    t.contracts = int(match.group(1))
                    continue

                # Partial at TP1
                if f"{variant}: === TAKING PARTIAL at TP1 ===" in line:
                    t.partial_taken = True
                    continue

                match = re.search(rf"{variant}: TP1: ([\d.]+) \| Closing (\d+) of (\d+)", line)
                if match:
                    t.partial_price = float(match.group(1))
                    t.partial_qty = int(match.group(2))
                    continue

                # Exits
                if f"{variant}: === TP2 HIT ===" in line:
                    t.exit_type = "TP2"
                    t.exit_price = t.tp2_price
                    finalize_trade(t, trades, variant)
                    current[variant] = None
                    continue

                if f"{variant}: === INITIAL STOP HIT ===" in line:
                    t.exit_type = "STOP"
                    t.exit_price = t.stop_price
                    finalize_trade(t, trades, variant)
                    current[variant] = None
                    continue

                if f"{variant}: === TRAILING STOP HIT ===" in line:
                    t.exit_type = "TRAIL_STOP"
                    t.exit_price = t.entry_price  # At breakeven
                    finalize_trade(t, trades, variant)
                    current[variant] = None
                    continue

                if f"{variant}: === BREAKEVEN STOP HIT ===" in line:
                    t.exit_type = "BE_STOP"
                    t.exit_price = t.entry_price
                    finalize_trade(t, trades, variant)
                    current[variant] = None
                    continue

                if f"{variant}: === TRAIL EXIT ===" in line:
                    t.exit_type = "TRAIL_EXIT"
                    t.exit_price = t.entry_price  # Approximate
                    finalize_trade(t, trades, variant)
                    current[variant] = None
                    continue

                if f"{variant}: === EOD FLATTEN ===" in line:
                    t.exit_type = "EOD"
                    t.exit_price = t.entry_price  # Unknown, assume BE
                    finalize_trade(t, trades, variant)
                    current[variant] = None
                    continue

    return trades


def finalize_trade(t: Trade, trades: Dict, variant: str):
    """Calculate P&L and store trade."""
    if t.entry_price == 0:
        return

    # Calculate P&L in points (NOT multiplied by contracts)
    # This assumes MotiveWave tracks per-point P&L, not per-contract-point
    if t.partial_taken and t.partial_qty > 0:
        # Partial at TP1 + remainder at exit
        half = t.contracts / 2
        partial_pts = (t.partial_price - t.entry_price)
        remainder_pts = (t.exit_price - t.entry_price)
        # Average the two exits
        t.pnl_points = (partial_pts + remainder_pts) / 2 * t.contracts
    else:
        t.pnl_points = (t.exit_price - t.entry_price) * t.contracts

    trades[variant].append(t)


def analyze_trades(trades: Dict[str, List[Trade]]):
    """Analyze trades and compare to MotiveWave values."""

    # Expected values from MotiveWave
    expected = {
        "ML-V1": 200.00,
        "ML-V2": 1037.50,
        "ML-V3": 200.00,
    }

    print("=" * 70)
    print("P&L CALCULATION TEST")
    print("=" * 70)

    for variant in ["ML-V1", "ML-V2", "ML-V3"]:
        variant_trades = trades[variant]
        if not variant_trades:
            continue

        total_pts = sum(t.pnl_points for t in variant_trades)
        total_dollars = total_pts * ES_POINT_VALUE

        # Count by exit type
        exit_counts = {}
        for t in variant_trades:
            exit_counts[t.exit_type] = exit_counts.get(t.exit_type, 0) + 1

        print(f"\n{variant}:")
        print(f"  Trades: {len(variant_trades)}")
        print(f"  Exit types: {exit_counts}")
        print(f"  Total P&L (calculated): {total_pts:.2f} pts = ${total_dollars:.2f}")
        print(f"  MotiveWave expected: ${expected[variant]:.2f}")
        print(f"  Ratio (calc/expected): {total_dollars / expected[variant]:.2f}x")

    # Try different calculation methods
    print("\n" + "=" * 70)
    print("TRYING ALTERNATIVE CALCULATIONS")
    print("=" * 70)

    for variant in ["ML-V1", "ML-V2", "ML-V3"]:
        variant_trades = trades[variant]
        if not variant_trades:
            continue

        # Method 1: Raw points without contract multiplier
        raw_pts = sum((t.exit_price - t.entry_price) for t in variant_trades if t.exit_price > 0)

        # Method 2: With partial handling but no contract multiplier
        method2_pts = 0
        for t in variant_trades:
            if t.exit_price == 0:
                continue
            if t.partial_taken:
                partial = (t.partial_price - t.entry_price)
                remainder = (t.exit_price - t.entry_price)
                method2_pts += (partial + remainder) / 2
            else:
                method2_pts += (t.exit_price - t.entry_price)

        print(f"\n{variant}:")
        print(f"  Method 1 (raw pts): {raw_pts:.2f} pts = ${raw_pts * 50:.2f}")
        print(f"  Method 2 (partial avg): {method2_pts:.2f} pts = ${method2_pts * 50:.2f}")
        print(f"  Expected: ${expected[variant]:.2f}")


if __name__ == "__main__":
    trades = parse_newest_log()
    if trades:
        analyze_trades(trades)
