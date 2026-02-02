# MTF MA Model Study

A multi-timeframe moving average trend filter with pivot-confirmed entries and automatic order block visualization.

---

## Strategy Overview

**Type:** Trend Following Indicator
**Direction:** Long and Short signals
**Best Timeframe:** 5-minute, 15-minute
**Best Markets:** All futures, Forex, Crypto
**Timezone:** Any (no session filtering)

### Core Concept

This indicator uses a dual-stack approach for high-probability trend signals:

1. **LTF Entry Stack** (5/13/34): Fast-moving entry timing
2. **HTF Filter Stack** (34/55/200): Higher timeframe trend filter
3. **Pivot Confirmation**: Signals only confirmed on pivot break
4. **Order Block Visualization**: Automatic OB lines at signal pivots

---

## Signal Logic

### Pending Long Signal

Created when ALL conditions are met:
- Entry stack bullish: Fast MA > Mid MA > Slow MA
- Price above all entry MAs
- HTF stack bullish: HTF Fast > HTF Mid > HTF Slow
- Price above all HTF MAs
- Trigger: Entry Fast MA crosses above Entry Mid MA

### Pending Short Signal

Created when ALL conditions are met:
- Entry stack bearish: Fast MA < Mid MA < Slow MA
- Price below all entry MAs
- HTF stack bearish: HTF Fast < HTF Mid < HTF Slow
- Price below all HTF MAs
- Trigger: Entry Fast MA crosses below Entry Mid MA

### Confirmation

- **Long Confirmed**: When close > most recent pivot high
- **Short Confirmed**: When close < most recent pivot low

---

## Settings Reference

### Moving Averages Tab

| Setting | Default | Description |
|---------|---------|-------------|
| MA Method | EMA | SMA, EMA, WMA, VWMA, etc. |
| VW Decay | 0.85 | Decay for volume-weighted MAs |
| Entry Fast | 5 | LTF fast MA period |
| Entry Mid | 13 | LTF mid MA period |
| Entry Slow | 34 | LTF slow MA period |

### HTF Filter Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Mode | Auto | Auto or Manual HTF selection |
| Manual HTF | 60 | Minutes (when Manual mode) |
| HTF Fast | 34 | HTF fast MA period |
| HTF Mid | 55 | HTF mid MA period |
| HTF Slow | 200 | HTF slow MA period |

### Display Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Show Entry MAs | true | Display LTF entry MAs |
| Show HTF MAs | true | Display HTF filter MAs |
| Monochrome Mode | false | Color all MAs by stack bias |

### Order Blocks Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Show OB Lines | true | Draw order block lines |
| Extend Type | Latest | All, Latest, or None |
| Max OB Lines | 20 | Maximum lines to display |

### Position Sizing Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable | false | Enable size calculations |
| Asset Class | Futures | Forex, Futures, or Crypto |
| Account Balance | 50000 | Account size |
| Risk Mode | Percent | Percent or Fixed amount |
| Risk % | 1.0 | Percentage of account |
| Risk Amount | 500 | Fixed dollar amount |
| Point Value | 5.0 | $/point for futures |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Stop | true | Track stop levels |
| Stop Mode | Tracking | Tracking, Fixed, or Signal Bar |
| Stop Buffer | 0.0 | Buffer beyond stop level |
| Fixed Distance | 10.0 | Points for fixed stop |

---

## HTF Auto Mapping

When HTF Mode is set to "Auto", the system automatically selects an appropriate higher timeframe:

| Chart Timeframe | HTF Multiplier | Effective HTF |
|-----------------|----------------|---------------|
| 5m or less | 12x | ~1 Hour |
| 6m - 15m | 16x | ~4 Hours |
| 16m - 60m | 24x | ~1 Day |

---

## Pivot Detection

Pivots are detected using candle direction changes:

- **Pivot Low**: Bullish candle (close > open) following a bearish candle
- **Pivot High**: Bearish candle (close < open) following a bullish candle

The most recent pivots are tracked for confirmation purposes.

---

## Order Block Lines

When a signal is confirmed:

1. An OB line is drawn at the pivot price level
2. The line extends from the pivot bar to current time
3. Extension behavior depends on settings:
   - **Extend All**: All OB lines extend forward
   - **Extend Latest**: Only most recent extends
   - **Extend None**: Lines have fixed endpoints

### Invalidation

If stop tracking is enabled and price breaches the stop level, the corresponding OB line is invalidated and removed.

---

## Example Trade Setup

```
5-Minute ES Chart:

Entry Stack (LTF):
- 5 EMA: 4520.50
- 13 EMA: 4518.25
- 34 EMA: 4515.00
→ Stack bullish (5 > 13 > 34)

HTF Filter (scaled):
- HTF Fast (34×12): 4510.00
- HTF Mid (55×12): 4505.00
- HTF Slow (200×12): 4480.00
→ HTF bullish

Trigger: 5 EMA crosses above 13 EMA
→ PENDING LONG generated

Recent Pivot High: 4522.00

Bar closes at 4523.50 (> 4522.00)
→ LONG CONFIRMED

OB Line drawn at 4522.00
Stop tracked at recent swing low
```

---

## State Machine

The indicator uses a state machine with 5 states:

1. **IDLE**: No active signal
2. **PENDING_LONG**: Awaiting pivot high break
3. **PENDING_SHORT**: Awaiting pivot low break
4. **CONFIRMED_LONG**: Long signal triggered
5. **CONFIRMED_SHORT**: Short signal triggered

---

## Tips for Success

1. **Wait for confirmation**: Don't act on pending signals alone
2. **Use HTF alignment**: Signals are stronger when HTF trend matches
3. **Respect pivot levels**: They represent natural market structure
4. **Monitor OB lines**: They show key support/resistance
5. **Adjust for volatility**: Use wider stops in volatile conditions

---

## Visual Indicators

- **Entry MAs** (Blue shades): Fast (5), Mid (13), Slow (34)
- **HTF MAs** (Orange shades): Scaled from higher timeframe
- **OB Lines** (Green/Red): Order block levels
- **Markers**: Triangles at signal generation points

---

## When to Use This Study

**Best Conditions:**
- Clear trending markets
- Multiple timeframe alignment
- After major support/resistance breaks

**Avoid When:**
- Choppy, ranging markets
- During major news events
- When LTF and HTF conflict

---

## Note on Multi-Timeframe Implementation

This study uses period scaling to approximate HTF behavior on the chart timeframe. While true MTF data would be ideal, this approach provides:

- Similar smoothing characteristics
- No data gaps or synchronization issues
- Simpler computation
- Consistent results across all instruments

For true MTF analysis, consider using multiple charts with different timeframes.
