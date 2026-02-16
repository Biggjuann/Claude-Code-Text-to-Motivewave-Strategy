"""
MagicLine Strategy — NautilusTrader Backtest Runner.

Usage:
    python run_magicline.py [--start 2024-01-01] [--end 2026-01-01]
    python run_magicline.py --start 2022-01-01 --end 2026-01-01 --mes --dollars-per-contract 5000
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
from magicline_strategy import MagicLineStrategy, MagicLineConfig
from regime_calculator import load_daily_vix

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
VIX_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\VIX_full_1min_ttewdg8.zip"
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2026-01-01"
STARTING_CAPITAL = 25_000.0


def main():
    parser = argparse.ArgumentParser(description="MagicLine Strategy Backtest")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=DEFAULT_END, help="End date YYYY-MM-DD")

    # LB Indicator
    parser.add_argument("--length", type=int, default=20)
    parser.add_argument("--touch-tol", type=int, default=4, help="Touch tolerance (ticks)")
    parser.add_argument("--zone-buffer", type=float, default=1.0, help="Entry zone buffer (pts)")
    parser.add_argument("--came-from-pts", type=float, default=5.0)
    parser.add_argument("--came-from-lookback", type=int, default=10)

    # EMA filter
    parser.add_argument("--ema-period", type=int, default=21)
    parser.add_argument("--no-ema-filter", action="store_true", help="Disable EMA filter")

    # Session
    parser.add_argument("--trade-start", type=int, default=200)
    parser.add_argument("--trade-end", type=int, default=1600)
    parser.add_argument("--max-trades", type=int, default=3)
    parser.add_argument("--no-session", action="store_true", help="Disable session window")

    # Stop
    parser.add_argument("--stop-mode", type=int, default=1, choices=[0, 1], help="0=fixed, 1=structural")
    parser.add_argument("--stop-buffer", type=int, default=20, help="Stop buffer (ticks)")

    # Breakeven
    parser.add_argument("--be-trigger", type=float, default=10.0)
    parser.add_argument("--no-be", action="store_true", help="Disable breakeven")

    # Targets
    parser.add_argument("--tp1-r", type=float, default=3.0)
    parser.add_argument("--tp2-r", type=float, default=10.0)
    parser.add_argument("--partial-pct", type=int, default=25)
    parser.add_argument("--no-partial", action="store_true", help="Disable partial profit")

    # Sizing
    parser.add_argument("--contracts", type=int, default=10)
    parser.add_argument("--dollars-per-contract", type=float, default=0, help="Dynamic sizing: $ per contract (0=fixed)")

    # Instrument / VIX
    parser.add_argument("--mes", action="store_true", help="Use MES ($5/point) instead of ES ($50/point)")
    parser.add_argument("--vix-filter", action="store_true", help="Enable VIX hysteresis filter")
    parser.add_argument("--vix-off", type=float, default=30.0)
    parser.add_argument("--vix-on", type=float, default=20.0)

    # Bar size / logging
    parser.add_argument("--bar-minutes", type=int, default=5, help="Bar size in minutes (default: 5)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    # 1. Create engine
    engine_config = BacktestEngineConfig(
        trader_id="BACKTESTER-003",
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
    print(f"Loading ES data: {args.start} to {args.end} ({args.bar_minutes}-min bars)...")
    bars, bar_type = load_es_bars(
        zip_path=ES_ZIP_PATH,
        instrument=es,
        start_date=args.start,
        end_date=args.end,
        bar_minutes=args.bar_minutes,
    )
    engine.add_data(bars)

    # 5. VIX data
    vix_lookup = {}
    if args.vix_filter:
        print("Loading VIX data for filter...")
        vix_lookup = load_daily_vix(VIX_ZIP_PATH)

    # 6. Create strategy
    strategy_config = MagicLineConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        length=args.length,
        touch_tolerance_ticks=args.touch_tol,
        zone_buffer_pts=args.zone_buffer,
        came_from_pts=args.came_from_pts,
        came_from_lookback=args.came_from_lookback,
        ema_filter_enabled=not args.no_ema_filter,
        ema_period=args.ema_period,
        trade_session_enabled=not args.no_session,
        trade_start=args.trade_start,
        trade_end=args.trade_end,
        max_trades_per_day=args.max_trades,
        stoploss_mode=args.stop_mode,
        stop_buffer_ticks=args.stop_buffer,
        contracts=args.contracts,
        dollars_per_contract=args.dollars_per_contract,
        be_enabled=not args.no_be,
        be_trigger_pts=args.be_trigger,
        tp1_r=args.tp1_r,
        tp2_r=args.tp2_r,
        partial_enabled=not args.no_partial,
        partial_pct=args.partial_pct,
        vix_filter_enabled=args.vix_filter,
        vix_off=args.vix_off,
        vix_on=args.vix_on,
        order_id_tag="003",
    )
    strategy = MagicLineStrategy(config=strategy_config, vix_lookup=vix_lookup)
    engine.add_strategy(strategy)

    # 7. Run
    print(f"\nRunning backtest ({len(bars):,} bars, {args.bar_minutes}-min)...")
    engine.run()

    # 8. Report results
    print("\n" + "=" * 60)
    print("MAGICLINE STRATEGY — BACKTEST RESULTS")
    print("=" * 60)
    print(f"Period: {args.start} to {args.end}")
    print(f"Starting Capital: ${STARTING_CAPITAL:,.0f}")
    if args.dollars_per_contract > 0:
        instrument_label = f"{'MES' if args.mes else 'ES'} dynamic (${args.dollars_per_contract:,.0f}/contract)"
    else:
        instrument_label = f"{'MES' if args.mes else 'ES'} x {args.contracts}"
    print(f"Instrument: {instrument_label}")
    print(f"Bar Size: {args.bar_minutes}-min")
    print(f"Direction: Long only")
    print(f"LB Length: {args.length} | EMA({args.ema_period}): {'ON' if not args.no_ema_filter else 'OFF'}")
    print(f"TP1: {args.tp1_r}R | TP2: {args.tp2_r}R | Partial: {args.partial_pct}%")
    print(f"Stop Mode: {'Structural' if args.stop_mode == 1 else 'Fixed'} ({args.stop_buffer} ticks)")
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

            equity = pnls.cumsum()
            peak = equity.cummax()
            drawdown = equity - peak
            max_dd = drawdown.min()

            if len(pnls) > 1 and pnls.std() > 0:
                sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252)
            else:
                sharpe = 0

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
        output_dir = Path(__file__).parent / "results" / "magicline"
        output_dir.mkdir(parents=True, exist_ok=True)
        positions_report.to_csv(output_dir / "positions.csv")
        if fills_report is not None and not fills_report.empty:
            fills_report.to_csv(output_dir / "fills.csv")
        print(f"\nResults saved to {output_dir}")

        # Generate and open equity curve
        from plot_equity import plot_equity
        title = f"MagicLine — {args.start} to {args.end} ({instrument_label}, {args.bar_minutes}min, TP1={args.tp1_r}R/TP2={args.tp2_r}R)"
        chart_path = plot_equity(str(output_dir / "positions.csv"), title)
        import subprocess
        subprocess.Popen(["cmd", "/c", "start", "", str(chart_path)],
                         creationflags=0x08000000)
    else:
        print("No trades were generated.")

    # 9. Cleanup
    engine.reset()
    engine.dispose()


if __name__ == "__main__":
    main()
