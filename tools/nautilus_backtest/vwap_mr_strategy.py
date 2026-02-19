"""
VWAP Mean Reversion Strategy — NautilusTrader.

Compute session VWAP from RTH bars. When price deviates significantly
(> deviation_mult x ATR) from VWAP and a reversal bar appears,
enter toward VWAP. Stop beyond the extreme, TP at VWAP.
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


class VWAPMRConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    deviation_mult: float = 2.0     # min distance from VWAP in ATR units
    atr_period: int = 14
    stop_buffer_pts: float = 2.0    # extra buffer beyond extreme for stop
    use_rr_target: bool = False     # if True use target_rr, else target = VWAP
    target_rr: float = 2.0

    entry_start: int = 1000         # give VWAP time to stabilize
    entry_end: int = 1500
    max_trades_per_day: int = 1
    eod_time: int = 1640

    contracts: int = 10
    dollars_per_contract: float = 0.0


class VWAPMRStrategy(Strategy):

    def __init__(self, config: VWAPMRConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # VWAP state (resets daily)
        self.cum_vol_price: float = 0.0
        self.cum_vol: float = 0.0
        self.vwap: float = 0.0

        # ATR state
        self.tr_values: list[float] = []
        self.prev_close: float = 0.0
        self.atr: float = 0.0

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
        # Use range as volume proxy since we don't have tick volume
        vol_proxy = max(h - l, 0.25)  # min tick

        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert("America/New_York")
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.cum_vol_price = 0.0
            self.cum_vol = 0.0
            self.vwap = 0.0
            self.last_reset_day = bar_day

        # Compute VWAP from RTH bars
        if 935 <= bar_time_int <= 1600:
            typical = (h + l + c) / 3.0
            self.cum_vol_price += typical * vol_proxy
            self.cum_vol += vol_proxy
            if self.cum_vol > 0:
                self.vwap = self.cum_vol_price / self.cum_vol

            # True Range for ATR
            if self.prev_close > 0:
                tr = max(h - l, abs(h - self.prev_close), abs(l - self.prev_close))
            else:
                tr = h - l
            self.tr_values.append(tr)
            if len(self.tr_values) > cfg.atr_period + 10:
                self.tr_values = self.tr_values[-(cfg.atr_period + 10):]
            if len(self.tr_values) >= cfg.atr_period:
                self.atr = sum(self.tr_values[-cfg.atr_period:]) / cfg.atr_period

            self.prev_close = c

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

        # Entry conditions
        if self.vwap <= 0 or self.atr <= 0:
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        deviation = abs(c - self.vwap)
        threshold = cfg.deviation_mult * self.atr

        if deviation < threshold:
            return

        # Price above VWAP + threshold AND bar is bearish (reversal) → SHORT toward VWAP
        if c > self.vwap + threshold and c < o:
            stop = h + cfg.stop_buffer_pts
            if cfg.use_rr_target:
                risk = stop - c
                tp = c - cfg.target_rr * risk if risk > 0 else self.vwap
            else:
                tp = self.vwap
            risk = stop - c
            if risk > 0:
                self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

        # Price below VWAP - threshold AND bar is bullish (reversal) → LONG toward VWAP
        elif c < self.vwap - threshold and c > o:
            stop = l - cfg.stop_buffer_pts
            if cfg.use_rr_target:
                risk = c - stop
                tp = c + cfg.target_rr * risk if risk > 0 else self.vwap
            else:
                tp = self.vwap
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
