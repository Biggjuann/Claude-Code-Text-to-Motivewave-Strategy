"""
Opening Drive Strategy — NautilusTrader.

If the first RTH bar (9:35) has a strong directional body (body > threshold %
of range) AND range exceeds average, enter in that direction.
Stop at opposite end of the candle, R:R target.
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


class OpeningDriveConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    body_pct_threshold: float = 60.0  # min body as % of range
    range_mult: float = 1.0           # min range vs avg (1.0 = at least average)
    range_lookback: int = 20
    target_rr: float = 2.0

    max_trades_per_day: int = 1
    eod_time: int = 1640

    contracts: int = 10
    dollars_per_contract: float = 0.0


class OpeningDriveStrategy(Strategy):

    def __init__(self, config: OpeningDriveConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        self.ranges: list[float] = []
        self.drive_checked: bool = False

        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp_price: float = 0.0
        self.trade_side: int = 0

        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    def on_stop(self):
        self.close_all_positions(self.instrument_id)

    def on_bar(self, bar: Bar):
        self.bar_count += 1
        cfg = self.config

        o = bar.open.as_double()
        h = bar.high.as_double()
        l = bar.low.as_double()
        c = bar.close.as_double()
        bar_range = h - l

        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert("America/New_York")
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.drive_checked = False
            self.last_reset_day = bar_day

        # Accumulate RTH ranges
        if 935 <= bar_time_int <= 1600:
            self.ranges.append(bar_range)
            if len(self.ranges) > cfg.range_lookback + 10:
                self.ranges = self.ranges[-(cfg.range_lookback + 10):]

        # EOD flatten
        if bar_time_int >= cfg.eod_time and not self.eod_processed:
            pos = self._get_open_position()
            if pos is not None:
                self.close_position(pos)
                self._reset_trade_state()
            self.eod_processed = True
            return

        # Trade management
        pos = self._get_open_position()
        if pos is not None:
            self._manage_position(pos, h, l, c)
            if self._get_open_position() is None and self.entry_price > 0:
                self._reset_trade_state()
            return

        if self.entry_price > 0:
            self._reset_trade_state()

        # Only check the 9:35 bar
        if bar_time_int != 935 or self.drive_checked:
            return
        self.drive_checked = True

        if self.trades_today >= cfg.max_trades_per_day:
            return
        if len(self.ranges) < cfg.range_lookback + 1:
            return

        # Compute avg range (excluding current)
        prev_ranges = self.ranges[-(cfg.range_lookback + 1):-1]
        avg_range = sum(prev_ranges) / len(prev_ranges)
        if avg_range <= 0:
            return

        # Check range is strong enough
        if bar_range < avg_range * cfg.range_mult:
            return

        # Check body quality
        body = abs(c - o)
        body_pct = (body / bar_range * 100) if bar_range > 0 else 0
        if body_pct < cfg.body_pct_threshold:
            return

        # Direction
        if c > o:  # bullish drive
            stop = l
            risk = c - stop
            if risk > 0:
                tp = c + cfg.target_rr * risk
                self._enter_trade(c, OrderSide.BUY, 1, stop, tp)
        elif c < o:  # bearish drive
            stop = h
            risk = stop - c
            if risk > 0:
                tp = c - cfg.target_rr * risk
                self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

    def _enter_trade(self, close, side, direction, stop, tp):
        qty = Quantity.from_int(self._compute_contracts())
        order = self.order_factory.market(
            instrument_id=self.instrument_id, order_side=side,
            quantity=qty, time_in_force=TimeInForce.GTC)
        self.submit_order(order)
        self.entry_price = close
        self.stop_price = stop
        self.tp_price = tp
        self.trade_side = direction
        self.trades_today += 1

    def _manage_position(self, position, high, low, close):
        if self.trade_side == 1:
            if low <= self.stop_price:
                self.close_position(position)
                self._reset_trade_state()
                return
            if self.tp_price > 0 and high >= self.tp_price:
                self.close_position(position)
                self._reset_trade_state()
                return
        else:
            if high >= self.stop_price:
                self.close_position(position)
                self._reset_trade_state()
                return
            if self.tp_price > 0 and low <= self.tp_price:
                self.close_position(position)
                self._reset_trade_state()
                return

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
