"""
Gap Fade Strategy — NautilusTrader.

At RTH open, if price gaps away from prior close by more than threshold,
fade the gap expecting mean reversion toward prior close.
Stop beyond the opening price, target = gap fill (prior close).
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


class GapFadeConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    gap_threshold_pts: float = 5.0
    stop_mult: float = 1.0      # stop = gap_size * stop_mult beyond open
    use_rr_target: bool = False  # if True, use target_rr instead of gap fill
    target_rr: float = 2.0

    entry_start: int = 935
    entry_end: int = 945       # only enter in first 10 min
    max_trades_per_day: int = 1
    eod_time: int = 1640

    contracts: int = 10
    dollars_per_contract: float = 0.0


class GapFadeStrategy(Strategy):

    def __init__(self, config: GapFadeConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        self.prior_close: float = 0.0
        self.rth_close: float = 0.0
        self.rth_started: bool = False

        self.today_open: float = 0.0
        self.gap_checked: bool = False

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

        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert("America/New_York")
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        # Track RTH close for prior_close
        if 935 <= bar_time_int <= 1600:
            self.rth_close = c
            self.rth_started = True

        if bar_day != self.last_reset_day:
            if self.rth_started and self.rth_close > 0:
                self.prior_close = self.rth_close
            self.trades_today = 0
            self.eod_processed = False
            self.gap_checked = False
            self.today_open = 0.0
            self.rth_started = False
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

        # Gap detection at first RTH bar
        if bar_time_int == 935 and not self.gap_checked and self.prior_close > 0:
            self.today_open = o
            self.gap_checked = True

        if not self.gap_checked or self.prior_close <= 0:
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        gap = self.today_open - self.prior_close

        # Gap up → SHORT (fade)
        if gap >= cfg.gap_threshold_pts:
            stop = self.today_open + gap * cfg.stop_mult
            if cfg.use_rr_target:
                risk = stop - c
                tp = c - cfg.target_rr * risk if risk > 0 else self.prior_close
            else:
                tp = self.prior_close
            risk = stop - c
            if risk > 0:
                self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

        # Gap down → LONG (fade)
        elif gap <= -cfg.gap_threshold_pts:
            stop = self.today_open - abs(gap) * cfg.stop_mult
            if cfg.use_rr_target:
                risk = c - stop
                tp = c + cfg.target_rr * risk if risk > 0 else self.prior_close
            else:
                tp = self.prior_close
            risk = c - stop
            if risk > 0:
                self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

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
