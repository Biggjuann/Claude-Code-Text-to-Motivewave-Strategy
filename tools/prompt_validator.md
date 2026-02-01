# Prompt Spec Validation Rules

This document defines validation rules for prompt spec files used to generate studies.

## Required Sections

Every prompt spec MUST contain these sections:

### # Name
- Must be non-empty
- Should be 2-5 words
- Will be used for class naming (PascalCase conversion)

### # Type
- Must be one of: `study`, `strategy`
- Case-insensitive

### # Behavior
- Must contain at least one bullet point (-)
- Should describe core functionality
- Should mention inputs with types

### # Outputs
- Must specify plots and/or signals
- Format: `- Plots: name1, name2`
- Format: `- Signals: SIGNAL1, SIGNAL2`

## Optional Sections

### # Risk/Trade Logic
- Required if Type = strategy
- Optional for studies
- Should describe position sizing, stops, targets

### # Notes
- Any additional implementation notes
- Edge cases to handle

## Validation Checks

### Name Validation
```
Valid:
  "My Simple Study"
  "MACD Crossover Strategy"
  "RSI"

Invalid:
  "" (empty)
  "A very long study name that goes on and on" (too long)
```

### Type Validation
```
Valid:
  "study"
  "Study"
  "STRATEGY"
  "strategy"

Invalid:
  "indicator"
  "signal"
  ""
```

### Behavior Validation
- Must have at least one hyphen-prefixed line
- Should mention inputs in parentheses: `inputName (type)`

### Outputs Validation
- Must have Plots and/or Signals
- Plot names should be camelCase
- Signal names should be UPPER_SNAKE_CASE

## Example Valid Spec

```markdown
# Name
Simple RSI Study

# Type
study

# Behavior
- Calculate RSI oscillator
- Show overbought/oversold levels
- Inputs:
  - period (int, default 14)
  - overbought (int, default 70)
  - oversold (int, default 30)

# Outputs
- Plots: rsi, overboughtLine, oversoldLine
- Signals: OVERBOUGHT, OVERSOLD

# Notes
- RSI should be displayed in separate panel (overlay=false)
- Use fill between overbought and oversold levels
```

## Parsing Rules

1. Sections start with `# ` (hash + space)
2. Section content is everything until next section or EOF
3. Bullet points start with `- ` (hyphen + space)
4. Whitespace is trimmed from values
5. Empty lines within sections are preserved

## Code Generation Mapping

| Spec Element | Java Element |
|--------------|--------------|
| Name | Class name (PascalCase), @StudyHeader name |
| Type=study | extends Study, no strategy flags |
| Type=strategy | extends Study, strategy=true, autoEntry=true |
| Behavior inputs | Settings descriptors, member variables |
| Output plots | Values enum, PathDescriptor, declarePath() |
| Output signals | Signals enum, declareSignal(), ctx.signal() |
