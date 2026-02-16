"""
BrianStonk Modular ICT Strategy — NautilusTrader port.

Ported from BrianStonkModularStrategy.java (MotiveWave SDK).
Multi-entry ICT engine: Breaker (BR1), IFVG (IF1), Order Block (OB1).
Manages positions with zone-based stops, breakeven, and fixed-R targets.

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

from zones import Zone, ZoneType, LiquidityTarget, BIAS_BULLISH, BIAS_BEARISH, BIAS_NEUTRAL
from zone_detectors import (
    detect_order_blocks,
    check_ob_to_breaker,
    detect_structure_breakers,
    detect_fvgs,
    detect_inversions,
    detect_bprs,
    invalidate_zones,
    update_swing_points,
)
from liquidity import update_draw_targets, update_bias


# ==================== Config ====================

class BrianStonkConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType

    # Entry models
    enable_long: bool = True
    enable_short: bool = True
    enable_breaker: bool = True
    enable_ifvg: bool = True
    enable_ob: bool = True
    enable_unicorn: bool = False

    # Session
    trade_start: int = 930
    trade_end: int = 1530
    max_trades_day: int = 6
    cooldown_minutes: int = 5
    forced_flat_time: int = 1555

    # Alignment
    require_intraday_align: bool = False
    htf_filter_mode: int = 1  # 0=Strict, 1=Loose, 2=Off
    intraday_ma_period: int = 21
    pivot_left: int = 2
    pivot_right: int = 2

    # Draw liquidity
    require_draw_target: bool = True
    use_session_liquidity: bool = True
    use_swing_liquidity: bool = True

    # OB/Breaker/FVG params
    ob_min_candles: int = 2
    ob_mean_threshold: bool = True
    breaker_require_sweep: bool = True
    breaker_require_displacement: bool = True
    tight_breaker_threshold: float = 10.0
    fvg_min_gap: float = 2.0
    fvg_ce_respect: bool = True

    # Risk
    stop_default: float = 20.0
    stop_min: float = 18.0
    stop_max: float = 25.0
    stop_override_to_structure: bool = True
    be_enabled: bool = True
    be_trigger_pts: float = 10.0
    contracts: int = 10
    dollars_per_contract: float = 0.0  # 0 = fixed sizing, >0 = dynamic (e.g. 5000)

    # Targets (Fixed R mode)
    target_r: float = 1.0
    partial_enabled: bool = False
    runner_enabled: bool = True

    # VIX filter
    vix_filter_enabled: bool = False
    vix_off: float = 30.0
    vix_on: float = 20.0

    # EOD
    eod_time: int = 1555


# ==================== Strategy ====================

class BrianStonkStrategy(Strategy):

    def __init__(self, config: BrianStonkConfig, vix_lookup: dict = None):
        super().__init__(config)

        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type

        # VIX filter
        self.vix_lookup = vix_lookup or {}
        self.vix_blocked: bool = False

        # Zone tracking
        self.ob_zones: list[Zone] = []
        self.breaker_zones: list[Zone] = []
        self.fvg_zones: list[Zone] = []
        self.ifvg_zones: list[Zone] = []
        self.bpr_zones: list[Zone] = []

        # Swing tracking
        self.last_swing_high: float = math.nan
        self.last_swing_low: float = math.nan
        self.last_swing_high_bar: int = -1
        self.last_swing_low_bar: int = -1
        self.prev_swing_high: float = math.nan
        self.prev_swing_low: float = math.nan

        # Session tracking
        self.session_high: float = math.nan
        self.session_low: float = math.nan

        # Bias
        self.intraday_bias: int = BIAS_NEUTRAL
        self.ltf_permission: bool = False

        # Draw targets
        self.draw_targets: list[LiquidityTarget] = []
        self.primary_draw_target: LiquidityTarget | None = None

        # EMA state (manual rolling EMA)
        self.ema_value: float = math.nan
        self.ema_count: int = 0

        # Trade state
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.target_price: float = 0.0
        self.risk_points: float = 0.0
        self.is_long_trade: bool = False
        self.be_activated: bool = False
        self.entry_model: str = ""

        # Pending confirmation
        self.pending_zone: Zone | None = None
        self.pending_model: str | None = None
        self.confirmation_wait_bar: int = -1

        # Daily tracking
        self.bar_count: int = 0
        self.last_reset_day: int = -1
        self.eod_processed: bool = False
        self.trades_today: int = 0
        self.last_trade_bar: int = -1

        # Bar history for detector functions (rolling window)
        self.hist_opens: list[float] = []
        self.hist_closes: list[float] = []
        self.hist_highs: list[float] = []
        self.hist_lows: list[float] = []
        self.max_hist = 60  # keep last N bars for detection

    # ==================== Lifecycle ====================

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info("BrianStonk Modular Strategy started")

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("BrianStonk Modular Strategy stopped")

    # ==================== Core Logic ====================

    def on_bar(self, bar: Bar):
        self.bar_count += 1
        cfg = self.config

        # Extract bar values
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

        # Need warmup
        if self.bar_count < 10:
            self._update_ema(c)
            return

        # Bar time in ET
        bar_dt = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC").tz_convert(
            "America/New_York"
        )
        bar_time_int = bar_dt.hour * 100 + bar_dt.minute
        bar_day = bar_dt.day_of_year + bar_dt.year * 1000

        # ===== Daily reset =====
        if bar_day != self.last_reset_day:
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

        # ===== Session H/L =====
        if bar_time_int >= cfg.trade_start and bar_time_int <= cfg.trade_end:
            if math.isnan(self.session_high) or h > self.session_high:
                self.session_high = h
            if math.isnan(self.session_low) or l < self.session_low:
                self.session_low = l

        # ===== Update swings =====
        swing_result = update_swing_points(
            self.hist_highs, self.hist_lows, self.bar_count,
            cfg.pivot_left, cfg.pivot_right,
            self.last_swing_high, self.last_swing_low,
            self.last_swing_high_bar, self.last_swing_low_bar,
            self.prev_swing_high, self.prev_swing_low,
        )
        if swing_result is not None:
            (self.last_swing_high, self.last_swing_low,
             self.last_swing_high_bar, self.last_swing_low_bar,
             self.prev_swing_high, self.prev_swing_low) = swing_result

        # ===== EMA =====
        self._update_ema(c)

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
            position = self._get_open_position()
            if position is None and self.entry_price > 0:
                self._reset_trade_state()
            return  # Don't detect/enter while in position

        if self.entry_price > 0:
            self._reset_trade_state()

        # ===== Zone detection =====
        # Order blocks
        new_obs = detect_order_blocks(
            self.hist_opens, self.hist_closes, self.hist_highs, self.hist_lows,
            self.bar_count, cfg.ob_min_candles,
        )
        self.ob_zones.extend(new_obs)
        if len(self.ob_zones) > 15:
            self.ob_zones = self.ob_zones[-15:]

        # OB -> Breaker
        new_breakers = check_ob_to_breaker(self.ob_zones, c, self.bar_count)
        self.breaker_zones.extend(new_breakers)

        # Structure breakers
        struct_breakers = detect_structure_breakers(
            self.hist_closes, self.hist_highs, self.hist_lows,
            self.bar_count,
            self.last_swing_high, self.last_swing_low,
            self.last_swing_high_bar, self.last_swing_low_bar,
            cfg.breaker_require_displacement,
        )
        self.breaker_zones.extend(struct_breakers)
        if len(self.breaker_zones) > 15:
            self.breaker_zones = self.breaker_zones[-15:]

        # FVGs
        new_fvgs = detect_fvgs(self.hist_highs, self.hist_lows, self.bar_count, cfg.fvg_min_gap)
        self.fvg_zones.extend(new_fvgs)
        if len(self.fvg_zones) > 20:
            self.fvg_zones = self.fvg_zones[-20:]

        # Inversions (IFVG)
        new_ifvgs = detect_inversions(self.fvg_zones, c, self.bar_count)
        self.ifvg_zones.extend(new_ifvgs)
        if len(self.ifvg_zones) > 15:
            self.ifvg_zones = self.ifvg_zones[-15:]

        # BPRs
        new_bprs = detect_bprs(self.ifvg_zones, self.fvg_zones, self.bar_count)
        for bpr in new_bprs:
            exists = any(
                abs(z.top - bpr.top) < 1 and abs(z.bottom - bpr.bottom) < 1
                for z in self.bpr_zones
            )
            if not exists:
                self.bpr_zones.append(bpr)
        if len(self.bpr_zones) > 10:
            self.bpr_zones = self.bpr_zones[-10:]

        # Invalidate old zones
        all_zone_lists = [self.ob_zones, self.breaker_zones, self.fvg_zones,
                          self.ifvg_zones, self.bpr_zones]
        invalidate_zones(all_zone_lists, c, self.bar_count)

        # ===== Draw targets + bias =====
        self.intraday_bias = update_bias(
            c, self.ema_value,
            self.last_swing_high, self.last_swing_low,
            self.prev_swing_high, self.prev_swing_low,
        )
        # HTF bias = intraday (Loose mode, htfFilterMode=1)
        self.ltf_permission = (self.intraday_bias != BIAS_NEUTRAL)

        self.draw_targets, self.primary_draw_target = update_draw_targets(
            c, self.intraday_bias,
            self.session_high, self.session_low,
            self.last_swing_high, self.last_swing_low,
            cfg.use_session_liquidity, cfg.use_swing_liquidity,
        )

        # ===== Entry conditions =====
        in_trade_window = cfg.trade_start <= bar_time_int < cfg.trade_end
        past_flat_time = bar_time_int >= cfg.forced_flat_time
        cooldown_ok = (self.bar_count - self.last_trade_bar) >= cfg.cooldown_minutes
        under_limit = self.trades_today < cfg.max_trades_day
        has_draw = self.primary_draw_target is not None or not cfg.require_draw_target
        has_align = self.ltf_permission or not cfg.require_intraday_align
        can_trade = (in_trade_window and not past_flat_time and cooldown_ok
                     and under_limit and has_draw and has_align
                     and not self.vix_blocked)

        if can_trade:
            self._process_entry_models(c, o)

        # Handle pending confirmation
        if self.pending_zone is not None and self._get_open_position() is None:
            self._handle_pending_confirmation(c, o)

    # ==================== Entry Models ====================

    def _process_entry_models(self, close: float, open_: float):
        cfg = self.config
        enable_long = cfg.enable_long
        enable_short = cfg.enable_short
        bias = self.intraday_bias

        # Priority: BR1 > IF1 > OB1 (no UN1 since enable_unicorn=false)

        # BR1: Breaker Retap
        if cfg.enable_breaker and self.pending_zone is None:
            for breaker in self.breaker_zones:
                if not breaker.is_valid:
                    continue
                if close >= breaker.bottom and close <= breaker.top:
                    if breaker.is_bullish and enable_long and bias >= BIAS_NEUTRAL:
                        self._set_pending_entry(breaker, "BR1")
                        break
                    elif not breaker.is_bullish and enable_short and bias <= BIAS_NEUTRAL:
                        self._set_pending_entry(breaker, "BR1")
                        break

        # IF1: IFVG/BPR Flip
        if cfg.enable_ifvg and self.pending_zone is None:
            for ifvg in self.ifvg_zones:
                if not ifvg.is_valid:
                    continue
                if close >= ifvg.bottom and close <= ifvg.top:
                    if ifvg.is_bullish and enable_long and bias >= BIAS_NEUTRAL:
                        self._set_pending_entry(ifvg, "IF1")
                        break
                    elif not ifvg.is_bullish and enable_short and bias <= BIAS_NEUTRAL:
                        self._set_pending_entry(ifvg, "IF1")
                        break

        # OB1: Order Block Mean Threshold
        if cfg.enable_ob and self.pending_zone is None:
            for ob in self.ob_zones:
                if not ob.is_valid or ob.violated:
                    continue
                if close >= ob.bottom and close <= ob.top:
                    mean_ok = True
                    if cfg.ob_mean_threshold:
                        if ob.is_bullish and close < ob.mid:
                            mean_ok = False
                        if not ob.is_bullish and close > ob.mid:
                            mean_ok = False
                    if mean_ok:
                        if ob.is_bullish and enable_long and bias >= BIAS_NEUTRAL:
                            self._set_pending_entry(ob, "OB1")
                            break
                        elif not ob.is_bullish and enable_short and bias <= BIAS_NEUTRAL:
                            self._set_pending_entry(ob, "OB1")
                            break

    def _set_pending_entry(self, zone: Zone, model: str):
        self.pending_zone = zone
        self.pending_model = model
        self.confirmation_wait_bar = self.bar_count

    def _handle_pending_confirmation(self, close: float, open_: float):
        """Wait up to 3 bars for a rejection candle confirming the entry."""
        if self.pending_zone is None:
            return

        # Timeout
        if self.bar_count - self.confirmation_wait_bar > 3:
            self.pending_zone = None
            self.pending_model = None
            self.confirmation_wait_bar = -1
            return

        # Confirmation: close in direction, beyond zone mid
        zone = self.pending_zone
        if zone.is_bullish:
            if close > open_ and close > zone.mid:
                self._trigger_entry(zone, True, self.pending_model, close)
        else:
            if close < open_ and close < zone.mid:
                self._trigger_entry(zone, False, self.pending_model, close)

    def _compute_contracts(self) -> int:
        """Compute position size from account equity if dynamic sizing enabled."""
        cfg = self.config
        if cfg.dollars_per_contract <= 0:
            return cfg.contracts
        account = self.portfolio.account(self.instrument_id.venue)
        if account is None:
            return cfg.contracts
        equity = float(account.balance_total().as_double())
        qty = max(1, int(equity // cfg.dollars_per_contract))
        return qty

    def _trigger_entry(self, zone: Zone, is_long: bool, model: str, price: float):
        cfg = self.config
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
        self.entry_price = price
        self.entry_model = model

        # Stop calculation: zone-based with structure override for tight zones
        if is_long:
            zone_stop = zone.bottom - 2
            if zone.height < cfg.tight_breaker_threshold and cfg.stop_override_to_structure:
                zone_stop = (self.last_swing_low - 2) if not math.isnan(self.last_swing_low) else (price - cfg.stop_max)
            self.risk_points = price - zone_stop
        else:
            zone_stop = zone.top + 2
            if zone.height < cfg.tight_breaker_threshold and cfg.stop_override_to_structure:
                zone_stop = (self.last_swing_high + 2) if not math.isnan(self.last_swing_high) else (price + cfg.stop_max)
            self.risk_points = zone_stop - price

        # Clamp risk
        self.risk_points = max(cfg.stop_min, min(self.risk_points, cfg.stop_max))

        if is_long:
            self.stop_price = price - self.risk_points
            self.target_price = price + self.risk_points * cfg.target_r
        else:
            self.stop_price = price + self.risk_points
            self.target_price = price - self.risk_points * cfg.target_r

        self.be_activated = False
        self.trades_today += 1
        self.last_trade_bar = self.bar_count

        # Invalidate the zone
        zone.is_valid = False
        self.pending_zone = None
        self.pending_model = None
        self.confirmation_wait_bar = -1

        self.log.info(
            f"{'LONG' if is_long else 'SHORT'} {model}: qty={num_contracts}, "
            f"entry={price:.2f}, stop={self.stop_price:.2f}, "
            f"target={self.target_price:.2f}, risk={self.risk_points:.1f}pts, "
            f"zone=[{zone.bottom:.2f}-{zone.top:.2f}]"
        )

    # ==================== Position Management ====================

    def _manage_position(self, position: Position, high: float, low: float, close: float):
        cfg = self.config
        is_long = position.is_long

        # Stop loss check
        if is_long and low <= self.stop_price:
            self.close_position(position)
            self.log.info(f"LONG stopped at {self.stop_price:.2f}")
            self._reset_trade_state()
            return
        if not is_long and high >= self.stop_price:
            self.close_position(position)
            self.log.info(f"SHORT stopped at {self.stop_price:.2f}")
            self._reset_trade_state()
            return

        # Breakeven
        if cfg.be_enabled and not self.be_activated and self.risk_points > 0:
            unrealized = (close - self.entry_price) if is_long else (self.entry_price - close)
            if unrealized >= cfg.be_trigger_pts:
                if is_long and self.entry_price > self.stop_price:
                    self.stop_price = self.entry_price
                elif not is_long and self.entry_price < self.stop_price:
                    self.stop_price = self.entry_price
                self.be_activated = True

        # Target hit
        if is_long and high >= self.target_price:
            self.close_position(position)
            self.log.info(f"LONG target hit at {self.target_price:.2f}")
            self._reset_trade_state()
            return
        if not is_long and low <= self.target_price:
            self.close_position(position)
            self.log.info(f"SHORT target hit at {self.target_price:.2f}")
            self._reset_trade_state()
            return

    # ==================== Helpers ====================

    def _update_ema(self, close: float):
        """Update running EMA value."""
        period = self.config.intraday_ma_period
        if math.isnan(self.ema_value):
            self.ema_value = close
            self.ema_count = 1
        else:
            self.ema_count += 1
            k = 2.0 / (period + 1)
            self.ema_value = close * k + self.ema_value * (1 - k)

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
        self.target_price = 0.0
        self.risk_points = 0.0
        self.be_activated = False
        self.entry_model = ""

    def _reset_daily_state(self):
        self.ob_zones.clear()
        self.breaker_zones.clear()
        self.fvg_zones.clear()
        self.ifvg_zones.clear()
        self.bpr_zones.clear()
        self.draw_targets.clear()
        self.primary_draw_target = None
        self.trades_today = 0
        self.eod_processed = False
        self.pending_zone = None
        self.pending_model = None
        self.confirmation_wait_bar = -1
        self.session_high = math.nan
        self.session_low = math.nan
        # Reset EMA on new day so it starts fresh
        self.ema_value = math.nan
        self.ema_count = 0
