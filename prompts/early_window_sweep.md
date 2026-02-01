# Name
6-10am Range Sweep Mean Reversion (Early Window)

# Type
strategy

# Behavior
- Build range during 6:00-10:00 AM ET window
- Trade sweeps only during early window (10:00-10:30 AM ET)
- Sweep detection: price exceeds range boundary then closes back inside
- Two sweep modes: single-bar or lookback window
- Configurable close-back-inside requirement
- Two stop loss modes: fixed points from entry OR beyond range boundary
- Three target modes: midpoint only, opposite boundary only, or partial at mid then runner
- Max trades per day limit
- One attempt per direction per day option

# Inputs
Sessions:
- rangeStart (time): Range window start [default: 0600]
- rangeEnd (time): Range window end [default: 1000]
- tradeStart (time): Early trade window start [default: 1000]
- tradeEnd (time): Early trade window end [default: 1030]

Sweep Rules:
- useLookbackSweep (bool): Use lookback vs single-bar sweep [default: false]
- sweepLookbackBars (int): Lookback bars for sweep detection [default: 12]
- requireCloseBackInside (bool): Require close back inside range [default: true]

Risk:
- contracts (int): Position size [default: 1]
- stoplossEnabled (bool): Enable stop loss [default: true]
- stoplossMode (enum): FIXED_POINTS_FROM_ENTRY or BEYOND_RANGE_PLUS_BUFFER [default: BEYOND_RANGE_PLUS_BUFFER]
- stoplossPoints (double): Stop distance in points [default: 10.0]

Targets:
- targetMode (enum): RANGE_MIDPOINT, OPPOSITE_RANGE_BOUNDARY, or BOTH_MID_THEN_OPPOSITE [default: RANGE_MIDPOINT]
- partialPctAtMid (int): Percentage to exit at midpoint [default: 50]

Limits:
- maxTradesPerDay (int): Maximum entries per day [default: 1]
- oneAttemptPerSide (bool): One attempt per direction per day [default: true]

# Outputs
- Plots: rangeHigh, rangeLow, rangeMid
- Signals: LONG_FADE, SHORT_FADE

# Risk/Trade Logic
Entry:
- Long: Sweep below rangeLow + close back inside (if required) + not used today
- Short: Sweep above rangeHigh + close back inside (if required) + not used today

Exit:
- Stop Loss: Based on mode - fixed from entry or beyond range boundary
- Targets: Based on mode - midpoint, opposite boundary, or partial split

Filters:
- Only trade after range window complete
- Must be within early trade window (10:00-10:30 ET)
- Under max trades per day
- One attempt per direction (if enabled)
