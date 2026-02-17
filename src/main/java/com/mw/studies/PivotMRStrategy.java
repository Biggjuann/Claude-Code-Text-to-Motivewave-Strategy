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
 * Pivot Point Mean Reversion Strategy v1.0
 *
 * Based on Andrea Unger's published ES strategy, adapted for mean-reversion.
 * Uses prior day's RTH OHLC to compute floor trader pivot points.
 * FADE at R1 (short) and S1 (long), targeting the Pivot Point (PP) as the mean.
 *
 * ES is mean-reverting intraday — price tends to be attracted back toward PP.
 * This strategy exploits overextensions at R1/S1 with PP as the natural target.
 *
 * Counter-trend filter: higher highs block longs (allow shorts at R1),
 * lower lows block shorts (allow longs at S1).
 *
 * Reference: Unger Academy + classic floor trader pivot bounce methodology.
 *
 * Architecture: Vector pattern
 *   - calculate() computes RTH OHLC, daily ATR, pivot levels, filters
 *   - onBarUpdate() handles all trade entry and management
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "PIVOT_MR",
    rb = "com.mw.studies.nls.strings",
    name = "PIVOT_MR",
    label = "LBL_PIVOT_MR",
    desc = "DESC_PIVOT_MR",
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
public class PivotMRStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String ATR_PERIOD = "atrPeriod";
    private static final String ATR_STOP_MULT = "atrStopMult";
    private static final String TREND_FILTER_ON = "trendFilterOn";
    private static final String TREND_FILTER_DAYS = "trendFilterDays";
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ENTRY_END = "entryEnd";
    private static final String EOD_TIME = "eodTime";

    // ==================== Values ====================
    enum Values { PLACEHOLDER }

    // ==================== State ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // Daily OHLC archive
    private final List<Double> dailyHighs = new ArrayList<>();
    private final List<Double> dailyLows = new ArrayList<>();
    private final List<Double> dailyCloses = new ArrayList<>();
    private static final int MAX_DAILY = 50;

    // Current day RTH tracking
    private double rthOpen = Double.NaN;
    private double rthHigh = Double.NaN;
    private double rthLow = Double.NaN;
    private double rthClose = Double.NaN;
    private boolean rthStarted = false;

    // Pivot levels
    private double pivot = Double.NaN;
    private double r1 = Double.NaN;
    private double s1 = Double.NaN;
    private boolean pivotsSet = false;

    // Daily ATR
    private double dailyAtr = Double.NaN;

    // Filters
    private boolean canGoLong = true;
    private boolean canGoShort = true;

    // Trade state
    private double entryPrice = 0.0;
    private double stopPrice = 0.0;
    private double tpPrice = 0.0;
    private int tradeSide = 0;

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
        var grp = tab.addGroup("ATR Parameters");
        grp.addRow(new IntegerDescriptor(ATR_PERIOD, "ATR Period", 14, 1, 100, 1));
        grp.addRow(new DoubleDescriptor(ATR_STOP_MULT, "ATR Stop Mult", 1.5, 0.1, 5.0, 0.1));

        grp = tab.addGroup("Counter-Trend Filter");
        grp.addRow(new BooleanDescriptor(TREND_FILTER_ON, "Trend Filter", true));
        grp.addRow(new IntegerDescriptor(TREND_FILTER_DAYS, "Trend Filter Days", 5, 1, 50, 1));

        grp = tab.addGroup("Session");
        grp.addRow(new IntegerDescriptor(ENTRY_END, "Entry Cutoff (HHMM)", 1300, 0, 2359, 1));
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

        sd.addQuickSettings(CONTRACTS, ATR_STOP_MULT, TREND_FILTER_DAYS, MAX_TRADES_DAY);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, ATR_STOP_MULT, TREND_FILTER_DAYS);
    }

    // ==================== Lifecycle ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== Pivot MR Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== Pivot MR Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        dailyHighs.clear();
        dailyLows.clear();
        dailyCloses.clear();
        rthOpen = Double.NaN;
        rthHigh = Double.NaN;
        rthLow = Double.NaN;
        rthClose = Double.NaN;
        rthStarted = false;
        pivot = Double.NaN;
        r1 = Double.NaN;
        s1 = Double.NaN;
        pivotsSet = false;
        dailyAtr = Double.NaN;
        canGoLong = true;
        canGoShort = true;
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

    // ==================== Calculate (RTH OHLC, ATR, pivots, filters) ====================
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
        double close = series.getClose(index);
        double open = series.getOpen(index);

        // Track RTH OHLC
        if (barTimeInt >= 935 && barTimeInt <= 1600) {
            if (!rthStarted) {
                rthOpen = open;
                rthHigh = high;
                rthLow = low;
                rthStarted = true;
            } else {
                if (high > rthHigh) rthHigh = high;
                if (low < rthLow) rthLow = low;
            }
            rthClose = close;
        }

        // Daily reset
        if (barDay != lastResetDay) {
            // Archive previous day
            if (rthStarted && !Double.isNaN(rthOpen)) {
                dailyHighs.add(rthHigh);
                dailyLows.add(rthLow);
                dailyCloses.add(rthClose);
                if (dailyHighs.size() > MAX_DAILY) {
                    dailyHighs.remove(0);
                    dailyLows.remove(0);
                    dailyCloses.remove(0);
                }
            }

            rthOpen = Double.NaN;
            rthHigh = Double.NaN;
            rthLow = Double.NaN;
            rthClose = Double.NaN;
            rthStarted = false;

            tradesToday = 0;
            eodProcessed = false;
            pivotsSet = false;
            lastResetDay = barDay;

            computePivots();
            computeDailyAtr();
            computeFilters();
        }

        series.setComplete(index);
    }

    // ==================== Pivot Points ====================
    private void computePivots()
    {
        int n = dailyCloses.size();
        if (n < 1) {
            pivotsSet = false;
            return;
        }

        double yh = dailyHighs.get(n - 1);
        double yl = dailyLows.get(n - 1);
        double yc = dailyCloses.get(n - 1);

        pivot = (yh + yl + yc) / 3.0;
        r1 = 2.0 * pivot - yl;
        s1 = 2.0 * pivot - yh;
        pivotsSet = true;
    }

    // ==================== Daily ATR ====================
    private void computeDailyAtr()
    {
        int period = getSettings().getInteger(ATR_PERIOD, 14);
        int n = dailyCloses.size();
        if (n < period + 1) {
            dailyAtr = Double.NaN;
            return;
        }
        double sum = 0;
        for (int i = n - period; i < n; i++) {
            double tr = Math.max(
                dailyHighs.get(i) - dailyLows.get(i),
                Math.max(
                    Math.abs(dailyHighs.get(i) - dailyCloses.get(i - 1)),
                    Math.abs(dailyLows.get(i) - dailyCloses.get(i - 1))
                )
            );
            sum += tr;
        }
        dailyAtr = sum / period;
    }

    // ==================== Counter-Trend Filter ====================
    private void computeFilters()
    {
        canGoLong = true;
        canGoShort = true;

        if (!getSettings().getBoolean(TREND_FILTER_ON, true)) return;

        int days = getSettings().getInteger(TREND_FILTER_DAYS, 5);
        int n = dailyHighs.size();
        if (n < days + 1) return;

        // Counter-trend MR: fade overextensions
        // Higher highs → uptrend → block longs at S1, allow shorts at R1
        // Lower lows → downtrend → block shorts at R1, allow longs at S1
        if (dailyHighs.get(n - 1) > dailyHighs.get(n - days - 1)) {
            canGoLong = false;
        }
        if (dailyLows.get(n - 1) < dailyLows.get(n - days - 1)) {
            canGoShort = false;
        }
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
            if (tradeSide == 1) { // long (fade at S1, target PP)
                if (low <= stopPrice) {
                    ctx.closeAtMarket();
                    info("STOP hit at " + fmt(stopPrice));
                    resetTradeState();
                    return;
                }
                if (high >= tpPrice) {
                    ctx.closeAtMarket();
                    info("TP hit at PP=" + fmt(tpPrice));
                    resetTradeState();
                    return;
                }
            } else { // short (fade at R1, target PP)
                if (high >= stopPrice) {
                    ctx.closeAtMarket();
                    info("STOP hit at " + fmt(stopPrice));
                    resetTradeState();
                    return;
                }
                if (low <= tpPrice) {
                    ctx.closeAtMarket();
                    info("TP hit at PP=" + fmt(tpPrice));
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
        if (!pivotsSet || Double.isNaN(dailyAtr)) return;
        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 1);
        if (tradesToday >= maxTrades) return;
        int entryEnd = settings.getInteger(ENTRY_END, 1300);
        if (barTimeInt < 935 || barTimeInt > entryEnd) return;

        double atrStopMult = settings.getDouble(ATR_STOP_MULT, 1.5);
        int contracts = settings.getInteger(CONTRACTS, 2);

        double stopDist = atrStopMult * dailyAtr;
        if (stopDist <= 0) return;

        // FADE SHORT at R1: price has risen to resistance → short, target PP
        if (canGoShort && close > r1) {
            double stop = instr.round(r1 + stopDist);
            double tp = pivot;
            ctx.sell(contracts);
            entryPrice = close;
            stopPrice = stop;
            tpPrice = tp;
            tradeSide = -1;
            tradesToday++;

            info(String.format("FADE SHORT: entry=%.2f, stop=%.2f, TP=%.2f (PP), R1=%.2f, ATR=%.2f",
                close, stop, tp, r1, dailyAtr));

            var marker = settings.getMarker(Inputs.DOWN_MARKER);
            if (marker != null && marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high),
                    Enums.Position.TOP, marker, "Fade S @ " + fmt(close)));
            }
        }
        // FADE LONG at S1: price has dropped to support → long, target PP
        else if (canGoLong && close < s1) {
            double stop = instr.round(s1 - stopDist);
            double tp = pivot;
            ctx.buy(contracts);
            entryPrice = close;
            stopPrice = stop;
            tpPrice = tp;
            tradeSide = 1;
            tradesToday++;

            info(String.format("FADE LONG: entry=%.2f, stop=%.2f, TP=%.2f (PP), S1=%.2f, ATR=%.2f",
                close, stop, tp, s1, dailyAtr));

            var marker = settings.getMarker(Inputs.UP_MARKER);
            if (marker != null && marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low),
                    Enums.Position.BOTTOM, marker, "Fade L @ " + fmt(close)));
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
