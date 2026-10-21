"""Lee las fichas de producto de Televés (PDF generado en global.televes.com/pdf/?sku=<ref>).

Extrae el nombre, la referencia y la tabla «Especificaciones técnicas». En estas fichas la tabla viene
con una codificación desplazada (letras en el bloque U+FF00-U+FFFC): se corrige restando 0xFF00.

Uso: python herramientas/leer_fichas_televes.py carpeta_con_pdfs salida.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader


def _decodificar(t: str) -> str:
    return "".join(chr(ord(c) - 0xFF00) if 0xFF00 <= ord(c) <= 0xFFFC else c for c in t)


def leer_ficha(ruta: Path) -> dict:
    paginas = []
    for p in PdfReader(str(ruta), strict=False).pages:
        try:
            paginas.append(p.extract_text() or "")
        except Exception:            # alguna página con imagen dañada: se salta, la tabla va en otra
            paginas.append("")
    portada = [l.strip() for l in paginas[0].splitlines() if l.strip()]
    i_ref = next(i for i, l in enumerate(portada) if l.startswith("Ref. "))
    ref = portada[i_ref][5:].strip()
    # el nombre son las líneas tras la cabecera («https://www.televes.com», «1») hasta la descripción
    cuerpo = [l for l in portada[:i_ref] if not l.startswith("http") and l != "1"]
    nombre = " ".join(cuerpo[:2]) if len(cuerpo) > 1 and not cuerpo[1][0].isupper() or (
        len(cuerpo) > 1 and re.match(r"^[\d.,/ ]+[A-Za-z]{2,3}", cuerpo[1])) else cuerpo[0]
    tabla: list[list[str]] = []
    especificaciones = False
    for p in paginas:
        for linea in _decodificar(p).splitlines():
            linea = " ".join(linea.split())
            if linea.startswith("Especificaciones técnicas"):
                especificaciones = True
                continue
            if especificaciones and linea and not linea.startswith("Powered by"):
                tabla.append(linea)
    return {"ref": ref, "nombre": nombre, "descripcion": " ".join(cuerpo[1:6]), "especificaciones": tabla}


if __name__ == "__main__":
    carpeta, salida = Path(sys.argv[1]), Path(sys.argv[2])
    fichas = {}
    for pdf in sorted(carpeta.glob("ficha_*.pdf")):
        try:
            f = leer_ficha(pdf)
            fichas[f["ref"]] = f
        except Exception as ex:          # se informa y se sigue con las demás
            print(f"{pdf.name}: {ex}")
    salida.write_text(json.dumps(fichas, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(fichas)} fichas leídas -> {salida}")
