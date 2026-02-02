# MA Cross Strategy

A classic moving average crossover strategy with configurable MA types, ATR-based or fixed stops, and risk:reward targeting.

---

## Strategy Overview

**Type:** Trend Following
**Direction:** Long and Short
**Best Timeframe:** 15-minute, 30-minute, 1-hour
**Best Markets:** All futures, Forex, Indices
**Timezone:** Any (no session filtering)

### Core Concept

The moving average crossover is one of the most widely used trading signals:

- **Long Signal**: Fast MA crosses above Slow MA
- **Short Signal**: Fast MA crosses below Slow MA

This implementation adds professional risk management with ATR-based stops and R-multiple targets.

---

## Entry Logic

### Long Entry
- Fast MA crosses above Slow MA
- No existing position
- Under maximum daily trade limit

### Short Entry
- Fast MA crosses below Slow MA
- No existing position
- Under maximum daily trade limit

---

## Settings Reference

### General Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Fast MA Period | 9 | Period for fast moving average |
| Slow MA Period | 21 | Period for slow moving average |
| MA Method | EMA | SMA, EMA, WMA, DEMA, TEMA |
| Input | Close | Price input (Close, Open, High, Low, etc.) |

### Risk Management Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Use ATR Stop | true | ATR-based vs fixed point stop |
| ATR Period | 14 | Period for ATR calculation |
| ATR Multiplier | 1.5 | Stop = Entry ± (ATR × Multiplier) |
| Fixed Stop (pts) | 10.0 | Fixed stop distance (if ATR disabled) |
| Risk:Reward Ratio | 2.0 | Target = Entry ± (Risk × R:R) |
| Max Trades/Day | 3 | Maximum entries per day |

### Display Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Fast MA Line | Blue | Color for fast MA |
| Slow MA Line | Red | Color for slow MA |
| Show Entry Markers | true | Display triangle markers |

---

## MA Methods Explained

| Method | Full Name | Characteristics |
|--------|-----------|-----------------|
| SMA | Simple Moving Average | Equal weight to all periods, lagging |
| EMA | Exponential Moving Average | More weight to recent prices, responsive |
| WMA | Weighted Moving Average | Linear weight decay |
| DEMA | Double Exponential MA | Reduced lag, more responsive |
| TEMA | Triple Exponential MA | Minimal lag, most responsive |

**Recommendation**: EMA is the most commonly used for crossover strategies.

---

## ATR-Based Stops Explained

The Average True Range (ATR) measures volatility. Using ATR for stops automatically adjusts to market conditions:

```
ATR Stop Calculation:
- Long Stop = Entry Price - (ATR × Multiplier)
- Short Stop = Entry Price + (ATR × Multiplier)

Example (Long Entry):
- Entry: 4500.00
- 14-period ATR: 8.0 points
- ATR Multiplier: 1.5
- Stop = 4500 - (8.0 × 1.5) = 4488.00

Target with 2:1 R:R:
- Risk = 4500 - 4488 = 12 points
- Target = 4500 + (12 × 2.0) = 4524.00
```

---

## Example Trade

```
15-Minute ES Chart:
- 9 EMA: 4495.00
- 21 EMA: 4493.00
- 14 ATR: 6.5 points

Signal: 9 EMA crosses above 21 EMA → LONG

Entry: 4495.00
Stop: 4495 - (6.5 × 1.5) = 4485.25
Risk: 9.75 points
Target: 4495 + (9.75 × 2.0) = 4514.50
```

---

## Optimization Tips

### For Trending Markets
- Use longer MA periods (13/34 or 20/50)
- Higher ATR multiplier (2.0-2.5) for wider stops
- Lower R:R (1.5) for higher win rate

### For Choppy Markets
- Shorter MA periods (5/13 or 8/21)
- Lower ATR multiplier (1.0-1.5)
- Consider adding trend filter (200 MA)

### Period Combinations to Test
| Style | Fast | Slow | Character |
|-------|------|------|-----------|
| Aggressive | 5 | 13 | Many signals, some false |
| Standard | 9 | 21 | Balanced |
| Conservative | 13 | 34 | Fewer signals, higher quality |
| Long-term | 20 | 50 | Position trading |

---

## Visual Indicators

- **Fast MA** (Blue): Shorter period moving average
- **Slow MA** (Red): Longer period moving average
- **Entry Markers**: Triangles at crossover points

---

## Limitations

1. **Whipsaw Risk**: Generates many false signals in ranging markets
2. **Lagging Indicator**: By definition, MAs confirm trends after they start
3. **No Context**: Doesn't consider support/resistance or market structure

### Suggested Enhancements
- Add trend filter (only trade in direction of 200 MA)
- Add session filter (only trade during high-volume hours)
- Add volatility filter (skip low ATR periods)

---

## When to Use This Strategy

**Best Conditions:**
- Clear trending markets
- Higher timeframes (15m+)
- After breakouts from consolidation

**Avoid When:**
- Market is choppy/ranging
- Around major news events
- Low volume periods (lunch hour, overnight)
