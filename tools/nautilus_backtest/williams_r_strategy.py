"""
Williams Volatility Breakout Strategy — NautilusTrader port.

Based on Larry Williams' actual World Cup Championship winning system.
Core logic: enter when price moves a percentage of yesterday's range
away from today's open. This captures volatility expansion that tends
to continue in the breakout direction.

Reference: "Long-Term Secrets to Short-Term Trading" by Larry Williams.
Entry = Open ± (Yesterday_Range × Multiplier), stop = range-based, target = R:R.
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

class WilliamsRConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Williams volatility breakout params
    entry_mult: float = 0.50   # entry = open ± range * mult (Williams default 0.25-0.70)
    stop_mult: float = 0.50    # stop = entry ∓ range * stop_mult
    target_rr: float = 3.0     # target as R-multiple (Williams used 3:1 to 4:1)

    # Session
    entry_start: int = 935     # first RTH bar
    entry_end: int = 1530
    max_trades_per_day: int = 1
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0


# ==================== Strategy ====================

class WilliamsRStrategy(Strategy):

    def __init__(self, config: WilliamsRConfig):
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

        # Today's trigger levels (set at start of RTH)
        self.long_trigger: float = math.nan
        self.short_trigger: float = math.nan
        self.yesterday_range: float = 0.0
        self.today_open: float = math.nan
        self.triggers_set: bool = False

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
        self.log.info("Williams Volatility Breakout started")

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
            # Archive previous day's RTH data
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

            # Reset RTH tracking
            self.rth_open = math.nan
            self.rth_high = -math.inf
            self.rth_low = math.inf
            self.rth_close = math.nan
            self.rth_started = False

            # Reset daily trade state
            self.trades_today = 0
            self.eod_processed = False
            self.triggers_set = False
            self.long_trigger = math.nan
            self.short_trigger = math.nan
            self.today_open = math.nan
            self.last_reset_day = bar_day

        # ===== Set triggers on first RTH bar =====
        if bar_time_int == 935 and not self.triggers_set and len(self.daily_highs) >= 1:
            yest_high = self.daily_highs[-1]
            yest_low = self.daily_lows[-1]
            self.yesterday_range = yest_high - yest_low

            if self.yesterday_range > 0:
                self.today_open = o  # RTH open price (the bar's open is the 9:30 price)
                self.long_trigger = self.today_open + self.yesterday_range * cfg.entry_mult
                self.short_trigger = self.today_open - self.yesterday_range * cfg.entry_mult
                self.triggers_set = True
                self.log.info(
                    f"Triggers: open={self.today_open:.2f}, "
                    f"long={self.long_trigger:.2f}, short={self.short_trigger:.2f}, "
                    f"yest_range={self.yesterday_range:.2f}"
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

        # ===== Entry conditions =====
        if not self.triggers_set:
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        # Long breakout: bar high exceeds long trigger
        if not math.isnan(self.long_trigger) and h > self.long_trigger:
            stop_dist = self.yesterday_range * cfg.stop_mult
            stop = c - stop_dist
            risk = abs(c - stop)
            if risk > 0:
                tp = c + cfg.target_rr * risk
                self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

        # Short breakout: bar low breaks short trigger
        elif not math.isnan(self.short_trigger) and l < self.short_trigger:
            stop_dist = self.yesterday_range * cfg.stop_mult
            stop = c + stop_dist
            risk = abs(stop - c)
            if risk > 0:
                tp = c - cfg.target_rr * risk
                self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

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
            f"risk={risk:.2f}, yest_range={self.yesterday_range:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        if self.trade_side == 1:  # long
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
        else:  # short
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
