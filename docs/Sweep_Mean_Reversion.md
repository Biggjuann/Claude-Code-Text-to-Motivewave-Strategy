# Sweep Mean Reversion Strategy

A straightforward mean reversion strategy that trades failed breakouts using a rolling range high/low, without session-specific timing.

---

## Strategy Overview

**Type:** Mean Reversion
**Direction:** Long and Short
**Best Timeframe:** 5-minute, 15-minute, 30-minute
**Best Markets:** All futures, especially ES, NQ
**Timezone:** Any (no session filtering)

### Core Concept

This is a simpler version of the RTH Sweep strategy, designed to work on any market and any time:

1. Calculate a rolling range (highest high / lowest low over N bars)
2. Watch for price to "sweep" beyond the range boundary
3. Enter when price closes back inside the range (failed breakout)
4. Target the middle or opposite side of the range

---

## Entry Logic

### Long Entry (Sweep Low)
- Current bar's low is below the rolling range low
- Current bar closes back inside the range (above range low)
- Under maximum trades per day limit

### Short Entry (Sweep High)
- Current bar's high is above the rolling range high
- Current bar closes back inside the range (below range high)
- Under maximum trades per day limit

---

## Settings Reference

### General Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Range Period | 20 | Bars for rolling high/low calculation |
| Contracts | 1 | Position size |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Stop Points | 5.0 | Points beyond the swept boundary |
| Target Mode | Midpoint | Midpoint or Opposite boundary |
| Max Trades/Day | 2 | Maximum entries per day |

### Display Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Range High Line | Red | Color for range high |
| Range Low Line | Green | Color for range low |
| Midpoint Line | Yellow | Color for range midpoint |

---

## How Rolling Range Works

Unlike session-based strategies, this uses a **rolling window**:

```
Range Period = 20 bars

At each bar:
- Range High = Highest high of last 20 bars
- Range Low = Lowest low of last 20 bars
- Midpoint = (Range High + Range Low) / 2

The range updates every bar, creating dynamic levels.
```

---

## Example Trade

```
20-bar Rolling Range:
- Range High: 4525.00
- Range Low: 4510.00
- Midpoint: 4517.50

Current Bar:
- High: 4524.00
- Low: 4508.00 (swept below 4510)
- Close: 4512.00 (back inside range ✓)

Entry: LONG at 4512.00
Stop: 4505.00 (4510 - 5 pts)
Target (Midpoint): 4517.50
Target (Opposite): 4525.00
```

---

## Comparison with RTH Sweep Strategy

| Feature | Sweep Mean Reversion | RTH Sweep Mean Reversion |
|---------|---------------------|-------------------------|
| Range Type | Rolling (N bars) | Session-based (time window) |
| Session Filter | None | Yes (trade window) |
| VWAP Filter | No | Yes |
| Timezone | Any | Chicago |
| Complexity | Simple | Advanced |
| Best For | Any market, any time | Index futures, RTH session |

---

## Target Modes

### Midpoint Target
- Exit entire position at range midpoint
- Higher win rate, smaller average win
- Best for choppy conditions

### Opposite Boundary Target
- Exit entire position at opposite side of range
- Lower win rate, larger average win
- Best when expecting full mean reversion

---

## Optimization Tips

### Range Period Selection

| Period | Character | Best For |
|--------|-----------|----------|
| 10-15 | Very responsive, many signals | Scalping, 1-5 min charts |
| 20-30 | Balanced | 5-15 min charts |
| 40-50 | Slower, fewer signals | 30-60 min charts |

### Stop Distance
- Tighter stops (3-5 pts): Higher frequency, more stop-outs
- Wider stops (8-12 pts): Lower frequency, more room to work

### Combining with Other Filters
Consider adding:
- Time-of-day filter (avoid low-volume periods)
- Trend filter (only trade sweeps against trend for mean reversion)
- Volatility filter (skip when ATR is too high or too low)

---

## Visual Indicators

- **Range High** (Red): Rolling highest high
- **Range Low** (Green): Rolling lowest low
- **Midpoint** (Yellow dashed): Middle of range
- **Entry Markers**: Triangles at entry points

---

## When to Use This Strategy

**Best Conditions:**
- Range-bound markets
- When you want a simple, universal approach
- Markets without clear session boundaries
- 24-hour markets (Forex, Crypto)

**Avoid When:**
- Strong trending conditions
- Breakout days
- High-impact news events

---

## Simplicity vs. Sophistication

This strategy trades off sophistication for simplicity:

**Advantages:**
- Works on any instrument, any timeframe
- Easy to understand and optimize
- No timezone/session complexity
- Quick to backtest

**Disadvantages:**
- No session context (morning ranges are different from afternoon)
- No volume/VWAP filtering
- May trigger on meaningless sweeps
- No "one attempt per side" logic

For index futures during regular trading hours, consider the RTH Sweep Mean Reversion strategy instead.
