"""Esquemas de principio: reparto de las líneas de cada vivienda desde el registro secundario o el derivador."""

from ict_ajp.esquemas import _salidas


def _cruces(y, filas, salidas, orden, x0=0.0, paso=3.0):
    """Cuenta los cruces entre las líneas (salida en horizontal, vertical propia y horizontal hasta la fila)."""
    lineas = []
    for yf, ys, i in zip(filas, salidas, orden):
        xb = x0 + paso * (i + 1)
        lineas.append(((x0, xb, ys), (xb, min(ys, yf), max(ys, yf)), (xb, 100.0, yf)))
    n = 0
    for a in range(len(lineas)):
        for b in range(len(lineas)):
            if a == b:
                continue
            for xa0, xa1, ya in (lineas[a][0], lineas[a][2]):
                xv, yv0, yv1 = lineas[b][1]
                if min(xa0, xa1) < xv < max(xa0, xa1) and yv0 < ya < yv1:
                    n += 1
    return n


def test_dos_viviendas_salen_en_orden_y_sin_cruzarse():
    filas = [16.0, 4.0]                       # de arriba abajo, el registro en medio
    salidas, orden = _salidas(10.0, filas, 1.2)
    assert salidas == [11.2, 8.8]             # la de arriba sale por arriba
    assert sorted(orden) == [0, 1]
    assert _cruces(10.0, filas, salidas, orden) == 0


def test_varias_viviendas_por_planta_sin_cruzarse():
    for filas in ([30.0, 20.0, 10.0], [34.0, 26.0, 18.0, 10.0], [40.0, 31.0, 22.0, 13.0, 4.0]):
        y = sum(filas) / len(filas)
        salidas, orden = _salidas(y, filas, 1.2)
        assert sorted(orden) == list(range(len(filas)))
        assert salidas == sorted(salidas, reverse=True)
        assert _cruces(y, filas, salidas, orden) == 0


def test_una_vivienda_sale_recta():
    salidas, orden = _salidas(10.0, [10.0], 1.2)
    assert salidas == [10.0] and orden == [0]
