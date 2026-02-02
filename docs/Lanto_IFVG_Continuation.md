# Lanto-style IFVG Continuation (1m, NQ/MNQ) v1.0

A trend-aligned IFVG (Inverse Fair Value Gap) continuation strategy designed for 1-minute charts with displacement filters, bias model, and fixed-R exits.

> **Note:** This is an auto-trading strategy optimized for NQ/MNQ on 1-minute charts with strict session gating and advanced market state filters.

---

## Strategy Overview

**Type:** IFVG Continuation (Auto-Trading)
**Direction:** Long and Short
**Best Timeframe:** 1-minute
**Best Markets:** NQ, MNQ, ES, MES
**Timezone:** America/New_York

### Core Concept

This strategy identifies Inverse Fair Value Gaps (IFVGs) created by displacement moves, then enters on retracement back into the zone when aligned with the trend bias. It uses a fixed risk-reward framework with partials and breakeven management.

**Key Features:**
- IFVG zone detection (inverse FVG from displacement)
- Displacement filter (1.6x average range, 2+ consecutive bars)
- Chop filter (overlap ratio method)
- Bias model (EMA 9/21 slope + structure)
- Session gating (NY AM, optional NY PM)
- 10-minute cooldown between trades
- Fixed-R exits (2R target) with partial at 1R (50%)
- Move stop to breakeven at 1R
- Time stop (25 bars max, progress check at 10 bars)
- Forced flat at 15:55 ET

---

## What is an IFVG?

An **Inverse Fair Value Gap (IFVG)** is created when:

1. A strong displacement move creates a regular FVG (3-candle imbalance)
2. Price then trades back through the midpoint of that FVG
3. The zone "inverts" and becomes a continuation zone in the new direction

**Example - Bullish IFVG:**
1. Strong bearish displacement creates a bearish FVG
2. Price reverses and trades above the FVG midpoint
3. The zone is now a bullish IFVG for long entries on retrace

---

## Trade Logic

### Long Entry Sequence

1. **Bias Check:** EMA 9 > EMA 21 with positive slope, OR bullish structure (higher lows + swing high break)
2. **Displacement:** 2+ consecutive bullish bars with range >= 1.6x average range
3. **FVG Formation:** Bullish 3-candle imbalance detected
4. **IFVG Signal:** Prior bearish FVG inverted (price closed above midpoint)
5. **Entry:** Price retraces into IFVG zone, rejection candle confirms
6. **Stop:** Below zone bottom or last swing low (whichever lower) + buffer
7. **Target:** 2R from entry

### Short Entry Sequence

1. **Bias Check:** EMA 9 < EMA 21 with negative slope, OR bearish structure (lower highs + swing low break)
2. **Displacement:** 2+ consecutive bearish bars with range >= 1.6x average range
3. **FVG Formation:** Bearish 3-candle imbalance detected
4. **IFVG Signal:** Prior bullish FVG inverted (price closed below midpoint)
5. **Entry:** Price retraces into IFVG zone, rejection candle confirms
6. **Stop:** Above zone top or last swing high (whichever higher) + buffer
7. **Target:** 2R from entry

---

## Settings Reference

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable NY AM | true | Trade during NY AM session |
| NY AM Start | 0930 | NY AM session start |
| NY AM End | 1130 | NY AM session end |
| Enable NY PM | false | Trade during NY PM session |
| NY PM Start | 1330 | NY PM session start |
| NY PM End | 1530 | NY PM session end |
| Max Trades/Window | 2 | Maximum trades per session window |
| Cooldown (minutes) | 10 | Wait time between trades |

### Bias Model Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Bias Filter | true | Require trend alignment |
| Fast EMA Period | 9 | Fast moving average period |
| Slow EMA Period | 21 | Slow moving average period |
| Slope Lookback | 3 | Bars to measure MA slope |
| Enable Structure | true | Use swing structure for bias |
| Pivot Left | 2 | Left bars for pivot detection |
| Pivot Right | 2 | Right bars for pivot detection |

### Filters Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Require Displacement | true | Only trade after displacement |
| Displacement Lookback | 20 | Bars for average range calculation |
| Min Impulse Multiple | 1.6 | Range multiple to qualify as displacement |
| Min Impulse Bars | 2 | Consecutive displacement bars required |
| Avoid Chop | true | Filter out choppy conditions |
| Chop Lookback | 15 | Bars for chop calculation |
| Max Overlap Ratio | 0.55 | Maximum overlap ratio (higher = more chop) |

### IFVG Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Min Gap Size (points) | 4.0 | Minimum FVG size to qualify |
| Max Zone Age (bars) | 30 | Bars before zone expires |
| Max Active Zones | 6 | Maximum zones to track |
| Entry Level | Mid | Entry at zone midpoint or edge |

### Entry Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Long | true | Allow long entries |
| Enable Short | true | Allow short entries |
| Require Rejection | true | Wait for rejection candle |
| Max Wait Bars | 3 | Max bars to wait for confirmation |
| Entry Buffer (points) | 1.0 | Buffer for entry price |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Sizing Mode | Fixed | 0=Fixed, 1=Risk-Based |
| Fixed Contracts | 1 | Contracts when using fixed mode |
| Account Size | 50000 | Account size for risk-based sizing |
| Risk % | 0.5 | Risk per trade as % of account |
| Max Contracts | 5 | Maximum position size |
| Stop Buffer (points) | 2.0 | Buffer below/above stop level |
| Max Stop (points) | 40.0 | Maximum stop distance (invalidates trade if exceeded) |
| Enable Daily Limit | true | Stop after daily loss limit |
| Max Daily Loss (R) | 2.0 | Maximum daily loss in R multiples |

### Exits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Target R | 2.0 | Target as multiple of risk |
| Enable Partial | true | Take partial at first target |
| Partial at R | 1.0 | R-multiple for partial exit |
| Partial % | 50 | Percentage to close at partial |
| Move to BE | true | Move stop to breakeven |
| BE at R | 1.0 | R-multiple to move stop to BE |
| BE Offset (points) | 0.5 | Points above/below entry for BE |
| Enable Time Stop | true | Exit after max bars |
| Max Bars in Trade | 25 | Maximum bars before time stop |
| Progress Check | true | Exit if not progressing |
| No Progress Bars | 10 | Bars to check progress |
| Force Flat | true | Flatten at end of day |
| Flat Time | 1555 | Time to force flat (3:55 PM) |

---

## Trade Management Flow

```
Entry Signal → Position Opened → Monitoring Active
    │
    ├─► Stop Hit → Exit at Loss → Update Daily R
    │
    ├─► 1R Reached → Partial 50% → Move Stop to BE
    │   │
    │   └─► 2R Reached → Exit Runner → Update Daily R
    │
    ├─► Time Stop (25 bars) → Exit → Update Daily R
    │
    └─► Progress Check (10 bars, < 0.5R) → Exit → Update Daily R
```

---

## Example Trade (Long)

```
Setup: Lanto IFVG Long on NQ 1-minute

1. Bias: EMA 9 (21850) > EMA 21 (21840), slow MA slope positive
2. Structure: Higher lows confirmed, recent swing high break
3. Displacement: 3 consecutive bullish bars, each > 1.6x avg range
4. Bullish FVG detected: 21830.00 - 21838.00 (8 point gap)
5. Price retraces, enters zone at 21834.00
6. Rejection candle: Close > Open AND Close > 21834.00 (zone mid)
7. Long entry triggered

Stop: 21828.00 (zone bottom 21830 - 2 point buffer)
Risk: 6 points
Target 1R: 21840.00 (partial 50%)
Target 2R: 21846.00 (runner)

Result:
- Price hits 21840 → 50% closed, stop moved to 21834.50 (BE + 0.5)
- Price continues to 21846 → Runner closed at 2R
- Total result: 1.5R profit
```

---

## Displacement Detection

The displacement filter ensures we only trade after strong, directional moves:

```
Average Range = Sum of (High - Low) for last 20 bars / 20

Displacement Bar Criteria:
1. Bar Range >= Average Range × 1.6
2. Body direction matches move direction
3. At least 2 consecutive bars meeting criteria
```

This filters out setups that form during weak, indecisive price action.

---

## Chop Filter

The chop filter prevents trading during sideways, overlapping price action:

```
Overlap Ratio = Total Body Overlap / Total Body Range (over 15 bars)

If Overlap Ratio > 0.55:
    → Market is choppy, skip trade
```

Higher overlap means more back-and-forth, consolidation behavior.

---

## Tips for Success

1. **Trust the bias filter** - The EMA + structure combination provides good trend alignment

2. **Displacement is key** - IFVGs without displacement are lower probability

3. **Watch the chop filter** - If getting filtered frequently, market may not be trending

4. **Respect the cooldown** - 10 minutes between trades prevents revenge trading

5. **Monitor daily R** - The 2R daily loss limit protects your account

6. **Optimal time** - NY AM (9:30-11:30) typically has best setups

7. **Consider partials** - Taking 50% at 1R locks in profit while keeping upside

8. **Progress check matters** - Trades not moving by 10 bars often fail

---

## Disclaimer

This strategy is provided for educational purposes. Past performance does not guarantee future results. Always test thoroughly in simulation before trading live. Trading futures involves substantial risk of loss.
