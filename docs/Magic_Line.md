# Magic Line Strategy v1.0

A futures trading strategy built around a regressive support/resistance level called the Magic Line (LB). Trades long when price is above LB (support) and short when below LB (resistance). Includes Basic Trend, Side-Exit, and Table-Top pattern families.

---

## Strategy Overview

**Type:** Adaptive S/R Strategy (Auto-Trading)
**Direction:** Long and Short
**Best Timeframe:** Any (chart-inherited)
**Best Markets:** All Futures (ES, NQ, YM, CL, GC, etc.)
**Timezone:** America/New_York

### Core Concept

The Magic Line (LB) is a regressive support/resistance level calculated as:
```
lowerBand = lowest(low, length)
LB = highest(lowerBand, length)
```

- **Bullish bias:** close >= LB (LB acts as support, prefer longs)
- **Bearish bias:** close < LB (LB acts as resistance, prefer shorts)

---

## Setup Families

### 1. Basic Trend Trades

Simple bounce/rejection and break-and-retest patterns.

**LONG_SUPPORT_BOUNCE:**
- Bias is bullish (close >= LB)
- Price touches or undercuts LB (within tolerance)
- Close back above LB confirms the bounce
- Stop: Below the touch low + buffer

**SHORT_RESISTANCE_REJECT:**
- Bias is bearish (close < LB)
- Price touches or overcuts LB (within tolerance)
- Close back below LB confirms the rejection
- Stop: Above the touch high + buffer

**LONG_BREAK_AND_RETEST:**
- Price breaks above LB (bias changes from bearish to bullish)
- Within N bars, price retests LB from above
- Close holds above LB on retest
- Stop: Below retest low + buffer

**SHORT_BREAK_AND_RETEST:**
- Price breaks below LB (bias changes from bullish to bearish)
- Within N bars, price retests LB from below
- Close holds below LB on retest
- Stop: Above retest high + buffer

### 2. Side-Exit (A/B/C)

Price presses into LB and exits sideways before resolving.

**Side-Exit A (Most Aggressive):**
- Price touches LB with a rejection candle
- Bullish: Lower wick > body, close > open
- Bearish: Upper wick > body, close < open
- Entry on the rejection candle close

**Side-Exit B (Moderate):**
- Price touches LB
- Then breaks a minor swing high/low after the touch
- Entry on the structure break confirmation
- Stop: Below/above the original touch extreme

**Side-Exit C (Most Conservative):**
- Price touches LB
- Breaks minor structure (swing)
- Retests the break level or LB
- Holds above/below on retest
- Entry on the hold confirmation
- Stop: Below/above the retest extreme

### 3. Table-Top (A/B)

Price flattens against LB as a horizontal barrier, then breaks.

**Table-Top A:**
- Multiple touches near LB (at least 2)
- Builds a "table" base with defined high/low
- Price breaks above the table high (bullish) or below the table low (bearish)
- Stop: Opposite side of the table base

**Table-Top B (With Adjustment):**
- Table-top base detected (2+ touches)
- An adjustment step occurs (price moves slightly in trade direction)
- Then breaks the horizontal level
- Stop: Below/above the adjustment extreme

---

## Settings Reference

### Magic Line Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Lookback Length | 20 | Bars for LB calculation |
| LB Slope Lookback | 3 | Bars for slope comparison |
| LB Slope Filter | false | Require LB slope not against trade |
| LB Line | Yellow, 2px | Line display style |
| Bar Coloring | true | Color bars by bias |

### Setups Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Setup Family | 0 (All) | 0=All, 1=Basic, 2=SideExit, 3=TableTop |
| Direction Mode | 0 (Both) | 0=Both, 1=Long Only, 2=Short Only |
| Close Confirmation | true | Require bar close for triggers |
| Max Retest Bars | 6 | Bars allowed for retest patterns |
| Touch Tolerance | 4 ticks | How close to LB counts as a touch |

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Restrict to Window | false | Limit trading to specific hours |
| Trade Start | 0930 | Window start (HHMM) |
| Trade End | 1600 | Window end (HHMM) |
| Max Trades/Day | 2 | Daily trade limit |
| One Trade At A Time | true | Only one open position |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Stop Loss | true | Use stop loss |
| Stop Mode | 1 (Structural) | 0=Fixed ticks, 1=Structural+buffer |
| Stop Buffer (ticks) | 20 | Buffer for structural stop or fixed distance |
| Contracts | 1 | Position size |

### Exits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Exit Model | 0 (TP1/TP2) | 0=TP1/TP2, 1=RR Multiple, 2=Trail, 3=Time |
| TP1 (R multiple) | 1.0 | First target |
| TP2 (R multiple) | 2.0 | Second target |
| Partial at TP1 | true | Take partial at TP1 |
| Partial % | 50 | Percentage to close at TP1 |
| Time Exit | false | Enable time-based exit |
| Time Exit Time | 1215 | Exit time (HHMM) |

### EOD Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Force Flat EOD | true | Flatten at end of day |
| EOD Time | 1640 | Flatten time (HHMM) |

---

## Exit Models

### TP1/TP2 (Default)
- Partial exit at TP1 (default 1R)
- Stop moves to breakeven after TP1
- Full exit at TP2 (default 2R)

### RR Multiple
- Single target at TP2 R-multiple
- No partial exit
- All-or-nothing

### Trail After TP1
- Partial exit at TP1
- Stop moves to breakeven
- Trailing stop engages, ratchets with price
- Trail distance = TP1 distance from entry

### Time Exit
- Closes position at specified time
- Independent of P&L

---

## Trade Flow Examples

### Example 1: Support Bounce Long

```
LB = 5100.00 (ES, 5-min chart)
Bias: Bullish (close >= LB)

1. Price dips: Low = 5100.25 (within 4-tick tolerance of LB)
2. Bar closes at 5102.00 (above LB) -> Confirmed
3. Long entry at 5102.00

Stop: 5100.25 - 20 ticks (5.00) = 5095.25 (structural)
Risk: 6.75 points
TP1: 5108.75 (1R)
TP2: 5115.50 (2R)

Result: Partial 50% at TP1, runner to TP2
```

### Example 2: Break-and-Retest Short

```
LB = 4950.00
Bias was: Bullish, then close breaks below LB -> Bearish

1. Break bar: Close = 4948.00 (below LB)
2. 3 bars later: High = 4950.50 (retests LB from below, within tolerance)
3. Close = 4947.00 (holds below LB) -> Confirmed
4. Short entry at 4947.00

Stop: 4950.50 + 20 ticks (5.00) = 4955.50
Risk: 8.50 points
TP1: 4938.50 (1R)
TP2: 4930.00 (2R)
```

### Example 3: Side-Exit B Long

```
LB = 21500.00 (NQ)

1. Price touches LB: Low = 21501.00 (within tolerance)
2. Touch bar extreme: 21498.00
3. Minor swing high develops at 21520.00
4. Next bar closes above 21520.00 -> Structure break confirmed
5. Long entry on break

Stop: 21498.00 - 20 ticks (5.00) = 21493.00
```

### Example 4: Table-Top A Short

```
LB = 18300.00
Bias: Bearish

1. Touch 1: High = 18299.50
2. Touch 2: High = 18300.25
3. Table base: Low = 18280.00, High = 18300.25
4. Price breaks below 18280.00 with close confirmation
5. Short entry

Stop: 18300.25 + 20 ticks (5.00) = 18305.25
```

---

## LB Slope Filter

When enabled, the slope filter adds trend alignment:

- **LB rising** (LB > LB[slopeBars]): Only allow long trades
- **LB falling** (LB < LB[slopeBars]): Only allow short trades
- **LB flat**: Both directions allowed

This filter is optional and off by default. Enable it for higher-conviction trend-aligned trades.

---

## Tips for Success

1. **Start with Basic Trend Trades** - Support Bounce and Resistance Reject are the simplest setups

2. **Use close confirmation** - More stable signals, less noise

3. **Structural stops are recommended** - They adapt to the actual price action at the touch point

4. **Side-Exit B is a good balance** - More confirmation than A, less waiting than C

5. **Table-Top needs patience** - Wait for 2+ touches before looking for breaks

6. **Adjust touch tolerance per instrument** - Wider for volatile instruments (CL, NQ), tighter for calmer ones (ES)

7. **LB length matters** - Shorter = more responsive, longer = more stable. Test 10-30 range.

---

## Disclaimer

This strategy is provided for educational purposes. Past performance does not guarantee future results. Always test thoroughly in simulation before trading live. Trading futures involves substantial risk of loss.
