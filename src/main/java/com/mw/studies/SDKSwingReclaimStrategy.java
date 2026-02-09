package com.mw.studies;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * SDK Swing Reclaim Strategy v2.0
 *
 * Uses MotiveWave's built-in SwingPoints detection (series.calcSwingPoints)
 * to identify swing highs/lows, then trades the "break then reclaim" pattern.
 *
 * Swing HIGH (Short setup): ACTIVE -> close above (BROKEN/sweep) -> close below (reclaim) -> SHORT
 * Swing LOW (Long setup):   ACTIVE -> close below (BROKEN/sweep) -> close above (reclaim) -> LONG
 *
 * @version 2.0.0
 * @author MW Study Builder
 * @generated 2026-02-08
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "SDK_SWING_RECLAIM",
    rb = "com.mw.studies.nls.strings",
    name = "SDK_SWING_RECLAIM",
    label = "LBL_SDK_SWING_RECLAIM",
    desc = "DESC_SDK_SWING_RECLAIM",
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
public class SDKSwingReclaimStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String ENABLE_LONG = "enableLong";
    private static final String ENABLE_SHORT = "enableShort";
    private static final String STRENGTH = "strength";
    private static final String RETENTION_DAYS = "retentionDays";
    private static final String RECLAIM_WINDOW = "reclaimWindow";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String SESSION_ENABLED = "sessionEnabled";
    private static final String SESSION_START = "sessionStart";
    private static final String SESSION_END = "sessionEnd";
    private static final String CONTRACTS = "contracts";
    private static final String STOP_BUFFER_TICKS = "stopBufferTicks";
    private static final String STOP_MIN_PTS = "stopMinPts";
    private static final String STOP_MAX_PTS = "stopMaxPts";
    private static final String TP1_POINTS = "tp1Points";
    private static final String TP1_PCT = "tp1Pct";
    private static final String TRAIL_POINTS = "trailPoints";
    private static final String EOD_ENABLED = "eodEnabled";
    private static final String EOD_TIME = "eodTime";
    private static final String SHOW_LEVELS = "showLevels";
    private static final String SWING_HIGH_PATH = "swingHighPath";
    private static final String SWING_LOW_PATH = "swingLowPath";

    // ==================== Level States ====================
    private static final int STATE_ACTIVE = 0;
    private static final int STATE_BROKEN = 1;

    // ==================== Values & Signals ====================
    enum Values { PLACEHOLDER }
    enum Signals { RECLAIM_LONG, RECLAIM_SHORT }

    // ==================== Inner Classes ====================
    private static class SwingLevel {
        double price;
        boolean isHigh;
        int state;
        double sweepExtreme;
        long detectedTime;
        int brokeIndex;
        boolean traded;
        boolean canceled;

        SwingLevel(double price, boolean isHigh, long detectedTime) {
            this.price = price;
            this.isHigh = isHigh;
            this.state = STATE_ACTIVE;
            this.sweepExtreme = Double.NaN;
            this.detectedTime = detectedTime;
            this.brokeIndex = -1;
            this.traded = false;
            this.canceled = false;
        }
    }

    // ==================== Constants ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== State ====================
    private List<SwingLevel> swingLevels = new ArrayList<>();
    private List<Marker> entryMarkers = new ArrayList<>();

    // Trade state (managed by onSignal/onBarClose, NOT cleared by calculateValues)
    private boolean isLongTrade = false;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double tp1Price = 0;
    private boolean tp1Filled = false;
    private boolean beActivated = false;
    private double bestPriceInTrade = Double.NaN;
    private double trailStopPrice = Double.NaN;
    private boolean trailingActive = false;

    // EOD tracking
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        var tab = sd.addTab("Setup");
        var grp = tab.addGroup("Direction");
        grp.addRow(new BooleanDescriptor(ENABLE_LONG, "Enable Long Setups", true));
        grp.addRow(new BooleanDescriptor(ENABLE_SHORT, "Enable Short Setups", true));

        grp = tab.addGroup("Swing Detection (SDK)");
        grp.addRow(new IntegerDescriptor(STRENGTH, "Swing Strength", 45, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(RETENTION_DAYS, "Level Retention (days)", 30, 1, 90, 1));
        grp.addRow(new IntegerDescriptor(RECLAIM_WINDOW, "Reclaim Window (bars after break)", 20, 1, 100, 1));

        tab = sd.addTab("Entry");
        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades Per Day", 3, 1, 10, 1));

        grp = tab.addGroup("Session Window (ET)");
        grp.addRow(new BooleanDescriptor(SESSION_ENABLED, "Restrict to Session Window", false));
        grp.addRow(new IntegerDescriptor(SESSION_START, "Session Start (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(SESSION_END, "Session End (HHMM)", 1600, 0, 2359, 1));

        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 2, 1, 100, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new IntegerDescriptor(STOP_BUFFER_TICKS, "Stop Buffer (ticks beyond sweep extreme)", 4, 0, 50, 1));
        grp.addRow(new DoubleDescriptor(STOP_MIN_PTS, "Min Stop Distance (pts)", 2.0, 0.25, 50.0, 0.25));
        grp.addRow(new DoubleDescriptor(STOP_MAX_PTS, "Max Stop Distance (pts)", 40.0, 1.0, 200.0, 0.5));

        tab = sd.addTab("Targets");
        grp = tab.addGroup("TP1 (Partial)");
        grp.addRow(new DoubleDescriptor(TP1_POINTS, "TP1 Distance (points)", 20.0, 0.25, 200.0, 0.25));
        grp.addRow(new IntegerDescriptor(TP1_PCT, "TP1 % of Contracts", 50, 1, 99, 1));

        grp = tab.addGroup("Runner Trail");
        grp.addRow(new DoubleDescriptor(TRAIL_POINTS, "Trail Distance (points)", 15.0, 0.25, 100.0, 0.25));

        tab = sd.addTab("EOD");
        grp = tab.addGroup("End of Day");
        grp.addRow(new BooleanDescriptor(EOD_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_TIME, "EOD Time (HHMM)", 1640, 0, 2359, 1));

        tab = sd.addTab("Display");
        grp = tab.addGroup("Swing Levels");
        grp.addRow(new BooleanDescriptor(SHOW_LEVELS, "Show Swing Levels", true));
        grp.addRow(new PathDescriptor(SWING_HIGH_PATH, "Swing High Line",
            defaults.getRedLine(), 1.5f, new float[]{6, 3}, true, false, false));
        grp.addRow(new PathDescriptor(SWING_LOW_PATH, "Swing Low Line",
            defaults.getGreenLine(), 1.5f, new float[]{6, 3}, true, false, false));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        sd.addQuickSettings(CONTRACTS, STRENGTH, TP1_POINTS, TRAIL_POINTS, MAX_TRADES_DAY);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, STRENGTH);
        desc.declareSignal(Signals.RECLAIM_LONG, "Reclaim Long");
        desc.declareSignal(Signals.RECLAIM_SHORT, "Reclaim Short");
    }

    @Override
    public int getMinBars() { return 100; }

    // ==================== CALCULATE VALUES ====================
    // Modeled on reference SwingPoints study: clearFigures, calcSwingPoints, draw.
    // State machine runs inline for all bars. Signals fire only on new complete bars.
    @Override
    protected void calculateValues(DataContext ctx)
    {
        clearFigures();
        var series = ctx.getDataSeries();
        var settings = getSettings();
        int size = series.size();
        if (size < 2) return;

        int strength = settings.getInteger(STRENGTH, 45);
        var swingPoints = series.calcSwingPoints(strength);
        if (swingPoints == null || swingPoints.isEmpty()) return;

        // Build level list from scratch
        swingLevels.clear();
        entryMarkers.clear();
        for (var sp : swingPoints) {
            swingLevels.add(new SwingLevel(sp.getValue(), sp.isTop(), sp.getCoordinate().getTime()));
        }

        // Read settings once
        boolean enableLong = settings.getBoolean(ENABLE_LONG, true);
        boolean enableShort = settings.getBoolean(ENABLE_SHORT, true);
        int reclaimWindow = settings.getInteger(RECLAIM_WINDOW, 20);
        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 3);
        boolean eodEnabled = settings.getBoolean(EOD_ENABLED, true);
        int eodTime = settings.getInteger(EOD_TIME, 1640);
        boolean sessionEnabled = settings.getBoolean(SESSION_ENABLED, false);
        int sessionStart = settings.getInteger(SESSION_START, 930);
        int sessionEnd = settings.getInteger(SESSION_END, 1600);

        int localTradesToday = 0;
        int localLastDay = -1;

        // Process every bar: state machine always runs, signals only on new complete bars
        for (int i = 0; i < size; i++) {
            long barTime = series.getStartTime(i);
            double close = series.getClose(i);
            double high = series.getHigh(i);
            double low = series.getLow(i);
            int barDay = getDayOfYear(barTime);
            int barTimeInt = getTimeInt(barTime);
            boolean canSignal = !series.isComplete(i) && series.isBarComplete(i);

            if (barDay != localLastDay) {
                localTradesToday = 0;
                localLastDay = barDay;
            }

            boolean pastEOD = eodEnabled && barTimeInt >= eodTime;
            boolean inSession = !sessionEnabled || (barTimeInt >= sessionStart && barTimeInt < sessionEnd);

            for (SwingLevel lv : swingLevels) {
                if (lv.traded || lv.canceled) continue;
                if (barTime <= lv.detectedTime) continue;

                // Expire reclaim window
                if (lv.state == STATE_BROKEN && lv.brokeIndex >= 0 && (i - lv.brokeIndex) > reclaimWindow) {
                    lv.canceled = true;
                    continue;
                }

                if (lv.isHigh) {
                    if (lv.state == STATE_ACTIVE && close > lv.price) {
                        lv.state = STATE_BROKEN;
                        lv.brokeIndex = i;
                        lv.sweepExtreme = high;
                    } else if (lv.state == STATE_BROKEN) {
                        if (high > lv.sweepExtreme) lv.sweepExtreme = high;
                        if (close < lv.price) {
                            // Reclaim detected — always mark traded
                            lv.traded = true;
                            boolean canEnter = enableShort && !pastEOD && inSession && localTradesToday < maxTrades;
                            if (canEnter) {
                                localTradesToday++;
                                var marker = settings.getMarker(Inputs.DOWN_MARKER);
                                if (marker != null && marker.isEnabled()) {
                                    entryMarkers.add(new Marker(new Coordinate(barTime, high),
                                        Enums.Position.TOP, marker, "RCL S " + fmt(lv.price)));
                                }
                                if (canSignal) {
                                    ctx.signal(i, Signals.RECLAIM_SHORT,
                                        "Sweep High " + fmt(lv.price) + " -> Short", close);
                                }
                            }
                        }
                    }
                } else {
                    if (lv.state == STATE_ACTIVE && close < lv.price) {
                        lv.state = STATE_BROKEN;
                        lv.brokeIndex = i;
                        lv.sweepExtreme = low;
                    } else if (lv.state == STATE_BROKEN) {
                        if (low < lv.sweepExtreme) lv.sweepExtreme = low;
                        if (close > lv.price) {
                            // Reclaim detected — always mark traded
                            lv.traded = true;
                            boolean canEnter = enableLong && !pastEOD && inSession && localTradesToday < maxTrades;
                            if (canEnter) {
                                localTradesToday++;
                                var marker = settings.getMarker(Inputs.UP_MARKER);
                                if (marker != null && marker.isEnabled()) {
                                    entryMarkers.add(new Marker(new Coordinate(barTime, low),
                                        Enums.Position.BOTTOM, marker, "RCL L " + fmt(lv.price)));
                                }
                                if (canSignal) {
                                    ctx.signal(i, Signals.RECLAIM_LONG,
                                        "Sweep Low " + fmt(lv.price) + " -> Long", close);
                                }
                            }
                        }
                    }
                }
            }

            if (canSignal) series.setComplete(i);
        }

        // Draw horizontal lines for ACTIVE levels only
        long endTime = series.getStartTime(size - 1);
        int drawn = 0;
        if (settings.getBoolean(SHOW_LEVELS, true)) {
            for (SwingLevel lv : swingLevels) {
                if (lv.traded || lv.canceled || lv.state != STATE_ACTIVE) continue;
                var path = lv.isHigh ? settings.getPath(SWING_HIGH_PATH) : settings.getPath(SWING_LOW_PATH);
                if (path != null && path.isEnabled()) {
                    addFigure(new Line(
                        new Coordinate(lv.detectedTime, lv.price),
                        new Coordinate(endTime, lv.price), path));
                    drawn++;
                }
            }
        }
        for (Marker m : entryMarkers) addFigure(m);

        // Debug summary
        int active = 0, broken = 0, traded = 0, canceled = 0;
        for (SwingLevel lv : swingLevels) {
            if (lv.canceled) canceled++;
            else if (lv.traded) traded++;
            else if (lv.state == STATE_BROKEN) broken++;
            else active++;
        }
        debug("calcValues: " + swingLevels.size() + " pts, " + drawn + " lines drawn | "
            + active + " active, " + broken + " broken, " + traded + " traded, " + canceled + " canceled");
    }

    // ==================== CALCULATE (required by validator, logic is in calculateValues) ====================
    @Override
    protected void calculate(int index, DataContext ctx)
    {
        // State machine and signals are handled inline in calculateValues.
        // This method exists to satisfy the build validator.
    }

    // ==================== BAR CLOSE (Study-level — refresh display) ====================
    // Same pattern as the reference SwingPoints study
    @Override
    public void onBarClose(DataContext ctx)
    {
        calculateValues(ctx);
    }

    // ==================== STRATEGY LIFECYCLE ====================

    @Override
    public void onActivate(OrderContext ctx)
    {
        debug("SDK Swing Reclaim Strategy activated");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position");
        }
        resetTradeState();
    }

    // ==================== SIGNAL HANDLER ====================

    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        if (signal != Signals.RECLAIM_LONG && signal != Signals.RECLAIM_SHORT) return;

        int position = ctx.getPosition();
        if (position != 0) {
            debug("Already in position, ignoring signal");
            return;
        }

        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();
        var settings = getSettings();
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime);

        if (settings.getBoolean(EOD_ENABLED, true) &&
            barTimeInt >= settings.getInteger(EOD_TIME, 1640)) {
            debug("Past EOD, blocking entry");
            return;
        }

        int qty = settings.getInteger(CONTRACTS, 2);
        int stopBufferTicks = settings.getInteger(STOP_BUFFER_TICKS, 4);
        double stopBuffer = stopBufferTicks * tickSize;
        double stopMinPts = settings.getDouble(STOP_MIN_PTS, 2.0);
        double stopMaxPts = settings.getDouble(STOP_MAX_PTS, 40.0);
        double tp1Pts = settings.getDouble(TP1_POINTS, 20.0);

        isLongTrade = (signal == Signals.RECLAIM_LONG);

        // Find trigger level (most recently traded level matching direction)
        SwingLevel triggerLevel = null;
        for (SwingLevel lv : swingLevels) {
            if (lv.traded && lv.isHigh != isLongTrade) {
                triggerLevel = lv;
            }
        }

        if (isLongTrade) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();
            if (triggerLevel != null && !Double.isNaN(triggerLevel.sweepExtreme)) {
                stopPrice = instr.round(triggerLevel.sweepExtreme - stopBuffer);
            } else {
                stopPrice = instr.round(entryPrice - stopMaxPts);
            }
            tp1Price = instr.round(entryPrice + tp1Pts);
            bestPriceInTrade = entryPrice;
        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();
            if (triggerLevel != null && !Double.isNaN(triggerLevel.sweepExtreme)) {
                stopPrice = instr.round(triggerLevel.sweepExtreme + stopBuffer);
            } else {
                stopPrice = instr.round(entryPrice + stopMaxPts);
            }
            tp1Price = instr.round(entryPrice - tp1Pts);
            bestPriceInTrade = entryPrice;
        }

        // Clamp stop distance
        double dist = Math.abs(entryPrice - stopPrice);
        if (dist < stopMinPts) {
            stopPrice = isLongTrade
                ? instr.round(entryPrice - stopMinPts)
                : instr.round(entryPrice + stopMinPts);
        }
        if (dist > stopMaxPts) {
            stopPrice = isLongTrade
                ? instr.round(entryPrice - stopMaxPts)
                : instr.round(entryPrice + stopMaxPts);
        }

        tp1Filled = false;
        beActivated = false;
        trailingActive = false;
        trailStopPrice = Double.NaN;

        debug(String.format("=== %s ENTRY === qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f",
            isLongTrade ? "LONG" : "SHORT", qty, entryPrice, stopPrice, tp1Price));
    }

    // ==================== BAR CLOSE (Strategy-level — trade management) ====================

    @Override
    public void onBarClose(OrderContext ctx)
    {
        // Refresh figures (same as study-level onBarClose, safe if called twice)
        calculateValues(ctx.getDataContext());

        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime);
        var instr = ctx.getInstrument();
        var settings = getSettings();
        int barDay = getDayOfYear(barTime);

        // EOD tracking reset
        if (barDay != lastResetDay) {
            eodProcessed = false;
            lastResetDay = barDay;
        }

        // EOD Flatten
        if (settings.getBoolean(EOD_ENABLED, true) &&
            barTimeInt >= settings.getInteger(EOD_TIME, 1640) && !eodProcessed) {
            int position = ctx.getPosition();
            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD forced flat at " + barTimeInt);
                resetTradeState();
            }
            eodProcessed = true;
            return;
        }

        // Position management
        int position = ctx.getPosition();
        if (position == 0) {
            if (entryPrice > 0) resetTradeState();
            return;
        }

        double high = series.getHigh(index);
        double low = series.getLow(index);
        boolean isLong = position > 0;

        // Track best price
        if (isLong) {
            if (Double.isNaN(bestPriceInTrade) || high > bestPriceInTrade) bestPriceInTrade = high;
        } else {
            if (Double.isNaN(bestPriceInTrade) || low < bestPriceInTrade) bestPriceInTrade = low;
        }

        // Effective stop
        double effectiveStop = stopPrice;
        if (!Double.isNaN(trailStopPrice) && trailingActive) {
            if (isLong) effectiveStop = Math.max(effectiveStop, trailStopPrice);
            else effectiveStop = Math.min(effectiveStop, trailStopPrice);
        }

        // Stop loss check
        if (isLong && low <= effectiveStop) {
            ctx.closeAtMarket();
            debug("LONG stopped at " + fmt(effectiveStop));
            resetTradeState();
            return;
        }
        if (!isLong && high >= effectiveStop) {
            ctx.closeAtMarket();
            debug("SHORT stopped at " + fmt(effectiveStop));
            resetTradeState();
            return;
        }

        // TP1 Partial
        int tp1Pct = settings.getInteger(TP1_PCT, 50);
        if (!tp1Filled) {
            boolean tp1Hit = (isLong && high >= tp1Price) || (!isLong && low <= tp1Price);
            if (tp1Hit) {
                int absPos = Math.abs(position);
                int partialQty = (int) Math.ceil(absPos * tp1Pct / 100.0);
                if (partialQty > 0 && partialQty < absPos) {
                    if (isLong) ctx.sell(partialQty);
                    else ctx.buy(partialQty);
                    tp1Filled = true;
                    debug("TP1: " + partialQty + " contracts at " + fmt(tp1Price));
                    if (!beActivated) {
                        stopPrice = instr.round(entryPrice);
                        beActivated = true;
                        debug("Stop to BE: " + fmt(stopPrice));
                    }
                } else {
                    ctx.closeAtMarket();
                    debug("Full exit at TP1");
                    resetTradeState();
                    return;
                }
            }
        }

        // Runner Trailing Stop
        if (tp1Filled && !trailingActive) {
            trailingActive = true;
            double trailDist = settings.getDouble(TRAIL_POINTS, 15.0);
            trailStopPrice = isLong
                ? instr.round(bestPriceInTrade - trailDist)
                : instr.round(bestPriceInTrade + trailDist);
        }
        if (trailingActive) {
            double trailDist = settings.getDouble(TRAIL_POINTS, 15.0);
            if (isLong) {
                double newTrail = instr.round(bestPriceInTrade - trailDist);
                if (Double.isNaN(trailStopPrice) || newTrail > trailStopPrice) trailStopPrice = newTrail;
            } else {
                double newTrail = instr.round(bestPriceInTrade + trailDist);
                if (Double.isNaN(trailStopPrice) || newTrail < trailStopPrice) trailStopPrice = newTrail;
            }
        }
    }

    // ==================== STATE RESET ====================

    private void resetTradeState()
    {
        entryPrice = 0;
        stopPrice = 0;
        tp1Price = 0;
        tp1Filled = false;
        beActivated = false;
        bestPriceInTrade = Double.NaN;
        trailStopPrice = Double.NaN;
        trailingActive = false;
    }

    // ==================== UTILITY ====================

    private int getTimeInt(long time)
    {
        Calendar cal = Calendar.getInstance(NY_TZ);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);
    }

    private int getDayOfYear(long time)
    {
        Calendar cal = Calendar.getInstance(NY_TZ);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.DAY_OF_YEAR) + cal.get(Calendar.YEAR) * 1000;
    }

    private String fmt(double val)
    {
        return String.format("%.2f", val);
    }

    // ==================== CLEAR STATE ====================
    @Override
    public void clearState()
    {
        super.clearState();
        swingLevels.clear();
        entryMarkers.clear();
        resetTradeState();
        lastResetDay = -1;
        eodProcessed = false;
    }
}
