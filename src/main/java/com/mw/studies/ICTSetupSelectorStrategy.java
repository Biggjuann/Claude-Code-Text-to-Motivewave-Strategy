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
 * ICT Setup Selector Suite (JadeCap-style) with Preset Pack
 *
 * A multi-setup ICT-style strategy that lets users select from top setups:
 * - MMBM (Buy Model): SSL sweep → MSS up → FVG entry
 * - MMSM (Sell Model): BSL sweep → MSS down → FVG entry
 * - Session Liquidity Raid: NY-window raid of PDH/PDL/session levels
 * - London AM Raid NY Reversal: London raid sets up NY reversal
 * - Daily Sweep PO3: Daily sweep framework with confirmation
 *
 * Features:
 * - Preset system (Jade Balanced, Aggressive, Conservative)
 * - Multiple kill zone presets (NY AM, NY PM, London)
 * - Session high/low tracking (Asian, London)
 * - Structural stop loss with buffer
 * - Multiple exit models (R:R, TP1+TP2, Scale+Trail, Time Exit)
 * - EOD forced flattening
 *
 * @version 1.0.0
 * @author MW Study Builder (ICT concepts, JadeCap-style presets)
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "ICT_SETUP_SELECTOR",
    rb = "com.mw.studies.nls.strings",
    name = "ICT_SETUP_SELECTOR",
    label = "LBL_ICT_SETUP_SELECTOR",
    desc = "DESC_ICT_SETUP_SELECTOR",
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
public class ICTSetupSelectorStrategy extends Study
{
    // ==================== Input Keys ====================
    // Presets
    private static final String PRESET_SELECTOR = "presetSelector";
    private static final String SETUP_SELECTOR = "setupSelector";

    // Sessions
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";
    private static final String KILL_ZONE_PRESET = "killZonePreset";
    private static final String KILL_ZONE_CUSTOM_START = "killZoneCustomStart";
    private static final String KILL_ZONE_CUSTOM_END = "killZoneCustomEnd";

    // EOD
    private static final String EOD_CLOSE_ENABLED = "eodCloseEnabled";
    private static final String EOD_CLOSE_TIME = "eodCloseTime";
    private static final String EOD_CANCEL_WORKING = "eodCancelWorking";

    // Limits
    private static final String MAX_TRADES_PER_DAY = "maxTradesPerDay";
    private static final String ONE_TRADE_AT_A_TIME = "oneTradeAtATime";

    // Sizing
    private static final String CONTRACTS = "contracts";

    // Structure
    private static final String PIVOT_STRENGTH = "pivotStrength";
    private static final String MIN_RAID_TICKS = "minRaidTicks";

    // Risk
    private static final String STOPLOSS_ENABLED = "stoplossEnabled";
    private static final String STOPLOSS_MODE = "stoplossMode";
    private static final String STOPLOSS_TICKS = "stoplossTicks";

    // Entry Models
    private static final String ENTRY_MODEL_PREFERENCE = "entryModelPreference";
    private static final String FVG_MIN_TICKS = "fvgMinTicks";
    private static final String ENTRY_PRICE_IN_ZONE = "entryPriceInZone";
    private static final String MAX_BARS_TO_FILL = "maxBarsToFill";

    // Confirmations
    private static final String CONFIRMATION_STRICTNESS = "confirmationStrictness";
    private static final String REQUIRE_MSS_CLOSE = "requireMSSClose";

    // Exits
    private static final String EXIT_MODEL = "exitModel";
    private static final String RR_MULTIPLE = "rrMultiple";
    private static final String PARTIAL_ENABLED = "partialEnabled";
    private static final String PARTIAL_PCT = "partialPct";
    private static final String MIDDAY_EXIT_ENABLED = "middayExitEnabled";
    private static final String MIDDAY_EXIT_TIME = "middayExitTime";

    // Display paths
    private static final String PDH_PATH = "pdhPath";
    private static final String PDL_PATH = "pdlPath";
    private static final String EQ_PATH = "eqPath";
    private static final String ASIAN_HIGH_PATH = "asianHighPath";
    private static final String ASIAN_LOW_PATH = "asianLowPath";
    private static final String LONDON_HIGH_PATH = "londonHighPath";
    private static final String LONDON_LOW_PATH = "londonLowPath";

    // ==================== Mode Constants ====================
    // Presets
    private static final int PRESET_JADE_BALANCED = 0;
    private static final int PRESET_JADE_AGGRESSIVE = 1;
    private static final int PRESET_JADE_CONSERVATIVE = 2;

    // Setups
    private static final int SETUP_MMBM = 0;
    private static final int SETUP_MMSM = 1;
    private static final int SETUP_SESSION_RAID = 2;
    private static final int SETUP_LONDON_NY = 3;
    private static final int SETUP_DAILY_PO3 = 4;

    // Kill zones
    private static final int KZ_NY_AM = 0;
    private static final int KZ_NY_PM = 1;
    private static final int KZ_LONDON_AM = 2;
    private static final int KZ_CUSTOM = 3;

    // Stop modes
    private static final int STOP_FIXED = 0;
    private static final int STOP_STRUCTURAL = 1;

    // Entry models
    private static final int ENTRY_IMMEDIATE = 0;
    private static final int ENTRY_FVG_ONLY = 1;
    private static final int ENTRY_BOTH = 2;
    private static final int ENTRY_MSS_MARKET = 3;

    // Entry price in zone
    private static final int ZONE_TOP = 0;
    private static final int ZONE_MID = 1;
    private static final int ZONE_BOTTOM = 2;

    // Confirmation strictness
    private static final int STRICT_AGGRESSIVE = 0;
    private static final int STRICT_BALANCED = 1;
    private static final int STRICT_CONSERVATIVE = 2;

    // Exit models
    private static final int EXIT_RR = 0;
    private static final int EXIT_TP1_TP2 = 1;
    private static final int EXIT_SCALE_TRAIL = 2;
    private static final int EXIT_TIME_MIDDAY = 3;

    // ==================== Values ====================
    enum Values {
        PDH, PDL, EQUILIBRIUM,
        ASIAN_HIGH, ASIAN_LOW,
        LONDON_HIGH, LONDON_LOW,
        LIQUIDITY_LEVEL, MSS_LEVEL, FVG_TOP, FVG_BOTTOM,
        SIGNAL_STATE
    }

    // ==================== Signals ====================
    enum Signals { SWEEP_DETECTED, MSS_CONFIRMED, ENTRY_LONG, ENTRY_SHORT }

    // ==================== State Machine ====================
    private static final int STATE_IDLE = 0;
    private static final int STATE_SWEEP_DETECTED = 1;
    private static final int STATE_MSS_PENDING = 2;
    private static final int STATE_FVG_HUNTING = 3;
    private static final int STATE_ENTRY_READY = 4;
    private static final int STATE_IN_TRADE = 5;

    // ==================== State Variables ====================
    private int signalState = STATE_IDLE;
    private int signalDirection = 0; // 1 = long, -1 = short

    // Daily tracking
    private double pdh = Double.NaN;
    private double pdl = Double.NaN;
    private double todayHigh = Double.NaN;
    private double todayLow = Double.NaN;
    private int lastResetDay = -1;

    // Session tracking
    private double asianHigh = Double.NaN;
    private double asianLow = Double.NaN;
    private double londonHigh = Double.NaN;
    private double londonLow = Double.NaN;
    private boolean asianComplete = false;
    private boolean londonComplete = false;

    // Liquidity/raid
    private double targetLiqLevel = Double.NaN;
    private double sweepExtreme = Double.NaN;
    private boolean sweepDetected = false;

    // MSS
    private double mssLevel = Double.NaN;
    private boolean mssConfirmed = false;

    // FVG
    private double fvgTop = Double.NaN;
    private double fvgBottom = Double.NaN;
    private boolean fvgDetected = false;
    private int fvgBarIndex = -1;

    // Trade tracking
    private int tradesToday = 0;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double tp1Price = 0;
    private double tp2Price = 0;
    private boolean partialTaken = false;
    private int entryBarIndex = -1;
    private boolean waitingForFill = false;
    private boolean eodProcessed = false;

    // NY timezone
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Presets Tab =====
        var tab = sd.addTab("Presets");
        var grp = tab.addGroup("Preset Selection");
        grp.addRow(new IntegerDescriptor(PRESET_SELECTOR,
            "Preset Pack (0=Balanced, 1=Aggressive, 2=Conservative)", PRESET_JADE_BALANCED, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(SETUP_SELECTOR,
            "Setup (0=MMBM, 1=MMSM, 2=SessionRaid, 3=LondonNY, 4=DailyPO3)", SETUP_MMBM, 0, 4, 1));

        // ===== Sessions Tab =====
        tab = sd.addTab("Sessions");
        grp = tab.addGroup("Trade Window (ET)");
        grp.addRow(new IntegerDescriptor(TRADE_START, "Start Time (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(TRADE_END, "End Time (HHMM)", 1130, 0, 2359, 1));

        grp = tab.addGroup("Kill Zone");
        grp.addRow(new IntegerDescriptor(KILL_ZONE_PRESET,
            "Kill Zone (0=NY AM, 1=NY PM, 2=London, 3=Custom)", KZ_NY_AM, 0, 3, 1));
        grp.addRow(new IntegerDescriptor(KILL_ZONE_CUSTOM_START, "Custom KZ Start (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(KILL_ZONE_CUSTOM_END, "Custom KZ End (HHMM)", 1130, 0, 2359, 1));

        grp = tab.addGroup("End of Day");
        grp.addRow(new BooleanDescriptor(EOD_CLOSE_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_CLOSE_TIME, "EOD Close Time (HHMM)", 1640, 0, 2359, 1));
        grp.addRow(new BooleanDescriptor(EOD_CANCEL_WORKING, "Cancel Working Orders at EOD", true));

        // ===== Limits Tab =====
        tab = sd.addTab("Limits");
        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_PER_DAY, "Max Trades Per Day", 1, 1, 10, 1));
        grp.addRow(new BooleanDescriptor(ONE_TRADE_AT_A_TIME, "One Trade At A Time", true));
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 1, 1, 100, 1));

        // ===== Structure Tab =====
        tab = sd.addTab("Structure");
        grp = tab.addGroup("Pivot/Swing Detection");
        grp.addRow(new IntegerDescriptor(PIVOT_STRENGTH, "Pivot Strength (L/R bars)", 2, 1, 10, 1));
        grp.addRow(new IntegerDescriptor(MIN_RAID_TICKS, "Min Raid Penetration (ticks)", 2, 1, 50, 1));

        // ===== Entry Tab =====
        tab = sd.addTab("Entry");
        grp = tab.addGroup("Entry Model");
        grp.addRow(new IntegerDescriptor(ENTRY_MODEL_PREFERENCE,
            "Entry Preference (0=Immediate, 1=FVG Only, 2=Both, 3=MSS Market)", ENTRY_BOTH, 0, 3, 1));
        grp.addRow(new IntegerDescriptor(FVG_MIN_TICKS, "Min FVG Size (ticks)", 2, 1, 50, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_PRICE_IN_ZONE,
            "Entry Price In Zone (0=Top, 1=Mid, 2=Bottom)", ZONE_MID, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(MAX_BARS_TO_FILL, "Max Bars to Fill Limit Entry", 30, 1, 100, 1));

        grp = tab.addGroup("Confirmations");
        grp.addRow(new IntegerDescriptor(CONFIRMATION_STRICTNESS,
            "Strictness (0=Aggressive, 1=Balanced, 2=Conservative)", STRICT_BALANCED, 0, 2, 1));
        grp.addRow(new BooleanDescriptor(REQUIRE_MSS_CLOSE, "Require MSS Close Confirmation", true));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Stop Loss");
        grp.addRow(new BooleanDescriptor(STOPLOSS_ENABLED, "Enable Stop Loss", true));
        grp.addRow(new IntegerDescriptor(STOPLOSS_MODE, "Stop Mode (0=Fixed, 1=Structural+Buffer)", STOP_STRUCTURAL, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(STOPLOSS_TICKS, "Stop Buffer (ticks)", 20, 1, 200, 1));

        // ===== Exits Tab =====
        tab = sd.addTab("Exits");
        grp = tab.addGroup("Exit Model");
        grp.addRow(new IntegerDescriptor(EXIT_MODEL,
            "Exit Model (0=RR, 1=TP1+TP2, 2=Scale+Trail, 3=Midday)", EXIT_TP1_TP2, 0, 3, 1));
        grp.addRow(new DoubleDescriptor(RR_MULTIPLE, "RR Multiple", 2.0, 0.5, 10.0, 0.25));

        grp = tab.addGroup("Partial Exits");
        grp.addRow(new BooleanDescriptor(PARTIAL_ENABLED, "Enable Partial", true));
        grp.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial %", 50, 1, 99, 1));

        grp = tab.addGroup("Time Exit");
        grp.addRow(new BooleanDescriptor(MIDDAY_EXIT_ENABLED, "Enable Midday Exit", true));
        grp.addRow(new IntegerDescriptor(MIDDAY_EXIT_TIME, "Midday Exit Time (HHMM)", 1215, 0, 2359, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Daily Levels");
        grp.addRow(new PathDescriptor(PDH_PATH, "PDH",
            defaults.getRed(), 1.5f, new float[]{8, 4}, true, true, true));
        grp.addRow(new PathDescriptor(PDL_PATH, "PDL",
            defaults.getGreen(), 1.5f, new float[]{8, 4}, true, true, true));
        grp.addRow(new PathDescriptor(EQ_PATH, "Equilibrium",
            defaults.getYellow(), 1.0f, new float[]{4, 4}, true, true, true));

        grp = tab.addGroup("Session Levels");
        grp.addRow(new PathDescriptor(ASIAN_HIGH_PATH, "Asian High",
            defaults.getBlue(), 1.0f, new float[]{4, 4}, true, true, true));
        grp.addRow(new PathDescriptor(ASIAN_LOW_PATH, "Asian Low",
            defaults.getBlue(), 1.0f, new float[]{4, 4}, true, true, true));
        grp.addRow(new PathDescriptor(LONDON_HIGH_PATH, "London High",
            defaults.getPurple(), 1.0f, new float[]{4, 4}, true, true, true));
        grp.addRow(new PathDescriptor(LONDON_LOW_PATH, "London Low",
            defaults.getPurple(), 1.0f, new float[]{4, 4}, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(PRESET_SELECTOR, SETUP_SELECTOR, CONTRACTS, MAX_TRADES_PER_DAY);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(PRESET_SELECTOR, SETUP_SELECTOR, RR_MULTIPLE);

        desc.exportValue(new ValueDescriptor(Values.PDH, "PDH", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.PDL, "PDL", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.EQUILIBRIUM, "Equilibrium", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.ASIAN_HIGH, "Asian High", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.ASIAN_LOW, "Asian Low", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.LONDON_HIGH, "London High", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.LONDON_LOW, "London Low", new String[]{}));

        desc.declarePath(Values.PDH, PDH_PATH);
        desc.declarePath(Values.PDL, PDL_PATH);
        desc.declarePath(Values.EQUILIBRIUM, EQ_PATH);
        desc.declarePath(Values.ASIAN_HIGH, ASIAN_HIGH_PATH);
        desc.declarePath(Values.ASIAN_LOW, ASIAN_LOW_PATH);
        desc.declarePath(Values.LONDON_HIGH, LONDON_HIGH_PATH);
        desc.declarePath(Values.LONDON_LOW, LONDON_LOW_PATH);

        desc.declareSignal(Signals.SWEEP_DETECTED, "Liquidity Sweep Detected");
        desc.declareSignal(Signals.MSS_CONFIRMED, "MSS Confirmed");
        desc.declareSignal(Signals.ENTRY_LONG, "Long Entry");
        desc.declareSignal(Signals.ENTRY_SHORT, "Short Entry");

        desc.setRangeKeys(Values.PDH, Values.PDL);
    }

    @Override
    public int getMinBars() {
        return 100;
    }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();

        if (index < 20) return;

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
            asianHigh = Double.NaN;
            asianLow = Double.NaN;
            londonHigh = Double.NaN;
            londonLow = Double.NaN;
            asianComplete = false;
            londonComplete = false;
            resetDailyState();
            lastResetDay = barDay;
        }

        // Track today's high/low
        if (Double.isNaN(todayHigh) || high > todayHigh) todayHigh = high;
        if (Double.isNaN(todayLow) || low < todayLow) todayLow = low;

        // Track session highs/lows
        updateSessionLevels(barTimeInt, high, low);

        // Plot levels
        if (!Double.isNaN(pdh)) {
            series.setDouble(index, Values.PDH, pdh);
            series.setDouble(index, Values.PDL, pdl);
            series.setDouble(index, Values.EQUILIBRIUM, (pdh + pdl) / 2.0);
        }
        if (asianComplete) {
            series.setDouble(index, Values.ASIAN_HIGH, asianHigh);
            series.setDouble(index, Values.ASIAN_LOW, asianLow);
        }
        if (londonComplete) {
            series.setDouble(index, Values.LONDON_HIGH, londonHigh);
            series.setDouble(index, Values.LONDON_LOW, londonLow);
        }

        // Store signal state
        series.setInt(index, Values.SIGNAL_STATE, signalState);

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (Double.isNaN(pdh) || Double.isNaN(pdl)) return;

        // Get settings
        int setupSelector = getSettings().getInteger(SETUP_SELECTOR, SETUP_MMBM);
        int tradeStart = getSettings().getInteger(TRADE_START, 930);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1130);
        int killZonePreset = getSettings().getInteger(KILL_ZONE_PRESET, KZ_NY_AM);
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_DAY, 1);
        boolean oneAtATime = getSettings().getBoolean(ONE_TRADE_AT_A_TIME, true);
        int pivotStrength = getSettings().getInteger(PIVOT_STRENGTH, 2);
        int minRaidTicks = getSettings().getInteger(MIN_RAID_TICKS, 2);
        int entryModel = getSettings().getInteger(ENTRY_MODEL_PREFERENCE, ENTRY_BOTH);
        int fvgMinTicks = getSettings().getInteger(FVG_MIN_TICKS, 2);
        boolean requireMSSClose = getSettings().getBoolean(REQUIRE_MSS_CLOSE, true);
        int strictness = getSettings().getInteger(CONFIRMATION_STRICTNESS, STRICT_BALANCED);

        // Check session/killzone
        boolean inTradeSession = barTimeInt >= tradeStart && barTimeInt < tradeEnd;
        boolean inKillZone = isInKillZone(barTimeInt, killZonePreset);

        // Check EOD cutoff
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1640);
        boolean pastEodCutoff = eodEnabled && barTimeInt >= eodTime;

        // Can we trade?
        boolean canTrade = inTradeSession && inKillZone && tradesToday < maxTrades && !pastEodCutoff;

        // Run setup-specific logic
        switch (setupSelector) {
            case SETUP_MMBM:
                processMMBM(ctx, series, index, tickSize, pivotStrength, minRaidTicks, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime);
                break;
            case SETUP_MMSM:
                processMMSM(ctx, series, index, tickSize, pivotStrength, minRaidTicks, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime);
                break;
            case SETUP_SESSION_RAID:
                processSessionRaid(ctx, series, index, tickSize, pivotStrength, minRaidTicks, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime);
                break;
            case SETUP_LONDON_NY:
                processLondonNYReversal(ctx, series, index, tickSize, pivotStrength, minRaidTicks, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime);
                break;
            case SETUP_DAILY_PO3:
                processDailyPO3(ctx, series, index, tickSize, pivotStrength, minRaidTicks, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime);
                break;
        }

        // Check for entry cancellation (max bars exceeded)
        if (waitingForFill && entryBarIndex > 0) {
            int maxBars = getSettings().getInteger(MAX_BARS_TO_FILL, 30);
            if (index - entryBarIndex > maxBars) {
                waitingForFill = false;
                fvgDetected = false;
                signalState = STATE_IDLE;
                debug("Entry cancelled - max bars exceeded");
            }
        }

        series.setComplete(index);
    }

    // ==================== Setup Processors ====================

    private void processMMBM(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int minRaidTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // MMBM: SSL sweep → MSS up → Bullish FVG → Long entry

        // Phase 1: Identify SSL (PDL or recent swing low)
        if (signalState == STATE_IDLE && canTrade) {
            targetLiqLevel = findSSL(series, index, pivotStrength);
        }

        // Phase 2: Detect SSL sweep
        if (signalState == STATE_IDLE && canTrade && !Double.isNaN(targetLiqLevel)) {
            double sweepThreshold = targetLiqLevel - (minRaidTicks * tickSize);
            if (low <= sweepThreshold) {
                boolean validSweep = (strictness == STRICT_AGGRESSIVE) || (close > targetLiqLevel);
                if (validSweep) {
                    sweepDetected = true;
                    sweepExtreme = low;
                    signalState = STATE_SWEEP_DETECTED;
                    signalDirection = 1; // Long
                    mssLevel = findSwingHigh(series, index, pivotStrength);
                    ctx.signal(index, Signals.SWEEP_DETECTED,
                        String.format("SSL Sweep: Low=%.2f", low), low);
                    debug("MMBM: SSL sweep detected at " + low);
                }
            }
        }

        // Update sweep extreme
        if (signalState == STATE_SWEEP_DETECTED && signalDirection == 1 && low < sweepExtreme) {
            sweepExtreme = low;
        }

        // Phase 3: Detect MSS (break of swing high with displacement)
        if (signalState == STATE_SWEEP_DETECTED && signalDirection == 1 && !Double.isNaN(mssLevel)) {
            boolean mssBreak = requireMSSClose ? (close > mssLevel) : (high > mssLevel);
            if (mssBreak) {
                int dispTicks = getDisplacementTicks(strictness);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispTicks * tickSize || strictness == STRICT_AGGRESSIVE) {
                    mssConfirmed = true;
                    signalState = STATE_MSS_PENDING;
                    ctx.signal(index, Signals.MSS_CONFIRMED, "MSS Up Confirmed", close);
                    debug("MMBM: MSS confirmed at " + close);

                    // If immediate entry allowed, can enter now
                    if (entryModel == ENTRY_IMMEDIATE || entryModel == ENTRY_MSS_MARKET) {
                        signalState = STATE_ENTRY_READY;
                    }
                }
            }
        }

        // Phase 4: Detect Bullish FVG
        if ((signalState == STATE_MSS_PENDING || signalState == STATE_SWEEP_DETECTED) &&
            signalDirection == 1 && index >= 2 &&
            (entryModel == ENTRY_FVG_ONLY || entryModel == ENTRY_BOTH))
        {
            double bar0High = series.getHigh(index - 2);
            double bar2Low = series.getLow(index);
            if (bar2Low > bar0High && (bar2Low - bar0High) >= fvgMinTicks * tickSize) {
                fvgTop = bar2Low;
                fvgBottom = bar0High;
                fvgDetected = true;
                fvgBarIndex = index;
                signalState = STATE_ENTRY_READY;
                debug("MMBM: Bullish FVG detected: " + fvgBottom + " - " + fvgTop);
            }
        }

        // Phase 5: Generate entry signal
        if (signalState == STATE_ENTRY_READY && signalDirection == 1 && canTrade && !waitingForFill) {
            waitingForFill = true;
            entryBarIndex = index;
            ctx.signal(index, Signals.ENTRY_LONG, "MMBM Long Setup Ready", close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, "MMBM"));
            }
        }
    }

    private void processMMSM(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int minRaidTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // MMSM: BSL sweep → MSS down → Bearish FVG → Short entry

        // Phase 1: Identify BSL (PDH or recent swing high)
        if (signalState == STATE_IDLE && canTrade) {
            targetLiqLevel = findBSL(series, index, pivotStrength);
        }

        // Phase 2: Detect BSL sweep
        if (signalState == STATE_IDLE && canTrade && !Double.isNaN(targetLiqLevel)) {
            double sweepThreshold = targetLiqLevel + (minRaidTicks * tickSize);
            if (high >= sweepThreshold) {
                boolean validSweep = (strictness == STRICT_AGGRESSIVE) || (close < targetLiqLevel);
                if (validSweep) {
                    sweepDetected = true;
                    sweepExtreme = high;
                    signalState = STATE_SWEEP_DETECTED;
                    signalDirection = -1; // Short
                    mssLevel = findSwingLow(series, index, pivotStrength);
                    ctx.signal(index, Signals.SWEEP_DETECTED,
                        String.format("BSL Sweep: High=%.2f", high), high);
                    debug("MMSM: BSL sweep detected at " + high);
                }
            }
        }

        // Update sweep extreme
        if (signalState == STATE_SWEEP_DETECTED && signalDirection == -1 && high > sweepExtreme) {
            sweepExtreme = high;
        }

        // Phase 3: Detect MSS Down
        if (signalState == STATE_SWEEP_DETECTED && signalDirection == -1 && !Double.isNaN(mssLevel)) {
            boolean mssBreak = requireMSSClose ? (close < mssLevel) : (low < mssLevel);
            if (mssBreak) {
                int dispTicks = getDisplacementTicks(strictness);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispTicks * tickSize || strictness == STRICT_AGGRESSIVE) {
                    mssConfirmed = true;
                    signalState = STATE_MSS_PENDING;
                    ctx.signal(index, Signals.MSS_CONFIRMED, "MSS Down Confirmed", close);
                    debug("MMSM: MSS Down confirmed at " + close);

                    if (entryModel == ENTRY_IMMEDIATE || entryModel == ENTRY_MSS_MARKET) {
                        signalState = STATE_ENTRY_READY;
                    }
                }
            }
        }

        // Phase 4: Detect Bearish FVG
        if ((signalState == STATE_MSS_PENDING || signalState == STATE_SWEEP_DETECTED) &&
            signalDirection == -1 && index >= 2 &&
            (entryModel == ENTRY_FVG_ONLY || entryModel == ENTRY_BOTH))
        {
            double bar0Low = series.getLow(index - 2);
            double bar2High = series.getHigh(index);
            if (bar2High < bar0Low && (bar0Low - bar2High) >= fvgMinTicks * tickSize) {
                fvgTop = bar0Low;
                fvgBottom = bar2High;
                fvgDetected = true;
                fvgBarIndex = index;
                signalState = STATE_ENTRY_READY;
                debug("MMSM: Bearish FVG detected: " + fvgBottom + " - " + fvgTop);
            }
        }

        // Phase 5: Generate entry signal
        if (signalState == STATE_ENTRY_READY && signalDirection == -1 && canTrade && !waitingForFill) {
            waitingForFill = true;
            entryBarIndex = index;
            ctx.signal(index, Signals.ENTRY_SHORT, "MMSM Short Setup Ready", close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, "MMSM"));
            }
        }
    }

    private void processSessionRaid(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int minRaidTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // Session Liquidity Raid: Raid of PDH/PDL/Asian/London levels

        if (signalState == STATE_IDLE && canTrade) {
            // Check for raids of multiple liquidity levels
            double sweepBuffer = minRaidTicks * tickSize;

            // Check PDL/Asian Low/London Low (potential long setup)
            double lowestLiq = Math.min(pdl,
                Math.min(asianComplete ? asianLow : Double.MAX_VALUE,
                         londonComplete ? londonLow : Double.MAX_VALUE));

            if (!Double.isNaN(lowestLiq) && lowestLiq < Double.MAX_VALUE && low <= lowestLiq - sweepBuffer) {
                if (strictness == STRICT_AGGRESSIVE || close > lowestLiq) {
                    sweepDetected = true;
                    sweepExtreme = low;
                    targetLiqLevel = lowestLiq;
                    signalState = STATE_SWEEP_DETECTED;
                    signalDirection = 1;
                    mssLevel = findSwingHigh(series, index, pivotStrength);
                    ctx.signal(index, Signals.SWEEP_DETECTED, "Session Low Raid", low);
                    debug("Session Raid: Low sweep at " + low);
                }
            }

            // Check PDH/Asian High/London High (potential short setup)
            double highestLiq = Math.max(pdh,
                Math.max(asianComplete ? asianHigh : Double.MIN_VALUE,
                         londonComplete ? londonHigh : Double.MIN_VALUE));

            if (!sweepDetected && !Double.isNaN(highestLiq) && highestLiq > Double.MIN_VALUE &&
                high >= highestLiq + sweepBuffer) {
                if (strictness == STRICT_AGGRESSIVE || close < highestLiq) {
                    sweepDetected = true;
                    sweepExtreme = high;
                    targetLiqLevel = highestLiq;
                    signalState = STATE_SWEEP_DETECTED;
                    signalDirection = -1;
                    mssLevel = findSwingLow(series, index, pivotStrength);
                    ctx.signal(index, Signals.SWEEP_DETECTED, "Session High Raid", high);
                    debug("Session Raid: High sweep at " + high);
                }
            }
        }

        // Continue with standard MSS/FVG detection based on direction
        if (signalDirection == 1) {
            processMSSAndFVGForLong(ctx, series, index, tickSize, pivotStrength, fvgMinTicks,
                entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime, "SessionRaid");
        } else if (signalDirection == -1) {
            processMSSAndFVGForShort(ctx, series, index, tickSize, pivotStrength, fvgMinTicks,
                entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime, "SessionRaid");
        }
    }

    private void processLondonNYReversal(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int minRaidTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // London AM Raid → NY Reversal
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        // Detect London raid during London session
        if (signalState == STATE_IDLE && londonComplete && barTimeInt >= 300 && barTimeInt < 930) {
            double sweepBuffer = minRaidTicks * tickSize;

            // Check if London made new high (potential short setup for NY)
            if (high >= londonHigh + sweepBuffer) {
                sweepDetected = true;
                sweepExtreme = high;
                targetLiqLevel = londonHigh;
                signalState = STATE_SWEEP_DETECTED;
                signalDirection = -1;
                debug("London Raid: High swept at " + high + ", waiting for NY reversal");
            }

            // Check if London made new low (potential long setup for NY)
            if (!sweepDetected && low <= londonLow - sweepBuffer) {
                sweepDetected = true;
                sweepExtreme = low;
                targetLiqLevel = londonLow;
                signalState = STATE_SWEEP_DETECTED;
                signalDirection = 1;
                debug("London Raid: Low swept at " + low + ", waiting for NY reversal");
            }
        }

        // Wait for NY session to confirm MSS
        if (signalState == STATE_SWEEP_DETECTED && canTrade) {
            if (signalDirection == 1) {
                mssLevel = findSwingHigh(series, index, pivotStrength);
                processMSSAndFVGForLong(ctx, series, index, tickSize, pivotStrength, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime, "LondonNY");
            } else {
                mssLevel = findSwingLow(series, index, pivotStrength);
                processMSSAndFVGForShort(ctx, series, index, tickSize, pivotStrength, fvgMinTicks,
                    entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime, "LondonNY");
            }
        }
    }

    private void processDailyPO3(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int minRaidTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // Daily Sweep PO3: Daily level sweep framework

        if (signalState == STATE_IDLE && canTrade) {
            double sweepBuffer = minRaidTicks * tickSize;

            // Sweep of PDL → Long setup
            if (low <= pdl - sweepBuffer) {
                if (strictness == STRICT_AGGRESSIVE || close > pdl) {
                    sweepDetected = true;
                    sweepExtreme = low;
                    targetLiqLevel = pdl;
                    signalState = STATE_SWEEP_DETECTED;
                    signalDirection = 1;
                    mssLevel = findSwingHigh(series, index, pivotStrength);
                    ctx.signal(index, Signals.SWEEP_DETECTED, "Daily Low Sweep (PO3)", low);
                    debug("Daily PO3: PDL sweep at " + low);
                }
            }

            // Sweep of PDH → Short setup
            if (!sweepDetected && high >= pdh + sweepBuffer) {
                if (strictness == STRICT_AGGRESSIVE || close < pdh) {
                    sweepDetected = true;
                    sweepExtreme = high;
                    targetLiqLevel = pdh;
                    signalState = STATE_SWEEP_DETECTED;
                    signalDirection = -1;
                    mssLevel = findSwingLow(series, index, pivotStrength);
                    ctx.signal(index, Signals.SWEEP_DETECTED, "Daily High Sweep (PO3)", high);
                    debug("Daily PO3: PDH sweep at " + high);
                }
            }
        }

        // Process MSS/FVG based on direction
        if (signalDirection == 1) {
            processMSSAndFVGForLong(ctx, series, index, tickSize, pivotStrength, fvgMinTicks,
                entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime, "DailyPO3");
        } else if (signalDirection == -1) {
            processMSSAndFVGForShort(ctx, series, index, tickSize, pivotStrength, fvgMinTicks,
                entryModel, requireMSSClose, strictness, canTrade, high, low, close, open, barTime, "DailyPO3");
        }
    }

    // ==================== Common MSS/FVG Processing ====================

    private void processMSSAndFVGForLong(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int fvgMinTicks, int entryModel, boolean requireMSSClose, int strictness,
            boolean canTrade, double high, double low, double close, double open, long barTime, String setupName)
    {
        // Update sweep extreme
        if (signalState == STATE_SWEEP_DETECTED && low < sweepExtreme) {
            sweepExtreme = low;
        }

        // MSS detection for long
        if (signalState == STATE_SWEEP_DETECTED && !Double.isNaN(mssLevel)) {
            boolean mssBreak = requireMSSClose ? (close > mssLevel) : (high > mssLevel);
            if (mssBreak) {
                int dispTicks = getDisplacementTicks(strictness);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispTicks * tickSize || strictness == STRICT_AGGRESSIVE) {
                    mssConfirmed = true;
                    signalState = STATE_MSS_PENDING;
                    ctx.signal(index, Signals.MSS_CONFIRMED, setupName + " MSS Up", close);
                    debug(setupName + ": MSS Up confirmed at " + close);

                    if (entryModel == ENTRY_IMMEDIATE || entryModel == ENTRY_MSS_MARKET) {
                        signalState = STATE_ENTRY_READY;
                    }
                }
            }
        }

        // Bullish FVG detection
        if ((signalState == STATE_MSS_PENDING || signalState == STATE_SWEEP_DETECTED) &&
            index >= 2 && (entryModel == ENTRY_FVG_ONLY || entryModel == ENTRY_BOTH))
        {
            double bar0High = series.getHigh(index - 2);
            double bar2Low = series.getLow(index);
            if (bar2Low > bar0High && (bar2Low - bar0High) >= fvgMinTicks * tickSize) {
                fvgTop = bar2Low;
                fvgBottom = bar0High;
                fvgDetected = true;
                fvgBarIndex = index;
                signalState = STATE_ENTRY_READY;
                debug(setupName + ": Bullish FVG detected");
            }
        }

        // Entry signal
        if (signalState == STATE_ENTRY_READY && canTrade && !waitingForFill) {
            waitingForFill = true;
            entryBarIndex = index;
            ctx.signal(index, Signals.ENTRY_LONG, setupName + " Long Ready", close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, setupName));
            }
        }
    }

    private void processMSSAndFVGForShort(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int fvgMinTicks, int entryModel, boolean requireMSSClose, int strictness,
            boolean canTrade, double high, double low, double close, double open, long barTime, String setupName)
    {
        // Update sweep extreme
        if (signalState == STATE_SWEEP_DETECTED && high > sweepExtreme) {
            sweepExtreme = high;
        }

        // MSS detection for short
        if (signalState == STATE_SWEEP_DETECTED && !Double.isNaN(mssLevel)) {
            boolean mssBreak = requireMSSClose ? (close < mssLevel) : (low < mssLevel);
            if (mssBreak) {
                int dispTicks = getDisplacementTicks(strictness);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispTicks * tickSize || strictness == STRICT_AGGRESSIVE) {
                    mssConfirmed = true;
                    signalState = STATE_MSS_PENDING;
                    ctx.signal(index, Signals.MSS_CONFIRMED, setupName + " MSS Down", close);
                    debug(setupName + ": MSS Down confirmed at " + close);

                    if (entryModel == ENTRY_IMMEDIATE || entryModel == ENTRY_MSS_MARKET) {
                        signalState = STATE_ENTRY_READY;
                    }
                }
            }
        }

        // Bearish FVG detection
        if ((signalState == STATE_MSS_PENDING || signalState == STATE_SWEEP_DETECTED) &&
            index >= 2 && (entryModel == ENTRY_FVG_ONLY || entryModel == ENTRY_BOTH))
        {
            double bar0Low = series.getLow(index - 2);
            double bar2High = series.getHigh(index);
            if (bar2High < bar0Low && (bar0Low - bar2High) >= fvgMinTicks * tickSize) {
                fvgTop = bar0Low;
                fvgBottom = bar2High;
                fvgDetected = true;
                fvgBarIndex = index;
                signalState = STATE_ENTRY_READY;
                debug(setupName + ": Bearish FVG detected");
            }
        }

        // Entry signal
        if (signalState == STATE_ENTRY_READY && canTrade && !waitingForFill) {
            waitingForFill = true;
            entryBarIndex = index;
            ctx.signal(index, Signals.ENTRY_SHORT, setupName + " Short Ready", close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, setupName));
            }
        }
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("ICT Setup Selector Strategy activated");
        applyPresetDefaults();
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
        if (signal != Signals.ENTRY_LONG && signal != Signals.ENTRY_SHORT) return;

        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        double tickSize = instr.getTickSize();

        // Check EOD cutoff
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1640);

        if (eodEnabled && barTimeInt >= eodTime) {
            debug("EOD cutoff reached, blocking new entry");
            return;
        }

        boolean oneAtATime = getSettings().getBoolean(ONE_TRADE_AT_A_TIME, true);
        if (oneAtATime && position != 0) {
            debug("Already in position, ignoring signal");
            return;
        }

        int qty = getSettings().getInteger(CONTRACTS, 1);
        int stopMode = getSettings().getInteger(STOPLOSS_MODE, STOP_STRUCTURAL);
        int stopTicks = getSettings().getInteger(STOPLOSS_TICKS, 20);
        int exitModel = getSettings().getInteger(EXIT_MODEL, EXIT_TP1_TP2);
        double rrMult = getSettings().getDouble(RR_MULTIPLE, 2.0);
        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);
        int zonePrice = getSettings().getInteger(ENTRY_PRICE_IN_ZONE, ZONE_MID);

        boolean isLong = (signal == Signals.ENTRY_LONG);

        // Execute entry
        if (isLong) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();

            // Calculate stop (structural = below sweep extreme)
            if (stopEnabled) {
                double stopBuffer = stopTicks * tickSize;
                if (stopMode == STOP_STRUCTURAL && !Double.isNaN(sweepExtreme)) {
                    stopPrice = sweepExtreme - stopBuffer;
                } else {
                    stopPrice = entryPrice - stopBuffer;
                }
                stopPrice = instr.round(stopPrice);
            }

            // Calculate targets
            double risk = entryPrice - stopPrice;
            double equilibrium = (pdh + pdl) / 2.0;

            tp1Price = equilibrium; // Internal target

            switch (exitModel) {
                case EXIT_RR:
                    tp2Price = entryPrice + (risk * rrMult);
                    break;
                case EXIT_TP1_TP2:
                    tp2Price = pdh; // Opposite liquidity
                    break;
                case EXIT_SCALE_TRAIL:
                    tp2Price = pdh;
                    break;
                default:
                    tp2Price = entryPrice + (risk * rrMult);
            }
            tp2Price = instr.round(tp2Price);

            debug(String.format("LONG: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
                qty, entryPrice, stopPrice, tp1Price, tp2Price));

        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();

            // Calculate stop (structural = above sweep extreme)
            if (stopEnabled) {
                double stopBuffer = stopTicks * tickSize;
                if (stopMode == STOP_STRUCTURAL && !Double.isNaN(sweepExtreme)) {
                    stopPrice = sweepExtreme + stopBuffer;
                } else {
                    stopPrice = entryPrice + stopBuffer;
                }
                stopPrice = instr.round(stopPrice);
            }

            // Calculate targets
            double risk = stopPrice - entryPrice;
            double equilibrium = (pdh + pdl) / 2.0;

            tp1Price = equilibrium; // Internal target

            switch (exitModel) {
                case EXIT_RR:
                    tp2Price = entryPrice - (risk * rrMult);
                    break;
                case EXIT_TP1_TP2:
                    tp2Price = pdl; // Opposite liquidity
                    break;
                case EXIT_SCALE_TRAIL:
                    tp2Price = pdl;
                    break;
                default:
                    tp2Price = entryPrice - (risk * rrMult);
            }
            tp2Price = instr.round(tp2Price);

            debug(String.format("SHORT: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
                qty, entryPrice, stopPrice, tp1Price, tp2Price));
        }

        tradesToday++;
        partialTaken = false;
        waitingForFill = false;
        signalState = STATE_IN_TRADE;
    }

    @Override
    public void onBarClose(OrderContext ctx) {
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        // ===== EOD FLATTEN (Highest Priority) =====
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1640);

        if (eodEnabled && barTimeInt >= eodTime && !eodProcessed) {
            int position = ctx.getPosition();

            if (getSettings().getBoolean(EOD_CANCEL_WORKING, true)) {
                waitingForFill = false;
                fvgDetected = false;
                signalState = STATE_IDLE;
                debug("EOD: Cancelled pending setup");
            }

            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD: Forced flat at " + barTimeInt);
                resetTradeState();
            }

            eodProcessed = true;
            return;
        }

        // ===== Midday Exit (if enabled) =====
        boolean middayEnabled = getSettings().getBoolean(MIDDAY_EXIT_ENABLED, true);
        int middayTime = getSettings().getInteger(MIDDAY_EXIT_TIME, 1215);
        int exitModel = getSettings().getInteger(EXIT_MODEL, EXIT_TP1_TP2);

        if (middayEnabled && (exitModel == EXIT_TIME_MIDDAY || exitModel == EXIT_TP1_TP2) &&
            barTimeInt >= middayTime)
        {
            int position = ctx.getPosition();
            if (position != 0) {
                ctx.closeAtMarket();
                debug("Midday exit at " + barTimeInt);
                resetTradeState();
                return;
            }
        }

        // ===== Normal Exit Logic =====
        int position = ctx.getPosition();
        if (position == 0) return;

        double high = series.getHigh(index);
        double low = series.getLow(index);

        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);
        boolean partialEnabled = getSettings().getBoolean(PARTIAL_ENABLED, true);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);

        if (position > 0) {
            // Long position
            if (stopEnabled && stopPrice > 0 && low <= stopPrice) {
                ctx.closeAtMarket();
                debug("LONG stopped out at " + low);
                resetTradeState();
                return;
            }

            if (partialEnabled && !partialTaken && high >= tp1Price) {
                int partialQty = (int) Math.ceil(position * partialPct / 100.0);
                if (partialQty > 0 && partialQty < position) {
                    ctx.sell(partialQty);
                    partialTaken = true;
                    debug("Partial exit: " + partialQty + " at TP1=" + tp1Price);

                    // Move stop to breakeven after partial
                    if (exitModel == EXIT_SCALE_TRAIL) {
                        stopPrice = entryPrice;
                        debug("Stop moved to breakeven: " + stopPrice);
                    }
                }
            }

            if (high >= tp2Price) {
                ctx.closeAtMarket();
                debug("LONG target hit at " + high);
                resetTradeState();
            }

        } else {
            // Short position
            if (stopEnabled && stopPrice > 0 && high >= stopPrice) {
                ctx.closeAtMarket();
                debug("SHORT stopped out at " + high);
                resetTradeState();
                return;
            }

            if (partialEnabled && !partialTaken && low <= tp1Price) {
                int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
                if (partialQty > 0 && partialQty < Math.abs(position)) {
                    ctx.buy(partialQty);
                    partialTaken = true;
                    debug("Partial cover: " + partialQty + " at TP1=" + tp1Price);

                    if (exitModel == EXIT_SCALE_TRAIL) {
                        stopPrice = entryPrice;
                        debug("Stop moved to breakeven: " + stopPrice);
                    }
                }
            }

            if (low <= tp2Price) {
                ctx.closeAtMarket();
                debug("SHORT target hit at " + low);
                resetTradeState();
            }
        }
    }

    // ==================== Helper Methods ====================

    private void applyPresetDefaults() {
        // Note: In a full implementation, this would modify Settings based on preset
        // For now, we document the preset values and users can manually adjust
        int preset = getSettings().getInteger(PRESET_SELECTOR, PRESET_JADE_BALANCED);
        debug("Using preset: " + (preset == 0 ? "Jade Balanced" : preset == 1 ? "Jade Aggressive" : "Jade Conservative"));
    }

    private void updateSessionLevels(int timeInt, double high, double low) {
        // Asian session: 18:00-00:00 ET (previous day evening)
        // Actually in NY, Asian is roughly 7pm - 3am
        if (timeInt >= 1900 || timeInt < 300) {
            if (Double.isNaN(asianHigh) || high > asianHigh) asianHigh = high;
            if (Double.isNaN(asianLow) || low < asianLow) asianLow = low;
        } else if (!asianComplete && timeInt >= 300) {
            asianComplete = true;
        }

        // London session: 3:00-9:30 ET
        if (timeInt >= 300 && timeInt < 930) {
            if (Double.isNaN(londonHigh) || high > londonHigh) londonHigh = high;
            if (Double.isNaN(londonLow) || low < londonLow) londonLow = low;
        } else if (!londonComplete && timeInt >= 930) {
            londonComplete = true;
        }
    }

    private void resetDailyState() {
        signalState = STATE_IDLE;
        signalDirection = 0;
        targetLiqLevel = Double.NaN;
        sweepExtreme = Double.NaN;
        sweepDetected = false;
        mssLevel = Double.NaN;
        mssConfirmed = false;
        fvgTop = Double.NaN;
        fvgBottom = Double.NaN;
        fvgDetected = false;
        fvgBarIndex = -1;
        waitingForFill = false;
        entryBarIndex = -1;
        tradesToday = 0;
        eodProcessed = false;
        resetTradeState();
    }

    private void resetTradeState() {
        entryPrice = 0;
        stopPrice = 0;
        tp1Price = 0;
        tp2Price = 0;
        partialTaken = false;
        signalState = STATE_IDLE;
        signalDirection = 0;
        sweepDetected = false;
        mssConfirmed = false;
        fvgDetected = false;
    }

    private double findSSL(DataSeries series, int index, int strength) {
        // Find sell-side liquidity (lowest swing low or PDL)
        double swingLow = findSwingLow(series, index, strength);
        return !Double.isNaN(swingLow) ? Math.min(swingLow, pdl) : pdl;
    }

    private double findBSL(DataSeries series, int index, int strength) {
        // Find buy-side liquidity (highest swing high or PDH)
        double swingHigh = findSwingHigh(series, index, strength);
        return !Double.isNaN(swingHigh) ? Math.max(swingHigh, pdh) : pdh;
    }

    private double findSwingLow(DataSeries series, int index, int strength) {
        for (int i = index - strength - 1; i >= strength; i--) {
            double low = series.getLow(i);
            boolean isSwing = true;
            for (int j = 1; j <= strength && isSwing; j++) {
                if (i - j >= 0 && series.getLow(i - j) <= low) isSwing = false;
                if (i + j <= index && series.getLow(i + j) <= low) isSwing = false;
            }
            if (isSwing) return low;
        }
        return Double.NaN;
    }

    private double findSwingHigh(DataSeries series, int index, int strength) {
        for (int i = index - strength - 1; i >= strength; i--) {
            double high = series.getHigh(i);
            boolean isSwing = true;
            for (int j = 1; j <= strength && isSwing; j++) {
                if (i - j >= 0 && series.getHigh(i - j) >= high) isSwing = false;
                if (i + j <= index && series.getHigh(i + j) >= high) isSwing = false;
            }
            if (isSwing) return high;
        }
        return Double.NaN;
    }

    private int getDisplacementTicks(int strictness) {
        switch (strictness) {
            case STRICT_AGGRESSIVE: return 4;
            case STRICT_BALANCED: return 8;
            case STRICT_CONSERVATIVE: return 12;
            default: return 8;
        }
    }

    private boolean isInKillZone(int timeInt, int killZone) {
        switch (killZone) {
            case KZ_NY_AM:
                return timeInt >= 830 && timeInt < 1100;
            case KZ_NY_PM:
                return timeInt >= 1330 && timeInt < 1600;
            case KZ_LONDON_AM:
                return timeInt >= 300 && timeInt < 500;
            case KZ_CUSTOM:
                int start = getSettings().getInteger(KILL_ZONE_CUSTOM_START, 930);
                int end = getSettings().getInteger(KILL_ZONE_CUSTOM_END, 1130);
                return timeInt >= start && timeInt < end;
            default:
                return true;
        }
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

    @Override
    public void clearState() {
        super.clearState();
        resetDailyState();
        lastResetDay = -1;
        pdh = Double.NaN;
        pdl = Double.NaN;
        todayHigh = Double.NaN;
        todayLow = Double.NaN;
        asianHigh = Double.NaN;
        asianLow = Double.NaN;
        londonHigh = Double.NaN;
        londonLow = Double.NaN;
        asianComplete = false;
        londonComplete = false;
    }
}
