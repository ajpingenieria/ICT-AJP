"""Memoria del proyecto técnico de ICT (Orden ITC/1644/2011, anexo I, apartado 1).

Sigue la estructura obligatoria del anexo I (1.1 Datos generales; 1.2.A a 1.2.F) y se rellena con los
resultados del dimensionado. Lo que falta por calcular o por confirmar sale marcado como
«[PENDIENTE: ...]» o «[A VERIFICAR: ...]», resaltado, para que nada se dé por resuelto sin estarlo.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from . import normativa as N
from .dimensionado import Partida, Resultado, Tabla
from .documento import DocumentoAJP, Plantilla
from .modelo import Proyecto, TipoUsuario

ORDEN = "Orden ITC/1644/2011"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def fecha_texto(d: dt.date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


_ACENTOS = {"SALON": "salón", "VESTIBULO": "vestíbulo", "BANO": "baño", "COMUN": "común", "ATICO": "ático",
            "HABITACION": "habitación", "ZAGUAN": "zaguán"}


def _bonito(nombre: str) -> str:
    """«SALON-COMEDOR» -> «salón-comedor»; «DORM. 1» -> «dormitorio»."""
    import re
    import unicodedata

    def palabra(m):
        w = m.group(0)
        k = "".join(c for c in unicodedata.normalize("NFKD", w.upper()) if not unicodedata.combining(c))
        return _ACENTOS.get(k, w.lower())
    return re.sub(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", palabra, nombre)


def _dependencias(u) -> str:
    """Resumen de dependencias: «salón-comedor, cocina, 3 dormitorios, 2 baños, vestíbulo, paso»."""
    import re
    from collections import Counter
    cuenta: Counter = Counter()
    for e in u.estancias:
        if e.tipo.value == "dormitorio":
            cuenta["dormitorio"] += 1
        elif e.tipo.value == "bano":
            cuenta["baño"] += 1
        else:
            cuenta[re.sub(r"\s*\d+$", "", _bonito(e.nombre))] += 1
    partes = []
    for k, n in cuenta.items():
        if n == 1:
            partes.append(k)
        else:
            plural = k + ("es" if k.endswith(("n", "r", "l")) and not k.endswith("ón") else "s")
            partes.append(f"{n} {plural}")
    return ", ".join(partes)


def _m2(v) -> str:
    return f"{v:.2f}".replace(".", ",") if v else ""


class _Res:
    """Acceso cómodo a partidas y tablas del resultado."""

    def __init__(self, r: Resultado):
        self.r = r

    def partida(self, seccion: str, concepto: str) -> Optional[Partida]:
        try:
            return next(p for p in self.r.seccion(seccion).partidas if p.concepto.startswith(concepto))
        except StopIteration:
            return None

    def valor(self, seccion: str, concepto: str, defecto: str = "[PENDIENTE: dato no calculado]") -> str:
        p = self.partida(seccion, concepto)
        return str(p.valor) if p else defecto

    def tabla(self, seccion: str, titulo: str) -> Optional[Tabla]:
        return next((t for t in self.r.seccion(seccion).tablas if t.titulo.startswith(titulo)), None)


def _tabla_resultado(d: DocumentoAJP, t: Optional[Tabla], col_cumple: Optional[int] = None,
                     excluir: Optional[list[str]] = None) -> None:
    if t is None:
        d.parrafo("[PENDIENTE: tabla no disponible en el cálculo]")
        return
    if excluir:
        quedan = [j for j, c in enumerate(t.cabeceras) if c not in excluir]
        t = Tabla(t.titulo, [t.cabeceras[j] for j in quedan], [[f[j] for j in quedan] for f in t.filas],
                  t.referencia)
    filas = [list(f) for f in t.filas]
    if t.fila_total:
        # los totales del Excel son fórmulas: aquí se suman en Python
        tot = []
        for j, v in enumerate(t.fila_total):
            if isinstance(v, (int, float)) and j > 0:
                if t.col_unidades and j != t.col_unidades - 1:
                    tot.append(sum(f[t.col_unidades - 1] * f[j] for f in t.filas if isinstance(f[j], (int, float))))
                else:
                    tot.append(sum(f[j] for f in t.filas if isinstance(f[j], (int, float))))
            else:
                tot.append(v)
        filas.append(tot)
    d.tabla(t.cabeceras, filas, col_cumple=col_cumple)
    if t.referencia:
        d.nota(f"Referencia: {t.referencia}.")


def _tabla_partidas(d: DocumentoAJP, partidas: list[Optional[Partida]]) -> None:
    filas = [[p.concepto, f"{p.valor} {p.unidad}".strip() if isinstance(p.valor, (int, float)) else p.valor,
              p.referencia] for p in partidas if p]
    d.tabla(["Elemento", "Proyecto", "Referencia"], filas)


def generar_memoria(p: Proyecto, res: Resultado, ruta: str | Path, plantilla: Optional[Plantilla] = None,
                    fecha: Optional[dt.date] = None, indice: Optional[list] = None) -> tuple[Path, list]:
    plantilla = plantilla or Plantilla.cargar()
    fecha = fecha or dt.date.today()
    dg, ed = p.datos_generales, p.edificio
    R = _Res(res)
    emplazamiento = ", ".join(x for x in (dg.direccion, dg.municipio, dg.provincia) if x) or "[A COMPLETAR: emplazamiento]"
    titulo = dg.titulo or "Proyecto técnico de infraestructura común de telecomunicaciones"
    pie = " · ".join(x for x in (f"Proyecto ICT {dg.numero}".strip(), dg.direccion) if x)
    d = DocumentoAJP(plantilla, pie)
    pr = plantilla.datos.get("proyectista", {})

    # --- Portada e índice -------------------------------------------------------------
    d.portada("Proyecto técnico de infraestructura común de telecomunicaciones", titulo, [
        ("Expediente", dg.numero or "[A COMPLETAR]"),
        ("Emplazamiento", emplazamiento),
        ("Promotor", dg.promotor or "[A COMPLETAR: promotor]"),
        ("Referencia catastral", dg.referencia_catastral or "[A COMPLETAR]"),
        ("Proyectista", " · ".join(x for x in (pr.get("nombre"), pr.get("titulacion"),
                                               f"col. n.º {pr['colegiado']} {pr.get('colegio', '')}".strip()
                                               if pr.get("colegiado") else None) if x) or "[A COMPLETAR]"),
        ("Documento", "1. Memoria"),
    ], fecha_texto(fecha))
    d.indice(indice)

    # --- 1.1 Datos generales ---------------------------------------------------------
    d.titulo("1. Memoria", 1)
    d.titulo("1.1 Datos generales", 2)
    d.titulo("1.1.A Datos del promotor", 3)
    d.tabla(["Concepto", "Dato"], [
        ["Promotor", dg.promotor or "[A COMPLETAR: nombre o razón social]"],
        ["Emplazamiento de la edificación", emplazamiento],
        ["Referencia catastral", dg.referencia_catastral or "[A COMPLETAR]"]])

    d.titulo("1.1.B Descripción del edificio", 3)
    plantas = sorted(ed.plantas, key=lambda x: x.nivel)
    n_viv = sum(1 for _, u in ed.usuarios() if u.tipo == TipoUsuario.vivienda)
    n_loc = sum(1 for _, u in ed.usuarios() if u.tipo in (TipoUsuario.local, TipoUsuario.oficina))
    sobre = [pl for pl in plantas if pl.nivel > 0]
    portal = "un único portal" if len(ed.verticales) == 1 else f"{len(ed.verticales)} verticales [A VERIFICAR: portales]"
    d.parrafo(f"Se trata de un edificio de uso residencial con {portal}, planta baja y "
              f"{len(sobre)} plantas sobre rasante ({', '.join(pl.nombre.lower() for pl in sobre)}). Alberga "
              f"{n_viv} viviendas" + (f" y {n_loc} locales u oficinas" if n_loc else ", sin locales comerciales ni "
                                     "oficinas")
              + ((f", y dispone de {ed.ascensores} ascensor" + ("es" if ed.ascensores > 1 else ""))
                 if ed.ascensores else ", sin ascensor") + ".")
    if ed.otras_dependencias:
        d.parrafo(ed.otras_dependencias)
    grupos: dict[str, list] = {}
    for pl in plantas:
        for u in pl.usuarios:
            grupos.setdefault(u.tipologia or u.id, []).append(u)
    filas = []
    for tip, us in grupos.items():
        u = us[0]
        filas.append([tip, ", ".join(x.id for x in us), len(u.estancias_computables()), _dependencias(u),
                      _m2(u.superficie_util_m2)])
    d.tabla(["Tipología", "Viviendas", "Estancias (sin baños ni trasteros)", "Dependencias", "Sup. útil (m²)"],
            filas, anchos_cm=[1.8, 3.0, 2.2, 6.6, 2.0])

    d.titulo("1.1.C Aplicación de la Ley de Propiedad Horizontal", 3)
    if ed.propiedad_horizontal:
        d.parrafo("La edificación se acogerá al régimen de propiedad horizontal regulado por la Ley 49/1960, de 21 de "
                  "julio, sobre Propiedad Horizontal, por lo que le son de aplicación las normas del Reglamento "
                  "regulador de las infraestructuras comunes de telecomunicaciones (Real Decreto 346/2011, de 11 de "
                  "marzo, art. 3.1). La infraestructura común de telecomunicaciones tendrá la consideración de elemento "
                  "común de la edificación a los efectos del artículo 5 de dicha ley (Real Decreto 346/2011, art. 2.3).")
    else:
        d.parrafo("[A VERIFICAR: régimen de propiedad horizontal de la edificación (Ley 49/1960)]. "
                  "El Reglamento se aplica a los edificios acogidos, o que deban acogerse, a dicho régimen "
                  "(Real Decreto 346/2011, art. 3.1).")

    d.titulo("1.1.D Objeto del proyecto técnico", 3)
    d.parrafo("El presente proyecto técnico tiene por objeto definir la infraestructura común de telecomunicaciones "
              "(ICT) de la edificación descrita, conforme al Real Decreto-ley 1/1998, de 27 de febrero, sobre "
              "infraestructuras comunes en los edificios para el acceso a los servicios de telecomunicación, al "
              "Reglamento aprobado por el Real Decreto 346/2011, de 11 de marzo, y a la Orden ITC/1644/2011, de 10 de "
              "junio, que establece el contenido y la estructura de este documento. La ICT proyectada cumple las "
              "funciones del artículo 2.1 del Reglamento:")
    d.vinetas(["Captación, adaptación y distribución hasta las tomas de usuario de las señales de radiodifusión "
               "sonora y televisión terrestres, y previsión para las procedentes de satélite.",
               "Acceso a los servicios de telefonía disponible al público y de banda ancha mediante redes de cables "
               "de pares trenzados, cables coaxiales y fibra óptica, desde las redes de los operadores hasta cada "
               "vivienda, y la canalización que les sirve de soporte."])

    # --- 1.2 Elementos de la ICT ------------------------------------------------------
    d.titulo("1.2 Elementos que constituyen la infraestructura común de telecomunicación", 2)
    _rtv(d, p, R)
    _satelite(d, p, R)
    _tba(d, p, R)
    d.titulo("1.2.D Infraestructuras de Hogar Digital", 3)
    d.parrafo("El proyecto no incluye instalaciones de Hogar Digital (anexo V del Reglamento).")
    _infraestructura(d, p, R)
    d.titulo("1.2.F Varios", 3)
    d.parrafo("Se procurará la máxima independencia entre las instalaciones de telecomunicación y las del resto de "
              "servicios. Las redes de telecomunicación no se alojarán en el mismo compartimento que otros servicios, "
              "y los cruces se harán preferentemente pasando la canalización de telecomunicación por encima, con una "
              "separación mínima de 100 mm en trazados paralelos y de 30 mm en cruces; en la canalización interior "
              "de usuario basta con 30 mm en todos los casos (" + N.ref("III", "8") + ").")
    if ed.ascensores and p.opciones.exigir_distancia_maquinaria_ascensor:
        d.parrafo("Los recintos de instalaciones de telecomunicación se distanciarán un mínimo de 2 m de la "
                  "maquinaria de ascensores (" + N.ref("III", "5.5.3") + "). En consecuencia, se prescribe que el "
                  "motor y el armario de maniobra del ascensor se sitúen a 2 m como mínimo de los recintos; si el "
                  "ascensor elegido no lo permite, deberá comunicarse al proyectista de la ICT antes de su instalación.")
    elif ed.ascensores:
        d.parrafo("Los recintos se separarán al menos 2 m de la maquinaria de ascensores, o se dotarán de protección "
                  "frente a campos electromagnéticos (" + N.ref("III", "5.5.3") + "). [A VERIFICAR: tipo de ascensor y "
                  "posición de su maquinaria respecto a los recintos]")

    d.firma(fecha_texto(fecha))
    return d.guardar(ruta), d.titulos


def _rtv(d: DocumentoAJP, p: Proyecto, R: _Res) -> None:
    d.titulo("1.2.A Captación y distribución de radiodifusión sonora y televisión terrestres", 3)
    d.parrafo("a) Consideraciones sobre el diseño.", bold=True)
    tipo = R.valor("rtv", "Tipo de cabecera")
    d.parrafo("La instalación capta las señales terrestres con antenas para UHF (televisión digital terrestre), banda "
              "III (radio digital DAB) y FM, las amplifica en una cabecera situada en el recinto superior y las "
              "distribuye por una red de dos cables (" + N.ref("I", "3.3") + ") con un derivador por planta en cada "
              "uno, hasta el punto de acceso al usuario (PAU) de cada vivienda. Desde el PAU, un repartidor con una "
              "salida por estancia alimenta las tomas en estrella (" + N.ref("I", "2.3.3 y 3.4") + "). "
              f"Cabecera: {tipo[0].lower() + tipo[1:]}. Los valores de ganancia, pérdidas y atenuación son los del catálogo del "
              "fabricante prescrito (Televés), indicados en el pliego de condiciones.")
    d.parrafo("b) Señales de radiodifusión sonora y televisión terrestres que se reciben en el emplazamiento.", bold=True)
    d.parrafo("Se distribuyen los canales planificados en el área geográfica del emplazamiento según el Plan Técnico "
              f"Nacional de la Televisión Digital Terrestre ({R.valor('rtv', 'Área geográfica')}), con el campo "
              "mínimo de la norma como valor de diseño, que es el caso más desfavorable, al no disponer de medidas en "
              "el emplazamiento (" + N.ref("I", "4.1.5 a 4.1.7") + ").")
    _tabla_resultado(d, R.tabla("rtv", "Canales de TDT"))
    tl = R.partida("rtv", "TDT local")
    if tl:
        d.parrafo(f"Televisión digital local: {tl.valor} ({tl.referencia}). [A VERIFICAR: existencia de prestador "
                  "con título habilitante en la demarcación; sin él no es obligatoria su distribución]")
    d.parrafo("Radio digital (DAB): bloques planificados en la provincia.")
    _tabla_resultado(d, R.tabla("rtv", "Radio digital DAB"), excluir=["Referencia"])
    fm = R.partida("rtv", "Emisoras FM")
    if fm:
        d.parrafo(f"Radio FM: emisoras de gestión indirecta planificadas en la localidad: {fm.valor} MHz "
                  f"({fm.referencia}). {fm.nota}")
    d.parrafo("c) Selección de emplazamiento y parámetros de las antenas receptoras.", bold=True)
    d.parrafo(f"{R.valor('rtv', 'Captación')}. Las antenas se instalarán en la cubierta sobre un mástil de altura no "
              "superior a 6 m, fijado a elementos de fábrica resistentes y accesibles, a una distancia mínima de 5 m "
              "de otros mástiles u obstáculos y de 1,5 veces su longitud a líneas eléctricas, conectado a la toma de "
              "tierra del edificio con cable de 25 mm² como mínimo (" + N.ref("I", "4.2.1") + "). " + _cubierta_txt(p))
    d.parrafo("d) Cálculo de los soportes para la instalación de las antenas receptoras.", bold=True)
    d.parrafo("Las antenas y sus soportes deben resistir vientos de 130 km/h al estar situados a menos de 20 m del "
              "suelo (" + N.ref("I", "4.2.1") + "). [A VERIFICAR: altura final de las antenas sobre el suelo] [PENDIENTE: cálculo del momento flector del mástil con la carga "
              "al viento de las antenas de las fichas del fabricante y las características del mástil prescrito]")
    d.parrafo("e) Plan de frecuencias.", bold=True)
    d.parrafo("Los canales de televisión terrestre se distribuyen en su frecuencia original, sin conversión "
              "(" + N.ref("I", "4.1.4") + "). La banda de 950 a 2.150 MHz queda libre en los dos cables para las "
              "señales de satélite (" + N.ref("I", "4.1.3") + ").")
    d.parrafo("f) Número de tomas.", bold=True)
    d.parrafo(f"Una toma por estancia, excluidos baños y trasteros, con un mínimo de dos por vivienda "
              f"({N.ref('I', '3.5.1')}): {R.valor('rtv', 'Tomas de RTV')} tomas en total.")
    d.parrafo("g) Cálculo de parámetros básicos de la instalación.", bold=True)
    d.parrafo("1) y 2) Derivadores y PAU de cada vivienda, y atenuación desde la cabecera hasta las tomas:")
    _tabla_resultado(d, R.tabla("rtv", "Red de distribución y dispersión"))
    resp = R.partida("rtv", "Respuesta amplitud")
    if resp:
        d.parrafo(f"3) Respuesta amplitud/frecuencia en la banda, en la toma más desfavorable: {resp.valor} "
                  f"({resp.referencia}; {resp.nota.lower()})")
    d.parrafo(f"4) Amplificadores: {R.valor('rtv', 'Cabecera')}, situados en el recinto superior. "
              f"{R.partida('rtv', 'Cabecera').nota if R.partida('rtv', 'Cabecera') else ''}")
    d.parrafo("5) y 6) Niveles de señal en la mejor y en la peor toma y relación señal/ruido en la peor toma:")
    _tabla_resultado(d, R.tabla("rtv", "Niveles y calidad en toma"), col_cumple=8)
    d.parrafo("7) Productos de intermodulación: con amplificación monocanal cada amplificador trabaja con un solo "
              "canal y por debajo de su nivel máximo de salida. [PENDIENTE: cálculo explícito de la relación de "
              "intermodulación (≥ 30 dB, " + N.ref("I", "4.5") + ")]")
    d.parrafo("8) No se instalan amplificadores en la red de distribución.")
    d.parrafo("h) Descripción de los elementos componentes de la instalación.", bold=True)
    d.vinetas([f"Sistemas captadores: {R.valor('rtv', 'Captación')}.",
               f"Amplificadores: {R.valor('rtv', 'Cabecera')}.",
               "Mezcladores: [PENDIENTE: mezclador TV/SAT de cabecera (" + N.ref("I", "3.2") + ")].",
               "Distribuidores, derivadores y PAU: según la tabla de la red de distribución y dispersión.",
               f"Cables y tomas: {R.valor('rtv', 'Tomas y cable')}."])


def _satelite(d: DocumentoAJP, p: Proyecto, R: _Res) -> None:
    d.titulo("1.2.B Distribución de radiodifusión sonora y televisión por satélite", 3)
    d.parrafo("La captación de satélite no forma parte de la instalación inicial. Se reserva en la parte superior "
              "de la edificación espacio físico suficiente libre de obstáculos, con accesibilidad garantizada, para "
              "las antenas y su sujeción (" + N.ref("I", "3.6") + "). " + _reserva_satelite_txt(p))
    d.parrafo("c) Previsión para incorporar las señales de satélite y d) mezcla con las terrestres: las señales se "
              "incorporarán a los dos cables de la red mediante el elemento de mezcla de la cabecera "
              "(" + N.ref("I", "3.2 y 4.1.3") + ").")
    sat = R.partida("rtv", "Previsión de satélite")
    if sat:
        d.parrafo(f"e) Cálculo de parámetros básicos: para que todas las tomas queden entre 47 y 77 dBµV en la banda "
                  f"de 950 a 2.150 MHz, la salida de cabecera de satélite deberá estar {sat.valor} "
                  f"({ORDEN}, anexo I, 1.2.B).")


def _tba(d: DocumentoAJP, p: Proyecto, R: _Res) -> None:
    d.titulo("1.2.C Acceso y distribución de los servicios de telefonía disponible al público (STDP) y de "
             "banda ancha (TBA)", 3)
    d.parrafo("Previsión de la demanda de cada tecnología, que determina las redes de distribución y dispersión "
              "(" + N.ref("II", "3.1") + "):")
    _tabla_resultado(d, R.tabla("demanda", "Demanda por planta"))
    if p.operadores.consulta_realizada is False:
        d.parrafo("La consulta a los operadores (art. 8 del Reglamento) se realizará en el replanteo. El proyecto "
                  "incluye las tres redes; las que ningún operador vaya a utilizar se dejarán canalizadas con hilo "
                  "guía (" + N.ref("II", "3.1.1.b, 3.1.3.b y 3.1.4.b") + ").")
    d.parrafo("a) Redes de cables de pares trenzados.", bold=True)
    _tabla_resultado(d, R.tabla("redes", "Cables de pares trenzados"))
    _tabla_partidas(d, [R.partida("redes", "Cables de 4 pares"), R.partida("redes", "Registro principal de cobre")])
    d.parrafo("[PENDIENTE: cálculo de la atenuación de las redes de distribución y dispersión de pares trenzados "
              "con las longitudes de los planos]")
    d.parrafo("b) Redes de cables coaxiales.", bold=True)
    _tabla_partidas(d, [R.partida("redes", "Red coaxial"), R.partida("redes", "Acometidas coaxiales"),
                        R.partida("redes", "Registro principal coaxial")])
    d.parrafo("[PENDIENTE: cálculo de la atenuación de la red coaxial con las longitudes de los planos]")
    d.parrafo("c) Redes de cables de fibra óptica.", bold=True)
    _tabla_partidas(d, [R.partida("redes", "Red de fibra"), R.partida("redes", "Registro principal óptico")])
    d.parrafo("[PENDIENTE: cálculo de la atenuación de la red de fibra óptica]")
    d.parrafo("Asignación de cables a cada vivienda (para la confección de paneles y regleteros):", bold=True)
    filas, k = [], 0
    for pl in sorted(p.edificio.plantas, key=lambda x: x.nivel):
        for u in pl.usuarios:
            k += 1
            filas.append([pl.nombre, u.id, f"Cable cat. 6 n.º {k}", f"Acometida de fibra n.º {k}",
                          f"Cable coaxial n.º {k}"])
    d.tabla(["Planta", "Vivienda", "Pares trenzados", "Fibra óptica", "Coaxial"], filas)
    d.nota("Numeración correlativa desde el registro principal, de la planta inferior a la superior. Los cables "
           "restantes quedan como reserva e instalaciones comunes.")
    d.parrafo("1.2.C.2 Redes interiores de usuario.", bold=True)
    _tabla_resultado(d, R.tabla("interior", "Registros de toma por usuario"))


def _infraestructura(d: DocumentoAJP, p: Proyecto, R: _Res) -> None:
    d.titulo("1.2.E Canalización e infraestructura de distribución", 3)
    rec = "RITI en planta baja y RITS en planta ático" if p.edificio.recintos == "RITI_RITS" else \
        "recinto único (RITU)"
    d.parrafo(f"a) Consideraciones sobre el esquema general del edificio: la ICT se organiza con {rec}, unidos por la "
              "canalización principal, que discurre junto a la escalera y da servicio a un registro secundario en "
              "cada planta con viviendas. " + ("Su ubicación figura en los planos de planta." if p.planos.base_dxf
                                               else "[PENDIENTE: ubicación de los recintos en los planos]"))
    _tabla_partidas(d, [R.partida("infra", c) for c in (
        "Arqueta de entrada", "Canalización externa", "Registros de enlace inferior", "Canalización de enlace inferior",
        "Canalización de enlace superior")])
    d.parrafo("e) Recintos de instalaciones de telecomunicación.", bold=True)
    _tabla_partidas(d, [x for x in R.r.seccion("infra").partidas if x.concepto.startswith(("RITI", "RITS", "RITU"))]
                    + R.r.seccion("recintos").partidas)
    d.parrafo("f) Registros principales, g) canalización principal y registros secundarios, h) canalización "
              "secundaria y registros de paso, i) registros de terminación de red, j) canalización interior de "
              "usuario y k) registros de toma:", bold=True)
    _tabla_partidas(d, [R.partida("redes", "Registro principal de cobre: salidas"),
                        R.partida("infra", "Canalización principal"),
                        R.partida("infra", "Registros secundarios de planta (dim"),
                        R.partida("infra", "Registros secundarios de planta"),
                        R.partida("infra", "Acceso a cada usuario"),
                        R.partida("infra", "Registros de paso tipo A"),
                        R.partida("infra", "Registros de paso en canalización interior"),
                        R.partida("infra", "Registros de terminación"),
                        R.partida("interior", "Tubos de canalización interior"),
                        R.partida("infra", "Canalización a cuarto de máquinas")])
    _tabla_resultado(d, R.tabla("infra", "Registros secundarios y canalización secundaria"))
    d.parrafo("l) Cuadro resumen de materiales necesarios.", bold=True)
    _materiales(d, p)


def _cubierta_txt(p: Proyecto) -> str:
    """Dónde va el mástil y cómo se accede a la cubierta (datos de los planos del proyecto)."""
    pl = p.planos
    if pl.mastil_xy:
        txt = (f"El mástil se sitúa en {pl.ubicacion_mastil or 'el punto indicado en el plano de la planta cubierta'}, "
               "con un radio de 5 m libre de obstáculos, como figura en el plano de la planta cubierta.")
    else:
        txt = "[PENDIENTE: ubicación del mástil]"
    return txt + (f" Acceso a la cubierta: {pl.acceso_cubierta}." if pl.acceso_cubierta
                  else " [PENDIENTE: acceso a la cubierta]")


def _reserva_satelite_txt(p: Proyecto) -> str:
    pl = p.planos
    if not pl.mastil_xy:
        return "[PENDIENTE: ubicación del espacio reservado y acceso a la cubierta]"
    return ("El espacio reservado, de 1,5 x 1,5 m, está junto al mástil de las antenas terrestres, hacia el interior "
            "de la cubierta, y figura en el plano de la planta cubierta."
            + (f" Acceso: {pl.acceso_cubierta}." if pl.acceso_cubierta else " [PENDIENTE: acceso a la cubierta]"))


def _materiales(d: DocumentoAJP, p: Proyecto) -> None:
    """Cuadro resumen con la medición de los planos de planta (orden «planos --actualizar-longitudes»)."""
    import re
    med = p.planos.materiales
    if not med:
        d.parrafo("[PENDIENTE: medición de tubos y registros a partir de los planos de planta]")
        return
    filas = []
    for clave, cantidad in sorted(med.items(), key=lambda c: (not c[0].startswith("Tubo"), c[0])):
        m = re.match(r"(.*?)\s*\[(m|ud)\]$", clave)
        nombre, unidad = (m.group(1), m.group(2)) if m else (clave, "")
        valor = f"{cantidad:.0f}" if unidad == "ud" else f"{cantidad:.1f}".replace(".", ",")
        filas.append([nombre, valor, unidad])
    d.tabla(["Material", "Cantidad", "Unidad"], filas)
    d.nota("Medición de proyecto sobre los planos de planta: recorridos en «L» más la subida o bajada en cada "
           "extremo; un tubo de la canalización interior por registro de toma; la canalización principal, con la "
           "altura entre plantas. Los registros principales, de enlace y de paso y los recintos, según las tablas "
           "anteriores.")
