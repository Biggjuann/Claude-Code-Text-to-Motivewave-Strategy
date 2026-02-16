"""
MagicLine Strategy — NautilusTrader port.

Ported from MagicLineStrategy.java v4.0 (MotiveWave SDK).
Long-only regressive S/R strategy using LB = highest(lowest(low, length), length).
EMA filter, 5-condition entry, BE/partial/trail/TP2 exit hierarchy.

User's saved MotiveWave defaults baked in as config defaults.
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

class MagicLineConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # LB Indicator
    length: int = 20
    touch_tolerance_ticks: int = 4
    zone_buffer_pts: float = 1.0       # saved: 1.0
    came_from_pts: float = 5.0
    came_from_lookback: int = 10       # saved: 10

    # EMA Filter
    ema_filter_enabled: bool = True
    ema_period: int = 21

    # Session
    trade_session_enabled: bool = True   # saved: true
    trade_start: int = 200               # saved: 200 (2 AM ET)
    trade_end: int = 1600
    max_trades_per_day: int = 3          # saved: 3

    # Stop
    stoploss_mode: int = 1   # 0=fixed, 1=structural
    stop_buffer_ticks: int = 20
    contracts: int = 10
    dollars_per_contract: float = 0.0

    # Breakeven
    be_enabled: bool = True
    be_trigger_pts: float = 10.0         # saved: 10

    # Targets
    tp1_r: float = 3.0                   # saved: 3
    tp2_r: float = 10.0                  # saved: 10
    partial_enabled: bool = True
    partial_pct: int = 25                # saved: 25

    # EOD
    eod_time: int = 1640

    # VIX
    vix_filter_enabled: bool = False
    vix_off: float = 30.0
    vix_on: float = 20.0


# ==================== Strategy ====================

class MagicLineStrategy(Strategy):

    def __init__(self, config: MagicLineConfig, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # VIX filter
        self.vix_lookup = vix_lookup or {}
        self.vix_blocked: bool = False

        # Bar history (rolling window for LB + entry conditions)
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.max_hist = 200  # 2*length + came_from_lookback + margin

        # LB values (rolling for trail check)
        self.lb_values: list[float] = []

        # EMA state (manual rolling)
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp1_price: float = 0.0
        self.tp2_price: float = 0.0
        self.risk_points: float = 0.0
        self.initial_qty: int = 0
        self.partial_taken: bool = False
        self.be_activated: bool = False
        self.trail_active: bool = False

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("MagicLine Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("MagicLine Strategy stopped")

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

        # ===== Trade management =====
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

        # Session window
        if cfg.trade_session_enabled:
            if not (cfg.trade_start <= bar_time_int < cfg.trade_end):
                return

        # Max trades
        if self.trades_today >= cfg.max_trades_per_day:
            return

        # Close must be above LB (bullish bias)
        if c < lb:
            return

        # EMA filter: close must be above EMA
        if cfg.ema_filter_enabled and not math.isnan(self.ema_value):
            if c < self.ema_value:
                return

        # 5-condition entry check
        if self._check_entry(lb, c, o, l):
            self._enter_long(c, l, lb)

    # ==================== LB Calculation ====================

    def _compute_lb(self) -> float:
        """LB = highest(lowest(low, length), length) — double windowed."""
        cfg = self.config
        length = cfg.length
        lows = self.hist_lows
        n = len(lows)

        if n < 2 * length:
            return math.nan

        # Compute lowest-low over 'length' bars for the last 'length' windows
        # We need lower_band[i] for i in [n-length, n-1]
        lower_bands = []
        for i in range(n - length, n):
            start = i - length + 1
            if start < 0:
                return math.nan
            window = lows[start:i + 1]
            lower_bands.append(min(window))

        # LB = highest of those lower bands
        return max(lower_bands)

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

    # ==================== Entry Check ====================

    def _check_entry(self, lb: float, close: float, open_: float, low: float) -> bool:
        """5-condition long entry check (conditions 4 & 5 are OR'd)."""
        cfg = self.config
        tick_size = 0.01  # ratio-adjusted data
        touch_tol = cfg.touch_tolerance_ticks * tick_size
        zone_buffer = cfg.zone_buffer_pts

        # Condition 1: Low in entry zone [lb - touchTol, lb + zoneBuffer]
        if not (low >= lb - touch_tol and low <= lb + zone_buffer):
            return False

        # Condition 2: Bullish bar (close > open)
        if not (close > open_):
            return False

        # Condition 3: Support held (close > lb)
        if not (close > lb):
            return False

        # Condition 4: Higher low forming
        higher_low = False
        n = len(self.hist_lows)
        if n >= 3:
            prev_low = self.hist_lows[-2]
            prev_prev_low = self.hist_lows[-3]
            higher_low = (low > prev_low) or (prev_low > prev_prev_low)

        # Condition 5: Price came from above
        came_from_above = False
        lookback = cfg.came_from_lookback
        highs = self.hist_highs
        n = len(highs)
        start = max(0, n - 1 - lookback)
        for i in range(start, n - 1):
            if highs[i] > lb + cfg.came_from_pts:
                came_from_above = True
                break

        return higher_low or came_from_above

    # ==================== Enter Long ====================

    def _enter_long(self, close: float, low: float, lb: float):
        cfg = self.config
        tick_size = 0.01
        stop_buffer = cfg.stop_buffer_ticks * tick_size

        # Compute stop
        if cfg.stoploss_mode == 1:  # structural
            stop = low - stop_buffer
        else:  # fixed
            stop = close - stop_buffer

        risk = abs(close - stop)
        if risk <= 0:
            risk = stop_buffer

        tp1 = close + cfg.tp1_r * risk
        tp2 = close + cfg.tp2_r * risk

        num_contracts = self._compute_contracts()
        qty = Quantity.from_int(num_contracts)

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        self.entry_price = close
        self.stop_price = stop
        self.tp1_price = tp1
        self.tp2_price = tp2
        self.risk_points = risk
        self.initial_qty = num_contracts
        self.partial_taken = False
        self.be_activated = False
        self.trail_active = False
        self.trades_today += 1

        self.log.info(
            f"LONG: qty={num_contracts}, entry={close:.2f}, "
            f"stop={stop:.2f}, TP1={tp1:.2f}, TP2={tp2:.2f}, "
            f"risk={risk:.1f}pts, LB={lb:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float, lb: float):
        cfg = self.config

        # 1. Breakeven trigger (before partial and stop)
        if cfg.be_enabled and not self.be_activated and not self.partial_taken:
            if high >= self.entry_price + cfg.be_trigger_pts:
                self.be_activated = True
                self.log.info(
                    f"BE triggered: entry={self.entry_price:.2f}, "
                    f"stop moved to {self.entry_price:.2f}"
                )

        # 2. Partial at TP1
        if not self.partial_taken and high >= self.tp1_price:
            if cfg.partial_enabled and self.initial_qty > 1:
                partial_qty = max(1, int(self.initial_qty * cfg.partial_pct / 100))
                current_qty = int(position.quantity.as_double())
                if partial_qty > 0 and partial_qty < current_qty:
                    sell_order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity.from_int(partial_qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sell_order)
                    self.log.info(
                        f"TP1 partial: sold {partial_qty} of {current_qty} "
                        f"at TP1={self.tp1_price:.2f}"
                    )
            self.partial_taken = True
            self.be_activated = True
            self.trail_active = True

        # 3. Stop loss
        current_stop = self.entry_price if (self.partial_taken or self.be_activated) else self.stop_price
        if current_stop > 0 and low <= current_stop:
            self.close_position(position)
            stop_type = "TRAIL" if self.partial_taken else ("BE" if self.be_activated else "INITIAL")
            self.log.info(f"{stop_type} stop hit at {current_stop:.2f}")
            self._reset_trade_state()
            return

        # 4. Trail exit: close below LB (after partial)
        if self.trail_active and self.partial_taken:
            if close < lb:
                self.close_position(position)
                self.log.info(f"Trail exit: close {close:.2f} < LB {lb:.2f}")
                self._reset_trade_state()
                return

        # 5. TP2 full exit
        if self.partial_taken and self.tp2_price > 0 and high >= self.tp2_price:
            self.close_position(position)
            self.log.info(f"TP2 hit at {self.tp2_price:.2f}")
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
        self.tp2_price = 0.0
        self.risk_points = 0.0
        self.initial_qty = 0
        self.partial_taken = False
        self.be_activated = False
        self.trail_active = False
