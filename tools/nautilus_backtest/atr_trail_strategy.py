"""
ATR Trailing Momentum Strategy -- NautilusTrader port.

Enter when the current bar's range (high - low) exceeds a multiple of
the ATR, indicating volatility expansion / momentum. Direction is
determined by bar close vs open (green = long, red = short).

NO fixed take-profit -- position is managed entirely by an ATR-based
trailing stop that locks in profits as the trend continues. Initial
stop is set at a fixed ATR multiple from entry.
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

class ATRTrailConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # ATR params
    atr_period: int = 14
    entry_atr_mult: float = 1.5    # bar range must exceed this * ATR
    stop_atr_mult: float = 1.0     # initial stop distance = N * ATR
    trail_atr_mult: float = 2.0    # trailing stop distance = N * ATR

    # Session
    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0



# ==================== Strategy ====================

class ATRTrailStrategy(Strategy):

    def __init__(self, config: ATRTrailConfig):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # Daily OHLC from RTH bars
        self.daily_highs: list[float] = []
        self.daily_lows: list[float] = []
        self.daily_closes: list[float] = []
        self.max_daily = 50

        # Current day RTH tracking
        self.rth_high: float = -math.inf
        self.rth_low: float = math.inf
        self.rth_close: float = math.nan
        self.rth_started: bool = False

        # Intraday ATR (5-min bars)
        self.close_history: list[float] = []
        self.high_history: list[float] = []
        self.low_history: list[float] = []
        self.intraday_atr: float = math.nan

        # Daily ATR
        self.daily_atr: float = math.nan

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp_price: float = 0.0  # always 0 (no fixed TP)
        self.trade_side: int = 0
        self.best_price: float = 0.0  # best price since entry (for trailing)

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("ATR Trailing Momentum started")

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

        # Bar time in ET
        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        # Track RTH OHLC for daily aggregation
        if 935 <= bar_time_int <= 1600:
            if not self.rth_started:
                self.rth_high = h
                self.rth_low = l
                self.rth_started = True
            else:
                self.rth_high = max(self.rth_high, h)
                self.rth_low = min(self.rth_low, l)
            self.rth_close = c

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
            if self.rth_started and not math.isnan(self.rth_close):
                self.daily_highs.append(self.rth_high)
                self.daily_lows.append(self.rth_low)
                self.daily_closes.append(self.rth_close)
                if len(self.daily_highs) > self.max_daily:
                    self.daily_highs.pop(0)
                    self.daily_lows.pop(0)
                    self.daily_closes.pop(0)

            self.rth_high = -math.inf
            self.rth_low = math.inf
            self.rth_close = math.nan
            self.rth_started = False

            self.trades_today = 0
            self.eod_processed = False
            self.last_reset_day = bar_day

            self._compute_daily_atr()

        # ===== Update intraday ATR on RTH bars =====
        if 935 <= bar_time_int <= 1600:
            self.close_history.append(c)
            self.high_history.append(h)
            self.low_history.append(l)
            max_hist = cfg.atr_period + 2
            if len(self.close_history) > max_hist:
                self.close_history.pop(0)
                self.high_history.pop(0)
                self.low_history.pop(0)
            self._compute_intraday_atr()

        # ===== EOD flatten =====
        if bar_time_int >= cfg.eod_time and not self.eod_processed:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"EOD flatten at {bar_time_int}")
                self._reset_trade_state()
            self.eod_processed = True
            return

        # ===== Trade management (trailing stop) =====
        position = self._get_open_position()
        if position is not None:
            self._manage_position(position, h, l, c)
            if self._get_open_position() is None and self.entry_price > 0:
                self._reset_trade_state()
            return

        if self.entry_price > 0:
            self._reset_trade_state()

        # ===== Entry conditions =====
        if math.isnan(self.intraday_atr) or self.intraday_atr <= 0:
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        bar_range = h - l
        threshold = cfg.entry_atr_mult * self.intraday_atr

        if bar_range <= threshold:
            return

        stop_dist = cfg.stop_atr_mult * self.intraday_atr
        if stop_dist <= 0:
            return

        # Long: volatility expansion + bullish close
        if c > o:
            stop = c - stop_dist
            self._enter_trade(c, OrderSide.BUY, 1, stop, 0.0)

        # Short: volatility expansion + bearish close
        elif c < o:
            stop = c + stop_dist
            self._enter_trade(c, OrderSide.SELL, -1, stop, 0.0)

    # ==================== Daily ATR ====================

    def _compute_daily_atr(self):
        period = self.config.atr_period
        n = len(self.daily_closes)
        if n < period + 1:
            self.daily_atr = math.nan
            return
        trs = []
        for i in range(n - period, n):
            tr = max(
                self.daily_highs[i] - self.daily_lows[i],
                abs(self.daily_highs[i] - self.daily_closes[i - 1]),
                abs(self.daily_lows[i] - self.daily_closes[i - 1]),
            )
            trs.append(tr)
        self.daily_atr = sum(trs) / period

    # ==================== Intraday ATR ====================

    def _compute_intraday_atr(self):
        period = self.config.atr_period
        n = len(self.close_history)
        if n < period + 1:
            self.intraday_atr = math.nan
            return
        trs = []
        for i in range(n - period, n):
            tr = max(
                self.high_history[i] - self.low_history[i],
                abs(self.high_history[i] - self.close_history[i - 1]),
                abs(self.low_history[i] - self.close_history[i - 1]),
            )
            trs.append(tr)
        self.intraday_atr = sum(trs) / period

    # ==================== Entry ====================

    def _enter_trade(self, close: float, side: OrderSide, direction: int,
                     stop: float, tp: float):
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
        self.tp_price = 0.0  # no fixed TP
        self.trade_side = direction
        self.best_price = close
        self.trades_today += 1

        label = "LONG" if direction == 1 else "SHORT"
        self.log.info(
            f"{label}: entry={close:.2f}, stop={stop:.2f}, "
            f"trail_mult={self.config.trail_atr_mult}, "
            f"iATR={self.intraday_atr:.2f}"
        )

    # ==================== Position Management (Trailing Stop) ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        cfg = self.config
        trail_dist = cfg.trail_atr_mult * self.intraday_atr if not math.isnan(self.intraday_atr) else cfg.trail_atr_mult * 5.0

        if self.trade_side == 1:  # LONG
            # Update best price
            if high > self.best_price:
                self.best_price = high
                # Trail stop up
                new_stop = self.best_price - trail_dist
                if new_stop > self.stop_price:
                    self.stop_price = new_stop

            if low <= self.stop_price:
                self.close_position(position)
                self.log.info(f"TRAIL STOP hit at {self.stop_price:.2f} (best={self.best_price:.2f})")
                self._reset_trade_state()
                return

        else:  # SHORT
            # Update best price
            if low < self.best_price:
                self.best_price = low
                # Trail stop down
                new_stop = self.best_price + trail_dist
                if new_stop < self.stop_price:
                    self.stop_price = new_stop

            if high >= self.stop_price:
                self.close_position(position)
                self.log.info(f"TRAIL STOP hit at {self.stop_price:.2f} (best={self.best_price:.2f})")
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
        self.best_price = 0.0
