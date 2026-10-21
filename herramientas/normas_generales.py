"""Comprueba en el BOE (datos abiertos) el título oficial y la vigencia de las normas generales que se citan
en el pliego de condiciones, y los guarda en docs/normativa/normas_generales.json.

Así ninguna cita sale de memoria (CLAUDE.md, regla 1): título, identificador y si sigue vigente son los del BOE.

Uso: python herramientas/normas_generales.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "normativa" / "normas_generales.json"
API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada"

# (clave, rango, número oficial, materia del pliego, apartado de la Orden ITC/1644/2011, anexo I)
NORMAS = [
    ("rdl_1_1998", "Real Decreto-ley", "1/1998", "Reglamento de ICT y normas anexas", "3.2.A"),
    ("rd_346_2011", "Real Decreto", "346/2011", "Reglamento de ICT y normas anexas", "3.2.A"),
    ("orden_itc_1644_2011", "Orden", "ITC/1644/2011", "Reglamento de ICT y normas anexas", "3.2.A"),
    ("orden_ece_983_2019", "Orden", "ECE/983/2019", "Reglamento de ICT y normas anexas", "3.2.A"),
    ("ley_11_2022", "Ley", "11/2022", "Secreto de las comunicaciones", "3.2.D"),
    ("ley_31_1995", "Ley", "31/1995", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_39_1997", "Real Decreto", "39/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_1627_1997", "Real Decreto", "1627/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_485_1997", "Real Decreto", "485/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_486_1997", "Real Decreto", "486/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_487_1997", "Real Decreto", "487/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_773_1997", "Real Decreto", "773/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_1215_1997", "Real Decreto", "1215/1997", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_614_2001", "Real Decreto", "614/2001", "Prevención de riesgos laborales", "3.2.B"),
    ("rd_1066_2001", "Real Decreto", "1066/2001", "Protección contra campos electromagnéticos", "3.2.C"),
    ("rd_186_2016", "Real Decreto", "186/2016", "Compatibilidad electromagnética", "3.2.C"),
    ("rd_1580_2006", "Real Decreto", "1580/2006", "Compatibilidad electromagnética", "3.2.C"),
    ("rd_105_2008", "Real Decreto", "105/2008", "Gestión de residuos", "3.2.E"),
    ("ley_7_2022", "Ley", "7/2022", "Gestión de residuos", "3.2.E"),
    ("rd_314_2006", "Real Decreto", "314/2006", "Protección contra incendios (CTE)", "3.2.F"),
    ("rd_842_2002", "Real Decreto", "842/2002", "Seguridad eléctrica (REBT)", "3.2.A"),
]


def buscar(rango: str, numero: str) -> dict | None:
    q = {"query": {"query_string": {"query": f'numero_oficial:"{numero}" and rango:"{rango}"'}}}
    url = f"{API}?query={urllib.parse.quote(json.dumps(q))}&limit=5"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = json.loads(r.read().decode("utf-8")).get("data", [])
    for d in datos:
        if d.get("numero_oficial") == numero and d.get("rango", {}).get("texto") == rango \
                and d.get("ambito", {}).get("texto") == "Estatal":
            return d
    return None


def main() -> int:
    res, faltan = {}, []
    for clave, rango, numero, materia, apartado in NORMAS:
        d = buscar(rango, numero)
        if not d:
            faltan.append(f"{rango} {numero}")
            continue
        res[clave] = {"identificador": d["identificador"], "titulo": d["titulo"].rstrip("."),
                      "vigente": d.get("vigencia_agotada") == "N", "materia": materia, "apartado_pliego": apartado,
                      "url": d.get("url_html_consolidada") or d.get("url_eli")}
    salida = {"consulta": dt.date.today().isoformat(), "fuente": API, "normas": res}
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res.items():
        print(("VIGENTE  " if v["vigente"] else "DEROGADA ") + v["titulo"][:110])
    if faltan:
        print("NO ENCONTRADAS:", ", ".join(faltan))
    return 1 if faltan else 0


if __name__ == "__main__":
    sys.exit(main())
