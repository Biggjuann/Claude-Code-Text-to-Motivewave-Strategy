package com.mw.studies;

import java.awt.Color;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * ICT IFVG Retest Strategy
 *
 * Detects Implied Fair Value Gaps (3-bar shadow pattern) and trades their retests.
 * When price pulls back into an active IFVG zone, the strategy enters in the
 * direction of the gap with zone-edge stop placement and multi-target exits.
 *
 * INPUTS
 * - shadowThreshold (double): Min shadow ratio for qualifying bars [default: 30%]
 * - ifvgExtension (int): Bars to extend zone drawing [default: 8]
 * - maxWaitBars (int): Max bars after detection to wait for retest [default: 30]
 * - enableLong (bool): Allow bullish IFVG long entries [default: true]
 * - enableShort (bool): Allow bearish IFVG short entries [default: true]
 * - contracts (int): Position size [default: 2]
 * - stopBufferTicks (int): Ticks beyond zone edge for stop [default: 4]
 * - tp1Points (double): TP1 distance in points [default: 20]
 * - tp1Pct (int): % of contracts to close at TP1 [default: 50]
 * - trailPoints (double): Runner trailing distance [default: 15]
 *
 * SIGNALS
 * - IFVG_LONG: Bullish IFVG zone retest — enter long
 * - IFVG_SHORT: Bearish IFVG zone retest — enter short
 *
 * CALCULATION LOGIC
 * 1. Scan bars for 3-bar IFVG pattern (middle bar largest body, qualifying shadows)
 * 2. Track zones as ACTIVE, check for violation (close through zone) or expiration
 * 3. On retest (price enters zone without closing through it), fire entry signal
 * 4. Manage exits: TP1 partial, breakeven, runner trail, EOD flatten
 *
 * @version 1.0.0
 * @author MW Study Builder
 * @generated 2026-02-14
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "ICT_IFVG_RETEST",
    rb = "com.mw.studies.nls.strings",
    name = "ICT_IFVG_RETEST",
    label = "LBL_ICT_IFVG_RETEST",
    desc = "DESC_ICT_IFVG_RETEST",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    strategy = true,
    autoEntry = true,
    manualEntry = false,
    signals = true,
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true,
    supportsBarUpdates = false
)
public class ICTIFVGRetestStrategy extends Study
{
    // ==================== Input Keys ====================
    private static final String ENABLE_LONG = "enableLong";
    private static final String ENABLE_SHORT = "enableShort";
    private static final String THR_PCT = "thrPct";
    private static final String EXT = "ext";
    private static final String MAX_WAIT = "maxWait";
    private static final String MAX_ZONES = "maxZones";
    private static final String SESSION_ENABLED = "sessionEnabled";
    private static final String SESSION_START = "sessionStart";
    private static final String SESSION_END = "sessionEnd";
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String CONTRACTS = "contracts";
    private static final String STOP_BUFFER_TICKS = "stopBufferTicks";
    private static final String STOP_MIN_PTS = "stopMinPts";
    private static final String STOP_MAX_PTS = "stopMaxPts";
    private static final String BE_ENABLED = "beEnabled";
    private static final String BE_TRIGGER_PTS = "beTriggerPts";
    private static final String TP1_POINTS = "tp1Points";
    private static final String TP1_PCT = "tp1Pct";
    private static final String TRAIL_POINTS = "trailPoints";
    private static final String EOD_ENABLED = "eodEnabled";
    private static final String EOD_TIME = "eodTime";
    private static final String SHOW_ZONES = "showZones";
    private static final String BULL_ZONE_PATH = "bullZonePath";
    private static final String BULL_AVG_PATH = "bullAvgPath";
    private static final String BEAR_ZONE_PATH = "bearZonePath";
    private static final String BEAR_AVG_PATH = "bearAvgPath";

    // ==================== Zone States ====================
    private static final int ZONE_ACTIVE = 0;
    private static final int ZONE_VIOLATED = 1;
    private static final int ZONE_TRADED = 2;
    private static final int ZONE_EXPIRED = 3;

    // ==================== Values & Signals ====================
    enum Values { PLACEHOLDER }
    enum Signals { IFVG_LONG, IFVG_SHORT }

    // ==================== Inner Classes ====================
    private static class IFVGZone {
        double top;
        double bottom;
        double avg;
        boolean isBullish;
        int barIndex;
        int state;
        boolean traded;

        IFVGZone(double top, double bottom, boolean isBullish, int barIndex) {
            this.top = top;
            this.bottom = bottom;
            this.avg = (top + bottom) / 2.0;
            this.isBullish = isBullish;
            this.barIndex = barIndex;
            this.state = ZONE_ACTIVE;
            this.traded = false;
        }
    }

    // ==================== Constants ====================
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== State ====================
    private List<IFVGZone> zones = new ArrayList<>();
    private List<Marker> entryMarkers = new ArrayList<>();

    // Trade state (managed by onSignal/onBarClose, NOT cleared by calculateValues)
    private boolean isLongTrade = false;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double tp1Price = 0;
    private boolean tp1Filled = false;
    private boolean beActivated = false;
    private double bestPriceInTrade = Double.NaN;
    private double trailStopPrice = Double.NaN;
    private boolean trailingActive = false;

    // Track the zone that triggered entry for stop placement
    private double triggerZoneBottom = Double.NaN;
    private double triggerZoneTop = Double.NaN;

    // EOD tracking
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // ==================== INITIALIZE ====================
    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Tab: Setup =====
        var tab = sd.addTab("Setup");
        var grp = tab.addGroup("Direction");
        grp.addRow(new BooleanDescriptor(ENABLE_LONG, "Enable Long Setups", true));
        grp.addRow(new BooleanDescriptor(ENABLE_SHORT, "Enable Short Setups", true));

        grp = tab.addGroup("IFVG Detection");
        grp.addRow(new DoubleDescriptor(THR_PCT, "Shadow Threshold %", 30.0, 0, 100, 0.1));
        grp.addRow(new IntegerDescriptor(EXT, "IFVG Extension (bars)", 8, 0, 5000, 1));
        grp.addRow(new IntegerDescriptor(MAX_WAIT, "Max Wait for Retest (bars)", 30, 5, 200, 1));
        grp.addRow(new IntegerDescriptor(MAX_ZONES, "Max Active Zones", 500, 50, 2000, 50));

        // ===== Tab: Entry =====
        tab = sd.addTab("Entry");
        grp = tab.addGroup("Session Window (ET)");
        grp.addRow(new BooleanDescriptor(SESSION_ENABLED, "Restrict to Session Window", false));
        grp.addRow(new IntegerDescriptor(SESSION_START, "Session Start (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(SESSION_END, "Session End (HHMM)", 1600, 0, 2359, 1));

        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades Per Day", 3, 1, 10, 1));

        // ===== Tab: Risk =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 2, 1, 100, 1));

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new IntegerDescriptor(STOP_BUFFER_TICKS, "Stop Buffer (ticks beyond zone)", 4, 0, 50, 1));
        grp.addRow(new DoubleDescriptor(STOP_MIN_PTS, "Min Stop Distance (pts)", 2.0, 0.25, 50.0, 0.25));
        grp.addRow(new DoubleDescriptor(STOP_MAX_PTS, "Max Stop Distance (pts)", 40.0, 1.0, 200.0, 0.5));

        grp = tab.addGroup("Breakeven");
        grp.addRow(new BooleanDescriptor(BE_ENABLED, "Move Stop to Breakeven", true));
        grp.addRow(new DoubleDescriptor(BE_TRIGGER_PTS, "BE Trigger (points in profit)", 10.0, 0.25, 100.0, 0.25));

        // ===== Tab: Targets =====
        tab = sd.addTab("Targets");
        grp = tab.addGroup("TP1 (Partial)");
        grp.addRow(new DoubleDescriptor(TP1_POINTS, "TP1 Distance (points)", 20.0, 0.25, 200.0, 0.25));
        grp.addRow(new IntegerDescriptor(TP1_PCT, "TP1 % of Contracts", 50, 1, 99, 1));

        grp = tab.addGroup("Runner Trail");
        grp.addRow(new DoubleDescriptor(TRAIL_POINTS, "Trail Distance (points)", 15.0, 0.25, 100.0, 0.25));

        // ===== Tab: EOD =====
        tab = sd.addTab("EOD");
        grp = tab.addGroup("End of Day");
        grp.addRow(new BooleanDescriptor(EOD_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_TIME, "EOD Time (HHMM)", 1640, 0, 2359, 1));

        // ===== Tab: Display =====
        Color bullColor = new Color(49, 121, 245);
        Color bearColor = new Color(255, 93, 0);
        Color bullZoneColor = new Color(49, 121, 245, 128);
        Color bearZoneColor = new Color(255, 93, 0, 128);

        tab = sd.addTab("Display");
        grp = tab.addGroup("Zones");
        grp.addRow(new BooleanDescriptor(SHOW_ZONES, "Show IFVG Zones", true));
        grp.addRow(new PathDescriptor(BULL_ZONE_PATH, "Bullish Zone Lines",
            bullZoneColor, 1.0f, new float[]{4, 4}, true, false, false));
        grp.addRow(new PathDescriptor(BULL_AVG_PATH, "Bullish Average Line",
            bullColor, 1.0f, null, true, false, false));
        grp.addRow(new PathDescriptor(BEAR_ZONE_PATH, "Bearish Zone Lines",
            bearZoneColor, 1.0f, new float[]{4, 4}, true, false, false));
        grp.addRow(new PathDescriptor(BEAR_AVG_PATH, "Bearish Average Line",
            bearColor, 1.0f, null, true, false, false));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        sd.addQuickSettings(CONTRACTS, THR_PCT, TP1_POINTS, TRAIL_POINTS, MAX_TRADES_DAY);

        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, THR_PCT);
        desc.declareSignal(Signals.IFVG_LONG, "IFVG Long");
        desc.declareSignal(Signals.IFVG_SHORT, "IFVG Short");
    }

    @Override
    public int getMinBars() { return 3; }

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
        int maxWait = settings.getInteger(MAX_WAIT, 30);
        int maxZonesLimit = settings.getInteger(MAX_ZONES, 500);
        boolean enableLong = settings.getBoolean(ENABLE_LONG, true);
        boolean enableShort = settings.getBoolean(ENABLE_SHORT, true);
        boolean showZones = settings.getBoolean(SHOW_ZONES, true);
        int maxTrades = settings.getInteger(MAX_TRADES_DAY, 3);
        boolean eodEnabled = settings.getBoolean(EOD_ENABLED, true);
        int eodTime = settings.getInteger(EOD_TIME, 1640);
        boolean sessionEnabled = settings.getBoolean(SESSION_ENABLED, false);
        int sessionStart = settings.getInteger(SESSION_START, 930);
        int sessionEnd = settings.getInteger(SESSION_END, 1600);

        zones.clear();
        entryMarkers.clear();
        int localTradesToday = 0;
        int localLastDay = -1;

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

            long barTime = series.getStartTime(i);
            int barDay = getDayOfYear(barTime);
            int barTimeInt = getTimeInt(barTime);
            boolean canSignal = !series.isComplete(i) && series.isBarComplete(i);

            // Daily reset
            if (barDay != localLastDay) {
                localTradesToday = 0;
                localLastDay = barDay;
            }

            boolean pastEOD = eodEnabled && barTimeInt >= eodTime;
            boolean inSession = !sessionEnabled || (barTimeInt >= sessionStart && barTimeInt < sessionEnd);

            // ===== Detect Bullish IFVG =====
            if (b1 > Math.max(b0, b2) && low0 < high2) {
                double lowerShadow0 = Math.min(close0, open0) - low0;
                double upperShadow2 = high2 - Math.max(close2, open2);
                double bullTop = (Math.min(close0, open0) + low0) / 2.0;
                double bullBtm = (Math.max(close2, open2) + high2) / 2.0;

                if (safeDiv(lowerShadow0, r) > thr
                    && safeDiv(upperShadow2, r) > thr
                    && bullTop > bullBtm) {
                    zones.add(new IFVGZone(bullTop, bullBtm, true, i));
                }
            }

            // ===== Detect Bearish IFVG =====
            if (b1 > Math.max(b0, b2) && high0 > low2) {
                double upperShadow0 = high0 - Math.max(close0, open0);
                double lowerShadow2 = Math.min(close2, open2) - low2;
                double bearTop = (Math.min(close2, open2) + low2) / 2.0;
                double bearBtm = (Math.max(close0, open0) + high0) / 2.0;

                if (safeDiv(upperShadow0, r) > thr
                    && safeDiv(lowerShadow2, r) > thr
                    && bearTop > bearBtm) {
                    zones.add(new IFVGZone(bearTop, bearBtm, false, i));
                }
            }

            // ===== Process active zones: violation, expiration, retest =====
            for (IFVGZone zone : zones) {
                if (zone.state != ZONE_ACTIVE) continue;
                if (i <= zone.barIndex) continue; // skip detection bar itself

                // Expiration check
                if ((i - zone.barIndex) > maxWait) {
                    zone.state = ZONE_EXPIRED;
                    continue;
                }

                // Violation check: price closed through the zone
                if (zone.isBullish && close0 < zone.bottom) {
                    zone.state = ZONE_VIOLATED;
                    continue;
                }
                if (!zone.isBullish && close0 > zone.top) {
                    zone.state = ZONE_VIOLATED;
                    continue;
                }

                // Retest check
                if (zone.isBullish && enableLong) {
                    // Price enters zone from above: low touches/enters zone, close stays above bottom
                    if (low0 <= zone.top && close0 > zone.bottom) {
                        zone.state = ZONE_TRADED;
                        zone.traded = true;
                        boolean canEnter = !pastEOD && inSession && localTradesToday < maxTrades;
                        if (canEnter) {
                            localTradesToday++;
                            var marker = settings.getMarker(Inputs.UP_MARKER);
                            if (marker != null && marker.isEnabled()) {
                                entryMarkers.add(new Marker(new Coordinate(barTime, low0),
                                    Enums.Position.BOTTOM, marker,
                                    "IFVG L " + fmt(zone.avg)));
                            }
                            if (canSignal) {
                                ctx.signal(i, Signals.IFVG_LONG,
                                    "Bull IFVG retest [" + fmt(zone.bottom) + "-" + fmt(zone.top) + "]",
                                    close0);
                            }
                        }
                    }
                } else if (!zone.isBullish && enableShort) {
                    // Price enters zone from below: high touches/enters zone, close stays below top
                    if (high0 >= zone.bottom && close0 < zone.top) {
                        zone.state = ZONE_TRADED;
                        zone.traded = true;
                        boolean canEnter = !pastEOD && inSession && localTradesToday < maxTrades;
                        if (canEnter) {
                            localTradesToday++;
                            var marker = settings.getMarker(Inputs.DOWN_MARKER);
                            if (marker != null && marker.isEnabled()) {
                                entryMarkers.add(new Marker(new Coordinate(barTime, high0),
                                    Enums.Position.TOP, marker,
                                    "IFVG S " + fmt(zone.avg)));
                            }
                            if (canSignal) {
                                ctx.signal(i, Signals.IFVG_SHORT,
                                    "Bear IFVG retest [" + fmt(zone.bottom) + "-" + fmt(zone.top) + "]",
                                    close0);
                            }
                        }
                    }
                }
            }

            if (canSignal) series.setComplete(i);
        }

        // ===== Draw IFVG zones =====
        if (showZones) {
            // Draw only active and traded zones (skip violated/expired), cap to maxZonesLimit
            int drawn = 0;
            int startIdx = Math.max(0, zones.size() - maxZonesLimit);
            for (int j = startIdx; j < zones.size(); j++) {
                IFVGZone zone = zones.get(j);
                if (zone.state == ZONE_VIOLATED || zone.state == ZONE_EXPIRED) continue;

                long startTime = series.getStartTime(Math.max(0, zone.barIndex - 2));
                long endTime = getExtendedTime(series, zone.barIndex + ext);

                var zonePath = settings.getPath(zone.isBullish ? BULL_ZONE_PATH : BEAR_ZONE_PATH);
                var avgPath = settings.getPath(zone.isBullish ? BULL_AVG_PATH : BEAR_AVG_PATH);

                if (zonePath != null && zonePath.isEnabled()) {
                    addFigure(new Line(new Coordinate(startTime, zone.top),
                        new Coordinate(endTime, zone.top), zonePath));
                    addFigure(new Line(new Coordinate(startTime, zone.bottom),
                        new Coordinate(endTime, zone.bottom), zonePath));
                    drawn++;
                }
                if (avgPath != null && avgPath.isEnabled()) {
                    addFigure(new Line(new Coordinate(startTime, zone.avg),
                        new Coordinate(endTime, zone.avg), avgPath));
                }
            }
        }

        // Draw entry markers
        for (Marker m : entryMarkers) addFigure(m);

        // Debug summary
        int active = 0, violated = 0, traded = 0, expired = 0;
        for (IFVGZone zone : zones) {
            switch (zone.state) {
                case ZONE_ACTIVE: active++; break;
                case ZONE_VIOLATED: violated++; break;
                case ZONE_TRADED: traded++; break;
                case ZONE_EXPIRED: expired++; break;
            }
        }
        debug("calcValues: " + zones.size() + " zones | "
            + active + " active, " + traded + " traded, " + violated + " violated, " + expired + " expired");
    }

    // ==================== CALCULATE (required by validator) ====================
    @Override
    protected void calculate(int index, DataContext ctx) { }

    // ==================== BAR CLOSE (Study-level — refresh display) ====================
    @Override
    public void onBarClose(DataContext ctx)
    {
        calculateValues(ctx);
    }

    // ==================== STRATEGY LIFECYCLE ====================

    @Override
    public void onActivate(OrderContext ctx)
    {
        debug("ICT IFVG Retest Strategy activated");
    }

    @Override
    public void onDeactivate(OrderContext ctx)
    {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position");
        }
        resetTradeState();
    }

    // ==================== SIGNAL HANDLER ====================

    @Override
    public void onSignal(OrderContext ctx, Object signal)
    {
        if (signal != Signals.IFVG_LONG && signal != Signals.IFVG_SHORT) return;

        int position = ctx.getPosition();
        if (position != 0) {
            debug("Already in position, ignoring signal");
            return;
        }

        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();
        var settings = getSettings();
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime);

        if (settings.getBoolean(EOD_ENABLED, true) &&
            barTimeInt >= settings.getInteger(EOD_TIME, 1640)) {
            debug("Past EOD, blocking entry");
            return;
        }

        int qty = settings.getInteger(CONTRACTS, 2);
        int stopBufferTicks = settings.getInteger(STOP_BUFFER_TICKS, 4);
        double stopBuffer = stopBufferTicks * tickSize;
        double stopMinPts = settings.getDouble(STOP_MIN_PTS, 2.0);
        double stopMaxPts = settings.getDouble(STOP_MAX_PTS, 40.0);
        double tp1Pts = settings.getDouble(TP1_POINTS, 20.0);

        isLongTrade = (signal == Signals.IFVG_LONG);

        // Find the zone that triggered this signal (most recently traded zone matching direction)
        IFVGZone triggerZone = null;
        for (IFVGZone zone : zones) {
            if (zone.traded && zone.isBullish == isLongTrade) {
                triggerZone = zone;
            }
        }

        if (isLongTrade) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();
            if (triggerZone != null) {
                stopPrice = instr.round(triggerZone.bottom - stopBuffer);
                triggerZoneBottom = triggerZone.bottom;
                triggerZoneTop = triggerZone.top;
            } else {
                stopPrice = instr.round(entryPrice - stopMaxPts);
                triggerZoneBottom = Double.NaN;
                triggerZoneTop = Double.NaN;
            }
            tp1Price = instr.round(entryPrice + tp1Pts);
            bestPriceInTrade = entryPrice;
        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();
            if (triggerZone != null) {
                stopPrice = instr.round(triggerZone.top + stopBuffer);
                triggerZoneBottom = triggerZone.bottom;
                triggerZoneTop = triggerZone.top;
            } else {
                stopPrice = instr.round(entryPrice + stopMaxPts);
                triggerZoneBottom = Double.NaN;
                triggerZoneTop = Double.NaN;
            }
            tp1Price = instr.round(entryPrice - tp1Pts);
            bestPriceInTrade = entryPrice;
        }

        // Clamp stop distance
        double dist = Math.abs(entryPrice - stopPrice);
        if (dist < stopMinPts) {
            stopPrice = isLongTrade
                ? instr.round(entryPrice - stopMinPts)
                : instr.round(entryPrice + stopMinPts);
        }
        if (dist > stopMaxPts) {
            stopPrice = isLongTrade
                ? instr.round(entryPrice - stopMaxPts)
                : instr.round(entryPrice + stopMaxPts);
        }

        tp1Filled = false;
        beActivated = false;
        trailingActive = false;
        trailStopPrice = Double.NaN;

        debug(String.format("=== %s ENTRY === qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f, zone=[%.2f-%.2f]",
            isLongTrade ? "LONG" : "SHORT", qty, entryPrice, stopPrice, tp1Price,
            triggerZone != null ? triggerZone.bottom : 0,
            triggerZone != null ? triggerZone.top : 0));
    }

    // ==================== BAR CLOSE (Strategy-level — trade management) ====================

    @Override
    public void onBarClose(OrderContext ctx)
    {
        calculateValues(ctx.getDataContext());

        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime);
        var instr = ctx.getInstrument();
        var settings = getSettings();
        int barDay = getDayOfYear(barTime);

        // EOD tracking reset
        if (barDay != lastResetDay) {
            eodProcessed = false;
            lastResetDay = barDay;
        }

        // EOD Flatten
        if (settings.getBoolean(EOD_ENABLED, true) &&
            barTimeInt >= settings.getInteger(EOD_TIME, 1640) && !eodProcessed) {
            int position = ctx.getPosition();
            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD forced flat at " + barTimeInt);
                resetTradeState();
            }
            eodProcessed = true;
            return;
        }

        // Position management
        int position = ctx.getPosition();
        if (position == 0) {
            if (entryPrice > 0) resetTradeState();
            return;
        }

        double high = series.getHigh(index);
        double low = series.getLow(index);
        boolean isLong = position > 0;

        // Track best price
        if (isLong) {
            if (Double.isNaN(bestPriceInTrade) || high > bestPriceInTrade) bestPriceInTrade = high;
        } else {
            if (Double.isNaN(bestPriceInTrade) || low < bestPriceInTrade) bestPriceInTrade = low;
        }

        // Effective stop
        double effectiveStop = stopPrice;
        if (!Double.isNaN(trailStopPrice) && trailingActive) {
            if (isLong) effectiveStop = Math.max(effectiveStop, trailStopPrice);
            else effectiveStop = Math.min(effectiveStop, trailStopPrice);
        }

        // Stop loss check
        if (isLong && low <= effectiveStop) {
            ctx.closeAtMarket();
            debug("LONG stopped at " + fmt(effectiveStop));
            resetTradeState();
            return;
        }
        if (!isLong && high >= effectiveStop) {
            ctx.closeAtMarket();
            debug("SHORT stopped at " + fmt(effectiveStop));
            resetTradeState();
            return;
        }

        // Move stop to breakeven
        if (!beActivated && settings.getBoolean(BE_ENABLED, true)) {
            double beTrigger = settings.getDouble(BE_TRIGGER_PTS, 10.0);
            double profitPts = isLong ? (bestPriceInTrade - entryPrice) : (entryPrice - bestPriceInTrade);
            if (profitPts >= beTrigger) {
                stopPrice = instr.round(entryPrice);
                beActivated = true;
                debug("Stop to BE at " + fmt(stopPrice) + " (profit reached " + fmt(profitPts) + " pts)");
            }
        }

        // TP1 Partial
        int tp1Pct = settings.getInteger(TP1_PCT, 50);
        if (!tp1Filled) {
            boolean tp1Hit = (isLong && high >= tp1Price) || (!isLong && low <= tp1Price);
            if (tp1Hit) {
                int absPos = Math.abs(position);
                int partialQty = (int) Math.ceil(absPos * tp1Pct / 100.0);
                if (partialQty > 0 && partialQty < absPos) {
                    if (isLong) ctx.sell(partialQty);
                    else ctx.buy(partialQty);
                    tp1Filled = true;
                    debug("TP1: " + partialQty + " contracts at " + fmt(tp1Price));
                } else {
                    ctx.closeAtMarket();
                    debug("Full exit at TP1");
                    resetTradeState();
                    return;
                }
            }
        }

        // Runner Trailing Stop
        if (tp1Filled && !trailingActive) {
            trailingActive = true;
            double trailDist = settings.getDouble(TRAIL_POINTS, 15.0);
            trailStopPrice = isLong
                ? instr.round(bestPriceInTrade - trailDist)
                : instr.round(bestPriceInTrade + trailDist);
        }
        if (trailingActive) {
            double trailDist = settings.getDouble(TRAIL_POINTS, 15.0);
            if (isLong) {
                double newTrail = instr.round(bestPriceInTrade - trailDist);
                if (Double.isNaN(trailStopPrice) || newTrail > trailStopPrice) trailStopPrice = newTrail;
            } else {
                double newTrail = instr.round(bestPriceInTrade + trailDist);
                if (Double.isNaN(trailStopPrice) || newTrail < trailStopPrice) trailStopPrice = newTrail;
            }
        }
    }

    // ==================== STATE RESET ====================

    private void resetTradeState()
    {
        entryPrice = 0;
        stopPrice = 0;
        tp1Price = 0;
        tp1Filled = false;
        beActivated = false;
        bestPriceInTrade = Double.NaN;
        trailStopPrice = Double.NaN;
        trailingActive = false;
        triggerZoneBottom = Double.NaN;
        triggerZoneTop = Double.NaN;
    }

    // ==================== UTILITY ====================

    private double safeDiv(double a, double b)
    {
        return b == 0 ? 0 : a / b;
    }

    private long getExtendedTime(DataSeries series, int barIndex)
    {
        int size = series.size();
        if (barIndex < size) return series.getStartTime(barIndex);
        if (size < 2) return series.getStartTime(size - 1);
        long interval = series.getStartTime(size - 1) - series.getStartTime(size - 2);
        return series.getStartTime(size - 1) + interval * (barIndex - size + 1);
    }

    private int getTimeInt(long time)
    {
        Calendar cal = Calendar.getInstance(NY_TZ);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);
    }

    private int getDayOfYear(long time)
    {
        Calendar cal = Calendar.getInstance(NY_TZ);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.DAY_OF_YEAR) + cal.get(Calendar.YEAR) * 1000;
    }

    private String fmt(double val)
    {
        return String.format("%.2f", val);
    }

    // ==================== CLEAR STATE ====================
    @Override
    public void clearState()
    {
        super.clearState();
        zones.clear();
        entryMarkers.clear();
        resetTradeState();
        lastResetDay = -1;
        eodProcessed = false;
    }
}
