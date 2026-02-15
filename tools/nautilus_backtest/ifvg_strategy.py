"""
ICT Implied Fair Value Gap Retest Strategy — NautilusTrader port.

Ported from ICTIFVGRetestStrategy.java (MotiveWave SDK).
Detects 3-bar IFVG patterns, tracks zone states, enters on retests.
Manages positions with stop, breakeven, TP1 partial, and runner trail.
"""

import math
from dataclasses import dataclass
from enum import IntEnum

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


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


# ==================== Strategy Config ====================

class IFVGRetestConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Direction
    enable_long: bool = True
    enable_short: bool = True

    # IFVG Detection
    shadow_threshold_pct: float = 30.0  # percentage (0-100)
    max_wait_bars: int = 30

    # VIX Filter (hysteresis: stop at vix_off, resume at vix_on)
    vix_filter_enabled: bool = False
    vix_off: float = 30.0   # stop trading when VIX closes above this
    vix_on: float = 20.0    # resume trading when VIX closes below this

    # Entry
    session_enabled: bool = False
    session_start: int = 930   # HHMM ET
    session_end: int = 1600    # HHMM ET
    max_trades_day: int = 3

    # Position
    contracts: int = 2

    # Stop
    stop_buffer_ticks: int = 40
    tick_size: float = 0.25    # actual ES tick size for buffer calculation
    stop_min_pts: float = 2.0
    stop_max_pts: float = 40.0

    # Breakeven
    be_enabled: bool = True
    be_trigger_pts: float = 10.0

    # Targets
    tp1_points: float = 20.0
    tp1_pct: int = 50          # % of contracts at TP1

    # Trail
    trail_points: float = 15.0

    # EOD
    eod_enabled: bool = True
    eod_time: int = 1640       # HHMM ET


# ==================== Strategy ====================

class IFVGRetestStrategy(Strategy):

    def __init__(self, config: IFVGRetestConfig, regime_lookup: dict = None, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type
        self.threshold = config.shadow_threshold_pct / 100.0

        # Volatility regime lookup: {"YYYY-MM-DD": {"stop": mult, "target": mult}}
        self.regime_lookup = regime_lookup or {}
        self.current_stop_mult: float = 1.0
        self.current_target_mult: float = 1.0
        self.current_regime: str = "Normal"

        # VIX filter: {"YYYY-MM-DD": float}
        self.vix_lookup = vix_lookup or {}
        self.vix_blocked: bool = False  # hysteresis state

        # Zone tracking
        self.zones: list = []
        self.bar_count: int = 0

        # Trade state
        self.is_long_trade: bool = False
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp1_price: float = 0.0
        self.tp1_filled: bool = False
        self.be_activated: bool = False
        self.best_price: float = float("nan")
        self.trail_stop: float = float("nan")
        self.trailing_active: bool = False

        # Daily tracking
        self.last_reset_day: int = -1
        self.eod_processed: bool = False
        self.trades_today: int = 0

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("IFVG Retest Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("IFVG Retest Strategy stopped")

    # ==================== Core Logic ====================

    def on_bar(self, bar: Bar):
        self.bar_count += 1

        # Need at least 3 bars for IFVG detection
        bars = self.cache.bars(self.bar_type)
        if bars is None or len(bars) < 3:
            return

        # NautilusTrader cache: bars[0]=newest, bars[1]=previous, bars[2]=two ago
        bar_0 = bars[0]  # current (i)
        bar_1 = bars[1]  # previous (i-1)
        bar_2 = bars[2]  # two bars ago (i-2)

        o0 = bar_0.open.as_double()
        h0 = bar_0.high.as_double()
        l0 = bar_0.low.as_double()
        c0 = bar_0.close.as_double()

        o1 = bar_1.open.as_double()
        c1 = bar_1.close.as_double()

        o2 = bar_2.open.as_double()
        h2 = bar_2.high.as_double()
        l2 = bar_2.low.as_double()
        c2 = bar_2.close.as_double()

        # Bar time in ET
        bar_dt = pd.Timestamp(bar_0.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        cfg = self.config

        # Daily reset
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.last_reset_day = bar_day

            # Update volatility regime for this day
            date_str = bar_dt.strftime("%Y-%m-%d")
            regime = self.regime_lookup.get(date_str)
            if regime:
                self.current_stop_mult = regime["stop"]
                self.current_target_mult = regime["target"]
                self.current_regime = regime["regime"]

            # VIX hysteresis filter: check previous day's close
            if cfg.vix_filter_enabled and self.vix_lookup:
                prev_date = (bar_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                vix_close = self.vix_lookup.get(prev_date)
                if vix_close is not None:
                    if self.vix_blocked and vix_close < cfg.vix_on:
                        self.vix_blocked = False
                        self.log.info(f"VIX filter OFF: VIX={vix_close:.1f} < {cfg.vix_on}")
                    elif not self.vix_blocked and vix_close > cfg.vix_off:
                        self.vix_blocked = True
                        self.log.info(f"VIX filter ON: VIX={vix_close:.1f} > {cfg.vix_off}")

        # --- EOD Flatten ---
        if cfg.eod_enabled and bar_time_int >= cfg.eod_time and not self.eod_processed:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"EOD flatten at {bar_time_int}")
                self._reset_trade_state()
            self.eod_processed = True
            return

        # --- Trade Management (if in position) ---
        position = self._get_open_position()
        if position is not None:
            self._manage_position(position, h0, l0, c0)
            # Re-check — position may have been closed
            position = self._get_open_position()
            if position is None and self.entry_price > 0:
                self._reset_trade_state()
            return  # Don't detect/enter while in a position

        # Clean stale trade state
        if self.entry_price > 0:
            self._reset_trade_state()

        # --- IFVG Zone Detection ---
        r = h0 - l0
        b0 = abs(c0 - o0)
        b1 = abs(c1 - o1)
        b2 = abs(c2 - o2)

        # Bullish IFVG: middle bar largest body, current low < prior high
        if b1 > max(b0, b2) and l0 < h2:
            lower_shadow_0 = min(c0, o0) - l0
            upper_shadow_2 = h2 - max(c2, o2)
            bull_top = (min(c0, o0) + l0) / 2.0
            bull_btm = (max(c2, o2) + h2) / 2.0

            if (
                _safe_div(lower_shadow_0, r) > self.threshold
                and _safe_div(upper_shadow_2, r) > self.threshold
                and bull_top > bull_btm
            ):
                self.zones.append(IFVGZone(bull_top, bull_btm, True, self.bar_count))

        # Bearish IFVG: middle bar largest body, current high > prior low
        if b1 > max(b0, b2) and h0 > l2:
            upper_shadow_0 = h0 - max(c0, o0)
            lower_shadow_2 = min(c2, o2) - l2
            bear_top = (min(c2, o2) + l2) / 2.0
            bear_btm = (max(c0, o0) + h0) / 2.0

            if (
                _safe_div(upper_shadow_0, r) > self.threshold
                and _safe_div(lower_shadow_2, r) > self.threshold
                and bear_top > bear_btm
            ):
                self.zones.append(IFVGZone(bear_top, bear_btm, False, self.bar_count))

        # --- Zone State Updates ---
        for zone in self.zones:
            if zone.state != ZoneState.ACTIVE:
                continue
            if self.bar_count <= zone.bar_index:
                continue

            # Expiration
            if (self.bar_count - zone.bar_index) > cfg.max_wait_bars:
                zone.state = ZoneState.EXPIRED
                continue

            # Violation: close through zone
            if zone.is_bullish and c0 < zone.bottom:
                zone.state = ZoneState.VIOLATED
                continue
            if not zone.is_bullish and c0 > zone.top:
                zone.state = ZoneState.VIOLATED
                continue

        # --- Entry Check ---
        past_eod = cfg.eod_enabled and bar_time_int >= cfg.eod_time
        in_session = not cfg.session_enabled or (
            cfg.session_start <= bar_time_int < cfg.session_end
        )
        can_enter = (not past_eod and in_session
                     and self.trades_today < cfg.max_trades_day
                     and not self.vix_blocked)

        if not can_enter:
            self._prune_zones()
            return

        for zone in self.zones:
            if zone.state != ZoneState.ACTIVE:
                continue
            if self.bar_count <= zone.bar_index:
                continue

            # Bullish retest: price enters zone from above
            if zone.is_bullish and cfg.enable_long:
                if l0 <= zone.top and c0 > zone.bottom:
                    zone.state = ZoneState.TRADED
                    zone.traded = True
                    self._enter_trade(zone, True, c0, bar_dt)
                    self._prune_zones()
                    return

            # Bearish retest: price enters zone from below
            if not zone.is_bullish and cfg.enable_short:
                if h0 >= zone.bottom and c0 < zone.top:
                    zone.state = ZoneState.TRADED
                    zone.traded = True
                    self._enter_trade(zone, False, c0, bar_dt)
                    self._prune_zones()
                    return

        self._prune_zones()

    # ==================== Entry ====================

    def _enter_trade(self, zone: IFVGZone, go_long: bool, price: float, bar_dt):
        cfg = self.config
        qty = Quantity.from_int(cfg.contracts)
        side = OrderSide.BUY if go_long else OrderSide.SELL

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        self.is_long_trade = go_long
        self.entry_price = price

        # Apply regime multiplier to targets only (stops use base values)
        target_mult = self.current_target_mult

        stop_buffer = cfg.stop_buffer_ticks * cfg.tick_size
        tp1_pts = cfg.tp1_points * target_mult
        stop_min = cfg.stop_min_pts
        stop_max = cfg.stop_max_pts

        if go_long:
            self.stop_price = zone.bottom - stop_buffer
            self.tp1_price = price + tp1_pts
        else:
            self.stop_price = zone.top + stop_buffer
            self.tp1_price = price - tp1_pts

        # Clamp stop distance
        dist = abs(price - self.stop_price)
        if dist < stop_min:
            self.stop_price = (
                (price - stop_min) if go_long else (price + stop_min)
            )
        if dist > stop_max:
            self.stop_price = (
                (price - stop_max) if go_long else (price + stop_max)
            )

        self.best_price = price
        self.tp1_filled = False
        self.be_activated = False
        self.trailing_active = False
        self.trail_stop = float("nan")
        self.trades_today += 1

        self.log.info(
            f"{'LONG' if go_long else 'SHORT'} ENTRY: qty={cfg.contracts}, "
            f"entry={price:.2f}, stop={self.stop_price:.2f}, "
            f"TP1={self.tp1_price:.2f}, zone=[{zone.bottom:.2f}-{zone.top:.2f}], "
            f"regime={self.current_regime}(target={target_mult:.2f}x)"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float, close: float):
        cfg = self.config
        is_long = position.is_long

        # Track best price
        if is_long:
            if math.isnan(self.best_price) or high > self.best_price:
                self.best_price = high
        else:
            if math.isnan(self.best_price) or low < self.best_price:
                self.best_price = low

        # Effective stop (includes trail)
        effective_stop = self.stop_price
        if not math.isnan(self.trail_stop) and self.trailing_active:
            if is_long:
                effective_stop = max(effective_stop, self.trail_stop)
            else:
                effective_stop = min(effective_stop, self.trail_stop)

        # Stop loss check
        if is_long and low <= effective_stop:
            self.close_position(position)
            self.log.info(f"LONG stopped at {effective_stop:.2f}")
            self._reset_trade_state()
            return
        if not is_long and high >= effective_stop:
            self.close_position(position)
            self.log.info(f"SHORT stopped at {effective_stop:.2f}")
            self._reset_trade_state()
            return

        # Breakeven (BE trigger scaled by target multiplier)
        if not self.be_activated and cfg.be_enabled:
            be_trigger = cfg.be_trigger_pts * self.current_target_mult
            profit_pts = (
                (self.best_price - self.entry_price)
                if is_long
                else (self.entry_price - self.best_price)
            )
            if profit_pts >= be_trigger:
                self.stop_price = self.entry_price
                self.be_activated = True
                self.log.info(f"Stop to BE at {self.stop_price:.2f}")

        # TP1 Partial
        if not self.tp1_filled:
            tp1_hit = (is_long and high >= self.tp1_price) or (
                not is_long and low <= self.tp1_price
            )
            if tp1_hit:
                abs_qty = abs(position.quantity.as_double())
                partial_qty = math.ceil(abs_qty * cfg.tp1_pct / 100.0)
                if 0 < partial_qty < abs_qty:
                    close_side = OrderSide.SELL if is_long else OrderSide.BUY
                    order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=close_side,
                        quantity=Quantity.from_int(int(partial_qty)),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)
                    self.tp1_filled = True
                    self.log.info(
                        f"TP1: closed {int(partial_qty)} at {self.tp1_price:.2f}"
                    )
                else:
                    self.close_position(position)
                    self.log.info("Full exit at TP1")
                    self._reset_trade_state()
                    return

        # Runner trail activation (trail distance scaled by target multiplier)
        trail_dist = cfg.trail_points * self.current_target_mult
        if self.tp1_filled and not self.trailing_active:
            self.trailing_active = True
            if is_long:
                self.trail_stop = self.best_price - trail_dist
            else:
                self.trail_stop = self.best_price + trail_dist

        # Update trailing stop (ratchet only)
        if self.trailing_active:
            if is_long:
                new_trail = self.best_price - trail_dist
                if math.isnan(self.trail_stop) or new_trail > self.trail_stop:
                    self.trail_stop = new_trail
            else:
                new_trail = self.best_price + trail_dist
                if math.isnan(self.trail_stop) or new_trail < self.trail_stop:
                    self.trail_stop = new_trail

    # ==================== Helpers ====================

    def _get_open_position(self):
        positions = self.cache.positions(instrument_id=self.instrument_id)
        if positions:
            for pos in positions:
                if not pos.is_closed:
                    return pos
        return None

    def _reset_trade_state(self):
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.tp1_price = 0.0
        self.tp1_filled = False
        self.be_activated = False
        self.best_price = float("nan")
        self.trail_stop = float("nan")
        self.trailing_active = False

    def _prune_zones(self):
        """Remove expired/violated zones to limit memory."""
        self.zones = [
            z for z in self.zones if z.state in (ZoneState.ACTIVE, ZoneState.TRADED)
        ]


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0 else 0.0
