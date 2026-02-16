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
 * LB Short Strategy v1.0 (Short Only)
 *
 * Architecture follows the proven Vector strategy pattern:
 *   - calculate() computes indicator (LB, EMA) and bar coloring ONLY
 *   - onBarUpdate() handles ALL trade entry and management via direct OrderContext
 *   - No signals — direct ctx.sell(), ctx.buy(), ctx.closeAtMarket()
 *
 * LB = highest(lowest(low, length), length) — regressive S/R line.
 *
 * Entry: Short when price crosses from green to red (prev close >= prev LB, current close < LB).
 * EMA filter: only short when close < EMA (bearish bias).
 * Exit: Bar-1 green exit, fixed stop above entry bar high, TP1 partial, trailing stop, EOD flatten.
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "LB_SHORT",
    rb = "com.mw.studies.nls.strings",
    name = "LB_SHORT",
    label = "LBL_LB_SHORT",
    desc = "DESC_LB_SHORT",
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
public class LBShortStrategy extends Study
{
    // ==================== Settings Keys ====================
    private static final String LENGTH = "length";

    private static final String EMA_FILTER_ENABLED = "emaFilterEnabled";
    private static final String EMA_PERIOD = "emaPeriod";
    private static final String SHOW_EMA = "showEma";
    private static final String EMA_LINE = "emaLine";

    private static final String LB_LINE = "lbLine";
    private static final String SHOW_BAR_COLORING = "showBarColoring";
    private static final String UP_COLOR = "upColor";
    private static final String DOWN_COLOR = "downColor";

    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";
    private static final String MAX_TRADES_PER_DAY = "maxTradesPerDay";

    private static final String STOP_BUFFER_TICKS = "stopBufferTicks";
    private static final String CONTRACTS = "contracts";

    private static final String TP1_PTS = "tp1Pts";
    private static final String PARTIAL_PCT = "partialPct";
    private static final String TRAIL_PTS = "trailPts";

    private static final String EOD_FLAT_ENABLED = "eodFlatEnabled";
    private static final String EOD_TIME = "eodTime";

    enum Values { LB, LOWER_BAND, EMA }

    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Trade State (Vector pattern) ====================
    private boolean inTrade = false;
    private double entryPrice = 0.0;
    private double stopPrice = 0.0;
    private double tp1Price = 0.0;
    private double entryBarHigh = 0.0;
    private int barsSinceEntry = 0;
    private int initialQty = 0;
    private boolean partialTaken = false;
    private boolean trailActive = false;
    private double trailStop = 0.0;
    private int tradesToday = 0;
    private int lastResetDay = -1;
    private double dailyRealizedPnl = 0.0;

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        var tabLB = sd.addTab("LB Short");
        var grpLB = tabLB.addGroup("LB Calculation");
        grpLB.addRow(new IntegerDescriptor(LENGTH, "Lookback Length (bars)", 20, 5, 200, 1));

        var grpFilter = tabLB.addGroup("EMA Filter");
        grpFilter.addRow(new BooleanDescriptor(EMA_FILTER_ENABLED, "EMA Filter (Short only below EMA)", true));
        grpFilter.addRow(new IntegerDescriptor(EMA_PERIOD, "EMA Period", 50, 5, 200, 1));
        grpFilter.addRow(new BooleanDescriptor(SHOW_EMA, "Show EMA Line", true));
        grpFilter.addRow(new PathDescriptor(EMA_LINE, "EMA Line",
            defaults.getBlueLine(), 1.5f, null, true, false, false));

        var grpDisplay = tabLB.addGroup("Display");
        grpDisplay.addRow(new PathDescriptor(LB_LINE, "LB Line",
            defaults.getYellowLine(), 2.0f, null, true, false, false));
        grpDisplay.addRow(new BooleanDescriptor(SHOW_BAR_COLORING, "Bar Coloring", true));
        grpDisplay.addRow(new ColorDescriptor(UP_COLOR, "Up Bar Color", defaults.getGreen()));
        grpDisplay.addRow(new ColorDescriptor(DOWN_COLOR, "Down Bar Color", defaults.getRed()));
        grpDisplay.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        var tabSess = sd.addTab("Sessions");
        var grpSess = tabSess.addGroup("Trade Window");
        grpSess.addRow(new IntegerDescriptor(TRADE_START, "Trade Start (HHMM)", 930, 0, 2359, 1));
        grpSess.addRow(new IntegerDescriptor(TRADE_END, "Trade End (HHMM)", 1600, 0, 2359, 1));
        var grpLimits = tabSess.addGroup("Limits");
        grpLimits.addRow(new IntegerDescriptor(MAX_TRADES_PER_DAY, "Max Trades Per Day", 1, 1, 20, 1));

        var tabRisk = sd.addTab("Risk");
        var grpStop = tabRisk.addGroup("Stop Loss");
        grpStop.addRow(new IntegerDescriptor(STOP_BUFFER_TICKS, "Stop Buffer Above Entry Bar High (ticks)", 20, 1, 200, 1));
        grpStop.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 10, 1, 100, 1));

        var tabExits = sd.addTab("Exits");
        var grpTP = tabExits.addGroup("Targets");
        grpTP.addRow(new DoubleDescriptor(TP1_PTS, "TP1 (points)", 10.0, 0.25, 100.0, 0.25));
        grpTP.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial % at TP1", 25, 1, 99, 1));
        var grpTrail = tabExits.addGroup("Trail");
        grpTrail.addRow(new DoubleDescriptor(TRAIL_PTS, "Trail Distance (points)", 10.0, 0.25, 100.0, 0.25));

        var tabEOD = sd.addTab("EOD");
        var grpEOD = tabEOD.addGroup("End of Day");
        grpEOD.addRow(new BooleanDescriptor(EOD_FLAT_ENABLED, "Force Flat EOD", true));
        grpEOD.addRow(new IntegerDescriptor(EOD_TIME, "EOD Flatten Time (HHMM)", 1640, 0, 2359, 1));

        sd.addQuickSettings(CONTRACTS, TP1_PTS, TRAIL_PTS, EMA_PERIOD, STOP_BUFFER_TICKS);

        var desc = createRD();
        desc.exportValue(new ValueDescriptor(Values.LB, "LB Line", new String[] { LB_LINE }));
        desc.declarePath(Values.LB, LB_LINE);
        desc.exportValue(new ValueDescriptor(Values.EMA, "EMA", new String[] { EMA_LINE }));
        desc.declarePath(Values.EMA, EMA_LINE);
    }

    // ==================== LIFECYCLE ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== LB Short Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== LB Short Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        tradesToday = 0;
        lastResetDay = -1;
        dailyRealizedPnl = 0.0;
        resetTradeState();
    }

    private void resetTradeState()
    {
        inTrade = false;
        entryPrice = 0.0;
        stopPrice = 0.0;
        tp1Price = 0.0;
        entryBarHigh = 0.0;
        barsSinceEntry = 0;
        initialQty = 0;
        partialTaken = false;
        trailActive = false;
        trailStop = 0.0;
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

        // ==================== EMA Calculation ====================
        int emaPeriod = settings.getInteger(EMA_PERIOD, 50);
        double closePrice = series.getClose(index);
        if (index < emaPeriod) {
            series.setDouble(index, Values.EMA, closePrice);
        } else {
            Double prevEma = series.getDouble(index - 1, Values.EMA);
            if (prevEma == null || Double.isNaN(prevEma)) {
                // Seed EMA with SMA
                double sum = 0;
                for (int i = index - emaPeriod + 1; i <= index; i++) {
                    sum += series.getClose(i);
                }
                series.setDouble(index, Values.EMA, sum / emaPeriod);
            } else {
                double k = 2.0 / (emaPeriod + 1);
                double ema = closePrice * k + prevEma * (1 - k);
                series.setDouble(index, Values.EMA, ema);
            }
        }

        // Bar coloring: green if close >= LB, red if close < LB
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

        // Previous bar LB (needed for crossed-from-above check)
        Double prevLbObj = (index > 0) ? series.getDouble(index - 1, Values.LB) : null;
        if (prevLbObj == null || Double.isNaN(prevLbObj)) return;
        double prevLb = prevLbObj;

        // Current bar data
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
            dailyRealizedPnl = 0.0;
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
            double exitPnl = (entryPrice - exitPrice) * Math.abs(position);
            dailyRealizedPnl += exitPnl;
            ctx.closeAtMarket();
            info("FILL: CLOSE " + position + " @ " + fmt(exitPrice) + " | Exit P&L: " + fmt(exitPnl) + " pts | Day P&L: " + fmt(dailyRealizedPnl) + " pts");
            resetTradeState();
            return;
        }

        // ============================================================
        // TRADE MANAGEMENT — handle existing short position
        // ============================================================
        if (position < 0 && inTrade) {
            manageShortTrade(ctx, series, index, lb);
            return;
        }

        // If position is 0 but we think we're in a trade, reset state
        if (position == 0 && inTrade) {
            resetTradeState();
        }

        // ============================================================
        // ENTRY LOGIC — look for short setups (crossed green→red)
        // ============================================================
        if (position == 0) {
            int tradeStart = settings.getInteger(TRADE_START, 930);
            int tradeEnd = settings.getInteger(TRADE_END, 1600);
            int maxTrades = settings.getInteger(MAX_TRADES_PER_DAY, 1);

            boolean inWindow = (timeInt >= tradeStart && timeInt < tradeEnd);
            if (!inWindow || tradesToday >= maxTrades) return;

            // EMA filter: only short when close is below EMA (bearish bias)
            boolean emaFilterEnabled = settings.getBoolean(EMA_FILTER_ENABLED, true);
            if (emaFilterEnabled) {
                Double emaObj = series.getDouble(index, Values.EMA);
                if (emaObj != null && !Double.isNaN(emaObj)) {
                    if (close >= emaObj) return;
                }
            }

            // Crossed-from-above: previous bar was GREEN (close >= LB), current bar is RED (close < LB)
            if (index < 1) return;
            double prevClose = series.getClose(index - 1);
            boolean prevWasGreen = prevClose >= prevLb;
            boolean currentIsRed = close < lb;

            if (prevWasGreen && currentIsRed) {
                Instrument instr = ctx.getInstrument();
                double tickSize = instr.getTickSize();
                int contracts = settings.getInteger(CONTRACTS, 10);
                int stopBufferTicks = settings.getInteger(STOP_BUFFER_TICKS, 20);
                double stopBuffer = stopBufferTicks * tickSize;
                double tp1Pts = settings.getDouble(TP1_PTS, 10.0);

                double calcStop = instr.round(high + stopBuffer);
                double calcTp1 = instr.round(close - tp1Pts);

                info("=== SHORT ENTRY SIGNAL ===");
                info("Entry: " + fmt(close) + " | LB: " + fmt(lb));
                info("Stop: " + fmt(calcStop) + " (" + stopBufferTicks + " ticks above bar high " + fmt(high) + ")");
                info("TP1: " + fmt(calcTp1) + " | Contracts: " + contracts);

                // Draw entry marker
                var marker = settings.getMarker(Inputs.DOWN_MARKER);
                if (marker != null && marker.isEnabled()) {
                    addFigure(new Marker(
                        new Coordinate(barTime, high),
                        Enums.Position.TOP, marker,
                        "Short @ " + fmt(close)));
                }

                ctx.sell(contracts);
                double fillPrice = ctx.getAvgEntryPrice();
                info("FILL: SELL " + contracts + " @ " + fmt(fillPrice));

                inTrade = true;
                entryPrice = fillPrice;
                stopPrice = calcStop;
                tp1Price = calcTp1;
                entryBarHigh = high;
                barsSinceEntry = 0;
                initialQty = contracts;
                partialTaken = false;
                trailActive = false;
                trailStop = 0.0;
                tradesToday++;
            }
        }
    }

    // ==================== TRADE MANAGEMENT (Short) ====================
    private void manageShortTrade(OrderContext ctx, DataSeries series, int index, double lb)
    {
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        int position = ctx.getPosition();

        Settings settings = getSettings();
        Instrument instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();

        barsSinceEntry++;

        // ============================================================
        // 1. BAR-1 GREEN CHECK: breakdown failed → exit immediately
        // ============================================================
        if (barsSinceEntry == 1) {
            if (close >= lb) {
                info("=== BAR-1 GREEN EXIT (breakdown failed) ===");
                info("Close " + fmt(close) + " >= LB " + fmt(lb));
                double exitPnl = (entryPrice - close) * Math.abs(position);
                dailyRealizedPnl += exitPnl;
                ctx.closeAtMarket();
                info("FILL: CLOSE " + position + " @ " + fmt(close) + " | Exit P&L: " + fmt(exitPnl) + " pts | Day P&L: " + fmt(dailyRealizedPnl) + " pts");
                resetTradeState();
                return;
            } else {
                // Bar-1 RED confirmed: lock stop at entry bar high + buffer
                int stopBufferTicks = settings.getInteger(STOP_BUFFER_TICKS, 20);
                stopPrice = instr.round(entryBarHigh + stopBufferTicks * tickSize);
                info("Bar-1 RED confirmed: stop locked at " + fmt(stopPrice));
            }
        }

        // ============================================================
        // 2. STOP CHECK: high >= stopPrice → stopped out
        // ============================================================
        if (stopPrice > 0 && high >= stopPrice) {
            info("=== STOP HIT ===");
            info("Stop: " + fmt(stopPrice) + " | High: " + fmt(high));
            double exitPnl = (entryPrice - stopPrice) * Math.abs(position);
            dailyRealizedPnl += exitPnl;
            ctx.closeAtMarket();
            info("FILL: CLOSE " + position + " @ " + fmt(stopPrice) + " | Exit P&L: " + fmt(exitPnl) + " pts | Day P&L: " + fmt(dailyRealizedPnl) + " pts");
            resetTradeState();
            return;
        }

        // ============================================================
        // 3. TP1 PARTIAL: low <= tp1Price → take partial, activate trail
        // ============================================================
        if (!partialTaken && tp1Price > 0 && low <= tp1Price) {
            int partialPct = settings.getInteger(PARTIAL_PCT, 25);
            int partialQty = Math.max(1, initialQty * partialPct / 100);
            int absPosition = Math.abs(position);
            if (partialQty > 0 && partialQty < absPosition) {
                info("=== TP1 PARTIAL ===");
                info("TP1: " + fmt(tp1Price) + " | Covering " + partialQty + " of " + absPosition + " contracts");
                ctx.buy(partialQty);
                double partialPnl = (entryPrice - tp1Price) * partialQty;
                dailyRealizedPnl += partialPnl;
                info("FILL: BUY " + partialQty + " @ " + fmt(tp1Price) + " | Partial P&L: " + fmt(partialPnl) + " pts | Day P&L: " + fmt(dailyRealizedPnl) + " pts");
            }
            partialTaken = true;
            trailActive = true;
            double trailPts = settings.getDouble(TRAIL_PTS, 10.0);
            trailStop = close + trailPts;
            info("Trail activated: trailStop=" + fmt(trailStop));
        }

        // ============================================================
        // 4. TRAIL: ratchet down, check for exit
        // ============================================================
        if (trailActive) {
            double trailPts = settings.getDouble(TRAIL_PTS, 10.0);
            double candidate = close + trailPts;
            if (candidate < trailStop) {
                trailStop = candidate;  // ratchet DOWN only
            }
            if (high >= trailStop) {
                info("=== TRAIL STOP HIT ===");
                info("TrailStop: " + fmt(trailStop) + " | High: " + fmt(high));
                int remainingQty = Math.abs(ctx.getPosition());
                double exitPnl = (entryPrice - trailStop) * remainingQty;
                dailyRealizedPnl += exitPnl;
                ctx.closeAtMarket();
                info("FILL: CLOSE " + remainingQty + " @ " + fmt(trailStop) + " | Exit P&L: " + fmt(exitPnl) + " pts | Day P&L: " + fmt(dailyRealizedPnl) + " pts");
                resetTradeState();
                return;
            }
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
