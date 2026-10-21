"""Radiodifusión sonora y televisión (Anexo I del Reglamento): señales a distribuir y cabecera.

Primera parte de la v0.2: canales de TDT planificados en el emplazamiento, campo de diseño, tipo de
cabecera admitido y previsión de satélite. El cálculo de niveles toma a toma vendrá con el catálogo
del fabricante (CLAUDE.md, regla 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import normativa as N
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
        R.aviso("revisar", "Faltan por incorporar el múltiple de TDT local de la demarcación (Plan técnico nacional "
                "de la TDT local) y las emisoras de radio FM y DAB con campo suficiente en el emplazamiento.",
                N.ref("I", "4.1.6"))

    ba = N.admite_banda_ancha(tomas_rtv)
    s.add("Tomas de RTV servidas desde la cabecera", tomas_rtv, "tomas", N.ref("I", "3.5"))
    if ba.valor:
        s.add("Tipo de cabecera", "Se admite central o amplificador de banda ancha", "", ba.referencia,
              f"Menos de {N.TOMAS_MAX_BANDA_ANCHA} tomas.")
    else:
        s.add("Tipo de cabecera", "Amplificación monocanal, o central programable que garantice menos de "
              f"{N.DIF_NIVEL_CABECERA_DB} dB entre canales de la misma naturaleza", "", ba.referencia,
              f"{tomas_rtv} tomas: no se admite banda ancha convencional (límite: menos de {N.TOMAS_MAX_BANDA_ANCHA}).")
    if p.rtv.satelite_instalado:
        s.add("Satélite", "Captación instalada", "", N.ref("I", "4.2.2"))
    else:
        s.add("Satélite", "Previsión: espacio libre y accesible en cubierta para las parábolas; red preparada hasta "
              "2.150 MHz", "", f"{N.ref('I', '3.6')}; {N.ref('I', '4.1.2')}",
              "La memoria incluye el cálculo de la previsión (Orden ITC/1644/2011, anexo I, 1.2.B).")
    return s
