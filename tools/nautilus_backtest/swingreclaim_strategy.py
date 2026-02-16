"""
SwingReclaim Strategy — NautilusTrader port.

Ported from SDKSwingReclaimStrategy.java v2.0 (MotiveWave SDK).
Bidirectional swing point break-then-reclaim strategy.
Swing detection via pivot high/low with configurable strength.
State machine: ACTIVE → BROKEN → RECLAIM (entry).

Java defaults used as config defaults (no saved overrides).
"""

import math
from dataclasses import dataclass

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


# ==================== Swing Level ====================

STATE_ACTIVE = 0
STATE_BROKEN = 1


@dataclass
class SwingLevel:
    price: float
    is_high: bool
    state: int = STATE_ACTIVE
    sweep_extreme: float = math.nan
    detected_bar: int = 0
    broke_bar: int = -1
    traded: bool = False
    canceled: bool = False
    reclaim_bar: int = -1  # bar on which reclaim fired (for entry timing)


# ==================== Config ====================

class SwingReclaimConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Direction
    enable_long: bool = True
    enable_short: bool = True

    # Swing detection
    strength: int = 45
    reclaim_window: int = 20

    # Session / limits
    max_trades_day: int = 3
    session_enabled: bool = False
    session_start: int = 930
    session_end: int = 1600

    # Position sizing
    contracts: int = 2
    dollars_per_contract: float = 0.0

    # Stop loss
    stop_buffer_ticks: int = 4
    stop_min_pts: float = 2.0
    stop_max_pts: float = 40.0

    # Breakeven
    be_enabled: bool = True
    be_trigger_pts: float = 10.0

    # TP1 Partial
    tp1_points: float = 20.0
    tp1_pct: int = 50

    # Runner trail
    trail_points: float = 15.0

    # EOD
    eod_enabled: bool = True
    eod_time: int = 1640

    # VIX
    vix_filter_enabled: bool = False
    vix_off: float = 30.0
    vix_on: float = 20.0


# ==================== Strategy ====================

class SwingReclaimStrategy(Strategy):

    def __init__(self, config: SwingReclaimConfig, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # VIX filter
        self.vix_lookup = vix_lookup or {}
        self.vix_blocked: bool = False

        # Bar history — keep enough for pivot detection window
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.hist_closes: list[float] = []
        self.max_hist = max(500, config.strength * 4)

        # Swing levels
        self.swing_levels: list[SwingLevel] = []
        self.last_checked_pivot_bar: int = -1  # absolute bar_count of last pivot check

        # Pending reclaim entries (set by state machine, consumed by entry logic)
        self.pending_reclaims: list[SwingLevel] = []

        # Trade state
        self.is_long_trade: bool = False
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp1_price: float = 0.0
        self.tp1_filled: bool = False
        self.be_activated: bool = False
        self.best_price: float = math.nan
        self.trail_stop: float = math.nan
        self.trailing_active: bool = False
        self.initial_qty: int = 0

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("SwingReclaim Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("SwingReclaim Strategy stopped")

    # ==================== Core Logic ====================

    def on_bar(self, bar: Bar):
        self.bar_count += 1
        cfg = self.config

        h = bar.high.as_double()
        l = bar.low.as_double()
        c = bar.close.as_double()

        # Maintain rolling history
        self.hist_highs.append(h)
        self.hist_lows.append(l)
        self.hist_closes.append(c)
        if len(self.hist_highs) > self.max_hist:
            self.hist_highs.pop(0)
            self.hist_lows.pop(0)
            self.hist_closes.pop(0)

        # Need warmup for pivot detection
        if self.bar_count < cfg.strength * 2 + 1:
            return

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

        # ===== Detect new swing points (with lag replay) =====
        self._detect_swing_points()

        # ===== Run state machine on all levels for current bar =====
        # Clears pending_reclaims, then populates it with any reclaims on this bar
        self.pending_reclaims.clear()
        self._run_state_machine(h, l, c, self.bar_count, live=True)

        # ===== EOD flatten =====
        if cfg.eod_enabled and bar_time_int >= cfg.eod_time and not self.eod_processed:
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
            position = self._get_open_position()
            if position is None and self.entry_price > 0:
                self._reset_trade_state()
            return  # Don't enter while in position

        if self.entry_price > 0:
            self._reset_trade_state()

        # ===== Entry conditions =====
        if self.vix_blocked:
            return

        if cfg.session_enabled:
            if not (cfg.session_start <= bar_time_int < cfg.session_end):
                return

        if self.trades_today >= cfg.max_trades_day:
            return

        if cfg.eod_enabled and bar_time_int >= cfg.eod_time:
            return

        # ===== Fire entry from pending reclaims =====
        if self.pending_reclaims:
            # Take the last reclaim (most recent)
            lv = self.pending_reclaims[-1]
            if lv.is_high and cfg.enable_short:
                self._enter_trade(False, c, lv.sweep_extreme, lv.price)
            elif not lv.is_high and cfg.enable_long:
                self._enter_trade(True, c, lv.sweep_extreme, lv.price)

        # ===== Prune dead levels periodically =====
        if self.bar_count % 100 == 0:
            self.swing_levels = [
                lv for lv in self.swing_levels
                if not lv.canceled and not lv.traded
            ][-200:]

    # ==================== State Machine ====================

    def _run_state_machine(self, h: float, l: float, c: float,
                           abs_bar: int, live: bool = False):
        """Run state machine on all levels for one bar.

        If live=True, reclaims are added to pending_reclaims for entry.
        If live=False (replay), reclaims just mark the level as traded.
        """
        cfg = self.config

        for lv in self.swing_levels:
            if lv.traded or lv.canceled:
                continue

            # Expire reclaim window
            if lv.state == STATE_BROKEN and lv.broke_bar >= 0:
                if (abs_bar - lv.broke_bar) > cfg.reclaim_window:
                    lv.canceled = True
                    continue

            if lv.is_high:
                if lv.state == STATE_ACTIVE and c > lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = h
                elif lv.state == STATE_BROKEN:
                    if h > lv.sweep_extreme:
                        lv.sweep_extreme = h
                    if c < lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar
                        if live:
                            self.pending_reclaims.append(lv)
            else:
                if lv.state == STATE_ACTIVE and c < lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = l
                elif lv.state == STATE_BROKEN:
                    if l < lv.sweep_extreme:
                        lv.sweep_extreme = l
                    if c > lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar
                        if live:
                            self.pending_reclaims.append(lv)

    # ==================== Swing Point Detection ====================

    def _detect_swing_points(self):
        """Detect pivot highs and lows with left=right=strength bars.

        Uses absolute bar_count for tracking so the rolling window
        truncation doesn't break the guard check. After detecting a
        new level, retroactively replays the lag window through the
        state machine.
        """
        cfg = self.config
        strength = cfg.strength
        n = len(self.hist_highs)

        if n < 2 * strength + 1:
            return

        # The pivot candidate is strength bars before the end of the buffer.
        # In absolute terms it corresponds to bar_count - strength.
        candidate_bar = self.bar_count - strength

        # Already checked this bar?
        if candidate_bar <= self.last_checked_pivot_bar:
            return
        self.last_checked_pivot_bar = candidate_bar

        # Array index of the candidate within the rolling buffer
        check_idx = n - 1 - strength

        # Check pivot high: high[check_idx] >= all highs in window
        h_val = self.hist_highs[check_idx]
        is_pivot_high = True
        for j in range(check_idx - strength, check_idx + strength + 1):
            if j == check_idx:
                continue
            if self.hist_highs[j] > h_val:
                is_pivot_high = False
                break

        if is_pivot_high:
            lv = SwingLevel(price=h_val, is_high=True, detected_bar=candidate_bar)
            self.swing_levels.append(lv)
            self._replay_lag(lv, strength)

        # Check pivot low: low[check_idx] <= all lows in window
        l_val = self.hist_lows[check_idx]
        is_pivot_low = True
        for j in range(check_idx - strength, check_idx + strength + 1):
            if j == check_idx:
                continue
            if self.hist_lows[j] < l_val:
                is_pivot_low = False
                break

        if is_pivot_low:
            lv = SwingLevel(price=l_val, is_high=False, detected_bar=candidate_bar)
            self.swing_levels.append(lv)
            self._replay_lag(lv, strength)

    def _replay_lag(self, lv: SwingLevel, lag_bars: int):
        """Retroactively process the lag window for a newly detected level.

        The pivot was at bar (bar_count - lag_bars) but we just detected it now.
        Run the state machine on bars [detected+1 .. current-1] so the level's
        state is caught up. The current bar will be processed by on_bar's
        _run_state_machine call (live=True).
        """
        cfg = self.config
        n = len(self.hist_highs)

        # Replay from 1 bar after pivot through 1 bar before current
        # Array indices: (check_idx+1) to (n-2). Current bar (n-1) handled live.
        start_idx = n - lag_bars  # = check_idx + 1
        end_idx = n - 1  # exclusive

        for i in range(max(0, start_idx), end_idx):
            if lv.traded or lv.canceled:
                break

            h = self.hist_highs[i]
            l_bar = self.hist_lows[i]
            c = self.hist_closes[i]
            abs_bar = self.bar_count - (n - 1 - i)

            # Expire reclaim window
            if lv.state == STATE_BROKEN and lv.broke_bar >= 0:
                if (abs_bar - lv.broke_bar) > cfg.reclaim_window:
                    lv.canceled = True
                    break

            if lv.is_high:
                if lv.state == STATE_ACTIVE and c > lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = h
                elif lv.state == STATE_BROKEN:
                    if h > lv.sweep_extreme:
                        lv.sweep_extreme = h
                    if c < lv.price:
                        # Reclaimed during lag — missed opportunity
                        lv.traded = True
                        lv.reclaim_bar = abs_bar
            else:
                if lv.state == STATE_ACTIVE and c < lv.price:
                    lv.state = STATE_BROKEN
                    lv.broke_bar = abs_bar
                    lv.sweep_extreme = l_bar
                elif lv.state == STATE_BROKEN:
                    if l_bar < lv.sweep_extreme:
                        lv.sweep_extreme = l_bar
                    if c > lv.price:
                        lv.traded = True
                        lv.reclaim_bar = abs_bar

    # ==================== Enter Trade ====================

    def _enter_trade(self, is_long: bool, close: float,
                     sweep_extreme: float, level_price: float):
        cfg = self.config
        tick_size = 0.01
        stop_buffer = cfg.stop_buffer_ticks * tick_size

        # Stop from sweep extreme
        if is_long:
            stop = sweep_extreme - stop_buffer
            tp1 = close + cfg.tp1_points
        else:
            stop = sweep_extreme + stop_buffer
            tp1 = close - cfg.tp1_points

        # Clamp stop distance
        dist = abs(close - stop)
        if dist < cfg.stop_min_pts:
            stop = (close - cfg.stop_min_pts) if is_long else (close + cfg.stop_min_pts)
        if dist > cfg.stop_max_pts:
            stop = (close - cfg.stop_max_pts) if is_long else (close + cfg.stop_max_pts)

        num_contracts = self._compute_contracts()
        qty = Quantity.from_int(num_contracts)
        side = OrderSide.BUY if is_long else OrderSide.SELL

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        self.is_long_trade = is_long
        self.entry_price = close
        self.stop_price = stop
        self.tp1_price = tp1
        self.tp1_filled = False
        self.be_activated = False
        self.best_price = close
        self.trail_stop = math.nan
        self.trailing_active = False
        self.initial_qty = num_contracts
        self.trades_today += 1

        direction = "LONG" if is_long else "SHORT"
        self.log.info(
            f"{direction}: qty={num_contracts}, entry={close:.2f}, "
            f"stop={stop:.2f}, TP1={tp1:.2f}, "
            f"sweep={sweep_extreme:.2f}, level={level_price:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float,
                         close: float):
        cfg = self.config
        is_long = position.is_long

        # Track best price
        if is_long:
            if math.isnan(self.best_price) or high > self.best_price:
                self.best_price = high
        else:
            if math.isnan(self.best_price) or low < self.best_price:
                self.best_price = low

        # Effective stop (include trail if active)
        effective_stop = self.stop_price
        if not math.isnan(self.trail_stop) and self.trailing_active:
            if is_long:
                effective_stop = max(effective_stop, self.trail_stop)
            else:
                effective_stop = min(effective_stop, self.trail_stop)

        # Stop loss check
        if is_long and low <= effective_stop:
            self.close_position(position)
            self.log.info(f"LONG stopped at {effective_stop:.2f}")
            self._reset_trade_state()
            return
        if not is_long and high >= effective_stop:
            self.close_position(position)
            self.log.info(f"SHORT stopped at {effective_stop:.2f}")
            self._reset_trade_state()
            return

        # Breakeven
        if cfg.be_enabled and not self.be_activated:
            profit = (self.best_price - self.entry_price) if is_long else (self.entry_price - self.best_price)
            if profit >= cfg.be_trigger_pts:
                self.stop_price = self.entry_price
                self.be_activated = True
                self.log.info(f"BE triggered at profit={profit:.1f}pts")

        # TP1 Partial
        if not self.tp1_filled:
            tp1_hit = (is_long and high >= self.tp1_price) or (not is_long and low <= self.tp1_price)
            if tp1_hit:
                current_qty = int(position.quantity.as_double())
                partial_qty = max(1, int(math.ceil(self.initial_qty * cfg.tp1_pct / 100.0)))
                if partial_qty > 0 and partial_qty < current_qty:
                    close_side = OrderSide.SELL if is_long else OrderSide.BUY
                    sell_order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=close_side,
                        quantity=Quantity.from_int(partial_qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sell_order)
                    self.tp1_filled = True
                    self.log.info(
                        f"TP1: closed {partial_qty} of {current_qty} at {self.tp1_price:.2f}"
                    )
                else:
                    # Close all at TP1
                    self.close_position(position)
                    self.log.info(f"Full exit at TP1={self.tp1_price:.2f}")
                    self._reset_trade_state()
                    return

        # Runner trailing stop (activate after TP1)
        if self.tp1_filled and not self.trailing_active:
            self.trailing_active = True
            if is_long:
                self.trail_stop = self.best_price - cfg.trail_points
            else:
                self.trail_stop = self.best_price + cfg.trail_points

        if self.trailing_active:
            if is_long:
                new_trail = self.best_price - cfg.trail_points
                if math.isnan(self.trail_stop) or new_trail > self.trail_stop:
                    self.trail_stop = new_trail
            else:
                new_trail = self.best_price + cfg.trail_points
                if math.isnan(self.trail_stop) or new_trail < self.trail_stop:
                    self.trail_stop = new_trail

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
        self.is_long_trade = False
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.tp1_price = 0.0
        self.tp1_filled = False
        self.be_activated = False
        self.best_price = math.nan
        self.trail_stop = math.nan
        self.trailing_active = False
        self.initial_qty = 0
