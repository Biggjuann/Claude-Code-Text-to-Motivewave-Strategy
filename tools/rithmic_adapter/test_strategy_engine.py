"""Test live strategy engines with real ES 5-min bars from backtest data.

Loads a ~2 week slice of real data, feeds through engines, and verifies
that entries/exits/state transitions are correct and match expectations.

Tests MagicLine in depth + smoke tests for all other engines.
"""

import sys
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

# Add this directory to path for bare imports
sys.path.insert(0, ".")

from shared_types import Action, Signal, TradeState
from engines import create_engine, STRATEGY_NAMES
from engines.magicline import MagicLineLiveEngine

ET = ZoneInfo("America/New_York")
ES_ZIP = r"C:\Users\jung_\Downloads\Backtesting data\ES_full_1min_continuous_ratio_adjusted_13wjmr (1).zip"


def load_5min_bars(start: str, end: str) -> pd.DataFrame:
    """Load real ES 1-min bars from zip, resample to 5-min, return DataFrame."""
    print(f"Loading bars: {start} to {end}...")
    with zipfile.ZipFile(ES_ZIP) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            df = pd.read_csv(
                f, header=None,
                names=["timestamp", "open", "high", "low", "close", "volume"],
                parse_dates=["timestamp"],
            )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp"] = df["timestamp"].dt.tz_localize(
        "America/New_York", ambiguous="NaT", nonexistent="shift_forward"
    )
    df = df.dropna(subset=["timestamp"])
    df = df.set_index("timestamp").sort_index()

    # Filter date range
    df = df[start:end]

    # Resample to 5-min
    bars = df.resample("5min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    print(f"  Loaded {len(bars)} 5-min bars")
    return bars


# ==================== MagicLine Tests ====================

MAGICLINE_PARAMS = {
    "length": 20,
    "touch_tolerance_ticks": 4,
    "zone_buffer_pts": 1.0,
    "came_from_pts": 5.0,
    "came_from_lookback": 10,
    "ema_filter_enabled": True,
    "ema_period": 21,
    "trade_start": "02:00",
    "trade_end": "16:00",
    "max_trades_per_day": 3,
    "stoploss_mode": "structural",
    "stop_buffer_ticks": 20,
    "be_enabled": True,
    "be_trigger_pts": 10.0,
    "tp1_r": 3.0,
    "tp2_r": 10.0,
    "partial_enabled": True,
    "partial_pct": 25,
    "contracts": 2,
    "max_contracts": 5,
    "eod_flatten_time": "16:40",
    "max_daily_loss": 5000.0,
    "tick_size": 0.25,
}


def test_warmup_and_first_signals():
    """Feed real bars, verify warmup phase then signal generation."""
    bars = load_5min_bars("2025-01-02", "2025-01-17")
    engine = MagicLineLiveEngine(MAGICLINE_PARAMS)

    total_entries = 0
    total_exits = 0
    total_be_moves = 0
    total_eod_flattens = 0
    all_signals: list[tuple[datetime, Signal]] = []
    position_qty = 0

    warmup_bars = 2 * MAGICLINE_PARAMS["length"]  # 40 bars

    for idx, (ts, row) in enumerate(bars.iterrows()):
        bar_time = ts.astimezone(ET)
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]

        signals = engine.on_bar(bar_time, o, h, l, c, position_qty=position_qty)

        for s in signals:
            all_signals.append((bar_time, s))

            if s.action == Action.BUY:
                position_qty += s.qty
                total_entries += 1
            elif s.action == Action.SELL and s.qty == 0:
                total_be_moves += 1
            elif s.action == Action.SELL and s.qty > 0:
                position_qty -= s.qty
            elif s.action == Action.FLATTEN:
                if "EOD" in s.reason:
                    total_eod_flattens += 1
                position_qty = 0
                total_exits += 1

        # Verify warmup phase
        if idx < warmup_bars:
            assert len(signals) == 0, (
                f"Bar {idx}: got signals during warmup: {signals}"
            )

    print(f"\n  Test: warmup_and_first_signals")
    print(f"  Total bars fed:    {len(bars)}")
    print(f"  Warmup bars:       {warmup_bars}")
    print(f"  Total entries:     {total_entries}")
    print(f"  Total exits:       {total_exits}")
    print(f"  BE moves:          {total_be_moves}")
    print(f"  EOD flattens:      {total_eod_flattens}")
    print(f"  Total signals:     {len(all_signals)}")
    print(f"  Final position:    {position_qty}")

    # Verify we got some activity
    assert total_entries > 0, "No entries generated — check config/data alignment"
    assert total_exits > 0, "No exits generated"

    # Print signal log
    print(f"\n  --- Signal Log ---")
    for ts, s in all_signals:
        print(f"  {ts.strftime('%Y-%m-%d %H:%M')} | {s}")

    print(f"\n  PASS: warmup_and_first_signals")


def test_state_transitions():
    """Verify trade state transitions are correct on a known pattern."""
    bars = load_5min_bars("2025-01-02", "2025-01-17")
    engine = MagicLineLiveEngine(MAGICLINE_PARAMS)

    position_qty = 0
    entry_count = 0
    state_log = []

    for ts, row in bars.iterrows():
        bar_time = ts.astimezone(ET)
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]

        signals = engine.on_bar(bar_time, o, h, l, c, position_qty=position_qty)

        for s in signals:
            if s.action == Action.BUY:
                position_qty += s.qty
                entry_count += 1

                # On entry, trade state must be properly set
                t = engine.trade
                assert t.is_active, "Trade should be active after BUY"
                assert t.entry_price > 0, "Entry price should be set"
                assert t.stop_price > 0, "Stop price should be set"
                assert t.stop_price < t.entry_price, "Stop must be below entry (long)"
                assert t.tp1_price > t.entry_price, "TP1 must be above entry"
                assert t.tp2_price > t.tp1_price, "TP2 must be above TP1"
                assert t.risk_points > 0, "Risk must be positive"
                assert not t.partial_taken, "Partial should not be taken on entry"
                assert not t.be_activated, "BE should not be activated on entry"
                assert not t.trail_active, "Trail should not be active on entry"

                state_log.append({
                    "time": bar_time,
                    "action": "ENTRY",
                    "entry": t.entry_price,
                    "stop": t.stop_price,
                    "tp1": t.tp1_price,
                    "tp2": t.tp2_price,
                    "risk": t.risk_points,
                })

            elif s.action == Action.FLATTEN:
                position_qty = 0
                state_log.append({
                    "time": bar_time,
                    "action": f"EXIT ({s.reason})",
                })

            elif s.action == Action.SELL:
                if s.qty > 0:
                    position_qty -= s.qty
                    state_log.append({
                        "time": bar_time,
                        "action": f"PARTIAL ({s.reason})",
                    })
                elif s.qty == 0:
                    state_log.append({
                        "time": bar_time,
                        "action": f"MODIFY ({s.reason})",
                    })

    # Verify: no orphan trade state left at end
    if position_qty == 0:
        assert not engine.trade.is_active, "Trade state should be reset when flat"

    print(f"\n  Test: state_transitions")
    print(f"  Entries verified:  {entry_count}")
    print(f"  --- State Log ---")
    for s in state_log:
        time_str = s["time"].strftime("%Y-%m-%d %H:%M")
        if s["action"] == "ENTRY":
            print(f"  {time_str} | ENTRY @ {s['entry']:.2f}  "
                  f"stop={s['stop']:.2f}  TP1={s['tp1']:.2f}  "
                  f"TP2={s['tp2']:.2f}  risk={s['risk']:.1f}pts")
        else:
            print(f"  {time_str} | {s['action']}")

    print(f"\n  PASS: state_transitions")


def test_eod_flatten():
    """Verify EOD flatten fires and resets state."""
    engine = MagicLineLiveEngine(MAGICLINE_PARAMS)

    # Manually set up a trade state as if we entered
    engine.trade = TradeState(
        entry_price=5900.0,
        stop_price=5895.0,
        tp1_price=5915.0,
        tp2_price=5950.0,
        risk_points=5.0,
        initial_qty=2,
        direction=1,
    )
    engine.bar_count = 50
    engine.last_reset_day = -1
    # Fill warmup history with dummy data so LB can compute
    for _ in range(50):
        engine.hist_opens.append(5900.0)
        engine.hist_closes.append(5900.0)
        engine.hist_highs.append(5905.0)
        engine.hist_lows.append(5895.0)
        engine._update_ema(5900.0)

    # Feed a bar at EOD time (16:40 = 1000 minutes)
    eod_time = datetime(2025, 1, 15, 16, 40, 0, tzinfo=ET)
    signals = engine.on_bar(eod_time, 5900.0, 5905.0, 5898.0, 5902.0,
                            position_qty=2)

    assert len(signals) == 1, f"Expected 1 EOD flatten signal, got {len(signals)}"
    assert signals[0].action == Action.FLATTEN
    assert "EOD" in signals[0].reason
    assert not engine.trade.is_active, "Trade state should be reset after EOD"
    assert engine.eod_processed, "eod_processed flag should be set"

    # Second bar after EOD should not flatten again
    eod_time2 = datetime(2025, 1, 15, 16, 45, 0, tzinfo=ET)
    signals2 = engine.on_bar(eod_time2, 5900.0, 5905.0, 5898.0, 5902.0,
                             position_qty=0)
    assert len(signals2) == 0, "No signals after EOD already processed"

    print(f"\n  Test: eod_flatten")
    print(f"  EOD signal: {signals[0]}")
    print(f"  PASS: eod_flatten")


def test_max_daily_loss():
    """Verify max daily loss triggers flatten."""
    engine = MagicLineLiveEngine(MAGICLINE_PARAMS)

    # Set up accumulated loss exceeding max
    # Set last_reset_day to match the bar we'll feed, so it doesn't trigger a daily reset
    bar_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
    engine.last_reset_day = bar_time.timetuple().tm_yday + bar_time.year * 1000
    engine.daily_pnl = -5001.0
    engine.trade = TradeState(
        entry_price=5900.0, stop_price=5895.0,
        tp1_price=5915.0, tp2_price=5950.0,
        risk_points=5.0, initial_qty=2,
        direction=1,
    )
    for _ in range(50):
        engine.hist_opens.append(5900.0)
        engine.hist_closes.append(5900.0)
        engine.hist_highs.append(5905.0)
        engine.hist_lows.append(5895.0)
        engine._update_ema(5900.0)

    # Feed a regular bar during session (same day as last_reset_day)
    signals = engine.on_bar(bar_time, 5900.0, 5905.0, 5898.0, 5902.0,
                            position_qty=2)

    assert len(signals) == 1, f"Expected 1 max loss flatten signal, got {len(signals)}"
    assert signals[0].action == Action.FLATTEN
    assert "daily loss" in signals[0].reason.lower()

    print(f"\n  Test: max_daily_loss")
    print(f"  Max loss signal: {signals[0]}")
    print(f"  PASS: max_daily_loss")


def test_snapshot_restore():
    """Verify state can be serialized and restored."""
    engine = MagicLineLiveEngine(MAGICLINE_PARAMS)

    # Feed some bars to build state
    base_time = datetime(2025, 1, 15, 9, 30, 0, tzinfo=ET)
    for i in range(50):
        price = 5900.0 + i * 0.5
        bar_time = base_time + timedelta(minutes=i * 5)
        engine.on_bar(
            bar_time,
            price - 1, price + 2, price - 3, price,
            position_qty=0,
        )

    # Snapshot
    snap = engine.get_state_snapshot()
    assert "trade" in snap
    assert "bars" in snap
    assert len(snap["bars"]) > 0

    # Restore into fresh engine
    engine2 = MagicLineLiveEngine(MAGICLINE_PARAMS)
    trade = TradeState.from_dict(snap["trade"])
    engine2.restore_state(trade, snap["bars"])

    assert len(engine2.hist_opens) == len(snap["bars"])
    assert engine2.hist_closes[-1] == engine.hist_closes[-1]

    print(f"\n  Test: snapshot_restore")
    print(f"  Snapshot bars:     {len(snap['bars'])}")
    print(f"  Restored bars:     {len(engine2.hist_opens)}")
    print(f"  Last close match:  {engine2.hist_closes[-1]:.2f} == {engine.hist_closes[-1]:.2f}")
    print(f"  PASS: snapshot_restore")


# ==================== Engine Factory Test ====================

def test_engine_factory():
    """Verify create_engine() works for all registered strategies."""
    for name in STRATEGY_NAMES:
        engine = create_engine(name, {})
        assert engine.strategy_name == name, f"Expected {name}, got {engine.strategy_name}"
        print(f"  Factory OK: {name} → {engine.__class__.__name__}")

    # Unknown strategy should raise
    try:
        create_engine("NonExistent", {})
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    print(f"\n  PASS: engine_factory")


# ==================== Smoke Tests ====================

def test_smoke_all_engines():
    """Feed 100 synthetic bars into each engine, verify no crashes."""
    base_time = datetime(2025, 1, 15, 9, 30, 0, tzinfo=ET)

    for name in STRATEGY_NAMES:
        engine = create_engine(name, {})
        total_signals = 0

        for i in range(100):
            price = 5900.0 + (i % 30) * 0.5 - 7.5  # oscillate around 5900
            bar_time = base_time + timedelta(minutes=i * 5)
            h = price + 3.0
            l = price - 3.0
            o = price - 0.5
            c = price + 0.5

            signals = engine.on_bar(bar_time, o, h, l, c, position_qty=0)
            total_signals += len(signals)

        # Snapshot and restore
        snap = engine.get_state_snapshot()
        assert "trade" in snap
        assert "bars" in snap

        print(f"  Smoke OK: {name:15s} — {total_signals:3d} signals, "
              f"{len(snap['bars']):3d} bars in snapshot")

    print(f"\n  PASS: smoke_all_engines")


if __name__ == "__main__":
    print("=" * 60)
    print("Live Strategy Engines — Test Suite")
    print("=" * 60)

    # Unit tests (no data needed)
    test_engine_factory()
    test_eod_flatten()
    test_max_daily_loss()
    test_snapshot_restore()
    test_smoke_all_engines()

    # Integration tests (need real data)
    try:
        test_warmup_and_first_signals()
        test_state_transitions()
    except FileNotFoundError:
        print("\n  SKIP: real data tests (ES zip not found)")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
