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
 * Displacement-Doji-Reversal (DDR) Strategy v1.0
 *
 * Detects a 3-bar candlestick reversal pattern:
 *   Bar[-2]: Displacement candle (range >= avg_range x mult)
 *   Bar[-1]: Doji (body_pct <= threshold — indecision/stalling)
 *   Bar[ 0]: Displacement candle in OPPOSITE direction
 *
 * Short setup: bullish displacement -> doji -> bearish displacement
 * Long setup:  bearish displacement -> doji -> bullish displacement
 *
 * Stop = highest high (short) / lowest low (long) of the 3-bar pattern.
 * TP   = entry +/- target_rr x risk.
 *
 * Best backtest (short-only, VIX 15-20): PF 2.65, Sharpe 6.08
 * Robust sweet spot: displacement_mult 1.75-2.0, doji_body 30%
 *
 * Architecture: Vector pattern
 *   - calculate() maintains rolling bar range buffer from RTH bars
 *   - onBarUpdate() handles 3-bar pattern detection, trade entry, management, and EOD
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "DDR_REVERSAL",
    rb = "com.mw.studies.nls.strings",
    name = "DDR_REVERSAL",
    label = "LBL_DDR_REVERSAL",
    desc = "DESC_DDR_REVERSAL",
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
public class DDRReversalStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String LOOKBACK = "lookback";
    private static final String DISPLACEMENT_MULT = "displacementMult";
    private static final String DOJI_MAX_BODY_PCT = "dojiMaxBodyPct";
    private static final String TARGET_RR = "targetRR";
    private static final String DIRECTION = "direction";
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ENTRY_START = "entryStart";
    private static final String ENTRY_END = "entryEnd";
    private static final String EOD_TIME = "eodTime";

    // Direction constants
    private static final String DIR_BOTH = "Both";
    private static final String DIR_LONG = "Long Only";
    private static final String DIR_SHORT = "Short Only";

    // ==================== Values ====================
    enum Values { PLACEHOLDER }

    // ==================== State ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // Rolling bar range buffer (RTH bars only)
    private final List<Double> ranges = new ArrayList<>();
    private static final int MAX_RANGES = 100;

    // Previous 2 bars for 3-bar pattern detection
    private double prev2Open, prev2High, prev2Low, prev2Close;
    private double prev1Open, prev1High, prev1Low, prev1Close;
    private int prevCount = 0; // counts up to 2

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
        var grp = tab.addGroup("DDR Pattern Detection");
        grp.addRow(new IntegerDescriptor(LOOKBACK, "Lookback Bars (Avg Range)", 20, 5, 100, 1));
        grp.addRow(new DoubleDescriptor(DISPLACEMENT_MULT, "Displacement Multiplier", 2.0, 1.0, 5.0, 0.25));
        grp.addRow(new DoubleDescriptor(DOJI_MAX_BODY_PCT, "Doji Max Body %", 30.0, 5.0, 60.0, 5.0));

        grp = tab.addGroup("Trade Settings");
        grp.addRow(new DoubleDescriptor(TARGET_RR, "Target R:R", 2.0, 0.5, 10.0, 0.25));
        grp.addRow(new DiscreteDescriptor(DIRECTION, "Direction", DIR_SHORT,
            java.util.List.of(new NVP(DIR_BOTH, DIR_BOTH), new NVP(DIR_LONG, DIR_LONG), new NVP(DIR_SHORT, DIR_SHORT))));

        grp = tab.addGroup("Session");
        grp.addRow(new IntegerDescriptor(ENTRY_START, "Entry Start (HHMM)", 935, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_END, "Entry Cutoff (HHMM)", 1530, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades/Day", 2, 1, 10, 1));

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

        sd.addQuickSettings(CONTRACTS, DISPLACEMENT_MULT, DOJI_MAX_BODY_PCT, TARGET_RR, DIRECTION);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, DISPLACEMENT_MULT, DOJI_MAX_BODY_PCT, TARGET_RR, DIRECTION);
    }

    // ==================== Lifecycle ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== DDR Reversal Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== DDR Reversal Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        ranges.clear();
        prevCount = 0;
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

    // ==================== Calculate (Range buffer) ====================
    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        if (index < 1) return;

        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);

        // Daily reset
        if (barDay != lastResetDay) {
            tradesToday = 0;
            eodProcessed = false;
            prevCount = 0;
            lastResetDay = barDay;
        }

        // Only accumulate ranges from RTH bars (9:35-16:00)
        if (barTimeInt >= 935 && barTimeInt <= 1600) {
            double high = series.getHigh(index);
            double low = series.getLow(index);
            double barRange = high - low;
            if (barRange > 0) {
                ranges.add(barRange);
                if (ranges.size() > MAX_RANGES) {
                    ranges.remove(0);
                }
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

        double open = series.getOpen(index);
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        double barRange = high - low;

        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        int position = ctx.getPosition();
        Settings settings = getSettings();

        // ===== EOD Flatten =====
        int eodTime = settings.getInteger(EOD_TIME, 1640);
        if (barTimeInt >= eodTime && !eodProcessed) {
            if (position != 0) {
                ctx.closeAtMarket();
                info("EOD flatten at " + barTimeInt);
                resetTradeState();
            }
            eodProcessed = true;
            shiftHistory(open, high, low, close);
            return;
        }

        // ===== Trade Management =====
        if (position != 0 && tradeSide != 0) {
            if (tradeSide == 1) { // long
                if (low <= stopPrice) {
                    ctx.closeAtMarket();
                    info("STOP hit at " + fmt(stopPrice));
                    resetTradeState();
                    shiftHistory(open, high, low, close);
                    return;
                }
                if (tpPrice > 0 && high >= tpPrice) {
                    ctx.closeAtMarket();
                    info("TP hit at " + fmt(tpPrice));
                    resetTradeState();
                    shiftHistory(open, high, low, close);
                    return;
                }
            } else { // short
                if (high >= stopPrice) {
                    ctx.closeAtMarket();
                    info("STOP hit at " + fmt(stopPrice));
                    resetTradeState();
                    shiftHistory(open, high, low, close);
                    return;
                }
                if (tpPrice > 0 && low <= tpPrice) {
                    ctx.closeAtMarket();
                    info("TP hit at " + fmt(tpPrice));
                    resetTradeState();
                    shiftHistory(open, high, low, close);
                    return;
                }
            }
            shiftHistory(open, high, low, close);
            return;
        }

        // Reset stale trade state
        if (position == 0 && tradeSide != 0) {
            resetTradeState();
        }

        // ===== Entry Logic =====
        if (position != 0) {
            shiftHistory(open, high, low, close);
            return;
        }

        int lookback = settings.getInteger(LOOKBACK, 20);
        if (ranges.size() < lookback) {
            shiftHistory(open, high, low, close);
            return;
        }
        if (prevCount < 2) {
            shiftHistory(open, high, low, close);
            return;
        }

        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 2);
        if (tradesToday >= maxTrades) {
            shiftHistory(open, high, low, close);
            return;
        }

        int entryStart = settings.getInteger(ENTRY_START, 935);
        int entryEnd = settings.getInteger(ENTRY_END, 1530);
        if (barTimeInt < entryStart || barTimeInt > entryEnd) {
            shiftHistory(open, high, low, close);
            return;
        }

        // Compute average range from lookback
        int bufSize = ranges.size();
        double sumRange = 0;
        int count = 0;
        for (int i = bufSize - 1; i >= 0 && count < lookback; i--) {
            sumRange += ranges.get(i);
            count++;
        }
        double avgRange = sumRange / count;
        if (avgRange <= 0) {
            shiftHistory(open, high, low, close);
            return;
        }

        double displacementMult = settings.getDouble(DISPLACEMENT_MULT, 2.0);
        double dojiMaxBodyPct = settings.getDouble(DOJI_MAX_BODY_PCT, 30.0);
        double dispThreshold = avgRange * displacementMult;

        // ===== 3-bar DDR pattern detection =====

        // Bar[-2] checks
        double prev2Range = prev2High - prev2Low;
        boolean prev2Bullish = prev2Close > prev2Open;
        boolean prev2Bearish = prev2Close < prev2Open;
        boolean prev2IsDisp = prev2Range >= dispThreshold;

        // Bar[-1] checks (doji)
        double prev1Range = prev1High - prev1Low;
        double prev1Body = Math.abs(prev1Close - prev1Open);
        double prev1BodyPct = prev1Range > 0 ? (prev1Body / prev1Range * 100.0) : 100.0;
        boolean prev1IsDoji = prev1BodyPct <= dojiMaxBodyPct;

        // Bar[0] (current) checks
        boolean currBullish = close > open;
        boolean currBearish = close < open;
        boolean currIsDisp = barRange >= dispThreshold;

        String direction = settings.getString(DIRECTION, DIR_SHORT);
        Instrument instr = ctx.getInstrument();
        double targetRR = settings.getDouble(TARGET_RR, 2.0);
        int contracts = settings.getInteger(CONTRACTS, 2);

        // ----- Short setup: bullish disp -> doji -> bearish disp -----
        if (!direction.equals(DIR_LONG)) {
            if (prev2Bullish && prev2IsDisp && prev1IsDoji && currBearish && currIsDisp) {
                double stop = instr.round(Math.max(prev2High, Math.max(prev1High, high)));
                double risk = stop - close;
                if (risk > 0) {
                    double tp = instr.round(close - targetRR * risk);

                    ctx.sell(contracts);
                    entryPrice = close;
                    stopPrice = stop;
                    tpPrice = tp;
                    tradeSide = -1;
                    tradesToday++;

                    info(String.format("SHORT DDR: entry=%.2f, stop=%.2f, TP=%.2f, disp=%.1fx",
                        close, stop, tp, barRange / avgRange));

                    drawTradeLevels(barTime, close, stop, tp, -1);

                    var marker = settings.getMarker(Inputs.DOWN_MARKER);
                    if (marker != null && marker.isEnabled()) {
                        addFigure(new Marker(new Coordinate(barTime, high),
                            Enums.Position.TOP, marker, "Short DDR @ " + fmt(close)));
                    }

                    shiftHistory(open, high, low, close);
                    return;
                }
            }
        }

        // ----- Long setup: bearish disp -> doji -> bullish disp -----
        if (!direction.equals(DIR_SHORT)) {
            if (prev2Bearish && prev2IsDisp && prev1IsDoji && currBullish && currIsDisp) {
                double stop = instr.round(Math.min(prev2Low, Math.min(prev1Low, low)));
                double risk = close - stop;
                if (risk > 0) {
                    double tp = instr.round(close + targetRR * risk);

                    ctx.buy(contracts);
                    entryPrice = close;
                    stopPrice = stop;
                    tpPrice = tp;
                    tradeSide = 1;
                    tradesToday++;

                    info(String.format("LONG DDR: entry=%.2f, stop=%.2f, TP=%.2f, disp=%.1fx",
                        close, stop, tp, barRange / avgRange));

                    drawTradeLevels(barTime, close, stop, tp, 1);

                    var marker = settings.getMarker(Inputs.UP_MARKER);
                    if (marker != null && marker.isEnabled()) {
                        addFigure(new Marker(new Coordinate(barTime, low),
                            Enums.Position.BOTTOM, marker, "Long DDR @ " + fmt(close)));
                    }

                    shiftHistory(open, high, low, close);
                    return;
                }
            }
        }

        shiftHistory(open, high, low, close);
    }

    // ==================== Signal Handler ====================
    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        // All trade logic handled in onBarUpdate()
    }

    // ==================== Bar History ====================
    private void shiftHistory(double o, double h, double l, double c)
    {
        prev2Open = prev1Open;
        prev2High = prev1High;
        prev2Low = prev1Low;
        prev2Close = prev1Close;

        prev1Open = o;
        prev1High = h;
        prev1Low = l;
        prev1Close = c;

        if (prevCount < 2) prevCount++;
    }

    // ==================== Drawing ====================
    private static final java.awt.Color SL_COLOR = new java.awt.Color(220, 50, 50);
    private static final java.awt.Color TP_COLOR = new java.awt.Color(50, 180, 50);
    private static final java.awt.Color ENTRY_COLOR = new java.awt.Color(100, 150, 255);
    private static final java.awt.Stroke DASH_STROKE = new java.awt.BasicStroke(
        1.5f, java.awt.BasicStroke.CAP_BUTT, java.awt.BasicStroke.JOIN_MITER,
        10.0f, new float[]{6.0f, 4.0f}, 0.0f);
    private static final java.awt.Font LEVEL_FONT = new java.awt.Font("SansSerif", java.awt.Font.PLAIN, 11);

    private void drawTradeLevels(long entryTime, double entry, double stop, double tp, int side)
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

        if (tp > 0) {
            Line tpLine = new Line(entryTime, tp, endTime, tp);
            tpLine.setColor(TP_COLOR);
            tpLine.setStroke(DASH_STROKE);
            tpLine.setText("TP " + fmt(tp), LEVEL_FONT);
            addFigure(tpLine);
        }
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
