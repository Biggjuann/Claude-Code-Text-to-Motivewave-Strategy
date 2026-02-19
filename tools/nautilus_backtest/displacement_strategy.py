"""
Displacement Candle Strategy — NautilusTrader port.

Core idea: A "displacement" candle has a range (high-low) that is significantly
larger than recent candles, signaling strong momentum. Enter in the direction
of the displacement candle, with stop at the candle's extreme.

Entry: Current bar range >= lookback_avg_range × displacement_mult
  - Bullish displacement (close > open) → LONG, stop = displacement candle low
  - Bearish displacement (close < open) → SHORT, stop = displacement candle high
Target: R:R based or EOD exit.
"""

import math

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


# ==================== Config ====================

class DisplacementConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Displacement detection
    lookback: int = 10           # bars to average for "normal" range
    displacement_mult: float = 2.0  # current range must be >= avg * mult

    # Risk management
    target_rr: float = 3.0       # TP as R-multiple (0 = EOD only)
    trail_after_rr: float = 0.0  # start trailing after this R-multiple (0 = no trail)
    trail_points: float = 0.0    # trail distance in points (0 = no trail)

    # Session
    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0


# ==================== Strategy ====================

class DisplacementStrategy(Strategy):

    def __init__(self, config: DisplacementConfig):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # Rolling range buffer
        self.ranges: list[float] = []

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp_price: float = 0.0
        self.trade_side: int = 0  # 1=long, -1=short
        self.trail_active: bool = False
        self.best_price: float = 0.0

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("Displacement Candle Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)

    # ==================== Core Logic ====================

    def on_bar(self, bar: Bar):
        self.bar_count += 1
        cfg = self.config

        o = bar.open.as_double()
        h = bar.high.as_double()
        l = bar.low.as_double()
        c = bar.close.as_double()
        bar_range = h - l

        # Bar time in ET
        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.last_reset_day = bar_day

        # ===== Update rolling range buffer =====
        # Only use RTH bars for range calculation
        if 935 <= bar_time_int <= 1600:
            self.ranges.append(bar_range)
            if len(self.ranges) > cfg.lookback + 10:
                self.ranges = self.ranges[-(cfg.lookback + 10):]

        # ===== EOD flatten =====
        if bar_time_int >= cfg.eod_time and not self.eod_processed:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"EOD flatten at {bar_time_int}")
                self._reset_trade_state()
            self.eod_processed = True
            return

        # ===== Trade management =====
        position = self._get_open_position()
        if position is not None:
            self._manage_position(position, h, l, c)
            if self._get_open_position() is None and self.entry_price > 0:
                self._reset_trade_state()
            return

        if self.entry_price > 0:
            self._reset_trade_state()

        # ===== Entry conditions =====
        if len(self.ranges) < cfg.lookback + 1:
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        # Compute average range of previous N bars (excluding current)
        prev_ranges = self.ranges[-(cfg.lookback + 1):-1]
        avg_range = sum(prev_ranges) / len(prev_ranges)

        if avg_range <= 0:
            return

        # Check displacement: current range >= avg * mult
        ratio = bar_range / avg_range
        if ratio < cfg.displacement_mult:
            return

        # Determine direction
        is_bullish = c > o
        is_bearish = c < o

        if not is_bullish and not is_bearish:
            return  # doji, skip

        if is_bullish:
            # LONG: stop at displacement candle low
            stop = l
            risk = c - stop
            if risk <= 0:
                return
            tp = c + cfg.target_rr * risk if cfg.target_rr > 0 else 0.0
            self._enter_trade(c, OrderSide.BUY, 1, stop, tp, ratio, avg_range)
        else:
            # SHORT: stop at displacement candle high
            stop = h
            risk = stop - c
            if risk <= 0:
                return
            tp = c - cfg.target_rr * risk if cfg.target_rr > 0 else 0.0
            self._enter_trade(c, OrderSide.SELL, -1, stop, tp, ratio, avg_range)

    # ==================== Entry ====================

    def _enter_trade(self, close: float, side: OrderSide, direction: int,
                     stop: float, tp: float, ratio: float, avg_range: float):
        num_contracts = self._compute_contracts()
        qty = Quantity.from_int(num_contracts)

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        self.entry_price = close
        self.stop_price = stop
        self.tp_price = tp
        self.trade_side = direction
        self.trail_active = False
        self.best_price = close
        self.trades_today += 1

        label = "LONG" if direction == 1 else "SHORT"
        risk = abs(close - stop)
        self.log.info(
            f"{label}: entry={close:.2f}, stop={stop:.2f}, TP={tp:.2f}, "
            f"risk={risk:.2f}, ratio={ratio:.2f}x (avg_range={avg_range:.2f})"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        cfg = self.config

        # Update best price
        if self.trade_side == 1:
            self.best_price = max(self.best_price, high)
        else:
            self.best_price = min(self.best_price, low)

        # Check trailing stop activation
        if cfg.trail_after_rr > 0 and cfg.trail_points > 0 and not self.trail_active:
            risk = abs(self.entry_price - self.stop_price)
            if risk > 0:
                unrealized_r = 0
                if self.trade_side == 1:
                    unrealized_r = (self.best_price - self.entry_price) / risk
                else:
                    unrealized_r = (self.entry_price - self.best_price) / risk
                if unrealized_r >= cfg.trail_after_rr:
                    self.trail_active = True
                    self.log.info(f"Trail activated at {unrealized_r:.1f}R")

        # Compute effective stop (trail or initial)
        effective_stop = self.stop_price
        if self.trail_active and cfg.trail_points > 0:
            if self.trade_side == 1:
                trail_stop = self.best_price - cfg.trail_points
                effective_stop = max(effective_stop, trail_stop)
            else:
                trail_stop = self.best_price + cfg.trail_points
                effective_stop = min(effective_stop, trail_stop)

        if self.trade_side == 1:  # long
            if low <= effective_stop:
                self.close_position(position)
                label = "TRAIL STOP" if self.trail_active else "STOP"
                self.log.info(f"{label} hit at {effective_stop:.2f}")
                self._reset_trade_state()
                return
            if self.tp_price > 0 and high >= self.tp_price:
                self.close_position(position)
                self.log.info(f"TP hit at {self.tp_price:.2f}")
                self._reset_trade_state()
                return
        else:  # short
            if high >= effective_stop:
                self.close_position(position)
                label = "TRAIL STOP" if self.trail_active else "STOP"
                self.log.info(f"{label} hit at {effective_stop:.2f}")
                self._reset_trade_state()
                return
            if self.tp_price > 0 and low <= self.tp_price:
                self.close_position(position)
                self.log.info(f"TP hit at {self.tp_price:.2f}")
                self._reset_trade_state()
                return

    # ==================== Helpers ====================

    def _compute_contracts(self) -> int:
        cfg = self.config
        if cfg.dollars_per_contract <= 0:
            return cfg.contracts
        account = self.portfolio.account(self.instrument_id.venue)
        if account is None:
            return cfg.contracts
        equity = float(account.balance_total().as_double())
        return max(1, int(equity // cfg.dollars_per_contract))

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
        self.tp_price = 0.0
        self.trade_side = 0
        self.trail_active = False
        self.best_price = 0.0
