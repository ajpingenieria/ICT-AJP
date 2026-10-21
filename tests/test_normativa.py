"""Comprueba los límites de cada tabla contra el texto del RD 346/2011."""

from ict_ajp import normativa as N


def dims(r):
    return (r.valor.a, r.valor.b, r.valor.c)


def test_arqueta_entrada():  # Anexo III 5.1
    assert dims(N.arqueta_entrada(20)) == (400, 400, 600)
    assert dims(N.arqueta_entrada(21)) == (600, 600, 800)
    assert dims(N.arqueta_entrada(100)) == (600, 600, 800)
    assert dims(N.arqueta_entrada(101)) == (800, 700, 820)


def test_canalizacion_externa():  # Anexo III 5.2
    t = lambda n: N.canalizacion_externa(n).valor["tubos"]
    assert [t(4), t(5), t(20), t(21), t(40), t(41)] == [3, 4, 4, 5, 5, 6]
    assert N.canalizacion_externa(10).valor["diametro_mm"] == 63


def test_rit():  # Anexo III 5.5.1
    assert dims(N.rit(20)) == (2000, 1000, 500)
    assert dims(N.rit(21)) == (2000, 1500, 500)
    assert dims(N.rit(45)) == (2000, 1500, 500)
    assert dims(N.rit(46)) == (2300, 2000, 1000)
    assert dims(N.rit(74)) == (2300, 2000, 1000)
    assert dims(N.rit(75)) == (2300, 2000, 2000)


def test_rit_compacto():  # Anexo III 5.5.1 (ancho y alto modificables) y 5.5 (puerta 180 x 80 cm)
    minimo = N.rit(20).valor                                   # 2000 x 1000 x 500
    c = lambda h: dims(N.rit_compacto(minimo, h))              # noqa: E731
    assert c(2000) == (2000, 1000, 500)                        # sin altura extra no cambia
    assert c(2350) == (2330, 860, 500)                         # 2,00 m² frontales: 0,86 x 2,33
    assert c(2500) == (2500, 800, 500)                         # justo en el ancho de la puerta
    assert c(3000) == (2500, 800, 500)                         # no baja de 80 cm de ancho
    assert c(1800) == (1800, 1120, 500)                        # menos altura: más ancho, nunca < puerta
    assert c(1799) == (2000, 1000, 500)                        # por debajo de la puerta: no se aplica
    for h in (1800, 2350, 2500, 3000):                         # siempre >= 2,00 m² y mismo fondo
        a, b, f = c(h)
        assert a * b >= 2000 * 1000 and f == 500


def test_ritu():
    assert dims(N.ritu(5, zonas_comunes=False)) == (1000, 500, 300)
    assert dims(N.ritu(5, zonas_comunes=True)) == (1000, 1000, 500)
    assert dims(N.ritu(16, True)) == (2000, 1000, 500)
    assert dims(N.ritu(17, True)) == (2000, 1500, 1000)
    assert dims(N.ritu_a(21)) == (2000, 3000, 500)


def test_canalizacion_principal():  # Anexo III 5.7.1
    u = lambda n: N.canalizacion_principal(n).valor
    assert u(10)["tubos"] == 5
    assert u(11)["tubos"] == 6 and u(11)["uso"]["coaxial"] == 2
    assert u(21)["tubos"] == 7 and u(21)["uso"]["pares"] == 2 and u(21)["uso"]["reserva"] == 2
    g = u(45)["uso"]
    assert g["pares"] == 3 and g["reserva"] == 3
    assert u(50)["uso"]["reserva"] == 4
    assert N.canalizacion_principal(50, "pares").valor["uso"]["pares"] == 2


def test_registro_secundario():  # Anexo III 5.8
    assert dims(N.registro_secundario(20, 3, 7)) == (450, 450, 150)
    assert dims(N.registro_secundario(20, 4, 5)) == (450, 450, 150)
    assert dims(N.registro_secundario(20, 4, 6)) == (500, 700, 150)
    assert dims(N.registro_secundario(25, 3, 9)) == (500, 700, 150)
    assert dims(N.registro_secundario(31, 2, 16)) == (550, 1000, 150)


def test_tubos_secundaria():  # Anexo III 5.9
    f = lambda n: N.tubos_secundaria(n, "pares_fibra_interior").valor
    assert f(3) == {"tubos": 1, "diametro_mm": 25}
    assert f(4) == {"tubos": 1, "diametro_mm": 32}
    assert f(8) == {"tubos": 1, "diametro_mm": 40}
    assert f(9) == {"tubos": 2, "diametro_mm": 32}
    assert N.tubos_secundaria(2, "coaxial_RTV").valor["diametro_mm"] == 25
    assert N.tubos_secundaria(3, "coaxial_RTV").valor["diametro_mm"] == 32
    assert N.tubos_secundaria(2, "pares_fibra_exterior").valor["diametro_mm"] == 25
    assert N.tubos_secundaria(3, "pares_fibra_exterior").valor["diametro_mm"] == 32


def test_demanda():  # Anexo II 3.1
    assert N.demanda_pares_trenzados("vivienda", False, True, None).valor == 1
    assert N.demanda_pares_trenzados("local", False, False, 95).valor == 3
    assert N.demanda_pares_trenzados("local", True, True, None).valor == 2
    assert N.demanda_pares("vivienda", False, True, None).valor == 2
    assert N.demanda_pares("oficina", True, False, 150).valor == 6
    assert N.demanda_coaxial("local", False, 130).valor == 2
    assert N.demanda_fibra("local", False, False, 34).valor == 2
    assert N.demanda_fibra("oficina", True, False, 201).valor == 6


def test_cables():
    assert N.cable_multipar(30).valor == "1(50p)"
    assert N.cable_multipar(130).valor == "1(100p)+1(50p)"
    assert N.cables_multifibra(40).valor == [48]
    assert N.cables_multifibra(65).valor == [48, 24]
    assert N.registro_principal_entrada_pt(10, 10).valor == 20
    assert N.registro_principal_entrada_pt(34, 20).valor == 51
