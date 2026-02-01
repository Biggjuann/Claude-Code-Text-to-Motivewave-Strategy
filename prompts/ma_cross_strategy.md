# Name
MA Cross Strategy

# Type
strategy

# Behavior
- Two moving averages (fast and slow)
- Enter LONG when fast MA crosses above slow MA
- Enter SHORT when fast MA crosses below slow MA
- Close opposite position before entering new one
- Inputs:
  - fastPeriod (int, default 9)
  - slowPeriod (int, default 21)
  - maMethod (MA method, default EMA)
  - input (price input, default CLOSE)

# Outputs
- Plots: fastMA, slowMA
- Signals: BUY, SELL

# Risk/Trade Logic
- Position sizing: fixed lots from settings
- Stop loss: ATR-based or fixed ticks (configurable)
- Take profit: risk:reward ratio (configurable)
- Only trade during specified session (optional)
- Max trades per day limit
