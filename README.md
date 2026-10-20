# ICT-AJP

Herramienta de AJP Ingeniería para calcular y generar proyectos de **Infraestructura Común de
Telecomunicaciones** según el RD 346/2011 y la Orden ITC/1644/2011.

El motor de cálculo es independiente de la interfaz: se puede usar desde la línea de órdenes
mientras se desarrolla la aplicación de escritorio.

## Estado

| Versión | Contenido | Estado |
|---|---|---|
| 0.1 | Modelo de proyecto, previsión de demanda, redes de pares trenzados / pares, coaxial y fibra, red interior, infraestructura, exportación a Excel | Hecho |
| 0.2 | Cálculo de RTV (Anexo I): niveles, atenuaciones, C/N, cabecera | Pendiente |
| 0.3 | Esquemas de principio en DXF | Pendiente |
| 0.4 | Memoria, pliego y presupuesto en Word | Pendiente |
| 0.5 | Plantas sobre la base del arquitecto (DXF) | Pendiente |
| 1.0 | Aplicación de escritorio para Windows (.exe) | Pendiente |

## Uso

```
pip install -e .
python -m ict_ajp calcular ejemplos/edificio_prueba.ict.json -o resultado.xlsx
```

El proyecto se describe en un archivo `.ict.json` (ver `ejemplos/`). El Excel resultante lleva
cada cifra con su referencia normativa y una hoja de avisos con las decisiones que debe revisar
el proyectista.

## Normativa

Los textos consolidados del BOE usados para programar las reglas están en `docs/normativa/`
(RD 346/2011 actualizado hasta el RD 250/2025). Cada regla de `ict_ajp/normativa.py` indica su
anexo y apartado, y `tests/test_normativa.py` comprueba los límites de cada tabla.

**Responsabilidad:** la herramienta ayuda a dimensionar, pero el proyecto lo firma el proyectista,
que debe revisar los resultados y los avisos.
