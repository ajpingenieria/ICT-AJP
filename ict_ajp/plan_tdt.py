"""Canales de TDT planificados por municipio (RD 250/2025, Plan Técnico Nacional de la TDT).

Los datos están en datos/plan_tdt.json, generado con herramientas/generar_plan_tdt.py a partir del
texto oficial en docs/normativa/RD_250_2025_PTN_TDT_consolidado.md (anexos I y II).
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

REFERENCIA_PLAN = "RD 250/2025, Plan Técnico Nacional de la TDT"
REFERENCIA = REFERENCIA_PLAN + ", anexos I y II"
# Plan, art. 1: «banda de frecuencias de 470 a 694 MHz (canales radioeléctricos 21 a 48)»: 8 MHz por canal
CANAL_MIN, CANAL_MAX, F_INICIO_MHZ, ANCHO_CANAL_MHZ = 21, 48, 470, 8


@lru_cache(maxsize=1)
def _datos() -> dict:
    return json.loads((Path(__file__).parent / "datos" / "plan_tdt.json").read_text(encoding="utf-8"))


def _clave(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).upper().replace(".", " ").split())


def frecuencia_central_mhz(canal: int) -> float:
    if not CANAL_MIN <= canal <= CANAL_MAX:
        raise ValueError(f"Canal {canal} fuera de la banda de TDT (canales {CANAL_MIN} a {CANAL_MAX}).")
    return F_INICIO_MHZ + (canal - CANAL_MIN) * ANCHO_CANAL_MHZ + ANCHO_CANAL_MHZ / 2


@dataclass(frozen=True)
class AreaTDT:
    numero: int
    nombre: str
    canales: dict[str, int]      # múltiple -> canal


@dataclass(frozen=True)
class Municipio:
    ine: str
    nombre: str
    area: AreaTDT


def buscar_municipios(nombre: str = "", ine: str = "") -> list[Municipio]:
    """Municipios por código INE (exacto) o por nombre (admite «Torres de Cotillas (Las)» o «Las Torres...»)."""
    res = []
    buscado = _clave(nombre)
    for a in _datos()["areas"].values():
        area = AreaTDT(a["numero"], a["nombre"], a["canales"])
        for cod, mun in a["municipios"].items():
            if ine:
                if cod == ine:
                    res.append(Municipio(cod, mun, area))
                continue
            k = _clave(mun)
            # «Torres de Cotillas (Las)» también como «Las Torres de Cotillas»
            alternativo = k
            if k.endswith(")") and "(" in k:
                base, art = k[:-1].split("(", 1)
                alternativo = f"{art.strip()} {base.strip()}"
            if buscado in (k, alternativo, k.replace("(", "").replace(")", "")):
                res.append(Municipio(cod, mun, area))
    return res


def municipio(nombre: str = "", ine: str = "") -> Optional[Municipio]:
    """Un único municipio, o None si no se encuentra o el nombre es ambiguo (hay que dar el INE)."""
    r = buscar_municipios(nombre, ine)
    return r[0] if len(r) == 1 else None
