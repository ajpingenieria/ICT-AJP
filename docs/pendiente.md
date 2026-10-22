# Pendiente para la app

Cosas que se resolvieron de forma provisional para sacar adelante un proyecto real y que hay que
llevar a la app más adelante. Sin datos del cliente: solo qué falta y por qué.

| Fecha | Qué falta | Motivo |
|---|---|---|
| 2026-10-20 | Crear la carpeta del proyecto en Drive (número consecutivo y subcarpetas `PLANOS`, `MEMORIA`, `CALCULOS`) desde la app | Se creó a mano para no retrasar el proyecto |
| 2026-10-20 | Lectura DXF: asignar cada letra de puerta (A, B...) a su vivienda; ahora solo se listan por planta y las viviendas se numeran de izquierda a derecha | Las letras están en el rellano, entre dos contornos, y no se distinguen con seguridad |
| 2026-10-20 | Lectura DXF: leer las unidades del dibujo; ahora se supone que está en metros | El `$INSUNITS` de la base del arquitecto no era fiable (decía pies) |
| 2026-10-21 | Lectura DXF: detectar ascensores dibujados sin rótulo (hueco con puertas de cabina) y accesos a cubierta (escotillas) | En el proyecto real el ascensor no tenía texto y se encontró mirando la vista previa |
| 2026-10-21 | RTV: medir en los planos las longitudes antena-cabecera y cabecera-primer derivador | Las acometidas e interiores ya salen de las plantas (`planos --actualizar-longitudes`); estas dos siguen estimadas |
| 2026-10-21 | RTV: añadir al catálogo el mezclador TV/SAT de cabecera (Anexo I 3.2) y la mezcla de los T12 | No estaban entre las fichas descargadas; sus pérdidas no entran aún en el cálculo |
| 2026-10-21 | RTV: cálculo explícito de intermodulación (≥ 30 dB, Anexo I 4.5) y opción de antena en modo activo | Con monocanal cada amplificador lleva un canal; se justifica en la memoria, pero conviene calcularlo |
| 2026-10-21 | RTV: cálculo de niveles con central programable | Solo está programado para cabecera monocanal |
| 2026-10-21 | Catálogo: más fabricantes (Ikusi, Fagor) | Solo Televés por ahora |
| 2026-10-21 | Memoria 1.2.C: cálculo de atenuación de las redes de pares trenzados, coaxial y fibra (Orden, anexo I) | Necesita las longitudes de los planos; ahora sale como «[PENDIENTE]» |
| 2026-10-21 | Memoria 1.2.A.d: cálculo del mástil (momento flector con la carga al viento de las fichas) | Falta la ficha del mástil y la altura final de las antenas |
| 2026-10-21 | Memoria 1.2.E.l: cuadro resumen de materiales (tubos, registros) | Necesita las plantas de la ICT |
| 2026-10-22 | Planos: trazar los tubos por pasillos y puertas en lugar de en «L» directa | Hace falta leer muros y huecos de puerta; la medición en «L» es de proyecto |
| 2026-10-22 | Planos: rotular en cada tramo el número y diámetro de tubos (canalización principal, secundaria e interior) | Ahora solo lo dice la leyenda y la memoria |
| 2026-10-22 | Planos: proponer la posición del mástil (zona de cubierta con 5 m libres) en vez de darla con coordenadas | En el proyecto real se eligió mirando la cubierta y se guardó en `planos.mastil_xy` |
| 2026-10-22 | Planos: dibujar en cubierta el espacio reservado para las antenas de satélite | La memoria lo deja como «[PENDIENTE]» |
| 2026-10-22 | Memoria: tomar de los planos la ubicación del mástil y de los recintos y quitar sus marcas «[PENDIENTE]» | Los planos ya los tienen, pero la memoria aún no los lee |
| 2026-10-22 | Planos: la canalización principal se alinea entre plantas por la posición de los títulos de las vistas | Si el arquitecto desplaza una vista respecto a su título, revisar la vertical |
| 2026-10-22 | Planos: esquemas de principio (v0.3) | Pendiente después de las plantas |