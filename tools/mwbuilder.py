#!/usr/bin/env python3
"""
mwbuilder - MotiveWave Study Builder CLI

Commands:
    mwbuilder build           - Compile the project and create JAR
    mwbuilder deploy          - Deploy JAR to MotiveWave Extensions
    mwbuilder gen <prompt>    - Generate study from prompt file
    mwbuilder all <prompt>    - Full pipeline: gen -> build -> deploy
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Project root (parent of tools directory)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_FILE = PROJECT_ROOT / "mwbuilder.config.json"


def load_config():
    """Load configuration from mwbuilder.config.json"""
    if not CONFIG_FILE.exists():
        print(f"Error: Config file not found: {CONFIG_FILE}")
        sys.exit(1)

    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def run_gradle(task: str, config: dict) -> bool:
    """Run a Gradle task and return success status"""
    gradlew = PROJECT_ROOT / ("gradlew.bat" if os.name == 'nt' else "gradlew")

    if not gradlew.exists():
        print(f"Error: Gradle wrapper not found: {gradlew}")
        return False

    print(f"Running: gradlew {task}")
    result = subprocess.run(
        [str(gradlew), task],
        cwd=PROJECT_ROOT,
        capture_output=False
    )

    return result.returncode == 0


def cmd_build(args, config):
    """Build the project"""
    print("=" * 50)
    print("Building MotiveWave Study...")
    print("=" * 50)

    success = run_gradle("build", config)

    if success:
        jar_dir = PROJECT_ROOT / "build" / "libs"
        jars = list(jar_dir.glob("*.jar"))
        if jars:
            jar = jars[0]
            print(f"\nBuild successful!")
            print(f"  JAR: {jar.name}")
            print(f"  Size: {jar.stat().st_size} bytes")
    else:
        print("\nBuild failed!")

    return success


def cmd_deploy(args, config):
    """Deploy JAR to MotiveWave Extensions"""
    print("=" * 50)
    print("Deploying to MotiveWave...")
    print("=" * 50)

    success = run_gradle("deploy", config)

    if success:
        ext_dir = Path(config['motivewave']['extensionsDir'])
        print(f"\nDeploy successful!")
        print(f"  Extensions dir: {ext_dir}")
        print(f"\nRestart MotiveWave or go to:")
        print(f"  Configure -> Preferences -> Studies -> Reload Extensions")
    else:
        print("\nDeploy failed!")

    return success


def cmd_gen(args, config):
    """Generate study from prompt file"""
    prompt_file = Path(args.prompt)

    if not prompt_file.exists():
        # Try looking in prompts/ directory
        prompt_file = PROJECT_ROOT / "prompts" / args.prompt
        if not prompt_file.exists():
            print(f"Error: Prompt file not found: {args.prompt}")
            return False

    print("=" * 50)
    print(f"Generating study from: {prompt_file.name}")
    print("=" * 50)

    # Read the prompt file
    with open(prompt_file, 'r') as f:
        prompt_content = f.read()

    # Parse the prompt (basic markdown format)
    spec = parse_prompt(prompt_content)

    print(f"Study: {spec.get('name', 'Unknown')}")
    print(f"Type: {spec.get('type', 'study')}")

    # Generate the Java file
    generate_study(spec, config)

    print(f"\nGeneration complete!")
    return True


def parse_prompt(content: str) -> dict:
    """Parse a markdown prompt file into a spec dictionary"""
    spec = {}
    current_section = None
    current_content = []

    for line in content.split('\n'):
        line = line.rstrip()

        if line.startswith('# '):
            if current_section and current_content:
                spec[current_section.lower()] = '\n'.join(current_content).strip()
            current_section = line[2:].strip()
            current_content = []
        elif current_section:
            current_content.append(line)

    # Save last section
    if current_section and current_content:
        spec[current_section.lower()] = '\n'.join(current_content).strip()

    return spec


def generate_study(spec: dict, config: dict):
    """Generate Java study file from spec"""
    # Get study metadata
    name = spec.get('name', 'GeneratedStudy')
    study_type = spec.get('type', 'study')
    behavior = spec.get('behavior', '')

    # Generate class name from study name
    class_name = ''.join(word.capitalize() for word in name.split())
    class_name = ''.join(c for c in class_name if c.isalnum())

    # Study ID
    study_id = class_name.upper().replace(' ', '_')

    # Package
    base_package = config['generation']['basePackage']

    # Generate the Java file
    java_content = generate_java_template(
        class_name=class_name,
        study_id=study_id,
        name=name,
        behavior=behavior,
        package=base_package,
        study_type=study_type
    )

    # Write to src directory
    src_dir = PROJECT_ROOT / "src" / "main" / "java" / base_package.replace('.', '/')
    src_dir.mkdir(parents=True, exist_ok=True)

    java_file = src_dir / f"{class_name}.java"
    with open(java_file, 'w') as f:
        f.write(java_content)

    print(f"Generated: {java_file.relative_to(PROJECT_ROOT)}")


def generate_java_template(class_name: str, study_id: str, name: str,
                          behavior: str, package: str, study_type: str) -> str:
    """Generate Java source code for a study"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Parse behavior for inputs/outputs hints
    is_overlay = 'overlay' in behavior.lower() or 'price' in behavior.lower()

    template = f'''package {package};

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
 * {name}
 *
 * Generated by mwbuilder on {timestamp}
 *
 * Behavior:
 * {behavior.replace(chr(10), chr(10) + " * ")}
 *
 * @version 0.1.0
 * @author MW Study Builder
 */
@StudyHeader(
    namespace = "{package}",
    id = "{study_id}",
    rb = "{package}.nls.strings",
    name = "{name}",
    label = "{name}",
    desc = "{name}",
    menu = "MW Generated",
    overlay = {str(is_overlay).lower()},
    studyOverlay = true
)
public class {class_name} extends Study {{

    // ==================== Values ====================
    enum Values {{ MAIN }}

    // ==================== Initialization ====================

    @Override
    public void initialize(Defaults defaults) {{
        var sd = createSD();
        var tab = sd.addTab("General");

        var grp = tab.addGroup("Inputs");
        grp.addRow(new InputDescriptor(Inputs.INPUT, "Input", Enums.BarInput.CLOSE));
        grp.addRow(new IntegerDescriptor(Inputs.PERIOD, "Period", 20, 1, 500, 1));

        grp = tab.addGroup("Display");
        grp.addRow(new PathDescriptor(Inputs.PATH, "Line", null, 1.5f, null, true, true, false));

        var desc = createRD();
        desc.setLabelSettings(Inputs.INPUT, Inputs.PERIOD);
        desc.exportValue(new ValueDescriptor(Values.MAIN, "Value", new String[]{{Inputs.INPUT, Inputs.PERIOD}}));
        desc.declarePath(Values.MAIN, Inputs.PATH);
    }}

    // ==================== Calculation ====================

    @Override
    public int getMinBars() {{
        return getSettings().getInteger(Inputs.PERIOD) * 2;
    }}

    @Override
    protected void calculate(int index, DataContext ctx) {{
        Object input = getSettings().getInput(Inputs.INPUT);
        int period = getSettings().getInteger(Inputs.PERIOD);

        if (index < period) return;

        var series = ctx.getDataSeries();

        // TODO: Implement calculation logic based on behavior spec
        Double value = series.sma(index, period, input);

        if (value == null) return;

        series.setDouble(index, Values.MAIN, value);
    }}
}}
'''
    return template


def cmd_all(args, config):
    """Run full pipeline: gen -> build -> deploy"""
    print("=" * 50)
    print("Running full pipeline...")
    print("=" * 50)

    # Generate if prompt provided
    if args.prompt:
        if not cmd_gen(args, config):
            return False
        print()

    # Build
    if not cmd_build(args, config):
        return False
    print()

    # Deploy
    if not cmd_deploy(args, config):
        return False

    print()
    print("=" * 50)
    print("Pipeline complete!")
    print("=" * 50)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="MotiveWave Study Builder CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # build command
    build_parser = subparsers.add_parser('build', help='Compile and create JAR')

    # deploy command
    deploy_parser = subparsers.add_parser('deploy', help='Deploy to MotiveWave')

    # gen command
    gen_parser = subparsers.add_parser('gen', help='Generate study from prompt')
    gen_parser.add_argument('prompt', help='Path to prompt file (or name in prompts/)')

    # all command
    all_parser = subparsers.add_parser('all', help='Full pipeline: gen -> build -> deploy')
    all_parser.add_argument('prompt', nargs='?', help='Optional prompt file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = load_config()

    # Execute command
    commands = {
        'build': cmd_build,
        'deploy': cmd_deploy,
        'gen': cmd_gen,
        'all': cmd_all,
    }

    success = commands[args.command](args, config)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
