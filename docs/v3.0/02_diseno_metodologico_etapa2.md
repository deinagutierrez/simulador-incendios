# Etapa 2 — Diseño técnico y metodológico

Fecha: 2026-10-14. Basado en el diagnóstico de la Etapa 1 (`docs/01_diagnostico_etapa1.md`) y en las mediciones adicionales realizadas al inicio de esta etapa (§1).

Convención de este documento: cada parámetro o regla se etiqueta como **[MEDIDO]** (obtenido de los datos o de pruebas en este entorno), **[BIBLIO]** (tomado de una fuente verificable citada en §12), **[CALIBRAR]** (valor inicial a ajustar con el evento de calibración) o **[HIPÓTESIS]** (supuesto por falta de información, con rango declarado).

---

## 1. Mediciones realizadas al inicio de la Etapa 2

### 1.1 Entorno
- Paquetes instalados en Python 3.14.2: scipy 1.18.1, numba 0.68.0, fastapi 0.143.1, uvicorn 0.54.0, pytest 9.1.1, psutil 7.2.2, xarray 2026.9.0, rioxarray 0.23.0, matplotlib 3.11.2, openmeteo-requests, requests-cache, retry-requests, netCDF4 1.7.4, zarr 3.4.1, scikit-image 0.26.0. **[MEDIDO]**
- WindNinja 4.0.0 (SCM 684468f, 2026-08-31) instalado en `C:\Users\lisan\tools\WindNinja-4.0.0\install` (instalador NSIS en modo silencioso, sin privilegios de administrador). CLI: `install\bin\WindNinja_cli.exe`. Ejemplos en `install\etc\windninja\example-files`. **[MEDIDO]**

### 1.2 DEM Copernicus GLO-30 vs ASTER GDEM (dominio + margen de 10 km)
Archivo generado: `data/derivados/dem/copernicus_glo30_2024_1_dominio_margen10km_epsg5345_30m.tif` (2.339 × 2.338 px, EPSG:5345, 30 m, float32, sin vacíos, 530–1.750 m; metadatos en el `.json` adjunto). **[MEDIDO]**

| Comparación dentro del dominio (2.797.256 px) | Valor |
|---|---|
| Diferencia ASTER − Copernicus: media / mediana / desvío | 0,22 m / 0,09 m / 4,59 m |
| Percentiles 5–95 de la diferencia | −6,7 m … +7,4 m |
| Píxeles con diferencia > 20 m | 0,28 % |
| Pendiente p50 / p90 / p99 | ASTER 4,1° / 9,5° / 20,2° — Copernicus 3,2° / 9,8° / 23,4° |
| Ruido de alta frecuencia (desvío del residuo respecto de la media 3 × 3) | ASTER 0,89 m (suavizado por el remuestreo bilineal desde 38 m) — Copernicus 1,15 m |

Los dos DEM son consistentes (sin sesgo vertical). **Decisión D3:** se adopta **Copernicus GLO-30 como DEM primario** porque no tiene vacíos, está en su resolución nativa de 30 m sobre la grilla exacta de simulación, y su datum y procedencia están documentados (GEE `COPERNICUS/DEM/GLO30_2024_1`). ASTER queda como DEM alternativo seleccionable por configuración (`dem.fuente = aster`) para análisis de sensibilidad.

### 1.3 WindNinja: costo real y convenciones (solver de conservación de masa, DEM Copernicus 70 × 70 km, 12 hilos, viento uniforme 7 m/s desde 0°, vegetación `brush`)

| Malla | Tiempo total | Memoria pico | Nodos de salida | Velocidad resultante |
|---|---|---|---|---|
| 200 m | 14,0 s (solver 7,1 s) | 1,73 GB | 351 × 351 | min 0,9 / media 6,93 / máx 14,7 m/s |
| 100 m | 35,6 s (solver 27,6 s) | 5,75 GB | 702 × 702 | min 0,3 / media 6,93 / máx 17,5 m/s |
| 60 m | 86,4 s (solver 71,4 s) | 15,33 GB | 1.170 × 1.169 | — |

La malla de 60 m es ejecutable pero consume la mitad de la RAM disponible; se reserva para análisis de sensibilidad, no para la cadena operativa.

Convenciones verificadas **[MEDIDO]**:
- Salidas `*_vel.tif/.asc` (m/s si `output_speed_units = mps`), `*_ang.tif/.asc` (grados, **convención meteorológica: dirección desde la que sopla**; con entrada 0° la celda central devuelve 359,7°–0,0°), `*_u.asc` y `*_v.asc` (componentes este y norte en m/s; con viento del norte `v` es negativo). También GeoTIFF con `write_geotiff_output = true`.
- Georreferencia: EPSG:5345 heredado del DEM, origen en la esquina inferior izquierda del DEM, NoData −9999, float64.
- El CLI acepta `input_speed_grid` / `input_dir_grid` (inicialización por grilla, `.asc`), `pointInitialization` con archivo de estaciones y series temporales, y `num_threads`.
- Una llamada HTTP de "call home" produce un aviso de tiempo de espera sin afectar la corrida; se desactiva con la variable de entorno `NINJA_DISABLE_CALL_HOME=TRUE`.

### 1.4 Linealidad del solver de conservación de masa **[MEDIDO]**
Tres ejecuciones a 200 m con viento desde 0° a 3,5, 7 y 14 m/s (estabilidad neutra, sin viento diurno):

| Comparación | máx |ΔU| | máx |ΔV| | RMS relativo |
|---|---|---|---|
| campo(14) − 2·campo(7) | 0,010 m/s | 0,010 m/s | 0,072 % |
| campo(3,5) − 0,5·campo(7) | 0,005 m/s | 0,010 m/s | 0,144 % |

Las diferencias son del orden del redondeo de escritura de WindNinja (0,01 m/s). **La solución es lineal en la velocidad de entrada**, como corresponde a un modelo diagnóstico de conservación de masa con perfil inicial neutro. Consecuencia (§6.4): basta una ejecución por clase de dirección a velocidad unitaria y escalar por la velocidad horaria. Esta propiedad deja de valer si se activan `diurnal_winds` o `non_neutral_stability`, que v1 no usa.

---

## 2. Arquitectura del sistema

```
Datos_SL_Completo/
├── config/                      # YAML no sensibles: dominio, eventos, parámetros del modelo, rutas
│   ├── dominio_las_lagunas.yaml
│   ├── eventos/SL-2024-LASLAGUNAS.yaml
│   └── modelo_v1.yaml
├── data/
│   ├── (originales, intactos)   # Topografia/, Uso_Cobertura_Suelo/, Fuego_MapBiomas/, Electricidad/, *.geojson, *.csv
│   ├── catalogo/                # catálogos de incendios (Etapa 1)
│   ├── derivados/               # rasters alineados a la grilla, viento, índices, combustibles; cada producto con .json de procedencia
│   │   ├── dem/  grilla/  cobertura/  indices/  combustibles/  viento/  meteo/  infraestructura/
│   └── resultados/<run_id>/     # salidas de simulación y validación
├── src/incendios_sl/            # paquete Python instalable (pyproject.toml)
│   ├── grilla.py                # definición de la grilla maestra EPSG:5345 y utilidades de alineación
│   ├── data/                    # lectura/validación de capas, reproyección, caché por hash
│   ├── meteorology/             # cliente Open-Meteo, normalización, QC, caché
│   ├── wind/                    # generación de .cfg, ejecución de WindNinja_cli, lectura/remuestreo, caché
│   ├── remote_sensing/          # GEE: NDVI/NDMI, máscaras, exportación recortada
│   ├── fuels/                   # clasificación provisional, tabla de parámetros, humedad de combustible
│   ├── simulation/              # autómata (núcleo numba), estados, reglas, registro de salidas
│   ├── validation/              # métricas espaciales/temporales, informes
│   └── api/                     # FastAPI: trabajos, estados, resultados, teselas
├── web/                         # Leaflet + JS vanilla (sin build step), servido por la API
├── scripts/                     # CLI de cada etapa (adquirir_meteo.py, obtener_indices.py, preparar_dominio.py, ejecutar_viento.py, simular.py, validar.py)
├── tests/                       # unitarias (sin red) + integración (marcadas, requieren red/WindNinja)
└── docs/
```

Principios: (1) toda salida derivada lleva un JSON de procedencia (fuente, parámetros, hash de entradas, versión del código, fecha); (2) la caché se indexa por hash de los parámetros que determinan la validez del producto; (3) el núcleo de simulación no conoce rutas ni formatos: recibe arrays NumPy y una configuración; (4) la API lanza trabajos en procesos separados y persiste el estado en disco (JSON) para que sobreviva a reinicios.

---

## 3. Grilla maestra y dominios

| Elemento | Definición |
|---|---|
| CRS | EPSG:5345 (POSGAR 2007 / Argentina faja 3). **[MEDIDO: distorsión < 0,01 %]** |
| Grilla de simulación | Rectángulo de la entidad 1 del GeoJSON: x 3.513.060–3.563.220, y 6.367.770–6.417.900, 30 m → 1.672 columnas × 1.671 filas = 2.793.912 celdas. Transformación afín: `(30, 0, 3513060, 0, −30, 6417900)`. |
| Máscara de dominio | Entidad 0 (polígono exacto rotado) rasterizada; celdas fuera = estado "fuera de dominio" (no propagan, no cuentan). ≈ 2.778.000 celdas dentro. |
| Dominio meteorológico / de viento | Grilla + margen de **10 km** por lado (70,17 × 70,14 km) — el usado en las pruebas de §1.3. Justificación: WindNinja necesita que las perturbaciones del borde del dominio (condiciones de contorno del solver) queden fuera del área de interés; 10 km supera ampliamente la escala del relieve (sierras de 5–10 km de ancho, desniveles de hasta 800 m). **[HIPÓTESIS razonable; verificable comparando campos con margen 5 y 10 km]** |
| Dominio de índices satelitales | Grilla + 1 km. |

Alineación: todo raster derivado se produce con `gdalwarp -t_srs EPSG:5345 -te 3513060 6367770 3563220 6417900 -tr 30 30 -tap` (o el equivalente con rasterio) y el método de remuestreo adecuado (categóricos: vecino más cercano; continuos: bilineal; viento: bilineal sobre U y V, nunca sobre la dirección).

---

## 4. Modelo de propagación

### 4.1 Decisión: velocidad de propagación → tiempos de llegada (y no probabilidades de transición)

Se evaluaron los dos enfoques pedidos:

| Criterio | Probabilístico (tipo Alexandridis et al. 2008) | Velocidad de propagación → tiempos de llegada (tipo "minimum travel time" sobre grilla) |
|---|---|---|
| Vínculo con meteorología horaria y combustibles | Indirecto: factores multiplicativos empíricos a calibrar por evento | Directo: ROS (m/min) = f(combustible, humedad, viento, pendiente) con ecuaciones publicadas |
| Determinismo / reproducibilidad | Estocástico; requiere ensambles | Determinista (ensambles opcionales para incertidumbre) |
| Validación temporal | El tiempo del AC no tiene unidades físicas sin calibración | El tiempo de llegada de cada celda es físico (s); se compara con hotspots diarios |
| Riesgo | Sobreajuste a la cicatriz final | Dependencia de parámetros de combustible no medidos localmente |

**Se adopta el enfoque de velocidad de propagación.** Los parámetros de combustible desconocidos se declaran como hipótesis con un factor de ajuste por clase **[CALIBRAR]**; el enfoque probabilístico queda como variante opcional (ignición estocástica de vecinos) para estudios de sensibilidad.

### 4.2 Estados y transiciones

| Estado | Código | Transición de salida |
|---|---|---|
| Fuera de dominio | 255 | ninguna |
| No combustible | 0 | ninguna (agua, urbano, suelo desnudo, roca) |
| Combustible sin quemar | 1 | → 2 cuando `t ≥ t_llegada(celda)` |
| En combustión (frente) | 2 | → 3 cuando `t ≥ t_llegada + t_residencia` |
| Quemada | 3 | ninguna (no hay reignición) |

Cada celda guarda además `t_llegada` (float32, s desde el inicio; `inf` si no alcanzada) y `t_fin_combustion`. Solo las celdas en estado 2 transmiten fuego. **Garantía:** una celda quemada (3) nunca vuelve a 1 ni a 2 (prueba automática).

### 4.3 Regla de propagación

Para cada celda en combustión *i* y cada vecina *j* del estencil, el tiempo de llegada candidato es

`t_cand(j) = t_llegada(i) + d_ij / R_i(θ_ij)`

donde `d_ij` es la distancia entre centros (30 m ortogonal, 42,43 m diagonal, 67,08 m en los saltos de caballo) y `R_i(θ_ij)` es la velocidad de propagación desde *i* en la dirección θ del vecino. Se toma `t_llegada(j) = min` sobre todas las *i*. Esto es la versión discreta del principio de tiempo mínimo de viaje (Finney 2002 **[BIBLIO]**) y evita la sobrevelocidad diagonal de las grillas cuadradas porque la distancia real se usa explícitamente.

**Estencil:** 16 vecinos (8 adyacentes + 8 saltos de caballo). Con 8 vecinos la forma del frente es octogonal; con 16 el error angular máximo se reduce de 22,5° a ~11° **[BIBLIO: práctica estándar en MTT raster; Finney 2002]**. Se mantiene configurable (8/16) para pruebas.

**ROS direccional (elipse):** `R(θ) = R_cabeza · (1 − e) / (1 − e·cos(θ − θ_max))`, con excentricidad `e = sqrt(1 − 1/LB²)` y relación largo/ancho `LB = 0,936·exp(0,2566·U) + 0,461·exp(−0,1548·U) − 0,397` (U = viento efectivo a media llama en m/s, Anderson 1983 según Finney 1998/FARSITE; forma documentada en Andrews 2018 **[BIBLIO]**). `θ_max` es la dirección de máxima propagación resultante de combinar viento y pendiente vectorialmente (§4.5).

### 4.4 Velocidad de propagación en cabeza: Rothermel (1972) con las correcciones de Albini (1976)

`R_cabeza = I_R · ξ · (1 + φ_w + φ_s) / (ρ_b · ε · Q_ig)` **[BIBLIO: Rothermel 1972; Andrews 2018, ec. completas]**

Variables: `I_R` intensidad de reacción (kW/m² o BTU/ft²·min), `ξ` razón de flujo propagante, `φ_w` factor de viento, `φ_s` factor de pendiente, `ρ_b` densidad aparente del lecho, `ε` número de calentamiento efectivo, `Q_ig` calor de preignición (función de la humedad). Entradas por clase de combustible: cargas por clase de tiempo de retardo (1 h, 10 h, 100 h, herbáceo vivo, leñoso vivo), relaciones superficie/volumen, profundidad del lecho, humedad de extinción, poder calorífico. Se implementará siguiendo RMRS-GTR-371 (unidades imperiales internas, conversión a m/min en la interfaz), con pruebas unitarias contra los valores de referencia publicados para los modelos GR2, SH2 y TU1 **[BIBLIO: Scott & Burgan 2005]**.

Factor de ajuste: `R_cabeza,efectivo = k_clase · R_cabeza` con `k_clase` **[CALIBRAR]** (inicial 1,0; rango de búsqueda 0,3–3).

### 4.5 Viento y pendiente

- Viento a 10 m (WindNinja) → viento a media llama: `U_mf = WAF · U_10`, con WAF por modelo de combustible (0,4 para pastizal sin dosel, 0,3 arbustal, 0,1–0,2 bajo dosel; Andrews 2012 **[BIBLIO]**, se verifica al implementar). `U_10` se interpola bilinealmente de la malla de WindNinja (100 m) a 30 m; se documenta que la resolución efectiva del viento es 100 m.
- Factor de viento de Rothermel: `φ_w = C · (3,281·U_mf)^B · (β/β_op)^−E` (U en m/min convertido a ft/min).
- Factor de pendiente: `φ_s = 5,275 · β^−0,3 · tan²(α)` (α pendiente del terreno). Pendiente y orientación se calculan del DEM Copernicus a 30 m (Horn 1981 via `gdaldem`).
- Combinación vectorial viento–pendiente: método de Rothermel/Finney (FARSITE), descrito en Andrews 2018 §"cross-slope wind" **[BIBLIO]**: el vector de pendiente apunta cuesta arriba con módulo φ_s, el de viento en la dirección hacia donde sopla con módulo φ_w; la suma da la dirección θ_max y el factor combinado φ_c, que reemplaza a (φ_w + φ_s). La bibliografía revisada por Sharples (2008) **[BIBLIO]** documenta las limitaciones de esta suma vectorial (sobrestimación en viento cruzado fuerte); se registra como incertidumbre.
- Dirección: Open-Meteo y WindNinja dan dirección "desde"; el simulador trabaja con la dirección "hacia" = (desde + 180°) mod 360 y con componentes U/V. Prueba automática obligatoria.

### 4.6 Residencia y extinción

- Tiempo de residencia de llama `t_r = 384/σ` min (σ relación superficie/volumen característica en ft⁻¹; Anderson 1969 citado en Rothermel 1972 **[BIBLIO]**): ≈ 1–4 min para pastizal/arbustal. La celda permanece en estado 2 durante `30 m / R + t_r` (tiempo de cruce más residencia) para que el frente tenga continuidad. **[HIPÓTESIS de implementación, sin efecto en el área final]**
- Sin propagación posible: si para todas las celdas en combustión `R(θ) < R_min` (p. ej. 0,05 m/min) hacia todos los vecinos no quemados, el frente se declara detenido en esa hora; si persiste N horas consecutivas (configurable, p. ej. 12 h) la simulación termina con motivo "sin continuación física según el modelo" (condición 3 de §11.2 del encargo). Esto ocurre cuando la humedad del combustible muerto supera la humedad de extinción (Rothermel: `η_M = 0` si `M_f ≥ M_x`), típicamente de noche con HR alta o tras lluvia.

### 4.7 Tiempo

- Meteorología y viento: horarios (UTC), constantes dentro de cada hora (función escalonada). Alternativa documentada: interpolación lineal de T, HR y viento entre horas; se evaluará su efecto en Etapa 7 como sensibilidad.
- Paso interno Δt: **60 s** (configurable). Como el tiempo de llegada se calcula continuo y solo se *acepta* cuando `t_cand ≤ t + Δt`, Δt no limita la velocidad máxima (una ROS de 3 m/s cruza 30 m en 10 s y se representa como llegada en el paso correspondiente); el error de discretización es ≤ Δt y la estabilidad está garantizada. **[MEDIDO en §9: 60 s es compatible con el presupuesto de tiempo]**
- Al cambiar de hora se recalculan los candidatos pendientes con la nueva ROS (las llegadas ya aceptadas no se revierten).

### 4.8 Ignición e inicialización

Para cada evento la configuración declara: punto(s) de ignición (lon/lat), instante de ignición (UTC), fuente y grado de confianza. Para `SL-2024-LASLAGUNAS`: dos focos SNMF (Las Lagunas y Potrerillos) **[MEDIDO: SNMF]**; hora **[HIPÓTESIS]**: se ensayarán 10:00, 12:00 y 14:00 hora local del 18/09/2024 (cota superior 14:26 por VIIRS NOAA-20) y se reportará la sensibilidad. Las celdas de ignición se marcan en combustión con `t_llegada = 0`.

### 4.9 Spotting, fuego de copas, mitigación

No se modelan en v1 (sin datos para parametrizarlos; sin mitigación por requisito). Se documenta como limitación; la subestimación de saltos sobre barreras (rutas, ríos secos) es esperable.

---

## 5. Estrategia meteorológica

| Aspecto | Decisión |
|---|---|
| Fuente para eventos 2022–2025 | Open-Meteo Historical Weather API, `models = ecmwf_ifs` (análisis IFS, 9 km, desde 2017) **[MEDIDO: entrega todas las variables]**; `era5` (25 km) como respaldo y para sensibilidad. `era5_land` solo para T/HR/VPD/humedad del suelo si hiciera falta. |
| Naturaleza del dato | Análisis/reanálisis de modelo, **no observaciones**. Se etiqueta así en todos los metadatos y en la interfaz. |
| Variables obligatorias | `temperature_2m` (°C), `relative_humidity_2m` (%), `wind_speed_10m` (m/s), `wind_direction_10m` (° desde), `precipitation` (mm/h) — entran en humedad de combustible muerto (§7.3) y viento. |
| Variables opcionales justificadas | `shortwave_radiation` (W/m², para extensión del modelo de humedad y para `diurnal_winds` de WindNinja si se activa), `wind_gusts_10m` (sensibilidad), `vapour_pressure_deficit` (diagnóstico), `soil_moisture_0_to_7cm` (indicador de sequía estacional; no entra en v1). No se solicitarán más variables. |
| Muestreo espacial | Malla de **4 × 4 puntos** sobre el dominio + margen (paso ≈ 23 km, acorde a los 9 km del modelo), 16 consultas por evento. Se guarda cada punto y se deriva: (a) promedio ponderado del dominio para T/HR/lluvia; (b) campo de viento interpolado (IDW sobre U/V) como entrada opcional de WindNinja por grilla; en v1 se usa el promedio de U/V para la inicialización de dominio. |
| Zona horaria y unidades | Descarga y almacenamiento en UTC, ISO 8601; conversión a `America/Argentina/San_Luis` solo en la interfaz. `wind_speed_unit=ms`. |
| QC | Rangos físicos (T −30…50 °C, HR 1–100 %, viento 0–60 m/s, lluvia 0–200 mm/h), duplicados, huecos → se registran y, si > 2 h consecutivas, se detiene la preparación con error explícito (no se rellena inventando). |
| Caché | Clave = hash(lat, lon, inicio, fin, variables, modelo); CSV + Parquet + JSON de procedencia (fecha de descarga, URL, licencia CC-BY 4.0). |
| Límites | 600/min, 5.000/h, 10.000/día (uso no comercial) **[MEDIDO: términos]**; un evento de 21 días × 16 puntos = 16 llamadas. |

---

## 6. Viento con WindNinja

### 6.1 Configuración base (v1)

```
initialization_method    = domainAverageInitialization   # viento uniforme de entrada (promedio de los 16 puntos IFS)
momentum_flag            = false                         # conservación de masa (requisito)
elevation_file           = dem_copernicus_margen10km.tif # EPSG:5345, 30 m, 70 x 70 km
mesh_resolution          = 100 ; units_mesh_resolution = m
input_wind_height        = 10 ; output_wind_height = 10 ; unidades m   # salida a 10 m; WAF se aplica en el simulador
vegetation               = brush                         # un solo valor por dominio (limitación del CLI); ver 6.3
diurnal_winds            = false ; non_neutral_stability = false   # v1 neutral; ver 6.5
output_speed_units       = mps ; write_geotiff_output = true ; ascii_out_uv = true ; write_ascii_output = true
num_threads              = 12
```

### 6.2 Resolución
Malla de **100 m** (36 s y 5,8 GB por ejecución **[MEDIDO]**). La malla de 60 m se evalúa en Etapa 5; 30 m no es viable (≈ 5,5 M nodos por capa y memoria estimada > 20 GB). Los campos U/V se remuestrean bilinealmente a la grilla de 30 m. **La resolución efectiva del viento es la de la malla (100 m), no 30 m**, y así se declarará en los metadatos y en la interfaz.

### 6.3 Vegetación
El CLI admite un único tipo (`grass`, `brush`, `trees`) que fija la rugosidad y la altura de desplazamiento para todo el dominio. Se usará `brush` (predominio de bosque abierto y arbustal: 50 % del área **[MEDIDO]**) y se documentará como limitación. La alternativa (archivo LCP con cobertura de dosel por celda) se evaluará solo si la validación lo justifica.

### 6.4 Estrategia horaria y caché
- Clave de caché: hash(DEM, malla, vegetación, velocidad redondeada a 0,25 m/s, dirección redondeada a 5°, opciones). Horas con la misma clave reutilizan el campo.
- **Linealidad verificada (§1.4):** se ejecuta WindNinja **una vez por clase de dirección (72 clases de 5°) a velocidad unitaria** y cada hora se obtiene como `U_h = v_h · U_unit(dir_h)`, `V_h = v_h · V_unit(dir_h)`. Costo por dominio: 72 × 36 s ≈ 43 min a 100 m (≈ 1,7 h a 60 m), **reutilizable para todos los eventos del mismo dominio**. La interpolación entre clases de dirección vecinas (ponderación angular de los campos unitarios) se evaluará como refinamiento; en v1 se usa la clase más cercana (error angular ≤ 2,5°).
- Almacenamiento: U y V unitarios float32 a 100 m (702 × 702 × 4 B × 2 ≈ 4 MB por clase) en un único Zarr/NetCDF con dimensión `direccion` ≈ 290 MB por dominio y malla.
- Registro por ejecución: `.cfg` usado, stdout, tiempo, memoria pico, código de salida; fallo → el trabajo se marca "Fallido" con el mensaje, nunca se sustituye silenciosamente por el viento uniforme.

### 6.5 Limitaciones documentadas
Sin efectos térmicos (brisas de ladera/valle) salvo que se active `diurnal_winds` (requiere T y nubosidad; rompe la linealidad); sin efecto de vegetación por celda ni de edificios; sin dependencia temporal (cada hora es un estado estacionario); las condiciones de contorno de entrada son uniformes (la variación de 9 km del modelo se pierde en v1; v2 puede usar `input_speed_grid`/`input_dir_grid`).

---

## 7. Combustibles

### 7.1 Evaluación metodológica
Lo que cada fuente aporta y no aporta se detalló en §8 de la Etapa 1. Conclusión: con cobertura + NDVI + NDMI + topografía se puede construir un **mapa estático de clases de combustible locales provisionales** y un **estado dinámico de humedad**, pero **no** cargas ni estructuras medidas. Un sistema estándar (Scott & Burgan 2005) solo se usa como *analogía declarada* para disponer de parámetros físicos completos; ninguna clase se presenta como validada en campo.

### 7.2 Clasificación provisional (reglas explícitas)

| Código | Clase local | Cobertura MapBiomas (año previo al evento) | Regla adicional NDVI/NDMI (compuesto pre-incendio) | Modelo análogo S&B 2005 [HIPÓTESIS] | Incertidumbre |
|---|---|---|---|---|---|
| 0 | No combustible | 24, 25, 33, 34, 27 | — | NB | baja |
| 1 | Pastizal natural | 12, 11 | NDVI < 0,35 → curado > 70 %; NDVI ≥ 0,35 → curado 50 % | GR2 (bajo, seco) / GR4 | alta (carga desconocida) |
| 2 | Pastura / cultivo | 15, 19, 18, 36, 21 | NDVI < 0,25 en invierno → rastrojo/suelo (GR1 o NB según NDVI < 0,15) | GR1 | alta |
| 3 | Arbustal abierto / mosaico | 77, 63 | NDMI modula humedad viva | GS2 | alta |
| 4 | Arbustal cerrado | 66 | idem | SH2 | alta |
| 5 | Bosque abierto con sotobosque | 4 | NDVI/NDMI para fracción herbácea y humedad viva | GS2 / TU1 (se decide por calibración) | alta |
| 6 | Bosque cerrado | 3, 6 | idem | TU1 / TL2 | alta |
| 7 | Plantación forestal | 9 | — | TL | alta |

La tabla completa de parámetros (cargas por clase de tiempo de retardo, σ, profundidad, M_x, poder calorífico, WAF, fuente de cada valor, rango de experimentación) se generará en Etapa 3 como `data/derivados/combustibles/tabla_combustibles_v1.csv` leyendo los valores publicados de RMRS-GTR-153 y marcando cada fila como [BIBLIO analogía] + `k_clase` [CALIBRAR]. Umbrales de NDVI/NDMI: **[HIPÓTESIS]** iniciales, revisables con los histogramas del área.

### 7.3 Estado dinámico de humedad

| Componente | Método | Etiqueta |
|---|---|---|
| Humedad del combustible muerto fino (1 h) | FFMC horario del sistema canadiense (Van Wagner 1977; implementación de referencia en `cffdrs`) a partir de T, HR, viento y lluvia horarios; conversión `m = 147,2·(101 − FFMC)/(59,5 + FFMC)` **[BIBLIO]**. Se calcula un valor por hora para el dominio (o por punto IFS e interpolado). | BIBLIO |
| 10 h y 100 h | 1 h + 1 y + 2 puntos porcentuales (práctica de BehavePlus para escenarios; **[HIPÓTESIS]**) | HIPÓTESIS |
| Humedad viva herbácea | `LFMC_h = a + b·NDMI_pre` reescalado al rango 30–120 % **[HIPÓTESIS, rango de experimentación]**, con curado derivado del NDVI | CALIBRAR |
| Humedad viva leñosa | análogo, rango 60–150 % | CALIBRAR |
| Lluvia | entra en FFMC; si lluvia acumulada 24 h > 5 mm se fuerza M_1h ≥ M_x durante 6 h **[HIPÓTESIS]** | HIPÓTESIS |

Se declara explícitamente que NDMI **no** equivale al porcentaje de humedad; la conversión es un modelo lineal de prueba sin validación local (Yebra et al. 2013 **[BIBLIO]** documentan la relación y su incertidumbre).

### 7.4 Selección temporal de índices
Para cada evento: compuesto por **mediana** de las escenas Sentinel-2 SR Harmonized con `cs_cdf ≥ 0,6` (Cloud Score+) entre 45 y 1 días antes de la ignición (para 2024: 30/07–17/09, con al menos 03/09 y 08/09 100 % despejadas **[MEDIDO]**). Mediana: robusta a nubes residuales y sombras, representa el estado típico pre-evento. Para eventos sin escenas útiles se usa Landsat 8/9 C2 L2 (30 m) con máscara QA_PIXEL, sin mezclar sensores en un mismo compuesto. Cobertura MapBiomas del **año anterior** al evento. Nunca imágenes posteriores.

---

## 8. Protocolo de validación

| Nivel | Datos de referencia | Métricas | Eventos |
|---|---|---|---|
| Espacial final | Polígono MapBiomas del evento rasterizado a la grilla; dominio de comparación = celdas dentro del dominio y combustibles (no se evalúa sobre agua/urbano) | IoU, Dice/F1, superficies simulada y de referencia (ha), diferencia absoluta y relativa, omisión (ref no simulada / ref), comisión (sim no ref / sim) | todos |
| Temporal aproximada | Agrupación diaria de hotspots VIIRS (375 m) y MODIS (1 km) | fracción de hotspots del día *d* cuyo píxel tiene `t_llegada ≤ fin del día d`; evolución diaria de superficie simulada vs. hotspots acumulados; dirección media de avance diaria | 2024 (y 2022 si se separa) |
| Sensibilidad | — | variación de IoU ante hora de ignición, `k_clase`, WAF, fuente meteorológica, 8/16 vecinos, Δt | 2024 |

Separación: **calibración** con `SL-2024-LASLAGUNAS` (búsqueda de `k_clase` y umbrales de humedad viva); **validación** con `2022_43667` (Renca–Piscu Yacu, previa separación en eventos usando raster mensual + hotspots) y `2021_46201` (Puertas Coloradas, enero 2022); **exploratorios**: `2023_26601` y menores. Ningún resultado de calibración se presentará como validación.

Incertidumbres a documentar: ignición (lugar/hora), fechas SNMF (día, sin hora), meteorología (análisis 9 km, sin observaciones), cicatriz (producto anual con errores de omisión/comisión no cuantificados localmente), clasificación de combustibles, parámetros físicos.

---

## 9. Estimación de costo computacional

| Componente | Medición / estimación | Fuente |
|---|---|---|
| Autómata, paso completo de grilla (NumPy, 8 vecinos) | 134 ms / paso, 2,79 M celdas | MEDIDO (Etapa 1) |
| Autómata, versión numba sobre frente activo (estimación) | < 10 ms / paso típico (frente de 10³–10⁵ celdas) | estimación; se mide en Etapa 4 |
| Evento 2024, 21 días, Δt = 60 s | 30.240 pasos → cota superior 68 min (grilla completa) / objetivo < 10 min (frente activo) | cálculo |
| Memoria del autómata | ~20 capas × 11 MB ≈ 250 MB + viento por hora 2 × 11 MB | cálculo |
| WindNinja 100 m | 36 s, 5,8 GB por campo; 72 direcciones ≈ 43 min por dominio (linealidad verificada); 60 m: 86 s y 15,3 GB por campo | MEDIDO |
| Open-Meteo | 16 llamadas por evento, < 1 min | MEDIDO |
| GEE índices | exportación de ~2.500 × 2.500 px a 20 m: 2–5 min por índice | estimación según descarga del DEM (17 MB en 75 s) |
| Almacenamiento por simulación | `t_llegada` float32 11 MB + estados horarios uint8 comprimidos ≈ 0,3 MB/h + metadatos ≈ 200 MB para 504 h | cálculo |

**Decisión D9 ratificada:** dominio completo de 2.500 km². No hay componente que requiera reducción.

---

## 10. API, trabajos y visualización (diseño)

- FastAPI con trabajos en `ProcessPoolExecutor` (1 trabajo de simulación simultáneo por defecto, configurable); estado persistido en `data/resultados/<run_id>/estado.json` con los estados pedidos (pendiente, preparando datos, calculando viento, ejecutando simulación, guardando resultados, completada, fallida, cancelada) y progreso (hora simulada / hora final). "Completada" solo tras verificar que existen y abren los archivos de salida.
- Endpoints: `GET /areas`, `GET /incendios`, `GET /incendios/{id}`, `POST /preparacion`, `POST /simulaciones`, `GET /simulaciones/{id}`, `GET /simulaciones/{id}/estado/{hora}` (PNG/COG del estado en esa hora), `GET /simulaciones/{id}/metricas`, `GET /simulaciones/{id}/parametros`, `GET /simulaciones/{id}/perimetro/{hora}.geojson`, `GET /capas/{nombre}` (teselas o GeoJSON simplificado).
- Visualización: Leaflet; rasters como superposiciones PNG generadas por hora (umbral sobre `t_llegada`, 1.672 × 1.671 px → ~100 KB PNG) o como teselas; perímetros vectoriales derivados por `rasterio.features.shapes` y simplificados; capas de contexto con simplificación por nivel de zoom; nunca polígonos por celda.

---

## 11. Plan de pruebas

Unitarias (sin red): grilla/transformaciones, áreas en EPSG:5345, convenciones de viento (U/V ↔ dirección), Rothermel contra valores de referencia, FFMC contra `cffdrs`, transiciones del autómata, ausencia de reignición, estencil 8/16 y distancias, escenarios sintéticos (ignición central sin viento → frente circular; con viento → elipse orientada; con pendiente → aceleración cuesta arriba; barrera no combustible → no cruce), métricas IoU/Dice sobre máscaras conocidas, persistencia/reproducibilidad (dos corridas con la misma configuración → hash idéntico). Integración (marcadas `@pytest.mark.integration`): Open-Meteo, GEE, WindNinja con DEM pequeño; comportamiento ante fallo (red caída → estado "fallida" con mensaje). Rendimiento: grillas de 10², 10³, 1,67 M, 2,79 M celdas y pasos crecientes; registro de tiempo y memoria.

---

## 12. Referencias verificadas (existencia y datos bibliográficos comprobados en línea en esta etapa; el contenido de ecuaciones se verificará contra el texto completo al implementar)

- Rothermel, R. C. (1972). *A mathematical model for predicting fire spread in wildland fuels.* USDA Forest Service Res. Pap. INT-115.
- Andrews, P. L. (2018). *The Rothermel surface fire spread model and associated developments: A comprehensive explanation.* USDA Forest Service Gen. Tech. Rep. RMRS-GTR-371.
- Scott, J. H.; Burgan, R. E. (2005). *Standard fire behavior fuel models: a comprehensive set for use with Rothermel's surface fire spread model.* RMRS-GTR-153.
- Finney, M. A. (2002). Fire growth using minimum travel time methods. *Canadian Journal of Forest Research* 32(8): 1420–1424. (Citado como base del esquema de tiempos de llegada; su ficha bibliográfica se confirmará al redactar la documentación científica final.)
- Alexandridis, A.; Vakalis, D.; Siettos, C. I.; Bafas, G. V. (2008). A cellular automata model for forest fire spread prediction: The case of the wildfire that swept through Spetses Island in 1990. *Applied Mathematics and Computation* 204: 191–201. doi:10.1016/j.amc.2008.06.046.
- Freire, J. G.; DaCamara, C. C. (2019). Using cellular automata to simulate wildfire propagation and to assist in fire management. *Natural Hazards and Earth System Sciences* 19: 169–179. doi:10.5194/nhess-19-169-2019.
- Forthofer, J. M.; Butler, B. W.; Wagenbrenner, N. S. (2014). A comparison of three approaches for simulating fine-scale surface winds in support of wildland fire management. Part I. *International Journal of Wildland Fire* 23(7): 969–981 (y Parte II, mismo volumen). Hallazgo relevante: el modelo de conservación de masa corre en segundos y es más preciso en laderas a barlovento y crestas; peor a sotavento.
- Viegas, D. X. (2004). Slope and wind effects on fire propagation. *International Journal of Wildland Fire* 13(2): 143–156. doi:10.1071/WF03046.
- Sharples, J. J. (2008). Review of formal methodologies for wind–slope correction of wildfire rate of spread. *International Journal of Wildland Fire* 17(2): 179–193. doi:10.1071/WF06156.
- Yebra, M. et al. (2013). A global review of remote sensing of live fuel moisture content for fire danger assessment: moving towards operational products. *Remote Sensing of Environment* 136: 455–468. doi:10.1016/j.rse.2013.05.029.
- Filippi, J.-B.; Mallet, V.; Nader, B. (2014). Representation and evaluation of wildfire propagation simulations. *International Journal of Wildland Fire* 23(1): 46–57. doi:10.1071/WF12202.
- Van Wagner, C. E. (1977). *A method of computing fine fuel moisture content throughout the diurnal cycle.* Canadian Forestry Service Information Report PS-X-69. (FFMC horario; su ficha se confirmará con la documentación de `cffdrs` al implementar.)
- Documentación oficial: WindNinja (GitHub `firelab/windninja`, `NEWS.md`, `doc/tutorials/CLI_instructions`, salida de `WindNinja_cli --help` 4.0.0); Open-Meteo (`/en/docs/historical-weather-api`, `/en/terms`); Google Earth Engine (catálogo de datos: S2_SR_HARMONIZED, CLOUD_SCORE_PLUS, FIRMS, LANCE VIIRS, COPERNICUS/DEM/GLO30_2024_1); MapBiomas Argentina (metadatos locales de descarga).

Pendiente de localizar: documento metodológico (ATBD) de MapBiomas Fuego Argentina Colección 1.

---

## 13. Qué requiere datos adicionales o calibración (resumen)

1. Cargas y estructura de combustible locales → `k_clase` y analogías S&B **[CALIBRAR/HIPÓTESIS]**.
2. Conversión NDMI → humedad viva **[CALIBRAR]**.
3. Hora y lugar exactos de ignición de cada evento **[HIPÓTESIS + sensibilidad]**.
4. Rugosidad/vegetación por celda en WindNinja (v2).
5. Separación de eventos fusionados en MapBiomas (2022).
6. Validación independiente de la cicatriz MapBiomas (no disponible).

## 14. Próximos pasos (Etapa 3)

Implementar, en este orden y con pruebas: `grilla.py` y preparación del dominio (DEM, pendiente, orientación, cobertura, máscara, infraestructura recortada) → cliente Open-Meteo → cliente GEE (NDVI/NDMI) → módulo WindNinja (incluida la prueba de linealidad y la caché) → mapa de combustibles v1 y tabla de parámetros → humedad de combustible (FFMC). Entregable: pipeline reproducible `scripts/preparar_evento.py --evento SL-2024-LASLAGUNAS`.
