package com.mw.studies;

import java.awt.Color;
import java.util.*;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * MTF MA Model Strategy
 *
 * Multi-timeframe moving average trend filter with pivot-confirmed entries
 * and automatic order block visualization. AUTO-TRADING ENABLED.
 *
 * v1.1 Changes:
 * - HTF filter now optional (toggle)
 * - Reduced default HTF periods (10/20/50)
 * - Debug logging shows which conditions fail
 * - Price above/below MAs now optional
 * - Pivot confirmation can be disabled
 *
 * @version 1.1.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "MTF_MA_MODEL_STRATEGY",
    rb = "com.mw.studies.nls.strings",
    name = "MTF MA Model Strategy",
    label = "MTF MA Strategy",
    desc = "Multi-timeframe MA strategy with pivot-confirmed entries and auto-trading",
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
public class MTFMAModelStrategy extends Study {

    // ==================== Constants ====================
    // MA Settings
    private static final String MA_TYPE = "maType";

    // Entry Stack (LTF)
    private static final String ENTRY_LEN_FAST = "entryLenFast";
    private static final String ENTRY_LEN_MID = "entryLenMid";
    private static final String ENTRY_LEN_SLOW = "entryLenSlow";

    // HTF Settings
    private static final String HTF_ENABLED = "htfEnabled";
    private static final String HTF_MODE = "htfMode";
    private static final String HTF_MANUAL = "htfManual";
    private static final String HTF_LEN_FAST = "htfLenFast";
    private static final String HTF_LEN_MID = "htfLenMid";
    private static final String HTF_LEN_SLOW = "htfLenSlow";

    // Entry Filters
    private static final String REQUIRE_PRICE_ABOVE_MAS = "requirePriceAboveMAs";
    private static final String REQUIRE_PIVOT_CONFIRM = "requirePivotConfirm";
    private static final String DEBUG_MODE = "debugMode";

    // Display
    private static final String SHOW_ENTRY_MAS = "showEntryMAs";
    private static final String SHOW_HTF_MAS = "showHTFMAs";

    // Order Blocks
    private static final String SHOW_OB_LINES = "showOBLines";
    private static final String OB_EXTEND_TYPE = "obExtendType";
    private static final String MAX_OB_LINES = "maxOBLines";

    // Trade Settings
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_PER_DAY = "maxTradesPerDay";

    // Risk Settings
    private static final String STOPLOSS_ENABLED = "stoplossEnabled";
    private static final String STOP_MODE = "stopMode";
    private static final String STOP_BUFFER = "stopBuffer";
    private static final String STOP_DISTANCE_POINTS = "stopDistancePoints";

    // Target Settings
    private static final String TP_MODE = "tpMode";
    private static final String RR_MULTIPLE = "rrMultiple";
    private static final String FIXED_TP_POINTS = "fixedTpPoints";

    // EOD Settings
    private static final String EOD_CLOSE_ENABLED = "eodCloseEnabled";
    private static final String EOD_CLOSE_TIME = "eodCloseTime";

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

    private static final int STOP_TRACKING_EXTREME = 0;
    private static final int STOP_FIXED_POINTS = 1;
    private static final int STOP_SIGNAL_BAR = 2;

    private static final int TP_RR_MULTIPLE = 0;
    private static final int TP_FIXED_POINTS = 1;

    // ==================== Values ====================
    enum Values {
        ENTRY_FAST, ENTRY_MID, ENTRY_SLOW,
        HTF_FAST, HTF_MID, HTF_SLOW,
        PIVOT_HIGH, PIVOT_LOW, STATE, STOP_LEVEL
    }

    // ==================== Signals ====================
    enum Signals {
        PENDING_LONG, PENDING_SHORT,
        CONFIRMED_LONG, CONFIRMED_SHORT
    }

    // ==================== State Constants ====================
    private static final int STATE_IDLE = 0;
    private static final int STATE_PENDING_LONG = 1;
    private static final int STATE_PENDING_SHORT = 2;

    // ==================== State Tracking ====================
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

    // Trade state
    private int tradesToday = 0;
    private int lastTradeDay = -1;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double targetPrice = 0;
    private boolean inTrade = false;
    private boolean isLongTrade = false;
    private boolean eodProcessed = false;

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {
        var sd = createSD();

        // ===== Entry Conditions Tab =====
        var tab = sd.addTab("Entry Conditions");

        var grp = tab.addGroup("Entry Stack (LTF)");
        grp.addRow(new MAMethodDescriptor(MA_TYPE, "MA Method", Enums.MAMethod.EMA));
        grp.addRow(new IntegerDescriptor(ENTRY_LEN_FAST, "Fast MA Length", 5, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_LEN_MID, "Mid MA Length", 13, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_LEN_SLOW, "Slow MA Length", 34, 1, 500, 1));

        grp = tab.addGroup("Entry Filters");
        grp.addRow(new BooleanDescriptor(REQUIRE_PRICE_ABOVE_MAS, "Require Price Above/Below MAs", false));
        grp.addRow(new BooleanDescriptor(REQUIRE_PIVOT_CONFIRM, "Require Pivot Confirmation", true));
        grp.addRow(new BooleanDescriptor(DEBUG_MODE, "Debug Mode (Log Conditions)", true));

        // ===== HTF Filter Tab =====
        tab = sd.addTab("HTF Filter");

        grp = tab.addGroup("HTF Toggle");
        grp.addRow(new BooleanDescriptor(HTF_ENABLED, "Enable HTF Filter", false));

        grp = tab.addGroup("HTF Mode");
        grp.addRow(new IntegerDescriptor(HTF_MODE, "Mode (0=Auto, 1=Manual)", 0, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(HTF_MANUAL, "Manual HTF (minutes)", 60, 1, 1440, 1));

        grp = tab.addGroup("HTF Stack (Shorter defaults)");
        grp.addRow(new IntegerDescriptor(HTF_LEN_FAST, "Fast MA Length", 10, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(HTF_LEN_MID, "Mid MA Length", 20, 1, 300, 1));
        grp.addRow(new IntegerDescriptor(HTF_LEN_SLOW, "Slow MA Length", 50, 1, 500, 1));

        // ===== Trade Settings Tab =====
        tab = sd.addTab("Trade Settings");

        grp = tab.addGroup("Position");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 1, 1, 100, 1));
        grp.addRow(new IntegerDescriptor(MAX_TRADES_PER_DAY, "Max Trades/Day", 5, 1, 20, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new BooleanDescriptor(STOPLOSS_ENABLED, "Enable Stop Loss", true));
        grp.addRow(new IntegerDescriptor(STOP_MODE, "Mode (0=Tracking, 1=Fixed, 2=SignalBar)", 1, 0, 2, 1));
        grp.addRow(new DoubleDescriptor(STOP_BUFFER, "Stop Buffer (points)", 1.0, 0.0, 50, 0.25));
        grp.addRow(new DoubleDescriptor(STOP_DISTANCE_POINTS, "Fixed Stop Distance", 10.0, 0.25, 500, 0.25));

        grp = tab.addGroup("Take Profit");
        grp.addRow(new IntegerDescriptor(TP_MODE, "Mode (0=R:R, 1=Fixed)", 0, 0, 1, 1));
        grp.addRow(new DoubleDescriptor(RR_MULTIPLE, "Risk:Reward Multiple", 2.0, 0.5, 10.0, 0.1));
        grp.addRow(new DoubleDescriptor(FIXED_TP_POINTS, "Fixed TP (points)", 20.0, 0.5, 500, 0.5));

        // ===== EOD Tab =====
        tab = sd.addTab("EOD");

        grp = tab.addGroup("End of Day");
        grp.addRow(new BooleanDescriptor(EOD_CLOSE_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_CLOSE_TIME, "EOD Time (HHMM)", 1555, 0, 2359, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");

        grp = tab.addGroup("Visibility");
        grp.addRow(new BooleanDescriptor(SHOW_ENTRY_MAS, "Show Entry MAs", true));
        grp.addRow(new BooleanDescriptor(SHOW_HTF_MAS, "Show HTF MAs", true));

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

        // ===== Markers Tab =====
        tab = sd.addTab("Markers");

        grp = tab.addGroup("Signal Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Signal",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Signal",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(ENTRY_LEN_FAST, ENTRY_LEN_MID, ENTRY_LEN_SLOW, MA_TYPE, CONTRACTS, HTF_ENABLED);

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

        desc.setRangeKeys(Values.ENTRY_FAST, Values.ENTRY_MID, Values.ENTRY_SLOW);
    }

    @Override
    public void onLoad(Defaults defaults) {
        int slow = getSettings().getInteger(ENTRY_LEN_SLOW, 34);
        setMinBars(slow + 10);
    }

    @Override
    public int getMinBars() {
        int slow = getSettings().getInteger(ENTRY_LEN_SLOW, 34);
        return slow + 10;
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        inTrade = false;
        tradesToday = 0;
        eodProcessed = false;
        debug("MTF MA Strategy activated");
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Deactivated - closed position: " + position);
        }
        resetTradeState();
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        int contracts = getSettings().getInteger(CONTRACTS, 1);
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_DAY, 5);

        if (tradesToday >= maxTrades) {
            debug("Max trades reached for today: " + tradesToday);
            return;
        }

        if (signal == Signals.CONFIRMED_LONG) {
            if (position < 0) {
                ctx.closeAtMarket();
                debug("Closed SHORT before entering LONG");
            }
            if (position <= 0) {
                ctx.buy(contracts);
                tradesToday++;
                inTrade = true;
                isLongTrade = true;
                entryPrice = instr.getLastPrice();
                setupStopAndTarget(ctx, true);
                debug(">>> LONG EXECUTED at " + entryPrice + ", contracts=" + contracts);
            }
        }
        else if (signal == Signals.CONFIRMED_SHORT) {
            if (position > 0) {
                ctx.closeAtMarket();
                debug("Closed LONG before entering SHORT");
            }
            if (position >= 0) {
                ctx.sell(contracts);
                tradesToday++;
                inTrade = true;
                isLongTrade = false;
                entryPrice = instr.getLastPrice();
                setupStopAndTarget(ctx, false);
                debug(">>> SHORT EXECUTED at " + entryPrice + ", contracts=" + contracts);
            }
        }
    }

    @Override
    public void onBarClose(OrderContext ctx) {
        var series = ctx.getDataContext().getDataSeries();
        var instr = ctx.getInstrument();
        int index = series.size() - 1;
        int position = ctx.getPosition();

        long barTime = series.getStartTime(index);
        Calendar cal = Calendar.getInstance(ctx.getDataContext().getTimeZone());
        cal.setTimeInMillis(barTime);
        int barTimeInt = cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);

        int barDay = cal.get(Calendar.DAY_OF_YEAR);
        if (barDay != lastTradeDay) {
            tradesToday = 0;
            lastTradeDay = barDay;
            eodProcessed = false;
        }

        // EOD FLATTENING
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1555);

        if (eodEnabled && barTimeInt >= eodTime && !eodProcessed) {
            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD: Flattened position at " + barTimeInt);
            }
            inTrade = false;
            eodProcessed = true;
            resetTradeState();
            return;
        }

        // STOP/TARGET MANAGEMENT
        if (position != 0 && inTrade) {
            double high = series.getHigh(index);
            double low = series.getLow(index);

            if (isLongTrade) {
                if (low <= stopPrice) {
                    ctx.closeAtMarket();
                    debug("STOP HIT (Long): stop=" + stopPrice);
                    inTrade = false;
                    resetTradeState();
                    return;
                }
                if (high >= targetPrice) {
                    ctx.closeAtMarket();
                    debug("TARGET HIT (Long): target=" + targetPrice);
                    inTrade = false;
                    resetTradeState();
                    return;
                }
            } else {
                if (high >= stopPrice) {
                    ctx.closeAtMarket();
                    debug("STOP HIT (Short): stop=" + stopPrice);
                    inTrade = false;
                    resetTradeState();
                    return;
                }
                if (low <= targetPrice) {
                    ctx.closeAtMarket();
                    debug("TARGET HIT (Short): target=" + targetPrice);
                    inTrade = false;
                    resetTradeState();
                    return;
                }
            }
        }

        if (position == 0 && inTrade) {
            inTrade = false;
            resetTradeState();
        }
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
        boolean htfEnabled = getSettings().getBoolean(HTF_ENABLED, false);
        int htfFastLen = getSettings().getInteger(HTF_LEN_FAST, 10);
        int htfMidLen = getSettings().getInteger(HTF_LEN_MID, 20);
        int htfSlowLen = getSettings().getInteger(HTF_LEN_SLOW, 50);
        boolean showEntryMAs = getSettings().getBoolean(SHOW_ENTRY_MAS, true);
        boolean showHTFMAs = getSettings().getBoolean(SHOW_HTF_MAS, true);
        boolean requirePriceAboveMAs = getSettings().getBoolean(REQUIRE_PRICE_ABOVE_MAS, false);
        boolean requirePivotConfirm = getSettings().getBoolean(REQUIRE_PIVOT_CONFIRM, true);
        boolean debugMode = getSettings().getBoolean(DEBUG_MODE, true);
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_DAY, 5);

        if (index < entrySlowLen) return;

        double close = series.getClose(index);
        double high = series.getHigh(index);
        double low = series.getLow(index);
        long barTime = series.getStartTime(index);

        int barDay = getDayOfYear(barTime, ctx.getTimeZone());
        if (barDay != lastTradeDay) {
            tradesToday = 0;
            lastTradeDay = barDay;
            eodProcessed = false;
        }

        // Calculate Entry Stack MAs
        Double entryFast = series.ma(maMethod, index, entryFastLen, Enums.BarInput.CLOSE);
        Double entryMid = series.ma(maMethod, index, entryMidLen, Enums.BarInput.CLOSE);
        Double entrySlow = series.ma(maMethod, index, entrySlowLen, Enums.BarInput.CLOSE);

        if (entryFast == null || entryMid == null || entrySlow == null) return;

        if (showEntryMAs) {
            series.setDouble(index, Values.ENTRY_FAST, entryFast);
            series.setDouble(index, Values.ENTRY_MID, entryMid);
            series.setDouble(index, Values.ENTRY_SLOW, entrySlow);
        }

        // Calculate HTF MAs (if enabled)
        Double htfFast = null, htfMid = null, htfSlow = null;
        boolean htfDataAvailable = false;

        if (htfEnabled) {
            int htfMultiplier = getHTFMultiplier(series);
            int htfFastPeriod = htfFastLen * htfMultiplier;
            int htfMidPeriod = htfMidLen * htfMultiplier;
            int htfSlowPeriod = htfSlowLen * htfMultiplier;

            if (index >= htfSlowPeriod) {
                htfFast = series.ma(maMethod, index, htfFastPeriod, Enums.BarInput.CLOSE);
                htfMid = series.ma(maMethod, index, htfMidPeriod, Enums.BarInput.CLOSE);
                htfSlow = series.ma(maMethod, index, htfSlowPeriod, Enums.BarInput.CLOSE);
                htfDataAvailable = (htfFast != null && htfMid != null && htfSlow != null);

                if (showHTFMAs && htfDataAvailable) {
                    series.setDouble(index, Values.HTF_FAST, htfFast);
                    series.setDouble(index, Values.HTF_MID, htfMid);
                    series.setDouble(index, Values.HTF_SLOW, htfSlow);
                }
            }
        }

        // Pivot Detection
        if (index >= 2) {
            double prevClose = series.getClose(index - 1);
            double prevOpen = series.getOpen(index - 1);
            double prev2Close = series.getClose(index - 2);
            double prev2Open = series.getOpen(index - 2);

            boolean prevBullish = prevClose > prevOpen;
            boolean prev2Bearish = prev2Close < prev2Open;
            boolean prevBearish = prevClose < prevOpen;
            boolean prev2Bullish = prev2Close > prev2Open;

            if (prevBullish && prev2Bearish) {
                pivotLowPrice = series.getLow(index - 1);
                pivotLowBarIndex = index - 1;
            }

            if (prevBearish && prev2Bullish) {
                pivotHighPrice = series.getHigh(index - 1);
                pivotHighBarIndex = index - 1;
            }
        }

        if (!series.isBarComplete(index)) return;

        // ===== Condition Checks with Debug Logging =====
        boolean entryStackBullish = entryFast > entryMid && entryMid > entrySlow;
        boolean entryStackBearish = entryFast < entryMid && entryMid < entrySlow;
        boolean priceAboveEntryMAs = close > entryFast && close > entryMid && close > entrySlow;
        boolean priceBelowEntryMAs = close < entryFast && close < entryMid && close < entrySlow;

        boolean htfStackBullish = true;  // Default true if HTF disabled
        boolean htfStackBearish = true;
        boolean priceAboveHTFMAs = true;
        boolean priceBelowHTFMAs = true;

        if (htfEnabled && htfDataAvailable) {
            htfStackBullish = htfFast > htfMid && htfMid > htfSlow;
            htfStackBearish = htfFast < htfMid && htfMid < htfSlow;
            priceAboveHTFMAs = close > htfFast && close > htfMid && close > htfSlow;
            priceBelowHTFMAs = close < htfFast && close < htfMid && close < htfSlow;
        }

        boolean crossAbove = crossedAbove(series, index, Values.ENTRY_FAST, Values.ENTRY_MID);
        boolean crossBelow = crossedBelow(series, index, Values.ENTRY_FAST, Values.ENTRY_MID);

        // Track extremes while pending
        if (currentState == STATE_PENDING_LONG) {
            minLowSincePending = Double.isNaN(minLowSincePending) ? low : Math.min(minLowSincePending, low);
        } else if (currentState == STATE_PENDING_SHORT) {
            maxHighSincePending = Double.isNaN(maxHighSincePending) ? high : Math.max(maxHighSincePending, high);
        }

        // ===== LONG SIGNAL LOGIC =====
        if (currentState == STATE_IDLE && crossAbove && tradesToday < maxTrades) {
            // Check conditions and log failures
            boolean canEnterLong = true;
            StringBuilder failReasons = new StringBuilder();

            if (!entryStackBullish) {
                canEnterLong = false;
                failReasons.append("EntryStack not bullish (").append(String.format("%.2f>%.2f>%.2f", entryFast, entryMid, entrySlow)).append(") ");
            }

            if (requirePriceAboveMAs && !priceAboveEntryMAs) {
                canEnterLong = false;
                failReasons.append("Price not above entry MAs ");
            }

            if (htfEnabled) {
                if (!htfDataAvailable) {
                    canEnterLong = false;
                    failReasons.append("HTF data not available ");
                } else if (!htfStackBullish) {
                    canEnterLong = false;
                    failReasons.append("HTF stack not bullish ");
                } else if (requirePriceAboveMAs && !priceAboveHTFMAs) {
                    canEnterLong = false;
                    failReasons.append("Price not above HTF MAs ");
                }
            }

            if (debugMode && crossAbove) {
                if (canEnterLong) {
                    debug(">>> CROSSOVER UP: All conditions MET for LONG");
                } else {
                    debug(">>> CROSSOVER UP: FAILED - " + failReasons.toString());
                }
            }

            if (canEnterLong) {
                if (requirePivotConfirm) {
                    currentState = STATE_PENDING_LONG;
                    signalBarIndex = index;
                    signalBarLow = low;
                    signalBarHigh = high;
                    minLowSincePending = low;

                    series.setBoolean(index, Signals.PENDING_LONG, true);
                    ctx.signal(index, Signals.PENDING_LONG, "Pending Long - awaiting pivot confirmation", close);

                    var marker = getSettings().getMarker(Inputs.UP_MARKER);
                    if (marker.isEnabled()) {
                        addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, "PEND L"));
                    }
                    debug("PENDING LONG created, waiting for pivot high break above " + pivotHighPrice);
                } else {
                    // No pivot confirmation required - enter immediately
                    series.setBoolean(index, Signals.CONFIRMED_LONG, true);
                    ctx.signal(index, Signals.CONFIRMED_LONG, "Long Signal (no pivot confirm)", close);

                    var marker = getSettings().getMarker(Inputs.UP_MARKER);
                    if (marker.isEnabled()) {
                        addFigure(new Marker(new Coordinate(barTime, low - instr.getTickSize() * 3), Enums.Position.BOTTOM, marker, "LONG"));
                    }
                }
            }
        }

        // ===== SHORT SIGNAL LOGIC =====
        if (currentState == STATE_IDLE && crossBelow && tradesToday < maxTrades) {
            boolean canEnterShort = true;
            StringBuilder failReasons = new StringBuilder();

            if (!entryStackBearish) {
                canEnterShort = false;
                failReasons.append("EntryStack not bearish (").append(String.format("%.2f<%.2f<%.2f", entryFast, entryMid, entrySlow)).append(") ");
            }

            if (requirePriceAboveMAs && !priceBelowEntryMAs) {
                canEnterShort = false;
                failReasons.append("Price not below entry MAs ");
            }

            if (htfEnabled) {
                if (!htfDataAvailable) {
                    canEnterShort = false;
                    failReasons.append("HTF data not available ");
                } else if (!htfStackBearish) {
                    canEnterShort = false;
                    failReasons.append("HTF stack not bearish ");
                } else if (requirePriceAboveMAs && !priceBelowHTFMAs) {
                    canEnterShort = false;
                    failReasons.append("Price not below HTF MAs ");
                }
            }

            if (debugMode && crossBelow) {
                if (canEnterShort) {
                    debug(">>> CROSSOVER DOWN: All conditions MET for SHORT");
                } else {
                    debug(">>> CROSSOVER DOWN: FAILED - " + failReasons.toString());
                }
            }

            if (canEnterShort) {
                if (requirePivotConfirm) {
                    currentState = STATE_PENDING_SHORT;
                    signalBarIndex = index;
                    signalBarLow = low;
                    signalBarHigh = high;
                    maxHighSincePending = high;

                    series.setBoolean(index, Signals.PENDING_SHORT, true);
                    ctx.signal(index, Signals.PENDING_SHORT, "Pending Short - awaiting pivot confirmation", close);

                    var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
                    if (marker.isEnabled()) {
                        addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, "PEND S"));
                    }
                    debug("PENDING SHORT created, waiting for pivot low break below " + pivotLowPrice);
                } else {
                    series.setBoolean(index, Signals.CONFIRMED_SHORT, true);
                    ctx.signal(index, Signals.CONFIRMED_SHORT, "Short Signal (no pivot confirm)", close);

                    var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
                    if (marker.isEnabled()) {
                        addFigure(new Marker(new Coordinate(barTime, high + instr.getTickSize() * 3), Enums.Position.TOP, marker, "SHORT"));
                    }
                }
            }
        }

        // Long Confirmation (pivot break)
        if (currentState == STATE_PENDING_LONG && !Double.isNaN(pivotHighPrice) && close > pivotHighPrice) {
            debug(">>> LONG CONFIRMED: Close " + close + " > Pivot High " + pivotHighPrice);

            series.setBoolean(index, Signals.CONFIRMED_LONG, true);
            ctx.signal(index, Signals.CONFIRMED_LONG, "Long Confirmed - broke pivot high " + pivotHighPrice, close);

            if (getSettings().getBoolean(SHOW_OB_LINES, true)) {
                addOBLine(pivotHighPrice, pivotHighBarIndex, barTime, true, series);
            }

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low - instr.getTickSize() * 5), Enums.Position.BOTTOM, marker, "LONG"));
            }

            resetSignalState();
        }

        // Short Confirmation (pivot break)
        if (currentState == STATE_PENDING_SHORT && !Double.isNaN(pivotLowPrice) && close < pivotLowPrice) {
            debug(">>> SHORT CONFIRMED: Close " + close + " < Pivot Low " + pivotLowPrice);

            series.setBoolean(index, Signals.CONFIRMED_SHORT, true);
            ctx.signal(index, Signals.CONFIRMED_SHORT, "Short Confirmed - broke pivot low " + pivotLowPrice, close);

            if (getSettings().getBoolean(SHOW_OB_LINES, true)) {
                addOBLine(pivotLowPrice, pivotLowBarIndex, barTime, false, series);
            }

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high + instr.getTickSize() * 5), Enums.Position.TOP, marker, "SHORT"));
            }

            resetSignalState();
        }

        updateOBLines(barTime);
        series.setComplete(index);
    }

    // ==================== Helper Methods ====================

    private void setupStopAndTarget(OrderContext ctx, boolean isLong) {
        var instr = ctx.getInstrument();
        int stopMode = getSettings().getInteger(STOP_MODE, STOP_FIXED_POINTS);
        double stopBuffer = getSettings().getDouble(STOP_BUFFER, 1.0);
        double stopDistancePoints = getSettings().getDouble(STOP_DISTANCE_POINTS, 10.0);
        int tpMode = getSettings().getInteger(TP_MODE, TP_RR_MULTIPLE);
        double rrMultiple = getSettings().getDouble(RR_MULTIPLE, 2.0);
        double fixedTpPoints = getSettings().getDouble(FIXED_TP_POINTS, 20.0);

        double stopDist;

        if (isLong) {
            switch (stopMode) {
                case STOP_TRACKING_EXTREME:
                    stopPrice = Double.isNaN(minLowSincePending) ? entryPrice - stopDistancePoints : minLowSincePending - stopBuffer;
                    break;
                case STOP_SIGNAL_BAR:
                    stopPrice = Double.isNaN(signalBarLow) ? entryPrice - stopDistancePoints : signalBarLow - stopBuffer;
                    break;
                default:
                    stopPrice = entryPrice - stopDistancePoints;
            }
            stopDist = entryPrice - stopPrice;
            targetPrice = (tpMode == TP_RR_MULTIPLE) ? entryPrice + (stopDist * rrMultiple) : entryPrice + fixedTpPoints;
        } else {
            switch (stopMode) {
                case STOP_TRACKING_EXTREME:
                    stopPrice = Double.isNaN(maxHighSincePending) ? entryPrice + stopDistancePoints : maxHighSincePending + stopBuffer;
                    break;
                case STOP_SIGNAL_BAR:
                    stopPrice = Double.isNaN(signalBarHigh) ? entryPrice + stopDistancePoints : signalBarHigh + stopBuffer;
                    break;
                default:
                    stopPrice = entryPrice + stopDistancePoints;
            }
            stopDist = stopPrice - entryPrice;
            targetPrice = (tpMode == TP_RR_MULTIPLE) ? entryPrice - (stopDist * rrMultiple) : entryPrice - fixedTpPoints;
        }

        stopPrice = instr.round(stopPrice);
        targetPrice = instr.round(targetPrice);
        debug(String.format("Stop/Target: Entry=%.2f, Stop=%.2f, Target=%.2f", entryPrice, stopPrice, targetPrice));
    }

    private int getHTFMultiplier(DataSeries series) {
        int htfMode = getSettings().getInteger(HTF_MODE, HTF_MODE_AUTO);
        if (htfMode == HTF_MODE_MANUAL) {
            int htfManual = getSettings().getInteger(HTF_MANUAL, 60);
            int ltfMinutes = estimateBarMinutes(series);
            return Math.max(1, htfManual / ltfMinutes);
        }
        int ltfMinutes = estimateBarMinutes(series);
        if (ltfMinutes <= 5) return 12;
        else if (ltfMinutes <= 15) return 16;
        else if (ltfMinutes <= 60) return 24;
        return 12;
    }

    private int estimateBarMinutes(DataSeries series) {
        if (series.size() < 2) return 5;
        long diff = series.getStartTime(1) - series.getStartTime(0);
        return Math.max(1, (int)(diff / 60000));
    }

    private int getDayOfYear(long time, java.util.TimeZone tz) {
        java.util.Calendar cal = java.util.Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(java.util.Calendar.DAY_OF_YEAR);
    }

    private void addOBLine(double price, int barIndex, long endTime, boolean isBullish, DataSeries series) {
        int maxLines = getSettings().getInteger(MAX_OB_LINES, 20);
        while (obLines.size() >= maxLines) obLines.remove(0);

        OBLine line = new OBLine();
        line.price = price;
        line.startBarIndex = barIndex;
        line.startTime = series.getStartTime(barIndex);
        line.endTime = endTime;
        line.isBullish = isBullish;
        line.valid = true;
        obLines.add(line);

        Color color = isBullish ? new Color(0, 180, 0, 180) : new Color(180, 0, 0, 180);
        Line fig = new Line(new Coordinate(line.startTime, price), new Coordinate(endTime, price));
        fig.setColor(color);
        fig.setStroke(new java.awt.BasicStroke(2.0f));
        line.figure = fig;
        addFigure(fig);
    }

    private void updateOBLines(long currentTime) {
        int extendType = getSettings().getInteger(OB_EXTEND_TYPE, OB_EXTEND_LATEST);
        for (int i = 0; i < obLines.size(); i++) {
            OBLine line = obLines.get(i);
            if (!line.valid) continue;
            boolean shouldExtend = (extendType == OB_EXTEND_ALL) || (extendType == OB_EXTEND_LATEST && i == obLines.size() - 1);
            if (line.figure != null && shouldExtend) {
                line.endTime = currentTime;
                line.figure.setEnd(currentTime, line.price);
            }
        }
    }

    private void resetSignalState() {
        currentState = STATE_IDLE;
        minLowSincePending = Double.NaN;
        maxHighSincePending = Double.NaN;
        signalBarIndex = -1;
        signalBarLow = Double.NaN;
        signalBarHigh = Double.NaN;
    }

    private void resetTradeState() {
        entryPrice = 0;
        stopPrice = 0;
        targetPrice = 0;
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
        tradesToday = 0;
        lastTradeDay = -1;
        inTrade = false;
        eodProcessed = false;
        resetTradeState();
    }

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
