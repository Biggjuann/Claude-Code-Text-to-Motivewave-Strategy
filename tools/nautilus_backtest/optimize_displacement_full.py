"""
Displacement Candle Strategy — Full-Period Optimizer (2010-2026).

Re-optimizes across entire dataset to find robust parameters
that aren't overfit to a single regime.
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

START = "2010-01-01"
END = "2026-01-01"

# Parameter grid
PARAM_GRID = {
    "displacement_mult": [1.5, 2.0, 2.5, 3.0],
    "target_rr": [2.0, 3.0, 4.0, 5.0],
    "lookback": [10, 20, 30],
    "max_trades": [1, 2],
}

combos = []
for dm, rr, lb, mt in itertools.product(
    PARAM_GRID["displacement_mult"],
    PARAM_GRID["target_rr"],
    PARAM_GRID["lookback"],
    PARAM_GRID["max_trades"],
):
    combos.append({"displacement_mult": dm, "target_rr": rr, "lookback": lb, "max_trades": mt})

print(f"Total parameter combinations: {len(combos)}")
print(f"Period: {START} to {END} (16 years)")
print("Loading data (one-time)...")

SIM = Venue("SIM")
es = create_es_instrument(venue=SIM, multiplier=50)
bars, bar_type = load_es_bars(
    zip_path=ES_ZIP_PATH,
    instrument=es,
    start_date=START,
    end_date=END,
    bar_minutes=5,
)
print(f"  Loaded {len(bars):,} 5-min bars")

results = []

for i, params in enumerate(combos):
    engine_config = BacktestEngineConfig(
        trader_id=f"FOPT-{i:03d}",
        logging=LoggingConfig(log_level="ERROR"),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

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

    positions_report = engine.trader.generate_positions_report()
    row = {**params, "trades": 0, "pnl": 0, "win_rate": 0, "pf": 0, "sharpe": 0,
           "max_dd": 0, "avg_win": 0, "avg_loss": 0, "calmar": 0,
           "pnl_per_trade": 0, "annual_pnl": 0}

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
            calmar = abs(total_pnl / max_dd) if max_dd != 0 else 0

            row.update({
                "trades": len(pnls),
                "pnl": total_pnl,
                "win_rate": win_rate,
                "pf": pf,
                "sharpe": sharpe,
                "max_dd": max_dd,
                "avg_win": wins.mean() if len(wins) > 0 else 0,
                "avg_loss": losses.mean() if len(losses) > 0 else 0,
                "calmar": calmar,
                "pnl_per_trade": total_pnl / len(pnls) if len(pnls) > 0 else 0,
                "annual_pnl": total_pnl / 16,  # 16 years
            })

    results.append(row)

    engine.reset()
    engine.dispose()

    status = (f"PF={row['pf']:.2f} PnL=${row['pnl']:>12,.0f} WR={row['win_rate']:.0f}% "
              f"Sharpe={row['sharpe']:.2f} DD=${row['max_dd']:>12,.0f} Trades={row['trades']}")
    sys.stdout.write(f"\r[{i+1}/{len(combos)}] mult={params['displacement_mult']:.1f} "
                     f"rr={params['target_rr']:.0f} lb={params['lookback']} "
                     f"mt={params['max_trades']} -> {status}   ")
    sys.stdout.flush()

print("\n\nDone! Ranking results...\n")

df = pd.DataFrame(results)

# Save full results
output_path = Path(__file__).parent / "results" / "displacement_full_sweep.csv"
df.to_csv(output_path, index=False)

# Filter: min 200 trades, PF > 1.0
viable = df[(df["trades"] >= 200) & (df["pf"] > 1.0)].copy()

# Rank by Sharpe (most robust risk-adjusted metric for long periods)
viable = viable.sort_values("sharpe", ascending=False)

print(f"{'='*120}")
print(f"TOP 20 CONFIGURATIONS — FULL PERIOD 2010-2026 (by Sharpe, min 200 trades, PF > 1.0)")
print(f"{'='*120}")
print(f"{'Mult':>5} {'RR':>4} {'LB':>4} {'MT':>3} {'Trades':>7} {'PnL':>14} {'$/Trade':>9} "
      f"{'$/Year':>10} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>12} {'Calmar':>7}")
print("-" * 120)

for _, r in viable.head(20).iterrows():
    print(f"{r['displacement_mult']:>5.1f} {r['target_rr']:>4.0f} {r['lookback']:>4.0f} "
          f"{r['max_trades']:>3.0f} {r['trades']:>7.0f} ${r['pnl']:>12,.0f} "
          f"${r['pnl_per_trade']:>7,.0f} ${r['annual_pnl']:>8,.0f} "
          f"{r['win_rate']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
          f"${r['max_dd']:>10,.0f} {r['calmar']:>6.2f}")

# Also show by PF
print(f"\n{'='*120}")
print(f"TOP 10 BY PROFIT FACTOR — FULL PERIOD 2010-2026")
print(f"{'='*120}")
pf_sorted = viable.sort_values("pf", ascending=False)
print(f"{'Mult':>5} {'RR':>4} {'LB':>4} {'MT':>3} {'Trades':>7} {'PnL':>14} {'$/Trade':>9} "
      f"{'$/Year':>10} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>12} {'Calmar':>7}")
print("-" * 120)
for _, r in pf_sorted.head(10).iterrows():
    print(f"{r['displacement_mult']:>5.1f} {r['target_rr']:>4.0f} {r['lookback']:>4.0f} "
          f"{r['max_trades']:>3.0f} {r['trades']:>7.0f} ${r['pnl']:>12,.0f} "
          f"${r['pnl_per_trade']:>7,.0f} ${r['annual_pnl']:>8,.0f} "
          f"{r['win_rate']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
          f"${r['max_dd']:>10,.0f} {r['calmar']:>6.2f}")

print(f"\nFull results saved to {output_path}")

# Summary of all combos
total_viable = len(viable)
total_tested = len(df)
print(f"\nViable configs (PF>1.0, 200+ trades): {total_viable}/{total_tested} ({total_viable/total_tested*100:.0f}%)")
