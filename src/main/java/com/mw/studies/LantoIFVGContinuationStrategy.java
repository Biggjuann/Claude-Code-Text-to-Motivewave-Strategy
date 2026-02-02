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
 * Lanto-style IFVG Continuation Strategy (1m, NQ/MNQ)
 *
 * A trend-aligned IFVG (Inverse Fair Value Gap) continuation strategy designed
 * for 1-minute charts with:
 * - IFVG detection (inverse FVG from displacement)
 * - Displacement filter (1.6x average range)
 * - Chop filter (overlap ratio)
 * - Bias model (EMA 9/21 slope + structure)
 * - Session gating with cooldown
 * - Fixed-R exits with partials and breakeven stop
 * - Time stop and forced flat
 *
 * @version 1.0.0
 * @author MW Study Builder (Lanto-style IFVG concepts)
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "LANTO_IFVG_CONTINUATION",
    rb = "com.mw.studies.nls.strings",
    name = "LANTO_IFVG_CONTINUATION",
    label = "LBL_LANTO_IFVG",
    desc = "DESC_LANTO_IFVG",
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
    supportsBarUpdates = true
)
public class LantoIFVGContinuationStrategy extends Study
{
    // ==================== Input Keys ====================
    // Sessions
    private static final String NY_AM_ENABLED = "nyAmEnabled";
    private static final String NY_AM_START = "nyAmStart";
    private static final String NY_AM_END = "nyAmEnd";
    private static final String NY_PM_ENABLED = "nyPmEnabled";
    private static final String NY_PM_START = "nyPmStart";
    private static final String NY_PM_END = "nyPmEnd";
    private static final String COOLDOWN_MINUTES = "cooldownMinutes";
    private static final String MAX_TRADES_PER_WINDOW = "maxTradesPerWindow";

    // Bias Model
    private static final String BIAS_ENABLED = "biasEnabled";
    private static final String FAST_MA_PERIOD = "fastMaPeriod";
    private static final String SLOW_MA_PERIOD = "slowMaPeriod";
    private static final String MA_SLOPE_BARS = "maSlopeBars";
    private static final String STRUCTURE_ENABLED = "structureEnabled";
    private static final String PIVOT_LEFT = "pivotLeft";
    private static final String PIVOT_RIGHT = "pivotRight";

    // Displacement Filter
    private static final String DISPLACEMENT_ENABLED = "displacementEnabled";
    private static final String DISPLACEMENT_LOOKBACK = "displacementLookback";
    private static final String DISPLACEMENT_MULTIPLE = "displacementMultiple";
    private static final String MIN_IMPULSE_BARS = "minImpulseBars";

    // Chop Filter
    private static final String CHOP_ENABLED = "chopEnabled";
    private static final String CHOP_LOOKBACK = "chopLookback";
    private static final String MAX_OVERLAP_RATIO = "maxOverlapRatio";

    // IFVG Model
    private static final String MIN_GAP_POINTS = "minGapPoints";
    private static final String ZONE_ENTRY_LEVEL = "zoneEntryLevel";
    private static final String ZONE_MAX_AGE = "zoneMaxAge";
    private static final String MAX_ACTIVE_ZONES = "maxActiveZones";

    // Entry
    private static final String ENABLE_LONG = "enableLong";
    private static final String ENABLE_SHORT = "enableShort";
    private static final String REQUIRE_REJECTION = "requireRejection";
    private static final String MAX_WAIT_CONFIRMATION = "maxWaitConfirmation";
    private static final String ENTRY_BUFFER_POINTS = "entryBufferPoints";

    // Risk/Position Sizing
    private static final String SIZING_MODE = "sizingMode";
    private static final String FIXED_CONTRACTS = "fixedContracts";
    private static final String ACCOUNT_SIZE = "accountSize";
    private static final String RISK_PERCENT = "riskPercent";
    private static final String MAX_CONTRACTS = "maxContracts";

    // Stop Loss
    private static final String STOP_BUFFER_POINTS = "stopBufferPoints";
    private static final String MAX_STOP_POINTS = "maxStopPoints";

    // Exits
    private static final String TARGET_R = "targetR";
    private static final String PARTIAL_ENABLED = "partialEnabled";
    private static final String PARTIAL_R = "partialR";
    private static final String PARTIAL_PCT = "partialPct";
    private static final String BE_ENABLED = "beEnabled";
    private static final String BE_AT_R = "beAtR";
    private static final String BE_OFFSET_POINTS = "beOffsetPoints";

    // Time Stop
    private static final String TIME_STOP_ENABLED = "timeStopEnabled";
    private static final String MAX_BARS_IN_TRADE = "maxBarsInTrade";
    private static final String PROGRESS_CHECK_ENABLED = "progressCheckEnabled";
    private static final String NO_PROGRESS_BARS = "noProgressBars";

    // Daily Limits
    private static final String DAILY_LIMIT_ENABLED = "dailyLimitEnabled";
    private static final String MAX_DAILY_LOSS_R = "maxDailyLossR";

    // Forced Flat
    private static final String FORCED_FLAT_ENABLED = "forcedFlatEnabled";
    private static final String FORCED_FLAT_TIME = "forcedFlatTime";

    // Display
    private static final String IFVG_ZONE_PATH = "ifvgZonePath";
    private static final String FAST_MA_PATH = "fastMaPath";
    private static final String SLOW_MA_PATH = "slowMaPath";
    private static final String SWING_HIGH_PATH = "swingHighPath";
    private static final String SWING_LOW_PATH = "swingLowPath";

    // ==================== Mode Constants ====================
    private static final int SIZING_FIXED = 0;
    private static final int SIZING_RISK_BASED = 1;

    private static final int ZONE_ENTRY_MID = 0;
    private static final int ZONE_ENTRY_EDGE = 1;

    private static final int BIAS_BULLISH = 1;
    private static final int BIAS_BEARISH = -1;
    private static final int BIAS_NEUTRAL = 0;

    // ==================== Values ====================
    enum Values {
        FAST_MA, SLOW_MA, SWING_HIGH, SWING_LOW,
        BULL_ZONE_TOP, BULL_ZONE_BOTTOM, BEAR_ZONE_TOP, BEAR_ZONE_BOTTOM,
        SESSION_HIGH, SESSION_LOW, PDH, PDL
    }

    // ==================== Signals ====================
    enum Signals {
        BULLISH_IFVG, BEARISH_IFVG, DISPLACEMENT_UP, DISPLACEMENT_DOWN,
        ENTRY_LONG, ENTRY_SHORT, STOP_HIT, TARGET_HIT, PARTIAL_EXIT
    }

    // ==================== Zone State ====================
    private static class IFVGZone {
        double top;
        double bottom;
        int barIndex;
        boolean isBullish;
        boolean isValid;
        boolean isInverted;

        IFVGZone(double top, double bottom, int barIndex, boolean isBullish) {
            this.top = top;
            this.bottom = bottom;
            this.barIndex = barIndex;
            this.isBullish = isBullish;
            this.isValid = true;
            this.isInverted = false;
        }

        double getMid() {
            return (top + bottom) / 2.0;
        }
    }

    // ==================== State Variables ====================
    // IFVG zones
    private List<IFVGZone> activeZones = new ArrayList<>();

    // Swing tracking
    private double lastSwingHigh = Double.NaN;
    private double lastSwingLow = Double.NaN;
    private int lastSwingHighBar = -1;
    private int lastSwingLowBar = -1;
    private double prevSwingHigh = Double.NaN;
    private double prevSwingLow = Double.NaN;

    // Bias tracking
    private int currentBias = BIAS_NEUTRAL;
    private int structureBias = BIAS_NEUTRAL;
    private int maBias = BIAS_NEUTRAL;

    // Session tracking
    private double sessionHigh = Double.NaN;
    private double sessionLow = Double.NaN;
    private double pdh = Double.NaN;
    private double pdl = Double.NaN;
    private double todayHigh = Double.NaN;
    private double todayLow = Double.NaN;
    private int lastResetDay = -1;

    // Trade tracking
    private int tradesThisWindow = 0;
    private long lastTradeTime = 0;
    private boolean inPosition = false;
    private boolean isLongPosition = false;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double targetPrice = 0;
    private double riskPoints = 0;
    private int entryBar = -1;
    private boolean partialTaken = false;
    private boolean movedToBE = false;
    private double bestProgress = 0;

    // Daily P&L tracking
    private double dailyRPL = 0;
    private boolean dailyLimitHit = false;

    // State
    private boolean flatProcessed = false;
    private int currentWindow = 0; // 0=none, 1=NY_AM, 2=NY_PM

    // Displacement detection
    private boolean recentBullDisplacement = false;
    private boolean recentBearDisplacement = false;
    private int lastBullDisplacementBar = -1;
    private int lastBearDisplacementBar = -1;

    // Confirmation tracking
    private IFVGZone pendingZone = null;
    private int confirmationWaitBar = -1;

    // NY timezone
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Sessions Tab =====
        var tab = sd.addTab("Sessions");
        var grp = tab.addGroup("NY AM Session");
        grp.addRow(new BooleanDescriptor(NY_AM_ENABLED, "Enable NY AM", true));
        grp.addRow(new IntegerDescriptor(NY_AM_START, "Start Time (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(NY_AM_END, "End Time (HHMM)", 1130, 0, 2359, 1));

        grp = tab.addGroup("NY PM Session");
        grp.addRow(new BooleanDescriptor(NY_PM_ENABLED, "Enable NY PM", false));
        grp.addRow(new IntegerDescriptor(NY_PM_START, "Start Time (HHMM)", 1330, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(NY_PM_END, "End Time (HHMM)", 1530, 0, 2359, 1));

        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_PER_WINDOW, "Max Trades Per Window", 2, 1, 10, 1));
        grp.addRow(new IntegerDescriptor(COOLDOWN_MINUTES, "Cooldown After Trade (minutes)", 10, 0, 60, 1));

        // ===== Bias Tab =====
        tab = sd.addTab("Bias Model");
        grp = tab.addGroup("Moving Averages");
        grp.addRow(new BooleanDescriptor(BIAS_ENABLED, "Enable Bias Filter", true));
        grp.addRow(new IntegerDescriptor(FAST_MA_PERIOD, "Fast EMA Period", 9, 2, 50, 1));
        grp.addRow(new IntegerDescriptor(SLOW_MA_PERIOD, "Slow EMA Period", 21, 5, 100, 1));
        grp.addRow(new IntegerDescriptor(MA_SLOPE_BARS, "Slope Lookback Bars", 3, 1, 10, 1));

        grp = tab.addGroup("Structure");
        grp.addRow(new BooleanDescriptor(STRUCTURE_ENABLED, "Enable Structure Filter", true));
        grp.addRow(new IntegerDescriptor(PIVOT_LEFT, "Pivot Left Bars", 2, 1, 10, 1));
        grp.addRow(new IntegerDescriptor(PIVOT_RIGHT, "Pivot Right Bars", 2, 1, 10, 1));

        // ===== Filters Tab =====
        tab = sd.addTab("Filters");
        grp = tab.addGroup("Displacement Filter");
        grp.addRow(new BooleanDescriptor(DISPLACEMENT_ENABLED, "Require Displacement", true));
        grp.addRow(new IntegerDescriptor(DISPLACEMENT_LOOKBACK, "Lookback Bars", 20, 5, 50, 1));
        grp.addRow(new DoubleDescriptor(DISPLACEMENT_MULTIPLE, "Min Impulse Multiple of Avg Range", 1.6, 1.0, 5.0, 0.1));
        grp.addRow(new IntegerDescriptor(MIN_IMPULSE_BARS, "Min Consecutive Impulse Bars", 2, 1, 5, 1));

        grp = tab.addGroup("Chop Filter");
        grp.addRow(new BooleanDescriptor(CHOP_ENABLED, "Avoid Chop", true));
        grp.addRow(new IntegerDescriptor(CHOP_LOOKBACK, "Lookback Bars", 15, 5, 30, 1));
        grp.addRow(new DoubleDescriptor(MAX_OVERLAP_RATIO, "Max Overlap Ratio", 0.55, 0.2, 0.9, 0.05));

        // ===== IFVG Tab =====
        tab = sd.addTab("IFVG");
        grp = tab.addGroup("Zone Detection");
        grp.addRow(new DoubleDescriptor(MIN_GAP_POINTS, "Min Gap Size (points)", 4.0, 1.0, 50.0, 0.5));
        grp.addRow(new IntegerDescriptor(ZONE_MAX_AGE, "Max Zone Age (bars)", 30, 5, 100, 1));
        grp.addRow(new IntegerDescriptor(MAX_ACTIVE_ZONES, "Max Active Zones", 6, 1, 20, 1));

        grp = tab.addGroup("Zone Entry");
        grp.addRow(new IntegerDescriptor(ZONE_ENTRY_LEVEL, "Entry Level (0=Mid, 1=Edge)", ZONE_ENTRY_MID, 0, 1, 1));

        // ===== Entry Tab =====
        tab = sd.addTab("Entry");
        grp = tab.addGroup("Direction");
        grp.addRow(new BooleanDescriptor(ENABLE_LONG, "Enable Long", true));
        grp.addRow(new BooleanDescriptor(ENABLE_SHORT, "Enable Short", true));

        grp = tab.addGroup("Confirmation");
        grp.addRow(new BooleanDescriptor(REQUIRE_REJECTION, "Require Rejection Candle", true));
        grp.addRow(new IntegerDescriptor(MAX_WAIT_CONFIRMATION, "Max Wait Bars for Confirmation", 3, 1, 10, 1));
        grp.addRow(new DoubleDescriptor(ENTRY_BUFFER_POINTS, "Entry Buffer (points)", 1.0, 0.0, 10.0, 0.25));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Sizing");
        grp.addRow(new IntegerDescriptor(SIZING_MODE, "Mode (0=Fixed, 1=Risk-Based)", SIZING_FIXED, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(FIXED_CONTRACTS, "Fixed Contracts", 1, 1, 100, 1));
        grp.addRow(new DoubleDescriptor(ACCOUNT_SIZE, "Account Size", 50000.0, 1000.0, 10000000.0, 1000.0));
        grp.addRow(new DoubleDescriptor(RISK_PERCENT, "Risk Per Trade %", 0.5, 0.1, 5.0, 0.1));
        grp.addRow(new IntegerDescriptor(MAX_CONTRACTS, "Max Contracts", 5, 1, 100, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new DoubleDescriptor(STOP_BUFFER_POINTS, "Stop Buffer (points)", 2.0, 0.0, 20.0, 0.25));
        grp.addRow(new DoubleDescriptor(MAX_STOP_POINTS, "Max Stop Distance (points)", 40.0, 5.0, 200.0, 1.0));

        grp = tab.addGroup("Daily Limits");
        grp.addRow(new BooleanDescriptor(DAILY_LIMIT_ENABLED, "Enable Daily Loss Limit", true));
        grp.addRow(new DoubleDescriptor(MAX_DAILY_LOSS_R, "Max Daily Loss (R)", 2.0, 0.5, 10.0, 0.5));

        // ===== Exits Tab =====
        tab = sd.addTab("Exits");
        grp = tab.addGroup("Fixed R Target");
        grp.addRow(new DoubleDescriptor(TARGET_R, "Target R", 2.0, 0.5, 10.0, 0.5));

        grp = tab.addGroup("Partial Exits");
        grp.addRow(new BooleanDescriptor(PARTIAL_ENABLED, "Enable Partial", true));
        grp.addRow(new DoubleDescriptor(PARTIAL_R, "Partial at R", 1.0, 0.5, 5.0, 0.25));
        grp.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial %", 50, 1, 99, 1));

        grp = tab.addGroup("Break-Even Stop");
        grp.addRow(new BooleanDescriptor(BE_ENABLED, "Move to BE", true));
        grp.addRow(new DoubleDescriptor(BE_AT_R, "Move at R", 1.0, 0.5, 5.0, 0.25));
        grp.addRow(new DoubleDescriptor(BE_OFFSET_POINTS, "BE Offset (points)", 0.5, 0.0, 10.0, 0.25));

        grp = tab.addGroup("Time Stop");
        grp.addRow(new BooleanDescriptor(TIME_STOP_ENABLED, "Enable Time Stop", true));
        grp.addRow(new IntegerDescriptor(MAX_BARS_IN_TRADE, "Max Bars in Trade", 25, 5, 100, 1));
        grp.addRow(new BooleanDescriptor(PROGRESS_CHECK_ENABLED, "Exit if Not Progressing", true));
        grp.addRow(new IntegerDescriptor(NO_PROGRESS_BARS, "No Progress Bars", 10, 3, 30, 1));

        grp = tab.addGroup("Forced Flat");
        grp.addRow(new BooleanDescriptor(FORCED_FLAT_ENABLED, "Force Flat at Time", true));
        grp.addRow(new IntegerDescriptor(FORCED_FLAT_TIME, "Flat Time (HHMM)", 1555, 0, 2359, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Moving Averages");
        grp.addRow(new PathDescriptor(FAST_MA_PATH, "Fast EMA",
            defaults.getBlue(), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(SLOW_MA_PATH, "Slow EMA",
            defaults.getOrange(), 1.5f, null, true, true, true));

        grp = tab.addGroup("Swing Points");
        grp.addRow(new PathDescriptor(SWING_HIGH_PATH, "Swing High",
            defaults.getRed(), 1.0f, new float[]{4, 4}, true, true, false));
        grp.addRow(new PathDescriptor(SWING_LOW_PATH, "Swing Low",
            defaults.getGreen(), 1.0f, new float[]{4, 4}, true, true, false));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(ENABLE_LONG, ENABLE_SHORT, TARGET_R, FIXED_CONTRACTS);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(TARGET_R, FIXED_CONTRACTS);

        desc.exportValue(new ValueDescriptor(Values.FAST_MA, "Fast EMA", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.SLOW_MA, "Slow EMA", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.SWING_HIGH, "Swing High", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.SWING_LOW, "Swing Low", new String[]{}));

        desc.declarePath(Values.FAST_MA, FAST_MA_PATH);
        desc.declarePath(Values.SLOW_MA, SLOW_MA_PATH);
        desc.declarePath(Values.SWING_HIGH, SWING_HIGH_PATH);
        desc.declarePath(Values.SWING_LOW, SWING_LOW_PATH);

        desc.declareSignal(Signals.BULLISH_IFVG, "Bullish IFVG Detected");
        desc.declareSignal(Signals.BEARISH_IFVG, "Bearish IFVG Detected");
        desc.declareSignal(Signals.DISPLACEMENT_UP, "Bullish Displacement");
        desc.declareSignal(Signals.DISPLACEMENT_DOWN, "Bearish Displacement");
        desc.declareSignal(Signals.ENTRY_LONG, "Long Entry");
        desc.declareSignal(Signals.ENTRY_SHORT, "Short Entry");

        desc.setRangeKeys(Values.FAST_MA, Values.SLOW_MA);
    }

    @Override
    public int getMinBars() {
        return 50;
    }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();
        double pointValue = instr.getPointValue();

        if (index < 30) return;

        // Get bar data
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        double open = series.getOpen(index);

        // Daily reset
        if (barDay != lastResetDay) {
            if (!Double.isNaN(todayHigh) && !Double.isNaN(todayLow)) {
                pdh = todayHigh;
                pdl = todayLow;
            }
            todayHigh = Double.NaN;
            todayLow = Double.NaN;
            sessionHigh = Double.NaN;
            sessionLow = Double.NaN;
            resetDailyState();
            lastResetDay = barDay;
        }

        // Track today's high/low
        if (Double.isNaN(todayHigh) || high > todayHigh) todayHigh = high;
        if (Double.isNaN(todayLow) || low < todayLow) todayLow = low;

        // Track session high/low
        int window = getCurrentWindow(barTimeInt);
        if (window != currentWindow) {
            sessionHigh = Double.NaN;
            sessionLow = Double.NaN;
            tradesThisWindow = 0;
            currentWindow = window;
        }
        if (window > 0) {
            if (Double.isNaN(sessionHigh) || high > sessionHigh) sessionHigh = high;
            if (Double.isNaN(sessionLow) || low < sessionLow) sessionLow = low;
        }

        // Calculate EMAs
        int fastPeriod = getSettings().getInteger(FAST_MA_PERIOD, 9);
        int slowPeriod = getSettings().getInteger(SLOW_MA_PERIOD, 21);
        Double fastMA = series.ema(index, fastPeriod, Enums.BarInput.CLOSE);
        Double slowMA = series.ema(index, slowPeriod, Enums.BarInput.CLOSE);

        if (fastMA != null) series.setDouble(index, Values.FAST_MA, fastMA);
        if (slowMA != null) series.setDouble(index, Values.SLOW_MA, slowMA);

        // Update swings
        int pivotLeft = getSettings().getInteger(PIVOT_LEFT, 2);
        int pivotRight = getSettings().getInteger(PIVOT_RIGHT, 2);
        updateSwingPoints(series, index, pivotLeft, pivotRight);

        if (!Double.isNaN(lastSwingHigh)) series.setDouble(index, Values.SWING_HIGH, lastSwingHigh);
        if (!Double.isNaN(lastSwingLow)) series.setDouble(index, Values.SWING_LOW, lastSwingLow);

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;

        // ===== Update Bias =====
        updateBias(series, index, fastMA, slowMA, close);

        // ===== Check Displacement =====
        checkDisplacement(ctx, series, index, barTime);

        // ===== Detect FVGs and IFVGs =====
        detectIFVGZones(ctx, series, index, tickSize, barTime);

        // ===== Invalidate Old Zones =====
        invalidateOldZones(series, index);

        // ===== Check Trade Window =====
        boolean inTradeWindow = window > 0;
        boolean pastCooldown = barTime - lastTradeTime >= getSettings().getInteger(COOLDOWN_MINUTES, 10) * 60000L;
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_WINDOW, 2);
        boolean underTradeLimit = tradesThisWindow < maxTrades;

        // Check forced flat time
        boolean forcedFlatEnabled = getSettings().getBoolean(FORCED_FLAT_ENABLED, true);
        int forcedFlatTime = getSettings().getInteger(FORCED_FLAT_TIME, 1555);
        boolean pastFlatTime = forcedFlatEnabled && barTimeInt >= forcedFlatTime;

        // Check daily limit
        boolean dailyOk = !dailyLimitHit;

        // Check chop
        boolean chopOk = !getSettings().getBoolean(CHOP_ENABLED, true) || !isChoppy(series, index);

        // Base can trade
        boolean canTrade = inTradeWindow && pastCooldown && underTradeLimit && !pastFlatTime && dailyOk && chopOk && !inPosition;

        // ===== Check for Entry =====
        if (canTrade) {
            checkEntrySignals(ctx, series, index, tickSize, close, barTime);
        }

        // ===== Handle Pending Confirmation =====
        if (pendingZone != null && !inPosition) {
            int maxWait = getSettings().getInteger(MAX_WAIT_CONFIRMATION, 3);
            if (index - confirmationWaitBar > maxWait) {
                debug("Confirmation timeout for pending zone");
                pendingZone = null;
                confirmationWaitBar = -1;
            } else {
                checkConfirmation(ctx, series, index, close, open, barTime);
            }
        }

        series.setComplete(index);
    }

    // ==================== Bias Model ====================

    private void updateBias(DataSeries series, int index, Double fastMA, Double slowMA, double close)
    {
        if (!getSettings().getBoolean(BIAS_ENABLED, true)) {
            currentBias = BIAS_NEUTRAL;
            return;
        }

        // MA Bias
        maBias = BIAS_NEUTRAL;
        if (fastMA != null && slowMA != null) {
            int slopeBars = getSettings().getInteger(MA_SLOPE_BARS, 3);
            Double prevSlowMA = series.ema(index - slopeBars, getSettings().getInteger(SLOW_MA_PERIOD, 21), Enums.BarInput.CLOSE);

            if (prevSlowMA != null) {
                double slopeSlowMA = slowMA - prevSlowMA;
                if (close > fastMA && fastMA > slowMA && slopeSlowMA > 0) {
                    maBias = BIAS_BULLISH;
                } else if (close < fastMA && fastMA < slowMA && slopeSlowMA < 0) {
                    maBias = BIAS_BEARISH;
                }
            }
        }

        // Structure Bias
        structureBias = BIAS_NEUTRAL;
        if (getSettings().getBoolean(STRUCTURE_ENABLED, true)) {
            // Bullish: last swing high broken, higher lows
            // Bearish: last swing low broken, lower highs
            if (!Double.isNaN(lastSwingHigh) && !Double.isNaN(prevSwingHigh) &&
                !Double.isNaN(lastSwingLow) && !Double.isNaN(prevSwingLow))
            {
                boolean higherLows = lastSwingLow > prevSwingLow;
                boolean lowerHighs = lastSwingHigh < prevSwingHigh;

                if (higherLows && close > lastSwingHigh) {
                    structureBias = BIAS_BULLISH;
                } else if (lowerHighs && close < lastSwingLow) {
                    structureBias = BIAS_BEARISH;
                }
            }
        }

        // Combined bias: require both MA and structure to agree
        if (maBias == structureBias) {
            currentBias = maBias;
        } else if (maBias != BIAS_NEUTRAL && structureBias == BIAS_NEUTRAL) {
            currentBias = maBias;
        } else if (structureBias != BIAS_NEUTRAL && maBias == BIAS_NEUTRAL) {
            currentBias = structureBias;
        } else {
            currentBias = BIAS_NEUTRAL;
        }
    }

    // ==================== Displacement Detection ====================

    private void checkDisplacement(DataContext ctx, DataSeries series, int index, long barTime)
    {
        if (!getSettings().getBoolean(DISPLACEMENT_ENABLED, true)) {
            recentBullDisplacement = true;
            recentBearDisplacement = true;
            return;
        }

        int lookback = getSettings().getInteger(DISPLACEMENT_LOOKBACK, 20);
        double multiple = getSettings().getDouble(DISPLACEMENT_MULTIPLE, 1.6);
        int minBars = getSettings().getInteger(MIN_IMPULSE_BARS, 2);

        // Calculate average range
        double sumRange = 0;
        for (int i = index - lookback; i < index; i++) {
            if (i >= 0) {
                sumRange += series.getHigh(i) - series.getLow(i);
            }
        }
        double avgRange = sumRange / lookback;
        double threshold = avgRange * multiple;

        // Check for bullish displacement (consecutive up bars with range > threshold)
        int bullCount = 0;
        for (int i = index; i > index - 5 && i >= 0; i--) {
            double range = series.getHigh(i) - series.getLow(i);
            double body = series.getClose(i) - series.getOpen(i);
            if (range >= threshold && body > 0) {
                bullCount++;
            } else {
                break;
            }
        }
        if (bullCount >= minBars) {
            recentBullDisplacement = true;
            lastBullDisplacementBar = index;
            ctx.signal(index, Signals.DISPLACEMENT_UP, "Bullish Displacement", series.getClose(index));
            debug("Bullish displacement detected at bar " + index);
        }

        // Check for bearish displacement
        int bearCount = 0;
        for (int i = index; i > index - 5 && i >= 0; i--) {
            double range = series.getHigh(i) - series.getLow(i);
            double body = series.getClose(i) - series.getOpen(i);
            if (range >= threshold && body < 0) {
                bearCount++;
            } else {
                break;
            }
        }
        if (bearCount >= minBars) {
            recentBearDisplacement = true;
            lastBearDisplacementBar = index;
            ctx.signal(index, Signals.DISPLACEMENT_DOWN, "Bearish Displacement", series.getClose(index));
            debug("Bearish displacement detected at bar " + index);
        }

        // Expire displacement after some bars
        if (index - lastBullDisplacementBar > 20) recentBullDisplacement = false;
        if (index - lastBearDisplacementBar > 20) recentBearDisplacement = false;
    }

    // ==================== IFVG Detection ====================

    private void detectIFVGZones(DataContext ctx, DataSeries series, int index, double tickSize, long barTime)
    {
        if (index < 2) return;

        double minGapPoints = getSettings().getDouble(MIN_GAP_POINTS, 4.0);
        int maxZones = getSettings().getInteger(MAX_ACTIVE_ZONES, 6);

        // Check for FVG (3-candle imbalance)
        double bar0High = series.getHigh(index - 2);
        double bar0Low = series.getLow(index - 2);
        double bar2High = series.getHigh(index);
        double bar2Low = series.getLow(index);

        // Bullish FVG: bar[0].high < bar[2].low (gap up)
        if (bar2Low > bar0High && (bar2Low - bar0High) >= minGapPoints) {
            if (recentBullDisplacement) {
                IFVGZone zone = new IFVGZone(bar2Low, bar0High, index, true);
                addZone(zone, maxZones);
                ctx.signal(index, Signals.BULLISH_IFVG,
                    String.format("Bullish IFVG: %.2f - %.2f", bar0High, bar2Low), bar2Low);
                debug("Bullish FVG detected: " + bar0High + " - " + bar2Low);
            }
        }

        // Bearish FVG: bar[0].low > bar[2].high (gap down)
        if (bar0Low > bar2High && (bar0Low - bar2High) >= minGapPoints) {
            if (recentBearDisplacement) {
                IFVGZone zone = new IFVGZone(bar0Low, bar2High, index, false);
                addZone(zone, maxZones);
                ctx.signal(index, Signals.BEARISH_IFVG,
                    String.format("Bearish IFVG: %.2f - %.2f", bar2High, bar0Low), bar2High);
                debug("Bearish FVG detected: " + bar2High + " - " + bar0Low);
            }
        }

        // Check for IFVG inversion (price trades through zone mid)
        double close = series.getClose(index);
        for (IFVGZone zone : activeZones) {
            if (!zone.isValid || zone.isInverted) continue;

            double mid = zone.getMid();
            if (zone.isBullish) {
                // Bearish FVG that price trades back above mid = bullish IFVG
                if (close > mid && !zone.isInverted) {
                    zone.isInverted = true;
                    zone.isBullish = true; // Now it's a bullish continuation zone
                    debug("Bearish FVG inverted to bullish IFVG at " + close);
                }
            } else {
                // Bullish FVG that price trades back below mid = bearish IFVG
                if (close < mid && !zone.isInverted) {
                    zone.isInverted = true;
                    zone.isBullish = false; // Now it's a bearish continuation zone
                    debug("Bullish FVG inverted to bearish IFVG at " + close);
                }
            }
        }
    }

    private void addZone(IFVGZone zone, int maxZones)
    {
        activeZones.add(zone);
        while (activeZones.size() > maxZones) {
            activeZones.remove(0);
        }
    }

    private void invalidateOldZones(DataSeries series, int index)
    {
        int maxAge = getSettings().getInteger(ZONE_MAX_AGE, 30);
        double close = series.getClose(index);

        for (IFVGZone zone : activeZones) {
            if (!zone.isValid) continue;

            // Age check
            if (index - zone.barIndex > maxAge) {
                zone.isValid = false;
                continue;
            }

            // Full fill invalidation
            if (zone.isBullish && close < zone.bottom) {
                zone.isValid = false;
            } else if (!zone.isBullish && close > zone.top) {
                zone.isValid = false;
            }
        }

        // Remove invalid zones
        activeZones.removeIf(z -> !z.isValid);
    }

    // ==================== Entry Logic ====================

    private void checkEntrySignals(DataContext ctx, DataSeries series, int index, double tickSize, double close, long barTime)
    {
        boolean enableLong = getSettings().getBoolean(ENABLE_LONG, true);
        boolean enableShort = getSettings().getBoolean(ENABLE_SHORT, true);
        boolean requireRejection = getSettings().getBoolean(REQUIRE_REJECTION, true);

        // Look for price retracing into an IFVG zone
        for (IFVGZone zone : activeZones) {
            if (!zone.isValid) continue;

            // Check if price is in zone
            boolean priceInZone = close >= zone.bottom && close <= zone.top;
            if (!priceInZone) continue;

            // Check direction and bias
            if (zone.isBullish && enableLong && currentBias >= BIAS_NEUTRAL) {
                if (requireRejection) {
                    pendingZone = zone;
                    confirmationWaitBar = index;
                    debug("Bullish IFVG zone touched, waiting for rejection candle");
                } else {
                    triggerLongEntry(ctx, series, index, zone, barTime);
                }
            } else if (!zone.isBullish && enableShort && currentBias <= BIAS_NEUTRAL) {
                if (requireRejection) {
                    pendingZone = zone;
                    confirmationWaitBar = index;
                    debug("Bearish IFVG zone touched, waiting for rejection candle");
                } else {
                    triggerShortEntry(ctx, series, index, zone, barTime);
                }
            }
        }
    }

    private void checkConfirmation(DataContext ctx, DataSeries series, int index, double close, double open, long barTime)
    {
        if (pendingZone == null) return;

        double mid = pendingZone.getMid();

        if (pendingZone.isBullish) {
            // Bullish rejection: close > open AND close > zone mid
            if (close > open && close > mid) {
                triggerLongEntry(ctx, series, index, pendingZone, barTime);
                pendingZone = null;
                confirmationWaitBar = -1;
            }
        } else {
            // Bearish rejection: close < open AND close < zone mid
            if (close < open && close < mid) {
                triggerShortEntry(ctx, series, index, pendingZone, barTime);
                pendingZone = null;
                confirmationWaitBar = -1;
            }
        }
    }

    private void triggerLongEntry(DataContext ctx, DataSeries series, int index, IFVGZone zone, long barTime)
    {
        // Check bias
        if (getSettings().getBoolean(BIAS_ENABLED, true) && currentBias == BIAS_BEARISH) {
            debug("Long entry blocked - bearish bias");
            return;
        }

        double close = series.getClose(index);
        double low = series.getLow(index);
        ctx.signal(index, Signals.ENTRY_LONG, "IFVG Long Entry", close);

        var marker = getSettings().getMarker(Inputs.UP_MARKER);
        if (marker.isEnabled()) {
            addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, "IFVG Long"));
        }

        zone.isValid = false; // Zone used
        debug("IFVG Long entry triggered at " + close);
    }

    private void triggerShortEntry(DataContext ctx, DataSeries series, int index, IFVGZone zone, long barTime)
    {
        // Check bias
        if (getSettings().getBoolean(BIAS_ENABLED, true) && currentBias == BIAS_BULLISH) {
            debug("Short entry blocked - bullish bias");
            return;
        }

        double close = series.getClose(index);
        double high = series.getHigh(index);
        ctx.signal(index, Signals.ENTRY_SHORT, "IFVG Short Entry", close);

        var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
        if (marker.isEnabled()) {
            addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, "IFVG Short"));
        }

        zone.isValid = false; // Zone used
        debug("IFVG Short entry triggered at " + close);
    }

    // ==================== Helper Methods ====================

    private void updateSwingPoints(DataSeries series, int index, int leftBars, int rightBars)
    {
        int pivotBar = index - rightBars;
        if (pivotBar < leftBars) return;

        // Check for swing high
        double high = series.getHigh(pivotBar);
        boolean isSwingHigh = true;
        for (int i = 1; i <= leftBars && isSwingHigh; i++) {
            if (pivotBar - i >= 0 && series.getHigh(pivotBar - i) >= high) isSwingHigh = false;
        }
        for (int i = 1; i <= rightBars && isSwingHigh; i++) {
            if (pivotBar + i <= index && series.getHigh(pivotBar + i) >= high) isSwingHigh = false;
        }
        if (isSwingHigh) {
            prevSwingHigh = lastSwingHigh;
            lastSwingHigh = high;
            lastSwingHighBar = pivotBar;
        }

        // Check for swing low
        double low = series.getLow(pivotBar);
        boolean isSwingLow = true;
        for (int i = 1; i <= leftBars && isSwingLow; i++) {
            if (pivotBar - i >= 0 && series.getLow(pivotBar - i) <= low) isSwingLow = false;
        }
        for (int i = 1; i <= rightBars && isSwingLow; i++) {
            if (pivotBar + i <= index && series.getLow(pivotBar + i) <= low) isSwingLow = false;
        }
        if (isSwingLow) {
            prevSwingLow = lastSwingLow;
            lastSwingLow = low;
            lastSwingLowBar = pivotBar;
        }
    }

    private boolean isChoppy(DataSeries series, int index)
    {
        int lookback = getSettings().getInteger(CHOP_LOOKBACK, 15);
        double maxOverlap = getSettings().getDouble(MAX_OVERLAP_RATIO, 0.55);

        if (index < lookback) return false;

        // Calculate overlap ratio: sum of overlapping portions / total range
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

        double overlapRatio = totalRange > 0 ? totalOverlap / totalRange : 0;
        return overlapRatio > maxOverlap;
    }

    private int getCurrentWindow(int timeInt)
    {
        boolean nyAmEnabled = getSettings().getBoolean(NY_AM_ENABLED, true);
        int nyAmStart = getSettings().getInteger(NY_AM_START, 930);
        int nyAmEnd = getSettings().getInteger(NY_AM_END, 1130);

        boolean nyPmEnabled = getSettings().getBoolean(NY_PM_ENABLED, false);
        int nyPmStart = getSettings().getInteger(NY_PM_START, 1330);
        int nyPmEnd = getSettings().getInteger(NY_PM_END, 1530);

        if (nyAmEnabled && timeInt >= nyAmStart && timeInt < nyAmEnd) return 1;
        if (nyPmEnabled && timeInt >= nyPmStart && timeInt < nyPmEnd) return 2;
        return 0;
    }

    private void resetDailyState()
    {
        activeZones.clear();
        tradesThisWindow = 0;
        currentWindow = 0;
        dailyRPL = 0;
        dailyLimitHit = false;
        flatProcessed = false;
        recentBullDisplacement = false;
        recentBearDisplacement = false;
        lastBullDisplacementBar = -1;
        lastBearDisplacementBar = -1;
        pendingZone = null;
        confirmationWaitBar = -1;
    }

    private void resetTradeState()
    {
        inPosition = false;
        entryPrice = 0;
        stopPrice = 0;
        targetPrice = 0;
        riskPoints = 0;
        entryBar = -1;
        partialTaken = false;
        movedToBE = false;
        bestProgress = 0;
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

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("Lanto IFVG Continuation v1.0 activated");
        debug("Long enabled: " + getSettings().getBoolean(ENABLE_LONG, true));
        debug("Short enabled: " + getSettings().getBoolean(ENABLE_SHORT, true));
        debug("Target R: " + getSettings().getDouble(TARGET_R, 2.0));
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position");
        }
        resetDailyState();
        resetTradeState();
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        if (signal != Signals.ENTRY_LONG && signal != Signals.ENTRY_SHORT) return;

        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        double tickSize = instr.getTickSize();

        // Already in position
        if (position != 0 || inPosition) {
            debug("Already in position, ignoring signal");
            return;
        }

        // Check daily limit
        if (dailyLimitHit) {
            debug("Daily limit hit, ignoring signal");
            return;
        }

        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        // Check forced flat time
        boolean forcedFlatEnabled = getSettings().getBoolean(FORCED_FLAT_ENABLED, true);
        int forcedFlatTime = getSettings().getInteger(FORCED_FLAT_TIME, 1555);
        if (forcedFlatEnabled && barTimeInt >= forcedFlatTime) {
            debug("Past forced flat time, ignoring signal");
            return;
        }

        // Calculate position size
        int qty = calculatePositionSize(ctx, instr);
        if (qty <= 0) {
            debug("Invalid position size, skipping trade");
            return;
        }

        double stopBuffer = getSettings().getDouble(STOP_BUFFER_POINTS, 2.0);
        double maxStop = getSettings().getDouble(MAX_STOP_POINTS, 40.0);
        double targetR = getSettings().getDouble(TARGET_R, 2.0);

        boolean isLong = (signal == Signals.ENTRY_LONG);

        if (isLong) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();
            isLongPosition = true;

            // Calculate stop: zone low - buffer, or last swing low - buffer
            double zoneStop = Double.NaN;
            for (IFVGZone zone : activeZones) {
                if (zone.isBullish && !Double.isNaN(zone.bottom)) {
                    zoneStop = zone.bottom - stopBuffer;
                    break;
                }
            }
            double swingStop = !Double.isNaN(lastSwingLow) ? lastSwingLow - stopBuffer : entryPrice - maxStop;
            stopPrice = !Double.isNaN(zoneStop) ? Math.min(zoneStop, swingStop) : swingStop;

            // Enforce max stop
            if (entryPrice - stopPrice > maxStop) {
                debug("Stop exceeds max, trade invalidated");
                ctx.closeAtMarket();
                return;
            }

            stopPrice = instr.round(stopPrice);
            riskPoints = entryPrice - stopPrice;
            targetPrice = instr.round(entryPrice + (riskPoints * targetR));

            debug(String.format("LONG: qty=%d, entry=%.2f, stop=%.2f, target=%.2f, risk=%.2f pts",
                qty, entryPrice, stopPrice, targetPrice, riskPoints));

        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();
            isLongPosition = false;

            // Calculate stop: zone high + buffer, or last swing high + buffer
            double zoneStop = Double.NaN;
            for (IFVGZone zone : activeZones) {
                if (!zone.isBullish && !Double.isNaN(zone.top)) {
                    zoneStop = zone.top + stopBuffer;
                    break;
                }
            }
            double swingStop = !Double.isNaN(lastSwingHigh) ? lastSwingHigh + stopBuffer : entryPrice + maxStop;
            stopPrice = !Double.isNaN(zoneStop) ? Math.max(zoneStop, swingStop) : swingStop;

            // Enforce max stop
            if (stopPrice - entryPrice > maxStop) {
                debug("Stop exceeds max, trade invalidated");
                ctx.closeAtMarket();
                return;
            }

            stopPrice = instr.round(stopPrice);
            riskPoints = stopPrice - entryPrice;
            targetPrice = instr.round(entryPrice - (riskPoints * targetR));

            debug(String.format("SHORT: qty=%d, entry=%.2f, stop=%.2f, target=%.2f, risk=%.2f pts",
                qty, entryPrice, stopPrice, targetPrice, riskPoints));
        }

        inPosition = true;
        entryBar = series.size() - 1;
        partialTaken = false;
        movedToBE = false;
        bestProgress = 0;
        tradesThisWindow++;
        lastTradeTime = barTime;
    }

    private int calculatePositionSize(OrderContext ctx, Instrument instr)
    {
        int sizingMode = getSettings().getInteger(SIZING_MODE, SIZING_FIXED);
        int fixedQty = getSettings().getInteger(FIXED_CONTRACTS, 1);

        if (sizingMode == SIZING_FIXED) {
            return fixedQty;
        }

        // Risk-based sizing
        double accountSize = getSettings().getDouble(ACCOUNT_SIZE, 50000.0);
        double riskPct = getSettings().getDouble(RISK_PERCENT, 0.5) / 100.0;
        int maxContracts = getSettings().getInteger(MAX_CONTRACTS, 5);
        double maxStopPoints = getSettings().getDouble(MAX_STOP_POINTS, 40.0);

        double riskDollars = accountSize * riskPct;
        double pointValue = instr.getPointValue();
        double riskPerContract = maxStopPoints * pointValue;

        int qty = (int) Math.floor(riskDollars / riskPerContract);
        qty = Math.max(1, Math.min(qty, maxContracts));

        return qty;
    }

    @Override
    public void onBarClose(OrderContext ctx) {
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        var instr = ctx.getInstrument();

        // ===== Forced Flat =====
        boolean forcedFlatEnabled = getSettings().getBoolean(FORCED_FLAT_ENABLED, true);
        int forcedFlatTime = getSettings().getInteger(FORCED_FLAT_TIME, 1555);

        if (forcedFlatEnabled && barTimeInt >= forcedFlatTime && !flatProcessed) {
            int position = ctx.getPosition();
            if (position != 0) {
                ctx.closeAtMarket();
                debug("Forced flat at " + barTimeInt);
                updateDailyPL(ctx, series);
                resetTradeState();
            }
            flatProcessed = true;
            return;
        }

        // ===== No position check =====
        int position = ctx.getPosition();
        if (position == 0 || !inPosition) return;

        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);

        // ===== Time Stop =====
        boolean timeStopEnabled = getSettings().getBoolean(TIME_STOP_ENABLED, true);
        int maxBars = getSettings().getInteger(MAX_BARS_IN_TRADE, 25);

        if (timeStopEnabled && index - entryBar >= maxBars) {
            ctx.closeAtMarket();
            debug("Time stop - max bars reached");
            updateDailyPL(ctx, series);
            resetTradeState();
            return;
        }

        // ===== Progress Check =====
        boolean progressEnabled = getSettings().getBoolean(PROGRESS_CHECK_ENABLED, true);
        int noProgressBars = getSettings().getInteger(NO_PROGRESS_BARS, 10);

        if (progressEnabled && index - entryBar >= noProgressBars) {
            double currentProgress = isLongPosition ?
                (close - entryPrice) / riskPoints :
                (entryPrice - close) / riskPoints;

            if (currentProgress > bestProgress) {
                bestProgress = currentProgress;
            }

            // If hasn't reached 0.5R after noProgressBars, exit
            if (bestProgress < 0.5) {
                ctx.closeAtMarket();
                debug("No progress exit - hasn't reached 0.5R");
                updateDailyPL(ctx, series);
                resetTradeState();
                return;
            }
        }

        // ===== Stop Loss =====
        if (isLongPosition) {
            if (low <= stopPrice) {
                ctx.closeAtMarket();
                debug("LONG stopped out at " + low);
                updateDailyPL(ctx, series);
                resetTradeState();
                return;
            }
        } else {
            if (high >= stopPrice) {
                ctx.closeAtMarket();
                debug("SHORT stopped out at " + high);
                updateDailyPL(ctx, series);
                resetTradeState();
                return;
            }
        }

        // ===== Partial and BE =====
        boolean partialEnabled = getSettings().getBoolean(PARTIAL_ENABLED, true);
        double partialR = getSettings().getDouble(PARTIAL_R, 1.0);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);
        boolean beEnabled = getSettings().getBoolean(BE_ENABLED, true);
        double beAtR = getSettings().getDouble(BE_AT_R, 1.0);
        double beOffset = getSettings().getDouble(BE_OFFSET_POINTS, 0.5);

        double currentR = isLongPosition ?
            (close - entryPrice) / riskPoints :
            (entryPrice - close) / riskPoints;

        // Partial exit
        if (partialEnabled && !partialTaken && currentR >= partialR) {
            int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
            if (partialQty > 0 && partialQty < Math.abs(position)) {
                if (isLongPosition) {
                    ctx.sell(partialQty);
                } else {
                    ctx.buy(partialQty);
                }
                partialTaken = true;
                debug("Partial exit: " + partialQty + " at " + partialR + "R");
            }
        }

        // Move to BE
        if (beEnabled && !movedToBE && currentR >= beAtR) {
            if (isLongPosition) {
                stopPrice = entryPrice + beOffset;
            } else {
                stopPrice = entryPrice - beOffset;
            }
            stopPrice = instr.round(stopPrice);
            movedToBE = true;
            debug("Stop moved to BE: " + stopPrice);
        }

        // ===== Target =====
        if (isLongPosition) {
            if (high >= targetPrice) {
                ctx.closeAtMarket();
                debug("LONG target hit at " + high);
                updateDailyPL(ctx, series);
                resetTradeState();
            }
        } else {
            if (low <= targetPrice) {
                ctx.closeAtMarket();
                debug("SHORT target hit at " + low);
                updateDailyPL(ctx, series);
                resetTradeState();
            }
        }
    }

    private void updateDailyPL(OrderContext ctx, DataSeries series)
    {
        // Estimate R-multiple of trade result
        double close = series.getClose(series.size() - 1);
        double result = isLongPosition ?
            (close - entryPrice) / riskPoints :
            (entryPrice - close) / riskPoints;

        dailyRPL += result;

        double maxLossR = getSettings().getDouble(MAX_DAILY_LOSS_R, 2.0);
        if (getSettings().getBoolean(DAILY_LIMIT_ENABLED, true) && dailyRPL <= -maxLossR) {
            dailyLimitHit = true;
            debug("Daily loss limit hit: " + dailyRPL + "R");
        }
    }

    @Override
    public void clearState() {
        super.clearState();
        resetDailyState();
        resetTradeState();
        lastResetDay = -1;
        pdh = Double.NaN;
        pdl = Double.NaN;
        todayHigh = Double.NaN;
        todayLow = Double.NaN;
        lastSwingHigh = Double.NaN;
        lastSwingLow = Double.NaN;
        prevSwingHigh = Double.NaN;
        prevSwingLow = Double.NaN;
    }
}
