"""SwingReclaim live engine — pivot break-then-reclaim.

Ported from swingreclaim_strategy.py (NautilusTrader).
Bidirectional swing point detection, state machine: ACTIVE → BROKEN → reclaim entry.
Replay lag mechanism for retroactive pivot detection.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime

from shared_types import Action, Signal, TradeState
from engines.base import BaseLiveEngine

log = logging.getLogger(__name__)

STATE_ACTIVE = 0
STATE_BROKEN = 1


@dataclass
class SwingLevel:
    price: float
    is_high: bool
    state: int = STATE_ACTIVE
    sweep_extreme: float = math.nan
    detected_bar: int = 0
    broke_bar: int = -1
    traded: bool = False
    canceled: bool = False
    reclaim_bar: int = -1


DEFAULTS = {
    "enable_long": True,
    "enable_short": True,
    "strength": 45,
    "reclaim_window": 20,
    "max_trades_per_day": 3,
    "trade_start": "09:30",
    "trade_end": "16:00",
    "eod_flatten_time": "16:40",
    "contracts": 1,
    "max_contracts": 5,
    "stop_buffer_ticks": 4,
    "stop_min_pts": 2.0,
    "stop_max_pts": 40.0,
    "be_enabled": True,
    "be_trigger_pts": 10.0,
    "tp1_points": 20.0,
    "tp1_pct": 50,
    "trail_points": 15.0,
    "max_daily_loss": 500.0,
    "tick_size": 0.25,
    "session_enabled": False,
}


def _time_to_minutes(t: str) -> int:
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


class SwingReclaimLiveEngine(BaseLiveEngine):
    """Swing point break-then-reclaim strategy — bidirectional."""

    def __init__(self, params: dict):
        self.params = {**DEFAULTS, **params}
        self._tick_size = self.params["tick_size"]
        self._strength = self.params["strength"]
        self._eod_flatten_min = _time_to_minutes(self.params["eod_flatten_time"])
        self._trade_start_min = _time_to_minutes(self.params["trade_start"])
        self._trade_end_min = _time_to_minutes(self.params["trade_end"])

        # Bar history
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.hist_closes: list[float] = []
        self.max_hist = max(500, self._strength * 4)

        # Swing levels
        self.swing_levels: list[SwingLevel] = []
        self.last_checked_pivot_bar: int = -1
        self.pending_reclaims: list[SwingLevel] = []

        # Trade state
        self.trade = TradeState()
        self.is_long_trade: bool = False
        self.best_price: float = math.nan
        self.trail_stop: float = math.nan
        self.trailing_active: bool = False

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.daily_pnl: float = 0.0
        self.eod_processed: bool = False

    @property
    def strategy_name(self) -> str:
        return "SwingReclaim"

    def on_bar(self, bar_time: datetime, o: float, h: float, l: float,
               c: float, position_qty: int = 0) -> list[Signal]:
        self.bar_count += 1
        signals: list[Signal] = []
        p = self.params

        self.hist_highs.append(h)
        self.hist_lows.append(l)
        self.hist_closes.append(c)
        if len(self.hist_highs) > self.max_hist:
            self.hist_highs.pop(0)
            self.hist_lows.pop(0)
            self.hist_closes.pop(0)

        if self.bar_count < self._strength * 2 + 1:
            return signals

        bar_minutes = bar_time.hour * 60 + bar_time.minute
        bar_day = bar_time.timetuple().tm_yday + bar_time.year * 1000

        # Daily reset
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.daily_pnl = 0.0
            self.eod_processed = False
            self.last_reset_day = bar_day

        # Detect new swing points
        self._detect_swing_points()

        # Run state machine
        self.pending_reclaims.clear()
        self._run_state_machine(h, l, c, self.bar_count, live=True)

        # EOD flatten
        if bar_minutes >= self._eod_flatten_min and not self.eod_processed:
            if position_qty != 0 or self.trade.is_active:
                signals.append(Signal(
                    action=Action.FLATTEN, qty=abs(position_qty),
                    reason=f"EOD flatten at {bar_time.strftime('%H:%M')}",
                ))
                self._reset_trade_state()
            self.eod_processed = True
            return signals

        # Trade management
        if position_qty != 0 and self.trade.is_active:
            mgmt = self._manage_position(h, l, c, abs(position_qty))
            signals.extend(mgmt)
            return signals

        if self.trade.is_active and position_qty == 0:
            self._reset_trade_state()

        # Entry filters
        if p["session_enabled"]:
            if not (self._trade_start_min <= bar_minutes < self._trade_end_min):
                return signals
        if self.trades_today >= p["max_trades_per_day"]:
            return signals
        if bar_minutes >= self._eod_flatten_min:
            return signals

        # Fire entry from pending reclaims
        if self.pending_reclaims:
            lv = self.pending_reclaims[-1]
            if lv.is_high and p["enable_short"]:
                entry_sigs = self._enter_trade(False, c, lv.sweep_extreme, lv.price)
                signals.extend(entry_sigs)
            elif not lv.is_high and p["enable_long"]:
                entry_sigs = self._enter_trade(True, c, lv.sweep_extreme, lv.price)
                signals.extend(entry_sigs)

        # Prune periodically
        if self.bar_count % 100 == 0:
            self.swing_levels = [
                lv for lv in self.swing_levels
                if not lv.canceled and not lv.traded
            ][-200:]

        return signals

    def check_eod_flatten(self, bar_time: datetime) -> bool:
        return bar_time.hour * 60 + bar_time.minute >= self._eod_flatten_min

    def restore_state(self, trade_state: TradeState, bars: list[dict]) -> None:
        self.trade = trade_state
        for bar in bars:
            self.hist_highs.append(bar["high"])
            self.hist_lows.append(bar["low"])
            self.hist_closes.append(bar["close"])
        log.info("State restored: trade=%s, bars=%d", trade_state.is_active, len(bars))

    def get_state_snapshot(self) -> dict:
        n = min(len(self.hist_highs), self.max_hist)
        bars = []
        for i in range(len(self.hist_highs) - n, len(self.hist_highs)):
            bars.append({
                "high": self.hist_highs[i], "low": self.hist_lows[i],
                "close": self.hist_closes[i], "open": self.hist_closes[i],
            })
        return {
            "trade": self.trade.to_dict(),
            "bars": bars,
            "trades_today": self.trades_today,
            "daily_pnl": self.daily_pnl,
            "bar_count": self.bar_count,
        }

    # ==================== State Machine ====================

    def _run_state_machine(self, h: float, l: float, c: float,
                           abs_bar: int, live: bool = False):
        p = self.params
        for lv in self.swing_levels:
            if lv.traded or lv.canceled:
                continue
            if lv.state == STATE_BROKEN and lv.broke_bar >= 0:
                if (abs_bar - lv.broke_bar) > p["reclaim_window"]:
                    lv.canceled = True
                    continue
            if lv.is_high:
                if lv.state == STATE_ACTIVE and c > lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = h
                elif lv.state == STATE_BROKEN:
                    if h > lv.sweep_extreme:
                        lv.sweep_extreme = h
                    if c < lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar
                        if live:
                            self.pending_reclaims.append(lv)
            else:
                if lv.state == STATE_ACTIVE and c < lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = l
                elif lv.state == STATE_BROKEN:
                    if l < lv.sweep_extreme:
                        lv.sweep_extreme = l
                    if c > lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar
                        if live:
                            self.pending_reclaims.append(lv)

    # ==================== Swing Point Detection ====================

    def _detect_swing_points(self):
        strength = self._strength
        n = len(self.hist_highs)
        if n < 2 * strength + 1:
            return

        candidate_bar = self.bar_count - strength
        if candidate_bar <= self.last_checked_pivot_bar:
            return
        self.last_checked_pivot_bar = candidate_bar
        check_idx = n - 1 - strength

        # Pivot high
        h_val = self.hist_highs[check_idx]
        is_pivot_high = True
        for j in range(check_idx - strength, check_idx + strength + 1):
            if j == check_idx:
                continue
            if self.hist_highs[j] > h_val:
                is_pivot_high = False
                break
        if is_pivot_high:
            lv = SwingLevel(price=h_val, is_high=True, detected_bar=candidate_bar)
            self.swing_levels.append(lv)
            self._replay_lag(lv, strength)

        # Pivot low
        l_val = self.hist_lows[check_idx]
        is_pivot_low = True
        for j in range(check_idx - strength, check_idx + strength + 1):
            if j == check_idx:
                continue
            if self.hist_lows[j] < l_val:
                is_pivot_low = False
                break
        if is_pivot_low:
            lv = SwingLevel(price=l_val, is_high=False, detected_bar=candidate_bar)
            self.swing_levels.append(lv)
            self._replay_lag(lv, strength)

    def _replay_lag(self, lv: SwingLevel, lag_bars: int):
        p = self.params
        n = len(self.hist_highs)
        start_idx = n - lag_bars
        end_idx = n - 1

        for i in range(max(0, start_idx), end_idx):
            if lv.traded or lv.canceled:
                break
            h = self.hist_highs[i]
            l_bar = self.hist_lows[i]
            c = self.hist_closes[i]
            abs_bar = self.bar_count - (n - 1 - i)

            if lv.state == STATE_BROKEN and lv.broke_bar >= 0:
                if (abs_bar - lv.broke_bar) > p["reclaim_window"]:
                    lv.canceled = True
                    break

            if lv.is_high:
                if lv.state == STATE_ACTIVE and c > lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = h
                elif lv.state == STATE_BROKEN:
                    if h > lv.sweep_extreme:
                        lv.sweep_extreme = h
                    if c < lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar
            else:
                if lv.state == STATE_ACTIVE and c < lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = l_bar
                elif lv.state == STATE_BROKEN:
                    if l_bar < lv.sweep_extreme:
                        lv.sweep_extreme = l_bar
                    if c > lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar

    # ==================== Enter Trade ====================

    def _enter_trade(self, is_long: bool, close: float,
                     sweep_extreme: float, level_price: float) -> list[Signal]:
        p = self.params
        signals: list[Signal] = []
        tick = self._tick_size
        stop_buffer = p["stop_buffer_ticks"] * tick

        if is_long:
            stop = sweep_extreme - stop_buffer
            tp1 = close + p["tp1_points"]
        else:
            stop = sweep_extreme + stop_buffer
            tp1 = close - p["tp1_points"]

        dist = abs(close - stop)
        if dist < p["stop_min_pts"]:
            stop = (close - p["stop_min_pts"]) if is_long else (close + p["stop_min_pts"])
        if dist > p["stop_max_pts"]:
            stop = (close - p["stop_max_pts"]) if is_long else (close + p["stop_max_pts"])

        num_contracts = min(p["contracts"], p["max_contracts"])
        action = Action.BUY if is_long else Action.SELL
        direction = 1 if is_long else -1

        signals.append(Signal(
            action=action, qty=num_contracts,
            reason=f"{'Long' if is_long else 'Short'} reclaim: level={level_price:.2f}, sweep={sweep_extreme:.2f}",
        ))

        self.trade = TradeState(
            entry_price=close, stop_price=stop, tp1_price=tp1,
            risk_points=abs(close - stop), initial_qty=num_contracts,
            direction=direction,
        )
        self.is_long_trade = is_long
        self.best_price = close
        self.trail_stop = math.nan
        self.trailing_active = False
        self.trades_today += 1

        log.info(
            "%s RECLAIM: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, sweep=%.2f",
            "LONG" if is_long else "SHORT", num_contracts, close, stop, tp1, sweep_extreme,
        )
        return signals

    # ==================== Position Management ====================

    def _manage_position(self, high: float, low: float, close: float,
                         position_qty: int) -> list[Signal]:
        p = self.params
        trade = self.trade
        signals: list[Signal] = []
        is_long = self.is_long_trade

        if is_long:
            if math.isnan(self.best_price) or high > self.best_price:
                self.best_price = high
        else:
            if math.isnan(self.best_price) or low < self.best_price:
                self.best_price = low

        effective_stop = trade.stop_price
        if not math.isnan(self.trail_stop) and self.trailing_active:
            if is_long:
                effective_stop = max(effective_stop, self.trail_stop)
            else:
                effective_stop = min(effective_stop, self.trail_stop)

        if is_long and low <= effective_stop:
            signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                  reason=f"Long stopped at {effective_stop:.2f}"))
            self._reset_trade_state()
            return signals
        if not is_long and high >= effective_stop:
            signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                  reason=f"Short stopped at {effective_stop:.2f}"))
            self._reset_trade_state()
            return signals

        if p["be_enabled"] and not trade.be_activated:
            profit = (self.best_price - trade.entry_price) if is_long else (trade.entry_price - self.best_price)
            if profit >= p["be_trigger_pts"]:
                trade.stop_price = trade.entry_price
                trade.be_activated = True

        if not trade.partial_taken:
            tp1_hit = (is_long and high >= trade.tp1_price) or (not is_long and low <= trade.tp1_price)
            if tp1_hit:
                partial_qty = max(1, int(math.ceil(trade.initial_qty * p["tp1_pct"] / 100.0)))
                if partial_qty > 0 and partial_qty < position_qty:
                    close_action = Action.SELL if is_long else Action.BUY
                    signals.append(Signal(action=close_action, qty=partial_qty,
                                          reason=f"TP1: closed {partial_qty} of {position_qty}"))
                    trade.partial_taken = True
                else:
                    signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                          reason=f"Full exit at TP1"))
                    self._reset_trade_state()
                    return signals

        if trade.partial_taken and not self.trailing_active:
            self.trailing_active = True
            if is_long:
                self.trail_stop = self.best_price - p["trail_points"]
            else:
                self.trail_stop = self.best_price + p["trail_points"]

        if self.trailing_active:
            if is_long:
                new_trail = self.best_price - p["trail_points"]
                if math.isnan(self.trail_stop) or new_trail > self.trail_stop:
                    self.trail_stop = new_trail
            else:
                new_trail = self.best_price + p["trail_points"]
                if math.isnan(self.trail_stop) or new_trail < self.trail_stop:
                    self.trail_stop = new_trail

        return signals

    def _reset_trade_state(self) -> None:
        self.trade = TradeState()
        self.is_long_trade = False
        self.best_price = math.nan
        self.trail_stop = math.nan
        self.trailing_active = False
