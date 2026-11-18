# Formatos de carga manual

Qué archivos acepta la sección **1. Datos → Carga manual** del simulador y cómo tienen que estar armados. Los archivos de
ejemplo están en [`formatos_de_carga/`](formatos_de_carga/) y pasan los mismos controles que una carga real. Desde la
pantalla se abren en `http://127.0.0.1:8000/formatos/…`.

Los controles están en `app/datos/meteo.py` (`leer_csv_manual`, `_hora_a_hora`) y en `app/datos/indices.py`
(`leer_tif_manual`). Si este documento y el código no coinciden, manda el código.

## 1. Meteorología (CSV)

| | |
|---|---|
| Extensión | `.csv` (también `.txt`), separado por comas, con encabezado |
| Tamaño máximo | 20 MB |
| Filas | una por hora en punto, en orden, **al menos 24** |
| Huecos | se rellenan por interpolación hasta 2 horas seguidas; más de 2 horas sin dato se rechaza |
| Celdas vacías | no se aceptan |
| Horas repetidas | no se aceptan |

Se aceptan dos formatos. El programa reconoce cuál es por los nombres de las columnas.

### Formato de v4.0 (recomendado para cargar a mano)

| Columna | Qué es | Unidad | Rango |
|---|---|---|---|
| `timestamp` | fecha y hora **con huso horario** | ISO 8601, por ejemplo `2026-11-13T09:00:00-03:00` | — |
| `temp_c` | temperatura del aire a 2 m | °C | −40 a 50 |
| `hr_pct` | humedad relativa | % | 0 a 100 |
| `viento_kmh` | velocidad del viento a 10 m | km/h | 0 a 216 |
| `viento_dir_deg` | dirección **de donde viene** el viento | grados (0 = norte, 90 = este) | 0 a 360 |
| `precip_mm` | lluvia en la hora | mm | 0 a 200 |

Hora argentina: `-03:00` (sin horario de verano). Un `timestamp` sin huso se rechaza.

Ejemplo: [`ejemplo_meteorologia_v40.csv`](formatos_de_carga/ejemplo_meteorologia_v40.csv)

```
timestamp,temp_c,hr_pct,viento_kmh,viento_dir_deg,precip_mm
2026-11-13T09:00:00-03:00,24.0,40.0,18.0,330,0.0
2026-11-13T10:00:00-03:00,26.1,34.0,19.4,332,0.0
```

### Formato de v3.x (el de Open-Meteo)

| Columna | Qué es | Unidad | Rango |
|---|---|---|---|
| `time_utc` | fecha y hora en **UTC** | ISO 8601, por ejemplo `2026-11-13T12:00:00Z` | — |
| `temperature_2m` | temperatura del aire a 2 m | °C | −40 a 50 |
| `relative_humidity_2m` | humedad relativa | % | 0 a 100 |
| `wind_speed_10m` | velocidad del viento a 10 m | **m/s** | 0 a 60 |
| `wind_direction_10m` | dirección de donde viene el viento | grados | 0 a 360 |
| `precipitation` | lluvia en la hora | mm | 0 a 200 |

Ejemplo: [`ejemplo_meteorologia_v3x.csv`](formatos_de_carga/ejemplo_meteorologia_v3x.csv) (las mismas 48 horas que el
de v4.0).

**Para tener en cuenta.** Es una serie de un solo punto: se aplica igual a todo el dominio. La toma queda rotulada
«meteorología cargada a mano». Después de cargarla, el evento se arma en **Datos actuales → Opciones avanzadas**.

## 2. Índices de vegetación (GeoTIFF)

Dos archivos: uno de NDVI y uno de NDMI. Los dos con estas mismas características:

| | |
|---|---|
| Extensión | `.tif` o `.tiff` (GeoTIFF) |
| Tamaño máximo | 60 MB cada uno |
| Bandas | una |
| Sistema de coordenadas | EPSG:5345 (POSGAR 2007 / Argentina 3) |
| Grilla | la del dominio, exacta: celdas de 30 m, **1672 columnas × 1671 filas** |
| Esquina noroeste | x = 3 513 060, y = 6 417 900 (esquina sudeste: 3 563 220, 6 367 770) |
| Tipo de dato | `int16` |
| Escala | índice × 10 000 (−10 000 a 10 000 equivale a −1 a 1) |
| Sin dato | −32 768 (tiene que estar declarado como *nodata* del archivo) |

Fórmulas:

- NDVI = (B08 − B04) / (B08 + B04)
- NDMI = (NIR − B11) / (NIR + B11), con NIR = B08 (10 m) o B8A (20 m). La banda se elige en la pantalla.

Además hay que declarar la **ventana de fechas** de las imágenes (primer y último día). El programa revisa la grilla, la
escala y el rango, pero no puede comprobar de qué fechas son las imágenes ni con qué banda se calculó el NDMI: la corrida
queda rotulada «índices cargados a mano».

Ejemplos: [`ejemplo_ndvi.tif`](formatos_de_carga/ejemplo_ndvi.tif) y [`ejemplo_ndmi.tif`](formatos_de_carga/ejemplo_ndmi.tif).
**No son datos reales**: son un gradiente suave de oeste a este con una franja sin dato arriba. Sirven para probar la
carga y ver el formato, no para simular.

Para llevar un ráster propio a esta grilla con GDAL:

```
gdalwarp -t_srs EPSG:5345 -te 3513060 6367770 3563220 6417900 -tr 30 30 -r bilinear -ot Int16 -dstnodata -32768 entrada.tif salida.tif
```

(antes, multiplicar el índice por 10 000 si viene entre −1 y 1).

## 3. Modo escenario

No usa archivos: se cargan en la pantalla el día y la hora de inicio, la cantidad de horas (1 a 240), la temperatura
(−40 a 50 °C), la humedad (0 a 100 %), la lluvia (0 a 200 mm/h), el viento (0 a 216 km/h) y de dónde viene (0 a 360°).
Los valores quedan fijos durante todo el período.
