"""Cálculo de niveles de RTV con el catálogo Televés (Anexo I, 4.4 y 4.5)."""

import time

import pytest

from ict_ajp import rtv_niveles as RN

CAMPOS = {"TDT": [(474.0, 56.5), (666.0, 59.5)], "FM": [(93.5, 66)], "DAB": [(218.6, 58)]}


def _edificio(n_plantas, viv=2, tomas=5):
    return [(f"Planta {n_plantas - k}", [(f"{n_plantas - k}{chr(65 + i)}", tomas) for i in range(viv)])
            for k in range(n_plantas)]


def test_formulas_fisicas():
    # Campo mínimo de la norma (3 + 20 log f) y antena de 17 dBi: la tensión no depende de la frecuencia
    assert RN.tension_antena_dbuv(3 + 20 * 2.8, 17, 10 ** 2.8) == pytest.approx(51.5, abs=0.05)
    assert RN.ruido_termico_dbuv(7.61) == 3.6                                  # kTB en 75 ohmios, 7,61 MHz


def test_edificio_de_4_plantas_cumple():
    r = RN.calcular(_edificio(4), CAMPOS, RN.Geometria(entre_plantas=2.9), canales_tdt=9)
    for serv in ("TDT", "FM", "DAB"):
        lo, hi = RN.NIVEL_TOMA[serv]
        peor, mejor = r.niveles_toma[serv]
        assert lo <= peor <= mejor <= hi, serv                  # todas las tomas dentro del margen de 4.5
        assert r.cn_toma[serv] >= RN.CN_MIN[serv]
    assert all(r.cumple.values())
    assert r.respuesta_banda["terr"] <= 16 and r.respuesta_banda["sat"] <= 20   # 4.4.3
    assert r.consumo_ma == 9 * 195 + 220                        # 9 T12 UHF + 1 T12 FM/DAB (fichas)
    assert {v.pau for v in r.viviendas} == {"519535"}           # PAU de 5 salidas para 5 tomas
    # las plantas más cercanas a la cabecera llevan derivadores de más pérdida
    derivacion = [int(ref[-1]) for _, ref in r.derivadores_por_planta]
    assert derivacion == sorted(derivacion, reverse=True)


def test_muchas_plantas_es_rapido():
    t0 = time.perf_counter()
    r = RN.calcular(_edificio(10), CAMPOS, canales_tdt=8)
    assert time.perf_counter() - t0 < 2
    assert len(r.derivadores_por_planta) == 10


def test_sin_pau_suficiente():
    with pytest.raises(ValueError, match="PAU de 9 salidas"):
        RN.calcular(_edificio(2, tomas=9), CAMPOS)
