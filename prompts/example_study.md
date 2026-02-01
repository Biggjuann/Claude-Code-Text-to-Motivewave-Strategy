# Name
NY Session Sweep Study

# Type
study

# Behavior
- Detects sweep of RTH range (09:30-16:00 NY)
- Sweep = price trades above range high then closes back inside (no wick-only sweeps)
- Mark entry arrow on the close that returns inside
- Plot range high/low lines during session
- Inputs:
  - rangeStart (session time)
  - rangeEnd (session time)
  - showLabels (bool)
  - maxSignalsPerDay (int)

# Outputs
- Plots: rangeHigh, rangeLow
- Signals: sweepUp, sweepDown
- Labels: "SweepUp", "SweepDown"

# Risk/Trade Logic (only if strategy)
N/A
