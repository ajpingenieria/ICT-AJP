"""Radio (DAB y FM) y TDT local planificadas en un emplazamiento.

Datos en datos/plan_radio.json, generado con herramientas/generar_plan_radio.py a partir de los textos
oficiales de docs/normativa:
- RD 1287/1999, Plan técnico nacional de la radiodifusión sonora digital terrestre (DAB).
- RD 964/2006, Plan técnico nacional de radiodifusión sonora en FM (anexo II, gestión indirecta).
- RD 439/2004, Plan técnico nacional de la televisión digital local.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

REF_DAB = "RD 1287/1999, Plan técnico nacional de la radiodifusión sonora digital terrestre"
REF_FM = "RD 964/2006, Plan técnico nacional de radiodifusión sonora en FM, anexo II"
REF_TDT_LOCAL = "RD 439/2004, Plan técnico nacional de la televisión digital local"
ISLAS_CANARIAS = {"FUERTEVENTURA", "GOMERA", "GRAN CANARIA", "HIERRO", "LA PALMA", "LANZAROTE", "TENERIFE"}


@lru_cache(maxsize=1)
def _datos() -> dict:
    return json.loads((Path(__file__).parent / "datos" / "plan_radio.json").read_text(encoding="utf-8"))


def _clave(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).upper().replace(".", " ").split())


@dataclass(frozen=True)
class BloqueDAB:
    red: str
    bloque: str
    f_min_mhz: float
    f_max_mhz: float
    referencia: str


def bloques_dab(provincia: str) -> list[BloqueDAB]:
    """Bloques DAB planificados en una provincia (o isla): FU-E, MF-I, MF-II, MF y FU de la comunidad."""
    d = _datos()["dab"]
    p = _clave(provincia)
    lim = d["bloques_mhz"]

    def b(red: str, bloque: str, ref: str) -> BloqueDAB:
        return BloqueDAB(red, bloque, lim[bloque][0], lim[bloque][1], f"{REF_DAB}, {ref}")

    res = [b("FU-E", d["fu_e"]["canarias" if p in ISLAS_CANARIAS else "general"], "art. 3.1.a")]
    if p in d["mf_nacional"]:
        for red, bloque in d["mf_nacional"][p].items():
            res.append(b(red, bloque, "anexo I"))
    mf = d["mf_autonomica"].get(p) or next((v for k, v in d["mf_autonomica"].items() if k.startswith(p)), None)
    if mf:
        res.append(b(mf["red"], mf["bloque"], "anexo III"))
        fu = d["fu_autonomica"].get(mf["red"].replace("MF-", "FU-"))
        if fu:
            res.append(b(mf["red"].replace("MF-", "FU-"), fu["bloque"], "anexo II"))
    return res


def emisoras_fm(localidad: str, pv: str = "") -> list[tuple[float, bool]]:
    """Frecuencias FM de gestión indirecta de una localidad: (MHz, disponible para concesión [EX])."""
    k = _clave(localidad)
    res: list[tuple[float, bool]] = []
    for clave, lista in _datos()["fm"].items():
        prov, loc = clave.split("|", 1)
        if loc == k and (not pv or prov == pv.upper()):
            res.extend((f, ex) for f, ex in lista)
    return sorted(res)


@dataclass(frozen=True)
class DemarcacionLocal:
    referencia: str
    denominacion: str
    canal: Optional[int]
    ambito: tuple[str, ...]


def demarcacion_tdt_local(municipio: str) -> Optional[DemarcacionLocal]:
    k = _clave(municipio)
    for ref, v in _datos()["tdt_local"].items():
        if any(_clave(m) == k for m in v.get("ambito", [])):
            return DemarcacionLocal(ref, v.get("denominacion", ""), v.get("canal"), tuple(v.get("ambito", [])))
    return None
