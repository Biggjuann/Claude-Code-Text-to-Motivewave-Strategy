"""
Pivot Point Mean Reversion Strategy — NautilusTrader port.

Based on Andrea Unger's published ES strategy, adapted for mean-reversion.
Uses prior day's cash session OHLC to compute floor trader pivot points.
FADE at R1 (short) and S1 (long), targeting the Pivot Point (PP) as the mean.

ES is mean-reverting intraday — price tends to be attracted back toward PP.
This strategy exploits overextensions at R1/S1 with PP as the natural target.

Reference: Unger Academy + classic floor trader pivot bounce methodology.
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

class ATRBreakoutConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Pivot-based risk management
    atr_period: int = 14
    atr_stop_mult: float = 1.5       # stop beyond R1/S1 by 1.5x ATR (wider = MR breathing room)

    # Session
    entry_start: int = 935           # RTH start
    entry_end: int = 1300            # no entries after 1 PM
    max_trades_per_day: int = 1
    eod_time: int = 1640

    # Filters
    trend_filter_enabled: bool = True
    trend_filter_days: int = 5

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0


# ==================== Strategy ====================

class ATRBreakoutStrategy(Strategy):

    def __init__(self, config: ATRBreakoutConfig):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # Daily OHLC from RTH bars
        self.daily_opens: list[float] = []
        self.daily_highs: list[float] = []
        self.daily_lows: list[float] = []
        self.daily_closes: list[float] = []
        self.max_daily = 50

        # Current day RTH tracking
        self.rth_open: float = math.nan
        self.rth_high: float = -math.inf
        self.rth_low: float = math.inf
        self.rth_close: float = math.nan
        self.rth_started: bool = False

        # Pivot levels (set at start of each day)
        self.pivot: float = math.nan
        self.r1: float = math.nan
        self.s1: float = math.nan
        self.daily_atr: float = math.nan
        self.pivots_set: bool = False

        # Filters
        self.can_go_long: bool = True
        self.can_go_short: bool = True

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
        self.log.info("Pivot Point Mean Reversion started (fade R1/S1 → PP)")

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
                self.rth_open = o
                self.rth_high = h
                self.rth_low = l
                self.rth_started = True
            else:
                self.rth_high = max(self.rth_high, h)
                self.rth_low = min(self.rth_low, l)
            self.rth_close = c

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
            if self.rth_started and not math.isnan(self.rth_open):
                self.daily_opens.append(self.rth_open)
                self.daily_highs.append(self.rth_high)
                self.daily_lows.append(self.rth_low)
                self.daily_closes.append(self.rth_close)
                if len(self.daily_opens) > self.max_daily:
                    self.daily_opens.pop(0)
                    self.daily_highs.pop(0)
                    self.daily_lows.pop(0)
                    self.daily_closes.pop(0)

            self.rth_open = math.nan
            self.rth_high = -math.inf
            self.rth_low = math.inf
            self.rth_close = math.nan
            self.rth_started = False

            self.trades_today = 0
            self.eod_processed = False
            self.pivots_set = False
            self.last_reset_day = bar_day

            # Compute pivots from yesterday's data
            self._compute_pivots()
            self._compute_daily_atr()
            self._compute_filters()

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
        if not self.pivots_set or math.isnan(self.daily_atr):
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        stop_dist = cfg.atr_stop_mult * self.daily_atr
        if stop_dist <= 0:
            return

        # FADE SHORT at R1: price has risen to resistance → short, target PP
        if self.can_go_short and c > self.r1:
            stop = self.r1 + stop_dist   # stop above R1
            tp = self.pivot              # target = PP (the mean)
            self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

        # FADE LONG at S1: price has dropped to support → long, target PP
        elif self.can_go_long and c < self.s1:
            stop = self.s1 - stop_dist   # stop below S1
            tp = self.pivot              # target = PP (the mean)
            self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

    # ==================== Pivot Points ====================

    def _compute_pivots(self):
        n = len(self.daily_closes)
        if n < 1:
            self.pivots_set = False
            return

        yh = self.daily_highs[-1]
        yl = self.daily_lows[-1]
        yc = self.daily_closes[-1]

        self.pivot = (yh + yl + yc) / 3.0
        self.r1 = 2.0 * self.pivot - yl   # R1 = 2*PP - Low
        self.s1 = 2.0 * self.pivot - yh   # S1 = 2*PP - High
        self.pivots_set = True

        self.log.info(
            f"Pivots: PP={self.pivot:.2f}, R1={self.r1:.2f}, S1={self.s1:.2f}"
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

    # ==================== Filters ====================

    def _compute_filters(self):
        cfg = self.config
        self.can_go_long = True
        self.can_go_short = True

        if not cfg.trend_filter_enabled:
            return

        n = len(self.daily_highs)
        if n >= cfg.trend_filter_days + 1:
            # Counter-trend MR at pivots: fade overextensions
            # Uptrend → allow SHORT at R1 (fade the rally), block LONG at S1
            # Downtrend → allow LONG at S1 (fade the selloff), block SHORT at R1
            if self.daily_highs[-1] > self.daily_highs[-(cfg.trend_filter_days + 1)]:
                self.can_go_long = False
            if self.daily_lows[-1] < self.daily_lows[-(cfg.trend_filter_days + 1)]:
                self.can_go_short = False

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

        label = "FADE LONG" if direction == 1 else "FADE SHORT"
        self.log.info(
            f"{label}: entry={close:.2f}, stop={stop:.2f}, TP={tp:.2f} (PP), "
            f"R1={self.r1:.2f}, S1={self.s1:.2f}, ATR={self.daily_atr:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        if self.trade_side == 1:  # LONG (fade at S1, target PP)
            if low <= self.stop_price:
                self.close_position(position)
                self.log.info(f"STOP hit at {self.stop_price:.2f}")
                self._reset_trade_state()
                return
            if high >= self.tp_price:
                self.close_position(position)
                self.log.info(f"TP hit at PP={self.tp_price:.2f}")
                self._reset_trade_state()
                return
        else:  # SHORT (fade at R1, target PP)
            if high >= self.stop_price:
                self.close_position(position)
                self.log.info(f"STOP hit at {self.stop_price:.2f}")
                self._reset_trade_state()
                return
            if low <= self.tp_price:
                self.close_position(position)
                self.log.info(f"TP hit at PP={self.tp_price:.2f}")
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
