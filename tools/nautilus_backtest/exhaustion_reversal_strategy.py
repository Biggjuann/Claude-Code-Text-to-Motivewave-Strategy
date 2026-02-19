"""
Exhaustion Reversal Strategy — NautilusTrader.

After N consecutive bars in the same direction, the trend is exhausted.
When the N+1 bar reverses direction, enter counter-trend.
Stop at the extreme of the run, R:R target.
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


class ExhaustionConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    consecutive_bars: int = 5     # N consecutive same-direction bars
    target_rr: float = 2.0

    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    contracts: int = 10
    dollars_per_contract: float = 0.0


class ExhaustionStrategy(Strategy):

    def __init__(self, config: ExhaustionConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        self.up_count: int = 0
        self.down_count: int = 0
        self.run_high: float = 0.0
        self.run_low: float = float('inf')
        self.exhaustion_up: bool = False    # had N up bars, waiting for reversal
        self.exhaustion_down: bool = False  # had N down bars, waiting for reversal
        self.exhaust_high: float = 0.0
        self.exhaust_low: float = float('inf')

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

        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.up_count = 0
            self.down_count = 0
            self.exhaustion_up = False
            self.exhaustion_down = False
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

        if not (935 <= bar_time_int <= 1600):
            return

        is_up = c > o
        is_down = c < o

        # Check for reversal entry BEFORE updating counts
        if self.trades_today < cfg.max_trades_per_day:
            if cfg.entry_start <= bar_time_int <= cfg.entry_end:
                # Exhaustion up (N up bars) → reversal down bar → SHORT
                if self.exhaustion_up and is_down:
                    stop = self.exhaust_high
                    risk = stop - c
                    if risk > 0:
                        tp = c - cfg.target_rr * risk
                        self._enter_trade(c, OrderSide.SELL, -1, stop, tp)
                    self.exhaustion_up = False
                    self.exhaustion_down = False

                # Exhaustion down (N down bars) → reversal up bar → LONG
                elif self.exhaustion_down and is_up:
                    stop = self.exhaust_low
                    risk = c - stop
                    if risk > 0:
                        tp = c + cfg.target_rr * risk
                        self._enter_trade(c, OrderSide.BUY, 1, stop, tp)
                    self.exhaustion_down = False
                    self.exhaustion_up = False

        # Update consecutive counts
        if is_up:
            self.up_count += 1
            self.down_count = 0
            self.run_high = max(self.run_high, h)
            if self.up_count == 1:
                self.run_low = l
            else:
                self.run_low = min(self.run_low, l)

            if self.up_count >= cfg.consecutive_bars:
                self.exhaustion_up = True
                self.exhaust_high = self.run_high
                self.exhaust_low = self.run_low
        elif is_down:
            self.down_count += 1
            self.up_count = 0
            self.run_low = min(self.run_low, l)
            if self.down_count == 1:
                self.run_high = h
            else:
                self.run_high = max(self.run_high, h)

            if self.down_count >= cfg.consecutive_bars:
                self.exhaustion_down = True
                self.exhaust_high = self.run_high
                self.exhaust_low = self.run_low
        else:
            # doji resets
            self.up_count = 0
            self.down_count = 0
            self.exhaustion_up = False
            self.exhaustion_down = False

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
