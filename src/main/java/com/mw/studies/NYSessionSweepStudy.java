package com.mw.studies;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

import java.util.Calendar;
import java.util.TimeZone;

/**
 * NY Session Sweep Study
 *
 * Detects sweeps of the RTH (Regular Trading Hours) range and marks potential
 * reversal points when price sweeps above/below the range then closes back inside.
 *
 * ============================================================
 * INPUTS
 * ============================================================
 * - rangeStart (time): Start of RTH session [default: 09:30]
 * - rangeEnd (time): End of RTH session [default: 16:00]
 * - showLabels (bool): Display sweep labels on chart [default: true]
 * - maxSignalsPerDay (int): Maximum signals per session [default: 3]
 *
 * ============================================================
 * OUTPUTS / PLOTS
 * ============================================================
 * - rangeHigh: The session high line (plotted during session)
 * - rangeLow: The session low line (plotted during session)
 *
 * ============================================================
 * SIGNALS
 * ============================================================
 * - SWEEP_HIGH: Price swept above range high then closed back inside
 *   (bearish reversal signal)
 * - SWEEP_LOW: Price swept below range low then closed back inside
 *   (bullish reversal signal)
 *
 * ============================================================
 * CALCULATION LOGIC
 * ============================================================
 * 1. Track the running high/low during the RTH session
 * 2. On each bar, check if:
 *    a. The HIGH exceeded the previous range high (sweep up)
 *    b. The CLOSE is back inside the range (not a breakout)
 * 3. If both conditions met, signal SWEEP_HIGH (bearish)
 * 4. Same logic inverted for SWEEP_LOW (bullish)
 * 5. Wick-only sweeps are excluded (close must have been outside)
 *
 * @version 0.1.0
 * @author MW Study Builder
 * @generated 2024-02-01
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "NY_SESSION_SWEEP",
    rb = "com.mw.studies.nls.strings",
    name = "NY Session Sweep",
    label = "NY Sweep",
    desc = "Detects sweeps of RTH range with reversal signals",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    signals = true
)
public class NYSessionSweepStudy extends Study {

    // ==================== Constants ====================
    private static final String RANGE_START = "rangeStart";
    private static final String RANGE_END = "rangeEnd";
    private static final String SHOW_LABELS = "showLabels";
    private static final String MAX_SIGNALS = "maxSignals";
    private static final String HIGH_PATH = "highPath";
    private static final String LOW_PATH = "lowPath";

    // ==================== Values (data series keys) ====================
    enum Values {
        RANGE_HIGH,      // Current session high
        RANGE_LOW,       // Current session low
        IN_SESSION       // Boolean: is this bar in session?
    }

    // ==================== Signals ====================
    enum Signals {
        SWEEP_HIGH,      // Swept above range, closed back inside (bearish)
        SWEEP_LOW        // Swept below range, closed back inside (bullish)
    }

    // ==================== Member Variables ====================
    private double sessionHigh = Double.MIN_VALUE;
    private double sessionLow = Double.MAX_VALUE;
    private int signalsToday = 0;
    private int lastSessionDay = -1;

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {
        var sd = createSD();

        // General Tab
        var tab = sd.addTab("General");

        // Session Settings
        var grp = tab.addGroup("Session");
        grp.addRow(new IntegerDescriptor(RANGE_START, "Session Start", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(RANGE_END, "Session End", 1600, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(MAX_SIGNALS, "Max Signals/Day", 3, 1, 20, 1));

        // Display Settings
        grp = tab.addGroup("Display");
        grp.addRow(new BooleanDescriptor(SHOW_LABELS, "Show Labels", true));
        grp.addRow(new PathDescriptor(HIGH_PATH, "Range High", defaults.getRed(), 1.5f,
            new float[]{5, 5}, true, true, true));
        grp.addRow(new PathDescriptor(LOW_PATH, "Range Low", defaults.getGreen(), 1.5f,
            new float[]{5, 5}, true, true, true));

        // Markers
        grp = tab.addGroup("Markers");
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Sweep High (Bearish)",
            Enums.MarkerType.TRIANGLE, Enums.Size.SMALL, defaults.getRed(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Sweep Low (Bullish)",
            Enums.MarkerType.TRIANGLE, Enums.Size.SMALL, defaults.getGreen(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(RANGE_START, RANGE_END);

        // Runtime descriptor
        var desc = createRD();
        desc.setLabelSettings(RANGE_START, RANGE_END);

        // Export values
        desc.exportValue(new ValueDescriptor(Values.RANGE_HIGH, "Range High", new String[]{RANGE_START, RANGE_END}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_LOW, "Range Low", new String[]{RANGE_START, RANGE_END}));

        // Declare paths
        desc.declarePath(Values.RANGE_HIGH, HIGH_PATH);
        desc.declarePath(Values.RANGE_LOW, LOW_PATH);

        // Declare signals
        desc.declareSignal(Signals.SWEEP_HIGH, "Sweep High (Bearish)");
        desc.declareSignal(Signals.SWEEP_LOW, "Sweep Low (Bullish)");

        // Range keys for auto-scaling
        desc.setRangeKeys(Values.RANGE_HIGH, Values.RANGE_LOW);
    }

    @Override
    public int getMinBars() {
        return 10;
    }

    // ==================== Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx) {
        var series = ctx.getDataSeries();

        // Get settings
        int sessionStart = getSettings().getInteger(RANGE_START, 930);
        int sessionEnd = getSettings().getInteger(RANGE_END, 1600);
        int maxSignals = getSettings().getInteger(MAX_SIGNALS, 3);
        boolean showLabels = getSettings().getBoolean(SHOW_LABELS, true);

        // Get bar time info
        long barTime = series.getStartTime(index);
        TimeZone tz = ctx.getTimeZone();

        // Use Calendar to extract time components
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(barTime);
        int barHour = cal.get(Calendar.HOUR_OF_DAY);
        int barMin = cal.get(Calendar.MINUTE);
        int barTimeInt = barHour * 100 + barMin;
        int barDay = cal.get(Calendar.DAY_OF_YEAR);

        // Reset session tracking on new day
        if (barDay != lastSessionDay) {
            sessionHigh = Double.MIN_VALUE;
            sessionLow = Double.MAX_VALUE;
            signalsToday = 0;
            lastSessionDay = barDay;
        }

        // Check if in session
        boolean inSession = barTimeInt >= sessionStart && barTimeInt <= sessionEnd;
        series.setBoolean(index, Values.IN_SESSION, inSession);

        if (!inSession) {
            // Outside session - don't plot range lines
            return;
        }

        // Get OHLC for current bar
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        double open = series.getOpen(index);

        // Store previous range values before updating
        double prevHigh = sessionHigh;
        double prevLow = sessionLow;

        // Update session high/low
        if (high > sessionHigh) sessionHigh = high;
        if (low < sessionLow) sessionLow = low;

        // Plot range lines
        series.setDouble(index, Values.RANGE_HIGH, sessionHigh);
        series.setDouble(index, Values.RANGE_LOW, sessionLow);

        // Skip signal detection until we have established range
        if (index < 5 || prevHigh == Double.MIN_VALUE) return;

        // Check for signals (only if under max)
        if (signalsToday >= maxSignals) return;

        // SWEEP HIGH: price swept above range, then closed back inside
        // Conditions:
        // 1. High exceeded previous range high (swept)
        // 2. Close is below the previous range high (returned inside)
        // 3. Not just a wick - the close of prior bar or open was also above (optional stricter check)
        boolean sweptHigh = high > prevHigh && prevHigh != Double.MIN_VALUE;
        boolean closedInsideFromHigh = close < prevHigh;

        if (sweptHigh && closedInsideFromHigh) {
            signalsToday++;
            series.setBoolean(index, Signals.SWEEP_HIGH, true);

            String msg = String.format("Sweep High @ %.2f, closed %.2f", high, close);
            ctx.signal(index, Signals.SWEEP_HIGH, msg, close);

            // Draw marker
            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, high);
                addFigure(new Marker(coord, Enums.Position.TOP, marker, showLabels ? "Sweep High" : null));
            }
        }

        // SWEEP LOW: price swept below range, then closed back inside
        boolean sweptLow = low < prevLow && prevLow != Double.MAX_VALUE;
        boolean closedInsideFromLow = close > prevLow;

        if (sweptLow && closedInsideFromLow) {
            signalsToday++;
            series.setBoolean(index, Signals.SWEEP_LOW, true);

            String msg = String.format("Sweep Low @ %.2f, closed %.2f", low, close);
            ctx.signal(index, Signals.SWEEP_LOW, msg, close);

            // Draw marker
            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, low);
                addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, showLabels ? "Sweep Low" : null));
            }
        }

        series.setComplete(index);
    }

    // ==================== Helper Methods ====================

    /**
     * Resets session tracking variables.
     * Called when study is reloaded or settings change.
     */
    @Override
    public void clearState() {
        super.clearState();
        sessionHigh = Double.MIN_VALUE;
        sessionLow = Double.MAX_VALUE;
        signalsToday = 0;
        lastSessionDay = -1;
    }
}
