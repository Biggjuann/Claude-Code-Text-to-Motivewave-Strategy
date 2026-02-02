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
 * ICT Market Maker Sell Model (MMSM) Strategy
 *
 * Captures bearish reversals using the ICT sequence:
 * BSL Sweep → Market Structure Shift Down → Bearish FVG Entry
 *
 * Features:
 * - Dealing range from PDH/PDL for premium/discount context
 * - Buy-side liquidity identification (PDH, swing highs, equal highs)
 * - Sweep detection with optional close-back-below requirement
 * - Bearish market structure shift confirmation (break of swing low)
 * - Bearish FVG detection for retracement entry
 * - Multiple stop loss and take profit modes
 * - Kill zone time filtering
 * - EOD (End of Day) forced flattening with configurable cutoff time
 *
 * @version 1.0.0
 * @author MW Study Builder (ICT concepts)
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "ICT_MMSM",
    rb = "com.mw.studies.nls.strings",
    name = "ICT_MMSM",
    label = "LBL_ICT_MMSM",
    desc = "DESC_ICT_MMSM",
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
public class ICTMMSMStrategy extends Study
{
    // ==================== Input Keys ====================
    // Sessions
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";
    private static final String KILL_ZONE = "killZone";

    // EOD (End of Day) Flattening
    private static final String EOD_CLOSE_ENABLED = "eodCloseEnabled";
    private static final String EOD_CLOSE_TIME = "eodCloseTime";
    private static final String EOD_CANCEL_WORKING = "eodCancelWorking";

    // Dealing Range
    private static final String PREMIUM_THRESHOLD = "premiumThreshold";

    // Liquidity
    private static final String BSL_MODE = "bslMode";
    private static final String BSL_LOOKBACK = "bslLookback";
    private static final String SWEEP_MIN_TICKS = "sweepMinTicks";
    private static final String REQUIRE_CLOSE_BACK = "requireCloseBack";

    // Structure
    private static final String SWING_STRENGTH = "swingStrength";
    private static final String DISPLACEMENT_MIN_TICKS = "displacementMinTicks";

    // Entry
    private static final String ENTRY_MODEL = "entryModel";
    private static final String FVG_MIN_TICKS = "fvgMinTicks";
    private static final String ENTRY_PRICE_MODE = "entryPriceMode";
    private static final String MAX_BARS_TO_FILL = "maxBarsToFill";

    // Risk
    private static final String CONTRACTS = "contracts";
    private static final String STOPLOSS_ENABLED = "stoplossEnabled";
    private static final String STOPLOSS_MODE = "stoplossMode";
    private static final String STOPLOSS_TICKS = "stoplossTicks";

    // Targets
    private static final String TP_MODE = "tpMode";
    private static final String RR_MULTIPLE = "rrMultiple";
    private static final String PARTIAL_ENABLED = "partialEnabled";
    private static final String PARTIAL_PCT = "partialPct";

    // Limits
    private static final String MAX_TRADES_PER_DAY = "maxTradesPerDay";

    // Path keys
    private static final String DEALING_HIGH_PATH = "dealingHighPath";
    private static final String DEALING_LOW_PATH = "dealingLowPath";
    private static final String EQ_PATH = "eqPath";
    private static final String BSL_PATH = "bslPath";

    // Mode constants
    // Kill zones: 0=NY_AM, 1=NY_PM, 2=LONDON_AM
    private static final int KZ_NY_AM = 0;
    private static final int KZ_NY_PM = 1;
    private static final int KZ_LONDON = 2;

    // BSL modes: 0=PDH, 1=SWING_HIGH, 2=EQUAL_HIGHS
    private static final int BSL_PDH = 0;
    private static final int BSL_SWING = 1;
    private static final int BSL_EQUAL = 2;

    // Entry models: 0=FVG, 1=OB
    private static final int ENTRY_FVG = 0;
    private static final int ENTRY_OB = 1;

    // Entry price: 0=TOP, 1=MID, 2=BOTTOM
    private static final int PRICE_TOP = 0;
    private static final int PRICE_MID = 1;
    private static final int PRICE_BOTTOM = 2;

    // Stop modes: 0=FIXED, 1=ABOVE_SWEEP, 2=ABOVE_ZONE, 3=ABOVE_PDH
    private static final int STOP_FIXED = 0;
    private static final int STOP_ABOVE_SWEEP = 1;
    private static final int STOP_ABOVE_ZONE = 2;
    private static final int STOP_ABOVE_PDH = 3;

    // TP modes: 0=RR, 1=EQUILIBRIUM, 2=PDL
    private static final int TP_RR = 0;
    private static final int TP_EQ = 1;
    private static final int TP_PDL = 2;

    // ==================== Values ====================
    enum Values {
        DEALING_HIGH, DEALING_LOW, EQUILIBRIUM, BSL_LEVEL, MSS_LEVEL,
        FVG_TOP, FVG_BOTTOM, IN_TRADE_SESSION, IN_PREMIUM
    }

    // ==================== Signals ====================
    enum Signals { BSL_SWEEP, MSS_CONFIRMED, MMSM_SHORT }

    // ==================== State Variables ====================
    // Daily reset
    private double dealingHigh = Double.NaN;
    private double dealingLow = Double.NaN;
    private boolean dealingComplete = false;
    private double bslLevel = Double.NaN;
    private boolean bslSwept = false;
    private double sweepHigh = Double.NaN;
    private double mssLevel = Double.NaN;
    private boolean mssConfirmed = false;
    private int tradesToday = 0;
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // FVG zone
    private double fvgTop = Double.NaN;
    private double fvgBottom = Double.NaN;
    private boolean fvgDetected = false;
    private int fvgBarIndex = -1;

    // Position tracking
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double tp1Price = 0;
    private double tp2Price = 0;
    private boolean partialTaken = false;
    private int entryBarIndex = -1;
    private boolean waitingForFill = false;

    // Previous day tracking
    private double prevDayHigh = Double.NaN;
    private double prevDayLow = Double.NaN;
    private double todayHigh = Double.NaN;
    private double todayLow = Double.NaN;

    // NY timezone
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Sessions Tab =====
        var tab = sd.addTab("Sessions");
        var grp = tab.addGroup("Trade Window (ET)");
        grp.addRow(new IntegerDescriptor(TRADE_START, "Start Time (HHMM)", 830, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(TRADE_END, "End Time (HHMM)", 1200, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(KILL_ZONE, "Kill Zone (0=NY AM, 1=NY PM, 2=London)", KZ_NY_AM, 0, 2, 1));

        grp = tab.addGroup("End of Day (EOD)");
        grp.addRow(new BooleanDescriptor(EOD_CLOSE_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_CLOSE_TIME, "EOD Close Time (HHMM)", 1640, 0, 2359, 1));
        grp.addRow(new BooleanDescriptor(EOD_CANCEL_WORKING, "Cancel Working Orders at EOD", true));

        // ===== Dealing Range Tab =====
        tab = sd.addTab("Dealing Range");
        grp = tab.addGroup("Premium/Discount");
        grp.addRow(new DoubleDescriptor(PREMIUM_THRESHOLD, "Premium Threshold (0.5=EQ)", 0.5, 0.0, 1.0, 0.05));

        // ===== Liquidity Tab =====
        tab = sd.addTab("Liquidity");
        grp = tab.addGroup("Buy-Side Liquidity (BSL)");
        grp.addRow(new IntegerDescriptor(BSL_MODE, "BSL Mode (0=PDH, 1=Swing, 2=EqualHighs)", BSL_PDH, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(BSL_LOOKBACK, "Swing/EqualHigh Lookback", 50, 5, 200, 1));
        grp.addRow(new IntegerDescriptor(SWEEP_MIN_TICKS, "Min Sweep Penetration (ticks)", 2, 1, 50, 1));
        grp.addRow(new BooleanDescriptor(REQUIRE_CLOSE_BACK, "Require Close Back Below BSL", true));

        // ===== Structure Tab =====
        tab = sd.addTab("Structure");
        grp = tab.addGroup("Market Structure Shift");
        grp.addRow(new IntegerDescriptor(SWING_STRENGTH, "Swing Strength (bars)", 2, 1, 10, 1));
        grp.addRow(new IntegerDescriptor(DISPLACEMENT_MIN_TICKS, "Min Displacement Body (ticks)", 8, 1, 50, 1));

        // ===== Entry Tab =====
        tab = sd.addTab("Entry");
        grp = tab.addGroup("Entry Zone");
        grp.addRow(new IntegerDescriptor(ENTRY_MODEL, "Entry Model (0=FVG, 1=OB)", ENTRY_FVG, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(FVG_MIN_TICKS, "Min FVG Size (ticks)", 2, 1, 50, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_PRICE_MODE, "Entry Price (0=Top, 1=Mid, 2=Bottom)", PRICE_MID, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(MAX_BARS_TO_FILL, "Max Bars to Fill Entry", 30, 1, 100, 1));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 1, 1, 100, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new BooleanDescriptor(STOPLOSS_ENABLED, "Enable Stop Loss", true));
        grp.addRow(new IntegerDescriptor(STOPLOSS_MODE, "Stop Mode (0=Fixed, 1=AboveSweep, 2=AboveZone, 3=AbovePDH)", STOP_ABOVE_SWEEP, 0, 3, 1));
        grp.addRow(new IntegerDescriptor(STOPLOSS_TICKS, "Stop Distance/Buffer (ticks)", 20, 1, 200, 1));

        // ===== Targets Tab =====
        tab = sd.addTab("Targets");
        grp = tab.addGroup("Take Profit");
        grp.addRow(new IntegerDescriptor(TP_MODE, "TP Mode (0=RR, 1=Equilibrium, 2=PDL)", TP_RR, 0, 2, 1));
        grp.addRow(new DoubleDescriptor(RR_MULTIPLE, "RR Multiple", 2.0, 0.5, 10.0, 0.25));
        grp.addRow(new BooleanDescriptor(PARTIAL_ENABLED, "Enable Partial TP", true));
        grp.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial % at TP1", 50, 1, 99, 1));

        // ===== Limits Tab =====
        tab = sd.addTab("Limits");
        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_PER_DAY, "Max Trades Per Day", 1, 1, 10, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Levels");
        grp.addRow(new PathDescriptor(DEALING_HIGH_PATH, "PDH / Dealing High",
            defaults.getRed(), 1.5f, new float[]{8, 4}, true, true, true));
        grp.addRow(new PathDescriptor(DEALING_LOW_PATH, "PDL / Dealing Low",
            defaults.getGreen(), 1.5f, new float[]{8, 4}, true, true, true));
        grp.addRow(new PathDescriptor(EQ_PATH, "Equilibrium",
            defaults.getYellow(), 1.0f, new float[]{4, 4}, true, true, true));
        grp.addRow(new PathDescriptor(BSL_PATH, "BSL Level",
            defaults.getOrange(), 2.0f, null, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(CONTRACTS, STOPLOSS_TICKS, RR_MULTIPLE, MAX_TRADES_PER_DAY);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(BSL_MODE, TP_MODE, RR_MULTIPLE);

        desc.exportValue(new ValueDescriptor(Values.DEALING_HIGH, "PDH", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.DEALING_LOW, "PDL", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.EQUILIBRIUM, "Equilibrium", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.BSL_LEVEL, "BSL Level", new String[]{}));

        desc.declarePath(Values.DEALING_HIGH, DEALING_HIGH_PATH);
        desc.declarePath(Values.DEALING_LOW, DEALING_LOW_PATH);
        desc.declarePath(Values.EQUILIBRIUM, EQ_PATH);
        desc.declarePath(Values.BSL_LEVEL, BSL_PATH);

        desc.declareSignal(Signals.BSL_SWEEP, "BSL Sweep Detected");
        desc.declareSignal(Signals.MSS_CONFIRMED, "MSS Down Confirmed");
        desc.declareSignal(Signals.MMSM_SHORT, "MMSM Short Entry");

        desc.setRangeKeys(Values.DEALING_HIGH, Values.DEALING_LOW);
    }

    @Override
    public int getMinBars() {
        return getSettings().getInteger(BSL_LOOKBACK, 50) + 20;
    }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();

        if (index < 10) return;

        // Get bar time in NY timezone
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);

        // Daily reset and PDH/PDL update
        if (barDay != lastResetDay) {
            // Store yesterday's range as dealing range
            if (!Double.isNaN(todayHigh) && !Double.isNaN(todayLow)) {
                prevDayHigh = todayHigh;
                prevDayLow = todayLow;
                dealingHigh = prevDayHigh;
                dealingLow = prevDayLow;
                dealingComplete = true;
            }
            // Reset today's range
            todayHigh = Double.NaN;
            todayLow = Double.NaN;
            resetDailyState();
            lastResetDay = barDay;
        }

        // Track today's high/low
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        double open = series.getOpen(index);

        if (Double.isNaN(todayHigh) || high > todayHigh) todayHigh = high;
        if (Double.isNaN(todayLow) || low < todayLow) todayLow = low;

        // Get settings
        int tradeStart = getSettings().getInteger(TRADE_START, 830);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1200);
        int killZone = getSettings().getInteger(KILL_ZONE, KZ_NY_AM);
        double premiumThreshold = getSettings().getDouble(PREMIUM_THRESHOLD, 0.5);
        int bslMode = getSettings().getInteger(BSL_MODE, BSL_PDH);
        int bslLookback = getSettings().getInteger(BSL_LOOKBACK, 50);
        int sweepMinTicks = getSettings().getInteger(SWEEP_MIN_TICKS, 2);
        boolean requireCloseBack = getSettings().getBoolean(REQUIRE_CLOSE_BACK, true);
        int swingStrength = getSettings().getInteger(SWING_STRENGTH, 2);
        int fvgMinTicks = getSettings().getInteger(FVG_MIN_TICKS, 2);
        int maxTrades = getSettings().getInteger(MAX_TRADES_PER_DAY, 1);

        // Check if in trade session
        boolean inTradeSession = barTimeInt >= tradeStart && barTimeInt < tradeEnd;
        boolean inKillZone = isInKillZone(barTimeInt, killZone);
        series.setBoolean(index, Values.IN_TRADE_SESSION, inTradeSession && inKillZone);

        // Plot dealing range levels
        if (dealingComplete) {
            series.setDouble(index, Values.DEALING_HIGH, dealingHigh);
            series.setDouble(index, Values.DEALING_LOW, dealingLow);
            double eq = (dealingHigh + dealingLow) / 2.0;
            series.setDouble(index, Values.EQUILIBRIUM, eq);

            // Check if in premium (above equilibrium threshold)
            double premiumMin = dealingLow + (dealingHigh - dealingLow) * premiumThreshold;
            series.setBoolean(index, Values.IN_PREMIUM, close >= premiumMin);
        }

        // Identify BSL level if not set
        if (dealingComplete && Double.isNaN(bslLevel)) {
            bslLevel = identifyBSL(series, index, bslMode, bslLookback, swingStrength, tickSize);
        }

        // Plot BSL level
        if (!Double.isNaN(bslLevel)) {
            series.setDouble(index, Values.BSL_LEVEL, bslLevel);
        }

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (!dealingComplete) return;

        // Phase 1: Detect BSL sweep (price trades above BSL)
        if (!bslSwept && !Double.isNaN(bslLevel)) {
            double sweepThreshold = bslLevel + (sweepMinTicks * tickSize);
            if (high >= sweepThreshold) {
                boolean validSweep = true;
                if (requireCloseBack && close >= bslLevel) {
                    validSweep = false;
                }
                if (validSweep) {
                    bslSwept = true;
                    sweepHigh = high;
                    ctx.signal(index, Signals.BSL_SWEEP,
                        String.format("BSL Sweep: High=%.2f above BSL=%.2f", high, bslLevel), high);

                    // Find MSS level (most recent swing low before sweep)
                    mssLevel = findSwingLow(series, index, swingStrength);
                }
            }
        }

        // Update sweep high if still sweeping
        if (bslSwept && !mssConfirmed && high > sweepHigh) {
            sweepHigh = high;
        }

        // Phase 2: Detect MSS Down (break of swing low)
        if (bslSwept && !mssConfirmed && !Double.isNaN(mssLevel)) {
            if (close < mssLevel) {
                // Check for displacement (strong body)
                int dispMinTicks = getSettings().getInteger(DISPLACEMENT_MIN_TICKS, 8);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispMinTicks * tickSize) {
                    mssConfirmed = true;
                    series.setDouble(index, Values.MSS_LEVEL, mssLevel);
                    ctx.signal(index, Signals.MSS_CONFIRMED,
                        String.format("MSS Down Confirmed: Close=%.2f below MSS=%.2f", close, mssLevel), close);
                }
            }
        }

        // Phase 3: Detect Bearish FVG after MSS
        if (mssConfirmed && !fvgDetected && index >= 2) {
            // ICT Bearish FVG: bar[2].high < bar[0].low (gap between)
            double bar0Low = series.getLow(index - 2);
            double bar2High = series.getHigh(index);

            if (bar2High < bar0Low) {
                double gapSize = bar0Low - bar2High;
                if (gapSize >= fvgMinTicks * tickSize) {
                    fvgTop = bar0Low;      // Top of FVG (for short entry)
                    fvgBottom = bar2High;  // Bottom of FVG
                    fvgDetected = true;
                    fvgBarIndex = index;
                    series.setDouble(index, Values.FVG_TOP, fvgTop);
                    series.setDouble(index, Values.FVG_BOTTOM, fvgBottom);
                }
            }
        }

        // Store FVG bounds for plotting
        if (fvgDetected) {
            series.setDouble(index, Values.FVG_TOP, fvgTop);
            series.setDouble(index, Values.FVG_BOTTOM, fvgBottom);
        }

        // Check EOD cutoff - block new entries
        boolean eodEnabled = getSettings().getBoolean(EOD_CLOSE_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_CLOSE_TIME, 1640);
        boolean pastEodCutoff = eodEnabled && barTimeInt >= eodTime;

        // Check if entry conditions are met
        if (!waitingForFill && fvgDetected && inTradeSession && inKillZone && tradesToday < maxTrades && !pastEodCutoff) {
            // Check if in premium
            double premiumMin = dealingLow + (dealingHigh - dealingLow) * premiumThreshold;
            if (close >= premiumMin) {
                // Generate entry signal
                waitingForFill = true;
                entryBarIndex = index;
                ctx.signal(index, Signals.MMSM_SHORT, "MMSM Short Setup Ready", close);

                var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
                if (marker.isEnabled()) {
                    var coord = new Coordinate(barTime, high);
                    addFigure(new Marker(coord, Enums.Position.TOP, marker, "MMSM"));
                }
            }
        }

        // Check for entry cancellation (max bars exceeded)
        if (waitingForFill && entryBarIndex > 0) {
            int maxBars = getSettings().getInteger(MAX_BARS_TO_FILL, 30);
            if (index - entryBarIndex > maxBars) {
                // Cancel setup
                waitingForFill = false;
                fvgDetected = false;
                debug("Entry cancelled - max bars exceeded");
            }
        }

        series.setComplete(index);
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("ICT MMSM Strategy activated");
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
        if (signal != Signals.MMSM_SHORT) return;

        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        double tickSize = instr.getTickSize();

        // Check EOD cutoff - block new entries
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

        if (position != 0) {
            debug("Already in position, ignoring signal");
            return;
        }

        if (!fvgDetected || Double.isNaN(fvgTop) || Double.isNaN(fvgBottom)) {
            debug("No valid FVG zone");
            return;
        }

        int qty = getSettings().getInteger(CONTRACTS, 1);
        int entryPriceMode = getSettings().getInteger(ENTRY_PRICE_MODE, PRICE_MID);
        int stopMode = getSettings().getInteger(STOPLOSS_MODE, STOP_ABOVE_SWEEP);
        int stopTicks = getSettings().getInteger(STOPLOSS_TICKS, 20);
        int tpMode = getSettings().getInteger(TP_MODE, TP_RR);
        double rrMult = getSettings().getDouble(RR_MULTIPLE, 2.0);
        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);

        // Calculate entry price (for shorts, typically enter at top of FVG on retrace)
        double entryPx;
        switch (entryPriceMode) {
            case PRICE_TOP:
                entryPx = fvgTop;
                break;
            case PRICE_BOTTOM:
                entryPx = fvgBottom;
                break;
            default:
                entryPx = (fvgTop + fvgBottom) / 2.0;
        }
        entryPx = instr.round(entryPx);

        // Enter short at market
        ctx.sell(qty);
        entryPrice = instr.getLastPrice();
        tradesToday++;
        partialTaken = false;

        // Calculate stop (above for shorts)
        if (stopEnabled) {
            double stopBuffer = stopTicks * tickSize;
            switch (stopMode) {
                case STOP_FIXED:
                    stopPrice = entryPrice + stopBuffer;
                    break;
                case STOP_ABOVE_SWEEP:
                    stopPrice = sweepHigh + stopBuffer;
                    break;
                case STOP_ABOVE_ZONE:
                    stopPrice = fvgTop + stopBuffer;
                    break;
                case STOP_ABOVE_PDH:
                    stopPrice = dealingHigh + stopBuffer;
                    break;
                default:
                    stopPrice = entryPrice + stopBuffer;
            }
            stopPrice = instr.round(stopPrice);
        }

        // Calculate targets (downward for shorts)
        double risk = stopPrice - entryPrice;
        double equilibrium = (dealingHigh + dealingLow) / 2.0;

        // TP1 is equilibrium for partials
        tp1Price = equilibrium;

        // Final TP based on mode
        switch (tpMode) {
            case TP_RR:
                tp2Price = entryPrice - (risk * rrMult);
                break;
            case TP_EQ:
                tp2Price = equilibrium;
                break;
            case TP_PDL:
                tp2Price = dealingLow;
                break;
            default:
                tp2Price = entryPrice - (risk * rrMult);
        }
        tp2Price = instr.round(tp2Price);

        debug(String.format("MMSM SHORT: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
            qty, entryPrice, stopPrice, tp1Price, tp2Price));

        waitingForFill = false;
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

            // Cancel working orders / invalidate pending setups
            if (getSettings().getBoolean(EOD_CANCEL_WORKING, true)) {
                waitingForFill = false;
                fvgDetected = false;
                debug("EOD: Cancelled pending entry setup");
            }

            // Close any open position
            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD: Forced flat at " + barTimeInt);
                resetTradeState();
            }

            eodProcessed = true;
            return; // Skip normal exit logic after EOD
        }

        // ===== Normal Exit Logic =====
        int position = ctx.getPosition();
        if (position >= 0) return; // Only process for short positions

        var instr = ctx.getInstrument();
        double high = series.getHigh(index);
        double low = series.getLow(index);

        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);
        boolean partialEnabled = getSettings().getBoolean(PARTIAL_ENABLED, true);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);

        // Check stop (above for shorts)
        if (stopEnabled && stopPrice > 0 && high >= stopPrice) {
            ctx.closeAtMarket();
            debug("SHORT stopped out at " + high);
            resetTradeState();
            return;
        }

        // Check TP1 (partial) - price goes down for shorts
        if (partialEnabled && !partialTaken && low <= tp1Price) {
            int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
            if (partialQty > 0 && partialQty < Math.abs(position)) {
                ctx.buy(partialQty);
                partialTaken = true;
                debug("Partial cover: " + partialQty + " at TP1=" + tp1Price);
            }
        }

        // Check TP2 (final)
        if (low <= tp2Price) {
            ctx.closeAtMarket();
            debug("SHORT target hit at " + low);
            resetTradeState();
        }
    }

    // ==================== Helper Methods ====================

    private void resetDailyState() {
        bslLevel = Double.NaN;
        bslSwept = false;
        sweepHigh = Double.NaN;
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
    }

    private double identifyBSL(DataSeries series, int index, int mode, int lookback, int swingStrength, double tickSize) {
        switch (mode) {
            case BSL_PDH:
                return dealingHigh;
            case BSL_SWING:
                return findSwingHighForBSL(series, index, lookback, swingStrength);
            case BSL_EQUAL:
                return findEqualHighs(series, index, lookback, tickSize * 4); // 4 tick tolerance
            default:
                return dealingHigh;
        }
    }

    private double findSwingHighForBSL(DataSeries series, int index, int lookback, int strength) {
        double highestSwing = Double.MIN_VALUE;
        int start = Math.max(strength, index - lookback);

        for (int i = start; i <= index - strength; i++) {
            double high = series.getHigh(i);
            boolean isSwing = true;

            // Check left side
            for (int j = 1; j <= strength && isSwing; j++) {
                if (series.getHigh(i - j) >= high) isSwing = false;
            }
            // Check right side
            for (int j = 1; j <= strength && isSwing; j++) {
                if (series.getHigh(i + j) >= high) isSwing = false;
            }

            if (isSwing && high > highestSwing) {
                highestSwing = high;
            }
        }

        return highestSwing == Double.MIN_VALUE ? dealingHigh : highestSwing;
    }

    private double findSwingLow(DataSeries series, int index, int strength) {
        // Find most recent swing low before current bar (for MSS level)
        for (int i = index - strength - 1; i >= strength; i--) {
            double low = series.getLow(i);
            boolean isSwing = true;

            for (int j = 1; j <= strength && isSwing; j++) {
                if (i - j >= 0 && series.getLow(i - j) <= low) isSwing = false;
                if (i + j <= index && series.getLow(i + j) <= low) isSwing = false;
            }

            if (isSwing) return low;
        }

        // Fallback to lowest low in recent bars
        double lowest = series.getLow(index);
        for (int i = index - 10; i < index; i++) {
            if (i >= 0 && series.getLow(i) < lowest) {
                lowest = series.getLow(i);
            }
        }
        return lowest;
    }

    private double findEqualHighs(DataSeries series, int index, int lookback, double tolerance) {
        int start = Math.max(0, index - lookback);
        double[] highs = new double[lookback];
        int count = 0;

        for (int i = start; i < index && count < lookback; i++) {
            highs[count++] = series.getHigh(i);
        }

        // Find clusters of equal highs
        double bestClusterHigh = dealingHigh;
        int bestClusterSize = 0;

        for (int i = 0; i < count; i++) {
            int clusterSize = 1;
            for (int j = i + 1; j < count; j++) {
                if (Math.abs(highs[i] - highs[j]) <= tolerance) {
                    clusterSize++;
                }
            }
            if (clusterSize > bestClusterSize) {
                bestClusterSize = clusterSize;
                bestClusterHigh = highs[i];
            }
        }

        return bestClusterSize >= 2 ? bestClusterHigh : dealingHigh;
    }

    private boolean isInKillZone(int timeInt, int killZone) {
        switch (killZone) {
            case KZ_NY_AM:
                return timeInt >= 830 && timeInt < 1100;
            case KZ_NY_PM:
                return timeInt >= 1330 && timeInt < 1600;
            case KZ_LONDON:
                return timeInt >= 300 && timeInt < 500;
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
        prevDayHigh = Double.NaN;
        prevDayLow = Double.NaN;
        todayHigh = Double.NaN;
        todayLow = Double.NaN;
        dealingHigh = Double.NaN;
        dealingLow = Double.NaN;
        dealingComplete = false;
        eodProcessed = false;
    }
}
