package com.mw.studies;

import java.awt.Color;
import java.util.ArrayList;
import java.util.List;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * ICT Implied Fair Value Gap (IFVG) Study
 *
 * Port of LuxAlgo's TradingView indicator to MotiveWave.
 * Detects Bullish/Bearish IFVGs using 3-bar structure and shadow-threshold rules.
 *
 * Detection logic (3-bar pattern at bars [i-2, i-1, i]):
 *   - Middle bar (i-1) has the largest body of the three
 *   - Current bar (i) and bar (i-2) have qualifying shadow ratios above threshold
 *   - The implied zone (shadow midpoints) forms a valid gap (top > bottom)
 *
 * Bullish IFVG zone:
 *   top = avg(min(close[i], open[i]), low[i])     (midpoint of bar i lower shadow)
 *   btm = avg(max(close[i-2], open[i-2]), high[i-2]) (midpoint of bar i-2 upper shadow)
 *
 * Bearish IFVG zone:
 *   top = avg(min(close[i-2], open[i-2]), low[i-2])  (midpoint of bar i-2 lower shadow)
 *   btm = avg(max(close[i], open[i]), high[i])       (midpoint of bar i upper shadow)
 *
 * Draws zone boundary lines and average line from bar (i-2) to bar (i+ext).
 * Optionally extends the average as a plot after the extension window has passed.
 *
 * Original indicator (c) LuxAlgo, CC BY-NC-SA 4.0. Logic port only.
 *
 * @version 1.0.0
 * @author MW Study Builder
 * @generated 2026-02-11
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "ICT_IFVG",
    rb = "com.mw.studies.nls.strings",
    name = "ICT_IFVG",
    label = "LBL_ICT_IFVG",
    desc = "DESC_ICT_IFVG",
    menu = "MW Generated",
    overlay = true,
    supportsBarUpdates = false
)
public class ICTIFVGStudy extends Study
{
    // ==================== Input Keys ====================
    private static final String THR_PCT = "thrPct";
    private static final String EXT = "ext";
    private static final String EXT_AVG = "extAvg";
    private static final String SHOW_BULL = "showBull";
    private static final String SHOW_BEAR = "showBear";
    private static final String MAX_OBJECTS = "maxObjects";
    private static final String BULL_ZONE_PATH = "bullZonePath";
    private static final String BULL_AVG_PATH = "bullAvgPath";
    private static final String BEAR_ZONE_PATH = "bearZonePath";
    private static final String BEAR_AVG_PATH = "bearAvgPath";

    // ==================== Values ====================
    enum Values { BULL_AVG, BEAR_AVG }

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Tab: Settings =====
        var tab = sd.addTab("Settings");
        var grp = tab.addGroup("IFVG Detection");
        grp.addRow(new DoubleDescriptor(THR_PCT, "Shadow Threshold %", 30.0, 0, 100, 0.1));
        grp.addRow(new IntegerDescriptor(EXT, "IFVG Extension (bars)", 8, 0, 5000, 1));
        grp.addRow(new BooleanDescriptor(EXT_AVG, "Extend Averages", false));

        grp = tab.addGroup("Visibility");
        grp.addRow(new BooleanDescriptor(SHOW_BULL, "Show Bullish IFVG", true));
        grp.addRow(new BooleanDescriptor(SHOW_BEAR, "Show Bearish IFVG", true));

        grp = tab.addGroup("Performance");
        grp.addRow(new IntegerDescriptor(MAX_OBJECTS, "Max Draw Objects", 500, 50, 2000, 50));

        // ===== Tab: Display =====
        Color bullColor = new Color(49, 121, 245);
        Color bearColor = new Color(255, 93, 0);
        Color bullZoneColor = new Color(49, 121, 245, 128);
        Color bearZoneColor = new Color(255, 93, 0, 128);

        tab = sd.addTab("Display");
        grp = tab.addGroup("Bullish IFVG");
        grp.addRow(new PathDescriptor(BULL_ZONE_PATH, "Zone Lines",
            bullZoneColor, 1.0f, new float[]{4, 4}, true, false, false));
        grp.addRow(new PathDescriptor(BULL_AVG_PATH, "Average Line",
            bullColor, 1.0f, null, true, false, false));

        grp = tab.addGroup("Bearish IFVG");
        grp.addRow(new PathDescriptor(BEAR_ZONE_PATH, "Zone Lines",
            bearZoneColor, 1.0f, new float[]{4, 4}, true, false, false));
        grp.addRow(new PathDescriptor(BEAR_AVG_PATH, "Average Line",
            bearColor, 1.0f, null, true, false, false));

        sd.addQuickSettings(THR_PCT, EXT, SHOW_BULL, SHOW_BEAR);

        var desc = createRD();
        desc.setLabelSettings(THR_PCT, EXT);
        desc.exportValue(new ValueDescriptor(Values.BULL_AVG, "Bull IFVG Avg", null));
        desc.exportValue(new ValueDescriptor(Values.BEAR_AVG, "Bear IFVG Avg", null));
        desc.declarePath(Values.BULL_AVG, BULL_AVG_PATH);
        desc.declarePath(Values.BEAR_AVG, BEAR_AVG_PATH);
    }

    @Override
    public int getMinBars() { return 3; }

    @Override
    protected void calculate(int index, DataContext ctx) { }

    // ==================== BAR CLOSE ====================
    @Override
    public void onBarClose(DataContext ctx) { calculateValues(ctx); }

    // ==================== CALCULATE VALUES ====================
    @Override
    protected void calculateValues(DataContext ctx)
    {
        clearFigures();
        var series = ctx.getDataSeries();
        int size = series.size();
        if (size < 3) return;

        var settings = getSettings();
        double thr = settings.getDouble(THR_PCT, 30.0) / 100.0;
        int ext = settings.getInteger(EXT, 8);
        boolean extAvg = settings.getBoolean(EXT_AVG, false);
        boolean showBull = settings.getBoolean(SHOW_BULL, true);
        boolean showBear = settings.getBoolean(SHOW_BEAR, true);
        int maxObjects = settings.getInteger(MAX_OBJECTS, 500);

        double bullAvgVal = Double.NaN;
        double bearAvgVal = Double.NaN;
        int lastBullIdx = Integer.MIN_VALUE;
        int lastBearIdx = Integer.MIN_VALUE;

        // Collect IFVG detections: [isBull(1/0), barIndex, top, bottom, avg]
        List<double[]> detections = new ArrayList<>();

        for (int i = 2; i < size; i++) {
            double open0 = series.getOpen(i);
            double high0 = series.getHigh(i);
            double low0 = series.getLow(i);
            double close0 = series.getClose(i);

            double open1 = series.getOpen(i - 1);
            double close1 = series.getClose(i - 1);

            double open2 = series.getOpen(i - 2);
            double high2 = series.getHigh(i - 2);
            double low2 = series.getLow(i - 2);
            double close2 = series.getClose(i - 2);

            double r = high0 - low0;
            double b0 = Math.abs(close0 - open0);
            double b1 = Math.abs(close1 - open1);
            double b2 = Math.abs(close2 - open2);

            // ===== Bullish IFVG =====
            if (showBull && b1 > Math.max(b0, b2) && low0 < high2) {
                double lowerShadow0 = Math.min(close0, open0) - low0;
                double upperShadow2 = high2 - Math.max(close2, open2);
                double bullTop = (Math.min(close0, open0) + low0) / 2.0;
                double bullBtm = (Math.max(close2, open2) + high2) / 2.0;

                if (safeDiv(lowerShadow0, r) > thr
                    && safeDiv(upperShadow2, r) > thr
                    && bullTop > bullBtm) {
                    bullAvgVal = (bullTop + bullBtm) / 2.0;
                    lastBullIdx = i;
                    detections.add(new double[]{1, i, bullTop, bullBtm, bullAvgVal});
                }
            }

            // ===== Bearish IFVG =====
            if (showBear && b1 > Math.max(b0, b2) && high0 > low2) {
                double upperShadow0 = high0 - Math.max(close0, open0);
                double lowerShadow2 = Math.min(close2, open2) - low2;
                double bearTop = (Math.min(close2, open2) + low2) / 2.0;
                double bearBtm = (Math.max(close0, open0) + high0) / 2.0;

                if (safeDiv(upperShadow0, r) > thr
                    && safeDiv(lowerShadow2, r) > thr
                    && bearTop > bearBtm) {
                    bearAvgVal = (bearTop + bearBtm) / 2.0;
                    lastBearIdx = i;
                    detections.add(new double[]{0, i, bearTop, bearBtm, bearAvgVal});
                }
            }

            // ===== Extended average plots (only after extension window passes) =====
            if (extAvg) {
                if ((i - lastBullIdx) > ext && !Double.isNaN(bullAvgVal)) {
                    series.setDouble(i, Values.BULL_AVG, bullAvgVal);
                }
                if ((i - lastBearIdx) > ext && !Double.isNaN(bearAvgVal)) {
                    series.setDouble(i, Values.BEAR_AVG, bearAvgVal);
                }
            }
        }

        // ===== Draw IFVG zones (3 lines per zone, capped by maxObjects) =====
        int maxZones = maxObjects / 3;
        int startIdx = Math.max(0, detections.size() - maxZones);

        for (int j = startIdx; j < detections.size(); j++) {
            double[] d = detections.get(j);
            boolean isBull = d[0] == 1;
            int barIdx = (int) d[1];
            double top = d[2];
            double bottom = d[3];
            double avg = d[4];

            long startTime = series.getStartTime(Math.max(0, barIdx - 2));
            long endTime = getExtendedTime(series, barIdx + ext);

            var zonePath = settings.getPath(isBull ? BULL_ZONE_PATH : BEAR_ZONE_PATH);
            var avgPath = settings.getPath(isBull ? BULL_AVG_PATH : BEAR_AVG_PATH);

            if (zonePath != null && zonePath.isEnabled()) {
                addFigure(new Line(new Coordinate(startTime, top),
                    new Coordinate(endTime, top), zonePath));
                addFigure(new Line(new Coordinate(startTime, bottom),
                    new Coordinate(endTime, bottom), zonePath));
            }
            if (avgPath != null && avgPath.isEnabled()) {
                addFigure(new Line(new Coordinate(startTime, avg),
                    new Coordinate(endTime, avg), avgPath));
            }
        }
    }

    // ==================== HELPERS ====================

    private double safeDiv(double a, double b) {
        return b == 0 ? 0 : a / b;
    }

    private long getExtendedTime(DataSeries series, int barIndex) {
        int size = series.size();
        if (barIndex < size) return series.getStartTime(barIndex);
        if (size < 2) return series.getStartTime(size - 1);
        long interval = series.getStartTime(size - 1) - series.getStartTime(size - 2);
        return series.getStartTime(size - 1) + interval * (barIndex - size + 1);
    }
}
