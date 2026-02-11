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
 * JadeCap Daily Sweep Strategy v1.1
 *
 * Multi-timeframe SFP strategy: swing detection + SFP on synthetic hourly bars
 * (12 x 5-min grouped), FVG entry on native 5-min bars.
 *
 * Based on JadeCap's 3-step "Daily Sweep" / Swing Failure Pattern model:
 *   1. Determine daily bias using MA on hourly bars
 *   2. Detect SFP at hourly swing levels (break + close back)
 *   3. Enter on 5-min FVG retrace (or immediate on SFP close) with fixed R:R
 *
 * Phase 1 (Hourly): Build synthetic bars → compute MA → detect swings → SFP state machine
 * Phase 2 (5-min):  Scan for FVG after SFP → enter on retrace into gap zone
 *
 * @version 1.1.0
 * @author MW Study Builder
 * @generated 2026-02-08
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "JADECAP_DAILY_SWEEP",
    rb = "com.mw.studies.nls.strings",
    name = "JADECAP_DAILY_SWEEP",
    label = "LBL_JADECAP_DAILY_SWEEP",
    desc = "DESC_JADECAP_DAILY_SWEEP",
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
public class JadeCapDailySweepStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String BIAS_MODE = "biasMode";
    private static final String MA_PERIOD = "maPeriod";
    private static final String MA_INPUT = "maInput";
    private static final String MA_METHOD = "maMethod";
    private static final String BAR_GROUP_SIZE = "barGroupSize";
    private static final String STRENGTH = "strength";
    private static final String SFP_WINDOW = "sfpWindow";
    private static final String ENTRY_MODEL = "entryModel";
    private static final String ENTRY_WINDOW = "entryWindow";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String SESSION_START = "sessionStart";
    private static final String SESSION_END = "sessionEnd";
    private static final String CONTRACTS = "contracts";
    private static final String STOP_BUFFER_TICKS = "stopBufferTicks";
    private static final String STOP_MIN_PTS = "stopMinPts";
    private static final String STOP_MAX_PTS = "stopMaxPts";
    private static final String BE_ENABLED = "beEnabled";
    private static final String BE_TRIGGER_PTS = "beTriggerPts";
    private static final String RR_RATIO = "rrRatio";
    private static final String EOD_ENABLED = "eodEnabled";
    private static final String EOD_TIME = "eodTime";
    private static final String SHOW_LEVELS = "showLevels";
    private static final String SWING_HIGH_PATH = "swingHighPath";
    private static final String SWING_LOW_PATH = "swingLowPath";
    private static final String MA_PATH = "maPath";

    // ==================== Constants ====================
    private static final int BIAS_AUTO = 0;
    private static final int BIAS_LONG_ONLY = 1;
    private static final int BIAS_SHORT_ONLY = 2;
    private static final int BIAS_BOTH = 3;

    private static final int ENTRY_FVG = 0;
    private static final int ENTRY_IMMEDIATE = 1;

    private static final int STATE_ACTIVE = 0;
    private static final int STATE_BROKEN = 1;
    private static final int STATE_SFP = 2;          // SFP confirmed, hunting for FVG on 5-min
    private static final int STATE_ENTRY_READY = 3;   // Immediate entry pending at specific chart bar

    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Values & Signals ====================
    enum Values { MA }
    enum Signals { SFP_LONG, SFP_SHORT }

    // ==================== Inner Classes ====================

    /** Synthetic hourly bar aggregated from chart-level bars */
    private static class HourlyBar {
        double open, high, low, close;
        long time;       // start time of first chart bar in group
        int startIdx;    // first chart bar index
        int endIdx;      // last chart bar index
    }

    /** Tracked swing level with SFP + FVG state */
    private static class SwingLevel {
        double price;
        boolean isHigh;
        int state;
        double sweepExtreme;
        long detectedTime;        // chart time for drawing
        int detectedGroupIndex;   // hourly group where swing was found
        int brokeGroupIndex;      // hourly group where break happened
        int sfpChartIndex;        // chart bar where SFP confirmed (FVG mode)
        int entryChartIndex;      // chart bar for immediate entry
        boolean traded;
        boolean canceled;
        // FVG tracking (5-min level)
        double fvgTop;
        double fvgBottom;
        boolean fvgFound;

        SwingLevel(double price, boolean isHigh, long detectedTime, int groupIndex) {
            this.price = price;
            this.isHigh = isHigh;
            this.state = STATE_ACTIVE;
            this.sweepExtreme = Double.NaN;
            this.detectedTime = detectedTime;
            this.detectedGroupIndex = groupIndex;
            this.brokeGroupIndex = -1;
            this.sfpChartIndex = -1;
            this.entryChartIndex = -1;
            this.traded = false;
            this.canceled = false;
            this.fvgTop = Double.NaN;
            this.fvgBottom = Double.NaN;
            this.fvgFound = false;
        }
    }

    // ==================== State ====================
    private List<SwingLevel> swingLevels = new ArrayList<>();
    private List<Marker> entryMarkers = new ArrayList<>();

    private boolean isLongTrade = false;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double targetPrice = 0;
    private boolean beActivated = false;
    private double bestPriceInTrade = Double.NaN;

    private int tradesToday = 0;
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Tab: Bias =====
        var tab = sd.addTab("Bias");
        var grp = tab.addGroup("Daily Bias");
        grp.addRow(new IntegerDescriptor(BIAS_MODE, "Bias Mode (0=Auto, 1=Long, 2=Short, 3=Both)", BIAS_AUTO, 0, 3, 1));

        grp = tab.addGroup("Bias MA (Auto mode, computed on hourly bars)");
        grp.addRow(new InputDescriptor(MA_INPUT, "MA Input", Enums.BarInput.CLOSE));
        grp.addRow(new IntegerDescriptor(MA_PERIOD, "MA Period (hourly bars)", 50, 1, 500, 1));
        grp.addRow(new MAMethodDescriptor(MA_METHOD, "MA Method", Enums.MAMethod.EMA));

        // ===== Tab: Setup =====
        tab = sd.addTab("Setup");
        grp = tab.addGroup("Hourly Bar Aggregation");
        grp.addRow(new IntegerDescriptor(BAR_GROUP_SIZE, "Chart Bars Per Hourly Candle", 12, 2, 60, 1));

        grp = tab.addGroup("Swing Detection (on hourly bars)");
        grp.addRow(new IntegerDescriptor(STRENGTH, "Swing Strength (hourly bars each side)", 3, 1, 50, 1));
        grp.addRow(new IntegerDescriptor(SFP_WINDOW, "SFP Window (hourly bars after break)", 5, 1, 50, 1));

        // ===== Tab: Entry =====
        tab = sd.addTab("Entry");
        grp = tab.addGroup("Entry Model");
        grp.addRow(new IntegerDescriptor(ENTRY_MODEL, "Entry Model (0=FVG Retrace, 1=Immediate)", ENTRY_FVG, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_WINDOW, "FVG Entry Window (chart bars after SFP)", 20, 5, 200, 1));

        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades Per Day", 2, 1, 5, 1));

        grp = tab.addGroup("Session Window (ET)");
        grp.addRow(new IntegerDescriptor(SESSION_START, "Session Start (HHMM)", 700, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(SESSION_END, "Session End (HHMM)", 1130, 0, 2359, 1));

        // ===== Tab: Risk =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 2, 1, 100, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new IntegerDescriptor(STOP_BUFFER_TICKS, "Stop Buffer (ticks beyond sweep extreme)", 4, 0, 50, 1));
        grp.addRow(new DoubleDescriptor(STOP_MIN_PTS, "Min Stop Distance (pts)", 2.0, 0.25, 50.0, 0.25));
        grp.addRow(new DoubleDescriptor(STOP_MAX_PTS, "Max Stop Distance (pts)", 40.0, 1.0, 200.0, 0.5));

        grp = tab.addGroup("Breakeven");
        grp.addRow(new BooleanDescriptor(BE_ENABLED, "Move Stop to Breakeven", true));
        grp.addRow(new DoubleDescriptor(BE_TRIGGER_PTS, "BE Trigger (points in profit)", 10.0, 0.25, 100.0, 0.25));

        // ===== Tab: Targets =====
        tab = sd.addTab("Targets");
        grp = tab.addGroup("Fixed R:R");
        grp.addRow(new DoubleDescriptor(RR_RATIO, "Risk:Reward Ratio", 2.0, 1.0, 5.0, 0.25));

        // ===== Tab: EOD =====
        tab = sd.addTab("EOD");
        grp = tab.addGroup("End of Day");
        grp.addRow(new BooleanDescriptor(EOD_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_TIME, "EOD Time (HHMM)", 1600, 0, 2359, 1));

        // ===== Tab: Display =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Bias MA");
        grp.addRow(new PathDescriptor(MA_PATH, "MA Line",
            defaults.getBlueLine(), 1.0f, null, true, true, false));

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

        sd.addQuickSettings(CONTRACTS, BAR_GROUP_SIZE, STRENGTH, RR_RATIO, BIAS_MODE, ENTRY_MODEL);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, STRENGTH, RR_RATIO);
        desc.exportValue(new ValueDescriptor(Values.MA, "Bias MA (Hourly)", new String[] { MA_INPUT, MA_PERIOD }));
        desc.declarePath(Values.MA, MA_PATH);
        desc.declareSignal(Signals.SFP_LONG, "SFP Long");
        desc.declareSignal(Signals.SFP_SHORT, "SFP Short");
    }

    @Override
    public int getMinBars() { return 200; }

    @Override
    protected void calculate(int index, DataContext ctx) { }

    // ==================== CALCULATE VALUES ====================
    @Override
    protected void calculateValues(DataContext ctx)
    {
        clearFigures();
        var series = ctx.getDataSeries();
        var settings = getSettings();
        int size = series.size();
        if (size < 2) return;

        // Read all settings
        int groupSize = settings.getInteger(BAR_GROUP_SIZE, 12);
        int maPeriod = settings.getInteger(MA_PERIOD, 50);
        Enums.MAMethod maMethod = settings.getMAMethod(MA_METHOD, Enums.MAMethod.EMA);
        int strength = settings.getInteger(STRENGTH, 3);
        int sfpWindow = settings.getInteger(SFP_WINDOW, 5);
        int entryModel = settings.getInteger(ENTRY_MODEL, ENTRY_FVG);
        int entryWindow = settings.getInteger(ENTRY_WINDOW, 20);
        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 2);
        boolean eodEnabled = settings.getBoolean(EOD_ENABLED, true);
        int eodTime = settings.getInteger(EOD_TIME, 1600);
        int sessionStart = settings.getInteger(SESSION_START, 700);
        int sessionEnd = settings.getInteger(SESSION_END, 1130);
        int biasMode = settings.getInteger(BIAS_MODE, BIAS_AUTO);

        // ===== PHASE 1: Build synthetic hourly bars =====
        int numGroups = (size + groupSize - 1) / groupSize;
        List<HourlyBar> hourlyBars = new ArrayList<>(numGroups);
        for (int g = 0; g < numGroups; g++) {
            int start = g * groupSize;
            int end = Math.min(start + groupSize - 1, size - 1);
            HourlyBar hb = new HourlyBar();
            hb.open = series.getOpen(start);
            hb.close = series.getClose(end);
            hb.time = series.getStartTime(start);
            hb.startIdx = start;
            hb.endIdx = end;
            hb.high = Double.NEGATIVE_INFINITY;
            hb.low = Double.POSITIVE_INFINITY;
            for (int j = start; j <= end; j++) {
                double h = series.getHigh(j);
                double l = series.getLow(j);
                if (h > hb.high) hb.high = h;
                if (l < hb.low) hb.low = l;
            }
            hourlyBars.add(hb);
        }
        if (hourlyBars.isEmpty()) return;

        // ===== PHASE 2: Compute MA on hourly bars for bias =====
        double[] hourlyMA = new double[numGroups];
        double emaK = 2.0 / (maPeriod + 1);
        for (int g = 0; g < numGroups; g++) {
            if (g < maPeriod - 1) {
                hourlyMA[g] = Double.NaN;
            } else if (maMethod == Enums.MAMethod.SMA) {
                double sum = 0;
                for (int j = g - maPeriod + 1; j <= g; j++) sum += hourlyBars.get(j).close;
                hourlyMA[g] = sum / maPeriod;
            } else {
                // EMA: seed with SMA, then standard EMA formula
                if (g == maPeriod - 1) {
                    double sum = 0;
                    for (int j = 0; j < maPeriod; j++) sum += hourlyBars.get(j).close;
                    hourlyMA[g] = sum / maPeriod;
                } else {
                    hourlyMA[g] = hourlyBars.get(g).close * emaK + hourlyMA[g - 1] * (1 - emaK);
                }
            }
        }

        // Map hourly MA to chart bars for display (step function)
        for (int g = 0; g < numGroups; g++) {
            if (Double.isNaN(hourlyMA[g])) continue;
            HourlyBar hb = hourlyBars.get(g);
            for (int i = hb.startIdx; i <= hb.endIdx; i++) {
                series.setDouble(i, Values.MA, hourlyMA[g]);
            }
        }

        // ===== PHASE 3: Detect swing points on hourly bars =====
        swingLevels.clear();
        entryMarkers.clear();

        for (int g = strength; g < numGroups - strength; g++) {
            HourlyBar hb = hourlyBars.get(g);
            boolean isSwingHigh = true;
            boolean isSwingLow = true;
            for (int j = g - strength; j <= g + strength; j++) {
                if (j == g) continue;
                HourlyBar other = hourlyBars.get(j);
                if (other.high >= hb.high) isSwingHigh = false;
                if (other.low <= hb.low) isSwingLow = false;
            }
            if (isSwingHigh) {
                swingLevels.add(new SwingLevel(hb.high, true, hb.time, g));
            }
            if (isSwingLow) {
                swingLevels.add(new SwingLevel(hb.low, false, hb.time, g));
            }
        }

        // ===== PHASE 4: SFP state machine on hourly bars =====
        for (int g = 0; g < numGroups; g++) {
            HourlyBar hb = hourlyBars.get(g);

            for (SwingLevel lv : swingLevels) {
                if (lv.traded || lv.canceled) continue;
                if (g <= lv.detectedGroupIndex) continue;

                // STATE_ACTIVE → STATE_BROKEN: hourly close breaks swing level
                if (lv.state == STATE_ACTIVE) {
                    if (lv.isHigh && hb.close > lv.price) {
                        lv.state = STATE_BROKEN;
                        lv.brokeGroupIndex = g;
                        lv.sweepExtreme = hb.high;
                    } else if (!lv.isHigh && hb.close < lv.price) {
                        lv.state = STATE_BROKEN;
                        lv.brokeGroupIndex = g;
                        lv.sweepExtreme = hb.low;
                    }
                    continue;
                }

                // STATE_BROKEN → SFP check on hourly close
                if (lv.state == STATE_BROKEN) {
                    if (g - lv.brokeGroupIndex > sfpWindow) {
                        lv.canceled = true;
                        continue;
                    }
                    // Track sweep extreme across hourly bars
                    if (lv.isHigh && hb.high > lv.sweepExtreme) lv.sweepExtreme = hb.high;
                    if (!lv.isHigh && hb.low < lv.sweepExtreme) lv.sweepExtreme = hb.low;

                    // SFP: hourly close back inside range
                    boolean sfp = (lv.isHigh && hb.close < lv.price) || (!lv.isHigh && hb.close > lv.price);
                    if (sfp) {
                        if (entryModel == ENTRY_IMMEDIATE) {
                            lv.state = STATE_ENTRY_READY;
                            lv.entryChartIndex = hb.endIdx;
                        } else {
                            lv.state = STATE_SFP;
                            lv.sfpChartIndex = hb.endIdx;
                        }
                    }
                    continue;
                }
            }
        }

        // ===== PHASE 5: FVG detection + entry on 5-min chart bars =====
        int localTradesToday = 0;
        int localLastDay = -1;

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

            // Determine bias from hourly MA at this bar's group
            int hourlyGroup = Math.min(i / groupSize, numGroups - 1);
            boolean allowLong = false, allowShort = false;
            switch (biasMode) {
                case BIAS_AUTO:
                    if (!Double.isNaN(hourlyMA[hourlyGroup])) {
                        allowLong = close > hourlyMA[hourlyGroup];
                        allowShort = close < hourlyMA[hourlyGroup];
                    }
                    break;
                case BIAS_LONG_ONLY:  allowLong = true; break;
                case BIAS_SHORT_ONLY: allowShort = true; break;
                case BIAS_BOTH:       allowLong = true; allowShort = true; break;
            }

            boolean pastEOD = eodEnabled && barTimeInt >= eodTime;
            boolean inSession = barTimeInt >= sessionStart && barTimeInt < sessionEnd;

            for (SwingLevel lv : swingLevels) {
                if (lv.traded || lv.canceled) continue;
                boolean isLong = !lv.isHigh; // swing LOW → LONG, swing HIGH → SHORT

                // STATE_ENTRY_READY: immediate entry at the specific chart bar
                if (lv.state == STATE_ENTRY_READY && i == lv.entryChartIndex) {
                    lv.traded = true;
                    boolean canEnter = (isLong ? allowLong : allowShort) && !pastEOD && inSession && localTradesToday < maxTrades;
                    if (canEnter) {
                        localTradesToday++;
                        addEntryMarker(settings, barTime, high, low, isLong, lv.price);
                        if (canSignal) {
                            ctx.signal(i, isLong ? Signals.SFP_LONG : Signals.SFP_SHORT,
                                "SFP " + (lv.isHigh ? "High" : "Low") + " " + fmt(lv.price), close);
                        }
                    }
                    continue;
                }

                // STATE_SFP: scan for FVG on 5-min bars after SFP
                if (lv.state == STATE_SFP) {
                    if (i <= lv.sfpChartIndex) continue;
                    if (i - lv.sfpChartIndex > entryWindow) {
                        lv.canceled = true;
                        continue;
                    }

                    // Scan for FVG if not yet found (3-candle gap pattern on 5-min)
                    if (!lv.fvgFound && i >= 2) {
                        if (isLong) {
                            // Bullish FVG: gap up — low[i] > high[i-2]
                            double highI2 = series.getHigh(i - 2);
                            double lowI = series.getLow(i);
                            if (lowI > highI2) {
                                lv.fvgFound = true;
                                lv.fvgBottom = highI2;
                                lv.fvgTop = lowI;
                            }
                        } else {
                            // Bearish FVG: gap down — high[i] < low[i-2]
                            double lowI2 = series.getLow(i - 2);
                            double highI = series.getHigh(i);
                            if (highI < lowI2) {
                                lv.fvgFound = true;
                                lv.fvgTop = lowI2;
                                lv.fvgBottom = highI;
                            }
                        }
                    }

                    // Retrace into FVG zone → entry
                    if (lv.fvgFound) {
                        boolean retrace = isLong ? (low <= lv.fvgTop) : (high >= lv.fvgBottom);
                        if (retrace) {
                            lv.traded = true;
                            boolean canEnter = (isLong ? allowLong : allowShort) && !pastEOD && inSession && localTradesToday < maxTrades;
                            if (canEnter) {
                                localTradesToday++;
                                addEntryMarker(settings, barTime, high, low, isLong, lv.price);
                                if (canSignal) {
                                    ctx.signal(i, isLong ? Signals.SFP_LONG : Signals.SFP_SHORT,
                                        "SFP+FVG " + (lv.isHigh ? "High" : "Low") + " " + fmt(lv.price), close);
                                }
                            }
                        }
                    }
                }
            }

            if (canSignal) series.setComplete(i);
        }

        // ===== Draw Figures =====
        long endTime = series.getStartTime(size - 1);
        int drawn = 0;
        if (settings.getBoolean(SHOW_LEVELS, true)) {
            for (SwingLevel lv : swingLevels) {
                if (lv.traded || lv.canceled) continue;
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

        tradesToday = localTradesToday;

        debug("JadeCap: " + hourlyBars.size() + " hrly bars, " + swingLevels.size() + " swings, "
            + drawn + " lines, " + entryMarkers.size() + " entries, " + tradesToday + " trades today");
    }

    private void addEntryMarker(Settings settings, long barTime, double high, double low, boolean isLong, double levelPrice)
    {
        if (isLong) {
            var marker = settings.getMarker(Inputs.UP_MARKER);
            if (marker != null && marker.isEnabled()) {
                entryMarkers.add(new Marker(new Coordinate(barTime, low),
                    Enums.Position.BOTTOM, marker, "SFP L " + fmt(levelPrice)));
            }
        } else {
            var marker = settings.getMarker(Inputs.DOWN_MARKER);
            if (marker != null && marker.isEnabled()) {
                entryMarkers.add(new Marker(new Coordinate(barTime, high),
                    Enums.Position.TOP, marker, "SFP S " + fmt(levelPrice)));
            }
        }
    }

    // ==================== BAR CLOSE (Study-level) ====================
    @Override
    public void onBarClose(DataContext ctx) { calculateValues(ctx); }

    // ==================== STRATEGY LIFECYCLE ====================

    @Override
    public void onActivate(OrderContext ctx) { debug("JadeCap Daily Sweep activated"); }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        if (ctx.getPosition() != 0) { ctx.closeAtMarket(); debug("Deactivated - closed position"); }
        resetTradeState();
    }

    // ==================== SIGNAL HANDLER ====================

    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        if (signal != Signals.SFP_LONG && signal != Signals.SFP_SHORT) return;
        if (ctx.getPosition() != 0) { debug("Already in position"); return; }

        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();
        var settings = getSettings();
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        int barTimeInt = getTimeInt(series.getStartTime(index));

        if (settings.getBoolean(EOD_ENABLED, true) && barTimeInt >= settings.getInteger(EOD_TIME, 1600)) {
            debug("Past EOD, blocking entry"); return;
        }

        int baseQty = settings.getInteger(CONTRACTS, 2);
        int qty = (tradesToday >= 1) ? Math.max(1, (int) Math.ceil(baseQty / 2.0)) : baseQty;

        int stopBufferTicks = settings.getInteger(STOP_BUFFER_TICKS, 4);
        double stopBuffer = stopBufferTicks * tickSize;
        double stopMinPts = settings.getDouble(STOP_MIN_PTS, 2.0);
        double stopMaxPts = settings.getDouble(STOP_MAX_PTS, 40.0);
        double rrRatio = settings.getDouble(RR_RATIO, 2.0);

        isLongTrade = (signal == Signals.SFP_LONG);

        // Find trigger level (most recently traded swing level matching direction)
        SwingLevel triggerLevel = null;
        for (SwingLevel lv : swingLevels) {
            if (lv.traded && lv.isHigh != isLongTrade) triggerLevel = lv;
        }

        if (isLongTrade) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();
            stopPrice = (triggerLevel != null && !Double.isNaN(triggerLevel.sweepExtreme))
                ? instr.round(triggerLevel.sweepExtreme - stopBuffer)
                : instr.round(entryPrice - stopMaxPts);
        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();
            stopPrice = (triggerLevel != null && !Double.isNaN(triggerLevel.sweepExtreme))
                ? instr.round(triggerLevel.sweepExtreme + stopBuffer)
                : instr.round(entryPrice + stopMaxPts);
        }

        // Clamp stop distance
        double dist = Math.abs(entryPrice - stopPrice);
        if (dist < stopMinPts) stopPrice = isLongTrade ? instr.round(entryPrice - stopMinPts) : instr.round(entryPrice + stopMinPts);
        if (dist > stopMaxPts) stopPrice = isLongTrade ? instr.round(entryPrice - stopMaxPts) : instr.round(entryPrice + stopMaxPts);

        // Fixed R:R target
        double stopDist = Math.abs(entryPrice - stopPrice);
        targetPrice = isLongTrade
            ? instr.round(entryPrice + stopDist * rrRatio)
            : instr.round(entryPrice - stopDist * rrRatio);

        beActivated = false;
        bestPriceInTrade = entryPrice;

        debug(String.format("=== %s ENTRY === qty=%d (trade#%d), entry=%.2f, stop=%.2f, target=%.2f (%.1fR)",
            isLongTrade ? "LONG" : "SHORT", qty, tradesToday, entryPrice, stopPrice, targetPrice, rrRatio));
    }

    // ==================== BAR CLOSE (Strategy-level) ====================

    @Override
    public void onBarClose(OrderContext ctx)
    {
        calculateValues(ctx.getDataContext());

        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime);
        var instr = ctx.getInstrument();
        var settings = getSettings();
        int barDay = getDayOfYear(barTime);

        if (barDay != lastResetDay) { eodProcessed = false; lastResetDay = barDay; }

        // EOD Flatten
        if (settings.getBoolean(EOD_ENABLED, true) && barTimeInt >= settings.getInteger(EOD_TIME, 1600) && !eodProcessed) {
            if (ctx.getPosition() != 0) { ctx.closeAtMarket(); debug("EOD flat"); resetTradeState(); }
            eodProcessed = true;
            return;
        }

        int position = ctx.getPosition();
        if (position == 0) { if (entryPrice > 0) resetTradeState(); return; }

        double high = series.getHigh(index);
        double low = series.getLow(index);
        boolean isLong = position > 0;

        if (isLong) { if (Double.isNaN(bestPriceInTrade) || high > bestPriceInTrade) bestPriceInTrade = high; }
        else { if (Double.isNaN(bestPriceInTrade) || low < bestPriceInTrade) bestPriceInTrade = low; }

        // Stop loss
        if ((isLong && low <= stopPrice) || (!isLong && high >= stopPrice)) {
            ctx.closeAtMarket();
            debug((isLong ? "LONG" : "SHORT") + " stopped at " + fmt(stopPrice) + (beActivated ? " (BE)" : ""));
            resetTradeState(); return;
        }

        // Target hit (fixed R:R)
        if ((isLong && high >= targetPrice) || (!isLong && low <= targetPrice)) {
            ctx.closeAtMarket();
            debug((isLong ? "LONG" : "SHORT") + " target hit at " + fmt(targetPrice));
            resetTradeState(); return;
        }

        // Breakeven
        if (!beActivated && settings.getBoolean(BE_ENABLED, true)) {
            double beTrigger = settings.getDouble(BE_TRIGGER_PTS, 10.0);
            double profitPts = isLong ? (bestPriceInTrade - entryPrice) : (entryPrice - bestPriceInTrade);
            if (profitPts >= beTrigger) {
                stopPrice = instr.round(entryPrice);
                beActivated = true;
                debug("Stop to BE at " + fmt(stopPrice));
            }
        }
    }

    // ==================== HELPERS ====================

    private void resetTradeState()
    {
        entryPrice = 0; stopPrice = 0; targetPrice = 0;
        beActivated = false; bestPriceInTrade = Double.NaN;
    }

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

    private String fmt(double val) { return String.format("%.2f", val); }

    @Override
    public void clearState()
    {
        super.clearState();
        swingLevels.clear(); entryMarkers.clear();
        resetTradeState(); tradesToday = 0; lastResetDay = -1; eodProcessed = false;
    }
}
