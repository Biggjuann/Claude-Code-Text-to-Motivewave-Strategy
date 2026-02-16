"""
LB Short Strategy — NautilusTrader port.

Short-only strategy using the LB regressive S/R line from MagicLine.
LB = highest(lowest(low, length), length).

Bar coloring (study-based):
  - Green bar: close >= LB (price holding support)
  - Red bar:   close < LB  (price broke support)

Entry: short when price crosses from green to red (close breaks below LB).
Optional EMA filter: only short when close < EMA (bearish bias).
Exit hierarchy: Green-bar exit -> Fixed stop -> TP1 partial -> Trail stop -> EOD.
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

class LBShortConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # LB Indicator
    length: int = 20

    # Session
    rth_start: int = 930       # RTH open (9:30 AM ET)
    rth_end: int = 1600        # RTH close (4:00 PM ET)
    eod_time: int = 1640       # forced flatten
    max_trades_per_day: int = 1

    # Sizing
    contracts: int = 10
    dollars_per_contract: float = 0.0

    # Stop
    stop_buffer_ticks: int = 20  # buffer above entry bar high

    # Breakeven
    be_enabled: bool = True
    be_trigger_pts: float = 10.0  # move stop to entry after this much profit

    # Targets
    tp1_pts: float = 15.0       # first target in points
    partial_pct: int = 25       # % to cut at TP1

    # Trail
    trail_pts: float = 5.0      # trailing stop distance from close

    # EMA Filter
    ema_filter_enabled: bool = True
    ema_period: int = 50

    # VIX
    vix_filter_enabled: bool = False
    vix_off: float = 30.0
    vix_on: float = 20.0


# ==================== Strategy ====================

class LBShortStrategy(Strategy):

    def __init__(self, config: LBShortConfig, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # VIX filter
        self.vix_lookup = vix_lookup or {}
        self.vix_blocked: bool = False

        # Bar history (rolling window for LB)
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.max_hist = 200

        # LB values
        self.lb_values: list[float] = []

        # EMA state
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp1_price: float = 0.0
        self.entry_bar_high: float = 0.0
        self.bars_since_entry: int = 0
        self.initial_qty: int = 0
        self.partial_taken: bool = False
        self.be_activated: bool = False
        self.trail_active: bool = False
        self.trail_stop: float = 0.0

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("LB Short Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("LB Short Strategy stopped")

    # ==================== Core Logic ====================

    def on_bar(self, bar: Bar):
        self.bar_count += 1
        cfg = self.config

        o = bar.open.as_double()
        h = bar.high.as_double()
        l = bar.low.as_double()
        c = bar.close.as_double()

        # Maintain rolling history
        self.hist_opens.append(o)
        self.hist_closes.append(c)
        self.hist_highs.append(h)
        self.hist_lows.append(l)
        if len(self.hist_opens) > self.max_hist:
            self.hist_opens.pop(0)
            self.hist_closes.pop(0)
            self.hist_highs.pop(0)
            self.hist_lows.pop(0)

        # Update EMA
        self._update_ema(c)

        # Warmup: need at least 2*length bars for LB
        min_bars = 2 * cfg.length
        if len(self.hist_lows) < min_bars:
            return

        # Compute LB
        lb = self._compute_lb()
        if math.isnan(lb):
            return
        self.lb_values.append(lb)
        if len(self.lb_values) > 100:
            self.lb_values.pop(0)

        # Bar time in ET
        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
            self.trades_today = 0
            self.eod_processed = False
            self.last_reset_day = bar_day

            # VIX hysteresis filter
            if cfg.vix_filter_enabled and self.vix_lookup:
                prev_date = (bar_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                vix_close = self.vix_lookup.get(prev_date)
                if vix_close is not None:
                    if self.vix_blocked and vix_close < cfg.vix_on:
                        self.vix_blocked = False
                        self.log.info(f"VIX filter OFF: VIX={vix_close:.1f} < {cfg.vix_on}")
                    elif not self.vix_blocked and vix_close > cfg.vix_off:
                        self.vix_blocked = True
                        self.log.info(f"VIX filter ON: VIX={vix_close:.1f} > {cfg.vix_off}")

        # ===== EOD flatten =====
        if bar_time_int >= cfg.eod_time and not self.eod_processed:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"EOD flatten at {bar_time_int}")
                self._reset_trade_state()
            self.eod_processed = True
            return

        # ===== Trade management (before entry) =====
        position = self._get_open_position()
        if position is not None:
            self._manage_position(position, h, l, c, lb)
            position = self._get_open_position()
            if position is None and self.entry_price > 0:
                self._reset_trade_state()
            return  # Don't enter while in position

        if self.entry_price > 0:
            self._reset_trade_state()

        # ===== Entry conditions =====
        # VIX block
        if self.vix_blocked:
            return

        # RTH window
        if not (cfg.rth_start <= bar_time_int < cfg.rth_end):
            return

        # Max trades
        if self.trades_today >= cfg.max_trades_per_day:
            return

        # EMA filter: only short when close is below EMA (bearish bias)
        if cfg.ema_filter_enabled and not math.isnan(self.ema_value):
            if c >= self.ema_value:
                return

        # Need at least 2 bars of LB history for prev comparison
        if len(self.lb_values) < 2:
            return

        prev_lb = self.lb_values[-2]

        # Bar color check
        is_red = c < lb                         # current bar is RED
        prev_close = self.hist_closes[-2]
        prev_was_green = prev_close >= prev_lb   # previous bar was GREEN

        if not is_red:
            return  # current bar must be RED

        # Entry trigger: crossed from above only (prev green -> current red)
        if prev_was_green:
            self._enter_short(c, h, lb)

    # ==================== EMA ====================

    def _update_ema(self, close: float):
        period = self.config.ema_period
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

    # ==================== LB Calculation ====================

    def _compute_lb(self) -> float:
        """LB = highest(lowest(low, length), length) — double windowed."""
        length = self.config.length
        lows = self.hist_lows
        n = len(lows)

        if n < 2 * length:
            return math.nan

        # Compute lowest-low over 'length' bars for the last 'length' windows
        lower_bands = []
        for i in range(n - length, n):
            start = i - length + 1
            if start < 0:
                return math.nan
            window = lows[start:i + 1]
            lower_bands.append(min(window))

        # LB = highest of those lower bands
        return max(lower_bands)

    # ==================== Enter Short ====================

    def _enter_short(self, close: float, high: float, lb: float):
        cfg = self.config
        tick_size = 0.01  # ratio-adjusted data

        num_contracts = self._compute_contracts()
        qty = Quantity.from_int(num_contracts)

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        stop = high + cfg.stop_buffer_ticks * tick_size
        tp1 = close - cfg.tp1_pts

        self.entry_price = close
        self.entry_bar_high = high
        self.stop_price = stop
        self.tp1_price = tp1
        self.bars_since_entry = 0
        self.initial_qty = num_contracts
        self.partial_taken = False
        self.be_activated = False
        self.trail_active = False
        self.trail_stop = 0.0
        self.trades_today += 1

        self.log.info(
            f"SHORT: qty={num_contracts}, entry={close:.2f}, "
            f"stop={stop:.2f}, TP1={tp1:.2f}, "
            f"entryBarHigh={high:.2f}, LB={lb:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float, lb: float):
        cfg = self.config
        tick_size = 0.01

        self.bars_since_entry += 1

        # 1. Bar-1 check: if first bar after entry is GREEN, close immediately
        if self.bars_since_entry == 1:
            if close >= lb:  # GREEN bar — breakdown failed
                self.close_position(position)
                self.log.info(
                    f"GREEN BAR EXIT (bar 1): close {close:.2f} >= LB {lb:.2f}, "
                    f"breakdown failed"
                )
                self._reset_trade_state()
                return
            else:
                # RED bar confirmed — lock in stop at entry_bar_high + buffer
                self.stop_price = self.entry_bar_high + cfg.stop_buffer_ticks * tick_size
                self.log.info(
                    f"Bar 1 RED confirmed: stop set at {self.stop_price:.2f}"
                )

        # 2. Breakeven trigger: move stop to entry price after profit threshold
        if cfg.be_enabled and not self.be_activated and not self.partial_taken:
            if low <= self.entry_price - cfg.be_trigger_pts:
                self.be_activated = True
                self.stop_price = self.entry_price
                self.log.info(
                    f"BE triggered: stop moved to entry {self.entry_price:.2f}"
                )

        # 3. Stop check (high breaches stop => stopped out)
        if self.stop_price > 0 and high >= self.stop_price:
            self.close_position(position)
            stop_type = "BE" if self.be_activated else "INITIAL"
            self.log.info(f"{stop_type} stop hit at {self.stop_price:.2f} (high={high:.2f})")
            self._reset_trade_state()
            return

        # 4. TP1 partial
        if not self.partial_taken and low <= self.tp1_price:
            current_qty = int(position.quantity.as_double())
            if cfg.partial_pct > 0 and self.initial_qty > 1:
                partial_qty = max(1, int(self.initial_qty * cfg.partial_pct / 100))
                if partial_qty < current_qty:
                    buy_order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity.from_int(partial_qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(buy_order)
                    self.log.info(
                        f"TP1 partial: covered {partial_qty} of {current_qty} "
                        f"at TP1={self.tp1_price:.2f}"
                    )
            self.partial_taken = True
            self.trail_active = True
            self.trail_stop = close + cfg.trail_pts
            self.log.info(f"Trail activated: trail_stop={self.trail_stop:.2f}")

        # 5. Trail update (if active)
        if self.trail_active:
            candidate = close + cfg.trail_pts
            if candidate < self.trail_stop:
                self.trail_stop = candidate  # ratchet DOWN only
            if high >= self.trail_stop:
                self.close_position(position)
                self.log.info(
                    f"TRAIL stop hit at {self.trail_stop:.2f} (high={high:.2f})"
                )
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
        qty = max(1, int(equity // cfg.dollars_per_contract))
        return qty

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
        self.tp1_price = 0.0
        self.entry_bar_high = 0.0
        self.bars_since_entry = 0
        self.initial_qty = 0
        self.partial_taken = False
        self.be_activated = False
        self.trail_active = False
        self.trail_stop = 0.0
