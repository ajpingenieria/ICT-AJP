"""Motor de dimensionado de la ICT (redes de telefonía y banda ancha e infraestructura).

Entrada: un `Proyecto`. Salida: un `Resultado` con secciones de partidas y
tablas, cada cifra con su referencia normativa, más una lista de avisos con
las decisiones que tiene que revisar el proyectista.

El cálculo de RTV (Anexo I, ap. 4) va en un módulo aparte (versión 0.2).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from . import normativa as N
from .modelo import Planta, Proyecto, TipoEstancia, TipoUsuario, Usuario


# ---------------------------------------------------------------------------
# Estructuras de resultado
# ---------------------------------------------------------------------------

@dataclass
class Partida:
    concepto: str
    valor: Any
    unidad: str = ""
    referencia: str = ""
    nota: str = ""


@dataclass
class Tabla:
    titulo: str
    cabeceras: list[str]
    filas: list[list[Any]]
    referencia: str = ""
    fila_total: Optional[list[Any]] = None
    col_unidades: Optional[int] = None  # nº de columna (1-based) con las unidades por fila, para totales ponderados


@dataclass
class Seccion:
    clave: str
    titulo: str
    partidas: list[Partida] = field(default_factory=list)
    tablas: list[Tabla] = field(default_factory=list)

    def add(self, *a, **k) -> Partida:
        p = Partida(*a, **k)
        self.partidas.append(p)
        return p


@dataclass
class Aviso:
    nivel: str  # "revisar" | "decision" | "info"
    texto: str
    referencia: str = ""


@dataclass
class Resultado:
    secciones: list[Seccion] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)
    datos: dict[str, Any] = field(default_factory=dict)

    def seccion(self, clave: str) -> Seccion:
        return next(s for s in self.secciones if s.clave == clave)

    def aviso(self, nivel: str, texto: str, referencia: str = "") -> None:
        self.avisos.append(Aviso(nivel, texto, referencia))


def _repartir(total: int, pesos: list[int]) -> list[int]:
    """Reparte `total` unidades de forma uniforme, priorizando los pesos mayores."""
    n = len(pesos)
    if n == 0 or total <= 0:
        return [0] * n
    base, resto = divmod(total, n)
    orden = sorted(range(n), key=lambda i: (-pesos[i], i))
    out = [base] * n
    for i in orden[:resto]:
        out[i] += 1
    return out


# ---------------------------------------------------------------------------
# Red interior de usuario
# ---------------------------------------------------------------------------

@dataclass
class InteriorUsuario:
    estancias_computables: int = 0
    reg_pt: int = 0
    reg_tba: int = 0
    reg_rtv: int = 0
    reg_fo: int = 0
    reg_configurable: int = 0
    tomas_pt: int = 0  # conectores RJ45 = acometidas interiores de pares trenzados desde el PAU
    tomas_tba: int = 0
    tomas_rtv: int = 0
    nota: str = ""

    @property
    def registros(self) -> int:
        return self.reg_pt + self.reg_tba + self.reg_rtv + self.reg_fo + self.reg_configurable


_PRIORIDAD_PRINCIPAL = [TipoEstancia.salon, TipoEstancia.comedor, TipoEstancia.dormitorio,
                        TipoEstancia.estudio, TipoEstancia.otra, TipoEstancia.cocina]


def _principales(u: Usuario) -> int:
    comp = u.estancias_computables()
    marcadas = [e for e in comp if e.principal]
    if len(marcadas) >= 2:
        return 2
    return min(2, len(comp))


def interior_usuario(u: Usuario, equipar_todos: bool) -> InteriorUsuario:
    r = InteriorUsuario()
    comp = u.estancias_computables()
    n = len(comp)
    r.estancias_computables = n

    if u.tipo == TipoUsuario.vivienda:
        p = _principales(u)
        resto = max(0, n - p)
        # Anexo III 5.13: 2 PT + 1 TBA + 1 RTV en cada estancia principal; 1 FO en una de ellas;
        # 1 PT + 1 RTV en el resto; 1 configurable junto al PAU.
        r.reg_pt = 2 * p + resto
        r.reg_tba = p
        r.reg_rtv = max(n, N.RTV_TOMAS_MIN_VIVIENDA)  # Anexo I 3.5.1
        r.reg_fo = 1 if n >= 1 else 0
        r.reg_configurable = 1
        # Anexo II 3.5.1: salón con BAT doble + BAT; otra estancia con BAT doble; resto BAT.
        if p >= 2:
            tomas_principal_2 = 3 if equipar_todos else 2
            r.tomas_pt = 3 + tomas_principal_2 + resto
        else:
            r.tomas_pt = 3 * p + resto
        r.tomas_tba = 2  # Anexo II 3.5.2: dos tomas en dos estancias diferentes
        r.tomas_rtv = r.reg_rtv
        if n < 2:
            r.nota = "Menos de 2 estancias computables: revisar registros de las estancias principales."
    elif u.tipo in (TipoUsuario.local, TipoUsuario.oficina):
        if not u.distribucion_definida:
            r.nota = "Sin distribución definida: no se instala red interior (Anexo II 3.5.1.c, Anexo III 5.13)."
            return r
        n = max(n, 1)
        r.estancias_computables = n
        r.reg_pt = n           # Anexo II 3.5.1.b: 1 registro por estancia con BAT doble
        r.tomas_pt = 2 * n
        r.reg_tba = 1          # Anexo III 5.13: mínimo 3 registros, uno de cada tipo
        r.reg_rtv = 1
        r.tomas_tba = 0        # Anexo II 3.5.2.b: red coaxial interior a cargo de la propiedad
        r.tomas_rtv = 1
        r.nota = "Mínimos de la norma; ampliar según superficie y uso del local."
    else:  # estancia común
        r.estancias_computables = 1
        r.reg_pt = r.reg_tba = r.reg_rtv = 1
        r.tomas_rtv = 1
        r.nota = "Dimensionado de la red interior a criterio del proyectista (Anexo II 3.5.1.d)."
    return r


# ---------------------------------------------------------------------------
# Motor principal
# ---------------------------------------------------------------------------

def dimensionar(p: Proyecto) -> Resultado:
    ed, op, ops = p.edificio, p.opciones, p.operadores
    R = Resultado()
    edif_oficinas = ed.uso == "oficinas"
    plantas = sorted(ed.plantas, key=lambda x: x.nivel)
    usuarios = ed.usuarios()
    n_pau = len(usuarios)
    # Recinto donde está el registro principal: RITU cuando se admite recinto único (Anexo III 4.5.3)
    rit_inf = "RITU" if ed.recintos == "RITU" and n_pau <= N.RITU_A_MAX_PAU else "RITI"
    if n_pau == 0:
        raise ValueError("El edificio no tiene viviendas, locales ni estancias comunes.")
    plantas_con_pau = [pl for pl in plantas if pl.usuarios]
    max_pau_planta = max(len(pl.usuarios) for pl in plantas_con_pau)
    verticales = ed.verticales

    # --- Tecnología de cobre -------------------------------------------------
    if op.tecnologia_cobre:
        cobre, motivo = op.tecnologia_cobre, "fijada por el proyectista"
    elif ed.distancia_max_pi_pau_m is None:
        cobre, motivo = "pares_trenzados", "distancia no indicada; se asume inferior a 100 m"
        R.aviso("revisar", "No se ha indicado la distancia del punto de interconexión al PAU más alejado. "
                "Se asume inferior a 100 m (red de pares trenzados).", N.ref("II", "3.1.1"))
    elif ed.distancia_max_pi_pau_m <= N.DIST_MAX_PARES_TRENZADOS_M:
        cobre, motivo = "pares_trenzados", f"distancia {ed.distancia_max_pi_pau_m:g} m ≤ 100 m"
    else:
        cobre, motivo = "pares", f"distancia {ed.distancia_max_pi_pau_m:g} m > 100 m"
    nombre_cobre = "pares trenzados (cat. 6)" if cobre == "pares_trenzados" else "pares (multipar)"

    if not ops.consulta_realizada:
        # Art. 8.4: la consulta se hace justo antes del inicio de obra, en el replanteo, y su resultado
        # solo decide qué redes se cablean al principio (art. 8.1). Mientras tanto se proyectan todas.
        ops = ops.model_copy(update={"pares_trenzados": True, "coaxial": True, "fibra": True})
        R.aviso("info", "Consulta a operadores pendiente: se hace en el replanteo, justo antes de empezar la obra, "
                "y se refleja en el acta de replanteo. El proyecto incluye las tres redes (pares trenzados, coaxial "
                "y fibra). Las que ningún operador vaya a usar se dejarán solo canalizadas con hilo guía (Anexo II, "
                "3.1.x.b), y la consulta confirma la ubicación de la arqueta de entrada.",
                f"{N.RD}, art. 8.1 y 8.4")

    # --- 1. Datos del edificio ----------------------------------------------
    s = Seccion("edificio", "Datos del edificio")
    filas = []
    conteo = defaultdict(int)
    for pl in plantas:
        c = defaultdict(int)
        for u in pl.usuarios:
            c[u.tipo.value] += 1
            conteo[u.tipo.value] += 1
        filas.append([pl.nombre, pl.nivel, c["vivienda"], c["local"], c["oficina"], c["estancia_comun"],
                      len(pl.usuarios), ", ".join(str(v) for v in sorted({u.vertical for u in pl.usuarios})) or "-"])
    s.tablas.append(Tabla("Usuarios (PAU) por planta",
                          ["Planta", "Nivel", "Viviendas", "Locales", "Oficinas", "Est. comunes", "PAU", "Vertical"],
                          filas, "RD 346/2011, Anexo III, nota 1",
                          ["TOTAL", "", conteo["vivienda"], conteo["local"], conteo["oficina"],
                           conteo["estancia_comun"], n_pau, ""]))
    s.add("Número total de PAU", n_pau, "PAU", "Anexo III, nota 1",
          "Un PAU por vivienda, local, oficina o estancia común.")
    s.add("Plantas con PAU", len(plantas_con_pau), "plantas")
    s.add("Máximo de PAU en una planta", max_pau_planta, "PAU")
    s.add("Verticales de distribución", len(verticales), "")
    s.add("Ascensores", ed.ascensores, "")
    s.add("Uso de la edificación", "Viviendas" if not edif_oficinas else "Fundamentalmente locales u oficinas")
    s.add("Tecnología de cobre", nombre_cobre, "", N.ref("II", "3.1.1 / 3.1.2"), motivo)
    R.secciones.append(s)

    por_planta_vertical = defaultdict(int)
    for pl, u in usuarios:
        por_planta_vertical[(pl.nivel, u.vertical)] += 1
    excesos = [(niv, v, n) for (niv, v), n in por_planta_vertical.items() if n > N.MAX_USUARIOS_POR_PLANTA_Y_VERTICAL]
    for niv, v, n in excesos:
        R.aviso("decision", f"Planta de nivel {niv}, vertical {v}: {n} usuarios. Con más de 8 usuarios por planta "
                "se recomienda más de una vertical.", N.ref("III", "5.7"))

    # --- 2. Previsión de la demanda -----------------------------------------
    s = Seccion("demanda", "Previsión de la demanda")
    dem = {}  # id usuario -> dict
    filas = []
    tot = defaultdict(int)
    for pl in plantas:
        fila_pl = defaultdict(int)
        for u in pl.usuarios:
            sup = u.superficie_util_m2
            t, d = u.tipo.value, u.distribucion_definida
            pt = (N.demanda_pares_trenzados(t, edif_oficinas, d, sup) if cobre == "pares_trenzados"
                  else N.demanda_pares(t, edif_oficinas, d, sup))
            cx = N.demanda_coaxial(t, d, sup)
            fo = N.demanda_fibra(t, edif_oficinas, d, sup)
            dem[u.id] = {"cobre": pt.valor, "coaxial": cx.valor, "fibra": fo.valor, "planta": pl.nivel,
                         "vertical": u.vertical}
            for k, v in (("cobre", pt.valor), ("coaxial", cx.valor), ("fibra", fo.valor)):
                fila_pl[k] += v
                tot[k] += v
        if pl.usuarios:
            filas.append([pl.nombre, len(pl.usuarios), fila_pl["cobre"], fila_pl["coaxial"], fila_pl["fibra"]])
    com = N.ACOMETIDAS_INSTALACIONES_COMUNES
    filas.append(["Instalaciones comunes del edificio", "-", com, com, com])
    for k in ("cobre", "coaxial", "fibra"):
        tot[k] += com
    unidad_cobre = "acometidas cat. 6" if cobre == "pares_trenzados" else "líneas (pares)"
    s.tablas.append(Tabla("Demanda por planta",
                          ["Planta", "PAU", f"Cobre ({unidad_cobre})", "Coaxial (acometidas)",
                           "Fibra (acometidas de 2 fibras)"],
                          filas, N.ref("II", "3.1"),
                          ["TOTAL", n_pau, tot["cobre"], tot["coaxial"], tot["fibra"]]))
    s.add(f"Demanda total de cobre", tot["cobre"], unidad_cobre, N.ref("II", "3.1.1" if cobre == "pares_trenzados" else "3.1.2"),
          "Incluye 2 para instalaciones comunes del edificio.")
    s.add("Demanda total coaxial", tot["coaxial"], "acometidas", N.ref("II", "3.1.3"))
    s.add("Demanda total de fibra óptica", tot["fibra"], "acometidas (2 fibras)", N.ref("II", "3.1.4"))
    for tec, hay, ap in (("pares trenzados", ops.pares_trenzados, "3.1.1.b"),
                         ("cable coaxial", ops.coaxial, "3.1.3.b"), ("fibra óptica", ops.fibra, "3.1.4.b")):
        if not hay:
            s.add(f"Red de {tec}", "Sin operador: solo canalización con hilo guía", "", N.ref("II", ap))
    sin_dist = [u.id for _, u in usuarios if u.tipo in (TipoUsuario.local, TipoUsuario.oficina)
                and not u.distribucion_definida]
    if sin_dist:
        R.aviso("info", f"Locales/oficinas sin distribución definida ({', '.join(sin_dist)}): sus acometidas se dejan "
                f"disponibles en el registro secundario de la planta (fibra en el {rit_inf} si hay menos de 15 PAU).",
                N.ref("II", "3.1.3.a.ii.2 / 3.1.4.a.ii.2"))
    R.secciones.append(s)

    # --- 3. Redes de distribución y dispersión ------------------------------
    s = Seccion("redes", "Redes de distribución y dispersión")
    v_princ = verticales[0]
    reg_pt_salida = reg_fo_salida = reg_cx_salida = 0
    datos_v = {}
    for v in verticales:
        us_v = [(pl, u) for pl, u in usuarios if u.vertical == v]
        pau_v = len(us_v)
        plantas_v = [pl for pl in plantas if any(u.vertical == v for u in pl.usuarios)]
        comunes = com if v == v_princ else 0
        sufijo = f" (vertical {v})" if len(verticales) > 1 else ""

        # Cobre
        dem_pl = [sum(dem[u.id]["cobre"] for u in pl.usuarios if u.vertical == v) for pl in plantas_v]
        d_cobre = sum(dem_pl) + comunes
        if cobre == "pares_trenzados":
            total_cables = math.ceil(d_cobre * N.FACTOR_RESERVA)
            reserva = total_cables - d_cobre
            rep = _repartir(reserva, dem_pl)
            filas = [[pl.nombre, d, r, d + r] for pl, d, r in zip(plantas_v, dem_pl, rep)]
            if comunes:
                filas.append([f"Instalaciones comunes (desde {rit_inf})", comunes, 0, comunes])
            s.tablas.append(Tabla(f"Cables de pares trenzados por planta{sufijo}",
                                  ["Planta", "Demanda", "Reserva", "Cables cat. 6"], filas, N.ref("II", "3.3.1"),
                                  ["TOTAL", d_cobre, reserva, total_cables]))
            s.add(f"Cables de 4 pares trenzados cat. 6{sufijo}", total_cables, "cables", N.ref("II", "3.3.1"),
                  f"{d_cobre} x 1,2 = {d_cobre * 1.2:.1f}; la reserva se deja en los registros secundarios.")
            reg_pt_salida += total_cables
            datos_cobre = {"cables": total_cables, "demanda": d_cobre, "por_planta": filas}
        else:
            n_pares = math.ceil(d_cobre * N.FACTOR_RESERVA)
            cab = N.cable_multipar(n_pares)
            n_pl = len(plantas_v)
            regletas = math.ceil(n_pares / (n_pl * op.regleta_pares)) if n_pl else 0
            s.add(f"Pares de la red de distribución{sufijo}", n_pares, "pares", N.ref("II", "3.3.2.a.i"),
                  f"{d_cobre} líneas x 1,2.")
            s.add(f"Cable multipar{sufijo}", cab.valor, "", cab.referencia,
                  "Con 30 pares o menos se puede usar cable de 1 o 2 pares desde el registro principal."
                  if n_pares <= 30 else cab.nota)
            s.add(f"Regletas de {op.regleta_pares} pares por planta{sufijo}", regletas, "regletas",
                  N.ref("II", "3.3.2.a.ii"))
            reg_pt_salida += n_pares
            datos_cobre = {"pares": n_pares, "cable": cab.valor, "regletas_planta": regletas}

        # Coaxial
        d_cx = sum(dem[u.id]["coaxial"] for _, u in us_v) + comunes
        estrella = pau_v <= N.COAXIAL_ESTRELLA_MAX_PAU
        if estrella:
            s.add(f"Red coaxial{sufijo}", f"Estrella: {d_cx} cables coaxiales desde el {rit_inf}", "cables",
                  N.ref("II", "3.3.3.a.i"), "Con 20 PAU o menos.")
            reg_cx_salida += d_cx
        else:
            s.add(f"Red coaxial{sufijo}", "Árbol-rama: 1 cable de distribución con derivador en cada registro "
                  f"secundario ({len(plantas_v)} derivadores)", "", N.ref("II", "3.3.3.a.ii"),
                  "Con más de 20 PAU.")
            reg_cx_salida += 1
        s.add(f"Acometidas coaxiales de dispersión{sufijo}", d_cx - comunes, "cables", N.ref("II", "3.4.3"))
        if not ops.coaxial:
            s.partidas[-1].nota = "Sin operador de cable: canalización con hilo guía, sin cablear."

        # Fibra óptica
        d_fo = sum(dem[u.id]["fibra"] for _, u in us_v) + comunes
        fibras_teoricas = d_fo * N.FIBRAS_POR_ACOMETIDA * N.FACTOR_RESERVA
        if pau_v <= N.FIBRA_ACOMETIDAS_DIRECTAS_MAX_PAU:
            n_acom = math.ceil(d_fo * N.FACTOR_RESERVA)
            fibras = n_acom * N.FIBRAS_POR_ACOMETIDA
            s.add(f"Red de fibra óptica{sufijo}", f"{n_acom} cables de acometida de 2 fibras desde el {rit_inf}", "cables",
                  N.ref("II", "3.3.4.a"), f"{d_fo} acometidas x 1,2 (20 PAU o menos: acometidas directas).")
            datos_fo = {"tipo": "acometidas", "cables": n_acom, "fibras": fibras}
        else:
            fibras_min = math.ceil(fibras_teoricas)
            cab = N.cables_multifibra(fibras_min)
            fibras = sum(cab.valor)
            s.add(f"Red de fibra óptica{sufijo}",
                  " + ".join(f"1 cable de {c} fibras" for c in cab.valor), "", cab.referencia,
                  f"{d_fo} acometidas x 2 fibras x 1,2 = {fibras_teoricas:.1f} fibras. Sobrantes repartidas "
                  "en los registros secundarios.")
            s.add(f"Acometidas ópticas de dispersión (2 fibras){sufijo}", d_fo - comunes, "cables",
                  N.ref("II", "3.4.4"))
            datos_fo = {"tipo": "multifibra", "cables": cab.valor, "fibras": fibras}
        reg_fo_salida += fibras
        datos_v[v] = {"pau": pau_v, "plantas": [pl.nivel for pl in plantas_v], "cobre": datos_cobre,
                      "coaxial": {"estrella": estrella, "acometidas": d_cx}, "fibra": datos_fo}

    # Registro principal
    asc = ed.ascensores * op.prevision_ascensor_por_tecnologia
    pt_sal = reg_pt_salida + asc
    e_pt = N.registro_principal_entrada_pt(pt_sal, n_pau)
    s.add("Registro principal de cobre: salidas", pt_sal, "conectores/pares", N.ref("III", "5.6.1" if cobre ==
          "pares_trenzados" else "5.6.2"), f"Incluye {asc} de previsión para ascensores." if asc else "")
    s.add("Registro principal de cobre: capacidad de entrada", e_pt.valor, "pares", e_pt.referencia, e_pt.nota)
    fo_sal = reg_fo_salida + asc * N.FIBRAS_POR_ACOMETIDA
    e_fo = N.registro_principal_entrada_fo(fo_sal)
    s.add("Registro principal óptico: conectores de salida", fo_sal, "conectores", N.ref("III", "5.6.4"),
          f"Incluye {asc * 2} de previsión para ascensores." if asc else "")
    s.add("Registro principal óptico: conectores de entrada", e_fo.valor, "conectores", e_fo.referencia, e_fo.nota)
    s.add("Registro principal coaxial: salidas", reg_cx_salida + asc, "conectores F", N.ref("III", "5.6.3"))
    R.secciones.append(s)

    # --- 4. Red interior de usuario -----------------------------------------
    s = Seccion("interior", "Red interior de usuario y registros de toma")
    grupos: dict[tuple, list[str]] = defaultdict(list)
    res_int: dict[str, InteriorUsuario] = {}
    for _, u in usuarios:
        iu = interior_usuario(u, op.equipar_todos_registros_pt)
        res_int[u.id] = iu
        clave = (u.tipo.value, u.tipologia or "", iu.estancias_computables, iu.reg_pt, iu.reg_tba, iu.reg_rtv,
                 iu.reg_fo, iu.reg_configurable, iu.tomas_pt, iu.tomas_tba, iu.tomas_rtv, iu.nota)
        grupos[clave].append(u.id)
    filas = []
    tot_int = defaultdict(int)
    for clave, ids in grupos.items():
        tipo, tip, n_e, rpt, rtba, rrtv, rfo, rconf, tpt, ttba, trtv, nota = clave
        n = len(ids)
        tubos = rpt + rtba + rrtv + rfo + rconf
        filas.append([tipo + (f" {tip}" if tip else ""), n, ", ".join(ids), n_e, rpt, rtba, rrtv, rfo, rconf,
                      tpt, ttba, trtv, tubos, nota])
        for k, val in (("reg_pt", rpt), ("reg_tba", rtba), ("reg_rtv", rrtv), ("reg_fo", rfo),
                       ("reg_conf", rconf), ("tomas_pt", tpt), ("tomas_tba", ttba), ("tomas_rtv", trtv),
                       ("tubos", tubos)):
            tot_int[k] += val * n
    s.tablas.append(Tabla("Registros de toma por usuario",
                          ["Tipo", "Uds.", "Usuarios", "Estancias computables", "Reg. pares trenzados",
                           "Reg. coaxial TBA", "Reg. RTV", "Reg. fibra", "Reg. configurable",
                           "Tomas RJ45", "Tomas coax TBA", "Tomas RTV", "Tubos Ø20 / usuario", "Nota"],
                          filas, N.ref("III", "5.13") + "; Anexo II 3.5; Anexo I 3.5",
                          ["TOTAL", n_pau, "", "", tot_int["reg_pt"], tot_int["reg_tba"], tot_int["reg_rtv"],
                           tot_int["reg_fo"], tot_int["reg_conf"], tot_int["tomas_pt"], tot_int["tomas_tba"],
                           tot_int["tomas_rtv"], tot_int["tubos"], ""], col_unidades=2))
    s.add("Tubos de canalización interior Ø20 mm", tot_int["tubos"], "tubos (uno por registro de toma)",
          N.ref("III", "5.12"))
    if op.equipar_todos_registros_pt:
        R.aviso("decision", "Se equipan con BAT los dos registros de pares trenzados de cada estancia principal "
                "(3 tomas en salón y 3 en la segunda estancia principal). La norma exige como mínimo BAT doble en "
                "una estancia además del salón.", N.ref("II", "3.5.1.a"))
    for _, u in usuarios:
        if u.tipo == TipoUsuario.vivienda and len([e for e in u.estancias_computables() if e.principal]) < 2 \
                and res_int[u.id].estancias_computables >= 2:
            R.aviso("info", f"{u.id}: no hay 2 estancias marcadas como principales; se toman 2 de las computables "
                    "(salón y un dormitorio, preferiblemente).", N.ref("III", "5.13.a"))
            break
    for _, u in usuarios:
        if res_int[u.id].nota.startswith("Menos de 2"):
            R.aviso("revisar", f"{u.id}: {res_int[u.id].nota}", N.ref("III", "5.13"))
    R.secciones.append(s)

    # --- 5. Infraestructura -------------------------------------------------
    s = Seccion("infra", "Infraestructura: canalizaciones, recintos y registros")
    a = N.arqueta_entrada(n_pau)
    s.add("Arqueta de entrada (dimensiones interiores mínimas)", str(a.valor), "", a.referencia, a.nota)
    ce = N.canalizacion_externa(n_pau)
    s.add("Canalización externa", f"{ce.valor['tubos']} tubos Ø{ce.valor['diametro_mm']} mm "
          f"({ce.valor['uso']})", "", ce.referencia, ce.nota)
    s.add("Canalización de enlace inferior",
          f"{ce.valor['tubos']} tubos Ø{op.diametro_enlace_inferior_mm} mm", "", N.ref("III", "5.4.1"),
          "Diámetro entre 40 y 63 mm a criterio del proyectista (ocupación máx. 50 %).")
    s.add("Registros de enlace inferior", f"{N.REGISTRO_ENLACE_INFERIOR} en pared; arqueta "
          f"{N.ARQUETA_ENLACE.a}x{N.ARQUETA_ENLACE.b}x{N.ARQUETA_ENLACE.c} mm si es subterránea", "",
          N.ref("III", "5.4.1"), "Cada 30 m empotrada / 50 m en superficie, y en cambios de dirección.")
    s.add("Canalización de enlace superior", f"{N.ENLACE_SUPERIOR['tubos']} tubos Ø{N.ENLACE_SUPERIOR['diametro_mm']} mm",
          "", N.ref("III", "5.4.2"), f"Registros de enlace, si hacen falta: {N.REGISTRO_ENLACE_SUPERIOR}.")

    n_alturas = len([pl for pl in plantas if pl.nivel > 0])
    aticos = [pl for pl in plantas if pl.nivel > 0 and pl.es_atico]
    if aticos and ed.recintos == "RITU":
        if not op.atico_cuenta_como_altura:
            n_alturas -= len(aticos)
        R.aviso("decision", f"El ático {'se cuenta' if op.atico_cuenta_como_altura else 'no se cuenta'} como altura "
                f"para elegir el recinto único: planta baja + {n_alturas} alturas. La norma no define «altura».",
                N.ref("III", "4.5.3"))
    def recinto_adoptado(nombre: str, minimo: N.Regla, alto_libre: Optional[int]) -> None:
        """Con altura libre conocida, se propone el recinto más estrecho que cumple (5.5.1)."""
        if not alto_libre:
            return
        c = N.rit_compacto(minimo.valor, alto_libre)
        if c.valor == minimo.valor:
            return
        s.add(f"{nombre} (dimensiones adoptadas)", str(c.valor), "", c.referencia, c.nota)
        R.aviso("decision", f"{nombre}: se aprovecha la altura libre para estrecharlo a {c.valor.b} mm de ancho "
                f"y {c.valor.a} mm de alto, en lugar de {minimo.valor.b} x {minimo.valor.a} mm. La norma lo permite "
                "manteniendo la superficie accesible y la profundidad.", c.referencia)

    if ed.recintos == "RITU":
        if n_pau <= N.RITU_MAX_PAU and n_alturas <= N.RITU_MAX_ALTURAS:
            r = N.ritu(n_pau, ed.zonas_comunes)
            s.add("RITU (dimensiones mínimas)", str(r.valor), "", r.referencia)
            recinto_adoptado("RITU", r, op.altura_libre_riti_mm)
        elif n_pau <= N.RITU_A_MAX_PAU:
            r = N.ritu_a(n_pau)
            s.add("RITU-A (dimensiones mínimas)", str(r.valor), "", r.referencia,
                  "Recinto único ampliado (Anexo III 4.5.3.ii).")
            recinto_adoptado("RITU-A", r, op.altura_libre_riti_mm)
        else:
            r = N.rit(n_pau)
            R.aviso("revisar", f"Con {n_pau} PAU no se admite recinto único; se dimensionan RITI y RITS.",
                    N.ref("III", "4.5.3"))
            s.add("RITI (dimensiones mínimas)", str(r.valor), "", r.referencia, r.nota)
            s.add("RITS (dimensiones mínimas)", str(r.valor), "", r.referencia, r.nota)
    else:
        r = N.rit(n_pau)
        if op.usar_ritm and n_pau <= N.RITM_MAX_PAU_PISOS:
            s.add("RITI y RITS", "Recintos modulares (RITM)", "", N.ref("III", "4.5.4"),
                  "Armarios modulares no propagadores de la llama (hasta 45 PAU).")
        elif op.usar_ritm:
            R.aviso("revisar", "Se pidió RITM pero hay más de 45 PAU: no se admite.", N.ref("III", "4.5.4"))
        # Las dimensiones de 5.5.1 son para todos los recintos, también los modulares
        s.add("RITI (dimensiones mínimas)", str(r.valor), "", r.referencia, r.nota)
        recinto_adoptado("RITI", r, op.altura_libre_riti_mm)
        s.add("RITS (dimensiones mínimas)", str(r.valor), "", r.referencia,
              "Preferentemente en cubierta y nunca por debajo de la última planta (5.5.3).")
        recinto_adoptado("RITS", r, op.altura_libre_rits_mm)

    for v in verticales:
        pau_v = datos_v[v]["pau"]
        cp = N.canalizacion_principal(pau_v, cobre)
        uso = cp.valor["uso"]
        suf = f" (vertical {v})" if len(verticales) > 1 else ""
        s.add(f"Canalización principal{suf}",
              f"{cp.valor['tubos']} tubos Ø{cp.valor['diametro_mm']} mm: {uso['RTV']} RTV, {uso['pares']} pares, "
              f"{uso['coaxial']} coaxial, {uso['fibra']} fibra, {uso['reserva']} reserva", "",
              cp.referencia, cp.nota)
        if cp.nota:
            R.aviso("revisar", f"Vertical {v} con {pau_v} PAU: la canalización principal requiere cálculo específico.",
                    cp.referencia)

    n_plantas_rs = len(plantas_con_pau)
    rs = N.registro_secundario(n_pau, max_pau_planta, n_plantas_rs)
    s.add("Registros secundarios de planta (dimensiones)", str(rs.valor), "", rs.referencia,
          f"{rs.nota} Datos: {n_pau} PAU, máx. {max_pau_planta} PAU/planta, {n_plantas_rs} plantas con PAU.")
    filas = []
    total_rs = 0
    total_reg_paso_a = 0
    nivel_min = min(pl.nivel for pl in plantas_con_pau)
    nivel_max = max(pl.nivel for pl in plantas_con_pau)
    usar_reg_paso_auto = op.registro_paso_en_acceso
    for pl in plantas_con_pau:
        for v in verticales:
            us = [u for u in pl.usuarios if u.vertical == v]
            if not us:
                continue
            n = len(us)
            hace_riti = op.riti_hace_registro_secundario and pl.nivel == nivel_min and pl.nivel <= 0
            hace_rits = op.rits_hace_registro_secundario and pl.nivel == nivel_max
            rs_txt = "En RITI" if hace_riti else ("En RITS" if hace_rits else "1")
            if not (hace_riti or hace_rits):
                total_rs += 1
            fib = N.tubos_secundaria(n, f"pares_fibra_{op.acometida_secundaria}").valor
            ctba = N.tubos_secundaria(n, "coaxial_TBA").valor
            crtv = N.tubos_secundaria(n, "coaxial_RTV").valor
            fmt = lambda t: f"{t['tubos']}xØ{t['diametro_mm']}"
            if usar_reg_paso_auto is None:
                necesita_a = n > N.SIN_REGISTRO_PASO_MAX_VIV_PLANTA
            else:
                necesita_a = usar_reg_paso_auto
            reg_a = n if necesita_a else 0
            total_reg_paso_a += reg_a
            filas.append([pl.nombre, v, n, rs_txt, fmt(fib), fmt(ctba), fmt(crtv), reg_a])
    s.tablas.append(Tabla("Registros secundarios y canalización secundaria (tramos comunitarios)",
                          ["Planta", "Vertical", "PAU", "Registro secundario", "Tubos pares trenzados + fibra",
                           "Tubos coaxial TBA", "Tubos coaxial RTV", "Registros de paso tipo A"],
                          filas, N.ref("III", "5.8 y 5.9")))
    s.add("Registros secundarios de planta", total_rs, "uds.", N.ref("III", "5.8.a"),
          "Más los de cambio de dirección y cada 30 m (450x450x150 mm), según planos.")
    s.add("Acceso a cada usuario", f"{N.ACCESO_VIVIENDA['tubos']} tubos Ø{N.ACCESO_VIVIENDA['diametro_mm']} mm "
          f"({N.ACCESO_VIVIENDA['uso']})", "", N.ref("III", "5.9"))
    s.add("Registros de paso tipo A en derivaciones", total_reg_paso_a, "uds.", N.ref("III", "5.9 y 5.10"),
          "Se pueden omitir con menos de 6 viviendas por planta si el tramo no supera 15 m."
          if total_reg_paso_a == 0 else "")
    if total_reg_paso_a == 0:
        R.aviso("decision", "Sin registros de paso en el acceso a viviendas: comprobar en planos que ningún tramo "
                "registro secundario–RTR supera 15 m.", N.ref("III", "5.9"))
    s.add("Registros de paso en canalización interior", "Tipo B (pares trenzados) y C (coaxial)", "",
          N.ref("III", "5.10"), "Cada 15 m y en cambios de dirección de radio < 120 mm; cantidad según planos.")

    n_rtr = sum(1 for _, u in usuarios if not (u.tipo in (TipoUsuario.local, TipoUsuario.oficina)
                                             and not u.distribucion_definida))
    desc, dims = N.RTR_OPCIONES[op.opcion_rtr]
    s.add("Registros de terminación de red (RTR)", n_rtr, "uds.", N.ref("III", "5.11"),
          f"Opción {op.opcion_rtr}: {desc}, {dims}. Entre 200 y 2.300 mm del suelo, con 2 bases de enchufe.")
    if ed.ascensores:
        s.add("Canalización a cuarto de máquinas de ascensor",
              f"{ed.ascensores} x tubo Ø{N.ASCENSOR_TUBO_DIAM_MM} mm con hilo guía desde el {rit_inf}, "
              "terminado en registro de toma con tapa ciega", "", N.ref("II", "3.1.5"))
    R.secciones.append(s)

    # --- 6. Instalaciones de los recintos -----------------------------------
    s = Seccion("recintos", "Instalaciones de los recintos")
    if rit_inf == "RITU":
        # Anexo III 5.5.5: «dos canalizaciones hasta el RITI, o hasta el RITU en los casos en que proceda,
        # y una hasta el RITS». Sin RITS no dice qué pasa con la tercera: se lleva también al RITU.
        s.add("Canalizaciones desde centralización de contadores", "3 tubos Ø32 mm al RITU",
              "", N.ref("III", "5.5.5"), "Espacio para 2 contadores de operadores en la centralización.")
        R.aviso("decision", "Con recinto único se llevan 3 tubos Ø32 mm desde la centralización de contadores al "
                "RITU: los 2 que pide la norma y el que iría al RITS.", N.ref("III", "5.5.5"))
    else:
        s.add("Canalizaciones desde centralización de contadores", "2 tubos Ø32 mm al RITI y 1 tubo Ø32 mm al RITS",
              "", N.ref("III", "5.5.5"), "Espacio para 2 contadores de operadores en la centralización.")
    s.add("Línea desde el Cuadro de Servicios Generales a cada recinto", "Cu 450/750 V, 2x6+T mm² en tubo Ø32 mm",
          "", N.ref("III", "5.5.5"))
    s.add("Cuadro de protección de cada recinto",
          "IGA 25 A (4,5 kA), ID 25 A/30 mA, MT 10 A alumbrado, MT 16 A tomas; en RITS además MT 16 A cabecera RTV",
          "", N.ref("III", "5.5.5"), "Previsión de ampliación del 50 %. IP 4X + IK 05.")
    s.add("Bases de enchufe por recinto", "2 x 16 A con toma de tierra (2x2,5+T mm²)", "", N.ref("III", "5.5.5"))
    s.add("Alumbrado", "300 lux medios + alumbrado de emergencia", "", N.ref("III", "5.5.6"))
    s.add("Ventilación", "Renovación total del aire al menos 2 veces por hora", "", N.ref("III", "5.5.4"))
    s.add("Puerta", "Metálica, 180x80 cm (acceso lateral), apertura hacia fuera, cerradura con llave común", "",
          N.ref("III", "5.5"))
    s.add("Toma de tierra", "Anillo de Cu ≥ 25 mm² con barra colectora; resistencia del sistema ≤ 10 Ω", "",
          N.ref("III", "7.1"))
    s.add("Placa de identificación", "200x200 mm, resistente al fuego, entre 1.200 y 1.800 mm de altura", "",
          N.ref("III", "5.5.7"))
    R.secciones.append(s)

    R.datos = {"n_pau": n_pau, "cobre": cobre, "verticales": datos_v, "demanda": dem,
               "interior": {k: vars(v) for k, v in res_int.items()}, "registros_secundarios": total_rs}
    return R
