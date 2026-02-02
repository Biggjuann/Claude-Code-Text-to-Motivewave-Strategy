# RTH Sweep Mean Reversion Strategy

A sophisticated mean reversion strategy that trades failed breakouts (sweeps) of a morning balance range, filtered by VWAP.

---

## Strategy Overview

**Type:** Mean Reversion
**Direction:** Long and Short
**Best Timeframe:** 5-minute, 15-minute
**Best Markets:** ES, NQ, MES, MNQ (Index Futures)
**Timezone:** America/Chicago (CME)

### Core Concept

1. Build a "balance range" during the morning session (default 9:30-11:30 CT)
2. After balance window closes, watch for price to "sweep" beyond the range
3. A sweep occurs when price exceeds the range boundary but closes back inside
4. This failed breakout suggests trapped traders and mean reversion potential
5. Enter in the direction of the reversion, targeting the opposite side of the range

---

## Entry Logic

### Long Entry (Sweep Low)
- Balance range is complete and valid (within min/max bounds)
- Price swept below RTH Low (low < rthLow)
- Price closed back inside range (close > rthLow && close < rthHigh)
- VWAP filter passed (close < VWAP if enabled) - "wrong side" confirms mean reversion
- Within trade window, under daily trade limit, long not already used today

### Short Entry (Sweep High)
- Balance range is complete and valid
- Price swept above RTH High (high > rthHigh)
- Price closed back inside range
- VWAP filter passed (close > VWAP if enabled)
- Within trade window, under trade limit, short not already used today

---

## Exit Logic

### Stop Loss
- **Long:** RTH Low - Stop Points
- **Short:** RTH High + Stop Points

### Take Profit (Two Targets)
- **Target 1 (Partial):** Range midpoint - exit partial % of position
- **Target 2 (Remainder):** Opposite range boundary

---

## Settings Reference

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Balance Start (HHMM) | 930 | When to start building the range |
| Balance End (HHMM) | 1130 | When balance window closes |
| Trade Start (HHMM) | 930 | Earliest time for entries |
| Trade End (HHMM) | 1600 | Latest time for entries |

### Range Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Min Range (pts) | 6.0 | Minimum range width to be valid |
| Max Range (pts) | 25.0 | Maximum range width to be valid |
| Use Lookback Sweep | false | Single bar vs multi-bar sweep detection |
| Lookback Bars | 12 | Bars to check for sweep (if lookback enabled) |

### VWAP Filter Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Require wrong side of VWAP | true | Price must be below VWAP for longs, above for shorts |
| Block when VWAP against fade | false | Additional filter based on VWAP slope |
| Slope Bars | 3 | Bars used to calculate VWAP slope |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Stop Distance (pts) | 5.0 | Points beyond range boundary for stop |
| Partial % at Midpoint | 50 | Percentage to exit at first target |
| Max Trades/Day | 2 | Maximum entries per day |

---

## Visual Indicators

When applied to a chart, the strategy plots:

- **RTH High** (Red line): Top of balance range
- **RTH Low** (Green line): Bottom of balance range
- **Range Mid** (Yellow dashed): Midpoint / first target
- **VWAP** (Blue line): Session VWAP
- **Entry Markers**: Triangle markers at entry points

---

## Example Trade

```
Morning Session (9:30-11:30 CT):
- High: 4520.00
- Low: 4505.00
- Midpoint: 4512.50

At 1:15 PM:
- Price drops to 4503.50 (swept below 4505 low)
- Candle closes at 4507.00 (back inside range)
- VWAP at 4515.00 (price below VWAP ✓)

Entry: LONG at 4507.00
Stop: 4500.00 (4505 - 5 pts)
Target 1: 4512.50 (midpoint) - exit 50%
Target 2: 4520.00 (range high) - exit remaining 50%
```

---

## Optimization Tips

1. **Tighter Range Settings**: For choppy days, use 8-20 pt range limits
2. **VWAP Slope Filter**: Enable for trending days to avoid fading strong moves
3. **Reduce Max Trades**: Set to 1 for higher quality setups only
4. **Adjust Balance Window**: Try 9:30-11:00 for faster range formation

---

## Backtest Considerations

- Requires minimum 2-3 weeks of intraday data
- Best results typically in first 2 hours after balance window closes
- Performance varies by market regime (range-bound days perform best)
- Consider filtering out high-volatility news days (FOMC, NFP, etc.)
