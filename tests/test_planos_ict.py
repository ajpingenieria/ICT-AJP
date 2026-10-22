"""Pruebas de las plantas de la ICT con un plano inventado (nunca con planos de clientes)."""

import ezdxf
import pytest
from ezdxf.math import Vec2, is_point_in_polygon_2d

from ict_ajp.leer_dxf import leer_plano, proyecto_desde_lectura
from ict_ajp.planos_ict import (CAPAS, ESCALAS, RETRANQUEO, _dist_segmento, _junto_a_pared, _partir,
                                datos_cajetin, generar_planos, resumen_longitudes, vistas_ict)

H = 0.1

# Estancias de la vivienda: nombre, superficie rotulada, recinto (x0, y0, x1, y1)
ESTANCIAS = [
    ("VESTIBULO", "4,00 m²", (1.2, 1.2, 3.2, 3.2)),
    ("BAÑO", "4,00 m²", (3.4, 1.2, 5.8, 3.2)),
    ("SALON-COMEDOR", "24,00 m²", (1.2, 3.4, 5.8, 8.8)),
    ("COCINA", "9,00 m²", (6.0, 1.2, 8.8, 4.8)),
    ("DORM. 1", "10,00 m²", (6.0, 5.0, 8.8, 8.8)),
]


def _caja(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _estancia(msp, nombre, sup, caja, dx=0.0):
    x0, y0, x1, y1 = caja
    msp.add_lwpolyline(_caja(x0 + dx, y0, x1 + dx, y1), close=True, dxfattribs={"layer": "0-AREA UTIL"})
    cx, cy = (x0 + x1) / 2 + dx - 0.3, (y0 + y1) / 2
    msp.add_text(nombre, height=H, dxfattribs={"layer": "0-TEXTOS", "insert": (cx, cy)})
    msp.add_text(sup, height=H, dxfattribs={"layer": "0-TEXTOS", "insert": (cx, cy - 0.12)})


def _titulo(msp, texto, x, y=0.0):
    msp.add_text(texto, height=0.25, dxfattribs={"layer": "0-TEXTOS", "insert": (x, y)})
    msp.add_text("ESCALA 1/50", height=0.1, dxfattribs={"layer": "0-TEXTOS", "insert": (x, y - 0.21)})


@pytest.fixture
def base(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    # Planta primera: una vivienda y el rellano
    _titulo(msp, "PLANTA PRIMERA COTAS Y SUPERFICIES", 0)
    msp.add_lwpolyline(_caja(1, 1, 9, 9), close=True, dxfattribs={"layer": "0-AREA CONST"})
    msp.add_lwpolyline(_caja(0.9, 0.9, 9.1, 9.1), close=True, dxfattribs={"layer": "0-MUROS"})
    for nombre, sup, caja in ESTANCIAS:
        _estancia(msp, nombre, sup, caja)
    _estancia(msp, "E. COMUN", "6,00 m²", (9.4, 1.2, 12.0, 4.0))
    # Planta baja: zaguán y RITI
    _titulo(msp, "PLANTA BAJA COTAS Y SUPERFICIES", 30)
    msp.add_lwpolyline(_caja(30.9, 0.9, 39.1, 9.1), close=True, dxfattribs={"layer": "0-MUROS"})
    _estancia(msp, "ZAGUAN", "20,00 m²", (31.2, 1.2, 38.8, 8.8))
    _estancia(msp, "R.I.T.I.", "0,60 m²", (31.4, 7.9, 32.6, 8.4))
    # Marco de la lámina del arquitecto: no se copia
    msp.add_lwpolyline(_caja(-2, -2, 50, 14), close=True, dxfattribs={"layer": "0-CAJETIN"})
    ruta = tmp_path / "base.dxf"
    doc.saveas(ruta)
    return ruta


@pytest.fixture
def planos(base, tmp_path):
    lectura = leer_plano(base)
    proyecto = proyecto_desde_lectura(lectura)
    res = generar_planos(base, lectura, proyecto, tmp_path / "planos.dxf", datos_cajetin(proyecto),
                         holgura_vertical_m=1.0, imagenes=False, pdf=False)
    return res, ezdxf.readfile(res.ruta), proyecto


def _registros(doc, cod=None):
    return [(Vec2(i.dxf.insert), i.get_attrib_text("COD")) for i in doc.modelspace().query("INSERT")
            if i.dxf.name == "ICT_REG" and (cod is None or i.get_attrib_text("COD") == cod)]


def test_vistas_y_hojas(base, planos):
    res, doc, _ = planos
    assert [v.titulo for v in vistas_ict(leer_plano(base))] == ["Planta baja", "Planta primera"]
    assert res.presentaciones == ["ICT-1 Planta baja", "ICT-2 Planta primera"]
    assert res.escala in ESCALAS
    for nombre in res.presentaciones:
        hoja = doc.layout(nombre)
        assert (hoja.dxf.paper_width, hoja.dxf.paper_height) == (420, 297)
        assert any(t.dxf.text == f"1:{res.escala}" for t in hoja.query("TEXT"))
    assert all(capa in doc.layers for capa in CAPAS)


def test_no_se_copia_el_marco_del_arquitecto(planos):
    _, doc, _ = planos
    capas = {e.dxf.layer for e in doc.modelspace()}
    assert "0-CAJETIN" not in capas
    assert {"0-AREA UTIL", "0-MUROS", "0-TEXTOS"} <= capas


def test_registros_junto_a_la_pared_de_su_estancia(planos):
    _, doc, _ = planos
    computables = [e for e in ESTANCIAS if e[0] in ("SALON-COMEDOR", "COCINA", "DORM. 1")]
    tv = _registros(doc, "TV")
    assert len(tv) == len(computables)                 # un registro de RTV por estancia que cuenta
    for _, _, caja in computables:
        poli = [Vec2(p) for p in _caja(*caja)]
        dentro = [q for q, _ in _registros(doc) if is_point_in_polygon_2d(q, poli) > 0]
        assert dentro, caja
        for q in dentro:                               # pegados a una pared, no en medio de la estancia
            d = min(_dist_segmento(q, a, b) for a, b in zip(poli, poli[1:] + poli[:1]))
            assert d == pytest.approx(RETRANQUEO, abs=0.01)
    salon = [Vec2(p) for p in _caja(*ESTANCIAS[2][2])]
    assert sorted(c for q, c in _registros(doc) if is_point_in_polygon_2d(q, salon) > 0) == [
        "FO", "PT", "PT", "TB", "TV"]


def test_rtr_y_toma_configurable_en_el_vestibulo(planos):
    _, doc, _ = planos
    vest = [Vec2(p) for p in _caja(*ESTANCIAS[0][2])]
    rtr = [Vec2(i.dxf.insert) for i in doc.modelspace().query("INSERT") if i.dxf.name == "ICT_RTR"]
    assert len(rtr) == 1 and is_point_in_polygon_2d(rtr[0], vest) > 0
    conf = [q for q, _ in _registros(doc, "C")]
    assert len(conf) == 1 and conf[0].distance(rtr[0]) < 1.0       # en la cercanía del PAU (Anexo II, 3.5 c)
    rs = [Vec2(i.dxf.insert) for i in doc.modelspace().query("INSERT") if i.dxf.name == "ICT_RS"]
    assert len(rs) == 1 and is_point_in_polygon_2d(rs[0], [Vec2(p) for p in _caja(9.4, 1.2, 12.0, 4.0)]) > 0


def test_recinto_y_arqueta_de_entrada(planos):
    _, doc, _ = planos
    msp = doc.modelspace()
    recintos = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == "ICT_RECINTOS"]
    assert len(recintos) == 1
    assert any(t.dxf.text == "RITI" for t in msp.query("TEXT"))
    arqueta = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == "ICT_ACOMETIDA"]
    assert len(arqueta) == 1
    centro = sum((Vec2(p) for p in arqueta[0].get_points("xy")), Vec2()) / 4
    assert not is_point_in_polygon_2d(centro, [Vec2(p) for p in _caja(30.9, 0.9, 39.1, 9.1)]) > 0  # fuera


def test_canalizacion_principal_en_la_misma_vertical(planos):
    _, doc, _ = planos
    cps = [Vec2(i.dxf.insert) for i in doc.modelspace().query("INSERT") if i.dxf.name == "ICT_CP"]
    assert len(cps) == 3            # en la planta primera, a la salida del RITI y al pie de la vertical
    primera = min(cps, key=lambda q: q.x)
    # Las vistas están a 30 m entre títulos: el pie de la vertical en planta baja cae en el mismo sitio
    assert any(q.isclose(primera + Vec2(30, 0), abs_tol=1e-6) for q in cps)


def test_mediciones_para_el_calculo_de_rtv(planos):
    res, _, proyecto = planos
    assert len(res.mediciones) == 1
    m = res.mediciones[0]
    assert m.vivienda == proyecto.edificio.plantas[1].usuarios[0].id
    assert m.secundaria_m > 2.0                         # recorrido en planta + 2 x 1 m de holgura
    assert len(m.interior_m) == 3 and all(x > 2.0 for x in m.interior_m)
    r = resumen_longitudes(res.mediciones)
    assert r["interior_min"] == min(m.interior_m) and r["acometida_max"] == m.secundaria_m


def test_junto_a_pared_elige_la_pared_mas_cercana():
    poli = _caja(0, 0, 4, 3)
    (x, y), u, n = _junto_a_pared(poli, (2.0, 0.6), 1.0)
    assert (x, y) == pytest.approx((2.0, RETRANQUEO)) and n == pytest.approx((0, 1))
    (x, y), _, _ = _junto_a_pared(poli, (2.0, 0.6), 1.0, hacia=(10.0, 1.5))   # hacia la puerta de la derecha
    assert (x, y) == pytest.approx((4 - RETRANQUEO, 1.5))


def test_textos_del_cajetin_caben_en_su_celda():
    lineas = _partir("Proyecto Telecomunicaciones Edificio 8 Viviendas, Trasteros y Garajes", 41.0, 1.8)
    assert len(lineas) >= 2 and " ".join(lineas).startswith("Proyecto Telecomunicaciones")


def test_pdf_de_las_hojas(base, tmp_path):
    from pypdf import PdfReader
    lectura = leer_plano(base)
    proyecto = proyecto_desde_lectura(lectura)
    res = generar_planos(base, lectura, proyecto, tmp_path / "p.dxf", datos_cajetin(proyecto), imagenes=False)
    paginas = PdfReader(res.pdf).pages
    assert len(paginas) == 2
    assert float(paginas[0].mediabox.width) == pytest.approx(420 / 25.4 * 72, abs=1)     # A3 apaisado
