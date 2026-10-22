"""Pliego de condiciones del proyecto de ICT (Orden ITC/1644/2011, anexo I, apartado 3).

Según el anexo I, el pliego describe los materiales (aquí, los de fabricante prescrito, con sus cifras del
catálogo) y las condiciones que no están en las Normas o son más estrictas; lo demás es de obligado
cumplimiento por las propias Normas, y se cita su apartado. Las normas generales (3.2) salen de
docs/normativa/normas_generales.json, comprobado en el BOE: título y vigencia oficiales.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from . import catalogo as C
from . import normativa as N
from .dimensionado import Resultado
from .documento import DocumentoAJP, Plantilla
from .memoria import _Res, fecha_texto
from .modelo import Proyecto

NORMAS_GENERALES = Path(__file__).resolve().parent.parent / "docs" / "normativa" / "normas_generales.json"


def _normas() -> dict:
    if NORMAS_GENERALES.exists():
        return json.loads(NORMAS_GENERALES.read_text(encoding="utf-8"))["normas"]
    return {}


def _cita(normas: dict, clave: str) -> str:
    n = normas.get(clave)
    if not n:
        return f"[A VERIFICAR: norma «{clave}» no comprobada en el BOE]"
    return n["titulo"] + ("" if n["vigente"] else " [A VERIFICAR: derogada]")


def _m(v: Optional[float], unidad: str = "") -> str:
    if v is None:
        return "—"
    s = f"{v:g}".replace(".", ",")
    return f"{s} {unidad}".strip()


def generar_pliego(p: Proyecto, res: Resultado, ruta: str | Path, plantilla: Optional[Plantilla] = None,
                   fecha: Optional[dt.date] = None, indice: Optional[list] = None) -> tuple[Path, list]:
    plantilla = plantilla or Plantilla.cargar()
    fecha = fecha or dt.date.today()
    dg = p.datos_generales
    R = _Res(res)
    normas = _normas()
    cat = C.cargar(p.rtv.fabricante)
    emplazamiento = ", ".join(x for x in (dg.direccion, dg.municipio, dg.provincia) if x) or "[A COMPLETAR]"
    d = DocumentoAJP(plantilla, " · ".join(x for x in (f"Proyecto ICT {dg.numero}".strip(), dg.direccion) if x))
    pr = plantilla.datos.get("proyectista", {})
    d.portada("Proyecto técnico de infraestructura común de telecomunicaciones",
              dg.titulo or "Pliego de condiciones", [
                  ("Expediente", dg.numero or "[A COMPLETAR]"), ("Emplazamiento", emplazamiento),
                  ("Promotor", dg.promotor or "[A COMPLETAR: promotor]"),
                  ("Proyectista", " · ".join(x for x in (pr.get("nombre"), pr.get("titulacion")) if x) or "[A COMPLETAR]"),
                  ("Documento", "3. Pliego de condiciones")], fecha_texto(fecha))
    d.indice(indice)

    d.titulo("3. Pliego de condiciones", 1)
    d.parrafo("Los materiales y su instalación cumplirán las Normas técnicas anexas al Reglamento regulador de las "
              "infraestructuras comunes de telecomunicaciones (Real Decreto 346/2011), de obligado cumplimiento. En "
              "este pliego se prescriben los productos concretos elegidos en el proyecto, con sus características "
              "según las fichas técnicas del fabricante, y las condiciones particulares que no recogen las Normas o "
              "que son más estrictas (" + "Orden ITC/1644/2011, anexo I, apartado 3). El instalador podrá emplear "
              "productos equivalentes de otro fabricante siempre que igualen o mejoren estas características y se "
              "compruebe que se siguen cumpliendo los niveles en toma de la memoria.")

    # ---------------------------------------------------------------- 3.1 Condiciones particulares
    d.titulo("3.1 Condiciones particulares", 2)
    d.titulo("3.1.A Radiodifusión sonora y televisión", 3)
    d.parrafo("a) Condicionantes de acceso a los sistemas de captación.", bold=True)
    d.parrafo("La accesibilidad a los elementos de captación estará garantizada en cualquier situación "
              f"({N.ref('I', '3.1')}), así como al espacio reservado en cubierta para las antenas de satélite "
              f"({N.ref('I', '3.6')}). Los mástiles se fijarán a elementos de fábrica resistentes y accesibles, "
              f"alejados de chimeneas u otros obstáculos ({N.ref('I', '4.2.1')}). [PENDIENTE: acceso a la cubierta "
              "(escotilla o similar) en los planos del arquitecto]")
    d.parrafo("b) Características de los sistemas de captación.", bold=True)
    d.tabla(["Referencia", "Elemento", "Banda (MHz)", "Ganancia (dBi)", "Ficha"],
            [[a["ref"], a["nombre"], a.get("margen_mhz") or "", _m(a["ganancia_dbi"]),
              "Ficha oficial del fabricante"] for a in cat["antenas"]])
    d.vinetas([
        "Antenas y elementos anexos (soportes, anclajes, riostras) de materiales resistentes a la corrosión o "
        f"tratados ({N.ref('I', '4.2.1')}).",
        "Mástiles diseñados para impedir o dificultar la entrada de agua y garantizar la evacuación de la que se "
        "recoja; altura máxima de 6 m (para alturas superiores, torretas); a 5 m como mínimo del obstáculo o mástil "
        "más próximo y a 1,5 veces su longitud de líneas eléctricas.",
        "Mástiles conectados a la toma de tierra del edificio por el camino más corto con cable de 25 mm² de "
        "sección mínima.",
        "Resistencia al viento de 130 km/h para sistemas a menos de 20 m del suelo y de 150 km/h por encima.",
        "Cables de conexión de tipo intemperie o protegidos adecuadamente."])
    d.parrafo("c) Características de los elementos activos.", bold=True)
    d.tabla(["Referencia", "Elemento", "Bandas", "Ganancia (dB)", "Nivel de salida EN 50083 (dBµV)",
             "Figura de ruido máx. (dB)", "Consumo (mA)"],
            [[a["ref"], a["nombre"], " / ".join(a["bandas"]), " / ".join(_m(x) for x in a["ganancia_db"]),
              " / ".join(_m(x) for x in a["nivel_salida_en50083_dbuv"]), _m(a.get("figura_ruido_max_db")),
              _m(a["corriente_ma"])] for a in cat["amplificadores"]])
    f = cat["fuentes"][0] if cat["fuentes"] else None
    if f:
        d.parrafo(f"Fuente de alimentación {f['ref']}: {_m(f['tension_v'], 'V')}, {_m(f['corriente_a'], 'A')}.")
    d.parrafo("Los equipos conectados directamente a la antena incorporarán los filtros necesarios para cumplir la "
              "inmunidad de la norma EN 50083-2 en 47-862 MHz. La diferencia de nivel a la salida de la cabecera entre "
              "canales de la misma naturaleza no será superior a 3 dB. A la salida de la cabecera: impedancia 75 Ω, "
              "pérdida de retorno ≥ 10 dB (≥ 6 dB en equipos con mezcla tipo «Z») y nivel máximo de trabajo de "
              f"113 dBµV en digital en la banda de 47-862 MHz y 110 dBµV en 950-2.150 MHz ({N.ref('I', '4.3')}).")
    s_tdt = _niveles_cabecera(R)
    if s_tdt:
        d.parrafo(f"Nivel de salida de cabecera de proyecto: {s_tdt}. Todos por debajo del máximo de 113 dBµV.")
    d.parrafo("d) Características de los elementos pasivos.", bold=True)
    usados = {fila[2] for fila in (R.tabla("rtv", "Red de distribución").filas if R.tabla("rtv", "Red de distribución")
                                   else [])} | {fila[3] for fila in (R.tabla("rtv", "Red de distribución").filas
                                                                      if R.tabla("rtv", "Red de distribución") else [])}
    filas = []
    for dv in cat["derivadores"]:
        if dv["ref"] in usados:
            filas.append([dv["ref"], dv["nombre"], _m(dv["derivacion_db"]["terr"]), _m(dv["derivacion_db"]["sat"]),
                          _m(dv["paso_db"]["terr"]) if dv["paso_db"] else "terminal",
                          _m(dv["paso_db"]["sat"]) if dv["paso_db"] else "terminal"])
    for rp in cat["repartidores"]:
        if rp["ref"] in usados or rp["ref"] == "519502":
            filas.append([rp["ref"], rp["nombre"], _m(rp["perdida_db"]["terr"]), _m(rp["perdida_db"]["sat"]), "—", "—"])
    d.tabla(["Referencia", "Elemento", "Derivación/reparto TV (dB)", "Derivación/reparto SAT (dB)",
             "Paso TV (dB)", "Paso SAT (dB)"], filas)
    toma = next((t for t in cat["tomas"] if t["ref"] == "527601"), None)
    cable = cat["cables"][0] if cat["cables"] else None
    if toma:
        d.parrafo(f"Tomas: {toma['ref']} {toma['nombre']}, atenuación {_m(toma['atenuacion_db'].get('TV'), 'dB')} "
                  f"en TV y {_m(toma['atenuacion_db'].get('SAT'), 'dB')} en SAT.")
    if cable:
        a = cable["atenuacion_db_m"]
        d.parrafo(f"Cable coaxial: {cable['ref']} {cable['nombre']}. Atenuación según ficha: "
                  + ", ".join(f"{_m(a[k] * 100)} dB/100 m a {k} MHz" for k in ("200", "500", "698", "862", "2150")
                              if k in a) + ".")
        d.parrafo("Los cables cumplirán " + N.ref("I", "5") + ": conductor central de cobre y dieléctrico de "
                  "polietileno celular físico; pantalla de cinta metalizada y trenza de cobre o aluminio; cubierta no "
                  "propagadora de la llama en interiores y de polietileno en exteriores; impedancia característica "
                  "media de 75 ± 3 Ω. Con atenuación a 800 MHz de hasta 18 dB/100 m, como el prescrito, la pérdida de "
                  "retorno será de al menos 23 dB (5-470 MHz), 20 dB (470-862 MHz) y 18 dB (862-2.150 MHz).")

    d.titulo("3.1.B Distribución de los servicios de telefonía disponible al público (STDP) y de banda ancha (TBA)", 3)
    d.parrafo("a) Redes de cables de pares trenzados.", bold=True)
    d.vinetas([
        "Cables: de 4 pares de cobre con aislamiento individual, sin apantallar, clase E (categoría 6), conformes "
        f"a UNE-EN 50288-6-1 ({N.ref('II', '5.1.1.a')}); en la red interior de usuario, además, UNE-EN 50288-6-2 "
        f"y cubierta no propagadora de la llama, libre de halógenos y de baja emisión de humos ({N.ref('II', '5.1.2.a')}).",
        f"Elementos de conexión (paneles, rosetas y conectores) según {N.ref('II', '5.2.1')}; bases de acceso de "
        "terminal con conectores hembra RJ45 de ocho vías.",
        "No hay elementos activos en esta red."])
    d.parrafo("b) Redes de cables coaxiales.", bold=True)
    d.vinetas([
        f"Cables de los tipos RG-6, RG-11 o RG-59 conformes a UNE-EN 50117-2-1 y UNE-EN 50117-2-2 ({N.ref('II', '5.1.1.c')}): "
        "impedancia media 75 Ω; conductor central de acero recubierto de cobre; dieléctrico de polietileno celular "
        "físico; cinta de aluminio-poliéster-aluminio; malla de aluminio con recubrimiento superior al 75 %; cubierta "
        "de PVC no propagadora de la llama. Atenuación máxima a 862 MHz: 13,5 dB/100 m (RG-11), 20 dB/100 m (RG-6) "
        "y 24,5 dB/100 m (RG-59); apantallamiento clase A.",
        f"Red interior de usuario con cable RG-59 ({N.ref('II', '5.1.2.b')}).",
        f"Elementos pasivos, cargas, conectores, distribuidores y bases de acceso de terminal según {N.ref('II', '5.2.3')}."])
    d.parrafo("c) Redes de cables de fibra óptica.", bold=True)
    d.vinetas([
        f"Fibras monomodo G.657 categoría A2 o B3, compatibles con G.652.D ({N.ref('II', '5.1.1.d')}).",
        "Cables multifibra dieléctricos, con cubierta termoplástica libre de halógenos, retardante a la llama y de "
        "baja emisión de humos; acometidas individuales interiores de 2 fibras (verde y roja), de unos 4 mm de "
        "diámetro y radio de curvatura mínimo de 2 cm.",
        f"Caja de interconexión, cajas de segregación, rosetas y conectores según {N.ref('II', '5.2.4')}. Las tapas de "
        f"cajas y rosetas llevarán las marcas de seguridad láser de la norma UNE-EN 60825-1 ({N.ref('II', '7.1')}).",
        "Empalmes de fibra: [A VERIFICAR: método (fusión o conectorizado) que elija el instalador; su pérdida entra "
        "en el límite de atenuación del cuadro de medidas]."])

    d.titulo("3.1.C Infraestructuras de Hogar Digital", 3)
    d.parrafo("No se incluyen en el proyecto.")

    d.titulo("3.1.D Infraestructura", 3)
    d.parrafo("a) Condicionantes para su ubicación.", bold=True)
    d.parrafo("Los recintos estarán en zona comunitaria; el inferior, a ser posible sobre la rasante, y el superior "
              "nunca por debajo de la última planta. Se evitará que queden en la proyección vertical de canalizaciones "
              f"o desagües y se garantizará su protección frente a la humedad ({N.ref('III', '5.5.3')}). La "
              "canalización de telecomunicación se separará de las de otros servicios 100 mm en trazados paralelos "
              f"y 30 mm en cruces ({N.ref('III', '8')}).")
    if p.edificio.ascensores and p.opciones.exigir_distancia_maquinaria_ascensor:
        d.parrafo("Condición particular: el motor y el armario de maniobra del ascensor se situarán a 2 m como mínimo "
                  f"de los recintos de instalaciones de telecomunicación ({N.ref('III', '5.5.3')}).")
    d.parrafo("La arqueta de entrada y la canalización externa son exclusivas de la ICT: no se compartirán con otros "
              f"servicios (baja tensión, alumbrado, agua...) ({N.ref('III', '8')}). Arqueta de entrada de "
              f"{R.valor('infra', 'Arqueta de entrada')} ({N.ref('III', '5.1')}); canalización externa de "
              f"{R.valor('infra', 'Canalización externa')}, lo más rectilínea posible, con arquetas de paso de "
              f"400 × 400 × 400 mm cada 50 m y en los cambios de dirección ({N.ref('III', '5.2')}). Su ubicación "
              "definitiva se confirmará con la consulta a los operadores en el replanteo.")
    d.parrafo("b) Características de las arquetas.", bold=True)
    d.parrafo(f"Arqueta de entrada de {R.valor('infra', 'Arqueta de entrada')}. Soportará las sobrecargas "
              "normalizadas y el empuje del terreno; tapa conforme a UNE-EN 124 clase B 125 (rotura superior a 125 kN), "
              "IP 55, cierre de seguridad y dos puntos de tendido a 150 mm del fondo que soporten 5 kN; en la tapa "
              f"figurarán las siglas ICT ({N.ref('III', '6.1')}).")
    d.parrafo("c) Características de las canalizaciones.", bold=True)
    d.tabla(["Característica", "Montaje superficial", "Montaje empotrado", "Montaje enterrado"], [
        ["Resistencia a la compresión", "≥ 1.250 N", "≥ 320 N", "≥ 450 N"],
        ["Resistencia al impacto", "≥ 2 J", "≥ 1 J (R = 320 N); ≥ 2 J (R > 320 N)", "Normal"],
        ["Temperatura de instalación y servicio", "-5 °C a 60 °C", "-5 °C a 60 °C", "No declarada"],
        ["Resistencia a la propagación de la llama", "No propagador", "No propagador", "No declarada"]])
    d.nota(f"Tubos conformes a UNE-EN 50086 o UNE-EN 61386 ({N.ref('III', '6.2.1')}).")
    d.vinetas([
        "Todos los tubos llevarán hilo guía (alambre de acero galvanizado de 2 mm o cuerda plástica de 5 mm), que "
        "sobresaldrá 200 mm en los extremos y permanecerá tras las ocupaciones (no metálico en tubos ocupados).",
        "Los tubos de las canalizaciones externa, de enlace y principal serán de pared interior lisa.",
        f"Canalizaciones del proyecto: externa {R.valor('infra', 'Canalización externa')}; enlace inferior "
        f"{R.valor('infra', 'Canalización de enlace inferior')}; enlace superior "
        f"{R.valor('infra', 'Canalización de enlace superior')}; principal {R.valor('infra', 'Canalización principal')}; "
        f"acceso a cada vivienda {R.valor('infra', 'Acceso a cada usuario')}."])
    d.parrafo("d) Distribución interior de los recintos e instalación de los equipos.", bold=True)
    d.parrafo("Los recintos tendrán espacios delimitados en planta para cada servicio, con bandejas o canales en todo "
              f"el perímetro interior a 300 mm del techo ({N.ref('III', '5.5')}). Puerta metálica de 180 × 80 cm "
              "como mínimo, de apertura hacia el exterior, con cerradura de llave común. Instalaciones eléctricas, "
              "alumbrado, ventilación y toma de tierra según la memoria (apartado 1.2.E).")
    d.parrafo("e) Características de los registros.", bold=True)
    d.tabla(["Registro", "Protección", "Referencia"], [
        ["Registros de enlace", "IP 3X / IK 7 en interior; IP 55 / IK 10 en exterior", N.ref("III", "6.3")],
        ["Registros principales", "IP 3X / IK 7 en interior; IP 55 / IK 10 en exterior", N.ref("III", "6.5")],
        ["Registros secundarios", "IP 3X / IK 7; tapa EI 30 si la canalización principal es de obra; cerradura con llave",
         N.ref("III", "6.6")],
        ["Registros de paso, terminación de red y toma", "IP 33 / IK 5, con tapa", N.ref("III", "6.7")]])

    # ---------------------------------------------------------------- 3.1.E Cuadros de medidas
    d.titulo("3.1.E Cuadros de medidas", 3)
    d.parrafo("a) Medidas en las tomas de radiodifusión sonora y televisión (47-694 MHz y 950-2.150 MHz).", bold=True)
    d.tabla(["Parámetro", "Unidad", "47-694 MHz", "950-2.150 MHz"], [
        ["Nivel COFDM-TV (TDT)", "dBµV", "47-70", "47-70"], ["Nivel FM radio", "dBµV", "40-70", "40-70"],
        ["Nivel DAB radio", "dBµV", "30-70", "30-70"], ["Nivel QPSK-TV (satélite)", "dBµV", "47-77", "47-77"],
        ["C/N COFDM-TV", "dB", "≥ 25", "≥ 25"], ["C/N COFDM-DAB", "dB", "≥ 18", "≥ 18"], ["C/N FM radio", "dB", "≥ 38", "≥ 38"],
        ["MER COFDM-TV", "dB", "≥ 21 en toma", "≥ 21 en toma"],
        ["MER COFDM-256QAM TV (DVB-T2)", "dB", "≥ 22 en toma", "≥ 22 en toma"],
        ["BER COFDM-TV", "", "9 × 10⁻⁵", "9 × 10⁻⁵"],
        ["Respuesta amplitud/frecuencia en banda de la red", "dB", "≤ 16", "≤ 20"]])
    d.nota(f"Referencia: {N.ref('I', '4.4.3 y 4.5')}. Las especificaciones de la banda de 470-862 MHz se entienden "
           "referidas a 470-694 MHz (Real Decreto 391/2019, disposición final 4.ª).")
    t = R.tabla("rtv", "Red de distribución")
    if t:
        d.parrafo("Valores de proyecto en cada vivienda (TDT), que el instalador comprobará en el protocolo de pruebas:")
        d.tabla(["Vivienda", "Derivador", "PAU", "Nivel peor toma (dBµV)", "Nivel mejor toma (dBµV)"],
                [[f[1], f[2], f[3], f[7], f[8]] for f in t.filas])
    d.parrafo("b) Medidas de las redes de telefonía disponible al público y de banda ancha.", bold=True)
    d.tabla(["Red", "Medida", "Valor exigido", "Referencia"], [
        ["Pares trenzados (distribución, dispersión e interior)", "Certificación del cableado",
         "Categoría 6 / clase E según UNE-EN 50346", N.ref("II", "6.2 y 6.7")],
        ["Cables coaxiales (estrella)", "Continuidad, identificación de ramas y atenuación",
         "≤ 20 dB entre el registro principal coaxial y el PAU más alejado (86-860 MHz)", N.ref("II", "6.4.1")],
        ["Fibra óptica", "Continuidad e identificación a 1.310, 1.490 y 1.550 nm",
         "Atenuación recomendada ≤ 1,55 dB; máxima 2 dB, del registro principal óptico al PAU", N.ref("II", "6.6")]])

    d.titulo("3.1.F Utilización de elementos no comunes del edificio", 3)
    d.parrafo("La ICT discurre por zonas comunes. [A VERIFICAR: que no se utilicen elementos no comunes; si los hubiera, "
              "se describirán y se determinarán sus servidumbres (Orden ITC/1644/2011, art. 2)]")
    d.titulo("3.1.G Estimación de los residuos generados por la instalación de la ICT", 3)
    d.parrafo(f"Conforme al {_cita(normas, 'rd_105_2008')}. [PENDIENTE: estimación de cantidades a partir de las "
              "mediciones del presupuesto (envases de cartón y plástico, recortes de tubo y cable, restos de obra de "
              "las rozas y registros)]")

    # ---------------------------------------------------------------- 3.2 Condiciones generales
    d.titulo("3.2 Condiciones generales", 2)
    d.titulo("3.2.A Reglamento de ICT y Normas anexas", 3)
    d.vinetas([_cita(normas, k) for k in ("rdl_1_1998", "rd_346_2011", "orden_itc_1644_2011", "orden_ece_983_2019")]
              + ["Real Decreto 250/2025, de 25 de marzo, por el que se aprueba el Plan Técnico Nacional de la Televisión "
                 "Digital Terrestre", _cita(normas, "rd_842_2002") + " (instalaciones eléctricas de los recintos)"])
    d.titulo("3.2.B Normativa sobre prevención de riesgos laborales", 3)
    d.vinetas([_cita(normas, k) for k in ("ley_31_1995", "rd_39_1997", "rd_1627_1997", "rd_485_1997", "rd_486_1997",
                                          "rd_487_1997", "rd_773_1997", "rd_1215_1997", "rd_614_2001")])
    d.parrafo("Actividades y tareas para la ejecución y el mantenimiento de la ICT, para la evaluación de riesgos del "
              "estudio (básico) de seguridad y salud de la obra:")
    d.tabla(["Fase", "Actividad o tarea", "Riesgos principales a evaluar"], [
        ["Ejecución", "Excavación de zanja y arqueta de entrada; canalización externa", "Caídas al mismo y a distinto nivel, golpes, sobreesfuerzos"],
        ["Ejecución", "Rozas y recibido de tubos, registros y cajas", "Proyección de partículas, polvo, ruido, cortes"],
        ["Ejecución", "Construcción y equipamiento de los recintos; cuadro eléctrico y toma de tierra", "Contacto eléctrico, caídas"],
        ["Ejecución", "Tendido y conexionado de cables en verticales y patinillos", "Caídas a distinto nivel, cortes, sobreesfuerzos"],
        ["Ejecución", "Manipulación y empalme de fibra óptica", "Radiación láser (ojos), pinchazos con restos de fibra"],
        ["Ejecución y mantenimiento", "Montaje y mantenimiento de mástil y antenas en cubierta", "Caídas a distinto nivel desde la cubierta, viento, contacto eléctrico, descargas atmosféricas"],
        ["Ejecución y mantenimiento", "Acceso a la cubierta por la escotilla o el medio previsto", "Caídas a distinto nivel"],
        ["Mantenimiento", "Revisión de cabecera, registros y recintos", "Contacto eléctrico, golpes"]])
    d.parrafo("Las medidas de protección para los trabajos en la cubierta (acceso y puntos de anclaje para los equipos "
              "de protección individual) deben mantenerse de forma permanente para el mantenimiento posterior "
              "(Orden ITC/1644/2011, anexo I, 3.2.B). [PENDIENTE: definir con el arquitecto el acceso a la cubierta y "
              "los puntos de anclaje]")
    d.titulo("3.2.C Normativa sobre protección contra campos electromagnéticos", 3)
    d.vinetas([_cita(normas, "rd_1066_2001"), _cita(normas, "rd_186_2016") + ". Sustituye al Real Decreto 1580/2006 que "
               "citan las Normas anexas al Reglamento, hoy derogado."])
    d.titulo("3.2.D Secreto de las comunicaciones", 3)
    d.parrafo("Los registros y recintos permanecerán cerrados con llave, en poder de la propiedad o de quien esta delegue, "
              "y cada operador accederá solo a sus elementos. Los operadores garantizarán el secreto de las "
              "comunicaciones hasta el punto de terminación de red (Real Decreto 346/2011, art. 5.1), conforme a la "
              f"{_cita(normas, 'ley_11_2022')}, que sustituye a la Ley 32/2003 que cita la Orden ITC/1644/2011.")
    d.titulo("3.2.E Normativa sobre gestión de residuos", 3)
    d.vinetas([_cita(normas, "rd_105_2008"), _cita(normas, "ley_7_2022")])
    d.titulo("3.2.F Normativa en materia de protección contra incendios", 3)
    d.parrafo("Todos los materiales prescritos cumplen la normativa vigente en materia de protección contra incendios. "
              "En los pasos de canalizaciones a través de elementos de compartimentación se mantendrá su resistencia "
              f"al fuego, según el apartado SI 1-3 del documento básico DB SI ({N.ref('II', '7.3')}), en coordinación "
              f"con el proyecto de edificación. Normativa: {_cita(normas, 'rd_314_2006')} (Código Técnico de la "
              f"Edificación, DB SI) y {_cita(normas, 'orden_ece_983_2019')}.")
    d.parrafo(f"Todos los cables de la ICT (coaxiales de radiodifusión y televisión y de banda ancha, de pares, de "
              f"pares trenzados y de fibra óptica) tendrán como mínimo la clase de reacción al fuego "
              f"{N.CLASE_FUEGO_CABLES_ICT}, con marcado conforme a la norma UNE-EN 50575 ({N.REF_ECE_983}). Si "
              "comparten canalización o conducto con cables de otro tipo (por ejemplo, eléctricos), todo el conjunto "
              "cumplirá los requisitos de la legislación más estricta (nota de la tabla 1). " + _clase_cable(cat))
    d.firma(fecha_texto(fecha))
    return d.guardar(ruta), d.titulos


def _clase_cable(cat: dict) -> str:
    """Comprueba la euroclase del cable coaxial prescrito (dato de su ficha) frente al mínimo de la Orden."""
    cab = cat["cables"][0] if cat.get("cables") else None
    if not cab:
        return ""
    clase = cab.get("euroclase", "")
    if N.cumple_clase_fuego(clase):
        return f"El cable coaxial prescrito ({cab['ref']}) es de euroclase {clase} según su ficha: cumple."
    return (f"[A VERIFICAR: que la euroclase del cable {cab['ref']} ({clase or 'sin dato'}) es igual o superior a "
            f"{N.CLASE_FUEGO_CABLES_ICT}]")


def _niveles_cabecera(R: _Res) -> str:
    t = R.tabla("rtv", "Niveles y calidad en toma")
    if not t:
        return ""
    return ", ".join(f"{f[0]} {str(f[2]).replace('.', ',')} dBµV" for f in t.filas)
