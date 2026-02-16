"""Zone detection functions for BrianStonk ICT strategy.

Direct 1:1 port of detection methods from BrianStonkModularStrategy.java.
All functions are pure: take bar data arrays, return new Zone objects.
"""

import math
from zones import Zone, ZoneType


def detect_order_blocks(
    opens: list[float],
    closes: list[float],
    highs: list[float],
    lows: list[float],
    bar_index: int,
    min_candles: int = 2,
) -> list[Zone]:
    """Detect order blocks at the current bar.

    Bullish OB: N consecutive up-close candles followed by a down-close that
    breaks below the series body bottom.
    Bearish OB: N consecutive down-close candles followed by an up-close that
    breaks above the series body top.
    """
    new_zones = []
    n = len(opens)
    if n < min_candles + 1:
        return new_zones

    cur_open = opens[-1]
    cur_close = closes[-1]

    # Bullish OB: consecutive up-close candles before current bar
    up_count = 0
    for i in range(n - 2, -1, -1):
        if closes[i] > opens[i]:
            up_count += 1
            if up_count >= 5:
                break
        else:
            break

    if up_count >= min_candles and cur_close < cur_open:
        ob_top = -math.inf
        ob_bottom = math.inf
        start = n - 1 - up_count
        for i in range(start, n - 1):
            body_hi = max(opens[i], closes[i])
            body_lo = min(opens[i], closes[i])
            ob_top = max(ob_top, body_hi)
            ob_bottom = min(ob_bottom, body_lo)

        if cur_close < ob_bottom:
            new_zones.append(Zone(ob_top, ob_bottom, bar_index, True, ZoneType.OB))

    # Bearish OB: consecutive down-close candles before current bar
    down_count = 0
    for i in range(n - 2, -1, -1):
        if closes[i] < opens[i]:
            down_count += 1
            if down_count >= 5:
                break
        else:
            break

    if down_count >= min_candles and cur_close > cur_open:
        ob_top = -math.inf
        ob_bottom = math.inf
        start = n - 1 - down_count
        for i in range(start, n - 1):
            body_hi = max(opens[i], closes[i])
            body_lo = min(opens[i], closes[i])
            ob_top = max(ob_top, body_hi)
            ob_bottom = min(ob_bottom, body_lo)

        if cur_close > ob_top:
            new_zones.append(Zone(ob_top, ob_bottom, bar_index, False, ZoneType.OB))

    return new_zones


def check_ob_to_breaker(ob_zones: list[Zone], close: float, bar_index: int) -> list[Zone]:
    """Check if any OB has been violated, flipping it to a breaker.

    Bullish OB violated (close < bottom) -> bearish breaker.
    Bearish OB violated (close > top) -> bullish breaker.
    """
    new_breakers = []
    for ob in ob_zones:
        if not ob.is_valid or ob.violated:
            continue
        if ob.is_bullish and close < ob.bottom:
            ob.violated = True
            ob.is_valid = False
            new_breakers.append(
                Zone(ob.top, ob.bottom, bar_index, False, ZoneType.BREAKER)
            )
        elif not ob.is_bullish and close > ob.top:
            ob.violated = True
            ob.is_valid = False
            new_breakers.append(
                Zone(ob.top, ob.bottom, bar_index, True, ZoneType.BREAKER)
            )
    return new_breakers


def detect_structure_breakers(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    bar_index: int,
    last_swing_high: float,
    last_swing_low: float,
    last_swing_high_bar: int,
    last_swing_low_bar: int,
    require_displacement: bool = True,
    lookback: int = 20,
) -> list[Zone]:
    """Detect structure breakers from sweep + displacement sequences.

    Bullish: sweep below swing low -> displacement above swing high.
    Bearish: sweep above swing high -> displacement below swing low.
    """
    new_breakers = []
    if math.isnan(last_swing_high) or math.isnan(last_swing_low):
        return new_breakers

    n = len(closes)
    cur_close = closes[-1]
    cur_open = closes[-2] if n >= 2 else cur_close  # approximate open

    # Bullish breaker: sweep below swing low, then close above swing high
    swept_low = False
    sweep_low_price = math.nan
    scan_start = max(0, n - lookback)
    swing_low_offset = max(0, n - (bar_index - last_swing_low_bar) - 1)
    for i in range(n - 2, max(scan_start, swing_low_offset) - 1, -1):
        if lows[i] < last_swing_low:
            swept_low = True
            sweep_low_price = lows[i]
            break

    if swept_low and cur_close > last_swing_high:
        body_size = abs(cur_close - (closes[-2] if n >= 2 else cur_close))
        if body_size > 5 or not require_displacement:
            breaker_top = last_swing_low + 3
            new_breakers.append(
                Zone(breaker_top, sweep_low_price, bar_index, True, ZoneType.BREAKER)
            )

    # Bearish breaker: sweep above swing high, then close below swing low
    swept_high = False
    sweep_high_price = math.nan
    swing_high_offset = max(0, n - (bar_index - last_swing_high_bar) - 1)
    for i in range(n - 2, max(scan_start, swing_high_offset) - 1, -1):
        if highs[i] > last_swing_high:
            swept_high = True
            sweep_high_price = highs[i]
            break

    if swept_high and cur_close < last_swing_low:
        body_size = abs(cur_close - (closes[-2] if n >= 2 else cur_close))
        if body_size > 5 or not require_displacement:
            breaker_bottom = last_swing_high - 3
            new_breakers.append(
                Zone(sweep_high_price, breaker_bottom, bar_index, False, ZoneType.BREAKER)
            )

    return new_breakers


def detect_fvgs(
    highs: list[float],
    lows: list[float],
    bar_index: int,
    min_gap: float = 2.0,
) -> list[Zone]:
    """Detect 3-bar fair value gaps.

    Bullish FVG: bar[0].high < bar[2].low (gap up).
    Bearish FVG: bar[0].low > bar[2].high (gap down).
    """
    new_zones = []
    n = len(highs)
    if n < 3:
        return new_zones

    c1_high = highs[-3]  # candle 1 (two bars ago)
    c1_low = lows[-3]
    c3_high = highs[-1]  # candle 3 (current)
    c3_low = lows[-1]

    # Bullish FVG
    if c3_low > c1_high and (c3_low - c1_high) >= min_gap:
        new_zones.append(Zone(c3_low, c1_high, bar_index, True, ZoneType.FVG))

    # Bearish FVG
    if c1_low > c3_high and (c1_low - c3_high) >= min_gap:
        new_zones.append(Zone(c1_low, c3_high, bar_index, False, ZoneType.FVG))

    return new_zones


def detect_inversions(fvg_zones: list[Zone], close: float, bar_index: int) -> list[Zone]:
    """Detect FVG inversions (IFVG): price displaces through FVG, flipping role.

    Bullish FVG displaced through (close < bottom) -> bearish IFVG.
    Bearish FVG displaced through (close > top) -> bullish IFVG.
    """
    new_ifvgs = []
    for fvg in fvg_zones:
        if not fvg.is_valid or fvg.zone_type == ZoneType.IFVG:
            continue
        if fvg.is_bullish and close < fvg.bottom:
            new_ifvgs.append(Zone(fvg.top, fvg.bottom, bar_index, False, ZoneType.IFVG))
            fvg.is_valid = False
        elif not fvg.is_bullish and close > fvg.top:
            new_ifvgs.append(Zone(fvg.top, fvg.bottom, bar_index, True, ZoneType.IFVG))
            fvg.is_valid = False
    return new_ifvgs


def detect_bprs(ifvg_zones: list[Zone], fvg_zones: list[Zone], bar_index: int) -> list[Zone]:
    """Detect balanced price ranges (overlap between IFVG and FVG)."""
    new_bprs = []
    existing_levels = set()

    for ifvg in ifvg_zones:
        if not ifvg.is_valid:
            continue
        for fvg in fvg_zones:
            if not fvg.is_valid or fvg.bar_index == ifvg.bar_index:
                continue
            overlap_top = min(ifvg.top, fvg.top)
            overlap_bottom = max(ifvg.bottom, fvg.bottom)
            if overlap_top > overlap_bottom:
                key = (round(overlap_top), round(overlap_bottom))
                if key not in existing_levels:
                    existing_levels.add(key)
                    new_bprs.append(
                        Zone(overlap_top, overlap_bottom, bar_index, ifvg.is_bullish, ZoneType.BPR)
                    )

    return new_bprs


def invalidate_zones(zone_lists: list[list[Zone]], close: float, bar_index: int, max_age: int = 50):
    """Invalidate old zones and remove them from their lists.

    OB/Breaker: invalidated if close passes through against direction.
    All zones: invalidated by age.
    """
    for zones in zone_lists:
        for zone in zones:
            if not zone.is_valid:
                continue
            if bar_index - zone.bar_index > max_age:
                zone.is_valid = False
                continue
            # Close through against direction invalidates OB and Breaker
            if zone.zone_type in (ZoneType.OB, ZoneType.BREAKER):
                if zone.is_bullish and close < zone.bottom:
                    zone.is_valid = False
                elif not zone.is_bullish and close > zone.top:
                    zone.is_valid = False

    # Prune invalid zones
    for i, zones in enumerate(zone_lists):
        zone_lists[i][:] = [z for z in zones if z.is_valid]


def update_swing_points(
    highs: list[float],
    lows: list[float],
    bar_index: int,
    left: int = 2,
    right: int = 2,
    last_swing_high: float = math.nan,
    last_swing_low: float = math.nan,
    last_swing_high_bar: int = -1,
    last_swing_low_bar: int = -1,
    prev_swing_high: float = math.nan,
    prev_swing_low: float = math.nan,
):
    """Check if a confirmed swing point exists at pivot_bar = bar_index - right.

    Returns updated (last_swing_high, last_swing_low, last_swing_high_bar,
    last_swing_low_bar, prev_swing_high, prev_swing_low) or None if no update.
    """
    n = len(highs)
    if n < left + right + 1:
        return None

    pivot_idx = n - 1 - right  # index into the arrays
    if pivot_idx < left:
        return None

    pivot_bar = bar_index - right  # absolute bar index

    updated = False

    # Check swing high
    pivot_high = highs[pivot_idx]
    is_swing_high = True
    for i in range(1, left + 1):
        if highs[pivot_idx - i] >= pivot_high:
            is_swing_high = False
            break
    if is_swing_high:
        for i in range(1, right + 1):
            if highs[pivot_idx + i] >= pivot_high:
                is_swing_high = False
                break
    if is_swing_high:
        prev_swing_high = last_swing_high
        last_swing_high = pivot_high
        last_swing_high_bar = pivot_bar
        updated = True

    # Check swing low
    pivot_low = lows[pivot_idx]
    is_swing_low = True
    for i in range(1, left + 1):
        if lows[pivot_idx - i] <= pivot_low:
            is_swing_low = False
            break
    if is_swing_low:
        for i in range(1, right + 1):
            if lows[pivot_idx + i] <= pivot_low:
                is_swing_low = False
                break
    if is_swing_low:
        prev_swing_low = last_swing_low
        last_swing_low = pivot_low
        last_swing_low_bar = pivot_bar
        updated = True

    if updated:
        return (last_swing_high, last_swing_low, last_swing_high_bar,
                last_swing_low_bar, prev_swing_high, prev_swing_low)
    return None
