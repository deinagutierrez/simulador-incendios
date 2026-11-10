# Etapa 3 — Pipeline reproducible de preparación de datos

Fecha: 2026-10-14. Implementa el diseño de la Etapa 2 (`docs/02_diseno_metodologico_etapa2.md`). Todo lo que se informa aquí fue ejecutado en este entorno; los tiempos y valores son los medidos.

## 1. Qué se implementó

Paquete instalable `incendios_sl` (`pyproject.toml`, `pip install -e . --no-deps`), con 24 pruebas unitarias que pasan (`python -m pytest -q`, 1,4 s, sin red).

| Módulo | Función | Estado |
|---|---|---|
| `src/incendios_sl/grilla.py` | Grilla maestra EPSG:5345 / 30 m (1.672 × 1.671), ampliación con margen múltiplo de 30 m, conversiones lon/lat ↔ fila/col, rasterización, alineación de rasters (`gdalwarp` equivalente vía rasterio), pendiente y orientación (Horn 3 × 3, convención azimut cuesta abajo) | probado |
| `src/incendios_sl/config.py`, `procedencia.py` | Carga de YAML (`config/`), rutas; JSON de procedencia por producto (hash SHA-256 de entradas y salida, parámetros, versión, fecha UTC) y reutilización solo si los parámetros coinciden | probado |
| `src/incendios_sl/data/preparar_dominio.py` | Máscara del dominio exacto; DEM (Copernicus GLO-30 vía GEE o ASTER provisto) + pendiente + orientación; cobertura MapBiomas 2021–2025 alineada; infraestructura recortada (GPKG, EPSG:5345); cicatriz mensual alineada; cicatriz de referencia del evento | ejecutado |
| `src/incendios_sl/remote_sensing/gee_comun.py`, `gee_dem.py`, `gee_indices.py` | Autenticación GEE (credenciales existentes, sin secretos en código); descarga recortada por teselas con `crs_transform` alineado; DEM GLO-30; compuestos NDVI/NDMI (mediana) con Cloud Score+, `n_obs`, metadatos de escenas; Landsat 8/9 como alternativa | ejecutado |
| `src/incendios_sl/meteorology/openmeteo.py` + `scripts/adquirir_meteo.py` | Malla 4 × 4 de puntos del modelo sobre dominio + margen, UTC, m/s, QC (rangos físicos, duplicados, huecos), promedio vectorial del viento, caché por hash, CSV + Parquet + JSON; script independiente con geometría/dominio/punto, fechas, variables, modelo, salida | ejecutado |
| `src/incendios_sl/wind/windninja.py` | Generación de `.cfg`, ejecución de `WindNinja_cli.exe` con registro (tiempo, memoria pico, stdout), lectura de `*_u.asc`/`*_v.asc`, biblioteca de campos unitarios por clase de dirección (NetCDF reanudable), composición horaria por escalado lineal e interpolación angular, remuestreo bilineal de U/V a 30 m | ejecutado (ver §2.6) |
| `src/incendios_sl/fuels/tabla.py`, `clasificacion.py`, `humedad.py` | Tabla de 8 clases locales v1 con parámetros S&B 2005 por analogía (SI), WAF de Baughman & Albini generalizado a 10 m, factor de dosel [HIPÓTESIS], `k_clase`; clasificación cobertura + NDVI con máscara de validez; FFMC horario (port de `cffdrs`) y humedades 1 h / 10 h / 100 h; LFMC desde NDMI [HIPÓTESIS] | ejecutado |
| `scripts/preparar_evento.py` | Orquestador por evento con manifiesto JSON de pasos, tiempos y errores | ejecutado |
| `scripts/obtener_indices.py` | Script independiente GEE (geometría o evento, fechas, colección, resolución, umbral de nubes, salida) | escrito |

## 2. Ejecución para `SL-2024-LASLAGUNAS` (dominio `las_lagunas_potrerillos`)

Comando: `python scripts/preparar_evento.py --evento SL-2024-LASLAGUNAS` (la biblioteca de viento se lanzó por separado). Manifiesto: `data/derivados/eventos/SL-2024-LASLAGUNAS/manifiesto_SL-2024-LASLAGUNAS.json`.

### 2.1 Dominio (17 s sin DEM; DEM 75 s)
- Máscara: **2.777.934 celdas dentro (2.500,14 km²)** de 2.793.912 de la grilla.
- DEM Copernicus GLO-30 ampliado (margen 10.020 m = 334 celdas): 2.340 × 2.339 px, 530,6–1.750,2 m, sin vacíos. En el dominio: 655,8–1.491,9 m (media 1.010,8 m). Pendiente p50 3,1°, media 4,3°, p99 21,6°, máx 57,2°. Orientación: −1 en celdas planas.
- Cobertura MapBiomas 2021–2025 alineada (vecino más cercano). Infraestructura recortada a dominio + 1 km: caminos 825 tramos, viviendas 325 entidades (capas `polygon` 246 y `point` 79), red MT 5.543 tramos.
- Cicatriz de referencia `2024_41914` rasterizada; cicatriz mensual 2022–2025 alineada.

Incidencia corregida: `mosaic().resample('bilinear')` en GEE sin fijar la proyección por defecto devuelve un raster constante (verificado: 917,2 m en todo el dominio); se corrigió con `setDefaultProjection`.

### 2.2 Meteorología (22 s)
- Fuente: Open-Meteo Historical Weather API, modelo `ecmwf_ifs` (análisis IFS 9 km). **No son observaciones.**
- 16 puntos (elevaciones del modelo 696–1.433 m), 2024-09-17 00:00 → 2024-10-10 03:00 UTC: **556 horas, 0 nulos, 0 fuera de rango, 0 huecos**.
- Serie del dominio (promedio; viento por promedio vectorial), días de propagación principal:

| Día (UTC) | T máx °C | HR mín % | Viento máx m/s | Viento medio m/s | Dir. mediana (desde) | Lluvia mm |
|---|---|---|---|---|---|---|
| 18/09 | 27,4 | 21,8 | 7,5 | 3,8 | 225 | 0 |
| 19/09 | 27,0 | **4,7** | 7,7 | 5,9 | 263 | 0 |
| 20/09 | 24,3 | 9,6 | 7,0 | 5,4 | 184 | 0 |
| 21/09 | 28,4 | 21,5 | 8,5 | 6,2 | 348 | 0 |
| 22/09 | 23,1 | 31,1 | 7,8 | 5,6 | 226 | 0 |
| 23/09 | 25,4 | 16,0 | 6,0 | 4,0 | 205 | 0 |
| 24/09 | 25,1 | 14,8 | 4,8 | 3,3 | 192 | 0 |

Lluvia total del periodo 36,7 mm (toda posterior al 24/09). Archivos en `data/derivados/meteo/` (`*_dominio.csv` es la serie que consume el simulador).

### 2.3 Índices satelitales (1.215 s)
- `COPERNICUS/S2_SR_HARMONIZED` + Cloud Score+ (`cs_cdf ≥ 0,6`), ventana 2024-07-30 → 2024-09-17 (anterior a la ignición), **40 escenas** (10 fechas × 4 teselas), compuesto por mediana, salida a 20 m sobre dominio + 1.020 m (2.610 × 2.608 px).
- Fechas y calidad: 03/09 (nubosidad 2,6 %), 08/09 (16 %), 04/08, 09/08, 24/08 buenas; 19/08 y 29/08 totalmente nubladas (excluidas por la máscara); 13/09 parcial.
- Cobertura válida **100 %**; observaciones válidas por píxel: mín 5, mediana 7, máx 32 (`n_obs`).
- NDVI: p5 0,16, mediana **0,24**, p95 0,36. NDMI: p5 −0,28, mediana **−0,21**, p95 −0,11. Valores bajos coherentes con vegetación seca de fin de invierno en año de sequía.
- El tiempo (20 min) lo domina el cálculo servidor de la mediana a 20 m; se reutiliza por caché.

### 2.4 Combustibles (1 s)
Tabla `data/derivados/combustibles/tabla_combustibles_v1.csv` (parámetros S&B 2005 convertidos a SI; WAF sin abrigo a 10 m: GR1 0,33, GR2 0,33, GS2 0,37, SH2 0,33, TU1 0,30, TL2 0,22, antes del factor de dosel).

Mapa `combustible_clase_SL-2024-LASLAGUNAS.tif` (cobertura 2023 + NDVI 2024 pre-incendio), % de la grilla:

| Clase | Nombre | % |
|---|---|---|
| 0 | no combustible (agua, urbano, desnudo, cultivo con NDVI < 0,15) | 1,2 |
| 1 | pastizal natural | 16,8 |
| 2 | pastura / cultivo | 12,8 |
| 3 | arbustal abierto | 20,7 |
| 4 | arbustal cerrado | 0,4 |
| 5 | bosque abierto | 30,6 |
| 6 | bosque cerrado | 17,6 |
| 7 | plantación | 0,0 |

Curado herbáceo: 80 % en la mayoría de las celdas herbáceas (NDVI < 0,35), 50 % en el resto [HIPÓTESIS]. 100 % de las celdas con índices válidos.

### 2.5 Humedad del combustible muerto
FFMC horario desde 85 el 17/09 00 UTC (1 día de inicialización):

| Día | m_1h mín % | m_1h máx % |
|---|---|---|
| 18/09 | 7,8 | 12,4 |
| 19/09 | 4,1 | 11,4 |
| 20/09 | 4,1 | 8,2 |
| 21/09 | 5,8 | 10,5 |
| 22/09 | 9,7 | 15,3 |

86 de 556 horas superan 15 % (humedad de extinción de los modelos GR), todas tras las lluvias de octubre (máx 24 h: 27 mm; m_1h llega a 242 %, tope físico del FFMC 250 %).

### 2.6 Biblioteca de viento WindNinja
Configuración: DEM Copernicus ampliado, malla 100 m, `brush`, salida 10 m, 72 direcciones a 10 m/s (campos divididos por 10 → unitarios), NetCDF `data/derivados/viento/viento_unitario_las_lagunas_potrerillos_100m_brush_<hash>.nc` (reanudable).

Incidencias corregidas: (1) el CLI 4.0.0 rechaza declarar juntos `momentum_flag` y `non_neutral_stability` ("Conflicting options") aunque sean `false`: se omiten (los valores por defecto son `false`); (2) el arranque del CLI hace una llamada HTTP (actualización THREDDS / call home) que, con la red ocupada por GEE, dejó el proceso bloqueado: se desactiva con `NINJA_DISABLE_CALL_HOME=TRUE` y `NINJA_DISABLE_THREDDS_UPDATE=TRUE`.

Incidencia (3): la versión inicial reescribía el NetCDF completo tras cada dirección; una lectura concurrente del archivo (monitoreo) sobre OneDrive produjo un `PermissionError` y dejó el archivo corrupto, perdiendo 37 direcciones. Se reescribió el módulo para guardar cada dirección en un `.npz` propio (`_campos_<clave>/`) y ensamblar el NetCDF al final de forma atómica (reanudable).

Resultado **[MEDIDO]**:
- 72 corridas, **35,1 s de media (máx 42,6 s), 5,76 GB de memoria pico**, ≈ 42 min en total. Archivo `viento_unitario_las_lagunas_potrerillos_100m_brush_c26e461c0ecb.nc` (169 MB, 72 × 702 × 703).
- Verificación: la dirección media de cada campo unitario difiere de la dirección de entrada ≤ 0,27°; la velocidad media unitaria del dominio es 0,989–0,991 (el solver conserva la masa; el relieve redistribuye, no añade energía).
- Campo horario real (19/09/2024 18 UTC, entrada IFS 4,47 m/s vectorial desde 272°): remuestreado a 30 m sin vacíos, velocidad 0,37–10,42 m/s (media 4,43, p99 5,26): aceleración hasta 2,3× en crestas y sotavento con desaceleración en valles (`docs/fig_etapa3_viento_2024-09-19_18Z.png`).

Figura de productos del evento: `docs/fig_etapa3_productos_SL-2024-LASLAGUNAS.png` (DEM, pendiente, clases de combustible, NDVI, NDMI, cicatriz y focos SNMF).

## 3. Reproducibilidad y caché
Cada producto tiene `<archivo>.json` con fuente, parámetros, hashes de entradas y salida, versión del código y fecha. `producto_vigente()` compara el hash de parámetros; solo se recalcula lo que cambió. El manifiesto del evento registra el estado y el tiempo de cada paso. Los archivos originales no se modifican.

## 4. Cómo incorporar un nuevo evento o área
1. Área: copiar `config/dominio_las_lagunas_potrerillos.yaml` con nuevo `id`, grilla alineada a 30 m en EPSG:5345 (xmin/ymin/xmax/ymax múltiplos de 30) y máscara (GeoJSON + filtro). Ejecutar `preparar_evento` genera DEM, derivados, cobertura e infraestructura.
2. Evento: copiar `config/eventos/SL-2024-LASLAGUNAS.yaml`: `oid` MapBiomas, fechas SNMF, hipótesis de ignición, ventana de índices anterior a la ignición, año de cobertura previo. Ejecutar `python scripts/preparar_evento.py --evento <id>`.
3. La biblioteca de viento se comparte entre eventos del mismo dominio (misma malla y vegetación).

## 5. Limitaciones registradas en esta etapa
- Meteorología de modelo (9 km) promediada sobre el dominio para T, HR y lluvia; la variación espacial solo entra por el campo de viento de WindNinja (inicialización uniforme).
- Índices: mediana de 7–32 observaciones a 20 m; sin corrección topográfica de iluminación; NDMI no es humedad del combustible.
- Clasificación de combustibles por reglas con umbrales de NDVI no validados; cargas por analogía.
- FFMC: modelo canadiense para litera de pino, aplicado sin calibración local; 10 h/100 h por desplazamiento fijo.
- WindNinja: un solo tipo de vegetación (`brush`), neutral, 100 m.
