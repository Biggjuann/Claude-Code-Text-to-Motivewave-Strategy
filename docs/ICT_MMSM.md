# ICT Market Maker Sell Model (MMSM) Strategy

An ICT-style strategy that captures bearish reversals after buy-side liquidity is swept, followed by a market structure shift down and bearish fair value gap entry.

---

## Strategy Overview

**Type:** ICT / Smart Money Concepts
**Direction:** Short Only
**Best Timeframe:** 5-minute, 15-minute
**Best Markets:** ES, NQ, Forex Majors
**Timezone:** America/New_York (Eastern)

### Core Concept (ICT Methodology)

The Market Maker Sell Model follows this sequence:

1. **Identify Buy-Side Liquidity (BSL)**: Levels where stop losses are clustered (PDH, swing highs, equal highs)
2. **Wait for BSL Sweep**: Price takes out the liquidity (trades above BSL)
3. **Confirm Market Structure Shift (MSS) Down**: Price breaks below a recent swing low
4. **Enter on Bearish Fair Value Gap (FVG)**: Retracement into the imbalance created by the displacement

This model captures the "smart money" distribution pattern where liquidity is grabbed before a reversal down.

---

## The ICT Sequence

```
     Dealing Range High (PDH) ← BSL Level
     ─────────────────────────
              ▲
         [BSL SWEEP] ← Price takes liquidity
              │
              ▼
         [MSS DOWN] ← Breaks swing low
              │
         [FVG FORMS] ← Displacement creates gap
              │
         [ENTRY] ← Sell on retracement to FVG
              │
              │  ← Premium Zone (Sell Interest)
              │
     ═══════════════════════════  ← Equilibrium (50%)
              │
              │  ← Discount Zone (Target Area)
              │
     ─────────────────────────
     Dealing Range Low (PDL) ← Target
```

---

## Entry Logic

### Prerequisites
1. Dealing range established (PDH/PDL from prior day)
2. Price is in **premium** (above equilibrium)
3. Within trade session and kill zone

### Entry Sequence
1. **BSL Sweep Detected**: Price trades above BSL by minimum ticks AND closes back below
2. **MSS Confirmed**: Price closes below the most recent swing low with displacement
3. **Bearish FVG Detected**: Gap between candle bodies (bar[2].high < bar[0].low)
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
| Premium Threshold | 0.5 | Price must be above this % of range (0.5 = equilibrium) |

### Liquidity Tab

| Setting | Default | Description |
|---------|---------|-------------|
| BSL Mode | 0 (PDH) | 0=PDH, 1=Swing High, 2=Equal Highs |
| Swing Lookback | 50 | Bars to search for swing/equal highs |
| Min Sweep Penetration | 2 | Minimum ticks above BSL |
| Require Close Back | true | Must close back below BSL |

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
| Stop Mode | 1 (Above Sweep) | 0=Fixed, 1=Above Sweep, 2=Above Zone, 3=Above PDH |
| Stop Ticks | 20 | Stop distance or buffer |

### Targets Tab

| Setting | Default | Description |
|---------|---------|-------------|
| TP Mode | 0 (RR) | 0=RR Multiple, 1=Equilibrium, 2=PDL |
| RR Multiple | 2.0 | Risk:Reward ratio |
| Enable Partial | true | Take partial profits |
| Partial % | 50 | Percentage at TP1 |

---

## BSL Modes Explained

### Mode 0: PDH (Prior Day High)
- Uses yesterday's high as the liquidity level
- Most common and reliable reference

### Mode 1: Swing High
- Finds the highest fractal swing high in lookback period
- More dynamic, adapts to current structure

### Mode 2: Equal Highs
- Finds clusters of similar highs (within tolerance)
- Identifies "engineered liquidity" pools

---

## Stop Loss Modes (For Shorts)

### Mode 0: Fixed Ticks from Entry
- Stop placed X ticks above entry price
- Example: Entry 4540, Stop Ticks 20 → Stop at 4545 (5 pts = 20 ticks on ES)

### Mode 1: Above Sweep High (Default)
- Stop placed above the highest point of the sweep
- Most logical invalidation point

### Mode 2: Above Zone High
- Stop placed above the top of the FVG/entry zone
- Tighter stop, higher risk of being stopped out

### Mode 3: Above PDH
- Stop placed above the prior day high
- Widest stop, gives most room

---

## Example Trade

```
Prior Day:
- PDH: 4550.00 (BSL Level)
- PDL: 4520.00
- Equilibrium: 4535.00

Current Day at 9:45 AM:
- Price rallies to 4552.50 (swept 4550 by 2.5+ pts)
- Closes at 4548.00 (back below BSL ✓)
→ BSL SWEEP CONFIRMED

Swing low at 4542.00 identified

At 9:55 AM:
- Strong bearish candle closes at 4538.00
- Body size > 8 ticks ✓
- Broke below 4542 swing low ✓
→ MSS DOWN CONFIRMED

Bearish FVG detected between 4544-4541

Entry: SHORT at 4542.50 (FVG midpoint)
Stop: 4554.50 (sweep high 4552.50 + 2 pts buffer)
Risk: 12 points

TP1: 4535.00 (equilibrium) - cover 50%
TP2: 4518.50 (entry - 2R) - cover remaining
```

---

## Visual Indicators

- **PDH** (Red dashed): Prior day high / dealing range top
- **PDL** (Green dashed): Prior day low / dealing range bottom
- **Equilibrium** (Yellow dashed): 50% level
- **BSL Level** (Orange solid): Buy-side liquidity reference
- **Entry Markers**: Downward triangle at entry point

---

## MMBM vs MMSM Comparison

| Aspect | MMBM (Buy) | MMSM (Sell) |
|--------|------------|-------------|
| Liquidity Type | SSL (Sell-Side) | BSL (Buy-Side) |
| Liquidity Level | PDL, Swing Lows | PDH, Swing Highs |
| Sweep Direction | Price goes DOWN | Price goes UP |
| MSS Direction | Break UP | Break DOWN |
| Entry Zone | Below sweep | Above sweep |
| Required Zone | Discount | Premium |
| Stop Placement | Below | Above |
| Target Direction | Up to PDH | Down to PDL |

---

## Tips for Success

1. **Trade in Kill Zones**: Most reliable setups occur 8:30-11:00 AM ET
2. **Wait for Clean Sweeps**: Price should trade through convincingly
3. **Displacement is Key**: MSS candle should show strong selling pressure
4. **Premium Zone Entry**: Don't short in discount - wait for retracement
5. **Respect EOD**: Strategy automatically flattens at 4:40 PM
6. **Combine with MMBM**: Use both models to trade both directions based on context
