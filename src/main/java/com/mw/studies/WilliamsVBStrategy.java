package com.mw.studies;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.Marker;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * Williams Volatility Breakout Strategy v1.0
 *
 * Based on Larry Williams' World Cup Championship winning system.
 * Enter when price moves a percentage of yesterday's range away from today's open.
 * This captures volatility expansion that continues in the breakout direction.
 *
 * Entry = Open +/- (Yesterday_Range x Multiplier), range-based stop, R:R target.
 *
 * Reference: "Long-Term Secrets to Short-Term Trading" by Larry Williams.
 *
 * Architecture: Vector pattern
 *   - calculate() computes RTH OHLC, daily range, trigger levels
 *   - onBarUpdate() handles all trade entry and management
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "WILLIAMS_VB",
    rb = "com.mw.studies.nls.strings",
    name = "WILLIAMS_VB",
    label = "LBL_WILLIAMS_VB",
    desc = "DESC_WILLIAMS_VB",
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
public class WilliamsVBStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String ENTRY_MULT = "entryMult";
    private static final String STOP_MULT = "stopMult";
    private static final String TARGET_RR = "targetRR";
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ENTRY_END = "entryEnd";
    private static final String EOD_TIME = "eodTime";

    // ==================== Values ====================
    enum Values { PLACEHOLDER }

    // ==================== State ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // Daily OHLC archive (from RTH bars)
    private final List<Double> dailyHighs = new ArrayList<>();
    private final List<Double> dailyLows = new ArrayList<>();
    private static final int MAX_DAILY = 50;

    // Current day RTH tracking
    private double rthHigh = Double.NaN;
    private double rthLow = Double.NaN;
    private boolean rthStarted = false;

    // Today's triggers
    private double longTrigger = Double.NaN;
    private double shortTrigger = Double.NaN;
    private double yesterdayRange = 0.0;
    private double todayOpen = Double.NaN;
    private boolean triggersSet = false;

    // Trade state
    private double entryPrice = 0.0;
    private double stopPrice = 0.0;
    private double tpPrice = 0.0;
    private int tradeSide = 0; // 1=long, -1=short

    // Daily tracking
    private int tradesToday = 0;
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // ==================== Initialize ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        var tab = sd.addTab("General");
        var grp = tab.addGroup("Williams VB Parameters");
        grp.addRow(new DoubleDescriptor(ENTRY_MULT, "Entry Multiplier", 0.50, 0.05, 2.0, 0.05));
        grp.addRow(new DoubleDescriptor(STOP_MULT, "Stop Multiplier", 0.50, 0.05, 2.0, 0.05));
        grp.addRow(new DoubleDescriptor(TARGET_RR, "Target R:R", 3.0, 0.5, 10.0, 0.25));

        grp = tab.addGroup("Session");
        grp.addRow(new IntegerDescriptor(ENTRY_END, "Entry Cutoff (HHMM)", 1530, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades/Day", 1, 1, 10, 1));

        var tabRisk = sd.addTab("Risk");
        var grpRisk = tabRisk.addGroup("Position Size");
        grpRisk.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 2, 1, 100, 1));

        var tabEOD = sd.addTab("EOD");
        var grpEOD = tabEOD.addGroup("End of Day");
        grpEOD.addRow(new IntegerDescriptor(EOD_TIME, "EOD Flatten (HHMM)", 1640, 0, 2359, 1));

        var tabDisplay = sd.addTab("Display");
        var grpMarkers = tabDisplay.addGroup("Entry Markers");
        grpMarkers.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grpMarkers.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        sd.addQuickSettings(CONTRACTS, ENTRY_MULT, TARGET_RR, MAX_TRADES_DAY);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, ENTRY_MULT, TARGET_RR);
    }

    // ==================== Lifecycle ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== Williams VB Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== Williams VB Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        dailyHighs.clear();
        dailyLows.clear();
        rthHigh = Double.NaN;
        rthLow = Double.NaN;
        rthStarted = false;
        triggersSet = false;
        longTrigger = Double.NaN;
        shortTrigger = Double.NaN;
        todayOpen = Double.NaN;
        yesterdayRange = 0.0;
        tradesToday = 0;
        lastResetDay = -1;
        eodProcessed = false;
        resetTradeState();
    }

    private void resetTradeState()
    {
        entryPrice = 0.0;
        stopPrice = 0.0;
        tpPrice = 0.0;
        tradeSide = 0;
    }

    // ==================== Calculate (RTH OHLC tracking only) ====================
    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        if (index < 1) return;

        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);

        double high = series.getHigh(index);
        double low = series.getLow(index);

        // Track RTH OHLC (9:35–16:00)
        if (barTimeInt >= 935 && barTimeInt <= 1600) {
            if (!rthStarted) {
                rthHigh = high;
                rthLow = low;
                rthStarted = true;
            } else {
                if (high > rthHigh) rthHigh = high;
                if (low < rthLow) rthLow = low;
            }
        }

        // Daily reset: archive yesterday's data, set triggers
        if (barDay != lastResetDay) {
            // Archive previous day
            if (rthStarted && !Double.isNaN(rthHigh)) {
                dailyHighs.add(rthHigh);
                dailyLows.add(rthLow);
                if (dailyHighs.size() > MAX_DAILY) {
                    dailyHighs.remove(0);
                    dailyLows.remove(0);
                }
            }

            // Reset RTH
            rthHigh = Double.NaN;
            rthLow = Double.NaN;
            rthStarted = false;

            // Reset daily
            tradesToday = 0;
            eodProcessed = false;
            triggersSet = false;
            longTrigger = Double.NaN;
            shortTrigger = Double.NaN;
            todayOpen = Double.NaN;
            lastResetDay = barDay;
        }

        // Set triggers on first RTH bar (9:35)
        if (barTimeInt == 935 && !triggersSet && !dailyHighs.isEmpty()) {
            double yestHigh = dailyHighs.get(dailyHighs.size() - 1);
            double yestLow = dailyLows.get(dailyLows.size() - 1);
            yesterdayRange = yestHigh - yestLow;

            if (yesterdayRange > 0) {
                double entryMult = getSettings().getDouble(ENTRY_MULT, 0.50);
                todayOpen = series.getOpen(index);
                longTrigger = todayOpen + yesterdayRange * entryMult;
                shortTrigger = todayOpen - yesterdayRange * entryMult;
                triggersSet = true;
            }
        }

        series.setComplete(index);
    }

    // ==================== Trade Logic (Vector pattern) ====================
    @Override
    public void onBarUpdate(OrderContext ctx)
    {
        DataSeries series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        if (index < 1) return;

        Settings settings = getSettings();
        Instrument instr = ctx.getInstrument();

        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);

        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);

        int position = ctx.getPosition();

        // ===== EOD Flatten =====
        int eodTime = settings.getInteger(EOD_TIME, 1640);
        if (barTimeInt >= eodTime && !eodProcessed) {
            if (position != 0) {
                ctx.closeAtMarket();
                info("EOD flatten at " + barTimeInt);
                resetTradeState();
            }
            eodProcessed = true;
            return;
        }

        // ===== Trade Management =====
        if (position != 0 && tradeSide != 0) {
            if (tradeSide == 1) { // long
                if (low <= stopPrice) {
                    ctx.closeAtMarket();
                    info("STOP hit at " + fmt(stopPrice));
                    resetTradeState();
                    return;
                }
                if (high >= tpPrice) {
                    ctx.closeAtMarket();
                    info("TP hit at " + fmt(tpPrice));
                    resetTradeState();
                    return;
                }
            } else { // short
                if (high >= stopPrice) {
                    ctx.closeAtMarket();
                    info("STOP hit at " + fmt(stopPrice));
                    resetTradeState();
                    return;
                }
                if (low <= tpPrice) {
                    ctx.closeAtMarket();
                    info("TP hit at " + fmt(tpPrice));
                    resetTradeState();
                    return;
                }
            }
            return;
        }

        // Reset stale trade state
        if (position == 0 && tradeSide != 0) {
            resetTradeState();
        }

        // ===== Entry Logic =====
        if (!triggersSet) return;
        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 1);
        if (tradesToday >= maxTrades) return;
        int entryEnd = settings.getInteger(ENTRY_END, 1530);
        if (barTimeInt < 935 || barTimeInt > entryEnd) return;

        double stopMult = settings.getDouble(STOP_MULT, 0.50);
        double targetRR = settings.getDouble(TARGET_RR, 3.0);
        int contracts = settings.getInteger(CONTRACTS, 2);

        // Long breakout: high exceeds long trigger
        if (!Double.isNaN(longTrigger) && high > longTrigger) {
            double stopDist = yesterdayRange * stopMult;
            double stop = instr.round(close - stopDist);
            double risk = Math.abs(close - stop);
            if (risk > 0) {
                double tp = instr.round(close + targetRR * risk);
                ctx.buy(contracts);
                entryPrice = close;
                stopPrice = stop;
                tpPrice = tp;
                tradeSide = 1;
                tradesToday++;

                info(String.format("LONG: entry=%.2f, stop=%.2f, TP=%.2f, yRange=%.2f",
                    close, stop, tp, yesterdayRange));

                var marker = settings.getMarker(Inputs.UP_MARKER);
                if (marker != null && marker.isEnabled()) {
                    addFigure(new Marker(new Coordinate(barTime, low),
                        Enums.Position.BOTTOM, marker, "Long @ " + fmt(close)));
                }
            }
        }
        // Short breakout: low breaks short trigger
        else if (!Double.isNaN(shortTrigger) && low < shortTrigger) {
            double stopDist = yesterdayRange * stopMult;
            double stop = instr.round(close + stopDist);
            double risk = Math.abs(stop - close);
            if (risk > 0) {
                double tp = instr.round(close - targetRR * risk);
                ctx.sell(contracts);
                entryPrice = close;
                stopPrice = stop;
                tpPrice = tp;
                tradeSide = -1;
                tradesToday++;

                info(String.format("SHORT: entry=%.2f, stop=%.2f, TP=%.2f, yRange=%.2f",
                    close, stop, tp, yesterdayRange));

                var marker = settings.getMarker(Inputs.DOWN_MARKER);
                if (marker != null && marker.isEnabled()) {
                    addFigure(new Marker(new Coordinate(barTime, high),
                        Enums.Position.TOP, marker, "Short @ " + fmt(close)));
                }
            }
        }
    }

    // ==================== Signal Handler ====================
    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        // All trade logic handled in onBarUpdate()
    }

    // ==================== Utility ====================
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
