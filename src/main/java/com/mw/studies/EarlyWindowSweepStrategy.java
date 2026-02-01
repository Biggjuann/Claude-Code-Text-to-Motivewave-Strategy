package com.mw.studies;

import java.util.Calendar;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * 6-10am Range Sweep Mean Reversion Strategy (Early Window)
 *
 * Builds a range during the 6:00-10:00 AM ET session, then trades
 * mean reversion when price sweeps and closes back inside the range
 * during the early trade window (10:00-10:30 AM ET).
 *
 * Features:
 * - Configurable range and trade windows (America/New_York timezone)
 * - Single-bar or lookback sweep detection
 * - Optional close-back-inside requirement
 * - Two stop loss modes: fixed from entry or beyond range boundary
 * - Three target modes: midpoint, opposite boundary, or partial split
 * - Max trades per day and one-attempt-per-side limits
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "EARLY_WINDOW_SWEEP",
    rb = "com.mw.studies.nls.strings",
    name = "EARLY_WINDOW_SWEEP",
    label = "LBL_EARLY_WINDOW_SWEEP",
    desc = "DESC_EARLY_WINDOW_SWEEP",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    strategy = true,
    autoEntry = true,
    manualEntry = false,
    signals = true,
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true,
    supportsBarUpdates = false
)
public class EarlyWindowSweepStrategy extends Study
{
    // ==================== Input Keys ====================
    // Sessions
    private static final String RANGE_START = "rangeStart";
    private static final String RANGE_END = "rangeEnd";
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";

    // Sweep Rules
    private static final String USE_LOOKBACK_SWEEP = "useLookbackSweep";
    private static final String SWEEP_LOOKBACK_BARS = "sweepLookbackBars";
    private static final String REQUIRE_CLOSE_BACK_INSIDE = "requireCloseBackInside";

    // Risk
    private static final String CONTRACTS = "contracts";
    private static final String STOPLOSS_ENABLED = "stoplossEnabled";
    private static final String STOPLOSS_MODE = "stoplossMode";
    private static final String STOPLOSS_POINTS = "stoplossPoints";

    // Targets
    private static final String TARGET_MODE = "targetMode";
    private static final String PARTIAL_PCT_AT_MID = "partialPctAtMid";

    // Limits
    private static final String MAX_TRADES_PER_DAY = "maxTradesPerDay";
    private static final String ONE_ATTEMPT_PER_SIDE = "oneAttemptPerSide";

    // Path keys
    private static final String RANGE_HIGH_PATH = "rangeHighPath";
    private static final String RANGE_LOW_PATH = "rangeLowPath";
    private static final String RANGE_MID_PATH = "rangeMidPath";

    // Stop loss modes (as integers)
    private static final int STOP_MODE_FIXED = 0;           // Fixed points from entry
    private static final int STOP_MODE_BEYOND_RANGE = 1;    // Beyond range + buffer

    // Target modes (as integers)
    private static final int TARGET_MIDPOINT = 0;           // Range midpoint only
    private static final int TARGET_OPPOSITE = 1;           // Opposite boundary only
    private static final int TARGET_BOTH = 2;               // Partial at mid, runner to opposite

    // ==================== Values ====================
    enum Values { RANGE_HIGH, RANGE_LOW, RANGE_MID, IN_RANGE_SESSION, IN_TRADE_SESSION, RANGE_COMPLETE }

    // ==================== Signals ====================
    enum Signals { LONG_FADE, SHORT_FADE }

    // ==================== State Variables ====================
    // Daily reset variables
    private double rangeHigh = Double.NaN;
    private double rangeLow = Double.NaN;
    private boolean rangeComplete = false;
    private int tradesToday = 0;
    private boolean longUsed = false;
    private boolean shortUsed = false;
    private int lastResetDay = -1;

    // Position tracking
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double target1Price = 0;
    private double target2Price = 0;
    private boolean isLong = false;
    private boolean partialTaken = false;

    // New York timezone for 6-10am ET
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Sessions Tab =====
        var tab = sd.addTab("Sessions");
        var grp = tab.addGroup("Range Window (6-10am ET)");
        grp.addRow(new IntegerDescriptor(RANGE_START, "Start Time (HHMM)", 600, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(RANGE_END, "End Time (HHMM)", 1000, 0, 2359, 1));

        grp = tab.addGroup("Early Trade Window");
        grp.addRow(new IntegerDescriptor(TRADE_START, "Start Time (HHMM)", 1000, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(TRADE_END, "End Time (HHMM)", 1030, 0, 2359, 1));

        // ===== Sweep Rules Tab =====
        tab = sd.addTab("Sweep Rules");
        grp = tab.addGroup("Sweep Detection");
        grp.addRow(new BooleanDescriptor(USE_LOOKBACK_SWEEP, "Use Lookback Sweep", false));
        grp.addRow(new IntegerDescriptor(SWEEP_LOOKBACK_BARS, "Lookback Bars", 12, 1, 50, 1));
        grp.addRow(new BooleanDescriptor(REQUIRE_CLOSE_BACK_INSIDE, "Require Close Back Inside", true));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 1, 1, 100, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new BooleanDescriptor(STOPLOSS_ENABLED, "Enable Stop Loss", true));
        grp.addRow(new IntegerDescriptor(STOPLOSS_MODE, "Stop Mode (0=Fixed, 1=Beyond Range)", STOP_MODE_BEYOND_RANGE, 0, 1, 1));
        grp.addRow(new DoubleDescriptor(STOPLOSS_POINTS, "Stop Points", 10.0, 0.25, 100.0, 0.25));

        // ===== Targets Tab =====
        tab = sd.addTab("Targets");
        grp = tab.addGroup("Profit Targets");
        grp.addRow(new IntegerDescriptor(TARGET_MODE, "Target Mode (0=Mid, 1=Opposite, 2=Both)", TARGET_MIDPOINT, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(PARTIAL_PCT_AT_MID, "Partial % at Midpoint", 50, 1, 99, 1));

        // ===== Limits Tab =====
        tab = sd.addTab("Limits");
        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_PER_DAY, "Max Trades Per Day", 1, 1, 10, 1));
        grp.addRow(new BooleanDescriptor(ONE_ATTEMPT_PER_SIDE, "One Attempt Per Side", true));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Range Lines");
        grp.addRow(new PathDescriptor(RANGE_HIGH_PATH, "Range High",
            defaults.getBlue(), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(RANGE_LOW_PATH, "Range Low",
            defaults.getRed(), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(RANGE_MID_PATH, "Range Mid",
            defaults.getGrey(), 1.0f, new float[] {5, 5}, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(CONTRACTS, STOPLOSS_POINTS, TARGET_MODE, MAX_TRADES_PER_DAY);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(RANGE_START, RANGE_END, TARGET_MODE);

        desc.exportValue(new ValueDescriptor(Values.RANGE_HIGH, "Range High", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_LOW, "Range Low", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_MID, "Range Mid", new String[]{}));

        desc.declarePath(Values.RANGE_HIGH, RANGE_HIGH_PATH);
        desc.declarePath(Values.RANGE_LOW, RANGE_LOW_PATH);
        desc.declarePath(Values.RANGE_MID, RANGE_MID_PATH);

        desc.declareSignal(Signals.LONG_FADE, "Long Fade Entry");
        desc.declareSignal(Signals.SHORT_FADE, "Short Fade Entry");

        desc.setRangeKeys(Values.RANGE_HIGH, Values.RANGE_LOW);
    }

    @Override
    public int getMinBars() {
        return getSettings().getInteger(SWEEP_LOOKBACK_BARS, 12) + 10;
    }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();

        // Get bar time in NY timezone
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);

        // Daily reset
        if (barDay != lastResetDay) {
            resetDailyState();
            lastResetDay = barDay;
        }

        // Get settings
        int rangeStart = getSettings().getInteger(RANGE_START, 600);
        int rangeEnd = getSettings().getInteger(RANGE_END, 1000);
        int tradeStart = getSettings().getInteger(TRADE_START, 1000);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1030);

        // Session flags
        boolean inRangeSession = barTimeInt >= rangeStart && barTimeInt < rangeEnd;
        boolean inTradeSession = barTimeInt >= tradeStart && barTimeInt < tradeEnd;

        series.setBoolean(index, Values.IN_RANGE_SESSION, inRangeSession);
        series.setBoolean(index, Values.IN_TRADE_SESSION, inTradeSession);

        // OHLC
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);

        // Build range during 6-10am ET
        if (inRangeSession) {
            if (Double.isNaN(rangeHigh) || high > rangeHigh) rangeHigh = high;
            if (Double.isNaN(rangeLow) || low < rangeLow) rangeLow = low;
        }

        // Check if range just ended
        if (index > 0) {
            Boolean wasInRange = series.getBoolean(index - 1, Values.IN_RANGE_SESSION);
            if (wasInRange != null && wasInRange && !inRangeSession) {
                if (!Double.isNaN(rangeHigh) && !Double.isNaN(rangeLow)) {
                    rangeComplete = true;
                }
            }
        }

        series.setBoolean(index, Values.RANGE_COMPLETE, rangeComplete);

        // Plot range lines after range is complete
        if (rangeComplete) {
            series.setDouble(index, Values.RANGE_HIGH, rangeHigh);
            series.setDouble(index, Values.RANGE_LOW, rangeLow);
            double rangeMid = (rangeHigh + rangeLow) / 2.0;
            series.setDouble(index, Values.RANGE_MID, rangeMid);
        }

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (!rangeComplete || !inTradeSession) return;

        // Get sweep settings
        boolean useLookback = getSettings().getBoolean(USE_LOOKBACK_SWEEP, false);
        int lookbackBars = getSettings().getInteger(SWEEP_LOOKBACK_BARS, 12);
        boolean requireCloseBack = getSettings().getBoolean(REQUIRE_CLOSE_BACK_INSIDE, true);
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_DAY, 1);
        boolean oneAttempt = getSettings().getBoolean(ONE_ATTEMPT_PER_SIDE, true);

        // Close back inside check
        boolean closeBackInside = close > rangeLow && close < rangeHigh;
        if (requireCloseBack && !closeBackInside) return;

        // Can we trade?
        boolean canTrade = tradesToday < maxTrades;
        if (!canTrade) return;

        // Sweep detection
        boolean longSweep;
        boolean shortSweep;

        if (useLookback) {
            double lowestRecent = getLowest(series, index, lookbackBars);
            double highestRecent = getHighest(series, index, lookbackBars);
            longSweep = lowestRecent < rangeLow;
            shortSweep = highestRecent > rangeHigh;
        } else {
            longSweep = low < rangeLow;
            shortSweep = high > rangeHigh;
        }

        // Generate signals
        if (longSweep && (!oneAttempt || !longUsed)) {
            series.setBoolean(index, Signals.LONG_FADE, true);
            ctx.signal(index, Signals.LONG_FADE,
                String.format("Long fade: Low=%.2f < Range Low=%.2f, Close=%.2f back inside", low, rangeLow, close),
                close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, low);
                addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "LONG"));
            }
        }

        if (shortSweep && (!oneAttempt || !shortUsed)) {
            series.setBoolean(index, Signals.SHORT_FADE, true);
            ctx.signal(index, Signals.SHORT_FADE,
                String.format("Short fade: High=%.2f > Range High=%.2f, Close=%.2f back inside", high, rangeHigh, close),
                close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, high);
                addFigure(new Marker(coord, Enums.Position.TOP, marker, "SHORT"));
            }
        }

        series.setComplete(index);
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("Early Window Sweep Strategy activated");
        partialTaken = false;
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position");
        }
        resetDailyState();
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        int qty = getSettings().getInteger(CONTRACTS, 1);
        double stopPts = getSettings().getDouble(STOPLOSS_POINTS, 10.0);
        int stopMode = getSettings().getInteger(STOPLOSS_MODE, STOP_MODE_BEYOND_RANGE);
        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);

        if (position != 0) {
            debug("Already in position, ignoring signal");
            return;
        }

        double rangeMid = (rangeHigh + rangeLow) / 2.0;

        if (signal == Signals.LONG_FADE) {
            // Enter long
            ctx.buy(qty);
            longUsed = true;
            tradesToday++;
            isLong = true;
            partialTaken = false;

            entryPrice = instr.getLastPrice();

            // Calculate stop
            if (stopEnabled) {
                if (stopMode == STOP_MODE_FIXED) {
                    stopPrice = instr.round(entryPrice - stopPts);
                } else {
                    stopPrice = instr.round(rangeLow - stopPts);
                }
            } else {
                stopPrice = 0;
            }

            target1Price = rangeMid;
            target2Price = rangeHigh;

            debug(String.format("LONG entry: qty=%d, entry=%.2f, stop=%.2f, T1=%.2f, T2=%.2f",
                qty, entryPrice, stopPrice, target1Price, target2Price));
        }
        else if (signal == Signals.SHORT_FADE) {
            // Enter short
            ctx.sell(qty);
            shortUsed = true;
            tradesToday++;
            isLong = false;
            partialTaken = false;

            entryPrice = instr.getLastPrice();

            // Calculate stop
            if (stopEnabled) {
                if (stopMode == STOP_MODE_FIXED) {
                    stopPrice = instr.round(entryPrice + stopPts);
                } else {
                    stopPrice = instr.round(rangeHigh + stopPts);
                }
            } else {
                stopPrice = 0;
            }

            target1Price = rangeMid;
            target2Price = rangeLow;

            debug(String.format("SHORT entry: qty=%d, entry=%.2f, stop=%.2f, T1=%.2f, T2=%.2f",
                qty, entryPrice, stopPrice, target1Price, target2Price));
        }
    }

    @Override
    public void onBarClose(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position == 0) return;

        var instr = ctx.getInstrument();
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        double close = series.getClose(index);
        double high = series.getHigh(index);
        double low = series.getLow(index);

        int targetMode = getSettings().getInteger(TARGET_MODE, TARGET_MIDPOINT);
        int partialPct = getSettings().getInteger(PARTIAL_PCT_AT_MID, 50);
        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);

        if (isLong && position > 0) {
            // Check stop
            if (stopEnabled && stopPrice > 0 && low <= stopPrice) {
                ctx.closeAtMarket();
                debug("LONG stopped out at " + low);
                return;
            }

            if (targetMode == TARGET_MIDPOINT) {
                // Exit all at midpoint
                if (high >= target1Price) {
                    ctx.closeAtMarket();
                    debug("LONG target (midpoint) hit at " + high);
                }
            } else if (targetMode == TARGET_OPPOSITE) {
                // Exit all at opposite boundary
                if (high >= target2Price) {
                    ctx.closeAtMarket();
                    debug("LONG target (opposite) hit at " + high);
                }
            } else if (targetMode == TARGET_BOTH) {
                // Partial at midpoint, remainder at opposite
                if (!partialTaken && high >= target1Price) {
                    int partialQty = (int) Math.ceil(position * partialPct / 100.0);
                    if (partialQty > 0 && partialQty < position) {
                        ctx.sell(partialQty);
                        partialTaken = true;
                        debug("LONG partial exit: " + partialQty + " at midpoint");
                    }
                }
                if (high >= target2Price) {
                    ctx.closeAtMarket();
                    debug("LONG target 2 (opposite) hit at " + high);
                }
            }
        }
        else if (!isLong && position < 0) {
            // Check stop
            if (stopEnabled && stopPrice > 0 && high >= stopPrice) {
                ctx.closeAtMarket();
                debug("SHORT stopped out at " + high);
                return;
            }

            if (targetMode == TARGET_MIDPOINT) {
                // Exit all at midpoint
                if (low <= target1Price) {
                    ctx.closeAtMarket();
                    debug("SHORT target (midpoint) hit at " + low);
                }
            } else if (targetMode == TARGET_OPPOSITE) {
                // Exit all at opposite boundary
                if (low <= target2Price) {
                    ctx.closeAtMarket();
                    debug("SHORT target (opposite) hit at " + low);
                }
            } else if (targetMode == TARGET_BOTH) {
                // Partial at midpoint, remainder at opposite
                if (!partialTaken && low <= target1Price) {
                    int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
                    if (partialQty > 0 && partialQty < Math.abs(position)) {
                        ctx.buy(partialQty);
                        partialTaken = true;
                        debug("SHORT partial exit: " + partialQty + " at midpoint");
                    }
                }
                if (low <= target2Price) {
                    ctx.closeAtMarket();
                    debug("SHORT target 2 (opposite) hit at " + low);
                }
            }
        }
    }

    // ==================== Helper Methods ====================

    private void resetDailyState() {
        rangeHigh = Double.NaN;
        rangeLow = Double.NaN;
        rangeComplete = false;
        tradesToday = 0;
        longUsed = false;
        shortUsed = false;
        partialTaken = false;
    }

    private int getTimeInt(long time, TimeZone tz) {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);
    }

    private int getDayOfYear(long time, TimeZone tz) {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.DAY_OF_YEAR) + cal.get(Calendar.YEAR) * 1000;
    }

    private double getLowest(DataSeries series, int index, int period) {
        double lowest = Double.MAX_VALUE;
        for (int i = Math.max(0, index - period + 1); i <= index; i++) {
            double low = series.getLow(i);
            if (low < lowest) lowest = low;
        }
        return lowest;
    }

    private double getHighest(DataSeries series, int index, int period) {
        double highest = Double.MIN_VALUE;
        for (int i = Math.max(0, index - period + 1); i <= index; i++) {
            double high = series.getHigh(i);
            if (high > highest) highest = high;
        }
        return highest;
    }

    @Override
    public void clearState() {
        super.clearState();
        resetDailyState();
        lastResetDay = -1;
    }
}
