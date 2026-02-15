"""
NautilusTrader IFVG Retest Strategy Backtest Runner.

Usage:
    python run_backtest.py [--start 2024-01-01] [--end 2026-01-01] [--contracts 2]
    python run_backtest.py --start 2020-01-01 --end 2026-01-01 --log-level WARNING
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from instrument import create_es_instrument
from data_loader import load_es_bars
from ifvg_strategy import IFVGRetestStrategy, IFVGRetestConfig
from regime_calculator import compute_daily_regimes, load_daily_vix

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
VIX_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\VIX_full_1min_ttewdg8.zip"
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2026-01-01"
STARTING_CAPITAL = 25_000.0


def main():
    parser = argparse.ArgumentParser(description="IFVG Retest Strategy Backtest")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=DEFAULT_END, help="End date YYYY-MM-DD")
    parser.add_argument("--contracts", type=int, default=2)
    parser.add_argument("--shadow-threshold", type=float, default=30.0)
    parser.add_argument("--max-wait", type=int, default=30)
    parser.add_argument("--tp1-points", type=float, default=20.0)
    parser.add_argument("--trail-points", type=float, default=15.0)
    parser.add_argument("--stop-buffer", type=int, default=40)
    parser.add_argument("--stop-max", type=float, default=40.0)
    parser.add_argument("--be-trigger", type=float, default=10.0)
    parser.add_argument("--max-trades", type=int, default=3)
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--short-only", action="store_true")
    parser.add_argument("--regime", action="store_true", help="Enable volatility regime adaptive stops/targets")
    parser.add_argument("--mes", action="store_true", help="Use MES ($5/point) instead of ES ($50/point)")
    parser.add_argument("--vix-filter", action="store_true", help="Enable VIX hysteresis filter")
    parser.add_argument("--vix-off", type=float, default=30.0, help="Stop trading when VIX > this")
    parser.add_argument("--vix-on", type=float, default=20.0, help="Resume trading when VIX < this")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    # 1. Create engine
    engine_config = BacktestEngineConfig(
        trader_id="BACKTESTER-001",
        logging=LoggingConfig(log_level=args.log_level),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

    # 2. Add venue
    SIM = Venue("SIM")
    engine.add_venue(
        venue=SIM,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(STARTING_CAPITAL, USD)],
    )

    # 3. Create instrument
    multiplier = 5 if args.mes else 50
    es = create_es_instrument(venue=SIM, multiplier=multiplier)
    engine.add_instrument(es)

    # 4. Load data
    print(f"Loading ES data: {args.start} to {args.end}...")
    bars, bar_type = load_es_bars(
        zip_path=ES_ZIP_PATH,
        instrument=es,
        start_date=args.start,
        end_date=args.end,
    )
    engine.add_data(bars)

    # 5. Compute volatility regimes and VIX data
    regime_lookup = {}
    vix_lookup = {}
    if args.regime:
        regime_lookup = compute_daily_regimes(
            es_zip_path=ES_ZIP_PATH,
            vix_zip_path=VIX_ZIP_PATH,
            start_date=args.start,
            end_date=args.end,
        )
    if args.vix_filter:
        print("Loading VIX data for filter...")
        vix_lookup = load_daily_vix(VIX_ZIP_PATH)

    # 6. Create strategy
    enable_long = not args.short_only
    enable_short = not args.long_only

    strategy_config = IFVGRetestConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        enable_long=enable_long,
        enable_short=enable_short,
        contracts=args.contracts,
        shadow_threshold_pct=args.shadow_threshold,
        max_wait_bars=args.max_wait,
        tp1_points=args.tp1_points,
        trail_points=args.trail_points,
        stop_buffer_ticks=args.stop_buffer,
        stop_max_pts=args.stop_max,
        be_trigger_pts=args.be_trigger,
        max_trades_day=args.max_trades,
        vix_filter_enabled=args.vix_filter,
        vix_off=args.vix_off,
        vix_on=args.vix_on,
        order_id_tag="001",
    )
    strategy = IFVGRetestStrategy(config=strategy_config, regime_lookup=regime_lookup, vix_lookup=vix_lookup)
    engine.add_strategy(strategy)

    # 7. Run
    print(f"\nRunning backtest ({len(bars):,} bars)...")
    engine.run()

    # 8. Report results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Period: {args.start} to {args.end}")
    print(f"Starting Capital: ${STARTING_CAPITAL:,.0f}")
    instrument_label = f"{'MES' if args.mes else 'ES'} x {args.contracts}"
    print(f"Instrument: {instrument_label}")
    print(f"Direction: {'Long+Short' if enable_long and enable_short else 'Long only' if enable_long else 'Short only'}")
    print(f"Vol Regime: {'ENABLED' if args.regime else 'OFF'}")
    if args.vix_filter:
        print(f"VIX Filter: OFF > {args.vix_off}, ON < {args.vix_on}")
    print()

    # Generate reports
    fills_report = engine.trader.generate_order_fills_report()
    positions_report = engine.trader.generate_positions_report()

    if positions_report is not None and not positions_report.empty:
        print(f"Total Trades: {len(positions_report)}")

        if "realized_pnl" in positions_report.columns:
            pnls = positions_report["realized_pnl"].apply(
                lambda x: float(str(x).replace(" USD", "").replace(",", ""))
            )
            total_pnl = pnls.sum()
            wins = pnls[pnls > 0]
            losses = pnls[pnls <= 0]
            win_rate = len(wins) / len(pnls) * 100 if len(pnls) > 0 else 0
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = losses.mean() if len(losses) > 0 else 0
            gross_wins = wins.sum() if len(wins) > 0 else 0
            gross_losses = abs(losses.sum()) if len(losses) > 0 else 0
            profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

            # Max drawdown from equity curve
            equity = pnls.cumsum()
            peak = equity.cummax()
            drawdown = equity - peak
            max_dd = drawdown.min()

            # Sharpe ratio (annualized, ~252 trading days)
            if len(pnls) > 1 and pnls.std() > 0:
                sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252)
            else:
                sharpe = 0

            # Return on capital
            roi = (total_pnl / STARTING_CAPITAL) * 100

            print(f"\n{'--- Key Statistics ---':^40}")
            print(f"{'Total P&L:':<25} ${total_pnl:>12,.2f}")
            print(f"{'ROI:':<25} {roi:>12.1f}%")
            print(f"{'Win Rate:':<25} {win_rate:>12.1f}%")
            print(f"{'Profit Factor:':<25} {profit_factor:>12.2f}")
            print(f"{'Avg Win:':<25} ${avg_win:>12,.2f}")
            print(f"{'Avg Loss:':<25} ${avg_loss:>12,.2f}")
            print(f"{'Max Drawdown:':<25} ${max_dd:>12,.2f}")
            print(f"{'Sharpe Ratio:':<25} {sharpe:>12.2f}")
            print(f"{'Winning Trades:':<25} {len(wins):>12}")
            print(f"{'Losing Trades:':<25} {len(losses):>12}")

        # Save to CSV
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        positions_report.to_csv(output_dir / "positions.csv")
        if fills_report is not None and not fills_report.empty:
            fills_report.to_csv(output_dir / "fills.csv")
        print(f"\nResults saved to {output_dir}")

        # Generate and open equity curve
        from plot_equity import plot_equity
        title = f"IFVG Retest Strategy — {args.start} to {args.end} ({instrument_label}, VIX {'ON' if args.vix_filter else 'OFF'})"
        chart_path = plot_equity(str(output_dir / "positions.csv"), title)
        import subprocess
        subprocess.Popen(["cmd", "/c", "start", "", str(chart_path)],
                         creationflags=0x08000000)
    else:
        print("No trades were generated.")

    # 8. Cleanup
    engine.reset()
    engine.dispose()


if __name__ == "__main__":
    main()
