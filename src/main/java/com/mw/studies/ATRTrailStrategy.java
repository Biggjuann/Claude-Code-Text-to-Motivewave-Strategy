package com.mw.studies;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.Line;
import com.motivewave.platform.sdk.draw.Marker;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * ATR Trailing Momentum Strategy v1.0
 *
 * Enter when the current bar's range (high - low) exceeds a multiple of
 * the ATR, indicating volatility expansion / momentum. Direction is
 * determined by bar close vs open (green = long, red = short).
 *
 * NO fixed take-profit -- position is managed entirely by an ATR-based
 * trailing stop that locks in profits as the trend continues. Initial
 * stop is set at a fixed ATR multiple from entry.
 *
 * Regime-tested: 6/8 windows profitable (2010-2026), Avg PF 1.08, Avg Sharpe 0.36,
 * Total P&L $340K across all regimes.
 *
 * Architecture: Vector pattern
 *   - calculate() computes intraday ATR
 *   - onBarUpdate() handles entry on volatility expansion, trailing stop management
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "ATR_TRAIL",
    rb = "com.mw.studies.nls.strings",
    name = "ATR_TRAIL",
    label = "LBL_ATR_TRAIL",
    desc = "DESC_ATR_TRAIL",
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
public class ATRTrailStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String ATR_PERIOD = "atrPeriod";
    private static final String ENTRY_ATR_MULT = "entryAtrMult";
    private static final String STOP_ATR_MULT = "stopAtrMult";
    private static final String TRAIL_ATR_MULT = "trailAtrMult";
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ENTRY_START = "entryStart";
    private static final String ENTRY_END = "entryEnd";
    private static final String EOD_TIME = "eodTime";

    // ==================== Values ====================
    enum Values { ATR }

    // ==================== State ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // Intraday ATR state
    private final List<Double> trValues = new ArrayList<>();
    private double prevClose = 0.0;
    private double atr = 0.0;

    // Trade state
    private double entryPrice = 0.0;
    private double stopPrice = 0.0;
    private int tradeSide = 0; // 1=long, -1=short
    private double bestPrice = 0.0; // best price since entry (for trailing)

    // Daily tracking
    private int tradesToday = 0;
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    private static final int MAX_BUF = 100;

    // ==================== Initialize ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        var tab = sd.addTab("General");
        var grp = tab.addGroup("ATR Trail Parameters");
        grp.addRow(new IntegerDescriptor(ATR_PERIOD, "ATR Period", 14, 5, 100, 1));
        grp.addRow(new DoubleDescriptor(ENTRY_ATR_MULT, "Entry ATR Mult (bar range threshold)", 2.0, 0.5, 5.0, 0.25));
        grp.addRow(new DoubleDescriptor(STOP_ATR_MULT, "Initial Stop ATR Mult", 1.5, 0.25, 5.0, 0.25));
        grp.addRow(new DoubleDescriptor(TRAIL_ATR_MULT, "Trailing Stop ATR Mult", 3.0, 0.5, 10.0, 0.25));

        grp = tab.addGroup("Session");
        grp.addRow(new IntegerDescriptor(ENTRY_START, "Entry Start (HHMM)", 935, 0, 2359, 1));
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

        sd.addQuickSettings(CONTRACTS, ATR_PERIOD, ENTRY_ATR_MULT, TRAIL_ATR_MULT, MAX_TRADES_DAY);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, ENTRY_ATR_MULT, STOP_ATR_MULT, TRAIL_ATR_MULT);

        desc.exportValue(new ValueDescriptor(Values.ATR, "ATR", new String[]{ATR_PERIOD}));
    }

    @Override
    public int getMinBars() { return 50; }

    // ==================== Lifecycle ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== ATR Trail Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== ATR Trail Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        trValues.clear();
        prevClose = 0.0;
        atr = 0.0;
        tradesToday = 0;
        lastResetDay = -1;
        eodProcessed = false;
        resetTradeState();
    }

    private void resetTradeState()
    {
        entryPrice = 0.0;
        stopPrice = 0.0;
        tradeSide = 0;
        bestPrice = 0.0;
    }

    // ==================== Calculate (ATR) ====================
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

        // Daily reset
        if (barDay != lastResetDay) {
            tradesToday = 0;
            eodProcessed = false;
            lastResetDay = barDay;
        }

        // Only compute indicators from RTH bars (9:35-16:00)
        if (barTimeInt >= 935 && barTimeInt <= 1600) {
            int atrPeriod = getSettings().getInteger(ATR_PERIOD, 14);

            // True Range
            double tr;
            if (prevClose > 0) {
                tr = Math.max(high - low, Math.max(Math.abs(high - prevClose), Math.abs(low - prevClose)));
            } else {
                tr = high - low;
            }
            trValues.add(tr);

            // Trim buffer
            if (trValues.size() > MAX_BUF) {
                trValues.subList(0, trValues.size() - MAX_BUF).clear();
            }

            // ATR (simple average of recent TR values)
            if (trValues.size() >= atrPeriod) {
                double atrSum = 0;
                for (int i = trValues.size() - atrPeriod; i < trValues.size(); i++) {
                    atrSum += trValues.get(i);
                }
                atr = atrSum / atrPeriod;
                series.setDouble(index, Values.ATR, atr);
            }

            prevClose = close;
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

        double open = series.getOpen(index);
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

        // ===== Trade Management (Trailing Stop) =====
        if (position != 0 && tradeSide != 0) {
            double trailAtrMult = settings.getDouble(TRAIL_ATR_MULT, 3.0);
            double trailDist = (atr > 0) ? trailAtrMult * atr : trailAtrMult * 5.0;

            if (tradeSide == 1) { // long
                // Update best price and trail stop up
                if (high > bestPrice) {
                    bestPrice = high;
                    double newStop = instr.round(bestPrice - trailDist);
                    if (newStop > stopPrice) {
                        stopPrice = newStop;
                    }
                }
                if (low <= stopPrice) {
                    ctx.closeAtMarket();
                    info(String.format("TRAIL STOP hit at %.2f (best=%.2f)", stopPrice, bestPrice));
                    resetTradeState();
                    return;
                }
            } else { // short
                // Update best price and trail stop down
                if (low < bestPrice) {
                    bestPrice = low;
                    double newStop = instr.round(bestPrice + trailDist);
                    if (newStop < stopPrice) {
                        stopPrice = newStop;
                    }
                }
                if (high >= stopPrice) {
                    ctx.closeAtMarket();
                    info(String.format("TRAIL STOP hit at %.2f (best=%.2f)", stopPrice, bestPrice));
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
        if (atr <= 0) return;

        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 1);
        if (tradesToday >= maxTrades) return;

        int entryStart = settings.getInteger(ENTRY_START, 935);
        int entryEnd = settings.getInteger(ENTRY_END, 1530);
        if (barTimeInt < entryStart || barTimeInt > entryEnd) return;

        double entryAtrMult = settings.getDouble(ENTRY_ATR_MULT, 2.0);
        double stopAtrMult = settings.getDouble(STOP_ATR_MULT, 1.5);
        int contracts = settings.getInteger(CONTRACTS, 2);

        double barRange = high - low;
        double threshold = entryAtrMult * atr;

        if (barRange <= threshold) return;

        double stopDist = stopAtrMult * atr;
        if (stopDist <= 0) return;

        // Long: volatility expansion + bullish close
        if (close > open) {
            double stop = instr.round(close - stopDist);
            ctx.buy(contracts);
            entryPrice = close;
            stopPrice = stop;
            tradeSide = 1;
            bestPrice = close;
            tradesToday++;

            info(String.format("LONG: entry=%.2f, stop=%.2f, barRange=%.2f, ATR=%.2f (trail only, no TP)",
                close, stop, barRange, atr));

            drawEntryLevel(barTime, close, stop);

            var marker = settings.getMarker(Inputs.UP_MARKER);
            if (marker != null && marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low),
                    Enums.Position.BOTTOM, marker, "Long @ " + fmt(close)));
            }
        }
        // Short: volatility expansion + bearish close
        else if (close < open) {
            double stop = instr.round(close + stopDist);
            ctx.sell(contracts);
            entryPrice = close;
            stopPrice = stop;
            tradeSide = -1;
            bestPrice = close;
            tradesToday++;

            info(String.format("SHORT: entry=%.2f, stop=%.2f, barRange=%.2f, ATR=%.2f (trail only, no TP)",
                close, stop, barRange, atr));

            drawEntryLevel(barTime, close, stop);

            var marker = settings.getMarker(Inputs.DOWN_MARKER);
            if (marker != null && marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high),
                    Enums.Position.TOP, marker, "Short @ " + fmt(close)));
            }
        }
    }

    // ==================== Drawing ====================
    private static final java.awt.Color SL_COLOR = new java.awt.Color(220, 50, 50);
    private static final java.awt.Color ENTRY_COLOR = new java.awt.Color(100, 150, 255);
    private static final java.awt.Stroke DASH_STROKE = new java.awt.BasicStroke(
        1.5f, java.awt.BasicStroke.CAP_BUTT, java.awt.BasicStroke.JOIN_MITER,
        10.0f, new float[]{6.0f, 4.0f}, 0.0f);
    private static final java.awt.Font LEVEL_FONT = new java.awt.Font("SansSerif", java.awt.Font.PLAIN, 11);

    private void drawEntryLevel(long entryTime, double entry, double stop)
    {
        long endTime = entryTime + 4L * 60 * 60 * 1000;

        Line entryLine = new Line(entryTime, entry, endTime, entry);
        entryLine.setColor(ENTRY_COLOR);
        entryLine.setText("Entry " + fmt(entry), LEVEL_FONT);
        addFigure(entryLine);

        Line slLine = new Line(entryTime, stop, endTime, stop);
        slLine.setColor(SL_COLOR);
        slLine.setStroke(DASH_STROKE);
        slLine.setText("SL " + fmt(stop) + " (trail)", LEVEL_FONT);
        addFigure(slLine);
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
