"""Genera ict_ajp/datos/plan_tdt.json a partir del texto oficial del Plan Técnico Nacional de la TDT.

Fuente: docs/normativa/RD_250_2025_PTN_TDT_consolidado.md (BOE-A-2025-6004, texto consolidado).
- Anexo I: áreas geográficas y municipios (código INE) de cada una.
- Anexo II: canal radioeléctrico de cada múltiple (RGE1 ... MPE5, MAUT) en cada área.

Uso: python herramientas/generar_plan_tdt.py
La prueba tests/test_plan_tdt.py comprueba que el JSON coincide con el texto oficial.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "docs" / "normativa" / "RD_250_2025_PTN_TDT_consolidado.md"
SALIDA = RAIZ / "ict_ajp" / "datos" / "plan_tdt.json"
MULTIPLES = ["RGE1", "RGE2", "MPE1", "MPE2", "MPE3", "MPE4", "MPE5", "MAUT"]


def clave(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre)
    t = "".join(c for c in t if not unicodedata.combining(c)).upper().strip().rstrip(".")
    return " ".join(t.split())


def _celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def leer(fuente: Path = FUENTE) -> dict:
    lineas = fuente.read_text(encoding="utf-8").splitlines()
    i_anexo2 = next(i for i, l in enumerate(lineas) if l.strip() == "## ANEXO II")

    # Anexo I: «*Área geográfica n.º 54*», «#### Murcia Sur» y tabla de (INE, municipio) x 3
    areas: dict[str, dict] = {}
    actual = None
    for i, l in enumerate(lineas[:i_anexo2]):
        m = re.match(r"^\*Área geográfica n\.º (\d+)\*$", l.strip())
        if m:
            nombre = next(x for x in lineas[i + 1:] if x.strip()).lstrip("#").strip()
            actual = clave(nombre)
            areas[actual] = {"numero": int(m.group(1)), "nombre": nombre, "municipios": {}}
            continue
        if actual and l.startswith("|") and not l.startswith("| Cód") and not l.startswith("| ---"):
            c = _celdas(l)
            for k in range(0, len(c) - 1, 2):
                if re.fullmatch(r"\d{5}", c[k]):
                    areas[actual]["municipios"][c[k]] = c[k + 1].rstrip(".")

    # Anexo II: | Área geográfica | RGE1 | ... | MAUT |
    canales: dict[str, dict[str, int]] = {}
    for l in lineas[i_anexo2:]:
        if not l.startswith("|") or l.startswith("| Área") or l.startswith("| ---"):
            continue
        c = _celdas(l)
        if len(c) == 1 + len(MULTIPLES) and all(re.fullmatch(r"\d+", x) for x in c[1:]):
            canales[clave(c[0])] = dict(zip(MULTIPLES, (int(x) for x in c[1:])))

    faltan = set(areas) ^ set(canales)
    if faltan:
        raise ValueError(f"Áreas sin correspondencia entre anexo I y anexo II: {sorted(faltan)}")
    for k, a in areas.items():
        a["canales"] = canales[k]
    return {"fuente": "RD 250/2025, Plan Técnico Nacional de la TDT (BOE-A-2025-6004, consolidado)",
            "multiples": MULTIPLES, "areas": areas}


if __name__ == "__main__":
    datos = leer()
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    n_mun = sum(len(a["municipios"]) for a in datos["areas"].values())
    print(f"{SALIDA}: {len(datos['areas'])} áreas, {n_mun} municipios")
