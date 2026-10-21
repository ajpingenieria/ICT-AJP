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
- `ict_ajp/__main__.py` — `python -m ict_ajp calcular proyecto.ict.json -o resultado.xlsx` y
  `python -m ict_ajp leer-dxf plano.dxf -o lectura.txt` y
  `python -m ict_ajp borrador plano.dxf -o proyecto.ict.json` (plantas y viviendas del DXF).
- `docs/normativa/` — **textos consolidados oficiales del BOE** (RD 346/2011 actualizado hasta el
  RD 250/2025; Orden ITC/1644/2011). Son la única fuente para programar reglas.
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
| 0.2 | RTV (Anexo I, ap. 4): niveles, atenuaciones toma a toma, C/N, cabecera | Siguiente |
| 0.3 | Esquemas de principio en DXF | Pendiente |
| 0.4 | Memoria, pliego y presupuesto en Word (estructura del Anexo I de la Orden ITC/1644/2011) | Pendiente |
| 0.5 | Plantas sobre la base DXF del arquitecto | Pendiente |
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
- Estancias que cuentan para tomas: salón, comedor, cocina, dormitorios y estudio. No cuentan
  vestíbulos, pasos, lavaderos, vestidores ni espacios exteriores. La otra estancia con BAT doble
  es el dormitorio mayor.
