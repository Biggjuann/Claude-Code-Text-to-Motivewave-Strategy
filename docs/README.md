# MW Generated Strategies - Documentation

Professional trading strategies for MotiveWave platform.

## Quick Start

### Installation

1. Download the latest `MWGeneratedStudies-x.x.x.jar`
2. Copy to your MotiveWave Extensions folder:
   - Windows: `C:\Users\[YourName]\MotiveWave Extensions\`
   - Mac: `~/MotiveWave Extensions/`
3. Restart MotiveWave (or: Configure → Preferences → Studies → Reload Extensions)
4. Find strategies under: **Study Menu → MW Generated**

### Applying a Strategy

1. Open a chart with your desired instrument and timeframe
2. Go to **Study** → **MW Generated** → Select strategy
3. Configure settings in the dialog
4. Click **OK** to apply
5. To run live: **Strategy** → **Activate Strategy**

---

## Strategy Library

### ICT Strategies

| Strategy | Description | Best Timeframe | Markets |
|----------|-------------|----------------|---------|
| [ICT Setup Selector](./ICT_Setup_Selector.md) | Multi-setup suite with JadeCap presets (MMBM, MMSM, Session Raid, London-NY, Daily PO3) | 5-15 min | ES, NQ, Forex |
| [BrianStonk Modular](./BrianStonk_Modular.md) | Modular ICT engine with OB, Breaker, FVG, IFVG, BPR, Unicorn setups, draw liquidity, TF alignment | 1-5 min | NQ, MNQ, ES, MES |

### Breakout Strategies

| Strategy | Description | Best Timeframe | Markets |
|----------|-------------|----------------|---------|
| [Time Range Breakout](./Time_Range_Breakout.md) | Time-window range breakout with TP1 partial, runner trail, BE, and EOD flatten | 1-5 min | All Futures |

### Adaptive S/R Strategies

| Strategy | Description | Best Timeframe | Markets |
|----------|-------------|----------------|---------|
| [Magic Line](./Magic_Line.md) | Regressive S/R line (LB) with Support Bounce, Side-Exit, and Table-Top patterns | Any | All Futures |

---

## Common Settings Explained

### Session Times (HHMM Format)
- `0930` = 9:30 AM
- `1600` = 4:00 PM (16:00)
- All times are in the strategy's configured timezone

### Position Sizing
- **Contracts**: Number of contracts per trade
- Most strategies default to 1 contract

### Risk Management
- **Stop Loss**: Distance or level where position is closed at a loss
- **Take Profit**: Target level(s) for profit taking
- **Partial %**: Percentage of position to close at first target

### EOD (End of Day) Settings
- **Force Flat at EOD**: Closes all positions at specified time
- **EOD Close Time**: Default 16:40 (4:40 PM ET)
- Prevents overnight exposure

---

## Recommended Instruments

| Instrument | Tick Size | Point Value | Recommended Strategies |
|------------|-----------|-------------|----------------------|
| ES (E-mini S&P) | 0.25 | $12.50 | All |
| MES (Micro E-mini S&P) | 0.25 | $1.25 | All |
| NQ (E-mini Nasdaq) | 0.25 | $5.00 | All |
| MNQ (Micro Nasdaq) | 0.25 | $0.50 | All |
| CL (Crude Oil) | 0.01 | $10.00 | Time Range Breakout |
| GC (Gold) | 0.10 | $10.00 | ICT Models |

---

## Support

- **Installation Issues**: Check that JAR is in correct Extensions folder
- **Strategy Not Appearing**: Restart MotiveWave completely
- **Backtest Questions**: Ensure sufficient historical data loaded

---

## Disclaimer

These strategies are provided for educational purposes. Past performance does not guarantee future results. Always test thoroughly in simulation before trading live. Trading futures involves substantial risk of loss.
