"""Exporta el resultado del dimensionado a una hoja de cálculo Excel.

Cada cifra va con su referencia normativa. Las filas de total se escriben como
fórmulas SUMA para que se puedan comprobar en la propia hoja.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import __version__
from .dimensionado import Resultado, Tabla
from .modelo import Proyecto

FUENTE = "Arial"
AZUL = "1F3864"
GRIS = "F2F2F2"
COLOR_AVISO = {"revisar": "FCE4D6", "decision": "FFF2CC", "info": "DDEBF7"}
ETIQUETA_AVISO = {"revisar": "Revisar", "decision": "Decisión del proyectista", "info": "Información"}

_fino = Side(style="thin", color="BFBFBF")
BORDE = Border(left=_fino, right=_fino, top=_fino, bottom=_fino)


def _f(bold=False, color="000000", size=10, italic=False):
    return Font(name=FUENTE, bold=bold, color=color, size=size, italic=italic)


def _cabecera(ws, fila: int, valores: list[str]) -> None:
    for j, v in enumerate(valores, start=1):
        c = ws.cell(row=fila, column=j, value=v)
        c.font = _f(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = BORDE


def _celda(ws, fila: int, col: int, valor, bold=False, fill=None, wrap=True):
    c = ws.cell(row=fila, column=col, value=valor)
    c.font = _f(bold=bold)
    c.alignment = Alignment(wrap_text=wrap, vertical="top")
    c.border = BORDE
    if fill:
        c.fill = PatternFill("solid", fgColor=fill)
    return c


def _titulo(ws, texto: str, sub: str = "") -> int:
    ws.cell(row=1, column=1, value=texto).font = _f(bold=True, size=14, color=AZUL)
    if sub:
        ws.cell(row=2, column=1, value=sub).font = _f(italic=True, color="595959")
    return 4


def _escribir_tabla(ws, fila: int, t: Tabla) -> int:
    ws.cell(row=fila, column=1, value=t.titulo).font = _f(bold=True, size=11, color=AZUL)
    if t.referencia:
        ws.cell(row=fila + 1, column=1, value=f"Referencia: {t.referencia}").font = _f(italic=True, color="595959")
    fila += 2
    _cabecera(ws, fila, t.cabeceras)
    primera = fila + 1
    for i, f in enumerate(t.filas):
        for j, v in enumerate(f, start=1):
            _celda(ws, primera + i, j, v)
    ultima = primera + len(t.filas) - 1
    fila = ultima + 1
    if t.fila_total:
        for j, v in enumerate(t.fila_total, start=1):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and j > 1:
                col = get_column_letter(j)
                if t.col_unidades and j != t.col_unidades:
                    cu = get_column_letter(t.col_unidades)
                    v = f"=SUMPRODUCT(${cu}${primera}:${cu}${ultima},{col}{primera}:{col}{ultima})"
                else:
                    v = f"=SUM({col}{primera}:{col}{ultima})"
            _celda(ws, fila, j, v, bold=True, fill=GRIS)
        fila += 1
    return fila + 1


def _anchos(ws, anchos: dict[int, int]) -> None:
    for col, w in anchos.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def exportar(proyecto: Proyecto, res: Resultado, ruta: str | Path) -> Path:
    wb = Workbook()
    dg = proyecto.datos_generales

    # Resumen y avisos
    ws = wb.active
    ws.title = "Resumen"
    fila = _titulo(ws, dg.titulo or "Proyecto ICT",
                   f"Dimensionado generado con ICT-AJP v{__version__} el {dt.date.today():%d/%m/%Y}")
    datos = [("Promotor", dg.promotor), ("Emplazamiento", ", ".join(x for x in (dg.direccion, dg.municipio,
                                                                                dg.provincia) if x)),
             ("Proyectista", dg.proyectista.nombre), ("Número de PAU", res.datos.get("n_pau")),
             ("Tecnología de cobre", "Pares trenzados (cat. 6)" if res.datos.get("cobre") == "pares_trenzados"
              else "Pares (multipar)")]
    for k, v in datos:
        _celda(ws, fila, 1, k, bold=True, fill=GRIS)
        _celda(ws, fila, 2, v)
        fila += 1
    fila += 1
    ws.cell(row=fila, column=1, value="Avisos y decisiones a revisar").font = _f(bold=True, size=11, color=AZUL)
    fila += 1
    _cabecera(ws, fila, ["Tipo", "Aviso", "Referencia"])
    fila += 1
    orden = {"revisar": 0, "decision": 1, "info": 2}
    for a in sorted(res.avisos, key=lambda a: orden.get(a.nivel, 9)):
        col = COLOR_AVISO.get(a.nivel)
        _celda(ws, fila, 1, ETIQUETA_AVISO.get(a.nivel, a.nivel), bold=True, fill=col)
        _celda(ws, fila, 2, a.texto, fill=col)
        _celda(ws, fila, 3, a.referencia, fill=col)
        fila += 1
    if not res.avisos:
        _celda(ws, fila, 1, "Sin avisos")
    _anchos(ws, {1: 26, 2: 95, 3: 40})

    # Una hoja por sección
    nombres = {"edificio": "Edificio", "demanda": "Demanda", "redes": "Redes", "interior": "Red interior",
               "infra": "Infraestructura", "recintos": "Recintos", "rtv": "RTV"}
    for sec in res.secciones:
        ws = wb.create_sheet(nombres.get(sec.clave, sec.clave[:31]))
        fila = _titulo(ws, sec.titulo, dg.titulo)
        for t in sec.tablas:
            fila = _escribir_tabla(ws, fila, t)
        if sec.partidas:
            _cabecera(ws, fila, ["Concepto", "Valor", "Unidad", "Referencia", "Nota"])
            fila += 1
            for p in sec.partidas:
                _celda(ws, fila, 1, p.concepto, bold=True)
                _celda(ws, fila, 2, p.valor)
                _celda(ws, fila, 3, p.unidad)
                _celda(ws, fila, 4, p.referencia)
                _celda(ws, fila, 5, p.nota)
                fila += 1
        n_cols = max([len(t.cabeceras) for t in sec.tablas] + [5])
        anchos = {1: 42, 2: 30, 3: 18, 4: 34, 5: 60}
        for c in range(6, n_cols + 1):
            anchos[c] = 14
        if sec.clave == "interior":
            anchos.update({1: 18, 2: 7, 3: 34, 4: 12, 5: 12, 14: 50})
        _anchos(ws, anchos)

    # Normativa
    ws = wb.create_sheet("Normativa")
    fila = _titulo(ws, "Normativa aplicada")
    normas = [
        ("Real Decreto 346/2011, de 11 de marzo", "Reglamento regulador de las ICT. Texto consolidado "
         "(incluye Orden ECE/983/2019, RD 391/2019, RD 805/2014 y RD 250/2025)."),
        ("Orden ITC/1644/2011, de 10 de junio", "Desarrollo del Reglamento: contenido y estructura del proyecto técnico."),
        ("Orden ECE/983/2019, de 26 de septiembre", "Reacción al fuego de los cables (euroclases CPR)."),
        ("Real Decreto-ley 1/1998, de 27 de febrero", "Infraestructuras comunes en los edificios."),
        ("Real Decreto 250/2025, de 25 de marzo", "Plan Técnico Nacional de la Televisión Digital Terrestre: "
         "áreas geográficas y canales de cada múltiple (anexos I y II)."),
        ("Resolución de 23 de julio de 2026 (SETID)", "Fechas de la fase 1: RGE2 en DVB-T2 (UHD) desde el 05/11/2026."),
    ]
    _cabecera(ws, fila, ["Norma", "Objeto"])
    fila += 1
    for n, o in normas:
        _celda(ws, fila, 1, n, bold=True)
        _celda(ws, fila, 2, o)
        fila += 1
    _anchos(ws, {1: 45, 2: 100})

    for w in wb.worksheets:
        w.sheet_view.showGridLines = False
        w.page_setup.orientation = "landscape"
        w.page_setup.paperSize = w.PAPERSIZE_A4
        w.sheet_properties.pageSetUpPr.fitToPage = True
        w.page_setup.fitToWidth = 1
        w.page_setup.fitToHeight = 0
        w.print_options.horizontalCentered = True
    ruta = Path(ruta)
    wb.save(ruta)
    return ruta
