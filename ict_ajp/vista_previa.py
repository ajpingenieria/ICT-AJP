"""Imagen de vista previa (PNG) de un DXF o de una zona de él.

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


def renderizar(ruta_dxf: str | Path, salida_png: str | Path,
               ventana: Optional[tuple[float, float, float, float]] = None,
               ancho_px: int = 2400) -> Path:
    """Dibuja el espacio modelo (o la ventana x0, y0, x1, y1) en blanco y negro sobre fondo blanco."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    doc = ezdxf.readfile(str(ruta_dxf))
    msp = doc.modelspace()
    if ventana:
        x0, y0, x1, y1 = ventana
        filtro = _filtro_ventana(x0, y0, x1, y1)
    else:
        caja = bbox.extents(msp, fast=True)
        x0, y0, x1, y1 = caja.extmin.x, caja.extmin.y, caja.extmax.x, caja.extmax.y
        filtro = None

    alto_px = max(1, int(ancho_px * (y1 - y0) / max(x1 - x0, 1e-9)))
    fig = plt.figure(figsize=(ancho_px / 100, alto_px / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    config = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                           min_lineweight=0.1)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=config).draw_layout(
        msp, finalize=True, filter_func=filtro)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    salida = Path(salida_png)
    fig.set_size_inches(ancho_px / 100, alto_px / 100)   # el dibujante de ezdxf cambia el tamaño
    fig.savefig(salida, dpi=100, facecolor="white")
    plt.close(fig)
    return salida


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
