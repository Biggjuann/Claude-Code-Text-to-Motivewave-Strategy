"""
ICT Setup Selector (JadeCap) Strategy — NautilusTrader Backtest Runner.

Usage:
    python run_jadecap.py [--start 2024-01-01] [--end 2026-01-01]
    python run_jadecap.py --start 2022-01-01 --end 2026-01-01 --mes --dollars-per-contract 5000
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
from jadecap_strategy import JadeCapStrategy, JadeCapConfig
from regime_calculator import load_daily_vix

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
VIX_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\VIX_full_1min_ttewdg8.zip"
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2026-01-01"
STARTING_CAPITAL = 25_000.0


def main():
    parser = argparse.ArgumentParser(description="JadeCap (ICT Setup Selector) Backtest")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=DEFAULT_END, help="End date YYYY-MM-DD")

    # Direction
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--short-only", action="store_true")

    # Session
    parser.add_argument("--no-always-on", action="store_true", help="Disable always-on trade window")
    parser.add_argument("--trade-start", type=int, default=1800)
    parser.add_argument("--trade-end", type=int, default=1230)
    parser.add_argument("--kz-preset", type=int, default=3, help="Kill zone: 0=NY AM, 1=NY PM, 2=London, 3=Custom")
    parser.add_argument("--kz-start", type=int, default=100)
    parser.add_argument("--kz-end", type=int, default=1130)

    # Limits
    parser.add_argument("--max-trades", type=int, default=1)
    parser.add_argument("--max-per-side", type=int, default=1)

    # Sizing
    parser.add_argument("--contracts", type=int, default=10)
    parser.add_argument("--dollars-per-contract", type=float, default=0, help="Dynamic sizing: $ per contract (0=fixed)")

    # Liquidity
    parser.add_argument("--no-deeper-liq", action="store_true", help="Disable require deeper liquidity")
    parser.add_argument("--pwl-enabled", action="store_true", help="Enable PWL tracking for MMBM")
    parser.add_argument("--no-major-swing", action="store_true", help="Disable major swing tracking")
    parser.add_argument("--major-swing-lookback", type=int, default=500)
    parser.add_argument("--sweep-min-ticks", type=int, default=2)
    parser.add_argument("--pivot-strength", type=int, default=10)

    # Entry
    parser.add_argument("--entry-model", type=int, default=1, help="0=Immediate, 1=FVG Only, 2=Both, 3=MSS Market")
    parser.add_argument("--fvg-min-ticks", type=int, default=2)
    parser.add_argument("--max-bars-fill", type=int, default=30)
    parser.add_argument("--strictness", type=int, default=0, help="0=Aggressive, 1=Balanced, 2=Conservative")

    # Risk
    parser.add_argument("--stop-mode", type=int, default=0, help="0=Fixed, 1=Structural")
    parser.add_argument("--stop-ticks", type=int, default=40)

    # Exits
    parser.add_argument("--exit-model", type=int, default=2, help="0=RR, 1=TP1+TP2, 2=Scale+Trail, 3=Midday")
    parser.add_argument("--rr-multiple", type=float, default=3.0)
    parser.add_argument("--partial-pct", type=int, default=25)
    parser.add_argument("--no-partial", action="store_true")

    # Instrument / VIX
    parser.add_argument("--mes", action="store_true", help="Use MES ($5/point) instead of ES ($50/point)")
    parser.add_argument("--vix-filter", action="store_true", help="Enable VIX hysteresis filter")
    parser.add_argument("--vix-off", type=float, default=30.0)
    parser.add_argument("--vix-on", type=float, default=20.0)

    # EMA filter
    parser.add_argument("--ema-filter", action="store_true", help="Enable EMA directional filter")
    parser.add_argument("--ema-period", type=int, default=50, help="EMA period (default: 50)")

    # Vol ceiling filter
    parser.add_argument("--vol-ceiling", action="store_true", help="Enable realized vol ceiling filter")
    parser.add_argument("--vol-ceiling-pct", type=float, default=20.0, help="Vol ceiling threshold %% (default: 20)")
    parser.add_argument("--vol-lookback", type=int, default=20, help="Vol lookback days (default: 20)")

    # Output
    parser.add_argument("--label", default="jadecap", help="Output subdirectory label (default: jadecap)")

    # Bar size / logging
    parser.add_argument("--bar-minutes", type=int, default=5, help="Bar size in minutes (default: 5)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--skip-margin", action="store_true", help="Skip margin analysis")
    args = parser.parse_args()

    # 1. Create engine
    engine_config = BacktestEngineConfig(
        trader_id="BACKTESTER-005",
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
    enable_long = not args.short_only
    enable_short = not args.long_only

    exit_model_names = {0: "RR", 1: "TP1+TP2", 2: "Scale+Trail", 3: "Midday"}
    entry_model_names = {0: "Immediate", 1: "FVG Only", 2: "Both", 3: "MSS Market"}
    strictness_names = {0: "Aggressive", 1: "Balanced", 2: "Conservative"}

    strategy_config = JadeCapConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        setup_mode=1,
        enable_long=enable_long,
        enable_short=enable_short,
        trade_window_always_on=not args.no_always_on,
        trade_start=args.trade_start,
        trade_end=args.trade_end,
        kill_zone_preset=args.kz_preset,
        kz_custom_start=args.kz_start,
        kz_custom_end=args.kz_end,
        max_trades_per_day=args.max_trades,
        max_trades_per_side=args.max_per_side,
        contracts=args.contracts,
        dollars_per_contract=args.dollars_per_contract,
        mmbm_pwl_enabled=args.pwl_enabled,
        mmbm_major_swing_enabled=not args.no_major_swing,
        mmsm_pwh_enabled=True,
        mmsm_major_swing_high_enabled=not args.no_major_swing,
        major_swing_lookback=args.major_swing_lookback,
        require_deeper_liq=not args.no_deeper_liq,
        sweep_min_ticks=args.sweep_min_ticks,
        pivot_strength=args.pivot_strength,
        entry_model=args.entry_model,
        fvg_min_ticks=args.fvg_min_ticks,
        max_bars_to_fill=args.max_bars_fill,
        confirmation_strictness=args.strictness,
        stoploss_mode=args.stop_mode,
        stoploss_ticks=args.stop_ticks,
        exit_model=args.exit_model,
        rr_multiple=args.rr_multiple,
        partial_enabled=not args.no_partial,
        partial_pct=args.partial_pct,
        vix_filter_enabled=args.vix_filter,
        vix_off=args.vix_off,
        vix_on=args.vix_on,
        ema_filter_enabled=args.ema_filter,
        ema_period=args.ema_period,
        vol_ceiling_enabled=args.vol_ceiling,
        vol_ceiling_pct=args.vol_ceiling_pct,
        vol_lookback_days=args.vol_lookback,
        order_id_tag="005",
    )
    strategy = JadeCapStrategy(config=strategy_config, vix_lookup=vix_lookup)
    engine.add_strategy(strategy)

    # 7. Run
    print(f"\nRunning backtest ({len(bars):,} bars, {args.bar_minutes}-min)...")
    engine.run()

    # 8. Report results
    print("\n" + "=" * 60)
    print("JADECAP (ICT SETUP SELECTOR) — BACKTEST RESULTS")
    print("=" * 60)
    print(f"Period: {args.start} to {args.end}")
    print(f"Starting Capital: ${STARTING_CAPITAL:,.0f}")
    if args.dollars_per_contract > 0:
        instrument_label = f"{'MES' if args.mes else 'ES'} dynamic (${args.dollars_per_contract:,.0f}/contract)"
    else:
        instrument_label = f"{'MES' if args.mes else 'ES'} x {args.contracts}"
    print(f"Instrument: {instrument_label}")
    print(f"Bar Size: {args.bar_minutes}-min")
    direction = "Long+Short" if enable_long and enable_short else ("Long only" if enable_long else "Short only")
    print(f"Direction: {direction}")
    print(f"Entry: {entry_model_names.get(args.entry_model, '?')} | Strictness: {strictness_names.get(args.strictness, '?')}")
    print(f"Exit: {exit_model_names.get(args.exit_model, '?')} | RR: {args.rr_multiple} | Partial: {args.partial_pct}%")
    print(f"Stop: {'Structural' if args.stop_mode == 1 else 'Fixed'} ({args.stop_ticks} ticks)")
    deeper = "Required" if not args.no_deeper_liq else "Not required"
    print(f"Deeper Liquidity: {deeper} | Pivot Strength: {args.pivot_strength}")
    print(f"Max Trades/Day: {args.max_trades} | Max/Side: {args.max_per_side}")
    if args.vix_filter:
        print(f"VIX Filter: OFF > {args.vix_off}, ON < {args.vix_on}")
    if args.ema_filter:
        print(f"EMA Filter: ON (period={args.ema_period})")
    if args.vol_ceiling:
        print(f"Vol Ceiling: ON ({args.vol_ceiling_pct}%, lookback={args.vol_lookback}d)")
    print(f"Label: {args.label}")
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
        title = f"JadeCap [{args.label}] — {args.start} to {args.end} ({instrument_label}, {args.bar_minutes}min)"
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
                print_margin_report(margin_result, label=args.label)
                save_margin_summary(margin_result, str(output_dir))
                margin_chart = plot_margin_analysis(
                    margin_result, str(output_dir),
                    title=f"Margin Analysis — JadeCap [{args.label}]",
                )
                if margin_chart:
                    subprocess.Popen(["cmd", "/c", "start", "", str(margin_chart)],
                                     creationflags=0x08000000)
            except Exception as e:
                print(f"\nWarning: Margin analysis failed: {e}")
    else:
        print("No trades were generated.")

    # 9. Cleanup
    engine.reset()
    engine.dispose()


if __name__ == "__main__":
    main()
