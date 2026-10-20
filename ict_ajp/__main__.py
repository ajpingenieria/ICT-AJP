"""Uso: python -m ict_ajp calcular proyecto.ict.json [-o resultado.xlsx]"""

import argparse
import sys
from pathlib import Path

from .dimensionado import dimensionar
from .exportar_excel import exportar
from .modelo import Proyecto


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ict_ajp", description="Motor de cálculo de proyectos ICT")
    sub = ap.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("calcular", help="Dimensiona el proyecto y exporta los resultados a Excel")
    c.add_argument("proyecto", type=Path)
    c.add_argument("-o", "--salida", type=Path)
    a = ap.parse_args(argv)

    p = Proyecto.cargar(a.proyecto)
    res = dimensionar(p)
    salida = a.salida or a.proyecto.with_name(a.proyecto.name.replace(".ict.json", "") + "_dimensionado.xlsx")
    exportar(p, res, salida)
    print(f"Dimensionado exportado a {salida}")
    for av in res.avisos:
        print(f"  [{av.nivel}] {av.texto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
