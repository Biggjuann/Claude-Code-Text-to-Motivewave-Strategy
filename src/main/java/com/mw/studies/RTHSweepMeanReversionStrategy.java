package com.mw.studies;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

import java.util.Calendar;
import java.util.TimeZone;

/**
 * RTH Range Sweep Mean Reversion Strategy
 *
 * A sophisticated mean reversion strategy that trades failed breakouts (sweeps)
 * of a morning balance range. Converts the PineScript "RTH Range Sweep – Mean
 * Reversion v3.1" to MotiveWave.
 *
 * ============================================================
 * STRATEGY CONCEPT
 * ============================================================
 * 1. Build a balance range during the morning session (e.g., 9:30-11:30 CT)
 * 2. After the balance window closes, look for "sweeps" where price exceeds
 *    the range boundary but closes back inside (failed breakout)
 * 3. Enter mean reversion trade expecting price to return toward opposite side
 * 4. Use VWAP as confirmation filter (price should be on "wrong side")
 * 5. Partial profit at range midpoint, remainder at opposite boundary
 *
 * ============================================================
 * INPUTS
 * ============================================================
 * Sessions (Chicago Time):
 * - balanceStart (int): Balance window start time HHMM [default: 930]
 * - balanceEnd (int): Balance window end time HHMM [default: 1130]
 * - tradeStart (int): Trade window start time HHMM [default: 930]
 * - tradeEnd (int): Trade window end time HHMM [default: 1600]
 *
 * Range Requirements:
 * - minRangePts (double): Minimum range width in points [default: 6.0]
 * - maxRangePts (double): Maximum range width in points [default: 25.0]
 *
 * Sweep Detection:
 * - useLookbackSweep (bool): Use lookback window vs single bar [default: false]
 * - sweepLookback (int): Bars to look back for sweep [default: 12]
 *
 * VWAP Filters:
 * - useVWAPLocation (bool): Require price on wrong side of VWAP [default: true]
 * - useVWAPSlope (bool): Block trades when VWAP slopes against [default: false]
 * - vwapSlopeBars (int): Bars for slope calculation [default: 3]
 *
 * Risk Management:
 * - stopPts (double): Stop distance beyond range boundary [default: 5.0]
 * - partialPct (int): Percent to exit at midpoint [default: 50]
 * - maxTradesPerDay (int): Maximum entries per day [default: 2]
 *
 * ============================================================
 * ENTRY LOGIC
 * ============================================================
 * LONG Entry (Sweep Low):
 * - Balance range is complete and valid (within min/max bounds)
 * - Price swept below rthLow (low < rthLow)
 * - Price closed back inside range (close > rthLow && close < rthHigh)
 * - VWAP filter passed (close < vwap if enabled)
 * - Within trade window, under trade limit, long not used today
 *
 * SHORT Entry (Sweep High):
 * - Balance range is complete and valid
 * - Price swept above rthHigh (high > rthHigh)
 * - Price closed back inside range
 * - VWAP filter passed (close > vwap if enabled)
 * - Within trade window, under trade limit, short not used today
 *
 * ============================================================
 * EXIT LOGIC
 * ============================================================
 * Stop Loss:
 * - Long: rthLow - stopPts
 * - Short: rthHigh + stopPts
 *
 * Take Profit:
 * - Target 1 (partial): Range midpoint (partialPct% of position)
 * - Target 2 (remainder): Opposite range boundary
 *
 * @version 3.1.0
 * @author MW Study Builder (converted from PineScript)
 * @generated 2024-02-01
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "RTH_SWEEP_MEAN_REVERSION",
    rb = "com.mw.studies.nls.strings",
    name = "RTH Sweep Mean Reversion",
    label = "RTH Sweep MR",
    desc = "Mean reversion strategy trading sweeps of RTH balance range with VWAP filter",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true,
    signals = true,
    strategy = true,
    autoEntry = true,
    manualEntry = false,
    supportsUnrealizedPL = true,
    supportsRealizedPL = true,
    supportsTotalPL = true,
    supportsBarUpdates = false
)
public class RTHSweepMeanReversionStrategy extends Study {

    // ==================== Input Keys ====================
    // Sessions
    private static final String BALANCE_START = "balanceStart";
    private static final String BALANCE_END = "balanceEnd";
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";

    // Range Requirements
    private static final String MIN_RANGE_PTS = "minRangePts";
    private static final String MAX_RANGE_PTS = "maxRangePts";

    // Sweep Rules
    private static final String USE_LOOKBACK_SWEEP = "useLookbackSweep";
    private static final String SWEEP_LOOKBACK = "sweepLookback";

    // VWAP Filters
    private static final String USE_VWAP_LOCATION = "useVWAPLocation";
    private static final String USE_VWAP_SLOPE = "useVWAPSlope";
    private static final String VWAP_SLOPE_BARS = "vwapSlopeBars";

    // Risk
    private static final String STOP_PTS = "stopPts";
    private static final String PARTIAL_PCT = "partialPct";
    private static final String MAX_TRADES = "maxTradesPerDay";

    // Path Keys
    private static final String RTH_HIGH_PATH = "rthHighPath";
    private static final String RTH_LOW_PATH = "rthLowPath";
    private static final String MID_PATH = "midPath";
    private static final String VWAP_PATH = "vwapPath";

    // ==================== Values ====================
    enum Values {
        RTH_HIGH,        // Balance range high
        RTH_LOW,         // Balance range low
        RANGE_MID,       // Range midpoint
        VWAP,            // Session VWAP
        IN_BALANCE,      // Boolean: in balance window
        IN_TRADE,        // Boolean: in trade window
        BALANCE_COMPLETE,// Boolean: balance range finalized
        VALID_RANGE      // Boolean: range is valid for trading
    }

    // ==================== Signals ====================
    enum Signals {
        LONG_SWEEP,      // Sweep low - long entry
        SHORT_SWEEP      // Sweep high - short entry
    }

    // ==================== State Variables ====================
    // Daily reset variables
    private double rthHigh = Double.NaN;
    private double rthLow = Double.NaN;
    private boolean balanceComplete = false;
    private int tradesToday = 0;
    private boolean longUsed = false;
    private boolean shortUsed = false;
    private int lastResetDay = -1;

    // VWAP calculation state
    private double vwapCumVolume = 0;
    private double vwapCumPV = 0;
    private int vwapResetDay = -1;

    // Position tracking
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double target1Price = 0;
    private double target2Price = 0;
    private boolean isLong = false;
    private boolean partialTaken = false;

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {
        var sd = createSD();

        // ===== Sessions Tab =====
        var tab = sd.addTab("Sessions");
        var grp = tab.addGroup("Balance Window (builds range)");
        grp.addRow(new IntegerDescriptor(BALANCE_START, "Start Time (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(BALANCE_END, "End Time (HHMM)", 1130, 0, 2359, 1));

        grp = tab.addGroup("Trade Window (entries allowed)");
        grp.addRow(new IntegerDescriptor(TRADE_START, "Start Time (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(TRADE_END, "End Time (HHMM)", 1600, 0, 2359, 1));

        // ===== Range Tab =====
        tab = sd.addTab("Range");
        grp = tab.addGroup("Range Requirements");
        grp.addRow(new DoubleDescriptor(MIN_RANGE_PTS, "Min Range (pts)", 6.0, 0.25, 100.0, 0.25));
        grp.addRow(new DoubleDescriptor(MAX_RANGE_PTS, "Max Range (pts)", 25.0, 0.25, 200.0, 0.25));

        grp = tab.addGroup("Sweep Detection");
        grp.addRow(new BooleanDescriptor(USE_LOOKBACK_SWEEP, "Use Lookback Sweep", false));
        grp.addRow(new IntegerDescriptor(SWEEP_LOOKBACK, "Lookback Bars", 12, 1, 50, 1));

        // ===== VWAP Tab =====
        tab = sd.addTab("VWAP Filter");
        grp = tab.addGroup("VWAP Location Filter");
        grp.addRow(new BooleanDescriptor(USE_VWAP_LOCATION, "Require wrong side of VWAP", true));

        grp = tab.addGroup("VWAP Slope Filter (stricter)");
        grp.addRow(new BooleanDescriptor(USE_VWAP_SLOPE, "Block when VWAP against fade", false));
        grp.addRow(new IntegerDescriptor(VWAP_SLOPE_BARS, "Slope Bars", 3, 1, 20, 1));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Stop Loss");
        grp.addRow(new DoubleDescriptor(STOP_PTS, "Stop Distance (pts)", 5.0, 0.25, 50.0, 0.25));

        grp = tab.addGroup("Profit Taking");
        grp.addRow(new IntegerDescriptor(PARTIAL_PCT, "Partial % at Midpoint", 50, 1, 99, 1));

        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES, "Max Trades/Day", 2, 1, 10, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Range Lines");
        grp.addRow(new PathDescriptor(RTH_HIGH_PATH, "RTH High",
            defaults.getRed(), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(RTH_LOW_PATH, "RTH Low",
            defaults.getGreen(), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(MID_PATH, "Range Mid",
            defaults.getYellow(), 1.0f, new float[]{4, 4}, true, true, true));

        grp = tab.addGroup("VWAP");
        grp.addRow(new PathDescriptor(VWAP_PATH, "VWAP",
            defaults.getBlue(), 1.5f, null, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(BALANCE_START, BALANCE_END, MIN_RANGE_PTS, MAX_RANGE_PTS);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(BALANCE_START, BALANCE_END, MIN_RANGE_PTS, MAX_RANGE_PTS);

        desc.exportValue(new ValueDescriptor(Values.RTH_HIGH, "RTH High", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.RTH_LOW, "RTH Low", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_MID, "Range Mid", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.VWAP, "VWAP", new String[]{}));

        desc.declarePath(Values.RTH_HIGH, RTH_HIGH_PATH);
        desc.declarePath(Values.RTH_LOW, RTH_LOW_PATH);
        desc.declarePath(Values.RANGE_MID, MID_PATH);
        desc.declarePath(Values.VWAP, VWAP_PATH);

        desc.declareSignal(Signals.LONG_SWEEP, "Long Sweep Entry");
        desc.declareSignal(Signals.SHORT_SWEEP, "Short Sweep Entry");

        desc.setRangeKeys(Values.RTH_HIGH, Values.RTH_LOW);
    }

    @Override
    public int getMinBars() {
        return getSettings().getInteger(SWEEP_LOOKBACK, 12) + 10;
    }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx) {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();

        // Get bar time
        long barTime = series.getStartTime(index);
        TimeZone tz = TimeZone.getTimeZone("America/Chicago"); // CME timezone
        int barTimeInt = getTimeInt(barTime, tz);
        int barDay = getDayOfYear(barTime, tz);

        // Daily reset
        if (barDay != lastResetDay) {
            resetDailyState();
            lastResetDay = barDay;
        }

        // Reset VWAP on new day
        if (barDay != vwapResetDay) {
            vwapCumVolume = 0;
            vwapCumPV = 0;
            vwapResetDay = barDay;
        }

        // Get settings
        int balanceStart = getSettings().getInteger(BALANCE_START, 930);
        int balanceEnd = getSettings().getInteger(BALANCE_END, 1130);
        int tradeStart = getSettings().getInteger(TRADE_START, 930);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1600);
        double minRangePts = getSettings().getDouble(MIN_RANGE_PTS, 6.0);
        double maxRangePts = getSettings().getDouble(MAX_RANGE_PTS, 25.0);

        // Session flags
        boolean inBalance = barTimeInt >= balanceStart && barTimeInt < balanceEnd;
        boolean inTrade = barTimeInt >= tradeStart && barTimeInt <= tradeEnd;

        series.setBoolean(index, Values.IN_BALANCE, inBalance);
        series.setBoolean(index, Values.IN_TRADE, inTrade);

        // OHLCV
        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        double hlc3 = (high + low + close) / 3.0;
        double volume = series.getVolume(index);

        // Calculate VWAP
        if (volume > 0) {
            vwapCumVolume += volume;
            vwapCumPV += hlc3 * volume;
        }
        double vwap = vwapCumVolume > 0 ? vwapCumPV / vwapCumVolume : hlc3;
        series.setDouble(index, Values.VWAP, vwap);

        // Build balance range
        if (inBalance) {
            if (Double.isNaN(rthHigh) || high > rthHigh) rthHigh = high;
            if (Double.isNaN(rthLow) || low < rthLow) rthLow = low;
        }

        // Check if balance just ended
        if (index > 0) {
            Boolean wasInBalance = series.getBoolean(index - 1, Values.IN_BALANCE);
            if (wasInBalance != null && wasInBalance && !inBalance) {
                if (!Double.isNaN(rthHigh) && !Double.isNaN(rthLow)) {
                    balanceComplete = true;
                }
            }
        }

        series.setBoolean(index, Values.BALANCE_COMPLETE, balanceComplete);

        // Plot range lines only after balance is complete
        if (balanceComplete) {
            series.setDouble(index, Values.RTH_HIGH, rthHigh);
            series.setDouble(index, Values.RTH_LOW, rthLow);
            double rangeMid = (rthHigh + rthLow) / 2.0;
            series.setDouble(index, Values.RANGE_MID, rangeMid);
        }

        // Validate range
        double rangeWidth = rthHigh - rthLow;
        boolean validRange = balanceComplete && rangeWidth >= minRangePts && rangeWidth <= maxRangePts;
        series.setBoolean(index, Values.VALID_RANGE, validRange);

        // Only process signals on complete bars
        if (!series.isBarComplete(index)) return;
        if (!validRange || !inTrade) return;

        // Check for sweep conditions
        boolean useLookback = getSettings().getBoolean(USE_LOOKBACK_SWEEP, false);
        int lookback = getSettings().getInteger(SWEEP_LOOKBACK, 12);

        boolean closeBackInside = close > rthLow && close < rthHigh;

        boolean longSweep;
        boolean shortSweep;

        if (useLookback) {
            // Lookback sweep: any bar in lookback swept, current close back inside
            double lowestRecent = getLowest(series, index, lookback);
            double highestRecent = getHighest(series, index, lookback);
            longSweep = lowestRecent < rthLow && closeBackInside;
            shortSweep = highestRecent > rthHigh && closeBackInside;
        } else {
            // Single bar sweep: this bar swept and closed back inside
            longSweep = low < rthLow && closeBackInside;
            shortSweep = high > rthHigh && closeBackInside;
        }

        // VWAP filters
        boolean useVWAPLoc = getSettings().getBoolean(USE_VWAP_LOCATION, true);
        boolean useVWAPSlope = getSettings().getBoolean(USE_VWAP_SLOPE, false);
        int vwapSlopeBars = getSettings().getInteger(VWAP_SLOPE_BARS, 3);

        Double vwapPrev = index >= vwapSlopeBars ? series.getDouble(index - vwapSlopeBars, Values.VWAP) : null;
        boolean vwapSlopeUp = vwapPrev != null && vwap > vwapPrev;
        boolean vwapSlopeDown = vwapPrev != null && vwap < vwapPrev;

        // Long VWAP OK: close below VWAP (optional) AND VWAP not strongly rising (optional)
        boolean longVWAPOk = (!useVWAPLoc || close < vwap) && (!useVWAPSlope || !vwapSlopeUp);

        // Short VWAP OK: close above VWAP (optional) AND VWAP not strongly falling (optional)
        boolean shortVWAPOk = (!useVWAPLoc || close > vwap) && (!useVWAPSlope || !vwapSlopeDown);

        // Entry conditions
        int maxTrades = getSettings().getInteger(MAX_TRADES, 2);
        boolean canTrade = tradesToday < maxTrades;

        boolean enterLong = canTrade && !longUsed && longSweep && longVWAPOk;
        boolean enterShort = canTrade && !shortUsed && shortSweep && shortVWAPOk;

        // Generate signals
        if (enterLong) {
            series.setBoolean(index, Signals.LONG_SWEEP, true);
            ctx.signal(index, Signals.LONG_SWEEP,
                String.format("Long sweep: Low=%.2f < RTH Low=%.2f, Close=%.2f back inside", low, rthLow, close),
                close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, low);
                addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "LONG"));
            }
        }

        if (enterShort) {
            series.setBoolean(index, Signals.SHORT_SWEEP, true);
            ctx.signal(index, Signals.SHORT_SWEEP,
                String.format("Short sweep: High=%.2f > RTH High=%.2f, Close=%.2f back inside", high, rthHigh, close),
                close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, high);
                addFigure(new Marker(coord, Enums.Position.TOP, marker, "SHORT"));
            }
        }

        series.setComplete(index);
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("RTH Sweep Mean Reversion Strategy activated");
        partialTaken = false;
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position");
        }
        resetDailyState();
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        int qty = getSettings().getTradeLots() * instr.getDefaultQuantity();
        double tickSize = instr.getTickSize();
        double stopPts = getSettings().getDouble(STOP_PTS, 5.0);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);

        if (position != 0) {
            debug("Already in position, ignoring signal");
            return;
        }

        if (signal == Signals.LONG_SWEEP) {
            // Enter long
            ctx.buy(qty);
            longUsed = true;
            tradesToday++;
            isLong = true;
            partialTaken = false;

            entryPrice = instr.getLastPrice();
            stopPrice = instr.round(rthLow - stopPts);
            target1Price = (rthHigh + rthLow) / 2.0; // Range mid
            target2Price = rthHigh; // Opposite boundary

            debug(String.format("LONG entry: qty=%d, entry=%.2f, stop=%.2f, T1=%.2f, T2=%.2f",
                qty, entryPrice, stopPrice, target1Price, target2Price));
        }
        else if (signal == Signals.SHORT_SWEEP) {
            // Enter short
            ctx.sell(qty);
            shortUsed = true;
            tradesToday++;
            isLong = false;
            partialTaken = false;

            entryPrice = instr.getLastPrice();
            stopPrice = instr.round(rthHigh + stopPts);
            target1Price = (rthHigh + rthLow) / 2.0; // Range mid
            target2Price = rthLow; // Opposite boundary

            debug(String.format("SHORT entry: qty=%d, entry=%.2f, stop=%.2f, T1=%.2f, T2=%.2f",
                qty, entryPrice, stopPrice, target1Price, target2Price));
        }
    }

    /**
     * Called on each bar to manage open positions (stops/targets).
     * Note: MotiveWave strategies typically use bracket orders or
     * manual exit logic in onBarClose or similar methods.
     */
    @Override
    public void onBarClose(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position == 0) return;

        var instr = ctx.getInstrument();
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        double close = series.getClose(index);
        double high = series.getHigh(index);
        double low = series.getLow(index);
        int partialPct = getSettings().getInteger(PARTIAL_PCT, 50);

        if (isLong && position > 0) {
            // Check stop
            if (low <= stopPrice) {
                ctx.closeAtMarket();
                debug("LONG stopped out at " + low);
                return;
            }

            // Check target 1 (partial)
            if (!partialTaken && high >= target1Price) {
                int partialQty = (int) Math.ceil(position * partialPct / 100.0);
                if (partialQty > 0 && partialQty < position) {
                    ctx.sell(partialQty);
                    partialTaken = true;
                    debug("LONG partial exit: " + partialQty + " at " + target1Price);
                }
            }

            // Check target 2 (full)
            if (high >= target2Price) {
                ctx.closeAtMarket();
                debug("LONG target 2 hit at " + high);
            }
        }
        else if (!isLong && position < 0) {
            // Check stop
            if (high >= stopPrice) {
                ctx.closeAtMarket();
                debug("SHORT stopped out at " + high);
                return;
            }

            // Check target 1 (partial)
            if (!partialTaken && low <= target1Price) {
                int partialQty = (int) Math.ceil(Math.abs(position) * partialPct / 100.0);
                if (partialQty > 0 && partialQty < Math.abs(position)) {
                    ctx.buy(partialQty);
                    partialTaken = true;
                    debug("SHORT partial exit: " + partialQty + " at " + target1Price);
                }
            }

            // Check target 2 (full)
            if (low <= target2Price) {
                ctx.closeAtMarket();
                debug("SHORT target 2 hit at " + low);
            }
        }
    }

    // ==================== Helper Methods ====================

    private void resetDailyState() {
        rthHigh = Double.NaN;
        rthLow = Double.NaN;
        balanceComplete = false;
        tradesToday = 0;
        longUsed = false;
        shortUsed = false;
        partialTaken = false;
    }

    private int getTimeInt(long time, TimeZone tz) {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.HOUR_OF_DAY) * 100 + cal.get(Calendar.MINUTE);
    }

    private int getDayOfYear(long time, TimeZone tz) {
        Calendar cal = Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(Calendar.DAY_OF_YEAR) + cal.get(Calendar.YEAR) * 1000;
    }

    private double getLowest(DataSeries series, int index, int period) {
        double lowest = Double.MAX_VALUE;
        for (int i = Math.max(0, index - period + 1); i <= index; i++) {
            double low = series.getLow(i);
            if (low < lowest) lowest = low;
        }
        return lowest;
    }

    private double getHighest(DataSeries series, int index, int period) {
        double highest = Double.MIN_VALUE;
        for (int i = Math.max(0, index - period + 1); i <= index; i++) {
            double high = series.getHigh(i);
            if (high > highest) highest = high;
        }
        return highest;
    }

    @Override
    public void clearState() {
        super.clearState();
        resetDailyState();
        lastResetDay = -1;
        vwapResetDay = -1;
        vwapCumVolume = 0;
        vwapCumPV = 0;
    }
}
