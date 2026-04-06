package com.mw.studies;

import java.awt.Color;
import java.awt.Font;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.List;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.Line;
import com.motivewave.platform.sdk.draw.Marker;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * GEX (Gamma Exposure) Levels Study v1.0
 *
 * Reads gex_levels.json (produced by tools/gex_analyzer/gex_analyzer.py) and
 * draws horizontal lines for key options-derived support/resistance levels:
 *   - Put Wall: strike with highest put open interest (support)
 *   - Call Wall: strike with highest call open interest (resistance)
 *   - Gamma Flip: net GEX zero-crossing point (regime boundary)
 *   - Top-N Gamma: strikes with largest absolute GEX
 *
 * All levels are converted from SPY strikes to ES/MES prices by the Python
 * analyzer using a dynamic SPY→ES conversion ratio.
 *
 * Architecture: Pure overlay study (not a strategy).
 *   - calculateValues() reads JSON and draws Line figures
 *   - Reloads JSON every 5 minutes (capped)
 *   - 24-hour staleness check on JSON file
 *
 * @version 1.0.0
 * @author MW Study Builder
 * @generated 2026-02-24
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "GEX_LEVELS",
    rb = "com.mw.studies.nls.strings",
    name = "GEX_LEVELS",
    label = "LBL_GEX_LEVELS",
    desc = "DESC_GEX_LEVELS",
    menu = "MW Generated",
    overlay = true,
    supportsBarUpdates = false
)
public class GEXLevelsStudy extends Study
{
    // ==================== Constants ====================
    private static final String GEX_FILE = "C:/Users/jung_/MotiveWave Extensions/gex_levels.json";
    private static final long RELOAD_INTERVAL_MS = 5 * 60 * 1000;    // 5 minutes
    private static final long MAX_FILE_AGE_MS = 24L * 60 * 60 * 1000; // 24 hours

    // Values enum (required by validator; no plotted series for this study)
    enum Values { PLACEHOLDER }

    // Input keys
    private static final String TOP_N = "topN";
    private static final String SHOW_PUT_WALL = "showPutWall";
    private static final String SHOW_CALL_WALL = "showCallWall";
    private static final String SHOW_GAMMA_FLIP = "showGammaFlip";
    private static final String SHOW_TOP_GAMMA = "showTopGamma";
    private static final String SHOW_LABELS = "showLabels";
    private static final String SHOW_NET_GEX = "showNetGex";

    // Path descriptor keys (Display tab)
    private static final String PUT_WALL_PATH = "putWallPath";
    private static final String CALL_WALL_PATH = "callWallPath";
    private static final String GAMMA_FLIP_PATH = "gammaFlipPath";
    private static final String TOP_GAMMA_PATH = "topGammaPath";

    // Drawing
    private static final Font LABEL_FONT = new Font("SansSerif", Font.PLAIN, 11);

    // State
    private long lastLoadTime = 0;
    private String cachedJson = null;

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Tab: Settings =====
        var tab = sd.addTab("Settings");
        var grp = tab.addGroup("GEX Levels");
        grp.addRow(new IntegerDescriptor(TOP_N, "Top N Gamma Strikes", 5, 1, 20, 1));
        grp.addRow(new BooleanDescriptor(SHOW_PUT_WALL, "Show Put Wall", true));
        grp.addRow(new BooleanDescriptor(SHOW_CALL_WALL, "Show Call Wall", true));
        grp.addRow(new BooleanDescriptor(SHOW_GAMMA_FLIP, "Show Gamma Flip", true));
        grp.addRow(new BooleanDescriptor(SHOW_TOP_GAMMA, "Show Top Gamma", true));
        grp.addRow(new BooleanDescriptor(SHOW_LABELS, "Show Labels", true));
        grp.addRow(new BooleanDescriptor(SHOW_NET_GEX, "Show Net GEX Marker", true));

        // ===== Tab: Display =====
        Color putWallColor = new Color(220, 50, 50);        // red
        Color callWallColor = new Color(50, 180, 50);       // green
        Color gammaFlipColor = new Color(218, 165, 32);     // gold
        Color topGammaColor = new Color(0, 200, 200);       // cyan

        tab = sd.addTab("Display");
        grp = tab.addGroup("Put Wall");
        grp.addRow(new PathDescriptor(PUT_WALL_PATH, "Put Wall Line",
            putWallColor, 2.0f, null, true, false, false));

        grp = tab.addGroup("Call Wall");
        grp.addRow(new PathDescriptor(CALL_WALL_PATH, "Call Wall Line",
            callWallColor, 2.0f, null, true, false, false));

        grp = tab.addGroup("Gamma Flip");
        grp.addRow(new PathDescriptor(GAMMA_FLIP_PATH, "Gamma Flip Line",
            gammaFlipColor, 2.0f, new float[]{8, 4}, true, false, false));

        grp = tab.addGroup("Top Gamma");
        grp.addRow(new PathDescriptor(TOP_GAMMA_PATH, "Top Gamma Lines",
            topGammaColor, 1.0f, new float[]{4, 4}, true, false, false));

        sd.addQuickSettings(TOP_N, SHOW_PUT_WALL, SHOW_CALL_WALL, SHOW_GAMMA_FLIP, SHOW_TOP_GAMMA, SHOW_NET_GEX);
    }

    @Override
    public int getMinBars() { return 1; }

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
        if (size < 1) return;

        var settings = getSettings();
        int topN = settings.getInteger(TOP_N, 5);
        boolean showPutWall = settings.getBoolean(SHOW_PUT_WALL, true);
        boolean showCallWall = settings.getBoolean(SHOW_CALL_WALL, true);
        boolean showGammaFlip = settings.getBoolean(SHOW_GAMMA_FLIP, true);
        boolean showTopGamma = settings.getBoolean(SHOW_TOP_GAMMA, true);
        boolean showLabels = settings.getBoolean(SHOW_LABELS, true);
        boolean showNetGex = settings.getBoolean(SHOW_NET_GEX, true);

        // Load JSON (cached, reloads every 5 min)
        String json = loadJson();
        if (json == null) return;

        // Time range for lines: span the entire visible chart
        long startTime = series.getStartTime(0);
        long endTime = series.getEndTime(size - 1) + 24L * 60 * 60 * 1000;

        // --- Put Wall ---
        if (showPutWall) {
            double esLevel = parseNestedDouble(json, "put_wall", "es_level", Double.NaN);
            if (!Double.isNaN(esLevel) && esLevel > 0) {
                var path = settings.getPath(PUT_WALL_PATH);
                if (path != null && path.isEnabled()) {
                    Line line = new Line(new Coordinate(startTime, esLevel),
                        new Coordinate(endTime, esLevel), path);
                    if (showLabels) {
                        double spyStrike = parseNestedDouble(json, "put_wall", "spy_strike", 0);
                        line.setText("Put Wall " + fmt(esLevel) + " (SPY " + fmt(spyStrike) + ")", LABEL_FONT);
                    }
                    addFigure(line);
                }
            }
        }

        // --- Call Wall ---
        if (showCallWall) {
            double esLevel = parseNestedDouble(json, "call_wall", "es_level", Double.NaN);
            if (!Double.isNaN(esLevel) && esLevel > 0) {
                var path = settings.getPath(CALL_WALL_PATH);
                if (path != null && path.isEnabled()) {
                    Line line = new Line(new Coordinate(startTime, esLevel),
                        new Coordinate(endTime, esLevel), path);
                    if (showLabels) {
                        double spyStrike = parseNestedDouble(json, "call_wall", "spy_strike", 0);
                        line.setText("Call Wall " + fmt(esLevel) + " (SPY " + fmt(spyStrike) + ")", LABEL_FONT);
                    }
                    addFigure(line);
                }
            }
        }

        // --- Gamma Flip ---
        if (showGammaFlip) {
            double esLevel = parseNestedDouble(json, "gamma_flip", "es_level", Double.NaN);
            if (!Double.isNaN(esLevel) && esLevel > 0) {
                var path = settings.getPath(GAMMA_FLIP_PATH);
                if (path != null && path.isEnabled()) {
                    Line line = new Line(new Coordinate(startTime, esLevel),
                        new Coordinate(endTime, esLevel), path);
                    if (showLabels) {
                        line.setText("Gamma Flip " + fmt(esLevel), LABEL_FONT);
                    }
                    addFigure(line);
                }
            }
        }

        // --- Top-N Gamma Strikes ---
        if (showTopGamma) {
            var path = settings.getPath(TOP_GAMMA_PATH);
            if (path != null && path.isEnabled()) {
                List<double[]> topLevels = parseTopGammaLevels(json, topN);
                for (double[] lvl : topLevels) {
                    double esLevel = lvl[0];
                    double spyStrike = lvl[1];
                    double netGex = lvl[2];
                    boolean isCallHeavy = lvl[3] > 0;

                    Line line = new Line(new Coordinate(startTime, esLevel),
                        new Coordinate(endTime, esLevel), path);
                    if (showLabels) {
                        String gexStr = String.format("%+,.0f", netGex);
                        String typeStr = isCallHeavy ? "C" : "P";
                        line.setText("GEX " + fmt(esLevel) + " [" + typeStr + " " + gexStr + "]", LABEL_FONT);
                    }
                    addFigure(line);
                }
            }
        }

        // --- Net GEX Direction Marker ---
        if (showNetGex) {
            double netGexTotal = parseJsonDouble(json, "net_gex_total", 0);
            String gexDir = parseJsonString(json, "gex_direction", "UNKNOWN");
            boolean isPositive = gexDir.equals("POSITIVE");
            Color markerColor = isPositive ? new Color(50, 180, 50) : new Color(220, 50, 50);

            long lastBarTime = series.getEndTime(size - 1);
            double lastClose = series.getClose(size - 1);

            Marker marker = new Marker(
                new Coordinate(lastBarTime, lastClose),
                Enums.MarkerType.DIAMOND, Enums.Size.MEDIUM,
                Enums.Position.TOP, markerColor, markerColor);
            marker.setTextValue("Net GEX: " + formatGexValue(netGexTotal) + " (" + gexDir + ")");
            marker.setTextPosition(Enums.Position.TOP);
            addFigure(marker);
        }
    }

    // ==================== JSON LOADING ====================

    private String loadJson()
    {
        long now = System.currentTimeMillis();
        if (cachedJson != null && (now - lastLoadTime) < RELOAD_INTERVAL_MS) {
            return cachedJson;
        }

        File file = new File(GEX_FILE);
        if (!file.exists()) {
            debug("GEX file not found: " + file.getAbsolutePath());
            cachedJson = null;
            return null;
        }

        // Staleness check
        if (now - file.lastModified() > MAX_FILE_AGE_MS) {
            debug("GEX file is stale (>24h), ignoring");
            cachedJson = null;
            return null;
        }

        try (BufferedReader br = new BufferedReader(new FileReader(file))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            cachedJson = sb.toString();
            lastLoadTime = now;
            debug("GEX levels loaded from " + file.getAbsolutePath());
        } catch (Exception e) {
            debug("Failed to load GEX file: " + e.getMessage());
            cachedJson = null;
        }

        return cachedJson;
    }

    // ==================== JSON PARSING ====================

    /**
     * Parse a double value from a top-level JSON key.
     * Same pattern as SDKSwingReclaimStrategy.parseJsonDouble.
     */
    private double parseJsonDouble(String json, String key, double defaultVal)
    {
        String pattern = "\"" + key + "\"";
        int idx = json.indexOf(pattern);
        if (idx < 0) return defaultVal;
        int colon = json.indexOf(':', idx + pattern.length());
        if (colon < 0) return defaultVal;
        int start = colon + 1;
        while (start < json.length() && json.charAt(start) == ' ') start++;
        int end = start;
        while (end < json.length() && (Character.isDigit(json.charAt(end))
            || json.charAt(end) == '.' || json.charAt(end) == '-')) end++;
        if (end == start) return defaultVal;
        try {
            return Double.parseDouble(json.substring(start, end));
        } catch (NumberFormatException e) {
            return defaultVal;
        }
    }

    /**
     * Parse a string value from a top-level JSON key.
     * Same pattern as SDKSwingReclaimStrategy.parseJsonString.
     */
    private String parseJsonString(String json, String key, String defaultVal)
    {
        String pattern = "\"" + key + "\"";
        int idx = json.indexOf(pattern);
        if (idx < 0) return defaultVal;
        int colon = json.indexOf(':', idx + pattern.length());
        if (colon < 0) return defaultVal;
        int openQuote = json.indexOf('"', colon + 1);
        if (openQuote < 0) return defaultVal;
        int closeQuote = json.indexOf('"', openQuote + 1);
        if (closeQuote < 0) return defaultVal;
        return json.substring(openQuote + 1, closeQuote);
    }

    /**
     * Parse a double from a nested JSON object.
     * e.g. "put_wall": { "es_level": 5900.59 }
     * Finds the outer key's object, then parses the inner key within it.
     */
    private double parseNestedDouble(String json, String outerKey, String innerKey, double defaultVal)
    {
        String pattern = "\"" + outerKey + "\"";
        int idx = json.indexOf(pattern);
        if (idx < 0) return defaultVal;
        int colon = json.indexOf(':', idx + pattern.length());
        if (colon < 0) return defaultVal;

        // Skip whitespace after colon
        int pos = colon + 1;
        while (pos < json.length() && Character.isWhitespace(json.charAt(pos))) pos++;

        // Check for null
        if (pos + 4 <= json.length() && json.substring(pos, pos + 4).equals("null")) {
            return defaultVal;
        }

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
        return parseJsonDouble(nested, innerKey, defaultVal);
    }

    /**
     * Parse the top_gamma_levels array from JSON.
     * Returns list of [es_level, spy_strike, net_gex, isCallHeavy(1/0)].
     */
    private List<double[]> parseTopGammaLevels(String json, int maxN)
    {
        List<double[]> result = new ArrayList<>();

        String key = "\"top_gamma_levels\"";
        int idx = json.indexOf(key);
        if (idx < 0) return result;

        int colon = json.indexOf(':', idx + key.length());
        if (colon < 0) return result;

        // Find the opening bracket
        int bracketStart = json.indexOf('[', colon);
        if (bracketStart < 0) return result;

        // Find matching closing bracket
        int depth = 1;
        int bracketEnd = bracketStart + 1;
        while (bracketEnd < json.length() && depth > 0) {
            char c = json.charAt(bracketEnd);
            if (c == '[') depth++;
            else if (c == ']') depth--;
            bracketEnd++;
        }

        String arrayStr = json.substring(bracketStart + 1, bracketEnd - 1);

        // Parse each object in the array
        int pos = 0;
        int count = 0;
        while (pos < arrayStr.length() && count < maxN) {
            int objStart = arrayStr.indexOf('{', pos);
            if (objStart < 0) break;

            int objDepth = 1;
            int objEnd = objStart + 1;
            while (objEnd < arrayStr.length() && objDepth > 0) {
                char c = arrayStr.charAt(objEnd);
                if (c == '{') objDepth++;
                else if (c == '}') objDepth--;
                objEnd++;
            }

            String obj = arrayStr.substring(objStart, objEnd);
            double esLevel = parseJsonDouble(obj, "es_level", Double.NaN);
            double spyStrike = parseJsonDouble(obj, "spy_strike", 0);
            double netGex = parseJsonDouble(obj, "net_gex", 0);
            String type = parseJsonString(obj, "type", "PUT_HEAVY");
            double isCallHeavy = type.equals("CALL_HEAVY") ? 1.0 : 0.0;

            if (!Double.isNaN(esLevel)) {
                result.add(new double[]{esLevel, spyStrike, netGex, isCallHeavy});
            }

            pos = objEnd;
            count++;
        }

        return result;
    }

    // ==================== UTILITY ====================

    private String fmt(double val)
    {
        if (val == (long) val) return String.valueOf((long) val);
        return String.format("%.2f", val);
    }

    private String formatGexValue(double val)
    {
        double abs = Math.abs(val);
        String sign = val >= 0 ? "+" : "-";
        if (abs >= 1_000_000_000) return sign + String.format("%.1fB", abs / 1_000_000_000);
        if (abs >= 1_000_000) return sign + String.format("%.1fM", abs / 1_000_000);
        if (abs >= 1_000) return sign + String.format("%.0fK", abs / 1_000);
        return sign + String.format("%.0f", abs);
    }
}
