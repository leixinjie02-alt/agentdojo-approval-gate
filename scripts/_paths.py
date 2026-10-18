# Imported first by every script in this folder: finds the project root and sets up imports.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_paths  # noqa: E402,F401
from project_paths import ROOT, RESULTS_DIR  # noqa: E402,F401
