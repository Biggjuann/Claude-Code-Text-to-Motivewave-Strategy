"""LB Short live engine — short-only LB breakdown with EMA filter.

Ported from lb_short_strategy.py (NautilusTrader).
Short when price crosses from green to red (close breaks below LB).
Bar-1 confirmation, fixed stop, TP1 partial, trailing stop.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from shared_types import Action, Signal, TradeState
from engines.base import BaseLiveEngine

log = logging.getLogger(__name__)

DEFAULTS = {
    "length": 20,
    "trade_start": "09:30",
    "trade_end": "16:00",
    "eod_flatten_time": "16:40",
    "max_trades_per_day": 1,
    "contracts": 1,
    "max_contracts": 5,
    "stop_buffer_ticks": 20,
    "be_enabled": True,
    "be_trigger_pts": 10.0,
    "tp1_pts": 15.0,
    "partial_pct": 25,
    "trail_pts": 5.0,
    "ema_filter_enabled": True,
    "ema_period": 50,
    "max_daily_loss": 500.0,
    "tick_size": 0.25,
}


def _time_to_minutes(t: str) -> int:
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


class LBShortLiveEngine(BaseLiveEngine):
    """Short-only LB breakdown strategy."""

    def __init__(self, params: dict):
        self.params = {**DEFAULTS, **params}
        self._tick_size = self.params["tick_size"]
        self._length = self.params["length"]
        self._trade_start_min = _time_to_minutes(self.params["trade_start"])
        self._trade_end_min = _time_to_minutes(self.params["trade_end"])
        self._eod_flatten_min = _time_to_minutes(self.params["eod_flatten_time"])

        # Bar history
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.max_hist = 200

        # LB values
        self.lb_values: list[float] = []

        # EMA state
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Trade state
        self.trade = TradeState(direction=-1)
        self.entry_bar_high: float = 0.0
        self.bars_since_entry: int = 0
        self.trail_stop: float = 0.0

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.daily_pnl: float = 0.0
        self.eod_processed: bool = False

    @property
    def strategy_name(self) -> str:
        return "LB Short"

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

        self._update_ema(c)

        min_bars = 2 * self._length
        if len(self.hist_lows) < min_bars:
            return signals

        lb = self._compute_lb()
        if math.isnan(lb):
            return signals
        self.lb_values.append(lb)
        if len(self.lb_values) > 100:
            self.lb_values.pop(0)

        bar_minutes = bar_time.hour * 60 + bar_time.minute
        bar_day = bar_time.timetuple().tm_yday + bar_time.year * 1000

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
                    action=Action.FLATTEN,
                    qty=abs(position_qty),
                    reason=f"EOD flatten at {bar_time.strftime('%H:%M')}",
                ))
                self._reset_trade_state()
            self.eod_processed = True
            return signals

        # Max daily loss
        if self.daily_pnl <= -self.params["max_daily_loss"]:
            if position_qty != 0 or self.trade.is_active:
                signals.append(Signal(
                    action=Action.FLATTEN,
                    qty=abs(position_qty),
                    reason=f"Max daily loss hit",
                ))
                self._reset_trade_state()
            return signals

        # Position management (short: position_qty < 0)
        if position_qty < 0 and self.trade.is_active:
            mgmt = self._manage_position(h, l, c, lb, abs(position_qty))
            signals.extend(mgmt)
            return signals

        # Stale state cleanup
        if self.trade.is_active and position_qty == 0:
            log.warning("Trade state active but position flat — resetting")
            self._reset_trade_state()

        # Entry conditions
        if not (self._trade_start_min <= bar_minutes < self._trade_end_min):
            return signals
        if self.trades_today >= self.params["max_trades_per_day"]:
            return signals
        if self.params["ema_filter_enabled"] and not math.isnan(self.ema_value):
            if c >= self.ema_value:
                return signals

        if len(self.lb_values) < 2:
            return signals

        prev_lb = self.lb_values[-2]
        is_red = c < lb
        prev_close = self.hist_closes[-2]
        prev_was_green = prev_close >= prev_lb

        if is_red and prev_was_green:
            entry_signals = self._enter_short(c, h, lb)
            signals.extend(entry_signals)

        return signals

    def check_eod_flatten(self, bar_time: datetime) -> bool:
        bar_minutes = bar_time.hour * 60 + bar_time.minute
        return bar_minutes >= self._eod_flatten_min

    def restore_state(self, trade_state: TradeState, bars: list[dict]) -> None:
        self.trade = trade_state
        for bar in bars:
            self.hist_opens.append(bar["open"])
            self.hist_closes.append(bar["close"])
            self.hist_highs.append(bar["high"])
            self.hist_lows.append(bar["low"])
            self._update_ema(bar["close"])
        if len(self.hist_lows) >= 2 * self._length:
            lb = self._compute_lb()
            if not math.isnan(lb):
                self.lb_values.append(lb)
        log.info("State restored: trade=%s, bars=%d", trade_state.is_active, len(bars))

    def get_state_snapshot(self) -> dict:
        n = min(len(self.hist_opens), self.max_hist)
        bars = []
        for i in range(len(self.hist_opens) - n, len(self.hist_opens)):
            bars.append({
                "open": self.hist_opens[i],
                "close": self.hist_closes[i],
                "high": self.hist_highs[i],
                "low": self.hist_lows[i],
            })
        return {
            "trade": self.trade.to_dict(),
            "bars": bars,
            "trades_today": self.trades_today,
            "daily_pnl": self.daily_pnl,
            "ema_value": self.ema_value if not math.isnan(self.ema_value) else None,
            "ema_count": self.ema_count,
            "bar_count": self.bar_count,
        }

    # ==================== LB Calculation ====================

    def _compute_lb(self) -> float:
        length = self._length
        lows = self.hist_lows
        n = len(lows)
        if n < 2 * length:
            return math.nan
        lower_bands = []
        for i in range(n - length, n):
            start = i - length + 1
            if start < 0:
                return math.nan
            lower_bands.append(min(lows[start:i + 1]))
        return max(lower_bands)

    def _update_ema(self, close: float) -> None:
        period = self.params["ema_period"]
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

    # ==================== Enter Short ====================

    def _enter_short(self, close: float, high: float, lb: float) -> list[Signal]:
        p = self.params
        signals: list[Signal] = []
        tick = self._tick_size

        num_contracts = min(p["contracts"], p["max_contracts"])
        stop = high + p["stop_buffer_ticks"] * tick
        tp1 = close - p["tp1_pts"]

        signals.append(Signal(
            action=Action.SELL,
            qty=num_contracts,
            reason=f"Short entry: LB={lb:.2f}",
        ))

        self.trade = TradeState(
            entry_price=close,
            stop_price=stop,
            tp1_price=tp1,
            risk_points=abs(stop - close),
            initial_qty=num_contracts,
            direction=-1,
        )
        self.entry_bar_high = high
        self.bars_since_entry = 0
        self.trail_stop = 0.0
        self.trades_today += 1

        log.info(
            "SHORT: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, LB=%.2f",
            num_contracts, close, stop, tp1, lb,
        )
        return signals

    # ==================== Position Management ====================

    def _manage_position(self, high: float, low: float, close: float,
                         lb: float, position_qty: int) -> list[Signal]:
        p = self.params
        trade = self.trade
        signals: list[Signal] = []
        tick = self._tick_size

        self.bars_since_entry += 1

        # 1. Bar-1 check: GREEN bar after entry → exit
        if self.bars_since_entry == 1:
            if close >= lb:
                signals.append(Signal(
                    action=Action.FLATTEN,
                    qty=position_qty,
                    reason=f"Green bar exit (bar 1): close {close:.2f} >= LB {lb:.2f}",
                ))
                self._reset_trade_state()
                return signals
            else:
                trade.stop_price = self.entry_bar_high + p["stop_buffer_ticks"] * tick

        # 2. Breakeven trigger
        if p["be_enabled"] and not trade.be_activated and not trade.partial_taken:
            if low <= trade.entry_price - p["be_trigger_pts"]:
                trade.be_activated = True
                trade.stop_price = trade.entry_price
                log.info("BE triggered: stop moved to entry %.2f", trade.entry_price)

        # 3. Stop check (high breaches stop)
        if trade.stop_price > 0 and high >= trade.stop_price:
            stop_type = "BE" if trade.be_activated else "INITIAL"
            signals.append(Signal(
                action=Action.FLATTEN,
                qty=position_qty,
                reason=f"{stop_type} stop hit at {trade.stop_price:.2f}",
            ))
            self._reset_trade_state()
            return signals

        # 4. TP1 partial
        if not trade.partial_taken and low <= trade.tp1_price:
            if p["partial_pct"] > 0 and trade.initial_qty > 1:
                partial_qty = max(1, int(trade.initial_qty * p["partial_pct"] / 100))
                if partial_qty < position_qty:
                    signals.append(Signal(
                        action=Action.BUY,
                        qty=partial_qty,
                        reason=f"TP1 partial: cover {partial_qty} of {position_qty}",
                    ))
            trade.partial_taken = True
            trade.trail_active = True
            self.trail_stop = close + p["trail_pts"]

        # 5. Trail update
        if trade.trail_active:
            candidate = close + p["trail_pts"]
            if candidate < self.trail_stop:
                self.trail_stop = candidate
            if high >= self.trail_stop:
                signals.append(Signal(
                    action=Action.FLATTEN,
                    qty=position_qty,
                    reason=f"Trail stop hit at {self.trail_stop:.2f}",
                ))
                self._reset_trade_state()
                return signals

        return signals

    def _reset_trade_state(self) -> None:
        self.trade = TradeState(direction=-1)
        self.entry_bar_high = 0.0
        self.bars_since_entry = 0
        self.trail_stop = 0.0
