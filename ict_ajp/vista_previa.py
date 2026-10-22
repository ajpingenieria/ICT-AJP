"""Imagen de vista previa (PNG) de un DXF o de una zona de él, y PDF de sus presentaciones.

Sirve para revisar la base del arquitecto y para acompañar cada entrega de planos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import ezdxf
from ezdxf import bbox
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

PUNTOS_POR_MM = 72 / 25.4
GRIS_BASE = "#8c8c8c"


def renderizar(ruta_dxf: str | Path, salida_png: str | Path,
               ventana: Optional[tuple[float, float, float, float]] = None,
               ancho_px: int = 2400, presentacion: Optional[str] = None,
               resaltar: Optional[dict[str, str]] = None) -> Path:
    """Dibuja el espacio modelo (o la ventana x0, y0, x1, y1) en blanco y negro sobre fondo blanco.

    Con `presentacion` dibuja esa presentación (espacio papel, con sus ventanas al modelo) a hoja completa.
    Con `resaltar` ({capa: color}), esas capas salen en su color y todas las demás en gris.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    doc = ezdxf.readfile(str(ruta_dxf))
    sustituir_fuentes_ausentes(doc)
    msp = doc.layout(presentacion) if presentacion else doc.modelspace()
    escala_lineas = 1.0
    if presentacion and not ventana:
        x0, y0, x1, y1 = 0.0, 0.0, msp.dxf.paper_width, msp.dxf.paper_height
        filtro = None
        escala_lineas = PUNTOS_POR_MM * (ancho_px / 100 * 25.4) / (x1 - x0)   # grosores a escala de la hoja
    elif ventana:
        x0, y0, x1, y1 = ventana
        filtro = _filtro_ventana(x0, y0, x1, y1)
    else:
        caja = bbox.extents(msp, fast=True)
        x0, y0, x1, y1 = caja.extmin.x, caja.extmin.y, caja.extmax.x, caja.extmax.y
        filtro = None

    alto_px = max(1, int(ancho_px * (y1 - y0) / max(x1 - x0, 1e-9)))
    fig = _dibujar(doc, msp, (x0, y0, x1, y1), ancho_px / 100, alto_px / 100, filtro, resaltar, escala_lineas)
    salida = Path(salida_png)
    fig.savefig(salida, dpi=100, facecolor="white")
    plt.close(fig)
    return salida


def renderizar_pdf(ruta_dxf: str | Path, salida_pdf: str | Path, presentaciones: list[str],
                   resaltar: Optional[dict[str, str]] = None) -> Path:
    """Las presentaciones en un PDF vectorial, una por página y a su tamaño de papel real."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    doc = ezdxf.readfile(str(ruta_dxf))
    sustituir_fuentes_ausentes(doc)
    salida = Path(salida_pdf)
    with PdfPages(salida) as pdf:
        for nombre in presentaciones:
            hoja = doc.layout(nombre)
            w, h = hoja.dxf.paper_width, hoja.dxf.paper_height
            fig = _dibujar(doc, hoja, (0.0, 0.0, w, h), w / 25.4, h / 25.4, None, resaltar, PUNTOS_POR_MM)
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    return salida


def _dibujar(doc, espacio, ventana, ancho_in: float, alto_in: float, filtro, resaltar, escala_lineas: float):
    import matplotlib.pyplot as plt

    x0, y0, x1, y1 = ventana
    fig = plt.figure(figsize=(ancho_in, alto_in), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    config = Configuration(background_policy=BackgroundPolicy.WHITE,
                           color_policy=ColorPolicy.COLOR if resaltar else ColorPolicy.BLACK,
                           min_lineweight=0.1, lineweight_scaling=escala_lineas)
    frontal = Frontend(RenderContext(doc), MatplotlibBackend(ax), config=config)
    if resaltar:
        colores = {k.upper(): v for k, v in resaltar.items()}

        def color_por_capa(entidad, propiedades) -> None:
            propiedades.color = colores.get(propiedades.layer.upper(), GRIS_BASE)
        frontal.push_property_override_function(color_por_capa)
    frontal.draw_layout(espacio, finalize=True, filter_func=filtro)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    fig.set_size_inches(ancho_in, alto_in)   # el dibujante de ezdxf cambia el tamaño
    return fig


def sustituir_fuentes_ausentes(doc, sustituta: str = "arial.ttf") -> list[str]:
    """Para dibujar la vista previa: los estilos con fuentes TrueType que no están en el equipo, o que están
    pero no tienen las letras normales (p. ej. «sanss___.ttf» de AutoCAD, que sale en cuadraditos), pasan a
    Arial. Solo en memoria; el DXF no se modifica. Devuelve las fuentes sustituidas."""
    from ezdxf.fonts import fonts

    cambiadas = []
    for estilo in doc.styles:
        fuente = (estilo.dxf.get("font", "") or "").strip()
        if not fuente.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        try:
            disponible = fonts.font_manager.has_font(fuente) and _tiene_letras(fuente)
        except Exception:
            disponible = False
        if not disponible:
            estilo.dxf.font = sustituta
            if estilo.has_extended_font_data:
                estilo.discard_extended_font_data()
            cambiadas.append(fuente)
    return cambiadas


def _tiene_letras(fuente: str) -> bool:
    """True si el archivo de fuente tiene glifos para letras latinas básicas."""
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def ruta(nombre: str):
        from matplotlib import font_manager
        for p in font_manager.findSystemFonts():
            if p.lower().replace("\\", "/").endswith("/" + nombre.lower()):
                return p
        return None

    p = ruta(fuente)
    if not p:
        return True          # no se encuentra el archivo: que decida el gestor de fuentes de ezdxf
    from matplotlib.ft2font import FT2Font
    f = FT2Font(p)
    return all(f.get_char_index(ord(c)) for c in "AEIOUaeiou")


def _filtro_ventana(x0: float, y0: float, x1: float, y1: float):
    """Solo dibuja lo que toca la ventana: acelera mucho los planos grandes."""
    def dentro(e) -> bool:
        try:
            c = bbox.extents([e], fast=True)
        except Exception:
            return True
        if not c.has_data:
            return True
        return not (c.extmax.x < x0 or c.extmin.x > x1 or c.extmax.y < y0 or c.extmin.y > y1)
    return dentro
