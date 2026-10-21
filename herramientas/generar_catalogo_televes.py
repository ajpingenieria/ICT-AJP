"""Genera ict_ajp/catalogos/televes.json desde las fichas oficiales de Televés (PDF descargados).

Las fichas no se guardan en el repositorio (son documentos del fabricante): solo las cifras, cada una
con la referencia del producto y la URL de su ficha, para poder comprobarlas.

Uso: python herramientas/generar_catalogo_televes.py carpeta_pdf [fecha_consulta AAAA-MM-DD]
  - ficha_<ref>.pdf: ficha de producto de https://global.televes.com/pdf/index.php?store=es&sku=<ref>
  - tec_<ref>.pdf: «Especificaciones técnicas» de https://www.televes.com/downloadfile/...
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leer_fichas_televes import _decodificar, leer_ficha  # noqa: E402
from pypdf import PdfReader  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "ict_ajp" / "catalogos" / "televes.json"
URL_FICHA = "https://global.televes.com/pdf/index.php?store=es&sku={}"
URL_TEC = {
    "414002": "https://www.televes.com/downloadfile/TEC05210233_20_Espanol_1444153.pdf/technical_specifications_es_ES_TEC05210233_414002.pdf",
    "527601": "https://www.televes.com/downloadfile/TEC08260000_2_Espanol_1673006.pdf/technical_specifications_es_ES_TEC08260000_527601.pdf",
    "5230": "https://www.televes.com/downloadfile/TEC12210017_186_Espanol_1671966.pdf/technical_specifications_es_ES_TEC12210017.pdf",
    "5228": "https://www.televes.com/downloadfile/TEC12210013_188_Espanol_1671922.pdf/technical_specifications_es_ES_TEC12210013.pdf",
    "5229": "https://www.televes.com/downloadfile/TEC12210016_181_Espanol_1671955.pdf/technical_specifications_es_ES_TEC12210016.pdf",
}
URL_TEC_AMP = {
    "509812": "https://www.televes.com/downloadfile/TEC05240008_4_Espanol_1717264.pdf/technical_specifications_es_ES_TEC05240008_509812.pdf",
    "509012": "https://www.televes.com/downloadfile/TEC05240007_4_Espanol_1717250.pdf/technical_specifications_es_ES_TEC05240007_509012.pdf",
}
NOMBRES_TEC = {"414002": "Cable coaxial SK2003plus (T100A+), Euroclase Dca, blindaje clase A+",
               "527601": "Toma terminal separadora ICT 2 conectores 5...694 MHz (FM/TV) - 950...2400 MHz (SAT)",
               "5230": "Toma terminal 2 conectores FM-TV",
               "5228": "Toma de paso 2 conectores FM/TV-SAT (planta 2)",
               "5229": "Toma terminal 2 conectores FM/TV-SAT (planta 1)"}


def _num(t: str) -> float:
    return float(t.replace(",", ".").replace(">", "").replace("<", "").strip())


def _fila(filas: list[str], etiqueta: str) -> list[str] | None:
    """Valores de la fila que empieza por la etiqueta (sin la unidad)."""
    for f in filas:
        if f.startswith(etiqueta):
            resto = f[len(etiqueta):].strip()
            resto = re.sub(r"^(dBi|dBµV|dB|MHz|mA|Vdc|W|A|°C)\s+", "", resto)
            return re.findall(r"[<>]?\s?-?\d+(?:,\d+)?(?:\s\.\.\.\s\d+(?:,\d+)?)?|--", resto)
    return None


def _leer_tec(ruta: Path) -> list[str]:
    texto = "\n".join(_decodificar(p.extract_text() or "") for p in PdfReader(str(ruta)).pages)
    return [" ".join(l.split()) for l in texto.splitlines() if l.strip() and "Especificaciones técnicas" not in l]


def generar(carpeta: Path, fecha: str) -> dict:
    fichas = {}
    for pdf in carpeta.glob("ficha_*.pdf"):
        try:
            f = leer_ficha(pdf)
            fichas[f["ref"]] = f
        except Exception:
            pass                       # fichas cortadas por el servidor: se usan las «tec_»
    cat: dict = {"fabricante": "Televés", "fecha_consulta": fecha, "antenas": [], "amplificadores": [],
                 "fuentes": [], "derivadores": [], "repartidores": [], "tomas": [], "cables": []}

    def fuente(ref: str) -> str:
        return URL_TEC.get(ref) or URL_FICHA.format(ref)

    for ref, f in sorted(fichas.items()):
        e = f["especificaciones"]
        nombre = f["nombre"].rstrip(": ")
        if nombre.startswith("Antena"):
            margen = _fila(e, "Margen de frecuencia")
            g = _fila(e, "Ganancia")
            cat["antenas"].append({"ref": ref, "nombre": nombre, "margen_mhz": margen[0] if margen else None,
                                   "ganancia_dbi": _num(g[-1]),   # DAT BOSS: modo pasivo (OFF) es la última
                                   "ganancia_activa_dbi": _num(g[0]) if len(g) > 1 else None,
                                   "fuente": fuente(ref)})
        elif nombre.startswith("Amplificador"):
            bandas = (_fila(e, "Bandas") or [])
            # La figura de ruido solo está en las «Especificaciones técnicas» (tec_<ref>.pdf)
            tec = carpeta / f"tec_{ref}.pdf"
            fr = _fila(_leer_tec(tec), "Figura de ruido") if tec.exists() else None
            cat["amplificadores"].append({
                "ref": ref, "nombre": nombre, "bandas": next(x for x in e if x.startswith("Bandas"))[7:].split(),
                "ganancia_db": [_num(x) for x in _fila(e, "Ganancia")],
                "nivel_salida_en50083_dbuv": [_num(x) for x in _fila(e, "Nivel de salida EN50083")],
                "figura_ruido_max_db": _num(fr[0]) if fr else None,
                "corriente_ma": _num(_fila(e, "Corriente máx.")[0]),
                "fuente": fuente(ref) + (f" ; {URL_TEC_AMP[ref]}" if ref in URL_TEC_AMP else "")})
            del bandas
        elif nombre.startswith("Fuente"):
            cat["fuentes"].append({"ref": ref, "nombre": nombre, "tension_v": _num(_fila(e, "Voltaje de salida")[0]),
                                   "corriente_a": _num(_fila(e, "Corriente máx. de salida")[0]), "fuente": fuente(ref)})
        elif nombre.startswith("Derivador"):
            paso = _fila(e, "Pérdidas de paso")
            der = _fila(e, "Pérdidas de derivación")
            cat["derivadores"].append({
                "ref": ref, "nombre": nombre, "salidas": int(_fila(e, "Número de salidas")[0]),
                "terminal": paso is None, "derivacion_db": {"terr": _num(der[0]), "sat": _num(der[1])},
                "paso_db": {"terr": _num(paso[0]), "sat": _num(paso[1])} if paso else None, "fuente": fuente(ref)})
        elif nombre.startswith("Repartidor"):
            p = _fila(e, "Pérdidas de paso")
            cat["repartidores"].append({"ref": ref, "nombre": nombre, "salidas": int(_fila(e, "Número de salidas")[0]),
                                        "pau": "PAU" in nombre, "perdida_db": {"terr": _num(p[0]), "sat": _num(p[1])},
                                        "fuente": fuente(ref)})
    for ref in sorted(URL_TEC):
        ruta = carpeta / f"tec_{ref}.pdf"
        e = _leer_tec(ruta)
        if ref == "414002":
            aten = {}
            for fila in e:
                m = re.match(r"Atenuación (\d+)MHz dB/m ([\d,]+)", fila)
                if m:
                    aten[int(m.group(1))] = _num(m.group(2))
            cat["cables"].append({"ref": ref, "nombre": NOMBRES_TEC[ref], "atenuacion_db_m": aten,
                                  "fuente": fuente(ref)})
            continue
        bandas = next(x for x in e if x.startswith("Bandas"))[7:].split()
        toma = {"ref": ref, "nombre": NOMBRES_TEC[ref], "bandas": bandas,
                "paso": "Salida de paso Si" in e, "atenuacion_db": {},
                "paso_db": None, "fuente": fuente(ref)}
        for fila in e:
            m = re.match(r"Atenuación: Conector (\S+) dB (.+)$", fila)
            if m:
                vals = [v for v in re.findall(r"\d+(?:,\d+)?|--", m.group(2))]
                for banda, v in zip(bandas, vals):
                    if v != "--":
                        toma["atenuacion_db"][banda] = _num(v)
        p = _fila(e, "Pérdidas de paso")
        if p:
            toma["paso_db"] = dict(zip(bandas, (_num(x) for x in p)))
        cat["tomas"].append(toma)
    for k in ("derivadores", "repartidores"):
        cat[k].sort(key=lambda d: (d["salidas"], d["ref"]))
    return cat


if __name__ == "__main__":
    carpeta = Path(sys.argv[1])
    fecha = sys.argv[2] if len(sys.argv) > 2 else ""
    cat = generar(carpeta, fecha)
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{SALIDA}: " + ", ".join(f"{len(v)} {k}" for k, v in cat.items() if isinstance(v, list)))
