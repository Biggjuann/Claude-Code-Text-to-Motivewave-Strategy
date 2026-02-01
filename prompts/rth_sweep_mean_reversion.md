# Name
RTH Range Sweep Mean Reversion Strategy

# Type
strategy

# Behavior
- Build balance range during morning session (configurable, default 9:30-11:30 CT)
- Trade sweeps during trade window (configurable, default 9:30-16:00 CT)
- Sweep detection: price exceeds range boundary then closes back inside
- Two sweep modes: single-bar or lookback window
- VWAP filters: require price on "wrong side" of VWAP for mean reversion
- Optional VWAP slope filter to avoid fading strong trends
- Partial profit taking at range midpoint
- Remainder targets opposite range boundary
- Stop loss beyond the swept boundary
- Max trades per day limit
- One attempt per direction per day

# Inputs
Sessions:
- balanceStart (time): Balance window start [default: 0930]
- balanceEnd (time): Balance window end [default: 1130]
- tradeStart (time): Trade window start [default: 0930]
- tradeEnd (time): Trade window end [default: 1600]

Range Requirements:
- minRangePts (double): Minimum range width in points [default: 6.0]
- maxRangePts (double): Maximum range width in points [default: 25.0]

Sweep Rules:
- useLookbackSweep (bool): Use lookback vs single-bar sweep [default: false]
- sweepLookback (int): Lookback bars for sweep detection [default: 12]

VWAP Filters:
- useVWAPLocation (bool): Require price on wrong side of VWAP [default: true]
- useVWAPSlope (bool): Block trades when VWAP slopes against fade [default: false]
- vwapSlopeBars (int): Bars for VWAP slope calculation [default: 3]

Risk:
- contracts (int): Position size [default: 1]
- stopPts (double): Stop distance beyond range boundary [default: 5.0]
- partialPct (int): Percentage to exit at midpoint [default: 50]

Limits:
- maxTradesPerDay (int): Maximum entries per day [default: 2]

# Outputs
- Plots: rthHigh, rthLow, rangeMid, vwap
- Signals: LONG_SWEEP, SHORT_SWEEP

# Risk/Trade Logic
Entry:
- Long: Sweep below rthLow + close back inside + VWAP below (optional) + not used today
- Short: Sweep above rthHigh + close back inside + VWAP above (optional) + not used today

Exit:
- Stop Loss: rthLow - stopPts (long) or rthHigh + stopPts (short)
- Target 1: rangeMid (partialPct% of position)
- Target 2: rthHigh/rthLow opposite boundary (remainder)

Filters:
- Only trade when balance range is complete
- Range width must be within min/max bounds
- Must be within trade window
- Under max trades per day
- One attempt per direction per day
