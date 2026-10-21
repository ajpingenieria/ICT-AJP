"""Catálogo Televés: cifras comprobadas contra las fichas oficiales (consultadas el 21/10/2026)."""

import pytest

from ict_ajp import catalogo as C


def test_cifras_de_las_fichas():
    assert C.elemento("149922")["ganancia_dbi"] == 17.0                 # DAT BOSS, modo pasivo
    t12 = C.elemento("509812")
    assert (t12["ganancia_db"], t12["nivel_salida_en50083_dbuv"]) == ([50.0], [118.0])
    assert C.elemento("509012")["nivel_salida_en50083_dbuv"] == [120.0, 113.0]   # FM, DAB
    d = C.elemento("519342")                                            # derivador 4D 12 dB
    assert (d["derivacion_db"], d["paso_db"]) == ({"terr": 13.0, "sat": 12.5}, {"terr": 2.5, "sat": 3.6})
    assert C.elemento("519341")["terminal"] is True and C.elemento("519341")["paso_db"] is None
    assert C.elemento("519535")["perdida_db"] == {"terr": 11.0, "sat": 10.0}   # PAU 5D
    assert C.elemento("5228")["paso"] is True and C.elemento("5228")["paso_db"] == {"TV": 3.5, "SAT": 5.0}
    assert C.elemento("5229")["atenuacion_db"] == {"TV": 4.0, "SAT": 5.0}
    assert all(e["fuente"].startswith("https://") for g in ("antenas", "derivadores", "tomas", "cables")
               for e in C.cargar()[g])


def test_atenuacion_cable():
    assert C.atenuacion_cable_db_m("414002", 698) == 0.17               # punto de la ficha
    assert C.atenuacion_cable_db_m("414002", 2150) == 0.31
    assert 0.14 < C.atenuacion_cable_db_m("414002", 600) < 0.17         # entre 500 y 698 MHz
    with pytest.raises(ValueError):
        C.atenuacion_cable_db_m("414002", 4000)                          # no se extrapola
    with pytest.raises(ValueError):
        C.atenuacion_cable_db_m("519322", 600)                           # no es un cable


def test_seleccion():
    assert [d["ref"] for d in C.derivadores(2)] == ["519322", "519323", "519324", "519325"]
    assert C.repartidor(5)["ref"] == "519535"                            # PAU de 5 salidas
    assert C.repartidor(7) is None                                       # no hay PAU de 7 en el catálogo
