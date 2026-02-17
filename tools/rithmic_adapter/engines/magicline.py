"""MagicLine live engine — long-only regressive S/R (LB line).

Ported from magicline_strategy.py (NautilusTrader) which was ported from
MagicLineStrategy.java v4.0 (MotiveWave SDK).

LB = highest(lowest(low, length), length).
EMA filter, 5-condition entry, BE/partial/trail/TP2 exit hierarchy.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from shared_types import Action, Signal, TradeState
from engines.base import BaseLiveEngine

log = logging.getLogger(__name__)

# Default parameters
DEFAULTS = {
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
    "contracts": 1,
    "max_contracts": 5,
    "eod_flatten_time": "15:45",
    "max_daily_loss": 500.0,
    "tick_size": 0.25,
}


def _p(params: dict, key: str):
    """Get param with default fallback."""
    return params.get(key, DEFAULTS[key])


def _time_to_minutes(t: str) -> int:
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


class MagicLineLiveEngine(BaseLiveEngine):
    """Pure-Python MagicLine signal generator."""

    def __init__(self, params: dict):
        self.params = {**DEFAULTS, **params}

        # Pre-compute derived values
        self._tick_size = self.params["tick_size"]
        self._length = self.params["length"]
        self._stop_buffer_pts = self.params["stop_buffer_ticks"] * self._tick_size
        self._touch_tolerance_pts = self.params["touch_tolerance_ticks"] * self._tick_size
        self._trade_start_min = _time_to_minutes(self.params["trade_start"])
        self._trade_end_min = _time_to_minutes(self.params["trade_end"])
        self._eod_flatten_min = _time_to_minutes(self.params["eod_flatten_time"])

        # Bar history (rolling window)
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
        self.trade = TradeState(direction=1)  # long-only

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.daily_pnl: float = 0.0
        self.eod_processed: bool = False

    @property
    def strategy_name(self) -> str:
        return "MagicLine"

    # ==================== Public Interface ====================

    def on_bar(self, bar_time: datetime, o: float, h: float, l: float,
               c: float, position_qty: int = 0) -> list[Signal]:
        self.bar_count += 1
        signals: list[Signal] = []

        # Maintain rolling history
        self.hist_opens.append(o)
        self.hist_closes.append(c)
        self.hist_highs.append(h)
        self.hist_lows.append(l)
        if len(self.hist_opens) > self.max_hist:
            self.hist_opens.pop(0)
            self.hist_closes.pop(0)
            self.hist_highs.pop(0)
            self.hist_lows.pop(0)

        # Update EMA
        self._update_ema(c)

        # Warmup
        min_bars = 2 * self._length
        if len(self.hist_lows) < min_bars:
            log.debug("Warmup: %d/%d bars", len(self.hist_lows), min_bars)
            return signals

        # Compute LB
        lb = self._compute_lb()
        if math.isnan(lb):
            return signals
        self.lb_values.append(lb)
        if len(self.lb_values) > 100:
            self.lb_values.pop(0)

        # Time calculations
        bar_minutes = bar_time.hour * 60 + bar_time.minute
        bar_day = bar_time.timetuple().tm_yday + bar_time.year * 1000

        # Daily reset
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.daily_pnl = 0.0
            self.eod_processed = False
            self.last_reset_day = bar_day
            log.info("New trading day: %s", bar_time.strftime("%Y-%m-%d"))

        # EOD flatten
        if bar_minutes >= self._eod_flatten_min and not self.eod_processed:
            if position_qty > 0 or self.trade.is_active:
                signals.append(Signal(
                    action=Action.FLATTEN,
                    qty=position_qty,
                    reason=f"EOD flatten at {bar_time.strftime('%H:%M')}",
                ))
                log.info("EOD flatten signal at %s", bar_time.strftime("%H:%M"))
                self._reset_trade_state()
            self.eod_processed = True
            return signals

        # Max daily loss check
        if self.daily_pnl <= -self.params["max_daily_loss"]:
            if position_qty > 0 or self.trade.is_active:
                signals.append(Signal(
                    action=Action.FLATTEN,
                    qty=position_qty,
                    reason=f"Max daily loss ${self.params['max_daily_loss']:.0f} hit",
                ))
                self._reset_trade_state()
            return signals

        # Position management
        if position_qty > 0 and self.trade.is_active:
            mgmt_signals = self._manage_position(h, l, c, lb, position_qty)
            signals.extend(mgmt_signals)
            return signals

        # Stale trade state cleanup
        if self.trade.is_active and position_qty == 0:
            log.warning("Trade state active but position flat — resetting")
            self._reset_trade_state()

        # Entry conditions
        if not self._check_entry_filters(bar_minutes, c, lb):
            return signals

        if self._check_entry(lb, c, o, l):
            entry_signals = self._enter_long(c, l, lb)
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
            window = lows[start:i + 1]
            lower_bands.append(min(window))
        return max(lower_bands)

    # ==================== EMA ====================

    def _update_ema(self, close: float) -> None:
        period = self.params["ema_period"]
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

    # ==================== Entry Filters ====================

    def _check_entry_filters(self, bar_minutes: int, close: float, lb: float) -> bool:
        if not (self._trade_start_min <= bar_minutes < self._trade_end_min):
            return False
        if self.trades_today >= self.params["max_trades_per_day"]:
            return False
        if close < lb:
            return False
        if self.params["ema_filter_enabled"] and not math.isnan(self.ema_value):
            if close < self.ema_value:
                return False
        return True

    # ==================== 5-Condition Entry ====================

    def _check_entry(self, lb: float, close: float, open_: float, low: float) -> bool:
        touch_tol = self._touch_tolerance_pts
        zone_buffer = self.params["zone_buffer_pts"]

        if not (lb - touch_tol <= low <= lb + zone_buffer):
            return False
        if close <= open_:
            return False
        if close <= lb:
            return False

        higher_low = False
        n = len(self.hist_lows)
        if n >= 3:
            prev_low = self.hist_lows[-2]
            prev_prev_low = self.hist_lows[-3]
            higher_low = (low > prev_low) or (prev_low > prev_prev_low)

        came_from_above = False
        lookback = self.params["came_from_lookback"]
        highs = self.hist_highs
        n = len(highs)
        start = max(0, n - 1 - lookback)
        for i in range(start, n - 1):
            if highs[i] > lb + self.params["came_from_pts"]:
                came_from_above = True
                break

        return higher_low or came_from_above

    # ==================== Enter Long ====================

    def _enter_long(self, close: float, low: float, lb: float) -> list[Signal]:
        p = self.params
        signals: list[Signal] = []

        if p["stoploss_mode"] == "structural":
            stop = low - self._stop_buffer_pts
        else:
            stop = close - self._stop_buffer_pts

        risk = abs(close - stop)
        if risk <= 0:
            risk = self._stop_buffer_pts

        tp1 = close + p["tp1_r"] * risk
        tp2 = close + p["tp2_r"] * risk
        num_contracts = min(p["contracts"], p["max_contracts"])

        signals.append(Signal(
            action=Action.BUY,
            qty=num_contracts,
            reason=f"Entry: LB={lb:.2f}, risk={risk:.1f}pts",
        ))

        self.trade = TradeState(
            entry_price=close,
            stop_price=stop,
            tp1_price=tp1,
            tp2_price=tp2,
            risk_points=risk,
            initial_qty=num_contracts,
            direction=1,
        )
        self.trades_today += 1

        log.info(
            "LONG: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f, risk=%.1fpts, LB=%.2f",
            num_contracts, close, stop, tp1, tp2, risk, lb,
        )
        return signals

    # ==================== Position Management ====================

    def _manage_position(self, high: float, low: float, close: float,
                         lb: float, position_qty: int) -> list[Signal]:
        p = self.params
        trade = self.trade
        signals: list[Signal] = []

        # 1. Breakeven trigger
        if p["be_enabled"] and not trade.be_activated and not trade.partial_taken:
            if high >= trade.entry_price + p["be_trigger_pts"]:
                trade.be_activated = True
                signals.append(Signal(
                    action=Action.SELL,
                    qty=0,
                    reason="BE triggered: move stop to entry",
                    price=trade.entry_price,
                ))
                log.info("BE triggered: stop moved to %.2f", trade.entry_price)

        # 2. Partial at TP1
        if not trade.partial_taken and high >= trade.tp1_price:
            if p["partial_enabled"] and trade.initial_qty > 1:
                partial_qty = max(1, int(trade.initial_qty * p["partial_pct"] / 100))
                if 0 < partial_qty < position_qty:
                    signals.append(Signal(
                        action=Action.SELL,
                        qty=partial_qty,
                        reason=f"TP1 partial: {partial_qty} of {position_qty}",
                    ))
                    log.info("TP1 partial: sell %d of %d at TP1=%.2f",
                             partial_qty, position_qty, trade.tp1_price)
            trade.partial_taken = True
            trade.be_activated = True
            trade.trail_active = True

        # 3. Stop loss check
        current_stop = (trade.entry_price
                        if (trade.partial_taken or trade.be_activated)
                        else trade.stop_price)
        if current_stop > 0 and low <= current_stop:
            stop_type = ("TRAIL" if trade.partial_taken
                         else ("BE" if trade.be_activated else "INITIAL"))
            signals.append(Signal(
                action=Action.FLATTEN,
                qty=position_qty,
                reason=f"{stop_type} stop hit at {current_stop:.2f}",
            ))
            log.info("%s stop hit at %.2f", stop_type, current_stop)
            self._reset_trade_state()
            return signals

        # 4. Trail exit: close below LB (after partial)
        if trade.trail_active and trade.partial_taken:
            if close < lb:
                signals.append(Signal(
                    action=Action.FLATTEN,
                    qty=position_qty,
                    reason=f"Trail exit: close {close:.2f} < LB {lb:.2f}",
                ))
                log.info("Trail exit: close %.2f < LB %.2f", close, lb)
                self._reset_trade_state()
                return signals

        # 5. TP2 full exit
        if trade.partial_taken and trade.tp2_price > 0 and high >= trade.tp2_price:
            signals.append(Signal(
                action=Action.FLATTEN,
                qty=position_qty,
                reason=f"TP2 hit at {trade.tp2_price:.2f}",
            ))
            log.info("TP2 hit at %.2f", trade.tp2_price)
            self._reset_trade_state()
            return signals

        return signals

    # ==================== Helpers ====================

    def _reset_trade_state(self) -> None:
        self.trade = TradeState(direction=1)
