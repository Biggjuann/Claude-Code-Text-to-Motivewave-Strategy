"""
Opening Range Breakout Strategy — NautilusTrader port.

Based on Kevin Davey's channel breakout approach adapted for day trading.
Computes the high/low of the first 30 minutes of RTH (the "opening range")
and trades breakouts from this range. The opening range acts as an intraday
Donchian channel — a compressed version of the classic N-day channel.

Stop: ATR-based. Exit: EOD flatten.

Reference: Kevin Davey — "Building Winning Algorithmic Trading Systems"
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

class DonchianConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Opening range (first N minutes of RTH)
    or_end_time: int = 945     # OR: 9:30-9:45 (15-min opening range)

    # Risk management
    atr_period: int = 14       # daily ATR
    atr_stop_mult: float = 0.50  # stop = 0.5x daily ATR
    atr_tp_mult: float = 0.0    # TP = Nx daily ATR (0=EOD only, best config)

    # Trend filter
    trend_filter_enabled: bool = True
    trend_lookback: int = 5    # compare yesterday close to N-day-ago close

    # Session
    max_trades_per_day: int = 1
    entry_end: int = 1300      # no entries after 1 PM
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0


# ==================== Strategy ====================

class DonchianStrategy(Strategy):

    def __init__(self, config: DonchianConfig):
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

        # Opening range (intraday channel)
        self.or_high: float = -math.inf
        self.or_low: float = math.inf
        self.or_set: bool = False

        # Daily ATR
        self.daily_atr: float = math.nan

        # Trend filter
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
        self.log.info("Opening Range Breakout started")

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

            self.or_high = -math.inf
            self.or_low = math.inf
            self.or_set = False

            self.trades_today = 0
            self.eod_processed = False
            self.last_reset_day = bar_day

            self._compute_daily_atr()
            self._compute_trend_filter()

        # ===== Build opening range =====
        if 935 <= bar_time_int <= cfg.or_end_time:
            self.or_high = max(self.or_high, h)
            self.or_low = min(self.or_low, l)
            if bar_time_int >= cfg.or_end_time and not self.or_set:
                self.or_set = True
                self.log.info(
                    f"Opening Range: high={self.or_high:.2f}, low={self.or_low:.2f}, "
                    f"width={self.or_high - self.or_low:.2f}"
                )

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

        # ===== Entry: breakout of opening range =====
        if not self.or_set or math.isnan(self.daily_atr):
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if bar_time_int <= cfg.or_end_time or bar_time_int > cfg.entry_end:
            return

        stop_dist = cfg.atr_stop_mult * self.daily_atr
        if stop_dist <= 0:
            return

        tp_dist = cfg.atr_tp_mult * self.daily_atr if cfg.atr_tp_mult > 0 else 0

        # Long: close breaks above opening range high
        if self.can_go_long and c > self.or_high:
            stop = c - stop_dist
            tp = c + tp_dist if tp_dist > 0 else 0.0
            self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

        # Short: close breaks below opening range low
        elif self.can_go_short and c < self.or_low:
            stop = c + stop_dist
            tp = c - tp_dist if tp_dist > 0 else 0.0
            self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

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

    # ==================== Trend Filter ====================

    def _compute_trend_filter(self):
        cfg = self.config
        self.can_go_long = True
        self.can_go_short = True

        if not cfg.trend_filter_enabled:
            return

        n = len(self.daily_closes)
        if n < cfg.trend_lookback + 1:
            return

        recent = self.daily_closes[-1]
        past = self.daily_closes[-(cfg.trend_lookback + 1)]

        if recent > past:
            self.can_go_short = False
        elif recent < past:
            self.can_go_long = False

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
        tp_str = f", TP={tp:.2f}" if tp > 0 else ""
        self.log.info(
            f"{label}: entry={close:.2f}, stop={stop:.2f}{tp_str}, "
            f"OR=[{self.or_low:.2f}, {self.or_high:.2f}], "
            f"ATR={self.daily_atr:.2f}"
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
            if self.tp_price > 0 and high >= self.tp_price:
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
