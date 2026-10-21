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
    d = sub.add_parser("leer-dxf", help="Lee plantas, viviendas y estancias de la base DXF del arquitecto")
    d.add_argument("plano", type=Path)
    d.add_argument("-o", "--salida", type=Path, help="Guardar el informe en un archivo de texto")
    b = sub.add_parser("borrador", help="Crea un proyecto .ict.json con las plantas y viviendas del DXF")
    b.add_argument("plano", type=Path)
    b.add_argument("-o", "--salida", type=Path, required=True)
    b.add_argument("--nombres", choices=["planta_letra", "letras_seguidas"], default="planta_letra",
                   help="1ºA, 1ºB... Ático A (por defecto) o A, B, C... de abajo arriba")
    m = sub.add_parser("memoria", help="Genera la memoria del proyecto en Word (y PDF si hay LibreOffice)")
    m.add_argument("proyecto", type=Path)
    m.add_argument("-o", "--salida", type=Path, help="Archivo .docx (por defecto, junto al proyecto)")
    m.add_argument("--plantilla", type=Path, help="Carpeta con empresa.json y logos de AJP")
    a = ap.parse_args(argv)

    if a.orden == "memoria":
        from .documento import Plantilla
        from .memoria import generar_memoria
        from . import pdf as PDF
        p = Proyecto.cargar(a.proyecto)
        res = dimensionar(p)
        nombre = (p.datos_generales.numero + " - " if p.datos_generales.numero else "") + "Memoria ICT.docx"
        salida = a.salida or a.proyecto.parent / nombre
        plantilla = Plantilla.cargar(a.plantilla)
        docx, titulos = generar_memoria(p, res, salida, plantilla)
        if PDF.soffice():
            # Segunda pasada: números de página en el índice a partir del PDF
            pdf = PDF.a_pdf(docx)
            paginas = PDF.paginas_de_titulos(pdf, [t for _, t in titulos], desde=3)
            indice = [(n, t, paginas.get(t)) for n, t in titulos]
            generar_memoria(p, res, salida, plantilla, indice=indice)
            pdf = PDF.a_pdf(docx)
            print(f"Memoria: {docx}\nPDF: {pdf}")
        else:
            print(f"Memoria: {docx} (sin PDF: LibreOffice no está instalado)")
        return 0

    if a.orden == "borrador":
        from .leer_dxf import leer_plano, proyecto_desde_lectura
        if a.salida.exists():
            print(f"{a.salida} ya existe: no se sobrescribe para no perder datos ya completados.")
            return 1
        p = proyecto_desde_lectura(leer_plano(a.plano), a.nombres)
        p.guardar(a.salida)
        print(f"Borrador guardado en {a.salida}:")
        for pl in p.edificio.plantas:
            print(f"  {pl.nombre}: {', '.join(u.id for u in pl.usuarios) or 'sin viviendas'}")
        return 0

    if a.orden == "leer-dxf":
        from .leer_dxf import informe, leer_plano
        texto = informe(leer_plano(a.plano))
        if a.salida:
            a.salida.write_text(texto + "\n", encoding="utf-8")
            print(f"Informe guardado en {a.salida}")
        print(texto)
        return 0

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
