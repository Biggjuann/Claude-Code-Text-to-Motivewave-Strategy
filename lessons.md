# Lessons Learned - MotiveWave Strategy Development

A comprehensive collection of learnings from building trading strategies for the MotiveWave platform.

---

## Table of Contents

1. [Build System](#build-system)
2. [MotiveWave SDK Patterns](#motivewave-sdk-patterns)
3. [Strategy Architecture](#strategy-architecture)
4. [ICT Concepts Implementation](#ict-concepts-implementation)
5. [Common Pitfalls & Fixes](#common-pitfalls--fixes)
6. [Best Practices](#best-practices)

---

## Build System

### Gradle, Not Maven

- **This project uses Gradle**, not Maven
- Build wrapper: `gradlew.bat` (Windows)
- Custom build script: `mwbuilder.bat` with commands:
  - `mwbuilder build` - Compile and create JAR
  - `mwbuilder deploy` - Deploy to MotiveWave Extensions
  - `mwbuilder all` - Full pipeline

### OneDrive Cache Errors Are Harmless

When building in a OneDrive-synced directory, you'll see errors like:
```
java.io.IOException: The cloud operation is invalid
Could not add entry ':jar' to cache executionHistory.bin
```

**These are harmless.** The build completes successfully before OneDrive tries to sync the cache. The JAR is created and deployed correctly despite the error message.

### Build Commands

```bash
# Build only
./gradlew.bat build --no-daemon

# Deploy to MotiveWave
./gradlew.bat deploy --no-daemon

# Use --no-daemon to avoid lock issues
```

### Gradle Lock Issues

If you see "Cannot lock execution history cache", clean up locks:
```bash
rm -rf .gradle/8.5/executionHistory/*.lock
```

---

## MotiveWave SDK Patterns

### Study vs Strategy

| Annotation | Purpose | Auto-Trading |
|------------|---------|--------------|
| `strategy = false` | Indicator/Study only | No |
| `strategy = true` | Full strategy | Yes |

### StudyHeader Annotation

```java
@StudyHeader(
    namespace = "com.mw.studies",
    id = "STRATEGY_ID",                    // Unique identifier
    rb = "com.mw.studies.nls.strings",     // Resource bundle for i18n
    name = "STRATEGY_ID",                  // Maps to strings.properties
    label = "LBL_STRATEGY",                // Short label
    desc = "DESC_STRATEGY",                // Description
    menu = "MW Generated",                 // Menu location
    overlay = true,                        // Draw on price chart
    studyOverlay = true,                   // Can overlay other studies
    strategy = true,                       // Enable auto-trading
    autoEntry = true,                      // Automatic entries
    manualEntry = false,                   // No manual entry mode
    signals = true,                        // Generate signals
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true,
    supportsBarUpdates = true              // Intrabar updates (for 1m strategies)
)
```

### Localization (strings.properties)

Always add entries for new strategies:
```properties
# StrategyName
STRATEGY_ID=Display Name for Strategy
LBL_STRATEGY=Short Label
DESC_STRATEGY=Full description of what the strategy does
```

### Settings Descriptor Pattern

```java
@Override
public void initialize(Defaults defaults) {
    var sd = createSD();

    // Create tabs
    var tab = sd.addTab("TabName");
    var grp = tab.addGroup("Group Name");

    // Add settings
    grp.addRow(new BooleanDescriptor(KEY, "Label", defaultValue));
    grp.addRow(new IntegerDescriptor(KEY, "Label", default, min, max, step));
    grp.addRow(new DoubleDescriptor(KEY, "Label", default, min, max, step));
    grp.addRow(new PathDescriptor(KEY, "Label", color, width, dash, ...));
    grp.addRow(new MarkerDescriptor(KEY, "Label", type, size, color, ...));

    // Quick settings (shown in toolbar)
    sd.addQuickSettings(KEY1, KEY2, KEY3);

    // Runtime descriptor
    var desc = createRD();
    desc.setLabelSettings(KEY1, KEY2);
    desc.exportValue(new ValueDescriptor(Values.NAME, "Label", new String[]{}));
    desc.declarePath(Values.NAME, PATH_KEY);
    desc.declareSignal(Signals.NAME, "Signal Description");
}
```

### Key Lifecycle Methods

```java
// Called when strategy is activated for live trading
@Override
public void onActivate(OrderContext ctx) { }

// Called when strategy is deactivated
@Override
public void onDeactivate(OrderContext ctx) { }

// Called on each bar calculation (backtest + live)
@Override
protected void calculate(int index, DataContext ctx) { }

// Called when a signal is generated (live trading)
@Override
public void onSignal(OrderContext ctx, Object signal) { }

// Called at bar close (live trading) - for exit management
@Override
public void onBarClose(OrderContext ctx) { }

// Called to reset state
@Override
public void clearState() { }
```

### Order Execution

```java
// Market orders
ctx.buy(qty);           // Long entry
ctx.sell(qty);          // Short entry or partial long exit
ctx.closeAtMarket();    // Close entire position

// Position info
int position = ctx.getPosition();  // + = long, - = short, 0 = flat

// Instrument info
var instr = ctx.getInstrument();
double tickSize = instr.getTickSize();
double pointValue = instr.getPointValue();
double lastPrice = instr.getLastPrice();
double rounded = instr.round(price);  // Round to tick
```

### Time Handling

```java
// NY timezone for session logic
private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

// Get time as HHMM integer (e.g., 930 for 9:30 AM)
private int getTimeInt(long time, TimeZone tz) {
    Calendar cal = Calendar.getInstance(tz);
    cal.setTimeInMillis(time);
    return cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);
}

// Get unique day identifier
private int getDayOfYear(long time, TimeZone tz) {
    Calendar cal = Calendar.getInstance(tz);
    cal.setTimeInMillis(time);
    return cal.get(Calendar.DAY_OF_YEAR) + cal.get(Calendar.YEAR) * 1000;
}
```

### Bar Data Access

```java
var series = ctx.getDataSeries();

// Current bar
double high = series.getHigh(index);
double low = series.getLow(index);
double open = series.getOpen(index);
double close = series.getClose(index);
long time = series.getStartTime(index);

// Previous bars
double prevHigh = series.getHigh(index - 1);

// Built-in indicators
Double ema = series.ema(index, period, Enums.BarInput.CLOSE);
Double sma = series.sma(index, period, Enums.BarInput.CLOSE);

// Bar completion check
if (!series.isBarComplete(index)) return;
```

### Drawing on Chart

```java
// Add marker
var marker = getSettings().getMarker(Inputs.UP_MARKER);
if (marker.isEnabled()) {
    addFigure(new Marker(
        new Coordinate(barTime, price),
        Enums.Position.BOTTOM,  // or TOP
        marker,
        "Label"
    ));
}

// Set plotted values
series.setDouble(index, Values.NAME, value);
```

---

## Strategy Architecture

### State Machine Pattern

For complex setups with multiple phases:

```java
private static final int STATE_IDLE = 0;
private static final int STATE_SWEEP_DETECTED = 1;
private static final int STATE_MSS_PENDING = 2;
private static final int STATE_ENTRY_READY = 3;
private static final int STATE_IN_TRADE = 4;

private int state = STATE_IDLE;
```

### Dual Mode (Long + Short Concurrent)

For strategies that run both directions simultaneously:

```java
// Separate state machines
private int mmbmState = STATE_IDLE;  // Long setup state
private int mmsmState = STATE_IDLE;  // Short setup state

// Per-side trade tracking
private int longTradesToday = 0;
private int shortTradesToday = 0;
```

### Zone Tracking Pattern

For FVG, IFVG, or other zone-based strategies:

```java
private static class Zone {
    double top;
    double bottom;
    int barIndex;
    boolean isValid;
    boolean isBullish;

    double getMid() { return (top + bottom) / 2.0; }
}

private List<Zone> activeZones = new ArrayList<>();

// Limit active zones
private void addZone(Zone zone, int maxZones) {
    activeZones.add(zone);
    while (activeZones.size() > maxZones) {
        activeZones.remove(0);  // Remove oldest
    }
}
```

### Daily Reset Pattern

```java
private int lastResetDay = -1;

// In calculate():
int barDay = getDayOfYear(barTime, NY_TZ);
if (barDay != lastResetDay) {
    // Carry forward previous day's high/low
    if (!Double.isNaN(todayHigh)) {
        pdh = todayHigh;
        pdl = todayLow;
    }
    // Reset daily state
    resetDailyState();
    lastResetDay = barDay;
}
```

### Session Window Pattern

```java
private int getCurrentWindow(int timeInt) {
    if (nyAmEnabled && timeInt >= 930 && timeInt < 1130) return 1;  // NY AM
    if (nyPmEnabled && timeInt >= 1330 && timeInt < 1530) return 2; // NY PM
    return 0;  // No window
}

// Track window changes to reset per-window state
if (window != currentWindow) {
    sessionHigh = Double.NaN;
    sessionLow = Double.NaN;
    tradesThisWindow = 0;
    currentWindow = window;
}
```

---

## ICT Concepts Implementation

### Liquidity Levels

- **SSL (Sell-Side Liquidity)**: Lows where stops rest (PDL, swing lows)
- **BSL (Buy-Side Liquidity)**: Highs where stops rest (PDH, swing highs)

```java
// Configurable liquidity reference
private static final int LIQ_REF_PREV_DAY = 0;   // PDH/PDL
private static final int LIQ_REF_SESSION = 1;    // Session H/L
private static final int LIQ_REF_CUSTOM = 2;     // Manual level
```

### Draw Liquidity

Liquidity levels price is "drawn to" - targets for price movement:

```java
private static class LiquidityTarget {
    double price;
    String type;  // "SESSION_HIGH", "SWING_LOW", "EQUAL_HIGH", etc.
    boolean isBullishDraw;  // True = above price, bullish target
}

// Track multiple target types
private List<LiquidityTarget> drawTargets = new ArrayList<>();

// Nearest draw target in trade direction
private LiquidityTarget findNearestDraw(double currentPrice, boolean lookingUp) {
    return drawTargets.stream()
        .filter(t -> t.isBullishDraw == lookingUp)
        .filter(t -> lookingUp ? t.price > currentPrice : t.price < currentPrice)
        .min(Comparator.comparingDouble(t -> Math.abs(t.price - currentPrice)))
        .orElse(null);
}
```

### Order Block (OB) - Proper Definition

An OB is the last consecutive candle(s) before displacement:

```java
// Bullish OB: consecutive down-close candles before up displacement
private Zone detectBullishOB(DataSeries series, int index, int minCandles) {
    // Find consecutive down candles before current
    int count = 0;
    int obEndIdx = -1;
    for (int i = index - 1; i >= 0 && count < 10; i--) {
        double open = series.getOpen(i);
        double close = series.getClose(i);
        if (close < open) {  // Down close
            if (obEndIdx < 0) obEndIdx = i;
            count++;
        } else {
            if (count >= minCandles) break;
            count = 0;
            obEndIdx = -1;
        }
    }

    if (count >= minCandles && obEndIdx >= 0) {
        int obStartIdx = obEndIdx - count + 1;
        double obHigh = series.getHigh(obStartIdx);
        double obLow = series.getLow(obEndIdx);

        // Check if current candle closes through OB high (displacement)
        if (series.getClose(index) > obHigh) {
            return new Zone(obHigh, obLow, obStartIdx, true, "OB");
        }
    }
    return null;
}
```

**Key point**: OB mean threshold is the midpoint. Price should react BEFORE reaching the mean for a valid OB1 entry.

### Breaker - Two Creation Methods

**Method 1: OB Violation Flip**
```java
// Track OB violation status
zone.violated = false;

// In calculate(): check if price closes through OB
if (zone.type.equals("OB") && zone.isValid && !zone.violated) {
    if (zone.isBullish && close < zone.bottom) {
        zone.violated = true;
        // Bullish OB violated → Bearish Breaker
        Zone breaker = new Zone(zone.top, zone.bottom, index, false, "BREAKER");
        breakers.add(breaker);
    } else if (!zone.isBullish && close > zone.top) {
        zone.violated = true;
        // Bearish OB violated → Bullish Breaker
        Zone breaker = new Zone(zone.top, zone.bottom, index, true, "BREAKER");
        breakers.add(breaker);
    }
}
```

**Method 2: Sweep + Displacement (Structure Breaker)**
```java
// Bullish structure breaker: sweep low + displacement up
if (swept != null && !swept.isHigh) {
    double body = close - open;
    double range = high - low;
    double avgRange = getAverageRange(series, index, 14);

    if (body > 0 && range >= avgRange * 1.2) {  // Bullish displacement
        Zone breaker = new Zone(swept.price, swept.price - buffer, index, true, "BREAKER");
        breakers.add(breaker);
    }
}
```

### FVG with Consequent Encroachment (CE)

```java
// Bullish FVG: gap between bar[2].low and bar[0].high
double gapTop = series.getLow(index);      // Current bar low
double gapBottom = series.getHigh(index - 2);  // Bar 2 back high

if (gapTop > gapBottom) {
    double gapSize = gapTop - gapBottom;
    if (gapSize >= minGapPoints) {
        Zone fvg = new Zone(gapTop, gapBottom, index - 1, true, "FVG");
        // CE = midpoint
        fvg.meanThreshold = (gapTop + gapBottom) / 2.0;
        fvgs.add(fvg);
    }
}

// CE Respect check: price should hold above CE for bullish FVG
boolean respectsCE = close > fvg.meanThreshold;
```

### IFVG (Inversion) - FVG Displaced Through

```java
// IFVG: FVG that price closes through, inverting direction
private void checkForInversion(Zone fvg, double close, int index) {
    if (!fvg.isValid || fvg.type.equals("IFVG")) return;

    if (fvg.isBullish) {
        // Bullish FVG → Bearish IFVG if price closes below bottom
        if (close < fvg.bottom) {
            fvg.type = "IFVG";
            fvg.isBullish = false;  // Flipped!
            fvg.barIndex = index;
        }
    } else {
        // Bearish FVG → Bullish IFVG if price closes above top
        if (close > fvg.top) {
            fvg.type = "IFVG";
            fvg.isBullish = true;  // Flipped!
            fvg.barIndex = index;
        }
    }
}
```

### BPR (Balanced Price Range) - Zone Overlap

```java
// BPR: overlap between complementary zones
private Zone detectBPR(Zone zone1, Zone zone2, int index, double minWidth) {
    // Find overlap
    double overlapTop = Math.min(zone1.top, zone2.top);
    double overlapBottom = Math.max(zone1.bottom, zone2.bottom);

    if (overlapTop > overlapBottom) {
        double width = overlapTop - overlapBottom;
        if (width >= minWidth) {
            // BPR inherits direction from the more recent zone
            boolean isBullish = zone1.barIndex > zone2.barIndex
                ? zone1.isBullish : zone2.isBullish;
            return new Zone(overlapTop, overlapBottom, index, isBullish, "BPR");
        }
    }
    return null;
}
```

### Unicorn Setup (A+ Grade)

```java
// Unicorn: Breaker + BPR/FVG confluence with price in overlap
private boolean checkUnicorn(Zone breaker, List<Zone> fvgs, double close) {
    if (breaker == null || !breaker.isValid) return false;

    for (Zone fvg : fvgs) {
        if (!fvg.isValid || fvg.isBullish != breaker.isBullish) continue;

        // Find overlap
        double overlapTop = Math.min(breaker.top, fvg.top);
        double overlapBottom = Math.max(breaker.bottom, fvg.bottom);

        if (overlapTop > overlapBottom) {
            // Check if price is in overlap zone
            if (close >= overlapBottom && close <= overlapTop) {
                return true;  // UNICORN DETECTED!
            }
        }
    }
    return false;
}
```

### Entry Model Priority

```java
// Entry models in priority order
private static final int MODEL_UN1 = 0;  // Unicorn (A+) - highest priority
private static final int MODEL_BR1 = 1;  // Breaker Retap
private static final int MODEL_IF1 = 2;  // IFVG/BPR Flip
private static final int MODEL_OB1 = 3;  // OB Mean Threshold

private int checkEntryModels(double close, List<Zone> zones) {
    // Check in priority order - first valid match wins
    if (enableUnicorn && checkUnicorn(activeBreaker, fvgs, close)) return MODEL_UN1;
    if (enableBreaker && checkBreakerRetap(breakers, close)) return MODEL_BR1;
    if (enableIFVG && checkIFVGEntry(ifvgs, close)) return MODEL_IF1;
    if (enableOB && checkOBEntry(orderBlocks, close)) return MODEL_OB1;
    return -1;  // No valid model
}
```

### Stop Logic with Tight Breaker Override

```java
private double calculateStop(Zone zone, boolean isLong, double defaultStop,
                            double minStop, double maxStop, double tightThreshold) {
    double structureStop;

    if (isLong) {
        structureStop = zone.bottom - stopBuffer;
    } else {
        structureStop = zone.top + stopBuffer;
    }

    double stopDistance = Math.abs(entryPrice - structureStop);

    // If Breaker zone is too tight (< threshold), use default stop
    if (zone.type.equals("BREAKER") && stopDistance < tightThreshold) {
        stopDistance = defaultStop;  // Override to 10-15 pts default
    }

    // Clamp to min/max
    stopDistance = Math.max(minStop, Math.min(maxStop, stopDistance));

    return isLong ? entryPrice - stopDistance : entryPrice + stopDistance;
}
```

### Sweep Detection

```java
// SSL sweep (for long setups)
double sweepThreshold = sslLevel - (sweepMinTicks * tickSize);
if (low <= sweepThreshold) {
    boolean validSweep = !requireCloseBack || (close > sslLevel);
    if (validSweep) {
        sweepDetected = true;
        sweepLow = low;
    }
}
```

### MSS (Market Structure Shift)

```java
// MSS Up (bullish)
boolean mssBreak = requireClose ? (close > swingHigh) : (high > swingHigh);
if (mssBreak) {
    double bodySize = Math.abs(close - open);
    if (bodySize >= minDisplacementTicks * tickSize) {
        mssConfirmed = true;
    }
}
```

### FVG (Fair Value Gap) Detection

```java
// Bullish FVG: gap up (bar[0].high < bar[2].low)
double bar0High = series.getHigh(index - 2);
double bar2Low = series.getLow(index);
if (bar2Low > bar0High && (bar2Low - bar0High) >= minGapTicks * tickSize) {
    fvgTop = bar2Low;
    fvgBottom = bar0High;
    fvgDetected = true;
}

// Bearish FVG: gap down (bar[0].low > bar[2].high)
double bar0Low = series.getLow(index - 2);
double bar2High = series.getHigh(index);
if (bar0Low > bar2High && (bar0Low - bar2High) >= minGapTicks * tickSize) {
    fvgTop = bar0Low;
    fvgBottom = bar2High;
    fvgDetected = true;
}
```

### IFVG (Inverse FVG)

An FVG that price trades back through, inverting its directional bias:

```java
// Bullish IFVG: prior bearish FVG + price closes above mid
if (!zone.isBullish && close > zone.getMid()) {
    zone.isInverted = true;
    zone.isBullish = true;  // Now bullish continuation zone
}
```

### Swing Point Detection

```java
private double findSwingLow(DataSeries series, int index, int strength) {
    for (int i = index - strength - 1; i >= strength; i--) {
        double low = series.getLow(i);
        boolean isSwing = true;
        for (int j = 1; j <= strength && isSwing; j++) {
            if (i - j >= 0 && series.getLow(i - j) <= low) isSwing = false;
            if (i + j <= index && series.getLow(i + j) <= low) isSwing = false;
        }
        if (isSwing) return low;
    }
    return Double.NaN;
}
```

### Displacement Detection

```java
// Calculate average range
double avgRange = 0;
for (int i = index - lookback; i < index; i++) {
    avgRange += series.getHigh(i) - series.getLow(i);
}
avgRange /= lookback;

// Check for displacement (range > multiple of average)
double threshold = avgRange * 1.6;  // 1.6x average
double currentRange = series.getHigh(index) - series.getLow(index);
double body = series.getClose(index) - series.getOpen(index);

if (currentRange >= threshold && body > 0) {
    bullishDisplacement = true;
}
```

### Chop Filter (Overlap Ratio)

```java
private boolean isChoppy(DataSeries series, int index) {
    double totalOverlap = 0;
    double totalRange = 0;

    for (int i = index - lookback + 1; i <= index; i++) {
        double bodyTop = Math.max(series.getOpen(i), series.getClose(i));
        double bodyBottom = Math.min(series.getOpen(i), series.getClose(i));
        double prevBodyTop = Math.max(series.getOpen(i-1), series.getClose(i-1));
        double prevBodyBottom = Math.min(series.getOpen(i-1), series.getClose(i-1));

        double overlapTop = Math.min(bodyTop, prevBodyTop);
        double overlapBottom = Math.max(bodyBottom, prevBodyBottom);
        if (overlapTop > overlapBottom) {
            totalOverlap += overlapTop - overlapBottom;
        }
        totalRange += Math.abs(bodyTop - bodyBottom);
    }

    return (totalOverlap / totalRange) > 0.55;  // >55% overlap = choppy
}
```

---

## Common Pitfalls & Fixes

### 1. Forgetting Bar Completion Check

**Problem:** Processing incomplete bars leads to false signals.

**Fix:**
```java
if (!series.isBarComplete(index)) return;
```

### 2. Not Handling NaN Values

**Problem:** Calculations fail with NaN inputs.

**Fix:**
```java
if (Double.isNaN(pdh) || Double.isNaN(pdl)) return;
```

### 3. State Not Reset Between Days

**Problem:** Yesterday's state affects today's trading.

**Fix:** Implement proper daily reset with day tracking.

### 4. Position Size Overflow

**Problem:** Partial exit quantity exceeds position.

**Fix:**
```java
int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
if (partialQty > 0 && partialQty < Math.abs(position)) {
    // Safe to exit partial
}
```

### 5. Ignoring Tick Rounding

**Problem:** Prices not aligned to tick size.

**Fix:**
```java
stopPrice = instr.round(stopPrice);
targetPrice = instr.round(targetPrice);
```

### 6. Blocking New Entries After EOD

**Problem:** Entries still happen after EOD cutoff.

**Fix:** Check EOD in both `calculate()` AND `onSignal()`.

### 7. Forgetting Cooldown Tracking

**Problem:** Trades too close together.

**Fix:**
```java
private long lastTradeTime = 0;

// In trade logic:
boolean pastCooldown = barTime - lastTradeTime >= cooldownMinutes * 60000L;

// After entry:
lastTradeTime = barTime;
```

---

## Best Practices

### 1. Always Use Enums for Values and Signals

```java
enum Values { PDH, PDL, EQUILIBRIUM, SIGNAL_LINE }
enum Signals { ENTRY_LONG, ENTRY_SHORT, STOP_HIT, TARGET_HIT }
```

### 2. Organize Settings into Logical Tabs

- Sessions / Time
- Filters / Market State
- Entry
- Risk / Position Sizing
- Exits
- Display

### 3. Provide Quick Settings

Most commonly adjusted settings should be in quick settings:
```java
sd.addQuickSettings(ENABLE_LONG, ENABLE_SHORT, CONTRACTS, TARGET_R);
```

### 4. Debug Logging

Use debug() for development, it shows in MotiveWave console:
```java
debug("MMBM: SSL sweep at " + low);
debug(String.format("LONG: qty=%d, entry=%.2f, stop=%.2f", qty, entry, stop));
```

### 5. Document Your Strategy

Create a markdown file in `/docs` with:
- Strategy overview
- Trade logic (entry sequence)
- All settings with descriptions
- Example trades
- Tips for success

### 6. Use Descriptive Constant Names

```java
// Good
private static final int BIAS_BULLISH = 1;
private static final int BIAS_BEARISH = -1;
private static final int BIAS_NEUTRAL = 0;

// Bad
private static final int B = 1;
private static final int S = -1;
```

### 7. Separate Concerns

- Detection logic in `calculate()`
- Order execution in `onSignal()`
- Exit management in `onBarClose()`

### 8. Handle All Exit Scenarios

- Stop loss
- Take profit (partial + full)
- Breakeven
- Time stop
- Forced flat / EOD
- Daily loss limit

---

## File Structure

```
project/
├── src/main/java/com/mw/studies/
│   ├── *.java                    # Strategy files
│   └── nls/
│       └── strings.properties    # Localization
├── docs/
│   ├── README.md                 # Strategy index
│   ├── StrategyName.md           # Per-strategy docs
│   └── ...
├── build.gradle                  # Build configuration
├── gradlew.bat                   # Gradle wrapper
├── mwbuilder.bat                 # Custom build script
└── lessons.md                    # This file
```

---

## Strategy Checklist

Before deploying a new strategy:

- [ ] StudyHeader annotation complete
- [ ] strings.properties entries added
- [ ] All settings have sensible defaults
- [ ] Daily reset logic implemented
- [ ] Bar completion check in calculate()
- [ ] NaN handling for all calculations
- [ ] EOD flattening if needed
- [ ] Position size validation
- [ ] Tick rounding on all prices
- [ ] Debug logging for key events
- [ ] Documentation created
- [ ] README.md updated
- [ ] Build passes validation
- [ ] Tested in simulation

---

*Last updated: February 2, 2026*
