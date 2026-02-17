"""Draw liquidity target tracking and bias calculation.

Copied from nautilus_backtest/liquidity.py — no Nautilus dependencies.
Import paths adjusted for ict_modules package.
"""

import math
from ict_modules.zones import LiquidityTarget, BIAS_BULLISH, BIAS_BEARISH, BIAS_NEUTRAL


def update_draw_targets(
    close: float,
    intraday_bias: int,
    session_high: float = math.nan,
    session_low: float = math.nan,
    swing_high: float = math.nan,
    swing_low: float = math.nan,
    use_session: bool = True,
    use_swing: bool = True,
) -> tuple[list[LiquidityTarget], LiquidityTarget | None]:
    targets = []

    if use_session:
        if not math.isnan(session_high) and close < session_high:
            targets.append(LiquidityTarget(session_high, "SESSION_HIGH", True))
        if not math.isnan(session_low) and close > session_low:
            targets.append(LiquidityTarget(session_low, "SESSION_LOW", False))

    if use_swing:
        if not math.isnan(swing_high) and close < swing_high:
            targets.append(LiquidityTarget(swing_high, "SWING_HIGH", True))
        if not math.isnan(swing_low) and close > swing_low:
            targets.append(LiquidityTarget(swing_low, "SWING_LOW", False))

    primary = None
    min_dist = math.inf
    for t in targets:
        dist = abs(t.price - close)
        if dist < min_dist:
            if (intraday_bias == BIAS_BULLISH and t.is_bullish_draw) or \
               (intraday_bias == BIAS_BEARISH and not t.is_bullish_draw) or \
               intraday_bias == BIAS_NEUTRAL:
                min_dist = dist
                primary = t

    return targets, primary


def update_bias(
    close: float,
    intraday_ma: float,
    last_swing_high: float,
    last_swing_low: float,
    prev_swing_high: float,
    prev_swing_low: float,
) -> int:
    if math.isnan(intraday_ma):
        return BIAS_NEUTRAL

    if close > intraday_ma and not math.isnan(last_swing_low) and not math.isnan(prev_swing_low):
        if last_swing_low > prev_swing_low:
            return BIAS_BULLISH

    if close < intraday_ma and not math.isnan(last_swing_high) and not math.isnan(prev_swing_high):
        if last_swing_high < prev_swing_high:
            return BIAS_BEARISH

    return BIAS_NEUTRAL
