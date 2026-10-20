from pathlib import Path

from ict_ajp.dimensionado import dimensionar, interior_usuario
from ict_ajp.modelo import Proyecto, Usuario

EJEMPLO = Path(__file__).parent.parent / "ejemplos" / "edificio_prueba.ict.json"


def partida(res, clave, concepto):
    return next(p for p in res.seccion(clave).partidas if p.concepto.startswith(concepto))


def test_ejemplo_completo():
    p = Proyecto.cargar(EJEMPLO)
    r = dimensionar(p)
    assert r.datos["n_pau"] == 20
    assert partida(r, "demanda", "Demanda total de cobre").valor == 27      # 16+2 viv, 3+4 locales, 2 comunes
    assert partida(r, "redes", "Cables de 4 pares").valor == 33             # ceil(27 x 1,2)
    assert partida(r, "redes", "Registro principal de cobre: capacidad").valor == 51
    assert r.datos["verticales"][1]["fibra"]["cables"] == 33
    assert "500 x 700 x 150" in partida(r, "infra", "Registros secundarios de planta (dim").valor
    assert "6 tubos" in partida(r, "infra", "Canalización principal").valor
    assert partida(r, "infra", "Registros de terminación").valor == 18
    assert {a.nivel for a in r.avisos} >= {"revisar", "decision"}


def test_interior_vivienda_tres_dormitorios():
    u = Usuario.model_validate({"id": "1A", "estancias": [
        {"nombre": "Salón", "tipo": "salon", "principal": True}, {"nombre": "Cocina", "tipo": "cocina"},
        {"nombre": "D1", "tipo": "dormitorio", "principal": True}, {"nombre": "D2", "tipo": "dormitorio"},
        {"nombre": "D3", "tipo": "dormitorio"}, {"nombre": "Baño", "tipo": "bano"}]})
    i = interior_usuario(u, equipar_todos=True)
    assert (i.reg_pt, i.reg_tba, i.reg_rtv, i.reg_fo, i.reg_configurable) == (7, 2, 5, 1, 1)
    assert i.tomas_pt == 9
    assert interior_usuario(u, equipar_todos=False).tomas_pt == 8


def test_estudio_minimo_dos_tomas_rtv():
    u = Usuario.model_validate({"id": "E", "estancias": [{"nombre": "Estancia", "tipo": "salon"},
                                                          {"nombre": "Baño", "tipo": "bano"}]})
    assert interior_usuario(u, True).reg_rtv == 2


def test_distancia_mayor_100_usa_pares():
    p = Proyecto.cargar(EJEMPLO)
    p.edificio.distancia_max_pi_pau_m = 120
    r = dimensionar(p)
    assert r.datos["cobre"] == "pares"
    # 18 viv x 2 + locales (3 + 4 líneas por 33 m²) + 2 comunes = 45 líneas -> 54 pares
    assert partida(r, "redes", "Pares de la red").valor == 54
