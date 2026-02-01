# JavaDoc Patterns for MotiveWave Studies

## File Header Template

```java
/**
 * [Study/Strategy Name]
 *
 * [2-3 sentence description of what this study does]
 *
 * ============================================================
 * INPUTS
 * ============================================================
 * - inputName (Type): Description [default: value]
 * - period (int): Lookback period for calculation [default: 20]
 *
 * ============================================================
 * OUTPUTS / PLOTS
 * ============================================================
 * - plotName: Description of what this line/histogram shows
 * - MA: The calculated moving average line
 *
 * ============================================================
 * SIGNALS
 * ============================================================
 * - SIGNAL_NAME: When this signal triggers and what it means
 * - CROSS_ABOVE: Triggers when fast MA crosses above slow MA
 *
 * ============================================================
 * CALCULATION LOGIC
 * ============================================================
 * 1. Step-by-step explanation of the calculation
 * 2. Any special conditions or edge cases
 * 3. When values are considered valid/invalid
 *
 * @version 0.1.0
 * @author MW Study Builder
 * @generated 2024-01-15 10:30:00
 */
```

## Common Input Types

```java
// Price input (OHLC selection)
grp.addRow(new InputDescriptor(Inputs.INPUT, "Input", Enums.BarInput.CLOSE));

// Integer with range
grp.addRow(new IntegerDescriptor(Inputs.PERIOD, "Period", 20, 1, 500, 1));

// Double with range and step
grp.addRow(new DoubleDescriptor("MULTIPLIER", "Multiplier", 2.0, 0.1, 10.0, 0.1));

// Boolean toggle
grp.addRow(new BooleanDescriptor("SHOW_LABELS", "Show Labels", true));

// MA method selection
grp.addRow(new MAMethodDescriptor(Inputs.METHOD, "MA Method", Enums.MAMethod.EMA));

// Color picker
grp.addRow(new ColorDescriptor("UP_COLOR", "Up Color", defaults.getGreen()));

// Time input
grp.addRow(new TimeDescriptor("START_TIME", "Start Time", 930));  // 9:30 AM
```

## Common Plot Descriptors

```java
// Simple line path
grp.addRow(new PathDescriptor(Inputs.PATH, "Line", null, 1.5f, null, true, true, false));

// Path with specific color
var path = new PathDescriptor("MA_PATH", "MA Line", defaults.getBlue(), 1.0f, null, true, true, true);
grp.addRow(path);

// Histogram/bar path
var histogram = new PathDescriptor(Inputs.BAR, "Histogram", defaults.getBarColor(), 1.0f, null, true, false, true);
histogram.setShowAsBars(true);
histogram.setSupportsShowAsBars(true);
grp.addRow(histogram);

// Shade/fill between two paths
grp.addRow(new ShadeDescriptor("FILL", "Fill", "TOP_PATH", "BOTTOM_PATH",
    Enums.ShadeType.BOTH, defaults.getFillColor(), false, true));

// Marker (arrow, triangle, etc.)
grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Up Marker",
    Enums.MarkerType.TRIANGLE, Enums.Size.SMALL, defaults.getGreen(), defaults.getLineColor(), true, true));
```

## Runtime Descriptor Setup

```java
var desc = createRD();

// Label settings (what shows in study label)
desc.setLabelSettings(Inputs.INPUT, Inputs.PERIOD);

// Export values for cursor display and other studies
desc.exportValue(new ValueDescriptor(Values.MA, "MA", new String[]{Inputs.INPUT, Inputs.PERIOD}));

// Declare paths (connect values to visual paths)
desc.declarePath(Values.MA, Inputs.PATH);

// Declare indicators (small value boxes)
desc.declareIndicator(Values.MA, "MA_IND");

// Set range keys for auto-scaling
desc.setRangeKeys(Values.HIGH, Values.LOW);

// Declare signals (for strategies)
desc.declareSignal(Signals.BUY, "Buy Signal");
desc.declareSignal(Signals.SELL, "Sell Signal");
```

## Calculation Patterns

### Basic Moving Average
```java
@Override
protected void calculate(int index, DataContext ctx) {
    Object input = getSettings().getInput(Inputs.INPUT);
    int period = getSettings().getInteger(Inputs.PERIOD);

    if (index < period) return;

    var series = ctx.getDataSeries();
    Double ma = series.sma(index, period, input);

    if (ma == null) return;
    series.setDouble(index, Values.MA, ma);
}
```

### Crossover Detection
```java
// In calculate method:
Double fastMA = series.sma(index, fastPeriod, input);
Double slowMA = series.sma(index, slowPeriod, input);

if (fastMA == null || slowMA == null) return;

series.setDouble(index, Values.FAST, fastMA);
series.setDouble(index, Values.SLOW, slowMA);

// Check for crossovers
boolean crossAbove = crossedAbove(series, index, Values.FAST, Values.SLOW);
boolean crossBelow = crossedBelow(series, index, Values.FAST, Values.SLOW);

if (crossAbove) {
    series.setBoolean(index, Signals.BUY, true);
    ctx.signal(index, Signals.BUY, "Fast crossed above slow", series.getClose(index));
}
```

### Session Time Filtering
```java
// Get bar time and check session
long barTime = series.getStartTime(index);
int barHour = Util.getHour(barTime, ctx.getTimeZone());
int barMin = Util.getMinute(barTime, ctx.getTimeZone());
int barTimeInt = barHour * 100 + barMin;

int sessionStart = getSettings().getInteger("START_TIME", 930);
int sessionEnd = getSettings().getInteger("END_TIME", 1600);

boolean inSession = barTimeInt >= sessionStart && barTimeInt <= sessionEnd;
if (!inSession) return;
```

### Drawing Markers
```java
// Create a marker at the signal point
var c = new Coordinate(series.getStartTime(index), series.getHigh(index));
var marker = getSettings().getMarker(Inputs.UP_MARKER);
if (marker.isEnabled()) {
    addFigure(new Marker(c, Enums.Position.TOP, marker, "Signal message"));
}
```

### Drawing Horizontal Lines
```java
// Draw a horizontal line at a price level
var line = new Line(
    new Coordinate(startTime, price),
    new Coordinate(endTime, price),
    getSettings().getPath("LEVEL_PATH")
);
addFigure(line);
```

## Strategy-Specific Patterns

### Position Sizing
```java
@Override
public void onSignal(OrderContext ctx, Object signal) {
    var instr = ctx.getInstrument();
    int position = ctx.getPosition();
    double tickSize = instr.getTickSize();

    // Fixed lot sizing
    int qty = getSettings().getTradeLots() * instr.getDefaultQuantity();

    // Or risk-based sizing (1% of account)
    double accountEquity = ctx.getCashBalance();
    double riskAmount = accountEquity * 0.01;
    double currentPrice = instr.getLastPrice();
    int riskQty = (int)(riskAmount / currentPrice);
}
```

### Entry with Stop/Target
```java
if (signal == Signals.BUY && position <= 0) {
    double entryPrice = ctx.getInstrument().getLastPrice();
    double stopPrice = entryPrice - (stopTicks * tickSize);
    double targetPrice = entryPrice + (targetTicks * tickSize);

    ctx.buy(qty);
    // Note: Stop/target orders typically set separately or via bracket orders
}
```
