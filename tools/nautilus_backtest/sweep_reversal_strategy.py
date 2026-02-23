"""
Displacement-Doji-Reversal (DDR) Strategy — NautilusTrader port.

Core pattern (3-bar candlestick reversal):
  Bar[-2]: Displacement candle (range >= avg × mult)
  Bar[-1]: Doji (body_pct <= threshold — indecision/stalling)
  Bar[ 0]: Displacement candle in OPPOSITE direction

Short setup: bullish displacement → doji → bearish displacement
Long setup:  bearish displacement → doji → bullish displacement

Stop = highest high (short) / lowest low (long) of the 3-bar pattern.
TP   = entry ± target_rr × risk.
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

class SweepReversalConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Displacement detection
    lookback: int = 20               # bars to compute average range
    displacement_mult: float = 2.0   # range >= avg × mult qualifies as displacement
    doji_max_body_pct: float = 25.0  # max body % for doji bar

    # Risk
    target_rr: float = 3.0
    direction: str = "both"          # "long", "short", "both"

    # VIX range filter
    vix_filter_enabled: bool = False
    vix_min: float = 15.0
    vix_max: float = 20.0

    # Session
    entry_start: int = 935
    entry_end: int = 1530
    max_trades_per_day: int = 2
    eod_time: int = 1640

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0


# ==================== Strategy ====================

class SweepReversalStrategy(Strategy):

    def __init__(self, config: SweepReversalConfig, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # VIX filter: {"YYYY-MM-DD": float}
        self.vix_lookup = vix_lookup or {}
        self.vix_in_range: bool = True

        # Rolling range buffer (RTH bars only)
        self.ranges: list[float] = []

        # Previous 2 bars for 3-bar pattern detection
        self.prev2_open: float = math.nan
        self.prev2_high: float = math.nan
        self.prev2_low: float = math.nan
        self.prev2_close: float = math.nan

        self.prev1_open: float = math.nan
        self.prev1_high: float = math.nan
        self.prev1_low: float = math.nan
        self.prev1_close: float = math.nan

        self.has_history: bool = False  # True once we have 2 previous bars
        self._prev_count: int = 0      # counts 0, 1, 2

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp_price: float = 0.0
        self.trade_side: int = 0  # 1=long, -1=short

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("DDR (Displacement-Doji-Reversal) Strategy started")

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
        bar_range = h - l

        # Bar time in ET
        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        # ===== Update rolling range buffer (RTH bars only, 935-1600) =====
        if 935 <= bar_time_int <= 1600 and bar_range > 0:
            self.ranges.append(bar_range)
            if len(self.ranges) > cfg.lookback:
                self.ranges.pop(0)

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.has_history = False
            self._prev_count = 0
            self.last_reset_day = bar_day

            # VIX range filter: check previous day's close
            if cfg.vix_filter_enabled and self.vix_lookup:
                prev_date = (bar_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                vix_close = self.vix_lookup.get(prev_date)
                if vix_close is not None:
                    was_in = self.vix_in_range
                    self.vix_in_range = cfg.vix_min <= vix_close <= cfg.vix_max
                    if self.vix_in_range != was_in:
                        state = "IN RANGE" if self.vix_in_range else "OUT OF RANGE"
                        self.log.info(
                            f"VIX {state}: {vix_close:.1f} "
                            f"(range {cfg.vix_min}-{cfg.vix_max})"
                        )

        # ===== EOD flatten =====
        if bar_time_int >= cfg.eod_time and not self.eod_processed:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"EOD flatten at {bar_time_int}")
                self._reset_trade_state()
            self.eod_processed = True
            self._shift_history(o, h, l, c)
            return

        # ===== Trade management =====
        position = self._get_open_position()
        if position is not None:
            self._manage_position(position, h, l, c)
            if self._get_open_position() is None and self.entry_price > 0:
                self._reset_trade_state()
            self._shift_history(o, h, l, c)
            return

        if self.entry_price > 0:
            self._reset_trade_state()

        # ===== Entry gates =====
        if not self.vix_in_range:
            self._shift_history(o, h, l, c)
            return
        if not self.has_history:
            self._shift_history(o, h, l, c)
            return
        if len(self.ranges) < cfg.lookback:
            self._shift_history(o, h, l, c)
            return
        if self.trades_today >= cfg.max_trades_per_day:
            self._shift_history(o, h, l, c)
            return
        if not (cfg.entry_start <= bar_time_int <= cfg.entry_end):
            self._shift_history(o, h, l, c)
            return

        # ===== Compute average range =====
        avg_range = sum(self.ranges) / len(self.ranges)
        if avg_range <= 0:
            self._shift_history(o, h, l, c)
            return

        disp_threshold = avg_range * cfg.displacement_mult

        # ===== 3-bar DDR pattern detection =====

        # Bar[-2] checks
        prev2_range = self.prev2_high - self.prev2_low
        prev2_bullish = self.prev2_close > self.prev2_open
        prev2_bearish = self.prev2_close < self.prev2_open
        prev2_is_disp = prev2_range >= disp_threshold

        # Bar[-1] checks (doji)
        prev1_range = self.prev1_high - self.prev1_low
        prev1_body = abs(self.prev1_close - self.prev1_open)
        prev1_body_pct = (prev1_body / prev1_range * 100) if prev1_range > 0 else 100.0
        prev1_is_doji = prev1_body_pct <= cfg.doji_max_body_pct

        # Bar[0] (current) checks
        curr_bullish = c > o
        curr_bearish = c < o
        curr_is_disp = bar_range >= disp_threshold

        # ----- Short setup: bullish disp → doji → bearish disp -----
        if cfg.direction in ("both", "short"):
            if prev2_bullish and prev2_is_disp and prev1_is_doji and curr_bearish and curr_is_disp:
                # Stop = highest high of 3-bar pattern
                stop = max(self.prev2_high, self.prev1_high, h)
                risk = stop - c
                if risk > 0:
                    tp = c - cfg.target_rr * risk
                    self._enter_trade(c, OrderSide.SELL, -1, stop, tp)
                    self._shift_history(o, h, l, c)
                    return

        # ----- Long setup: bearish disp → doji → bullish disp -----
        if cfg.direction in ("both", "long"):
            if prev2_bearish and prev2_is_disp and prev1_is_doji and curr_bullish and curr_is_disp:
                # Stop = lowest low of 3-bar pattern
                stop = min(self.prev2_low, self.prev1_low, l)
                risk = c - stop
                if risk > 0:
                    tp = c + cfg.target_rr * risk
                    self._enter_trade(c, OrderSide.BUY, 1, stop, tp)
                    self._shift_history(o, h, l, c)
                    return

        self._shift_history(o, h, l, c)

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
            f"risk={risk:.2f}, R:R={self.config.target_rr}"
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
            if self.tp_price > 0 and high >= self.tp_price:
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
            if self.tp_price > 0 and low <= self.tp_price:
                self.close_position(position)
                self.log.info(f"TP hit at {self.tp_price:.2f}")
                self._reset_trade_state()
                return

    # ==================== Helpers ====================

    def _shift_history(self, o: float, h: float, l: float, c: float):
        """Shift bar history: prev2 ← prev1, prev1 ← current."""
        self.prev2_open = self.prev1_open
        self.prev2_high = self.prev1_high
        self.prev2_low = self.prev1_low
        self.prev2_close = self.prev1_close

        self.prev1_open = o
        self.prev1_high = h
        self.prev1_low = l
        self.prev1_close = c

        self._prev_count = min(self._prev_count + 1, 2)
        if self._prev_count >= 2:
            self.has_history = True

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
