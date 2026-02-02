# ICT Market Maker Buy Model (MMBM) Strategy

An ICT-style strategy that captures bullish reversals after sell-side liquidity is swept, followed by a market structure shift and fair value gap entry.

---

## Strategy Overview

**Type:** ICT / Smart Money Concepts
**Direction:** Long Only
**Best Timeframe:** 5-minute, 15-minute
**Best Markets:** ES, NQ, Forex Majors
**Timezone:** America/New_York (Eastern)

### Core Concept (ICT Methodology)

The Market Maker Buy Model follows this sequence:

1. **Identify Sell-Side Liquidity (SSL)**: Levels where stop losses are clustered (PDL, swing lows, equal lows)
2. **Wait for SSL Sweep**: Price takes out the liquidity (trades below SSL)
3. **Confirm Market Structure Shift (MSS)**: Price breaks above a recent swing high
4. **Enter on Fair Value Gap (FVG)**: Retracement into the imbalance created by the displacement

This model captures the "smart money" accumulation pattern where liquidity is grabbed before a reversal.

---

## The ICT Sequence

```
     Dealing Range High (PDH)
     ─────────────────────────
              │
              │  ← Premium Zone (Sell Interest)
              │
     ═══════════════════════════  ← Equilibrium (50%)
              │
              │  ← Discount Zone (Buy Interest)
              │
     ─────────────────────────
     Dealing Range Low (PDL) ← SSL Level
              │
              ▼
         [SSL SWEEP] ← Price takes liquidity
              │
              ▲
         [MSS UP] ← Breaks swing high
              │
         [FVG FORMS] ← Displacement creates gap
              │
         [ENTRY] ← Buy on retracement to FVG
```

---

## Entry Logic

### Prerequisites
1. Dealing range established (PDH/PDL from prior day)
2. Price is in **discount** (below equilibrium)
3. Within trade session and kill zone

### Entry Sequence
1. **SSL Sweep Detected**: Price trades below SSL by minimum ticks AND closes back above
2. **MSS Confirmed**: Price closes above the most recent swing high with displacement
3. **Bullish FVG Detected**: Gap between candle bodies (bar[2].low > bar[0].high)
4. **Entry Signal**: Generated when all conditions align

---

## Settings Reference

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Trade Start (HHMM) | 830 | Start of trade window |
| Trade End (HHMM) | 1200 | End of trade window |
| Kill Zone | 0 (NY AM) | 0=NY AM, 1=NY PM, 2=London |

### EOD Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Force Flat at EOD | true | Close positions at end of day |
| EOD Close Time | 1640 | Time to flatten (4:40 PM ET) |
| Cancel Working Orders | true | Cancel pending setups at EOD |

### Dealing Range Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Discount Threshold | 0.5 | Price must be below this % of range (0.5 = equilibrium) |

### Liquidity Tab

| Setting | Default | Description |
|---------|---------|-------------|
| SSL Mode | 0 (PDL) | 0=PDL, 1=Swing Low, 2=Equal Lows |
| Swing Lookback | 50 | Bars to search for swing/equal lows |
| Min Sweep Penetration | 2 | Minimum ticks below SSL |
| Require Close Back | true | Must close back above SSL |

### Structure Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Swing Strength | 2 | Bars left/right for swing detection |
| Min Displacement Body | 8 | Minimum candle body (ticks) for MSS |

### Entry Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Entry Model | 0 (FVG) | 0=FVG, 1=Order Block |
| Min FVG Size | 2 | Minimum gap size (ticks) |
| Entry Price | 1 (Midpoint) | 0=Top, 1=Midpoint, 2=Bottom of zone |
| Max Bars to Fill | 30 | Cancel if not filled in X bars |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Contracts | 1 | Position size |
| Stop Mode | 1 (Below Sweep) | 0=Fixed, 1=Below Sweep, 2=Below Zone, 3=Below PDL |
| Stop Ticks | 20 | Stop distance or buffer |

### Targets Tab

| Setting | Default | Description |
|---------|---------|-------------|
| TP Mode | 0 (RR) | 0=RR Multiple, 1=Equilibrium, 2=PDH |
| RR Multiple | 2.0 | Risk:Reward ratio |
| Enable Partial | true | Take partial profits |
| Partial % | 50 | Percentage at TP1 |

---

## Kill Zones Explained

ICT emphasizes trading during high-probability time windows:

| Kill Zone | Time (ET) | Characteristics |
|-----------|-----------|-----------------|
| NY AM | 8:30-11:00 | Highest volume, news events |
| NY PM | 1:30-4:00 | Afternoon continuation/reversal |
| London | 3:00-5:00 | European session overlap |

---

## SSL Modes Explained

### Mode 0: PDL (Prior Day Low)
- Uses yesterday's low as the liquidity level
- Most common and reliable reference

### Mode 1: Swing Low
- Finds the lowest fractal swing low in lookback period
- More dynamic, adapts to current structure

### Mode 2: Equal Lows
- Finds clusters of similar lows (within tolerance)
- Identifies "engineered liquidity" pools

---

## Example Trade

```
Prior Day:
- PDH: 4550.00
- PDL: 4520.00 (SSL Level)
- Equilibrium: 4535.00

Current Day at 9:15 AM:
- Price drops to 4518.00 (swept 4520 by 2+ ticks)
- Closes at 4522.00 (back above SSL ✓)
→ SSL SWEEP CONFIRMED

Swing high at 4528.00 identified

At 9:25 AM:
- Strong bullish candle closes at 4532.00
- Body size > 8 ticks ✓
- Broke above 4528 swing high ✓
→ MSS CONFIRMED

FVG detected between 4525-4528

Entry: LONG at 4526.50 (FVG midpoint)
Stop: 4516.00 (sweep low 4518 - 2 ticks buffer)
Risk: 10.50 points

TP1: 4535.00 (equilibrium) - exit 50%
TP2: 4547.00 (entry + 2R) - exit remaining
```

---

## Visual Indicators

- **PDH** (Red dashed): Prior day high / dealing range top
- **PDL** (Green dashed): Prior day low / dealing range bottom
- **Equilibrium** (Yellow dashed): 50% level
- **SSL Level** (Orange solid): Sell-side liquidity reference
- **Entry Markers**: Triangle at entry point

---

## Tips for Success

1. **Trade in Kill Zones**: Avoid trading outside designated times
2. **Wait for Clean Sweeps**: Price should trade through, not just touch
3. **Displacement Matters**: MSS candle should have conviction (large body)
4. **Don't Chase**: If FVG doesn't fill, don't force the trade
5. **Respect EOD**: Let the strategy flatten before the close
