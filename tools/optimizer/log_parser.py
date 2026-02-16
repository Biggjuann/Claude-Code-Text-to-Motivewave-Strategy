"""
Magic Line Strategy Log Parser v6.0
Correlates OrderDirectory fills with strategy FILL logs by sequence.
Tracks individual trades for detailed analysis and optimization.

The log shows:
  1. OrderDirectory::orderFilled()... fill price: X  (actual fill price)
  2. ML-V2: FILL: BUY/SELL @ Y                       (strategy identifier)

We pair them by sequence to get both accurate price AND strategy attribution.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Point value for MES (Micro E-mini S&P 500)
MES_POINT_VALUE = 5.0
ES_POINT_VALUE = 5.0  # Alias for compatibility

# Variant name mapping
VARIANT_NAMES = {
    "Magic Line": "Original",
    "ML-V1": "V1",
    "ML-V2": "V2",
    "ML-V3": "V3",
}


@dataclass
class Trade:
    """Represents a single trade with entry and exit details."""
    variant: str
    entry_time: str = ""
    exit_time: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    side: str = "BUY"  # BUY for long, SELL for short
    pnl_points: float = 0.0
    pnl_dollars: float = 0.0
    exit_type: str = ""  # INITIAL_STOP, BREAKEVEN_STOP, TRAIL_STOP, TP1, TP2, EOD, UNKNOWN

    # Additional context from logs
    lb_at_entry: float = 0.0
    stop_buffer_ticks: int = 0
    be_trigger: float = 0.0
    tp1_r: float = 0.0
    tp2_r: float = 0.0

    def is_winner(self) -> bool:
        return self.pnl_points > 0

    def r_multiple(self) -> float:
        """Calculate R-multiple (reward relative to initial risk)."""
        if self.stop_buffer_ticks > 0:
            # Convert ticks to points (4 ticks = 1 point for ES/MES)
            risk_points = self.stop_buffer_ticks / 4.0
            if risk_points > 0:
                return self.pnl_points / risk_points
        return 0.0


@dataclass
class OpenPosition:
    """Tracks an open position during parsing."""
    variant: str
    entry_price: float
    entry_time: str
    quantity: int
    initial_qty: int
    partial_taken: bool = False


def parse_log_file(log_path: str) -> Dict[str, List[Trade]]:
    """Parse log file by correlating OrderDirectory fills with strategy FILL logs.

    Returns:
        Dict mapping variant name to list of completed trades
    """
    trades_by_variant: Dict[str, List[Trade]] = {
        "Original": [],
        "V1": [],
        "V2": [],
        "V3": [],
    }

    # Track open positions: variant -> OpenPosition
    positions: Dict[str, OpenPosition] = {}

    # Patterns - support both short (HH:MM:SS) and long (YYYY/MM/DD HH:MM:SS.sss) timestamps
    # OrderDirectory fill: orderFilled()...Filled BUY/SELL MKT Qty:X... fill price: Y
    order_fill_pattern = re.compile(
        r'(\d{1,2}:\d{2}:\d{2}|\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+).*'
        r'OrderDirectory::orderFilled\(\).*Filled (BUY|SELL) MKT Qty:([\d.]+).*fill price: ([\d.]+)'
    )

    # Strategy fill: ML-V2: FILL: BUY/SELL/CLOSE X @
    strategy_fill_pattern = re.compile(
        r'(\d{1,2}:\d{2}:\d{2}|\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+).*'
        r'INFO (Magic Line|ML-V1|ML-V2|ML-V3): FILL: (BUY|SELL|CLOSE) (\d+) @'
    )

    # Exit type patterns (from strategy logs)
    exit_patterns = {
        "INITIAL_STOP": re.compile(r'Exiting.*stop loss|stop triggered|Stop loss hit'),
        "BREAKEVEN_STOP": re.compile(r'Breakeven stop|BE stop'),
        "TRAIL_STOP": re.compile(r'Trail stop|Trailing stop'),
        "TP1": re.compile(r'TP1|partial.*target|first target'),
        "TP2": re.compile(r'TP2|final target|second target'),
        "EOD": re.compile(r'EOD|end of day|flattening'),
    }

    # State: last OrderDirectory fill waiting to be matched
    pending_order_fill: Optional[Tuple[str, str, int, float]] = None  # (time, side, qty, price)
    last_exit_type = "UNKNOWN"

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Check for exit type hints before processing fills
                for exit_type, pattern in exit_patterns.items():
                    if pattern.search(line):
                        last_exit_type = exit_type
                        break

                # Check for OrderDirectory fill
                order_match = order_fill_pattern.search(line)
                if order_match:
                    time_str = order_match.group(1)
                    side = order_match.group(2)
                    qty = int(float(order_match.group(3)))
                    price = float(order_match.group(4))
                    pending_order_fill = (time_str, side, qty, price)
                    continue

                # Check for strategy FILL log
                strat_match = strategy_fill_pattern.search(line)
                if strat_match and pending_order_fill:
                    strat_time = strat_match.group(1)
                    label = strat_match.group(2)
                    strat_side = strat_match.group(3)
                    strat_qty = int(strat_match.group(4))

                    variant = VARIANT_NAMES.get(label)
                    if not variant:
                        pending_order_fill = None
                        continue

                    order_time, order_side, order_qty, order_price = pending_order_fill

                    # Verify sides match (SELL/CLOSE both map to SELL in OrderDirectory)
                    expected_order_side = 'SELL' if strat_side in ('SELL', 'CLOSE') else strat_side
                    if order_side != expected_order_side:
                        # Mismatch - skip this pairing
                        pending_order_fill = None
                        continue

                    # Process the fill
                    if strat_side == 'BUY':
                        # Entry
                        positions[variant] = OpenPosition(
                            variant=variant,
                            entry_price=order_price,
                            entry_time=order_time,
                            quantity=order_qty,
                            initial_qty=order_qty
                        )
                    else:
                        # Exit (SELL or CLOSE)
                        if variant in positions:
                            pos = positions[variant]

                            # Calculate P&L for this exit
                            exit_pnl = (order_price - pos.entry_price) * order_qty

                            # Determine exit type
                            exit_type = last_exit_type
                            if strat_side == 'SELL' and not pos.partial_taken:
                                # First partial exit is likely TP1
                                exit_type = "TP1"
                                pos.partial_taken = True
                            elif strat_side == 'CLOSE':
                                # Full close - could be TP2, stop, EOD
                                if exit_type == "UNKNOWN":
                                    # Infer from P&L
                                    if exit_pnl > 0:
                                        exit_type = "TP2"
                                    else:
                                        exit_type = "INITIAL_STOP"

                            # Create trade record
                            trade = Trade(
                                variant=variant,
                                entry_time=pos.entry_time,
                                exit_time=order_time,
                                entry_price=pos.entry_price,
                                exit_price=order_price,
                                quantity=order_qty,
                                side="BUY",  # Long only for now
                                pnl_points=exit_pnl,
                                pnl_dollars=exit_pnl * MES_POINT_VALUE,
                                exit_type=exit_type
                            )
                            trades_by_variant[variant].append(trade)

                            # If this was CLOSE, remove position
                            if strat_side == 'CLOSE':
                                del positions[variant]
                            else:
                                # Partial - update remaining quantity
                                pos.quantity -= order_qty

                    pending_order_fill = None
                    last_exit_type = "UNKNOWN"

    except Exception as e:
        print(f"Error parsing {log_path}: {e}")

    return trades_by_variant


def parse_all_logs(log_dir: str, newest_only: bool = True) -> Dict[str, List[Trade]]:
    """Parse log files from directory.

    Returns:
        Dict mapping variant name to list of all trades
    """
    log_path = Path(log_dir)
    log_files = sorted(log_path.glob("output*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)

    if newest_only and log_files:
        log_files = [log_files[0]]

    all_trades: Dict[str, List[Trade]] = {
        "Original": [],
        "V1": [],
        "V2": [],
        "V3": [],
    }

    for log_file in log_files:
        try:
            trades = parse_log_file(str(log_file))
            for variant in all_trades:
                all_trades[variant].extend(trades.get(variant, []))
            print(f"Parsed: {log_file.name}")
        except Exception as e:
            print(f"Error parsing {log_file.name}: {e}")

    return all_trades


def calculate_stats(trades: List[Trade]) -> Dict:
    """Calculate statistics for a list of trades."""
    if not trades:
        return {
            "total_trades": 0,
            "winners": 0,
            "losers": 0,
            "win_rate": 0.0,
            "total_pnl_points": 0.0,
            "total_pnl_dollars": 0.0,
            "avg_winner_points": 0.0,
            "avg_loser_points": 0.0,
            "profit_factor": 0.0,
            "exit_distribution": {}
        }

    winners = [t for t in trades if t.pnl_points > 0]
    losers = [t for t in trades if t.pnl_points <= 0]

    total_pnl = sum(t.pnl_points for t in trades)
    gross_profit = sum(t.pnl_points for t in winners)
    gross_loss = abs(sum(t.pnl_points for t in losers))

    # Exit distribution
    exit_dist: Dict[str, int] = {}
    for t in trades:
        exit_dist[t.exit_type] = exit_dist.get(t.exit_type, 0) + 1

    return {
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": len(winners) / len(trades) * 100 if trades else 0.0,
        "total_pnl_points": total_pnl,
        "total_pnl_dollars": total_pnl * MES_POINT_VALUE,
        "avg_winner_points": gross_profit / len(winners) if winners else 0.0,
        "avg_loser_points": -gross_loss / len(losers) if losers else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0,
        "exit_distribution": exit_dist
    }


def print_comparison_report(trades_by_variant: Dict[str, List[Trade]]):
    """Print comparison report across variants."""
    print("=" * 70)
    print("MAGIC LINE A/B TEST COMPARISON")
    print("(Using actual OrderDirectory fill prices)")
    print("=" * 70)

    print(f"\n{'Variant':<15} {'Trades':>8} {'Win%':>8} {'P&L (pts)':>12} {'P&L ($)':>14}")
    print("-" * 70)

    results = []
    for variant in ["Original", "V1", "V2", "V3"]:
        trades = trades_by_variant.get(variant, [])
        stats = calculate_stats(trades)
        pnl_pts = stats["total_pnl_points"]
        pnl_dollars = stats["total_pnl_dollars"]
        trade_count = stats["total_trades"]
        win_rate = stats["win_rate"]

        results.append((variant, trade_count, win_rate, pnl_pts, pnl_dollars))
        print(f"{variant:<15} {trade_count:>8} {win_rate:>7.1f}% {pnl_pts:>+11.2f} ${pnl_dollars:>+12,.2f}")

    print("-" * 70)

    # Totals
    all_trades = []
    for trades in trades_by_variant.values():
        all_trades.extend(trades)
    total_stats = calculate_stats(all_trades)
    print(f"{'TOTAL':<15} {total_stats['total_trades']:>8} {total_stats['win_rate']:>7.1f}% "
          f"{total_stats['total_pnl_points']:>+11.2f} ${total_stats['total_pnl_dollars']:>+12,.2f}")

    # Best performer
    if results:
        results.sort(key=lambda x: x[4], reverse=True)
        winner = results[0]
        print(f"\nBEST: {winner[0]} with {winner[3]:+.2f} pts (${winner[4]:+,.2f})")


def get_pnl_summary(log_dir: str, newest_only: bool = True) -> Tuple[Dict[str, float], Dict[str, int]]:
    """Get simple P&L summary by variant (for quick comparison).

    Returns:
        Tuple of (pnl_by_variant, trade_counts)
    """
    trades_by_variant = parse_all_logs(log_dir, newest_only)

    pnl_by_variant = {}
    trade_counts = {}

    for variant, trades in trades_by_variant.items():
        stats = calculate_stats(trades)
        pnl_by_variant[variant] = stats["total_pnl_points"]
        trade_counts[variant] = stats["total_trades"]

    return pnl_by_variant, trade_counts


if __name__ == "__main__":
    log_dir = r"C:\Users\jung_\AppData\Roaming\MotiveWave\output"

    print(f"Parsing logs from: {log_dir}\n")

    trades_by_variant = parse_all_logs(log_dir, newest_only=True)
    print()
    print_comparison_report(trades_by_variant)

    # Show detailed stats
    print("\n" + "=" * 70)
    print("DETAILED STATISTICS")
    print("=" * 70)

    for variant in ["Original", "V1", "V2", "V3"]:
        trades = trades_by_variant.get(variant, [])
        if trades:
            stats = calculate_stats(trades)
            print(f"\n{variant}:")
            print(f"  Profit Factor: {stats['profit_factor']:.2f}")
            print(f"  Avg Winner: {stats['avg_winner_points']:+.2f} pts")
            print(f"  Avg Loser: {stats['avg_loser_points']:+.2f} pts")
            print(f"  Exit Distribution: {stats['exit_distribution']}")
