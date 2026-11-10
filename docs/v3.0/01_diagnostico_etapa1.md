# Etapa 1 — Diagnóstico técnico de datos y viabilidad metodológica

Proyecto: simulador de propagación de incendios forestales para San Luis (autómata celular, 30 × 30 m).
Fecha del diagnóstico: 2026-10-14.
Directorio inspeccionado: `C:\Users\lisan\OneDrive\Documentos\Proyectos\Datos_SL_Completo`.
Scripts de inspección reproducibles: `scripts/inspeccion/01..03_*.py`. Catálogos generados: `data/catalogo/*.csv`.

Todo lo que sigue fue medido sobre los archivos reales o consultado en línea durante este diagnóstico. Donde algo es interpretación o hipótesis se indica explícitamente.

---

## 1. Resumen ejecutivo

| Pregunta previa (sección 21 del encargo) | Resultado |
|---|---|
| ¿`primero_cuadrado.geojson` representa 2.500 km²? | **Sí.** El polígono "dominio exacto" mide 2.500,16 km² en EPSG:5345 (2.500,06 km² geodésicos), lados de 50,00 km. No hace falta renombrar ni reducir. |
| ¿Hay incendios históricos útiles dentro del área? | **Sí.** 133 polígonos MapBiomas Fuego intersectan el área (2022–2025). El principal es **Las Lagunas–Potrerillos, 18/09/2024 → 09/10/2024**, 40.048 ha dentro del área (100 % contenido), con registros diarios SNMF y detecciones VIIRS/MODIS que acotan la ignición. Hay 3–4 eventos secundarios de 1.300–4.300 ha. |
| ¿Cobertura temporal de meteorología? | **Completa.** Open-Meteo Historical API responde para 2021–2026 en el área. ECMWF IFS (9 km, desde 2017), ERA5 (25 km) y ERA5-Land (11 km, sin viento vía API). |
| ¿Imágenes satelitales previas a los incendios? | **Sí.** Sentinel-2 SR (4 teselas cubren el área, revisita 5 días). Para el evento 2024: escenas 100 % despejadas el 03/09 y 08/09/2024, 10 y 15 días antes de la ignición. Landsat 8/9 también disponibles. |
| ¿Requisitos reales de WindNinja? | **No está instalado.** Versión actual 4.0.0 (31/08/2026, zip Windows x64 de 186 MB). CLI `WindNinja_cli.exe` con archivos `.cfg`. Requiere DEM proyectado y un valor único de vegetación por dominio (salvo LCP). Costo por hora de simulación: **no medido** aún (requiere instalación, ver §9). |
| ¿Viabilidad de NDVI/NDMI vía GEE? | **Verificada.** `ee.Initialize()` funciona con las credenciales existentes. Sentinel-2 SR Harmonized, Cloud Score+ y Landsat C2 L2 accesibles para el área. |
| ¿Capacidad de procesar millones de celdas? | **Viable.** Prueba vectorizada NumPy: 2.792.241 celdas, vecindad de 8, **134 ms por paso** sobre toda la grilla, 11,2 MB por capa float32. Hardware: Ryzen 5 8600G (6 núcleos/12 hilos), 31,2 GB RAM, 278 GB libres. |

**Conclusión:** no hay motivo para reducir el dominio de 2.500 km² por el autómata. El único costo no cuantificado es WindNinja (instalación pendiente de autorización de descarga).

---

## 2. Entorno de cómputo y herramientas

| Elemento | Estado verificado |
|---|---|
| Hardware | AMD Ryzen 5 8600G, 6 núcleos / 12 hilos, 31,2 GB RAM (22 GB libres), disco C: 278 GB libres. Windows 11 Home. |
| Python | 3.14.2 (único intérprete; sin conda). Instalados: numpy 2.5.2, pandas 3.0.5, rasterio 1.5.1, geopandas 1.1.4, shapely 2.1.2, pyproj 3.8.0, earthengine-api 1.7.43, requests 2.34.2. |
| Faltantes con rueda binaria disponible para 3.14 (verificado con `pip download --only-binary`) | scipy, numba, llvmlite, fastapi, uvicorn, pytest, psutil, xarray, rioxarray, matplotlib, openmeteo-requests, requests-cache, retry-requests, netCDF4, zarr, scikit-image. |
| GDAL de línea de comandos | No está en PATH. Disponible vía QGIS 3.44.14: `C:\Program Files\QGIS 3.44.14\bin\gdalinfo.exe` → **GDAL 3.13.3**. Útil para `gdalwarp`, `gdaldem`, `gdal_translate`. |
| WindNinja | **No instalado.** Sin Docker. Ver §9. |
| GEE | `~/.config/earthengine/credentials` con `refresh_token` y `project`. Inicialización correcta en 2,4 s. Las credenciales no se copiarán al código ni al repositorio. |
| Open-Meteo | API de archivo histórico operativa sin clave. Límite gratuito no comercial: 600 llamadas/min, 5.000/h, 10.000/día (términos de uso), licencia CC-BY 4.0. Uso académico en institución pública encaja en no comercial. |

---

## 3. Área de estudio: `primero_cuadrado.geojson`

### 3.1 Estructura real del archivo

El archivo **no es un único polígono**: es un FeatureCollection de **27 entidades**, en EPSG:4326 (sin miembro `crs`, asumido WGS84 por GeoJSON):

| Entidad | `tipo` | Contenido |
|---|---|---|
| 0 | `dominio_exacto_25_celdas` | Polígono de 200 vértices, nombre "Las Lagunas-Potrerillos", lados de 50.000,8 m, 2.500,1 km² (atributos). Departamentos: Libertador Gral. San Martín 85 %, Chacabuco 12 %, Junín 3 %. |
| 1 | `bbox_rectangulo_en_epsg5345` | Rectángulo alineado a 30 m en EPSG:5345: xmin 3.513.060, ymin 6.367.770, xmax 3.563.220, ymax 6.417.900; 1.672 col × 1.671 fil = **2.793.912 celdas**. Nota del autor: el cuadrado se construyó con meridiano central −65,75° y queda rotado ≈0,14° respecto de faja 3 (meridiano −66°). |
| 2–26 | `celda_grilla_10km` | 25 celdas de 10 km (F06–F10 × C08–C12) con conteos SNMF por celda. |

### 3.2 Verificación geométrica (entidad 0)

| Medición | Valor |
|---|---|
| Validez | Geometría válida (shapely), sin autointersecciones. |
| Bounds (lon/lat) | −65,8602 / −32,8316 → −65,3262 / −32,3800 |
| Centroide | −65,5936°, −32,6062° |
| Longitud geodésica de cada uno de los 200 segmentos | 1,000 km (WGS84, pyproj Geod) |
| Área geodésica | **2.500,06 km²**, perímetro 200,00 km |
| Área en EPSG:5345 (POSGAR 2007 / Argentina faja 3) | **2.500,16 km²** (distorsión 0,004 %) |
| Área en ESRI:102033 (Albers Sudamérica, equivalente) | 2.500,07 km² |
| Área en EPSG:32720 (UTM 20S) | 2.501,72 km² |
| Área en EPSG:3857 | 3.533 km² (no usar para superficies) |
| Bbox en EPSG:5345 | 50.119 × 50.119 m (incluye la rotación de 0,14°) |
| Celdas de 30 m dentro del polígono (área / 900 m²) | **2.777.954** |
| Celdas de 30 m en el bbox alineado | 1.671 × 1.671 = 2.792.241 (cálculo propio) / 1.672 × 1.671 = 2.793.912 (entidad 1, con holgura) |

**Conclusión:** el archivo representa efectivamente 2.500 km² y ~2,78 millones de celdas. El dominio de simulación es la entidad 0; la grilla raster se definirá sobre la entidad 1 (rectángulo alineado a 30 m), marcando como "fuera de dominio" las ~16.000 celdas del borde rotado (0,6 %).

### 3.3 Sistema de coordenadas de trabajo

Se propone **EPSG:5345 (POSGAR 2007 / Argentina faja 3, Gauss-Krüger, meridiano −66°)**. Razones: oficial en Argentina (IGN), unidades en metros, el área está a solo 0,41° del meridiano central (distorsión de escala < 0,01 %), y el bbox ya provisto está en ese sistema. Toda superficie, pendiente y distancia se calculará en este CRS.

---

## 4. Capas raster

### 4.1 Modelo digital de elevación — `Topografia/MDT_ASTER GDEM.tif`

| Propiedad | Valor medido |
|---|---|
| Formato | GeoTIFF, 670 MB, sin compresión, sin teselado (bloques de 1 fila), con overviews externos `.ovr` (2–64) |
| CRS | **EPSG:3395 (World Mercator)** — no es el CRS nativo de ASTER GDEM (que se distribuye en EPSG:4326, 1"); el archivo fue reproyectado por alguien antes de llegar aquí. |
| Tamaño | 9.545 × 17.553 píxeles; cubre toda la provincia (−67,44/−36,53 → −64,16/−31,51) |
| Resolución nominal | 38,2185 m en unidades Mercator. A latitud −32,6° la escala de Mercator es 1/cos(φ) = 1,187, por lo que la **resolución efectiva en terreno es ≈ 32,2 m** (comparable a 1" ≈ 30,9 m N-S / 26,0 m E-O). |
| Tipo / NoData | int32 (metros enteros), NoData = −32767 |
| Dentro del área | 1.555 × 1.556 px; elevación 656–1.510 m (mediana 983 m); **12.557 píxeles NoData (0,52 %)** distribuidos por todo el cuadrado (vacíos típicos de ASTER GDEM). |
| Pendiente (gradiente simple) | mediana 4,5°, p90 10,1°, p99 21°, máximo 60° |
| `AREA_OR_POINT` | Point |

Limitaciones conocidas de ASTER GDEM (cualquier versión): ruido de alta frecuencia y artefactos ("mole runs") en zonas planas, vacíos rellenados o no, sesgo vertical de varios metros, y en este archivo una reproyección previa a Mercator con remuestreo no documentado. Para pendiente y orientación a 30 m el ruido se traduce en pendientes espurias de varios grados.

**Decisión pendiente (usuario):** usar este DEM tal cual (rellenando los vacíos) o compararlo/reemplazarlo por un DEM de referencia de 30 m descargable para el área vía GEE (Copernicus DEM GLO-30 `COPERNICUS/DEM/GLO30_2024_1`, NASADEM o SRTM 1"; todos verificados accesibles, escala nominal 30,92 m). El recorte del área ocuparía ~10 MB. Recomendación: mantener ASTER como capa provista, pero generar el Copernicus GLO-30 del área y cuantificar la diferencia antes de derivar pendientes; elegir con datos.

### 4.2 Cobertura del suelo — `Uso_Cobertura_Suelo/Coleccion_3/mapbiomas_col3_sanluis_{2021..2025}.tif`

| Propiedad | Valor medido |
|---|---|
| Fuente | MapBiomas Argentina Colección 3 (metadatos: URL pública de GCS, recorte por ventana sin remuestreo) |
| CRS / grilla | EPSG:4326, píxel 0,00026949° (≈ 30,0 m N-S × 25,3 m E-O a esta latitud), 9.697 × 15.532, misma grilla en los 5 años y en los rasters de fuego |
| Tipo / NoData | uint8, NoData = 0; teselado 512, LZW, overviews |
| Leyenda | `leyenda_col3.csv`: 20 clases con campo `quemable` (1/0) ya definido por el autor del dataset |
| Periodo | 2021–2025 (anual) |

Composición dentro del área (porcentaje de píxeles, 3.307.011 px por año):

| Clase (código) | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| Bosque cerrado (3) | 18,1 | 18,1 | 17,5 | 17,7 | 15,6 |
| Bosque abierto (4) | 27,7 | 29,2 | 30,6 | 32,0 | 35,5 |
| Herbáceas / pastizal (12) | 16,0 | 16,5 | 16,8 | 16,8 | 18,1 |
| Arbustal abierto (77) | 21,5 | 19,5 | 19,0 | 17,1 | 13,7 |
| Pasturas (15) | 8,0 | 7,6 | 8,5 | 8,0 | 9,0 |
| Cultivos temporarios (19) | 5,1 | 5,6 | 4,9 | 5,7 | 5,6 |
| Mosaico arbustos/herbáceas (63) | 1,5 | 1,5 | 1,7 | 1,5 | 1,3 |
| Arbustal cerrado (66) | 1,4 | 1,4 | 0,4 | 0,4 | 0,4 |
| Agua (33) | 0,4 | 0,4 | 0,4 | 0,5 | 0,5 |
| Urbano (24), no vegetado (25), silvicultura (9), herb. inundables (11) | < 0,3 cada una | | | | |

El 97 % del área es vegetación natural o pastura potencialmente combustible. Solo hay 13 clases presentes. Las clases no describen carga, estructura ni humedad del combustible (ver §8).

### 4.3 Cicatrices de fuego raster — `Fuego_MapBiomas/Coleccion_1/fuego_{anual,mensual}_sanluis_2022_2025.tif`

| Propiedad | Valor medido |
|---|---|
| Grilla | Idéntica a la de cobertura (EPSG:4326, 0,00026949°). Remuestreo vecino más cercano desde EPSG:3857 30 m en GEE (metadato). |
| Bandas | 4 (2022–2025). Anual: 1 quemado / 0 no / 255 fuera de provincia. Mensual: mes 1–12 / 0 / 255. uint8, NoData 255. |

Píxeles quemados dentro del área y mes dominante:

| Año | Píxeles quemados | % del área | Meses principales (px) |
|---|---:|---:|---|
| 2022 | 121.438 | 3,7 | sep 55.022, ene 29.913, oct 14.548, nov 9.210 |
| 2023 | 41.180 | 1,2 | oct 21.946, sep 8.290, ago 6.320 |
| 2024 | **547.210** | **16,5** | **sep 534.833** |
| 2025 | 4.284 | 0,1 | disperso |

Un píxel de esta grilla equivale a ~0,0757 ha a esta latitud (no 0,09 ha); 534.833 px ≈ 40.500 ha en septiembre de 2024.

---

## 5. Capas vectoriales

Todas en EPSG:4326, geometrías válidas (salvo 6 líneas MT inválidas), extensión provincial.

| Capa | Entidades | Geometría | Atributos útiles | Dentro del área |
|---|---:|---|---|---:|
| `incendios_mapbiomas_fuego_sanluis.gpkg` (capa `incendios`) | 2.679 | MultiPolygon | `oid`, `area_ha`, `calendar_year`, `fire_year`, `date_min/med/max`, `p_mean`, `p_width`, `seed_mean`, `area_ha_sl`, `frac_en_sl` | **133** |
| `..._{2022..2025}.gpkg` | 857/605/542/675 | idem | subconjuntos anuales del anterior | — |
| `caminos_sanluis_integrado.geojson` | 61.665 | LineString | `fuente` (SIG_SL/OSM/IGN), `clase` (calle, camino, ruta, senda, servicio, huella, autopista, ferrocarril), `jerarquia` 1–10, `superficie` (tierra/pavimentado/consolidado/desconocido 71 %), `dup_probable` (47 % marcados como duplicados probables entre fuentes) | 736 tramos, 2.419 km viales + 4,4 km FFCC |
| `viviendas_sanluis_integrado.geojson` | 24.501 | mixta: 19.523 polígonos (edificaciones), 4.864 puntos, 112 multipolígonos | `tipo` (edificacion / area_residencial / lugar_poblado), `uso_residencial` (si/probable/no/abandonada), `area_m2`, `fuente` OSM/IGN | 305 |
| `departamentos_san_luis_ign_conae.geojson` | 9 | Polygon | `departamento`, `cabecera` | 5 intersectan |
| `Electricidad/red_distribucion_MT_EDESAL_SL.geojson` | 88.387 | LineString | solo `tension_kv` (13,2 / 33 / 7,62) | **5.391** |
| `Electricidad/lineas_transmision_electrica_SL.geojson` | 20 | MultiLineString | `tension_kv` 132/500, `propiedad` | 0 |
| `Electricidad/estructuras_cables_AT_SL.geojson` | 489 | Point | `id_linea` | 0 |
| `Electricidad/estaciones_transformadoras_AT_MT_SL.geojson` | 1 | Point | ET Luján 500/132 kV | 0 |
| `Electricidad/centrales_generacion_SL.geojson` | 16 | Point | tecnología | 0 |

Observaciones:
- Dentro del área solo existe **red de media tensión** (EDESAL). No hay alta tensión. La capa MT no tiene fecha ni identificador de línea.
- Caminos: el 71 % no tiene superficie conocida; la jerarquía y la clase sí están completas. La deduplicación entre SIG_SL y OSM está marcada pero no resuelta.
- Viviendas: la mezcla de polígonos de edificaciones y "áreas residenciales" (polígonos de hasta 21 km²) obliga a separar por `tipo` antes de cualquier análisis de exposición.
- Interpretación de los atributos MapBiomas (`date_min/med/max`, `p_mean`, `p_width`, `seed_mean`): **no documentada localmente** ni localizada en línea durante este diagnóstico. Por su comportamiento (p. ej. evento 2024: `date_min` 03/05, `date_med` 16/09, `date_max` 20/04/2025) se interpretan como fechas mínima/mediana/máxima de detección de los píxeles del polígono y probabilidad media del clasificador; `date_med` coincide bien con la fecha real en los eventos grandes. **Esto es una hipótesis a confirmar con la documentación de MapBiomas Argentina Fuego Col. 1.** Las fechas de MapBiomas no sirven como inicio/fin del incendio.

### 5.1 Registros SNMF — `registros_incendios_san_luis_2020-2026(SNMF).csv`

787 filas (UTF-8 con BOM), 21 columnas. Son **reportes diarios** (una fila por día y por incendio), no eventos: `fecha_reporte`, `fecha_inicio`, `fecha_extincion` (62 % vacía), `nombre`, `departamento`, `estado` (Activo/Contenido/Controlado/Extinguido), coordenadas (todas válidas), `observaciones` (texto con superficie y recursos, parcialmente parseable). Procedencia: archivos anuales `incendios_san_luis_{2020..2026}.csv`.

Las columnas `superficie_ha_sat`, `evento_sat`, `confianza_sat`, `comparte_evento_sat`, `fila_para_totales`, `fuente_superficie` ("Sentinel-2 L2A dNBR anclado en focos VIIRS SNPP") **no son del SNMF**: son un posprocesamiento añadido por quien compiló el archivo (186 filas). Se usarán solo como referencia secundaria, nunca como cicatriz de validación.

Dentro del área: **100 reportes → 40 eventos únicos** (nombre + fecha de inicio), 2021–2025. Catálogo: `data/catalogo/eventos_snmf_en_aoi.csv`.

---

## 6. Catálogo de incendios candidatos

Cruce de polígonos MapBiomas (área dentro del dominio, en EPSG:5345), reportes SNMF a ≤ 2 km y ± 15 días, y detecciones MODIS (colección `FIRMS` en GEE) y VIIRS (LANCE SNPP/NOAA-20 en GEE).

| Rango | `oid` MapBiomas | ha en área (% del polígono) | Evento SNMF asociado | Inicio SNMF | Extinción SNMF | Hotspots MODIS en área | Confianza temporal |
|---|---|---:|---|---|---|---|---|
| **1** | **2024_41914** | **40.048 (100 %)** | LAS LAGUNAS / POTRERILLOS / LAS LAGUNAS POTRERILLOS (24 reportes diarios, 2 focos informados) | **2024-09-18** | **2024-10-09** (último "Controlado" 08/10, 48.226 ha informadas) | 18/09 (66 px), 19/09 (250), 20/09 (528), 21/09 (201), 22–24/09, 29/09 | **Alta** para fecha de inicio y fin; hora acotada por VIIRS (ver abajo) |
| 2 | 2022_43667 | 4.270 (100 %) | PLANTA PISCU YACU (27–29/08), RUTA 40 Junín (30–31/08), RENCA SAN FELIPE (07–11/09): **3 eventos SNMF dentro del mismo polígono** | 2022-08-27 / 08-30 / 09-07 | 08-29 / 08-31 / 09-11 | 28/08 (41), 30/08 (12), 02/09, 06/09 (88), 07–08/09 | Media: el polígono MapBiomas fusiona varios eventos; habría que separarlos con el raster mensual + hotspots |
| 3 | 2021_46201 | 2.103 (100 %) | PJE. PUERTAS COLORADAS (punto a 922 m del polígono) | 2022-01-12 | 2022-01-16 | 12/01 (12), 13/01 (59), 14/01 (110), 15/01 | Media-alta (verano, posible distinta estacionalidad de combustibles) |
| 4 | 2024_41959 | 549 (**16 %**; 3.461 ha totales) | PASO GRANDE (1.945 ha sat.) | 2024-09-03 | 2024-09-12 | 03–06/09 | Alta, pero **84 % del polígono queda fuera del dominio** → no apto como validación salvo ampliar el dominio |
| 5 | 2023_26601 | 1.336 (100 %) | LAS CHACRAS (1.042 m; superficie sat. informada 72,7 ha, inconsistente con 1.336 ha) | 2023-10-19 | 2023-10-23 | 17–19/10 (51, 20, 29) | Baja-media: discrepancia de superficie |
| 6 | 2022_43580 | 509 | sin reporte SNMF a ≤ 2 km | — | — | 01/10/2022 (26) | Solo prueba espacial |
| 7–133 | resto | < 500 ha cada uno (107 polígonos < 50 ha) | mayoritariamente sin reporte | | | | Prueba espacial o descartados |

Superficie MapBiomas dentro del área por año: 2022: 9.182 ha (52 polígonos); 2023: 3.105 ha (28); 2024: 41.375 ha (32); 2025: 311 ha (21).

### 6.1 Ficha preliminar del evento principal: Las Lagunas–Potrerillos (2024)

| Campo | Valor | Fuente |
|---|---|---|
| Identificador propuesto | `SL-2024-LASLAGUNAS` (MapBiomas `2024_41914`; SNMF evento_sat `2024-003`) | — |
| Inicio | **2024-09-18** (fecha). Primera detección satelital: VIIRS NOAA-20, `acq_time` 62760 s ≈ **17:26 UTC (14:26 hora Argentina)**, píxeles en (−65,690, −32,624) y (−65,627, −32,637); SNPP a 18:43 UTC con frente ya activo en (−65,70, −32,64) con FRP 86 MW. MODIS del mismo día: 66 px entre −65,73 y −65,58. | SNMF (24 reportes); GEE `NASA/LANCE/NOAA20_VIIRS/C2`, `NASA/LANCE/SNPP_VIIRS/C2`, `FIRMS` |
| Hora de ignición | **No documentada.** Acotada a antes de las 14:26 hora local del 18/09 (puede ser la madrugada o la mañana). Hipótesis a declarar en Etapa 6. La interpretación de `acq_time` como segundos desde 00 UTC es coherente con el horario de paso de NOAA-20 pero debe confirmarse con la documentación del dataset. |
| Puntos de ignición informados | SNMF: "LAS LAGUNAS" (−65,5477, −32,6367) y "POTRERILLOS" (−65,6232, −32,6422). El segundo coincide (≈ 0,5 km) con la primera detección NOAA-20. **No se asume que sean los puntos exactos de origen.** | SNMF |
| Fin documentado | 2024-10-09 ("Extinguido", `fecha_extincion`); "Contenido" desde 28/09; "Controlado" 08/10. La propagación principal ocurrió 18–24/09 según hotspots. | SNMF, MODIS |
| Superficie | MapBiomas: 40.048 ha (100 % dentro del dominio, a 3,4 km del borde más cercano; 1 polígono multiparte). SNMF: 48.226 ha informadas; dNBR del compilador: 25.437 ha (parcial, hasta 26/09). | MapBiomas, SNMF |
| Meteorología | Disponible (Open-Meteo, IFS 9 km / ERA5). Viento ERA5-Land el 18/09: del S-SO débil (< 2 m/s) de madrugada, giro a **norte 5–7 m/s desde las 15 UTC** (coherente con avance hacia el sur). | Open-Meteo, GEE ERA5-Land |
| Imágenes previas | Sentinel-2 100 % despejadas sobre todo el bbox el **03/09 y 08/09/2024** (también 09/08, 04/08, 30/07). Falta comprobar 13/09. | GEE S2 SR Harmonized + Cloud Score+ |
| Cobertura del suelo pre-incendio | MapBiomas 2024 (clasificación anual; su año de referencia puede incluir meses posteriores al incendio → usar 2023 como estado pre-fuego y 2024 solo para contraste). | MapBiomas Col. 3 |
| Mitigación | Hubo combate (SNMF informa bomberos); la simulación sin mitigación sobreestimará por construcción. | SNMF |
| Limitaciones | Hora de ignición desconocida; dos focos; la cicatriz MapBiomas es anual-mensual y puede incluir quemas pequeñas vecinas de septiembre; superficies informadas difieren 20 %. | — |

---

## 7. Fuentes externas verificadas

### 7.1 Open-Meteo (archivo histórico)

| Modelo (`models=`) | Resolución | Punto de grilla devuelto para el centroide | Variables con datos en la prueba (05–08/09/2024) |
|---|---|---|---|
| `best_match` / `ecmwf_ifs` | 9 km (desde 2017) | −32,654 / −65,634, 1.036 m | todas: T2m, HR, viento 10 m y 100 m (vel., dir., ráfagas), precipitación, radiación, VPD, punto de rocío, presión, ET0, humedad de suelo |
| `era5` | 0,25° (~25 km, desde 1940) | −32,5 / −65,5 | todas |
| `era5_land` | 0,1° (~11 km, desde 1950) | −32,6 / −65,6 | **solo** T2m, HR, VPD, punto de rocío, humedad de suelo; **viento, precipitación y radiación vienen nulos** |

- Cobertura temporal comprobada: 2021-12-20, 2022-01-01 y 2026-10-01..10 devuelven 100 % de horas válidas.
- Zona horaria: `timezone=UTC` devuelve ISO 8601 sin desfase; se guardará en UTC y se convertirá a `America/Argentina/San_Luis` (UTC−3) solo para presentación.
- Unidades solicitadas: `wind_speed_unit=ms`, temperatura °C, precipitación mm, radiación W/m².
- **Convención de dirección del viento verificada empíricamente**: comparando 24 horas de `wind_direction_10m` (modelo `era5`) con componentes U/V de ERA5-Land en GEE, 23 de 24 horas coinciden con la convención **meteorológica (dirección DESDE la que sopla)**. El simulador deberá sumar 180° para obtener la dirección de avance.
- Variación espacial: la altitud de los 4 puntos ERA5-Land que rodean el área va de 687 m a 1.420 m; el modelo de 9 km tiene ~30 puntos de grilla sobre el dominio + margen. Una sola coordenada **no** representa el dominio; se propone muestrear una malla de puntos del modelo (p. ej. 4 × 4) y entregarlos a WindNinja como pseudo-estaciones (inicialización por puntos) o usar el promedio ponderado por hora.
- Los datos son **reanálisis / análisis de modelo**, no observaciones. Se documentará así en todos los metadatos.

### 7.2 Google Earth Engine

| Colección | Verificación |
|---|---|
| `COPERNICUS/S2_SR_HARMONIZED` | 4 teselas MGRS cubren el área (19HGD, 19HGE, 20HKJ, 20HKK); ~32 escenas por ventana de 40 días; bandas B4 (10 m), B8 (10 m), B11 (20 m), SCL, MSK_CLDPRB; baseline 05.11 (BOA offset ya armonizado). |
| `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | Disponible; banda `cs_cdf` usada para fracción despejada por escena. |
| `LANDSAT/LC08/C02/T1_L2`, `LC09` | 8–12 escenas por ventana de 40 días; path/row 229/082–083. |
| `FIRMS` (MODIS, 1 km, diario) | Disponible 2022–2024; sin hora de paso. |
| `NASA/LANCE/SNPP_VIIRS/C2`, `NOAA20_VIIRS/C2` (375 m) | Disponibles para septiembre 2024 con `acq_time`, `frp`, `confidence`. |
| `NASA/VIIRS/002/VNP14A1` | Disponible (diario, 1 km). |
| `ECMWF/ERA5_LAND/HOURLY` | Disponible (usado para verificar convención de viento). |
| DEM: `USGS/SRTMGL1_003`, `NASA/NASADEM_HGT/001`, `COPERNICUS/DEM/GLO30(_2024_1)` | Accesibles, 30,9 m. |

Exportación: el cálculo de NDVI/NDMI se hará en GEE y se descargará solo el recorte (≈ 2.800 × 2.800 px a 20 m, < 50 MB por índice).

### 7.3 WindNinja

| Aspecto | Verificado |
|---|---|
| Última versión | **4.0.0**, publicada 2026-08-31. Activo: `firelab-WindNinja-4.0.0-win64.zip` (186,4 MB, GitHub Releases). Versión previa 3.12.2 (2026-03-17). |
| Novedades 4.0.0 relevantes | GUI Qt6; **admite DEM con proyecciones que no sean "north-up"**; **nueva API en C**; corrección de NoData en GDAL; GDAL 3.12.4 / NetCDF 4.9.3 embebidos. |
| Interfaz | `WindNinja_cli.exe` (carpeta `bin` de la instalación). Opciones por línea de comandos o archivo `.cfg` (`opcion = valor`); la línea de comandos sobreescribe el `.cfg`. Ejemplos oficiales en `etc/windninja/example-files` (`cli_domainAverage.cfg`, `cli_momentumSolver_diurnal.cfg`, `cli_pointInitialization*.cfg`, `cli_wxModelInitialization*.cfg`). |
| Entradas obligatorias | `elevation_file`, `initialization_method`, `output_wind_height` + unidades, `vegetation` (grass / brush / trees, **un solo valor para todo el dominio** salvo archivo LCP), `mesh_resolution` + `units_mesh_resolution` o `mesh_choice` (coarse/medium/fine). |
| Inicialización por hora | `domainAverageInitialization` con `input_speed`, `input_speed_units`, `input_direction`, `input_wind_height` (viento uniforme) — una ejecución por hora; o `pointInitialization` con `wx_station_filename` (varias estaciones con serie temporal) — permite usar puntos del modelo meteorológico como pseudo-estaciones. Los modelos meteorológicos descargables (`wxModelInitialization`) son solo de EE. UU./globales GFS actuales, no sirven para reconstrucción histórica. |
| Solver | Conservación de masa por defecto (`momentum_flag = false`); `momentum_flag = true` activa OpenFOAM (mucho más costoso). Opcionales: `diurnal_winds`, `non_neutral_stability` (requieren fecha/hora, temperatura, nubosidad). |
| Salidas | `write_ascii_output = true` → grillas ASCII de velocidad y dirección (`ascii_out_resolution`); también shapefile, KMZ, `write_farsite_atm`. |
| No verificado | Tiempo de ejecución por hora para un dominio de 50 × 50 km + margen con malla ≤ 100 m; comportamiento del solver de masa con el DEM ASTER (ruido); límite práctico de resolución de malla. |

Interpretación propia: con malla de 30 m el dominio tendría ≥ 2,8 M nodos por capa; WindNinja (conservación de masa) suele usarse con mallas de 50–200 m en dominios de este tamaño. Lo esperable es ejecutar a 60–100 m y remuestrear bilinealmente a 30 m documentando que la resolución efectiva del viento es la de la malla, no 30 m.

---

## 8. Viabilidad del mapa de combustibles (evaluación preliminar)

| Variable disponible | Qué aporta | Qué no aporta |
|---|---|---|
| Cobertura MapBiomas (13 clases presentes) | Tipo de vegetación dominante (bosque cerrado/abierto, arbustal, pastizal, pastura, cultivo), continuidad espacial a 30 m, cambios anuales | Carga (t/ha), altura, relación vivo/muerto, humedad, estructura vertical |
| NDVI (S2 10 m / Landsat 30 m) | Verdor / fracción de vegetación verde; distingue pastizal seco vs verde; detecta cultivos y suelo desnudo | No separa carga de combustible muerto (un pastizal curado tiene NDVI bajo y mucha carga fina) |
| NDMI (S2 20 m / Landsat 30 m) | Proxy del contenido de agua del dosel (sensible al SWIR); útil como estado relativo de humedad de combustible vivo | No es porcentaje de humedad del combustible muerto fino, que depende de la meteorología horaria |
| DEM, pendiente, orientación | Efecto directo en velocidad de propagación y exposición solar | Nada sobre el combustible en sí |
| Meteorología horaria | Humedad del combustible muerto fino (modelable con T, HR, radiación, lluvia) | — |

Conclusión preliminar: la combinación permite un **mapa de clases locales provisionales** (p. ej. pastizal, pastura/cultivo, arbustal abierto, arbustal cerrado/bosque abierto con sotobosque, bosque cerrado, no combustible) con parámetros tomados de modelos estándar publicados (Scott & Burgan 2005 / Anderson 1982) como **rangos de hipótesis**, no como valores validados para el Chaco Serrano / Espinal de San Luis. La calibración se hará con el evento 2024 y la validación con 2022 (Renca–Piscu Yacu) y enero 2022 (Puertas Coloradas), si se logran separar los eventos. Los detalles metodológicos se desarrollarán en la Etapa 2.

---

## 9. Viabilidad computacional

Prueba realizada (NumPy puro, sin numba): grilla 1.671 × 1.671 = 2.792.241 celdas, vecindad de 8 con corrección de distancia diagonal, estado uint8, tiempo de llegada float32, 200 pasos de 30 s.

| Métrica | Valor |
|---|---|
| Tiempo por paso, grilla completa | **134 ms** (8 desplazamientos `np.roll` + mínimos) |
| Memoria por capa | 11,2 MB (float32) / 2,8 MB (uint8); 20 capas ≈ 250 MB |
| Extrapolación evento 2024 (21 días) con paso de 60 s y grilla completa | 30.240 pasos × 0,134 s ≈ **68 min** (cota superior) |
| Con ventana activa (bbox del frente + margen) y/o numba | estimado < 10 min; se medirá en Etapa 5 |
| Almacenamiento de estados | tiempo de llegada (1 capa float32, 11 MB) reconstruye cualquier instante; instantáneas horarias opcionales en uint8 comprimido (~0,3 MB/h) |

**No hay justificación para reducir el dominio por debajo de 2.500 km²** desde el punto de vista del autómata. El componente de riesgo es WindNinja, cuyo costo real por hora no se puede medir hasta instalarlo.

---

## 10. Compatibilidad entre capas y procedimientos de alineación previstos

| Capa | CRS origen | Procedimiento a la grilla de simulación (EPSG:5345, 30 m, bbox entidad 1) |
|---|---|---|
| DEM ASTER | EPSG:3395, 38,2 m (≈32 m terreno) | `gdalwarp` bilineal (o cúbica) a 30 m con margen de ≥ 5 km para WindNinja; relleno de NoData (`gdal_fillnodata`) documentado; derivación de pendiente/orientación en metros. |
| Cobertura MapBiomas | EPSG:4326, 0,00027° (30 × 25 m) | `gdalwarp` vecino más cercano (categórico) a 30 m. |
| Fuego MapBiomas raster | idem | vecino más cercano; conservar también los polígonos originales para IoU en vector. |
| Polígonos de fuego, SNMF, caminos, viviendas, MT | EPSG:4326 | reproyección a 5345 y recorte al bbox; rasterización a 30 m donde haga falta (no para visualización). |
| NDVI/NDMI (GEE) | exportar directamente en EPSG:5345 a 20 m (S2) o 30 m (Landsat) y promediar/remuestrear a la grilla. |
| Viento WindNinja | malla propia (m) | remuestreo bilineal de U/V (no de dirección) a 30 m y recorte al dominio. |
| Meteorología Open-Meteo | puntos de modelo | tabla horaria UTC; interpolación espacial solo si se usa más de un punto. |

Se conservan todos los archivos originales sin modificación; los derivados irán a `data/derivados/`.

---

## 11. Limitaciones y datos faltantes identificados

1. **WindNinja no instalado.** Requiere descargar `firelab-WindNinja-4.0.0-win64.zip` (186,4 MB) desde GitHub Releases de `firelab/windninja`. Pendiente de autorización.
2. **Hora de ignición** del evento 2024 no documentada; solo cota superior (14:26 hora local del 18/09).
3. **Documentación de MapBiomas Fuego Argentina Col. 1** (semántica de `date_*`, `p_mean`, `seed_mean`, exactitud declarada) no localizada; se usará la cicatriz como referencia espacial sin atribuirle fechas.
4. **DEM**: ASTER reproyectado a Mercator con 0,5 % de vacíos y ruido conocido; alternativa Copernicus GLO-30 disponible en GEE (decisión del usuario).
5. **ERA5-Land vía Open-Meteo no entrega viento** (probado); el viento histórico vendrá de IFS 9 km (2017+) o ERA5 25 km.
6. **Combustibles**: no hay inventario de campo ni cargas medidas; los parámetros serán hipótesis bibliográficas a calibrar.
7. **Evento 2022 (2022_43667)** fusiona al menos tres incendios SNMF; necesita separación por mes/hotspots antes de usarse para validación.
8. **Capa de viviendas** mezcla edificaciones, áreas residenciales y lugares poblados; hay que filtrar por `tipo`.
9. **Paquetes Python** faltantes (scipy, numba, fastapi, pytest, etc.) deben instalarse; todas las ruedas para 3.14 existen.
10. No se dispone de **observaciones meteorológicas de estación** dentro del área; todo es reanálisis/análisis de modelo.

---

## 12. Decisiones que deben tomarse antes de programar

| # | Decisión | Recomendación |
|---|---|---|
| D1 | CRS y grilla | EPSG:5345; grilla = bbox entidad 1 (1.672 × 1.671); máscara = entidad 0. |
| D2 | Evento principal de calibración | Las Lagunas–Potrerillos 2024 (`2024_41914`). Validación: `2022_43667` (tras separar eventos) y `2021_46201`. |
| D3 | DEM | Mantener ASTER provisto, pero generar Copernicus GLO-30 del área (vía GEE) para comparar antes de derivar pendientes. **Requiere su conformidad.** |
| D4 | Fuente meteorológica | Open-Meteo `ecmwf_ifs` (9 km) como primaria para 2022–2025; `era5` como respaldo y para análisis de sensibilidad; muestreo multipunto. |
| D5 | WindNinja | Instalar 4.0.0 (zip, sin instalador). Solver de conservación de masa, inicialización por dominio promedio o por puntos, malla a definir por pruebas (60–100 m), DEM con margen de 5–10 km. **Requiere autorización de descarga.** |
| D6 | Índices satelitales | Sentinel-2 SR Harmonized + Cloud Score+ (umbral `cs_cdf` ≥ 0,6), composición por mediana de las últimas 2–3 escenas despejadas anteriores a la ignición (para 2024: 30/07–08/09). Landsat solo como respaldo. |
| D7 | Cobertura de referencia por evento | Año anterior al incendio (2023 para el evento 2024; 2021 para los de 2022). |
| D8 | Modelo de propagación | Se definirá en Etapa 2; la prueba de rendimiento favorece un esquema de tiempos de llegada (ROS → tiempo) sobre uno puramente probabilístico. |
| D9 | Dominio | **2.500 km² completos**, sin reducción. |

---

## 13. Archivos generados en esta etapa

- `docs/01_diagnostico_etapa1.md` (este informe).
- `data/catalogo/incendios_mapbiomas_en_aoi.csv` — 133 polígonos con área total y dentro del dominio (EPSG:5345), fracción, distancia al borde, centroide, número de partes.
- `data/catalogo/registros_snmf_en_aoi.csv` — 100 reportes diarios SNMF dentro del dominio, con superficie parseada de observaciones.
- `data/catalogo/eventos_snmf_en_aoi.csv` — 40 eventos únicos SNMF (nombre + fecha de inicio) con primer/último reporte, extinción y coordenadas.
- `scripts/inspeccion/01_inspeccion_area_estudio.py`, `02_inspeccion_rasters.py`, `03_inspeccion_vectores.py` — scripts con los que se obtuvieron los valores de este informe.

Fuentes en línea consultadas: GitHub `firelab/windninja` (releases, `NEWS.md`, `README.md`, `data/*.cfg`, `doc/tutorials/CLI_instructions/CLI_instructions.tex`); Open-Meteo (`/en/docs`, `/en/docs/historical-weather-api`, `/en/terms`); Google Earth Engine (catálogo, consultas directas con la API Python).
