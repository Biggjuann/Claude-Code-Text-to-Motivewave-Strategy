package com.mw.studies;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
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
 * Displacement Filtered Strategy v1.0
 *
 * Enhanced version of Displacement Candle Strategy with regime filters.
 * Backtested 2019-2025 (ES x10): VIX>25/<18 filter transforms results:
 *   Baseline: $805K P&L, $-348K MaxDD, Sharpe 0.54
 *   Filtered: $924K P&L, $-102K MaxDD, Sharpe 1.29
 *
 * Filters (manual toggles for live trading):
 *   - VIX Blocked: user enables when VIX > 25, disables when VIX < 18
 *   - Skip Events: user enables on FOMC/CPI/NFP days
 *   - Weekly Pivot: longs only above weekly PP, shorts only below
 *
 * Core logic identical to DisplacementCandleStrategy v1.2.
 *
 * Architecture: Vector pattern
 *   - calculate() maintains rolling bar range buffer and weekly pivot
 *   - onBarUpdate() handles filters, displacement detection, entry, management, EOD
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "DISPLACEMENT_FILTERED",
    rb = "com.mw.studies.nls.strings",
    name = "DISPLACEMENT_FILTERED",
    label = "LBL_DISPLACEMENT_FILTERED",
    desc = "DESC_DISPLACEMENT_FILTERED",
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
public class DisplacementFilteredStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String LOOKBACK = "lookback";
    private static final String DISPLACEMENT_MULT = "displacementMult";
    private static final String TARGET_RR = "targetRR";
    private static final String CONTRACTS = "contracts";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ENTRY_END = "entryEnd";
    private static final String EOD_TIME = "eodTime";
    private static final String PIVOT_FILTER = "pivotFilter";
    private static final String VIX_AUTO = "vixAuto";
    private static final String VIX_BLOCKED = "vixBlocked";
    private static final String SKIP_EVENTS = "skipEvents";

    // File-based VIX auto-filter
    private static final String REGIME_FILE = "C:/Users/jung_/MotiveWave Extensions/volatility_regime.json";
    private static final long RELOAD_INTERVAL_MS = 5 * 60 * 1000;    // 5 minutes
    private static final long MAX_FILE_AGE_MS = 24L * 60 * 60 * 1000; // 24 hours

    // ==================== Values ====================
    enum Values { PLACEHOLDER }

    // ==================== State ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // Rolling bar range buffer (RTH bars only)
    private final List<Double> ranges = new ArrayList<>();
    private static final int MAX_RANGES = 50;

    // VIX auto-filter cache
    private String cachedJson = null;
    private long lastLoadTime = 0;
    private boolean autoVixBlocked = false;

    // Trade state
    private double entryPrice = 0.0;
    private double stopPrice = 0.0;
    private double tpPrice = 0.0;
    private int tradeSide = 0; // 1=long, -1=short

    // Daily tracking
    private int tradesToday = 0;
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // Weekly pivot tracking
    private double weeklyHigh = Double.MIN_VALUE;
    private double weeklyLow = Double.MAX_VALUE;
    private double weeklyClose = 0.0;
    private double prevWeekPivot = 0.0;
    private int currentWeekNum = -1;

    // ==================== Initialize ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        var tab = sd.addTab("General");
        var grp = tab.addGroup("Displacement Detection");
        grp.addRow(new IntegerDescriptor(LOOKBACK, "Lookback Bars", 10, 5, 100, 1));
        grp.addRow(new DoubleDescriptor(DISPLACEMENT_MULT, "Displacement Multiplier", 2.0, 1.0, 5.0, 0.1));
        grp.addRow(new DoubleDescriptor(TARGET_RR, "Target R:R", 3.0, 0.5, 10.0, 0.25));

        grp = tab.addGroup("Filters");
        grp.addRow(new BooleanDescriptor(VIX_AUTO, "Auto VIX Filter (reads regime file)", true));
        grp.addRow(new BooleanDescriptor(VIX_BLOCKED, "VIX Blocked (manual override)", false));
        grp.addRow(new BooleanDescriptor(SKIP_EVENTS, "Skip Events Today (FOMC/CPI/NFP)", false));
        grp.addRow(new BooleanDescriptor(PIVOT_FILTER, "Weekly Pivot Filter", false));

        grp = tab.addGroup("Session");
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

        sd.addQuickSettings(CONTRACTS, DISPLACEMENT_MULT, TARGET_RR, LOOKBACK, VIX_AUTO, VIX_BLOCKED, SKIP_EVENTS, PIVOT_FILTER);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, DISPLACEMENT_MULT, TARGET_RR);
    }

    // ==================== Lifecycle ====================
    @Override
    public void onActivate(OrderContext ctx)
    {
        resetTradeState();
        info("=== Displacement Filtered Strategy Activated ===");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        info("=== Displacement Filtered Strategy Deactivated ===");
    }

    @Override
    public void clearState()
    {
        super.clearState();
        ranges.clear();
        tradesToday = 0;
        lastResetDay = -1;
        eodProcessed = false;
        weeklyHigh = Double.MIN_VALUE;
        weeklyLow = Double.MAX_VALUE;
        weeklyClose = 0.0;
        prevWeekPivot = 0.0;
        currentWeekNum = -1;
        cachedJson = null;
        lastLoadTime = 0;
        autoVixBlocked = false;
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
            lastResetDay = barDay;
        }

        // Weekly pivot tracking (RTH bars only, classic: PP = (H+L+C)/3)
        if (barTimeInt >= 930 && barTimeInt <= 1600) {
            double h = series.getHigh(index);
            double l = series.getLow(index);
            double c = series.getClose(index);

            int weekNum = getWeekOfYear(barTime, NY_TZ);
            if (weekNum != currentWeekNum) {
                // New week — finalize previous week's pivot
                if (currentWeekNum != -1 && weeklyHigh != Double.MIN_VALUE) {
                    prevWeekPivot = (weeklyHigh + weeklyLow + weeklyClose) / 3.0;
                }
                weeklyHigh = h;
                weeklyLow = l;
                weeklyClose = c;
                currentWeekNum = weekNum;
            } else {
                if (h > weeklyHigh) weeklyHigh = h;
                if (l < weeklyLow) weeklyLow = l;
                weeklyClose = c; // always latest close
            }
        }

        // Only accumulate ranges from RTH bars (9:35-16:00)
        if (barTimeInt >= 935 && barTimeInt <= 1600) {
            double high = series.getHigh(index);
            double low = series.getLow(index);
            double barRange = high - low;
            ranges.add(barRange);
            if (ranges.size() > MAX_RANGES) {
                ranges.remove(0);
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

        double high = series.getHigh(index);
        double low = series.getLow(index);

        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        int position = ctx.getPosition();

        // ===== EOD Flatten =====
        int eodTime = getSettings().getInteger(EOD_TIME, 1640);
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
                if (tpPrice > 0 && high >= tpPrice) {
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
                if (tpPrice > 0 && low <= tpPrice) {
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
        if (position != 0) return;

        Settings settings = getSettings();
        int lookback = settings.getInteger(LOOKBACK, 10);
        if (ranges.size() < lookback + 1) return;

        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 2);
        if (tradesToday >= maxTrades) return;

        int entryEnd = settings.getInteger(ENTRY_END, 1530);
        if (barTimeInt < 935 || barTimeInt > entryEnd) return;

        // ===== Filter Checks =====
        // VIX auto-filter: read from volatility_regime.json
        if (settings.getBoolean(VIX_AUTO, true)) {
            updateAutoVixState();
            if (autoVixBlocked) return;
        }

        // VIX manual override (always wins if enabled)
        if (settings.getBoolean(VIX_BLOCKED, false)) return;

        // Event filter: user manually enables on FOMC/CPI/NFP days
        if (settings.getBoolean(SKIP_EVENTS, false)) return;

        double open = series.getOpen(index);
        double close = series.getClose(index);
        double barRange = high - low;

        // Compute average range of previous N bars (excluding current)
        int bufSize = ranges.size();
        double sumRange = 0;
        for (int i = bufSize - 2; i >= bufSize - 1 - lookback && i >= 0; i--) {
            sumRange += ranges.get(i);
        }
        double avgRange = sumRange / lookback;
        if (avgRange <= 0) return;

        // Check displacement threshold
        double displacementMult = settings.getDouble(DISPLACEMENT_MULT, 2.0);
        double ratio = barRange / avgRange;
        if (ratio < displacementMult) return;

        // Direction: green candle → LONG, red candle → SHORT
        boolean isBullish = close > open;
        boolean isBearish = close < open;
        if (!isBullish && !isBearish) return; // doji, skip

        // Weekly pivot filter: longs only above PP, shorts only below PP
        boolean pivotFilterOn = settings.getBoolean(PIVOT_FILTER, false);
        if (pivotFilterOn && prevWeekPivot > 0) {
            if (isBullish && close < prevWeekPivot) return;  // price below pivot, skip long
            if (isBearish && close > prevWeekPivot) return;  // price above pivot, skip short
        }

        Instrument instr = ctx.getInstrument();
        double targetRR = settings.getDouble(TARGET_RR, 3.0);
        int contracts = settings.getInteger(CONTRACTS, 2);

        if (isBullish) {
            double stop = instr.round(low);
            double risk = close - stop;
            if (risk <= 0) return;
            double tp = targetRR > 0 ? instr.round(close + targetRR * risk) : 0.0;

            ctx.buy(contracts);
            entryPrice = close;
            stopPrice = stop;
            tpPrice = tp;
            tradeSide = 1;
            tradesToday++;

            info(String.format("LONG: entry=%.2f, stop=%.2f, TP=%.2f, ratio=%.1fx",
                close, stop, tp, ratio));

            drawTradeLevels(barTime, close, stop, tp, 1);

            var marker = settings.getMarker(Inputs.UP_MARKER);
            if (marker != null && marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low),
                    Enums.Position.BOTTOM, marker, "Long @ " + fmt(close)));
            }
        } else {
            double stop = instr.round(high);
            double risk = stop - close;
            if (risk <= 0) return;
            double tp = targetRR > 0 ? instr.round(close - targetRR * risk) : 0.0;

            ctx.sell(contracts);
            entryPrice = close;
            stopPrice = stop;
            tpPrice = tp;
            tradeSide = -1;
            tradesToday++;

            info(String.format("SHORT: entry=%.2f, stop=%.2f, TP=%.2f, ratio=%.1fx",
                close, stop, tp, ratio));

            drawTradeLevels(barTime, close, stop, tp, -1);

            var marker = settings.getMarker(Inputs.DOWN_MARKER);
            if (marker != null && marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high),
                    Enums.Position.TOP, marker, "Short @ " + fmt(close)));
            }
        }
    }

    // ==================== Signal Handler ====================
    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        // All trade logic handled in onBarUpdate()
    }

    // ==================== Drawing ====================
    private static final java.awt.Color SL_COLOR = new java.awt.Color(220, 50, 50);   // red
    private static final java.awt.Color TP_COLOR = new java.awt.Color(50, 180, 50);   // green
    private static final java.awt.Color ENTRY_COLOR = new java.awt.Color(100, 150, 255); // blue
    private static final java.awt.Stroke DASH_STROKE = new java.awt.BasicStroke(
        1.5f, java.awt.BasicStroke.CAP_BUTT, java.awt.BasicStroke.JOIN_MITER,
        10.0f, new float[]{6.0f, 4.0f}, 0.0f);
    private static final java.awt.Font LEVEL_FONT = new java.awt.Font("SansSerif", java.awt.Font.PLAIN, 11);

    private void drawTradeLevels(long entryTime, double entry, double stop, double tp, int side)
    {
        long endTime = entryTime + 4L * 60 * 60 * 1000; // 4 hours ahead

        // Entry level (solid blue)
        Line entryLine = new Line(entryTime, entry, endTime, entry);
        entryLine.setColor(ENTRY_COLOR);
        entryLine.setText("Entry " + fmt(entry), LEVEL_FONT);
        addFigure(entryLine);

        // Stop loss (dashed red)
        Line slLine = new Line(entryTime, stop, endTime, stop);
        slLine.setColor(SL_COLOR);
        slLine.setStroke(DASH_STROKE);
        slLine.setText("SL " + fmt(stop), LEVEL_FONT);
        addFigure(slLine);

        // Take profit (dashed green)
        if (tp > 0) {
            Line tpLine = new Line(entryTime, tp, endTime, tp);
            tpLine.setColor(TP_COLOR);
            tpLine.setStroke(DASH_STROKE);
            tpLine.setText("TP " + fmt(tp), LEVEL_FONT);
            addFigure(tpLine);
        }
    }

    // ==================== VIX Auto-Filter ====================

    private void updateAutoVixState()
    {
        String json = loadJson();
        if (json == null) {
            // File missing/stale — fall through to manual toggle
            autoVixBlocked = false;
            return;
        }
        // Parse displacement_filter.band_status
        String status = parseNestedString(json, "displacement_filter", "band_status", "TRADEABLE");
        boolean wasBlocked = autoVixBlocked;
        autoVixBlocked = !"TRADEABLE".equals(status);
        if (autoVixBlocked != wasBlocked) {
            info("VIX Auto: " + status + " (was " + (wasBlocked ? "BLOCKED" : "ACTIVE") + ")");
        }
    }

    // ==================== JSON Loading ====================

    private String loadJson()
    {
        long now = System.currentTimeMillis();
        if (cachedJson != null && (now - lastLoadTime) < RELOAD_INTERVAL_MS) {
            return cachedJson;
        }

        File file = new File(REGIME_FILE);
        if (!file.exists()) {
            debug("Regime file not found: " + file.getAbsolutePath());
            cachedJson = null;
            return null;
        }

        // Staleness check
        if (now - file.lastModified() > MAX_FILE_AGE_MS) {
            debug("Regime file is stale (>24h), ignoring");
            cachedJson = null;
            return null;
        }

        try (BufferedReader br = new BufferedReader(new FileReader(file))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            cachedJson = sb.toString();
            lastLoadTime = now;
            debug("Regime data loaded from " + file.getAbsolutePath());
        } catch (Exception e) {
            debug("Failed to load regime file: " + e.getMessage());
            cachedJson = null;
        }

        return cachedJson;
    }

    // ==================== JSON Parsing ====================

    private String parseNestedString(String json, String outerKey, String innerKey, String defaultVal)
    {
        String pattern = "\"" + outerKey + "\"";
        int idx = json.indexOf(pattern);
        if (idx < 0) return defaultVal;
        int colon = json.indexOf(':', idx + pattern.length());
        if (colon < 0) return defaultVal;

        // Skip whitespace after colon
        int pos = colon + 1;
        while (pos < json.length() && Character.isWhitespace(json.charAt(pos))) pos++;

        // Find the opening brace of the nested object
        if (pos >= json.length() || json.charAt(pos) != '{') return defaultVal;
        int braceStart = pos;

        // Find matching closing brace
        int depth = 1;
        int braceEnd = braceStart + 1;
        while (braceEnd < json.length() && depth > 0) {
            char c = json.charAt(braceEnd);
            if (c == '{') depth++;
            else if (c == '}') depth--;
            braceEnd++;
        }

        String nested = json.substring(braceStart, braceEnd);

        // Parse string value from nested object
        String innerPattern = "\"" + innerKey + "\"";
        int innerIdx = nested.indexOf(innerPattern);
        if (innerIdx < 0) return defaultVal;
        int innerColon = nested.indexOf(':', innerIdx + innerPattern.length());
        if (innerColon < 0) return defaultVal;
        int openQuote = nested.indexOf('"', innerColon + 1);
        if (openQuote < 0) return defaultVal;
        int closeQuote = nested.indexOf('"', openQuote + 1);
        if (closeQuote < 0) return defaultVal;
        return nested.substring(openQuote + 1, closeQuote);
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

    private int getWeekOfYear(long time, TimeZone tz)
    {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.WEEK_OF_YEAR) + cal.get(Calendar.YEAR) * 100;
    }

    private String fmt(double val) { return String.format("%.2f", val); }
}
