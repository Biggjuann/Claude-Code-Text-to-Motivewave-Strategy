# Name
ICT Market Maker Buy Model (MMBM)

# Type
strategy

# Behavior
- Captures bullish reversals after sell-side liquidity (SSL) sweep
- Sequence: SSL Sweep → Market Structure Shift (MSS) → FVG/OB Entry
- Uses dealing range (PDH/PDL or session) for premium/discount context
- Only enters in discount (below equilibrium)
- Kill zone filtering for high-probability times

# Inputs
Sessions:
- tradeStart/tradeEnd (time): Trade window [default: 0830-1200 ET]
- killZone (int): 0=NY_AM, 1=NY_PM, 2=LONDON_AM, 3=CUSTOM

EOD (End of Day):
- eodCloseEnabled (bool): Force flat at end of day [default: true]
- eodCloseTime (time): EOD cutoff time [default: 1640 ET]
- eodCancelWorking (bool): Cancel working orders at EOD [default: true]

Dealing Range:
- dealingRangeMode (int): 0=PDH_PDL, 1=ASIAN, 2=LONDON, 3=CUSTOM
- discountThresholdPct (double): Max price fraction for discount [default: 0.5]

Liquidity:
- sslMode (int): 0=PDL, 1=SWING_LOW, 2=EQUAL_LOWS
- sslLookbackBars (int): Lookback for swing/equal lows [default: 50]
- sweepMinTicks (int): Min penetration for sweep [default: 2]
- requireCloseBackAboveSSL (bool): Require close above SSL [default: true]

Structure:
- swingStrength (int): Bars left/right for swing detection [default: 2]
- displacementMinTicks (int): Min body size for displacement [default: 8]

Entry:
- entryModel (int): 0=BULLISH_FVG, 1=ORDER_BLOCK
- fvgMinTicks (int): Min FVG size [default: 2]
- entryPriceMode (int): 0=TOP, 1=MIDPOINT, 2=BOTTOM
- maxBarsToFill (int): Cancel unfilled entry after [default: 30]

Risk:
- contracts (int): Position size [default: 1]
- stoplossMode (int): 0=FIXED, 1=BELOW_SWEEP, 2=BELOW_ZONE, 3=BELOW_PDL
- stoplossTicks (int): Stop distance/buffer [default: 20]

Targets:
- takeProfitMode (int): 0=RR_MULTIPLE, 1=EQUILIBRIUM, 2=PDH
- rrMultiple (double): Risk:reward multiple [default: 2.0]
- partialEnabled (bool): Take partial at TP1 [default: true]
- partialPct (int): Percent at TP1 [default: 50]

Limits:
- maxTradesPerDay (int): Max entries per day [default: 1]

# Outputs
- Plots: dealingHigh, dealingLow, equilibrium, sslLevel, mssLevel
- Zones: entryZone (FVG/OB bounds)
- Signals: SSL_SWEEP, MSS_CONFIRMED, MMBM_LONG

# Risk/Trade Logic
Entry Sequence:
1. Dealing range established (PDH/PDL or session)
2. SSL level identified (PDL, swing low, or equal lows)
3. Price sweeps SSL (trades below + optional close back above)
4. MSS confirmed (close above prior swing high)
5. Bullish FVG or OB detected
6. Enter on limit at FVG/OB (if in discount and trade window)

Exit:
- Stop: Based on mode (fixed, below sweep, below zone, below PDL)
- TP1: Equilibrium or 1R (partial)
- TP2: RR multiple, equilibrium, or PDH (remainder)
