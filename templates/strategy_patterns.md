# Strategy Implementation Patterns for MotiveWave

## Strategy vs Study Differences

### @StudyHeader Additions
```java
@StudyHeader(
    // ... standard study fields ...
    signals = true,           // Required for strategies
    strategy = true,          // Marks this as a strategy
    autoEntry = true,         // Allow automatic trade execution
    manualEntry = false,      // Disable manual entry mode
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true,
    supportsBarUpdates = false  // Only calculate on bar close for strategies
)
```

### Required Imports
```java
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
```

### Required Methods
```java
@Override
public void onActivate(OrderContext ctx) { }

@Override
public void onDeactivate(OrderContext ctx) { }

@Override
public void onSignal(OrderContext ctx, Object signal) { }
```

## OrderContext Methods

### Position Information
```java
int position = ctx.getPosition();              // Current strategy position
float avgEntry = ctx.getAvgEntryPrice();       // Average entry price
double realizedPnL = ctx.getRealizedPnL();     // Realized P&L
double unrealizedPnL = ctx.getUnrealizedPnL(); // Unrealized P&L
int accountPos = ctx.getAccountPosition();     // Full account position
```

### Instrument Information
```java
var instr = ctx.getInstrument();
double tickSize = instr.getTickSize();
double lastPrice = instr.getLastPrice();
int defaultQty = instr.getDefaultQuantity();
double roundedPrice = instr.round(price);
```

### Account Information
```java
double cashBalance = ctx.getCashBalance();
long currentTime = ctx.getCurrentTime();
```

### Accessing Data Series in Order Methods
```java
// In onSignal, onActivate, onDeactivate:
var series = ctx.getDataContext().getDataSeries();
int index = series.size() - 1;
Double value = series.getDouble(index, Values.MY_VALUE);
```

## Order Execution

### Basic Orders
```java
// Market orders
ctx.buy(qty);           // Buy at market
ctx.sell(qty);          // Sell at market
ctx.closeAtMarket();    // Close entire position

// With price
ctx.buy(qty, price);    // Limit buy
ctx.sell(qty, price);   // Limit sell
```

### Position Sizing
```java
// Fixed lot sizing (from settings panel)
int qty = getSettings().getTradeLots() * instr.getDefaultQuantity();

// Risk-based sizing (1% of account)
double riskPercent = 0.01;
double accountEquity = ctx.getCashBalance();
double riskAmount = accountEquity * riskPercent;
double stopDistance = 10 * tickSize;
int qty = (int)(riskAmount / stopDistance);
```

## Signal Generation Pattern

### In calculate() method:
```java
// Check conditions
boolean buyCondition = /* your logic */;
boolean sellCondition = /* your logic */;

// Only signal on complete bars for strategies
if (!series.isBarComplete(index)) return;

if (buyCondition) {
    series.setBoolean(index, Signals.BUY, true);
    ctx.signal(index, Signals.BUY, "Buy reason", price);
}

if (sellCondition) {
    series.setBoolean(index, Signals.SELL, true);
    ctx.signal(index, Signals.SELL, "Sell reason", price);
}
```

### In onSignal() method:
```java
@Override
public void onSignal(OrderContext ctx, Object signal) {
    int position = ctx.getPosition();
    int qty = getTradeQuantity(ctx);

    if (signal == Signals.BUY) {
        // Close shorts first
        if (position < 0) ctx.closeAtMarket();

        // Enter long
        if (position <= 0) {
            ctx.buy(qty);
            // Set up stop/target
        }
    }
    else if (signal == Signals.SELL) {
        // Close longs first
        if (position > 0) ctx.closeAtMarket();

        // Enter short
        if (position >= 0) {
            ctx.sell(qty);
            // Set up stop/target
        }
    }
}
```

## Risk Management Patterns

### ATR-Based Stop Loss
```java
Double atr = series.atr(index, atrPeriod);
double stopDistance = atr * multiplier;

if (isLong) {
    stopPrice = entryPrice - stopDistance;
    targetPrice = entryPrice + (stopDistance * riskRewardRatio);
} else {
    stopPrice = entryPrice + stopDistance;
    targetPrice = entryPrice - (stopDistance * riskRewardRatio);
}
```

### Fixed Tick Stop Loss
```java
int stopTicks = 20;
double stopDistance = stopTicks * tickSize;
```

### Daily Trade Limits
```java
// Member variables
private int tradesToday = 0;
private int lastTradeDay = -1;

// In calculate():
int barDay = getDayOfYear(barTime, tz);
if (barDay != lastTradeDay) {
    tradesToday = 0;
    lastTradeDay = barDay;
}

// In onSignal():
if (tradesToday >= maxTrades) return;
tradesToday++;
```

## Strategy Lifecycle

### onActivate Pattern
```java
@Override
public void onActivate(OrderContext ctx) {
    // Only enter if "Enter on Activate" is checked
    if (!getSettings().isEnterOnActivate()) return;

    var series = ctx.getDataContext().getDataSeries();
    int index = series.size() - 1;

    // Check current conditions
    Double indicator = series.getDouble(index, Values.INDICATOR);
    if (indicator == null) return;

    int qty = getTradeQuantity(ctx);

    // Enter based on current state
    if (indicator > threshold) {
        ctx.buy(qty);
    } else {
        ctx.sell(qty);
    }
}
```

### onDeactivate Pattern
```java
@Override
public void onDeactivate(OrderContext ctx) {
    int position = ctx.getPosition();
    if (position != 0) {
        ctx.closeAtMarket();
        debug("Deactivated - closed position");
    }
    // Reset state
    resetTradeState();
}
```

## State Management

### Clearing State
```java
@Override
public void clearState() {
    super.clearState();
    tradesToday = 0;
    lastTradeDay = -1;
    // Reset any other member variables
}
```

## Debug Logging
```java
debug("Message: " + value);  // Shows in MotiveWave console
```

## Complete Strategy Template

```java
@StudyHeader(
    namespace = "com.mw.studies",
    id = "MY_STRATEGY",
    name = "My Strategy",
    strategy = true,
    autoEntry = true,
    signals = true,
    // ... other fields
)
public class MyStrategy extends Study {

    enum Values { INDICATOR }
    enum Signals { BUY, SELL }

    private int tradesToday = 0;
    private int lastTradeDay = -1;

    @Override
    public void initialize(Defaults defaults) {
        // Settings UI setup
        var desc = createRD();
        desc.declareSignal(Signals.BUY, "Buy");
        desc.declareSignal(Signals.SELL, "Sell");
    }

    @Override
    protected void calculate(int index, DataContext ctx) {
        // Calculate indicators
        // Generate signals with ctx.signal()
    }

    @Override
    public void onActivate(OrderContext ctx) {
        // Initial entry if enabled
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        // Close positions
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        // Execute trades based on signals
    }

    @Override
    public void clearState() {
        super.clearState();
        // Reset member variables
    }
}
```
