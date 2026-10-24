"""Plantas de la ICT sobre la base DXF del arquitecto (hoja de ruta v0.5).

Para cada planta se copia la vista de distribución del arquitecto, sin modificarla, y encima se dibuja la
ICT en capas propias con prefijo ICT_ (CLAUDE.md, regla 5): recintos, registros secundarios, RTR, registros
de toma de cada estancia, canalizaciones secundaria e interior, y en planta baja, ático y cubierta la
arqueta de entrada, los recintos y el mástil. Cada planta va en una presentación A3 con el cajetín de AJP
y una leyenda, y se saca una imagen de vista previa y un PDF con todas las hojas.

Los registros se colocan junto a la pared de cada estancia (polilíneas de superficie útil del arquitecto)
más cercana a su rótulo; el RTR, en la pared del vestíbulo más cercana al registro secundario, y junto a él
el registro de toma configurable (RD 346/2011, Anexo II, 3.5 c: «en la cercanía del PAU»).
Los recorridos se dibujan ortogonales (en «L») y su longitud se mide así más una holgura vertical por
extremo: es una medición de proyecto, no de obra.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import ezdxf
from ezdxf import bbox
from ezdxf.addons import Importer
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2, is_point_in_polygon_2d

from .leer_dxf import LecturaPlano, PlantaLeida, _es_exterior, _nombre_planta, normalizar

CAPAS = {  # nombre: (color ACI, grosor de línea en centésimas de mm)
    "ICT_RECINTOS": (1, 50), "ICT_REGISTROS": (6, 35), "ICT_TOMAS": (5, 25), "ICT_CANALIZACION": (3, 35),
    "ICT_TEXTOS": (7, 18), "ICT_RTV": (4, 35), "ICT_ACOMETIDA": (30, 35), "ICT_CAJETIN": (7, 35),
    "ICT_LEYENDA": (7, 25),
}
# Vista previa y PDF: la base del arquitecto en gris y la ICT en color
COLORES_VISTA = {
    "ICT_RECINTOS": "#c00000", "ICT_REGISTROS": "#9c1a8a", "ICT_TOMAS": "#0047ab", "ICT_CANALIZACION": "#00873c",
    "ICT_TEXTOS": "#000000", "ICT_RTV": "#00737f", "ICT_ACOMETIDA": "#b35c00", "ICT_CAJETIN": "#000000",
    "ICT_LEYENDA": "#000000",
    # Cajetín y leyenda de la plantilla de AJP, en negro como en sus planos
    "G-MARCO": "#000000", "G-CAJETIN": "#000000", "G-CAJETIN-FINO": "#555555", "G-LEYENDA": "#000000",
}
CAPAS_ESTANCIAS = r"AREA.?UTIL|SUP.?UTIL|SUPERFICIE.?UTIL"    # polilíneas de superficie útil de cada estancia
CAPAS_IGNORADAS = r"CAJETIN|MARCO"                          # marco y cajetín de las láminas del arquitecto
CAPAS_MUROS = r"MURO|TABIQ|CERRAM|FACHADA|PARED"            # paredes del arquitecto: los rótulos no las pisan
ESCALAS = [50, 75, 100, 125, 150, 200]
HOJA = (420.0, 297.0)                   # A3 apaisado, mm
MARGEN = 10.0
ALTO_CAJETIN = 32.0
ANCHO_LEYENDA = 95.0
COLUMNAS_CAJETIN = [MARGEN, 175.0, 220.0, 262.0, 304.0, HOJA[0] - MARGEN]


@dataclass
class Vista:
    titulo: str                          # «Planta tipo (2ª y 3ª)»
    planta: PlantaLeida
    niveles: list[int]
    ventana: tuple[float, float, float, float]       # x0, y0, x1, y1 en la vista de distribución
    dx: float = 0.0
    dy: float = 0.0


@dataclass
class Medicion:
    vivienda: str
    secundaria_m: float
    interior_m: list[float] = field(default_factory=list)      # hasta el registro de RTV de cada estancia


@dataclass
class ResultadoPlanos:
    ruta: Path
    presentaciones: list[str]
    mediciones: list[Medicion]
    escala: int = 100
    imagenes: list[Path] = field(default_factory=list)
    pdf: Optional[Path] = None
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------- vistas

def _titulo_legible(nombre: str, niveles: list[int]) -> str:
    from .leer_dxf import nombre_legible
    if len(niveles) > 1:
        ords = {1: "1ª", 2: "2ª", 3: "3ª", 4: "4ª", 5: "5ª"}
        return f"Planta tipo ({' y '.join(ords.get(n, str(n)) for n in niveles)})"
    return nombre_legible(nombre)


def vistas_ict(lectura: LecturaPlano) -> list[Vista]:
    """Una vista por plano: plantas tipo agrupadas; la vista de distribución si existe, si no la leída.

    La ventana es provisional (contenido más 1,5 m): `generar_planos` la ajusta al dibujo del arquitecto.
    """
    grupos: dict[str, list[PlantaLeida]] = {}
    for p in lectura.plantas:
        grupos.setdefault(p.titulo, []).append(p)
    datos = []
    for plantas in grupos.values():
        p = plantas[0]
        if not p.zona:
            continue
        nombre_base, _, _ = _nombre_planta(p.titulo)
        dx = dy = 0.0
        for texto, x, y in lectura.vistas:
            if "DISTRIBUCION" in normalizar(texto) and _nombre_planta(texto)[0] == nombre_base:
                dx, dy = x - p.titulo_xy[0], y - p.titulo_xy[1]
                break
        datos.append((p, plantas, dx, dy, _caja_contenido(p)))
    # Las vistas sin viviendas ni estancias rotuladas (la cubierta) toman el tamaño de las demás
    cajas = [c for *_, c in datos if c]
    ancho = max((c[2] - c[0] for c in cajas), default=16.0)
    alto = max((c[3] - c[1] for c in cajas), default=25.0)
    vistas = []
    for p, plantas, dx, dy, caja in datos:
        if caja is None:
            x0, _, y0, _ = p.zona
            caja = (x0, y0, x0 + ancho, y0 + alto)
        x0, y0, x1, y1 = caja
        niveles = [q.nivel for q in plantas]
        repetida = plantas[0].repetida_de is not None
        vistas.append(Vista(_titulo_legible(p.nombre if not repetida else "PLANTA TIPO", niveles), p, niveles,
                            (x0 + dx, y0 + dy, x1 + dx, y1 + dy), dx, dy))
    return sorted(vistas, key=lambda v: min(v.niveles))


def _caja_contenido(p: PlantaLeida, m: float = 1.5) -> Optional[tuple[float, float, float, float]]:
    xs, ys = [], []
    for v in p.viviendas:
        for x, y in v.contorno:
            xs.append(x)
            ys.append(y)
    for e in p.otras_estancias:
        xs.append(e.x)
        ys.append(e.y)
    if len(xs) < 3:
        return None
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def _ajustar_ventana(v: Vista, cajas: list) -> tuple[float, float, float, float]:
    """Ventana ceñida al dibujo de la planta, sin el marco ni el título de la lámina del arquitecto.

    Cuenta lo que toca el contenido leído (viviendas y estancias); en la cubierta, lo que cabe entero en la
    ventana provisional, sin textos (el título queda fuera).
    """
    x0, y0, x1, y1 = v.ventana
    ignorar = re.compile(CAPAS_IGNORADAS, re.I)
    interior = _caja_contenido(v.planta, 0.0)
    if interior:
        interior = (interior[0] + v.dx, interior[1] + v.dy, interior[2] + v.dx, interior[3] + v.dy)
    franja_titulo = v.planta.titulo_xy[1] + v.dy + 0.6 if v.planta.titulo_xy else -math.inf
    sel = []
    for e, a, b, c, d in cajas:
        if ignorar.search(e.dxf.layer) or c - a > 1.5 * (x1 - x0) or d - b > 1.5 * (y1 - y0):
            continue
        if interior:
            vale = not (c < interior[0] or a > interior[2] or d < interior[1] or b > interior[3])
        else:       # sin textos ni lo que queda a la altura del título (su subrayado)
            vale = (a >= x0 and c <= x1 and b >= y0 and d <= y1 and e.dxftype() not in ("TEXT", "MTEXT")
                    and d > franja_titulo)
        if vale:
            sel.append((a, b, c, d))
    if not sel:
        return v.ventana
    m = 0.3
    return (max(min(s[0] for s in sel) - m, x0 - 1), max(min(s[1] for s in sel) - m, y0 - 1),
            min(max(s[2] for s in sel) + m, x1 + 1), min(max(s[3] for s in sel) + m, y1 + 1))


# --------------------------------------------------------------------------------------- geometría

def _dentro(q, poli) -> bool:
    return is_point_in_polygon_2d(Vec2(q), [Vec2(p) for p in poli]) >= 0


def _area(poli) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poli, poli[1:] + poli[:1]))) / 2


def _aristas(poli):
    pts = list(poli)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return [(a, b) for a, b in zip(pts, pts[1:]) if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6]


def _poligono_de(q, polis):
    """El recinto más pequeño que contiene el punto (el rótulo de una estancia)."""
    return min((pl for pl in polis if _dentro(q, pl)), key=_area, default=None)


def _junto_a_pared(poli, ref, largo: float, hacia=None, retranqueo: float = 0.0):
    """Punto de la pared, dirección de la pared y normal hacia dentro (unitarias) para un grupo de `largo` m
    junto a la pared de la estancia más cercana a `hacia` (o, si no se da, a `ref`); el punto, separado de la
    pared `retranqueo` m. None si no hay recinto."""
    if not poli:
        return None
    objetivo = hacia or ref
    for minimo in (largo + 0.1, 0.0):
        mejor = None
        for a, b in _aristas(poli):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < minimo:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            medio = min(largo / 2 + 0.05, L / 2)
            t = min(max((objetivo[0] - a[0]) * ux + (objetivo[1] - a[1]) * uy, medio), L - medio)
            q = (a[0] + ux * t, a[1] + uy * t)
            nx, ny = -uy, ux
            if not _dentro((q[0] + nx * 0.05, q[1] + ny * 0.05), poli):
                nx, ny = -nx, -ny
            d = math.hypot(objetivo[0] - q[0], objetivo[1] - q[1])
            if mejor is None or d < mejor[0]:
                mejor = (d, (q[0] + nx * retranqueo, q[1] + ny * retranqueo), (ux, uy), (nx, ny))
        if mejor:
            return mejor[1], mejor[2], mejor[3]
    return None


def _giro(u) -> float:
    """Ángulo de la pared en grados, entre -90 y 90 para que los textos se lean derechos."""
    g = math.degrees(math.atan2(u[1], u[0]))
    if g > 90:
        g -= 180
    elif g <= -90:
        g += 180
    return g


def _dist_segmento(p, a, b) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


# --------------------------------------------------------------------------------------- dibujo
# Los símbolos se definen en milímetros de papel y se insertan a la escala de la hoja (k = metros por mm de
# papel), para que en el plano impreso tengan siempre el mismo tamaño. Estilo elegido por el proyectista: tomas
# pegadas a la pared (como la toma TV-FM de sus planos de electricidad) con las siglas dentro, registros con
# su nombre dentro y el número y diámetro de tubos rotulado en cada tramo.

TOMA = (4.2, 2.2, 0.6)          # ancho, fondo y patilla hasta la pared (mm)
SEP_TOMAS = 0.6                 # hueco entre las tomas de una estancia (mm)
RTR_MM = (5.6, 3.8)             # ancho y fondo del RTR (mm)
RS_MM = (5.2, 2.8)
CP_RADIO = 1.4
ARQUETA_MM = 3.4
H_TOMA = 1.25                   # alturas de texto (mm)
H_TUBO = 1.2
H_NOTA = 1.4
H_RECINTO = 1.8
H_VIVIENDA = 2.5
SIGLAS = {"PT": "RJ45", "TV": "TV", "TB": "TBA", "FO": "FO", "C": "C"}
C = TextEntityAlignment.MIDDLE_CENTER


def _preparar(doc) -> None:
    for capa, (color, grosor) in CAPAS.items():
        if capa not in doc.layers:
            doc.layers.add(capa, color=color, lineweight=grosor)
    if "ICT_TRAZOS" not in doc.linetypes:
        # En unidades de papel (mm): con PSLTSCALE = 1 las ventanas lo escalan para que en la hoja impresa
        # salgan trazos de 2 mm a cualquier escala
        doc.linetypes.add("ICT_TRAZOS", pattern=[3.0, 2.0, -1.0], description="ICT trazos __ __ __")
        doc.header["$PSLTSCALE"] = 1
    if "ICT_VENTANAS" not in doc.layers:
        doc.layers.add("ICT_VENTANAS", color=8).dxf.plot = 0      # borde de las ventanas: no se imprime
    for estilo, fuente in (("ICT_ITALICA", "ariali.ttf"), ("ICT_ARIAL", "arial.ttf"), ("ICT_NEGRITA", "arialbd.ttf")):
        if estilo not in doc.styles:
            doc.styles.add(estilo, font=fuente)

    def caja(b, x0, y0, x1, y1):
        b.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True)

    def etiqueta(b, nombre, y, h, estilo="ICT_ARIAL"):
        b.add_attdef(nombre, (0, y), dxfattribs={"height": h, "style": estilo}).set_placement((0, y), align=C)

    w, f, pata = TOMA
    if "ICT_TOMA" not in doc.blocks:       # toma colgada de la pared por su patilla, siglas dentro
        b = doc.blocks.new("ICT_TOMA")
        b.add_line((0, 0), (0, -pata))
        caja(b, -w / 2, -pata, w / 2, -pata - f)
        etiqueta(b, "COD", -pata - f / 2, H_TOMA)
    if "ICT_RTR" not in doc.blocks:        # RTR con el PAU, contra la pared
        b = doc.blocks.new("ICT_RTR")
        caja(b, -RTR_MM[0] / 2, 0, RTR_MM[0] / 2, -RTR_MM[1])
        etiqueta(b, "L1", -RTR_MM[1] * 0.3, 1.15, "ICT_NEGRITA")
        etiqueta(b, "L2", -RTR_MM[1] * 0.7, 1.15, "ICT_NEGRITA")
    if "ICT_RS" not in doc.blocks:
        b = doc.blocks.new("ICT_RS")
        caja(b, -RS_MM[0] / 2, 0, RS_MM[0] / 2, -RS_MM[1])
        etiqueta(b, "COD", -RS_MM[1] / 2, 1.4, "ICT_NEGRITA")
    if "ICT_CP" not in doc.blocks:         # canalización principal (vertical)
        b = doc.blocks.new("ICT_CP")
        b.add_circle((0, 0), CP_RADIO)
        r = CP_RADIO / math.sqrt(2)
        b.add_line((-r, -r), (r, r))
        b.add_line((-r, r), (r, -r))
    if "ICT_ARQ" not in doc.blocks:        # arqueta de entrada
        b = doc.blocks.new("ICT_ARQ")
        a = ARQUETA_MM / 2
        caja(b, -a, -a, a, a)
        b.add_text("ICT", height=1.0, dxfattribs={"style": "ICT_NEGRITA"}).set_placement((0, 0), align=C)


# ----------------------------------------------------------------- textos y cajas ocupadas

@lru_cache(maxsize=None)
def _fuente_unidad(fuente: str):
    try:
        from ezdxf.fonts import fonts
        return fonts.make_font(fuente, 1.0).text_width
    except Exception:
        return lambda s: 0.6 * len(s)


def _ancho_texto(texto: str, h: float, negrita: bool = False) -> float:
    return _fuente_unidad("arialbd.ttf" if negrita else "arial.ttf")(texto) * h


def _caja_texto(texto: str, punto, h: float, alin=C, giro: float = 0.0, negrita: bool = False):
    """Caja (x0, y0, x1, y1) que ocupa un texto, con un pequeño margen."""
    w = _ancho_texto(texto, h, negrita)
    x0, x1 = {"LEFT": (0, w), "RIGHT": (-w, 0)}.get(alin.name.split("_")[-1], (-w / 2, w / 2))
    vert = alin.name.split("_")[0] if "_" in alin.name else "BASE"
    y0, y1 = {"TOP": (-h, 0), "BOTTOM": (0, h), "MIDDLE": (-h / 2, h / 2)}.get(vert, (-0.2 * h, h))
    m = 0.25 * h
    c, s = math.cos(math.radians(giro)), math.sin(math.radians(giro))
    pts = [(punto[0] + x * c - y * s, punto[1] + x * s + y * c)
           for x, y in ((x0 - m, y0 - m), (x1 + m, y0 - m), (x1 + m, y1 + m), (x0 - m, y1 + m))]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _solape(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _corta(a, b, caja) -> bool:
    """El segmento a-b atraviesa la caja (recorte de Liang-Barsky)."""
    x0, y0, x1, y1 = caja
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def _cuantos_cortan(segmentos, caja) -> int:
    x0, y0, x1, y1 = caja
    return sum(1 for a, b in segmentos
               if not (max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1 or max(a[1], b[1]) < y0 or min(a[1], b[1]) > y1)
               and _corta(a, b, caja))


def segmentos_de(entidades, patron: str = CAPAS_MUROS) -> list[tuple]:
    """Segmentos de las líneas y polilíneas de las capas que cumplen el patrón (las paredes del arquitecto)."""
    capas = re.compile(patron, re.I)
    res = []
    for e in entidades:
        if not capas.search(e.dxf.layer):
            continue
        if e.dxftype() == "LINE":
            res.append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
        elif e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            if e.closed and pts:
                pts.append(pts[0])
            res += list(zip(pts, pts[1:]))
    return res


class _Lienzo:
    """Lo que se va dibujando en una planta y lo que ocupa, para colocar los textos sin que se pisen ni los
    corten los tubos."""

    def __init__(self, msp, k: float):
        self.msp, self.k = msp, k
        self.cajas: list[tuple] = []          # símbolos, textos y rótulos del arquitecto
        self.tramos: list[tuple] = []         # segmentos de tubo ya dibujados
        self.muros: list[tuple] = []          # segmentos de las paredes del arquitecto

    def ocupar(self, caja) -> None:
        self.cajas.append(caja)

    def coste(self, caja) -> float:
        """Cuánto pisa una caja de texto: área sobre otras cajas más una penalización por cada tubo y, menor,
        por cada pared que la cruzan."""
        return (sum(_solape(caja, c) for c in self.cajas) / (self.k * self.k)
                + 50 * _cuantos_cortan(self.tramos, caja) + 8 * _cuantos_cortan(self.muros, caja))

    def cruces(self, puntos) -> int:
        """Cuántas cajas atraviesa un recorrido (encogidas un poco: los extremos tocan su símbolo)."""
        e = 0.3 * self.k
        cajas = [(x0 + e, y0 + e, x1 - e, y1 - e) for x0, y0, x1, y1 in self.cajas if x1 - x0 > 2 * e and y1 - y0 > 2 * e]
        return sum(1 for c in cajas if any(_corta(a, b, c) for a, b in zip(puntos, puntos[1:])))

    def encima(self, puntos) -> float:
        """Milímetros de papel que un recorrido iría justo encima de tubos ya dibujados (tramos paralelos a
        menos de 0,5 mm)."""
        total = 0.0
        tol = 0.5 * self.k
        for a, b in zip(puntos, puntos[1:]):
            for c, d in self.tramos:
                if abs(a[1] - b[1]) < 1e-9 and abs(c[1] - d[1]) < 1e-9 and abs(a[1] - c[1]) < tol:
                    i0, i1 = max(min(a[0], b[0]), min(c[0], d[0])), min(max(a[0], b[0]), max(c[0], d[0]))
                elif abs(a[0] - b[0]) < 1e-9 and abs(c[0] - d[0]) < 1e-9 and abs(a[0] - c[0]) < tol:
                    i0, i1 = max(min(a[1], b[1]), min(c[1], d[1])), min(max(a[1], b[1]), max(c[1], d[1]))
                else:
                    continue
                total += max(0.0, i1 - i0)
        return total / self.k * 0.2

    def texto(self, texto: str, punto, h_mm: float, capa: str = "ICT_TEXTOS", alin=C, giro: float = 0.0,
              negrita: bool = False):
        h = h_mm * self.k
        self.msp.add_text(texto, height=h, rotation=giro, dxfattribs={
            "layer": capa, "style": "ICT_NEGRITA" if negrita else "ICT_ARIAL"}).set_placement(punto, align=alin)
        caja = _caja_texto(texto, punto, h, alin, giro, negrita)
        self.ocupar(caja)
        return caja

    def rotulo_libre(self, lineas: list[str], centro, radio: float, h_mm: float = H_NOTA,
                     capa: str = "ICT_TEXTOS") -> None:
        """Texto de una o varias líneas junto a un símbolo (derecha, izquierda, arriba o abajo), donde menos pise."""
        h = h_mm * self.k
        paso = 1.5 * h
        alto = paso * (len(lineas) - 1)
        ancho = max(_ancho_texto(t, h) for t in lineas)
        d = radio + 0.8 * self.k
        opciones = [((centro[0] + d, centro[1] + alto / 2), TextEntityAlignment.MIDDLE_LEFT),
                    ((centro[0] - d, centro[1] + alto / 2), TextEntityAlignment.MIDDLE_RIGHT),
                    ((centro[0], centro[1] + d + h / 2 + alto), C), ((centro[0], centro[1] - d - h / 2), C)]

        def caja_de(p, alin):
            x0 = p[0] if alin.name.endswith("LEFT") else (p[0] - ancho if alin.name.endswith("RIGHT") else p[0] - ancho / 2)
            return (x0 - 0.25 * h, p[1] - alto - 0.75 * h, x0 + ancho + 0.25 * h, p[1] + 0.75 * h)
        punto, alin = min(opciones, key=lambda o: self.coste(caja_de(*o)))
        for j, t in enumerate(lineas):
            self.texto(t, (punto[0], punto[1] - paso * j), h_mm, capa, alin)

    def linea(self, puntos, capa: str = "ICT_CANALIZACION", tipo: Optional[str] = None) -> None:
        self.msp.add_lwpolyline(puntos, dxfattribs={"layer": capa, **({"linetype": tipo} if tipo else {})})
        self.tramos += list(zip(puntos, puntos[1:]))

    def rotular_tubo(self, puntos, texto: str, capa: str = "ICT_CANALIZACION") -> None:
        """«nØD mm» paralelo a un tramo del tubo, a un lado, donde no pise textos, símbolos ni otros tubos."""
        h = H_TUBO * self.k
        ancho = _ancho_texto(texto, h)
        mejor = None
        tramos = sorted(zip(puntos, puntos[1:]), key=lambda t: -math.dist(*t))
        for a, b in tramos:
            L = math.dist(a, b)
            if L < ancho + self.k:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            nx, ny = -uy, ux
            giro = _giro((ux, uy))
            for f in (0.5, 0.35, 0.65, 0.2, 0.8):
                for lado in (1, -1):
                    s = lado * (h / 2 + 0.7 * self.k)
                    p = (a[0] + ux * L * f + nx * s, a[1] + uy * L * f + ny * s)
                    caja = _caja_texto(texto, p, h, C, giro)
                    coste = self.coste(caja)
                    if mejor is None or coste < mejor[0]:
                        mejor = (coste, p, giro)
                    if coste == 0:
                        break
                if mejor[0] == 0:
                    break
            if mejor and mejor[0] == 0:
                break
        if mejor is None:                     # tramos más cortos que el texto: al lado del primero
            a, b = puntos[0], puntos[-1]
            mejor = (0, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + h), 0.0)
        self.texto(texto, mejor[1], H_TUBO, capa, C, mejor[2])

    def en_pared(self, bloque: str, q, n, valores: Optional[dict], ancho: float, fondo: float, capa: str):
        """Símbolo pegado a la pared: q en la cara de la pared y n la normal hacia la estancia. Sus textos quedan
        derechos. Devuelve la caja que ocupa."""
        k = self.k
        w = (-n[0], -n[1])                    # hacia la pared
        xh = (w[1], -w[0])                    # a lo largo de la pared
        giro = math.degrees(math.atan2(xh[1], xh[0]))
        ins = self.msp.add_blockref(bloque, q, dxfattribs={"layer": capa, "xscale": k, "yscale": k, "rotation": giro})
        if valores:
            if not -90 < giro <= 90 and "L1" in valores and "L2" in valores:
                # el bloque queda boca abajo y sus textos se enderezan: las dos líneas cambian de sitio
                valores = {**valores, "L1": valores["L2"], "L2": valores["L1"]}
            _atributos(ins, valores, capa, _giro(xh))
        pts = [(q[0] + (xh[0] * lx + w[0] * ly) * k, q[1] + (xh[1] * lx + w[1] * ly) * k)
               for lx, ly in ((-ancho / 2, 0), (ancho / 2, 0), (ancho / 2, -fondo), (-ancho / 2, -fondo))]
        caja = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        self.ocupar(caja)
        return caja


def _atributos(ins, valores: dict, capa: str, giro: Optional[float] = None) -> None:
    """Rellena los textos de un bloque, en la capa del propio bloque y, si se da `giro`, derechos."""
    ins.add_auto_attribs(valores)
    for a in ins.attribs:
        a.dxf.layer = capa
        if giro is not None:
            a.dxf.rotation = giro


def _caja_rotulo_arquitecto(nombre: str, p, h: float = 0.1):
    """Lo que ocupan, más o menos, el nombre y la superficie de una estancia rotulados por el arquitecto."""
    w = max(_ancho_texto(nombre, h), _ancho_texto("00,00 m²", h))
    return (p[0] - 0.6 * w, p[1] - 2.2 * h, p[0] + 1.1 * w, p[1] + 1.4 * h)


def _limpiar(puntos):
    """Quita puntos repetidos y los intermedios de tramos rectos."""
    res = []
    for p in puntos:
        if res and math.dist(res[-1], p) < 1e-6:
            continue
        if len(res) >= 2:
            a, b = res[-2], res[-1]
            if abs((b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])) < 1e-9:
                res[-1] = p
                continue
        res.append(p)
    return res


def _longitud(puntos) -> float:
    return sum(math.dist(a, b) for a, b in zip(puntos, puntos[1:]))


def _ruta(lz: _Lienzo, a0, na, b0, nb, contorno=None, evitar=(), salida_mm: float = 1.8):
    """Tubo de a0 a b0 saliendo perpendicular a la pared de cada extremo (na, nb: normales hacia la estancia),
    con el tramo intermedio en «L» por dentro del contorno, cruzando los menos textos y símbolos posibles y sin
    ir encima de otros tubos."""
    s = salida_mm * lz.k
    a1 = (a0[0] + na[0] * s, a0[1] + na[1] * s) if na else a0
    b1 = (b0[0] + nb[0] * 1.8 * lz.k, b0[1] + nb[1] * 1.8 * lz.k) if nb else b0
    # en «L» por un lado o por el otro, y en «Z» con el tramo del medio en varias posiciones (para rodear patios)
    medios = [[(b1[0], a1[1])], [(a1[0], b1[1])]]
    x0, x1 = sorted((a1[0], b1[0]))
    y0, y1 = sorted((a1[1], b1[1]))
    for f in (0.25, 0.5, 0.75):
        xm, ym = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        medios += [[(xm, a1[1]), (xm, b1[1])], [(a1[0], ym), (b1[0], ym)]]
    for d in (1.0, 2.5, 4.0):              # o dando un rodeo por fuera de la caja que forman los extremos
        medios += [[(x0 - d, a1[1]), (x0 - d, b1[1])], [(x1 + d, a1[1]), (x1 + d, b1[1])],
                   [(a1[0], y0 - d), (b1[0], y0 - d)], [(a1[0], y1 + d), (b1[0], y1 + d)]]
    opciones = []
    for medio in medios:
        pts = _limpiar([a0, a1, *medio, b1, b0])
        coste = lz.cruces(pts) + lz.encima(pts)
        if contorno:                       # que no salga de la vivienda (p. ej. por un patio de luces)
            coste += 100 * sum(1 for q in medio if not _dentro(q, contorno)) + 5 * _fuera(pts, contorno)
        if evitar and _cruza(pts, evitar):
            coste += 1000
        opciones.append((coste + 0.5 * (len(pts) - 2), _longitud(pts), pts))
    return min(opciones, key=lambda o: (o[0] + o[1] / (10 * lz.k), o[1]))[2]


def _fuera(camino, contorno, paso: float = 0.2) -> int:
    """Cuántos puntos del recorrido (cada `paso` m) caen fuera del contorno."""
    n = 0
    for p, q in zip(camino, camino[1:]):
        m = max(1, int(math.dist(p, q) / paso))
        n += sum(1 for k in range(1, m) if not _dentro((p[0] + (q[0] - p[0]) * k / m,
                                                      p[1] + (q[1] - p[1]) * k / m), contorno))
    return n


def _cruza(camino, polis, paso: float = 0.2) -> bool:
    for p, q in zip(camino, camino[1:]):
        n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / paso))
        for k in range(n + 1):
            r = (p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n)
            if any(_dentro(r, pl) for pl in polis):
                return True
    return False


def _buscar(estancias, patron: str):
    return next((e for e in estancias if re.search(patron, normalizar(e.nombre))), None)


def _registros_estancia(principal: bool, es_salon: bool) -> list[str]:
    """Registros por estancia según el reparto del dimensionado (Anexo III 5.13; Anexo II 3.5)."""
    if principal:
        return ["PT", "PT", "TB", "TV"] + (["FO"] if es_salon else [])
    return ["PT", "TV"]


def _grupo_tomas(lz: _Lienzo, poli, ref, cods: list[str]):
    """Las tomas de una estancia, juntas en la pared más cercana a su rótulo. Devuelve [(código, punto en la
    pared, punto de entrada del tubo)], la dirección de la pared y la normal hacia dentro."""
    k = lz.k
    paso = (TOMA[0] + SEP_TOMAS) * k
    largo = len(cods) * TOMA[0] * k + (len(cods) - 1) * SEP_TOMAS * k
    sitio = _junto_a_pared(poli, ref, largo)
    (cx, cy), u, n = sitio if sitio else ((ref[0], ref[1] - 0.45), (1.0, 0.0), (0.0, -1.0))
    fondo = TOMA[1] + TOMA[2]
    tomas = []
    for j, cod in enumerate(cods):
        off = (j - (len(cods) - 1) / 2) * paso
        q = (cx + u[0] * off, cy + u[1] * off)
        lz.en_pared("ICT_TOMA", q, n, {"COD": SIGLAS[cod]}, TOMA[0], fondo, "ICT_TOMAS")
        tomas.append((cod, q, (q[0] + n[0] * fondo * k, q[1] + n[1] * fondo * k)))
    return tomas, u, n


def tubos_del_proyecto(proyecto) -> dict:
    """Número y diámetro de tubos de cada canalización, del dimensionado (lo mismo que dice la memoria)."""
    from . import normativa as N
    from .dimensionado import dimensionar
    tubos = {"acceso": f"{N.ACCESO_VIVIENDA['tubos']}Ø{N.ACCESO_VIVIENDA['diametro_mm']} mm", "interior_mm": 20,
             "principal": "", "externa": "", "enlace_superior": ""}
    try:
        r = dimensionar(proyecto)
    except Exception:
        return tubos
    claves = {"Canalización principal": "principal", "Canalización externa": "externa",
              "Canalización de enlace superior": "enlace_superior"}
    for s in r.secciones:
        for p in s.partidas:
            m = re.match(r"(\d+) tubos Ø(\d+)", str(p.valor))
            clave = next((c for t, c in claves.items() if p.concepto.startswith(t)), None)
            if m and clave and not tubos[clave]:
                tubos[clave] = f"{m.group(1)}Ø{m.group(2)} mm"
            m = re.search(r"interior Ø(\d+)", p.concepto)
            if m:
                tubos["interior_mm"] = int(m.group(1))
    return tubos


def _dibujar_vista(msp, v: Vista, proyecto, polis: list, holgura: float, hacia_cp=None, k: float = 0.1,
                   tubos: Optional[dict] = None, muros: Optional[list] = None, huecos: Optional[list] = None):
    """Dibuja la ICT de una planta. `hacia_cp`: dónde está la canalización principal en las plantas ya
    dibujadas (para que sea la misma vertical); `k`: metros del dibujo por mm de papel; `muros`: segmentos de
    las paredes del arquitecto, para que los rótulos no las pisen. Devuelve mediciones, avisos, centro del RITS
    (en la vista leída) y posición de la canalización principal."""
    tubos = tubos or tubos_del_proyecto(proyecto)
    lz = _Lienzo(msp, k)
    lz.muros = list(muros or [])
    med, avisos = [], []
    p = v.planta
    mover = lambda x, y: (x + v.dx, y + v.dy)  # noqa: E731
    todas = [e for viv in p.viviendas for e in viv.estancias] + list(p.otras_estancias)
    for e in todas:
        lz.ocupar(_caja_rotulo_arquitecto(e.nombre, mover(e.x, e.y)))
    # Patios, terrazas y demás espacios exteriores (con su superficie útil dibujada, o el contorno que rodea su
    # rótulo, como los patios de luces): los tubos no pasan por ellos
    exteriores = [pl for pl in (_poligono_de(mover(e.x, e.y), polis) for e in todas if _es_exterior(e.nombre)) if pl]
    exteriores += list(huecos or [])

    # Recintos: su contorno y el nombre dentro
    rits = salida_riti = riti = None
    for e in p.otras_estancias:
        n = normalizar(e.nombre)
        es_riti = re.search(r"\bR\.?I\.?T\.?[UI]\b", n)
        if not (es_riti or re.search(r"ARM.*TELEC|RITS", n)):
            continue
        q = mover(e.x, e.y)
        poli = _poligono_de(q, polis)
        if poli and _area(poli) > max(2 * e.superficie_m2, 3.0):
            poli = None                 # el rótulo cae en una estancia mayor (el zaguán): no es el recinto
        nombre = ("RITI" if proyecto.edificio.recintos == "RITI_RITS" else "RITU") if es_riti else "RITS"
        caja = _recinto(lz, q, poli, nombre)
        if es_riti:
            riti = q
            salida_riti = (caja[2] + (CP_RADIO + 0.6) * k, (caja[1] + caja[3]) / 2)
        else:
            rits = ((caja[0] + caja[2]) / 2 - v.dx, (caja[1] + caja[3]) / 2 - v.dy)   # en la vista leída

    # Registro secundario y, a su lado, la canalización principal, en una pared de la zona común
    comun = _buscar(p.otras_estancias, r"COMUN|RELLANO|DESCANSILLO")
    rs = cp = n_rs = None
    if p.viviendas and comun:
        lc = mover(comun.x, comun.y)
        largo = (RS_MM[0] + 1.0 + 2 * CP_RADIO) * k
        sitio = _junto_a_pared(_poligono_de(lc, polis), lc, largo, hacia=hacia_cp)
        (cx, cy), u, n_rs = sitio if sitio else ((lc[0], lc[1] - 0.6), (1.0, 0.0), (0.0, 1.0))
        d_rs, d_cp = (2 * CP_RADIO + 1.0) / 2 * k, (RS_MM[0] + 1.0) / 2 * k
        if hacia_cp and math.dist((cx + u[0] * d_cp, cy + u[1] * d_cp), hacia_cp) < math.dist(
                (cx - u[0] * d_cp, cy - u[1] * d_cp), hacia_cp):
            u = (-u[0], -u[1])                    # la canalización principal, del lado de la de abajo
        q_rs = (cx + u[0] * d_rs, cy + u[1] * d_rs)
        lz.en_pared("ICT_RS", q_rs, n_rs, {"COD": "RS"}, RS_MM[0], RS_MM[1], "ICT_REGISTROS")
        rs = (q_rs[0] + n_rs[0] * RS_MM[1] * k, q_rs[1] + n_rs[1] * RS_MM[1] * k)      # salida de los tubos
        dentro = (CP_RADIO + 0.4) * k
        cp = (cx - u[0] * d_cp + n_rs[0] * dentro, cy - u[1] * d_cp + n_rs[1] * dentro)
        msp.add_blockref("ICT_CP", cp, dxfattribs={"layer": "ICT_CANALIZACION", "xscale": k, "yscale": k})
        r = CP_RADIO * k
        lz.ocupar((cp[0] - r, cp[1] - r, cp[0] + r, cp[1] + r))

    # RTR, toma configurable y tomas de cada estancia (primero todos los símbolos; después los tubos)
    planta_proy = [pl for pl in proyecto.edificio.plantas if pl.nivel in v.niveles]
    viviendas = []
    for i, viv in enumerate(p.viviendas):
        ids = [pl.usuarios[i].id for pl in planta_proy if i < len(pl.usuarios)]
        usuario = next((pl.usuarios[i] for pl in planta_proy if i < len(pl.usuarios)), None)
        contorno = [mover(x, y) for x, y in viv.contorno]
        # RTR junto a la entrada: en la pared más cercana al registro secundario del vestíbulo o, si la
        # vivienda no tiene, de la estancia más cercana a él (por la que se entra)
        vest = _buscar(viv.estancias, r"VESTIBULO|RECIBIDOR|HALL")
        entrada = _poligono_de(mover(vest.x, vest.y), polis) if vest else None
        if not entrada and rs:
            cand = [pl for pl in (_poligono_de(mover(e.x, e.y), polis) for e in viv.estancias) if pl]
            entrada = min(cand, key=lambda pl: min(_dist_segmento(rs, a, b) for a, b in _aristas(pl)), default=None)
        largo = (RTR_MM[0] + 0.8 + TOMA[0]) * k
        sitio = _junto_a_pared(entrada, mover(vest.x, vest.y) if vest else entrada[0], largo, hacia=rs) \
            if entrada else None
        if sitio:
            (cx, cy), u, n = sitio
        elif vest or rs:
            ref = mover(vest.x, vest.y) if vest else rs
            (cx, cy), u, n = (ref[0], ref[1] - 0.5), (1.0, 0.0), (0.0, -1.0)
        else:
            continue
        # el RTR del lado del registro secundario y la toma configurable al otro (Anexo II 3.5 c)
        d_rtr, d_c = (TOMA[0] + 0.8) / 2 * k, (RTR_MM[0] + 0.8) / 2 * k
        if rs and math.dist((cx + u[0] * d_rtr, cy + u[1] * d_rtr), rs) < math.dist(
                (cx - u[0] * d_rtr, cy - u[1] * d_rtr), rs):
            u = (-u[0], -u[1])
        q_rtr = (cx - u[0] * d_rtr, cy - u[1] * d_rtr)
        q_c = (cx + u[0] * d_c, cy + u[1] * d_c)
        lz.en_pared("ICT_RTR", q_rtr, n, {"L1": "PAU", "L2": "RTR"}, RTR_MM[0], RTR_MM[1], "ICT_REGISTROS")
        lz.en_pared("ICT_TOMA", q_c, n, {"COD": "C"}, TOMA[0], TOMA[1] + TOMA[2], "ICT_TOMAS")
        estancias = []
        principales = {e.nombre for e in (usuario.estancias if usuario else []) if e.principal}
        for e, ep in zip(viv.estancias, usuario.estancias if usuario else []):
            if not ep.es_computable:
                continue
            regs = _registros_estancia(ep.principal and ep.nombre in principales, ep.tipo.value == "salon")
            le = mover(e.x, e.y)
            tomas, u_g, n_g = _grupo_tomas(lz, _poligono_de(le, polis), le, regs)
            estancias.append((regs, tomas, n_g))
        viviendas.append((ids, contorno, q_rtr, u, n, q_c, estancias))

    # Tubos: acometida del registro secundario a cada RTR e interiores del RTR a cada estancia
    rotulos = []
    for ids, contorno, q_rtr, u, n, q_c, estancias in viviendas:
        borde = (q_rtr[0] + n[0] * RTR_MM[1] * k, q_rtr[1] + n[1] * RTR_MM[1] * k)   # cara interior del RTR
        # una salida por tubo repartida a lo largo del RTR, ordenadas como sus destinos, para que no se crucen
        destinos = [min(t, key=lambda x: math.dist(x[2], borde)) for _, t, _ in estancias]
        orden = sorted(range(len(estancias)), key=lambda j: (destinos[j][2][0] - borde[0]) * u[0]
                       + (destinos[j][2][1] - borde[1]) * u[1])
        n_sal = len(estancias)
        util = (RTR_MM[0] - 1.6) * k
        salidas = [(borde[0] + u[0] * (-util / 2 + util * j / max(n_sal - 1, 1)),
                    borde[1] + u[1] * (-util / 2 + util * j / max(n_sal - 1, 1))) for j in range(n_sal)]
        if n_sal == 1:
            salidas = [borde]
        sec = 0.0
        if rs:
            # la acometida llega al RTR por detrás, a través de la pared, desde el registro secundario
            pts = _ruta(lz, rs, n_rs, q_rtr, (-n[0], -n[1]), evitar=exteriores)
            lz.linea(pts)
            rotulos.append((pts, tubos["acceso"]))
            sec = _longitud(pts) + 2 * holgura
            if _longitud(pts) > 15:
                avisos.append(f"{' / '.join(ids)}: el tramo registro secundario-RTR mide {_longitud(pts):.1f} m "
                              "en planta (más de 15 m): hacen falta registros de paso (Anexo III, 5.9).")
        m = Medicion(" / ".join(ids), round(float(sec), 1))
        # toma configurable: tubo corto desde el lado del RTR
        lado = (q_rtr[0] + u[0] * RTR_MM[0] / 2 * k + n[0] * RTR_MM[1] / 2 * k,
                q_rtr[1] + u[1] * RTR_MM[0] / 2 * k + n[1] * RTR_MM[1] / 2 * k)
        c_entrada = (q_c[0] - u[0] * TOMA[0] / 2 * k + n[0] * (TOMA[2] + TOMA[1] / 2) * k,
                     q_c[1] - u[1] * TOMA[0] / 2 * k + n[1] * (TOMA[2] + TOMA[1] / 2) * k)
        lz.linea([lado, c_entrada])
        interiores = [0.0] * len(estancias)
        for idx, (s, j) in enumerate(zip(salidas, orden)):
            regs, tomas, n_g = estancias[j]
            destino = destinos[j]
            # cada tubo se separa del RTR una distancia distinta, para que sus tramos no vayan unos encima de otros
            pts = _ruta(lz, s, n, destino[2], n_g, contorno, evitar=exteriores,
                        salida_mm=1.8 + 1.0 * min(idx, n_sal - 1 - idx))
            lz.linea(pts)
            rotulos.append((pts, f"{len(regs)}Ø{tubos['interior_mm']} mm"))
            tv = next(t for t in tomas if t[0] == "TV")
            interiores[j] = _longitud(pts) + math.dist(tv[1], destino[1]) + 2 * holgura
        m.interior_m = [round(float(x), 1) for x in interiores]
        med.append(m)
    for pts, texto in rotulos:
        lz.rotular_tubo(pts, texto)

    # Planta baja: del RITI, por el techo, al pie de la vertical; y la acometida desde la arqueta de entrada
    if salida_riti:
        msp.add_blockref("ICT_CP", salida_riti, dxfattribs={"layer": "ICT_CANALIZACION", "xscale": k, "yscale": k})
        r = CP_RADIO * k
        lz.ocupar((salida_riti[0] - r, salida_riti[1] - r, salida_riti[0] + r, salida_riti[1] + r))
        if hacia_cp and not p.viviendas and math.dist(salida_riti, hacia_cp) > 0.5:
            pts = _ruta(lz, salida_riti, None, hacia_cp, None)
            lz.linea(pts)
            msp.add_blockref("ICT_CP", hacia_cp, dxfattribs={"layer": "ICT_CANALIZACION", "xscale": k, "yscale": k})
            lz.ocupar((hacia_cp[0] - r, hacia_cp[1] - r, hacia_cp[0] + r, hacia_cp[1] + r))
            if tubos["principal"]:
                lz.rotular_tubo(pts, tubos["principal"])
            cp = hacia_cp
        caja_planta = _caja_contenido(p, 0.0)
        centro = mover((caja_planta[0] + caja_planta[2]) / 2, (caja_planta[1] + caja_planta[3]) / 2) if (
            caja_planta) else ((v.ventana[0] + v.ventana[2]) / 2, (v.ventana[1] + v.ventana[3]) / 2)
        _acometida(lz, riti, centro, polis, tubos)
    if cp:
        lz.rotulo_libre([f"C.P. {tubos['principal']}".strip()], cp, CP_RADIO * k)

    # Nombre de cada vivienda, donde no pise nada
    for ids, contorno, *_ in viviendas:
        texto = " / ".join(ids)
        x, y = _sitio_rotulo(lz, contorno, texto, H_VIVIENDA * k)
        lz.texto(texto, (x, y), H_VIVIENDA, negrita=True)
    return med, avisos, rits, cp


def _sitio_rotulo(lz: _Lienzo, contorno, texto: str, h: float, paso: float = 0.3):
    """Punto de la vivienda donde su nombre no pisa textos, símbolos ni tubos (el más cercano al centro)."""
    xs, ys = [p[0] for p in contorno], [p[1] for p in contorno]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    mejor = None
    y = min(ys) + paso
    while y < max(ys):
        x = min(xs) + paso
        while x < max(xs):
            caja = _caja_texto(texto, (x, y), h, C, 0.0, True)
            esquinas = ((caja[0], caja[1]), (caja[2], caja[1]), (caja[2], caja[3]), (caja[0], caja[3]))
            if all(_dentro(q, contorno) for q in esquinas):
                coste = (lz.coste(caja), math.hypot(x - cx, y - cy))
                if mejor is None or coste < mejor[0]:
                    mejor = (coste, (x, y))
            x += paso
        y += paso
    return mejor[1] if mejor else (cx, cy)


def _recinto(lz: _Lienzo, q, poli, nombre: str) -> tuple[float, float, float, float]:
    """Contorno del recinto (el del arquitecto si lo hay) con su nombre dentro. Devuelve su caja."""
    if not poli:
        poli = [(q[0] - 0.5, q[1] - 0.3), (q[0] + 0.5, q[1] - 0.3), (q[0] + 0.5, q[1] + 0.3), (q[0] - 0.5, q[1] + 0.3)]
    lz.msp.add_lwpolyline(poli, close=True, dxfattribs={"layer": "ICT_RECINTOS"})
    caja = (min(p[0] for p in poli), min(p[1] for p in poli), max(p[0] for p in poli), max(p[1] for p in poli))
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    giro = 90.0 if alto > ancho * 1.3 else 0.0           # a lo largo del recinto
    largo, corto = (alto, ancho) if giro else (ancho, alto)
    h_mm = H_RECINTO
    while h_mm > 0.9 and (_ancho_texto(nombre, h_mm * lz.k, True) > 0.85 * largo or h_mm * lz.k > 0.7 * corto):
        h_mm -= 0.1
    lz.texto(nombre, ((caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2), h_mm, "ICT_RECINTOS", C, giro, negrita=True)
    lz.ocupar(caja)
    return caja


def _acometida(lz: _Lienzo, riti, centro, polis, tubos: dict) -> None:
    """Arqueta de entrada fuera del edificio: desde el centro de la planta, en la dirección del RITI, 1,2 m
    más allá de la última estancia que se cruza (pasado el muro de fachada)."""
    vx, vy = riti[0] - centro[0], riti[1] - centro[1]
    n = math.hypot(vx, vy) or 1
    ux, uy = vx / n, vy / n
    ultimo = 0.0
    for j in range(1, 81):                       # hasta 8 m más allá del RITI
        q = (riti[0] + ux * 0.1 * j, riti[1] + uy * 0.1 * j)
        if any(_dentro(q, pl) for pl in polis):
            ultimo = 0.1 * j
    d = ultimo + 1.2
    arq = (riti[0] + ux * d, riti[1] + uy * d)
    k = lz.k
    lz.msp.add_blockref("ICT_ARQ", arq, dxfattribs={"layer": "ICT_ACOMETIDA", "xscale": k, "yscale": k})
    a = ARQUETA_MM / 2 * k
    lz.ocupar((arq[0] - a, arq[1] - a, arq[0] + a, arq[1] + a))
    inicio = (arq[0] - ux * a, arq[1] - uy * a)
    lz.linea([inicio, riti], capa="ICT_ACOMETIDA", tipo="ICT_TRAZOS")
    if tubos.get("externa"):
        lz.rotular_tubo([inicio, riti], tubos["externa"], capa="ICT_ACOMETIDA")
    lz.rotulo_libre(["Arqueta de entrada 400x400x600 mm", "(ubicación según consulta a operadores)"], arq, a,
                    capa="ICT_ACOMETIDA")


def _cubierta(msp, v: Vista, mastil: Optional[tuple[float, float]], rits_cubierta: Optional[tuple],
              acceso: str, huecos=(), k: float = 0.1, tubos: Optional[dict] = None,
              lineas: Optional[list] = None) -> None:
    """Mástil, su radio libre y el enlace superior hasta el RITS sin cruzar los `huecos` (patios). `lineas`:
    segmentos del dibujo de la cubierta, para que los rótulos no los pisen."""
    lz = _Lienzo(msp, k)
    lz.muros = list(lineas or [])
    x0, y0 = v.ventana[0], v.ventana[1]
    lz.texto(f"Acceso a cubierta: {acceso or '[PENDIENTE: definir]'}", (x0 + 0.5, y0 + 0.6), H_NOTA, "ICT_RTV",
             TextEntityAlignment.LEFT)
    if not mastil:
        lz.texto("[PENDIENTE: posición del mástil]", (x0 + 0.5, y0 + 0.6 + 3 * H_NOTA * k), H_NOTA, "ICT_RTV",
                 TextEntityAlignment.LEFT)
        return
    r = 1.2 * k
    msp.add_circle(mastil, r, dxfattribs={"layer": "ICT_RTV"})
    lz.ocupar((mastil[0] - r, mastil[1] - r, mastil[0] + r, mastil[1] + r))
    msp.add_circle(mastil, 5.0, dxfattribs={"layer": "ICT_RTV", "linetype": "ICT_TRAZOS"})
    if rits_cubierta:
        pts = _ruta(lz, mastil, None, rits_cubierta, None, evitar=huecos)
        lz.linea(pts, capa="ICT_RTV")
        msp.add_circle(rits_cubierta, 0.8 * k, dxfattribs={"layer": "ICT_RTV"})
        lz.ocupar((rits_cubierta[0] - k, rits_cubierta[1] - k, rits_cubierta[0] + k, rits_cubierta[1] + k))
        lz.rotular_tubo(pts, (tubos or {}).get("enlace_superior") or "2Ø40 mm", capa="ICT_RTV")
        lz.rotulo_libre(["Paso al RITS"], rits_cubierta, 0.8 * k, capa="ICT_RTV")
    lz.rotulo_libre(["Mástil de antenas (UHF, FM y DAB)", "Radio libre de 5 m (Anexo I, 4.2.1)"], mastil, r,
                    capa="ICT_RTV")


# --------------------------------------------------------------------------------------- hojas

@dataclass
class Formato:
    """Hoja A3: zona de dibujo y zona de leyenda (mm), y la plantilla DXF del cajetín de AJP si la hay."""
    dibujo: tuple[float, float, float, float]
    leyenda: tuple[float, float, float, float]
    plantilla: Optional[Path] = None
    capa_ventana: str = "ICT_VENTANAS"
    capa_leyenda: str = "ICT_LEYENDA"
    estilo: str = "ICT_ARIAL"
    estilo_negrita: str = "ICT_NEGRITA"
    marco: tuple = ()                    # x0, y0, x1, y1 del marco de la hoja
    colores: Optional[dict] = None       # colores de la empresa: {"texto", "secundario", "marca"} en hexadecimal


# Sin plantilla (pruebas, o si falta la carpeta de AJP): cajetín sencillo abajo y leyenda arriba a la derecha
FORMATO_BASICO = Formato(
    dibujo=(MARGEN + 2, MARGEN + ALTO_CAJETIN + 2, HOJA[0] - MARGEN - ANCHO_LEYENDA - 3, HOJA[1] - MARGEN - 2),
    leyenda=(HOJA[0] - MARGEN - ANCHO_LEYENDA, HOJA[1] - MARGEN - 95, HOJA[0] - MARGEN - 2, HOJA[1] - MARGEN - 2))


def formato_de_plantilla(ruta: str | Path, colores: Optional[dict] = None) -> Formato:
    """Lee la presentación de la plantilla de AJP: el marco (capa *MARCO) y el cajetín (polilínea cerrada de la
    capa *CAJETIN). El dibujo va encima del cajetín y la leyenda, a su izquierda («LEYENDA / CUADROS»).
    Con `colores`, el cajetín se pinta con los colores de la empresa."""
    doc = ezdxf.readfile(str(ruta))
    hoja = next(l for l in doc.layouts if l.name != "Model")

    def caja(patron: str):
        polis = [e for e in hoja.query("LWPOLYLINE") if e.closed and re.search(patron, e.dxf.layer, re.I)]
        pts = max(([p[:2] for p in e.get_points("xy")] for e in polis), key=_area)
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    mx0, my0, mx1, my1 = caja(r"MARCO$")
    cx0, _, _, cy1 = caja(r"CAJETIN$")
    return Formato(dibujo=(mx0 + 2, cy1 + 2, mx1 - 2, my1 - 2), leyenda=(mx0 + 2, my0 + 2, cx0 - 2, cy1 - 2),
                   plantilla=Path(ruta), capa_ventana="X-VENTANAS", capa_leyenda="G-LEYENDA", estilo="AJP",
                   estilo_negrita="AJP-NEGRITA", marco=(mx0, my0, mx1, my1), colores=colores)


def colores_empresa(plantilla) -> Optional[dict]:
    """Colores corporativos de empresa.json (estilo): texto, secundario y el de la marca."""
    if not plantilla or not plantilla.carpeta:
        return None
    return {"texto": plantilla.estilo("color_texto", "1F1F1F"), "secundario": plantilla.estilo("color_secundario", "555555"),
            "marca": plantilla.estilo("color_marca", "FBC213")}


def _rgb(hexa: str) -> int:
    from ezdxf import colors
    h = hexa.lstrip("#")
    return colors.rgb2int((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))


def _colores_corporativos(lay, formato: Formato, numero=None) -> None:
    """Cajetín y leyenda con los colores de la empresa: textos y líneas en su gris oscuro, etiquetas en el
    secundario, el logo con su color, una franja del color de la marca encima del cajetín y el número de plano
    en ese color."""
    c = formato.colores
    if not c:
        return
    oscuro, gris, marca = _rgb(c["texto"]), _rgb(c["secundario"]), _rgb(c["marca"])
    for e in lay:
        capa = e.dxf.layer.upper()
        if e.dxftype() in ("INSERT", "VIEWPORT") or not capa.startswith("G-"):
            continue                          # el logo conserva su color; la ICT, el de sus capas
        if capa.endswith("FINO"):
            e.dxf.true_color = gris
        elif not e.dxf.hasattr("true_color") and e.dxf.get("color", 256) in (0, 256):
            e.dxf.true_color = oscuro
    if numero is not None:                        # el texto del número de plano
        numero.dxf.true_color = marca
    if formato.marco:
        x0, _, x1, _ = formato.marco
        y = formato.dibujo[1] - 2                 # borde superior de la franja del cajetín
        lay.add_line((x0, y), (x1, y), dxfattribs={"layer": "G-CAJETIN", "true_color": marca, "lineweight": 70})


def _escala(ventana, formato: Formato = FORMATO_BASICO) -> int:
    x0, y0, x1, y1 = ventana
    d = formato.dibujo
    return next((e for e in ESCALAS if (x1 - x0) * 1000 / e <= d[2] - d[0] and (y1 - y0) * 1000 / e <= d[3] - d[1]),
                ESCALAS[-1])


def _medidor(fuente: str, h: float):
    try:
        from ezdxf.fonts import fonts
        return fonts.make_font(fuente, h).text_width
    except Exception:
        return lambda s: 0.6 * h * len(s)


def _partir(texto: str, ancho_mm: float, h: float) -> list[str]:
    """Reparte el texto en líneas que caben en `ancho_mm` con Arial de altura `h`."""
    medir = _medidor("arial.ttf", h)
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if actual and medir(prueba) > ancho_mm:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    return lineas


def _encajar(t, ancho_mm: float) -> None:
    """Estrecha el texto (factor de anchura hasta 0,7 y, si no basta, altura) para que quepa en su casilla."""
    doc = t.doc
    estilo = doc.styles.get(t.dxf.style) if doc and t.dxf.style in doc.styles else None
    fuente = (estilo.dxf.font if estilo else "") or "arial.ttf"
    ancho = _medidor(fuente, t.dxf.height)(t.dxf.text)
    if ancho <= ancho_mm or ancho <= 0:
        return
    factor = ancho_mm / ancho
    t.dxf.width = max(0.7, factor)
    if factor < 0.7:
        t.dxf.height *= factor / 0.7


def _rellenar_cajetin(lay, valores: dict) -> tuple[list[str], dict]:
    """Pone los valores en las casillas del cajetín de la plantilla. Cada casilla se reconoce por su etiqueta
    (texto en la capa *FINO: «PROYECTO», «Nº PLANO»...) y su valor es el texto que tiene justo debajo.
    Devuelve las etiquetas que no se han encontrado y el texto rellenado de cada casilla."""
    textos = list(lay.query("TEXT"))
    etiquetas = [t for t in textos if t.dxf.layer.upper().endswith("FINO")]
    contenidos = [t for t in textos if t not in etiquetas]
    borde = max((p[0] for e in lay.query("LWPOLYLINE") if re.search(r"CAJETIN$", e.dxf.layer, re.I)
                 for p in e.get_points("xy")), default=HOJA[0] - MARGEN)
    faltan, rellenas = [], {}
    for clave, valor in valores.items():
        et = next((t for t in etiquetas if normalizar(t.dxf.text) == normalizar(clave)), None)
        if et is None:
            faltan.append(clave)
            continue
        ex, ey = et.dxf.insert.x, et.dxf.insert.y
        derecha = min([o.dxf.insert.x for o in etiquetas if abs(o.dxf.insert.y - ey) < 0.5 and o.dxf.insert.x > ex + 1]
                      + [borde]) - 1.5
        bajo = [t for t in contenidos if ex - 2 <= t.dxf.insert.x < derecha and ey - 12 < t.dxf.insert.y < ey]
        if not bajo:
            faltan.append(clave)
            continue
        t = max(bajo, key=lambda t: t.dxf.insert.y)
        t.dxf.text = valor
        izquierda = ex - 1 if t.dxf.get("halign", 0) else t.dxf.insert.x
        _encajar(t, derecha - izquierda - 1)
        rellenas[clave] = t
    return faltan, rellenas


def _cajetin_basico(lay, valores: dict) -> None:
    a = {"layer": "ICT_CAJETIN"}
    lay.add_lwpolyline([(MARGEN, MARGEN), (HOJA[0] - MARGEN, MARGEN), (HOJA[0] - MARGEN, HOJA[1] - MARGEN),
                        (MARGEN, HOJA[1] - MARGEN)], close=True, dxfattribs=a)
    yb = MARGEN + ALTO_CAJETIN
    lay.add_line((MARGEN, yb), (HOJA[0] - MARGEN, yb), dxfattribs=a)
    xs = COLUMNAS_CAJETIN
    for x in xs[1:-1]:
        lay.add_line((x, MARGEN), (x, yb), dxfattribs=a)
    lay.add_line((MARGEN, MARGEN + ALTO_CAJETIN / 2), (xs[1], MARGEN + ALTO_CAJETIN / 2), dxfattribs=a)

    def t(texto, x, y, h=2.5, estilo="ICT_ITALICA", alin=TextEntityAlignment.LEFT):
        lay.add_text(texto, height=h, dxfattribs={"layer": "ICT_CAJETIN", "style": estilo}).set_placement(
            (x, y), align=alin)
    t("Autor:", MARGEN + 3, yb - 6)
    t(valores.get("autor", ""), MARGEN + 18, yb - 10)
    t("Descripción:", MARGEN + 3, MARGEN + ALTO_CAJETIN / 2 - 6)
    t(valores.get("PLANO", ""), MARGEN + 25, MARGEN + ALTO_CAJETIN / 2 - 10)
    # Celda en blanco: proyecto y emplazamiento en las líneas que hagan falta
    ancho = xs[2] - xs[1] - 4
    for h in (1.8, 1.6, 1.4):
        lineas = [ln for clave in ("PROYECTO", "EMPLAZAMIENTO") if valores.get(clave)
                  for ln in _partir(valores[clave], ancho, h)]
        if len(lineas) * 1.7 * h <= ALTO_CAJETIN - 4:
            break
    for k, linea in enumerate(lineas):
        t(linea, xs[1] + 2, yb - 3 - h - 1.7 * h * k, h=h, estilo="ICT_ARIAL")
    t("Nº Plano", (xs[2] + xs[3]) / 2, yb - 7, alin=TextEntityAlignment.MIDDLE_CENTER)
    t(valores.get("Nº PLANO", ""), (xs[2] + xs[3]) / 2, MARGEN + 10, h=5.6, alin=TextEntityAlignment.MIDDLE_CENTER)
    t("Escala:", (xs[3] + xs[4]) / 2, yb - 7, alin=TextEntityAlignment.MIDDLE_CENTER)
    t(valores.get("ESCALA", ""), (xs[3] + xs[4]) / 2, MARGEN + 10, h=5.6, alin=TextEntityAlignment.MIDDLE_CENTER)
    t("Firma:", xs[4] + 3, yb - 6)


def _hoja(doc, nombre: str, v: Vista, numero: int, datos: dict, escala: int, formato: Formato = FORMATO_BASICO,
          plantilla=None) -> list[str]:
    """Presentación A3 con la ventana a la planta, el cajetín y la leyenda. `plantilla`: (importador, entidades
    de la presentación de la plantilla de AJP). Devuelve avisos (casillas del cajetín que no se han encontrado)."""
    x0, y0, x1, y1 = v.ventana
    lay = doc.layouts.new(nombre)
    lay.page_setup(size=HOJA, margins=(0, 0, 0, 0), units="mm")
    d = formato.dibujo
    lay.add_viewport(center=((d[0] + d[2]) / 2, (d[1] + d[3]) / 2),
                     size=((x1 - x0) * 1000 / escala, (y1 - y0) * 1000 / escala),
                     view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=y1 - y0,
                     dxfattribs={"layer": formato.capa_ventana})
    valores = {**datos, "PLANO": f"ICT · {v.titulo}", "Nº PLANO": f"{numero:02d}", "ESCALA": f"1:{escala}"}
    avisos = []
    if plantilla:
        importador, entidades = plantilla
        importador.import_entities(entidades, lay)
        faltan, rellenas = _rellenar_cajetin(lay, {k: valores.get(k, "") for k in CASILLAS_CAJETIN})
        avisos += [f"Cajetín de la plantilla: no se encuentra la casilla «{c}»." for c in faltan]
        _leyenda(lay, formato)
        _colores_corporativos(lay, formato, rellenas.get("Nº PLANO"))
    else:
        _cajetin_basico(lay, valores)
        _leyenda(lay, formato)
    return avisos


CASILLAS_CAJETIN = ("PROYECTO", "EMPLAZAMIENTO", "TITULAR", "PLANO", "Nº PLANO", "ESCALA", "FECHA", "REV.",
                    "EXPEDIENTE")


def _filas_leyenda() -> list[tuple[str, str]]:
    return [("TOMA:RJ45", "Toma de pares trenzados (RJ45)"), ("TOMA:TV", "Toma de radio y televisión (RTV)"),
            ("TOMA:TBA", "Toma coaxial de banda ancha (TBA)"), ("TOMA:FO", "Toma de fibra óptica"),
            ("TOMA:C", "Toma configurable"), ("ICT_RTR", "Registro de terminación de red, con el PAU"),
            ("ICT_RS", "Registro secundario de planta"), ("ICT_CP", "Canalización principal (vertical)"),
            ("ICT_ARQ", "Arqueta de entrada"), ("RECINTO", "Recinto de telecomunicaciones (RITI / RITS)"),
            ("LINEA", "Tubos, con su número y diámetro"), ("DISCONTINUA", "Canalización externa")]


def _leyenda(lay, formato: Formato) -> None:
    """Leyenda sin recuadro, como en los planos de AJP: título en negrita y, debajo, símbolo y descripción, en
    las columnas que hagan falta para caber en su zona. Los símbolos son los mismos bloques del plano, a su
    tamaño en papel."""
    x0, y0, x1, y1 = formato.leyenda
    a = {"layer": formato.capa_leyenda}
    lay.add_text("LEYENDA ICT", height=2.1, dxfattribs={**a, "style": formato.estilo_negrita}).set_placement(
        (x0 + 1, y1 - 2.1), align=TextEntityAlignment.LEFT)
    filas = _filas_leyenda()
    alto = 5.4
    arriba = y1 - 6.0
    por_columna = max(1, int((arriba - y0) // alto))
    columnas = math.ceil(len(filas) / por_columna)
    ancho_col = (x1 - x0) / columnas
    en_pared = {"ICT_RTR": (RTR_MM, {"L1": "PAU", "L2": "RTR"}, "ICT_REGISTROS"),
                "ICT_RS": (RS_MM, {"COD": "RS"}, "ICT_REGISTROS")}
    for k, (simbolo, desc) in enumerate(filas):
        cx = x0 + ancho_col * (k // por_columna) + 6
        cy = arriba - alto * (k % por_columna) - alto / 2
        if simbolo.startswith("TOMA:") or simbolo in en_pared:
            if simbolo.startswith("TOMA:"):
                (ancho, fondo), valores, capa, bloque = (TOMA[0], TOMA[1] + TOMA[2]), {"COD": simbolo[5:]}, \
                    "ICT_TOMAS", "ICT_TOMA"
            else:
                (ancho, fondo), valores, capa = en_pared[simbolo]
                bloque = simbolo
            yp = cy + fondo / 2                   # cara de la pared
            lay.add_line((cx - ancho / 2 - 0.8, yp), (cx + ancho / 2 + 0.8, yp), dxfattribs={**a, "color": 8})
            _atributos(lay.add_blockref(bloque, (cx, yp), dxfattribs={"layer": capa}), valores, capa)
        elif simbolo in ("ICT_CP", "ICT_ARQ"):
            lay.add_blockref(simbolo, (cx, cy), dxfattribs={
                "layer": "ICT_CANALIZACION" if simbolo == "ICT_CP" else "ICT_ACOMETIDA"})
        elif simbolo == "RECINTO":
            lay.add_lwpolyline([(cx - 4.5, cy - 1.8), (cx + 4.5, cy - 1.8), (cx + 4.5, cy + 1.8), (cx - 4.5, cy + 1.8)],
                               close=True, dxfattribs={"layer": "ICT_RECINTOS"})
            lay.add_text("RITI", height=1.5, dxfattribs={"layer": "ICT_RECINTOS", "style": "ICT_NEGRITA"}
                         ).set_placement((cx, cy), align=C)
        else:
            capa = "ICT_CANALIZACION" if simbolo == "LINEA" else "ICT_ACOMETIDA"
            tipo = {"linetype": "ICT_TRAZOS"} if simbolo == "DISCONTINUA" else {}
            lay.add_line((cx - 5, cy - 0.7), (cx + 5, cy - 0.7), dxfattribs={"layer": capa, **tipo})
            lay.add_text("3Ø25 mm" if simbolo == "LINEA" else "4Ø63 mm", height=H_TUBO,
                         dxfattribs={"layer": capa, "style": "ICT_ARIAL"}).set_placement((cx, cy + 0.6), align=C)
        lay.add_text(desc, height=1.6, dxfattribs={**a, "style": formato.estilo}).set_placement(
            (cx + 7, cy), align=TextEntityAlignment.MIDDLE_LEFT)


# --------------------------------------------------------------------------------------- principal

_MESES = ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE",
          "NOVIEMBRE", "DICIEMBRE")


def datos_cajetin(proyecto, plantilla=None, fecha=None) -> dict:
    """Valores del cajetín comunes a todas las hojas (el plano, su número y la escala los pone cada hoja)."""
    import datetime
    dg = proyecto.datos_generales
    hoy = fecha or datetime.date.today()
    autor = (plantilla.datos.get("proyectista", {}).get("nombre", "") if plantilla else "") or dg.proyectista.nombre
    emplazamiento = ". ".join(x for x in (dg.direccion, dg.municipio) if x)
    if dg.provincia and dg.provincia not in dg.municipio:
        emplazamiento += f" ({dg.provincia})"
    return {"autor": autor, "PROYECTO": dg.titulo.upper(), "EMPLAZAMIENTO": emplazamiento,
            "TITULAR": dg.promotor, "FECHA": f"{_MESES[hoy.month - 1]} {hoy.year}",
            "REV.": proyecto.planos.revision, "EXPEDIENTE": dg.numero[-3:] if dg.numero else ""}


def ruta_cajetin(plantilla) -> Optional[Path]:
    """DXF con el cajetín de AJP de la carpeta de plantilla (clave «cajetin_planos» de empresa.json)."""
    if plantilla and plantilla.carpeta and plantilla.datos.get("cajetin_planos"):
        ruta = Path(plantilla.carpeta) / plantilla.datos["cajetin_planos"]
        return ruta if ruta.exists() else None
    return None


def generar_planos(base_dxf: str | Path, lectura: LecturaPlano, proyecto, salida: str | Path,
                   datos_cajetin: dict, mastil: Optional[tuple[float, float]] = None,
                   holgura_vertical_m: float = 1.0, imagenes: bool = True, pdf: bool = True,
                   acceso_cubierta: str = "", cajetin: Optional[str | Path] = None,
                   colores: Optional[dict] = None) -> ResultadoPlanos:
    """Plantas de la ICT. `cajetin`: DXF con la plantilla de hoja de AJP (si no, un cajetín sencillo);
    `colores`: los de la empresa para el cajetín (ver `colores_empresa`)."""
    formato = formato_de_plantilla(cajetin, colores) if cajetin else FORMATO_BASICO
    origen = ezdxf.readfile(str(base_dxf))
    vistas = vistas_ict(lectura)
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 6          # metros
    # Copiar del arquitecto solo lo que cae en cada vista (sus capas y bloques, sin tocarlos)
    ignorar = re.compile(CAPAS_IGNORADAS, re.I)
    cajas = []
    for e in origen.modelspace():
        if e.dxftype() in ("IMAGE", "OLE2FRAME", "VIEWPORT"):
            continue
        try:
            c = bbox.extents([e], fast=True)
        except Exception:
            continue
        if c.has_data:
            cajas.append((e, c.extmin.x, c.extmin.y, c.extmax.x, c.extmax.y))
    for v in vistas:
        v.ventana = _ajustar_ventana(v, cajas)
    imp = Importer(origen, doc)
    copiadas = set()
    poligonos: dict[int, list] = {}
    entidades_vista: dict[int, list] = {}
    capas_estancias = re.compile(CAPAS_ESTANCIAS, re.I)
    for k, v in enumerate(vistas):
        x0, y0, x1, y1 = v.ventana
        ents = [e for e, a, b, c, d in cajas if not (c < x0 or a > x1 or d < y0 or b > y1)
                and not ignorar.search(e.dxf.layer)]
        entidades_vista[k] = ents
        poligonos[k] = [[(p[0], p[1]) for p in e.get_points("xy")] for e in ents
                        if e.dxftype() == "LWPOLYLINE" and capas_estancias.search(e.dxf.layer) and len(e) >= 3]
        nuevas = [e for e in ents if id(e) not in copiadas]
        copiadas.update(id(e) for e in nuevas)
        imp.import_entities(nuevas, doc.modelspace())
    imp.finalize()
    _preparar(doc)
    msp = doc.modelspace()
    mediciones, avisos, presentaciones = [], [], []
    # Escala de las hojas, para dibujar los símbolos a su tamaño en papel (se comprueba al final)
    escala_prevista = max(_escala(v.ventana, formato) for v in vistas) if vistas else 100
    k_mm = escala_prevista / 1000                 # metros del dibujo por milímetro de papel
    tubos = tubos_del_proyecto(proyecto)
    rits = None
    cp_titulo = None        # canalización principal respecto al título de su vista: la misma en todas
    # Primero las plantas con viviendas, de abajo arriba; después la baja, que se une a esa vertical
    for k in sorted(range(len(vistas)), key=lambda k: (not vistas[k].planta.viviendas, min(vistas[k].niveles))):
        v = vistas[k]
        if v.planta.viviendas or any(re.search(r"R\.?I\.?T|ARM.*TELEC", normalizar(e.nombre))
                                     for e in v.planta.otras_estancias):
            tx, ty = v.planta.titulo_xy or (0.0, 0.0)
            hacia = (cp_titulo[0] + tx + v.dx, cp_titulo[1] + ty + v.dy) if cp_titulo else None
            antes = len(msp)
            m, a, centro_rits, cp = _dibujar_vista(msp, v, proyecto, poligonos[k], holgura_vertical_m, hacia,
                                                   k=k_mm, tubos=tubos, muros=segmentos_de(entidades_vista[k]),
                                                   huecos=_huecos(cajas, v.ventana))
            mediciones += m
            avisos += a
            v.ventana = _incluir(v.ventana, list(msp)[antes:])
            if centro_rits:
                rits = (centro_rits, v)         # en la vista leída: la cubierta se lee en la misma fila
            if cp and cp_titulo is None:
                cp_titulo = (cp[0] - v.dx - tx, cp[1] - v.dy - ty)
    for k, v in enumerate(vistas):
        if "CUBIERTA" in normalizar(v.planta.nombre):
            rits_cub = None
            if rits:
                # mismo desplazamiento entre vistas que entre los títulos de la planta del RITS y la cubierta
                (x, y), w = rits
                rits_cub = (x + v.planta.titulo_xy[0] - w.planta.titulo_xy[0],
                            y + v.planta.titulo_xy[1] - w.planta.titulo_xy[1])
            _cubierta(msp, v, mastil, rits_cub, acceso_cubierta, huecos=_huecos(cajas, v.ventana), k=k_mm,
                      tubos=tubos, lineas=segmentos_de(entidades_vista[k], r"."))
    escala = max(_escala(v.ventana, formato) for v in vistas) if vistas else 100   # la misma en todas las hojas
    if escala != escala_prevista:
        avisos.append(f"Los símbolos se han dibujado para 1:{escala_prevista} y las hojas salen a 1:{escala}: "
                      "en papel serán algo más pequeños.")
    plantilla = None
    if formato.plantilla:
        # De la hoja de AJP se copia todo menos sus ventanas, el rótulo de muestra de la zona de leyenda y la
        # flecha del norte (su orientación depende de cada edificio)
        doc_plantilla = ezdxf.readfile(str(formato.plantilla))
        hoja = next(l for l in doc_plantilla.layouts if l.name != "Model")
        entidades = [e for e in hoja if e.dxftype() != "VIEWPORT" and not e.dxf.layer.upper().startswith("X-")
                     and not (e.dxftype() == "TEXT" and "LEYENDA" in normalizar(e.dxf.text))
                     and not (e.dxftype() == "INSERT" and "NORTE" in normalizar(e.dxf.name))]
        importador = Importer(doc_plantilla, doc)
        importador.import_table("layers", ["X-VENTANAS", "G-LEYENDA"])
        importador.import_table("styles", ["AJP", "AJP-NEGRITA"])
        plantilla = (importador, entidades)
        avisos.append("Hojas con el cajetín de AJP: la flecha del norte no se pone (falta su orientación).")
    for k, v in enumerate(vistas, start=1):
        nombre = f"ICT-{k} {v.titulo}"[:31]
        avisos += _hoja(doc, nombre, v, k, datos_cajetin, escala, formato, plantilla)
        presentaciones.append(nombre)
    if plantilla:
        plantilla[0].finalize()
    for nombre in [l.name for l in doc.layouts if l.name not in presentaciones and l.name != "Model"]:
        doc.layouts.delete(nombre)
    salida = Path(salida)
    doc.saveas(salida)
    res = ResultadoPlanos(salida, presentaciones, mediciones, escala, avisos=avisos)
    if imagenes:
        from .vista_previa import renderizar
        for k, nombre in enumerate(presentaciones, start=1):
            png = salida.with_name(f"{salida.stem} - {k}.png")
            renderizar(salida, png, ancho_px=2400, presentacion=nombre, resaltar=COLORES_VISTA)
            res.imagenes.append(png)
    if pdf:
        from .vista_previa import renderizar_pdf
        res.pdf = renderizar_pdf(salida, salida.with_suffix(".pdf"), presentaciones, resaltar=COLORES_VISTA)
    return res


def _huecos(cajas, ventana) -> list[list[tuple]]:
    """Patios y otros huecos de una cubierta: la polilínea cerrada más pequeña que rodea cada rótulo «PATIO»,
    «HUECO», «LUCERNARIO» o «CLARABOYA» de la vista (por ellos no puede pasar un tubo)."""
    x0, y0, x1, y1 = ventana
    dentro = [e for e, a, b, c, d in cajas if a >= x0 and c <= x1 and b >= y0 and d <= y1]
    cerradas = [[(p[0], p[1]) for p in e.get_points("xy")] for e in dentro
                if e.dxftype() == "LWPOLYLINE" and e.closed and len(e) >= 3
                and not re.search(CAPAS_IGNORADAS, e.dxf.layer, re.I)]
    muros = None
    huecos = []
    for t in dentro:
        if t.dxftype() in ("TEXT", "MTEXT") and re.search(r"PATIO|HUECO|LUCERNARIO|CLARABOYA",
                                                          normalizar(t.plain_text())):
            q = (t.dxf.insert.x, t.dxf.insert.y)
            pl = min((c for c in cerradas if _dentro(q, c) and _area(c) < 60), key=_area, default=None)
            if pl is None:
                # dibujado con líneas sueltas: la caja hasta la pared más cercana en cada dirección, solo si su
                # superficie coincide con la rotulada (si no, las paredes no cierran el patio y no se usa)
                muros = muros if muros is not None else segmentos_de(dentro)
                pl = _caja_entre_paredes(q, muros)
                sup = _superficie_rotulada(t, dentro)
                if pl and not (sup and abs(_area(pl) - sup) <= 0.25 * sup):
                    pl = None
            if pl and pl not in huecos:
                huecos.append(pl)
    return huecos


def _superficie_rotulada(rotulo, entidades) -> Optional[float]:
    """Superficie («17,77 m²») rotulada justo debajo de un nombre de estancia."""
    x, y = rotulo.dxf.insert.x, rotulo.dxf.insert.y
    h = rotulo.dxf.get("height", 0.1) or 0.1
    for e in entidades:
        if e.dxftype() != "TEXT" or e is rotulo:
            continue
        m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*m(?:²|2)\s*$", e.dxf.text)
        if m and 0 < y - e.dxf.insert.y <= 3 * h and abs(e.dxf.insert.x - x) <= 10 * h:
            return float(m.group(1).replace(",", "."))
    return None


def _caja_entre_paredes(q, muros, alcance: float = 8.0):
    """Rectángulo alrededor de q hasta la primera pared hacia la derecha, la izquierda, arriba y abajo. None si
    en alguna dirección no hay pared a menos de `alcance` m."""
    dist = {}
    for eje, signo in ((0, 1), (0, -1), (1, 1), (1, -1)):
        otro = 1 - eje
        mejor = None
        for a, b in muros:
            if (a[otro] - q[otro]) * (b[otro] - q[otro]) > 0 or a[otro] == b[otro]:
                continue                       # el segmento no cruza la recta del rayo
            corte = a[eje] + (q[otro] - a[otro]) * (b[eje] - a[eje]) / (b[otro] - a[otro])
            t = (corte - q[eje]) * signo
            if 0.05 < t < alcance and (mejor is None or t < mejor):
                mejor = t
        if mejor is None:
            return None
        dist[(eje, signo)] = mejor
    x0, x1 = q[0] - dist[(0, -1)], q[0] + dist[(0, 1)]
    y0, y1 = q[1] - dist[(1, -1)], q[1] + dist[(1, 1)]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _incluir(ventana, entidades, margen: float = 0.3):
    """Amplía la ventana para que quepa lo dibujado de la ICT (p. ej. la arqueta de entrada, fuera)."""
    try:
        c = bbox.extents(entidades, fast=True)
    except Exception:
        return ventana
    if not c.has_data:
        return ventana
    x0, y0, x1, y1 = ventana
    return (min(x0, c.extmin.x - margen), min(y0, c.extmin.y - margen),
            max(x1, c.extmax.x + margen), max(y1, c.extmax.y + margen))


def resumen_longitudes(mediciones: list[Medicion]) -> dict[str, float]:
    """Mínimas y máximas de la red de acometida (RS-RTR) e interior (RTR-toma de RTV) para el cálculo de niveles."""
    sec = [m.secundaria_m for m in mediciones if m.secundaria_m]
    inter = [x for m in mediciones for x in m.interior_m]
    return {"acometida_min": min(sec, default=0), "acometida_max": max(sec, default=0),
            "interior_min": min(inter, default=0), "interior_max": max(inter, default=0)}
