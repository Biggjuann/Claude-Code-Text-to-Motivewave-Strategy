"""
Unger First-Bar Mean Reversion Strategy — NautilusTrader port.

Based on Andrea Unger's 4x World Cup Championship mean-reversion approach.
Unger says ES/S&P is "naturally a mean-reverting market." His method:
compute displacement levels from the first RTH bar, then FADE overextended
moves (short when price rises too far, long when it drops too far).

Key improvements over naive implementation:
- 0.40% displacement (selective, not triggering every day)
- Entry cutoff at 1 PM (need time for reversion before EOD)
- Trend-aligned filter: only fade against the trend (no shorts in uptrend, etc.)
- 80% ADR stop (wider room for mean reversion to work)

Reference: Unger Academy "Strategy of the Month" and Benzinga articles.
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

class BollingerMRConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # First-bar displacement
    displacement_pct: float = 0.0035   # 0.35% from first bar high/low
    adr_period: int = 14               # Average Daily Range lookback
    adr_stop_mult: float = 1.5          # stop = 150% of ADR (wider = MR breathing room)
    adr_tp_mult: float = 0.0           # TP = Nx ADR from entry (0=disabled)
    tp_at_first_bar: bool = True       # TP at first bar midpoint (structural mean)

    # Trend filter: only allow fades that align with recent trend
    trend_filter_enabled: bool = False  # OFF by default (hurts performance)
    trend_lookback: int = 3            # compare yesterday close to N days ago close

    # Session
    entry_start: int = 940             # after first RTH bar (935)
    entry_end: int = 1300              # no entries after 1 PM (need time for MR)
    max_trades_per_day: int = 1
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0


# ==================== Strategy ====================

class BollingerMRStrategy(Strategy):

    def __init__(self, config: BollingerMRConfig):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # Daily OHLC from RTH bars
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

        # First bar levels
        self.first_bar_high: float = math.nan
        self.first_bar_low: float = math.nan
        self.upper_level: float = math.nan   # fade-short above this
        self.lower_level: float = math.nan   # fade-long below this
        self.first_bar_set: bool = False

        # Average Daily Range
        self.adr: float = math.nan

        # Trend filter
        self.can_fade_long: bool = True   # buy dips allowed
        self.can_fade_short: bool = True  # sell rips allowed

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp_price: float = 0.0
        self.trade_side: int = 0  # 1=long (fading down), -1=short (fading up)

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("Unger First-Bar Mean Reversion started (selective)")

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
                self.daily_highs.append(self.rth_high)
                self.daily_lows.append(self.rth_low)
                self.daily_closes.append(self.rth_close)
                if len(self.daily_highs) > self.max_daily:
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
            self.first_bar_set = False
            self.first_bar_high = math.nan
            self.first_bar_low = math.nan
            self.upper_level = math.nan
            self.lower_level = math.nan
            self.last_reset_day = bar_day

            # Compute ADR and trend filter
            self._compute_adr()
            self._compute_trend_filter()

        # ===== Capture first RTH bar =====
        if bar_time_int == 935 and not self.first_bar_set:
            self.first_bar_high = h
            self.first_bar_low = l
            # Displacement levels
            self.upper_level = self.first_bar_high * (1.0 + cfg.displacement_pct)
            self.lower_level = self.first_bar_low * (1.0 - cfg.displacement_pct)
            self.first_bar_set = True
            self.log.info(
                f"First bar: H={h:.2f}, L={l:.2f}, "
                f"upper={self.upper_level:.2f}, lower={self.lower_level:.2f}"
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
        if not self.first_bar_set or math.isnan(self.adr):
            return
        if self.trades_today >= cfg.max_trades_per_day:
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            return

        stop_dist = cfg.adr_stop_mult * self.adr
        if stop_dist <= 0:
            return

        # Compute TP target
        fb_mid = (self.first_bar_high + self.first_bar_low) / 2.0
        tp_dist = cfg.adr_tp_mult * self.adr if cfg.adr_tp_mult > 0 else 0

        # FADE SHORT: price overextended above first bar → short (mean revert down)
        if self.can_fade_short and c > self.upper_level:
            stop = c + stop_dist
            if cfg.tp_at_first_bar:
                tp = fb_mid  # structural target: first bar midpoint
            elif tp_dist > 0:
                tp = c - tp_dist
            else:
                tp = 0.0
            self._enter_trade(c, OrderSide.SELL, -1, stop, tp)

        # FADE LONG: price overextended below first bar → long (mean revert up)
        elif self.can_fade_long and c < self.lower_level:
            stop = c - stop_dist
            if cfg.tp_at_first_bar:
                tp = fb_mid  # structural target: first bar midpoint
            elif tp_dist > 0:
                tp = c + tp_dist
            else:
                tp = 0.0
            self._enter_trade(c, OrderSide.BUY, 1, stop, tp)

    # ==================== ADR ====================

    def _compute_adr(self):
        period = self.config.adr_period
        n = len(self.daily_highs)
        if n < period:
            self.adr = math.nan
            return
        ranges = [self.daily_highs[-(i + 1)] - self.daily_lows[-(i + 1)]
                  for i in range(period)]
        self.adr = sum(ranges) / period

    # ==================== Trend Filter ====================

    def _compute_trend_filter(self):
        cfg = self.config
        self.can_fade_long = True
        self.can_fade_short = True

        if not cfg.trend_filter_enabled:
            return

        n = len(self.daily_closes)
        if n < cfg.trend_lookback + 1:
            return

        # In uptrend (yesterday close > N-day-ago close):
        #   - fading LONG is OK (buy dips in uptrend = with-trend MR)
        #   - fading SHORT is risky (selling rips in uptrend = counter-trend)
        # In downtrend (yesterday close < N-day-ago close):
        #   - fading SHORT is OK (sell rips in downtrend = with-trend MR)
        #   - fading LONG is risky (buying dips in downtrend = counter-trend)
        recent_close = self.daily_closes[-1]
        past_close = self.daily_closes[-(cfg.trend_lookback + 1)]

        if recent_close > past_close:
            # Uptrend: only allow fade-long (buy dips), block fade-short
            self.can_fade_short = False
        elif recent_close < past_close:
            # Downtrend: only allow fade-short (sell rips), block fade-long
            self.can_fade_long = False

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
        tp_str = f", TP={tp:.2f}" if tp > 0 else ""
        self.log.info(
            f"{label}: entry={close:.2f}, stop={stop:.2f}{tp_str}, "
            f"1st_bar=[{self.first_bar_low:.2f}, {self.first_bar_high:.2f}], "
            f"ADR={self.adr:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        if self.trade_side == 1:  # long (fading down move)
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
        else:  # short (fading up move)
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
