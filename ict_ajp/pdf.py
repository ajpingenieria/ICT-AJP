"""Conversión de documentos a PDF con LibreOffice y utilidades sobre el PDF resultante."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional

RUTAS_SOFFICE = [r"C:\Program Files\LibreOffice\program\soffice.exe",
                 r"C:\Program Files (x86)\LibreOffice\program\soffice.exe", "/usr/bin/soffice"]


def soffice() -> Optional[str]:
    return shutil.which("soffice") or next((r for r in RUTAS_SOFFICE if Path(r).exists()), None)


def a_pdf(documento: str | Path, carpeta: Optional[str | Path] = None) -> Path:
    exe = soffice()
    if not exe:
        raise RuntimeError("LibreOffice no está instalado: no se puede convertir a PDF.")
    documento = Path(documento)
    carpeta = Path(carpeta or documento.parent)
    with tempfile.TemporaryDirectory() as perfil:   # perfil propio: no choca con un LibreOffice abierto
        subprocess.run([exe, f"-env:UserInstallation=file:///{Path(perfil).as_posix()}", "--headless",
                        "--convert-to", "pdf", "--outdir", str(carpeta), str(documento)],
                       check=True, capture_output=True, timeout=300)
    return carpeta / (documento.stem + ".pdf")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).upper().split())


def paginas_de_titulos(pdf: str | Path, titulos: list[str], desde: int = 1) -> dict[str, int]:
    """Página (1, 2...) en la que empieza cada título, buscando a partir de la página `desde`."""
    from pypdf import PdfReader

    paginas = [_norm(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    res, k = {}, desde - 1
    for t in titulos:
        clave = _norm(t)[:60]
        for j in range(k, len(paginas)):
            if clave in paginas[j]:
                res[t] = j + 1
                k = j
                break
    return res
