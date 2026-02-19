"""
Engulfing Reversal Strategy — NautilusTrader.

Detect bullish/bearish engulfing patterns (two-bar reversal).
Bullish: bar[i-1] red, bar[i] green, bar[i] body engulfs bar[i-1] body.
Bearish: bar[i-1] green, bar[i] red, bar[i] body engulfs bar[i-1] body.
Stop at pattern extreme, R:R target.
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


class EngulfingConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    min_body_pct: float = 50.0    # engulfing bar min body %
    target_rr: float = 2.0

    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    contracts: int = 10
    dollars_per_contract: float = 0.0


class EngulfingStrategy(Strategy):

    def __init__(self, config: EngulfingConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        self.prev_open: float = 0.0
        self.prev_close: float = 0.0
        self.prev_high: float = 0.0
        self.prev_low: float = 0.0
        self.has_prev: bool = False

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
            self.last_reset_day = bar_day

        # EOD flatten
        if bar_time_int >= cfg.eod_time and not self.eod_processed:
            pos = self._get_open_position()
            if pos is not None:
                self.close_position(pos)
                self._reset_trade_state()
            self.eod_processed = True
            self._update_prev(o, h, l, c, bar_time_int)
            return

        # Trade management
        pos = self._get_open_position()
        if pos is not None:
            self._manage_position(pos, h, l, c)
            if self._get_open_position() is None and self.entry_price > 0:
                self._reset_trade_state()
            self._update_prev(o, h, l, c, bar_time_int)
            return

        if self.entry_price > 0:
            self._reset_trade_state()

        # Entry conditions
        if not self.has_prev:
            self._update_prev(o, h, l, c, bar_time_int)
            return
        if self.trades_today >= cfg.max_trades_per_day:
            self._update_prev(o, h, l, c, bar_time_int)
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            self._update_prev(o, h, l, c, bar_time_int)
            return

        # Body quality
        body = abs(c - o)
        body_pct = (body / bar_range * 100) if bar_range > 0 else 0

        prev_bullish = self.prev_close > self.prev_open
        prev_bearish = self.prev_close < self.prev_open
        curr_bullish = c > o
        curr_bearish = c < o

        # Bullish engulfing: prev bearish, curr bullish, curr body engulfs prev body
        if (prev_bearish and curr_bullish and body_pct >= cfg.min_body_pct
                and c > self.prev_open and o < self.prev_close):
            pattern_low = min(l, self.prev_low)
            stop = pattern_low
            risk = c - stop
            if risk > 0:
                tp = c + cfg.target_rr * risk
                self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

        # Bearish engulfing: prev bullish, curr bearish, curr body engulfs prev body
        elif (prev_bullish and curr_bearish and body_pct >= cfg.min_body_pct
              and c < self.prev_open and o > self.prev_close):
            pattern_high = max(h, self.prev_high)
            stop = pattern_high
            risk = stop - c
            if risk > 0:
                tp = c - cfg.target_rr * risk
                self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

        self._update_prev(o, h, l, c, bar_time_int)

    def _update_prev(self, o, h, l, c, bar_time_int):
        if 935 <= bar_time_int <= 1600:
            self.prev_open = o
            self.prev_high = h
            self.prev_low = l
            self.prev_close = c
            self.has_prev = True

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
