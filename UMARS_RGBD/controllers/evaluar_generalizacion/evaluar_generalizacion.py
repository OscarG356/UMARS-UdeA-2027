"""Activa la prueba de varios inicios desde mundos dedicados de Webots."""

import os
from pathlib import Path
import runpy


os.environ["UMARS_GENERALIZACION"] = "1"
evaluador = Path(__file__).resolve().parents[1] / "evaluar" / "evaluar.py"
runpy.run_path(str(evaluador), run_name="__main__")
