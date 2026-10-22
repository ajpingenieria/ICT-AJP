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
from pathlib import Path
from typing import Optional

import ezdxf
from ezdxf import bbox
from ezdxf.addons import Importer
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2, is_point_in_polygon_2d

from .leer_dxf import LecturaPlano, PlantaLeida, _nombre_planta, normalizar

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
}
CAPAS_ESTANCIAS = r"AREA.?UTIL|SUP.?UTIL|SUPERFICIE.?UTIL"    # polilíneas de superficie útil de cada estancia
CAPAS_IGNORADAS = r"CAJETIN|MARCO"                          # marco y cajetín de las láminas del arquitecto
ESCALAS = [50, 75, 100, 125, 150, 200]
HOJA = (420.0, 297.0)                   # A3 apaisado, mm
MARGEN = 10.0
ALTO_CAJETIN = 32.0
ANCHO_LEYENDA = 95.0
COLUMNAS_CAJETIN = [MARGEN, 175.0, 220.0, 262.0, 304.0, HOJA[0] - MARGEN]
TEXTO = 0.16                            # altura de texto en el modelo (m)
RADIO_REGISTRO = 0.17                   # símbolo de registro de toma (m): 1,7 mm en papel a 1:100
SEP = 0.38                              # separación entre registros de un grupo (m)
RETRANQUEO = 0.22                       # del centro de un registro a su pared (m)
SIMBOLOS = {
    "PT": "Registro de toma de pares trenzados (BAT RJ45)",
    "TV": "Registro de toma de RTV",
    "TB": "Registro de toma coaxial de banda ancha (TBA)",
    "FO": "Registro de toma de fibra óptica",
    "C": "Registro de toma configurable",
}


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


def _junto_a_pared(poli, ref, largo: float, hacia=None):
    """Centro y dirección (unitaria) de un grupo de `largo` m pegado a la pared de la estancia más cercana
    a `hacia` (o, si no se da, a `ref`), retranqueado hacia dentro. None si no hay recinto."""
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
                mejor = (d, (q[0] + nx * RETRANQUEO, q[1] + ny * RETRANQUEO), (ux, uy), (nx, ny))
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


def _sitio_libre(contorno, ocupados, paso: float = 0.4):
    """Punto de la vivienda más alejado de los rótulos y símbolos (para el nombre de la vivienda)."""
    xs = [p[0] for p in contorno]
    ys = [p[1] for p in contorno]
    aristas = _aristas(contorno)
    mejor = None
    y = min(ys) + paso
    while y < max(ys):
        x = min(xs) + paso
        while x < max(xs):
            if _dentro((x, y), contorno):
                borde = min(_dist_segmento((x, y), a, b) for a, b in aristas)
                libre = min((math.hypot((x - ox) / 2, y - oy) for ox, oy in ocupados), default=9.0)
                s = min(libre, 1.2 * borde)
                if mejor is None or s > mejor[0]:
                    mejor = (s, (x, y))
            x += paso
        y += paso
    return mejor[1] if mejor else (sum(xs) / len(xs), sum(ys) / len(ys))


def _dist_segmento(p, a, b) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


def _longitud_l(a, b) -> float:
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


# --------------------------------------------------------------------------------------- dibujo

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
    if "ICT_ITALICA" not in doc.styles:
        doc.styles.add("ICT_ITALICA", font="ariali.ttf")
    if "ICT_ARIAL" not in doc.styles:
        doc.styles.add("ICT_ARIAL", font="arial.ttf")
    if "ICT_REG" not in doc.blocks:
        b = doc.blocks.new("ICT_REG")
        b.add_circle((0, 0), RADIO_REGISTRO, dxfattribs={"layer": "0"})
        b.add_attdef("COD", (0, 0), dxfattribs={"height": 0.13, "style": "ICT_ARIAL", "layer": "0"}).set_placement(
            (0, 0), align=TextEntityAlignment.MIDDLE_CENTER)
    if "ICT_RTR" not in doc.blocks:
        b = doc.blocks.new("ICT_RTR")
        b.add_lwpolyline([(-0.3, -0.17), (0.3, -0.17), (0.3, 0.17), (-0.3, 0.17)], close=True)
        b.add_text("RTR", height=0.14, dxfattribs={"style": "ICT_ARIAL"}).set_placement(
            (0, 0), align=TextEntityAlignment.MIDDLE_CENTER)
    if "ICT_RS" not in doc.blocks:
        b = doc.blocks.new("ICT_RS")
        b.add_lwpolyline([(-0.25, -0.25), (0.25, -0.25), (0.25, 0.25), (-0.25, 0.25)], close=True)
        b.add_line((-0.25, -0.25), (0.25, 0.25))
        b.add_line((-0.25, 0.25), (0.25, -0.25))
    if "ICT_CP" not in doc.blocks:          # canalización principal (vertical)
        b = doc.blocks.new("ICT_CP")
        b.add_circle((0, 0), 0.22)
        b.add_circle((0, 0), 0.06)


def _texto(msp, texto: str, x: float, y: float, h: float = TEXTO, capa: str = "ICT_TEXTOS",
           alin=TextEntityAlignment.LEFT, giro: float = 0.0) -> None:
    msp.add_text(texto, height=h, rotation=giro, dxfattribs={"layer": capa, "style": "ICT_ARIAL"}).set_placement(
        (x, y), align=alin)


def _l(msp, a, b, capa="ICT_CANALIZACION", contorno=None, evitar=()) -> tuple:
    """Recorrido ortogonal; el codo, por dentro del contorno si se da y sin cruzar los recintos de `evitar`
    (p. ej. un patio en la cubierta). Devuelve el codo."""
    def malo(codo) -> bool:
        return bool((contorno and not _dentro(codo, contorno)) or _cruza([a, codo, b], evitar))
    codo = (b[0], a[1])
    if malo(codo) and not malo((a[0], b[1])):
        codo = (a[0], b[1])
    msp.add_lwpolyline([a, codo, b], dxfattribs={"layer": capa})
    return codo


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


def _registro(msp, q, cod: str) -> None:
    msp.add_blockref("ICT_REG", q, dxfattribs={"layer": "ICT_TOMAS"}).add_auto_attribs({"COD": cod})


def _dibujar_vista(msp, v: Vista, proyecto, polis: list, holgura: float, hacia_cp=None):
    """Dibuja la ICT de una planta. `hacia_cp`: dónde está la canalización principal en las plantas ya
    dibujadas (para que sea la misma vertical). Devuelve mediciones, avisos, centro del RITS (en la vista
    leída) y posición de la canalización principal."""
    med, avisos = [], []
    p = v.planta
    mover = lambda x, y: (x + v.dx, y + v.dy)  # noqa: E731
    ocupados = [mover(e.x + dx, e.y + dy) for viv in p.viviendas for e in viv.estancias
                for dx, dy in ((0, 0), (0.8, 0), (0, -0.15))]

    # Registro secundario y canalización principal, en una pared de la zona común
    comun = _buscar(p.otras_estancias, r"COMUN|RELLANO|DESCANSILLO")
    rs = cp = None
    if p.viviendas and comun:
        lc = mover(comun.x, comun.y)
        sitio = _junto_a_pared(_poligono_de(lc, polis), lc, 1.1, hacia=hacia_cp)
        if sitio:
            (cx, cy), u, n = sitio
            if hacia_cp and math.dist((cx + u[0] * 0.3, cy + u[1] * 0.3), hacia_cp) < math.dist(
                    (cx - u[0] * 0.3, cy - u[1] * 0.3), hacia_cp):
                u = (-u[0], -u[1])                    # la canalización principal, del lado de la de abajo
            rs = (cx + u[0] * 0.3, cy + u[1] * 0.3)
            cp = (cx - u[0] * 0.3, cy - u[1] * 0.3)
        else:
            u, n = (1.0, 0.0), (0.0, 1.0)
            rs, cp = (lc[0], lc[1] - 0.6), (lc[0] - 0.6, lc[1] - 0.6)
        msp.add_blockref("ICT_RS", rs, dxfattribs={"layer": "ICT_REGISTROS", "rotation": _giro(u)})
        msp.add_blockref("ICT_CP", cp, dxfattribs={"layer": "ICT_CANALIZACION"})
        _texto(msp, "R.S.", rs[0] + n[0] * 0.45, rs[1] + n[1] * 0.45, alin=TextEntityAlignment.MIDDLE_CENTER)
        _texto(msp, "C.P.", cp[0] + n[0] * 0.45, cp[1] + n[1] * 0.45, h=0.12, alin=TextEntityAlignment.MIDDLE_CENTER)
        ocupados += [rs, cp]

    planta_proy = [pl for pl in proyecto.edificio.plantas if pl.nivel in v.niveles]
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
        sitio = None
        if entrada:
            sitio = _junto_a_pared(entrada, mover(vest.x, vest.y) if vest else entrada[0], 1.1, hacia=rs)
        if sitio:
            (cx, cy), u, n = sitio
            rtr = (cx - u[0] * 0.2, cy - u[1] * 0.2)
            conf = (cx + u[0] * 0.4, cy + u[1] * 0.4)
        else:
            if vest:
                rtr = mover(vest.x, vest.y - 0.5)
            elif rs:
                cerca = min(contorno, key=lambda q: math.hypot(q[0] - rs[0], q[1] - rs[1]))
                rtr = _hacia_dentro(cerca, contorno, 0.6)
            else:
                continue
            u = (1.0, 0.0)
            conf = (rtr[0] + 0.45, rtr[1])
        msp.add_blockref("ICT_RTR", rtr, dxfattribs={"layer": "ICT_REGISTROS", "rotation": _giro(u)})
        _registro(msp, conf, "C")
        ocupados += [rtr, conf]
        sec = 0.0
        if rs:
            _l(msp, rs, rtr)
            sec = _longitud_l(rs, rtr) + 2 * holgura
            if _longitud_l(rs, rtr) > 15:
                avisos.append(f"{' / '.join(ids)}: el tramo registro secundario-RTR mide {_longitud_l(rs, rtr):.1f} m "
                              "en planta (más de 15 m): hacen falta registros de paso (Anexo III, 5.9).")
        m = Medicion(" / ".join(ids), round(float(sec), 1))
        principales = {e.nombre for e in (usuario.estancias if usuario else []) if e.principal}
        for e, ep in zip(viv.estancias, usuario.estancias if usuario else []):
            if not ep.es_computable:
                continue
            regs = _registros_estancia(ep.principal and ep.nombre in principales, ep.tipo.value == "salon")
            le = mover(e.x, e.y)
            sitio = _junto_a_pared(_poligono_de(le, polis), le, SEP * (len(regs) - 1) + 0.3)
            if sitio:
                (cx, cy), u, _ = sitio
            else:
                (cx, cy), u = (le[0], le[1] - 0.45), (1.0, 0.0)
            puntos = [(cx + u[0] * SEP * (k - (len(regs) - 1) / 2), cy + u[1] * SEP * (k - (len(regs) - 1) / 2))
                      for k in range(len(regs))]
            for cod, q in zip(regs, puntos):
                _registro(msp, q, cod)
            ocupados += puntos
            destino = min(puntos, key=lambda q: _longitud_l(rtr, q))
            _l(msp, rtr, destino, contorno=contorno)
            tv = puntos[regs.index("TV")]
            m.interior_m.append(round(float(_longitud_l(rtr, tv) + 2 * holgura), 1))
        med.append(m)
    for i, viv in enumerate(p.viviendas):
        ids = [pl.usuarios[i].id for pl in planta_proy if i < len(pl.usuarios)]
        contorno = [mover(x, y) for x, y in viv.contorno]
        x, y = _sitio_libre(contorno, ocupados)
        _texto(msp, " / ".join(ids), x, y, h=0.3, alin=TextEntityAlignment.MIDDLE_CENTER)

    # Recintos y elementos singulares
    rits = None
    for e in p.otras_estancias:
        n = normalizar(e.nombre)
        q = mover(e.x, e.y)
        poli = _poligono_de(q, polis)
        if poli and _area(poli) > max(2 * e.superficie_m2, 3.0):
            poli = None                 # el rótulo cae en una estancia mayor (el zaguán): no es el recinto
        if re.search(r"\bR\.?I\.?T\.?[UI]\b", n):
            caja = _recinto(msp, q, poli)
            salida_riti = (caja[2] + 0.3, (caja[1] + caja[3]) / 2)
            msp.add_blockref("ICT_CP", salida_riti, dxfattribs={"layer": "ICT_CANALIZACION"})
            _rotulo_recinto(msp, caja, "RITI" if proyecto.edificio.recintos == "RITI_RITS" else "RITU",
                            ocupados + [salida_riti])
            if hacia_cp and not p.viviendas and math.dist(salida_riti, hacia_cp) > 0.5:
                # Del RITI, por el techo, hasta el pie de la vertical de la canalización principal
                _l(msp, salida_riti, hacia_cp)
                msp.add_blockref("ICT_CP", hacia_cp, dxfattribs={"layer": "ICT_CANALIZACION"})
                _texto(msp, "C.P.", hacia_cp[0] + 0.3, hacia_cp[1] + 0.15, h=0.12)
                cp = hacia_cp
            caja_planta = _caja_contenido(p, 0.0)
            centro = mover((caja_planta[0] + caja_planta[2]) / 2, (caja_planta[1] + caja_planta[3]) / 2) if (
                caja_planta) else ((v.ventana[0] + v.ventana[2]) / 2, (v.ventana[1] + v.ventana[3]) / 2)
            _acometida(msp, q, centro, polis)
        elif re.search(r"ARM.*TELEC|RITS", n):
            caja = _recinto(msp, q, poli)
            _rotulo_recinto(msp, caja, "RITS", ocupados)      # el enlace superior se rotula en la cubierta
            rits = ((caja[0] + caja[2]) / 2 - v.dx, (caja[1] + caja[3]) / 2 - v.dy)   # en la vista leída
    return med, avisos, rits, cp


def _hacia_dentro(p, contorno, d: float):
    cx = sum(x for x, _ in contorno) / len(contorno)
    cy = sum(y for _, y in contorno) / len(contorno)
    vx, vy = cx - p[0], cy - p[1]
    n = math.hypot(vx, vy) or 1
    return p[0] + vx / n * d, p[1] + vy / n * d


def _recinto(msp, q, poli=None) -> tuple[float, float, float, float]:
    """Contorno del recinto (el del arquitecto si lo hay). Devuelve su caja."""
    if not poli:
        poli = [(q[0] - 0.5, q[1] - 0.3), (q[0] + 0.5, q[1] - 0.3), (q[0] + 0.5, q[1] + 0.3), (q[0] - 0.5, q[1] + 0.3)]
    msp.add_lwpolyline(poli, close=True, dxfattribs={"layer": "ICT_RECINTOS"})
    return (min(p[0] for p in poli), min(p[1] for p in poli), max(p[0] for p in poli), max(p[1] for p in poli))


def _rotulo_recinto(msp, caja, nombre: str, ocupados) -> str:
    """Nombre del recinto encima, debajo o a un lado, donde quede más lejos de los símbolos ya dibujados."""
    x0, y0, x1, y1 = caja
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lados = [("arriba", (cx, y1 + 0.12), (cx, y1 + 0.23), TextEntityAlignment.BOTTOM_CENTER),
             ("abajo", (cx, y0 - 0.12), (cx, y0 - 0.23), TextEntityAlignment.TOP_CENTER),
             ("derecha", (x1 + 0.15, cy), (x1 + 0.45, cy), TextEntityAlignment.MIDDLE_LEFT),
             ("izquierda", (x0 - 0.15, cy), (x0 - 0.45, cy), TextEntityAlignment.MIDDLE_RIGHT)]

    def holgura(centro) -> float:
        return min((math.hypot((centro[0] - ox) / 2, centro[1] - oy) for ox, oy in ocupados), default=9.0)
    lado, punto, _, alin = next((l for l in lados if holgura(l[2]) >= 0.4), max(lados, key=lambda l: holgura(l[2])))
    _texto(msp, nombre, *punto, h=0.22, capa="ICT_RECINTOS", alin=alin)
    return lado


def _acometida(msp, riti, centro, polis) -> None:
    """Arqueta de entrada fuera del edificio: desde el centro de la planta, en la dirección del RITI, 1,2 m
    más allá de la última estancia que se cruza (pasado el muro de fachada)."""
    vx, vy = riti[0] - centro[0], riti[1] - centro[1]
    n = math.hypot(vx, vy) or 1
    ux, uy = vx / n, vy / n
    ultimo = 0.0
    for k in range(1, 81):                       # hasta 8 m más allá del RITI
        q = (riti[0] + ux * 0.1 * k, riti[1] + uy * 0.1 * k)
        if any(_dentro(q, pl) for pl in polis):
            ultimo = 0.1 * k
    d = ultimo + 1.2
    arq = (riti[0] + ux * d, riti[1] + uy * d)
    msp.add_lwpolyline([(arq[0] - 0.2, arq[1] - 0.2), (arq[0] + 0.2, arq[1] - 0.2), (arq[0] + 0.2, arq[1] + 0.2),
                        (arq[0] - 0.2, arq[1] + 0.2)], close=True, dxfattribs={"layer": "ICT_ACOMETIDA"})
    msp.add_line(arq, riti, dxfattribs={"layer": "ICT_ACOMETIDA", "linetype": "ICT_TRAZOS"})
    lineas = ("Arqueta de entrada ICT", "400x400x600 mm", "4 Ø63 mm a vía pública", "(según consulta a operadores)")
    h, paso = 0.13, 0.2
    if abs(ux) >= abs(uy):          # a un lado de la arqueta, hacia fuera
        alin = TextEntityAlignment.LEFT if ux > 0 else TextEntityAlignment.RIGHT
        x, y = arq[0] + (0.35 if ux > 0 else -0.35), arq[1] + 0.1
    else:                           # encima o debajo, hacia fuera
        alin = TextEntityAlignment.LEFT
        x = arq[0] - 0.2
        y = arq[1] + 0.35 + paso * (len(lineas) - 1) if uy > 0 else arq[1] - 0.35 - h
    for k, linea in enumerate(lineas):
        _texto(msp, linea, x, y - paso * k, h=h, capa="ICT_ACOMETIDA", alin=alin)


def _cubierta(msp, v: Vista, mastil: Optional[tuple[float, float]], rits_cubierta: Optional[tuple],
              acceso: str, huecos=()) -> None:
    """Mástil, su radio libre y el enlace superior hasta el RITS sin cruzar los `huecos` (patios)."""
    x0, y0 = v.ventana[0], v.ventana[1]
    _texto(msp, f"Acceso a cubierta: {acceso or '[PENDIENTE: definir]'}", x0 + 0.5, y0 + 0.5, h=0.2, capa="ICT_RTV")
    if not mastil:
        _texto(msp, "[PENDIENTE: posición del mástil]", x0 + 0.5, y0 + 0.9, h=0.25, capa="ICT_RTV")
        return
    msp.add_circle(mastil, 0.15, dxfattribs={"layer": "ICT_RTV"})
    msp.add_circle(mastil, 5.0, dxfattribs={"layer": "ICT_RTV", "linetype": "ICT_TRAZOS"})
    _texto(msp, "Mástil de antenas (UHF, FM y DAB)", mastil[0] + 0.3, mastil[1] + 0.2, h=0.18, capa="ICT_RTV")
    _texto(msp, "Radio libre de 5 m (Anexo I, 4.2.1)", mastil[0] + 0.3, mastil[1] - 0.15, h=0.13, capa="ICT_RTV")
    if rits_cubierta:
        codo = _l(msp, mastil, rits_cubierta, capa="ICT_RTV", evitar=huecos)
        # El rótulo, sobre el tramo más largo del recorrido
        a, b = max(((mastil, codo), (codo, rits_cubierta)), key=lambda t: math.dist(*t))
        vertical = abs(b[0] - a[0]) < abs(b[1] - a[1])
        medio = ((a[0] + b[0]) / 2 - (0.12 if vertical else 0), (a[1] + b[1]) / 2 + (0 if vertical else 0.12))
        _texto(msp, "Enlace superior 2 Ø40 mm hasta el RITS", *medio, h=0.13, capa="ICT_RTV",
               alin=TextEntityAlignment.BOTTOM_CENTER, giro=90 if vertical else 0)
        msp.add_circle(rits_cubierta, 0.1, dxfattribs={"layer": "ICT_RTV"})
        _texto(msp, "Paso al RITS", rits_cubierta[0] + 0.2, rits_cubierta[1] - 0.05, h=0.13, capa="ICT_RTV")


# --------------------------------------------------------------------------------------- hojas

def _escala(ventana) -> int:
    x0, y0, x1, y1 = ventana
    disp_w = HOJA[0] - 2 * MARGEN - ANCHO_LEYENDA - 5
    disp_h = HOJA[1] - 2 * MARGEN - ALTO_CAJETIN - 3
    return next((e for e in ESCALAS if (x1 - x0) * 1000 / e <= disp_w and (y1 - y0) * 1000 / e <= disp_h),
                ESCALAS[-1])


def _partir(texto: str, ancho_mm: float, h: float) -> list[str]:
    """Reparte el texto en líneas que caben en `ancho_mm` con Arial de altura `h`."""
    try:
        from ezdxf.fonts import fonts
        fuente = fonts.make_font("arial.ttf", h)
        medir = fuente.text_width
    except Exception:
        medir = lambda s: 0.6 * h * len(s)  # noqa: E731
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


def _hoja(doc, nombre: str, v: Vista, numero: int, datos: dict, escala: int) -> str:
    x0, y0, x1, y1 = v.ventana
    ancho_m, alto_m = x1 - x0, y1 - y0
    disp_w = HOJA[0] - 2 * MARGEN - ANCHO_LEYENDA - 5
    disp_h = HOJA[1] - 2 * MARGEN - ALTO_CAJETIN - 3
    lay = doc.layouts.new(nombre)
    lay.page_setup(size=HOJA, margins=(0, 0, 0, 0), units="mm")
    w_mm, h_mm = ancho_m * 1000 / escala, alto_m * 1000 / escala
    cx = MARGEN + 2 + disp_w / 2
    cy = MARGEN + ALTO_CAJETIN + 2 + disp_h / 2
    lay.add_viewport(center=(cx, cy), size=(w_mm, h_mm), view_center_point=((x0 + x1) / 2, (y0 + y1) / 2),
                     view_height=alto_m, dxfattribs={"layer": "ICT_VENTANAS"})
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
    t(datos.get("autor", ""), MARGEN + 18, yb - 10)
    t("Descripción:", MARGEN + 3, MARGEN + ALTO_CAJETIN / 2 - 6)
    t(f"ICT - {v.titulo}", MARGEN + 25, MARGEN + ALTO_CAJETIN / 2 - 10)
    # Celda en blanco: proyecto, edificio y emplazamiento en las líneas que hagan falta
    ancho = xs[2] - xs[1] - 4
    for h in (1.8, 1.6, 1.4):
        lineas = [ln for clave in ("proyecto", "titulo", "emplazamiento") if datos.get(clave)
                  for ln in _partir(datos[clave], ancho, h)]
        if len(lineas) * 1.7 * h <= ALTO_CAJETIN - 4:
            break
    for k, linea in enumerate(lineas):
        t(linea, xs[1] + 2, yb - 3 - h - 1.7 * h * k, h=h, estilo="ICT_ARIAL")
    t("Nº Plano", (xs[2] + xs[3]) / 2, yb - 7, alin=TextEntityAlignment.MIDDLE_CENTER)
    t(str(numero), (xs[2] + xs[3]) / 2, MARGEN + 10, h=5.6, alin=TextEntityAlignment.MIDDLE_CENTER)
    t("Escala:", (xs[3] + xs[4]) / 2, yb - 7, alin=TextEntityAlignment.MIDDLE_CENTER)
    t(f"1:{escala}", (xs[3] + xs[4]) / 2, MARGEN + 10, h=5.6, alin=TextEntityAlignment.MIDDLE_CENTER)
    t("Firma:", xs[4] + 3, yb - 6)
    _leyenda(lay, HOJA[0] - MARGEN - ANCHO_LEYENDA, HOJA[1] - MARGEN - 2)
    return nombre


def _leyenda(lay, x, ytop) -> None:
    """Tabla SÍMBOLO / DESCRIPCIÓN con los símbolos dibujados (bloques de la ICT a escala de papel)."""
    a = {"layer": "ICT_LEYENDA"}
    filas = [("ICT_RTR", "Registro de terminación de red (RTR)"), ("ICT_RS", "Registro secundario de planta"),
             ("ICT_CP", "Canalización principal (vertical)")] + [(f"REG:{c}", d) for c, d in SIMBOLOS.items()] + [
        ("LINEA", "Canalización secundaria e interior (tubos)"), ("DISCONTINUA", "Canalización externa"),
        ("RECINTO", "Recinto de instalaciones de telecomunicación")]
    alto = 6.0
    w = ANCHO_LEYENDA
    abajo = ytop - alto * (len(filas) + 2)
    lay.add_lwpolyline([(x, ytop), (x + w, ytop), (x + w, abajo), (x, abajo)], close=True, dxfattribs=a)
    lay.add_text("LEYENDA ICT", height=3.0, dxfattribs={**a, "style": "ICT_ARIAL"}).set_placement(
        (x + w / 2, ytop - alto / 2 - 0.5), align=TextEntityAlignment.MIDDLE_CENTER)
    yy = ytop - alto
    lay.add_line((x, yy), (x + w, yy), dxfattribs=a)
    for txt, xx in (("SÍMBOLO", x + 10), ("DESCRIPCIÓN", x + 22 + (w - 22) / 2)):
        lay.add_text(txt, height=2.2, dxfattribs={**a, "style": "ICT_ARIAL"}).set_placement(
            (xx, yy - alto / 2 - 0.4), align=TextEntityAlignment.MIDDLE_CENTER)
    lay.add_line((x + 20, yy), (x + 20, abajo), dxfattribs=a)
    k_papel = 10.0          # los bloques están en metros: 1 m del bloque = 10 mm en la leyenda
    for k, (simbolo, desc) in enumerate(filas):
        y = yy - alto * (k + 1)
        c = (x + 10, y - alto / 2)
        lay.add_line((x, y), (x + w, y), dxfattribs=a)
        if simbolo.startswith("REG:"):
            lay.add_blockref("ICT_REG", c, dxfattribs={"layer": "ICT_TOMAS", "xscale": k_papel, "yscale": k_papel}
                             ).add_auto_attribs({"COD": simbolo[4:]})
        elif simbolo.startswith("ICT_"):
            capa = "ICT_CANALIZACION" if simbolo == "ICT_CP" else "ICT_REGISTROS"
            lay.add_blockref(simbolo, c, dxfattribs={"layer": capa, "xscale": k_papel, "yscale": k_papel})
        elif simbolo == "RECINTO":
            lay.add_lwpolyline([(c[0] - 5, c[1] - 1.8), (c[0] + 5, c[1] - 1.8), (c[0] + 5, c[1] + 1.8),
                                (c[0] - 5, c[1] + 1.8)], close=True, dxfattribs={"layer": "ICT_RECINTOS"})
        else:
            capa = "ICT_CANALIZACION" if simbolo == "LINEA" else "ICT_ACOMETIDA"
            tipo = {"linetype": "ICT_TRAZOS"} if simbolo == "DISCONTINUA" else {}
            lay.add_line((c[0] - 6, c[1]), (c[0] + 6, c[1]), dxfattribs={"layer": capa, **tipo})
        lay.add_text(desc, height=1.9, dxfattribs={**a, "style": "ICT_ARIAL"}).set_placement(
            (x + 22, y - alto / 2 - 0.4), align=TextEntityAlignment.LEFT)


# --------------------------------------------------------------------------------------- principal

def datos_cajetin(proyecto, plantilla=None) -> dict:
    """Textos del cajetín: autor (de la plantilla de AJP si se da), proyecto, edificio y emplazamiento."""
    dg = proyecto.datos_generales
    autor = (plantilla.datos.get("proyectista", {}).get("nombre", "") if plantilla else "") or dg.proyectista.nombre
    return {"autor": autor,
            "proyecto": f"Proyecto ICT {dg.numero}".strip(),
            "titulo": dg.titulo,
            "emplazamiento": ", ".join(x for x in (dg.direccion, dg.municipio) if x)}


def generar_planos(base_dxf: str | Path, lectura: LecturaPlano, proyecto, salida: str | Path,
                   datos_cajetin: dict, mastil: Optional[tuple[float, float]] = None,
                   holgura_vertical_m: float = 1.0, imagenes: bool = True, pdf: bool = True,
                   acceso_cubierta: str = "") -> ResultadoPlanos:
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
    capas_estancias = re.compile(CAPAS_ESTANCIAS, re.I)
    for k, v in enumerate(vistas):
        x0, y0, x1, y1 = v.ventana
        ents = [e for e, a, b, c, d in cajas if not (c < x0 or a > x1 or d < y0 or b > y1)
                and not ignorar.search(e.dxf.layer)]
        poligonos[k] = [[(p[0], p[1]) for p in e.get_points("xy")] for e in ents
                        if e.dxftype() == "LWPOLYLINE" and capas_estancias.search(e.dxf.layer) and len(e) >= 3]
        nuevas = [e for e in ents if id(e) not in copiadas]
        copiadas.update(id(e) for e in nuevas)
        imp.import_entities(nuevas, doc.modelspace())
    imp.finalize()
    _preparar(doc)
    msp = doc.modelspace()
    mediciones, avisos, presentaciones = [], [], []
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
            m, a, centro_rits, cp = _dibujar_vista(msp, v, proyecto, poligonos[k], holgura_vertical_m, hacia)
            mediciones += m
            avisos += a
            v.ventana = _incluir(v.ventana, list(msp)[antes:])
            if centro_rits:
                rits = (centro_rits, v)         # en la vista leída: la cubierta se lee en la misma fila
            if cp and cp_titulo is None:
                cp_titulo = (cp[0] - v.dx - tx, cp[1] - v.dy - ty)
    for v in vistas:
        if "CUBIERTA" in normalizar(v.planta.nombre):
            rits_cub = None
            if rits:
                # mismo desplazamiento entre vistas que entre los títulos de la planta del RITS y la cubierta
                (x, y), w = rits
                rits_cub = (x + v.planta.titulo_xy[0] - w.planta.titulo_xy[0],
                            y + v.planta.titulo_xy[1] - w.planta.titulo_xy[1])
            _cubierta(msp, v, mastil, rits_cub, acceso_cubierta, huecos=_huecos(cajas, v.ventana))
    escala = max(_escala(v.ventana) for v in vistas) if vistas else 100     # la misma en todas las hojas
    for k, v in enumerate(vistas, start=1):
        presentaciones.append(_hoja(doc, f"ICT-{k} {v.titulo}"[:31], v, k, datos_cajetin, escala))
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
    huecos = []
    for t in dentro:
        if t.dxftype() in ("TEXT", "MTEXT") and re.search(r"PATIO|HUECO|LUCERNARIO|CLARABOYA",
                                                          normalizar(t.plain_text())):
            q = (t.dxf.insert.x, t.dxf.insert.y)
            pl = min((c for c in cerradas if _dentro(q, c) and _area(c) < 60), key=_area, default=None)
            if pl and pl not in huecos:
                huecos.append(pl)
    return huecos


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
