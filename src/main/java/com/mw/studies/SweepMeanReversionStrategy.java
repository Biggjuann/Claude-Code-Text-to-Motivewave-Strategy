package com.mw.studies;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

import java.util.Calendar;
import java.util.TimeZone;

/**
 * Sweep Mean Reversion Strategy
 *
 * Trades mean reversion setups when price sweeps a range level and reverses.
 * Based on the concept that failed breakouts (sweeps) often lead to mean reversion.
 *
 * ============================================================
 * STRATEGY CONCEPT
 * ============================================================
 * When price sweeps above/below a defined range and then closes back inside,
 * this often indicates a failed breakout (liquidity grab) and sets up a
 * mean reversion trade back toward the opposite side of the range.
 *
 * ============================================================
 * INPUTS
 * ============================================================
 * Range Settings:
 * - rangePeriod (int): Bars to look back for range high/low [default: 20]
 * - rangeType (enum): Session-based or rolling period [default: Period]
 *
 * Entry Filters:
 * - minSweepTicks (int): Minimum sweep size in ticks [default: 2]
 * - requireInsideClose (bool): Close must be inside range [default: true]
 *
 * Risk Management:
 * - stopBeyondSweep (int): Ticks beyond sweep high/low for stop [default: 4]
 * - targetMidRange (bool): Target middle of range [default: false]
 * - targetOppositeSide (bool): Target opposite range level [default: true]
 * - maxRiskPercent (double): Max risk as % of account [default: 1.0]
 *
 * ============================================================
 * ENTRY LOGIC
 * ============================================================
 * SHORT Entry (Sweep High):
 * - Bar high exceeds range high (sweep)
 * - Bar close is below range high (failed breakout)
 * - Sweep size >= minimum ticks
 * - Enter short on close
 *
 * LONG Entry (Sweep Low):
 * - Bar low goes below range low (sweep)
 * - Bar close is above range low (failed breakout)
 * - Sweep size >= minimum ticks
 * - Enter long on close
 *
 * ============================================================
 * EXIT LOGIC
 * ============================================================
 * Stop Loss: Beyond the sweep point + buffer
 * Take Profit: Middle of range or opposite side (configurable)
 *
 * @version 0.1.0
 * @author MW Study Builder
 * @generated 2024-02-01
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "SWEEP_MEAN_REVERSION",
    rb = "com.mw.studies.nls.strings",
    name = "Sweep Mean Reversion",
    label = "Sweep MR",
    desc = "Trades mean reversion after range sweeps",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    signals = true,
    strategy = true,
    autoEntry = true,
    manualEntry = false,
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true,
    supportsBarUpdates = false
)
public class SweepMeanReversionStrategy extends Study {

    // ==================== Constants ====================
    private static final String RANGE_PERIOD = "rangePeriod";
    private static final String MIN_SWEEP_TICKS = "minSweepTicks";
    private static final String REQUIRE_INSIDE_CLOSE = "requireInsideClose";
    private static final String STOP_BEYOND_SWEEP = "stopBeyondSweep";
    private static final String TARGET_MID_RANGE = "targetMidRange";
    private static final String TARGET_OPPOSITE = "targetOpposite";
    private static final String MAX_TRADES = "maxTrades";

    private static final String HIGH_PATH = "highPath";
    private static final String LOW_PATH = "lowPath";
    private static final String MID_PATH = "midPath";

    // ==================== Values ====================
    enum Values {
        RANGE_HIGH,      // Rolling range high
        RANGE_LOW,       // Rolling range low
        RANGE_MID,       // Range midpoint
        SWEEP_SIZE       // Size of last sweep in ticks
    }

    // ==================== Signals ====================
    enum Signals {
        SWEEP_HIGH_SHORT,  // Sweep high - go short
        SWEEP_LOW_LONG     // Sweep low - go long
    }

    // ==================== Member Variables ====================
    private int tradesToday = 0;
    private int lastTradeDay = -1;
    private double lastSweepHigh = 0;
    private double lastSweepLow = 0;

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {
        var sd = createSD();

        // ===== Range Settings Tab =====
        var tab = sd.addTab("Range");

        var grp = tab.addGroup("Range Calculation");
        grp.addRow(new IntegerDescriptor(RANGE_PERIOD, "Lookback Period", 20, 5, 200, 1));

        grp = tab.addGroup("Display");
        grp.addRow(new PathDescriptor(HIGH_PATH, "Range High",
            defaults.getRed(), 1.0f, new float[]{5, 3}, true, true, true));
        grp.addRow(new PathDescriptor(LOW_PATH, "Range Low",
            defaults.getGreen(), 1.0f, new float[]{5, 3}, true, true, true));
        grp.addRow(new PathDescriptor(MID_PATH, "Range Mid",
            defaults.getYellow(), 1.0f, new float[]{2, 2}, true, true, true));

        // ===== Entry Tab =====
        tab = sd.addTab("Entry");

        grp = tab.addGroup("Sweep Detection");
        grp.addRow(new IntegerDescriptor(MIN_SWEEP_TICKS, "Min Sweep Size (ticks)", 2, 1, 50, 1));
        grp.addRow(new BooleanDescriptor(REQUIRE_INSIDE_CLOSE, "Require Inside Close", true));

        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES, "Max Trades/Day", 3, 1, 20, 1));

        // ===== Exit Tab =====
        tab = sd.addTab("Exit");

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new IntegerDescriptor(STOP_BEYOND_SWEEP, "Ticks Beyond Sweep", 4, 1, 50, 1));

        grp = tab.addGroup("Take Profit Target");
        grp.addRow(new BooleanDescriptor(TARGET_MID_RANGE, "Target Range Mid", false));
        grp.addRow(new BooleanDescriptor(TARGET_OPPOSITE, "Target Opposite Side", true));

        // ===== Markers Tab =====
        tab = sd.addTab("Markers");

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Sweep Low (Long)",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Sweep High (Short)",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(RANGE_PERIOD, MIN_SWEEP_TICKS);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(RANGE_PERIOD);

        desc.exportValue(new ValueDescriptor(Values.RANGE_HIGH, "Range High", new String[]{RANGE_PERIOD}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_LOW, "Range Low", new String[]{RANGE_PERIOD}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_MID, "Range Mid", new String[]{RANGE_PERIOD}));

        desc.declarePath(Values.RANGE_HIGH, HIGH_PATH);
        desc.declarePath(Values.RANGE_LOW, LOW_PATH);
        desc.declarePath(Values.RANGE_MID, MID_PATH);

        desc.declareSignal(Signals.SWEEP_HIGH_SHORT, "Sweep High - Short Entry");
        desc.declareSignal(Signals.SWEEP_LOW_LONG, "Sweep Low - Long Entry");

        desc.setRangeKeys(Values.RANGE_HIGH, Values.RANGE_LOW);
    }

    @Override
    public int getMinBars() {
        return getSettings().getInteger(RANGE_PERIOD, 20) + 5;
    }

    // ==================== Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx) {
        var series = ctx.getDataSeries();

        int rangePeriod = getSettings().getInteger(RANGE_PERIOD, 20);
        int minSweepTicks = getSettings().getInteger(MIN_SWEEP_TICKS, 2);
        boolean requireInsideClose = getSettings().getBoolean(REQUIRE_INSIDE_CLOSE, true);
        int maxTrades = getSettings().getInteger(MAX_TRADES, 3);

        if (index < rangePeriod + 1) return;

        // Calculate range (looking back from previous bar to avoid look-ahead)
        double rangeHigh = Double.MIN_VALUE;
        double rangeLow = Double.MAX_VALUE;

        for (int i = index - rangePeriod; i < index; i++) {
            double h = series.getHigh(i);
            double l = series.getLow(i);
            if (h > rangeHigh) rangeHigh = h;
            if (l < rangeLow) rangeLow = l;
        }

        double rangeMid = (rangeHigh + rangeLow) / 2.0;

        series.setDouble(index, Values.RANGE_HIGH, rangeHigh);
        series.setDouble(index, Values.RANGE_LOW, rangeLow);
        series.setDouble(index, Values.RANGE_MID, rangeMid);

        // Current bar OHLC
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        long barTime = series.getStartTime(index);

        // Get tick size for calculations
        double tickSize = ctx.getInstrument().getTickSize();

        // Reset daily counter
        TimeZone tz = ctx.getTimeZone();
        int barDay = getDayOfYear(barTime, tz);
        if (barDay != lastTradeDay) {
            tradesToday = 0;
            lastTradeDay = barDay;
        }

        // Only check signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (tradesToday >= maxTrades) return;

        // Check for SWEEP HIGH (bearish)
        // Condition: High exceeded range high, but close is below range high
        boolean sweptHigh = high > rangeHigh;
        boolean closedInside = close <= rangeHigh;
        double sweepHighSize = (high - rangeHigh) / tickSize;

        if (sweptHigh && (!requireInsideClose || closedInside) && sweepHighSize >= minSweepTicks) {
            lastSweepHigh = high;
            series.setDouble(index, Values.SWEEP_SIZE, sweepHighSize);
            series.setBoolean(index, Signals.SWEEP_HIGH_SHORT, true);

            String msg = String.format("Sweep High: %.2f (%.0f ticks above range)", high, sweepHighSize);
            ctx.signal(index, Signals.SWEEP_HIGH_SHORT, msg, close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, high);
                addFigure(new Marker(coord, Enums.Position.TOP, marker, "SHORT"));
            }
        }

        // Check for SWEEP LOW (bullish)
        boolean sweptLow = low < rangeLow;
        boolean closedAbove = close >= rangeLow;
        double sweepLowSize = (rangeLow - low) / tickSize;

        if (sweptLow && (!requireInsideClose || closedAbove) && sweepLowSize >= minSweepTicks) {
            lastSweepLow = low;
            series.setDouble(index, Values.SWEEP_SIZE, sweepLowSize);
            series.setBoolean(index, Signals.SWEEP_LOW_LONG, true);

            String msg = String.format("Sweep Low: %.2f (%.0f ticks below range)", low, sweepLowSize);
            ctx.signal(index, Signals.SWEEP_LOW_LONG, msg, close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, low);
                addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "LONG"));
            }
        }

        series.setComplete(index);
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("Sweep Mean Reversion Strategy activated");
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position: " + position);
        }
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        var instr = ctx.getInstrument();
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;

        int position = ctx.getPosition();
        int qty = getSettings().getTradeLots() * instr.getDefaultQuantity();
        double tickSize = instr.getTickSize();

        int stopBeyondSweep = getSettings().getInteger(STOP_BEYOND_SWEEP, 4);
        boolean targetMid = getSettings().getBoolean(TARGET_MID_RANGE, false);
        boolean targetOpposite = getSettings().getBoolean(TARGET_OPPOSITE, true);
        int maxTrades = getSettings().getInteger(MAX_TRADES, 3);

        if (tradesToday >= maxTrades) {
            debug("Max trades reached: " + tradesToday);
            return;
        }

        Double rangeHigh = series.getDouble(index, Values.RANGE_HIGH);
        Double rangeLow = series.getDouble(index, Values.RANGE_LOW);
        Double rangeMid = series.getDouble(index, Values.RANGE_MID);

        if (rangeHigh == null || rangeLow == null || rangeMid == null) return;

        if (signal == Signals.SWEEP_HIGH_SHORT) {
            // Close any long position first
            if (position > 0) {
                ctx.closeAtMarket();
                debug("Closed LONG before SHORT entry");
            }

            if (position >= 0) {
                ctx.sell(qty);
                tradesToday++;

                // Calculate stop above sweep high
                double stopPrice = instr.round(lastSweepHigh + (stopBeyondSweep * tickSize));

                // Calculate target
                double targetPrice;
                if (targetMid) {
                    targetPrice = rangeMid;
                } else if (targetOpposite) {
                    targetPrice = rangeLow;
                } else {
                    targetPrice = rangeMid;
                }

                debug(String.format("SHORT entry: Stop=%.2f, Target=%.2f", stopPrice, targetPrice));
            }
        }
        else if (signal == Signals.SWEEP_LOW_LONG) {
            // Close any short position first
            if (position < 0) {
                ctx.closeAtMarket();
                debug("Closed SHORT before LONG entry");
            }

            if (position <= 0) {
                ctx.buy(qty);
                tradesToday++;

                // Calculate stop below sweep low
                double stopPrice = instr.round(lastSweepLow - (stopBeyondSweep * tickSize));

                // Calculate target
                double targetPrice;
                if (targetMid) {
                    targetPrice = rangeMid;
                } else if (targetOpposite) {
                    targetPrice = rangeHigh;
                } else {
                    targetPrice = rangeMid;
                }

                debug(String.format("LONG entry: Stop=%.2f, Target=%.2f", stopPrice, targetPrice));
            }
        }
    }

    // ==================== Helper Methods ====================

    private int getDayOfYear(long time, TimeZone tz) {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.DAY_OF_YEAR);
    }

    @Override
    public void clearState() {
        super.clearState();
        tradesToday = 0;
        lastTradeDay = -1;
        lastSweepHigh = 0;
        lastSweepLow = 0;
    }
}
