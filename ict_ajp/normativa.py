"""Tablas y reglas de dimensionado del Reglamento ICT.

Fuente: Real Decreto 346/2011, de 11 de marzo, texto consolidado del BOE
(BOE-A-2011-5834), que incluye las modificaciones de la Orden ECE/983/2019,
el RD 391/2019, el RD 805/2014 y el RD 250/2025. Copia de referencia en
docs/normativa/RD_346_2011_consolidado.md.

Cada función devuelve el valor y la referencia exacta del apartado, para que
cualquier cifra del proyecto se pueda trazar hasta la norma.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

RD = "RD 346/2011"


def ref(anexo: str, apartado: str) -> str:
    return f"{RD}, Anexo {anexo}, ap. {apartado}"


@dataclass(frozen=True)
class Dim:
    """Dimensiones en mm, en el orden que indica la norma para cada elemento."""

    a: int
    b: int
    c: int
    orden: str = "alto x ancho x fondo"

    def __str__(self) -> str:
        return f"{self.a} x {self.b} x {self.c} mm ({self.orden})"


@dataclass(frozen=True)
class Regla:
    valor: object
    referencia: str
    nota: str = ""


# ---------------------------------------------------------------------------
# Anexo III. Infraestructura
# ---------------------------------------------------------------------------

def arqueta_entrada(n_pau: int) -> Regla:
    orden = "largo x ancho x profundidad"
    if n_pau <= 20:
        d = Dim(400, 400, 600, orden)
    elif n_pau <= 100:
        d = Dim(600, 600, 800, orden)
    else:
        d = Dim(800, 700, 820, orden)
    return Regla(d, ref("III", "5.1"),
                 "Ubicación según la consulta a operadores (art. 8).")


def canalizacion_externa(n_pau: int) -> Regla:
    if n_pau <= 4:
        n, uso = 3, "2 TBA+STDP, 1 reserva"
    elif n_pau <= 20:
        n, uso = 4, "2 TBA+STDP, 2 reserva"
    elif n_pau <= 40:
        n, uso = 5, "3 TBA+STDP, 2 reserva"
    else:
        n, uso = 6, "4 TBA+STDP, 2 reserva"
    return Regla({"tubos": n, "diametro_mm": 63, "uso": uso}, ref("III", "5.2"),
                 "Arquetas de paso de 400x400x400 mm cada 50 m y en cambios de dirección.")


ENLACE_INFERIOR_DIAM_MIN = 40
ENLACE_INFERIOR_DIAM_MAX = 63
REGISTRO_ENLACE_INFERIOR = Dim(450, 450, 120)
ARQUETA_ENLACE = Dim(400, 400, 400, "largo x ancho x profundidad")
REGISTRO_ENLACE_SUPERIOR = Dim(360, 360, 120)
ENLACE_SUPERIOR = {"tubos": 2, "diametro_mm": 40}


def rit(n_pau: int) -> Regla:
    """Dimensiones mínimas de RITI y RITS (ap. 5.5.1)."""
    if n_pau <= 20:
        d = Dim(2000, 1000, 500)
    elif n_pau <= 45:
        d = Dim(2000, 1500, 500)
    elif n_pau <= 74:
        d = Dim(2300, 2000, 1000)
    else:
        d = Dim(2300, 2000, 2000)
    return Regla(d, ref("III", "5.5.1"),
                 "Ancho y alto modificables si se mantienen superficie accesible y profundidad.")


def ritu(n_pau: int, zonas_comunes: bool) -> Regla:
    if n_pau <= 5:
        d = Dim(1000, 1000, 500) if zonas_comunes else Dim(1000, 500, 300)
    elif n_pau <= 16:
        d = Dim(2000, 1000, 500)
    elif n_pau <= 30:
        d = Dim(2000, 1500, 1000)
    else:
        d = Dim(2000, 2000, 1500)
    return Regla(d, ref("III", "5.5.1"))


def ritu_a(n_pau: int) -> Regla:
    if n_pau <= 20:
        d = Dim(2000, 2000, 500)
    else:
        d = Dim(2000, 3000, 500)
    return Regla(d, ref("III", "5.5.1"))


PUERTA_RIT_LATERAL_MM = (1800, 800)   # alto x ancho mínimos, acceso lateral (Anexo III, ap. 5.5)


def rit_compacto(minimo: Dim, alto_libre_mm: int) -> Regla:
    """Recinto que ocupa menos planta cumpliendo 5.5.1 con la altura libre disponible.

    Ap. 5.5.1: «las dimensiones de anchura y altura de los recintos podrán ser modificadas a criterio
    del proyectista, siempre que la superficie accesible y la profundidad mínima se mantengan». Se
    aprovecha la altura libre para estrechar el recinto, sin bajar del ancho de la puerta de acceso
    lateral (80 cm, ap. 5.5), que tampoco permite alturas por debajo de 1,80 m.
    """
    alto_puerta, ancho_puerta = PUERTA_RIT_LATERAL_MM
    if alto_libre_mm < alto_puerta:
        return Regla(minimo, ref("III", "5.5.1"),
                     f"Altura libre {alto_libre_mm} mm menor que la puerta mínima de {alto_puerta} mm (ap. 5.5).")
    superficie = minimo.a * minimo.b
    ancho = max(ancho_puerta, math.ceil(superficie / alto_libre_mm / 10) * 10)
    alto = max(alto_puerta, math.ceil(superficie / ancho / 10) * 10)
    return Regla(Dim(alto, ancho, minimo.c), ref("III", "5.5.1"),
                 f"Superficie frontal {superficie / 1e6:.2f}".replace(".", ",")
                 + f" m² y fondo {minimo.c} mm mantenidos; altura libre disponible {alto_libre_mm} mm.")


RITU_MAX_PAU = 16          # Anexo III, ap. 4.5.3.i (y hasta PB + 3 alturas)
RITU_MAX_ALTURAS = 3
RITU_A_MAX_PAU = 30        # Anexo III, ap. 4.5.3.ii
RITM_MAX_PAU_PISOS = 45    # Anexo III, ap. 4.5.4


def canalizacion_principal(n_pau: int, cobre: str = "pares_trenzados") -> Regla:
    """Tubos de 50 mm de la canalización principal (ap. 5.7.1)."""
    if n_pau <= 10:
        uso = {"RTV": 1, "pares": 1, "coaxial": 1, "fibra": 1, "reserva": 1}
        nota = ""
    elif n_pau <= 20:
        uso = {"RTV": 1, "pares": 1, "coaxial": 2, "fibra": 1, "reserva": 1}
        nota = ""
    elif n_pau <= 30:
        uso = {"RTV": 1, "pares": 2, "coaxial": 1, "fibra": 1, "reserva": 2}
        nota = ""
    else:
        pares = math.ceil(n_pau / 20) if cobre == "pares_trenzados" else 2
        uso = {"RTV": 1, "pares": pares, "coaxial": 1, "fibra": 1,
               "reserva": max(3, math.ceil(n_pau / 15))}
        nota = ("Más de 30 PAU: cálculo específico en el proyecto (varias verticales o "
                "solución coordinada con arquitectura). Se dan las capacidades mínimas.")
    return Regla({"tubos": sum(uso.values()), "diametro_mm": 50, "uso": uso},
                 ref("III", "5.7.1"), nota)


MAX_USUARIOS_POR_PLANTA_Y_VERTICAL = 8  # ap. 5.7


def registro_secundario(n_pau_total: int, max_pau_planta: int, n_plantas: int) -> Regla:
    """Dimensiones del registro secundario de planta (ap. 5.8, casos a)."""
    caso1 = (max_pau_planta <= 3 and n_pau_total <= 20) or (max_pau_planta <= 4 and n_plantas <= 5)
    if n_pau_total > 30:
        d, motivo = Dim(550, 1000, 150), "más de 30 PAU"
    elif caso1:
        d, motivo = Dim(450, 450, 150), "≤3 PAU/planta y ≤20 PAU, o ≤4 PAU/planta y ≤5 plantas"
    else:
        d, motivo = Dim(500, 700, 150), "21 a 30 PAU, o ≤20 PAU superando los límites del caso 1º"
    return Regla(d, ref("III", "5.8"), f"Caso aplicado: {motivo}.")


REGISTRO_SECUNDARIO_PASO = Dim(450, 450, 150)  # casos b) y c): cambios de dirección y cada 30 m

# Canalización secundaria: diámetro -> nº máximo de PAU atendidos (ap. 5.9)
TABLA_SECUNDARIA = {
    "pares_fibra_interior": {25: 3, 32: 6, 40: 8},
    "pares_fibra_exterior": {25: 2, 32: 4, 40: 6},
    "coaxial_TBA": {25: 2, 32: 6, 40: 8},
    "coaxial_RTV": {25: 2, 32: 6, 40: 8},
}


def tubos_secundaria(n_pau: int, servicio: str) -> Regla:
    """Tubos necesarios en un tramo comunitario de canalización secundaria."""
    tabla = TABLA_SECUNDARIA[servicio]
    cap_max = max(tabla.values())
    k = max(1, math.ceil(n_pau / cap_max))
    por_tubo = math.ceil(n_pau / k) if n_pau else 0
    diam = min(d for d, cap in tabla.items() if cap >= por_tubo)
    return Regla({"tubos": k, "diametro_mm": diam}, ref("III", "5.9"))


ACCESO_VIVIENDA = {"tubos": 3, "diametro_mm": 25,
                   "uso": "pares trenzados + fibra, coaxial TBA, coaxial RTV"}
SIN_REGISTRO_PASO_MAX_VIV_PLANTA = 5   # "inferior a seis"
SIN_REGISTRO_PASO_MAX_DIST_M = 15

REGISTROS_PASO = {
    "A": {"dim": Dim(360, 360, 120), "entradas_lateral": 6, "diam_max_mm": 40},
    "B": {"dim": Dim(100, 100, 40), "entradas_lateral": 3, "diam_max_mm": 25},
    "C": {"dim": Dim(100, 160, 40), "entradas_lateral": 3, "diam_max_mm": 25},
}

RTR_OPCIONES = {
    1: ("Empotrable en tabique, equipos en vertical", "500 x 600 x 80 mm"),
    2: ("Dos envolventes adyacentes", "2 x (500 x 300 x 80 mm)"),
    3: ("Empotrable en otro elemento, equipos en horizontal", "300 x 400 x 300 mm"),
    4: ("SDTP/TBA según opción 1-3 + envolvente RTV independiente", "RTV: 200 x 300 x 60 mm"),
}

INTERIOR_USUARIO_DIAM_MM = 20
ASCENSOR_TUBO_DIAM_MM = 25


# ---------------------------------------------------------------------------
# Anexo II. Previsión de demanda y redes (telefonía y banda ancha)
# ---------------------------------------------------------------------------

FACTOR_RESERVA = 1.2  # Anexo II, ap. 3.3.1, 3.3.2 y 3.3.4
DIST_MAX_PARES_TRENZADOS_M = 100  # Anexo II, ap. 3.1.1 / 3.1.2
COAXIAL_ESTRELLA_MAX_PAU = 20     # Anexo II, ap. 3.3.3
FIBRA_ACOMETIDAS_DIRECTAS_MAX_PAU = 20  # Anexo II, ap. 3.3.4
FIBRAS_POR_ACOMETIDA = 2
MULTIFIBRA_NORMALIZADO = [8, 16, 24, 32, 48]  # preferentemente hasta 48 fibras (ap. 5)


def demanda_pares_trenzados(tipo: str, edif_oficinas: bool, definida: bool, sup_m2: float | None) -> Regla:
    """Acometidas de 4 pares trenzados (cat. 6) por usuario (ap. 3.1.1)."""
    if tipo == "vivienda":
        return Regla(1, ref("II", "3.1.1.a.i"))
    if tipo in ("local", "oficina"):
        if definida:
            n = 2 if edif_oficinas else 1
            return Regla(n, ref("II", "3.1.1.a.iii.1" if edif_oficinas else "3.1.1.a.ii.1"))
        return Regla(math.ceil((sup_m2 or 0) / 33), ref("II", "3.1.1.a.iii.2" if edif_oficinas else "3.1.1.a.ii.2"),
                     "1 acometida por cada 33 m² útiles.")
    return Regla(0, "", "Las estancias comunes se cubren con las 2 acometidas del edificio.")


def demanda_pares(tipo: str, edif_oficinas: bool, definida: bool, sup_m2: float | None) -> Regla:
    """Líneas (pares) por usuario cuando la distancia supera 100 m (ap. 3.1.2)."""
    if tipo == "vivienda":
        return Regla(2, ref("II", "3.1.2.a.i"))
    if tipo in ("local", "oficina"):
        if definida:
            return Regla(3, ref("II", "3.1.2.a.iii.1" if edif_oficinas else "3.1.2.a.ii.1"))
        if edif_oficinas:
            return Regla(3 * math.ceil((sup_m2 or 0) / 100), ref("II", "3.1.2.a.iii.2"))
        return Regla(math.ceil((sup_m2 or 0) / 33), ref("II", "3.1.2.a.ii.2"))
    return Regla(0, "")


def demanda_coaxial(tipo: str, definida: bool, sup_m2: float | None) -> Regla:
    if tipo == "vivienda":
        return Regla(1, ref("II", "3.1.3.a.i"))
    if tipo in ("local", "oficina"):
        if definida:
            return Regla(1, ref("II", "3.1.3.a.ii.1"))
        return Regla(math.ceil((sup_m2 or 0) / 100), ref("II", "3.1.3.a.ii.2"),
                     "Se deja disponible en el registro secundario de la planta.")
    return Regla(0, "")


def demanda_fibra(tipo: str, edif_oficinas: bool, definida: bool, sup_m2: float | None) -> Regla:
    """Acometidas ópticas (2 fibras cada una) por usuario (ap. 3.1.4)."""
    if tipo == "vivienda":
        return Regla(1, ref("II", "3.1.4.a.i"))
    if tipo in ("local", "oficina"):
        if edif_oficinas:
            if definida:
                return Regla(2, ref("II", "3.1.4.a.iii.1"))
            return Regla(2 * math.ceil((sup_m2 or 0) / 100), ref("II", "3.1.4.a.iii.2"))
        if definida:
            return Regla(1, ref("II", "3.1.4.a.ii.1"))
        return Regla(math.ceil((sup_m2 or 0) / 33), ref("II", "3.1.4.a.ii.2"),
                     "Se deja disponible en el registro secundario (o en el RITI si hay menos de 15 PAU).")
    return Regla(0, "")


ACOMETIDAS_INSTALACIONES_COMUNES = 2  # cada tecnología, para toda la edificación


# Cables multipares normalizados (ap. 3.3.2.ii)
_TABLA_MULTIPAR = [
    (25, "1(25p)"), (50, "1(50p)"), (75, "1(75p)"), (100, "1(100p)"),
    (125, "1(100p)+1(25p)"), (150, "1(100p)+1(50p)"), (175, "1(100p)+1(75p)"),
    (200, "2(100p)"), (225, "2(100p)+1(25p)"), (250, "2(100p)+1(50p)"),
    (275, "2(100p)+1(75p)"), (300, "3(100p)"),
]


def cable_multipar(n_pares: int) -> Regla:
    for limite, cable in _TABLA_MULTIPAR:
        if n_pares <= limite:
            return Regla(cable, ref("II", "3.3.2.a.ii"))
    n100 = math.ceil(n_pares / 100)
    return Regla(f"{n100}(100p)", ref("II", "3.3.2.a.ii"), "Fuera de tabla: combinación de cables de 100 pares.")


def cables_multifibra(n_fibras: int) -> Regla:
    """Combinación de cables multifibra normalizados de capacidad >= n_fibras."""
    if n_fibras <= 0:
        return Regla([], ref("II", "3.3.4.a.ii"))
    cables = []
    resto = n_fibras
    while resto > 48:
        cables.append(48)
        resto -= 48
    cables.append(min(c for c in MULTIFIBRA_NORMALIZADO if c >= resto))
    return Regla(cables, ref("II", "3.3.4.a.ii"), "Preferentemente cables de hasta 48 fibras (ap. 5).")


def registro_principal_entrada_pt(n_salida: int, n_pau: int) -> Regla:
    factor = 2 if n_pau <= 10 else 1.5
    return Regla(math.ceil(n_salida * factor), ref("III", "5.6.1"), f"Entrada = {factor} x salida.")


def registro_principal_entrada_fo(n_salida: int) -> Regla:
    return Regla(2 * n_salida, ref("III", "5.6.4"), "Conectores de entrada = 2 x salida.")


# ---------------------------------------------------------------------------
# Anexo I y Anexo III. Red interior de usuario
# ---------------------------------------------------------------------------

ESTANCIAS_NO_COMPUTABLES = {"bano", "aseo", "trastero"}
RTV_TOMAS_MIN_VIVIENDA = 2  # Anexo I, ap. 3.5.1


# ---------------------------------------------------------------------------
# Anexo I. Radiodifusión sonora y televisión (RTV)
# ---------------------------------------------------------------------------

def campo_minimo_tdt(f_mhz: float) -> Regla:
    """Intensidad de campo por encima de la cual hay que distribuir un canal de TDT (ap. 4.1.6).

    Tabla «Televisión terrestre»: digital, 470,0-862,0 MHz, «3 + 20 log f (MHz)» dBµV/m. Sin medidas en
    el emplazamiento se usa como campo de diseño (caso más desfavorable).
    """
    if not 470.0 <= f_mhz <= 862.0:
        raise ValueError(f"{f_mhz} MHz fuera de la banda de la tabla (470,0-862,0 MHz).")
    return Regla(round(3 + 20 * math.log10(f_mhz), 1), ref("I", "4.1.6"), "dBµV/m")


TOMAS_MAX_BANDA_ANCHA = 30   # Anexo I, ap. 4.3: central o amplificador de banda ancha si las tomas son < 30
DIF_NIVEL_CABECERA_DB = 3    # Anexo I, ap. 4.3: diferencia máxima entre canales de la misma naturaleza


def admite_banda_ancha(tomas: int) -> Regla:
    """Ap. 4.3: «queda limitado el uso de cualquier tipo de central amplificadora o amplificador de banda
    ancha a las edificaciones en las que el número de tomas servidas desde la cabecera sea inferior a 30»,
    salvo equipos que garanticen menos de 3 dB entre canales de la misma banda."""
    return Regla(tomas < TOMAS_MAX_BANDA_ANCHA, ref("I", "4.3"))
