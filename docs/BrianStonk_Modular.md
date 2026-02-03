# Brian Stonk Essentials Core Engine v1.0

A comprehensive ICT-style strategy derived from Brian Stonk's concepts with proper Order Block, Breaker, FVG/IFVG, BPR, and Unicorn setup detection.

> **Note:** Educational automation derived from public content. Always validate and forward-test before live trading.

---

## Strategy Overview

**Type:** Multi-Entry ICT Strategy (Auto-Trading)
**Direction:** Long and Short
**Best Timeframe:** 1-minute (execution), 5m/15m (intraday anchor)
**Best Markets:** NQ, MNQ, ES, MES
**Timezone:** America/New_York
**Trade Window:** 13:00-15:00 ET (NY PM session)

### Core Concept

This strategy implements authentic ICT concepts with proper definitions:

1. **Order Block (OB)** - Last consecutive candle(s) before displacement
2. **Breaker** - Failed OB flip OR sweep + displacement structure
3. **Fair Value Gap (FVG)** - 3-candle imbalance with consequent encroachment
4. **Inversion (IFVG)** - FVG displaced through, flips directional role
5. **Balanced Price Range (BPR)** - Overlap zone between complementary zones
6. **Unicorn** - A+ setup: Breaker + BPR/FVG confluence

---

## ICT Concept Definitions

### Order Block (OB)

**Bullish OB:**
- One or more consecutive down-close candles
- Followed by a candle that closes through the high of the first down candle
- Displacement confirms the OB

**Bearish OB:**
- One or more consecutive up-close candles
- Followed by a candle that closes through the low of the first up candle
- Displacement confirms the OB

**Mean Threshold:** The midpoint of the OB range. Price should react at or before reaching the mean for a valid OB entry (OB1 model).

### Breaker

Two creation methods:

**Method 1: OB Violation Flip**
- A valid OB that gets violated (price closes through it)
- The OB "flips" polarity and becomes a Breaker
- Bullish Breaker = failed bearish OB
- Bearish Breaker = failed bullish OB

**Method 2: Sweep + Displacement (Structure Breaker)**
- Price sweeps a swing high/low (liquidity grab)
- Followed by displacement candle in opposite direction
- Creates a Breaker at the sweep origin

### Fair Value Gap (FVG)

**Bullish FVG:**
- Three-candle pattern
- Gap between bar[2].low and bar[0].high
- Minimum gap size: 3 points (configurable)

**Bearish FVG:**
- Three-candle pattern
- Gap between bar[2].high and bar[0].low
- Minimum gap size: 3 points (configurable)

**Consequent Encroachment (CE):** The midpoint of the FVG. Price respecting CE = bullish for FVG validity.

### Inversion (IFVG)

- An FVG that price "displaces through" (closes beyond the opposite edge)
- The FVG flips its directional role:
  - Bullish FVG → Bearish IFVG (if price closes below FVG bottom)
  - Bearish FVG → Bullish IFVG (if price closes above FVG top)
- IFVG becomes a retracement entry zone

### Balanced Price Range (BPR)

- Overlap zone between two complementary zones
- Example: IFVG overlapping with an FVG
- High-probability reversal/continuation area
- Minimum width: 2 points

### Unicorn Setup (A+ Grade)

The highest-confidence setup combining:
1. A valid Breaker zone
2. BPR or FVG zone overlapping with the Breaker
3. Price currently in the overlap region
4. Directional alignment (bullish Breaker + bullish FVG/BPR = bullish Unicorn)

---

## Entry Models

### UN1: Unicorn Entry (Highest Priority)
- Requires: Breaker + BPR/FVG overlap
- Entry: Price enters the overlap zone
- Confirmation: Rejection candle aligned with direction
- Stop: Below/above Breaker structure

### BR1: Breaker Retap Continuation
- Requires: Valid Breaker (from OB flip or structure)
- Entry: Price retraces into Breaker zone
- Confirmation: Rejection candle
- Stop: 10-15 pts default, override to structure if Breaker < 10 pts

### IF1: IFVG/BPR Flip Entry
- Requires: Valid IFVG (inverted FVG)
- Entry: Price retraces into IFVG zone
- Confirmation: Rejection candle respecting CE
- Stop: Beyond IFVG boundary

### OB1: Order Block Mean Threshold Bounce
- Requires: Valid OB (not violated)
- Entry: Price reaches OB zone, respects mean threshold
- Confirmation: Rejection candle before mean is breached
- Stop: Beyond OB structure

**Priority:** UN1 > BR1 > IF1 > OB1

---

## Timeframe Alignment

### LTF (Low Timeframe) - Execution
- 1-minute chart
- Entry timing and confirmation candles
- Zone detection and entry triggers

### Intraday Anchor
- 5m or 15m equivalent (MA period setting)
- Trend direction confirmation
- Swing structure for bias

### HTF (High Timeframe) - Bias
- 4-hour equivalent (optional filter)
- Overall trend direction
- Modes: Strict, Loose, Off

---

## Draw Liquidity

The strategy identifies and tracks liquidity targets:

### Target Types
- **Session High/Low** - Current session extremes
- **Swing High/Low** - Pivot-based swing points
- **Equal Highs/Lows** - Clustered levels indicating resting liquidity

### How It's Used
- Determines directional bias (price draws to liquidity)
- Target selection for exits
- Confluence for entry validation

---

## Settings Reference

### Presets Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Preset | 0 | 0=1m/15m/4h (Core), 1=1m/5m/4h (Substitute) |
| Enable Long | true | Allow long entries |
| Enable Short | true | Allow short entries |

### Entry Models Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Unicorn (UN1) | true | A+ Breaker+BPR/FVG setup |
| Enable Breaker (BR1) | true | Breaker retap continuation |
| Enable IFVG (IF1) | true | IFVG/BPR flip entry |
| Enable OB (OB1) | true | OB mean threshold bounce |

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Trade Start | 1300 | Trade window start (1:00 PM ET) |
| Trade End | 1500 | Trade window end (3:00 PM ET) |
| Max Trades/Day | 2 | Maximum trades per session |
| Cooldown (minutes) | 10 | Wait time between trades |
| Force Flat | true | Flatten at end of day |
| Flat Time | 1505 | Forced flat time (3:05 PM ET) |

### Timeframe Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Require Intraday Align | true | Require anchor TF alignment |
| HTF Filter Mode | 1 (Loose) | 0=Strict, 1=Loose, 2=Off |
| Intraday MA Period | 15 | Anchor trend MA period |
| Pivot Left | 3 | Left bars for swing detection |
| Pivot Right | 3 | Right bars for swing detection |

### Draw Liquidity Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Require Draw Target | true | Require identified liquidity draw |
| Use Session Liquidity | true | Track session H/L |
| Use Swing Liquidity | true | Track swing H/L |
| Use Equal H/L | true | Track equal highs/lows |

### Order Block Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Min Candles | 1 | Minimum consecutive candles for OB |
| Mean Threshold | true | Require price respect mean |

### Breaker Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Require Sweep | true | Require liquidity sweep for structure breaker |
| Require Displacement | true | Require ATR-based displacement |
| Tight Breaker Threshold | 10.0 | Points below which to override stop to structure |

### FVG/IFVG Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Min Gap (points) | 3.0 | Minimum FVG size |
| CE Respect | true | Require price respect consequent encroachment |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Stop Default | 12.0 | Default stop distance (points) |
| Stop Min | 10.0 | Minimum stop distance |
| Stop Max | 25.0 | Maximum stop distance |
| Override to Structure | true | Use structure stop if Breaker < threshold |
| Fixed Contracts | 1 | Position size |

### Targets Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Target Mode | 0 (Fixed R) | 0=Fixed R, 1=Liquidity, 2=Hybrid |
| Target R | 2.0 | Target as risk multiple |
| Enable Partial | true | Take partial at intermediate level |
| Partial R | 1.0 | R-multiple for partial |
| Partial % | 50 | Percentage to close at partial |
| Enable Runner | true | Keep runner to full target |

### Display Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Show OB Zones | true | Draw OB rectangles |
| Show Breaker Zones | true | Draw Breaker rectangles |
| Show FVG Zones | true | Draw FVG/IFVG rectangles |

---

## Trade Flow Examples

### Example 1: Unicorn Long (UN1)

```
Time: 1:20 PM ET
Entry Model: UN1 (Unicorn)

1. Bearish OB identified at 21820-21830
2. Price closes through OB → Breaker created at 21820-21830
3. Bullish FVG formed at 21815-21825
4. Overlap zone: 21820-21825 (Breaker ∩ FVG)
5. UNICORN detected!
6. Price retraces into overlap zone
7. Rejection candle: Close 21823 > Open 21821 ✓
8. Long entry at 21823

Stop: 21808 (Breaker low - buffer)
Risk: 15 points
Target: 21853 (2R)

Result: A+ setup, high probability
```

### Example 2: Breaker Retap Short (BR1)

```
Time: 1:45 PM ET
Entry Model: BR1 (Breaker)

1. Bullish OB identified at 21850-21860
2. Price closes below 21850 → OB violated
3. Bearish Breaker created at 21850-21860
4. Price retraces up into Breaker zone
5. Rejection candle: Close 21855 < Open 21858 ✓
6. Short entry at 21855

Stop: 21867 (Breaker high + buffer)
Risk: 12 points (default)
Target: 21831 (2R)

Result: Clean breaker retap continuation
```

### Example 3: IFVG Entry Long (IF1)

```
Time: 2:00 PM ET
Entry Model: IF1 (IFVG)

1. Bearish FVG detected at 21800-21810
2. Price displaces up, closes above 21810
3. FVG inverted → Bullish IFVG at 21800-21810
4. CE (midpoint) at 21805
5. Price retraces down into IFVG
6. Rejection candle at 21806 (above CE) ✓
7. Long entry at 21806

Stop: 21794 (IFVG bottom - buffer)
Risk: 12 points
Target: 21830 (2R)

Result: Clean IFVG flip with CE respect
```

### Example 4: Order Block Long (OB1)

```
Time: 2:15 PM ET
Entry Model: OB1 (OB Mean)

1. Bullish OB identified at 21780-21790
2. Mean threshold at 21785
3. Price retraces into OB zone
4. Price touches 21783 (before mean breached)
5. Rejection candle: Close 21786 > Open 21783 ✓
6. Long entry at 21786

Stop: 21775 (OB low - buffer)
Risk: 11 points
Target: 21808 (2R)

Result: OB respected mean threshold
```

---

## Bias Model

### Intraday Bias (Anchor TF)
- **Bullish:** Close > MA(period) + higher lows structure
- **Bearish:** Close < MA(period) + lower highs structure
- **Neutral:** Otherwise

### HTF Bias (Strict Mode)
- Only trade in HTF direction
- Bullish HTF = longs only
- Bearish HTF = shorts only

### HTF Bias (Loose Mode)
- Trade both directions
- Prioritize HTF-aligned trades
- Counter-trend trades require stronger confluence

---

## Tips for Success

1. **Prioritize Unicorn setups** - UN1 is the A+ grade, highest probability

2. **Breaker > OB** - Once an OB is violated, it becomes more reliable as a Breaker

3. **IFVG needs displacement** - Don't trade weak inversions without clear displacement

4. **Respect the mean** - OB1 entries should see price react before reaching the mean threshold

5. **BPR adds confluence** - Overlapping zones increase probability significantly

6. **Draw liquidity matters** - Know where price is likely heading before entry

7. **1m execution, 15m bias** - Use the 1m for timing, 15m for direction

8. **NY PM window (1-3 PM)** - This is when setups typically develop cleanly

---

## Disclaimer

This strategy is derived from publicly available concepts for educational purposes. Past performance does not guarantee future results. Always test thoroughly in simulation before trading live. Trading futures involves substantial risk of loss.
