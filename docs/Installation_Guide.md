# Installation Guide

Step-by-step instructions for installing and using MW Generated Strategies in MotiveWave.

---

## Prerequisites

- **MotiveWave** installed (any edition that supports custom studies)
- **Java 11+** (usually bundled with MotiveWave)
- Downloaded `MWGeneratedStudies-x.x.x.jar` file

---

## Step 1: Locate Your Extensions Folder

### Windows
```
C:\Users\[YourUsername]\MotiveWave Extensions\
```

### Mac
```
~/MotiveWave Extensions/
```
Or:
```
/Users/[YourUsername]/MotiveWave Extensions/
```

### Linux
```
~/MotiveWave Extensions/
```

**Note:** If the folder doesn't exist, create it manually.

---

## Step 2: Install the JAR File

1. Copy `MWGeneratedStudies-x.x.x.jar` to your Extensions folder
2. **Important:** Only keep ONE version of the JAR in the folder
3. Delete any older versions to avoid conflicts

---

## Step 3: Load the Strategies

### Option A: Restart MotiveWave (Recommended)
1. Close MotiveWave completely
2. Reopen MotiveWave
3. Strategies will be loaded automatically

### Option B: Reload Extensions (Without Restart)
1. Go to **Configure** → **Preferences**
2. Click **Studies** in the left panel
3. Click **Reload Extensions** button
4. Click **OK**

---

## Step 4: Verify Installation

1. Open any chart
2. Go to **Study** menu
3. Look for **MW Generated** submenu
4. You should see all available strategies listed

If you don't see the menu:
- Check that the JAR is in the correct folder
- Ensure only one version of the JAR exists
- Try restarting MotiveWave again

---

## Step 5: Apply a Strategy

1. Open a chart with your desired:
   - **Instrument** (ES, NQ, etc.)
   - **Timeframe** (5 min, 15 min, etc.)
   - **Sufficient history** (at least a few days of data)

2. Go to **Study** → **MW Generated** → Select your strategy

3. Configure settings in the dialog:
   - Review default values
   - Adjust as needed for your preferences
   - Click **OK**

4. The strategy will appear on your chart with visual indicators

---

## Step 6: Backtest the Strategy

Before trading live, always backtest:

1. Go to **Strategy** → **Run Backtest**
2. Set your date range
3. Configure initial capital and position sizing
4. Click **Run**
5. Review the results:
   - Total P&L
   - Win rate
   - Profit factor
   - Drawdown

---

## Step 7: Activate for Live/Sim Trading

**Only after thorough backtesting:**

1. Apply the strategy to your chart
2. Ensure you're connected to your broker/data feed
3. Go to **Strategy** → **Activate Strategy**
4. Confirm the activation dialog
5. Monitor the strategy

**Warning:** Start with simulation trading before using real money!

---

## Troubleshooting

### Strategy Not Appearing in Menu

| Issue | Solution |
|-------|----------|
| JAR not in right folder | Verify Extensions folder path |
| Multiple JAR versions | Delete old versions |
| MotiveWave not restarted | Restart completely |
| Corrupted JAR | Re-download the file |

### Strategy Shows Errors

| Error | Solution |
|-------|----------|
| "Cannot find class" | JAR may be corrupted, re-download |
| "Null pointer" | Check chart has enough historical data |
| "No data" | Ensure instrument has data for the timeframe |

### Strategy Not Generating Signals

| Issue | Solution |
|-------|----------|
| Outside trade window | Check session/time settings |
| No qualifying setups | Market may not have met entry conditions |
| Already at max trades | Check max trades per day setting |
| EOD cutoff passed | Check EOD settings |

### Backtest Shows No Trades

| Issue | Solution |
|-------|----------|
| Date range too short | Extend backtest period |
| Wrong timeframe | Use recommended timeframe for strategy |
| Settings too restrictive | Relax entry criteria |
| No data | Load more historical data |

---

## Updating Strategies

When a new version is released:

1. **Close MotiveWave**
2. Delete the old JAR from Extensions folder
3. Copy the new JAR to Extensions folder
4. Restart MotiveWave
5. Re-apply strategies to charts (settings may reset)

---

## Recommended Chart Setup

For best results with these strategies:

### Index Futures (ES, NQ, MES, MNQ)
- **Timeframe:** 5-minute or 15-minute
- **Session:** RTH (Regular Trading Hours) or 24-hour
- **Data:** At least 5 trading days loaded

### Display Settings
- Show volume bars
- Consider adding VWAP study separately for reference
- Use a clean color scheme that doesn't clash with strategy plots

---

## Getting Help

If you encounter issues:

1. Check this troubleshooting guide first
2. Verify your MotiveWave version is up to date
3. Try removing and re-adding the strategy
4. Check the MotiveWave console for error messages:
   - **Help** → **Show Console**

---

## Important Notes

- **Always backtest** before live trading
- **Start with simulation** to verify behavior
- **Monitor actively** when first running live
- **Risk only what you can afford to lose**

These strategies are tools to assist your trading, not guaranteed profit systems. Past performance does not guarantee future results.
