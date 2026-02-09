package com.mw.studies;

import java.util.Calendar;
import java.util.TimeZone;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * Time Range Breakout Strategy (TP1 + Runner Trail + BE + EOD Flat)
 *
 * Trades breakouts above/below a defined time-range high/low with structured
 * risk management: initial stop, move-to-breakeven, partial TP1, and runner
 * management with trailing stop.
 *
 * RANGE BUILDING:
 * - Tracks high/low during a configurable time window (default 9:30-10:00 ET)
 * - Range validated against min/max size constraints
 *
 * ENTRY:
 * - Long: price breaks above range high + offset
 * - Short: price breaks below range low - offset
 * - Two modes: TOUCH_THROUGH (wick) or CLOSE_THROUGH (bar close)
 *
 * RISK MANAGEMENT:
 * - Initial stop: fixed points OR other side of range + buffer
 * - Move to breakeven after configurable profit threshold
 * - TP1: partial exit at fixed points distance
 * - Runner: remaining contracts with trailing stop (fixed points or ATR)
 * - EOD forced flatten
 *
 * @version 1.0.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "TIME_RANGE_BREAKOUT",
    rb = "com.mw.studies.nls.strings",
    name = "TIME_RANGE_BREAKOUT",
    label = "LBL_TIME_RANGE_BREAKOUT",
    desc = "DESC_TIME_RANGE_BREAKOUT",
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
public class TimeRangeBreakoutStrategy extends Study
{
    // ==================== Input Keys ====================

    // Range
    private static final String RANGE_START = "rangeStart";
    private static final String RANGE_END = "rangeEnd";
    private static final String TRADE_START = "tradeStart";
    private static final String TRADE_END = "tradeEnd";
    private static final String RANGE_MIN_PTS = "rangeMinPts";
    private static final String RANGE_MAX_PTS = "rangeMaxPts";

    // Entry
    private static final String BREAKOUT_MODE = "breakoutMode";
    private static final String ENTRY_OFFSET_TICKS = "entryOffsetTicks";

    // Limits
    private static final String MAX_TRADES_DAY = "maxTradesDay";
    private static final String ONE_AT_A_TIME = "oneAtATime";

    // Risk
    private static final String CONTRACTS = "contracts";
    private static final String STOP_MODE = "stopMode";
    private static final String STOP_POINTS = "stopPoints";
    private static final String STOP_BUFFER_TICKS = "stopBufferTicks";

    // Breakeven
    private static final String BE_ENABLED = "beEnabled";
    private static final String BE_TRIGGER_PTS = "beTriggerPts";
    private static final String BE_PLUS_TICKS = "bePlusTicks";

    // Exits / TP1
    private static final String TP1_POINTS = "tp1Points";
    private static final String TP1_PCT = "tp1Pct";

    // Runner
    private static final String RUNNER_TRAIL_MODE = "runnerTrailMode";
    private static final String RUNNER_TRAIL_PTS = "runnerTrailPts";
    private static final String RUNNER_ATR_LEN = "runnerAtrLen";
    private static final String RUNNER_ATR_MULT = "runnerAtrMult";
    private static final String RUNNER_TRAIL_AFTER_TP1 = "runnerTrailAfterTp1";

    // EOD
    private static final String EOD_ENABLED = "eodEnabled";
    private static final String EOD_TIME = "eodTime";

    // Display
    private static final String RANGE_HIGH_PATH = "rangeHighPath";
    private static final String RANGE_LOW_PATH = "rangeLowPath";

    // ==================== Constants ====================

    // Breakout modes
    private static final int MODE_TOUCH = 0;
    private static final int MODE_CLOSE = 1;

    // Stop modes
    private static final int STOP_FIXED = 0;
    private static final int STOP_OTHER_SIDE = 1;

    // Runner trail modes
    private static final int TRAIL_POINTS = 0;
    private static final int TRAIL_ATR = 1;

    // ==================== Values ====================
    enum Values { RANGE_HIGH, RANGE_LOW, ATR }

    // ==================== Signals ====================
    enum Signals { LONG_BREAKOUT, SHORT_BREAKDOWN }

    // ==================== State Variables ====================

    // Range
    private double rangeHigh = Double.NaN;
    private double rangeLow = Double.NaN;
    private boolean rangeComplete = false;
    private boolean wasInRangeWindow = false;

    // Trade tracking
    private int tradesToday = 0;
    private boolean isLongTrade = false;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double tp1Price = 0;
    private boolean tp1Filled = false;
    private boolean beActivated = false;
    private double trailStopPrice = Double.NaN;
    private boolean trailingActive = false;
    private double bestPriceInTrade = Double.NaN;

    // Daily reset
    private int lastResetDay = -1;
    private boolean eodProcessed = false;

    // NY timezone
    private static final TimeZone NY_TZ = TimeZone.getTimeZone("America/New_York");

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults)
    {
        var sd = createSD();

        // ===== Range Tab =====
        var tab = sd.addTab("Range");
        var grp = tab.addGroup("Range Build Window (ET)");
        grp.addRow(new IntegerDescriptor(RANGE_START, "Range Start (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(RANGE_END, "Range End (HHMM)", 1000, 0, 2359, 1));

        grp = tab.addGroup("Trade Window (ET)");
        grp.addRow(new IntegerDescriptor(TRADE_START, "Trade Start (HHMM)", 930, 0, 2359, 1));
        grp.addRow(new IntegerDescriptor(TRADE_END, "Trade End (HHMM)", 1600, 0, 2359, 1));

        grp = tab.addGroup("Range Size Filter");
        grp.addRow(new DoubleDescriptor(RANGE_MIN_PTS, "Min Range (points)", 2.0, 0.0, 50.0, 0.25));
        grp.addRow(new DoubleDescriptor(RANGE_MAX_PTS, "Max Range (points)", 50.0, 0.25, 200.0, 0.25));

        // ===== Entry Tab =====
        tab = sd.addTab("Entry");
        grp = tab.addGroup("Breakout Trigger");
        grp.addRow(new IntegerDescriptor(BREAKOUT_MODE, "Mode (0=Touch Through, 1=Close Through)", MODE_CLOSE, 0, 1, 1));
        grp.addRow(new IntegerDescriptor(ENTRY_OFFSET_TICKS, "Entry Offset (ticks)", 1, 0, 20, 1));

        // ===== Limits Tab =====
        tab = sd.addTab("Limits");
        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES_DAY, "Max Trades Per Day", 2, 1, 10, 1));
        grp.addRow(new BooleanDescriptor(ONE_AT_A_TIME, "One Trade at a Time", true));

        // ===== Risk Tab =====
        tab = sd.addTab("Risk");
        grp = tab.addGroup("Position Size");
        grp.addRow(new IntegerDescriptor(CONTRACTS, "Contracts", 2, 1, 100, 1));

        grp = tab.addGroup("Initial Stop");
        grp.addRow(new IntegerDescriptor(STOP_MODE, "Stop Mode (0=Fixed Pts, 1=Other Side of Range)", STOP_OTHER_SIDE, 0, 1, 1));
        grp.addRow(new DoubleDescriptor(STOP_POINTS, "Fixed Stop (points)", 5.0, 0.25, 50.0, 0.25));
        grp.addRow(new IntegerDescriptor(STOP_BUFFER_TICKS, "Range Stop Buffer (ticks)", 2, 0, 20, 1));

        grp = tab.addGroup("Breakeven");
        grp.addRow(new BooleanDescriptor(BE_ENABLED, "Move Stop to Breakeven", true));
        grp.addRow(new DoubleDescriptor(BE_TRIGGER_PTS, "BE Trigger (points profit)", 3.0, 0.25, 50.0, 0.25));
        grp.addRow(new IntegerDescriptor(BE_PLUS_TICKS, "BE Plus (ticks)", 0, 0, 20, 1));

        // ===== Exits Tab =====
        tab = sd.addTab("Exits");
        grp = tab.addGroup("TP1 (Partial)");
        grp.addRow(new DoubleDescriptor(TP1_POINTS, "TP1 Distance (points)", 6.0, 0.25, 100.0, 0.25));
        grp.addRow(new IntegerDescriptor(TP1_PCT, "TP1 % of Contracts", 50, 1, 99, 1));

        grp = tab.addGroup("Runner Trailing Stop");
        grp.addRow(new IntegerDescriptor(RUNNER_TRAIL_MODE, "Trail Mode (0=Points, 1=ATR)", TRAIL_POINTS, 0, 1, 1));
        grp.addRow(new DoubleDescriptor(RUNNER_TRAIL_PTS, "Trail Distance (points)", 4.0, 0.25, 50.0, 0.25));
        grp.addRow(new IntegerDescriptor(RUNNER_ATR_LEN, "ATR Period", 14, 1, 100, 1));
        grp.addRow(new DoubleDescriptor(RUNNER_ATR_MULT, "ATR Multiplier", 2.0, 0.25, 10.0, 0.25));
        grp.addRow(new BooleanDescriptor(RUNNER_TRAIL_AFTER_TP1, "Start Trail After TP1", true));

        // ===== EOD Tab =====
        tab = sd.addTab("EOD");
        grp = tab.addGroup("End of Day");
        grp.addRow(new BooleanDescriptor(EOD_ENABLED, "Force Flat at EOD", true));
        grp.addRow(new IntegerDescriptor(EOD_TIME, "EOD Time (HHMM)", 1640, 0, 2359, 1));

        // ===== Display Tab =====
        tab = sd.addTab("Display");
        grp = tab.addGroup("Range Lines");
        grp.addRow(new PathDescriptor(RANGE_HIGH_PATH, "Range High",
            defaults.getGreen(), 2.0f, new float[]{6, 3}, true, true, true));
        grp.addRow(new PathDescriptor(RANGE_LOW_PATH, "Range Low",
            defaults.getRed(), 2.0f, new float[]{6, 3}, true, true, true));

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Long Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Short Entry",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(CONTRACTS, TP1_POINTS, STOP_MODE, MAX_TRADES_DAY);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(CONTRACTS, TP1_POINTS);

        desc.exportValue(new ValueDescriptor(Values.RANGE_HIGH, "Range High", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.RANGE_LOW, "Range Low", new String[]{}));
        desc.exportValue(new ValueDescriptor(Values.ATR, "ATR", new String[]{RUNNER_ATR_LEN}));

        desc.declarePath(Values.RANGE_HIGH, RANGE_HIGH_PATH);
        desc.declarePath(Values.RANGE_LOW, RANGE_LOW_PATH);

        desc.declareSignal(Signals.LONG_BREAKOUT, "Long Breakout");
        desc.declareSignal(Signals.SHORT_BREAKDOWN, "Short Breakdown");

        desc.setRangeKeys(Values.RANGE_HIGH, Values.RANGE_LOW);
    }

    @Override
    public int getMinBars() { return 50; }

    // ==================== Main Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx)
    {
        var series = ctx.getDataSeries();
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();

        if (index < 10) return;

        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        int barDay = getDayOfYear(barTime, NY_TZ);

        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);

        // ===== Daily Reset =====
        if (barDay != lastResetDay) {
            rangeHigh = Double.NaN;
            rangeLow = Double.NaN;
            rangeComplete = false;
            wasInRangeWindow = false;
            tradesToday = 0;
            eodProcessed = false;
            lastResetDay = barDay;
        }

        // ===== Settings =====
        int rangeStart = getSettings().getInteger(RANGE_START, 930);
        int rangeEnd = getSettings().getInteger(RANGE_END, 1000);
        int tradeStart = getSettings().getInteger(TRADE_START, 930);
        int tradeEnd = getSettings().getInteger(TRADE_END, 1600);
        int atrLen = getSettings().getInteger(RUNNER_ATR_LEN, 14);

        // ===== Range Building =====
        boolean inRangeWindow = barTimeInt >= rangeStart && barTimeInt < rangeEnd;

        if (inRangeWindow) {
            if (Double.isNaN(rangeHigh) || high > rangeHigh) rangeHigh = high;
            if (Double.isNaN(rangeLow) || low < rangeLow) rangeLow = low;
            wasInRangeWindow = true;
        }

        // Range completion: first bar after range window ends
        if (wasInRangeWindow && !inRangeWindow && !rangeComplete) {
            if (!Double.isNaN(rangeHigh) && !Double.isNaN(rangeLow)) {
                double rangeWidth = rangeHigh - rangeLow;
                double minPts = getSettings().getDouble(RANGE_MIN_PTS, 2.0);
                double maxPts = getSettings().getDouble(RANGE_MAX_PTS, 50.0);

                if (rangeWidth >= minPts && rangeWidth <= maxPts) {
                    rangeComplete = true;
                    debug(String.format("Range complete: High=%.2f, Low=%.2f, Width=%.2f",
                        rangeHigh, rangeLow, rangeWidth));
                } else {
                    debug(String.format("Range invalid: Width=%.2f (min=%.2f, max=%.2f)",
                        rangeWidth, minPts, maxPts));
                }
            }
        }

        // ===== Plot Range =====
        if (rangeComplete) {
            series.setDouble(index, Values.RANGE_HIGH, rangeHigh);
            series.setDouble(index, Values.RANGE_LOW, rangeLow);
        }

        // ===== ATR =====
        Double atr = series.atr(index, atrLen);
        if (atr != null) series.setDouble(index, Values.ATR, atr);

        // Only process entries on complete bars
        if (!series.isBarComplete(index)) return;

        // ===== EOD Check =====
        boolean eodEnabled = getSettings().getBoolean(EOD_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_TIME, 1640);
        boolean pastEod = eodEnabled && barTimeInt >= eodTime;

        // ===== Entry Logic =====
        if (!rangeComplete || pastEod) return;

        boolean inTradeWindow = barTimeInt >= tradeStart && barTimeInt < tradeEnd;
        int maxTrades = getSettings().getInteger(MAX_TRADES_DAY, 2);
        boolean oneAtATime = getSettings().getBoolean(ONE_AT_A_TIME, true);
        int breakoutMode = getSettings().getInteger(BREAKOUT_MODE, MODE_CLOSE);
        int offsetTicks = getSettings().getInteger(ENTRY_OFFSET_TICKS, 1);
        double offset = offsetTicks * tickSize;

        boolean canTrade = inTradeWindow && tradesToday < maxTrades;

        if (!canTrade) return;

        double longTrigger = rangeHigh + offset;
        double shortTrigger = rangeLow - offset;

        // Long breakout
        boolean longSignal;
        if (breakoutMode == MODE_TOUCH) {
            longSignal = high >= longTrigger;
        } else {
            longSignal = close >= longTrigger;
        }

        if (longSignal) {
            ctx.signal(index, Signals.LONG_BREAKOUT, "Long Breakout", close);

            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, low), Enums.Position.BOTTOM, marker, "BRK L"));
            }
        }

        // Short breakdown
        boolean shortSignal;
        if (breakoutMode == MODE_TOUCH) {
            shortSignal = low <= shortTrigger;
        } else {
            shortSignal = close <= shortTrigger;
        }

        if (shortSignal) {
            ctx.signal(index, Signals.SHORT_BREAKDOWN, "Short Breakdown", close);

            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                addFigure(new Marker(new Coordinate(barTime, high), Enums.Position.TOP, marker, "BRK S"));
            }
        }

        series.setComplete(index);
    }

    // ==================== Strategy Lifecycle ====================

    @Override
    public void onActivate(OrderContext ctx) {
        debug("Time Range Breakout Strategy activated");
    }

    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Strategy deactivated - closed position");
        }
        resetTradeState();
    }

    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        if (signal != Signals.LONG_BREAKOUT && signal != Signals.SHORT_BREAKDOWN) return;

        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();
        int position = ctx.getPosition();
        boolean oneAtATime = getSettings().getBoolean(ONE_AT_A_TIME, true);

        // Check one-at-a-time
        if (oneAtATime && position != 0) {
            debug("Already in position, ignoring breakout");
            return;
        }

        // EOD gate
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);

        if (getSettings().getBoolean(EOD_ENABLED, true) &&
            barTimeInt >= getSettings().getInteger(EOD_TIME, 1640)) {
            debug("Past EOD time, blocking entry");
            return;
        }

        int qty = getSettings().getInteger(CONTRACTS, 2);
        int stopMode = getSettings().getInteger(STOP_MODE, STOP_OTHER_SIDE);
        double stopPts = getSettings().getDouble(STOP_POINTS, 5.0);
        int stopBufferTicks = getSettings().getInteger(STOP_BUFFER_TICKS, 2);
        double stopBuffer = stopBufferTicks * tickSize;
        double tp1Pts = getSettings().getDouble(TP1_POINTS, 6.0);

        isLongTrade = (signal == Signals.LONG_BREAKOUT);

        // Close any existing position
        if (position != 0) {
            ctx.closeAtMarket();
        }

        if (isLongTrade) {
            ctx.buy(qty);
            entryPrice = instr.getLastPrice();

            // Calculate stop
            if (stopMode == STOP_FIXED) {
                stopPrice = instr.round(entryPrice - stopPts);
            } else {
                stopPrice = instr.round(rangeLow - stopBuffer);
            }

            tp1Price = instr.round(entryPrice + tp1Pts);
            bestPriceInTrade = entryPrice;

            debug(String.format("LONG: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f",
                qty, entryPrice, stopPrice, tp1Price));

        } else {
            ctx.sell(qty);
            entryPrice = instr.getLastPrice();

            if (stopMode == STOP_FIXED) {
                stopPrice = instr.round(entryPrice + stopPts);
            } else {
                stopPrice = instr.round(rangeHigh + stopBuffer);
            }

            tp1Price = instr.round(entryPrice - tp1Pts);
            bestPriceInTrade = entryPrice;

            debug(String.format("SHORT: qty=%d, entry=%.2f, stop=%.2f, TP1=%.2f",
                qty, entryPrice, stopPrice, tp1Price));
        }

        tp1Filled = false;
        beActivated = false;
        trailingActive = false;
        trailStopPrice = Double.NaN;
        tradesToday++;
    }

    @Override
    public void onBarClose(OrderContext ctx)
    {
        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        long barTime = series.getStartTime(index);
        int barTimeInt = getTimeInt(barTime, NY_TZ);
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();

        // ===== EOD Flatten (Highest Priority) =====
        boolean eodEnabled = getSettings().getBoolean(EOD_ENABLED, true);
        int eodTime = getSettings().getInteger(EOD_TIME, 1640);

        if (eodEnabled && barTimeInt >= eodTime && !eodProcessed) {
            int position = ctx.getPosition();
            if (position != 0) {
                ctx.closeAtMarket();
                debug("EOD forced flat at " + barTimeInt);
                resetTradeState();
            }
            eodProcessed = true;
            return;
        }

        // ===== Position Management =====
        int position = ctx.getPosition();
        if (position == 0) {
            if (entryPrice > 0) resetTradeState();
            return;
        }

        double high = series.getHigh(index);
        double low = series.getLow(index);
        double close = series.getClose(index);
        boolean isLong = position > 0;

        // Track best price in trade
        if (isLong) {
            if (Double.isNaN(bestPriceInTrade) || high > bestPriceInTrade)
                bestPriceInTrade = high;
        } else {
            if (Double.isNaN(bestPriceInTrade) || low < bestPriceInTrade)
                bestPriceInTrade = low;
        }

        // ===== Determine effective stop =====
        double effectiveStop = stopPrice;
        if (!Double.isNaN(trailStopPrice) && trailingActive) {
            if (isLong) effectiveStop = Math.max(effectiveStop, trailStopPrice);
            else effectiveStop = Math.min(effectiveStop, trailStopPrice);
        }

        // ===== Stop Loss Check =====
        if (isLong && low <= effectiveStop) {
            ctx.closeAtMarket();
            debug("LONG stopped at " + effectiveStop + (trailingActive ? " (trail)" : beActivated ? " (BE)" : " (initial)"));
            resetTradeState();
            return;
        }
        if (!isLong && high >= effectiveStop) {
            ctx.closeAtMarket();
            debug("SHORT stopped at " + effectiveStop + (trailingActive ? " (trail)" : beActivated ? " (BE)" : " (initial)"));
            resetTradeState();
            return;
        }

        // ===== Unrealized profit =====
        double unrealizedPts = isLong ? close - entryPrice : entryPrice - close;

        // ===== Move to Breakeven =====
        boolean beEnable = getSettings().getBoolean(BE_ENABLED, true);
        double beTrigger = getSettings().getDouble(BE_TRIGGER_PTS, 3.0);
        int bePlusTicks = getSettings().getInteger(BE_PLUS_TICKS, 0);
        double bePlus = bePlusTicks * tickSize;

        if (beEnable && !beActivated && unrealizedPts >= beTrigger) {
            double newStop;
            if (isLong) {
                newStop = instr.round(entryPrice + bePlus);
                if (newStop > stopPrice) stopPrice = newStop;
            } else {
                newStop = instr.round(entryPrice - bePlus);
                if (newStop < stopPrice) stopPrice = newStop;
            }
            beActivated = true;
            debug("Stop moved to breakeven: " + stopPrice);
        }

        // ===== TP1 Partial =====
        int tp1Pct = getSettings().getInteger(TP1_PCT, 50);
        if (!tp1Filled) {
            boolean tp1Hit = (isLong && high >= tp1Price) || (!isLong && low <= tp1Price);
            if (tp1Hit) {
                int absPos = Math.abs(position);
                int partialQty = (int) Math.ceil(absPos * tp1Pct / 100.0);

                if (partialQty > 0 && partialQty < absPos) {
                    if (isLong) ctx.sell(partialQty);
                    else ctx.buy(partialQty);

                    tp1Filled = true;
                    debug(String.format("TP1 partial: %d contracts at %.2f", partialQty, tp1Price));

                    // Ensure stop is at least at breakeven after TP1
                    if (!beActivated) {
                        if (isLong && entryPrice > stopPrice) stopPrice = instr.round(entryPrice);
                        if (!isLong && entryPrice < stopPrice) stopPrice = instr.round(entryPrice);
                        beActivated = true;
                    }
                } else {
                    // Single contract: full exit at TP1
                    ctx.closeAtMarket();
                    debug("Full exit at TP1");
                    resetTradeState();
                    return;
                }
            }
        }

        // ===== Runner Trailing Stop =====
        boolean trailAfterTp1 = getSettings().getBoolean(RUNNER_TRAIL_AFTER_TP1, true);
        boolean canActivateTrail = trailAfterTp1 ? tp1Filled : (position != 0);

        if (canActivateTrail && !trailingActive) {
            trailingActive = true;
            // Initialize trail stop from current best price
            double trailDist = getTrailDistance(series, index);
            if (isLong) {
                trailStopPrice = instr.round(bestPriceInTrade - trailDist);
            } else {
                trailStopPrice = instr.round(bestPriceInTrade + trailDist);
            }
            debug("Runner trailing activated at " + trailStopPrice);
        }

        if (trailingActive) {
            double trailDist = getTrailDistance(series, index);

            if (isLong) {
                double newTrail = instr.round(bestPriceInTrade - trailDist);
                if (Double.isNaN(trailStopPrice) || newTrail > trailStopPrice) {
                    trailStopPrice = newTrail;
                }
            } else {
                double newTrail = instr.round(bestPriceInTrade + trailDist);
                if (Double.isNaN(trailStopPrice) || newTrail < trailStopPrice) {
                    trailStopPrice = newTrail;
                }
            }
        }
    }

    // ==================== Trail Distance ====================

    private double getTrailDistance(DataSeries series, int index)
    {
        int trailMode = getSettings().getInteger(RUNNER_TRAIL_MODE, TRAIL_POINTS);

        if (trailMode == TRAIL_ATR) {
            Double atr = series.getDouble(index, Values.ATR);
            double mult = getSettings().getDouble(RUNNER_ATR_MULT, 2.0);
            if (atr != null && atr > 0) {
                return atr * mult;
            }
        }

        return getSettings().getDouble(RUNNER_TRAIL_PTS, 4.0);
    }

    // ==================== State Reset ====================

    private void resetTradeState()
    {
        entryPrice = 0;
        stopPrice = 0;
        tp1Price = 0;
        tp1Filled = false;
        beActivated = false;
        trailStopPrice = Double.NaN;
        trailingActive = false;
        bestPriceInTrade = Double.NaN;
    }

    // ==================== Utility ====================

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

    @Override
    public void clearState() {
        super.clearState();
        resetTradeState();
        rangeHigh = Double.NaN;
        rangeLow = Double.NaN;
        rangeComplete = false;
        wasInRangeWindow = false;
        tradesToday = 0;
        lastResetDay = -1;
        eodProcessed = false;
    }
}
