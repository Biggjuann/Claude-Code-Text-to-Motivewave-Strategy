# 6-10am Range Sweep Mean Reversion Strategy

A focused mean reversion strategy that trades sweeps of the pre-market/early session range during a narrow 30-minute window.

---

## Strategy Overview

**Type:** Mean Reversion
**Direction:** Long and Short
**Best Timeframe:** 5-minute, 15-minute
**Best Markets:** ES, NQ, MES, MNQ (Index Futures)
**Timezone:** America/New_York (Eastern)

### Core Concept

1. Build a range during the 6:00-10:00 AM ET window (pre-market + first 30 min)
2. Only take trades during the narrow "early window" (10:00-10:30 AM ET)
3. This captures the high-probability period right after the range completes
4. Configurable stop loss modes and multiple target options

---

## What Makes This Different

- **Narrow Trade Window**: Only 30 minutes of trading exposure
- **Pre-Market Range**: Captures overnight activity + opening move
- **Flexible Stop Modes**: Fixed from entry OR structural (beyond range)
- **Three Target Modes**: Midpoint only, opposite boundary, or partial split

---

## Entry Logic

### Long Entry (Sweep Low)
- Range is complete (after 10:00 AM ET)
- Within early trade window (10:00-10:30 AM ET)
- Price swept below range low
- Close back inside range (if required)
- Under max trades limit, long not used today (if one-attempt enabled)

### Short Entry (Sweep High)
- Range is complete (after 10:00 AM ET)
- Within early trade window (10:00-10:30 AM ET)
- Price swept above range high
- Close back inside range (if required)
- Under max trades limit, short not used today (if one-attempt enabled)

---

## Settings Reference

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Range Start (HHMM) | 600 | Start of range building (6:00 AM ET) |
| Range End (HHMM) | 1000 | End of range building (10:00 AM ET) |
| Trade Start (HHMM) | 1000 | Start of trade window |
| Trade End (HHMM) | 1030 | End of trade window |

### Sweep Rules Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Use Lookback Sweep | false | Check multiple bars for sweep |
| Lookback Bars | 12 | Number of bars to check |
| Require Close Back Inside | true | Must close inside range after sweep |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Contracts | 1 | Position size |
| Enable Stop Loss | true | Master stop toggle |
| Stop Mode | 1 (Beyond Range) | 0=Fixed from entry, 1=Beyond range boundary |
| Stop Points | 10.0 | Stop distance or buffer |

### Targets Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Target Mode | 0 (Midpoint) | 0=Midpoint, 1=Opposite boundary, 2=Both |
| Partial % at Midpoint | 50 | Percent to exit at first target (mode 2 only) |

### Limits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Max Trades Per Day | 1 | Total entries allowed |
| One Attempt Per Side | true | Only one long and one short attempt per day |

---

## Stop Loss Modes Explained

### Mode 0: Fixed Points from Entry
- Stop is placed X points from your entry price
- Example: Entry at 4510, Stop Points = 10 → Stop at 4500 (long)
- **Best for:** Consistent risk per trade

### Mode 1: Beyond Range + Buffer (Default)
- Stop is placed beyond the swept range boundary
- Example: Range Low = 4505, Stop Points = 10 → Stop at 4495 (long)
- **Best for:** Structural invalidation levels

---

## Target Modes Explained

### Mode 0: Range Midpoint Only
- Exit entire position at range midpoint
- **Best for:** Conservative, high win-rate approach

### Mode 1: Opposite Range Boundary
- Exit entire position at opposite side of range
- **Best for:** Capturing full mean reversion move

### Mode 2: Partial at Midpoint + Runner
- Exit partial % at midpoint
- Hold remainder for opposite boundary
- **Best for:** Balanced risk/reward

---

## Example Trade

```
6:00-10:00 AM ET Range:
- High: 4525.00
- Low: 4508.00
- Midpoint: 4516.50

At 10:15 AM ET:
- Price drops to 4506.00 (swept below 4508 low)
- Candle closes at 4510.00 (back inside range)

Entry: LONG at 4510.00
Stop (Mode 1): 4498.00 (4508 - 10 pts buffer)

Target Mode 0: Exit all at 4516.50
Target Mode 1: Exit all at 4525.00
Target Mode 2: Exit 50% at 4516.50, remainder at 4525.00
```

---

## Why the Narrow Window?

The 10:00-10:30 AM ET window is chosen because:

1. **Range is fresh**: Just completed, levels are most relevant
2. **Volume spike**: Often increased activity after 10 AM
3. **Trapped traders**: Breakout attempts in first 30 min often fail
4. **Limited exposure**: Only 30 minutes of risk per day
5. **Avoid chop**: Later in day, range levels become less meaningful

---

## Optimization Tips

1. **Extend Trade Window**: Try 10:00-11:00 for more opportunities
2. **Tighten Stop**: Use Mode 0 with smaller points for tighter risk
3. **Target Mode 2**: Best balance of win rate and profit factor
4. **Single Trade**: Keep max trades at 1 for highest quality
