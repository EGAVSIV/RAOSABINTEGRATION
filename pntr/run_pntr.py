#!/usr/bin/env python3
"""Run all PNTR batch generators in dependency order."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
for name in ("nakshatra_30y.py", "pada_30y.py", "weekly_levels.py"):
    path = HERE / name
    print(f"\n=== Running {path.name} ===")
    subprocess.run([sys.executable, str(path)], check=True, cwd=HERE.parent)
print("\nPNTR generation complete.")
