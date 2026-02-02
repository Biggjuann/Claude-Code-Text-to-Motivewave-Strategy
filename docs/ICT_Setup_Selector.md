# ICT Setup Selector Suite (JadeCap-style)

A comprehensive multi-setup ICT strategy with preset pack that lets users select from top ICT-style setups.

> **Note:** This is an auto-trading strategy with 5 selectable setup modules and 3 preset configurations.

---

## Strategy Overview

**Type:** Multi-Setup ICT Strategy (Auto-Trading)
**Direction:** Long and Short
**Best Timeframe:** 5-minute, 15-minute
**Best Markets:** ES, NQ, Forex, All Futures
**Timezone:** America/New_York (configurable)

### Core Concept

This strategy provides a unified framework for trading multiple ICT-style setups:
1. **MMBM** (Market Maker Buy Model): SSL sweep → MSS up → FVG entry
2. **MMSM** (Market Maker Sell Model): BSL sweep → MSS down → FVG entry
3. **Session Liquidity Raid**: PDH/PDL/Asian/London level raids
4. **London AM Raid NY Reversal**: London raid sets up NY reversal
5. **Daily Sweep PO3**: Daily level sweep framework

---

## Preset System

### Jade Balanced (Default)
- Trade Window: 9:30-11:30 AM
- Max Trades: 1/day
- Entry: Both Immediate + FVG Retrace
- Confirmation: Balanced (MSS close required)
- Stop: Structural + 20 tick buffer
- Exit: TP1 (internal) + TP2 (opposite liquidity)
- Midday Exit: 12:15 PM

### Jade Aggressive
- Trade Window: 9:30-11:30 AM
- Max Trades: 2/day
- Entry: Immediate Post-Sweep
- Confirmation: Aggressive (looser requirements)
- Stop: Structural + 16 tick buffer
- Exit: Scale Out + Trail
- Midday Exit: 12:00 PM

### Jade Conservative
- Trade Window: 9:30-11:00 AM
- Max Trades: 1/day
- Entry: FVG Retrace Only
- Confirmation: Conservative (strict MSS close required)
- Stop: Structural + 24 tick buffer
- Exit: TP1 + TP2 (opposite liquidity)
- Midday Exit: 12:15 PM

---

## Setup Modules

### MMBM_BUY (Market Maker Buy Model)
**Direction:** Long only

**Sequence:**
1. Identify SSL (Sell-Side Liquidity): PDL or recent swing low
2. Detect sweep: Price penetrates below SSL by min raid ticks
3. Confirm MSS Up: Break above recent swing high with displacement
4. Detect Bullish FVG: Gap where bar[2].low > bar[0].high
5. Enter long

**Stop:** Below sweep extreme + buffer
**Target:** Equilibrium (TP1), PDH/opposite liquidity (TP2)

### MMSM_SELL (Market Maker Sell Model)
**Direction:** Short only

**Sequence:**
1. Identify BSL (Buy-Side Liquidity): PDH or recent swing high
2. Detect sweep: Price penetrates above BSL by min raid ticks
3. Confirm MSS Down: Break below recent swing low with displacement
4. Detect Bearish FVG: Gap where bar[2].high < bar[0].low
5. Enter short

**Stop:** Above sweep extreme + buffer
**Target:** Equilibrium (TP1), PDL/opposite liquidity (TP2)

### SESSION_LIQUIDITY_RAID
**Direction:** Both

Trades raids of session liquidity levels (PDH, PDL, Asian High/Low, London High/Low) during NY session with MSS confirmation and FVG entry.

### LONDON_AM_RAID_NY_REVERSAL
**Direction:** Both

Detects London AM session raids, then waits for NY session to confirm reversal with MSS and FVG entry. Great for capturing the NY reversal of London moves.

### DAILY_SWEEP_PO3
**Direction:** Both

Daily sweep framework (Power of 3) - identifies daily level sweeps and trades the reversal with MSS/FVG confirmation.

---

## Settings Reference

### Presets Tab

| Setting | Options | Description |
|---------|---------|-------------|
| Preset Pack | Balanced, Aggressive, Conservative | Pre-configured settings |
| Setup | MMBM, MMSM, SessionRaid, LondonNY, DailyPO3 | Which setup module to use |

### Sessions Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Trade Start | 0930 | Trade window start (HHMM) |
| Trade End | 1130 | Trade window end (HHMM) |
| Kill Zone | NY AM | NY AM, NY PM, London, or Custom |
| EOD Close | true | Force flat at end of day |
| EOD Time | 1640 | EOD flatten time (4:40 PM) |

### Limits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Max Trades/Day | 1 | Daily trade limit |
| One At A Time | true | Only one position at a time |
| Contracts | 1 | Position size |

### Structure Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Pivot Strength | 2 | L/R bars for swing detection |
| Min Raid Ticks | 2 | Minimum penetration for sweep |

### Entry Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Entry Preference | Both | Immediate, FVG Only, Both, MSS Market |
| Min FVG Size | 2 | Minimum FVG size in ticks |
| Entry Price In Zone | Mid | Top, Mid, or Bottom of zone |
| Max Bars To Fill | 30 | Cancel limit entry after N bars |
| Strictness | Balanced | Aggressive, Balanced, Conservative |
| Require MSS Close | true | MSS confirmed on close only |

### Risk Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Enable Stop | true | Use stop loss |
| Stop Mode | Structural | Fixed or Structural+Buffer |
| Stop Buffer | 20 | Buffer in ticks |

### Exits Tab

| Setting | Default | Description |
|---------|---------|-------------|
| Exit Model | TP1+TP2 | R:R, TP1+TP2, Scale+Trail, Midday |
| RR Multiple | 2.0 | Risk:Reward ratio for R:R mode |
| Enable Partial | true | Take partial at TP1 |
| Partial % | 50 | Percentage to close at TP1 |
| Midday Exit | true | Exit at midday time |
| Midday Time | 1215 | Midday exit time (12:15 PM) |

---

## Kill Zone Times (ET)

| Kill Zone | Time Window |
|-----------|-------------|
| NY AM | 8:30 AM - 11:00 AM |
| NY PM | 1:30 PM - 4:00 PM |
| London AM | 3:00 AM - 5:00 AM |
| Custom | User-defined |

---

## Session Level Tracking

The strategy automatically tracks:

| Level | Session Time (ET) |
|-------|------------------|
| PDH/PDL | Previous day high/low |
| Asian High/Low | 7:00 PM - 3:00 AM |
| London High/Low | 3:00 AM - 9:30 AM |

---

## Entry Models Explained

### Immediate Post-Sweep
Market entry immediately after sweep shows failure-to-continue behavior. Fastest entry but requires less confirmation.

### FVG Retrace
Limit entry into a valid Fair Value Gap zone after sweep/MSS. More patient entry with better prices but may miss some setups.

### Both (Immediate + FVG)
Uses immediate entry if sweep shows clear reversal, otherwise waits for FVG. Best of both worlds.

### MSS Market
Market entry on MSS close confirmation. Pure momentum entry after structure shift confirmed.

---

## Exit Models Explained

### R:R Multiple
Single target at configured Risk:Reward multiple (default 2:1).

### TP1 + TP2 (Internal + Opposite Liquidity)
- TP1: Equilibrium (50% retracement of dealing range)
- TP2: Opposite liquidity (PDH for longs, PDL for shorts)

### Scale Out + Trail
- Partial at first liquidity target
- Move stop to breakeven after partial
- Runner targets final liquidity

### Time Exit (Midday)
Closes position at configured midday time regardless of P&L.

---

## Example Trade (MMBM)

```
Setup: MMBM_BUY on ES 5-minute

1. PDL identified at 5420.00
2. Price sweeps PDL, trades down to 5418.25 (8+ ticks below)
3. Price closes back above PDL → Sweep confirmed
4. Swing high identified at 5432.00
5. Price breaks 5432 with strong bullish candle → MSS confirmed
6. Bullish FVG detected: 5430.00 - 5433.00
7. Long entry triggered at market

Stop: 5418.25 - 5 points = 5413.25 (below sweep)
TP1: 5435.00 (equilibrium)
TP2: 5450.00 (PDH)

Result: Partial at TP1, runner to TP2
```

---

## Tips for Success

1. **Start with Balanced preset** - Provides good risk/reward without excessive confirmation requirements

2. **Use MMBM for bullish bias days** - When higher timeframe is bullish, focus on MMBM setups

3. **Use MMSM for bearish bias days** - When higher timeframe is bearish, focus on MMSM setups

4. **Session Raid for range days** - When no clear bias, Session Raid works well for mean reversion

5. **London NY for continuation days** - When London makes a strong move, NY often reverses

6. **Respect the time windows** - ICT setups work best during kill zones

7. **Monitor your fills** - FVG entries may not fill if price moves away quickly

---

## Disclaimer

This strategy is provided for educational purposes. Past performance does not guarantee future results. Always test thoroughly in simulation before trading live. Trading futures involves substantial risk of loss.
