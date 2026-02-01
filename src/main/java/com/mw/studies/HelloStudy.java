package com.mw.studies;

import com.motivewave.platform.sdk.common.DataContext;
import com.motivewave.platform.sdk.common.Defaults;
import com.motivewave.platform.sdk.common.Enums;
import com.motivewave.platform.sdk.common.Inputs;
import com.motivewave.platform.sdk.common.desc.InputDescriptor;
import com.motivewave.platform.sdk.common.desc.IntegerDescriptor;
import com.motivewave.platform.sdk.common.desc.PathDescriptor;
import com.motivewave.platform.sdk.common.desc.ValueDescriptor;
import com.motivewave.platform.sdk.study.Study;
import com.motivewave.platform.sdk.study.StudyHeader;

/**
 * HelloStudy - A simple test study to verify the build pipeline.
 *
 * This study displays a simple moving average on the chart.
 * It serves as a minimal working example for the MW Study Builder.
 *
 * Inputs:
 *   - Input: Price input (default: Close)
 *   - Period: Moving average period (default: 20)
 *
 * Outputs:
 *   - MA: The calculated moving average line
 *
 * @version 0.1.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "com.mw.studies",
    id = "HELLO_STUDY",
    rb = "com.mw.studies.nls.strings",
    name = "Hello Study",
    label = "Hello Study",
    desc = "A simple test study to verify the build pipeline",
    menu = "MW Generated",
    overlay = true,
    studyOverlay = true
)
public class HelloStudy extends Study {

    // ==================== Values ====================
    // Keys for storing calculated values in the data series
    enum Values { MA }

    // ==================== Initialization ====================

    /**
     * Initializes the study settings and runtime descriptors.
     * Called once when the study is first added to a chart.
     */
    @Override
    public void initialize(Defaults defaults) {
        // Create settings descriptor for user-configurable inputs
        var sd = createSD();
        var tab = sd.addTab("General");

        // Input settings group
        var grp = tab.addGroup("Inputs");
        grp.addRow(new InputDescriptor(Inputs.INPUT, "Input", Enums.BarInput.CLOSE));
        grp.addRow(new IntegerDescriptor(Inputs.PERIOD, "Period", 20, 1, 500, 1));

        // Display settings group
        grp = tab.addGroup("Display");
        grp.addRow(new PathDescriptor(Inputs.PATH, "MA Line", null, 1.5f, null, true, true, false));

        // Create runtime descriptor for labels and exports
        var desc = createRD();
        desc.setLabelSettings(Inputs.INPUT, Inputs.PERIOD);
        desc.exportValue(new ValueDescriptor(Values.MA, "MA", new String[]{Inputs.INPUT, Inputs.PERIOD}));
        desc.declarePath(Values.MA, Inputs.PATH);
    }

    // ==================== Calculation ====================

    /**
     * Returns the minimum number of bars required before calculation can begin.
     */
    @Override
    public int getMinBars() {
        return getSettings().getInteger(Inputs.PERIOD) * 2;
    }

    /**
     * Calculates the moving average for the given bar index.
     * Called for each bar in the data series.
     *
     * @param index The bar index to calculate
     * @param ctx   The data context providing access to price data
     */
    @Override
    protected void calculate(int index, DataContext ctx) {
        // Get user settings
        Object input = getSettings().getInput(Inputs.INPUT);
        int period = getSettings().getInteger(Inputs.PERIOD);

        // Need enough bars for calculation
        if (index < period) return;

        // Get data series and calculate SMA
        var series = ctx.getDataSeries();
        Double ma = series.sma(index, period, input);

        if (ma == null) return;

        // Store the calculated value
        series.setDouble(index, Values.MA, ma);
    }
}
