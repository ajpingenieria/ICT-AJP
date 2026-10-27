"""Uso: python -m ict_ajp calcular proyecto.ict.json [-o resultado.xlsx]"""

import argparse
import sys
from pathlib import Path

from .dimensionado import dimensionar
from .exportar_excel import exportar
from .modelo import Proyecto


def _salida_utf8() -> None:
    """En Windows, la salida redirigida usa cp1252 y no admite «≥», «µ»...: se pasa a UTF-8."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _salida_utf8()
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
    for orden, ayuda in (("memoria", "Genera la memoria del proyecto en Word (y PDF si hay LibreOffice)"),
                         ("pliego", "Genera el pliego de condiciones en Word (y PDF si hay LibreOffice)")):
        m = sub.add_parser(orden, help=ayuda)
        m.add_argument("proyecto", type=Path)
        m.add_argument("-o", "--salida", type=Path, help="Archivo .docx (por defecto, junto al proyecto)")
        m.add_argument("--plantilla", type=Path, help="Carpeta con empresa.json y logos de AJP")
    pl = sub.add_parser("planos", help="Dibuja las plantas de la ICT sobre la base DXF del arquitecto (DXF, PNG y PDF)")
    pl.add_argument("proyecto", type=Path)
    pl.add_argument("--base", type=Path, help="DXF del arquitecto (por defecto, el de planos.base_dxf del proyecto)")
    pl.add_argument("-o", "--salida", type=Path, help="DXF de salida (por defecto, junto a la base)")
    pl.add_argument("--plantilla", type=Path, help="Carpeta con empresa.json de AJP (autor del cajetín)")
    pl.add_argument("--sin-imagenes", action="store_true", help="Sin vistas previas PNG ni PDF (más rápido)")
    pl.add_argument("--actualizar-longitudes", action="store_true",
                    help="Guardar en el proyecto las longitudes medidas para el cálculo de RTV y la medición de "
                         "materiales para la memoria")
    a = ap.parse_args(argv)

    if a.orden == "planos":
        return _planos(a)

    if a.orden in ("memoria", "pliego"):
        from .documento import Plantilla
        from . import pdf as PDF
        if a.orden == "memoria":
            from .memoria import generar_memoria as generar
            nombre_doc = "Memoria ICT"
        else:
            from .pliego import generar_pliego as generar
            nombre_doc = "Pliego de condiciones ICT"
        p = Proyecto.cargar(a.proyecto)
        res = dimensionar(p)
        nombre = (p.datos_generales.numero + " - " if p.datos_generales.numero else "") + nombre_doc + ".docx"
        salida = a.salida or a.proyecto.parent / nombre
        plantilla = Plantilla.cargar(a.plantilla)
        docx, titulos = generar(p, res, salida, plantilla)
        if PDF.soffice():
            # Segunda pasada: números de página en el índice a partir del PDF
            pdf = PDF.a_pdf(docx)
            paginas = PDF.paginas_de_titulos(pdf, [t for _, t in titulos], desde=3)
            indice = [(n, t, paginas.get(t)) for n, t in titulos]
            generar(p, res, salida, plantilla, indice=indice)
            pdf = PDF.a_pdf(docx)
            print(f"{nombre_doc}: {docx}\nPDF: {pdf}")
        else:
            print(f"{nombre_doc}: {docx} (sin PDF: LibreOffice no está instalado)")
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


def _planos(a) -> int:
    from .documento import Plantilla
    from .leer_dxf import leer_plano
    from .planos_ict import colores_empresa, datos_cajetin, generar_planos, resumen_longitudes, ruta_cajetin

    p = Proyecto.cargar(a.proyecto)
    base = a.base or (Path(p.planos.base_dxf) if p.planos.base_dxf else None)
    if base and not base.is_absolute():
        base = (a.proyecto.parent / base).resolve()
    if not base or not base.exists():
        print("Falta la base DXF del arquitecto: indíquela con --base o en «planos.base_dxf» del proyecto.")
        return 1
    nombre = (p.datos_generales.numero + " - " if p.datos_generales.numero else "") + "Planos ICT.dxf"
    salida = a.salida or base.parent / nombre
    plantilla = Plantilla.cargar(a.plantilla)
    res = generar_planos(base, leer_plano(base), p, salida, datos_cajetin(p, plantilla),
                         mastil=p.planos.mastil_xy, holgura_vertical_m=p.planos.holgura_vertical_m,
                         imagenes=not a.sin_imagenes, pdf=not a.sin_imagenes, acceso_cubierta=p.planos.acceso_cubierta,
                         cajetin=ruta_cajetin(plantilla), colores=colores_empresa(plantilla))
    print(f"Planos de la ICT: {res.ruta} (escala 1:{res.escala})")
    for nombre_hoja, img in zip(res.presentaciones, res.imagenes):
        print(f"  {nombre_hoja}: {img.name}")
    if res.pdf:
        print(f"PDF: {res.pdf}")
    print("Longitudes medidas en planta (con la holgura vertical):")
    for m in res.mediciones:
        print(f"  {m.vivienda}: secundaria {m.secundaria_m:.1f} m; interior hasta cada toma de RTV "
              + ", ".join(f"{x:.1f}" for x in m.interior_m) + " m")
    for av in res.avisos:
        print(f"  [revisar] {av}")
    if res.materiales:
        print("Medición de los planos (para el cuadro resumen de materiales):")
        for clave, cantidad in res.materiales.items():
            print(f"  {clave}: {cantidad:g}")
    lon = resumen_longitudes(res.mediciones)
    if a.actualizar_longitudes and res.mediciones:
        r = p.rtv
        r.long_acometida_min_m, r.long_acometida_max_m = lon["acometida_min"], lon["acometida_max"]
        r.long_interior_min_m, r.long_interior_max_m = lon["interior_min"], lon["interior_max"]
        r.longitudes_medidas = True
        p.planos.materiales = res.materiales
        p.guardar(a.proyecto)
        print(f"Longitudes de RTV y medición guardadas en {a.proyecto}: acometida {lon['acometida_min']:.1f}-"
              f"{lon['acometida_max']:.1f} m, interior {lon['interior_min']:.1f}-{lon['interior_max']:.1f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
