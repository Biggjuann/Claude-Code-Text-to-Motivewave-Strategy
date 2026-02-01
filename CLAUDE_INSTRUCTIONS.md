# Claude Code Instructions for Study Generation

This document defines how Claude Code should generate MotiveWave studies from prompt specs.

## When User Asks for a New Study

1. **Read the prompt spec** from `prompts/` directory
2. **Parse the spec** to extract:
   - Name and type (study vs strategy)
   - Inputs with types and defaults
   - Outputs (plots, signals)
   - Calculation logic
   - Risk rules (if strategy)
3. **Generate Java file** in `src/main/java/com/mw/studies/`
4. **Update strings.properties** with new labels
5. **Build and deploy** using `gradlew build deploy`

## Code Generation Rules

### File Structure
Every generated study MUST include:
1. Package declaration: `package com.mw.studies;`
2. Complete imports (no wildcards when possible)
3. Full JavaDoc header with:
   - Study name and description
   - INPUTS section with types and defaults
   - OUTPUTS section with plots and signals
   - CALCULATION LOGIC section
   - @version, @author, @generated tags
4. @StudyHeader annotation with all required fields
5. Values enum for data series keys
6. Signals enum (if signals are used)
7. initialize() method with settings UI
8. calculate() method with the logic

### Naming Conventions
- Class name: PascalCase, e.g., `NYSessionSweepStudy`
- Study ID: UPPER_SNAKE_CASE, e.g., `NY_SESSION_SWEEP`
- Constants: UPPER_SNAKE_CASE
- Values enum: PascalCase, e.g., `Values.RANGE_HIGH`
- Input keys: camelCase strings, e.g., `"rangeStart"`

### Required Imports
```java
import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;
```

For strategies, add:
```java
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
```

For time operations:
```java
import java.util.Calendar;
import java.util.TimeZone;
```

### Input Types to Descriptor Mapping
| Spec Type | Java Descriptor |
|-----------|-----------------|
| int | IntegerDescriptor |
| double/float | DoubleDescriptor |
| bool/boolean | BooleanDescriptor |
| time | IntegerDescriptor (HHMM format) |
| price input | InputDescriptor with Enums.BarInput |
| MA method | MAMethodDescriptor |
| color | ColorDescriptor |

### Settings UI Pattern
```java
@Override
public void initialize(Defaults defaults) {
    var sd = createSD();
    var tab = sd.addTab("General");

    // Group inputs logically
    var grp = tab.addGroup("Inputs");
    grp.addRow(new InputDescriptor(...));
    grp.addRow(new IntegerDescriptor(...));

    grp = tab.addGroup("Display");
    grp.addRow(new PathDescriptor(...));

    // Quick settings for toolbar
    sd.addQuickSettings("key1", "key2");

    // Runtime descriptor
    var desc = createRD();
    desc.setLabelSettings(...);
    desc.exportValue(...);
    desc.declarePath(...);
    desc.declareSignal(...);  // if signals used
}
```

### Calculation Pattern
```java
@Override
protected void calculate(int index, DataContext ctx) {
    // 1. Get settings
    int period = getSettings().getInteger("period", 20);

    // 2. Check minimum bars
    if (index < period) return;

    // 3. Get data series
    var series = ctx.getDataSeries();

    // 4. Perform calculations
    Double value = series.sma(index, period, Enums.BarInput.CLOSE);
    if (value == null) return;

    // 5. Store results
    series.setDouble(index, Values.MAIN, value);

    // 6. Check signal conditions
    if (/* condition */) {
        series.setBoolean(index, Signals.SIGNAL_NAME, true);
        ctx.signal(index, Signals.SIGNAL_NAME, "message", price);
    }

    // 7. Mark complete
    series.setComplete(index);
}
```

### Time Filtering Pattern
```java
// Get bar time components
long barTime = series.getStartTime(index);
TimeZone tz = ctx.getTimeZone();
Calendar cal = Calendar.getInstance(tz);
cal.setTimeInMillis(barTime);

int barHour = cal.get(Calendar.HOUR_OF_DAY);
int barMin = cal.get(Calendar.MINUTE);
int barTimeInt = barHour * 100 + barMin;  // e.g., 930 for 9:30

// Check session
int sessionStart = getSettings().getInteger("startTime", 930);
int sessionEnd = getSettings().getInteger("endTime", 1600);
boolean inSession = barTimeInt >= sessionStart && barTimeInt <= sessionEnd;
```

### Drawing Markers
```java
var marker = getSettings().getMarker(Inputs.UP_MARKER);
if (marker.isEnabled()) {
    var coord = new Coordinate(barTime, price);
    addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "Label"));
}
```

## Strategy-Specific Rules

### Additional @StudyHeader Fields
```java
@StudyHeader(
    // ... standard fields ...
    signals = true,
    strategy = true,
    autoEntry = true,
    manualEntry = false,
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true
)
```

### Required Overrides
```java
@Override
public void onActivate(OrderContext ctx) {
    // Initial position logic
}

@Override
public void onDeactivate(OrderContext ctx) {
    // Cleanup logic
}

@Override
public void onSignal(OrderContext ctx, Object signal) {
    // Trade execution logic
}
```

### Position Sizing
```java
var instr = ctx.getInstrument();
int qty = getSettings().getTradeLots() * instr.getDefaultQuantity();
```

## Strategy-Specific Generation

When type = "strategy", the generated code MUST include:

### Additional @StudyHeader fields
```java
signals = true,
strategy = true,
autoEntry = true,
manualEntry = false,
supportsUnrealizedPL = true,
supportsRealizedPL = true,
supportsTotalPL = true,
supportsBarUpdates = false  // Important for strategies
```

### Required imports
```java
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
```

### Required method overrides
```java
@Override
public void onActivate(OrderContext ctx) {
    // Enter initial position if settings allow
}

@Override
public void onDeactivate(OrderContext ctx) {
    // Close positions, reset state
}

@Override
public void onSignal(OrderContext ctx, Object signal) {
    // Execute trades based on signal
}
```

### Signal generation in calculate()
```java
// Only signal on complete bars for strategies
if (!series.isBarComplete(index)) return;

if (buyCondition) {
    series.setBoolean(index, Signals.BUY, true);
    ctx.signal(index, Signals.BUY, "message", price);
}
```

### Data access in OrderContext methods
```java
// Use getDataContext().getDataSeries() in onSignal/onActivate
var series = ctx.getDataContext().getDataSeries();
int index = series.size() - 1;
```

### Position sizing
```java
int qty = getSettings().getTradeLots() * ctx.getInstrument().getDefaultQuantity();
```

See `templates/strategy_patterns.md` for complete reference.

## After Generation

1. Update `src/main/java/com/mw/studies/nls/strings.properties`:
```properties
STUDY_ID=Study Name
LBL_STUDY_ID=Short Label
DESC_STUDY_ID=Description text
```

2. Build and deploy:
```batch
gradlew build deploy
```

3. Verify in MotiveWave:
   - Restart MotiveWave
   - Find study in "MW Generated" menu
   - Add to chart and test

## Example Interaction

**User:** "Create a study that shows the previous day's high and low as horizontal lines"

**Claude Code:**
1. Reads/creates prompt spec
2. Generates `PreviousDayHighLowStudy.java`:
   - Tracks daily high/low reset at midnight
   - Draws horizontal lines at levels
   - Updates lines as new bars form
3. Updates strings.properties
4. Runs `gradlew build deploy`
5. Reports success with instructions to reload
