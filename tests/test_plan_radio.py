"""Radio (DAB, FM) y TDT local: el JSON de la app coincide con los planes técnicos de docs/normativa."""

import importlib.util
import json
from pathlib import Path

from ict_ajp import plan_radio as R

RAIZ = Path(__file__).parent.parent


def test_json_coincide_con_los_textos_oficiales():
    spec = importlib.util.spec_from_file_location("gen", RAIZ / "herramientas" / "generar_plan_radio.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    app = json.loads((RAIZ / "ict_ajp" / "datos" / "plan_radio.json").read_text(encoding="utf-8"))
    assert app == gen.leer()


def test_dab_murcia():                     # RD 1287/1999: art. 3.1.a y anexos I a IV
    b = {x.red: (x.bloque, x.f_min_mhz, x.f_max_mhz) for x in R.bloques_dab("Murcia")}
    assert b == {"FU-E": ("11B", 217.872, 219.408), "MF-I": ("9C", 205.584, 207.12),
                 "MF-II": ("10D", 214.304, 215.84), "MF-MUR": ("10B", 210.88, 212.416),
                 "FU-MUR": ("11A", 216.16, 217.696)}
    assert R.bloques_dab("Tenerife")[0].bloque == "11D"                      # FU-E en Canarias
    assert all(195 <= x.f_min_mhz < x.f_max_mhz <= 223 for x in R.bloques_dab("Madrid"))


def test_fm_lorca():                       # RD 964/2006, anexo II
    assert R.emisoras_fm("Lorca") == [(88.4, True), (93.5, False), (94.0, True), (95.3, False), (97.4, True)]
    assert R.emisoras_fm("Lorca", pv="AL") == []


def test_tdt_local_lorca():                # RD 439/2004
    d = R.demarcacion_tdt_local("Águilas")
    assert (d.referencia, d.denominacion, d.canal, d.canal_anterior) == ("TL04MU", "Lorca", 37, 39)  # RD 391/2019
    assert R.demarcacion_tdt_local("Alcantarilla").canal_anterior is None   # TL06MU Murcia: sin cambio
    assert "Puerto Lumbreras" in d.ambito
    assert R.demarcacion_tdt_local("Baena").canal is None                   # «Canal múltiple: Pendiente*»
    assert R.demarcacion_tdt_local("Municipio inexistente") is None
