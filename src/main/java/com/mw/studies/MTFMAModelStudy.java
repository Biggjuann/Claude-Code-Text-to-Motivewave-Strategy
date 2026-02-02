package com.mw.studies;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

import java.awt.Color;
import java.util.*;

/**
 * MTF MA Model Study
 *
 * Multi-timeframe moving average trend filter with pivot-confirmed entries
 * and automatic order block visualization.
 *
 * Core Concept:
 * - LTF Entry Stack (5/13/34) + HTF Filter Stack (34/55/200)
 * - Generate pending signals when stacks align + fast/mid crossover
 * - Confirm entries only on pivot break
 * - Draw OB lines at signal pivot and invalidate on stop breach
 *
 * @version 0.1.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "MTF_MA_MODEL",
    rb = "com.mw.studies.nls.strings",
    name = "MTF MA Model",
    label = "MTF MA",
    desc = "Multi-timeframe MA trend filter with pivot-confirmed entries and order block visualization",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    signals = true,
    strategy = false,
    supportsBarUpdates = false
)
public class MTFMAModelStudy extends Study {

    // ==================== Constants ====================
    // MA Settings
    private static final String MA_TYPE = "maType";
    private static final String VW_DECAY = "vwDecay";

    // Entry Stack (LTF)
    private static final String ENTRY_LEN_FAST = "entryLenFast";
    private static final String ENTRY_LEN_MID = "entryLenMid";
    private static final String ENTRY_LEN_SLOW = "entryLenSlow";

    // HTF Settings
    private static final String HTF_MODE = "htfMode";
    private static final String HTF_MANUAL = "htfManual";
    private static final String HTF_LEN_FAST = "htfLenFast";
    private static final String HTF_LEN_MID = "htfLenMid";
    private static final String HTF_LEN_SLOW = "htfLenSlow";

    // Display
    private static final String SHOW_ENTRY_MAS = "showEntryMAs";
    private static final String SHOW_HTF_MAS = "showHTFMAs";
    private static final String MONOCHROME_MODE = "monochromeMode";

    // Order Blocks
    private static final String SHOW_OB_LINES = "showOBLines";
    private static final String OB_EXTEND_TYPE = "obExtendType";
    private static final String MAX_OB_LINES = "maxOBLines";

    // Position Sizing
    private static final String ENABLE_POS_SIZING = "enablePosSizing";
    private static final String ASSET_CLASS = "assetClass";
    private static final String ACCOUNT_BALANCE = "accountBalance";
    private static final String RISK_MODE = "riskMode";
    private static final String RISK_PERCENT = "riskPercent";
    private static final String RISK_AMOUNT = "riskAmount";
    private static final String FUTURES_POINT_VALUE = "futuresPointValue";
    private static final String FX_PIP_VALUE = "fxPipValue";
    private static final String CRYPTO_UNIT_VALUE = "cryptoUnitValue";

    // Risk
    private static final String STOPLOSS_ENABLED = "stoplossEnabled";
    private static final String STOP_MODE = "stopMode";
    private static final String STOP_BUFFER = "stopBuffer";
    private static final String STOP_DISTANCE_POINTS = "stopDistancePoints";

    // Path Keys
    private static final String ENTRY_FAST_PATH = "entryFastPath";
    private static final String ENTRY_MID_PATH = "entryMidPath";
    private static final String ENTRY_SLOW_PATH = "entrySlowPath";
    private static final String HTF_FAST_PATH = "htfFastPath";
    private static final String HTF_MID_PATH = "htfMidPath";
    private static final String HTF_SLOW_PATH = "htfSlowPath";

    // Mode Constants
    private static final int HTF_MODE_AUTO = 0;
    private static final int HTF_MODE_MANUAL = 1;

    private static final int OB_EXTEND_ALL = 0;
    private static final int OB_EXTEND_LATEST = 1;
    private static final int OB_EXTEND_NONE = 2;

    private static final int ASSET_FOREX = 0;
    private static final int ASSET_FUTURES = 1;
    private static final int ASSET_CRYPTO = 2;

    private static final int RISK_PERCENT_MODE = 0;
    private static final int RISK_FIXED_MODE = 1;

    private static final int STOP_TRACKING_EXTREME = 0;
    private static final int STOP_FIXED_POINTS = 1;
    private static final int STOP_SIGNAL_BAR = 2;

    // ==================== Values ====================
    enum Values {
        ENTRY_FAST,
        ENTRY_MID,
        ENTRY_SLOW,
        HTF_FAST,
        HTF_MID,
        HTF_SLOW,
        PIVOT_HIGH,
        PIVOT_LOW,
        STATE,
        STOP_LEVEL
    }

    // ==================== Signals ====================
    enum Signals {
        PENDING_LONG,
        PENDING_SHORT,
        CONFIRMED_LONG,
        CONFIRMED_SHORT
    }

    // ==================== State ====================
    private static final int STATE_IDLE = 0;
    private static final int STATE_PENDING_LONG = 1;
    private static final int STATE_PENDING_SHORT = 2;
    private static final int STATE_CONFIRMED_LONG = 3;
    private static final int STATE_CONFIRMED_SHORT = 4;

    // State tracking
    private int currentState = STATE_IDLE;
    private double pivotHighPrice = Double.NaN;
    private int pivotHighBarIndex = -1;
    private double pivotLowPrice = Double.NaN;
    private int pivotLowBarIndex = -1;
    private double minLowSincePending = Double.NaN;
    private double maxHighSincePending = Double.NaN;
    private int signalBarIndex = -1;
    private double signalBarLow = Double.NaN;
    private double signalBarHigh = Double.NaN;

    // Order Block tracking
    private List<OBLine> obLines = new ArrayList<>();

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {
        var sd = createSD();

        // ===== Moving Averages Tab =====
        var tab = sd.addTab("Moving Averages");

        var grp = tab.addGroup("MA Type");
        grp.addRow(new MAMethodDescriptor(MA_TYPE, "MA Method", Enums.MAMethod.EMA));
        grp.addRow(new DoubleDescriptor(VW_DECAY, "VW Decay Multiplier", 0.85, 0.01, 0.999, 0.01));

        grp = tab.addGroup("Entry Stack (LTF)");
        grp.addRow(new IntegerDescriptor(ENTRY_LEN_FAST, "Fast MA Length", 5, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_LEN_MID, "Mid MA Length", 13, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_LEN_SLOW, "Slow MA Length", 34, 1, 500, 1));

        // ===== HTF Filter Tab =====
        tab = sd.addTab("HTF Filter");

        grp = tab.addGroup("HTF Mode");
        grp.addRow(new IntegerDescriptor(HTF_MODE, "Mode (0=Auto, 1=Manual)", 0, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(HTF_MANUAL, "Manual HTF (minutes)", 60, 1, 1440, 1));

        grp = tab.addGroup("HTF Stack");
        grp.addRow(new IntegerDescriptor(HTF_LEN_FAST, "Fast MA Length", 34, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(HTF_LEN_MID, "Mid MA Length", 55, 1, 300, 1));
        grp.addRow(new IntegerDescriptor(HTF_LEN_SLOW, "Slow MA Length", 200, 1, 500, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");

        grp = tab.addGroup("Visibility");
        grp.addRow(new BooleanDescriptor(SHOW_ENTRY_MAS, "Show Entry MAs", true));
        grp.addRow(new BooleanDescriptor(SHOW_HTF_MAS, "Show HTF MAs", true));
        grp.addRow(new BooleanDescriptor(MONOCHROME_MODE, "Monochrome Mode", false));

        grp = tab.addGroup("Entry MA Lines");
        grp.addRow(new PathDescriptor(ENTRY_FAST_PATH, "Fast MA", new Color(0, 200, 255), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(ENTRY_MID_PATH, "Mid MA", new Color(100, 180, 255), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(ENTRY_SLOW_PATH, "Slow MA", new Color(50, 100, 200), 1.5f, null, true, true, true));

        grp = tab.addGroup("HTF MA Lines");
        grp.addRow(new PathDescriptor(HTF_FAST_PATH, "HTF Fast MA", new Color(255, 150, 50), 2.0f, null, true, true, true));
        grp.addRow(new PathDescriptor(HTF_MID_PATH, "HTF Mid MA", new Color(255, 100, 0), 2.0f, null, true, true, true));
        grp.addRow(new PathDescriptor(HTF_SLOW_PATH, "HTF Slow MA", new Color(200, 50, 0), 2.0f, null, true, true, true));

        // ===== Order Blocks Tab =====
        tab = sd.addTab("Order Blocks");

        grp = tab.addGroup("OB Lines");
        grp.addRow(new BooleanDescriptor(SHOW_OB_LINES, "Show OB Lines", true));
        grp.addRow(new IntegerDescriptor(OB_EXTEND_TYPE, "Extend (0=All, 1=Latest, 2=None)", 1, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(MAX_OB_LINES, "Max OB Lines", 20, 1, 100, 1));

        // ===== Position Sizing Tab =====
        tab = sd.addTab("Position Sizing");

        grp = tab.addGroup("Settings");
        grp.addRow(new BooleanDescriptor(ENABLE_POS_SIZING, "Enable Position Sizing", false));
        grp.addRow(new IntegerDescriptor(ASSET_CLASS, "Asset (0=Forex, 1=Futures, 2=Crypto)", 1, 0, 2, 1));
        grp.addRow(new DoubleDescriptor(ACCOUNT_BALANCE, "Account Balance", 50000, 0, 10000000, 100));
        grp.addRow(new IntegerDescriptor(RISK_MODE, "Risk Mode (0=%, 1=Fixed)", 0, 0, 1, 1));
        grp.addRow(new DoubleDescriptor(RISK_PERCENT, "Risk %", 1.0, 0.01, 20.0, 0.05));
        grp.addRow(new DoubleDescriptor(RISK_AMOUNT, "Risk Amount ($)", 500, 0, 100000, 10));

        grp = tab.addGroup("Instrument Values");
        grp.addRow(new DoubleDescriptor(FUTURES_POINT_VALUE, "Futures $/Point", 5.0, 0.0001, 1000, 0.25));
        grp.addRow(new DoubleDescriptor(FX_PIP_VALUE, "Forex $/Pip per Lot", 10.0, 0.0001, 100, 0.1));
        grp.addRow(new DoubleDescriptor(CRYPTO_UNIT_VALUE, "Crypto Unit Value", 1.0, 0.00000001, 100000, 0.01));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new BooleanDescriptor(STOPLOSS_ENABLED, "Enable Stop Tracking", true));
        grp.addRow(new IntegerDescriptor(STOP_MODE, "Mode (0=Tracking, 1=Fixed, 2=SignalBar)", 0, 0, 2, 1));
        grp.addRow(new DoubleDescriptor(STOP_BUFFER, "Stop Buffer (points)", 0.0, 0.0, 100, 0.25));
        grp.addRow(new DoubleDescriptor(STOP_DISTANCE_POINTS, "Fixed Stop Distance", 10.0, 0.25, 500, 0.25));

        // ===== Markers Tab =====
        tab = sd.addTab("Markers");

        grp = tab.addGroup("Signal Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Signal",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Signal",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(ENTRY_LEN_FAST, ENTRY_LEN_MID, ENTRY_LEN_SLOW, MA_TYPE);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(ENTRY_LEN_FAST, ENTRY_LEN_MID, ENTRY_LEN_SLOW, MA_TYPE);

        // Export values
        desc.exportValue(new ValueDescriptor(Values.ENTRY_FAST, "Entry Fast MA", new String[]{ENTRY_LEN_FAST}));
        desc.exportValue(new ValueDescriptor(Values.ENTRY_MID, "Entry Mid MA", new String[]{ENTRY_LEN_MID}));
        desc.exportValue(new ValueDescriptor(Values.ENTRY_SLOW, "Entry Slow MA", new String[]{ENTRY_LEN_SLOW}));
        desc.exportValue(new ValueDescriptor(Values.HTF_FAST, "HTF Fast MA", new String[]{HTF_LEN_FAST}));
        desc.exportValue(new ValueDescriptor(Values.HTF_MID, "HTF Mid MA", new String[]{HTF_LEN_MID}));
        desc.exportValue(new ValueDescriptor(Values.HTF_SLOW, "HTF Slow MA", new String[]{HTF_LEN_SLOW}));

        // Declare paths
        desc.declarePath(Values.ENTRY_FAST, ENTRY_FAST_PATH);
        desc.declarePath(Values.ENTRY_MID, ENTRY_MID_PATH);
        desc.declarePath(Values.ENTRY_SLOW, ENTRY_SLOW_PATH);
        desc.declarePath(Values.HTF_FAST, HTF_FAST_PATH);
        desc.declarePath(Values.HTF_MID, HTF_MID_PATH);
        desc.declarePath(Values.HTF_SLOW, HTF_SLOW_PATH);

        // Declare signals
        desc.declareSignal(Signals.PENDING_LONG, "Pending Long");
        desc.declareSignal(Signals.PENDING_SHORT, "Pending Short");
        desc.declareSignal(Signals.CONFIRMED_LONG, "Confirmed Long");
        desc.declareSignal(Signals.CONFIRMED_SHORT, "Confirmed Short");

        // Range keys
        desc.setRangeKeys(Values.ENTRY_FAST, Values.ENTRY_MID, Values.ENTRY_SLOW);
    }

    @Override
    public void onLoad(Defaults defaults) {
        int slow = getSettings().getInteger(ENTRY_LEN_SLOW, 34);
        int htfSlow = getSettings().getInteger(HTF_LEN_SLOW, 200);
        setMinBars(Math.max(slow, htfSlow) * 2);
    }

    @Override
    public int getMinBars() {
        int slow = getSettings().getInteger(ENTRY_LEN_SLOW, 34);
        int htfSlow = getSettings().getInteger(HTF_LEN_SLOW, 200);
        return Math.max(slow, htfSlow) * 2;
    }

    // ==================== Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx) {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();

        // Get settings
        var maMethod = getSettings().getMAMethod(MA_TYPE, Enums.MAMethod.EMA);
        int entryFastLen = getSettings().getInteger(ENTRY_LEN_FAST, 5);
        int entryMidLen = getSettings().getInteger(ENTRY_LEN_MID, 13);
        int entrySlowLen = getSettings().getInteger(ENTRY_LEN_SLOW, 34);
        int htfFastLen = getSettings().getInteger(HTF_LEN_FAST, 34);
        int htfMidLen = getSettings().getInteger(HTF_LEN_MID, 55);
        int htfSlowLen = getSettings().getInteger(HTF_LEN_SLOW, 200);
        boolean showEntryMAs = getSettings().getBoolean(SHOW_ENTRY_MAS, true);
        boolean showHTFMAs = getSettings().getBoolean(SHOW_HTF_MAS, true);
        boolean monochromeMode = getSettings().getBoolean(MONOCHROME_MODE, false);
        boolean stoplossEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);
        int stopMode = getSettings().getInteger(STOP_MODE, STOP_TRACKING_EXTREME);
        double stopBuffer = getSettings().getDouble(STOP_BUFFER, 0.0);

        // Need enough bars
        int minBars = Math.max(entrySlowLen, htfSlowLen);
        if (index < minBars) return;

        double close = series.getClose(index);
        double high = series.getHigh(index);
        double low = series.getLow(index);
        long barTime = series.getStartTime(index);

        // ===== Calculate Entry Stack (LTF) MAs =====
        Double entryFast = series.ma(maMethod, index, entryFastLen, Enums.BarInput.CLOSE);
        Double entryMid = series.ma(maMethod, index, entryMidLen, Enums.BarInput.CLOSE);
        Double entrySlow = series.ma(maMethod, index, entrySlowLen, Enums.BarInput.CLOSE);

        if (entryFast == null || entryMid == null || entrySlow == null) return;

        if (showEntryMAs) {
            series.setDouble(index, Values.ENTRY_FAST, entryFast);
            series.setDouble(index, Values.ENTRY_MID, entryMid);
            series.setDouble(index, Values.ENTRY_SLOW, entrySlow);
        }

        // ===== Calculate HTF MAs =====
        // HTF MAs are approximated by using longer periods on the LTF series
        // This simulates the smoothing effect of higher timeframe MAs
        int htfMultiplier = getHTFMultiplier(series);
        int htfFastPeriod = htfFastLen * htfMultiplier;
        int htfMidPeriod = htfMidLen * htfMultiplier;
        int htfSlowPeriod = htfSlowLen * htfMultiplier;

        Double htfFast = null, htfMid = null, htfSlow = null;

        if (index >= htfSlowPeriod) {
            htfFast = series.ma(maMethod, index, htfFastPeriod, Enums.BarInput.CLOSE);
            htfMid = series.ma(maMethod, index, htfMidPeriod, Enums.BarInput.CLOSE);
            htfSlow = series.ma(maMethod, index, htfSlowPeriod, Enums.BarInput.CLOSE);

            if (showHTFMAs && htfFast != null && htfMid != null && htfSlow != null) {
                series.setDouble(index, Values.HTF_FAST, htfFast);
                series.setDouble(index, Values.HTF_MID, htfMid);
                series.setDouble(index, Values.HTF_SLOW, htfSlow);
            }
        }

        // ===== Pivot Detection =====
        // Pivot Low: bullish candle after bearish (close > open after close < open)
        // Pivot High: bearish candle after bullish (close < open after close > open)
        if (index >= 2) {
            double prevClose = series.getClose(index - 1);
            double prevOpen = series.getOpen(index - 1);
            double prev2Close = series.getClose(index - 2);
            double prev2Open = series.getOpen(index - 2);

            boolean prevBullish = prevClose > prevOpen;
            boolean prev2Bearish = prev2Close < prev2Open;
            boolean prevBearish = prevClose < prevOpen;
            boolean prev2Bullish = prev2Close > prev2Open;

            // Pivot low: bullish candle after bearish
            if (prevBullish && prev2Bearish) {
                double pivLow = series.getLow(index - 1);
                if (Double.isNaN(pivotLowPrice) || pivLow < pivotLowPrice) {
                    pivotLowPrice = pivLow;
                    pivotLowBarIndex = index - 1;
                }
            }

            // Pivot high: bearish candle after bullish
            if (prevBearish && prev2Bullish) {
                double pivHigh = series.getHigh(index - 1);
                if (Double.isNaN(pivotHighPrice) || pivHigh > pivotHighPrice) {
                    pivotHighPrice = pivHigh;
                    pivotHighBarIndex = index - 1;
                }
            }
        }

        // Only process on completed bars
        if (!series.isBarComplete(index)) return;

        // ===== Determine Stack Bias =====
        boolean entryStackBullish = entryFast > entryMid && entryMid > entrySlow;
        boolean entryStackBearish = entryFast < entryMid && entryMid < entrySlow;
        boolean priceAboveEntryMAs = close > entryFast && close > entryMid && close > entrySlow;
        boolean priceBelowEntryMAs = close < entryFast && close < entryMid && close < entrySlow;

        boolean htfStackBullish = false;
        boolean htfStackBearish = false;
        boolean priceAboveHTFMAs = false;
        boolean priceBelowHTFMAs = false;

        if (htfFast != null && htfMid != null && htfSlow != null) {
            htfStackBullish = htfFast > htfMid && htfMid > htfSlow;
            htfStackBearish = htfFast < htfMid && htfMid < htfSlow;
            priceAboveHTFMAs = close > htfFast && close > htfMid && close > htfSlow;
            priceBelowHTFMAs = close < htfFast && close < htfMid && close < htfSlow;
        }

        // ===== Check for Fast/Mid Crossovers =====
        boolean crossAbove = crossedAbove(series, index, Values.ENTRY_FAST, Values.ENTRY_MID);
        boolean crossBelow = crossedBelow(series, index, Values.ENTRY_FAST, Values.ENTRY_MID);

        // ===== State Machine Logic =====

        // Track extremes while pending
        if (currentState == STATE_PENDING_LONG) {
            if (Double.isNaN(minLowSincePending)) {
                minLowSincePending = low;
            } else {
                minLowSincePending = Math.min(minLowSincePending, low);
            }
        } else if (currentState == STATE_PENDING_SHORT) {
            if (Double.isNaN(maxHighSincePending)) {
                maxHighSincePending = high;
            } else {
                maxHighSincePending = Math.max(maxHighSincePending, high);
            }
        }

        // Check for stop invalidation on pending/confirmed states
        if (stoplossEnabled && currentState != STATE_IDLE) {
            double stopPrice = calculateStopPrice(currentState == STATE_PENDING_LONG || currentState == STATE_CONFIRMED_LONG,
                stopMode, stopBuffer, series, index);

            if (currentState == STATE_PENDING_LONG || currentState == STATE_CONFIRMED_LONG) {
                if (low <= stopPrice) {
                    // Invalidate - remove most recent bullish OB line
                    invalidateOBLine(true);
                    resetState();
                }
            } else if (currentState == STATE_PENDING_SHORT || currentState == STATE_CONFIRMED_SHORT) {
                if (high >= stopPrice) {
                    // Invalidate - remove most recent bearish OB line
                    invalidateOBLine(false);
                    resetState();
                }
            }
        }

        // Pending Long conditions
        if (currentState == STATE_IDLE && crossAbove) {
            if (entryStackBullish && priceAboveEntryMAs && htfStackBullish && priceAboveHTFMAs) {
                currentState = STATE_PENDING_LONG;
                signalBarIndex = index;
                signalBarLow = low;
                signalBarHigh = high;
                minLowSincePending = low;

                series.setBoolean(index, Signals.PENDING_LONG, true);
                ctx.signal(index, Signals.PENDING_LONG, "Pending Long - awaiting pivot confirmation", close);

                // Draw pending marker
                var marker = getSettings().getMarker(Inputs.UP_MARKER);
                if (marker.isEnabled()) {
                    var coord = new Coordinate(barTime, low);
                    addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "PENDING L"));
                }
            }
        }

        // Pending Short conditions
        if (currentState == STATE_IDLE && crossBelow) {
            if (entryStackBearish && priceBelowEntryMAs && htfStackBearish && priceBelowHTFMAs) {
                currentState = STATE_PENDING_SHORT;
                signalBarIndex = index;
                signalBarLow = low;
                signalBarHigh = high;
                maxHighSincePending = high;

                series.setBoolean(index, Signals.PENDING_SHORT, true);
                ctx.signal(index, Signals.PENDING_SHORT, "Pending Short - awaiting pivot confirmation", close);

                // Draw pending marker
                var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
                if (marker.isEnabled()) {
                    var coord = new Coordinate(barTime, high);
                    addFigure(new Marker(coord, Enums.Position.TOP, marker, "PENDING S"));
                }
            }
        }

        // Long Confirmation: close > pivot high
        if (currentState == STATE_PENDING_LONG && !Double.isNaN(pivotHighPrice) && close > pivotHighPrice) {
            currentState = STATE_CONFIRMED_LONG;

            series.setBoolean(index, Signals.CONFIRMED_LONG, true);
            ctx.signal(index, Signals.CONFIRMED_LONG, "Long Confirmed - broke pivot high " + pivotHighPrice, close);

            // Add OB line at pivot high
            if (getSettings().getBoolean(SHOW_OB_LINES, true)) {
                addOBLine(pivotHighPrice, pivotHighBarIndex, barTime, true, series);
            }

            // Draw confirmation marker
            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, low - (instr.getTickSize() * 5));
                addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "LONG"));
            }

            // Log position sizing
            logPositionSizing(true, close, stopBuffer, stopMode, series, index, ctx);

            // Reset pending state
            resetState();
        }

        // Short Confirmation: close < pivot low
        if (currentState == STATE_PENDING_SHORT && !Double.isNaN(pivotLowPrice) && close < pivotLowPrice) {
            currentState = STATE_CONFIRMED_SHORT;

            series.setBoolean(index, Signals.CONFIRMED_SHORT, true);
            ctx.signal(index, Signals.CONFIRMED_SHORT, "Short Confirmed - broke pivot low " + pivotLowPrice, close);

            // Add OB line at pivot low
            if (getSettings().getBoolean(SHOW_OB_LINES, true)) {
                addOBLine(pivotLowPrice, pivotLowBarIndex, barTime, false, series);
            }

            // Draw confirmation marker
            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, high + (instr.getTickSize() * 5));
                addFigure(new Marker(coord, Enums.Position.TOP, marker, "SHORT"));
            }

            // Log position sizing
            logPositionSizing(false, close, stopBuffer, stopMode, series, index, ctx);

            // Reset pending state
            resetState();
        }

        // Extend OB lines
        updateOBLines(barTime);

        series.setComplete(index);
    }

    // ==================== Helper Methods ====================

    /**
     * Gets the HTF data series based on mode setting.
     * Note: This returns the LTF series for now - true MTF requires advanced SDK features.
     * The HTF MAs are calculated with longer periods to simulate HTF behavior.
     */
    private DataSeries getHTFSeries(DataContext ctx, DataSeries ltfSeries) {
        // For simplicity, we use the same series but with longer periods
        // This is a common approximation when true MTF is complex to implement
        return ltfSeries;
    }

    /**
     * Gets the HTF multiplier based on mode setting.
     * This is used to scale the HTF MA periods.
     */
    private int getHTFMultiplier(DataSeries series) {
        int htfMode = getSettings().getInteger(HTF_MODE, HTF_MODE_AUTO);

        if (htfMode == HTF_MODE_MANUAL) {
            int htfManual = getSettings().getInteger(HTF_MANUAL, 60);
            // Estimate LTF minutes from bar duration
            int ltfMinutes = estimateBarMinutes(series);
            return Math.max(1, htfManual / ltfMinutes);
        }

        // Auto mode - estimate based on chart timeframe
        int ltfMinutes = estimateBarMinutes(series);

        if (ltfMinutes <= 5) {
            return 12; // 5m -> 1H (12x)
        } else if (ltfMinutes <= 15) {
            return 16; // 15m -> 4H (16x)
        } else if (ltfMinutes <= 60) {
            return 24; // 1H -> 1D (24x)
        }
        return 12; // Default
    }

    /**
     * Estimates bar size in minutes from the series.
     */
    private int estimateBarMinutes(DataSeries series) {
        if (series.size() < 2) return 5;
        long diff = series.getStartTime(1) - series.getStartTime(0);
        int minutes = (int)(diff / 60000);
        return Math.max(1, minutes);
    }

    /**
     * Calculates stop price based on mode.
     */
    private double calculateStopPrice(boolean isLong, int stopMode, double stopBuffer, DataSeries series, int index) {
        double stopDistancePoints = getSettings().getDouble(STOP_DISTANCE_POINTS, 10.0);

        if (isLong) {
            switch (stopMode) {
                case STOP_TRACKING_EXTREME:
                    return Double.isNaN(minLowSincePending) ? Double.MIN_VALUE : minLowSincePending - stopBuffer;
                case STOP_FIXED_POINTS:
                    return series.getClose(index) - stopDistancePoints - stopBuffer;
                case STOP_SIGNAL_BAR:
                    return Double.isNaN(signalBarLow) ? Double.MIN_VALUE : signalBarLow - stopBuffer;
                default:
                    return Double.MIN_VALUE;
            }
        } else {
            switch (stopMode) {
                case STOP_TRACKING_EXTREME:
                    return Double.isNaN(maxHighSincePending) ? Double.MAX_VALUE : maxHighSincePending + stopBuffer;
                case STOP_FIXED_POINTS:
                    return series.getClose(index) + stopDistancePoints + stopBuffer;
                case STOP_SIGNAL_BAR:
                    return Double.isNaN(signalBarHigh) ? Double.MAX_VALUE : signalBarHigh + stopBuffer;
                default:
                    return Double.MAX_VALUE;
            }
        }
    }

    /**
     * Logs position sizing information.
     */
    private void logPositionSizing(boolean isLong, double entryPrice, double stopBuffer, int stopMode,
            DataSeries series, int index, DataContext ctx) {
        if (!getSettings().getBoolean(ENABLE_POS_SIZING, false)) return;

        double stopPrice = calculateStopPrice(isLong, stopMode, stopBuffer, series, index);
        double stopDistance = Math.abs(entryPrice - stopPrice);

        int assetClass = getSettings().getInteger(ASSET_CLASS, ASSET_FUTURES);
        double accountBalance = getSettings().getDouble(ACCOUNT_BALANCE, 50000);
        int riskMode = getSettings().getInteger(RISK_MODE, RISK_PERCENT_MODE);
        double riskPercent = getSettings().getDouble(RISK_PERCENT, 1.0);
        double riskAmount = getSettings().getDouble(RISK_AMOUNT, 500);

        double riskBudget = (riskMode == RISK_PERCENT_MODE)
            ? accountBalance * (riskPercent / 100.0)
            : riskAmount;

        double suggestedSize = 0;
        switch (assetClass) {
            case ASSET_FUTURES:
                double pointValue = getSettings().getDouble(FUTURES_POINT_VALUE, 5.0);
                suggestedSize = Math.floor(riskBudget / (stopDistance * pointValue));
                break;
            case ASSET_FOREX:
                double pipValue = getSettings().getDouble(FX_PIP_VALUE, 10.0);
                suggestedSize = riskBudget / (stopDistance * pipValue);
                break;
            case ASSET_CRYPTO:
                suggestedSize = riskBudget / stopDistance;
                break;
        }

        debug(String.format("Position Sizing: Entry=%.2f, Stop=%.2f, Risk=$%.2f, Size=%.2f",
            entryPrice, stopPrice, riskBudget, suggestedSize));
    }

    /**
     * Adds an OB line.
     */
    private void addOBLine(double price, int barIndex, long endTime, boolean isBullish, DataSeries series) {
        int maxLines = getSettings().getInteger(MAX_OB_LINES, 20);

        // Remove oldest if at max
        while (obLines.size() >= maxLines) {
            obLines.remove(0);
        }

        OBLine line = new OBLine();
        line.price = price;
        line.startBarIndex = barIndex;
        line.startTime = series.getStartTime(barIndex);
        line.endTime = endTime;
        line.isBullish = isBullish;
        line.valid = true;

        obLines.add(line);
        drawOBLine(line, series);
    }

    /**
     * Draws an OB line on the chart.
     */
    private void drawOBLine(OBLine line, DataSeries series) {
        int extendType = getSettings().getInteger(OB_EXTEND_TYPE, OB_EXTEND_LATEST);

        Color color = line.isBullish ? new Color(0, 180, 0, 180) : new Color(180, 0, 0, 180);

        var start = new Coordinate(line.startTime, line.price);
        var end = new Coordinate(line.endTime, line.price);

        // Use Line constructor with start/end coordinates
        Line fig = new Line(start, end);
        fig.setColor(color);
        fig.setStroke(new java.awt.BasicStroke(2.0f, java.awt.BasicStroke.CAP_ROUND, java.awt.BasicStroke.JOIN_ROUND));

        // Extension is handled by updating end coordinate
        line.figure = fig;
        addFigure(fig);
    }

    /**
     * Updates OB line extensions.
     */
    private void updateOBLines(long currentTime) {
        int extendType = getSettings().getInteger(OB_EXTEND_TYPE, OB_EXTEND_LATEST);

        for (int i = 0; i < obLines.size(); i++) {
            OBLine line = obLines.get(i);
            if (!line.valid) continue;

            boolean shouldExtend = (extendType == OB_EXTEND_ALL) ||
                (extendType == OB_EXTEND_LATEST && i == obLines.size() - 1);

            if (line.figure != null && shouldExtend) {
                // Update end time to extend the line
                line.endTime = currentTime;
                line.figure.setEnd(currentTime, line.price);
            }
        }
    }

    /**
     * Invalidates OB line when stop is breached.
     */
    private void invalidateOBLine(boolean isBullish) {
        // Find and remove most recent line of the given type
        for (int i = obLines.size() - 1; i >= 0; i--) {
            OBLine line = obLines.get(i);
            if (line.isBullish == isBullish && line.valid) {
                line.valid = false;
                if (line.figure != null) {
                    removeFigure(line.figure);
                }
                debug("OB Line invalidated at price " + line.price);
                break;
            }
        }
    }

    /**
     * Resets state tracking variables.
     */
    private void resetState() {
        currentState = STATE_IDLE;
        minLowSincePending = Double.NaN;
        maxHighSincePending = Double.NaN;
        signalBarIndex = -1;
        signalBarLow = Double.NaN;
        signalBarHigh = Double.NaN;
        // Keep pivot tracking - they persist
    }

    @Override
    public void clearState() {
        super.clearState();
        currentState = STATE_IDLE;
        pivotHighPrice = Double.NaN;
        pivotHighBarIndex = -1;
        pivotLowPrice = Double.NaN;
        pivotLowBarIndex = -1;
        minLowSincePending = Double.NaN;
        maxHighSincePending = Double.NaN;
        signalBarIndex = -1;
        signalBarLow = Double.NaN;
        signalBarHigh = Double.NaN;
        obLines.clear();
    }

    // ==================== Inner Classes ====================

    /**
     * Order Block Line tracking.
     */
    private static class OBLine {
        double price;
        int startBarIndex;
        long startTime;
        long endTime;
        boolean isBullish;
        boolean valid;
        Line figure;
    }
}
