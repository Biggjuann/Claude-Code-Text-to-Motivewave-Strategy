"""
Unger First-Bar Mean Reversion Strategy — NautilusTrader Backtest Runner.

Usage:
    python run_bollinger_mr.py [--start 2024-01-01] [--end 2026-01-01]
    python run_bollinger_mr.py --start 2024-01-01 --end 2026-01-01 --mes --dollars-per-contract 5000
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
from bollinger_mr_strategy import BollingerMRStrategy, BollingerMRConfig

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2026-01-01"
STARTING_CAPITAL = 25_000.0


def main():
    parser = argparse.ArgumentParser(description="Unger First-Bar Mean Reversion Backtest")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=DEFAULT_END, help="End date YYYY-MM-DD")

    # First-bar displacement params
    parser.add_argument("--displacement-pct", type=float, default=0.0035, help="Displacement from first bar (0.35%%)")
    parser.add_argument("--adr-period", type=int, default=14, help="Average Daily Range lookback")
    parser.add_argument("--adr-stop-mult", type=float, default=1.5, help="Stop = mult * ADR")
    parser.add_argument("--adr-tp-mult", type=float, default=0, help="TP = mult * ADR (0=disabled)")
    parser.add_argument("--no-fb-tp", action="store_true", help="Disable first-bar midpoint TP")

    # Session
    parser.add_argument("--max-trades", type=int, default=1)
    parser.add_argument("--eod-time", type=int, default=1640)

    # Sizing
    parser.add_argument("--contracts", type=int, default=10)
    parser.add_argument("--dollars-per-contract", type=float, default=0, help="Dynamic sizing: $ per contract (0=fixed)")
    parser.add_argument("--mes", action="store_true", help="Use MES ($5/point) instead of ES ($50/point)")

    # Output
    parser.add_argument("--bar-minutes", type=int, default=5, help="Bar size in minutes")
    parser.add_argument("--label", default="bollinger_mr", help="Output subdirectory label")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--skip-margin", action="store_true", help="Skip margin analysis")
    args = parser.parse_args()

    # 1. Create engine
    engine_config = BacktestEngineConfig(
        trader_id="BACKTESTER-012",
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

    # 5. Create strategy
    strategy_config = BollingerMRConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        displacement_pct=args.displacement_pct,
        adr_period=args.adr_period,
        adr_stop_mult=args.adr_stop_mult,
        adr_tp_mult=args.adr_tp_mult,
        tp_at_first_bar=not args.no_fb_tp,
        max_trades_per_day=args.max_trades,
        eod_time=args.eod_time,
        contracts=args.contracts,
        dollars_per_contract=args.dollars_per_contract,
        order_id_tag="012",
    )
    strategy = BollingerMRStrategy(config=strategy_config)
    engine.add_strategy(strategy)

    # 6. Run
    print(f"\nRunning backtest ({len(bars):,} bars, {args.bar_minutes}-min)...")
    engine.run()

    # 7. Report results
    print("\n" + "=" * 60)
    print("UNGER FIRST-BAR MEAN REVERSION — BACKTEST RESULTS")
    print("=" * 60)
    print(f"Period: {args.start} to {args.end}")
    print(f"Starting Capital: ${STARTING_CAPITAL:,.0f}")
    if args.dollars_per_contract > 0:
        instrument_label = f"{'MES' if args.mes else 'ES'} dynamic (${args.dollars_per_contract:,.0f}/contract)"
    else:
        instrument_label = f"{'MES' if args.mes else 'ES'} x {args.contracts}"
    print(f"Instrument: {instrument_label}")
    print(f"Bar Size: {args.bar_minutes}-min")
    print(f"Direction: Long + Short (Mean Reversion / Fade)")
    print(f"Displacement: {args.displacement_pct*100:.2f}% from first RTH bar")
    if not args.no_fb_tp:
        tp_label = "first-bar midpoint"
    elif args.adr_tp_mult > 0:
        tp_label = f"{args.adr_tp_mult}x ADR"
    else:
        tp_label = "EOD"
    print(f"Stop: {args.adr_stop_mult}x ADR | TP: {tp_label} | Exit: EOD")
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
        output_dir = Path(__file__).parent / "results" / args.label
        output_dir.mkdir(parents=True, exist_ok=True)
        positions_report.to_csv(output_dir / "positions.csv")
        if fills_report is not None and not fills_report.empty:
            fills_report.to_csv(output_dir / "fills.csv")
        print(f"\nResults saved to {output_dir}")

        # Generate and open equity curve
        from plot_equity import plot_equity
        title = f"Unger First-Bar MR — {args.start} to {args.end} ({instrument_label}, {args.bar_minutes}min)"
        chart_path = plot_equity(str(output_dir / "positions.csv"), title)
        import subprocess
        subprocess.Popen(["cmd", "/c", "start", "", str(chart_path)],
                         creationflags=0x08000000)

        # Margin analysis
        if not args.skip_margin:
            try:
                from margin_analyzer import analyze_margin, print_margin_report, plot_margin_analysis, save_margin_summary
                margin_result = analyze_margin(
                    fills_csv=str(output_dir / "fills.csv"),
                    positions_csv=str(output_dir / "positions.csv"),
                    bars=bars,
                    starting_capital=STARTING_CAPITAL,
                    multiplier=multiplier,
                )
                print_margin_report(margin_result, label="Unger First-Bar MR")
                save_margin_summary(margin_result, str(output_dir))
                margin_chart = plot_margin_analysis(
                    margin_result, str(output_dir),
                    title="Margin Analysis — Unger First-Bar MR",
                )
                if margin_chart:
                    subprocess.Popen(["cmd", "/c", "start", "", str(margin_chart)],
                                     creationflags=0x08000000)
            except Exception as e:
                print(f"\nWarning: Margin analysis failed: {e}")
    else:
        print("No trades were generated.")

    # 8. Cleanup
    engine.reset()
    engine.dispose()


if __name__ == "__main__":
    main()
