import ezdxf

from ict_ajp.vista_previa import renderizar


def test_renderiza_png_de_una_ventana(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True)
    msp.add_line((100, 100), (110, 110))          # fuera de la ventana
    msp.add_text("RITI", height=0.5, dxfattribs={"insert": (2, 2)})
    dxf = tmp_path / "p.dxf"
    doc.saveas(dxf)
    png = renderizar(dxf, tmp_path / "p.png", ventana=(-1, -1, 11, 6), ancho_px=600)
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    import matplotlib.image as mpimg
    img = mpimg.imread(png)
    assert img.shape[:2] == (350, 600)          # proporción de la ventana: 12 x 7 m


def test_renderiza_una_presentacion_a3(tmp_path):
    doc = ezdxf.new("R2018")
    hoja = doc.layouts.new("A3")
    hoja.page_setup(size=(420, 297), margins=(0, 0, 0, 0), units="mm")
    hoja.add_lwpolyline([(10, 10), (410, 10), (410, 287), (10, 287)], close=True)
    hoja.add_text("Nº Plano", height=2.5, dxfattribs={"insert": (300, 20)})
    dxf = tmp_path / "h.dxf"
    doc.saveas(dxf)
    png = renderizar(dxf, tmp_path / "h.png", ancho_px=840, presentacion="A3")
    import matplotlib.image as mpimg
    assert mpimg.imread(png).shape[:2] == (594, 840)    # hoja completa, proporción A3
