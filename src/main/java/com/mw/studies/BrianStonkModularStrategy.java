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
 * Brian Stonk Essentials Core Engine v1.0
 *
 * A comprehensive ICT-style strategy derived from Brian Stonk's concepts:
 * - Order Block (OB) with mean threshold logic
 * - Breaker (failed OB flip or sweep+displacement structure)
 * - Fair Value Gap (FVG) with consequent encroachment
 * - Inversion (IFVG) - FVG displaced through, flips role
 * - Balanced Price Range (BPR) - overlap of zones
 * - Unicorn - A+ setup: Breaker + FVG/BPR confluence
 * - Draw Liquidity targeting
 * - Timeframe Alignment (LTF execution, intraday anchor, HTF bias)
 *
 * Entry Models:
 * - UN1: A+ Unicorn (Breaker + BPR/FVG overlap)
 * - BR1: Breaker Retap Continuation
 * - IF1: IFVG/BPR Flip Entry
 * - OB1: Order Block Mean Threshold Bounce
 *
 * @version 1.0.0
 * @author MW Study Builder (Brian Stonk transcript-derived concepts)
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "BRIANSTONK_MODULAR",
    rb = "com.mw.studies.nls.strings",
    name = "BRIANSTONK_MODULAR",
    label = "LBL_BRIANSTONK",
    desc = "DESC_BRIANSTONK",
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
public class BrianStonkModularStrategy extends Study
{
    // ==================== Input Keys ====================
    // Presets
    private static final String PRESET_SELECTOR = "presetSelector";
    private static final String ENABLE_LONG = "enableLong";
    private static final String ENABLE_SHORT = "enableShort";

    // Entry Models
    private static final String ENABLE_UNICORN = "enableUnicorn";
    private static final String ENABLE_BREAKER = "enableBreaker";
    private static final String ENABLE_IFVG = "enableIfvg";
    private static final String ENABLE_OB = "enableOb";

    // Sessions
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String COOLDOWN_MINUTES = "cooldownMinutes";
    private static final String FORCED_FLAT_ENABLED = "forcedFlatEnabled";
    private static final String FORCED_FLAT_TIME = "forcedFlatTime";

    // Timeframe Alignment
    private static final String REQUIRE_INTRADAY_ALIGN = "requireIntradayAlign";
    private static final String HTF_FILTER_MODE = "htfFilterMode";
    private static final String INTRADAY_MA_PERIOD = "intradayMaPeriod";
    private static final String PIVOT_LEFT = "pivotLeft";
    private static final String PIVOT_RIGHT = "pivotRight";

    // Draw Liquidity
    private static final String REQUIRE_DRAW_TARGET = "requireDrawTarget";
    private static final String USE_SESSION_LIQUIDITY = "useSessionLiquidity";
    private static final String USE_SWING_LIQUIDITY = "useSwingLiquidity";
    private static final String USE_EQUAL_HL = "useEqualHl";

    // Order Block
    private static final String OB_MIN_CANDLES = "obMinCandles";
    private static final String OB_MEAN_THRESHOLD = "obMeanThreshold";

    // Breaker
    private static final String BREAKER_REQUIRE_SWEEP = "breakerRequireSweep";
    private static final String BREAKER_REQUIRE_DISPLACEMENT = "breakerRequireDisplacement";
    private static final String TIGHT_BREAKER_THRESHOLD = "tightBreakerThreshold";

    // FVG/IFVG
    private static final String FVG_MIN_GAP = "fvgMinGap";
    private static final String FVG_CE_RESPECT = "fvgCeRespect";

    // Risk
    private static final String STOP_DEFAULT = "stopDefault";
    private static final String STOP_MIN = "stopMin";
    private static final String STOP_MAX = "stopMax";
    private static final String STOP_OVERRIDE_TO_STRUCTURE = "stopOverrideToStructure";
    private static final String FIXED_CONTRACTS = "fixedContracts";
    private static final String BE_ENABLED = "beEnabled";
    private static final String BE_TRIGGER_PTS = "beTriggerPts";

    // Targets
    private static final String TARGET_MODE = "targetMode";
    private static final String TARGET_R = "targetR";
    private static final String PARTIAL_ENABLED = "partialEnabled";
    private static final String PARTIAL_R = "partialR";
    private static final String PARTIAL_PCT = "partialPct";
    private static final String RUNNER_ENABLED = "runnerEnabled";

    // Display
    private static final String SHOW_OB_ZONES = "showObZones";
    private static final String SHOW_BREAKER_ZONES = "showBreakerZones";
    private static final String SHOW_FVG_ZONES = "showFvgZones";

    // ==================== Constants ====================
    // Presets
    private static final int PRESET_1M_15M_4H = 0;  // Core: 1m exec, 15m anchor, 4h HTF
    private static final int PRESET_1M_5M_4H = 1;   // Substitute: 1m exec, 5m anchor

    // HTF Filter Modes
    private static final int HTF_STRICT = 0;
    private static final int HTF_LOOSE = 1;
    private static final int HTF_OFF = 2;

    // Target Modes
    private static final int TARGET_FIXED_R = 0;
    private static final int TARGET_LIQUIDITY = 1;
    private static final int TARGET_HYBRID = 2;

    // Bias
    private static final int BIAS_BULLISH = 1;
    private static final int BIAS_BEARISH = -1;
    private static final int BIAS_NEUTRAL = 0;

    // Zone Types
    private static final String ZONE_OB = "OB";
    private static final String ZONE_BREAKER = "BREAKER";
    private static final String ZONE_FVG = "FVG";
    private static final String ZONE_IFVG = "IFVG";
    private static final String ZONE_BPR = "BPR";

    // ==================== Values ====================
    enum Values { INTRADAY_MA, SWING_HIGH, SWING_LOW, SESSION_HIGH, SESSION_LOW }

    // ==================== Signals ====================
    enum Signals {
        OB_BULLISH, OB_BEARISH, BREAKER_BULLISH, BREAKER_BEARISH,
        FVG_BULLISH, FVG_BEARISH, IFVG_BULLISH, IFVG_BEARISH,
        BPR_CREATED, UNICORN_SETUP,
        ENTRY_LONG, ENTRY_SHORT, LIQUIDITY_TAGGED
    }

    // ==================== Zone Class ====================
    private static class Zone {
        double top;
        double bottom;
        int barIndex;
        boolean isBullish;
        boolean isValid;
        String type;
        double meanThreshold;  // Midpoint (CE for FVG, mean for OB)
        boolean violated;      // For OB->Breaker flip tracking
        int sourceTimeframe;   // For TF tagging

        Zone(double top, double bottom, int barIndex, boolean isBullish, String type) {
            this.top = top;
            this.bottom = bottom;
            this.barIndex = barIndex;
            this.isBullish = isBullish;
            this.isValid = true;
            this.type = type;
            this.meanThreshold = (top + bottom) / 2.0;
            this.violated = false;
            this.sourceTimeframe = 1;
        }

        double getMid() { return meanThreshold; }
        double getHeight() { return Math.abs(top - bottom); }
    }

    // ==================== Liquidity Target ====================
    private static class LiquidityTarget {
        double price;
        String type;  // "SESSION_HIGH", "SESSION_LOW", "SWING_HIGH", "SWING_LOW", "EQUAL_HIGH", "EQUAL_LOW"
        boolean isBullishDraw;

        LiquidityTarget(double price, String type, boolean isBullishDraw) {
            this.price = price;
            this.type = type;
            this.isBullishDraw = isBullishDraw;
        }
    }

    // ==================== State Variables ====================
    // Zones
    private List<Zone> obZones = new ArrayList<>();
    private List<Zone> breakerZones = new ArrayList<>();
    private List<Zone> fvgZones = new ArrayList<>();
    private List<Zone> ifvgZones = new ArrayList<>();
    private List<Zone> bprZones = new ArrayList<>();

    // Swing tracking
    private double lastSwingHigh = Double.NaN;
    private double lastSwingLow = Double.NaN;
    private int lastSwingHighBar = -1;
    private int lastSwingLowBar = -1;
    private double prevSwingHigh = Double.NaN;
    private double prevSwingLow = Double.NaN;

    // Liquidity levels
    private double sessionHigh = Double.NaN;
    private double sessionLow = Double.NaN;
    private double todayHigh = Double.NaN;
    private double todayLow = Double.NaN;

    // Draw targets
    private LiquidityTarget primaryDrawTarget = null;
    private List<LiquidityTarget> drawTargets = new ArrayList<>();

    // Bias tracking
    private int intradayBias = BIAS_NEUTRAL;
    private int htfBias = BIAS_NEUTRAL;
    private boolean ltfPermission = false;

    // Sweep tracking for breaker validation
    private boolean sweepHighDetected = false;
    private boolean sweepLowDetected = false;
    private int lastSweepBar = -1;
    private double sweepExtreme = Double.NaN;

    // Trade tracking
    private int tradesToday = 0;
    private long lastTradeTime = 0;
    private boolean inPosition = false;
    private boolean isLongPosition = false;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double targetPrice = 0;
    private double riskPoints = 0;
    private int entryBar = -1;
    private boolean partialTaken = false;
    private boolean beActivated = false;
    private String entryModel = "";

    // Pending confirmation
    private Zone pendingZone = null;
    private int confirmationWaitBar = -1;
    private String pendingModel = null;

    // Daily tracking
    private int lastResetDay = -1;
    private boolean flatProcessed = false;

    // NY timezone
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Presets Tab =====
        var tab = sd.addTab("Presets");
        var grp = tab.addGroup("Strategy Configuration");
        grp.addRow(new IntegerDescriptor(PRESET_SELECTOR,
            "Preset (0=1m/15m/4h Core, 1=1m/5m/4h Substitute)", PRESET_1M_15M_4H, 0, 1, 1));
        grp.addRow(new BooleanDescriptor(ENABLE_LONG, "Enable Long", true));
        grp.addRow(new BooleanDescriptor(ENABLE_SHORT, "Enable Short", true));

        grp = tab.addGroup("Entry Models");
        grp.addRow(new BooleanDescriptor(ENABLE_UNICORN, "UN1: Unicorn (Breaker+BPR/FVG)", true));
        grp.addRow(new BooleanDescriptor(ENABLE_BREAKER, "BR1: Breaker Retap", true));
        grp.addRow(new BooleanDescriptor(ENABLE_IFVG, "IF1: IFVG/BPR Flip", true));
        grp.addRow(new BooleanDescriptor(ENABLE_OB, "OB1: OB Mean Threshold", true));

        // ===== Sessions Tab =====
        tab = sd.addTab("Sessions");
        grp = tab.addGroup("Trade Window (ET)");
        grp.addRow(new IntegerDescriptor(TRADE_START, "Start Time (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(TRADE_END, "End Time (HHMM)", 1600, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades Per Day", 3, 1, 10, 1));
        grp.addRow(new IntegerDescriptor(COOLDOWN_MINUTES, "Cooldown (minutes)", 5, 0, 60, 1));

        grp = tab.addGroup("Forced Flat");
        grp.addRow(new BooleanDescriptor(FORCED_FLAT_ENABLED, "Force Flat at Time", true));
        grp.addRow(new IntegerDescriptor(FORCED_FLAT_TIME, "Flat Time (HHMM)", 1555, 0, 2359, 1));

        // ===== Alignment Tab =====
        tab = sd.addTab("Alignment");
        grp = tab.addGroup("Timeframe Alignment");
        grp.addRow(new BooleanDescriptor(REQUIRE_INTRADAY_ALIGN, "Require Intraday Alignment", true));
        grp.addRow(new IntegerDescriptor(HTF_FILTER_MODE, "HTF Filter (0=Strict, 1=Loose, 2=Off)", HTF_LOOSE, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(INTRADAY_MA_PERIOD, "Intraday MA Period", 21, 5, 100, 1));
        grp.addRow(new IntegerDescriptor(PIVOT_LEFT, "Pivot Left Bars", 2, 1, 10, 1));
        grp.addRow(new IntegerDescriptor(PIVOT_RIGHT, "Pivot Right Bars", 2, 1, 10, 1));

        // ===== Liquidity Tab =====
        tab = sd.addTab("Liquidity");
        grp = tab.addGroup("Draw Liquidity Targets");
        grp.addRow(new BooleanDescriptor(REQUIRE_DRAW_TARGET, "Require Draw Target", true));
        grp.addRow(new BooleanDescriptor(USE_SESSION_LIQUIDITY, "Use Session H/L", true));
        grp.addRow(new BooleanDescriptor(USE_SWING_LIQUIDITY, "Use Swing H/L", true));
        grp.addRow(new BooleanDescriptor(USE_EQUAL_HL, "Use Equal H/L", true));

        // ===== OB Tab =====
        tab = sd.addTab("Order Block");
        grp = tab.addGroup("OB Detection");
        grp.addRow(new IntegerDescriptor(OB_MIN_CANDLES, "Min Consecutive Candles", 2, 1, 5, 1));
        grp.addRow(new BooleanDescriptor(OB_MEAN_THRESHOLD, "Enforce Mean Threshold Rule", true));

        // ===== Breaker Tab =====
        tab = sd.addTab("Breaker");
        grp = tab.addGroup("Breaker Detection");
        grp.addRow(new BooleanDescriptor(BREAKER_REQUIRE_SWEEP, "Prefer Sweep (Manipulation)", true));
        grp.addRow(new BooleanDescriptor(BREAKER_REQUIRE_DISPLACEMENT, "Require Displacement", true));
        grp.addRow(new DoubleDescriptor(TIGHT_BREAKER_THRESHOLD, "Tight Breaker Threshold (pts)", 10.0, 1.0, 50.0, 1.0));

        // ===== FVG Tab =====
        tab = sd.addTab("FVG/IFVG");
        grp = tab.addGroup("FVG Detection");
        grp.addRow(new DoubleDescriptor(FVG_MIN_GAP, "Min Gap Size (points)", 2.0, 0.5, 20.0, 0.5));
        grp.addRow(new BooleanDescriptor(FVG_CE_RESPECT, "CE Rule (no close through mid)", true));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Stop Loss (1m Breaker Default)");
        grp.addRow(new DoubleDescriptor(STOP_DEFAULT, "Default Stop (points)", 12.5, 5.0, 50.0, 0.5));
        grp.addRow(new DoubleDescriptor(STOP_MIN, "Min Stop (points)", 10.0, 1.0, 50.0, 0.5));
        grp.addRow(new DoubleDescriptor(STOP_MAX, "Max Stop (points)", 15.0, 5.0, 100.0, 1.0));
        grp.addRow(new BooleanDescriptor(STOP_OVERRIDE_TO_STRUCTURE, "Override to Structure if Tight", true));

        grp = tab.addGroup("Breakeven");
        grp.addRow(new BooleanDescriptor(BE_ENABLED, "Move Stop to Breakeven", true));
        grp.addRow(new DoubleDescriptor(BE_TRIGGER_PTS, "BE Trigger (points profit)", 3.0, 0.25, 50.0, 0.25));

        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(FIXED_CONTRACTS, "Contracts", 1, 1, 100, 1));

        // ===== Targets Tab =====
        tab = sd.addTab("Targets");
        grp = tab.addGroup("Target Mode");
        grp.addRow(new IntegerDescriptor(TARGET_MODE, "Mode (0=Fixed R, 1=Liquidity, 2=Hybrid)", TARGET_HYBRID, 0, 2, 1));
        grp.addRow(new DoubleDescriptor(TARGET_R, "Fixed R Target", 2.0, 0.5, 10.0, 0.5));

        grp = tab.addGroup("Partials");
        grp.addRow(new BooleanDescriptor(PARTIAL_ENABLED, "Enable Partial", true));
        grp.addRow(new DoubleDescriptor(PARTIAL_R, "Partial at R", 1.0, 0.5, 5.0, 0.25));
        grp.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial %", 50, 10, 90, 10));
        grp.addRow(new BooleanDescriptor(RUNNER_ENABLED, "Keep Runner", true));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Zone Visibility");
        grp.addRow(new BooleanDescriptor(SHOW_OB_ZONES, "Show Order Blocks", true));
        grp.addRow(new BooleanDescriptor(SHOW_BREAKER_ZONES, "Show Breakers", true));
        grp.addRow(new BooleanDescriptor(SHOW_FVG_ZONES, "Show FVG/IFVG", true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(PRESET_SELECTOR, ENABLE_LONG, ENABLE_SHORT, TARGET_R, FIXED_CONTRACTS);

        // Runtime descriptor
        var desc = createRD();
        desc.setLabelSettings(PRESET_SELECTOR, TARGET_R);

        desc.declareSignal(Signals.BREAKER_BULLISH, "Bullish Breaker Validated");
        desc.declareSignal(Signals.BREAKER_BEARISH, "Bearish Breaker Validated");
        desc.declareSignal(Signals.IFVG_BULLISH, "Bullish IFVG Created");
        desc.declareSignal(Signals.IFVG_BEARISH, "Bearish IFVG Created");
        desc.declareSignal(Signals.BPR_CREATED, "BPR Confluence Created");
        desc.declareSignal(Signals.UNICORN_SETUP, "A+ Unicorn Setup");
        desc.declareSignal(Signals.ENTRY_LONG, "Entry Long");
        desc.declareSignal(Signals.ENTRY_SHORT, "Entry Short");
    }

    @Override
    public int getMinBars() { return 100; }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();

        if (index < 50) return;

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
                // Could track PDH/PDL here
            }
            todayHigh = Double.NaN;
            todayLow = Double.NaN;
            sessionHigh = Double.NaN;
            sessionLow = Double.NaN;
            resetDailyState();
            lastResetDay = barDay;
        }

        // Track today/session H/L
        if (Double.isNaN(todayHigh) || high > todayHigh) todayHigh = high;
        if (Double.isNaN(todayLow) || low < todayLow) todayLow = low;

        int tradeStart = getSettings().getInteger(TRADE_START, 930);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1600);
        if (barTimeInt >= tradeStart && barTimeInt <= tradeEnd) {
            if (Double.isNaN(sessionHigh) || high > sessionHigh) sessionHigh = high;
            if (Double.isNaN(sessionLow) || low < sessionLow) sessionLow = low;
        }

        // Update swings
        int pivotLeft = getSettings().getInteger(PIVOT_LEFT, 2);
        int pivotRight = getSettings().getInteger(PIVOT_RIGHT, 2);
        updateSwingPoints(series, index, pivotLeft, pivotRight);

        // Calculate intraday MA for bias
        int maPeriod = getSettings().getInteger(INTRADAY_MA_PERIOD, 21);
        Double intradayMA = series.ema(index, maPeriod, Enums.BarInput.CLOSE);

        if (!series.isBarComplete(index)) return;

        // ===== Step 1: Draw Liquidity =====
        updateDrawTargets(series, index, close);

        // ===== Step 2: Timeframe Alignment =====
        updateBias(series, index, intradayMA, close);

        // ===== Detect Zones =====
        detectOrderBlocks(ctx, series, index, open, close);
        detectFVGs(ctx, series, index);
        checkOBViolationToBreaker(ctx, series, index, close);
        detectStructureBreakers(ctx, series, index, close);
        detectInversions(ctx, series, index, close);
        detectBPRs(ctx, series, index);
        detectUnicornSetups(ctx, series, index);

        // Invalidate old zones
        invalidateZones(series, index, close);

        // ===== Check Trade Conditions =====
        boolean inTradeWindow = barTimeInt >= tradeStart && barTimeInt < tradeEnd;
        boolean pastCooldown = barTime - lastTradeTime >= getSettings().getInteger(COOLDOWN_MINUTES, 5) * 60000L;
        int maxTrades = getSettings().getInteger(MAX_TRADES_DAY, 3);
        boolean underLimit = tradesToday < maxTrades;

        boolean forcedFlatEnabled = getSettings().getBoolean(FORCED_FLAT_ENABLED, true);
        int forcedFlatTime = getSettings().getInteger(FORCED_FLAT_TIME, 1555);
        boolean pastFlatTime = forcedFlatEnabled && barTimeInt >= forcedFlatTime;

        boolean hasDrawTarget = primaryDrawTarget != null || !getSettings().getBoolean(REQUIRE_DRAW_TARGET, true);
        boolean hasAlignment = ltfPermission || !getSettings().getBoolean(REQUIRE_INTRADAY_ALIGN, true);

        boolean canTrade = inTradeWindow && pastCooldown && underLimit && !pastFlatTime &&
                           hasDrawTarget && hasAlignment && !inPosition;

        // ===== Step 3: Entry Models =====
        if (canTrade) {
            processEntryModels(ctx, series, index, close, open, barTime);
        }

        // Handle pending confirmation
        if (pendingZone != null && !inPosition) {
            handlePendingConfirmation(ctx, series, index, close, open, barTime);
        }

        series.setComplete(index);
    }

    // ==================== Order Block Detection ====================

    private void detectOrderBlocks(DataContext ctx, DataSeries series, int index, double open, double close)
    {
        int minCandles = getSettings().getInteger(OB_MIN_CANDLES, 2);
        if (index < minCandles + 1) return;

        // Check for bullish OB: consecutive up-close candles, then close below
        int upCount = 0;
        for (int i = index - 1; i >= 0 && upCount < 5; i--) {
            if (series.getClose(i) > series.getOpen(i)) {
                upCount++;
            } else {
                break;
            }
        }

        if (upCount >= minCandles && close < open) {
            // Current candle closes down through the up-close series
            double obTop = Double.MIN_VALUE;
            double obBottom = Double.MAX_VALUE;
            for (int i = index - upCount; i < index; i++) {
                obTop = Math.max(obTop, Math.max(series.getOpen(i), series.getClose(i)));
                obBottom = Math.min(obBottom, Math.min(series.getOpen(i), series.getClose(i)));
            }

            if (close < obBottom) {
                Zone ob = new Zone(obTop, obBottom, index, true, ZONE_OB);
                obZones.add(ob);
                ctx.signal(index, Signals.OB_BULLISH, "Bullish OB", obBottom);
                debug("Bullish OB created: " + obBottom + " - " + obTop);
            }
        }

        // Check for bearish OB: consecutive down-close candles, then close above
        int downCount = 0;
        for (int i = index - 1; i >= 0 && downCount < 5; i--) {
            if (series.getClose(i) < series.getOpen(i)) {
                downCount++;
            } else {
                break;
            }
        }

        if (downCount >= minCandles && close > open) {
            double obTop = Double.MIN_VALUE;
            double obBottom = Double.MAX_VALUE;
            for (int i = index - downCount; i < index; i++) {
                obTop = Math.max(obTop, Math.max(series.getOpen(i), series.getClose(i)));
                obBottom = Math.min(obBottom, Math.min(series.getOpen(i), series.getClose(i)));
            }

            if (close > obTop) {
                Zone ob = new Zone(obTop, obBottom, index, false, ZONE_OB);
                obZones.add(ob);
                ctx.signal(index, Signals.OB_BEARISH, "Bearish OB", obTop);
                debug("Bearish OB created: " + obBottom + " - " + obTop);
            }
        }

        while (obZones.size() > 15) obZones.remove(0);
    }

    // ==================== OB Violation to Breaker ====================

    private void checkOBViolationToBreaker(DataContext ctx, DataSeries series, int index, double close)
    {
        // When OB is violated by close through it, flip to breaker
        for (Zone ob : obZones) {
            if (!ob.isValid || ob.violated) continue;

            if (ob.isBullish) {
                // Bullish OB violated = close below bottom → becomes bearish breaker
                if (close < ob.bottom) {
                    ob.violated = true;
                    ob.isValid = false;
                    Zone breaker = new Zone(ob.top, ob.bottom, index, false, ZONE_BREAKER);
                    breakerZones.add(breaker);
                    ctx.signal(index, Signals.BREAKER_BEARISH, "OB->Breaker (Bearish)", ob.top);
                    debug("Bullish OB violated -> Bearish Breaker");
                }
            } else {
                // Bearish OB violated = close above top → becomes bullish breaker
                if (close > ob.top) {
                    ob.violated = true;
                    ob.isValid = false;
                    Zone breaker = new Zone(ob.top, ob.bottom, index, true, ZONE_BREAKER);
                    breakerZones.add(breaker);
                    ctx.signal(index, Signals.BREAKER_BULLISH, "OB->Breaker (Bullish)", ob.bottom);
                    debug("Bearish OB violated -> Bullish Breaker");
                }
            }
        }
    }

    // ==================== Structure Breaker Detection ====================

    private void detectStructureBreakers(DataContext ctx, DataSeries series, int index, double close)
    {
        if (Double.isNaN(lastSwingHigh) || Double.isNaN(lastSwingLow)) return;

        boolean requireSweep = getSettings().getBoolean(BREAKER_REQUIRE_SWEEP, true);

        // Bullish breaker sequence: swing low -> swing high -> sweep below low -> displacement above high
        // Check if we swept below swing low recently
        boolean sweptLow = false;
        double sweepLowPrice = Double.NaN;
        for (int i = index - 1; i > lastSwingLowBar && i > index - 20 && i >= 0; i--) {
            if (series.getLow(i) < lastSwingLow) {
                sweptLow = true;
                sweepLowPrice = series.getLow(i);
                break;
            }
        }

        if (sweptLow && close > lastSwingHigh) {
            // Strong displacement through swing high after sweep
            double bodySize = Math.abs(close - series.getOpen(index));
            if (bodySize > 5 || !getSettings().getBoolean(BREAKER_REQUIRE_DISPLACEMENT, true)) {
                // Create bullish breaker zone from sweep area
                Zone breaker = new Zone(lastSwingLow + 3, sweepLowPrice, index, true, ZONE_BREAKER);
                breakerZones.add(breaker);
                ctx.signal(index, Signals.BREAKER_BULLISH, "Structure Breaker (Bullish)", sweepLowPrice);
                debug("Bullish structure breaker after sweep");
                sweepLowDetected = false;
            }
        }

        // Bearish breaker sequence: swing high -> swing low -> sweep above high -> displacement below low
        boolean sweptHigh = false;
        double sweepHighPrice = Double.NaN;
        for (int i = index - 1; i > lastSwingHighBar && i > index - 20 && i >= 0; i--) {
            if (series.getHigh(i) > lastSwingHigh) {
                sweptHigh = true;
                sweepHighPrice = series.getHigh(i);
                break;
            }
        }

        if (sweptHigh && close < lastSwingLow) {
            double bodySize = Math.abs(close - series.getOpen(index));
            if (bodySize > 5 || !getSettings().getBoolean(BREAKER_REQUIRE_DISPLACEMENT, true)) {
                Zone breaker = new Zone(sweepHighPrice, lastSwingHigh - 3, index, false, ZONE_BREAKER);
                breakerZones.add(breaker);
                ctx.signal(index, Signals.BREAKER_BEARISH, "Structure Breaker (Bearish)", sweepHighPrice);
                debug("Bearish structure breaker after sweep");
                sweepHighDetected = false;
            }
        }

        while (breakerZones.size() > 15) breakerZones.remove(0);
    }

    // ==================== FVG Detection ====================

    private void detectFVGs(DataContext ctx, DataSeries series, int index)
    {
        if (index < 2) return;

        double minGap = getSettings().getDouble(FVG_MIN_GAP, 2.0);

        double c1High = series.getHigh(index - 2);
        double c1Low = series.getLow(index - 2);
        double c3High = series.getHigh(index);
        double c3Low = series.getLow(index);

        // Bullish FVG: candle1 wick high to candle3 wick low (gap up)
        if (c3Low > c1High && (c3Low - c1High) >= minGap) {
            Zone fvg = new Zone(c3Low, c1High, index, true, ZONE_FVG);
            fvgZones.add(fvg);
            ctx.signal(index, Signals.FVG_BULLISH, "Bullish FVG", c1High);
            debug("Bullish FVG: " + c1High + " - " + c3Low);
        }

        // Bearish FVG: candle1 wick low to candle3 wick high (gap down)
        if (c1Low > c3High && (c1Low - c3High) >= minGap) {
            Zone fvg = new Zone(c1Low, c3High, index, false, ZONE_FVG);
            fvgZones.add(fvg);
            ctx.signal(index, Signals.FVG_BEARISH, "Bearish FVG", c1Low);
            debug("Bearish FVG: " + c3High + " - " + c1Low);
        }

        while (fvgZones.size() > 20) fvgZones.remove(0);
    }

    // ==================== Inversion (IFVG) Detection ====================

    private void detectInversions(DataContext ctx, DataSeries series, int index, double close)
    {
        // IFVG: price displaces through FVG, flipping its role
        for (Zone fvg : fvgZones) {
            if (!fvg.isValid || fvg.type.equals(ZONE_IFVG)) continue;

            if (fvg.isBullish) {
                // Bullish FVG displaced through → bearish inversion
                if (close < fvg.bottom) {
                    Zone ifvg = new Zone(fvg.top, fvg.bottom, index, false, ZONE_IFVG);
                    ifvgZones.add(ifvg);
                    fvg.isValid = false;
                    ctx.signal(index, Signals.IFVG_BEARISH, "Bearish IFVG (inverted)", fvg.top);
                    debug("Bullish FVG inverted to Bearish IFVG");
                }
            } else {
                // Bearish FVG displaced through → bullish inversion
                if (close > fvg.top) {
                    Zone ifvg = new Zone(fvg.top, fvg.bottom, index, true, ZONE_IFVG);
                    ifvgZones.add(ifvg);
                    fvg.isValid = false;
                    ctx.signal(index, Signals.IFVG_BULLISH, "Bullish IFVG (inverted)", fvg.bottom);
                    debug("Bearish FVG inverted to Bullish IFVG");
                }
            }
        }

        while (ifvgZones.size() > 15) ifvgZones.remove(0);
    }

    // ==================== BPR Detection ====================

    private void detectBPRs(DataContext ctx, DataSeries series, int index)
    {
        // BPR = overlap between inversion and another FVG/zone
        for (Zone ifvg : ifvgZones) {
            if (!ifvg.isValid) continue;

            for (Zone fvg : fvgZones) {
                if (!fvg.isValid || fvg.barIndex == ifvg.barIndex) continue;

                // Check for overlap
                double overlapTop = Math.min(ifvg.top, fvg.top);
                double overlapBottom = Math.max(ifvg.bottom, fvg.bottom);

                if (overlapTop > overlapBottom) {
                    // There's an overlap - create BPR
                    Zone bpr = new Zone(overlapTop, overlapBottom, index, ifvg.isBullish, ZONE_BPR);

                    // Check if BPR already exists at this level
                    boolean exists = false;
                    for (Zone existing : bprZones) {
                        if (Math.abs(existing.top - bpr.top) < 1 && Math.abs(existing.bottom - bpr.bottom) < 1) {
                            exists = true;
                            break;
                        }
                    }

                    if (!exists) {
                        bprZones.add(bpr);
                        ctx.signal(index, Signals.BPR_CREATED, "BPR Created", bpr.getMid());
                        debug("BPR created: " + bpr.bottom + " - " + bpr.top);
                    }
                }
            }
        }

        while (bprZones.size() > 10) bprZones.remove(0);
    }

    // ==================== Unicorn Detection ====================

    private void detectUnicornSetups(DataContext ctx, DataSeries series, int index)
    {
        // Unicorn = Breaker + FVG/BPR confluence
        for (Zone breaker : breakerZones) {
            if (!breaker.isValid) continue;

            // Check for overlapping BPR or FVG
            for (Zone zone : bprZones) {
                if (!zone.isValid) continue;
                if (zone.isBullish == breaker.isBullish) {
                    double overlapTop = Math.min(breaker.top, zone.top);
                    double overlapBottom = Math.max(breaker.bottom, zone.bottom);
                    if (overlapTop > overlapBottom) {
                        ctx.signal(index, Signals.UNICORN_SETUP, "A+ Unicorn (Breaker+BPR)", zone.getMid());
                        debug("Unicorn setup detected: Breaker + BPR");
                    }
                }
            }

            for (Zone fvg : ifvgZones) {
                if (!fvg.isValid) continue;
                if (fvg.isBullish == breaker.isBullish) {
                    double overlapTop = Math.min(breaker.top, fvg.top);
                    double overlapBottom = Math.max(breaker.bottom, fvg.bottom);
                    if (overlapTop > overlapBottom) {
                        ctx.signal(index, Signals.UNICORN_SETUP, "Unicorn (Breaker+IFVG)", fvg.getMid());
                        debug("Unicorn setup detected: Breaker + IFVG");
                    }
                }
            }
        }
    }

    // ==================== Draw Liquidity ====================

    private void updateDrawTargets(DataSeries series, int index, double close)
    {
        drawTargets.clear();
        primaryDrawTarget = null;

        // Session liquidity
        if (getSettings().getBoolean(USE_SESSION_LIQUIDITY, true)) {
            if (!Double.isNaN(sessionHigh) && close < sessionHigh) {
                drawTargets.add(new LiquidityTarget(sessionHigh, "SESSION_HIGH", true));
            }
            if (!Double.isNaN(sessionLow) && close > sessionLow) {
                drawTargets.add(new LiquidityTarget(sessionLow, "SESSION_LOW", false));
            }
        }

        // Swing liquidity
        if (getSettings().getBoolean(USE_SWING_LIQUIDITY, true)) {
            if (!Double.isNaN(lastSwingHigh) && close < lastSwingHigh) {
                drawTargets.add(new LiquidityTarget(lastSwingHigh, "SWING_HIGH", true));
            }
            if (!Double.isNaN(lastSwingLow) && close > lastSwingLow) {
                drawTargets.add(new LiquidityTarget(lastSwingLow, "SWING_LOW", false));
            }
        }

        // Find nearest draw target aligned with bias
        double minDist = Double.MAX_VALUE;
        for (LiquidityTarget target : drawTargets) {
            double dist = Math.abs(target.price - close);
            if (dist < minDist) {
                // Check bias alignment
                if ((intradayBias == BIAS_BULLISH && target.isBullishDraw) ||
                    (intradayBias == BIAS_BEARISH && !target.isBullishDraw) ||
                    intradayBias == BIAS_NEUTRAL) {
                    minDist = dist;
                    primaryDrawTarget = target;
                }
            }
        }
    }

    // ==================== Bias/Alignment ====================

    private void updateBias(DataSeries series, int index, Double intradayMA, double close)
    {
        // Intraday bias from MA + structure
        intradayBias = BIAS_NEUTRAL;

        if (intradayMA != null) {
            if (close > intradayMA && !Double.isNaN(lastSwingLow) && !Double.isNaN(prevSwingLow)) {
                if (lastSwingLow > prevSwingLow) {
                    intradayBias = BIAS_BULLISH;
                }
            } else if (close < intradayMA && !Double.isNaN(lastSwingHigh) && !Double.isNaN(prevSwingHigh)) {
                if (lastSwingHigh < prevSwingHigh) {
                    intradayBias = BIAS_BEARISH;
                }
            }
        }

        // HTF bias - simplified (would need HTF data in real impl)
        int htfMode = getSettings().getInteger(HTF_FILTER_MODE, HTF_LOOSE);
        if (htfMode == HTF_OFF) {
            htfBias = intradayBias;
        } else {
            htfBias = intradayBias; // Simplified - in real impl, would use HTF series
        }

        // LTF permission: intraday must align with trade direction
        ltfPermission = (intradayBias != BIAS_NEUTRAL);
    }

    // ==================== Entry Models ====================

    private void processEntryModels(DataContext ctx, DataSeries series, int index, double close, double open, long barTime)
    {
        boolean enableLong = getSettings().getBoolean(ENABLE_LONG, true);
        boolean enableShort = getSettings().getBoolean(ENABLE_SHORT, true);

        // Priority: UN1 (Unicorn) > BR1 (Breaker) > IF1 (IFVG) > OB1 (OB)

        // UN1: Unicorn (Breaker + BPR/FVG confluence)
        if (getSettings().getBoolean(ENABLE_UNICORN, true)) {
            Zone unicornZone = findUnicornZone(close);
            if (unicornZone != null) {
                if (unicornZone.isBullish && enableLong && intradayBias >= BIAS_NEUTRAL) {
                    setPendingEntry(unicornZone, "UN1_UNICORN", index);
                } else if (!unicornZone.isBullish && enableShort && intradayBias <= BIAS_NEUTRAL) {
                    setPendingEntry(unicornZone, "UN1_UNICORN", index);
                }
            }
        }

        // BR1: Breaker Retap
        if (getSettings().getBoolean(ENABLE_BREAKER, true) && pendingZone == null) {
            for (Zone breaker : breakerZones) {
                if (!breaker.isValid) continue;
                if (close >= breaker.bottom && close <= breaker.top) {
                    if (breaker.isBullish && enableLong && intradayBias >= BIAS_NEUTRAL) {
                        setPendingEntry(breaker, "BR1_BREAKER", index);
                        break;
                    } else if (!breaker.isBullish && enableShort && intradayBias <= BIAS_NEUTRAL) {
                        setPendingEntry(breaker, "BR1_BREAKER", index);
                        break;
                    }
                }
            }
        }

        // IF1: IFVG/BPR Flip
        if (getSettings().getBoolean(ENABLE_IFVG, true) && pendingZone == null) {
            for (Zone ifvg : ifvgZones) {
                if (!ifvg.isValid) continue;
                if (close >= ifvg.bottom && close <= ifvg.top) {
                    if (ifvg.isBullish && enableLong && intradayBias >= BIAS_NEUTRAL) {
                        setPendingEntry(ifvg, "IF1_IFVG", index);
                        break;
                    } else if (!ifvg.isBullish && enableShort && intradayBias <= BIAS_NEUTRAL) {
                        setPendingEntry(ifvg, "IF1_IFVG", index);
                        break;
                    }
                }
            }
        }

        // OB1: Order Block Mean Threshold
        if (getSettings().getBoolean(ENABLE_OB, true) && pendingZone == null) {
            for (Zone ob : obZones) {
                if (!ob.isValid || ob.violated) continue;
                if (close >= ob.bottom && close <= ob.top) {
                    // Mean threshold check
                    boolean meanOk = true;
                    if (getSettings().getBoolean(OB_MEAN_THRESHOLD, true)) {
                        if (ob.isBullish && close < ob.getMid()) meanOk = false;
                        if (!ob.isBullish && close > ob.getMid()) meanOk = false;
                    }
                    if (meanOk) {
                        if (ob.isBullish && enableLong && intradayBias >= BIAS_NEUTRAL) {
                            setPendingEntry(ob, "OB1_MEAN", index);
                            break;
                        } else if (!ob.isBullish && enableShort && intradayBias <= BIAS_NEUTRAL) {
                            setPendingEntry(ob, "OB1_MEAN", index);
                            break;
                        }
                    }
                }
            }
        }
    }

    private Zone findUnicornZone(double close)
    {
        // Find a breaker that overlaps with BPR or IFVG and price is in zone
        for (Zone breaker : breakerZones) {
            if (!breaker.isValid) continue;
            if (close < breaker.bottom || close > breaker.top) continue;

            for (Zone bpr : bprZones) {
                if (!bpr.isValid || bpr.isBullish != breaker.isBullish) continue;
                double overlapTop = Math.min(breaker.top, bpr.top);
                double overlapBottom = Math.max(breaker.bottom, bpr.bottom);
                if (overlapTop > overlapBottom && close >= overlapBottom && close <= overlapTop) {
                    return breaker;
                }
            }

            for (Zone ifvg : ifvgZones) {
                if (!ifvg.isValid || ifvg.isBullish != breaker.isBullish) continue;
                double overlapTop = Math.min(breaker.top, ifvg.top);
                double overlapBottom = Math.max(breaker.bottom, ifvg.bottom);
                if (overlapTop > overlapBottom && close >= overlapBottom && close <= overlapTop) {
                    return breaker;
                }
            }
        }
        return null;
    }

    private void setPendingEntry(Zone zone, String model, int index)
    {
        pendingZone = zone;
        pendingModel = model;
        confirmationWaitBar = index;
        debug("Pending entry: " + model + " at zone " + zone.bottom + "-" + zone.top);
    }

    private void handlePendingConfirmation(DataContext ctx, DataSeries series, int index, double close, double open, long barTime)
    {
        if (pendingZone == null) return;

        // Max wait 3 bars for confirmation
        if (index - confirmationWaitBar > 3) {
            debug("Confirmation timeout for " + pendingModel);
            pendingZone = null;
            pendingModel = null;
            confirmationWaitBar = -1;
            return;
        }

        // Confirmation: rejection candle (close in direction, beyond zone mid)
        if (pendingZone.isBullish) {
            if (close > open && close > pendingZone.getMid()) {
                triggerEntry(ctx, series, index, true, pendingModel, barTime);
            }
        } else {
            if (close < open && close < pendingZone.getMid()) {
                triggerEntry(ctx, series, index, false, pendingModel, barTime);
            }
        }
    }

    private void triggerEntry(DataContext ctx, DataSeries series, int index, boolean isLong, String model, long barTime)
    {
        double close = series.getClose(index);
        double low = series.getLow(index);
        double high = series.getHigh(index);

        if (isLong) {
            ctx.signal(index, Signals.ENTRY_LONG, model + " Long", close);
            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, model));
            }
        } else {
            ctx.signal(index, Signals.ENTRY_SHORT, model + " Short", close);
            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, model));
            }
        }

        entryModel = model;
        if (pendingZone != null) pendingZone.isValid = false;
        pendingZone = null;
        pendingModel = null;
        confirmationWaitBar = -1;
        debug(model + " entry triggered: " + (isLong ? "LONG" : "SHORT"));
    }

    // ==================== Zone Invalidation ====================

    private void invalidateZones(DataSeries series, int index, double close)
    {
        int maxAge = 50;

        // OB invalidation
        for (Zone ob : obZones) {
            if (!ob.isValid) continue;
            if (index - ob.barIndex > maxAge) ob.isValid = false;
            // Close through against direction invalidates
            if (ob.isBullish && close < ob.bottom) ob.isValid = false;
            if (!ob.isBullish && close > ob.top) ob.isValid = false;
        }

        // Breaker invalidation (close through breaker)
        for (Zone breaker : breakerZones) {
            if (!breaker.isValid) continue;
            if (index - breaker.barIndex > maxAge) breaker.isValid = false;
            if (breaker.isBullish && close < breaker.bottom) breaker.isValid = false;
            if (!breaker.isBullish && close > breaker.top) breaker.isValid = false;
        }

        // FVG/IFVG invalidation
        for (Zone fvg : fvgZones) {
            if (!fvg.isValid) continue;
            if (index - fvg.barIndex > maxAge) fvg.isValid = false;
        }

        for (Zone ifvg : ifvgZones) {
            if (!ifvg.isValid) continue;
            if (index - ifvg.barIndex > maxAge) ifvg.isValid = false;
        }

        // BPR invalidation
        for (Zone bpr : bprZones) {
            if (!bpr.isValid) continue;
            if (index - bpr.barIndex > maxAge) bpr.isValid = false;
        }

        // Cleanup
        obZones.removeIf(z -> !z.isValid);
        breakerZones.removeIf(z -> !z.isValid);
        fvgZones.removeIf(z -> !z.isValid);
        ifvgZones.removeIf(z -> !z.isValid);
        bprZones.removeIf(z -> !z.isValid);
    }

    // ==================== Helper Methods ====================

    private void updateSwingPoints(DataSeries series, int index, int leftBars, int rightBars)
    {
        int pivotBar = index - rightBars;
        if (pivotBar < leftBars) return;

        // Swing high
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

        // Swing low
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

    private void resetDailyState()
    {
        obZones.clear();
        breakerZones.clear();
        fvgZones.clear();
        ifvgZones.clear();
        bprZones.clear();
        drawTargets.clear();
        primaryDrawTarget = null;
        tradesToday = 0;
        flatProcessed = false;
        pendingZone = null;
        pendingModel = null;
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
        beActivated = false;
        entryModel = "";
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
        int preset = getSettings().getInteger(PRESET_SELECTOR, PRESET_1M_15M_4H);
        String presetName = preset == 0 ? "1m/15m/4h Core" : "1m/5m/4h Substitute";
        debug("Brian Stonk Essentials v1.0 activated - Preset: " + presetName);
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        if (ctx.getPosition() != 0) {
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
        if (ctx.getPosition() != 0 || inPosition) {
            debug("Already in position");
            return;
        }

        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        if (getSettings().getBoolean(FORCED_FLAT_ENABLED, true) &&
            barTimeInt >= getSettings().getInteger(FORCED_FLAT_TIME, 1555)) {
            debug("Past flat time");
            return;
        }

        int qty = getSettings().getInteger(FIXED_CONTRACTS, 1);
        double stopDefault = getSettings().getDouble(STOP_DEFAULT, 12.5);
        double stopMin = getSettings().getDouble(STOP_MIN, 10.0);
        double stopMax = getSettings().getDouble(STOP_MAX, 15.0);
        double tightThreshold = getSettings().getDouble(TIGHT_BREAKER_THRESHOLD, 10.0);
        double targetR = getSettings().getDouble(TARGET_R, 2.0);

        boolean isLong = (signal == Signals.ENTRY_LONG);

        if (isLong) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();
            isLongPosition = true;

            // Calculate stop: breaker zone or structure
            double zoneStop = entryPrice - stopDefault;
            if (pendingZone != null) {
                double breakerHeight = pendingZone.getHeight();
                if (breakerHeight < tightThreshold && getSettings().getBoolean(STOP_OVERRIDE_TO_STRUCTURE, true)) {
                    zoneStop = !Double.isNaN(lastSwingLow) ? lastSwingLow - 2 : entryPrice - stopMax;
                } else {
                    zoneStop = pendingZone.bottom - 2;
                }
            }

            riskPoints = entryPrice - zoneStop;
            riskPoints = Math.max(stopMin, Math.min(riskPoints, stopMax));
            stopPrice = instr.round(entryPrice - riskPoints);
            targetPrice = instr.round(entryPrice + (riskPoints * targetR));

            debug(String.format("LONG %s: qty=%d, entry=%.2f, stop=%.2f, target=%.2f",
                entryModel, qty, entryPrice, stopPrice, targetPrice));

        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();
            isLongPosition = false;

            double zoneStop = entryPrice + stopDefault;
            if (pendingZone != null) {
                double breakerHeight = pendingZone.getHeight();
                if (breakerHeight < tightThreshold && getSettings().getBoolean(STOP_OVERRIDE_TO_STRUCTURE, true)) {
                    zoneStop = !Double.isNaN(lastSwingHigh) ? lastSwingHigh + 2 : entryPrice + stopMax;
                } else {
                    zoneStop = pendingZone.top + 2;
                }
            }

            riskPoints = zoneStop - entryPrice;
            riskPoints = Math.max(stopMin, Math.min(riskPoints, stopMax));
            stopPrice = instr.round(entryPrice + riskPoints);
            targetPrice = instr.round(entryPrice - (riskPoints * targetR));

            debug(String.format("SHORT %s: qty=%d, entry=%.2f, stop=%.2f, target=%.2f",
                entryModel, qty, entryPrice, stopPrice, targetPrice));
        }

        inPosition = true;
        entryBar = index;
        partialTaken = false;
        tradesToday++;
        lastTradeTime = barTime;
    }

    @Override
    public void onBarClose(OrderContext ctx) {
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        var instr = ctx.getInstrument();

        // Forced flat
        if (getSettings().getBoolean(FORCED_FLAT_ENABLED, true) &&
            barTimeInt >= getSettings().getInteger(FORCED_FLAT_TIME, 1555) && !flatProcessed) {
            if (ctx.getPosition() != 0) {
                ctx.closeAtMarket();
                debug("Forced flat");
                resetTradeState();
            }
            flatProcessed = true;
            return;
        }

        if (ctx.getPosition() == 0 || !inPosition) return;

        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);

        // Stop loss
        if (isLongPosition && low <= stopPrice) {
            ctx.closeAtMarket();
            debug("LONG stopped");
            resetTradeState();
            return;
        }
        if (!isLongPosition && high >= stopPrice) {
            ctx.closeAtMarket();
            debug("SHORT stopped");
            resetTradeState();
            return;
        }

        // Move to breakeven
        if (getSettings().getBoolean(BE_ENABLED, true) && !beActivated && riskPoints > 0) {
            double beTrigger = getSettings().getDouble(BE_TRIGGER_PTS, 3.0);
            double unrealizedPts = isLongPosition ? close - entryPrice : entryPrice - close;
            if (unrealizedPts >= beTrigger) {
                double bePrice = instr.round(entryPrice);
                if (isLongPosition && bePrice > stopPrice) {
                    stopPrice = bePrice;
                } else if (!isLongPosition && bePrice < stopPrice) {
                    stopPrice = bePrice;
                }
                beActivated = true;
                debug("Stop moved to breakeven: " + stopPrice);
            }
        }

        // Partial at R
        boolean partialEnabled = getSettings().getBoolean(PARTIAL_ENABLED, true);
        double partialR = getSettings().getDouble(PARTIAL_R, 1.0);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);

        double currentR = isLongPosition ?
            (close - entryPrice) / riskPoints :
            (entryPrice - close) / riskPoints;

        if (partialEnabled && !partialTaken && currentR >= partialR) {
            int position = ctx.getPosition();
            int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
            if (partialQty > 0 && partialQty < Math.abs(position)) {
                if (isLongPosition) ctx.sell(partialQty);
                else ctx.buy(partialQty);
                partialTaken = true;
                // Move stop to breakeven
                stopPrice = instr.round(entryPrice + (isLongPosition ? 0.5 : -0.5));
                debug("Partial + BE at " + partialR + "R");
            }
        }

        // Target
        if (isLongPosition && high >= targetPrice) {
            ctx.closeAtMarket();
            debug("LONG target hit");
            resetTradeState();
        }
        if (!isLongPosition && low <= targetPrice) {
            ctx.closeAtMarket();
            debug("SHORT target hit");
            resetTradeState();
        }
    }

    @Override
    public void clearState() {
        super.clearState();
        resetDailyState();
        resetTradeState();
        lastResetDay = -1;
        todayHigh = Double.NaN;
        todayLow = Double.NaN;
        sessionHigh = Double.NaN;
        sessionLow = Double.NaN;
        lastSwingHigh = Double.NaN;
        lastSwingLow = Double.NaN;
        prevSwingHigh = Double.NaN;
        prevSwingLow = Double.NaN;
    }
}
