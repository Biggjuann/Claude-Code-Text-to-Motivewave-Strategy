# Name
MTF MA Model

# Type
indicator (trend_following_indicator)

# Behavior
- Multi-timeframe moving average trend filter with pivot-confirmed entries
- Generates pending signals when LTF MA stack + HTF trend filter align
- Confirms entries only on pivot break
- Draws order block lines at signal pivot with invalidation on stop breach

# Inputs
Moving Averages:
- maType (enum): MA calculation method [default: EMA] - SMA, EMA, SMMA_RMA, WMA, VWMA, EVWAP, VRMA
- vwDecayMultiplier (double): Decay for volume-weighted MAs [default: 0.85]

Entry Stack (LTF):
- entryLenFast (int): Fast MA length [default: 5]
- entryLenMid (int): Mid MA length [default: 13]
- entryLenSlow (int): Slow MA length [default: 34]

HTF Filter Stack:
- htfMode (int): 0=AUTO, 1=MANUAL [default: 0]
- htfManual (int): Manual HTF minutes [default: 60]
- htfLenFast (int): HTF fast MA length [default: 34]
- htfLenMid (int): HTF mid MA length [default: 55]
- htfLenSlow (int): HTF slow MA length [default: 200]

Display:
- showEntryMAs (bool): Show entry MAs [default: true]
- showHTFMAs (bool): Show HTF MAs [default: true]
- monochromeMode (bool): Color by bias [default: false]

Order Blocks:
- showOBLines (bool): Show OB lines [default: true]
- obExtendType (int): 0=EXTEND_ALL, 1=EXTEND_LATEST, 2=EXTEND_NONE [default: 1]
- maxOBLines (int): Maximum OB lines to show [default: 20]

Position Sizing:
- enablePositionSizing (bool): Enable sizing calc [default: false]
- assetClass (int): 0=FOREX, 1=FUTURES, 2=CRYPTO [default: 1]
- accountBalance (double): Account balance [default: 50000]
- riskMode (int): 0=PERCENT, 1=FIXED_AMOUNT [default: 0]
- riskPercent (double): Risk percent [default: 1.0]
- riskAmount (double): Risk amount [default: 500]
- futuresPointValue (double): $/point for futures [default: 5.0]
- fxPipValuePerLot (double): $/pip per lot [default: 10.0]
- cryptoUnitValue (double): Unit value [default: 1.0]

Risk:
- stoplossEnabled (bool): Enable stop tracking [default: true]
- stopMode (int): 0=TRACKING_EXTREME, 1=FIXED_POINTS, 2=SIGNAL_BAR [default: 0]
- stopBuffer (double): Buffer beyond stop level [default: 0.0]
- stopDistancePoints (double): Fixed stop distance [default: 10.0]

# Outputs
- Plots: Entry MAs (fast/mid/slow), HTF MAs (fast/mid/slow)
- Signals: PENDING_LONG, PENDING_SHORT, CONFIRMED_LONG, CONFIRMED_SHORT
- Lines: Order block levels with extend/invalidation
- Dashboard: HTF, bias, state, pivot levels, position size

# State Machine
States: IDLE, PENDING_LONG, PENDING_SHORT, CONFIRMED_LONG, CONFIRMED_SHORT

Long Pending conditions:
- Entry stack bullish: fast > mid > slow
- Price above all entry MAs
- HTF stack bullish: fast > mid > slow
- Price above all HTF MAs
- Trigger: fast crosses above mid

Short Pending conditions:
- Entry stack bearish: fast < mid < slow
- Price below all entry MAs
- HTF stack bearish: fast < mid < slow
- Price below all HTF MAs
- Trigger: fast crosses below mid

Long Confirmation: close > most recent pivot high
Short Confirmation: close < most recent pivot low

# HTF Auto Mapping
- LTF <= 5m: HTF = 60m
- LTF 5m-15m: HTF = 240m (4H)
- LTF 60m-240m: HTF = 1D

# Pivots
- Pivot Low: bullish candle after bearish candle
- Pivot High: bearish candle after bullish candle
