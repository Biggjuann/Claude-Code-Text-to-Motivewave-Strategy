"""JadeCap (ICT Setup Selector) live engine — dual MMBM/MMSM state machines.

Ported from jadecap_strategy.py (NautilusTrader).
Liquidity sweep → MSS → FVG → entry. PDH/PDL/PWH/PWL tracking.
Long + Short with separate counters per side.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from shared_types import Action, Signal, TradeState
from engines.base import BaseLiveEngine

log = logging.getLogger(__name__)

# State machine phases
STATE_IDLE = 0
STATE_SWEEP_DETECTED = 1
STATE_MSS_PENDING = 2
STATE_ENTRY_READY = 3
STATE_IN_TRADE = 4

# Entry models
ENTRY_IMMEDIATE = 0
ENTRY_FVG_ONLY = 1
ENTRY_BOTH = 2
ENTRY_MSS_MARKET = 3

# Exit models
EXIT_RR = 0
EXIT_TP1_TP2 = 1
EXIT_SCALE_TRAIL = 2
EXIT_TIME_MIDDAY = 3

# Stop modes
STOP_FIXED = 0
STOP_STRUCTURAL = 1

# Confirmation strictness
STRICT_AGGRESSIVE = 0
STRICT_BALANCED = 1
STRICT_CONSERVATIVE = 2

# Kill zone presets
KZ_NY_AM = 0
KZ_NY_PM = 1
KZ_LONDON_AM = 2
KZ_CUSTOM = 3

# Liquidity references
LIQ_REF_PREV_DAY = 0
LIQ_REF_SESSION = 1

DEFAULTS = {
    "setup_mode": 1,
    "enable_long": True,
    "enable_short": True,
    "trade_window_always_on": True,
    "trade_start": 1800,
    "trade_end": 1230,
    "kill_zone_preset": 3,
    "kz_custom_start": 100,
    "kz_custom_end": 1130,
    "eod_close_enabled": True,
    "eod_close_time": 1640,
    "max_trades_per_day": 1,
    "max_trades_per_side": 1,
    "one_trade_at_a_time": True,
    "allow_opposite_side": True,
    "contracts": 1,
    "max_contracts": 5,
    "mmbm_ssl_ref": 0,
    "mmsm_bsl_ref": 0,
    "liq_session_start": 2000,
    "liq_session_end": 0,
    "mmbm_pwl_enabled": False,
    "mmbm_major_swing_enabled": True,
    "mmsm_pwh_enabled": True,
    "mmsm_major_swing_high_enabled": True,
    "major_swing_lookback": 500,
    "require_deeper_liq": True,
    "sweep_min_ticks": 2,
    "require_close_back": True,
    "pivot_strength": 10,
    "entry_model": 1,
    "fvg_min_ticks": 2,
    "max_bars_to_fill": 30,
    "confirmation_strictness": 0,
    "require_mss_close": True,
    "stoploss_enabled": True,
    "stoploss_mode": 0,
    "stoploss_ticks": 40,
    "exit_model": 2,
    "rr_multiple": 3.0,
    "partial_enabled": True,
    "partial_pct": 25,
    "midday_exit_enabled": False,
    "midday_exit_time": 1215,
    "ema_filter_enabled": False,
    "ema_period": 50,
    "max_daily_loss": 500.0,
    "tick_size": 0.25,
}


def _time_to_minutes(t) -> int:
    """Convert HHMM int or 'HH:MM' string to minutes since midnight."""
    if isinstance(t, str) and ":" in t:
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    t = int(t)
    return (t // 100) * 60 + (t % 100)


class JadeCapLiveEngine(BaseLiveEngine):
    """ICT Setup Selector (JadeCap) — dual MMBM/MMSM."""

    def __init__(self, params: dict):
        self.params = {**DEFAULTS, **params}
        self._tick = self.params["tick_size"]

        # Bar history
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.max_hist = max(600, self.params["major_swing_lookback"] + 50)

        # EMA
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Daily levels
        self.pdh: float = math.nan
        self.pdl: float = math.nan
        self.today_high: float = math.nan
        self.today_low: float = math.nan
        self.last_reset_day: int = -1

        # Weekly levels
        self.pwh: float = math.nan
        self.pwl: float = math.nan
        self.this_week_high: float = math.nan
        self.this_week_low: float = math.nan
        self.last_reset_week: int = -1

        # Major swing
        self.major_swing_high: float = math.nan
        self.major_swing_low: float = math.nan

        # Session liquidity
        self.session_high: float = math.nan
        self.session_low: float = math.nan
        self.in_liq_session: bool = False

        # MMBM state
        self.mmbm_state: int = STATE_IDLE
        self.mmbm_ssl_level: float = math.nan
        self.mmbm_sweep_low: float = math.nan
        self.mmbm_mss_level: float = math.nan
        self.mmbm_sweep_strength: int = 0
        self.mmbm_fvg_detected: bool = False
        self.mmbm_entry_bar: int = -1

        # MMSM state
        self.mmsm_state: int = STATE_IDLE
        self.mmsm_bsl_level: float = math.nan
        self.mmsm_sweep_high: float = math.nan
        self.mmsm_mss_level: float = math.nan
        self.mmsm_sweep_strength: int = 0
        self.mmsm_fvg_detected: bool = False
        self.mmsm_entry_bar: int = -1

        # Trade state
        self.trade = TradeState()
        self.current_direction: int = 0

        # Daily tracking
        self.bar_count: int = 0
        self.trades_today: int = 0
        self.long_trades_today: int = 0
        self.short_trades_today: int = 0
        self.daily_pnl: float = 0.0
        self.eod_processed: bool = False

    @property
    def strategy_name(self) -> str:
        return "JadeCap"

    def on_bar(self, bar_time: datetime, o: float, h: float, l: float,
               c: float, position_qty: int = 0) -> list[Signal]:
        self.bar_count += 1
        p = self.params
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

        if self.bar_count < 20:
            return signals

        # Time
        bar_minutes = bar_time.hour * 60 + bar_time.minute
        bar_time_int = bar_time.hour * 100 + bar_time.minute
        bar_day = bar_time.timetuple().tm_yday + bar_time.year * 1000

        # Week tracking (simple: use isocalendar week)
        iso = bar_time.isocalendar()
        bar_week = iso[1] + bar_time.year * 100

        # Weekly reset
        if bar_week != self.last_reset_week:
            if not math.isnan(self.this_week_high) and not math.isnan(self.this_week_low):
                self.pwh = self.this_week_high
                self.pwl = self.this_week_low
            self.this_week_high = math.nan
            self.this_week_low = math.nan
            self.last_reset_week = bar_week

        # Daily reset
        if bar_day != self.last_reset_day:
            if not math.isnan(self.today_high) and not math.isnan(self.today_low):
                self.pdh = self.today_high
                self.pdl = self.today_low
            self.today_high = math.nan
            self.today_low = math.nan
            self.session_high = math.nan
            self.session_low = math.nan
            self._reset_daily_state()
            self.last_reset_day = bar_day

        # Track today/week H/L
        if math.isnan(self.today_high) or h > self.today_high:
            self.today_high = h
        if math.isnan(self.today_low) or l < self.today_low:
            self.today_low = l
        if math.isnan(self.this_week_high) or h > self.this_week_high:
            self.this_week_high = h
        if math.isnan(self.this_week_low) or l < self.this_week_low:
            self.this_week_low = l

        # Liquidity session
        self._update_liq_session(bar_time_int, h, l)

        if math.isnan(self.pdh) or math.isnan(self.pdl):
            return signals

        # Major swings
        n = len(self.hist_lows)
        htf_strength = 5
        if p["mmbm_major_swing_enabled"] and n > p["major_swing_lookback"]:
            self.major_swing_low = self._find_major_swing_low(htf_strength, p["major_swing_lookback"])
        if p["mmsm_major_swing_high_enabled"] and n > p["major_swing_lookback"]:
            self.major_swing_high = self._find_major_swing_high(htf_strength, p["major_swing_lookback"])

        self.mmbm_ssl_level = self._resolve_ssl_level()
        self.mmsm_bsl_level = self._resolve_bsl_level()

        # EOD flatten
        eod_time = p["eod_close_time"]
        if p["eod_close_enabled"] and bar_time_int >= eod_time and not self.eod_processed:
            if position_qty != 0 or self.trade.is_active:
                signals.append(Signal(
                    action=Action.FLATTEN, qty=abs(position_qty),
                    reason=f"EOD flatten at {bar_time_int}",
                ))
                self._reset_trade_state()
            self._reset_mmbm_state()
            self._reset_mmsm_state()
            self.eod_processed = True
            return signals

        # Trade management
        if position_qty != 0 and self.trade.is_active:
            mgmt = self._manage_position(h, l, c, abs(position_qty))
            signals.extend(mgmt)
            return signals

        if self.trade.is_active and position_qty == 0:
            self._reset_trade_state()

        # Past EOD — no new entries
        if p["eod_close_enabled"] and bar_time_int >= eod_time:
            return signals

        # Session/KZ checks
        if p["trade_window_always_on"]:
            in_trade_session = True
        elif p["trade_start"] > p["trade_end"]:
            in_trade_session = bar_time_int >= p["trade_start"] or bar_time_int < p["trade_end"]
        else:
            in_trade_session = p["trade_start"] <= bar_time_int < p["trade_end"]

        in_kill_zone = p["trade_window_always_on"] or self._is_in_kill_zone(bar_time_int)
        base_can_trade = in_trade_session and in_kill_zone and self.trades_today < p["max_trades_per_day"]

        can_trade_long = base_can_trade and self.long_trades_today < p["max_trades_per_side"] and p["enable_long"]
        can_trade_short = base_can_trade and self.short_trades_today < p["max_trades_per_side"] and p["enable_short"]

        if p["one_trade_at_a_time"] and self.current_direction != 0:
            if not p["allow_opposite_side"]:
                can_trade_long = False
                can_trade_short = False
            else:
                if self.current_direction > 0:
                    can_trade_long = False
                if self.current_direction < 0:
                    can_trade_short = False

        if p["ema_filter_enabled"] and not math.isnan(self.ema_value):
            if c <= self.ema_value:
                can_trade_long = False
            if c >= self.ema_value:
                can_trade_short = False

        eval_mmbm = (p["setup_mode"] == 1) or p["enable_long"]
        eval_mmsm = (p["setup_mode"] == 1) or p["enable_short"]

        entered_long = False
        if eval_mmbm:
            entry = self._process_mmbm(h, l, c, o, can_trade_long)
            if entry:
                entry_sigs = self._do_enter_long(c)
                signals.extend(entry_sigs)
                entered_long = True

        if eval_mmsm:
            if entered_long:
                can_trade_short = (self.trades_today < p["max_trades_per_day"]
                                   and self.short_trades_today < p["max_trades_per_side"]
                                   and p["enable_short"])
                if p["one_trade_at_a_time"] and not p["allow_opposite_side"]:
                    can_trade_short = False
            entry = self._process_mmsm(h, l, c, o, can_trade_short)
            if entry:
                entry_sigs = self._do_enter_short(c)
                signals.extend(entry_sigs)

        # Max bars cancellation
        if self.mmbm_state == STATE_ENTRY_READY and self.mmbm_entry_bar > 0:
            if self.bar_count - self.mmbm_entry_bar > p["max_bars_to_fill"]:
                self._reset_mmbm_state()
        if self.mmsm_state == STATE_ENTRY_READY and self.mmsm_entry_bar > 0:
            if self.bar_count - self.mmsm_entry_bar > p["max_bars_to_fill"]:
                self._reset_mmsm_state()

        return signals

    def check_eod_flatten(self, bar_time: datetime) -> bool:
        bar_time_int = bar_time.hour * 100 + bar_time.minute
        return bar_time_int >= self.params["eod_close_time"]

    def restore_state(self, trade_state: TradeState, bars: list[dict]) -> None:
        self.trade = trade_state
        for bar in bars:
            self.hist_opens.append(bar.get("open", bar.get("close", 0)))
            self.hist_closes.append(bar["close"])
            self.hist_highs.append(bar["high"])
            self.hist_lows.append(bar["low"])
            self._update_ema(bar["close"])
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

    # ==================== MMBM Processing ====================

    def _process_mmbm(self, h, l, c, o, can_trade) -> bool:
        p = self.params
        tick = self._tick

        if self.mmbm_state == STATE_IDLE and can_trade and not math.isnan(self.mmbm_ssl_level):
            sweep_threshold = self.mmbm_ssl_level - (p["sweep_min_ticks"] * tick)
            if l <= sweep_threshold:
                valid_sweep = not p["require_close_back"] or (c > self.mmbm_ssl_level)
                if p["confirmation_strictness"] == STRICT_AGGRESSIVE:
                    valid_sweep = True
                if valid_sweep:
                    self.mmbm_sweep_strength = 1
                    if p["mmbm_pwl_enabled"] and not math.isnan(self.pwl):
                        if l <= self.pwl - (p["sweep_min_ticks"] * tick):
                            self.mmbm_sweep_strength = 2
                    if p["mmbm_major_swing_enabled"] and not math.isnan(self.major_swing_low):
                        if l <= self.major_swing_low - (p["sweep_min_ticks"] * tick):
                            self.mmbm_sweep_strength = 3
                    if p["require_deeper_liq"] and self.mmbm_sweep_strength == 1:
                        return False
                    self.mmbm_sweep_low = l
                    self.mmbm_state = STATE_SWEEP_DETECTED
                    self.mmbm_mss_level = self._find_swing_high(p["pivot_strength"])

        if self.mmbm_state == STATE_SWEEP_DETECTED and l < self.mmbm_sweep_low:
            self.mmbm_sweep_low = l

        if self.mmbm_state == STATE_SWEEP_DETECTED and not math.isnan(self.mmbm_mss_level):
            mss_break = (c > self.mmbm_mss_level) if p["require_mss_close"] else (h > self.mmbm_mss_level)
            if mss_break:
                disp_ticks = self._get_displacement_ticks()
                body_size = abs(c - o)
                if body_size >= disp_ticks * tick or p["confirmation_strictness"] == STRICT_AGGRESSIVE:
                    self.mmbm_state = STATE_MSS_PENDING
                    if p["entry_model"] in (ENTRY_IMMEDIATE, ENTRY_MSS_MARKET):
                        self.mmbm_state = STATE_ENTRY_READY
                        self.mmbm_entry_bar = self.bar_count

        n = len(self.hist_highs)
        if (self.mmbm_state in (STATE_MSS_PENDING, STATE_SWEEP_DETECTED)
                and n >= 3 and p["entry_model"] in (ENTRY_FVG_ONLY, ENTRY_BOTH)):
            bar0_high = self.hist_highs[-3]
            bar2_low = l
            if bar2_low > bar0_high and (bar2_low - bar0_high) >= p["fvg_min_ticks"] * tick:
                self.mmbm_fvg_detected = True
                self.mmbm_state = STATE_ENTRY_READY
                self.mmbm_entry_bar = self.bar_count

        if self.mmbm_state == STATE_ENTRY_READY and can_trade:
            return True
        return False

    # ==================== MMSM Processing ====================

    def _process_mmsm(self, h, l, c, o, can_trade) -> bool:
        p = self.params
        tick = self._tick

        if self.mmsm_state == STATE_IDLE and can_trade and not math.isnan(self.mmsm_bsl_level):
            sweep_threshold = self.mmsm_bsl_level + (p["sweep_min_ticks"] * tick)
            if h >= sweep_threshold:
                valid_sweep = not p["require_close_back"] or (c < self.mmsm_bsl_level)
                if p["confirmation_strictness"] == STRICT_AGGRESSIVE:
                    valid_sweep = True
                if valid_sweep:
                    self.mmsm_sweep_strength = 1
                    if p["mmsm_pwh_enabled"] and not math.isnan(self.pwh):
                        if h >= self.pwh + (p["sweep_min_ticks"] * tick):
                            self.mmsm_sweep_strength = 2
                    if p["mmsm_major_swing_high_enabled"] and not math.isnan(self.major_swing_high):
                        if h >= self.major_swing_high + (p["sweep_min_ticks"] * tick):
                            self.mmsm_sweep_strength = 3
                    if p["require_deeper_liq"] and self.mmsm_sweep_strength == 1:
                        return False
                    self.mmsm_sweep_high = h
                    self.mmsm_state = STATE_SWEEP_DETECTED
                    self.mmsm_mss_level = self._find_swing_low(p["pivot_strength"])

        if self.mmsm_state == STATE_SWEEP_DETECTED and h > self.mmsm_sweep_high:
            self.mmsm_sweep_high = h

        if self.mmsm_state == STATE_SWEEP_DETECTED and not math.isnan(self.mmsm_mss_level):
            mss_break = (c < self.mmsm_mss_level) if p["require_mss_close"] else (l < self.mmsm_mss_level)
            if mss_break:
                disp_ticks = self._get_displacement_ticks()
                body_size = abs(c - o)
                if body_size >= disp_ticks * tick or p["confirmation_strictness"] == STRICT_AGGRESSIVE:
                    self.mmsm_state = STATE_MSS_PENDING
                    if p["entry_model"] in (ENTRY_IMMEDIATE, ENTRY_MSS_MARKET):
                        self.mmsm_state = STATE_ENTRY_READY
                        self.mmsm_entry_bar = self.bar_count

        n = len(self.hist_lows)
        if (self.mmsm_state in (STATE_MSS_PENDING, STATE_SWEEP_DETECTED)
                and n >= 3 and p["entry_model"] in (ENTRY_FVG_ONLY, ENTRY_BOTH)):
            bar0_low = self.hist_lows[-3]
            bar2_high = h
            if bar2_high < bar0_low and (bar0_low - bar2_high) >= p["fvg_min_ticks"] * tick:
                self.mmsm_fvg_detected = True
                self.mmsm_state = STATE_ENTRY_READY
                self.mmsm_entry_bar = self.bar_count

        if self.mmsm_state == STATE_ENTRY_READY and can_trade:
            return True
        return False

    # ==================== Entry ====================

    def _do_enter_long(self, close) -> list[Signal]:
        p = self.params
        tick = self._tick
        signals: list[Signal] = []
        num_contracts = min(p["contracts"], p["max_contracts"])

        signals.append(Signal(action=Action.BUY, qty=num_contracts,
                              reason=f"MMBM long entry (strength={self.mmbm_sweep_strength})"))

        stop = 0.0
        if p["stoploss_enabled"]:
            stop_buffer = p["stoploss_ticks"] * tick
            if p["stoploss_mode"] == STOP_STRUCTURAL and not math.isnan(self.mmbm_sweep_low):
                stop = self.mmbm_sweep_low - stop_buffer
            else:
                stop = close - stop_buffer

        risk = abs(close - stop) if stop > 0 else p["stoploss_ticks"] * tick
        equilibrium = (self.pdh + self.pdl) / 2.0
        tp1 = equilibrium
        if p["exit_model"] == EXIT_RR:
            tp2 = close + (risk * p["rr_multiple"])
        else:
            tp2 = self.pdh

        self.trade = TradeState(
            entry_price=close, stop_price=stop, tp1_price=tp1, tp2_price=tp2,
            risk_points=risk, initial_qty=num_contracts, direction=1,
        )
        self.current_direction = 1
        self.trades_today += 1
        self.long_trades_today += 1
        self.mmbm_state = STATE_IN_TRADE

        log.info("LONG JADECAP: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
                 num_contracts, close, stop, tp1, tp2)
        return signals

    def _do_enter_short(self, close) -> list[Signal]:
        p = self.params
        tick = self._tick
        signals: list[Signal] = []
        num_contracts = min(p["contracts"], p["max_contracts"])

        signals.append(Signal(action=Action.SELL, qty=num_contracts,
                              reason=f"MMSM short entry (strength={self.mmsm_sweep_strength})"))

        stop = 0.0
        if p["stoploss_enabled"]:
            stop_buffer = p["stoploss_ticks"] * tick
            if p["stoploss_mode"] == STOP_STRUCTURAL and not math.isnan(self.mmsm_sweep_high):
                stop = self.mmsm_sweep_high + stop_buffer
            else:
                stop = close + stop_buffer

        risk = abs(stop - close) if stop > 0 else p["stoploss_ticks"] * tick
        equilibrium = (self.pdh + self.pdl) / 2.0
        tp1 = equilibrium
        if p["exit_model"] == EXIT_RR:
            tp2 = close - (risk * p["rr_multiple"])
        else:
            tp2 = self.pdl

        self.trade = TradeState(
            entry_price=close, stop_price=stop, tp1_price=tp1, tp2_price=tp2,
            risk_points=risk, initial_qty=num_contracts, direction=-1,
        )
        self.current_direction = -1
        self.trades_today += 1
        self.short_trades_today += 1
        self.mmsm_state = STATE_IN_TRADE

        log.info("SHORT JADECAP: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
                 num_contracts, close, stop, tp1, tp2)
        return signals

    # ==================== Position Management ====================

    def _manage_position(self, high, low, close, position_qty) -> list[Signal]:
        p = self.params
        trade = self.trade
        signals: list[Signal] = []

        if trade.direction > 0:  # Long
            if p["stoploss_enabled"] and trade.stop_price > 0 and low <= trade.stop_price:
                signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                      reason=f"Long stop at {trade.stop_price:.2f}"))
                self._reset_trade_state()
                return signals
            if p["partial_enabled"] and not trade.partial_taken and high >= trade.tp1_price:
                partial_qty = max(1, int(math.ceil(position_qty * p["partial_pct"] / 100.0)))
                if partial_qty > 0 and partial_qty < position_qty:
                    signals.append(Signal(action=Action.SELL, qty=partial_qty,
                                          reason=f"Partial at TP1={trade.tp1_price:.2f}"))
                    if p["exit_model"] == EXIT_SCALE_TRAIL:
                        trade.stop_price = trade.entry_price
                trade.partial_taken = True
            if high >= trade.tp2_price and trade.tp2_price > 0:
                signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                      reason=f"Long TP2 at {trade.tp2_price:.2f}"))
                self._reset_trade_state()
                return signals

        elif trade.direction < 0:  # Short
            if p["stoploss_enabled"] and trade.stop_price > 0 and high >= trade.stop_price:
                signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                      reason=f"Short stop at {trade.stop_price:.2f}"))
                self._reset_trade_state()
                return signals
            if p["partial_enabled"] and not trade.partial_taken and low <= trade.tp1_price:
                partial_qty = max(1, int(math.ceil(position_qty * p["partial_pct"] / 100.0)))
                if partial_qty > 0 and partial_qty < position_qty:
                    signals.append(Signal(action=Action.BUY, qty=partial_qty,
                                          reason=f"Partial at TP1={trade.tp1_price:.2f}"))
                    if p["exit_model"] == EXIT_SCALE_TRAIL:
                        trade.stop_price = trade.entry_price
                trade.partial_taken = True
            if low <= trade.tp2_price and trade.tp2_price > 0:
                signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                      reason=f"Short TP2 at {trade.tp2_price:.2f}"))
                self._reset_trade_state()
                return signals

        return signals

    # ==================== Helpers ====================

    def _update_ema(self, close: float):
        period = self.params["ema_period"]
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

    def _get_displacement_ticks(self) -> int:
        s = self.params["confirmation_strictness"]
        if s == STRICT_AGGRESSIVE:
            return 4
        elif s == STRICT_BALANCED:
            return 8
        return 12

    def _resolve_ssl_level(self) -> float:
        if self.params["mmbm_ssl_ref"] == LIQ_REF_SESSION:
            return self.session_low if not math.isnan(self.session_low) else self.pdl
        return self.pdl

    def _resolve_bsl_level(self) -> float:
        if self.params["mmsm_bsl_ref"] == LIQ_REF_SESSION:
            return self.session_high if not math.isnan(self.session_high) else self.pdh
        return self.pdh

    def _update_liq_session(self, time_int, high, low):
        start = self.params["liq_session_start"]
        end = self.params["liq_session_end"]
        if start > end:
            in_session = time_int >= start or time_int < end
        else:
            in_session = start <= time_int < end
        if in_session:
            if math.isnan(self.session_high) or high > self.session_high:
                self.session_high = high
            if math.isnan(self.session_low) or low < self.session_low:
                self.session_low = low
            self.in_liq_session = True
        elif self.in_liq_session:
            self.in_liq_session = False

    def _find_swing_high(self, strength) -> float:
        highs = self.hist_highs
        n = len(highs)
        for i in range(n - strength - 2, strength - 1, -1):
            high = highs[i]
            is_swing = True
            for j in range(1, strength + 1):
                if i - j >= 0 and highs[i - j] >= high:
                    is_swing = False
                    break
                if i + j < n and highs[i + j] >= high:
                    is_swing = False
                    break
            if is_swing:
                return high
        return math.nan

    def _find_swing_low(self, strength) -> float:
        lows = self.hist_lows
        n = len(lows)
        for i in range(n - strength - 2, strength - 1, -1):
            low = lows[i]
            is_swing = True
            for j in range(1, strength + 1):
                if i - j >= 0 and lows[i - j] <= low:
                    is_swing = False
                    break
                if i + j < n and lows[i + j] <= low:
                    is_swing = False
                    break
            if is_swing:
                return low
        return math.nan

    def _find_major_swing_low(self, htf_strength, lookback) -> float:
        lows = self.hist_lows
        n = len(lows)
        lowest = math.nan
        start_idx = max(htf_strength, n - lookback)
        for i in range(start_idx, n - htf_strength):
            low = lows[i]
            is_swing = True
            for j in range(1, htf_strength + 1):
                if i - j >= 0 and lows[i - j] <= low:
                    is_swing = False
                    break
                if i + j < n and lows[i + j] <= low:
                    is_swing = False
                    break
            if is_swing and (math.isnan(lowest) or low < lowest):
                lowest = low
        return lowest

    def _find_major_swing_high(self, htf_strength, lookback) -> float:
        highs = self.hist_highs
        n = len(highs)
        highest = math.nan
        start_idx = max(htf_strength, n - lookback)
        for i in range(start_idx, n - htf_strength):
            high = highs[i]
            is_swing = True
            for j in range(1, htf_strength + 1):
                if i - j >= 0 and highs[i - j] >= high:
                    is_swing = False
                    break
                if i + j < n and highs[i + j] >= high:
                    is_swing = False
                    break
            if is_swing and (math.isnan(highest) or high > highest):
                highest = high
        return highest

    def _is_in_kill_zone(self, time_int) -> bool:
        kz = self.params["kill_zone_preset"]
        if kz == KZ_NY_AM:
            return 830 <= time_int < 1100
        elif kz == KZ_NY_PM:
            return 1330 <= time_int < 1600
        elif kz == KZ_LONDON_AM:
            return 300 <= time_int < 500
        elif kz == KZ_CUSTOM:
            return self.params["kz_custom_start"] <= time_int < self.params["kz_custom_end"]
        return True

    def _reset_daily_state(self):
        self._reset_mmbm_state()
        self._reset_mmsm_state()
        self.trades_today = 0
        self.long_trades_today = 0
        self.short_trades_today = 0
        self.eod_processed = False
        self._reset_trade_state()

    def _reset_mmbm_state(self):
        self.mmbm_state = STATE_IDLE
        self.mmbm_sweep_low = math.nan
        self.mmbm_mss_level = math.nan
        self.mmbm_sweep_strength = 0
        self.mmbm_fvg_detected = False
        self.mmbm_entry_bar = -1

    def _reset_mmsm_state(self):
        self.mmsm_state = STATE_IDLE
        self.mmsm_sweep_high = math.nan
        self.mmsm_mss_level = math.nan
        self.mmsm_sweep_strength = 0
        self.mmsm_fvg_detected = False
        self.mmsm_entry_bar = -1

    def _reset_trade_state(self):
        self.trade = TradeState()
        self.current_direction = 0
