"""Catálogo del fabricante de RTV prescrito (CLAUDE.md, regla 3: atenuaciones y ganancias del catálogo).

Cada catálogo es un JSON en ict_ajp/catalogos/<fabricante>.json generado desde las fichas oficiales
(herramientas/generar_catalogo_<fabricante>.py). Cada elemento lleva su referencia y la URL de su ficha.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=None)
def cargar(fabricante: str = "televes") -> dict:
    return json.loads((Path(__file__).parent / "catalogos" / f"{fabricante}.json").read_text(encoding="utf-8"))


def elemento(ref: str, fabricante: str = "televes") -> Optional[dict]:
    for grupo, lista in cargar(fabricante).items():
        if isinstance(lista, list):
            for e in lista:
                if e.get("ref") == ref:
                    return {**e, "grupo": grupo}
    return None


def atenuacion_cable_db_m(ref: str, f_mhz: float, fabricante: str = "televes") -> float:
    """Atenuación del cable a una frecuencia: interpolación lineal en log(f) entre los puntos de la ficha.

    No se extrapola: fuera de los puntos publicados se lanza error para no inventar valores.
    """
    c = elemento(ref, fabricante)
    if not c or c["grupo"] != "cables":
        raise ValueError(f"{ref} no es un cable del catálogo {fabricante}.")
    puntos = sorted((float(k), v) for k, v in c["atenuacion_db_m"].items())
    if not puntos[0][0] <= f_mhz <= puntos[-1][0]:
        raise ValueError(f"{f_mhz} MHz fuera de los datos de la ficha ({puntos[0][0]:g}-{puntos[-1][0]:g} MHz).")
    for (f1, a1), (f2, a2) in zip(puntos, puntos[1:]):
        if f1 <= f_mhz <= f2:
            if f1 == f2:
                return a1
            x = (math.log(f_mhz) - math.log(f1)) / (math.log(f2) - math.log(f1))
            return round(a1 + x * (a2 - a1), 4)
    return puntos[-1][1]


def derivadores(salidas: int, fabricante: str = "televes") -> list[dict]:
    return [d for d in cargar(fabricante)["derivadores"] if d["salidas"] == salidas]


def repartidor(salidas_min: int, pau: bool = True, fabricante: str = "televes") -> Optional[dict]:
    """El repartidor (o PAU) más pequeño con al menos `salidas_min` salidas."""
    c = [r for r in cargar(fabricante)["repartidores"] if r["pau"] == pau and r["salidas"] >= salidas_min]
    return min(c, key=lambda r: r["salidas"]) if c else None
