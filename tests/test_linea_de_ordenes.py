"""La línea de órdenes funciona con la salida redirigida en Windows (cp1252), como en GitHub Actions."""

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent


def test_calcular_con_salida_en_cp1252(tmp_path):
    entorno = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    r = subprocess.run([sys.executable, "-m", "ict_ajp", "calcular", str(RAIZ / "ejemplos" / "edificio_prueba.ict.json"),
                        "-o", str(tmp_path / "r.xlsx")], capture_output=True, env=entorno, cwd=RAIZ)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert (tmp_path / "r.xlsx").exists()
    assert "≥" in r.stdout.decode("utf-8")       # los avisos salen enteros, en UTF-8
