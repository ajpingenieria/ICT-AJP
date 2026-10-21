"""Radiodifusión sonora y televisión (Anexo I del Reglamento): señales a distribuir y cabecera.

Primera parte de la v0.2: canales de TDT planificados en el emplazamiento, campo de diseño, tipo de
cabecera admitido y previsión de satélite. El cálculo de niveles toma a toma vendrá con el catálogo
del fabricante (CLAUDE.md, regla 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import normativa as N
from . import plan_radio as PR
from . import plan_tdt as P
from .modelo import Proyecto

if TYPE_CHECKING:
    from .dimensionado import Resultado, Seccion

RESOLUCION_FASE1 = "Resolución SETID de 23/07/2026 (BOE-A-2026-16750)"


def seccion_rtv(p: Proyecto, R: "Resultado", tomas_rtv: int) -> "Seccion":
    from .dimensionado import Seccion, Tabla

    s = Seccion("rtv", "Radiodifusión sonora y televisión")
    dg = p.datos_generales
    mun = P.municipio(dg.municipio, dg.codigo_ine)
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
        _tdt_local(s, R, mun.nombre, a.canales)
    _radio(s, R, dg.provincia, dg.municipio)

    ba = N.admite_banda_ancha(tomas_rtv)
    limite = (f"Menos de {N.TOMAS_MAX_BANDA_ANCHA} tomas: se admite banda ancha." if ba.valor else
              f"{tomas_rtv} tomas: banda ancha solo si garantiza menos de {N.DIF_NIVEL_CABECERA_DB} dB entre canales "
              "de la misma naturaleza.")
    s.add("Tomas de RTV servidas desde la cabecera", tomas_rtv, "tomas", N.ref("I", "3.5"))
    if p.opciones.cabecera_rtv == "monocanal":
        s.add("Tipo de cabecera", "Amplificación monocanal: un amplificador por canal de TDT, más FM y DAB", "",
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
    return s


def _tdt_local(s: "Seccion", R: "Resultado", municipio: str, canales_area: dict[str, int]) -> None:
    dem = PR.demarcacion_tdt_local(municipio)
    if dem is None:
        R.aviso("info", f"{municipio} no pertenece a ninguna demarcación de TDT local.", PR.REF_TDT_LOCAL)
        return
    canal = str(dem.canal) if dem.canal else "pendiente en el plan"
    s.add("TDT local", f"Demarcación {dem.referencia} {dem.denominacion}: canal {canal}", "", PR.REF_TDT_LOCAL,
          "Ámbito: " + ", ".join(dem.ambito) + ".")
    choque = [m for m, c in canales_area.items() if c == dem.canal]
    R.aviso("revisar", f"TDT local {dem.referencia} ({dem.denominacion}): el plan consolidado indica el canal {canal}, "
            "pero el anexo III del Plan Técnico de la TDT de 2019 (RD 391/2019) reasignó canales locales"
            + (f", y el {dem.canal} coincide con el del múltiple {', '.join(choque)} del área" if choque else "")
            + ". Confirmar el canal vigente y si hay prestador con título habilitante: solo entonces es obligatorio "
            "distribuirlo.", f"{PR.REF_TDT_LOCAL}; {N.ref('I', '4.1.6 y 4.1.7')}")


def _radio(s: "Seccion", R: "Resultado", provincia: str, municipio: str) -> None:
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

