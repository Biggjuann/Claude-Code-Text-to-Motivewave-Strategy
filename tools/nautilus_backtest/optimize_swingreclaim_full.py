"""
SwingReclaim Strategy — Full-Period Optimizer (2010-2026).

Sweeps strength, reclaim_window, tp1_points, trail_points across 16 years
to find robust parameters that aren't overfit to a single regime.
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
from swingreclaim_strategy import SwingReclaimStrategy, SwingReclaimConfig

ES_ZIP_PATH = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"
STARTING_CAPITAL = 25_000.0

START = "2010-01-01"
END = "2026-01-01"

# Parameter grid
PARAM_GRID = {
    "strength": [30, 45, 60],
    "reclaim_window": [15, 20, 30],
    "tp1_points": [15.0, 20.0, 25.0, 30.0],
    "trail_points": [10.0, 15.0, 20.0],
}

combos = []
for st, rw, tp, tr in itertools.product(
    PARAM_GRID["strength"],
    PARAM_GRID["reclaim_window"],
    PARAM_GRID["tp1_points"],
    PARAM_GRID["trail_points"],
):
    combos.append({"strength": st, "reclaim_window": rw, "tp1_points": tp, "trail_points": tr})

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
        trader_id=f"SOPT-{i:03d}",
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

    strategy_config = SwingReclaimConfig(
        instrument_id=es.id,
        bar_type=bar_type,
        strength=params["strength"],
        reclaim_window=params["reclaim_window"],
        tp1_points=params["tp1_points"],
        trail_points=params["trail_points"],
        # Fixed params (current deployed defaults)
        enable_long=True,
        enable_short=True,
        max_trades_day=3,
        stop_buffer_ticks=4,
        stop_min_pts=2.0,
        stop_max_pts=40.0,
        be_enabled=True,
        be_trigger_pts=10.0,
        tp1_pct=50,
        eod_time=1640,
        contracts=10,
        dollars_per_contract=0.0,
        order_id_tag=f"{i:03d}",
    )
    strategy = SwingReclaimStrategy(config=strategy_config)
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
                "annual_pnl": total_pnl / 16,
            })

    results.append(row)

    engine.reset()
    engine.dispose()

    status = (f"PF={row['pf']:.2f} PnL=${row['pnl']:>12,.0f} WR={row['win_rate']:.0f}% "
              f"Sharpe={row['sharpe']:.2f} DD=${row['max_dd']:>12,.0f} Trades={row['trades']}")
    sys.stdout.write(f"\r[{i+1}/{len(combos)}] str={params['strength']} "
                     f"rw={params['reclaim_window']} tp={params['tp1_points']:.0f} "
                     f"tr={params['trail_points']:.0f} -> {status}   ")
    sys.stdout.flush()

print("\n\nDone! Ranking results...\n")

df = pd.DataFrame(results)

# Save full results
output_dir = Path(__file__).parent / "results" / "swingreclaim_full_sweep"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "swingreclaim_full_sweep.csv"
df.to_csv(output_path, index=False)

# Filter: min 200 trades, PF > 1.0
viable = df[(df["trades"] >= 200) & (df["pf"] > 1.0)].copy()

# Rank by Sharpe
viable = viable.sort_values("sharpe", ascending=False)

print(f"{'='*130}")
print(f"TOP 20 CONFIGURATIONS — SWINGRECLAIM FULL PERIOD 2010-2026 (by Sharpe, min 200 trades, PF > 1.0)")
print(f"{'='*130}")
print(f"{'Str':>4} {'RW':>4} {'TP1':>5} {'Trail':>5} {'Trades':>7} {'PnL':>14} {'$/Trade':>9} "
      f"{'$/Year':>10} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>12} {'Calmar':>7}")
print("-" * 130)

for _, r in viable.head(20).iterrows():
    print(f"{r['strength']:>4.0f} {r['reclaim_window']:>4.0f} {r['tp1_points']:>5.0f} "
          f"{r['trail_points']:>5.0f} {r['trades']:>7.0f} ${r['pnl']:>12,.0f} "
          f"${r['pnl_per_trade']:>7,.0f} ${r['annual_pnl']:>8,.0f} "
          f"{r['win_rate']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
          f"${r['max_dd']:>10,.0f} {r['calmar']:>6.2f}")

# Also show by PF
print(f"\n{'='*130}")
print(f"TOP 10 BY PROFIT FACTOR — SWINGRECLAIM FULL PERIOD 2010-2026")
print(f"{'='*130}")
pf_sorted = viable.sort_values("pf", ascending=False)
print(f"{'Str':>4} {'RW':>4} {'TP1':>5} {'Trail':>5} {'Trades':>7} {'PnL':>14} {'$/Trade':>9} "
      f"{'$/Year':>10} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>12} {'Calmar':>7}")
print("-" * 130)
for _, r in pf_sorted.head(10).iterrows():
    print(f"{r['strength']:>4.0f} {r['reclaim_window']:>4.0f} {r['tp1_points']:>5.0f} "
          f"{r['trail_points']:>5.0f} {r['trades']:>7.0f} ${r['pnl']:>12,.0f} "
          f"${r['pnl_per_trade']:>7,.0f} ${r['annual_pnl']:>8,.0f} "
          f"{r['win_rate']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
          f"${r['max_dd']:>10,.0f} {r['calmar']:>6.2f}")

print(f"\nFull results saved to {output_path}")

total_viable = len(viable)
total_tested = len(df)
print(f"\nViable configs (PF>1.0, 200+ trades): {total_viable}/{total_tested} ({total_viable/total_tested*100:.0f}%)")
