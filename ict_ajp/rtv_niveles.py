"""Cálculo de niveles de RTV toma a toma con el catálogo del fabricante.

Estructura (RD 346/2011, Anexo I): cabecera -> red de distribución con dos cables (3.3) -> un derivador
por planta en cada cable -> red de dispersión hasta el PAU de cada vivienda -> repartidor del PAU con una
salida por estancia (3.4) -> red interior en estrella hasta cada toma (2.3.3).

Se calculan, para cada vivienda, la atenuación de la toma mejor y la peor situada a las frecuencias
extremas de cada servicio, y con ellas el nivel de salida de cabecera que deja todas las tomas dentro de
los márgenes de 4.5. Las ganancias, pérdidas y atenuaciones salen del catálogo (CLAUDE.md, regla 3).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

from . import catalogo as C
from . import normativa as N

# Anexo I, 4.5: niveles en toma (dBµV) y relaciones C/N mínimas (dB)
NIVEL_TOMA = {"TDT": (47, 70), "DAB": (30, 70), "FM": (40, 70), "SAT": (47, 77)}
CN_MIN = {"TDT": 25, "DAB": 18, "FM": 38}
RESPUESTA_BANDA_MAX = {"terr": 16, "sat": 20}       # Anexo I, 4.4.3
# Bandas de cálculo (MHz): extremos de lo que se distribuye
BANDAS = {"FM": (87.5, 108.0), "DAB": (195.0, 223.0), "TDT": (470.0, 694.0), "SAT": (950.0, 2150.0)}
# Ruido térmico en 75 ohmios: kTB a 290 K (física, no norma). B en MHz.
def ruido_termico_dbuv(b_mhz: float) -> float:
    return round(10 * math.log10(1.380649e-23 * 290 * b_mhz * 1e6 * 75) + 120, 1)


ANCHO_BANDA_MHZ = {"TDT": 7.61, "DAB": 1.536, "FM": 0.2}   # DVB-T 8 MHz, bloque DAB, FM


def tension_antena_dbuv(campo_dbuvm: float, ganancia_dbi: float, f_mhz: float) -> float:
    """Tensión en bornes de una antena adaptada a 75 ohmios (física, no norma).

    V = E + G - 20 log f + 31,5, con E en dBµV/m, G en dBi y f en MHz
    (de Ae = G·λ²/4π, P = E²·Ae/120π y V² = P·75).
    """
    return round(campo_dbuvm + ganancia_dbi - 20 * math.log10(f_mhz) + 31.5, 1)


@dataclass
class Geometria:
    """Longitudes de cable (m). Por defecto, estimaciones conservadoras a sustituir por las de planos."""

    antena_cabecera: float = 10.0
    cabecera_primer_derivador: float = 5.0
    entre_plantas: float = 3.0
    acometida_min: float = 3.0
    acometida_max: float = 8.0
    interior_min: float = 3.0
    interior_max: float = 15.0


@dataclass
class Material:
    antena_uhf: str = "149922"
    antena_fm: str = "1201"
    antena_dab: str = "105001"
    amp_uhf: str = "509812"
    amp_fm_dab: str = "509012"
    fuente: str = "549812"
    repartidor_cabecera: str = "519502"     # reparto de la salida de cabecera a los dos cables (3.3)
    cable: str = "414002"
    toma: str = "527601"


@dataclass
class TramoVivienda:
    planta: str
    vivienda: str
    derivador: str
    pau: str
    tomas: int
    atenuacion: dict[str, tuple[float, float]] = field(default_factory=dict)   # servicio -> (mejor, peor)


@dataclass
class ResultadoNiveles:
    derivadores_por_planta: list[tuple[str, str]]        # (planta, ref)
    viviendas: list[TramoVivienda]
    salida_cabecera: dict[str, tuple[float, float]]      # servicio -> (mín. necesario, máx. admisible)
    salida_elegida: dict[str, float]
    niveles_toma: dict[str, tuple[float, float]]         # servicio -> (peor, mejor)
    entrada_amplificador: dict[str, float]
    cn_toma: dict[str, float]
    respuesta_banda: dict[str, float]
    consumo_ma: float
    cumple: dict[str, bool]
    notas: list[str] = field(default_factory=list)


def _cable(m: Material, metros: float, f: float) -> float:
    return metros * C.atenuacion_cable_db_m(m.cable, f)


def _terr_o_sat(f: float) -> str:
    return "sat" if f >= 950 else "terr"


def _toma_db(m: Material, f: float) -> float:
    t = C.elemento(m.toma)["atenuacion_db"]
    return t["SAT"] if f >= 950 else t.get("TV", t.get("FM"))


def calcular(plantas: list[tuple[str, list[tuple[str, int]]]], campos: dict[str, list[tuple[float, float]]],
             geo: Optional[Geometria] = None, mat: Optional[Material] = None,
             canales_tdt: int = 1) -> ResultadoNiveles:
    """plantas: [(nombre, [(vivienda, nº tomas), ...]), ...] ordenadas desde la cabecera hacia abajo.

    campos: por servicio terrestre («TDT», «FM», «DAB»), lista de (frecuencia MHz, campo de diseño dBµV/m);
    se calcula con la señal que peor llega a la cabecera.
    canales_tdt: número de amplificadores monocanal de UHF (para el consumo).
    """
    geo, mat = geo or Geometria(), mat or Material()
    n_plantas = len(plantas)
    max_viv = max(len(v) for _, v in plantas)
    candidatos = C.derivadores(max(2, max_viv))
    rep_cab = C.elemento(mat.repartidor_cabecera)["perdida_db"]

    def atenuaciones(combo, f: float) -> list[tuple[float, float]]:
        """(mejor, peor) por planta para la combinación de derivadores, sin PAU ni tramo interior."""
        b = _terr_o_sat(f)
        res, paso_acum = [], rep_cab[b]
        for k, d in enumerate(combo):
            metros = geo.cabecera_primer_derivador + k * geo.entre_plantas
            base = paso_acum + _cable(mat, metros, f) + d["derivacion_db"][b]
            res.append((base + _cable(mat, geo.acometida_min, f), base + _cable(mat, geo.acometida_max, f)))
            if d["paso_db"] is not None:
                paso_acum += d["paso_db"][b]
        return res

    # Combinación de derivadores que iguala mejor las plantas en TDT (la más exigente). Con pocas plantas se
    # prueban todas; con más, para cada nivel objetivo se elige planta a planta el derivador que más se acerca.
    f_lo, f_hi = BANDAS["TDT"]

    def evaluar(combo):
        a = atenuaciones(combo, f_lo) + atenuaciones(combo, f_hi)
        return (round(max(x[1] for x in a) - min(x[0] for x in a), 2), max(x[1] for x in a))

    if len(candidatos) ** n_plantas <= 1000:
        opciones = itertools.product(candidatos, repeat=n_plantas)
    else:
        opciones = []
        for objetivo in [x / 2 for x in range(20, 121)]:          # 10 a 60 dB
            combo, paso_acum = [], rep_cab["terr"]
            for k in range(n_plantas):
                cable = _cable(mat, geo.cabecera_primer_derivador + k * geo.entre_plantas, f_hi)
                d = min(candidatos, key=lambda c: abs(paso_acum + cable + c["derivacion_db"]["terr"] - objetivo))
                combo.append(d)
                paso_acum += d["paso_db"]["terr"] if d["paso_db"] else 0
            opciones.append(tuple(combo))
    combo = min(opciones, key=evaluar)

    viviendas: list[TramoVivienda] = []
    for (planta, vivs), d in zip(plantas, combo):
        for viv, n_tomas in vivs:
            pau = C.repartidor(n_tomas, pau=True)
            if pau is None:
                raise ValueError(f"{viv}: no hay en el catálogo un PAU de {n_tomas} salidas.")
            viviendas.append(TramoVivienda(planta, viv, d["ref"], pau["ref"], n_tomas))

    for servicio, (fa, fb) in BANDAS.items():
        for v in viviendas:
            k = [p for p, _ in plantas].index(v.planta)
            pau = C.elemento(v.pau)["perdida_db"]
            extremos = []
            for f in (fa, fb):
                b_, p_ = atenuaciones(combo, f)[k]
                extra_b = pau[_terr_o_sat(f)] + _cable(mat, geo.interior_min, f) + _toma_db(mat, f)
                extra_p = pau[_terr_o_sat(f)] + _cable(mat, geo.interior_max, f) + _toma_db(mat, f)
                extremos += [b_ + extra_b, p_ + extra_p]
            v.atenuacion[servicio] = (round(min(extremos), 1), round(max(extremos), 1))

    salida, elegida, niveles, entrada, cn, notas, cumple = {}, {}, {}, {}, {}, [], {}
    amp_uhf, amp_fd = C.elemento(mat.amp_uhf), C.elemento(mat.amp_fm_dab)
    antenas = {"TDT": C.elemento(mat.antena_uhf), "FM": C.elemento(mat.antena_fm), "DAB": C.elemento(mat.antena_dab)}
    amp = {"TDT": (amp_uhf["ganancia_db"][0], amp_uhf["nivel_salida_en50083_dbuv"][0]),
           "FM": (amp_fd["ganancia_db"][0], amp_fd["nivel_salida_en50083_dbuv"][0]),
           "DAB": (amp_fd["ganancia_db"][1], amp_fd["nivel_salida_en50083_dbuv"][1])}
    # figura de ruido de la ficha («< 8 dB», «< 5 dB»): se toma el máximo, caso más desfavorable
    figura_ruido = {"TDT": amp_uhf["figura_ruido_max_db"], "FM": amp_fd["figura_ruido_max_db"],
                    "DAB": amp_fd["figura_ruido_max_db"]}
    for servicio in ("TDT", "FM", "DAB", "SAT"):
        a_min = min(v.atenuacion[servicio][0] for v in viviendas)
        a_max = max(v.atenuacion[servicio][1] for v in viviendas)
        lo, hi = NIVEL_TOMA[servicio]
        salida[servicio] = (round(lo + a_max, 1), round(hi + a_min, 1))
        if servicio == "SAT":
            cumple[servicio] = salida[servicio][0] <= salida[servicio][1]
            continue
        v_in = min(round(tension_antena_dbuv(e, antenas[servicio]["ganancia_dbi"], f)
                         - _cable(mat, geo.antena_cabecera, f), 1) for f, e in campos[servicio])
        g, s_max = amp[servicio]
        s_posible = min(v_in + g, s_max)
        # se ajusta la salida al centro del margen útil, sin pasar de lo que da el amplificador
        s = min(round((salida[servicio][0] + salida[servicio][1]) / 2, 1), s_posible)
        elegida[servicio] = s
        niveles[servicio] = (round(s - a_max, 1), round(s - a_min, 1))
        entrada[servicio] = v_in
        cn[servicio] = round(v_in - figura_ruido[servicio] - ruido_termico_dbuv(ANCHO_BANDA_MHZ[servicio]), 1)
        cumple[servicio] = (niveles[servicio][0] >= lo and niveles[servicio][1] <= hi and cn[servicio] >= CN_MIN[servicio])
    respuesta = {}
    for b, (fa, fb) in (("terr", (BANDAS["FM"][0], BANDAS["TDT"][1])), ("sat", BANDAS["SAT"])):
        def total(v, f):
            k = [p for p, _ in plantas].index(v.planta)
            pau = C.elemento(v.pau)["perdida_db"]
            return atenuaciones(combo, f)[k][1] + pau[_terr_o_sat(f)] + _cable(mat, geo.interior_max, f) + _toma_db(mat, f)
        # la toma con más cable es la de mayor pendiente: se toma el máximo de todas
        respuesta[b] = round(max(total(v, fb) - total(v, fa) for v in viviendas), 1)
        cumple[f"respuesta_{b}"] = respuesta[b] <= RESPUESTA_BANDA_MAX[b]
    consumo = canales_tdt * C.elemento(mat.amp_uhf)["corriente_ma"] + C.elemento(mat.amp_fm_dab)["corriente_ma"]
    cumple["fuente"] = consumo <= C.elemento(mat.fuente)["corriente_a"] * 1000
    return ResultadoNiveles([(p, d["ref"]) for (p, _), d in zip(plantas, combo)], viviendas, salida, elegida,
                            niveles, entrada, cn, respuesta, consumo, cumple, notas)
