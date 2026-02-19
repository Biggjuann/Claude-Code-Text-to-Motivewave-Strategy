"""
Previous Day High/Low Breakout Strategy -- NautilusTrader port.

Tracks the RTH high and low each day and archives them at day change.
Next day: enter long if close breaks above yesterday's high, short if
close breaks below yesterday's low. This captures continuation moves
that breach prior-session extremes.

Stop: ATR-based. Target: R:R ratio from risk.
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

class PrevDayHLConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # ATR params
    atr_period: int = 14
    stop_atr_mult: float = 1.5
    target_rr: float = 3.0

    # Session
    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0



# ==================== Strategy ====================

class PrevDayHLStrategy(Strategy):

    def __init__(self, config: PrevDayHLConfig):
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

        # Previous day levels
        self.yesterday_high: float = math.nan
        self.yesterday_low: float = math.nan
        self.levels_set: bool = False

        # Daily ATR
        self.daily_atr: float = math.nan

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp_price: float = 0.0
        self.trade_side: int = 0

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("Previous Day High/Low Breakout started")

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

        # Track RTH OHLC
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
            self.levels_set = False
            self.last_reset_day = bar_day

            # Set previous day levels
            self._set_prev_day_levels()
            self._compute_daily_atr()

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
        if not self.levels_set or math.isnan(self.daily_atr):
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        stop_dist = cfg.stop_atr_mult * self.daily_atr
        if stop_dist <= 0:
            return

        # Long: close breaks above yesterday's high
        if c > self.yesterday_high:
            stop = c - stop_dist
            risk = abs(c - stop)
            tp = c + cfg.target_rr * risk
            self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

        # Short: close breaks below yesterday's low
        elif c < self.yesterday_low:
            stop = c + stop_dist
            risk = abs(stop - c)
            tp = c - cfg.target_rr * risk
            self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

    # ==================== Previous Day Levels ====================

    def _set_prev_day_levels(self):
        if len(self.daily_highs) < 1:
            self.levels_set = False
            return

        self.yesterday_high = self.daily_highs[-1]
        self.yesterday_low = self.daily_lows[-1]
        self.levels_set = True
        self.log.info(
            f"Prev day levels: high={self.yesterday_high:.2f}, "
            f"low={self.yesterday_low:.2f}"
        )

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
        self.tp_price = tp
        self.trade_side = direction
        self.trades_today += 1

        label = "LONG" if direction == 1 else "SHORT"
        risk = abs(close - stop)
        self.log.info(
            f"{label}: entry={close:.2f}, stop={stop:.2f}, TP={tp:.2f}, "
            f"risk={risk:.2f}, yest_H={self.yesterday_high:.2f}, "
            f"yest_L={self.yesterday_low:.2f}, ATR={self.daily_atr:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        if self.trade_side == 1:  # LONG
            if low <= self.stop_price:
                self.close_position(position)
                self.log.info(f"STOP hit at {self.stop_price:.2f}")
                self._reset_trade_state()
                return
            if high >= self.tp_price:
                self.close_position(position)
                self.log.info(f"TP hit at {self.tp_price:.2f}")
                self._reset_trade_state()
                return
        else:  # SHORT
            if high >= self.stop_price:
                self.close_position(position)
                self.log.info(f"STOP hit at {self.stop_price:.2f}")
                self._reset_trade_state()
                return
            if low <= self.tp_price:
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
