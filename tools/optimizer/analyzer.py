"""
Strategy Performance Analyzer v2.0
Analyzes trade data per variant and identifies patterns for optimization.
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from log_parser import Trade, parse_all_logs, calculate_stats, print_comparison_report, ES_POINT_VALUE


@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report."""
    # Basic stats (combined across all variants)
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0  # In points
    total_pnl_dollars: float = 0.0

    # Risk metrics
    avg_risk: float = 0.0
    avg_reward: float = 0.0
    expected_value: float = 0.0
    avg_r_multiple: float = 0.0

    # Trade distribution
    exit_distribution: Dict[str, int] = None
    stop_out_rate: float = 0.0
    be_rate: float = 0.0
    target_hit_rate: float = 0.0

    # Per-variant stats
    variant_stats: Dict[str, Dict] = None

    # Insights and recommendations
    insights: List[str] = None
    recommendations: List[Dict] = None


def analyze_stop_effectiveness(trades: List[Trade]) -> Dict:
    """Analyze how often stops are hit and if they're too tight/loose."""
    if not trades:
        return {}

    stop_outs = [t for t in trades if t.exit_type == "INITIAL_STOP"]
    be_stops = [t for t in trades if t.exit_type in ("BREAKEVEN_STOP", "TRAIL_STOP")]
    trail_exits = [t for t in trades if t.exit_type == "TRAIL_EXIT"]
    tp_exits = [t for t in trades if t.exit_type == "TP2"]

    # Analyze stop buffer distribution
    stop_buffers = [t.stop_buffer_ticks for t in trades if t.stop_buffer_ticks > 0]
    avg_stop_buffer = sum(stop_buffers) / len(stop_buffers) if stop_buffers else 0

    return {
        "initial_stop_outs": len(stop_outs),
        "be_stop_outs": len(be_stops),
        "trail_exits": len(trail_exits),
        "target_hits": len(tp_exits),
        "stop_out_rate": len(stop_outs) / len(trades) * 100 if trades else 0,
        "avg_stop_buffer_ticks": avg_stop_buffer,
    }


def analyze_entry_quality(trades: List[Trade]) -> Dict:
    """Analyze entry conditions and identify patterns."""
    if not trades:
        return {}

    # Group by LB distance at entry
    lb_distances = [(t.entry_price - t.lb_at_entry) for t in trades if t.lb_at_entry > 0]

    # Winning trades
    winners = [t for t in trades if t.pnl_points > 0]
    winner_lb_dist = [(t.entry_price - t.lb_at_entry) for t in winners if t.lb_at_entry > 0]

    # Losing trades
    losers = [t for t in trades if t.pnl_points < 0]
    loser_lb_dist = [(t.entry_price - t.lb_at_entry) for t in losers if t.lb_at_entry > 0]

    return {
        "avg_lb_distance_all": sum(lb_distances) / len(lb_distances) if lb_distances else 0,
        "avg_lb_distance_winners": sum(winner_lb_dist) / len(winner_lb_dist) if winner_lb_dist else 0,
        "avg_lb_distance_losers": sum(loser_lb_dist) / len(loser_lb_dist) if loser_lb_dist else 0,
    }


def generate_optimization_recommendations(trades: List[Trade], stats: Dict) -> List[Dict]:
    """Generate specific parameter recommendations based on analysis."""
    recommendations = []

    if not trades:
        return [{"param": "N/A", "suggestion": "No trades found", "priority": "HIGH"}]

    stop_analysis = analyze_stop_effectiveness(trades)
    entry_analysis = analyze_entry_quality(trades)

    # 1. Stop Loss Analysis
    stop_out_rate = stop_analysis.get("stop_out_rate", 0)
    if stop_out_rate > 60:
        recommendations.append({
            "param": "STOP_BUFFER_TICKS",
            "current": int(stop_analysis.get("avg_stop_buffer_ticks", 20)),
            "suggestion": "INCREASE",
            "reason": f"High stop-out rate ({stop_out_rate:.1f}%). Stops may be too tight.",
            "test_values": [25, 30, 35, 40],
            "priority": "HIGH"
        })
    elif stop_out_rate < 20 and stats.get("win_rate", 0) < 50:
        recommendations.append({
            "param": "STOP_BUFFER_TICKS",
            "current": int(stop_analysis.get("avg_stop_buffer_ticks", 20)),
            "suggestion": "DECREASE",
            "reason": f"Low stop-out rate but low win rate. May be exiting at poor levels.",
            "test_values": [15, 12, 10],
            "priority": "MEDIUM"
        })

    # 2. Breakeven Trigger
    be_rate = stop_analysis.get("be_stop_outs", 0)
    target_rate = stop_analysis.get("target_hits", 0)
    if be_rate > target_rate and be_rate > 0:
        recommendations.append({
            "param": "BE_TRIGGER_PTS",
            "current": 5.0,
            "suggestion": "INCREASE",
            "reason": "More BE stops than target hits. BE trigger may be too aggressive.",
            "test_values": [6.0, 7.0, 8.0, 10.0],
            "priority": "MEDIUM"
        })

    # 3. Entry Zone Analysis
    avg_lb_dist_winners = entry_analysis.get("avg_lb_distance_winners", 0)
    avg_lb_dist_losers = entry_analysis.get("avg_lb_distance_losers", 0)

    if avg_lb_dist_winners > 0 and avg_lb_dist_losers > 0:
        if avg_lb_dist_winners < avg_lb_dist_losers:
            recommendations.append({
                "param": "ZONE_BUFFER_PTS",
                "current": 2.0,
                "suggestion": "DECREASE",
                "reason": f"Winners enter closer to LB ({avg_lb_dist_winners:.2f}) than losers ({avg_lb_dist_losers:.2f})",
                "test_values": [1.5, 1.0, 0.75],
                "priority": "MEDIUM"
            })
        else:
            recommendations.append({
                "param": "ZONE_BUFFER_PTS",
                "current": 2.0,
                "suggestion": "INCREASE",
                "reason": f"Winners enter further from LB. Allow more buffer.",
                "test_values": [2.5, 3.0, 4.0],
                "priority": "LOW"
            })

    # 4. Take Profit Analysis
    profit_factor = stats.get("profit_factor", 0)
    if profit_factor < 1.0:
        recommendations.append({
            "param": "TP1_R / TP2_R",
            "current": "1.0 / 2.0",
            "suggestion": "Adjust R targets",
            "reason": f"Profit factor < 1 ({profit_factor:.2f}). Need better reward:risk.",
            "test_values": ["1.5/3.0", "2.0/4.0"],
            "priority": "HIGH"
        })

    return recommendations


def generate_report(log_dir: str) -> PerformanceReport:
    """Generate a comprehensive performance report with variant comparison."""
    # Parse logs - returns Dict[variant_name, List[Trade]]
    trades_by_variant = parse_all_logs(log_dir)

    # Combine all trades for overall stats
    all_trades = []
    for variant, trades in trades_by_variant.items():
        all_trades.extend(trades)

    report = PerformanceReport()

    if not all_trades:
        report.total_trades = 0
        report.insights = ["No trades found in logs."]
        report.recommendations = [{"param": "N/A", "suggestion": "Run replay sessions first", "priority": "HIGH"}]
        report.exit_distribution = {}
        report.variant_stats = {}
        return report

    # Calculate combined stats
    combined_stats = calculate_stats(all_trades)

    report.total_trades = combined_stats["total_trades"]
    report.win_rate = combined_stats["win_rate"]
    report.profit_factor = combined_stats["profit_factor"]
    report.total_pnl = combined_stats["total_pnl_points"]
    report.total_pnl_dollars = combined_stats["total_pnl_dollars"]
    report.exit_distribution = combined_stats["exit_distribution"]

    # Calculate rates
    if report.total_trades > 0:
        report.stop_out_rate = report.exit_distribution.get("INITIAL_STOP", 0) / report.total_trades * 100
        report.be_rate = (report.exit_distribution.get("BREAKEVEN_STOP", 0) +
                         report.exit_distribution.get("TRAIL_STOP", 0)) / report.total_trades * 100
        tp_hits = report.exit_distribution.get("TP2", 0)
        report.target_hit_rate = tp_hits / report.total_trades * 100

    # Expected value
    report.expected_value = (
        (report.win_rate / 100) * combined_stats.get("avg_winner_points", 0) +
        ((100 - report.win_rate) / 100) * combined_stats.get("avg_loser_points", 0)
    )

    # Per-variant stats
    report.variant_stats = {}
    for variant, trades in trades_by_variant.items():
        if trades:
            report.variant_stats[variant] = calculate_stats(trades)

    # Generate insights
    report.insights = []

    # Variant comparison insights
    if len(report.variant_stats) > 1:
        sorted_variants = sorted(
            report.variant_stats.items(),
            key=lambda x: x[1]["total_pnl_dollars"],
            reverse=True
        )
        best = sorted_variants[0]
        worst = sorted_variants[-1]
        report.insights.append(f"Best variant: {best[0]} (${best[1]['total_pnl_dollars']:+,.2f})")
        if worst[1]["total_pnl_dollars"] < best[1]["total_pnl_dollars"]:
            report.insights.append(f"Worst variant: {worst[0]} (${worst[1]['total_pnl_dollars']:+,.2f})")

    if report.stop_out_rate > 50:
        report.insights.append(f"High initial stop-out rate ({report.stop_out_rate:.1f}%) - consider wider stops")
    if report.profit_factor < 1.0:
        report.insights.append(f"Profit factor {report.profit_factor:.2f} < 1.0 - strategy is net negative")
    if report.profit_factor > 2.0:
        report.insights.append(f"Strong profit factor {report.profit_factor:.2f} - strategy shows promise")
    if report.win_rate < 40:
        report.insights.append(f"Low win rate ({report.win_rate:.1f}%) - need larger winners or tighter entry")

    # Generate recommendations
    report.recommendations = generate_optimization_recommendations(all_trades, combined_stats)

    return report


def print_report(report: PerformanceReport):
    """Print formatted performance report."""
    print("\n" + "=" * 70)
    print("MAGIC LINE STRATEGY - PERFORMANCE ANALYSIS")
    print("=" * 70)

    print(f"\nTOTAL TRADES: {report.total_trades}")
    print(f"WIN RATE: {report.win_rate:.1f}%")
    print(f"PROFIT FACTOR: {report.profit_factor:.2f}")
    print(f"TOTAL P&L: {report.total_pnl:+.2f} points (${report.total_pnl_dollars:+,.2f})")
    print(f"EXPECTED VALUE: {report.expected_value:+.2f} points per trade")

    # Variant comparison
    if report.variant_stats and len(report.variant_stats) > 0:
        print("\n" + "-" * 70)
        print("PER-VARIANT PERFORMANCE")
        print("-" * 70)
        print(f"{'Variant':<15} {'Trades':>8} {'Win%':>7} {'P&L ($)':>12} {'PF':>8}")
        print("-" * 70)

        sorted_variants = sorted(
            report.variant_stats.items(),
            key=lambda x: x[1]["total_pnl_dollars"],
            reverse=True
        )
        for variant, stats in sorted_variants:
            print(f"{variant:<15} {stats['total_trades']:>8} {stats['win_rate']:>6.1f}% "
                  f"{stats['total_pnl_dollars']:>+11.2f} {stats['profit_factor']:>8.2f}")

    print("\nEXIT DISTRIBUTION:")
    if report.exit_distribution:
        for exit_type, count in sorted(report.exit_distribution.items()):
            pct = count / report.total_trades * 100 if report.total_trades > 0 else 0
            print(f"  {exit_type}: {count} ({pct:.1f}%)")

    if report.insights:
        print("\nKEY INSIGHTS:")
        for insight in report.insights:
            print(f"  - {insight}")

    if report.recommendations:
        print("\nOPTIMIZATION RECOMMENDATIONS:")
        print("-" * 70)
        for rec in report.recommendations:
            print(f"\n[{rec.get('priority', 'MEDIUM')}] {rec.get('param')}")
            print(f"  Current: {rec.get('current')}")
            print(f"  Suggestion: {rec.get('suggestion')}")
            print(f"  Reason: {rec.get('reason')}")
            if rec.get('test_values'):
                print(f"  Test Values: {rec.get('test_values')}")


if __name__ == "__main__":
    import sys

    log_dir = r"C:\Users\jung_\AppData\Roaming\MotiveWave\output"
    if len(sys.argv) > 1:
        log_dir = sys.argv[1]

    print(f"Analyzing logs from: {log_dir}\n")

    # First show the variant comparison
    trades_by_variant = parse_all_logs(log_dir)
    print_comparison_report(trades_by_variant)

    # Then show the full report
    report = generate_report(log_dir)
    print_report(report)

    # Save as JSON
    output_file = "analysis_report.json"
    with open(output_file, 'w') as f:
        json.dump({
            "total_trades": report.total_trades,
            "win_rate": report.win_rate,
            "profit_factor": report.profit_factor,
            "total_pnl_points": report.total_pnl,
            "total_pnl_dollars": report.total_pnl_dollars,
            "expected_value": report.expected_value,
            "exit_distribution": report.exit_distribution,
            "variant_stats": report.variant_stats,
            "insights": report.insights,
            "recommendations": [
                {
                    "param": r.get("param"),
                    "current": r.get("current"),
                    "suggestion": r.get("suggestion"),
                    "reason": r.get("reason"),
                    "test_values": r.get("test_values"),
                    "priority": r.get("priority")
                }
                for r in (report.recommendations or [])
            ]
        }, f, indent=2)

    print(f"\nReport saved to: {output_file}")
