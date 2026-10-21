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


def test_sin_consulta_a_operadores_se_proyectan_las_tres_redes():
    p = Proyecto.cargar(EJEMPLO)
    p.operadores.coaxial = False
    p.operadores.consulta_realizada = False
    r = dimensionar(p)
    assert not partida(r, "redes", "Acometidas coaxiales de dispersión").nota
    assert any("art. 8" in a.referencia and a.nivel == "info" for a in r.avisos)
    p.operadores.consulta_realizada = True      # consulta hecha y sin operador de cable
    r = dimensionar(p)
    assert "hilo guía" in partida(r, "redes", "Acometidas coaxiales de dispersión").nota


def _edificio_ritu(n_plantas: int, atico: bool, cuenta: bool):
    p = Proyecto.cargar(EJEMPLO)
    plantas = [pl for pl in p.edificio.plantas if 0 < pl.nivel <= n_plantas]
    plantas[-1].es_atico = atico
    p.edificio.plantas = plantas
    p.edificio.recintos = "RITU"
    p.opciones.atico_cuenta_como_altura = cuenta
    return dimensionar(p)


def test_atico_y_recinto_unico():
    conceptos = lambda r: [x.concepto for x in r.seccion("infra").partidas]   # noqa: E731
    # 4 alturas con ático que cuenta -> RITU-A; si no cuenta -> 3 alturas -> RITU
    r = _edificio_ritu(4, atico=True, cuenta=True)
    assert any(c.startswith("RITU-A") for c in conceptos(r))
    assert any(a.nivel == "decision" and "ático se cuenta" in a.texto for a in r.avisos)
    r = _edificio_ritu(4, atico=True, cuenta=False)
    assert any(c.startswith("RITU (") for c in conceptos(r))
    # Con recinto único, los textos hablan del RITU y los 3 tubos de contadores van a él
    assert "desde el RITU" in partida(r, "redes", "Red de fibra óptica").valor
    assert partida(r, "recintos", "Canalizaciones desde centralización").valor == "3 tubos Ø32 mm al RITU"
    # Sin ático no hay aviso de criterio
    r = _edificio_ritu(3, atico=False, cuenta=True)
    assert any(c.startswith("RITU (") for c in conceptos(r))
    assert not any("ático" in a.texto for a in r.avisos)


def test_riti_rits_con_rits_compacto():
    p = Proyecto.cargar(EJEMPLO)
    p.edificio.recintos = "RITI_RITS"
    p.opciones.altura_libre_rits_mm = 2350
    r = dimensionar(p)
    assert partida(r, "infra", "RITI (dimensiones mínimas)").valor.startswith("2000 x 1000 x 500")
    assert partida(r, "infra", "RITS (dimensiones adoptadas)").valor.startswith("2330 x 860 x 500")
    assert not any(x.concepto.startswith("RITI (dimensiones adoptadas)") for x in r.seccion("infra").partidas)
    assert any(a.nivel == "decision" and a.texto.startswith("RITS:") for a in r.avisos)
    assert partida(r, "recintos", "Canalizaciones desde centralización").valor.endswith("1 tubo Ø32 mm al RITS")


def test_distancia_mayor_100_usa_pares():
    p = Proyecto.cargar(EJEMPLO)
    p.edificio.distancia_max_pi_pau_m = 120
    r = dimensionar(p)
    assert r.datos["cobre"] == "pares"
    # 18 viv x 2 + locales (3 + 4 líneas por 33 m²) + 2 comunes = 45 líneas -> 54 pares
    assert partida(r, "redes", "Pares de la red").valor == 54
