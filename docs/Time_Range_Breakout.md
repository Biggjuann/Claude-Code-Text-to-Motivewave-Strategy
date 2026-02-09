# Time Range Breakout Strategy

Trades breakouts above a defined time-range high and breakdowns below a defined time-range low with structured risk management: initial stop, move-to-breakeven, partial take-profit at TP1, and runner management with trailing stop.

## Strategy Overview

**Type:** Range Breakout
**Direction:** Long and Short
**Best Timeframe:** 1-5 minute
**Best Markets:** All futures (MES, ES, MNQ, NQ, CL, GC)

## Core Concept

During a defined time window (default 9:30-10:00 ET), the strategy tracks the high and low to build a range. After the range window closes, it enters long on a breakout above the range high or short on a breakdown below the range low.

This is a classic breakout strategy enhanced with:
- Configurable breakout confirmation (touch vs. close)
- Move-to-breakeven after profit threshold
- Partial exit at TP1
- Runner management with trailing stop (fixed points or ATR-based)
- End-of-day forced flatten

## Entry Logic

### Range Building
1. During the range window (default 9:30-10:00 ET), track the highest high and lowest low
2. When the range window ends, validate the range size against min/max constraints
3. If valid, the range is locked and plotted

### Long Breakout
- **Touch Through:** High of bar reaches range high + offset ticks
- **Close Through:** Bar closes at or above range high + offset ticks

### Short Breakdown
- **Touch Through:** Low of bar reaches range low - offset ticks
- **Close Through:** Bar closes at or below range low - offset ticks

## Risk Management

### Initial Stop
Two modes:
- **Fixed Points:** Stop at entry +/- configurable points
- **Other Side of Range:** Stop at the opposite range boundary + buffer ticks

### Move to Breakeven
- When unrealized profit reaches the trigger threshold (default 3 pts)
- Stop moves to entry price + optional "plus" ticks (locks small profit)
- Activates independently of TP1

### TP1 (Partial Exit)
- Exit a percentage of contracts (default 50%) at TP1 distance
- After TP1, remaining contracts become "runners"
- If only 1 contract, full exit at TP1

### Runner Trailing Stop
Two modes:
- **Fixed Points:** Trail by configurable distance (default 4 pts)
- **ATR-Based:** Trail by ATR * multiplier
- By default, trailing activates only after TP1 fills
- Trail follows the best price achieved since entry

### Stop Priority (highest to lowest)
1. EOD flatten
2. Trailing stop (when active)
3. Breakeven stop (when activated)
4. Initial stop

## Settings Reference

### Range Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Range Start | 0930 | Range build window start (ET) |
| Range End | 1000 | Range build window end (ET) |
| Trade Start | 0930 | Trade window start (ET) |
| Trade End | 1600 | Trade window end (ET) |
| Min Range Pts | 2.0 | Reject ranges smaller than this |
| Max Range Pts | 50.0 | Reject ranges larger than this |

### Entry Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Breakout Mode | 1 (Close) | 0=Touch Through, 1=Close Through |
| Entry Offset | 1 tick | Buffer beyond range boundary |

### Limits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Max Trades/Day | 2 | Daily trade limit |
| One at a Time | true | Only one position open |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Contracts | 2 | Total contracts per trade |
| Stop Mode | 1 (Range) | 0=Fixed Points, 1=Other Side of Range |
| Fixed Stop | 5.0 pts | Stop distance (fixed mode) |
| Range Buffer | 2 ticks | Buffer beyond range (range mode) |
| Move to BE | true | Enable breakeven stop |
| BE Trigger | 3.0 pts | Profit needed to trigger BE |
| BE Plus | 0 ticks | Lock this much profit at BE |

### Exits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| TP1 Distance | 6.0 pts | First target distance |
| TP1 % | 50 | Percentage to close at TP1 |
| Trail Mode | 0 (Points) | 0=Fixed Points, 1=ATR |
| Trail Points | 4.0 pts | Fixed trail distance |
| ATR Period | 14 | ATR for trail calculation |
| ATR Multiplier | 2.0 | ATR multiple for trail |
| Trail After TP1 | true | Trail starts after TP1 fills |

### EOD Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Force Flat EOD | true | Close all at EOD |
| EOD Time | 1640 | Flatten time (ET) |

## Example Trade

5-Minute MES Chart:
1. **Range (9:30-10:00):** High = 5250.00, Low = 5242.00 (8 pt range, valid)
2. **Breakout:** At 10:15, bar closes at 5250.50 (above range high 5250.00 + 1 tick offset = 5250.25)
3. **Entry:** LONG 2 contracts at 5250.50
4. **Stop:** Other side of range: 5242.00 - 0.50 (2 ticks) = 5241.50
5. **BE trigger:** At 5253.50 (+3 pts), stop moves to 5250.50 (entry)
6. **TP1:** At 5256.50 (+6 pts), sell 1 contract (50%)
7. **Runner:** Trail activates. Best price 5259.00, trail 4 pts = stop at 5255.00
8. **Price continues:** Best price 5262.00, trail = stop at 5258.00
9. **Exit:** Price pulls back, runner stopped at 5258.00

## Configuration Tips

- **Narrow range sessions** (30 min) produce tighter ranges with more defined breakouts
- **Close Through** mode reduces false breakouts but may enter slightly later
- **2+ contracts** needed for TP1 partial + runner. With 1 contract, full exit at TP1
- **Range stop mode** naturally adapts stop size to volatility (wider range = wider stop)
- Increase **Max Range** for volatile instruments or widen the range window

## Disclaimer

This strategy is provided for educational purposes. Past performance does not guarantee future results. Breakout strategies can experience false breakouts leading to consecutive losses. Always test thoroughly in simulation before trading live.
