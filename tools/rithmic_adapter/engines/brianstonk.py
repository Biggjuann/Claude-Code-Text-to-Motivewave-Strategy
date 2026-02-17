"""BrianStonk Modular ICT live engine — multi-entry ICT.

Ported from brianstonk_strategy.py (NautilusTrader).
Entry models: Breaker (BR1), IFVG (IF1), Order Block (OB1).
3-bar confirmation window, zone-based stops, BE, fixed-R targets.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from shared_types import Action, Signal, TradeState
from engines.base import BaseLiveEngine
from ict_modules.zones import Zone, ZoneType, LiquidityTarget, BIAS_BULLISH, BIAS_BEARISH, BIAS_NEUTRAL
from ict_modules.zone_detectors import (
    detect_order_blocks,
    check_ob_to_breaker,
    detect_structure_breakers,
    detect_fvgs,
    detect_inversions,
    detect_bprs,
    invalidate_zones,
    update_swing_points,
)
from ict_modules.liquidity import update_draw_targets, update_bias

log = logging.getLogger(__name__)

DEFAULTS = {
    "enable_long": True,
    "enable_short": True,
    "enable_breaker": True,
    "enable_ifvg": True,
    "enable_ob": True,
    "enable_unicorn": False,
    "trade_start": "09:30",
    "trade_end": "15:30",
    "max_trades_day": 6,
    "cooldown_minutes": 5,
    "eod_flatten_time": "15:55",
    "require_intraday_align": False,
    "htf_filter_mode": 1,
    "intraday_ma_period": 21,
    "pivot_left": 2,
    "pivot_right": 2,
    "require_draw_target": True,
    "use_session_liquidity": True,
    "use_swing_liquidity": True,
    "ob_min_candles": 2,
    "ob_mean_threshold": True,
    "breaker_require_sweep": True,
    "breaker_require_displacement": True,
    "tight_breaker_threshold": 10.0,
    "fvg_min_gap": 2.0,
    "fvg_ce_respect": True,
    "stop_default": 20.0,
    "stop_min": 18.0,
    "stop_max": 25.0,
    "stop_override_to_structure": True,
    "be_enabled": True,
    "be_trigger_pts": 10.0,
    "contracts": 1,
    "max_contracts": 5,
    "target_r": 1.0,
    "partial_enabled": False,
    "runner_enabled": True,
    "max_daily_loss": 500.0,
    "tick_size": 0.25,
}


def _time_to_minutes(t: str) -> int:
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


class BrianStonkLiveEngine(BaseLiveEngine):
    """BrianStonk Modular ICT multi-entry engine."""

    def __init__(self, params: dict):
        self.params = {**DEFAULTS, **params}
        self._eod_flatten_min = _time_to_minutes(self.params["eod_flatten_time"])
        self._trade_start_min = _time_to_minutes(self.params["trade_start"])
        self._trade_end_min = _time_to_minutes(self.params["trade_end"])

        # Zone tracking
        self.ob_zones: list[Zone] = []
        self.breaker_zones: list[Zone] = []
        self.fvg_zones: list[Zone] = []
        self.ifvg_zones: list[Zone] = []
        self.bpr_zones: list[Zone] = []

        # Swing tracking
        self.last_swing_high: float = math.nan
        self.last_swing_low: float = math.nan
        self.last_swing_high_bar: int = -1
        self.last_swing_low_bar: int = -1
        self.prev_swing_high: float = math.nan
        self.prev_swing_low: float = math.nan

        # Session tracking
        self.session_high: float = math.nan
        self.session_low: float = math.nan

        # Bias
        self.intraday_bias: int = BIAS_NEUTRAL
        self.ltf_permission: bool = False
        self.draw_targets: list[LiquidityTarget] = []
        self.primary_draw_target: LiquidityTarget | None = None

        # EMA
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Trade state
        self.trade = TradeState()
        self.is_long_trade: bool = False
        self.entry_model: str = ""

        # Pending confirmation
        self.pending_zone: Zone | None = None
        self.pending_model: str | None = None
        self.confirmation_wait_bar: int = -1

        # Bar history
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.max_hist = 60

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.daily_pnl: float = 0.0
        self.eod_processed: bool = False
        self.last_trade_bar: int = -1

    @property
    def strategy_name(self) -> str:
        return "BrianStonk"

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

        if self.bar_count < 10:
            self._update_ema(c)
            return signals

        bar_minutes = bar_time.hour * 60 + bar_time.minute
        bar_day = bar_time.timetuple().tm_yday + bar_time.year * 1000

        # Daily reset
        if bar_day != self.last_reset_day:
            self._reset_daily_state()
            self.last_reset_day = bar_day

        # Session H/L
        if self._trade_start_min <= bar_minutes <= self._trade_end_min:
            if math.isnan(self.session_high) or h > self.session_high:
                self.session_high = h
            if math.isnan(self.session_low) or l < self.session_low:
                self.session_low = l

        # Update swings
        swing_result = update_swing_points(
            self.hist_highs, self.hist_lows, self.bar_count,
            p["pivot_left"], p["pivot_right"],
            self.last_swing_high, self.last_swing_low,
            self.last_swing_high_bar, self.last_swing_low_bar,
            self.prev_swing_high, self.prev_swing_low,
        )
        if swing_result is not None:
            (self.last_swing_high, self.last_swing_low,
             self.last_swing_high_bar, self.last_swing_low_bar,
             self.prev_swing_high, self.prev_swing_low) = swing_result

        self._update_ema(c)

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

        # Zone detection
        new_obs = detect_order_blocks(
            self.hist_opens, self.hist_closes, self.hist_highs, self.hist_lows,
            self.bar_count, p["ob_min_candles"],
        )
        self.ob_zones.extend(new_obs)
        if len(self.ob_zones) > 15:
            self.ob_zones = self.ob_zones[-15:]

        new_breakers = check_ob_to_breaker(self.ob_zones, c, self.bar_count)
        self.breaker_zones.extend(new_breakers)

        struct_breakers = detect_structure_breakers(
            self.hist_closes, self.hist_highs, self.hist_lows, self.bar_count,
            self.last_swing_high, self.last_swing_low,
            self.last_swing_high_bar, self.last_swing_low_bar,
            p["breaker_require_displacement"],
        )
        self.breaker_zones.extend(struct_breakers)
        if len(self.breaker_zones) > 15:
            self.breaker_zones = self.breaker_zones[-15:]

        new_fvgs = detect_fvgs(self.hist_highs, self.hist_lows, self.bar_count, p["fvg_min_gap"])
        self.fvg_zones.extend(new_fvgs)
        if len(self.fvg_zones) > 20:
            self.fvg_zones = self.fvg_zones[-20:]

        new_ifvgs = detect_inversions(self.fvg_zones, c, self.bar_count)
        self.ifvg_zones.extend(new_ifvgs)
        if len(self.ifvg_zones) > 15:
            self.ifvg_zones = self.ifvg_zones[-15:]

        new_bprs = detect_bprs(self.ifvg_zones, self.fvg_zones, self.bar_count)
        for bpr in new_bprs:
            exists = any(abs(z.top - bpr.top) < 1 and abs(z.bottom - bpr.bottom) < 1
                         for z in self.bpr_zones)
            if not exists:
                self.bpr_zones.append(bpr)
        if len(self.bpr_zones) > 10:
            self.bpr_zones = self.bpr_zones[-10:]

        all_zone_lists = [self.ob_zones, self.breaker_zones, self.fvg_zones,
                          self.ifvg_zones, self.bpr_zones]
        invalidate_zones(all_zone_lists, c, self.bar_count)

        # Bias
        self.intraday_bias = update_bias(
            c, self.ema_value,
            self.last_swing_high, self.last_swing_low,
            self.prev_swing_high, self.prev_swing_low,
        )
        self.ltf_permission = (self.intraday_bias != BIAS_NEUTRAL)

        self.draw_targets, self.primary_draw_target = update_draw_targets(
            c, self.intraday_bias,
            self.session_high, self.session_low,
            self.last_swing_high, self.last_swing_low,
            p["use_session_liquidity"], p["use_swing_liquidity"],
        )

        # Entry conditions
        in_trade_window = self._trade_start_min <= bar_minutes < self._trade_end_min
        past_flat_time = bar_minutes >= self._eod_flatten_min
        cooldown_ok = (self.bar_count - self.last_trade_bar) >= p["cooldown_minutes"]
        under_limit = self.trades_today < p["max_trades_day"]
        has_draw = self.primary_draw_target is not None or not p["require_draw_target"]
        has_align = self.ltf_permission or not p["require_intraday_align"]
        can_trade = (in_trade_window and not past_flat_time and cooldown_ok
                     and under_limit and has_draw and has_align)

        if can_trade:
            entry_sigs = self._process_entry_models(c, o)
            signals.extend(entry_sigs)

        # Pending confirmation
        if self.pending_zone is not None and position_qty == 0:
            confirm_sigs = self._handle_pending_confirmation(c, o)
            signals.extend(confirm_sigs)

        return signals

    def check_eod_flatten(self, bar_time: datetime) -> bool:
        return bar_time.hour * 60 + bar_time.minute >= self._eod_flatten_min

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

    # ==================== Entry Models ====================

    def _process_entry_models(self, close: float, open_: float) -> list[Signal]:
        p = self.params
        bias = self.intraday_bias

        # BR1: Breaker Retap
        if p["enable_breaker"] and self.pending_zone is None:
            for breaker in self.breaker_zones:
                if not breaker.is_valid:
                    continue
                if close >= breaker.bottom and close <= breaker.top:
                    if breaker.is_bullish and p["enable_long"] and bias >= BIAS_NEUTRAL:
                        self._set_pending_entry(breaker, "BR1")
                        break
                    elif not breaker.is_bullish and p["enable_short"] and bias <= BIAS_NEUTRAL:
                        self._set_pending_entry(breaker, "BR1")
                        break

        # IF1: IFVG/BPR Flip
        if p["enable_ifvg"] and self.pending_zone is None:
            for ifvg in self.ifvg_zones:
                if not ifvg.is_valid:
                    continue
                if close >= ifvg.bottom and close <= ifvg.top:
                    if ifvg.is_bullish and p["enable_long"] and bias >= BIAS_NEUTRAL:
                        self._set_pending_entry(ifvg, "IF1")
                        break
                    elif not ifvg.is_bullish and p["enable_short"] and bias <= BIAS_NEUTRAL:
                        self._set_pending_entry(ifvg, "IF1")
                        break

        # OB1: Order Block Mean Threshold
        if p["enable_ob"] and self.pending_zone is None:
            for ob in self.ob_zones:
                if not ob.is_valid or ob.violated:
                    continue
                if close >= ob.bottom and close <= ob.top:
                    mean_ok = True
                    if p["ob_mean_threshold"]:
                        if ob.is_bullish and close < ob.mid:
                            mean_ok = False
                        if not ob.is_bullish and close > ob.mid:
                            mean_ok = False
                    if mean_ok:
                        if ob.is_bullish and p["enable_long"] and bias >= BIAS_NEUTRAL:
                            self._set_pending_entry(ob, "OB1")
                            break
                        elif not ob.is_bullish and p["enable_short"] and bias <= BIAS_NEUTRAL:
                            self._set_pending_entry(ob, "OB1")
                            break

        return []  # entries come through _handle_pending_confirmation

    def _set_pending_entry(self, zone: Zone, model: str):
        self.pending_zone = zone
        self.pending_model = model
        self.confirmation_wait_bar = self.bar_count

    def _handle_pending_confirmation(self, close: float, open_: float) -> list[Signal]:
        if self.pending_zone is None:
            return []

        if self.bar_count - self.confirmation_wait_bar > 3:
            self.pending_zone = None
            self.pending_model = None
            self.confirmation_wait_bar = -1
            return []

        zone = self.pending_zone
        if zone.is_bullish:
            if close > open_ and close > zone.mid:
                return self._trigger_entry(zone, True, self.pending_model, close)
        else:
            if close < open_ and close < zone.mid:
                return self._trigger_entry(zone, False, self.pending_model, close)

        return []

    def _trigger_entry(self, zone: Zone, is_long: bool, model: str, price: float) -> list[Signal]:
        p = self.params
        signals: list[Signal] = []
        num_contracts = min(p["contracts"], p["max_contracts"])

        action = Action.BUY if is_long else Action.SELL
        direction = 1 if is_long else -1

        signals.append(Signal(
            action=action, qty=num_contracts,
            reason=f"{'Long' if is_long else 'Short'} {model}: zone=[{zone.bottom:.2f}-{zone.top:.2f}]",
        ))

        # Stop calculation
        if is_long:
            zone_stop = zone.bottom - 2
            if zone.height < p["tight_breaker_threshold"] and p["stop_override_to_structure"]:
                zone_stop = (self.last_swing_low - 2) if not math.isnan(self.last_swing_low) else (price - p["stop_max"])
            risk_points = price - zone_stop
        else:
            zone_stop = zone.top + 2
            if zone.height < p["tight_breaker_threshold"] and p["stop_override_to_structure"]:
                zone_stop = (self.last_swing_high + 2) if not math.isnan(self.last_swing_high) else (price + p["stop_max"])
            risk_points = zone_stop - price

        risk_points = max(p["stop_min"], min(risk_points, p["stop_max"]))

        if is_long:
            stop = price - risk_points
            target = price + risk_points * p["target_r"]
        else:
            stop = price + risk_points
            target = price - risk_points * p["target_r"]

        self.trade = TradeState(
            entry_price=price, stop_price=stop, tp1_price=target,
            risk_points=risk_points, initial_qty=num_contracts,
            direction=direction,
        )
        self.is_long_trade = is_long
        self.entry_model = model
        self.trades_today += 1
        self.last_trade_bar = self.bar_count

        zone.is_valid = False
        self.pending_zone = None
        self.pending_model = None
        self.confirmation_wait_bar = -1

        log.info(
            "%s %s: qty=%d, entry=%.2f, stop=%.2f, target=%.2f, risk=%.1f",
            "LONG" if is_long else "SHORT", model, num_contracts,
            price, stop, target, risk_points,
        )
        return signals

    # ==================== Position Management ====================

    def _manage_position(self, high: float, low: float, close: float,
                         position_qty: int) -> list[Signal]:
        p = self.params
        trade = self.trade
        signals: list[Signal] = []
        is_long = trade.direction > 0

        # Stop loss
        if is_long and low <= trade.stop_price:
            signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                  reason=f"Long stopped at {trade.stop_price:.2f}"))
            self._reset_trade_state()
            return signals
        if not is_long and high >= trade.stop_price:
            signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                  reason=f"Short stopped at {trade.stop_price:.2f}"))
            self._reset_trade_state()
            return signals

        # Breakeven
        if p["be_enabled"] and not trade.be_activated and trade.risk_points > 0:
            unrealized = (close - trade.entry_price) if is_long else (trade.entry_price - close)
            if unrealized >= p["be_trigger_pts"]:
                if is_long and trade.entry_price > trade.stop_price:
                    trade.stop_price = trade.entry_price
                elif not is_long and trade.entry_price < trade.stop_price:
                    trade.stop_price = trade.entry_price
                trade.be_activated = True

        # Target hit
        if is_long and high >= trade.tp1_price:
            signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                  reason=f"Long target at {trade.tp1_price:.2f}"))
            self._reset_trade_state()
            return signals
        if not is_long and low <= trade.tp1_price:
            signals.append(Signal(action=Action.FLATTEN, qty=position_qty,
                                  reason=f"Short target at {trade.tp1_price:.2f}"))
            self._reset_trade_state()
            return signals

        return signals

    # ==================== Helpers ====================

    def _update_ema(self, close: float):
        period = self.params["intraday_ma_period"]
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

    def _reset_trade_state(self):
        self.trade = TradeState()
        self.is_long_trade = False
        self.entry_model = ""

    def _reset_daily_state(self):
        self.ob_zones.clear()
        self.breaker_zones.clear()
        self.fvg_zones.clear()
        self.ifvg_zones.clear()
        self.bpr_zones.clear()
        self.draw_targets.clear()
        self.primary_draw_target = None
        self.trades_today = 0
        self.eod_processed = False
        self.pending_zone = None
        self.pending_model = None
        self.confirmation_wait_bar = -1
        self.session_high = math.nan
        self.session_low = math.nan
        self.ema_value = math.nan
        self.ema_count = 0
