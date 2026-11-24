"""Ejecuta la politica de referencia con el mismo mundo y controlador."""

import os
from pathlib import Path
import runpy
import sys

principal = Path(__file__).resolve().parents[1] / "umars_qlearning" / "umars_qlearning.py"
sys.path.insert(0, str(principal.parent))
os.environ["UMARS_POLITICA"] = "reglas"
runpy.run_path(str(principal), run_name="__main__")
