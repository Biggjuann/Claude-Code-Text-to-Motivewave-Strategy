# Name
ICT Market Maker Sell Model (MMSM)

# Type
strategy

# Behavior
- Captures bearish reversals after buy-side liquidity (BSL) sweep
- Sequence: BSL Sweep → MSS Down → FVG Entry
- Uses dealing range (PDH/PDL) for premium/discount context
- Only enters in premium (above equilibrium)
- Kill zone filtering for high-probability times
- EOD forced flattening

# Inputs
Sessions:
- tradeStart/tradeEnd (time): Trade window [default: 0830-1200 ET]
- killZone (int): 0=NY_AM, 1=NY_PM, 2=LONDON_AM, 3=CUSTOM

EOD (End of Day):
- eodCloseEnabled (bool): Force flat at end of day [default: true]
- eodCloseTime (time): EOD cutoff time [default: 1640 ET]
- eodCancelWorking (bool): Cancel working orders at EOD [default: true]

Dealing Range:
- premiumThresholdPct (double): Min price fraction for premium [default: 0.5]

Liquidity:
- bslMode (int): 0=PDH, 1=SWING_HIGH, 2=EQUAL_HIGHS
- bslLookbackBars (int): Lookback for swing/equal highs [default: 50]
- sweepMinTicks (int): Min penetration for sweep [default: 2]
- requireCloseBackBelowBSL (bool): Require close below BSL [default: true]

Structure:
- swingStrength (int): Bars left/right for swing detection [default: 2]
- displacementMinTicks (int): Min body size for displacement [default: 8]

Entry:
- entryModel (int): 0=BEARISH_FVG, 1=ORDER_BLOCK
- fvgMinTicks (int): Min FVG size [default: 2]
- entryPriceMode (int): 0=TOP, 1=MIDPOINT, 2=BOTTOM
- maxBarsToFill (int): Cancel unfilled entry after [default: 30]

Risk:
- contracts (int): Position size [default: 1]
- stoplossMode (int): 0=FIXED, 1=ABOVE_SWEEP, 2=ABOVE_ZONE, 3=ABOVE_PDH
- stoplossTicks (int): Stop distance/buffer [default: 20]

Targets:
- takeProfitMode (int): 0=RR_MULTIPLE, 1=EQUILIBRIUM, 2=PDL
- rrMultiple (double): Risk:reward multiple [default: 2.0]
- partialEnabled (bool): Take partial at TP1 [default: true]
- partialPct (int): Percent at TP1 [default: 50]

Limits:
- maxTradesPerDay (int): Max entries per day [default: 1]

# Outputs
- Plots: dealingHigh, dealingLow, equilibrium, bslLevel, mssLevel
- Zones: entryZone (FVG/OB bounds)
- Signals: BSL_SWEEP, MSS_CONFIRMED, MMSM_SHORT

# Risk/Trade Logic
Entry Sequence:
1. Dealing range established (PDH/PDL)
2. BSL level identified (PDH, swing high, or equal highs)
3. Price sweeps BSL (trades above + optional close back below)
4. MSS confirmed (close below prior swing low)
5. Bearish FVG detected
6. Enter short on retracement to FVG (if in premium and trade window)

Exit:
- Stop: Based on mode (fixed, above sweep, above zone, above PDH)
- TP1: Equilibrium or 1R (partial)
- TP2: RR multiple, equilibrium, or PDL (remainder)
