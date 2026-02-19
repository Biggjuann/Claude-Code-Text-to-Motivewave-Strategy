"""
3-Bar Momentum Strategy — NautilusTrader.

Detect 3 consecutive bars all closing in the same direction (all bullish
or all bearish). Enter on the 3rd bar close in that direction.
Stop at the extreme of the 3-bar run, R:R target.
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


class ThreeBarConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    consecutive: int = 3
    min_body_pct: float = 50.0   # min body as % of range
    target_rr: float = 2.0

    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    contracts: int = 10
    dollars_per_contract: float = 0.0


class ThreeBarStrategy(Strategy):

    def __init__(self, config: ThreeBarConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        self.bull_count: int = 0
        self.bear_count: int = 0
        self.run_high: float = 0.0
        self.run_low: float = float('inf')

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
            self.bull_count = 0
            self.bear_count = 0
            self.run_high = 0.0
            self.run_low = float('inf')
            self.last_reset_day = bar_day

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

        # Only track during RTH
        if not (935 <= bar_time_int <= 1600):
            return

        # Body percentage check
        body = abs(c - o)
        body_pct = (body / bar_range * 100) if bar_range > 0 else 0

        is_bull = c > o and body_pct >= cfg.min_body_pct
        is_bear = c < o and body_pct >= cfg.min_body_pct

        if is_bull:
            self.bull_count += 1
            self.bear_count = 0
            self.run_high = max(self.run_high, h)
            if self.bull_count == 1:
                self.run_low = l
            else:
                self.run_low = min(self.run_low, l)
        elif is_bear:
            self.bear_count += 1
            self.bull_count = 0
            self.run_low = min(self.run_low, l)
            if self.bear_count == 1:
                self.run_high = h
            else:
                self.run_high = max(self.run_high, h)
        else:
            self.bull_count = 0
            self.bear_count = 0
            self.run_high = 0.0
            self.run_low = float('inf')

        # Entry conditions
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        # 3-bar bullish momentum → LONG
        if self.bull_count >= cfg.consecutive:
            stop = self.run_low
            risk = c - stop
            if risk > 0:
                tp = c + cfg.target_rr * risk
                self._enter_trade(c, OrderSide.BUY, 1, stop, tp)
                self.bull_count = 0

        # 3-bar bearish momentum → SHORT
        elif self.bear_count >= cfg.consecutive:
            stop = self.run_high
            risk = stop - c
            if risk > 0:
                tp = c - cfg.target_rr * risk
                self._enter_trade(c, OrderSide.SELL, -1, stop, tp)
                self.bear_count = 0

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
