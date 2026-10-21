"""Convierte un texto del BOE en XML a Markdown para docs/normativa.

Admite el texto consolidado de la API de datos abiertos
(https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/<ID>/texto) y el XML de una
disposición del diario (https://www.boe.es/diario_boe/xml.php?id=<ID>). Del consolidado toma la
última versión de cada bloque, que es la vigente.

Uso: python herramientas/boe_a_markdown.py entrada.xml salida.md --id BOE-A-... --titulo "..."
     [--fuente URL] [--publicacion AAAA-MM-DD] [--descarga AAAA-MM-DD]
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def _texto(e: ET.Element) -> str:
    return " ".join("".join(e.itertext()).split())


def _tabla(t: ET.Element) -> list[str]:
    filas = []
    for tr in t.iter("tr"):
        celdas = [_texto(c).replace("|", "/") for c in tr if c.tag in ("td", "th")]
        if celdas:
            filas.append(celdas)
    if not filas:
        return []
    ancho = max(len(f) for f in filas)
    filas = [f + [""] * (ancho - len(f)) for f in filas]
    lineas = ["| " + " | ".join(filas[0]) + " |", "| " + " | ".join(["---"] * ancho) + " |"]
    lineas += ["| " + " | ".join(f) + " |" for f in filas[1:]]
    return lineas


_ENCABEZADOS = {"articulo": "###### ", "capitulo_num": "### ", "capitulo_tit": "### ", "anexo_num": "## ",
                "anexo_tit": "## ", "titulo_num": "### ", "titulo_tit": "### ", "seccion": "#### ",
                "centro_redonda": "#### "}


def _contenido(contenedor: ET.Element) -> list[str]:
    md: list[str] = []
    for e in contenedor:
        if e.tag == "p":
            txt = _texto(e)
            if not txt:
                continue
            clase = e.get("class", "")
            if clase in _ENCABEZADOS:
                md.append(_ENCABEZADOS[clase] + txt)
            elif clase == "centro_cursiva":
                md.append(f"*{txt}*")
            elif clase in ("cita", "nota_pie", "textoCompleto"):
                md.append("> " + txt)
            else:
                md.append(txt)
        elif e.tag == "table":
            md.extend(_tabla(e))
        elif e.tag == "blockquote":
            md.extend("> " + linea for linea in _contenido(e) if linea)
        else:
            md.extend(_contenido(e))
        md.append("")
    return md


def convertir(entrada: Path) -> list[str]:
    raiz = ET.parse(entrada).getroot()
    bloques = list(raiz.iter("bloque"))
    if bloques:                                    # texto consolidado
        md: list[str] = []
        for b in bloques:
            versiones = b.findall("version")
            if versiones:
                md.extend(_contenido(versiones[-1]))
        return md
    # Disposición del diario: hay varios <texto> (también en los metadatos); el bueno es el de más párrafos
    textos = sorted(raiz.iter("texto"), key=lambda t: len(list(t.iter("p"))), reverse=True)
    return _contenido(textos[0]) if textos else []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--fuente", default="")
    ap.add_argument("--publicacion", default="")
    ap.add_argument("--descarga", default="")
    a = ap.parse_args(argv)
    cabecera = ["---", f'title: "{a.titulo}"', f'identifier: "{a.id}"',
                f'source: "{a.fuente or "https://www.boe.es/buscar/doc.php?id=" + a.id}"',
                f'publication_date: "{a.publicacion}"', f'downloaded: "{a.descarga}"', "---", "",
                f"# {a.titulo}", ""]
    cuerpo = convertir(a.entrada)
    # sin líneas en blanco repetidas
    lineas: list[str] = []
    for linea in cabecera + cuerpo:
        if linea == "" and lineas and lineas[-1] == "":
            continue
        lineas.append(linea)
    a.salida.write_text("\n".join(lineas).rstrip() + "\n", encoding="utf-8")
    print(f"{a.salida}: {len(lineas)} líneas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
