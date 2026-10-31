"""Esquemas de principio de la ICT (Orden ITC/1644/2011, anexo I, apartado 2.3), en hojas A3 con el cajetín de
AJP, a continuación de las plantas:

- 2.3.A Esquema general de la infraestructura: canalizaciones y registros de cada red.
- 2.3.B Radiodifusión sonora y televisión: material activo y pasivo con su referencia del catálogo del fabricante
  prescrito y longitudes en metros.
- 2.3.C Redes de pares trenzados, cable coaxial y fibra óptica: asignación de cables por planta y vivienda,
  elementos del registro principal, registros secundarios y PAU, y longitudes en metros.

Se dibujan directamente en la presentación, en milímetros de papel (sin escala), por bandas de planta de abajo
arriba. Los datos salen del dimensionado y del catálogo; las longitudes de acometida e interiores, de la
medición de las plantas de la ICT (la misma con la que se calculan los niveles de RTV).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ezdxf.enums import TextEntityAlignment as A

from .planos_ict import RTR_MM, TOMA, Medicion, _atributos, _limpiar, _registros_estancia, hoja_a3

H = 1.8              # texto normal (mm)
HP = 1.3             # texto pequeño: longitudes
GRIS = 8


def _m(x: Optional[float]) -> str:
    return f"{x:.1f}".replace(".", ",") + " m" if x is not None else "[PENDIENTE: medir]"


@dataclass
class Estancia:
    nombre: str
    regs: list[str]                       # «PT», «PT», «TB», «TV», «FO»
    interior_m: Optional[float] = None    # del RTR a la toma de RTV de la estancia (medida en planta)


@dataclass
class Vivienda:
    id: str
    nivel: int
    estancias: list[Estancia] = field(default_factory=list)
    acometida_m: Optional[float] = None   # del registro secundario al RTR (medida en planta)
    derivador: str = ""                   # referencia del derivador de RTV de su planta
    pau_rtv: str = ""

    def cuenta(self, cod: str) -> int:
        return sum(e.regs.count(cod) for e in self.estancias) + (1 if cod == "C" else 0)


def _viviendas(p, R, mediciones: list[Medicion]) -> list[Vivienda]:
    med = {vid: m for m in mediciones for vid in m.vivienda.split(" / ")}
    rtv = next((t for t in R.seccion("rtv").tablas if t.titulo.startswith("Red de distribución")), None)
    filas_rtv = {f[1]: f for f in (rtv.filas if rtv else [])}
    res = []
    for pl in sorted(p.edificio.plantas, key=lambda x: x.nivel):
        for u in pl.usuarios:
            m = med.get(u.id)
            principales = {e.nombre for e in u.estancias if e.principal}
            est = []
            for k, e in enumerate([e for e in u.estancias if e.es_computable]):
                regs = _registros_estancia(e.nombre in principales, e.tipo.value == "salon")
                interior = m.interior_m[k] if m and k < len(m.interior_m) else None
                est.append(Estancia(e.nombre, regs, interior))
            f = filas_rtv.get(u.id)
            res.append(Vivienda(u.id, pl.nivel, est, m.secundaria_m if m else None,
                                str(f[2]) if f else "", str(f[3]) if f else ""))
    return res


class _Lamina:
    """Bandas de planta, de abajo arriba, en la zona de dibujo de la hoja, y utilidades de dibujo en mm."""

    def __init__(self, lay, area, bandas: list[tuple[str, object]]):
        self.lay = lay
        self.x0, self.y0, self.x1, self.y1 = area
        self.alto = (self.y1 - self.y0) / len(bandas)
        self.base = {}
        for k, (nombre, clave) in enumerate(bandas):
            y = self.y0 + k * self.alto
            self.base[clave] = y
            if k:
                self.linea([(self.x0, y), (self.x1, y)], "ICT_TEXTOS", color=GRIS)
            self.texto(nombre.upper(), (self.x0 + 1, y + self.alto - 2.5), 1.6, color=GRIS, negrita=True)

    def medio(self, clave, f: float = 0.5) -> float:
        return self.base[clave] + self.alto * f

    def texto(self, t: str, p, h: float = H, capa: str = "ICT_TEXTOS", alin=A.LEFT, giro: float = 0.0,
              negrita: bool = False, color: Optional[int] = None):
        at = {"layer": capa, "style": "ICT_NEGRITA" if negrita else "ICT_ARIAL"}
        if color is not None:
            at["color"] = color
        self.lay.add_text(t, height=h, rotation=giro, dxfattribs=at).set_placement(p, align=alin)

    def linea(self, pts, capa: str, color: Optional[int] = None, tipo: Optional[str] = None):
        at = {"layer": capa}
        if color is not None:
            at["color"] = color
        if tipo:
            at["linetype"] = tipo
        self.lay.add_lwpolyline(pts, dxfattribs=at)

    def caja(self, x0, y0, x1, y1, capa: str, lineas: list[str] = (), h: float = H):
        """Recuadro con líneas de texto dentro (la primera en negrita), centradas."""
        self.linea([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], capa)
        paso = 1.6 * h
        y = (y0 + y1) / 2 + paso * (len(lineas) - 1) / 2
        for k, t in enumerate(lineas):
            self.texto(t, ((x0 + x1) / 2, y - paso * k), h if k else h * 1.1, capa if k == 0 else "ICT_TEXTOS",
                       A.MIDDLE_CENTER, negrita=(k == 0))

    def bloque(self, nombre: str, p, capa: str, valores: Optional[dict] = None, giro: float = 0.0):
        ins = self.lay.add_blockref(nombre, p, dxfattribs={"layer": capa, "rotation": giro})
        if valores:
            _atributos(ins, valores, capa, 0.0 if giro else None)
        return ins

    def toma(self, cod: str, p, rotulo: str = "", capa: str = "ICT_TOMAS"):
        """Toma con su patilla hacia arriba (donde llega el cable) y su rótulo debajo."""
        self.bloque("ICT_TOMA", p, capa, {"COD": cod})
        if rotulo:
            self.texto(rotulo, (p[0], p[1] - TOMA[1] - TOMA[2] - 1.6), HP, alin=A.MIDDLE_CENTER)


def _bandas(p, con_baja: bool, con_cubierta: bool = True) -> list[tuple[str, object]]:
    plantas = sorted({pl.nivel: pl.nombre for pl in p.edificio.plantas if pl.usuarios}.items())
    bandas = [("Planta baja", 0)] if con_baja and all(n != 0 for n, _ in plantas) else []
    return (bandas + [(nombre, nivel) for nivel, nombre in plantas]
            + ([("Cubierta", "cubierta")] if con_cubierta else []))


def _por_planta(viviendas: list[Vivienda]) -> dict[int, list[Vivienda]]:
    res: dict[int, list[Vivienda]] = {}
    for v in viviendas:
        res.setdefault(v.nivel, []).append(v)
    return dict(sorted(res.items()))


def _filas(L: _Lamina, nivel, n: int, centro: float = 0.5, paso_max: float = 12.0) -> list[float]:
    """y de las filas de las viviendas de una planta (de arriba abajo), centradas en `centro` de su banda."""
    paso = min(paso_max, L.alto * 0.75 / max(n, 1))
    yc = L.medio(nivel, centro)
    return [yc + paso * ((n - 1) / 2 - k) for k in range(n)]


def _salidas(y: float, filas: list[float], abertura: float) -> tuple[list[float], list[int]]:
    """Por dónde sale del registro (o derivador) la línea de cada fila y en qué orden van sus bajadas, para que
    no se crucen: la fila más alta sale por arriba y baja (o sube) por la vertical más cercana al registro, y así
    hacia el centro; luego las filas de debajo, de la más baja hacia el centro."""
    n = len(filas)
    salidas = [y + abertura * ((n - 1) / 2 - k) / ((n - 1) / 2 or 1) for k in range(n)]
    arriba = [k for k, yf in enumerate(filas) if yf > y + 0.1]
    abajo = [k for k, yf in enumerate(filas) if yf < y - 0.1][::-1]
    resto = [k for k in range(n) if k not in arriba and k not in abajo]
    orden = {k: i for i, k in enumerate(arriba + abajo + resto)}
    return salidas, [orden[k] for k in range(n)]


def _acometida(L: _Lamina, origen, y_fin: float, x_bajada: float, x_fin: float, capa: str, rotulo: str = "") -> None:
    """Del registro o derivador (origen) a la vivienda: en horizontal, sube o baja por su propia vertical
    (x_bajada) y sigue en horizontal hasta el PAU; el rótulo, encima del último tramo."""
    L.linea(_limpiar([origen, (x_bajada, origen[1]), (x_bajada, y_fin), (x_fin, y_fin)]), capa)
    if rotulo:
        L.texto(rotulo, ((x_bajada + x_fin) / 2, y_fin + 0.8), HP, alin=A.BOTTOM_CENTER)


def _vivienda(L: _Lamina, v: Vivienda, x: float, y: float, l2: str, tomas: list[tuple[str, str]], capa: str,
              rotulo_tubos: str = "", paso: float = 6.4) -> None:
    """PAU (en el RTR) con el nombre de la vivienda encima y, a su derecha, sus tomas colgando de una línea."""
    w, h = RTR_MM
    L.bloque("ICT_RTR", (x + w / 2, y + h / 2), "ICT_REGISTROS", {"L1": "PAU", "L2": l2}, giro=0)
    L.texto(v.id, (x + w / 2, y + h / 2 + 1.2), H, alin=A.BOTTOM_CENTER, negrita=True)
    xt0 = x + w + (15 if rotulo_tubos else 6)
    if tomas:
        L.linea([(x + w, y), (xt0 + paso * (len(tomas) - 1), y)], capa)
    if rotulo_tubos:
        L.texto(rotulo_tubos, (x + w + 1, y + 0.8), HP, alin=A.BOTTOM_LEFT)
    for j, (sig, rotulo) in enumerate(tomas):
        L.toma(sig, (xt0 + paso * j, y), rotulo)


def _vertical(L: _Lamina, x: float, tramos: list[tuple[float, float, str]], capa: str) -> None:
    """Canalización o cables en vertical: cada tramo (y desde, y hasta, rótulo girado a su izquierda, si cabe)."""
    for ya, yb, rotulo in tramos:
        if yb - ya > 0.5:
            L.linea([(x, ya), (x, yb)], capa)
            if rotulo and len(rotulo) * HP * 0.8 + 2 < yb - ya:
                L.texto(rotulo, (x - 1.5, (ya + yb) / 2), HP, alin=A.BOTTOM_CENTER, giro=90)


def _registros_de_planta(L: _Lamina, xv: float, y_rs: dict, alto_rs: float, x_pau: float, plantas: dict,
                         centro: dict, rotulo, dibujar_vivienda) -> None:
    """Registro secundario de cada planta y, desde él, la línea de cada vivienda hasta su PAU."""
    for n, vs in plantas.items():
        y = y_rs[n]
        L.caja(xv - 6, y - alto_rs / 2, xv + 6, y + alto_rs / 2, "ICT_REGISTROS", ["RS"])
        filas = _filas(L, n, len(vs), centro[n])
        salidas, orden = _salidas(y, filas, 1.2)
        for v, yf, ys, i in zip(vs, filas, salidas, orden):
            _acometida(L, (xv + 6, ys), yf, xv + 12 + 3 * i, x_pau, "ICT_CANALIZACION", rotulo(v))
            dibujar_vivienda(v, yf)


# ------------------------------------------------------------------------- 2.3.A esquema general

def _general(L: _Lamina, p, R, viviendas: list[Vivienda], tubos: dict) -> None:
    def valor(seccion, concepto, defecto=""):
        pa = next((x for x in R.seccion(seccion).partidas if x.concepto.startswith(concepto)), None)
        return str(pa.valor) if pa else defecto

    plantas = _por_planta(viviendas)
    niveles = list(plantas)
    tope = niveles[-1]
    xv = L.x0 + 95                                  # vertical: canalización principal
    # Planta baja: arqueta, canalización externa, registro de enlace y RITI
    yb = L.medio(0, 0.45)
    xa = L.x0 + 14
    L.bloque("ICT_ARQ", (xa, yb), "ICT_ACOMETIDA")
    L.texto("Arqueta de entrada", (xa, yb - 3.2), HP, alin=A.TOP_CENTER)
    L.texto(re.sub(r"\s*\(.*\)", "", valor("infra", "Arqueta de entrada")), (xa, yb - 5.2), HP, alin=A.TOP_CENTER)
    xre = L.x0 + 40
    L.linea([(xa + 1.7, yb), (xre - 2, yb)], "ICT_ACOMETIDA", tipo="ICT_TRAZOS")
    L.texto(f"{tubos.get('externa') or ''} c. externa", ((xa + xre) / 2, yb + 1.0), HP, alin=A.BOTTOM_CENTER)
    L.caja(xre - 2, yb - 2, xre + 2, yb + 2, "ICT_REGISTROS")
    L.texto("Registro de enlace", (xre, yb + 3), HP, alin=A.BOTTOM_CENTER)
    x_riti0, x_riti1 = xv - 25, xv + 25
    y_riti0, y_riti1 = L.medio(0, 0.15), L.medio(0, 0.75)
    L.linea([(xre + 2, yb), (x_riti0, yb)], "ICT_ACOMETIDA")
    L.texto(f"{tubos.get('externa') or ''} enlace inferior", ((xre + x_riti0) / 2, yb + 1.0), HP,
            alin=A.BOTTOM_CENTER)
    L.caja(x_riti0, y_riti0, x_riti1, y_riti1, "ICT_RECINTOS",
           ["RITI", "Registros principales:", "pares trenzados, coaxial y fibra"])
    if p.edificio.ascensores:
        y_asc = L.medio(0, 0.3)
        L.linea([(x_riti1, y_asc), (x_riti1 + 30, y_asc)], "ICT_CANALIZACION")
        L.texto(f"{p.edificio.ascensores}Ø25 mm con hilo guía al cuarto de máquinas del ascensor",
                (x_riti1 + 31, y_asc), HP, alin=A.MIDDLE_LEFT)
    contadores = valor("recintos", "Canalizaciones desde centralización")
    if contadores:
        L.texto(f"Desde la centralización de contadores: {contadores}", (x_riti1 + 2, L.medio(0, 0.62)), HP,
                alin=A.MIDDLE_LEFT)
    # Canalización principal hasta el RITS, con un registro secundario en cada planta con viviendas
    alto_rs = 6.0
    centro = {n: 0.33 if n == tope else 0.5 for n in niveles}
    y_rs = {n: L.medio(n, centro[n]) for n in niveles}
    y_rits0, y_rits1 = L.medio(tope, 0.64), L.medio(tope, 0.95)
    cp = f"C.P. {tubos.get('principal') or ''}"
    cortes = [y_riti1] + [y for n in niveles for y in (y_rs[n] - alto_rs / 2, y_rs[n] + alto_rs / 2)] + [y_rits0]
    _vertical(L, xv, [(cortes[k], cortes[k + 1], cp) for k in range(0, len(cortes) - 1, 2)], "ICT_CANALIZACION")
    rs_dim = re.sub(r"\s*\(.*\)", "", valor("infra", "Registros secundarios de planta (dim"))
    for n in niveles:
        L.texto(rs_dim, (xv - 7, y_rs[n]), HP, alin=A.MIDDLE_RIGHT)
    tipos = [("PT", "RJ45"), ("TV", "TV"), ("TB", "TBA"), ("FO", "FO"), ("C", "C")]

    def vivienda(v, yf):
        n_tubos = sum(v.cuenta(c) for c, _ in tipos)
        _vivienda(L, v, xv + 55, yf, "RTR", [(sig, f"x{v.cuenta(cod)}") for cod, sig in tipos], "ICT_CANALIZACION",
                  f"{n_tubos}Ø{tubos['interior_mm']} mm")

    _registros_de_planta(L, xv, y_rs, alto_rs, xv + 55, plantas, centro,
                         lambda v: f"{tubos['acceso']} · {_m(v.acometida_m)}", vivienda)
    # RITS, enlace superior y mástil
    L.caja(xv - 25, y_rits0, xv + 25, y_rits1, "ICT_RECINTOS", ["RITS", "Cabecera de RTV"])
    y_mastil = L.medio("cubierta", 0.55)
    _vertical(L, xv, [(y_rits1, y_mastil - 3, "")], "ICT_RTV")
    L.texto(f"Enlace superior: {tubos.get('enlace_superior') or ''}", (xv + 1.5, (y_rits1 + y_mastil - 3) / 2), HP,
            alin=A.MIDDLE_LEFT)
    L.bloque("ICT_ANT", (xv, y_mastil), "ICT_RTV")
    L.texto("Mástil de antenas", (xv + 4, y_mastil + 1), H, alin=A.MIDDLE_LEFT)
    L.texto("Reserva de espacio para antenas de satélite (Anexo I, 3.6)", (xv + 4, y_mastil - 2.2), HP,
            alin=A.MIDDLE_LEFT)


# ------------------------------------------------------------------------- 2.3.B radio y televisión

def _rtv(L: _Lamina, p, R, viviendas: list[Vivienda]) -> None:
    def valor(concepto, defecto=""):
        pa = next((x for x in R.seccion("rtv").partidas if x.concepto.startswith(concepto)), None)
        return str(pa.valor) if pa else defecto

    plantas = _por_planta(viviendas)
    niveles = list(plantas)
    tope = niveles[-1]
    # Cabecera en el RITS: un amplificador monocanal por canal de TDT y uno de FM/DAB, con la fuente
    canales = []
    t = next((t for t in R.seccion("rtv").tablas if t.titulo.startswith("Canales de TDT")), None)
    for f in (t.filas if t else []):
        canales.append(f"C{f[1]}")
    m = re.search(r"canal (\d+)", valor("TDT local"))
    if m and f"C{m.group(1)}" not in canales:
        canales.append(f"C{m.group(1)}")
    cab = valor("Cabecera")
    ref_uhf = (re.search(r"monocanal UHF (\d+)", cab) or [None, ""])[1]
    ref_fm = (re.search(r"FM/DAB (\d+)", cab) or [None, ""])[1]
    ref_fuente = (re.search(r"fuente (\d+)", cab) or [None, ""])[1]
    amps = [(c, ref_uhf) for c in canales] + [("FM/DAB", ref_fm)]
    x_c0 = L.x0 + 30
    x_amp = [x_c0 + 2 + 9.0 * k for k in range(len(amps))]
    x_mez = x_amp[-1] + 12
    x_c1 = x_mez + 22
    y_c0, y_c1 = L.medio(tope, 0.6), L.medio(tope, 0.97)
    L.caja(x_c0 - 4, y_c0, x_c1, y_c1, "ICT_RECINTOS")
    L.texto("RITS · cabecera", (x_c1 - 1, y_c1 - 1), H, "ICT_RECINTOS", A.TOP_RIGHT, negrita=True)
    y_amp = (y_c0 + y_c1) / 2
    for (canal, ref), x in zip(amps, x_amp):
        L.bloque("ICT_AMP", (x, y_amp), "ICT_RTV")
        L.texto(canal, (x + 2.3, y_amp + 0.6), HP, alin=A.MIDDLE_LEFT, negrita=True)
        L.texto(ref, (x + 2.3, y_amp - 1.0), 1.0, alin=A.MIDDLE_LEFT)
    # Antenas en cubierta: la UHF, sobre los monocanal; FM y DAB, sobre el amplificador FM/DAB
    refs = re.findall(r"(UHF|FM|DAB)[^0-9]*(\d{3,6})", valor("Captación"))
    refs = sorted(refs, key=lambda r: r[0] != "UHF")
    uhf = x_amp[:-1] or x_amp
    x_ant = [(uhf[0] + uhf[-1]) / 2] + [x_amp[-1] + 12 * i for i in range(len(refs) - 1)]
    y_ant = L.medio("cubierta", 0.5)
    for (banda, ref), x in zip(refs, x_ant):
        L.bloque("ICT_ANT", (x, y_ant), "ICT_RTV")
        L.texto(f"{banda} {ref}", (x, y_ant + 4), HP, alin=A.BOTTOM_CENTER)
    y_ent = y_amp + 4.6
    for x in uhf:
        L.linea([(x, y_amp + 1.6), (x, y_ent)], "ICT_RTV")
    if len(uhf) > 1:
        L.linea([(uhf[0], y_ent), (uhf[-1], y_ent)], "ICT_RTV")
    if refs:
        L.linea([(x_ant[0], y_ant - 3), (x_ant[0], y_ent)], "ICT_RTV")
        for i, x in enumerate(x_ant[1:]):
            if i == 0:
                L.linea([(x, y_ant - 3), (x, y_amp + 1.6)], "ICT_RTV")
            else:                               # las demás, por encima del RITS hasta el amplificador FM/DAB
                yh = y_c1 + 4 - 1.6 * (i - 1)
                L.linea([(x, y_ant - 3), (x, yh), (x_amp[-1] + i, yh), (x_amp[-1] + i, y_amp + 1.6)], "ICT_RTV")
        L.texto(f"Cable 414002 · {_m(p.rtv.long_antena_cabecera_m)} (cada antena)", (x_ant[-1] + 4, y_ant - 5), HP,
                alin=A.MIDDLE_LEFT)
    # Salidas a la mezcla y, de ella, los dos cables de la red de distribución
    y_bus = y_amp - 5.0
    for x in x_amp:
        L.linea([(x, y_amp - 1.8), (x, y_bus)], "ICT_RTV")
    L.linea([(x_amp[0], y_bus), (x_mez - 1.6, y_bus)], "ICT_RTV")
    L.bloque("ICT_MEZ", (x_mez, y_bus), "ICT_RTV")
    L.texto(f"Fuente {ref_fuente}", (x_mez + 2.5, y_amp + 1), HP, alin=A.MIDDLE_LEFT)
    xd = [x_mez - 4.5, x_mez + 4.5]                 # los dos cables de la red
    dy = [2.4, -2.4]                                # el derivador de cada cable, a una altura
    y_ini = y_bus - 3.5
    for x in xd:
        L.linea([(x_mez, y_bus - 1.6), (x, y_ini)], "ICT_RTV")
    L.texto("2 cables", (xd[1] + 1.5, y_ini - 3), HP, alin=A.MIDDLE_LEFT)
    y_rs = {n: L.medio(n, 0.3 if n == tope else 0.5) for n in niveles}
    x_pau = xd[1] + 40
    arriba = {0: y_ini, 1: y_ini}                   # dónde termina, por abajo, cada cable
    for n in reversed(niveles):
        vs = plantas[n]
        y = y_rs[n]
        largo = p.rtv.long_cabecera_primer_derivador_m if n == tope else p.rtv.altura_entre_plantas_m
        L.texto(_m(largo), (xd[0] - 1.5, (arriba[0] + y + dy[0] + 1.7) / 2), HP, alin=A.MIDDLE_RIGHT)
        for c, (x, d) in enumerate(zip(xd, dy)):
            L.linea([(x, arriba[c]), (x, y + d + 1.7)], "ICT_RTV")
            L.bloque("ICT_DER", (x, y + d), "ICT_RTV", {"REF": ""})
            arriba[c] = y + d - 1.7
        L.texto(f"Derivador {vs[0].derivador} (2 uds.)", (xd[0] - 4.5, y + dy[0]), HP, alin=A.MIDDLE_RIGHT)
        filas = _filas(L, n, len(vs), 0.3 if n == tope else 0.5)
        salidas, orden = _salidas(y, filas, 0.8)
        for v, yf, ys, i in zip(vs, filas, salidas, orden):
            # una acometida desde el derivador de cada cable a cada una de las dos entradas del PAU
            ida = [0, 1] if yf >= y else [1, 0]         # orden de sus dos bajadas, para cruzarse lo menos posible
            for c in (0, 1):
                xb = xd[1] + 8 + 4 * (2 * i + ida.index(c))
                _acometida(L, (xd[c] + 3.2, ys + dy[c]), yf + (0.9 if c == 0 else -0.9), xb, x_pau,
                           "ICT_RTV", f"Acometidas · {_m(v.acometida_m)}" if c == 0 else "")
            tvs = [e for e in v.estancias if "TV" in e.regs]
            _vivienda(L, v, x_pau, yf, v.pau_rtv, [("TV", _m(e.interior_m).replace(" m", "")) for e in tvs], "ICT_RTV",
                      paso=7.5)
    y_fin = min(arriba.values()) - 3
    for c, x in enumerate(xd):
        L.linea([(x, arriba[c]), (x, y_fin)], "ICT_RTV")
        L.bloque("ICT_CARGA", (x, y_fin), "ICT_RTV")
    L.texto("Cargas de 75 Ω", (xd[1] + 2, y_fin - 2.0), HP, alin=A.MIDDLE_LEFT)
    L.texto("Longitudes en metros. Toma 527601 en cada estancia; bajo cada toma, su longitud desde el PAU.",
            (L.x0 + 1, L.y0 + 1), HP, alin=A.BOTTOM_LEFT)


# ------------------------------------------------------------------------- 2.3.C redes de telecomunicación

@dataclass
class _Red:
    corto: str                   # nombre de la presentación
    titulo: str
    registro: list[str]          # líneas del registro principal (RITI)
    cable: str                   # «cat. 6», «coaxial RG-6», «2 fibras G.657»
    tipos: list[tuple[str, str]]  # (código interior, siglas de la toma)
    por_planta: dict[int, tuple[int, int]]   # nivel -> (cables a viviendas, reserva)
    comunes: int = 0


def _red(L: _Lamina, p, viviendas: list[Vivienda], red: _Red) -> None:
    plantas = _por_planta(viviendas)
    niveles = list(plantas)
    xv = L.x0 + 95
    y_r0, y_r1 = L.medio(0, 0.12), L.medio(0, 0.8)
    L.caja(xv - 30, y_r0, xv + 30, y_r1, "ICT_RECINTOS", ["RITI"] + red.registro, h=1.5)
    L.linea([(L.x0 + 8, (y_r0 + y_r1) / 2), (xv - 30, (y_r0 + y_r1) / 2)], "ICT_ACOMETIDA", tipo="ICT_TRAZOS")
    L.texto("Red de alimentación de los operadores", (L.x0 + 9, (y_r0 + y_r1) / 2 + 1), HP, alin=A.BOTTOM_LEFT)
    if red.comunes:
        L.linea([(xv + 30, L.medio(0, 0.3)), (xv + 50, L.medio(0, 0.3))], "ICT_CANALIZACION")
        L.texto(f"{red.comunes} cables {red.cable} a instalaciones comunes del edificio", (xv + 51, L.medio(0, 0.3)),
                HP, alin=A.MIDDLE_LEFT)
    # Vertical: en cada tramo, los cables que siguen hacia arriba (con los de reserva)
    alto_rs = 6.0
    centro = {n: 0.5 for n in niveles}
    y_rs = {n: L.medio(n) for n in niveles}
    tramos, ya = [], y_r1
    for n in niveles:
        arriba = sum(sum(red.por_planta.get(x, (0, 0))) for x in niveles if x >= n)
        tramos.append((ya, y_rs[n] - alto_rs / 2, f"{arriba} cables {red.cable}"))
        ya = y_rs[n] + alto_rs / 2
    _vertical(L, xv, tramos, "ICT_CANALIZACION")
    for n in niveles:
        reserva = red.por_planta.get(n, (0, 0))[1]
        if reserva:
            L.texto(f"{reserva} de reserva", (xv - 7, y_rs[n]), HP, alin=A.MIDDLE_RIGHT)
    numero = {v.id: k + 1 for k, v in enumerate(viviendas)}

    def vivienda(v, yf):
        tomas = [(sig, _m(e.interior_m).replace(" m", "")) for e in v.estancias for cod, sig in red.tipos
                 for _ in range(e.regs.count(cod))]
        _vivienda(L, v, xv + 60, yf, "RTR", tomas, "ICT_CANALIZACION")

    _registros_de_planta(L, xv, y_rs, alto_rs, xv + 60, plantas, centro,
                         lambda v: f"N.º {numero[v.id]} · {red.cable} · {_m(v.acometida_m)}", vivienda)
    L.texto("Numeración de cables correlativa desde el registro principal, de la planta inferior a la superior. "
            "Longitudes en metros (acometida: del registro secundario al PAU; bajo cada toma, su longitud desde el PAU).",
            (L.x0 + 1, L.y0 + 1), HP, alin=A.BOTTOM_LEFT)


def _redes_tba(p, R) -> list[_Red]:
    from .dimensionado import _repartir

    def valor(concepto, defecto=""):
        pa = next((x for x in R.seccion("redes").partidas if x.concepto.startswith(concepto)), None)
        return pa.valor if pa else defecto

    dem = next((t for t in R.seccion("demanda").tablas if t.titulo.startswith("Demanda por planta")), None)
    nivel_de = {pl.nombre: pl.nivel for pl in p.edificio.plantas}
    filas_dem = [f for f in (dem.filas if dem else []) if f[0] in nivel_de]
    comunes = next((f[2] for f in (dem.filas if dem else []) if str(f[0]).startswith("Instalaciones")), 0)
    redes = []
    # Pares trenzados: cables por planta (demanda y reserva) de la tabla del dimensionado
    tpt = next((t for t in R.seccion("redes").tablas if t.titulo.startswith("Cables de pares trenzados")), None)
    if tpt:
        por = {nivel_de[f[0]]: (f[1], f[2]) for f in tpt.filas if f[0] in nivel_de}
        redes.append(_Red("Esquema pares trenzados", "ICT · Esquema de la red de pares trenzados",
                          ["Registro principal de pares trenzados:",
                           f"{valor('Registro principal de cobre: salidas')} salidas (panel cat. 6, RJ45)",
                           f"entrada: {valor('Registro principal de cobre: capacidad')} pares"],
                          "cat. 6", [("PT", "RJ45")], por, comunes))
    # Coaxial (estrella): un cable por vivienda
    redes.append(_Red("Esquema coaxial", "ICT · Esquema de la red de cable coaxial",
                      ["Registro principal coaxial:", f"{valor('Registro principal coaxial')} salidas con conector F"],
                      "coaxial RG-6", [("TB", "TBA")], {nivel_de[f[0]]: (f[3], 0) for f in filas_dem}, comunes))
    # Fibra: acometidas de 2 fibras; las sobrantes, repartidas de manera uniforme en los registros secundarios
    # (Anexo II, 3.3.4)
    dem_fo = [f[4] for f in filas_dem]
    m = re.match(r"(\d+)", str(valor("Red de fibra óptica")))
    total = int(m.group(1)) if m else sum(dem_fo) + comunes
    reserva = _repartir(max(0, total - sum(dem_fo) - comunes), dem_fo)
    redes.append(_Red("Esquema fibra óptica", "ICT · Esquema de la red de fibra óptica",
                      ["Registro principal óptico:",
                       f"{valor('Registro principal óptico: conectores de salida')} conectores de salida",
                       f"{valor('Registro principal óptico: conectores de entrada')} conectores de entrada"],
                      "2 fibras G.657", [("FO", "FO")],
                      {nivel_de[f[0]]: (f[4], r) for f, r in zip(filas_dem, reserva)}, comunes))
    return redes


# ------------------------------------------------------------------------- hojas

LEYENDA_GENERAL = [("TOMA:RJ45", "Toma de pares trenzados (RJ45)"), ("TOMA:TV", "Toma de RTV"),
                   ("TOMA:TBA", "Toma coaxial TBA"), ("TOMA:FO", "Toma de fibra óptica"), ("TOMA:C", "Toma configurable"),
                   ("ICT_RTR", "RTR con el PAU"), ("ICT_ARQ", "Arqueta de entrada"),
                   ("RECINTO", "Recinto (RITI / RITS)"), ("LINEA", "Tubos, con su número y diámetro"),
                   ("DISCONTINUA", "Canalización externa"), ("ICT_ANT", "Mástil y antenas")]
LEYENDA_RTV = [("ICT_ANT", "Antena"), ("ICT_AMP", "Amplificador monocanal"), ("ICT_MEZ", "Mezcla de cabecera"),
               ("ICT_DER", "Derivador"), ("ICT_RTR", "PAU (repartidor) en el RTR"), ("TOMA:TV", "Toma de RTV"),
               ("ICT_CARGA", "Carga de 75 Ω"), ("CABLE:ICT_RTV:414002", "Cable coaxial (longitud en m)"),
               ("RECINTO", "RITS")]


def _leyenda_red(red: _Red) -> list[tuple[str, str]]:
    return [(f"TOMA:{red.tipos[0][1]}", "Toma"), ("ICT_RTR", "RTR con el PAU"), ("RECINTO", "RITI"),
            (f"CABLE:ICT_CANALIZACION:{red.cable}", "Cable (número, tipo y longitud en m)"),
            ("DISCONTINUA", "Red de alimentación de los operadores")]


def anadir_esquemas(doc, proyecto, mediciones: list[Medicion], tubos: dict, datos: dict, formato, plantilla=None,
                    primer_numero: int = 1) -> tuple[list[str], list[str]]:
    """Añade las hojas de los esquemas de principio. Devuelve los nombres de las presentaciones y los avisos."""
    from .dimensionado import dimensionar
    R = dimensionar(proyecto)
    viviendas = _viviendas(proyecto, R, mediciones)
    if not viviendas:
        return [], ["Esquemas de principio: el proyecto no tiene viviendas."]
    nombres, avisos = [], []
    hojas = [("Esquema general", "ICT · Esquema general de la infraestructura", LEYENDA_GENERAL, True,
              lambda L: _general(L, proyecto, R, viviendas, tubos)),
             ("Esquema RTV", "ICT · Esquema de radio y televisión", LEYENDA_RTV, False,
              lambda L: _rtv(L, proyecto, R, viviendas))]
    for red in _redes_tba(proyecto, R):
        hojas.append((red.corto, red.titulo, _leyenda_red(red), True,
                      lambda L, red=red: _red(L, proyecto, viviendas, red)))
    for k, (corto, titulo, leyenda, con_baja, dibujar) in enumerate(hojas):
        numero = primer_numero + k
        nombre = f"ICT-{numero} {corto}"
        lay, av = hoja_a3(doc, nombre, titulo, numero, "S/E", datos, formato, plantilla, leyenda)
        avisos += av
        dibujar(_Lamina(lay, formato.dibujo, _bandas(proyecto, con_baja, con_cubierta=k < 2)))
        nombres.append(nombre)
    if any(v.acometida_m is None for v in viviendas):
        avisos.append("Esquemas: faltan longitudes medidas de alguna vivienda; salen como «[PENDIENTE: medir]».")
    return nombres, avisos
