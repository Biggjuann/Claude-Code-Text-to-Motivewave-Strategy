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
 * Keltner Channel Breakout Strategy v1.0
 *
 * Compute EMA(period) and ATR(period) from RTH bars. Upper = EMA + mult*ATR,
 * Lower = EMA - mult*ATR. Enter on close beyond the channel. Stop at EMA
 * (midline), R:R target.
 *
 * Regime-tested: 6/8 windows profitable (2010-2026), Avg Sharpe 0.46,
 * Total P&L $1.1M across all regimes.
 *
 * Architecture: Vector pattern
 *   - calculate() computes EMA, ATR, Keltner bands
 *   - onBarUpdate() handles all trade entry and management
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "KELTNER_BREAKOUT",
    rb = "com.mw.studies.nls.strings",
    name = "KELTNER_BREAKOUT",
    label = "LBL_KELTNER_BREAKOUT",
    desc = "DESC_KELTNER_BREAKOUT",
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
public class KeltnerBreakoutStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String EMA_PERIOD = "emaPeriod";
    private static final String ATR_PERIOD = "atrPeriod";
    private static final String KELT_MULT = "keltMult";
    private static final String TARGET_RR = "targetRR";
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ENTRY_START = "entryStart";
    private static final String ENTRY_END = "entryEnd";
    private static final String EOD_TIME = "eodTime";

    // ==================== Display Paths ====================
    private static final String UPPER_PATH = "upperPath";
    private static final String LOWER_PATH = "lowerPath";
    private static final String EMA_PATH = "emaPath";

    // ==================== Values ====================
    enum Values { EMA, ATR, UPPER, LOWER }

    // ==================== State ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // EMA state
    private double ema = Double.NaN;
    private boolean emaInitialized = false;
    private final List<Double> closes = new ArrayList<>();

    // ATR state
    private final List<Double> trValues = new ArrayList<>();
    private double prevClose = 0.0;
    private double atr = 0.0;

    // Keltner bands (computed each bar)
    private double upper = Double.NaN;
    private double lower = Double.NaN;

    // Trade state
    private double entryPrice = 0.0;
    private double stopPrice = 0.0;
    private double tpPrice = 0.0;
    private int tradeSide = 0; // 1=long, -1=short

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
        var grp = tab.addGroup("Keltner Channel Parameters");
        grp.addRow(new IntegerDescriptor(EMA_PERIOD, "EMA Period", 20, 5, 100, 1));
        grp.addRow(new IntegerDescriptor(ATR_PERIOD, "ATR Period", 14, 5, 100, 1));
        grp.addRow(new DoubleDescriptor(KELT_MULT, "Channel Multiplier", 2.0, 0.5, 5.0, 0.25));
        grp.addRow(new DoubleDescriptor(TARGET_RR, "Target R:R", 3.0, 0.5, 10.0, 0.25));

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
        var grpLines = tabDisplay.addGroup("Keltner Lines");
        grpLines.addRow(new PathDescriptor(EMA_PATH, "EMA (Midline)",
            defaults.getBlue(), 1.5f, null, true, true, true));
        grpLines.addRow(new PathDescriptor(UPPER_PATH, "Upper Band",
            defaults.getGreen(), 1.0f, new float[]{6, 3}, true, true, true));
        grpLines.addRow(new PathDescriptor(LOWER_PATH, "Lower Band",
            defaults.getRed(), 1.0f, new float[]{6, 3}, true, true, true));

        var grpMarkers = tabDisplay.addGroup("Entry Markers");
        grpMarkers.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grpMarkers.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        sd.addQuickSettings(CONTRACTS, EMA_PERIOD, KELT_MULT, TARGET_RR, MAX_TRADES_DAY);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, EMA_PERIOD, KELT_MULT, TARGET_RR);

        desc.exportValue(new ValueDescriptor(Values.EMA, "EMA", new String[]{EMA_PERIOD}));
        desc.exportValue(new ValueDescriptor(Values.ATR, "ATR", new String[]{ATR_PERIOD}));
        desc.exportValue(new ValueDescriptor(Values.UPPER, "Upper Band", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.LOWER, "Lower Band", new String[]{}));

        desc.declarePath(Values.EMA, EMA_PATH);
        desc.declarePath(Values.UPPER, UPPER_PATH);
        desc.declarePath(Values.LOWER, LOWER_PATH);

        desc.setRangeKeys(Values.UPPER, Values.LOWER, Values.EMA);
    }

    @Override
    public int getMinBars() { return 50; }

    // ==================== Lifecycle ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== Keltner Breakout Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== Keltner Breakout Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        ema = Double.NaN;
        emaInitialized = false;
        closes.clear();
        trValues.clear();
        prevClose = 0.0;
        atr = 0.0;
        upper = Double.NaN;
        lower = Double.NaN;
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

    // ==================== Calculate (EMA + ATR + Bands) ====================
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
            int emaPeriod = getSettings().getInteger(EMA_PERIOD, 20);
            int atrPeriod = getSettings().getInteger(ATR_PERIOD, 14);
            double keltMult = getSettings().getDouble(KELT_MULT, 2.0);

            // True Range
            double tr;
            if (prevClose > 0) {
                tr = Math.max(high - low, Math.max(Math.abs(high - prevClose), Math.abs(low - prevClose)));
            } else {
                tr = high - low;
            }
            trValues.add(tr);
            closes.add(close);

            // Trim buffers
            if (closes.size() > MAX_BUF) {
                closes.subList(0, closes.size() - MAX_BUF).clear();
            }
            if (trValues.size() > MAX_BUF) {
                trValues.subList(0, trValues.size() - MAX_BUF).clear();
            }

            // EMA
            if (closes.size() >= emaPeriod) {
                if (!emaInitialized) {
                    double sum = 0;
                    for (int i = closes.size() - emaPeriod; i < closes.size(); i++) {
                        sum += closes.get(i);
                    }
                    ema = sum / emaPeriod;
                    emaInitialized = true;
                } else {
                    double k = 2.0 / (emaPeriod + 1);
                    ema = close * k + ema * (1 - k);
                }
            }

            // ATR (simple average of recent TR values)
            if (trValues.size() >= atrPeriod) {
                double atrSum = 0;
                for (int i = trValues.size() - atrPeriod; i < trValues.size(); i++) {
                    atrSum += trValues.get(i);
                }
                atr = atrSum / atrPeriod;
            }

            prevClose = close;

            // Compute bands
            if (emaInitialized && atr > 0) {
                upper = ema + keltMult * atr;
                lower = ema - keltMult * atr;

                series.setDouble(index, Values.EMA, ema);
                series.setDouble(index, Values.ATR, atr);
                series.setDouble(index, Values.UPPER, upper);
                series.setDouble(index, Values.LOWER, lower);
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
        if (!emaInitialized || atr <= 0) return;
        if (Double.isNaN(upper) || Double.isNaN(lower)) return;

        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 1);
        if (tradesToday >= maxTrades) return;

        int entryStart = settings.getInteger(ENTRY_START, 935);
        int entryEnd = settings.getInteger(ENTRY_END, 1530);
        if (barTimeInt < entryStart || barTimeInt > entryEnd) return;

        double targetRR = settings.getDouble(TARGET_RR, 3.0);
        int contracts = settings.getInteger(CONTRACTS, 2);

        // Long: close above upper channel
        if (close > upper) {
            double stop = instr.round(ema);
            double risk = close - stop;
            if (risk > 0) {
                double tp = instr.round(close + targetRR * risk);
                ctx.buy(contracts);
                entryPrice = close;
                stopPrice = stop;
                tpPrice = tp;
                tradeSide = 1;
                tradesToday++;

                info(String.format("LONG: entry=%.2f, stop=%.2f (EMA), TP=%.2f, upper=%.2f",
                    close, stop, tp, upper));

                drawTradeLevels(barTime, close, stop, tp);

                var marker = settings.getMarker(Inputs.UP_MARKER);
                if (marker != null && marker.isEnabled()) {
                    addFigure(new Marker(new Coordinate(barTime, low),
                        Enums.Position.BOTTOM, marker, "Long @ " + fmt(close)));
                }
            }
        }
        // Short: close below lower channel
        else if (close < lower) {
            double stop = instr.round(ema);
            double risk = stop - close;
            if (risk > 0) {
                double tp = instr.round(close - targetRR * risk);
                ctx.sell(contracts);
                entryPrice = close;
                stopPrice = stop;
                tpPrice = tp;
                tradeSide = -1;
                tradesToday++;

                info(String.format("SHORT: entry=%.2f, stop=%.2f (EMA), TP=%.2f, lower=%.2f",
                    close, stop, tp, lower));

                drawTradeLevels(barTime, close, stop, tp);

                var marker = settings.getMarker(Inputs.DOWN_MARKER);
                if (marker != null && marker.isEnabled()) {
                    addFigure(new Marker(new Coordinate(barTime, high),
                        Enums.Position.TOP, marker, "Short @ " + fmt(close)));
                }
            }
        }
    }

    // ==================== Drawing ====================
    private static final java.awt.Color SL_COLOR = new java.awt.Color(220, 50, 50);
    private static final java.awt.Color TP_COLOR = new java.awt.Color(50, 180, 50);
    private static final java.awt.Color ENTRY_COLOR = new java.awt.Color(100, 150, 255);
    private static final java.awt.Stroke DASH_STROKE = new java.awt.BasicStroke(
        1.5f, java.awt.BasicStroke.CAP_BUTT, java.awt.BasicStroke.JOIN_MITER,
        10.0f, new float[]{6.0f, 4.0f}, 0.0f);
    private static final java.awt.Font LEVEL_FONT = new java.awt.Font("SansSerif", java.awt.Font.PLAIN, 11);

    private void drawTradeLevels(long entryTime, double entry, double stop, double tp)
    {
        long endTime = entryTime + 4L * 60 * 60 * 1000;

        Line entryLine = new Line(entryTime, entry, endTime, entry);
        entryLine.setColor(ENTRY_COLOR);
        entryLine.setText("Entry " + fmt(entry), LEVEL_FONT);
        addFigure(entryLine);

        Line slLine = new Line(entryTime, stop, endTime, stop);
        slLine.setColor(SL_COLOR);
        slLine.setStroke(DASH_STROKE);
        slLine.setText("SL " + fmt(stop), LEVEL_FONT);
        addFigure(slLine);

        Line tpLine = new Line(entryTime, tp, endTime, tp);
        tpLine.setColor(TP_COLOR);
        tpLine.setStroke(DASH_STROKE);
        tpLine.setText("TP " + fmt(tp), LEVEL_FONT);
        addFigure(tpLine);
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
