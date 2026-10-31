"""Pruebas de las plantas de la ICT con un plano inventado (nunca con planos de clientes)."""

import math

import ezdxf
import pytest
from ezdxf.math import Vec2, is_point_in_polygon_2d

from ict_ajp.leer_dxf import leer_plano, proyecto_desde_lectura
from ict_ajp.planos_ict import (CAPAS, ESCALAS, TOMA, _caja_texto, _corta, _dist_segmento, _junto_a_pared,
                                _partir, datos_cajetin, generar_planos, resumen_longitudes, vistas_ict)

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


def _centro(i, etiqueta="COD"):
    """Centro del símbolo: donde va su texto (el bloque se inserta en la cara de la pared)."""
    return Vec2(i.get_attrib(etiqueta).dxf.align_point)


def _registros(doc, cod=None):
    return [(_centro(i), i.get_attrib_text("COD")) for i in doc.modelspace().query("INSERT")
            if i.dxf.name == "ICT_TOMA" and (cod is None or i.get_attrib_text("COD") == cod)]


def test_vistas_y_hojas(base, planos):
    res, doc, _ = planos
    assert [v.titulo for v in vistas_ict(leer_plano(base))] == ["Planta baja", "Planta primera"]
    assert res.presentaciones == ["ICT-1 Planta baja", "ICT-2 Planta primera", "ICT-3 Esquema general",
                                  "ICT-4 Esquema RTV", "ICT-5 Esquema pares trenzados", "ICT-6 Esquema coaxial",
                                  "ICT-7 Esquema fibra óptica"]
    assert res.escala in ESCALAS
    for k, nombre in enumerate(res.presentaciones):
        hoja = doc.layout(nombre)
        assert (hoja.dxf.paper_width, hoja.dxf.paper_height) == (420, 297)
        escala = f"1:{res.escala}" if k < 2 else "S/E"            # los esquemas van sin escala
        assert any(t.dxf.text == escala for t in hoja.query("TEXT"))
    assert all(capa in doc.layers for capa in CAPAS)


def test_no_se_copia_el_marco_del_arquitecto(planos):
    _, doc, _ = planos
    capas = {e.dxf.layer for e in doc.modelspace()}
    assert "0-CAJETIN" not in capas
    assert {"0-AREA UTIL", "0-MUROS", "0-TEXTOS"} <= capas


def test_registros_junto_a_la_pared_de_su_estancia(planos):
    res, doc, _ = planos
    k = res.escala / 1000
    computables = [e for e in ESTANCIAS if e[0] in ("SALON-COMEDOR", "COCINA", "DORM. 1")]
    tv = _registros(doc, "TV")
    assert len(tv) == len(computables)                 # un registro de RTV por estancia que cuenta
    for _, _, caja in computables:
        poli = [Vec2(p) for p in _caja(*caja)]
        dentro = [q for q, _ in _registros(doc) if is_point_in_polygon_2d(q, poli) > 0]
        assert dentro, caja
        for q in dentro:                               # pegados a una pared, no en medio de la estancia
            d = min(_dist_segmento(q, a, b) for a, b in zip(poli, poli[1:] + poli[:1]))
            assert d == pytest.approx((TOMA[2] + TOMA[1] / 2) * k, abs=0.01)
    salon = [Vec2(p) for p in _caja(*ESTANCIAS[2][2])]
    assert sorted(c for q, c in _registros(doc) if is_point_in_polygon_2d(q, salon) > 0) == [
        "FO", "RJ45", "RJ45", "TBA", "TV"]


def test_rtr_y_toma_configurable_en_el_vestibulo(planos):
    _, doc, _ = planos
    vest = [Vec2(p) for p in _caja(*ESTANCIAS[0][2])]
    rtr = [_centro(i, "L1") for i in doc.modelspace().query("INSERT") if i.dxf.name == "ICT_RTR"]
    assert len(rtr) == 1 and is_point_in_polygon_2d(rtr[0], vest) > 0
    conf = [q for q, _ in _registros(doc, "C")]
    assert len(conf) == 1 and conf[0].distance(rtr[0]) < 1.0       # en la cercanía del PAU (Anexo II, 3.5 c)
    rs = [_centro(i) for i in doc.modelspace().query("INSERT") if i.dxf.name == "ICT_RS"]
    assert len(rs) == 1 and is_point_in_polygon_2d(rs[0], [Vec2(p) for p in _caja(9.4, 1.2, 12.0, 4.0)]) > 0


def test_recinto_y_arqueta_de_entrada(planos):
    _, doc, _ = planos
    msp = doc.modelspace()
    recintos = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == "ICT_RECINTOS"]
    assert len(recintos) == 1
    assert any(t.dxf.text == "RITI" for t in msp.query("TEXT"))
    arqueta = [i for i in msp.query("INSERT") if i.dxf.name == "ICT_ARQ"]
    assert len(arqueta) == 1
    centro = Vec2(arqueta[0].dxf.insert)
    assert not is_point_in_polygon_2d(centro, [Vec2(p) for p in _caja(30.9, 0.9, 39.1, 9.1)]) > 0  # fuera


def test_canalizacion_principal_en_la_misma_vertical(planos):
    _, doc, _ = planos
    cps = [Vec2(i.dxf.insert) for i in doc.modelspace().query("INSERT") if i.dxf.name == "ICT_CP"]
    assert len(cps) == 3            # en la planta primera, a la salida del RITI y al pie de la vertical
    primera = min(cps, key=lambda q: q.x)
    # Las vistas están a 30 m entre títulos: el pie de la vertical en planta baja cae en el mismo sitio
    assert any(q.isclose(primera + Vec2(30, 0), abs_tol=1e-6) for q in cps)


def test_tubos_rotulados_sin_cortar_ningun_texto(planos):
    res, doc, _ = planos
    msp = doc.modelspace()
    textos = [t for t in msp.query("TEXT") if t.dxf.layer.startswith("ICT_")]
    rotulos = {t.dxf.text for t in textos if "Ø" in t.dxf.text}
    assert "3Ø25 mm" in rotulos                         # acceso a la vivienda (Anexo III, 5.9)
    assert "5Ø20 mm" in rotulos                         # salón: un tubo de Ø20 por registro de toma
    tramos = [(a, b) for e in msp.query("LWPOLYLINE") if e.dxf.layer == "ICT_CANALIZACION"
              for a, b in zip(list(e.get_points("xy")), list(e.get_points("xy"))[1:])]
    for t in textos:
        alin = t.get_align_enum()
        punto = t.dxf.align_point if alin.name not in ("LEFT",) else t.dxf.insert
        caja = _caja_texto(t.dxf.text, (punto[0], punto[1]), t.dxf.height, alin, t.dxf.rotation)
        # la caja lleva un margen de un cuarto de la altura: se mira solo el texto
        m = 0.24 * t.dxf.height
        caja = (caja[0] + m, caja[1] + m, caja[2] - m, caja[3] - m)
        assert not any(_corta(a[:2], b[:2], caja) for a, b in tramos), t.dxf.text


def test_mediciones_para_el_calculo_de_rtv(planos):
    res, _, proyecto = planos
    assert len(res.mediciones) == 1
    m = res.mediciones[0]
    assert m.vivienda == proyecto.edificio.plantas[1].usuarios[0].id
    assert m.secundaria_m > 2.0                         # recorrido en planta + 2 x 1 m de holgura
    assert len(m.interior_m) == 3 and all(x > 2.0 for x in m.interior_m)
    r = resumen_longitudes(res.mediciones)
    assert r["interior_min"] == min(m.interior_m) and r["acometida_max"] == m.secundaria_m
    # Medición para el cuadro resumen de materiales
    mat = res.materiales
    assert mat["Registro de toma de RTV [ud]"] == 3 and mat["Registro de toma configurable [ud]"] == 1
    assert mat["Registro de terminación de red (RTR) [ud]"] == 1 and mat["Registro secundario de planta [ud]"] == 1
    assert mat["Arqueta de entrada 400x400x600 mm [ud]"] == 1
    assert mat["Tubo Ø25 mm, acceso a las viviendas [m]"] == pytest.approx(3 * m.secundaria_m, abs=0.2)
    assert mat["Tubo Ø20 mm, canalización interior de usuario [m]"] > sum(m.interior_m)   # un tubo por registro
    assert any(c.startswith("Tubo Ø63 mm") for c in mat) and any("canalización principal" in c for c in mat)


@pytest.mark.parametrize("n", [(0, 1), (0, -1), (1, 0), (-1, 0)])
def test_rtr_se_lee_pau_arriba_y_rtr_abajo_en_cualquier_pared(n):
    from ict_ajp.planos_ict import RTR_MM, _Lienzo, _preparar
    doc = ezdxf.new("R2018")
    _preparar(doc)
    ins_lz = _Lienzo(doc.modelspace(), 0.125)
    ins_lz.en_pared("ICT_RTR", (0, 0), n, {"L1": "PAU", "L2": "RTR"}, RTR_MM[0], RTR_MM[1], "ICT_REGISTROS")
    ins = doc.modelspace().query("INSERT")[0]
    pau, rtr = Vec2(ins.get_attrib("L1").dxf.align_point), Vec2(ins.get_attrib("L2").dxf.align_point)
    if ins.get_attrib_text("L1") == "RTR":
        pau, rtr = rtr, pau
    giro = ins.get_attrib("L1").dxf.rotation
    arriba = Vec2(-math.sin(math.radians(giro)), math.cos(math.radians(giro)))   # «arriba» del texto
    assert (pau - rtr).dot(arriba) > 0                  # «PAU» encima de «RTR», leídos derechos
    assert -90 < giro <= 90


def test_el_tubo_rodea_los_patios():
    from ict_ajp.planos_ict import _Lienzo, _cruza, _ruta
    lz = _Lienzo(ezdxf.new("R2018").modelspace(), 0.125)
    patio = _caja(1.0, 1.0, 3.0, 3.0)
    # en «L» por cualquiera de los dos lados pasaría por el patio: tiene que dar un rodeo
    pts = _ruta(lz, (2.0, -1.0), (0, 1), (2.0, 5.0), (0, -1), evitar=[patio])
    assert not _cruza(pts, [patio])
    assert pts[0] == (2.0, -1.0) and pts[-1] == (2.0, 5.0)


def test_junto_a_pared_elige_la_pared_mas_cercana():
    poli = _caja(0, 0, 4, 3)
    (x, y), u, n = _junto_a_pared(poli, (2.0, 0.6), 1.0, retranqueo=0.2)
    assert (x, y) == pytest.approx((2.0, 0.2)) and n == pytest.approx((0, 1))
    (x, y), _, _ = _junto_a_pared(poli, (2.0, 0.6), 1.0, hacia=(10.0, 1.5))   # hacia la puerta de la derecha
    assert (x, y) == pytest.approx((4, 1.5))


def test_textos_del_cajetin_caben_en_su_celda():
    lineas = _partir("Proyecto Telecomunicaciones Edificio 8 Viviendas, Trasteros y Garajes", 41.0, 1.8)
    assert len(lineas) >= 2 and " ".join(lineas).startswith("Proyecto Telecomunicaciones")


def _plantilla_cajetin(ruta):
    """Hoja A3 inventada con la disposición del cajetín de AJP: marco, cajetín abajo a la derecha, etiquetas
    en la capa fina y valores de muestra debajo."""
    doc = ezdxf.new("R2018")
    doc.styles.add("AJP", font="arial.ttf")
    doc.styles.add("AJP-NEGRITA", font="arialbd.ttf")
    for capa in ("G-MARCO", "G-CAJETIN", "G-CAJETIN-FINO", "G-LEYENDA", "G-NORTE-ESCALA", "X-VENTANAS"):
        doc.layers.add(capa)
    norte = doc.blocks.new("AJP_NORTE")
    norte.add_circle((0, 0), 5)
    hoja = doc.layout("Layout1")
    hoja.page_setup(size=(420, 297), margins=(0, 0, 0, 0), units="mm")
    hoja.add_lwpolyline(_caja(20, 7, 413, 290), close=True, dxfattribs={"layer": "G-MARCO"})
    hoja.add_lwpolyline(_caja(233, 7, 413, 57), close=True, dxfattribs={"layer": "G-CAJETIN"})
    hoja.add_lwpolyline(_caja(0, 0, 420, 297), close=True, dxfattribs={"layer": "X-VENTANAS"})
    hoja.add_blockref("AJP_NORTE", (220, 22), dxfattribs={"layer": "G-NORTE-ESCALA"})
    hoja.add_text("LEYENDA / CUADROS", height=1.8, dxfattribs={"layer": "G-CAJETIN-FINO", "insert": (22, 53.7)})
    for etiqueta, (x, y), muestra in (("PROYECTO", (289.5, 54.8), "PROYECTO DE MUESTRA"),
                                      ("EMPLAZAMIENTO", (289.5, 46.8), "Calle de muestra"),
                                      ("TITULAR", (289.5, 38.8), "Nombre del titular"),
                                      ("PLANO", (289.5, 30.8), "NOMBRE DEL PLANO"),
                                      ("Nº PLANO", (384.5, 30.8), "00"), ("ESCALA", (289.5, 16.8), "1:75"),
                                      ("FECHA", (319.5, 16.8), "MES"), ("REV.", (349.5, 16.8), "R9"),
                                      ("EXPEDIENTE", (369.5, 16.8), "000")):
        hoja.add_text(etiqueta, height=1.5, dxfattribs={"layer": "G-CAJETIN-FINO", "style": "AJP", "insert": (x, y)})
        hoja.add_text(muestra, height=2.4, dxfattribs={"layer": "G-CAJETIN", "style": "AJP-NEGRITA",
                                                       "insert": (x + 0.5, y - 5)})
    doc.saveas(ruta)
    return ruta


def test_hojas_con_el_cajetin_de_la_plantilla(base, tmp_path):
    import datetime
    from ict_ajp.planos_ict import formato_de_plantilla
    plantilla = _plantilla_cajetin(tmp_path / "cajetin.dxf")
    lectura = leer_plano(base)
    proyecto = proyecto_desde_lectura(lectura)
    proyecto.datos_generales.titulo = "Proyecto ICT de un edificio de prueba con un título bastante largo"
    proyecto.datos_generales.numero = "12099001"
    proyecto.datos_generales.promotor = "Promotora de Prueba, S.L."
    datos = datos_cajetin(proyecto, fecha=datetime.date(2026, 10, 22))
    colores = {"texto": "1F1F1F", "secundario": "555555", "marca": "FBC213"}
    res = generar_planos(base, lectura, proyecto, tmp_path / "p.dxf", datos, imagenes=False, pdf=False,
                         cajetin=plantilla, colores=colores)
    doc = ezdxf.readfile(res.ruta)
    hoja = doc.layout("ICT-2 Planta primera")
    textos = {t.dxf.text: t for t in hoja.query("TEXT")}
    for valor in ("PROYECTO ICT DE UN EDIFICIO DE PRUEBA CON UN TÍTULO BASTANTE LARGO", "Promotora de Prueba, S.L.",
                  "ICT · Planta primera", "02", f"1:{res.escala}", "OCTUBRE 2026", "R0", "001", "LEYENDA ICT"):
        assert valor in textos, valor
    assert not {"PROYECTO DE MUESTRA", "NOMBRE DEL PLANO", "00", "LEYENDA / CUADROS"} & set(textos)
    assert not any(i.dxf.name == "AJP_NORTE" for i in hoja.query("INSERT"))      # el norte no se adivina
    largo = textos["PROYECTO ICT DE UN EDIFICIO DE PRUEBA CON UN TÍTULO BASTANTE LARGO"]
    assert largo.dxf.width < 1.0                                                  # estrechado para caber
    # Colores de la empresa: textos en su gris oscuro, etiquetas en el secundario y el nº de plano y una franja
    # sobre el cajetín en el color de la marca
    assert largo.rgb == (0x1F, 0x1F, 0x1F)
    assert textos["PLANO"].rgb == (0x55, 0x55, 0x55)
    assert textos["02"].rgb == (0xFB, 0xC2, 0x13)
    assert any(e.rgb == (0xFB, 0xC2, 0x13) for e in hoja.query("LINE"))
    # La planta cabe en la zona de dibujo, encima del cajetín
    d = formato_de_plantilla(plantilla).dibujo
    vp = [v for v in hoja.query("VIEWPORT") if v.dxf.id != 1][0]
    assert vp.dxf.layer == "X-VENTANAS"
    assert d[0] <= vp.dxf.center.x - vp.dxf.width / 2 and vp.dxf.center.x + vp.dxf.width / 2 <= d[2]
    assert d[1] <= vp.dxf.center.y - vp.dxf.height / 2 and vp.dxf.center.y + vp.dxf.height / 2 <= d[3]


def test_pdf_de_las_hojas(base, tmp_path):
    from pypdf import PdfReader
    lectura = leer_plano(base)
    proyecto = proyecto_desde_lectura(lectura)
    res = generar_planos(base, lectura, proyecto, tmp_path / "p.dxf", datos_cajetin(proyecto), imagenes=False)
    paginas = PdfReader(res.pdf).pages
    assert len(paginas) == 7                                    # 2 plantas y 5 esquemas de principio
    assert float(paginas[0].mediabox.width) == pytest.approx(420 / 25.4 * 72, abs=1)     # A3 apaisado
