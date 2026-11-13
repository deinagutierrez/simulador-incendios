# E-E3-2 — Escala de reflectancia elegida antes de medir

Paso previo que fija el prerregistro (`E-E3-2_indices_aws.md`, §Diseño): "Antes de medir se resuelve con números la escala
de reflectancia … se prueba cada lectura contra (a) y se elige la que da el menor error; esa elección se anota antes de mirar
(b) y (c)". Escrito el 2026-11-13 por quien escribe el prerregistro (deinagutierrez, con Claude). **No es la evaluación**: la
hace LisandroV2002 con `herramientas/e_e3_2.py` (D-E3-25).

## Qué dicen los metadatos

En las escenas de Earth Search (por ejemplo `S2A_19HGD_20240913_0_L2A`, línea base 05.11) aparecen a la vez
`earthsearch:boa_offset_applied: true` y, en cada banda, `raster:bands.offset: -0.1` con `scale: 0.0001`.

## Prueba

Compuesto de ventana de Las Lagunas 2024 (30/07 a 16/09/2024 inclusive, la ventana `["2024-07-30", "2024-09-17")` de la
ficha), con el módulo `app/datos/sentinel2.py` tal como está en este cambio: 40 escenas en el catálogo, 32 después de
descartar teselas con más de 80 % de nubes, 8 fechas con datos. Pasado a 30 m con la función de v3.1 (`indices_a_grilla`,
promedio) y comparado con `ndvi_30m` y `ndmi_30m` del evento (GEE) en todas las celdas con dato en los dos.

| Lectura | Índice | Diferencia absoluta mediana | Percentil 95 | Diferencia mediana (AWS − GEE) |
|---|---|---|---|---|
| reflectancia = DN / 10000 | NDVI | 0,0053 | 0,022 | +0,0032 |
| reflectancia = DN / 10000 | NDMI | 0,0062 | 0,024 | −0,0034 |
| reflectancia = DN / 10000 − 0,1 | NDVI | 0,6056 | 1,076 | +0,5182 |
| reflectancia = DN / 10000 − 0,1 | NDMI | 0,2136 | 0,395 | −0,2133 |

## Elección

**Reflectancia = DN / 10000, sin restar 0,1** (`desplazamiento = 0`). Las escenas de Earth Search ya traen el desplazamiento
aplicado; el `offset` de los metadatos no hay que sumarlo. Queda como valor por defecto en `app/datos/sentinel2.py` y en la
procedencia de cada producto.

No se tocó nada más del método (máscara, umbral de nubes, remuestreo) después de ver estas cifras. Las partes (b) y (c) no se
miraron.
