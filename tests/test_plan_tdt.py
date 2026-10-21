"""Canales de TDT del RD 250/2025: el JSON de la app coincide con el texto oficial de docs/normativa."""

import importlib.util
import json
from pathlib import Path

import pytest

from ict_ajp import normativa as N
from ict_ajp import plan_tdt as P
from ict_ajp.dimensionado import dimensionar
from ict_ajp.modelo import Proyecto

RAIZ = Path(__file__).parent.parent
EJEMPLO = RAIZ / "ejemplos" / "edificio_prueba.ict.json"


def test_json_coincide_con_el_texto_oficial():
    spec = importlib.util.spec_from_file_location("gen", RAIZ / "herramientas" / "generar_plan_tdt.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    oficial = gen.leer()
    app = json.loads((RAIZ / "ict_ajp" / "datos" / "plan_tdt.json").read_text(encoding="utf-8"))
    assert app == oficial
    assert len(app["areas"]) == 75


def test_areas_y_canales():
    lorca = P.municipio("Lorca")
    assert (lorca.ine, lorca.area.numero, lorca.area.nombre) == ("30024", 54, "Murcia Sur")
    assert lorca.area.canales == {"RGE1": 38, "RGE2": 45, "MPE1": 42, "MPE2": 39, "MPE3": 44,
                                  "MPE4": 36, "MPE5": 35, "MAUT": 29}
    assert P.municipio(ine="30022").area.nombre == "Murcia Norte"            # Jumilla
    assert P.municipio("Las Torres de Cotillas").ine == "30038"              # «Torres de Cotillas (Las)»
    assert P.municipio("murcia").ine == "30030"
    assert P.municipio("No existe") is None


def test_frecuencias_y_campo_minimo():
    assert P.frecuencia_central_mhz(21) == 474.0                             # 470-478 MHz
    assert P.frecuencia_central_mhz(48) == 690.0                             # 686-694 MHz
    with pytest.raises(ValueError):
        P.frecuencia_central_mhz(49)                                         # fuera de 470-694 MHz
    assert N.campo_minimo_tdt(470.0).valor == 56.4                          # 3 + 20 log 470
    assert N.campo_minimo_tdt(666.0).valor == 59.5
    with pytest.raises(ValueError):
        N.campo_minimo_tdt(469.9)


def test_banda_ancha_limite_30_tomas():                                     # Anexo I 4.3: «inferior a 30»
    assert N.admite_banda_ancha(29).valor is True
    assert N.admite_banda_ancha(30).valor is False


def test_seccion_rtv_en_el_ejemplo():
    p = Proyecto.cargar(EJEMPLO)
    r = dimensionar(p)
    s = r.seccion("rtv")
    assert next(x for x in s.partidas if x.concepto.startswith("Área geográfica")).valor == "n.º 54 Murcia Sur"
    canales = [f[1] for f in s.tablas[0].filas]
    assert canales == [29, 35, 36, 38, 39, 42, 44, 45]
    assert "monocanal" in next(x for x in s.partidas if x.concepto == "Tipo de cabecera").valor
    assert any(a.nivel == "decision" and "3 + 20 log f" in a.texto for a in r.avisos)
    p.rtv.campos_medidos_dbuvm = {"45": 70.0}
    fila = next(f for f in dimensionar(p).seccion("rtv").tablas[0].filas if f[1] == 45)
    assert fila[4:6] == [70.0, "medido"]
    p.datos_generales.municipio = "Inventado"
    assert any("No se encuentra el municipio" in a.texto for a in dimensionar(p).avisos)
