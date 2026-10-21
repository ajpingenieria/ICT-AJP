"""Genera ict_ajp/datos/plan_radio.json desde los planes técnicos de radio de docs/normativa.

- DAB: RD 1287/1999, Plan técnico nacional de la radiodifusión sonora digital terrestre (consolidado).
  Red FU-E (art. 3.1.a del plan), anexo I (redes MF-I y MF-II por provincia), anexo II (red FU de cada
  comunidad autónoma), anexo III (red MF de cada comunidad, por provincia) y anexo IV (límites de bloque).
- FM: RD 964/2006, Plan técnico nacional de FM (consolidado), anexo II: emisoras de gestión indirecta
  por localidad. Las emisoras de gestión directa (RNE, autonómicas, municipales) no figuran en el anexo.

Uso: python herramientas/generar_plan_radio.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DAB = RAIZ / "docs" / "normativa" / "RD_1287_1999_PTN_radio_digital_consolidado.md"
FM = RAIZ / "docs" / "normativa" / "RD_964_2006_PTN_FM_consolidado.md"
SALIDA = RAIZ / "ict_ajp" / "datos" / "plan_radio.json"


def clave(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre)
    t = "".join(c for c in t if not unicodedata.combining(c)).upper().replace(".", " ")
    return " ".join(t.split())


def _celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def _secciones(lineas: list[str]) -> dict[str, list[str]]:
    """Trozos del texto por anexo («## ANEXO I», ...)."""
    idx = [(i, l[3:].strip()) for i, l in enumerate(lineas) if re.match(r"^## ANEXO( [IVX]+)?$", l.strip())]
    res = {}
    for k, (i, nombre) in enumerate(idx):
        fin = idx[k + 1][0] if k + 1 < len(idx) else len(lineas)
        res[nombre] = lineas[i:fin]
    return res


def _bloque(t: str) -> str:
    m = re.search(r"Bloque (\d{1,2}[A-D])", t)
    if not m:
        raise ValueError(f"Sin bloque en «{t}»")
    return m.group(1)


def leer_dab(fuente: Path = DAB) -> dict:
    lineas = fuente.read_text(encoding="utf-8").splitlines()
    texto = "\n".join(lineas)
    m = re.search(r"El bloque de frecuencias (\d+[A-D]) en red de frecuencia única de ámbito nacional, excepto en "
                  r"las Islas Canarias, donde se utilizará el bloque de frecuencias (\d+[A-D])", texto)
    fu_e = {"general": m.group(1), "canarias": m.group(2)}
    s = _secciones(lineas)

    mf_nacional = {}
    for l in s["ANEXO I"]:
        c = _celdas(l) if l.startswith("|") else []
        if len(c) == 3 and re.match(r"Bloque \d", c[1]):
            mf_nacional[clave(c[0])] = {"MF-I": _bloque(c[1]), "MF-II": _bloque(c[2])}

    fu_autonomica = {}
    for l in s["ANEXO II"]:
        c = _celdas(l) if l.startswith("|") else []
        if len(c) == 3 and re.match(r"Bloque \d", c[1]):
            m = re.search(r"(FU-[A-Z]+)", c[2])
            if not m:
                raise ValueError(f"Anexo II del plan DAB: fila sin red FU reconocible: {c}")
            fu_autonomica[m.group(1)] = {"comunidad": c[0], "bloque": _bloque(c[1])}

    mf_autonomica = {}
    red = None
    for l in s["ANEXO III"]:
        m = re.match(r"^(.*)\(red (MF-[A-Z]+)\):$", l.strip())
        if m:
            red = m.group(2)
            continue
        m = re.match(r"^([^:|#]+): Bloque (\d{1,2}[A-D])\.?$", l.strip())
        if m and red:
            mf_autonomica[clave(m.group(1))] = {"red": red, "bloque": m.group(2)}

    bloques = {}
    for l in s["ANEXO IV"]:
        c = _celdas(l) if l.startswith("|") else []
        if len(c) == 2 and re.fullmatch(r"\d{1,2}[A-D]", c[0]):
            a, b = (float(x.replace(",", ".")) for x in c[1].split("-"))
            bloques[c[0]] = [a, b]
    return {"fu_e": fu_e, "mf_nacional": mf_nacional, "fu_autonomica": fu_autonomica,
            "mf_autonomica": mf_autonomica, "bloques_mhz": bloques}


def leer_fm(fuente: Path = FM) -> dict:
    """{«MU|LORCA»: [[88.4, true], ...]}: frecuencia en MHz y si está marcada [EX] (disponible para concesión)."""
    res: dict[str, list] = {}
    for l in fuente.read_text(encoding="utf-8").splitlines():
        if not l.startswith("|"):
            continue
        c = _celdas(l)
        if len(c) == 11 and re.fullmatch(r"[A-Z]{1,2}", c[0]) and re.fullmatch(r"\d+\.\d+", c[2]):
            res.setdefault(f"{c[0]}|{clave(c[1])}", []).append([float(c[2]), c[3] == "EX"])
    return res


TDT_LOCAL = RAIZ / "docs" / "normativa" / "RD_439_2004_PTN_TDT_local_consolidado.md"
CAMBIOS_TDT_LOCAL = RAIZ / "docs" / "normativa" / "RD_391_2019_PTN_TDT_2019_consolidado.md"


def leer_tdt_local(fuente: Path = TDT_LOCAL) -> dict:
    """Demarcaciones de TDT local: {«TL04MU»: {denominacion, canal, ambito: [municipios]}}."""
    res: dict[str, dict] = {}
    actual = None
    for l in fuente.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        m = re.match(r"^Referencia: (T[LI]\d+[A-Z]+)\.?$", l)
        if m:
            actual = res.setdefault(m.group(1), {})
            continue
        if actual is None:
            continue
        if m := re.match(r"^Denominación: (.+?)\.?$", l):
            actual["denominacion"] = m.group(1)
        elif m := re.match(r"^Canal múltiple: (.+?)\.?$", l):
            actual["canal"] = int(m.group(1)) if m.group(1).isdigit() else None   # «pendiente» en el plan
        elif m := re.match(r"^Ámbito: (.+?)\.?$", l):
            partes = re.split(r", | y (?=[A-ZÁÉÍÓÚÑ])", m.group(1))
            actual["ambito"] = [p.strip() for p in partes if p.strip()]
    # RD 391/2019, disposición final tercera y anexo III: canales locales reasignados (segundo dividendo)
    lineas = CAMBIOS_TDT_LOCAL.read_text(encoding="utf-8").splitlines()
    i = next(k for k, l in enumerate(lineas) if "Modificación de canales radioeléctricos del Plan Nacional de la "
             "Televisión Digital Local" in l)
    for l in lineas[i:]:
        if l.startswith("## ANEXO IV"):
            break
        c = _celdas(l) if l.startswith("|") else []
        if len(c) == 4 and re.fullmatch(r"T[LI]\d+[A-Z]+", c[0]):
            if c[0] not in res:      # p. ej. TL09IB Menorca: no figura en el texto consolidado del RD 439/2004
                res[c[0]] = {"denominacion": c[1].title(), "ambito": []}
            res[c[0]]["canal_anterior"] = int(c[2])
            res[c[0]]["canal"] = int(c[3])
    return res


def leer() -> dict:
    return {"fuente_dab": "RD 1287/1999, Plan técnico nacional de la radiodifusión sonora digital terrestre",
            "fuente_fm": "RD 964/2006, Plan técnico nacional de radiodifusión sonora en FM, anexo II",
            "fuente_tdt_local": "RD 439/2004, Plan técnico nacional de la televisión digital local, con los canales "
                                "modificados por el RD 391/2019 (disposición final tercera y anexo III)",
            "dab": leer_dab(), "fm": leer_fm(), "tdt_local": leer_tdt_local()}


if __name__ == "__main__":
    d = leer()
    SALIDA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{SALIDA}: DAB {len(d['dab']['mf_nacional'])} provincias MF, {len(d['dab']['fu_autonomica'])} redes FU, "
          f"{len(d['dab']['mf_autonomica'])} provincias MF autonómica, {len(d['dab']['bloques_mhz'])} bloques; "
          f"FM {len(d['fm'])} localidades")
