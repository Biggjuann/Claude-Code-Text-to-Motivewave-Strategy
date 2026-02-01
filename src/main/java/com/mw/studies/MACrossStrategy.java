package com.mw.studies;

import com.motivewave.platform.sdk.common.*;
import com.motivewave.platform.sdk.common.desc.*;
import com.motivewave.platform.sdk.draw.*;
import com.motivewave.platform.sdk.order_mgmt.OrderContext;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * MA Cross Strategy
 *
 * A classic moving average crossover strategy with configurable risk management.
 * Enters long when fast MA crosses above slow MA, short when crossing below.
 *
 * ============================================================
 * INPUTS
 * ============================================================
 * Moving Averages:
 * - fastPeriod (int): Fast MA period [default: 9]
 * - slowPeriod (int): Slow MA period [default: 21]
 * - maMethod (MAMethod): Moving average calculation method [default: EMA]
 * - input (BarInput): Price input for MA calculation [default: CLOSE]
 *
 * Risk Management:
 * - useATRStop (bool): Use ATR for stop loss calculation [default: true]
 * - atrPeriod (int): ATR period for stop calculation [default: 14]
 * - atrMultiplier (double): ATR multiplier for stop distance [default: 2.0]
 * - fixedStopTicks (int): Fixed stop loss in ticks (if not using ATR) [default: 20]
 * - riskRewardRatio (double): Take profit as multiple of stop [default: 2.0]
 * - maxTradesPerDay (int): Maximum trades allowed per day [default: 3]
 *
 * ============================================================
 * ENTRY LOGIC
 * ============================================================
 * LONG Entry:
 * - Fast MA crosses above Slow MA
 * - Not already in a long position
 * - Under max trades per day limit
 *
 * SHORT Entry:
 * - Fast MA crosses below Slow MA
 * - Not already in a short position
 * - Under max trades per day limit
 *
 * ============================================================
 * EXIT LOGIC
 * ============================================================
 * - Stop Loss: ATR-based or fixed ticks below/above entry
 * - Take Profit: Risk:Reward ratio from stop distance
 * - Signal Exit: Close on opposite signal (before reversing)
 *
 * ============================================================
 * POSITION SIZING
 * ============================================================
 * - Uses Trade Lots setting from strategy panel
 * - Multiplied by instrument's default quantity
 *
 * @version 0.1.0
 * @author MW Study Builder
 * @generated 2024-02-01
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "MA_CROSS_STRATEGY",
    rb = "com.mw.studies.nls.strings",
    name = "MA Cross Strategy",
    label = "MA Cross",
    desc = "Moving average crossover strategy with risk management",
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
public class MACrossStrategy extends Study {

    // ==================== Constants ====================
    // Input Keys
    private static final String FAST_PERIOD = "fastPeriod";
    private static final String SLOW_PERIOD = "slowPeriod";
    private static final String MA_METHOD = "maMethod";
    private static final String USE_ATR_STOP = "useATRStop";
    private static final String ATR_PERIOD = "atrPeriod";
    private static final String ATR_MULTIPLIER = "atrMultiplier";
    private static final String FIXED_STOP_TICKS = "fixedStopTicks";
    private static final String RISK_REWARD = "riskReward";
    private static final String MAX_TRADES = "maxTrades";

    // Path Keys
    private static final String FAST_PATH = "fastPath";
    private static final String SLOW_PATH = "slowPath";

    // ==================== Values (data series keys) ====================
    enum Values {
        FAST_MA,         // Fast moving average
        SLOW_MA,         // Slow moving average
        ATR,             // Average True Range (for stops)
        STOP_LEVEL,      // Current stop loss level
        TARGET_LEVEL     // Current take profit level
    }

    // ==================== Signals ====================
    enum Signals {
        BUY,             // Long entry signal
        SELL             // Short entry signal
    }

    // ==================== Member Variables ====================
    private int tradesToday = 0;
    private int lastTradeDay = -1;
    private double entryPrice = 0;
    private double stopPrice = 0;
    private double targetPrice = 0;

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {
        var sd = createSD();

        // ===== Moving Average Tab =====
        var tab = sd.addTab("Moving Averages");

        var grp = tab.addGroup("Parameters");
        grp.addRow(new MAMethodDescriptor(MA_METHOD, "MA Method", Enums.MAMethod.EMA));
        grp.addRow(new InputDescriptor(Inputs.INPUT, "Price Input", Enums.BarInput.CLOSE));
        grp.addRow(new IntegerDescriptor(FAST_PERIOD, "Fast Period", 9, 1, 200, 1));
        grp.addRow(new IntegerDescriptor(SLOW_PERIOD, "Slow Period", 21, 1, 500, 1));

        grp = tab.addGroup("Display");
        grp.addRow(new PathDescriptor(FAST_PATH, "Fast MA", defaults.getBlue(), 1.5f, null, true, true, true));
        grp.addRow(new PathDescriptor(SLOW_PATH, "Slow MA", defaults.getRed(), 1.5f, null, true, true, true));

        // ===== Risk Management Tab =====
        tab = sd.addTab("Risk Management");

        grp = tab.addGroup("Stop Loss");
        grp.addRow(new BooleanDescriptor(USE_ATR_STOP, "Use ATR Stop", true));
        grp.addRow(new IntegerDescriptor(ATR_PERIOD, "ATR Period", 14, 1, 100, 1));
        grp.addRow(new DoubleDescriptor(ATR_MULTIPLIER, "ATR Multiplier", 2.0, 0.5, 10.0, 0.1));
        grp.addRow(new IntegerDescriptor(FIXED_STOP_TICKS, "Fixed Stop (ticks)", 20, 1, 500, 1));

        grp = tab.addGroup("Take Profit");
        grp.addRow(new DoubleDescriptor(RISK_REWARD, "Risk:Reward Ratio", 2.0, 0.5, 10.0, 0.1));

        grp = tab.addGroup("Trade Limits");
        grp.addRow(new IntegerDescriptor(MAX_TRADES, "Max Trades/Day", 3, 1, 50, 1));

        // ===== Markers Tab =====
        tab = sd.addTab("Markers");

        grp = tab.addGroup("Entry Markers");
        grp.addRow(new MarkerDescriptor(Inputs.UP_MARKER, "Buy Signal",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getGreen(), defaults.getLineColor(), true, true));
        grp.addRow(new MarkerDescriptor(Inputs.DOWN_MARKER, "Sell Signal",
            Enums.MarkerType.TRIANGLE, Enums.Size.MEDIUM, defaults.getRed(), defaults.getLineColor(), true, true));

        // Quick settings
        sd.addQuickSettings(FAST_PERIOD, SLOW_PERIOD, MA_METHOD);

        // ===== Runtime Descriptor =====
        var desc = createRD();
        desc.setLabelSettings(FAST_PERIOD, SLOW_PERIOD, MA_METHOD);

        // Export values for cursor
        desc.exportValue(new ValueDescriptor(Values.FAST_MA, "Fast MA", new String[]{FAST_PERIOD}));
        desc.exportValue(new ValueDescriptor(Values.SLOW_MA, "Slow MA", new String[]{SLOW_PERIOD}));
        desc.exportValue(new ValueDescriptor(Values.ATR, "ATR", new String[]{ATR_PERIOD}));

        // Declare paths
        desc.declarePath(Values.FAST_MA, FAST_PATH);
        desc.declarePath(Values.SLOW_MA, SLOW_PATH);

        // Declare signals
        desc.declareSignal(Signals.BUY, "Buy Signal");
        desc.declareSignal(Signals.SELL, "Sell Signal");

        // Range keys
        desc.setRangeKeys(Values.FAST_MA, Values.SLOW_MA);
    }

    @Override
    public void onLoad(Defaults defaults) {
        int fast = getSettings().getInteger(FAST_PERIOD, 9);
        int slow = getSettings().getInteger(SLOW_PERIOD, 21);
        int atr = getSettings().getInteger(ATR_PERIOD, 14);
        setMinBars(Math.max(slow, atr) * 2);
    }

    @Override
    public int getMinBars() {
        int slow = getSettings().getInteger(SLOW_PERIOD, 21);
        int atr = getSettings().getInteger(ATR_PERIOD, 14);
        return Math.max(slow, atr) * 2;
    }

    // ==================== Calculation ====================

    @Override
    protected void calculate(int index, DataContext ctx) {
        var series = ctx.getDataSeries();

        // Get settings
        int fastPeriod = getSettings().getInteger(FAST_PERIOD, 9);
        int slowPeriod = getSettings().getInteger(SLOW_PERIOD, 21);
        var maMethod = getSettings().getMAMethod(MA_METHOD, Enums.MAMethod.EMA);
        Object input = getSettings().getInput(Inputs.INPUT, Enums.BarInput.CLOSE);
        int atrPeriod = getSettings().getInteger(ATR_PERIOD, 14);
        int maxTrades = getSettings().getInteger(MAX_TRADES, 3);

        // Need enough bars
        int minBars = Math.max(slowPeriod, atrPeriod);
        if (index < minBars) return;

        // Calculate MAs
        Double fastMA = series.ma(maMethod, index, fastPeriod, input);
        Double slowMA = series.ma(maMethod, index, slowPeriod, input);

        if (fastMA == null || slowMA == null) return;

        series.setDouble(index, Values.FAST_MA, fastMA);
        series.setDouble(index, Values.SLOW_MA, slowMA);

        // Calculate ATR for stop loss
        Double atr = series.atr(index, atrPeriod);
        if (atr != null) {
            series.setDouble(index, Values.ATR, atr);
        }

        // Reset daily trade count
        long barTime = series.getStartTime(index);
        int barDay = getDayOfYear(barTime, ctx.getTimeZone());
        if (barDay != lastTradeDay) {
            tradesToday = 0;
            lastTradeDay = barDay;
        }

        // Check for crossovers (only on completed bars for strategies)
        if (!series.isBarComplete(index)) return;

        boolean crossAbove = crossedAbove(series, index, Values.FAST_MA, Values.SLOW_MA);
        boolean crossBelow = crossedBelow(series, index, Values.FAST_MA, Values.SLOW_MA);

        double close = series.getClose(index);

        // BUY signal
        if (crossAbove && tradesToday < maxTrades) {
            series.setBoolean(index, Signals.BUY, true);
            ctx.signal(index, Signals.BUY, "Fast MA crossed above Slow MA", close);

            // Draw marker
            var marker = getSettings().getMarker(Inputs.UP_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, series.getLow(index));
                addFigure(new Marker(coord, Enums.Position.BOTTOM, marker, "BUY"));
            }
        }

        // SELL signal
        if (crossBelow && tradesToday < maxTrades) {
            series.setBoolean(index, Signals.SELL, true);
            ctx.signal(index, Signals.SELL, "Fast MA crossed below Slow MA", close);

            // Draw marker
            var marker = getSettings().getMarker(Inputs.DOWN_MARKER);
            if (marker.isEnabled()) {
                var coord = new Coordinate(barTime, series.getHigh(index));
                addFigure(new Marker(coord, Enums.Position.TOP, marker, "SELL"));
            }
        }

        series.setComplete(index);
    }

    // ==================== Strategy Lifecycle ====================

    /**
     * Called when strategy is activated.
     * Can enter initial position based on current MA relationship.
     */
    @Override
    public void onActivate(OrderContext ctx) {
        if (!getSettings().isEnterOnActivate()) return;

        var series = ctx.getDataContext().getDataSeries();
        int index = series.size() - 1;
        if (index < getMinBars()) return;

        Double fastMA = series.getDouble(index, Values.FAST_MA);
        Double slowMA = series.getDouble(index, Values.SLOW_MA);

        if (fastMA == null || slowMA == null) return;

        int qty = getTradeQuantity(ctx);

        // Enter based on current MA relationship
        if (fastMA > slowMA) {
            ctx.buy(qty);
            setupStopAndTarget(ctx, true);
            debug("Activated with LONG position, qty=" + qty);
        } else if (fastMA < slowMA) {
            ctx.sell(qty);
            setupStopAndTarget(ctx, false);
            debug("Activated with SHORT position, qty=" + qty);
        }
    }

    /**
     * Called when strategy is deactivated.
     * Closes any open position.
     */
    @Override
    public void onDeactivate(OrderContext ctx) {
        int position = ctx.getPosition();
        if (position != 0) {
            ctx.closeAtMarket();
            debug("Deactivated - closed position: " + position);
        }
        resetTradeState();
    }

    /**
     * Called when a signal is generated.
     * Handles trade execution with risk management.
     */
    @Override
    public void onSignal(OrderContext ctx, Object signal) {
        var instr = ctx.getInstrument();
        int position = ctx.getPosition();
        int qty = getTradeQuantity(ctx);
        int maxTrades = getSettings().getInteger(MAX_TRADES, 3);

        // Check trade limit
        if (tradesToday >= maxTrades) {
            debug("Max trades reached for today: " + tradesToday);
            return;
        }

        if (signal == Signals.BUY) {
            // Close any short position first
            if (position < 0) {
                ctx.closeAtMarket();
                debug("Closed SHORT before reversing to LONG");
            }

            // Enter long if not already long
            if (position <= 0) {
                ctx.buy(qty);
                tradesToday++;
                setupStopAndTarget(ctx, true);
                debug("BUY executed, qty=" + qty + ", trades today=" + tradesToday);
            }
        }
        else if (signal == Signals.SELL) {
            // Close any long position first
            if (position > 0) {
                ctx.closeAtMarket();
                debug("Closed LONG before reversing to SHORT");
            }

            // Enter short if not already short
            if (position >= 0) {
                ctx.sell(qty);
                tradesToday++;
                setupStopAndTarget(ctx, false);
                debug("SELL executed, qty=" + qty + ", trades today=" + tradesToday);
            }
        }
    }

    // ==================== Helper Methods ====================

    /**
     * Calculates trade quantity based on settings.
     */
    private int getTradeQuantity(OrderContext ctx) {
        var instr = ctx.getInstrument();
        return getSettings().getTradeLots() * instr.getDefaultQuantity();
    }

    /**
     * Sets up stop loss and take profit levels.
     */
    private void setupStopAndTarget(OrderContext ctx, boolean isLong) {
        var instr = ctx.getInstrument();
        double tickSize = instr.getTickSize();
        double currentPrice = instr.getLastPrice();

        // Get stop distance
        double stopDistance;
        boolean useATR = getSettings().getBoolean(USE_ATR_STOP, true);

        if (useATR) {
            var series = ctx.getDataContext().getDataSeries();
            int index = series.size() - 1;
            Double atr = series.getDouble(index, Values.ATR);
            double multiplier = getSettings().getDouble(ATR_MULTIPLIER, 2.0);

            if (atr != null && atr > 0) {
                stopDistance = atr * multiplier;
            } else {
                // Fallback to fixed
                int fixedTicks = getSettings().getInteger(FIXED_STOP_TICKS, 20);
                stopDistance = fixedTicks * tickSize;
            }
        } else {
            int fixedTicks = getSettings().getInteger(FIXED_STOP_TICKS, 20);
            stopDistance = fixedTicks * tickSize;
        }

        // Calculate stop and target
        double rrRatio = getSettings().getDouble(RISK_REWARD, 2.0);
        double targetDistance = stopDistance * rrRatio;

        if (isLong) {
            entryPrice = currentPrice;
            stopPrice = instr.round(currentPrice - stopDistance);
            targetPrice = instr.round(currentPrice + targetDistance);
        } else {
            entryPrice = currentPrice;
            stopPrice = instr.round(currentPrice + stopDistance);
            targetPrice = instr.round(currentPrice - targetDistance);
        }

        debug(String.format("Stop/Target set: Entry=%.2f, Stop=%.2f, Target=%.2f",
            entryPrice, stopPrice, targetPrice));
    }

    /**
     * Resets trade state tracking.
     */
    private void resetTradeState() {
        entryPrice = 0;
        stopPrice = 0;
        targetPrice = 0;
    }

    /**
     * Gets day of year from timestamp.
     */
    private int getDayOfYear(long time, java.util.TimeZone tz) {
        java.util.Calendar cal = java.util.Calendar.getInstance(tz);
        cal.setTimeInMillis(time);
        return cal.get(java.util.Calendar.DAY_OF_YEAR);
    }

    /**
     * Clears state when study is reset.
     */
    @Override
    public void clearState() {
        super.clearState();
        tradesToday = 0;
        lastTradeDay = -1;
        resetTradeState();
    }
}
