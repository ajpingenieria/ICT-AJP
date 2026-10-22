"""Lectura de la base DXF del arquitecto: plantas, viviendas y estancias.

Busca en el espacio modelo:

- Títulos de planta: textos que empiezan por «PLANTA» o «PL.» con un texto «ESCALA» justo debajo.
  Si hay varias vistas de la misma planta (distribución, cotas, accesibilidad...), se queda con
  la que más estancias rotuladas tiene. «PLANTA TIPO (2ª Y 3ª)» se cuenta como dos plantas.
- Estancias: un texto de superficie («12,07 m²») con el nombre de la estancia justo encima.
- Viviendas: polilíneas de superficie construida (capa configurable) que encierran estancias de
  vivienda (salón o dormitorio). Se numeran de izquierda a derecha en cada planta.
- Elementos de telecomunicaciones ya dibujados (RITU, RITI, RITS, armarios de telecomunicaciones)
  y ascensores.

No interpreta nada a criterio: devuelve lo que encuentra para que el proyectista lo confirme.
Se supone el dibujo en metros (el $INSUNITS de muchos planos no es fiable).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import ezdxf
from ezdxf.math import Vec2, area as area_poligono, is_point_in_polygon_2d

from .modelo import TipoEstancia

# ---------------------------------------------------------------------------
# Opciones de lectura (dependen de cómo dibuje cada arquitecto)
# ---------------------------------------------------------------------------


@dataclass
class OpcionesLectura:
    capas_viviendas: str = r"AREA.?CONST|SUP.?CONST|SUPERFICIE.?CONSTRUIDA"
    superficie_min_vivienda_m2: float = 25.0
    capas_ignoradas: str = r"CAJETIN"


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class EstanciaLeida:
    nombre: str
    superficie_m2: float
    x: float
    y: float
    tipo: TipoEstancia
    computa: Optional[bool]        # propuesta: None = a decidir por el proyectista
    motivo: str = ""


@dataclass
class ViviendaLeida:
    orden: int                     # 1, 2... de izquierda a derecha en la planta
    superficie_construida_m2: float
    estancias: list[EstanciaLeida] = field(default_factory=list)
    contorno: list[tuple[float, float]] = field(default_factory=list)   # polilínea de superficie construida

    @property
    def superficie_util_m2(self) -> float:
        return round(sum(e.superficie_m2 for e in self.estancias if not _es_exterior(e.nombre)), 2)


@dataclass
class PlantaLeida:
    titulo: str
    nombre: str                    # «PLANTA PRIMERA», «PLANTA SEGUNDA»...
    nivel: int
    repetida_de: Optional[str] = None   # título de la planta tipo de la que sale
    viviendas: list[ViviendaLeida] = field(default_factory=list)
    otras_estancias: list[EstanciaLeida] = field(default_factory=list)
    letras_puertas: list[str] = field(default_factory=list)
    zona: tuple = ()                    # (x0, x1, y0, y1) de la vista leída en el dibujo
    titulo_xy: tuple = ()               # posición del título de esa vista


@dataclass
class ElementoLeido:
    texto: str
    planta: str
    superficie_m2: Optional[float] = None


@dataclass
class LecturaPlano:
    archivo: str
    plantas: list[PlantaLeida]
    telecomunicaciones: list[ElementoLeido]
    ascensores: list[ElementoLeido]
    titulos_descartados: list[str]
    vistas: list[tuple[str, float, float]] = field(default_factory=list)   # todos los títulos (texto, x, y)


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

_RE_SUPERFICIE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*m(?:²|2)\s*$", re.I)
_RE_TITULO = re.compile(r"^(PLANTA|PL\.)\s+", re.I)
_RE_ESCALA = re.compile(r"^ESCALA\b", re.I)
_RE_LETRA = re.compile(r"^[A-Z]$")
# Textos de justificación que el arquitecto pone junto a las estancias y no son su nombre
_RE_ANOTACION = re.compile(r"[=<>]|SUP\.? ?HUECOS|CUMPLE|ILUMINACI|ESCALA|PDTE", re.I)
_RE_TELECO = re.compile(r"\bR\.?I\.?T\.?[USIM]\b|\bRIT[USIM]?\b|TELEC|ANTENA", re.I)
_RE_ASCENSOR = re.compile(r"ASCENSOR", re.I)

_ORDINALES = {
    "PRIMERA": 1, "SEGUNDA": 2, "TERCERA": 3, "CUARTA": 4, "QUINTA": 5, "SEXTA": 6,
    "SEPTIMA": 7, "OCTAVA": 8, "NOVENA": 9, "DECIMA": 10,
}
_NOMBRE_ORDINAL = {v: k for k, v in _ORDINALES.items()}


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)      # «ª» pasa a «a»: se pasa a mayúsculas después
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).upper().split())


def _es_exterior(nombre: str) -> bool:
    return bool(re.search(r"TERRAZA|PATIO|BALCON|JARDIN|PORCHE", normalizar(nombre)))


def clasificar_estancia(nombre: str) -> tuple[TipoEstancia, Optional[bool], str]:
    """Tipo de estancia y propuesta de si cuenta para tomas (Anexo II 3.4: excluidos baños y trasteros)."""
    n = normalizar(nombre)
    if re.search(r"BANO|\bWC\b", n):
        return TipoEstancia.bano, False, "baño (excluido por norma)"
    if "ASEO" in n:
        return TipoEstancia.aseo, False, "aseo (excluido por norma)"
    if "TRASTERO" in n:
        return TipoEstancia.trastero, False, "trastero (excluido por norma)"
    if re.search(r"SALON|ESTAR", n):
        return TipoEstancia.salon, True, ""
    if re.search(r"DORM|HABITACION|\bHAB\b", n):
        return TipoEstancia.dormitorio, True, ""
    if "COMEDOR" in n:
        return TipoEstancia.comedor, True, ""
    if "COCINA" in n:
        return TipoEstancia.cocina, True, ""
    if re.search(r"ESTUDIO|DESPACHO", n):
        return TipoEstancia.estudio, True, ""
    if re.search(r"VESTIBULO|PASO|PASILLO|DISTRIBUIDOR|RECIBIDOR|HALL", n):
        return TipoEstancia.otra, False, "zona de paso"
    if _es_exterior(n):
        return TipoEstancia.otra, False, "espacio exterior"
    if re.search(r"LAVADERO|TENDEDERO|VESTIDOR|DESPENSA|ARMARIO", n):
        return TipoEstancia.otra, False, "dependencia auxiliar"
    return TipoEstancia.otra, None, "sin clasificar"


def _nombre_planta(titulo: str) -> tuple[str, list[int] | None, int | None]:
    """«PLANTA TIPO (2ª Y 3ª) COTAS...» -> («PLANTA TIPO», [2, 3], None); «PLANTA PRIMERA» -> (..., None, 1)."""
    n = normalizar(titulo)
    n = re.sub(r"^PL\.\s*", "PLANTA ", n)
    m = re.match(r"PLANTA\s+(BAJA|SOTANO|SEMISOTANO|ENTREPLANTA|ATICO|BAJO ?CUBIERTA|CUBIERTA|TIPO|"
                 + "|".join(_ORDINALES) + r"|-?\d+)\b(\s*\([^)]*\))?", n)
    if not m:
        return n, None, None
    clave = m.group(1)
    nombre = f"PLANTA {clave}"
    if clave == "TIPO":
        ords = [int(x) for x in re.findall(r"(\d+)\s*[ªA]", m.group(2) or "")]
        return nombre, ords or None, None
    if clave in _ORDINALES:
        return nombre, None, _ORDINALES[clave]
    if clave == "BAJA":
        return nombre, None, 0
    if clave in ("SOTANO", "SEMISOTANO"):
        return nombre, None, -1
    if re.fullmatch(r"-?\d+", clave):
        return nombre, None, int(clave)
    return nombre, None, None      # ático, cubierta: se colocan encima de la última


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


@dataclass
class _Texto:
    texto: str
    x: float
    y: float
    h: float
    capa: str


def _textos(msp, opciones: OpcionesLectura) -> list[_Texto]:
    ignorar = re.compile(opciones.capas_ignoradas, re.I)
    res = []
    for e in msp.query("TEXT MTEXT"):
        if ignorar.search(e.dxf.layer):
            continue
        t = " ".join(e.plain_text().split())
        if not t:
            continue
        h = e.dxf.char_height if e.dxftype() == "MTEXT" else e.dxf.height
        p = e.dxf.insert
        res.append(_Texto(t, p.x, p.y, h or 0.1, e.dxf.layer))
    return res


def _poligonos_vivienda(msp, opciones: OpcionesLectura) -> list[tuple[list[Vec2], float]]:
    capas = re.compile(opciones.capas_viviendas, re.I)
    res: list[tuple[list[Vec2], float]] = []
    for e in msp.query("LWPOLYLINE"):
        if not capas.search(e.dxf.layer) or len(e) < 3:
            continue
        pts = [Vec2(p[0], p[1]) for p in e.get_points("xy")]
        sup = abs(area_poligono(pts))
        if sup < opciones.superficie_min_vivienda_m2:
            continue
        res.append((pts, sup))
    # Quitar duplicados (misma vivienda dibujada abierta y cerrada): si el centro de uno cae dentro
    # de otro de superficie parecida, se queda el mayor.
    res.sort(key=lambda r: -r[1])
    unicos: list[tuple[list[Vec2], float]] = []
    for pts, sup in res:
        c = sum(pts, Vec2()) / len(pts)
        if any(is_point_in_polygon_2d(c, u[0]) >= 0 and sup > 0.8 * u[1] for u in unicos):
            continue
        unicos.append((pts, sup))
    return unicos


def _emparejar_estancias(textos: list[_Texto]) -> list[EstanciaLeida]:
    superficies = [t for t in textos if _RE_SUPERFICIE.match(t.texto)]
    nombres = [t for t in textos if len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", t.texto)) >= 2
               and not _RE_SUPERFICIE.match(t.texto) and not _RE_ANOTACION.search(t.texto)]
    res: list[EstanciaLeida] = []
    for s in superficies:
        # Nombre encima de la superficie, o en la misma línea a su izquierda («R.I.T.U. 0.60 m²»)
        candidatos = [n for n in nombres
                      if (s.h <= n.y - s.y <= 2.5 * s.h and abs(n.x - s.x) <= 10 * s.h)
                      or (abs(n.y - s.y) < s.h and -10 * s.h <= n.x - s.x < 0)]
        if not candidatos:
            continue
        n = min(candidatos, key=lambda n: (n.y - s.y) ** 2 + (0.2 * (n.x - s.x)) ** 2)
        sup = float(_RE_SUPERFICIE.match(s.texto).group(1).replace(",", "."))
        if any(e.nombre == n.texto and abs(e.x - n.x) < s.h and abs(e.y - n.y) < s.h
               and abs(e.superficie_m2 - sup) < 0.01 for e in res):
            continue   # rótulo duplicado
        tipo, computa, motivo = clasificar_estancia(n.texto)
        res.append(EstanciaLeida(n.texto, sup, n.x, n.y, tipo, computa, motivo))
    return res


def leer_plano(ruta: str | Path, opciones: OpcionesLectura | None = None) -> LecturaPlano:
    opciones = opciones or OpcionesLectura()
    doc = ezdxf.readfile(str(ruta))
    msp = doc.modelspace()
    textos = _textos(msp, opciones)

    # Títulos de vistas: todo texto con «ESCALA» justo debajo. Sirven de límites entre vistas.
    escalas = [t for t in textos if _RE_ESCALA.match(t.texto)]
    titulos = [t for t in textos if not _RE_ESCALA.match(t.texto)
               and any(0 < t.y - e.y <= 2.5 * e.h and abs(t.x - e.x) <= 2 * e.h for e in escalas)]
    def zona(t: _Texto) -> tuple[float, float, float, float]:
        # Hasta el siguiente título de la misma fila a la derecha, y hasta el siguiente título
        # que haya encima en esa franja (si las vistas están en varias filas).
        x0 = t.x - 2 * t.h
        misma_fila = sorted(o.x for o in titulos if abs(o.y - t.y) < 3 * t.h and o.x > t.x + t.h)
        x1 = (misma_fila[0] - 2 * t.h) if misma_fila else float("inf")
        encima = [o.y for o in titulos if o.y > t.y + 3 * t.h and x0 <= o.x < x1]
        y1 = (min(encima) - 2 * t.h) if encima else float("inf")
        return x0, x1, t.y - t.h, y1

    estancias = _emparejar_estancias(textos)
    poligonos = _poligonos_vivienda(msp, opciones)

    # Para cada planta, la vista con más estancias rotuladas
    vistas: dict[str, tuple[_Texto, list[int] | None, int | None, tuple]] = {}
    cuenta: dict[str, int] = {}
    descartados: list[str] = []
    for t in titulos:
        if not _RE_TITULO.match(t.texto):
            continue
        nombre, repeticion, nivel = _nombre_planta(t.texto)
        z = zona(t)
        n = sum(1 for e in estancias if z[0] <= e.x < z[1] and z[2] <= e.y < z[3])
        if n and "SUPERFICIE" in normalizar(t.texto):
            n += 10_000        # la vista de superficies manda: es la que acota el arquitecto
        if nombre not in vistas or n > cuenta[nombre]:
            if nombre in vistas:
                descartados.append(vistas[nombre][0].texto)
            vistas[nombre], cuenta[nombre] = (t, repeticion, nivel, z), n
        else:
            descartados.append(t.texto)

    plantas: list[PlantaLeida] = []
    for nombre, (t, repeticion, nivel, z) in vistas.items():
        dentro = [e for e in estancias if z[0] <= e.x < z[1] and z[2] <= e.y < z[3]]
        polis = [(p, s) for p, s in poligonos
                 if all(z[0] <= v.x < z[1] and z[2] <= v.y < z[3] for v in p)]
        viviendas: list[ViviendaLeida] = []
        libres = list(dentro)
        for pts, sup in sorted(polis, key=lambda r: min(v.x for v in r[0])):
            suyas = [e for e in libres if is_point_in_polygon_2d(Vec2(e.x, e.y), pts) >= 0]
            if any(e.tipo in (TipoEstancia.salon, TipoEstancia.dormitorio) for e in suyas):
                viviendas.append(ViviendaLeida(len(viviendas) + 1, round(sup, 2), suyas,
                                               [(v.x, v.y) for v in pts]))
                libres = [e for e in libres if e not in suyas]
        letras = sorted({x.texto for x in textos if _RE_LETRA.match(x.texto)
                         and z[0] <= x.x < z[1] and z[2] <= x.y < z[3]}) if viviendas else []
        base = PlantaLeida(t.texto, nombre, nivel if nivel is not None else 0, None,
                           viviendas, libres, letras, z, (t.x, t.y))
        if repeticion:
            for k in repeticion:
                plantas.append(PlantaLeida(t.texto, f"PLANTA {_NOMBRE_ORDINAL.get(k, str(k))}", k,
                                           t.texto, viviendas, libres, letras, z, (t.x, t.y)))
        elif nivel is None:
            plantas.append(base)       # se coloca después
            base.nivel = 10_000 if "CUBIERTA" in nombre and "BAJO" not in nombre else 9_999
        else:
            plantas.append(base)
    plantas.sort(key=lambda p: p.nivel)
    ultimo = max((p.nivel for p in plantas if p.nivel < 9_999), default=0)
    for p in plantas:
        if p.nivel >= 9_999:
            ultimo += 1
            p.nivel = ultimo

    def planta_de(x: float, y: float) -> str:
        for p in plantas:
            t, _, _, z = vistas[next(k for k, v in vistas.items() if v[0].texto == p.titulo)]
            if z[0] <= x < z[1] and z[2] <= y < z[3]:
                return p.repetida_de or p.nombre
        return "(fuera de las plantas)"

    def elementos(regex: re.Pattern) -> list[ElementoLeido]:
        res, vistos = [], set()
        for x in textos:
            if not regex.search(x.texto):
                continue
            pl = planta_de(x.x, x.y)
            if pl == "(fuera de las plantas)":
                continue
            sup = next((e.superficie_m2 for e in estancias if e.nombre == x.texto
                        and abs(e.x - x.x) < 1e-6 and abs(e.y - x.y) < 1e-6), None)
            if (x.texto, pl) not in vistos:
                vistos.add((x.texto, pl))
                res.append(ElementoLeido(x.texto, pl, sup))
        return res

    return LecturaPlano(str(ruta), plantas, elementos(_RE_TELECO), elementos(_RE_ASCENSOR), descartados,
                        [(t.texto, t.x, t.y) for t in titulos])


# ---------------------------------------------------------------------------
# Paso a proyecto (.ict.json de borrador)
# ---------------------------------------------------------------------------

_ORDINAL_CORTO = {1: "1ª", 2: "2ª", 3: "3ª"}


def _id_planta(p: PlantaLeida) -> tuple[str, str]:
    """(nombre de planta, prefijo de vivienda): («Planta 1ª», «1º»), («Planta ático», «Ático »)."""
    if "ATICO" in p.nombre:
        return "Planta ático", "Ático "
    if p.nivel == 0:
        return "Planta baja", "Bajo "
    return f"Planta {_ORDINAL_CORTO.get(p.nivel, f'{p.nivel}ª')}", f"{p.nivel}º"


def proyecto_desde_lectura(lectura: LecturaPlano, nombres: str = "planta_letra"):
    """Borrador de proyecto con las plantas y viviendas leídas del plano.

    nombres: «planta_letra» (1ºA, 1ºB... Ático A) o «letras_seguidas» (A, B, C... de abajo arriba).
    Las viviendas de cada planta se nombran de izquierda a derecha. La tipología agrupa las viviendas
    con las mismas estancias. Se marca como principal el salón (Anexo II 3.5.1.a) y, como «otra de
    las estancias» con BAT doble, que la norma deja sin fijar, el dormitorio mayor.
    """
    from .modelo import Edificio, Estancia, Planta, Proyecto, Usuario

    firmas: dict[tuple, str] = {}
    plantas = []
    letra_seguida = 0
    for p in lectura.plantas:
        if "CUBIERTA" in p.nombre and "BAJO" not in p.nombre and not p.viviendas:
            continue
        nombre_pl, prefijo = _id_planta(p)
        usuarios = []
        for i, v in enumerate(p.viviendas):
            if nombres == "letras_seguidas":
                vid = chr(ord("A") + letra_seguida)
                letra_seguida += 1
            else:
                vid = f"{prefijo}{chr(ord('A') + i)}"
            firma = tuple(sorted((e.nombre, e.superficie_m2) for e in v.estancias))
            tipologia = firmas.setdefault(firma, f"Tipo {len(firmas) + 1}")
            dorms = [e for e in v.estancias if e.tipo == TipoEstancia.dormitorio]
            mayor = max(dorms, key=lambda e: e.superficie_m2) if dorms else None
            estancias = []
            for e in v.estancias:
                forzar = e.computa if (e.tipo == TipoEstancia.otra and e.computa is False) else None
                estancias.append(Estancia(nombre=e.nombre, tipo=e.tipo, computa=forzar,
                                          principal=e.tipo == TipoEstancia.salon or e is mayor))
            usuarios.append(Usuario(id=vid, tipologia=tipologia, estancias=estancias,
                                    superficie_util_m2=v.superficie_util_m2))
        plantas.append(Planta(nombre=nombre_pl, nivel=p.nivel, es_atico="ATICO" in p.nombre, usuarios=usuarios))
    return Proyecto(edificio=Edificio(plantas=plantas))


# ---------------------------------------------------------------------------
# Informe para el proyectista
# ---------------------------------------------------------------------------


def _m2(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") + " m²"


_ACENTOS = {"ATICO": "ático", "SOTANO": "sótano", "SEMISOTANO": "semisótano", "SEPTIMA": "séptima",
            "DECIMA": "décima"}


def nombre_legible(nombre: str) -> str:
    """«PLANTA ATICO» -> «Planta ático»."""
    return " ".join(_ACENTOS.get(w, w.lower()) for w in nombre.split()).capitalize()


def informe(lectura: LecturaPlano) -> str:
    L = [f"Lectura del plano: {Path(lectura.archivo).name}", ""]
    vistas_tipo: set[str] = set()
    for p in lectura.plantas:
        cab = f"{nombre_legible(p.nombre)} (nivel {p.nivel})"
        if p.repetida_de:
            cab += f" — según «{p.repetida_de}»"
        L.append(cab)
        if p.repetida_de and p.repetida_de in vistas_tipo:
            L.append(f"  Igual que la anterior: {len(p.viviendas)} viviendas.")
            L.append("")
            continue
        vistas_tipo.add(p.repetida_de or "")
        if p.letras_puertas:
            L.append(f"  Letras rotuladas en la planta: {', '.join(p.letras_puertas)}")
        for v in p.viviendas:
            cuentan = [e for e in v.estancias if e.computa]
            L.append(f"  Vivienda {v.orden} (de izquierda a derecha): construida {_m2(v.superficie_construida_m2)}, "
                     f"útil interior {_m2(v.superficie_util_m2)}, {len(cuentan)} estancias para tomas")
            for e in v.estancias:
                marca = "cuenta" if e.computa else ("A DECIDIR" if e.computa is None else "no cuenta")
                L.append(f"    - {e.nombre}: {_m2(e.superficie_m2)}  [{marca}{', ' + e.motivo if e.motivo else ''}]")
        if p.otras_estancias:
            L.append("  Fuera de viviendas:")
            for e in p.otras_estancias:
                L.append(f"    - {e.nombre}: {_m2(e.superficie_m2)}")
        L.append("")
    L.append("Elementos de telecomunicaciones dibujados:")
    for e in lectura.telecomunicaciones or []:
        L.append(f"  - {e.texto} en {nombre_legible(e.planta).lower()}"
                 + (f": {_m2(e.superficie_m2)}" if e.superficie_m2 else ""))
    if not lectura.telecomunicaciones:
        L.append("  (ninguno)")
    L.append("Ascensores: " + (", ".join(f"{e.texto} ({nombre_legible(e.planta).lower()})"
                                         for e in lectura.ascensores)
                               if lectura.ascensores else "no aparece ninguno rotulado"))
    return "\n".join(L)
