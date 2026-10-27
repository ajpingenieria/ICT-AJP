# ICT-AJP — contexto para Claude

Herramienta de **AJP Ingeniería** para calcular y generar proyectos de Infraestructura Común de
Telecomunicaciones (ICT) según el RD 346/2011 y la Orden ITC/1644/2011. El objetivo final es una
aplicación de escritorio para Windows (.exe), parecida en flujo a CYPE, que saque el proyecto
completo: cálculos, planos DXF, memoria, pliego y presupuesto.

## Con quién trabajas

- **Contesta siempre en español**, en todos los mensajes, aunque las herramientas o los errores
  salgan en inglés.
- El usuario es el ingeniero proyectista de AJP Ingeniería: conoce la normativa y firma el proyecto,
  pero **no es programador**. Explica sin jerga de programación y dile qué hace falta que él
  revise o decida.
- Se usa en paralelo para un **proyecto real urgente** (bloque de viviendas). Prioridad: que el
  motor saque adelante ese proyecto; la interfaz gráfica, después.

## Proyectos reales (clientes)

1. **Los datos y resultados de cada edificio van en Google Drive, nunca en el repositorio.** Cada
   proyecto tiene su carpeta en `G:\Mi unidad\Proyectos AJP\`, con el formato
   `<número> - <nombre>` (`1` + año + número de 3 cifras, consecutivo al último existente) y
   subcarpetas `PLANOS`, `MEMORIA` y `CALCULOS`.
   Nada del cliente (planos del arquitecto, `.ict.json`, Excel, DXF, nombres, direcciones) se
   copia al repositorio ni se sube a GitHub; tampoco en las pruebas ni en los ejemplos.
2. **Todo lo que se haga para un edificio se hace como parte reutilizable de la app**, no a mano:
   si hace falta algo nuevo, se programa en `ict_ajp/` con sus pruebas y se ejecuta sobre el
   proyecto.
3. **El proyecto real tiene prioridad.** Si algo de la app lo retrasa, se resuelve el proyecto y
   lo que quede por hacer en la app se apunta en [`docs/pendiente.md`](docs/pendiente.md).

## Estructura

- `ict_ajp/modelo.py` — modelo de datos del proyecto (pydantic). Un proyecto es un archivo `.ict.json`.
- `ict_ajp/normativa.py` — tablas y reglas del reglamento, cada una con su anexo y apartado.
- `ict_ajp/dimensionado.py` — motor: devuelve secciones de partidas y tablas, más avisos
  (`revisar`, `decision`, `info`) para el proyectista.
- `ict_ajp/exportar_excel.py` — exportación a Excel con referencias normativas.
- `ict_ajp/leer_dxf.py` — lectura de la base DXF del arquitecto: plantas, viviendas (contornos de
  superficie construida) y estancias (nombre + superficie rotulados), más RIT y ascensores dibujados.
- `ict_ajp/vista_previa.py` — imagen PNG de un DXF, de una zona o de una presentación, y PDF vectorial de
  las presentaciones a tamaño real; con `resaltar` la base del arquitecto sale en gris y la ICT en color.
- `ict_ajp/planos_ict.py` — plantas de la ICT sobre la base DXF del arquitecto: copia su vista de
  distribución (sin su marco ni título) y dibuja en capas `ICT_` el registro secundario y la canalización
  principal, el RTR con la toma configurable, los registros de toma junto a la pared de cada estancia
  (polilíneas de superficie útil), los tubos, los recintos, la arqueta de entrada y el mástil con el enlace
  superior. Hojas A3 con el cajetín de AJP (plantilla DXF en la carpeta de Drive, `cajetin_planos` de
  `empresa.json`, con sus colores corporativos) y leyenda, todas a la misma escala, PNG de cada una y un PDF.
  Símbolos elegidos por el proyectista: pegados a la pared con su texto dentro, en mm de papel (mismo tamaño a
  cualquier escala), y el número y diámetro de tubos (del dimensionado) rotulado en cada tramo sin pisar textos.
  Mide las longitudes RS-RTR y RTR-toma de RTV para el cálculo de niveles y la medición de tubos y registros
  (cuadro resumen de materiales de la memoria). En cubierta marca la reserva para antenas de satélite (Anexo I
  3.6). Los datos del edificio (base DXF, mástil, acceso a cubierta, medición) van en `planos` del `.ict.json`.
- `ict_ajp/rtv.py` — radio y televisión: canales de TDT del emplazamiento, campo de diseño, tipo de
  cabecera y previsión de satélite.
- `ict_ajp/plan_tdt.py` + `ict_ajp/datos/plan_tdt.json` — áreas y canales del Plan Técnico Nacional
  de la TDT. El JSON se genera con `herramientas/generar_plan_tdt.py` desde `docs/normativa` y una
  prueba comprueba que coinciden.
- `ict_ajp/plan_radio.py` + `ict_ajp/datos/plan_radio.json` — bloques DAB por provincia, emisoras FM
  por localidad y demarcaciones de TDT local (generado con `herramientas/generar_plan_radio.py`).
- `ict_ajp/rtv_niveles.py` — niveles toma a toma: elige derivadores por planta, PAU por número de tomas,
  salida de cabecera, niveles, C/N, respuesta en banda, consumo y previsión de satélite (Anexo I 4.4 y 4.5).
  Las fórmulas físicas (tensión en antena, kTB) están comentadas como tales, no son norma.
- `ict_ajp/catalogo.py` + `ict_ajp/catalogos/televes.json` — catálogo de RTV del fabricante:
  antenas, amplificadores T12, fuente, derivadores y repartidores/PAU serie F, tomas y cable
  SK2003plus, cada uno con la URL de su ficha. Se genera con `herramientas/generar_catalogo_televes.py`
  desde las fichas PDF descargadas (los PDF no se suben: son del fabricante).
- `ict_ajp/documento.py` — Word con el estilo de AJP (A4, Arial, cabecera con logo y dirección, pie con
  «Página x de y», tablas, marcas «[PENDIENTE: …]» resaltadas). Los datos y logos de AJP están en
  `G:\Mi unidad\Proyectos AJP\_Plantilla ICT-AJP\` (`empresa.json`), **no en el repositorio, que es
  público**.
- `ict_ajp/memoria.py` — memoria con la estructura del anexo I de la Orden ITC/1644/2011 (1.1 a 1.2.F)
  rellenada con el dimensionado. `python -m ict_ajp memoria proyecto.ict.json -o memoria.docx` saca Word
  y PDF (LibreOffice), con el índice paginado en dos pasadas.
- `ict_ajp/pliego.py` — pliego de condiciones (anexo I, apartado 3 de la Orden): productos del catálogo con
  sus cifras, apartados de las Normas que se cumplen, cuadros de medidas y normas generales.
  `python -m ict_ajp pliego proyecto.ict.json -o pliego.docx`.
- `docs/normativa/normas_generales.json` — título oficial y vigencia de las normas generales que cita el
  pliego (PRL, residuos, campos electromagnéticos, incendios...), comprobados en el BOE con
  `herramientas/normas_generales.py`. Nunca citar una norma general de memoria: añadirla ahí.
- `ict_ajp/pdf.py` — conversión a PDF con LibreOffice (instalado en este ordenador).
- `herramientas/boe_a_markdown.py` — pasa un XML del BOE a Markdown para `docs/normativa`.
- `ict_ajp/__main__.py` — `python -m ict_ajp calcular proyecto.ict.json -o resultado.xlsx` y
  `python -m ict_ajp leer-dxf plano.dxf -o lectura.txt` y
  `python -m ict_ajp borrador plano.dxf -o proyecto.ict.json` (plantas y viviendas del DXF) y
  `python -m ict_ajp planos proyecto.ict.json [--actualizar-longitudes]` (plantas de la ICT en DXF, PNG y PDF;
  con la opción, guarda en el proyecto las longitudes medidas para RTV y la medición de materiales).
- `docs/normativa/` — **textos consolidados oficiales del BOE** (RD 346/2011 actualizado hasta el
  RD 250/2025; Orden ITC/1644/2011; RD 250/2025 Plan Técnico Nacional de la TDT y su corrección de
  errores; Resolución de 23/07/2026 de la fase 1 de DVB-T2; planes técnicos de TDT local RD 439/2004,
  DAB RD 1287/1999 y FM RD 964/2006; Orden ECE/983/2019 de reacción al fuego de los cables). Son la única
  fuente para programar reglas.
- `ejemplos/edificio_prueba.ict.json` — edificio de prueba (18 viviendas, 2 locales).
- `tests/` — `pytest -q`. Las pruebas corren en Windows y Linux con GitHub Actions en cada subida.

## Reglas de trabajo

1. **Normativa solo desde `docs/normativa/`.** Nunca de memoria ni de resúmenes de internet (uno
   que se consultó tenía mal la tabla de dimensiones del RITI). Cada regla nueva lleva su
   referencia (`N.ref("III", "5.7.1")`) y pruebas en los límites de cada rango.
2. Cuando la norma deja algo a criterio del proyectista, no lo decidas en silencio: ponlo como
   opción en `OpcionesDiseno` con un valor conservador y genera un aviso `decision`.
3. RTV: atenuaciones y ganancias del **catálogo del fabricante** que se prescriba, no valores genéricos.
4. Presupuesto: precios de la base de precios que indique el proyectista. **No inventar precios.**
5. Planos: DXF (ezdxf). La ICT va en capas propias con prefijo `ICT_`, sin tocar las capas del
   arquitecto. Cada entrega de planos va con una imagen de vista previa.
6. Nombres de código, mensajes y documentos en español.
7. Antes de dar algo por terminado: `pytest -q` en verde y, si hay Excel/DXF/Word, abrir o
   renderizar el resultado y mirarlo.

## Hoja de ruta

| Versión | Contenido | Estado |
|---|---|---|
| 0.1 | Demanda, redes TBA (pares trenzados/pares, coaxial, fibra), red interior, infraestructura, recintos, Excel | Hecho |
| 0.2 | RTV (Anexo I, ap. 4): niveles, atenuaciones toma a toma, C/N, cabecera | Hecho salvo lo apuntado en `docs/pendiente.md` |
| 0.3 | Esquemas de principio en DXF | Pendiente |
| 0.4 | Memoria, pliego y presupuesto en Word (estructura del Anexo I de la Orden ITC/1644/2011) | En curso: memoria y pliego hechos; presupuesto pendiente (falta la base de precios) |
| 0.5 | Plantas sobre la base DXF del arquitecto | En curso: plantas, cubierta, hojas A3 y PDF hechos; lo que falta, en `docs/pendiente.md` |
| 1.0 | Interfaz de escritorio (PySide6) y .exe de Windows compilado con GitHub Actions | Pendiente |

## Criterios adoptados en v0.1 (revisables por el proyectista)

- Instalaciones comunes: 2 acometidas por tecnología para el edificio, dentro de la demanda a la
  que se aplica el factor 1,2.
- Reserva del 20 % de pares trenzados repartida por plantas, priorizando las de más demanda.
- Ascensor: 1 salida prevista por tecnología en el registro principal.
- Segunda estancia principal: se equipan los dos registros de pares trenzados (3 tomas).
- Tamaño del registro secundario: cuentan todas las plantas con PAU, incluida la planta baja.
- Sin consulta a operadores (se hace en el replanteo, art. 8.4) se proyectan las tres redes.
- El ático cuenta como altura para elegir RITU / RITU-A (`atico_cuenta_como_altura`).
- Con RITU, los 3 tubos de Ø32 mm desde la centralización de contadores van al RITU.
- Si se indica la altura libre del recinto (`altura_libre_riti_mm` / `altura_libre_rits_mm`), se
  propone el más estrecho que mantiene superficie frontal y fondo (5.5.1), sin bajar de la puerta
  de 180 x 80 cm (5.5).
- Recintos de obra por defecto. Los modulares (RITM) tienen las mismas medidas mínimas de 5.5.1.
- RTV: sin medidas, campo de diseño = mínimo de la norma (3 + 20 log f). Cabecera monocanal por
  defecto (`cabecera_rtv`); una programable solo si su ficha garantiza < 3 dB entre canales (Anexo I
  4.3; la de la Avant 12 no lo dice). Satélite: solo previsión.
- Estancias que cuentan para tomas: salón, comedor, cocina, dormitorios y estudio. No cuentan
  vestíbulos, pasos, lavaderos, vestidores ni espacios exteriores. La otra estancia con BAT doble
  es el dormitorio mayor.
- Planos: registros de toma en la pared de la estancia más cercana a su rótulo; RTR en la pared del
  vestíbulo (o, sin vestíbulo, de la estancia por la que se entra) más cercana al registro secundario, y la
  toma configurable a su lado (Anexo II 3.5 c). Tubos dibujados en «L» y medidos así más 1 m de subida o
  bajada en cada extremo (`planos.holgura_vertical_m`). La canalización principal, en la misma vertical en
  todas las plantas, y en planta baja unida al RITI. Arqueta de entrada 1,2 m fuera de la fachada en la
  dirección del RITI, a confirmar con la consulta a operadores.
