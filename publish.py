import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    print(f"🚀 {description}...")
    try:
        subprocess.run(cmd, check=True, shell=sys.platform == "win32")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during {description}: {e}")
        sys.exit(1)


def build_production():
    BRAND_COLOR = "#2E7D32"

    # Removed --include-data as it's not a valid Flet flag
    base_args = ["flet", "build", "--splash-color", BRAND_COLOR, "--compile-packages", "."]

    # Target Logic
    if sys.platform == "win32":
        targets = ["windows"]
    elif sys.platform == "darwin":
        targets = ["macos"]  # Start with these then add "apk", "ipa"
    else:
        targets = ["linux", "apk"]

    for target in targets:
        print(f"\n--- Building for {target.upper()} ---")
        final_cmd = base_args.copy()
        final_cmd.insert(2, target)

        # Flet looks for assets/icon.png by default if you don't specify
        if Path("assets/icon.png").exists():
            final_cmd.extend(["--icon", "assets/icon.png"])

        run_command(final_cmd, f"Compiling {target}")


if __name__ == "__main__":
    build_production()
