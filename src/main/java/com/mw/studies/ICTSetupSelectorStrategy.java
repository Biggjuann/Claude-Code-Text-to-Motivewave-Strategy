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
 * ICT Setup Selector Suite (JadeCap-style) with Preset Pack + Dual MMBM/MMSM
 *
 * A multi-setup ICT-style strategy that supports:
 * - MMBM (Buy Model): SSL sweep → MSS up → FVG entry
 * - MMSM (Sell Model): BSL sweep → MSS down → FVG entry
 * - Session Liquidity Raid, London-NY Reversal, Daily PO3
 * - **Dual Mode**: Run both MMBM and MMSM concurrently
 *
 * Features:
 * - Preset system (Jade Balanced, Aggressive, Conservative)
 * - Configurable liquidity references (PDH/PDL, Session H/L, Custom)
 * - Multiple kill zone presets (NY AM, NY PM, London)
 * - Per-side trade limits for dual mode
 * - Structural stop loss with buffer
 * - Multiple exit models (R:R, TP1+TP2, Scale+Trail, Time Exit)
 * - EOD forced flattening
 *
 * @version 2.0.0
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
    private static final String SETUP_MODE = "setupMode";
    private static final String SETUP_SELECTOR = "setupSelector";

    // Sessions
    private static final String TRADE_WINDOW_ALWAYS_ON = "tradeWindowAlwaysOn";
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
    private static final String MAX_TRADES_PER_SIDE = "maxTradesPerSide";
    private static final String ONE_TRADE_AT_A_TIME = "oneTradeAtATime";
    private static final String ALLOW_OPPOSITE_SIDE = "allowOppositeSide";

    // Sizing
    private static final String CONTRACTS = "contracts";

    // Structure
    private static final String PIVOT_STRENGTH = "pivotStrength";

    // Liquidity
    private static final String SWEEP_MIN_TICKS = "sweepMinTicks";
    private static final String REQUIRE_CLOSE_BACK = "requireCloseBack";
    private static final String MMBM_SSL_REF = "mmbmSslRef";
    private static final String MMSM_BSL_REF = "mmsmBslRef";
    private static final String LIQ_SESSION_START = "liqSessionStart";
    private static final String LIQ_SESSION_END = "liqSessionEnd";
    private static final String CUSTOM_LIQ_LEVEL = "customLiqLevel";

    // Deeper Liquidity (Stronger Setups)
    private static final String MMBM_PWL_ENABLED = "mmbmPwlEnabled";
    private static final String MMBM_MAJOR_SWING_ENABLED = "mmbmMajorSwingEnabled";
    private static final String MAJOR_SWING_LOOKBACK = "majorSwingLookback";
    private static final String REQUIRE_DEEPER_LIQ = "requireDeeperLiq";
    private static final String MMSM_PWH_ENABLED = "mmsmPwhEnabled";
    private static final String MMSM_MAJOR_SWING_HIGH_ENABLED = "mmsmMajorSwingHighEnabled";

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
    private static final String SSL_PATH = "sslPath";
    private static final String BSL_PATH = "bslPath";
    private static final String PWL_PATH = "pwlPath";
    private static final String PWH_PATH = "pwhPath";
    private static final String MAJOR_SWING_LOW_PATH = "majorSwingLowPath";
    private static final String MAJOR_SWING_HIGH_PATH = "majorSwingHighPath";

    // ==================== Mode Constants ====================
    // Presets
    private static final int PRESET_JADE_BALANCED = 0;
    private static final int PRESET_JADE_AGGRESSIVE = 1;
    private static final int PRESET_JADE_CONSERVATIVE = 2;

    // Setup Modes
    private static final int MODE_SINGLE = 0;
    private static final int MODE_BOTH_MMBM_MMSM = 1;

    // Setups (for single mode)
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

    // Liquidity References
    private static final int LIQ_REF_PREV_DAY = 0;
    private static final int LIQ_REF_SESSION = 1;
    private static final int LIQ_REF_CUSTOM = 2;

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
        PDH, PDL, EQUILIBRIUM, SSL_LEVEL, BSL_LEVEL,
        SESSION_HIGH, SESSION_LOW,
        PWH, PWL, MAJOR_SWING_HIGH, MAJOR_SWING_LOW
    }

    // ==================== Signals ====================
    enum Signals { SSL_SWEEP, BSL_SWEEP, MSS_UP, MSS_DOWN, ENTRY_LONG, ENTRY_SHORT }

    // ==================== State Machine ====================
    private static final int STATE_IDLE = 0;
    private static final int STATE_SWEEP_DETECTED = 1;
    private static final int STATE_MSS_PENDING = 2;
    private static final int STATE_ENTRY_READY = 3;
    private static final int STATE_IN_TRADE = 4;

    // ==================== State Variables ====================
    // Separate state for MMBM (long) and MMSM (short) when in dual mode
    private int mmbmState = STATE_IDLE;
    private int mmsmState = STATE_IDLE;

    // Daily tracking
    private double pdh = Double.NaN;
    private double pdl = Double.NaN;
    private double todayHigh = Double.NaN;
    private double todayLow = Double.NaN;
    private int lastResetDay = -1;

    // Weekly tracking (Previous Week High/Low)
    private double pwh = Double.NaN;
    private double pwl = Double.NaN;
    private double thisWeekHigh = Double.NaN;
    private double thisWeekLow = Double.NaN;
    private int lastResetWeek = -1;

    // Major swing levels (HTF)
    private double majorSwingHigh = Double.NaN;
    private double majorSwingLow = Double.NaN;

    // Sweep strength tracking
    private int mmbmSweepStrength = 0; // 0=none, 1=PDL, 2=PWL, 3=major swing
    private int mmsmSweepStrength = 0; // 0=none, 1=PDH, 2=PWH, 3=major swing

    // Session liquidity tracking
    private double sessionHigh = Double.NaN;
    private double sessionLow = Double.NaN;
    private boolean inLiquiditySession = false;

    // MMBM state (long setup)
    private double mmbmSslLevel = Double.NaN;
    private double mmbmSweepLow = Double.NaN;
    private double mmbmMssLevel = Double.NaN;
    private boolean mmbmSweepDetected = false;
    private boolean mmbmMssConfirmed = false;
    private double mmbmFvgTop = Double.NaN;
    private double mmbmFvgBottom = Double.NaN;
    private boolean mmbmFvgDetected = false;
    private int mmbmFvgBarIndex = -1;
    private boolean mmbmWaitingForFill = false;
    private int mmbmEntryBarIndex = -1;

    // MMSM state (short setup)
    private double mmsmBslLevel = Double.NaN;
    private double mmsmSweepHigh = Double.NaN;
    private double mmsmMssLevel = Double.NaN;
    private boolean mmsmSweepDetected = false;
    private boolean mmsmMssConfirmed = false;
    private double mmsmFvgTop = Double.NaN;
    private double mmsmFvgBottom = Double.NaN;
    private boolean mmsmFvgDetected = false;
    private int mmsmFvgBarIndex = -1;
    private boolean mmsmWaitingForFill = false;
    private int mmsmEntryBarIndex = -1;

    // Trade tracking
    private int tradesToday = 0;
    private int longTradesToday = 0;
    private int shortTradesToday = 0;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double tp1Price = 0;
    private double tp2Price = 0;
    private boolean partialTaken = false;
    private boolean eodProcessed = false;
    private int currentDirection = 0; // 1=long, -1=short, 0=flat

    // NY timezone
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Presets Tab =====
        var tab = sd.addTab("Presets");
        var grp = tab.addGroup("Preset & Mode Selection");
        grp.addRow(new IntegerDescriptor(PRESET_SELECTOR,
            "Preset Pack (0=Balanced, 1=Aggressive, 2=Conservative)", PRESET_JADE_BALANCED, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(SETUP_MODE,
            "Setup Mode (0=Single, 1=Both MMBM+MMSM)", MODE_BOTH_MMBM_MMSM, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(SETUP_SELECTOR,
            "Setup (Single Mode: 0=MMBM, 1=MMSM, 2=SessionRaid, 3=LondonNY, 4=DailyPO3)", SETUP_MMBM, 0, 4, 1));

        // ===== Sessions Tab =====
        tab = sd.addTab("Sessions");
        grp = tab.addGroup("Trade Window (ET)");
        grp.addRow(new BooleanDescriptor(TRADE_WINDOW_ALWAYS_ON, "Always On (Ignore Time Filter)", false));
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
        grp.addRow(new IntegerDescriptor(MAX_TRADES_PER_SIDE, "Max Trades Per Side Per Day", 1, 1, 5, 1));
        grp.addRow(new BooleanDescriptor(ONE_TRADE_AT_A_TIME, "One Trade At A Time", true));
        grp.addRow(new BooleanDescriptor(ALLOW_OPPOSITE_SIDE, "Allow Opposite Side While In Position", false));
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 1, 1, 100, 1));

        // ===== Liquidity Tab =====
        tab = sd.addTab("Liquidity");
        grp = tab.addGroup("MMBM/MMSM Reference Levels");
        grp.addRow(new IntegerDescriptor(MMBM_SSL_REF,
            "MMBM SSL Reference (0=PDL, 1=Session Low, 2=Custom)", LIQ_REF_PREV_DAY, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(MMSM_BSL_REF,
            "MMSM BSL Reference (0=PDH, 1=Session High, 2=Custom)", LIQ_REF_PREV_DAY, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(LIQ_SESSION_START, "Liquidity Session Start (HHMM)", 2000, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(LIQ_SESSION_END, "Liquidity Session End (HHMM)", 0, 0, 2359, 1));
        grp.addRow(new DoubleDescriptor(CUSTOM_LIQ_LEVEL, "Custom Liquidity Level", 0.0, 0.0, 100000.0, 0.25));

        grp = tab.addGroup("Deeper Liquidity (Stronger Setups)");
        grp.addRow(new BooleanDescriptor(MMBM_PWL_ENABLED, "MMBM: Track Previous Week Low (PWL)", true));
        grp.addRow(new BooleanDescriptor(MMBM_MAJOR_SWING_ENABLED, "MMBM: Track Major Swing Low (HTF)", true));
        grp.addRow(new BooleanDescriptor(MMSM_PWH_ENABLED, "MMSM: Track Previous Week High (PWH)", true));
        grp.addRow(new BooleanDescriptor(MMSM_MAJOR_SWING_HIGH_ENABLED, "MMSM: Track Major Swing High (HTF)", true));
        grp.addRow(new IntegerDescriptor(MAJOR_SWING_LOOKBACK, "Major Swing Lookback (bars)", 100, 20, 500, 10));
        grp.addRow(new BooleanDescriptor(REQUIRE_DEEPER_LIQ, "Require Deeper Liquidity for Entry", false));

        grp = tab.addGroup("Sweep Detection");
        grp.addRow(new IntegerDescriptor(SWEEP_MIN_TICKS, "Min Sweep Penetration (ticks)", 2, 1, 50, 1));
        grp.addRow(new BooleanDescriptor(REQUIRE_CLOSE_BACK, "Require Close Back Through Level", true));

        // ===== Structure Tab =====
        tab = sd.addTab("Structure");
        grp = tab.addGroup("Pivot/Swing Detection");
        grp.addRow(new IntegerDescriptor(PIVOT_STRENGTH, "Pivot Strength (L/R bars)", 2, 1, 10, 1));

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

        grp = tab.addGroup("Liquidity Levels");
        grp.addRow(new PathDescriptor(SSL_PATH, "SSL Level (MMBM)",
            defaults.getGreen(), 2.0f, null, true, true, true));
        grp.addRow(new PathDescriptor(BSL_PATH, "BSL Level (MMSM)",
            defaults.getRed(), 2.0f, null, true, true, true));

        grp = tab.addGroup("Deeper Liquidity Levels");
        grp.addRow(new PathDescriptor(PWL_PATH, "Previous Week Low (PWL)",
            new java.awt.Color(0, 180, 0), 2.0f, new float[]{6, 3}, true, true, true));
        grp.addRow(new PathDescriptor(PWH_PATH, "Previous Week High (PWH)",
            new java.awt.Color(180, 0, 0), 2.0f, new float[]{6, 3}, true, true, true));
        grp.addRow(new PathDescriptor(MAJOR_SWING_LOW_PATH, "Major Swing Low (HTF)",
            new java.awt.Color(0, 255, 100), 2.5f, new float[]{10, 5}, true, true, true));
        grp.addRow(new PathDescriptor(MAJOR_SWING_HIGH_PATH, "Major Swing High (HTF)",
            new java.awt.Color(255, 100, 0), 2.5f, new float[]{10, 5}, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(PRESET_SELECTOR, SETUP_MODE, CONTRACTS, MAX_TRADES_PER_DAY);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(PRESET_SELECTOR, SETUP_MODE, RR_MULTIPLE);

        desc.exportValue(new ValueDescriptor(Values.PDH, "PDH", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.PDL, "PDL", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.EQUILIBRIUM, "Equilibrium", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.SSL_LEVEL, "SSL Level", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.BSL_LEVEL, "BSL Level", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.PWL, "PWL", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.PWH, "PWH", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.MAJOR_SWING_LOW, "Major Swing Low", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.MAJOR_SWING_HIGH, "Major Swing High", new String[]{}));

        desc.declarePath(Values.PDH, PDH_PATH);
        desc.declarePath(Values.PDL, PDL_PATH);
        desc.declarePath(Values.EQUILIBRIUM, EQ_PATH);
        desc.declarePath(Values.SSL_LEVEL, SSL_PATH);
        desc.declarePath(Values.BSL_LEVEL, BSL_PATH);
        desc.declarePath(Values.PWL, PWL_PATH);
        desc.declarePath(Values.PWH, PWH_PATH);
        desc.declarePath(Values.MAJOR_SWING_LOW, MAJOR_SWING_LOW_PATH);
        desc.declarePath(Values.MAJOR_SWING_HIGH, MAJOR_SWING_HIGH_PATH);

        desc.declareSignal(Signals.SSL_SWEEP, "SSL Sweep Detected");
        desc.declareSignal(Signals.BSL_SWEEP, "BSL Sweep Detected");
        desc.declareSignal(Signals.MSS_UP, "MSS Up Confirmed");
        desc.declareSignal(Signals.MSS_DOWN, "MSS Down Confirmed");
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

        // Weekly reset (for PWH/PWL)
        int barWeek = getWeekOfYear(barTime, NY_TZ);
        if (barWeek != lastResetWeek) {
            if (!Double.isNaN(thisWeekHigh) && !Double.isNaN(thisWeekLow)) {
                pwh = thisWeekHigh;
                pwl = thisWeekLow;
            }
            thisWeekHigh = Double.NaN;
            thisWeekLow = Double.NaN;
            lastResetWeek = barWeek;
        }

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

        // Track this week's high/low
        if (Double.isNaN(thisWeekHigh) || high > thisWeekHigh) thisWeekHigh = high;
        if (Double.isNaN(thisWeekLow) || low < thisWeekLow) thisWeekLow = low;

        // Track liquidity session high/low
        updateLiquiditySessionLevels(barTimeInt, high, low);

        // Plot levels
        if (!Double.isNaN(pdh)) {
            series.setDouble(index, Values.PDH, pdh);
            series.setDouble(index, Values.PDL, pdl);
            series.setDouble(index, Values.EQUILIBRIUM, (pdh + pdl) / 2.0);
        }

        // Plot PWH/PWL if enabled
        boolean pwlEnabled = getSettings().getBoolean(MMBM_PWL_ENABLED, true);
        boolean pwhEnabled = getSettings().getBoolean(MMSM_PWH_ENABLED, true);
        if (pwlEnabled && !Double.isNaN(pwl)) {
            series.setDouble(index, Values.PWL, pwl);
        }
        if (pwhEnabled && !Double.isNaN(pwh)) {
            series.setDouble(index, Values.PWH, pwh);
        }

        // Calculate and plot major swing levels
        boolean majorSwingLowEnabled = getSettings().getBoolean(MMBM_MAJOR_SWING_ENABLED, true);
        boolean majorSwingHighEnabled = getSettings().getBoolean(MMSM_MAJOR_SWING_HIGH_ENABLED, true);
        int majorSwingLookback = getSettings().getInteger(MAJOR_SWING_LOOKBACK, 100);

        if (majorSwingLowEnabled && index > majorSwingLookback) {
            majorSwingLow = findMajorSwingLow(series, index, majorSwingLookback);
            if (!Double.isNaN(majorSwingLow)) {
                series.setDouble(index, Values.MAJOR_SWING_LOW, majorSwingLow);
            }
        }
        if (majorSwingHighEnabled && index > majorSwingLookback) {
            majorSwingHigh = findMajorSwingHigh(series, index, majorSwingLookback);
            if (!Double.isNaN(majorSwingHigh)) {
                series.setDouble(index, Values.MAJOR_SWING_HIGH, majorSwingHigh);
            }
        }

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (Double.isNaN(pdh) || Double.isNaN(pdl)) return;

        // Get settings
        int setupMode = getSettings().getInteger(SETUP_MODE, MODE_BOTH_MMBM_MMSM);
        int setupSelector = getSettings().getInteger(SETUP_SELECTOR, SETUP_MMBM);
        boolean alwaysOn = getSettings().getBoolean(TRADE_WINDOW_ALWAYS_ON, false);
        int tradeStart = getSettings().getInteger(TRADE_START, 930);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1130);
        int killZonePreset = getSettings().getInteger(KILL_ZONE_PRESET, KZ_NY_AM);
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_DAY, 1);
        int maxPerSide = getSettings().getInteger(MAX_TRADES_PER_SIDE, 1);
        boolean oneAtATime = getSettings().getBoolean(ONE_TRADE_AT_A_TIME, true);
        boolean allowOpposite = getSettings().getBoolean(ALLOW_OPPOSITE_SIDE, false);
        int pivotStrength = getSettings().getInteger(PIVOT_STRENGTH, 2);
        int sweepMinTicks = getSettings().getInteger(SWEEP_MIN_TICKS, 2);
        boolean requireCloseBack = getSettings().getBoolean(REQUIRE_CLOSE_BACK, true);
        int entryModel = getSettings().getInteger(ENTRY_MODEL_PREFERENCE, ENTRY_BOTH);
        int fvgMinTicks = getSettings().getInteger(FVG_MIN_TICKS, 2);
        boolean requireMSSClose = getSettings().getBoolean(REQUIRE_MSS_CLOSE, true);
        int strictness = getSettings().getInteger(CONFIRMATION_STRICTNESS, STRICT_BALANCED);

        // Check session/killzone (bypass if always on)
        boolean inTradeSession = alwaysOn || (barTimeInt >= tradeStart && barTimeInt < tradeEnd);
        boolean inKillZone = alwaysOn || isInKillZone(barTimeInt, killZonePreset);

        // Check EOD cutoff
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1640);
        boolean pastEodCutoff = eodEnabled && barTimeInt >= eodTime;

        // Base trade gate
        boolean baseCanTrade = inTradeSession && inKillZone && tradesToday < maxTrades && !pastEodCutoff;

        // Resolve liquidity levels
        mmbmSslLevel = resolveSSLLevel(series, index, pivotStrength);
        mmsmBslLevel = resolveBSLLevel(series, index, pivotStrength);

        // Plot liquidity levels
        if (!Double.isNaN(mmbmSslLevel)) series.setDouble(index, Values.SSL_LEVEL, mmbmSslLevel);
        if (!Double.isNaN(mmsmBslLevel)) series.setDouble(index, Values.BSL_LEVEL, mmsmBslLevel);

        // Determine which setups to evaluate
        boolean evalMMBM = (setupMode == MODE_BOTH_MMBM_MMSM) || (setupMode == MODE_SINGLE && setupSelector == SETUP_MMBM);
        boolean evalMMSM = (setupMode == MODE_BOTH_MMBM_MMSM) || (setupMode == MODE_SINGLE && setupSelector == SETUP_MMSM);

        // Check per-side limits and position constraints
        boolean canTradeLong = baseCanTrade && longTradesToday < maxPerSide;
        boolean canTradeShort = baseCanTrade && shortTradesToday < maxPerSide;

        if (oneAtATime && currentDirection != 0) {
            if (!allowOpposite) {
                canTradeLong = false;
                canTradeShort = false;
            } else {
                // Allow opposite side only
                if (currentDirection > 0) canTradeLong = false;
                if (currentDirection < 0) canTradeShort = false;
            }
        }

        // Process MMBM (long setup)
        if (evalMMBM) {
            processMMBM(ctx, series, index, tickSize, pivotStrength, sweepMinTicks, fvgMinTicks,
                entryModel, requireMSSClose, requireCloseBack, strictness, canTradeLong,
                high, low, close, open, barTime);
        }

        // Process MMSM (short setup)
        if (evalMMSM) {
            processMMSM(ctx, series, index, tickSize, pivotStrength, sweepMinTicks, fvgMinTicks,
                entryModel, requireMSSClose, requireCloseBack, strictness, canTradeShort,
                high, low, close, open, barTime);
        }

        // Handle single-mode other setups
        if (setupMode == MODE_SINGLE) {
            switch (setupSelector) {
                case SETUP_SESSION_RAID:
                case SETUP_LONDON_NY:
                case SETUP_DAILY_PO3:
                    // These use combined state, simplified for this version
                    break;
            }
        }

        // Check for entry cancellation (max bars exceeded)
        int maxBars = getSettings().getInteger(MAX_BARS_TO_FILL, 30);
        if (mmbmWaitingForFill && mmbmEntryBarIndex > 0 && index - mmbmEntryBarIndex > maxBars) {
            resetMMBMState();
            debug("MMBM entry cancelled - max bars exceeded");
        }
        if (mmsmWaitingForFill && mmsmEntryBarIndex > 0 && index - mmsmEntryBarIndex > maxBars) {
            resetMMSMState();
            debug("MMSM entry cancelled - max bars exceeded");
        }

        series.setComplete(index);
    }

    // ==================== MMBM Processing ====================

    private void processMMBM(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int sweepMinTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, boolean requireCloseBack, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // Get deeper liquidity settings
        boolean pwlEnabled = getSettings().getBoolean(MMBM_PWL_ENABLED, true);
        boolean majorSwingEnabled = getSettings().getBoolean(MMBM_MAJOR_SWING_ENABLED, true);
        boolean requireDeeperLiq = getSettings().getBoolean(REQUIRE_DEEPER_LIQ, false);

        // Phase 1: Detect SSL sweep (check deepest levels first for strength)
        if (mmbmState == STATE_IDLE && canTrade && !Double.isNaN(mmbmSslLevel)) {
            double sweepThreshold = mmbmSslLevel - (sweepMinTicks * tickSize);
            if (low <= sweepThreshold) {
                boolean validSweep = !requireCloseBack || (close > mmbmSslLevel);
                if (strictness == STRICT_AGGRESSIVE) validSweep = true;

                if (validSweep) {
                    // Determine sweep strength - check deepest levels first
                    mmbmSweepStrength = 1; // Default: PDL sweep
                    String sweepType = "PDL";

                    // Check if also swept PWL (deeper)
                    if (pwlEnabled && !Double.isNaN(pwl)) {
                        double pwlThreshold = pwl - (sweepMinTicks * tickSize);
                        if (low <= pwlThreshold) {
                            mmbmSweepStrength = 2;
                            sweepType = "PWL";
                        }
                    }

                    // Check if also swept Major Swing Low (deepest)
                    if (majorSwingEnabled && !Double.isNaN(majorSwingLow)) {
                        double majorThreshold = majorSwingLow - (sweepMinTicks * tickSize);
                        if (low <= majorThreshold) {
                            mmbmSweepStrength = 3;
                            sweepType = "MAJOR SWING LOW";
                        }
                    }

                    // If require deeper liquidity and only PDL swept, skip
                    if (requireDeeperLiq && mmbmSweepStrength == 1) {
                        debug("MMBM: PDL sweep detected but deeper liquidity required - skipping");
                        return;
                    }

                    mmbmSweepDetected = true;
                    mmbmSweepLow = low;
                    mmbmState = STATE_SWEEP_DETECTED;
                    mmbmMssLevel = findSwingHigh(series, index, pivotStrength);

                    String strengthLabel = mmbmSweepStrength == 3 ? " [STRONGEST]" :
                                           mmbmSweepStrength == 2 ? " [STRONG]" : "";
                    ctx.signal(index, Signals.SSL_SWEEP,
                        String.format("%s Sweep: Low=%.2f%s", sweepType, low, strengthLabel), low);
                    debug("MMBM: " + sweepType + " sweep at " + low + " (strength=" + mmbmSweepStrength + ")");
                }
            }
        }

        // Update sweep extreme
        if (mmbmState == STATE_SWEEP_DETECTED && low < mmbmSweepLow) {
            mmbmSweepLow = low;
        }

        // Phase 2: Detect MSS Up
        if (mmbmState == STATE_SWEEP_DETECTED && !Double.isNaN(mmbmMssLevel)) {
            boolean mssBreak = requireMSSClose ? (close > mmbmMssLevel) : (high > mmbmMssLevel);
            if (mssBreak) {
                int dispTicks = getDisplacementTicks(strictness);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispTicks * tickSize || strictness == STRICT_AGGRESSIVE) {
                    mmbmMssConfirmed = true;
                    mmbmState = STATE_MSS_PENDING;
                    ctx.signal(index, Signals.MSS_UP, "MMBM MSS Up Confirmed", close);
                    debug("MMBM: MSS Up at " + close);

                    if (entryModel == ENTRY_IMMEDIATE || entryModel == ENTRY_MSS_MARKET) {
                        mmbmState = STATE_ENTRY_READY;
                    }
                }
            }
        }

        // Phase 3: Detect Bullish FVG
        if ((mmbmState == STATE_MSS_PENDING || mmbmState == STATE_SWEEP_DETECTED) &&
            index >= 2 && (entryModel == ENTRY_FVG_ONLY || entryModel == ENTRY_BOTH))
        {
            double bar0High = series.getHigh(index - 2);
            double bar2Low = series.getLow(index);
            if (bar2Low > bar0High && (bar2Low - bar0High) >= fvgMinTicks * tickSize) {
                mmbmFvgTop = bar2Low;
                mmbmFvgBottom = bar0High;
                mmbmFvgDetected = true;
                mmbmFvgBarIndex = index;
                mmbmState = STATE_ENTRY_READY;
                debug("MMBM: Bullish FVG: " + mmbmFvgBottom + " - " + mmbmFvgTop);
            }
        }

        // Phase 4: Generate entry signal
        if (mmbmState == STATE_ENTRY_READY && canTrade && !mmbmWaitingForFill) {
            mmbmWaitingForFill = true;
            mmbmEntryBarIndex = index;

            String strengthLabel = mmbmSweepStrength == 3 ? " [MAJOR SWING]" :
                                   mmbmSweepStrength == 2 ? " [PWL]" : "";
            ctx.signal(index, Signals.ENTRY_LONG, "MMBM Long Ready" + strengthLabel, close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                String markerLabel = mmbmSweepStrength >= 2 ? "MMBM+" : "MMBM";
                addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, markerLabel));
            }
        }
    }

    // ==================== MMSM Processing ====================

    private void processMMSM(DataContext ctx, DataSeries series, int index, double tickSize,
            int pivotStrength, int sweepMinTicks, int fvgMinTicks, int entryModel,
            boolean requireMSSClose, boolean requireCloseBack, int strictness, boolean canTrade,
            double high, double low, double close, double open, long barTime)
    {
        // Get deeper liquidity settings
        boolean pwhEnabled = getSettings().getBoolean(MMSM_PWH_ENABLED, true);
        boolean majorSwingEnabled = getSettings().getBoolean(MMSM_MAJOR_SWING_HIGH_ENABLED, true);
        boolean requireDeeperLiq = getSettings().getBoolean(REQUIRE_DEEPER_LIQ, false);

        // Phase 1: Detect BSL sweep (check deepest levels first for strength)
        if (mmsmState == STATE_IDLE && canTrade && !Double.isNaN(mmsmBslLevel)) {
            double sweepThreshold = mmsmBslLevel + (sweepMinTicks * tickSize);
            if (high >= sweepThreshold) {
                boolean validSweep = !requireCloseBack || (close < mmsmBslLevel);
                if (strictness == STRICT_AGGRESSIVE) validSweep = true;

                if (validSweep) {
                    // Determine sweep strength - check deepest levels first
                    mmsmSweepStrength = 1; // Default: PDH sweep
                    String sweepType = "PDH";

                    // Check if also swept PWH (deeper)
                    if (pwhEnabled && !Double.isNaN(pwh)) {
                        double pwhThreshold = pwh + (sweepMinTicks * tickSize);
                        if (high >= pwhThreshold) {
                            mmsmSweepStrength = 2;
                            sweepType = "PWH";
                        }
                    }

                    // Check if also swept Major Swing High (deepest)
                    if (majorSwingEnabled && !Double.isNaN(majorSwingHigh)) {
                        double majorThreshold = majorSwingHigh + (sweepMinTicks * tickSize);
                        if (high >= majorThreshold) {
                            mmsmSweepStrength = 3;
                            sweepType = "MAJOR SWING HIGH";
                        }
                    }

                    // If require deeper liquidity and only PDH swept, skip
                    if (requireDeeperLiq && mmsmSweepStrength == 1) {
                        debug("MMSM: PDH sweep detected but deeper liquidity required - skipping");
                        return;
                    }

                    mmsmSweepDetected = true;
                    mmsmSweepHigh = high;
                    mmsmState = STATE_SWEEP_DETECTED;
                    mmsmMssLevel = findSwingLow(series, index, pivotStrength);

                    String strengthLabel = mmsmSweepStrength == 3 ? " [STRONGEST]" :
                                           mmsmSweepStrength == 2 ? " [STRONG]" : "";
                    ctx.signal(index, Signals.BSL_SWEEP,
                        String.format("%s Sweep: High=%.2f%s", sweepType, high, strengthLabel), high);
                    debug("MMSM: " + sweepType + " sweep at " + high + " (strength=" + mmsmSweepStrength + ")");
                }
            }
        }

        // Update sweep extreme
        if (mmsmState == STATE_SWEEP_DETECTED && high > mmsmSweepHigh) {
            mmsmSweepHigh = high;
        }

        // Phase 2: Detect MSS Down
        if (mmsmState == STATE_SWEEP_DETECTED && !Double.isNaN(mmsmMssLevel)) {
            boolean mssBreak = requireMSSClose ? (close < mmsmMssLevel) : (low < mmsmMssLevel);
            if (mssBreak) {
                int dispTicks = getDisplacementTicks(strictness);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispTicks * tickSize || strictness == STRICT_AGGRESSIVE) {
                    mmsmMssConfirmed = true;
                    mmsmState = STATE_MSS_PENDING;
                    ctx.signal(index, Signals.MSS_DOWN, "MMSM MSS Down Confirmed", close);
                    debug("MMSM: MSS Down at " + close);

                    if (entryModel == ENTRY_IMMEDIATE || entryModel == ENTRY_MSS_MARKET) {
                        mmsmState = STATE_ENTRY_READY;
                    }
                }
            }
        }

        // Phase 3: Detect Bearish FVG
        if ((mmsmState == STATE_MSS_PENDING || mmsmState == STATE_SWEEP_DETECTED) &&
            index >= 2 && (entryModel == ENTRY_FVG_ONLY || entryModel == ENTRY_BOTH))
        {
            double bar0Low = series.getLow(index - 2);
            double bar2High = series.getHigh(index);
            if (bar2High < bar0Low && (bar0Low - bar2High) >= fvgMinTicks * tickSize) {
                mmsmFvgTop = bar0Low;
                mmsmFvgBottom = bar2High;
                mmsmFvgDetected = true;
                mmsmFvgBarIndex = index;
                mmsmState = STATE_ENTRY_READY;
                debug("MMSM: Bearish FVG: " + mmsmFvgBottom + " - " + mmsmFvgTop);
            }
        }

        // Phase 4: Generate entry signal
        if (mmsmState == STATE_ENTRY_READY && canTrade && !mmsmWaitingForFill) {
            mmsmWaitingForFill = true;
            mmsmEntryBarIndex = index;

            String strengthLabel = mmsmSweepStrength == 3 ? " [MAJOR SWING]" :
                                   mmsmSweepStrength == 2 ? " [PWH]" : "";
            ctx.signal(index, Signals.ENTRY_SHORT, "MMSM Short Ready" + strengthLabel, close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                String markerLabel = mmsmSweepStrength >= 2 ? "MMSM+" : "MMSM";
                addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, markerLabel));
            }
        }
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("ICT Setup Selector v2.0 activated");
        int preset = getSettings().getInteger(PRESET_SELECTOR, PRESET_JADE_BALANCED);
        int mode = getSettings().getInteger(SETUP_MODE, MODE_BOTH_MMBM_MMSM);
        debug("Preset: " + (preset == 0 ? "Balanced" : preset == 1 ? "Aggressive" : "Conservative"));
        debug("Mode: " + (mode == 0 ? "Single Setup" : "Both MMBM+MMSM"));
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
        boolean allowOpposite = getSettings().getBoolean(ALLOW_OPPOSITE_SIDE, false);

        if (oneAtATime && position != 0 && !allowOpposite) {
            debug("Already in position, ignoring signal");
            return;
        }

        int qty = getSettings().getInteger(CONTRACTS, 1);
        int stopMode = getSettings().getInteger(STOPLOSS_MODE, STOP_STRUCTURAL);
        int stopTicks = getSettings().getInteger(STOPLOSS_TICKS, 20);
        int exitModel = getSettings().getInteger(EXIT_MODEL, EXIT_TP1_TP2);
        double rrMult = getSettings().getDouble(RR_MULTIPLE, 2.0);
        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);

        boolean isLong = (signal == Signals.ENTRY_LONG);

        if (isLong) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();
            currentDirection = 1;

            if (stopEnabled) {
                double stopBuffer = stopTicks * tickSize;
                if (stopMode == STOP_STRUCTURAL && !Double.isNaN(mmbmSweepLow)) {
                    stopPrice = mmbmSweepLow - stopBuffer;
                } else {
                    stopPrice = entryPrice - stopBuffer;
                }
                stopPrice = instr.round(stopPrice);
            }

            double risk = entryPrice - stopPrice;
            double equilibrium = (pdh + pdl) / 2.0;
            tp1Price = equilibrium;

            switch (exitModel) {
                case EXIT_RR:
                    tp2Price = entryPrice + (risk * rrMult);
                    break;
                default:
                    tp2Price = pdh;
            }
            tp2Price = instr.round(tp2Price);

            debug(String.format("LONG: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
                qty, entryPrice, stopPrice, tp1Price, tp2Price));

            tradesToday++;
            longTradesToday++;
            mmbmWaitingForFill = false;
            mmbmState = STATE_IN_TRADE;

        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();
            currentDirection = -1;

            if (stopEnabled) {
                double stopBuffer = stopTicks * tickSize;
                if (stopMode == STOP_STRUCTURAL && !Double.isNaN(mmsmSweepHigh)) {
                    stopPrice = mmsmSweepHigh + stopBuffer;
                } else {
                    stopPrice = entryPrice + stopBuffer;
                }
                stopPrice = instr.round(stopPrice);
            }

            double risk = stopPrice - entryPrice;
            double equilibrium = (pdh + pdl) / 2.0;
            tp1Price = equilibrium;

            switch (exitModel) {
                case EXIT_RR:
                    tp2Price = entryPrice - (risk * rrMult);
                    break;
                default:
                    tp2Price = pdl;
            }
            tp2Price = instr.round(tp2Price);

            debug(String.format("SHORT: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
                qty, entryPrice, stopPrice, tp1Price, tp2Price));

            tradesToday++;
            shortTradesToday++;
            mmsmWaitingForFill = false;
            mmsmState = STATE_IN_TRADE;
        }

        partialTaken = false;
    }

    @Override
    public void onBarClose(OrderContext ctx) {
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        // ===== EOD FLATTEN =====
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1640);

        if (eodEnabled && barTimeInt >= eodTime && !eodProcessed) {
            int position = ctx.getPosition();

            if (getSettings().getBoolean(EOD_CANCEL_WORKING, true)) {
                resetMMBMState();
                resetMMSMState();
                debug("EOD: Cancelled pending setups");
            }

            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD: Forced flat at " + barTimeInt);
                resetTradeState();
            }

            eodProcessed = true;
            return;
        }

        // ===== Midday Exit =====
        boolean middayEnabled = getSettings().getBoolean(MIDDAY_EXIT_ENABLED, true);
        int middayTime = getSettings().getInteger(MIDDAY_EXIT_TIME, 1215);
        int exitModel = getSettings().getInteger(EXIT_MODEL, EXIT_TP1_TP2);

        if (middayEnabled && exitModel == EXIT_TIME_MIDDAY && barTimeInt >= middayTime) {
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

                    if (exitModel == EXIT_SCALE_TRAIL) {
                        stopPrice = entryPrice;
                        debug("Stop moved to breakeven");
                    }
                }
            }

            if (high >= tp2Price) {
                ctx.closeAtMarket();
                debug("LONG target hit at " + high);
                resetTradeState();
            }

        } else {
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
                        debug("Stop moved to breakeven");
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

    private double resolveSSLLevel(DataSeries series, int index, int pivotStrength) {
        int ref = getSettings().getInteger(MMBM_SSL_REF, LIQ_REF_PREV_DAY);
        switch (ref) {
            case LIQ_REF_SESSION:
                return !Double.isNaN(sessionLow) ? sessionLow : pdl;
            case LIQ_REF_CUSTOM:
                double custom = getSettings().getDouble(CUSTOM_LIQ_LEVEL, 0.0);
                return custom > 0 ? custom : pdl;
            default:
                return pdl;
        }
    }

    private double resolveBSLLevel(DataSeries series, int index, int pivotStrength) {
        int ref = getSettings().getInteger(MMSM_BSL_REF, LIQ_REF_PREV_DAY);
        switch (ref) {
            case LIQ_REF_SESSION:
                return !Double.isNaN(sessionHigh) ? sessionHigh : pdh;
            case LIQ_REF_CUSTOM:
                double custom = getSettings().getDouble(CUSTOM_LIQ_LEVEL, 0.0);
                return custom > 0 ? custom : pdh;
            default:
                return pdh;
        }
    }

    private void updateLiquiditySessionLevels(int timeInt, double high, double low) {
        int start = getSettings().getInteger(LIQ_SESSION_START, 2000);
        int end = getSettings().getInteger(LIQ_SESSION_END, 0);

        // Handle overnight session (e.g., 2000-0000)
        boolean inSession;
        if (start > end) {
            inSession = timeInt >= start || timeInt < end;
        } else {
            inSession = timeInt >= start && timeInt < end;
        }

        if (inSession) {
            if (Double.isNaN(sessionHigh) || high > sessionHigh) sessionHigh = high;
            if (Double.isNaN(sessionLow) || low < sessionLow) sessionLow = low;
            inLiquiditySession = true;
        } else if (inLiquiditySession) {
            inLiquiditySession = false;
        }
    }

    private void resetDailyState() {
        resetMMBMState();
        resetMMSMState();
        tradesToday = 0;
        longTradesToday = 0;
        shortTradesToday = 0;
        eodProcessed = false;
        resetTradeState();
    }

    private void resetMMBMState() {
        mmbmState = STATE_IDLE;
        mmbmSweepDetected = false;
        mmbmSweepLow = Double.NaN;
        mmbmMssLevel = Double.NaN;
        mmbmMssConfirmed = false;
        mmbmFvgTop = Double.NaN;
        mmbmFvgBottom = Double.NaN;
        mmbmFvgDetected = false;
        mmbmFvgBarIndex = -1;
        mmbmWaitingForFill = false;
        mmbmEntryBarIndex = -1;
        mmbmSweepStrength = 0;
    }

    private void resetMMSMState() {
        mmsmState = STATE_IDLE;
        mmsmSweepDetected = false;
        mmsmSweepHigh = Double.NaN;
        mmsmMssLevel = Double.NaN;
        mmsmMssConfirmed = false;
        mmsmFvgTop = Double.NaN;
        mmsmFvgBottom = Double.NaN;
        mmsmFvgDetected = false;
        mmsmFvgBarIndex = -1;
        mmsmWaitingForFill = false;
        mmsmEntryBarIndex = -1;
        mmsmSweepStrength = 0;
    }

    private void resetTradeState() {
        entryPrice = 0;
        stopPrice = 0;
        tp1Price = 0;
        tp2Price = 0;
        partialTaken = false;
        currentDirection = 0;
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

    private int getWeekOfYear(long time, TimeZone tz) {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.WEEK_OF_YEAR) + cal.get(Calendar.YEAR) * 100;
    }

    /**
     * Find the major swing low over the specified lookback period.
     * Uses a larger pivot strength (5) for HTF swing detection.
     */
    private double findMajorSwingLow(DataSeries series, int index, int lookback) {
        int htfStrength = 5; // Larger strength for major swings
        double lowestSwing = Double.NaN;

        int startIdx = Math.max(htfStrength, index - lookback);
        for (int i = startIdx; i <= index - htfStrength; i++) {
            double low = series.getLow(i);
            boolean isSwing = true;
            for (int j = 1; j <= htfStrength && isSwing; j++) {
                if (i - j >= 0 && series.getLow(i - j) <= low) isSwing = false;
                if (i + j <= index && series.getLow(i + j) <= low) isSwing = false;
            }
            if (isSwing) {
                if (Double.isNaN(lowestSwing) || low < lowestSwing) {
                    lowestSwing = low;
                }
            }
        }
        return lowestSwing;
    }

    /**
     * Find the major swing high over the specified lookback period.
     * Uses a larger pivot strength (5) for HTF swing detection.
     */
    private double findMajorSwingHigh(DataSeries series, int index, int lookback) {
        int htfStrength = 5; // Larger strength for major swings
        double highestSwing = Double.NaN;

        int startIdx = Math.max(htfStrength, index - lookback);
        for (int i = startIdx; i <= index - htfStrength; i++) {
            double high = series.getHigh(i);
            boolean isSwing = true;
            for (int j = 1; j <= htfStrength && isSwing; j++) {
                if (i - j >= 0 && series.getHigh(i - j) >= high) isSwing = false;
                if (i + j <= index && series.getHigh(i + j) >= high) isSwing = false;
            }
            if (isSwing) {
                if (Double.isNaN(highestSwing) || high > highestSwing) {
                    highestSwing = high;
                }
            }
        }
        return highestSwing;
    }

    /**
     * Get sweep strength label for display
     */
    private String getSweepStrengthLabel(int strength) {
        switch (strength) {
            case 1: return "PDL";
            case 2: return "PWL";
            case 3: return "MAJOR SWING";
            default: return "";
        }
    }

    @Override
    public void clearState() {
        super.clearState();
        resetDailyState();
        lastResetDay = -1;
        lastResetWeek = -1;
        pdh = Double.NaN;
        pdl = Double.NaN;
        pwh = Double.NaN;
        pwl = Double.NaN;
        todayHigh = Double.NaN;
        todayLow = Double.NaN;
        thisWeekHigh = Double.NaN;
        thisWeekLow = Double.NaN;
        sessionHigh = Double.NaN;
        sessionLow = Double.NaN;
        majorSwingHigh = Double.NaN;
        majorSwingLow = Double.NaN;
        inLiquiditySession = false;
    }
}
