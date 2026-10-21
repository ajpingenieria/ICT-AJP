"""Pruebas de la lectura del DXF con un plano inventado (nunca con planos de clientes)."""

import ezdxf
import pytest

from ict_ajp.leer_dxf import (clasificar_estancia, informe, leer_plano, normalizar, proyecto_desde_lectura,
                              _nombre_planta)
from ict_ajp.modelo import TipoEstancia

H = 0.1   # altura de los rótulos


def _rotulo(msp, nombre, sup, x, y, capa="0-TEXTOS"):
    msp.add_text(nombre, height=H, dxfattribs={"layer": capa, "insert": (x, y)})
    msp.add_text(sup, height=H, dxfattribs={"layer": capa, "insert": (x, y - 0.12)})


def _vivienda(msp, x0, y0, ancho=6.0, fondo=10.0):
    pts = [(x0, y0), (x0 + ancho, y0), (x0 + ancho, y0 + fondo), (x0, y0 + fondo)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "0-AREA CONST"})


def _titulo(msp, texto, x, y=0.0):
    msp.add_text(texto, height=0.25, dxfattribs={"layer": "0-TEXTOS", "insert": (x, y)})
    msp.add_text("ESCALA 1/50", height=0.1, dxfattribs={"layer": "0-TEXTOS", "insert": (x, y - 0.21)})


@pytest.fixture
def plano(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    # Planta baja: portal y RITU, sin viviendas
    _titulo(msp, "PLANTA BAJA COTAS Y SUPERFICIES", 0)
    _rotulo(msp, "ZAGUAN", "10,00 m²", 2, 5)
    msp.add_text("R.I.T.U.", height=H, dxfattribs={"layer": "0-TEXTOS", "insert": (3, 7)})
    msp.add_text("0.60 m²", height=H, dxfattribs={"layer": "0-TEXTOS", "insert": (3.4, 7)})
    _rotulo(msp, "TRASTERO 1", "2,50 m²", 5, 5)
    # Planta tipo (1ª y 2ª): dos viviendas
    _titulo(msp, "PLANTA TIPO (1ª Y 2ª) COTAS Y SUPERFICIES", 20)
    _vivienda(msp, 20, 1)
    _vivienda(msp, 27, 1)
    for x0, letra in ((20, "A"), (27, "B")):
        _rotulo(msp, "SALON-COMEDOR", "22,00 m²", x0 + 1, 9)
        _rotulo(msp, "DORM. 1", "12,00 m²", x0 + 1, 6)
        _rotulo(msp, "COCINA", "9,00 m²", x0 + 4, 9)
        _rotulo(msp, "BAÑO", "4,00 m²", x0 + 4, 6)
        _rotulo(msp, "PASO", "5,00 m²", x0 + 4, 3)
        msp.add_text(letra, height=H, dxfattribs={"insert": (x0 + 5.5, 2)})
    # Anotación de cotas junto a un dormitorio: no debe tomarse como nombre
    msp.add_text("Sup. huecos estancia", height=H * 0.6, dxfattribs={"layer": "0-COTAS", "insert": (21, 5.92)})
    # La misma planta en otra vista con menos rótulos: se descarta
    _titulo(msp, "PLANTA TIPO (1ª Y 2ª) DISTRIBUCION", 40)
    _rotulo(msp, "SALON", "21,00 m²", 41, 9)
    # Ático: una vivienda de un dormitorio y un estar-cocina
    _titulo(msp, "PLANTA ATICO COTAS Y SUPERFICIES", 60)
    _vivienda(msp, 60, 1, ancho=8)
    _rotulo(msp, "SALON-COCINA-COMEDOR", "25,00 m²", 61, 9)
    _rotulo(msp, "DORM. 1", "11,00 m²", 61, 5)
    _rotulo(msp, "ARM. TELEC.", "0,37 m²", 66, 5)
    _rotulo(msp, "TERRAZA", "15,00 m²", 70, 5)      # fuera del contorno de la vivienda
    ruta = tmp_path / "plano.dxf"
    doc.saveas(ruta)
    return leer_plano(ruta)


def test_plantas_y_niveles(plano):
    assert [(p.nombre, p.nivel) for p in plano.plantas] == [
        ("PLANTA BAJA", 0), ("PLANTA PRIMERA", 1), ("PLANTA SEGUNDA", 2), ("PLANTA ATICO", 3)]
    assert "PLANTA TIPO (1ª Y 2ª) DISTRIBUCION" in plano.titulos_descartados


def test_viviendas_y_estancias(plano):
    pb, p1, p2, at = plano.plantas
    assert pb.viviendas == []
    assert {e.nombre for e in pb.otras_estancias} == {"ZAGUAN", "R.I.T.U.", "TRASTERO 1"}
    assert len(p1.viviendas) == len(p2.viviendas) == 2
    v = p1.viviendas[0]
    assert v.superficie_construida_m2 == 60.0
    assert sorted(e.nombre for e in v.estancias) == ["BAÑO", "COCINA", "DORM. 1", "PASO", "SALON-COMEDOR"]
    assert sum(1 for e in v.estancias if e.computa) == 3       # salón, dormitorio y cocina
    assert p1.letras_puertas == ["A", "B"]
    assert [e.nombre for e in at.viviendas[0].estancias if e.computa] == ["SALON-COCINA-COMEDOR", "DORM. 1"]
    assert "TERRAZA" in {e.nombre for e in at.otras_estancias}


def test_elementos_telecomunicaciones(plano):
    assert {(e.texto, e.planta, e.superficie_m2) for e in plano.telecomunicaciones} == {
        ("R.I.T.U.", "PLANTA BAJA", 0.60), ("ARM. TELEC.", "PLANTA ATICO", 0.37)}
    assert plano.ascensores == []
    assert "Planta ático (nivel 3)" in informe(plano)


def test_borrador_de_proyecto(plano):
    p = proyecto_desde_lectura(plano)
    assert [(pl.nombre, pl.nivel, pl.es_atico) for pl in p.edificio.plantas] == [
        ("Planta baja", 0, False), ("Planta 1ª", 1, False), ("Planta 2ª", 2, False), ("Planta ático", 3, True)]
    assert [u.id for _, u in p.edificio.usuarios()] == ["1ºA", "1ºB", "2ºA", "2ºB", "Ático A"]
    u = p.edificio.plantas[1].usuarios[0]
    assert u.tipologia == "Tipo 1" and p.edificio.plantas[3].usuarios[0].tipologia == "Tipo 2"
    assert [e.nombre for e in u.estancias_computables()] == ["SALON-COMEDOR", "DORM. 1", "COCINA"]
    assert [e.nombre for e in u.estancias if e.principal] == ["SALON-COMEDOR", "DORM. 1"]
    seguidas = proyecto_desde_lectura(plano, "letras_seguidas")
    assert [u.id for _, u in seguidas.edificio.usuarios()] == ["A", "B", "C", "D", "E"]


@pytest.mark.parametrize("nombre, tipo, computa", [
    ("SALON-COMEDOR", TipoEstancia.salon, True),
    ("Salón-cocina-comedor", TipoEstancia.salon, True),
    ("DORM. 3", TipoEstancia.dormitorio, True),
    ("COCINA", TipoEstancia.cocina, True),
    ("BAÑO", TipoEstancia.bano, False),
    ("ASEO", TipoEstancia.aseo, False),
    ("TRASTERO 4", TipoEstancia.trastero, False),
    ("VESTIBULO", TipoEstancia.otra, False),
    ("LAVADERO", TipoEstancia.otra, False),
    ("PATIO USO PRIVATIVO VIV. A", TipoEstancia.otra, False),
    ("BODEGA", TipoEstancia.otra, None),
])
def test_clasificar_estancia(nombre, tipo, computa):
    t, c, _ = clasificar_estancia(nombre)
    assert (t, c) == (tipo, computa)


def test_nombre_planta():
    assert normalizar("Planta ático (2ª)") == "PLANTA ATICO (2A)"
    assert _nombre_planta("PL. TIPO (2ª Y 3ª) ACCESIBILIDAD") == ("PLANTA TIPO", [2, 3], None)
    assert _nombre_planta("PLANTA PRIMERA DISTRIBUCION") == ("PLANTA PRIMERA", None, 1)
    assert _nombre_planta("PLANTA BAJA") == ("PLANTA BAJA", None, 0)
    assert _nombre_planta("PL. CUBIERTA")[2] is None
