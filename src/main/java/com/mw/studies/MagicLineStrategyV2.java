package com.mw.studies;

import java.awt.Color;
import java.util.Calendar;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.Marker;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * Magic Line Strategy v4.0 (Long Only)
 *
 * Architecture follows the proven Vector strategy pattern:
 *   - calculate() computes indicator (LB) and bar coloring ONLY
 *   - onBarUpdate() handles ALL trade entry and management via direct OrderContext
 *   - No signals — direct ctx.buy(), ctx.sell(), ctx.closeAtMarket()
 *
 * LB = highest(lowest(low, length), length) — regressive S/R line.
 *
 * Entry: Vector-style multi-condition bounce off LB support.
 * Exit: BE trigger, partial at TP1, trail (close below LB), TP2, EOD flatten.
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "MAGIC_LINE_V2_R2",
    rb = "com.mw.studies.nls.strings",
    name = "MAGIC_LINE_V2_LATE_BE",
    label = "LBL_MAGIC_LINE_V2",
    desc = "DESC_MAGIC_LINE",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    strategy = true,
    autoEntry = true,
    manualEntry = false,
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true
)
public class MagicLineStrategyV2 extends Study
{
    // ==================== Settings Keys ====================
    private static final String LENGTH = "length";
    private static final String TOUCH_TOLERANCE_TICKS = "touchToleranceTicks";
    private static final String ZONE_BUFFER_PTS = "zoneBufferPts";
    private static final String CAME_FROM_PTS = "cameFromPts";
    private static final String CAME_FROM_LOOKBACK = "cameFromLookback";

    private static final String TRADE_SESSION_ENABLED = "tradeSessionEnabled";
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";
    private static final String MAX_TRADES_PER_DAY = "maxTradesPerDay";
    private static final String ONE_TRADE_AT_A_TIME = "oneTradeAtATime";

    private static final String STOPLOSS_ENABLED = "stoplossEnabled";
    private static final String STOPLOSS_MODE = "stoplossMode";
    private static final String STOP_BUFFER_TICKS = "stopBufferTicks";
    private static final String CONTRACTS = "contracts";
    private static final String BE_ENABLED = "beEnabled";
    private static final String BE_TRIGGER_PTS = "beTriggerPts";

    private static final String TP1_R = "tp1R";
    private static final String TP2_R = "tp2R";
    private static final String PARTIAL_ENABLED = "partialEnabled";
    private static final String PARTIAL_PCT = "partialPct";
    private static final String TIME_EXIT_ENABLED = "timeExitEnabled";
    private static final String TIME_EXIT_TIME = "timeExitTime";

    private static final String EOD_FLAT_ENABLED = "eodFlatEnabled";
    private static final String EOD_TIME = "eodTime";

    private static final String LB_LINE = "lbLine";
    private static final String SHOW_BAR_COLORING = "showBarColoring";
    private static final String UP_COLOR = "upColor";
    private static final String DOWN_COLOR = "downColor";

    // ==================== Constants ====================
    private static final int STOP_FIXED = 0;
    private static final int STOP_STRUCTURAL = 1;

    enum Values { LB, LOWER_BAND }

    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Trade State (Vector pattern) ====================
    private boolean inTrade = false;
    private double entryPrice = 0.0;
    private double initialStopPrice = 0.0;
    private int initialQty = 0;
    private boolean partialTaken = false;
    private boolean stopAtBreakeven = false;
    private boolean trailActive = false;
    private double tp1Price = 0.0;
    private double tp2Price = 0.0;
    private int tradesToday = 0;
    private int lastResetDay = -1;

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        var tabLB = sd.addTab("Magic Line");
        var grpLB = tabLB.addGroup("LB Calculation");
        grpLB.addRow(new IntegerDescriptor(LENGTH, "Lookback Length (bars)", 20, 5, 200, 1));

        var grpEntry = tabLB.addGroup("Entry Conditions");
        grpEntry.addRow(new IntegerDescriptor(TOUCH_TOLERANCE_TICKS, "Touch Tolerance Below LB (ticks)", 4, 1, 20, 1));
        grpEntry.addRow(new DoubleDescriptor(ZONE_BUFFER_PTS, "Entry Zone Buffer Above LB (points)", 2.0, 0.25, 20.0, 0.25));
        grpEntry.addRow(new DoubleDescriptor(CAME_FROM_PTS, "Came-From Distance (points above LB)", 5.0, 0.5, 50.0, 0.5));
        grpEntry.addRow(new IntegerDescriptor(CAME_FROM_LOOKBACK, "Came-From Lookback (bars)", 5, 2, 20, 1));

        var grpDisplay = tabLB.addGroup("Display");
        grpDisplay.addRow(new PathDescriptor(LB_LINE, "LB Line",
            defaults.getYellowLine(), 2.0f, null, true, false, false));
        grpDisplay.addRow(new BooleanDescriptor(SHOW_BAR_COLORING, "Bar Coloring", true));
        grpDisplay.addRow(new ColorDescriptor(UP_COLOR, "Up Bar Color", defaults.getGreen()));
        grpDisplay.addRow(new ColorDescriptor(DOWN_COLOR, "Down Bar Color", defaults.getRed()));

        var tabSess = sd.addTab("Sessions");
        var grpSess = tabSess.addGroup("Trade Window");
        grpSess.addRow(new BooleanDescriptor(TRADE_SESSION_ENABLED, "Restrict to Trade Window", false));
        grpSess.addRow(new IntegerDescriptor(TRADE_START, "Trade Start (HHMM)", 930, 0, 2359, 1));
        grpSess.addRow(new IntegerDescriptor(TRADE_END, "Trade End (HHMM)", 1600, 0, 2359, 1));
        var grpLimits = tabSess.addGroup("Limits");
        grpLimits.addRow(new IntegerDescriptor(MAX_TRADES_PER_DAY, "Max Trades Per Day", 6, 1, 20, 1));
        grpLimits.addRow(new BooleanDescriptor(ONE_TRADE_AT_A_TIME, "One Trade At A Time", true));

        var tabRisk = sd.addTab("Risk");
        var grpStop = tabRisk.addGroup("Stop Loss");
        grpStop.addRow(new BooleanDescriptor(STOPLOSS_ENABLED, "Enable Stop Loss", true));
        grpStop.addRow(new IntegerDescriptor(STOPLOSS_MODE, "Stop Mode (0=Fixed, 1=Structural+Buffer)", 1, 0, 1, 1));
        grpStop.addRow(new IntegerDescriptor(STOP_BUFFER_TICKS, "Stop Buffer/Distance (ticks)", 20, 1, 200, 1));
        grpStop.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 12, 1, 100, 1));  // V2: 12 contracts for unique identification
        var grpBE = tabRisk.addGroup("Breakeven");
        grpBE.addRow(new BooleanDescriptor(BE_ENABLED, "Enable Breakeven Trigger", true));
        grpBE.addRow(new DoubleDescriptor(BE_TRIGGER_PTS, "Breakeven Trigger (points profit)", 4.0, 0.5, 50.0, 0.5));

        var tabExits = sd.addTab("Exits");
        var grpExit = tabExits.addGroup("Targets");
        grpExit.addRow(new DoubleDescriptor(TP1_R, "TP1 (R multiple)", 1.0, 0.25, 10.0, 0.25));
        grpExit.addRow(new DoubleDescriptor(TP2_R, "TP2 (R multiple)", 2.0, 0.5, 20.0, 0.25));
        grpExit.addRow(new BooleanDescriptor(PARTIAL_ENABLED, "Take Partial at TP1", true));
        grpExit.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial % at TP1", 50, 1, 99, 1));
        var grpTime = tabExits.addGroup("Time Exit");
        grpTime.addRow(new BooleanDescriptor(TIME_EXIT_ENABLED, "Enable Time-Based Exit", false));
        grpTime.addRow(new IntegerDescriptor(TIME_EXIT_TIME, "Time Exit (HHMM)", 1215, 0, 2359, 1));

        var tabEOD = sd.addTab("EOD");
        var grpEOD = tabEOD.addGroup("End of Day");
        grpEOD.addRow(new BooleanDescriptor(EOD_FLAT_ENABLED, "Force Flat EOD", true));
        grpEOD.addRow(new IntegerDescriptor(EOD_TIME, "EOD Flatten Time (HHMM)", 1640, 0, 2359, 1));

        sd.addQuickSettings(CONTRACTS, TP1_R, TP2_R, TOUCH_TOLERANCE_TICKS);

        var desc = createRD();
        desc.exportValue(new ValueDescriptor(Values.LB, "Magic Line (LB)", new String[] { LB_LINE }));
        desc.declarePath(Values.LB, LB_LINE);
    }

    // ==================== LIFECYCLE ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== Magic Line Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== Magic Line Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        tradesToday = 0;
        lastResetDay = -1;
        resetTradeState();
    }

    private void resetTradeState()
    {
        inTrade = false;
        entryPrice = 0.0;
        initialStopPrice = 0.0;
        initialQty = 0;
        partialTaken = false;
        stopAtBreakeven = false;
        trailActive = false;
        tp1Price = 0.0;
        tp2Price = 0.0;
    }

    // ==================== CALCULATE (Indicator Only) ====================
    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var settings = getSettings();
        int length = settings.getInteger(LENGTH, 20);

        int size = series.size();
        if (index >= size || index < length) return;

        // LowerBand: lowest low over 'length' bars
        double lowerBand = Double.MAX_VALUE;
        for (int i = index - length + 1; i <= index; i++) {
            double lo = series.getLow(i);
            if (lo < lowerBand) lowerBand = lo;
        }
        series.setDouble(index, Values.LOWER_BAND, lowerBand);

        // LB: highest(lowerBand, length)
        if (index < (2 * length - 1)) return;
        double lb = Double.MIN_VALUE;
        for (int i = index - length + 1; i <= index; i++) {
            Double lbVal = series.getDouble(i, Values.LOWER_BAND);
            if (lbVal != null && !Double.isNaN(lbVal) && lbVal > lb) lb = lbVal;
        }
        if (lb == Double.MIN_VALUE) return;
        series.setDouble(index, Values.LB, lb);

        // Bar coloring (same approach as Vector strategy)
        double close = series.getClose(index);
        if (!Double.isNaN(close)) {
            if (settings.getBoolean(SHOW_BAR_COLORING, true)) {
                Color upColor = settings.getColor(UP_COLOR);
                Color downColor = settings.getColor(DOWN_COLOR);
                series.setPriceBarColor(index, (close >= lb) ? upColor : downColor);
            }
        }

        series.setComplete(index);
    }

    // ==================== ALL TRADE LOGIC (Vector pattern) ====================
    @Override
    public void onBarUpdate(OrderContext ctx)
    {
        DataSeries series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;

        Settings settings = getSettings();
        int length = settings.getInteger(LENGTH, 20);
        if (index < (2 * length - 1)) return;

        // Get the LB value computed by calculate()
        Double lbObj = series.getDouble(index, Values.LB);
        if (lbObj == null || Double.isNaN(lbObj)) return;
        double lb = lbObj;

        // Current bar data
        double open = series.getOpen(index);
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);

        int position = ctx.getPosition();

        // Time checks
        long barTime = series.getStartTime(index);
        int timeInt = getTimeInt(barTime, NY_TZ);

        // Daily reset
        int barDay = getDayOfYear(barTime, NY_TZ);
        if (barDay != lastResetDay) {
            tradesToday = 0;
            lastResetDay = barDay;
        }

        // ============================================================
        // EOD FLATTEN
        // ============================================================
        boolean eodEnabled = settings.getBoolean(EOD_FLAT_ENABLED, true);
        int eodTime = settings.getInteger(EOD_TIME, 1640);
        if (eodEnabled && position != 0 && timeInt >= eodTime) {
            info("=== EOD FLATTEN ===");
            double exitPrice = series.getClose(index);
            double exitPnl = (exitPrice - entryPrice) * position;
            ctx.closeAtMarket();
            info("FILL: CLOSE " + position + " @ " + fmt(exitPrice) + " | Exit P&L: " + fmt(exitPnl) + " pts");
            resetTradeState();
            return;
        }

        // ============================================================
        // TIME EXIT
        // ============================================================
        if (settings.getBoolean(TIME_EXIT_ENABLED, false) && position != 0
                && timeInt >= settings.getInteger(TIME_EXIT_TIME, 1215)) {
            info("=== TIME EXIT ===");
            double exitPrice = series.getClose(index);
            double exitPnl = (exitPrice - entryPrice) * position;
            ctx.closeAtMarket();
            info("FILL: CLOSE " + position + " @ " + fmt(exitPrice) + " | Exit P&L: " + fmt(exitPnl) + " pts");
            resetTradeState();
            return;
        }

        // ============================================================
        // TRADE MANAGEMENT — handle existing position first
        // ============================================================
        if (position > 0 && inTrade) {
            manageExistingTrade(ctx, series, index, lb);
            return;
        }

        // If position is 0 but we think we're in a trade, reset state
        if (position == 0 && inTrade) {
            resetTradeState();
        }

        // ============================================================
        // ENTRY LOGIC — look for long setups at LB support
        // ============================================================
        if (position == 0) {
            // Session window check
            boolean sessionEnabled = settings.getBoolean(TRADE_SESSION_ENABLED, false);
            int tradeStart = settings.getInteger(TRADE_START, 930);
            int tradeEnd = settings.getInteger(TRADE_END, 1600);
            int maxTrades = settings.getInteger(MAX_TRADES_PER_DAY, 6);

            boolean inWindow = !sessionEnabled || (timeInt >= tradeStart && timeInt < tradeEnd);
            if (!inWindow || tradesToday >= maxTrades) return;

            // Bullish bias required (close >= LB)
            if (close < lb) return;

            Instrument instr = ctx.getInstrument();
            double tickSize = instr.getTickSize();
            int touchTolTicks = settings.getInteger(TOUCH_TOLERANCE_TICKS, 4);
            double touchTol = touchTolTicks * tickSize;
            double zoneBuffer = settings.getDouble(ZONE_BUFFER_PTS, 2.0);
            double cameFromPts = settings.getDouble(CAME_FROM_PTS, 5.0);
            int cameFromLookback = settings.getInteger(CAME_FROM_LOOKBACK, 5);

            boolean entrySignal = checkLongEntry(series, index, lb, touchTol, zoneBuffer,
                                                  cameFromPts, cameFromLookback);

            if (entrySignal) {
                int contracts = settings.getInteger(CONTRACTS, 1);
                boolean stopEnabled = settings.getBoolean(STOPLOSS_ENABLED, true);
                int stopMode = settings.getInteger(STOPLOSS_MODE, 1);
                int stopBufferTicks = settings.getInteger(STOP_BUFFER_TICKS, 20);
                double stopBuffer = stopBufferTicks * tickSize;

                // Calculate stop
                double calcStop = 0.0;
                if (stopEnabled) {
                    calcStop = (stopMode == STOP_FIXED) ? close - stopBuffer : low - stopBuffer;
                    calcStop = instr.round(calcStop);
                }

                double riskDist = Math.abs(close - calcStop);
                if (riskDist <= 0) riskDist = stopBuffer;

                double calcTp1 = instr.round(close + settings.getDouble(TP1_R, 1.0) * riskDist);
                double calcTp2 = instr.round(close + settings.getDouble(TP2_R, 2.0) * riskDist);

                info("=== LONG ENTRY SIGNAL ===");
                info("Entry: " + fmt(close) + " | LB: " + fmt(lb));
                info("Stop: " + fmt(calcStop) + " (" + stopBufferTicks + " ticks buffer)");
                info("TP1: " + fmt(calcTp1) + " | TP2: " + fmt(calcTp2));
                info("Contracts: " + contracts);

                // Draw entry marker
                var marker = settings.getMarker(Inputs.UP_MARKER);
                if (marker != null && marker.isEnabled()) {
                    addFigure(new Marker(
                        new Coordinate(barTime, low),
                        Enums.Position.BOTTOM, marker,
                        "Long @ " + fmt(close)));
                }

                ctx.buy(contracts);
                double fillPrice = ctx.getAvgEntryPrice();
                info("FILL: BUY " + contracts + " @ " + fmt(fillPrice));

                inTrade = true;
                entryPrice = fillPrice;  // Use actual fill price
                initialStopPrice = calcStop;
                initialQty = contracts;
                tp1Price = calcTp1;
                tp2Price = calcTp2;
                partialTaken = false;
                stopAtBreakeven = false;
                trailActive = false;
                tradesToday++;
            }
        }
    }

    // ==================== ENTRY CHECK ====================
    private boolean checkLongEntry(DataSeries series, int index, double lb,
                                    double touchTol, double zoneBuffer,
                                    double cameFromPts, int cameFromLookback)
    {
        double close = series.getClose(index);
        double open = series.getOpen(index);
        double low = series.getLow(index);

        // Condition 1: Low is within entry zone (lb - touchTol to lb + zoneBuffer)
        if (!(low <= lb + zoneBuffer && low >= lb - touchTol)) return false;

        // Condition 2: Bullish bar (close > open)
        if (!(close > open)) return false;

        // Condition 3: Close above LB (support held)
        if (!(close > lb)) return false;

        // Condition 4: Higher low forming
        boolean higherLowForming = false;
        if (index >= 2) {
            double prevLow = series.getLow(index - 1);
            double prevPrevLow = series.getLow(index - 2);
            higherLowForming = low > prevLow || prevLow > prevPrevLow;
        }

        // Condition 5: Price came from above to test support
        boolean cameFromAbove = false;
        int start = Math.max(0, index - cameFromLookback);
        for (int i = start; i < index; i++) {
            if (series.getHigh(i) > lb + cameFromPts) {
                cameFromAbove = true;
                break;
            }
        }

        return higherLowForming || cameFromAbove;
    }

    // ==================== TRADE MANAGEMENT (Vector pattern) ====================
    private void manageExistingTrade(OrderContext ctx, DataSeries series, int index, double lb)
    {
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        int position = ctx.getPosition();

        Settings settings = getSettings();
        boolean enableBE = settings.getBoolean(BE_ENABLED, true);
        double beTriggerPts = settings.getDouble(BE_TRIGGER_PTS, 5.0);

        // ============================================================
        // 1. BREAKEVEN TRIGGER (before partial and stop check)
        // ============================================================
        if (enableBE && !stopAtBreakeven && !partialTaken) {
            if (high >= entryPrice + beTriggerPts) {
                stopAtBreakeven = true;
                info("=== STOP MOVED TO BREAKEVEN ===");
                info("Trigger hit at: " + fmt(entryPrice + beTriggerPts) + " | Stop now at: " + fmt(entryPrice));
            }
        }

        // ============================================================
        // 2. PARTIAL PROFIT at TP1 (same as Vector: ctx.sell(halfQty))
        // ============================================================
        if (!partialTaken && high >= tp1Price) {
            boolean partEnabled = settings.getBoolean(PARTIAL_ENABLED, true);
            if (partEnabled && initialQty > 1) {
                int partialPct = settings.getInteger(PARTIAL_PCT, 50);
                int halfQty = initialQty / 2;
                if (halfQty > 0 && halfQty < position) {
                    info("=== TAKING PARTIAL at TP1 ===");
                    info("TP1: " + fmt(tp1Price) + " | Closing " + halfQty + " of " + position + " contracts");
                    ctx.sell(halfQty);
                    double partialPnl = (tp1Price - entryPrice) * halfQty;
                    info("FILL: SELL " + halfQty + " @ " + fmt(tp1Price) + " | Partial P&L: " + fmt(partialPnl) + " pts");
                }
            }
            partialTaken = true;
            stopAtBreakeven = true;
            trailActive = true;
            info("Stop moved to BREAKEVEN: " + fmt(entryPrice) + " | Trail active");
        }

        // ============================================================
        // 3. STOP LOSS (calculate current stop level based on state)
        // ============================================================
        double currentStop;
        if (partialTaken || stopAtBreakeven) {
            // After partial or BE trigger: stop at breakeven (entry price)
            currentStop = entryPrice;
        } else {
            // Initial stop: structural or fixed
            currentStop = initialStopPrice;
        }

        if (currentStop > 0 && low <= currentStop) {
            String stopType = partialTaken ? "TRAILING STOP" : (stopAtBreakeven ? "BREAKEVEN STOP" : "INITIAL STOP");
            info("=== " + stopType + " HIT ===");
            info("Stop: " + fmt(currentStop) + " | Low: " + fmt(low));
            int remainingQty = position;
            double exitPnl = (currentStop - entryPrice) * remainingQty;
            ctx.closeAtMarket();
            info("FILL: CLOSE " + remainingQty + " @ " + fmt(currentStop) + " | Exit P&L: " + fmt(exitPnl) + " pts");
            resetTradeState();
            return;
        }

        // ============================================================
        // 4. TRAIL EXIT: close below LB (after TP1)
        // ============================================================
        if (trailActive && partialTaken) {
            if (close < lb) {
                info("=== TRAIL EXIT ===");
                info("Close " + fmt(close) + " < LB " + fmt(lb));
                int remainingQty = position;
                double exitPnl = (close - entryPrice) * remainingQty;
                ctx.closeAtMarket();
                info("FILL: CLOSE " + remainingQty + " @ " + fmt(close) + " | Exit P&L: " + fmt(exitPnl) + " pts");
                resetTradeState();
                return;
            }
        }

        // ============================================================
        // 5. TP2 full exit
        // ============================================================
        if (partialTaken && tp2Price > 0 && high >= tp2Price) {
            info("=== TP2 HIT ===");
            info("TP2: " + fmt(tp2Price));
            int remainingQty = position;
            double exitPnl = (tp2Price - entryPrice) * remainingQty;
            ctx.closeAtMarket();
            info("FILL: CLOSE " + remainingQty + " @ " + fmt(tp2Price) + " | Exit P&L: " + fmt(exitPnl) + " pts");
            resetTradeState();
            return;
        }

        // Check if position closed externally
        if (ctx.getPosition() == 0) {
            info("Position closed externally");
            resetTradeState();
        }
    }

    // ==================== SIGNAL HANDLER (required by framework) ====================
    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        // All trade logic is handled directly in onBarUpdate() — no signals used.
    }

    // ==================== UTILITY ====================
    private int getTimeInt(long time, TimeZone tz)
    {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);
    }

    private int getDayOfYear(long time, TimeZone tz)
    {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.DAY_OF_YEAR) + cal.get(Calendar.YEAR) * 1000;
    }

    private String fmt(double val) { return String.format("%.2f", val); }
}
