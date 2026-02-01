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
 * ICT Market Maker Buy Model (MMBM) Strategy
 *
 * Captures bullish reversals using the ICT sequence:
 * SSL Sweep → Market Structure Shift (MSS) → FVG/OB Entry
 *
 * Features:
 * - Dealing range from PDH/PDL for premium/discount context
 * - Sell-side liquidity identification (PDL, swing lows, equal lows)
 * - Sweep detection with optional close-back-above requirement
 * - Market structure shift confirmation (break of swing high)
 * - Bullish FVG detection for retracement entry
 * - Multiple stop loss and take profit modes
 * - Kill zone time filtering
 * - EOD (End of Day) forced flattening with configurable cutoff time
 *
 * @version 1.1.0
 * @author MW Study Builder (ICT concepts)
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "ICT_MMBM",
    rb = "com.mw.studies.nls.strings",
    name = "ICT_MMBM",
    label = "LBL_ICT_MMBM",
    desc = "DESC_ICT_MMBM",
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
public class ICTMMBMStrategy extends Study
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
    private static final String DISCOUNT_THRESHOLD = "discountThreshold";

    // Liquidity
    private static final String SSL_MODE = "sslMode";
    private static final String SSL_LOOKBACK = "sslLookback";
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
    private static final String SSL_PATH = "sslPath";

    // Mode constants
    // Kill zones: 0=NY_AM, 1=NY_PM, 2=LONDON_AM, 3=CUSTOM
    private static final int KZ_NY_AM = 0;
    private static final int KZ_NY_PM = 1;
    private static final int KZ_LONDON = 2;

    // SSL modes: 0=PDL, 1=SWING_LOW, 2=EQUAL_LOWS
    private static final int SSL_PDL = 0;
    private static final int SSL_SWING = 1;
    private static final int SSL_EQUAL = 2;

    // Entry models: 0=FVG, 1=OB
    private static final int ENTRY_FVG = 0;
    private static final int ENTRY_OB = 1;

    // Entry price: 0=TOP, 1=MID, 2=BOTTOM
    private static final int PRICE_TOP = 0;
    private static final int PRICE_MID = 1;
    private static final int PRICE_BOTTOM = 2;

    // Stop modes: 0=FIXED, 1=BELOW_SWEEP, 2=BELOW_ZONE, 3=BELOW_PDL
    private static final int STOP_FIXED = 0;
    private static final int STOP_BELOW_SWEEP = 1;
    private static final int STOP_BELOW_ZONE = 2;
    private static final int STOP_BELOW_PDL = 3;

    // TP modes: 0=RR, 1=EQUILIBRIUM, 2=PDH
    private static final int TP_RR = 0;
    private static final int TP_EQ = 1;
    private static final int TP_PDH = 2;

    // ==================== Values ====================
    enum Values {
        DEALING_HIGH, DEALING_LOW, EQUILIBRIUM, SSL_LEVEL, MSS_LEVEL,
        FVG_TOP, FVG_BOTTOM, IN_TRADE_SESSION, IN_DISCOUNT
    }

    // ==================== Signals ====================
    enum Signals { SSL_SWEEP, MSS_CONFIRMED, MMBM_LONG }

    // ==================== State Variables ====================
    // Daily reset
    private double dealingHigh = Double.NaN;
    private double dealingLow = Double.NaN;
    private boolean dealingComplete = false;
    private double sslLevel = Double.NaN;
    private boolean sslSwept = false;
    private double sweepLow = Double.NaN;
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
        grp.addRow(new DoubleDescriptor(DISCOUNT_THRESHOLD, "Discount Threshold (0.5=EQ)", 0.5, 0.0, 1.0, 0.05));

        // ===== Liquidity Tab =====
        tab = sd.addTab("Liquidity");
        grp = tab.addGroup("Sell-Side Liquidity (SSL)");
        grp.addRow(new IntegerDescriptor(SSL_MODE, "SSL Mode (0=PDL, 1=Swing, 2=EqualLows)", SSL_PDL, 0, 2, 1));
        grp.addRow(new IntegerDescriptor(SSL_LOOKBACK, "Swing/EqualLow Lookback", 50, 5, 200, 1));
        grp.addRow(new IntegerDescriptor(SWEEP_MIN_TICKS, "Min Sweep Penetration (ticks)", 2, 1, 50, 1));
        grp.addRow(new BooleanDescriptor(REQUIRE_CLOSE_BACK, "Require Close Back Above SSL", true));

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
        grp.addRow(new IntegerDescriptor(STOPLOSS_MODE, "Stop Mode (0=Fixed, 1=BelowSweep, 2=BelowZone, 3=BelowPDL)", STOP_BELOW_SWEEP, 0, 3, 1));
        grp.addRow(new IntegerDescriptor(STOPLOSS_TICKS, "Stop Distance/Buffer (ticks)", 20, 1, 200, 1));

        // ===== Targets Tab =====
        tab = sd.addTab("Targets");
        grp = tab.addGroup("Take Profit");
        grp.addRow(new IntegerDescriptor(TP_MODE, "TP Mode (0=RR, 1=Equilibrium, 2=PDH)", TP_RR, 0, 2, 1));
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
        grp.addRow(new PathDescriptor(SSL_PATH, "SSL Level",
            defaults.getOrange(), 2.0f, null, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(CONTRACTS, STOPLOSS_TICKS, RR_MULTIPLE, MAX_TRADES_PER_DAY);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(SSL_MODE, TP_MODE, RR_MULTIPLE);

        desc.exportValue(new ValueDescriptor(Values.DEALING_HIGH, "PDH", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.DEALING_LOW, "PDL", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.EQUILIBRIUM, "Equilibrium", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.SSL_LEVEL, "SSL Level", new String[]{}));

        desc.declarePath(Values.DEALING_HIGH, DEALING_HIGH_PATH);
        desc.declarePath(Values.DEALING_LOW, DEALING_LOW_PATH);
        desc.declarePath(Values.EQUILIBRIUM, EQ_PATH);
        desc.declarePath(Values.SSL_LEVEL, SSL_PATH);

        desc.declareSignal(Signals.SSL_SWEEP, "SSL Sweep Detected");
        desc.declareSignal(Signals.MSS_CONFIRMED, "MSS Confirmed");
        desc.declareSignal(Signals.MMBM_LONG, "MMBM Long Entry");

        desc.setRangeKeys(Values.DEALING_HIGH, Values.DEALING_LOW);
    }

    @Override
    public int getMinBars() {
        return getSettings().getInteger(SSL_LOOKBACK, 50) + 20;
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
        double discountThreshold = getSettings().getDouble(DISCOUNT_THRESHOLD, 0.5);
        int sslMode = getSettings().getInteger(SSL_MODE, SSL_PDL);
        int sslLookback = getSettings().getInteger(SSL_LOOKBACK, 50);
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

            // Check if in discount
            double discountMax = dealingLow + (dealingHigh - dealingLow) * discountThreshold;
            series.setBoolean(index, Values.IN_DISCOUNT, close <= discountMax);
        }

        // Identify SSL level if not set
        if (dealingComplete && Double.isNaN(sslLevel)) {
            sslLevel = identifySSL(series, index, sslMode, sslLookback, swingStrength, tickSize);
        }

        // Plot SSL level
        if (!Double.isNaN(sslLevel)) {
            series.setDouble(index, Values.SSL_LEVEL, sslLevel);
        }

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (!dealingComplete) return;

        // Phase 1: Detect SSL sweep
        if (!sslSwept && !Double.isNaN(sslLevel)) {
            double sweepThreshold = sslLevel - (sweepMinTicks * tickSize);
            if (low <= sweepThreshold) {
                boolean validSweep = true;
                if (requireCloseBack && close <= sslLevel) {
                    validSweep = false;
                }
                if (validSweep) {
                    sslSwept = true;
                    sweepLow = low;
                    ctx.signal(index, Signals.SSL_SWEEP,
                        String.format("SSL Sweep: Low=%.2f below SSL=%.2f", low, sslLevel), low);

                    // Find MSS level (most recent swing high before sweep)
                    mssLevel = findSwingHigh(series, index, swingStrength);
                }
            }
        }

        // Update sweep low if still sweeping
        if (sslSwept && !mssConfirmed && low < sweepLow) {
            sweepLow = low;
        }

        // Phase 2: Detect MSS (break of swing high)
        if (sslSwept && !mssConfirmed && !Double.isNaN(mssLevel)) {
            if (close > mssLevel) {
                // Check for displacement (strong body)
                int dispMinTicks = getSettings().getInteger(DISPLACEMENT_MIN_TICKS, 8);
                double bodySize = Math.abs(close - open);
                if (bodySize >= dispMinTicks * tickSize) {
                    mssConfirmed = true;
                    series.setDouble(index, Values.MSS_LEVEL, mssLevel);
                    ctx.signal(index, Signals.MSS_CONFIRMED,
                        String.format("MSS Confirmed: Close=%.2f above MSS=%.2f", close, mssLevel), close);
                }
            }
        }

        // Phase 3: Detect Bullish FVG after MSS
        if (mssConfirmed && !fvgDetected && index >= 2) {
            // ICT Bullish FVG: bar[2].low > bar[0].high (gap between)
            double bar0High = series.getHigh(index - 2);
            double bar2Low = series.getLow(index);

            if (bar2Low > bar0High) {
                double gapSize = bar2Low - bar0High;
                if (gapSize >= fvgMinTicks * tickSize) {
                    fvgTop = bar2Low;
                    fvgBottom = bar0High;
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
            // Check if in discount
            double discountMax = dealingLow + (dealingHigh - dealingLow) * discountThreshold;
            if (close <= discountMax) {
                // Generate entry signal
                waitingForFill = true;
                entryBarIndex = index;
                ctx.signal(index, Signals.MMBM_LONG, "MMBM Long Setup Ready", close);

                var marker = getSettings().getMarker(Inputs.UP_MARKER);
                if (marker.isEnabled()) {
                    var coord = new Coordinate(barTime, low);
                    addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "MMBM"));
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
        debug("ICT MMBM Strategy activated");
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
        if (signal != Signals.MMBM_LONG) return;

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
        int stopMode = getSettings().getInteger(STOPLOSS_MODE, STOP_BELOW_SWEEP);
        int stopTicks = getSettings().getInteger(STOPLOSS_TICKS, 20);
        int tpMode = getSettings().getInteger(TP_MODE, TP_RR);
        double rrMult = getSettings().getDouble(RR_MULTIPLE, 2.0);
        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);

        // Calculate entry price
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

        // Enter at market (simplification - true ICT would use limit)
        ctx.buy(qty);
        entryPrice = instr.getLastPrice();
        tradesToday++;
        partialTaken = false;

        // Calculate stop
        if (stopEnabled) {
            double stopBuffer = stopTicks * tickSize;
            switch (stopMode) {
                case STOP_FIXED:
                    stopPrice = entryPrice - stopBuffer;
                    break;
                case STOP_BELOW_SWEEP:
                    stopPrice = sweepLow - stopBuffer;
                    break;
                case STOP_BELOW_ZONE:
                    stopPrice = fvgBottom - stopBuffer;
                    break;
                case STOP_BELOW_PDL:
                    stopPrice = dealingLow - stopBuffer;
                    break;
                default:
                    stopPrice = entryPrice - stopBuffer;
            }
            stopPrice = instr.round(stopPrice);
        }

        // Calculate targets
        double risk = entryPrice - stopPrice;
        double equilibrium = (dealingHigh + dealingLow) / 2.0;

        // TP1 is always equilibrium for partials
        tp1Price = equilibrium;

        // Final TP based on mode
        switch (tpMode) {
            case TP_RR:
                tp2Price = entryPrice + (risk * rrMult);
                break;
            case TP_EQ:
                tp2Price = equilibrium;
                break;
            case TP_PDH:
                tp2Price = dealingHigh;
                break;
            default:
                tp2Price = entryPrice + (risk * rrMult);
        }
        tp2Price = instr.round(tp2Price);

        debug(String.format("MMBM LONG: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, TP2=%.2f",
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
        if (position <= 0) return;

        var instr = ctx.getInstrument();
        double high = series.getHigh(index);
        double low = series.getLow(index);

        boolean stopEnabled = getSettings().getBoolean(STOPLOSS_ENABLED, true);
        boolean partialEnabled = getSettings().getBoolean(PARTIAL_ENABLED, true);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);

        // Check stop
        if (stopEnabled && stopPrice > 0 && low <= stopPrice) {
            ctx.closeAtMarket();
            debug("LONG stopped out at " + low);
            resetTradeState();
            return;
        }

        // Check TP1 (partial)
        if (partialEnabled && !partialTaken && high >= tp1Price) {
            int partialQty = (int) Math.ceil(position * partialPct / 100.0);
            if (partialQty > 0 && partialQty < position) {
                ctx.sell(partialQty);
                partialTaken = true;
                debug("Partial exit: " + partialQty + " at TP1=" + tp1Price);
            }
        }

        // Check TP2 (final)
        if (high >= tp2Price) {
            ctx.closeAtMarket();
            debug("LONG target hit at " + high);
            resetTradeState();
        }
    }

    // ==================== Helper Methods ====================

    private void resetDailyState() {
        sslLevel = Double.NaN;
        sslSwept = false;
        sweepLow = Double.NaN;
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

    private double identifySSL(DataSeries series, int index, int mode, int lookback, int swingStrength, double tickSize) {
        switch (mode) {
            case SSL_PDL:
                return dealingLow;
            case SSL_SWING:
                return findSwingLow(series, index, lookback, swingStrength);
            case SSL_EQUAL:
                return findEqualLows(series, index, lookback, tickSize * 4); // 4 tick tolerance
            default:
                return dealingLow;
        }
    }

    private double findSwingLow(DataSeries series, int index, int lookback, int strength) {
        double lowestSwing = Double.MAX_VALUE;
        int start = Math.max(strength, index - lookback);

        for (int i = start; i <= index - strength; i++) {
            double low = series.getLow(i);
            boolean isSwing = true;

            // Check left side
            for (int j = 1; j <= strength && isSwing; j++) {
                if (series.getLow(i - j) <= low) isSwing = false;
            }
            // Check right side
            for (int j = 1; j <= strength && isSwing; j++) {
                if (series.getLow(i + j) <= low) isSwing = false;
            }

            if (isSwing && low < lowestSwing) {
                lowestSwing = low;
            }
        }

        return lowestSwing == Double.MAX_VALUE ? dealingLow : lowestSwing;
    }

    private double findSwingHigh(DataSeries series, int index, int strength) {
        // Find most recent swing high before current bar
        for (int i = index - strength - 1; i >= strength; i--) {
            double high = series.getHigh(i);
            boolean isSwing = true;

            for (int j = 1; j <= strength && isSwing; j++) {
                if (i - j >= 0 && series.getHigh(i - j) >= high) isSwing = false;
                if (i + j <= index && series.getHigh(i + j) >= high) isSwing = false;
            }

            if (isSwing) return high;
        }

        // Fallback to highest high in recent bars
        double highest = series.getHigh(index);
        for (int i = index - 10; i < index; i++) {
            if (i >= 0 && series.getHigh(i) > highest) {
                highest = series.getHigh(i);
            }
        }
        return highest;
    }

    private double findEqualLows(DataSeries series, int index, int lookback, double tolerance) {
        int start = Math.max(0, index - lookback);
        double[] lows = new double[lookback];
        int count = 0;

        for (int i = start; i < index && count < lookback; i++) {
            lows[count++] = series.getLow(i);
        }

        // Find clusters of equal lows
        double bestClusterLow = dealingLow;
        int bestClusterSize = 0;

        for (int i = 0; i < count; i++) {
            int clusterSize = 1;
            for (int j = i + 1; j < count; j++) {
                if (Math.abs(lows[i] - lows[j]) <= tolerance) {
                    clusterSize++;
                }
            }
            if (clusterSize > bestClusterSize) {
                bestClusterSize = clusterSize;
                bestClusterLow = lows[i];
            }
        }

        return bestClusterSize >= 2 ? bestClusterLow : dealingLow;
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
