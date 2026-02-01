# MotiveWave Study Builder

Generate, compile, and deploy MotiveWave studies/strategies from natural language prompts using Claude Code.

## Quick Start

```batch
# Build existing studies
gradlew build

# Deploy to MotiveWave
gradlew deploy

# Both at once
gradlew build deploy
```

After deploying, **restart MotiveWave** or go to:
`Configure -> Preferences -> Studies -> Reload Extensions`

## Project Structure

```
motivewave-study-builder/
├── mwbuilder.config.json    # Configuration
├── build.gradle             # Gradle build script
├── lib/
│   └── mwave_sdk.jar        # MotiveWave SDK
├── src/main/java/com/mw/studies/
│   ├── HelloStudy.java      # Simple example
│   ├── NYSessionSweepStudy.java  # Generated from prompt
│   └── nls/strings.properties    # Localization
├── prompts/
│   └── example_study.md     # Prompt spec files
└── templates/
    ├── StudyTemplate.java.txt    # Study template
    ├── StrategyTemplate.java.txt # Strategy template
    └── javadoc_blocks.md         # Code patterns reference
```

## Creating New Studies with Claude Code

### 1. Create a Prompt Spec

Create a file in `prompts/` following this format:

```markdown
# Name
Your Study Name

# Type
study  (or "strategy")

# Behavior
- What the study does
- Input parameters needed
- Calculation logic
- Signal conditions

# Outputs
- Plots: what lines/indicators to show
- Signals: what signals to generate
- Labels: text to display

# Risk/Trade Logic (only if strategy)
- Entry conditions
- Exit conditions
- Position sizing
```

### 2. Ask Claude Code to Generate

Tell Claude Code:
> "Read the prompt at prompts/my_study.md and generate a MotiveWave study for it"

Claude will:
1. Parse your spec
2. Generate proper Java code with full JavaDoc
3. Add necessary imports and SDK patterns
4. Create the file in `src/main/java/com/mw/studies/`

### 3. Build and Deploy

```batch
gradlew build deploy
```

## Prompt Examples

### Simple Study
```markdown
# Name
Double EMA Study

# Type
study

# Behavior
- Calculate two EMAs with different periods
- Plot both on the price chart
- Signal when fast crosses slow
- Inputs: fastPeriod (int), slowPeriod (int)

# Outputs
- Plots: fastEMA, slowEMA
- Signals: crossAbove, crossBelow
```

### Strategy
```markdown
# Name
EMA Cross Strategy

# Type
strategy

# Behavior
- Same as Double EMA Study
- Enter long on cross above
- Enter short on cross below

# Outputs
- Plots: fastEMA, slowEMA
- Signals: BUY, SELL

# Risk/Trade Logic
- Fixed lot sizing
- Close opposite position on signal
- No stop loss (exit on reverse signal)
```

## SDK Notes

### Important Discovery
The installed MotiveWave SDK (2025 version) has a bytecode bug - missing `InnerClasses` attribute. This project uses an older working SDK from the Eclipse project.

### Common Patterns

See `templates/javadoc_blocks.md` for:
- Input descriptors
- Plot descriptors
- Calculation patterns
- Signal generation
- Marker drawing
- Session time filtering

### Key Classes
- `Study` - Base class for studies
- `Enums.BarInput` - Price inputs (CLOSE, HIGH, LOW, etc.)
- `Enums.MAMethod` - Moving average methods (SMA, EMA, etc.)
- `DataContext` - Access to price data
- `OrderContext` - Access to order management (strategies only)

## Configuration

Edit `mwbuilder.config.json`:

```json
{
  "project": {
    "group": "com.mw.studies",
    "name": "MWGeneratedStudies",
    "version": "0.1.0"
  },
  "motivewave": {
    "extensionsDir": "C:/Users/YOUR_USER/MotiveWave Extensions",
    "sdkJar": "lib/mwave_sdk.jar",
    "reloadTrigger": ".last_updated"
  }
}
```

## Validation & Quality

The project includes comprehensive validation tasks:

```batch
# Validate source files
gradlew validate

# Validate prompt specs
gradlew validatePrompts

# Validate built JAR
gradlew validateJar

# List all studies/strategies
gradlew listStudies

# Full verified deploy (all validations + deploy)
gradlew verifiedDeploy
```

### What Gets Validated

**Source Validation:**
- Package declaration
- @StudyHeader annotation
- Required methods (initialize, calculate)
- Values enum
- Strategy-specific methods (onSignal, onActivate)
- Code quality warnings (System.out, Thread.sleep)
- JavaDoc presence

**Prompt Validation:**
- Required sections (Name, Type, Behavior, Outputs)
- Valid type (study/strategy)
- Bullet points in Behavior
- Plots/Signals in Outputs

**JAR Validation:**
- Class files present
- Properties files for localization
- Main study classes listed

## Troubleshooting

### "Cannot find symbol: Enums.BarInput"
Using wrong SDK version. Ensure `lib/mwave_sdk.jar` is the working version (not from installed MotiveWave).

### Build succeeds but study doesn't appear
1. Restart MotiveWave completely
2. Check the JAR was copied to Extensions folder
3. Look for errors in MotiveWave console

### OneDrive cache errors
These are harmless - the build/deploy still completes. The error is about Gradle's cache in the OneDrive-synced folder.

## Generated Studies & Strategies

Current studies in this project:

### Studies
1. **Hello Study** - Simple moving average (test/example)
2. **NY Session Sweep** - Detects RTH range sweeps with reversal signals

### Strategies
3. **MA Cross Strategy** - Moving average crossover with full risk management
   - Configurable fast/slow MA periods
   - ATR-based or fixed stop loss
   - Risk:Reward ratio for targets
   - Max trades per day limit

4. **Sweep Mean Reversion** - Trades reversals after range sweeps
   - Rolling range high/low detection
   - Enter on failed breakout (sweep + inside close)
   - Stop beyond sweep point
   - Target middle or opposite side of range
