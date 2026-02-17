"""IFVG Retest live engine — 3-bar shadow pattern + zone retest.

Ported from ifvg_strategy.py (NautilusTrader).
Detects bullish/bearish IFVGs, tracks zone states, enters on retests.
Long + Short, TP1 partial + trailing stop.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from shared_types import Action, Signal, TradeState
from engines.base import BaseLiveEngine

log = logging.getLogger(__name__)


# ==================== Zone Data ====================

class ZoneState(IntEnum):
    ACTIVE = 0
    VIOLATED = 1
    TRADED = 2
    EXPIRED = 3


@dataclass
class IFVGZone:
    top: float
    bottom: float
    avg: float
    is_bullish: bool
    bar_index: int
    state: int = ZoneState.ACTIVE
    traded: bool = False

    def __init__(self, top, bottom, is_bullish, bar_index):
        self.top = top
        self.bottom = bottom
        self.avg = (top + bottom) / 2.0
        self.is_bullish = is_bullish
        self.bar_index = bar_index
        self.state = ZoneState.ACTIVE
        self.traded = False


# ==================== Defaults ====================

DEFAULTS = {
    "enable_long": True,
    "enable_short": True,
    "shadow_threshold_pct": 30.0,
    "max_wait_bars": 30,
    "trade_start": "09:30",
    "trade_end": "16:00",
    "eod_flatten_time": "16:40",
    "max_trades_per_day": 3,
    "contracts": 1,
    "max_contracts": 5,
    "stop_buffer_ticks": 40,
    "tick_size": 0.25,
    "stop_min_pts": 2.0,
    "stop_max_pts": 40.0,
    "be_enabled": True,
    "be_trigger_pts": 10.0,
    "tp1_points": 20.0,
    "tp1_pct": 50,
    "trail_points": 15.0,
    "max_daily_loss": 500.0,
    "session_enabled": False,
}


def _time_to_minutes(t: str) -> int:
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0 else 0.0


class IFVGLiveEngine(BaseLiveEngine):
    """IFVG Retest strategy — bidirectional."""

    def __init__(self, params: dict):
        self.params = {**DEFAULTS, **params}
        self._tick_size = self.params["tick_size"]
        self._threshold = self.params["shadow_threshold_pct"] / 100.0
        self._eod_flatten_min = _time_to_minutes(self.params["eod_flatten_time"])
        self._trade_start_min = _time_to_minutes(self.params["trade_start"])
        self._trade_end_min = _time_to_minutes(self.params["trade_end"])

        # Bar history (keep 3 recent for detection)
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.max_hist = 100

        # Zone tracking
        self.zones: list[IFVGZone] = []
        self.bar_count: int = 0

        # Trade state
        self.trade = TradeState()
        self.is_long_trade: bool = False
        self.best_price: float = math.nan
        self.trail_stop: float = math.nan
        self.trailing_active: bool = False

        # Daily tracking
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.daily_pnl: float = 0.0
        self.eod_processed: bool = False

    @property
    def strategy_name(self) -> str:
        return "IFVG"

    def on_bar(self, bar_time: datetime, o: float, h: float, l: float,
               c: float, position_qty: int = 0) -> list[Signal]:
        self.bar_count += 1
        signals: list[Signal] = []

        self.hist_opens.append(o)
        self.hist_closes.append(c)
        self.hist_highs.append(h)
        self.hist_lows.append(l)
        if len(self.hist_opens) > self.max_hist:
            self.hist_opens.pop(0)
            self.hist_closes.pop(0)
            self.hist_highs.pop(0)
            self.hist_lows.pop(0)

        if len(self.hist_opens) < 3:
            return signals

        # Previous bars for IFVG detection
        o1 = self.hist_opens[-2]
        c1 = self.hist_closes[-2]
        o2 = self.hist_opens[-3]
        h2 = self.hist_highs[-3]
        l2 = self.hist_lows[-3]
        c2 = self.hist_closes[-3]

        bar_minutes = bar_time.hour * 60 + bar_time.minute
        bar_day = bar_time.timetuple().tm_yday + bar_time.year * 1000
        p = self.params

        # Daily reset
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.daily_pnl = 0.0
            self.eod_processed = False
            self.last_reset_day = bar_day

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

        # IFVG Zone Detection
        r = h - l
        b0 = abs(c - o)
        b1 = abs(c1 - o1)
        b2 = abs(c2 - o2)

        # Bullish IFVG
        if b1 > max(b0, b2) and l < h2:
            lower_shadow_0 = min(c, o) - l
            upper_shadow_2 = h2 - max(c2, o2)
            bull_top = (min(c, o) + l) / 2.0
            bull_btm = (max(c2, o2) + h2) / 2.0
            if (_safe_div(lower_shadow_0, r) > self._threshold
                    and _safe_div(upper_shadow_2, r) > self._threshold
                    and bull_top > bull_btm):
                self.zones.append(IFVGZone(bull_top, bull_btm, True, self.bar_count))

        # Bearish IFVG
        if b1 > max(b0, b2) and h > l2:
            upper_shadow_0 = h - max(c, o)
            lower_shadow_2 = min(c2, o2) - l2
            bear_top = (min(c2, o2) + l2) / 2.0
            bear_btm = (max(c, o) + h) / 2.0
            if (_safe_div(upper_shadow_0, r) > self._threshold
                    and _safe_div(lower_shadow_2, r) > self._threshold
                    and bear_top > bear_btm):
                self.zones.append(IFVGZone(bear_top, bear_btm, False, self.bar_count))

        # Zone state updates
        for zone in self.zones:
            if zone.state != ZoneState.ACTIVE:
                continue
            if self.bar_count <= zone.bar_index:
                continue
            if (self.bar_count - zone.bar_index) > p["max_wait_bars"]:
                zone.state = ZoneState.EXPIRED
                continue
            if zone.is_bullish and c < zone.bottom:
                zone.state = ZoneState.VIOLATED
                continue
            if not zone.is_bullish and c > zone.top:
                zone.state = ZoneState.VIOLATED
                continue

        # Entry check
        in_session = not p["session_enabled"] or (
            self._trade_start_min <= bar_minutes < self._trade_end_min)
        past_eod = bar_minutes >= self._eod_flatten_min
        can_enter = (not past_eod and in_session
                     and self.trades_today < p["max_trades_per_day"])

        if can_enter:
            for zone in self.zones:
                if zone.state != ZoneState.ACTIVE or self.bar_count <= zone.bar_index:
                    continue
                if zone.is_bullish and p["enable_long"]:
                    if l <= zone.top and c > zone.bottom:
                        zone.state = ZoneState.TRADED
                        entry_sigs = self._enter_trade(zone, True, c)
                        signals.extend(entry_sigs)
                        break
                if not zone.is_bullish and p["enable_short"]:
                    if h >= zone.bottom and c < zone.top:
                        zone.state = ZoneState.TRADED
                        entry_sigs = self._enter_trade(zone, False, c)
                        signals.extend(entry_sigs)
                        break

        self._prune_zones()
        return signals

    def check_eod_flatten(self, bar_time: datetime) -> bool:
        return bar_time.hour * 60 + bar_time.minute >= self._eod_flatten_min

    def restore_state(self, trade_state: TradeState, bars: list[dict]) -> None:
        self.trade = trade_state
        for bar in bars:
            self.hist_opens.append(bar["open"])
            self.hist_closes.append(bar["close"])
            self.hist_highs.append(bar["high"])
            self.hist_lows.append(bar["low"])
        log.info("State restored: trade=%s, bars=%d", trade_state.is_active, len(bars))

    def get_state_snapshot(self) -> dict:
        n = min(len(self.hist_opens), self.max_hist)
        bars = []
        for i in range(len(self.hist_opens) - n, len(self.hist_opens)):
            bars.append({
                "open": self.hist_opens[i], "close": self.hist_closes[i],
                "high": self.hist_highs[i], "low": self.hist_lows[i],
            })
        return {
            "trade": self.trade.to_dict(),
            "bars": bars,
            "trades_today": self.trades_today,
            "daily_pnl": self.daily_pnl,
            "bar_count": self.bar_count,
        }

    # ==================== Entry ====================

    def _enter_trade(self, zone: IFVGZone, go_long: bool, price: float) -> list[Signal]:
        p = self.params
        signals: list[Signal] = []
        num_contracts = min(p["contracts"], p["max_contracts"])
        stop_buffer = p["stop_buffer_ticks"] * self._tick_size

        if go_long:
            stop = zone.bottom - stop_buffer
            tp1 = price + p["tp1_points"]
        else:
            stop = zone.top + stop_buffer
            tp1 = price - p["tp1_points"]

        # Clamp stop distance
        dist = abs(price - stop)
        if dist < p["stop_min_pts"]:
            stop = (price - p["stop_min_pts"]) if go_long else (price + p["stop_min_pts"])
        if dist > p["stop_max_pts"]:
            stop = (price - p["stop_max_pts"]) if go_long else (price + p["stop_max_pts"])

        action = Action.BUY if go_long else Action.SELL
        direction = 1 if go_long else -1
        signals.append(Signal(
            action=action, qty=num_contracts,
            reason=f"{'Long' if go_long else 'Short'} IFVG retest: zone=[{zone.bottom:.2f}-{zone.top:.2f}]",
        ))

        self.trade = TradeState(
            entry_price=price, stop_price=stop, tp1_price=tp1,
            risk_points=abs(price - stop), initial_qty=num_contracts,
            direction=direction,
        )
        self.is_long_trade = go_long
        self.best_price = price
        self.trailing_active = False
        self.trail_stop = math.nan
        self.trades_today += 1

        log.info(
            "%s IFVG: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f",
            "LONG" if go_long else "SHORT", num_contracts, price, stop, tp1,
        )
        return signals

    # ==================== Position Management ====================

    def _manage_position(self, high: float, low: float, close: float,
                         position_qty: int) -> list[Signal]:
        p = self.params
        trade = self.trade
        signals: list[Signal] = []
        is_long = self.is_long_trade

        # Track best price
        if is_long:
            if math.isnan(self.best_price) or high > self.best_price:
                self.best_price = high
        else:
            if math.isnan(self.best_price) or low < self.best_price:
                self.best_price = low

        # Effective stop
        effective_stop = trade.stop_price
        if not math.isnan(self.trail_stop) and self.trailing_active:
            if is_long:
                effective_stop = max(effective_stop, self.trail_stop)
            else:
                effective_stop = min(effective_stop, self.trail_stop)

        # Stop loss check
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

        # Breakeven
        if not trade.be_activated and p["be_enabled"]:
            profit = (self.best_price - trade.entry_price) if is_long else (trade.entry_price - self.best_price)
            if profit >= p["be_trigger_pts"]:
                trade.stop_price = trade.entry_price
                trade.be_activated = True

        # TP1 Partial
        if not trade.partial_taken:
            tp1_hit = (is_long and high >= trade.tp1_price) or (not is_long and low <= trade.tp1_price)
            if tp1_hit:
                partial_qty = max(1, int(math.ceil(trade.initial_qty * p["tp1_pct"] / 100.0)))
                if 0 < partial_qty < position_qty:
                    close_action = Action.SELL if is_long else Action.BUY
                    signals.append(Signal(
                        action=close_action, qty=partial_qty,
                        reason=f"TP1 partial: {partial_qty} of {position_qty}",
                    ))
                    trade.partial_taken = True
                else:
                    signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                          reason="Full exit at TP1"))
                    self._reset_trade_state()
                    return signals

        # Trail
        trail_dist = p["trail_points"]
        if trade.partial_taken and not self.trailing_active:
            self.trailing_active = True
            if is_long:
                self.trail_stop = self.best_price - trail_dist
            else:
                self.trail_stop = self.best_price + trail_dist

        if self.trailing_active:
            if is_long:
                new_trail = self.best_price - trail_dist
                if math.isnan(self.trail_stop) or new_trail > self.trail_stop:
                    self.trail_stop = new_trail
            else:
                new_trail = self.best_price + trail_dist
                if math.isnan(self.trail_stop) or new_trail < self.trail_stop:
                    self.trail_stop = new_trail

        return signals

    def _reset_trade_state(self) -> None:
        self.trade = TradeState()
        self.is_long_trade = False
        self.best_price = math.nan
        self.trail_stop = math.nan
        self.trailing_active = False

    def _prune_zones(self):
        self.zones = [z for z in self.zones if z.state in (ZoneState.ACTIVE, ZoneState.TRADED)]
