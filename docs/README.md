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

### Mean Reversion Strategies

| Strategy | Description | Best Timeframe | Markets |
|----------|-------------|----------------|---------|
| [RTH Sweep Mean Reversion](./RTH_Sweep_Mean_Reversion.md) | Trades sweeps of morning balance range with VWAP filter | 5-15 min | ES, NQ, MES, MNQ |
| [6-10am Range Sweep](./Early_Window_Sweep.md) | Early session range sweep with narrow trade window | 5-15 min | ES, NQ, Futures |
| [Sweep Mean Reversion](./Sweep_Mean_Reversion.md) | Basic rolling range sweep detection | 5-30 min | All Futures |

### ICT Strategies

| Strategy | Description | Best Timeframe | Markets |
|----------|-------------|----------------|---------|
| [ICT MMBM (Buy Model)](./ICT_MMBM.md) | Buy-side model: SSL sweep → MSS → FVG entry | 5-15 min | ES, NQ, Forex |
| [ICT MMSM (Sell Model)](./ICT_MMSM.md) | Sell-side model: BSL sweep → MSS → FVG entry | 5-15 min | ES, NQ, Forex |

### Trend Following

| Strategy | Description | Best Timeframe | Markets |
|----------|-------------|----------------|---------|
| [MA Cross Strategy](./MA_Cross_Strategy.md) | Moving average crossover with ATR stops | 15-60 min | All |
| [MTF MA Model Strategy](./MTF_MA_Model.md) | Multi-timeframe MA with pivot confirmation, OB visualization, auto-trading | 5-15 min | All |

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
| CL (Crude Oil) | 0.01 | $10.00 | Mean Reversion |
| GC (Gold) | 0.10 | $10.00 | ICT Models |

---

## Support

- **Installation Issues**: Check that JAR is in correct Extensions folder
- **Strategy Not Appearing**: Restart MotiveWave completely
- **Backtest Questions**: Ensure sufficient historical data loaded

---

## Disclaimer

These strategies are provided for educational purposes. Past performance does not guarantee future results. Always test thoroughly in simulation before trading live. Trading futures involves substantial risk of loss.
