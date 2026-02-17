"""
ICT Setup Selector (JadeCap) Strategy — NautilusTrader port.

Ported from ICTSetupSelectorStrategy.java v2.0 (MotiveWave SDK).
Dual MMBM/MMSM state machines with liquidity sweep -> MSS -> FVG -> entry.
Supports deeper liquidity (PWL/PWH, Major Swing), multiple exit models.

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

# ==================== Constants ====================

# State machine phases
STATE_IDLE = 0
STATE_SWEEP_DETECTED = 1
STATE_MSS_PENDING = 2
STATE_ENTRY_READY = 3
STATE_IN_TRADE = 4

# Entry models
ENTRY_IMMEDIATE = 0
ENTRY_FVG_ONLY = 1
ENTRY_BOTH = 2
ENTRY_MSS_MARKET = 3

# Exit models
EXIT_RR = 0
EXIT_TP1_TP2 = 1
EXIT_SCALE_TRAIL = 2
EXIT_TIME_MIDDAY = 3

# Stop modes
STOP_FIXED = 0
STOP_STRUCTURAL = 1

# Confirmation strictness
STRICT_AGGRESSIVE = 0
STRICT_BALANCED = 1
STRICT_CONSERVATIVE = 2

# Kill zone presets
KZ_NY_AM = 0
KZ_NY_PM = 1
KZ_LONDON_AM = 2
KZ_CUSTOM = 3

# Liquidity references
LIQ_REF_PREV_DAY = 0
LIQ_REF_SESSION = 1
LIQ_REF_CUSTOM = 2


# ==================== Config ====================

class JadeCapConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Setup mode: 0=Single, 1=Both MMBM+MMSM
    setup_mode: int = 1               # saved: 1
    enable_long: bool = True
    enable_short: bool = True

    # Session
    trade_window_always_on: bool = True   # saved: true
    trade_start: int = 1800               # saved: 1800
    trade_end: int = 1230                 # saved: 1230
    kill_zone_preset: int = 3             # saved: 3 (Custom)
    kz_custom_start: int = 100            # saved: 100
    kz_custom_end: int = 1130             # saved: 1130

    # EOD
    eod_close_enabled: bool = True
    eod_close_time: int = 1640

    # Limits
    max_trades_per_day: int = 1           # saved: 1
    max_trades_per_side: int = 1          # saved: 1
    one_trade_at_a_time: bool = True      # saved: true
    allow_opposite_side: bool = True      # saved: true

    # Sizing
    contracts: int = 10                   # saved: 10
    dollars_per_contract: float = 0.0

    # Liquidity
    mmbm_ssl_ref: int = 0                # saved: 0 (PDL)
    mmsm_bsl_ref: int = 0                # saved: 0 (PDH)
    liq_session_start: int = 2000         # saved: 2000
    liq_session_end: int = 0              # saved: 0
    mmbm_pwl_enabled: bool = False        # saved: false
    mmbm_major_swing_enabled: bool = True # saved: true
    mmsm_pwh_enabled: bool = True         # saved: true
    mmsm_major_swing_high_enabled: bool = True  # saved: true
    major_swing_lookback: int = 500       # saved: 500
    require_deeper_liq: bool = True       # saved: true
    sweep_min_ticks: int = 2              # saved: 2
    require_close_back: bool = True       # saved: true

    # Structure
    pivot_strength: int = 10              # saved: 10

    # Entry
    entry_model: int = 1                  # saved: 1 (FVG Only)
    fvg_min_ticks: int = 2                # saved: 2
    max_bars_to_fill: int = 30            # saved: 30
    confirmation_strictness: int = 0      # saved: 0 (Aggressive)
    require_mss_close: bool = True        # saved: true

    # Risk
    stoploss_enabled: bool = True
    stoploss_mode: int = 0                # saved: 0 (Fixed)
    stoploss_ticks: int = 40              # saved: 40

    # Exits
    exit_model: int = 2                   # saved: 2 (Scale+Trail)
    rr_multiple: float = 3.0             # saved: 3.0
    partial_enabled: bool = True
    partial_pct: int = 25                 # saved: 25
    midday_exit_enabled: bool = False     # saved: false
    midday_exit_time: int = 1215

    # VIX
    vix_filter_enabled: bool = False
    vix_off: float = 30.0
    vix_on: float = 20.0

    # EMA directional filter
    ema_filter_enabled: bool = False
    ema_period: int = 50

    # Realized vol ceiling filter
    vol_ceiling_enabled: bool = False
    vol_ceiling_pct: float = 20.0
    vol_lookback_days: int = 20


# ==================== Strategy ====================

class JadeCapStrategy(Strategy):

    def __init__(self, config: JadeCapConfig, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type
        self.tick_size = 0.25  # ES tick size (must match MotiveWave instrument)

        # VIX filter
        self.vix_lookup = vix_lookup or {}
        self.vix_blocked: bool = False

        # EMA filter state
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Vol ceiling filter state
        self.daily_closes: list[float] = []
        self.current_day_close: float = math.nan
        self.realized_vol: float = math.nan
        self.vol_blocked: bool = False

        # Bar history
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.max_hist = max(600, config.major_swing_lookback + 50)

        # Daily levels
        self.pdh: float = math.nan
        self.pdl: float = math.nan
        self.today_high: float = math.nan
        self.today_low: float = math.nan
        self.last_reset_day: int = -1

        # Weekly levels
        self.pwh: float = math.nan
        self.pwl: float = math.nan
        self.this_week_high: float = math.nan
        self.this_week_low: float = math.nan
        self.last_reset_week: int = -1

        # Major swing levels
        self.major_swing_high: float = math.nan
        self.major_swing_low: float = math.nan

        # Session liquidity
        self.session_high: float = math.nan
        self.session_low: float = math.nan
        self.in_liq_session: bool = False

        # MMBM state (long setup)
        self.mmbm_state: int = STATE_IDLE
        self.mmbm_ssl_level: float = math.nan
        self.mmbm_sweep_low: float = math.nan
        self.mmbm_mss_level: float = math.nan
        self.mmbm_sweep_strength: int = 0
        self.mmbm_fvg_detected: bool = False
        self.mmbm_entry_bar: int = -1

        # MMSM state (short setup)
        self.mmsm_state: int = STATE_IDLE
        self.mmsm_bsl_level: float = math.nan
        self.mmsm_sweep_high: float = math.nan
        self.mmsm_mss_level: float = math.nan
        self.mmsm_sweep_strength: int = 0
        self.mmsm_fvg_detected: bool = False
        self.mmsm_entry_bar: int = -1

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.tp1_price: float = 0.0
        self.tp2_price: float = 0.0
        self.partial_taken: bool = False
        self.current_direction: int = 0  # 1=long, -1=short, 0=flat
        self.initial_qty: int = 0

        # Daily tracking
        self.bar_count: int = 0
        self.trades_today: int = 0
        self.long_trades_today: int = 0
        self.short_trades_today: int = 0
        self.eod_processed: bool = False

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("JadeCap Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("JadeCap Strategy stopped")

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

        # Update EMA every bar (before warmup)
        self._update_ema(c)

        # Track current day close for realized vol
        self.current_day_close = c

        # Warmup
        if self.bar_count < 20:
            return

        # Bar time in ET
        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000
        bar_week = bar_dt.isocalendar()[1] + bar_dt.year * 100

        # ===== Weekly reset =====
        if bar_week != self.last_reset_week:
            if not math.isnan(self.this_week_high) and not math.isnan(self.this_week_low):
                self.pwh = self.this_week_high
                self.pwl = self.this_week_low
            self.this_week_high = math.nan
            self.this_week_low = math.nan
            self.last_reset_week = bar_week

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
            if not math.isnan(self.today_high) and not math.isnan(self.today_low):
                self.pdh = self.today_high
                self.pdl = self.today_low
            self.today_high = math.nan
            self.today_low = math.nan
            self.session_high = math.nan
            self.session_low = math.nan
            self._reset_daily_state()
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

            # Realized vol ceiling filter — capture prev day close, compute vol
            if cfg.vol_ceiling_enabled and not math.isnan(self.current_day_close):
                self.daily_closes.append(self.current_day_close)
                if len(self.daily_closes) > cfg.vol_lookback_days + 5:
                    self.daily_closes = self.daily_closes[-(cfg.vol_lookback_days + 5):]
                self.realized_vol = self._compute_realized_vol()
                if not math.isnan(self.realized_vol):
                    was_blocked = self.vol_blocked
                    self.vol_blocked = self.realized_vol > cfg.vol_ceiling_pct
                    if self.vol_blocked and not was_blocked:
                        self.log.info(f"Vol ceiling ON: realized={self.realized_vol:.1f}% > {cfg.vol_ceiling_pct}%")
                    elif not self.vol_blocked and was_blocked:
                        self.log.info(f"Vol ceiling OFF: realized={self.realized_vol:.1f}% <= {cfg.vol_ceiling_pct}%")

        # Track today's high/low
        if math.isnan(self.today_high) or h > self.today_high:
            self.today_high = h
        if math.isnan(self.today_low) or l < self.today_low:
            self.today_low = l

        # Track this week's high/low
        if math.isnan(self.this_week_high) or h > self.this_week_high:
            self.this_week_high = h
        if math.isnan(self.this_week_low) or l < self.this_week_low:
            self.this_week_low = l

        # Track liquidity session
        self._update_liq_session(bar_time_int, h, l)

        # Need PDH/PDL to proceed
        if math.isnan(self.pdh) or math.isnan(self.pdl):
            return

        # Compute major swing levels
        n = len(self.hist_lows)
        htf_strength = 5
        if cfg.mmbm_major_swing_enabled and n > cfg.major_swing_lookback:
            self.major_swing_low = self._find_major_swing_low(htf_strength, cfg.major_swing_lookback)
        if cfg.mmsm_major_swing_high_enabled and n > cfg.major_swing_lookback:
            self.major_swing_high = self._find_major_swing_high(htf_strength, cfg.major_swing_lookback)

        # Resolve SSL/BSL levels
        self.mmbm_ssl_level = self._resolve_ssl_level()
        self.mmsm_bsl_level = self._resolve_bsl_level()

        # ===== EOD flatten =====
        if cfg.eod_close_enabled and bar_time_int >= cfg.eod_close_time and not self.eod_processed:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"EOD flatten at {bar_time_int}")
                self._reset_trade_state()
            self._reset_mmbm_state()
            self._reset_mmsm_state()
            self.eod_processed = True
            return

        # ===== Midday exit =====
        if cfg.midday_exit_enabled and cfg.exit_model == EXIT_TIME_MIDDAY and bar_time_int >= cfg.midday_exit_time:
            position = self._get_open_position()
            if position is not None:
                self.close_position(position)
                self.log.info(f"Midday exit at {bar_time_int}")
                self._reset_trade_state()
                return

        # ===== Trade management =====
        position = self._get_open_position()
        if position is not None:
            self._manage_position(position, h, l, c)
            position = self._get_open_position()
            if position is None and self.entry_price > 0:
                self._reset_trade_state()
            # Don't evaluate new entries while in position (unless allow_opposite)
            if position is not None and cfg.one_trade_at_a_time and not cfg.allow_opposite_side:
                return
        elif self.entry_price > 0:
            self._reset_trade_state()

        # VIX block
        if self.vix_blocked:
            return

        # Realized vol ceiling block
        if self.vol_blocked:
            return

        # Past EOD cutoff — no new entries
        if cfg.eod_close_enabled and bar_time_int >= cfg.eod_close_time:
            return

        # Session/KZ checks (bypass if always_on)
        if cfg.trade_window_always_on:
            in_trade_session = True
        elif cfg.trade_start > cfg.trade_end:
            # Overnight window (e.g. 1800–1230)
            in_trade_session = bar_time_int >= cfg.trade_start or bar_time_int < cfg.trade_end
        else:
            in_trade_session = cfg.trade_start <= bar_time_int < cfg.trade_end

        in_kill_zone = cfg.trade_window_always_on or self._is_in_kill_zone(bar_time_int)

        base_can_trade = in_trade_session and in_kill_zone and self.trades_today < cfg.max_trades_per_day

        # Per-side limits
        can_trade_long = base_can_trade and self.long_trades_today < cfg.max_trades_per_side and cfg.enable_long
        can_trade_short = base_can_trade and self.short_trades_today < cfg.max_trades_per_side and cfg.enable_short

        # One-at-a-time constraint
        if cfg.one_trade_at_a_time and self.current_direction != 0:
            if not cfg.allow_opposite_side:
                can_trade_long = False
                can_trade_short = False
            else:
                if self.current_direction > 0:
                    can_trade_long = False
                if self.current_direction < 0:
                    can_trade_short = False

        # EMA directional filter: longs need close > EMA, shorts need close < EMA
        if cfg.ema_filter_enabled and not math.isnan(self.ema_value):
            if c <= self.ema_value:
                can_trade_long = False
            if c >= self.ema_value:
                can_trade_short = False

        # Which setups to evaluate
        eval_mmbm = (cfg.setup_mode == 1) or cfg.enable_long
        eval_mmsm = (cfg.setup_mode == 1) or cfg.enable_short

        # Process MMBM (long setup)
        entered_long = False
        if eval_mmbm:
            entry = self._process_mmbm(h, l, c, o, can_trade_long)
            if entry:
                self._enter_long(c)
                entered_long = True

        # Process MMSM (short setup) — recheck eligibility if long was entered
        if eval_mmsm:
            if entered_long:
                can_trade_short = (self.trades_today < cfg.max_trades_per_day and
                                   self.short_trades_today < cfg.max_trades_per_side and
                                   cfg.enable_short)
                if cfg.one_trade_at_a_time and not cfg.allow_opposite_side:
                    can_trade_short = False
            entry = self._process_mmsm(h, l, c, o, can_trade_short)
            if entry:
                self._enter_short(c)

        # Max bars to fill cancellation
        if self.mmbm_state == STATE_ENTRY_READY and self.mmbm_entry_bar > 0:
            if self.bar_count - self.mmbm_entry_bar > cfg.max_bars_to_fill:
                self._reset_mmbm_state()
        if self.mmsm_state == STATE_ENTRY_READY and self.mmsm_entry_bar > 0:
            if self.bar_count - self.mmsm_entry_bar > cfg.max_bars_to_fill:
                self._reset_mmsm_state()

    # ==================== MMBM Processing ====================

    def _process_mmbm(self, h, l, c, o, can_trade) -> bool:
        """Process MMBM (long) state machine. Returns True if entry should fire."""
        cfg = self.config
        tick = self.tick_size

        # Phase 1: Detect SSL sweep
        if self.mmbm_state == STATE_IDLE and can_trade and not math.isnan(self.mmbm_ssl_level):
            sweep_threshold = self.mmbm_ssl_level - (cfg.sweep_min_ticks * tick)
            if l <= sweep_threshold:
                valid_sweep = not cfg.require_close_back or (c > self.mmbm_ssl_level)
                if cfg.confirmation_strictness == STRICT_AGGRESSIVE:
                    valid_sweep = True

                if valid_sweep:
                    self.mmbm_sweep_strength = 1  # PDL

                    # Check PWL (deeper)
                    if cfg.mmbm_pwl_enabled and not math.isnan(self.pwl):
                        if l <= self.pwl - (cfg.sweep_min_ticks * tick):
                            self.mmbm_sweep_strength = 2

                    # Check Major Swing Low (deepest)
                    if cfg.mmbm_major_swing_enabled and not math.isnan(self.major_swing_low):
                        if l <= self.major_swing_low - (cfg.sweep_min_ticks * tick):
                            self.mmbm_sweep_strength = 3

                    # Require deeper liq
                    if cfg.require_deeper_liq and self.mmbm_sweep_strength == 1:
                        return False

                    self.mmbm_sweep_low = l
                    self.mmbm_state = STATE_SWEEP_DETECTED
                    self.mmbm_mss_level = self._find_swing_high(cfg.pivot_strength)
                    strength_label = {3: "MAJOR SWING LOW", 2: "PWL", 1: "PDL"}.get(self.mmbm_sweep_strength, "")
                    self.log.info(f"MMBM: {strength_label} sweep at {l:.2f} (strength={self.mmbm_sweep_strength})")

        # Update sweep extreme
        if self.mmbm_state == STATE_SWEEP_DETECTED and l < self.mmbm_sweep_low:
            self.mmbm_sweep_low = l

        # Phase 2: Detect MSS Up
        if self.mmbm_state == STATE_SWEEP_DETECTED and not math.isnan(self.mmbm_mss_level):
            mss_break = (c > self.mmbm_mss_level) if cfg.require_mss_close else (h > self.mmbm_mss_level)
            if mss_break:
                disp_ticks = self._get_displacement_ticks()
                body_size = abs(c - o)
                if body_size >= disp_ticks * tick or cfg.confirmation_strictness == STRICT_AGGRESSIVE:
                    self.mmbm_state = STATE_MSS_PENDING
                    self.log.info(f"MMBM: MSS Up at {c:.2f} (mss_level={self.mmbm_mss_level:.2f})")

                    if cfg.entry_model in (ENTRY_IMMEDIATE, ENTRY_MSS_MARKET):
                        self.mmbm_state = STATE_ENTRY_READY
                        self.mmbm_entry_bar = self.bar_count

        # Phase 3: Detect Bullish FVG
        n = len(self.hist_highs)
        if (self.mmbm_state in (STATE_MSS_PENDING, STATE_SWEEP_DETECTED) and
                n >= 3 and cfg.entry_model in (ENTRY_FVG_ONLY, ENTRY_BOTH)):
            bar0_high = self.hist_highs[-3]  # 2 bars ago
            bar2_low = l                     # current bar
            if bar2_low > bar0_high and (bar2_low - bar0_high) >= cfg.fvg_min_ticks * tick:
                self.mmbm_fvg_detected = True
                self.mmbm_state = STATE_ENTRY_READY
                self.mmbm_entry_bar = self.bar_count
                self.log.info(f"MMBM: Bullish FVG: {bar0_high:.2f} - {bar2_low:.2f}")

        # Phase 4: Entry
        if self.mmbm_state == STATE_ENTRY_READY and can_trade:
            return True

        return False

    # ==================== MMSM Processing ====================

    def _process_mmsm(self, h, l, c, o, can_trade) -> bool:
        """Process MMSM (short) state machine. Returns True if entry should fire."""
        cfg = self.config
        tick = self.tick_size

        # Phase 1: Detect BSL sweep
        if self.mmsm_state == STATE_IDLE and can_trade and not math.isnan(self.mmsm_bsl_level):
            sweep_threshold = self.mmsm_bsl_level + (cfg.sweep_min_ticks * tick)
            if h >= sweep_threshold:
                valid_sweep = not cfg.require_close_back or (c < self.mmsm_bsl_level)
                if cfg.confirmation_strictness == STRICT_AGGRESSIVE:
                    valid_sweep = True

                if valid_sweep:
                    self.mmsm_sweep_strength = 1  # PDH

                    # Check PWH (deeper)
                    if cfg.mmsm_pwh_enabled and not math.isnan(self.pwh):
                        if h >= self.pwh + (cfg.sweep_min_ticks * tick):
                            self.mmsm_sweep_strength = 2

                    # Check Major Swing High (deepest)
                    if cfg.mmsm_major_swing_high_enabled and not math.isnan(self.major_swing_high):
                        if h >= self.major_swing_high + (cfg.sweep_min_ticks * tick):
                            self.mmsm_sweep_strength = 3

                    # Require deeper liq
                    if cfg.require_deeper_liq and self.mmsm_sweep_strength == 1:
                        return False

                    self.mmsm_sweep_high = h
                    self.mmsm_state = STATE_SWEEP_DETECTED
                    self.mmsm_mss_level = self._find_swing_low(cfg.pivot_strength)
                    strength_label = {3: "MAJOR SWING HIGH", 2: "PWH", 1: "PDH"}.get(self.mmsm_sweep_strength, "")
                    self.log.info(f"MMSM: {strength_label} sweep at {h:.2f} (strength={self.mmsm_sweep_strength})")

        # Update sweep extreme
        if self.mmsm_state == STATE_SWEEP_DETECTED and h > self.mmsm_sweep_high:
            self.mmsm_sweep_high = h

        # Phase 2: Detect MSS Down
        if self.mmsm_state == STATE_SWEEP_DETECTED and not math.isnan(self.mmsm_mss_level):
            mss_break = (c < self.mmsm_mss_level) if cfg.require_mss_close else (l < self.mmsm_mss_level)
            if mss_break:
                disp_ticks = self._get_displacement_ticks()
                body_size = abs(c - o)
                if body_size >= disp_ticks * tick or cfg.confirmation_strictness == STRICT_AGGRESSIVE:
                    self.mmsm_state = STATE_MSS_PENDING
                    self.log.info(f"MMSM: MSS Down at {c:.2f} (mss_level={self.mmsm_mss_level:.2f})")

                    if cfg.entry_model in (ENTRY_IMMEDIATE, ENTRY_MSS_MARKET):
                        self.mmsm_state = STATE_ENTRY_READY
                        self.mmsm_entry_bar = self.bar_count

        # Phase 3: Detect Bearish FVG
        n = len(self.hist_lows)
        if (self.mmsm_state in (STATE_MSS_PENDING, STATE_SWEEP_DETECTED) and
                n >= 3 and cfg.entry_model in (ENTRY_FVG_ONLY, ENTRY_BOTH)):
            bar0_low = self.hist_lows[-3]  # 2 bars ago
            bar2_high = h                  # current bar
            if bar2_high < bar0_low and (bar0_low - bar2_high) >= cfg.fvg_min_ticks * tick:
                self.mmsm_fvg_detected = True
                self.mmsm_state = STATE_ENTRY_READY
                self.mmsm_entry_bar = self.bar_count
                self.log.info(f"MMSM: Bearish FVG: {bar2_high:.2f} - {bar0_low:.2f}")

        # Phase 4: Entry
        if self.mmsm_state == STATE_ENTRY_READY and can_trade:
            return True

        return False

    # ==================== Entry ====================

    def _enter_long(self, close):
        cfg = self.config
        tick = self.tick_size

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
        self.current_direction = 1
        self.initial_qty = num_contracts

        # Stop
        if cfg.stoploss_enabled:
            stop_buffer = cfg.stoploss_ticks * tick
            if cfg.stoploss_mode == STOP_STRUCTURAL and not math.isnan(self.mmbm_sweep_low):
                self.stop_price = self.mmbm_sweep_low - stop_buffer
            else:
                self.stop_price = close - stop_buffer

        # Targets
        risk = abs(close - self.stop_price) if self.stop_price > 0 else cfg.stoploss_ticks * tick
        equilibrium = (self.pdh + self.pdl) / 2.0
        self.tp1_price = equilibrium

        if cfg.exit_model == EXIT_RR:
            self.tp2_price = close + (risk * cfg.rr_multiple)
        else:
            self.tp2_price = self.pdh

        self.partial_taken = False
        self.trades_today += 1
        self.long_trades_today += 1
        self.mmbm_state = STATE_IN_TRADE

        strength_label = {3: "MAJOR", 2: "PWL", 1: "PDL"}.get(self.mmbm_sweep_strength, "")
        self.log.info(
            f"LONG [{strength_label}]: qty={num_contracts}, entry={close:.2f}, "
            f"stop={self.stop_price:.2f}, TP1={self.tp1_price:.2f}, TP2={self.tp2_price:.2f}"
        )

    def _enter_short(self, close):
        cfg = self.config
        tick = self.tick_size

        num_contracts = self._compute_contracts()
        qty = Quantity.from_int(num_contracts)

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        self.entry_price = close
        self.current_direction = -1
        self.initial_qty = num_contracts

        # Stop
        if cfg.stoploss_enabled:
            stop_buffer = cfg.stoploss_ticks * tick
            if cfg.stoploss_mode == STOP_STRUCTURAL and not math.isnan(self.mmsm_sweep_high):
                self.stop_price = self.mmsm_sweep_high + stop_buffer
            else:
                self.stop_price = close + stop_buffer

        # Targets
        risk = abs(self.stop_price - close) if self.stop_price > 0 else cfg.stoploss_ticks * tick
        equilibrium = (self.pdh + self.pdl) / 2.0
        self.tp1_price = equilibrium

        if cfg.exit_model == EXIT_RR:
            self.tp2_price = close - (risk * cfg.rr_multiple)
        else:
            self.tp2_price = self.pdl

        self.partial_taken = False
        self.trades_today += 1
        self.short_trades_today += 1
        self.mmsm_state = STATE_IN_TRADE

        strength_label = {3: "MAJOR", 2: "PWH", 1: "PDH"}.get(self.mmsm_sweep_strength, "")
        self.log.info(
            f"SHORT [{strength_label}]: qty={num_contracts}, entry={close:.2f}, "
            f"stop={self.stop_price:.2f}, TP1={self.tp1_price:.2f}, TP2={self.tp2_price:.2f}"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high, low, close):
        cfg = self.config

        if self.current_direction > 0:  # Long
            # Stop
            if cfg.stoploss_enabled and self.stop_price > 0 and low <= self.stop_price:
                self.close_position(position)
                stop_type = "BE" if self.partial_taken and cfg.exit_model == EXIT_SCALE_TRAIL else "STOP"
                self.log.info(f"LONG {stop_type} at {self.stop_price:.2f}")
                self._reset_trade_state()
                return

            # Partial TP1
            if cfg.partial_enabled and not self.partial_taken and high >= self.tp1_price:
                current_qty = int(position.quantity.as_double())
                partial_qty = max(1, int(math.ceil(current_qty * cfg.partial_pct / 100.0)))
                if partial_qty > 0 and partial_qty < current_qty:
                    sell_order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity.from_int(partial_qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sell_order)
                    self.log.info(f"Partial: sold {partial_qty}/{current_qty} at TP1={self.tp1_price:.2f}")

                    if cfg.exit_model == EXIT_SCALE_TRAIL:
                        self.stop_price = self.entry_price
                        self.log.info("Stop moved to breakeven")
                self.partial_taken = True

            # TP2
            if high >= self.tp2_price and self.tp2_price > 0:
                self.close_position(position)
                self.log.info(f"LONG TP2 hit at {self.tp2_price:.2f}")
                self._reset_trade_state()
                return

        elif self.current_direction < 0:  # Short
            # Stop
            if cfg.stoploss_enabled and self.stop_price > 0 and high >= self.stop_price:
                self.close_position(position)
                stop_type = "BE" if self.partial_taken and cfg.exit_model == EXIT_SCALE_TRAIL else "STOP"
                self.log.info(f"SHORT {stop_type} at {self.stop_price:.2f}")
                self._reset_trade_state()
                return

            # Partial TP1
            if cfg.partial_enabled and not self.partial_taken and low <= self.tp1_price:
                current_qty = int(position.quantity.as_double())
                partial_qty = max(1, int(math.ceil(current_qty * cfg.partial_pct / 100.0)))
                if partial_qty > 0 and partial_qty < current_qty:
                    buy_order = self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity.from_int(partial_qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(buy_order)
                    self.log.info(f"Partial: cover {partial_qty}/{current_qty} at TP1={self.tp1_price:.2f}")

                    if cfg.exit_model == EXIT_SCALE_TRAIL:
                        self.stop_price = self.entry_price
                        self.log.info("Stop moved to breakeven")
                self.partial_taken = True

            # TP2
            if low <= self.tp2_price and self.tp2_price > 0:
                self.close_position(position)
                self.log.info(f"SHORT TP2 hit at {self.tp2_price:.2f}")
                self._reset_trade_state()
                return

    # ==================== Liquidity Helpers ====================

    def _resolve_ssl_level(self) -> float:
        cfg = self.config
        if cfg.mmbm_ssl_ref == LIQ_REF_SESSION:
            return self.session_low if not math.isnan(self.session_low) else self.pdl
        return self.pdl

    def _resolve_bsl_level(self) -> float:
        cfg = self.config
        if cfg.mmsm_bsl_ref == LIQ_REF_SESSION:
            return self.session_high if not math.isnan(self.session_high) else self.pdh
        return self.pdh

    def _update_liq_session(self, time_int, high, low):
        cfg = self.config
        start = cfg.liq_session_start
        end = cfg.liq_session_end

        if start > end:
            in_session = time_int >= start or time_int < end
        else:
            in_session = start <= time_int < end

        if in_session:
            if math.isnan(self.session_high) or high > self.session_high:
                self.session_high = high
            if math.isnan(self.session_low) or low < self.session_low:
                self.session_low = low
            self.in_liq_session = True
        elif self.in_liq_session:
            self.in_liq_session = False

    # ==================== Swing Detection ====================

    def _find_swing_high(self, strength) -> float:
        """Find most recent swing high (pivot high) working backwards."""
        highs = self.hist_highs
        n = len(highs)
        for i in range(n - strength - 2, strength - 1, -1):
            high = highs[i]
            is_swing = True
            for j in range(1, strength + 1):
                if i - j >= 0 and highs[i - j] >= high:
                    is_swing = False
                    break
                if i + j < n and highs[i + j] >= high:
                    is_swing = False
                    break
            if is_swing:
                return high
        return math.nan

    def _find_swing_low(self, strength) -> float:
        """Find most recent swing low (pivot low) working backwards."""
        lows = self.hist_lows
        n = len(lows)
        for i in range(n - strength - 2, strength - 1, -1):
            low = lows[i]
            is_swing = True
            for j in range(1, strength + 1):
                if i - j >= 0 and lows[i - j] <= low:
                    is_swing = False
                    break
                if i + j < n and lows[i + j] <= low:
                    is_swing = False
                    break
            if is_swing:
                return low
        return math.nan

    def _find_major_swing_low(self, htf_strength, lookback) -> float:
        """Find lowest swing low over lookback period."""
        lows = self.hist_lows
        n = len(lows)
        lowest = math.nan

        start_idx = max(htf_strength, n - lookback)
        for i in range(start_idx, n - htf_strength):
            low = lows[i]
            is_swing = True
            for j in range(1, htf_strength + 1):
                if i - j >= 0 and lows[i - j] <= low:
                    is_swing = False
                    break
                if i + j < n and lows[i + j] <= low:
                    is_swing = False
                    break
            if is_swing:
                if math.isnan(lowest) or low < lowest:
                    lowest = low
        return lowest

    def _find_major_swing_high(self, htf_strength, lookback) -> float:
        """Find highest swing high over lookback period."""
        highs = self.hist_highs
        n = len(highs)
        highest = math.nan

        start_idx = max(htf_strength, n - lookback)
        for i in range(start_idx, n - htf_strength):
            high = highs[i]
            is_swing = True
            for j in range(1, htf_strength + 1):
                if i - j >= 0 and highs[i - j] >= high:
                    is_swing = False
                    break
                if i + j < n and highs[i + j] >= high:
                    is_swing = False
                    break
            if is_swing:
                if math.isnan(highest) or high > highest:
                    highest = high
        return highest

    # ==================== Kill Zone ====================

    def _is_in_kill_zone(self, time_int) -> bool:
        cfg = self.config
        kz = cfg.kill_zone_preset
        if kz == KZ_NY_AM:
            return 830 <= time_int < 1100
        elif kz == KZ_NY_PM:
            return 1330 <= time_int < 1600
        elif kz == KZ_LONDON_AM:
            return 300 <= time_int < 500
        elif kz == KZ_CUSTOM:
            return cfg.kz_custom_start <= time_int < cfg.kz_custom_end
        return True

    # ==================== Helpers ====================

    def _update_ema(self, close: float):
        period = self.config.ema_period
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

    def _compute_realized_vol(self) -> float:
        """Annualized realized volatility from daily log returns."""
        closes = self.daily_closes
        n = self.config.vol_lookback_days
        if len(closes) < n + 1:
            return math.nan
        recent = closes[-(n + 1):]
        log_returns = [math.log(recent[i] / recent[i - 1]) for i in range(1, len(recent))]
        mean_r = sum(log_returns) / len(log_returns)
        var = sum((r - mean_r) ** 2 for r in log_returns) / (len(log_returns) - 1)
        return math.sqrt(var * 252) * 100  # annualized %

    def _get_displacement_ticks(self) -> int:
        s = self.config.confirmation_strictness
        if s == STRICT_AGGRESSIVE:
            return 4
        elif s == STRICT_BALANCED:
            return 8
        return 12  # Conservative

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

    def _reset_daily_state(self):
        self._reset_mmbm_state()
        self._reset_mmsm_state()
        self.trades_today = 0
        self.long_trades_today = 0
        self.short_trades_today = 0
        self.eod_processed = False
        self._reset_trade_state()

    def _reset_mmbm_state(self):
        self.mmbm_state = STATE_IDLE
        self.mmbm_sweep_low = math.nan
        self.mmbm_mss_level = math.nan
        self.mmbm_sweep_strength = 0
        self.mmbm_fvg_detected = False
        self.mmbm_entry_bar = -1

    def _reset_mmsm_state(self):
        self.mmsm_state = STATE_IDLE
        self.mmsm_sweep_high = math.nan
        self.mmsm_mss_level = math.nan
        self.mmsm_sweep_strength = 0
        self.mmsm_fvg_detected = False
        self.mmsm_entry_bar = -1

    def _reset_trade_state(self):
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.partial_taken = False
        self.current_direction = 0
        self.initial_qty = 0
