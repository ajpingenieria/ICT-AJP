"""Radiodifusión sonora y televisión (Anexo I del Reglamento): señales a distribuir y cabecera.

Primera parte de la v0.2: canales de TDT planificados en el emplazamiento, campo de diseño, tipo de
cabecera admitido y previsión de satélite. El cálculo de niveles toma a toma vendrá con el catálogo
del fabricante (CLAUDE.md, regla 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from . import normativa as N
from . import plan_radio as PR
from . import plan_tdt as P
from .modelo import Proyecto

if TYPE_CHECKING:
    from .dimensionado import Resultado, Seccion

NOMBRE_FABRICANTE = {"televes": "Televés"}
RESOLUCION_FASE1 = "Resolución SETID de 23/07/2026 (BOE-A-2026-16750)"


def seccion_rtv(p: Proyecto, R: "Resultado", tomas_rtv: int,
                tomas_por_usuario: Optional[dict[str, int]] = None) -> "Seccion":
    from .dimensionado import Seccion, Tabla

    s = Seccion("rtv", "Radiodifusión sonora y televisión")
    dg = p.datos_generales
    mun = P.municipio(dg.municipio, dg.codigo_ine)
    campos_tdt: list[tuple[float, float]] = []
    canales_cabecera = 0
    if mun is None:
        n = len(P.buscar_municipios(dg.municipio, dg.codigo_ine))
        R.aviso("revisar", (f"El municipio «{dg.municipio}» aparece {n} veces en el Plan Técnico de la TDT: indicar "
                            "su código INE." if n > 1 else f"No se encuentra el municipio «{dg.municipio or '(vacío)'}» "
                            "en el Plan Técnico de la TDT: revisar el nombre o indicar el código INE."), P.REFERENCIA)
    else:
        a = mun.area
        s.add("Área geográfica del Plan Técnico de la TDT", f"n.º {a.numero} {a.nombre}", "",
              P.REFERENCIA_PLAN + ", anexo I", f"{mun.nombre} (INE {mun.ine}).")
        filas = []
        medidos = p.rtv.campos_medidos_dbuvm
        for mux, canal in a.canales.items():
            f = P.frecuencia_central_mhz(canal)
            emin = N.campo_minimo_tdt(f).valor
            campo = medidos.get(str(canal))
            filas.append([mux, canal, f, emin, campo if campo is not None else emin,
                          "medido" if campo is not None else "mínimo de la norma",
                          "DVB-T2 (UHD) desde el 05/11/2026" if mux == "RGE2" else "DVB-T"])
            campos_tdt.append((f, campo if campo is not None else emin))
        canales_cabecera = len(a.canales)
        s.tablas.append(Tabla("Canales de TDT a distribuir", ["Múltiple", "Canal", "Frecuencia central (MHz)",
                                                               "Campo mínimo norma (dBµV/m)",
                                                               "Campo de diseño (dBµV/m)", "Origen",
                                                               "Transmisión"],
                              sorted(filas, key=lambda f: f[1]), P.REFERENCIA_PLAN + ", anexo II; " + N.ref("I", "4.1.6")))
        if not medidos:
            R.aviso("decision", "Campo de TDT de diseño: el mínimo de la norma (3 + 20 log f) en cada canal, como caso "
                    "más desfavorable, al no haber medidas en el emplazamiento.", N.ref("I", "4.1.6"))
        R.aviso("info", "El múltiple RGE2 pasa a DVB-T2 en ultra alta definición el 05/11/2026 (fase 1). La cabecera "
                "y la red deben ser transparentes a la modulación; la calidad en toma se comprueba con el MER de "
                "COFDM-256QAM (≥ 22 dB en toma).", f"{RESOLUCION_FASE1}; {N.ref('I', '4.5')}")
        local = _tdt_local(s, R, mun.nombre, a.canales)
        if local:
            f = P.frecuencia_central_mhz(local)
            campos_tdt.append((f, p.rtv.campos_medidos_dbuvm.get(str(local), N.campo_minimo_tdt(f).valor)))
            canales_cabecera += 1
    bloques, fm = _radio(s, R, dg.provincia, dg.municipio)

    ba = N.admite_banda_ancha(tomas_rtv)
    limite = (f"Menos de {N.TOMAS_MAX_BANDA_ANCHA} tomas: se admite banda ancha." if ba.valor else
              f"{tomas_rtv} tomas: banda ancha solo si garantiza menos de {N.DIF_NIVEL_CABECERA_DB} dB entre canales "
              "de la misma naturaleza.")
    s.add("Tomas de RTV servidas desde la cabecera", tomas_rtv, "tomas", N.ref("I", "3.5"))
    if p.opciones.cabecera_rtv == "monocanal":
        s.add("Tipo de cabecera", "Amplificación monocanal: un amplificador por canal de TDT, más uno de FM y DAB", "",
              ba.referencia, limite)
        R.aviso("decision", "Cabecera con amplificadores monocanal: cumple siempre la diferencia de nivel de menos de "
                f"{N.DIF_NIVEL_CABECERA_DB} dB entre canales, con cualquier número de tomas.", ba.referencia)
    else:
        s.add("Tipo de cabecera", "Central programable", "", ba.referencia, limite)
        if not ba.valor:
            R.aviso("revisar", "Central programable con 30 tomas o más: comprobar que su ficha garantiza menos de "
                    f"{N.DIF_NIVEL_CABECERA_DB} dB entre canales de la misma naturaleza.", ba.referencia)
    if p.rtv.satelite_instalado:
        s.add("Satélite", "Captación instalada", "", N.ref("I", "4.2.2"))
    else:
        s.add("Satélite", "Previsión: espacio libre y accesible en cubierta para las parábolas; red preparada hasta "
              "2.150 MHz", "", f"{N.ref('I', '3.6')}; {N.ref('I', '4.1.2')}",
              "La memoria incluye el cálculo de la previsión (Orden ITC/1644/2011, anexo I, 1.2.B).")
    if tomas_por_usuario and campos_tdt and p.opciones.cabecera_rtv == "monocanal":
        _niveles(s, R, p, tomas_por_usuario, campos_tdt, bloques, fm, canales_cabecera)
    elif tomas_por_usuario and campos_tdt:
        R.aviso("revisar", "El cálculo de niveles toma a toma solo está programado para cabecera monocanal.",
                N.ref("I", "4.5"))
    return s


def _niveles(s: "Seccion", R: "Resultado", p: Proyecto, tomas: dict[str, int], campos_tdt, bloques, fm,
             canales_tdt: int) -> None:
    from .dimensionado import Tabla
    from . import rtv_niveles as RN

    rtv = p.rtv
    arriba = p.edificio.recintos == "RITI_RITS"        # cabecera en el RITS; con RITU, abajo
    plantas = []
    for pl in sorted(p.edificio.plantas, key=lambda x: x.nivel, reverse=arriba):
        vivs = [(u.id, tomas[u.id]) for u in pl.usuarios if tomas.get(u.id)]
        if vivs:
            plantas.append((pl.nombre, vivs))
    if not plantas:
        return
    campos = {"TDT": campos_tdt,
              "FM": [(f, N.CAMPO_MINIMO_FM_ESTEREO[rtv.entorno_fm]) for f, _ in fm] or
                    [(87.5, N.CAMPO_MINIMO_FM_ESTEREO[rtv.entorno_fm])],
              "DAB": [((b.f_min_mhz + b.f_max_mhz) / 2, N.CAMPO_MINIMO_DAB) for b in bloques] or
                     [(195.0, N.CAMPO_MINIMO_DAB)]}
    geo = RN.Geometria(rtv.long_antena_cabecera_m, rtv.long_cabecera_primer_derivador_m, rtv.altura_entre_plantas_m,
                       rtv.long_acometida_min_m, rtv.long_acometida_max_m, rtv.long_interior_min_m,
                       rtv.long_interior_max_m)
    try:
        r = RN.calcular(plantas, campos, geo, canales_tdt=canales_tdt)
    except ValueError as ex:
        R.aviso("revisar", f"No se pueden calcular los niveles de RTV: {ex}", N.ref("I", "4.5"))
        return
    ref_cat = f"Catálogo {NOMBRE_FABRICANTE.get(rtv.fabricante, rtv.fabricante)} (fichas oficiales)"
    s.tablas.append(Tabla("Red de distribución y dispersión de RTV", [
        "Planta", "Vivienda", "Derivador (cada cable)", "PAU", "Tomas", "Atenuación TDT mejor toma (dB)",
        "Atenuación TDT peor toma (dB)", "Nivel TDT peor toma (dBµV)", "Nivel TDT mejor toma (dBµV)"],
        [[v.planta, v.vivienda, v.derivador, v.pau, v.tomas, v.atenuacion["TDT"][0], v.atenuacion["TDT"][1],
          round(r.salida_elegida["TDT"] - v.atenuacion["TDT"][1], 1),
          round(r.salida_elegida["TDT"] - v.atenuacion["TDT"][0], 1)] for v in r.viviendas],
        f"{N.ref('I', '2.3, 3.3, 3.4 y 4.5')}; {ref_cat}"))
    filas = []
    for serv, (lo, hi) in RN.NIVEL_TOMA.items():
        if serv == "SAT":
            continue
        filas.append([serv, r.entrada_amplificador[serv], r.salida_elegida[serv], r.niveles_toma[serv][0],
                      r.niveles_toma[serv][1], f"{lo}-{hi}", r.cn_toma[serv], f"≥ {RN.CN_MIN[serv]}",
                      "Cumple" if r.cumple[serv] else "NO CUMPLE"])
    s.tablas.append(Tabla("Niveles y calidad en toma", [
        "Servicio", "Entrada amplificador (dBµV)", "Salida cabecera (dBµV)", "Nivel peor toma (dBµV)",
        "Nivel mejor toma (dBµV)", "Margen norma (dBµV)", "C/N (dB)", "C/N norma (dB)", "Resultado"],
        filas, f"{N.ref('I', '4.5')}; {ref_cat}"))
    sat_lo, sat_hi = r.salida_cabecera["SAT"]
    s.add("Previsión de satélite: salida de cabecera necesaria (950-2150 MHz)",
          f"entre {sat_lo:.1f} y {sat_hi:.1f} dBµV".replace(".", ","), "", "Orden ITC/1644/2011, anexo I, 1.2.B",
          "Con ese nivel todas las tomas quedan entre 47 y 77 dBµV (QPSK).")
    s.add("Respuesta amplitud/frecuencia en banda (peor toma)",
          f"{r.respuesta_banda['terr']} dB (47-694 MHz), {r.respuesta_banda['sat']} dB (950-2150 MHz)".replace(".", ","), "",
          N.ref("I", "4.4.3"), "Límite: 16 dB y 20 dB.")
    s.add("Cabecera", f"{canales_tdt} amplificadores monocanal UHF {RN.Material.amp_uhf}, 1 amplificador FM/DAB "
          f"{RN.Material.amp_fm_dab} y fuente {RN.Material.fuente}", "", ref_cat,
          f"Consumo {r.consumo_ma:,.0f} mA de 2.500 mA de la fuente.".replace(",", "."))
    s.add("Captación", f"Antena UHF {RN.Material.antena_uhf} (modo pasivo), FM {RN.Material.antena_fm} y DAB "
          f"{RN.Material.antena_dab}", "", ref_cat)
    s.add("Tomas y cable", f"Toma {RN.Material.toma}; cable {RN.Material.cable}", "", ref_cat)
    if not rtv.longitudes_medidas:
        n = lambda x: f"{x:g}".replace(".", ",")   # noqa: E731
        R.aviso("decision", "Niveles de RTV calculados con longitudes estimadas: antena-cabecera "
                f"{n(rtv.long_antena_cabecera_m)} m, {n(rtv.altura_entre_plantas_m)} m entre plantas, acometida "
                f"{n(rtv.long_acometida_min_m)}-{n(rtv.long_acometida_max_m)} m e interior "
                f"{n(rtv.long_interior_min_m)}-{n(rtv.long_interior_max_m)} m. Recalcular con las medidas de los planos.",
                N.ref("I", "4.5"))
    for clave, ok in r.cumple.items():
        if not ok:
            R.aviso("revisar", f"RTV: no se cumple «{clave}» con el material y las longitudes actuales.", N.ref("I", "4.5"))
    margen = r.niveles_toma["TDT"][0] - RN.NIVEL_TOMA["TDT"][0]
    if 0 <= margen < 3:
        R.aviso("info", f"TDT: la peor toma queda solo {margen:.1f} dB por encima del mínimo de 47 dBµV con el campo "
                "mínimo de la norma. Con medidas reales o la antena en modo activo habrá más margen.", N.ref("I", "4.5"))


def _tdt_local(s: "Seccion", R: "Resultado", municipio: str, canales_area: dict[str, int]) -> Optional[int]:
    """Añade la TDT local y devuelve su canal (si está planificado y no coincide con uno del área)."""
    dem = PR.demarcacion_tdt_local(municipio)
    if dem is None:
        R.aviso("info", f"{municipio} no pertenece a ninguna demarcación de TDT local.", PR.REF_TDT_LOCAL)
        return None
    canal = str(dem.canal) if dem.canal else "pendiente en el plan"
    ref = PR.REF_TDT_LOCAL + (f"; {PR.REF_CAMBIO_LOCAL}" if dem.canal_anterior else "")
    nota = "Ámbito: " + ", ".join(dem.ambito) + "."
    if dem.canal_anterior:
        nota += f" Canal cambiado del {dem.canal_anterior} al {dem.canal} por el segundo dividendo digital."
    s.add("TDT local", f"Demarcación {dem.referencia} {dem.denominacion}: canal {canal}", "", ref, nota)
    choque = [m for m, c in canales_area.items() if c == dem.canal]
    if choque:
        R.aviso("revisar", f"TDT local {dem.referencia}: el canal {dem.canal} coincide con el del múltiple "
                f"{', '.join(choque)} del área geográfica.", ref)
    R.aviso("revisar", f"TDT local {dem.referencia} ({dem.denominacion}, canal {canal}): solo es obligatorio "
            "distribuirla si hay un prestador con título habilitante en la demarcación. Confirmarlo; mientras tanto "
            "se prevé su amplificador en cabecera.", f"{ref}; {N.ref('I', '4.1.6 y 4.1.7')}")
    return dem.canal if dem.canal and not choque else None


def _radio(s: "Seccion", R: "Resultado", provincia: str, municipio: str) -> tuple[list, list]:
    from .dimensionado import Tabla

    bloques = PR.bloques_dab(provincia) if provincia else []
    if bloques:
        s.tablas.append(Tabla("Radio digital DAB planificada", ["Red", "Bloque", "Desde (MHz)", "Hasta (MHz)",
                                                                "Referencia"],
                              [[b.red, b.bloque, b.f_min_mhz, b.f_max_mhz, b.referencia] for b in bloques],
                              PR.REF_DAB))
        R.aviso("info", "Radio digital (DAB): se distribuyen los bloques planificados con campo superior a 58 dBµV/m "
                "en el emplazamiento; la cabecera amplifica la banda III de DAB.", N.ref("I", "4.1.6"))
    else:
        R.aviso("revisar", f"No se encuentran bloques DAB para la provincia «{provincia or '(vacía)'}».", PR.REF_DAB)
    fm = PR.emisoras_fm(municipio)
    if fm:
        s.add("Emisoras FM planificadas (gestión indirecta)",
              ", ".join(f"{f:.1f}".replace(".", ",") + (" [EX]" if ex else "") for f, ex in fm), "MHz", PR.REF_FM,
              "[EX]: disponible para concesión, puede no estar emitiendo. Las emisoras públicas (RNE, autonómicas y "
              "municipales) no figuran en este anexo: la cabecera amplifica toda la banda de FM (87,5-108 MHz).")
    return bloques, fm

