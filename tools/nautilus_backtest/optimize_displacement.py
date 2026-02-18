"""
Displacement Candle Strategy — Parameter Sweep Optimizer.

Sweeps displacement_mult, target_rr, lookback, max_trades, bar_minutes
and ranks by Profit Factor and Sharpe Ratio.
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from instrument import create_es_instrument
from data_loader import load_es_bars
from displacement_strategy import DisplacementStrategy, DisplacementConfig

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
STARTING_CAPITAL = 25_000.0

# Parameter grid
PARAM_GRID = {
    "displacement_mult": [1.5, 2.0, 2.5, 3.0],
    "target_rr": [0, 2.0, 3.0, 4.0, 5.0],
    "lookback": [10, 20, 30],
    "max_trades": [1, 2],
    "bar_minutes": [5],
}

# Generate combos - skip target_rr=0 without trail (would just be EOD exit with no edge)
combos = []
for dm, rr, lb, mt, bm in itertools.product(
    PARAM_GRID["displacement_mult"],
    PARAM_GRID["target_rr"],
    PARAM_GRID["lookback"],
    PARAM_GRID["max_trades"],
    PARAM_GRID["bar_minutes"],
):
    if rr == 0:
        continue  # skip pure EOD - no TP rarely works
    combos.append({"displacement_mult": dm, "target_rr": rr, "lookback": lb,
                    "max_trades": mt, "bar_minutes": bm})

print(f"Total parameter combinations: {len(combos)}")
print("Loading data (one-time)...")

# Pre-load bars for each bar_minutes
bar_cache = {}
for bm in set(PARAM_GRID["bar_minutes"]):
    SIM = Venue("SIM")
    es = create_es_instrument(venue=SIM, multiplier=50)
    bars, bar_type = load_es_bars(
        zip_path=ES_ZIP_PATH,
        instrument=es,
        start_date="2024-01-01",
        end_date="2026-01-01",
        bar_minutes=bm,
    )
    bar_cache[bm] = (bars, bar_type, es)
    print(f"  {bm}-min: {len(bars):,} bars loaded")

results = []

for i, params in enumerate(combos):
    bm = params["bar_minutes"]
    bars, bar_type, es = bar_cache[bm]

    # Create engine
    engine_config = BacktestEngineConfig(
        trader_id=f"OPT-{i:03d}",
        logging=LoggingConfig(log_level="ERROR"),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

    SIM = Venue("SIM")
    engine.add_venue(
        venue=SIM,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(STARTING_CAPITAL, USD)],
    )
    engine.add_instrument(es)
    engine.add_data(bars)

    strategy_config = DisplacementConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        lookback=params["lookback"],
        displacement_mult=params["displacement_mult"],
        target_rr=params["target_rr"],
        trail_after_rr=0.0,
        trail_points=0.0,
        max_trades_per_day=params["max_trades"],
        entry_end=1530,
        eod_time=1640,
        contracts=10,
        dollars_per_contract=0.0,
        order_id_tag=f"{i:03d}",
    )
    strategy = DisplacementStrategy(config=strategy_config)
    engine.add_strategy(strategy)

    engine.run()

    # Extract results
    positions_report = engine.trader.generate_positions_report()
    row = {**params, "trades": 0, "pnl": 0, "win_rate": 0, "pf": 0, "sharpe": 0,
           "max_dd": 0, "avg_win": 0, "avg_loss": 0}

    if positions_report is not None and not positions_report.empty:
        if "realized_pnl" in positions_report.columns:
            pnls = positions_report["realized_pnl"].apply(
                lambda x: float(str(x).replace(" USD", "").replace(",", ""))
            )
            total_pnl = pnls.sum()
            wins = pnls[pnls > 0]
            losses = pnls[pnls <= 0]
            win_rate = len(wins) / len(pnls) * 100 if len(pnls) > 0 else 0
            gross_wins = wins.sum() if len(wins) > 0 else 0
            gross_losses = abs(losses.sum()) if len(losses) > 0 else 0
            pf = gross_wins / gross_losses if gross_losses > 0 else 0

            equity = pnls.cumsum()
            peak = equity.cummax()
            max_dd = (equity - peak).min()

            sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252) if len(pnls) > 1 and pnls.std() > 0 else 0

            row.update({
                "trades": len(pnls),
                "pnl": total_pnl,
                "win_rate": win_rate,
                "pf": pf,
                "sharpe": sharpe,
                "max_dd": max_dd,
                "avg_win": wins.mean() if len(wins) > 0 else 0,
                "avg_loss": losses.mean() if len(losses) > 0 else 0,
            })

    results.append(row)

    engine.reset()
    engine.dispose()

    # Progress
    status = f"PF={row['pf']:.2f} PnL=${row['pnl']:>10,.0f} WR={row['win_rate']:.0f}% DD=${row['max_dd']:>10,.0f} Trades={row['trades']}"
    sys.stdout.write(f"\r[{i+1}/{len(combos)}] mult={params['displacement_mult']:.1f} rr={params['target_rr']:.0f} lb={params['lookback']} mt={params['max_trades']} → {status}   ")
    sys.stdout.flush()

print("\n\nDone! Ranking results...\n")

df = pd.DataFrame(results)

# Filter: at least 50 trades, PF > 1.0
viable = df[(df["trades"] >= 50) & (df["pf"] > 1.0)].copy()
viable = viable.sort_values("pf", ascending=False)

print(f"{'='*100}")
print(f"TOP 20 CONFIGURATIONS (by Profit Factor, min 50 trades, PF > 1.0)")
print(f"{'='*100}")
print(f"{'Mult':>5} {'RR':>4} {'LB':>4} {'MT':>3} {'Trades':>7} {'PnL':>12} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>12} {'AvgWin':>10} {'AvgLoss':>10}")
print("-" * 100)

for _, r in viable.head(20).iterrows():
    print(f"{r['displacement_mult']:>5.1f} {r['target_rr']:>4.0f} {r['lookback']:>4.0f} {r['max_trades']:>3.0f} "
          f"{r['trades']:>7.0f} ${r['pnl']:>10,.0f} {r['win_rate']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
          f"${r['max_dd']:>10,.0f} ${r['avg_win']:>8,.0f} ${r['avg_loss']:>8,.0f}")

# Save full results
output_path = Path(__file__).parent / "results" / "displacement_sweep.csv"
df.to_csv(output_path, index=False)
print(f"\nFull results saved to {output_path}")

# Also show top by Sharpe
print(f"\n{'='*100}")
print(f"TOP 10 BY SHARPE RATIO (min 50 trades)")
print(f"{'='*100}")
sharpe_sorted = viable.sort_values("sharpe", ascending=False)
print(f"{'Mult':>5} {'RR':>4} {'LB':>4} {'MT':>3} {'Trades':>7} {'PnL':>12} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>12}")
print("-" * 100)
for _, r in sharpe_sorted.head(10).iterrows():
    print(f"{r['displacement_mult']:>5.1f} {r['target_rr']:>4.0f} {r['lookback']:>4.0f} {r['max_trades']:>3.0f} "
          f"{r['trades']:>7.0f} ${r['pnl']:>10,.0f} {r['win_rate']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
          f"${r['max_dd']:>10,.0f}")
