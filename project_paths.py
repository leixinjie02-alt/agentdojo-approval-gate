"""Puts every source folder on sys.path, so modules keep their short import names
(`from approval_gate import ...`) after the reorganisation into src/, scripts/ and tests/.

Imported automatically by pytest (via conftest.py) and by every script in scripts/.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_DIRS = ["src/gate", "src/rules", "src/adapters", "src/utils", "scripts", "tests"]
RESULTS_DIR = ROOT / "data" / "results"

for d in SOURCE_DIRS:
    p = str(ROOT / d)
    if p not in sys.path:
        sys.path.insert(0, p)
