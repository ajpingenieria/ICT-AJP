# Pendiente para la app

Cosas que se resolvieron de forma provisional para sacar adelante un proyecto real y que hay que
llevar a la app más adelante. Sin datos del cliente: solo qué falta y por qué.

| Fecha | Qué falta | Motivo |
|---|---|---|
| 2026-10-20 | Crear la carpeta del proyecto en Drive (número consecutivo y subcarpetas `PLANOS`, `MEMORIA`, `CALCULOS`) desde la app | Se creó a mano para no retrasar el proyecto |
| 2026-10-20 | Lectura DXF: asignar cada letra de puerta (A, B...) a su vivienda; ahora solo se listan por planta y las viviendas se numeran de izquierda a derecha | Las letras están en el rellano, entre dos contornos, y no se distinguen con seguridad |
| 2026-10-20 | Lectura DXF: leer las unidades del dibujo; ahora se supone que está en metros | El `$INSUNITS` de la base del arquitecto no era fiable (decía pies) |
| 2026-10-21 | Lectura DXF: detectar ascensores dibujados sin rótulo (hueco con puertas de cabina) y accesos a cubierta (escotillas) | En el proyecto real el ascensor no tenía texto y se encontró mirando la vista previa |
| 2026-10-21 | Vista previa: algunos textos del arquitecto salen como cuadrados (fuente TrueType que no se encuentra) | Para revisar no molesta; para las entregas de planos hay que resolverlo |
| 2026-10-21 | RTV: medir en las plantas las longitudes de cable (antena-cabecera, acometidas, interiores) y recalcular | Ahora son estimaciones conservadoras con aviso de decisión |
| 2026-10-21 | RTV: añadir al catálogo el mezclador TV/SAT de cabecera (Anexo I 3.2) y la mezcla de los T12 | No estaban entre las fichas descargadas; sus pérdidas no entran aún en el cálculo |
| 2026-10-21 | RTV: cálculo explícito de intermodulación (≥ 30 dB, Anexo I 4.5) y opción de antena en modo activo | Con monocanal cada amplificador lleva un canal; se justifica en la memoria, pero conviene calcularlo |
| 2026-10-21 | RTV: cálculo de niveles con central programable | Solo está programado para cabecera monocanal |
| 2026-10-21 | Catálogo: más fabricantes (Ikusi, Fagor) | Solo Televés por ahora |
| 2026-10-21 | Memoria 1.2.C: cálculo de atenuación de las redes de pares trenzados, coaxial y fibra (Orden, anexo I) | Necesita las longitudes de los planos; ahora sale como «[PENDIENTE]» |
| 2026-10-21 | Memoria 1.2.A.d: cálculo del mástil (momento flector con la carga al viento de las fichas) | Falta la ficha del mástil y la altura final de las antenas |
| 2026-10-21 | Memoria 1.2.E.l: cuadro resumen de materiales (tubos, registros) | Necesita las plantas de la ICT |