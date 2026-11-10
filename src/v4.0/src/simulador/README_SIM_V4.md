# Simulador de propagación de incendios · autómata celular (Etapa 2)

Gemelo digital para la prevención y mitigación de incendios forestales, provincia de San Luis (UNSL).
Núcleo de simulación de **propagación libre** (sin mitigación ni agentes) sobre una grilla de 30 m, con el
modelo de Rothermel (1972) y los 40 modelos de combustible de Scott & Burgan (2005). Repositorio del
proyecto: https://github.com/gvcosta/Gemelos_Digitales_Incendios_UNSL

```
python -m simulador validar                                        # verifica el manifiesto de datos
python -m simulador run  --config escenarios/ejemplo_las_lagunas_2023.yaml
python -m simulador caso conjunto_prueba/las_lagunas_la_aguada_2023 [--todas | --variante t0_06h]
python -m simulador informe conjunto_prueba/las_lagunas_la_aguada_2023    # rearma evaluacion.md sin re-simular
python -m pytest tests -q                                          # 28 tests (física, simetría, E/S)
python scripts/preparar_datos.py                                   # copia insumos y arma el caso (una sola vez)
```

Requisitos: Python 3.11+ y `requirements.txt` (numpy, rasterio, geopandas, pyogrio, shapely, pyproj, matplotlib,
imageio, scipy, pyyaml, pytest). Probado con Python 3.14 en Windows.

---

## 1. Estructura

```
simulador_incendios/
├── manifiesto_datos.yaml          catálogo de TODAS las entradas (sha256, CRS, dtype, nodata, origen)
├── datos/                         insumos del dominio (copiados por scripts/preparar_datos.py)
│   ├── dominio/                   dominio.geojson (WGS84), grilla.json
│   ├── estaticos/                 topografia/ (mdt, pendiente, orientacion), combustible/ (sb40_AAAA.tif,
│   │                              parametros_sb40.csv, tablas del generador), infraestructura.gpkg
│   └── dinamicos/                 indices/ (NDVI_NDMI_AAAA_MM.tif, solo los meses usados), meteo/
├── conjunto_prueba/               un caso = una carpeta autocontenida (sección 7.1 del enunciado)
│   └── las_lagunas_la_aguada_2023/
├── escenarios/                    YAML de corridas
├── salidas/                       una subcarpeta por corrida (<fecha>_<nombre>, nunca se pisa)
├── scripts/preparar_datos.py      ÚNICO lugar con rutas de origen fuera de esta carpeta
├── simulador/
│   ├── io/        grilla.py, manifiesto.py, capas.py, meteo.py
│   ├── fuel/      sb40.py (tabla S&B), generar_sb40.py (MapBiomas → FBFM40)
│   ├── physics/   rothermel.py, humedad.py, viento.py, elipse.py
│   ├── ca/        estados.py, automata.py
│   ├── outputs/   indicadores.py, descripcion.py, figuras.py, geo.py
│   ├── evaluacion/ metricas.py, informe.py
│   ├── config.py, corrida.py, sintetico.py, __main__.py
└── tests/
```

El simulador **nunca lee fuera de `datos/` y `conjunto_prueba/`**; las rutas de los YAML son relativas a su
carpeta y se rechazan las que salgan de la raíz del simulador (`config.resolver`).

## 2. Dominio y grilla

| | |
|---|---|
| CRS | EPSG:5345 (POSGAR 2007 / Argentina faja 3) |
| Resolución | 30 × 30 m |
| Extensión | xmin 3513060 · ymin 6367770 · xmax 3563220 · ymax 6417900 |
| Tamaño | 1672 × 1671 = 2.793.912 celdas (≈ 2.500 km²) |

Al cargar, cada raster se compara con `grilla.json` (transform, ancho, alto, CRS): si no coincide, el simulador se
detiene (`ErrorGrilla`/`ErrorManifiesto`). Un escenario o caso puede definir una **ventana** (`grilla: {xmin, ymin,
xmax, ymax}`) alineada a la grilla del dominio; las celdas fuera de la ventana son `NO_COMBUSTIBLE` y, si el fuego
las toca, el estado horario lleva el aviso "el dominio quedó chico" (`toco_borde`).

## 3. Estándar de datos (sección 2 del enunciado)

**Manifiesto.** `manifiesto_datos.yaml` lista cada entrada con `nombre`, `ruta` (relativa), `tipo`, `crs`, `dtype`,
`nodata`, `unidades`, `rango`, `bandas`, `origen` (ruta y fuente originales), `fecha_preparacion`, `sha256` y los
valores por defecto que se completaron. Al iniciar, el simulador lee solo el manifiesto, verifica existencia y
sha256 (omisible con `--sin-sha` para corridas repetidas), grilla, dtype, nodata, rangos, códigos FBFM40, capas y
atributos de los vectores y columnas de las series meteorológicas. No hay correcciones silenciosas.

**Rasters.** GeoTIFF EPSG:5345 en la grilla exacta. `mdt.tif` int16 m (nodata −32768); `pendiente.tif` uint8 grados
(nodata 255); `orientacion.tif` uint16 grados 0 = N horario, 361 = plano (nodata 65535); `sb40_AAAA.tif` int16 códigos
FBFM40 (nodata −9999); `NDVI_NDMI_AAAA_MM.tif` int16 ×10000, 2 bandas (nodata −32768).

**Vectores.** `infraestructura.gpkg` (EPSG:5345) con `caminos` (`id`, `tipo` ∈ pavimentado/ripio/tierra/huella,
`ancho_m`), `viviendas` (`id`), `red_electrica` (`id`, `tension` ∈ AT/MT/BT). La fuente no trae ancho: se infiere
del tipo (pavimentado 8 m, ripio 7, tierra 5, huella 3, autopista 20) y queda registrado en el manifiesto.

**Meteorología horaria.** CSV con exactamente
`timestamp,temp_c,hr_pct,viento_kmh,viento_dir_deg,precip_mm,fuente`; `timestamp` ISO 8601 **con huso**
(America/Argentina/San_Luis, UTC−3); `viento_dir_deg` = dirección desde donde sopla (0 = N); viento a 10 m; una fila
por hora, sin huecos (se rechaza la serie si los hay). Se interpola linealmente al paso del AC; el viento por
componentes u/v.

**Ignición.** GeoJSON de puntos con `id`, `hora_ignicion` (ISO 8601 con huso) y, opcional, `usar` (bool).
**Perímetro observado.** GeoJSON de polígonos con `fecha` y `fuente`. **Focos.** GeoJSON de puntos con
`hora_deteccion` (UTC) y `frp`.

## 4. Modelo

### 4.1 Estados y transiciones (`ca/estados.py`)

```
NO_COMBUSTIBLE  nunca cambia (NB, agua, roca, urbano, camino ≥ 30 m, fuera del dominio)
COMBUSTIBLE  ──[avance desde una vecina en combustión ≥ d_ij; si es camino, llama ≥ umbral]──► IGNICION
IGNICION     ──[ignicion_delay_min, 0 por defecto]──► COMBUSTION
COMBUSTION   ──[todas las vecinas ya encendidas/no combustibles y t ≥ t_ign + τ]──► QUEMADO
COMBUSTION   ──[humedad muerta ≥ Mx del modelo (ROS = 0) y t ≥ t_ign + τ]──► QUEMADO   (extinción natural)
```
τ = 384/σ min (Anderson 1969). d_ij = 30 m ortogonal, 42,43 m diagonal, 67,08 m en los saltos de caballo
(vecindad de 16).

### 4.2 ROS (`physics/rothermel.py`)

Rothermel (1972) con la formulación de Andrews (2018): ponderación por clases (1 h, 10 h, 100 h, herbáceo
muerto, herbáceo vivo, leñoso), factores g_ij, humedad de extinción viva, η_M, η_s, ξ, Γ', factor de viento
φ_w = C·U^B·(β/β_op)^−E con el límite U ≤ 0,9·I_R, y factor de pendiente φ_s = 5,275·β^−0,3·tan²θ. Viento y pendiente se
combinan **vectorialmente** (BehavePlus/FARSITE): R_max = R0·(1 + |φ_w + φ_s|), rumbo de la cabeza = dirección del
vector resultante, viento efectivo U_eff invirtiendo φ_w. Intensidad de Byram I_B = I_R·τ·R/60 (kW/m) y longitud de
llama L = 0,45·I_B^0,46 ft (Byram 1959).

Modelos **dinámicos** (GR, GS, SH1, SH9, TU1, TU3): la carga herbácea se reparte entre muerta y viva según el
**curado**. Verificación: a 5 mi/h de viento a media llama y humedades 3/4/5/30/60 % la ROS en ch/h es
GR1 27 · GR2 66 · GR4 132 · GS2 39 · SH2 11 · SH5 91 · TU1 5 · TU5 14, coherente con las fichas de Scott &
Burgan (test `test_rothermel_orden_de_magnitud_scott_burgan`, tolerancia ±25 %). La comparación numérica fina
contra BehavePlus queda pendiente (ver 8).

### 4.3 Humedades (`physics/humedad.py`)

- Muerto 1 h: EMC de Simard (1968) con T y HR, retardo 1 h, piso 2 %; +2 puntos bajo dosel (TU/TL), +1 en laderas
  al sur con pendiente > 5°. 10 h y 100 h: relajación exponencial (τ = 10 h, 100 h) hacia la EMC, con arranque en
  equilibrio al inicio de la serie (por eso la serie empieza ≥ 24 h antes de la ignición). Lluvia: +3/+1,5/+0,5 puntos
  por mm (1 h/10 h/100 h), tope 35 %.
- Vivo: M (%) = clip(120 + 250·NDMI_mes, 50, 250). Curado = clip(1,5·(1 − NDVI_mes/NDVI_verano), 0,3, 1). Sin índices
  se usa la regla de S&B (curado por humedad herbácea).

### 4.4 Viento (`physics/viento.py`)

10 m → 20 ft (×1/0,87) → media llama × WAF. WAF sin dosel según Andrews (2012) con la profundidad del lecho; bajo
dosel 0,3 (TU) y 0,2 (TL). Ajuste topográfico v1: factor = 1 + 0,5·tanθ·cos(orientación − dir_viento) +
0,3·relieve/100 m, acotado a [0,7; 1,3] (barlovento y crestas aceleran; sotavento y hondonadas frenan). Interfaz
`viento_externo: {u, v}` para un campo WindNinja en GeoTIFF multibanda (banda = hora) en la grilla del estándar.

### 4.5 Forma elíptica y regla de transición (`physics/elipse.py`, `ca/automata.py`)

LB = 0,936·e^(0,2566·U) + 0,461·e^(−0,1548·U) − 0,397 (Anderson 1983; U en mi/h, LB ≤ 8), e = √(LB²−1)/LB,
R(θ) = R_max·(1−e)/(1−e·cosθ). Regla determinista por **tiempo de llegada**: `avance_k += R(θ_k)·Δt`, la vecina
se enciende cuando `avance_k ≥ d_k`, con el instante de llegada interpolado dentro del paso.

Dos detalles de implementación que importan:
- **Sub-pasos adaptativos** (condición tipo CFL): dentro de cada Δt el frente no avanza más de 0,9 celdas por
  sub-paso; sin esto la velocidad quedaría limitada a una celda por paso (Δt = 2 min → 15 m/min) y el área dependería
  del rumbo del viento.
- **Huygens discreto (origen heredado)**: un AC vecino a vecino subestima mucho los flancos de elipses alargadas
  (LB simulada 8 contra 3,85 teórica en la prueba). Cada celda hereda el origen de la elipse que la encendió y mide
  sus avances sobre los rayos que salen de ese origen; se re-ancla al superar `radio_huygens_m` (300 m), al cambiar
  de modelo de combustible o de factor de carga, o al cruzar un camino. Con esto la LB simulada queda dentro del
  10 % de Anderson y el área no depende del rumbo del viento (≤ 3 %).

**Vecindad de 16** (`vecindad: 16`, saltos de caballo a 67,08 m): los saltos exigen que las celdas intermedias sean
combustibles (no atraviesan caminos ni agua). Mejora la isotropía en terreno homogéneo, pero en el mosaico real de
combustibles a 30 m da ~50 % más de superficie que la de 8, porque la ROS que gobierna cada transición es la de la celda
emisora y los saltos no "pagan" las celdas lentas intermedias. Por eso el valor por defecto es 8; la mejora pendiente es
ponderar la ROS emisora con la receptora.

Modo **estocástico** (ensembles, semilla fija): p_k = 1 − exp(−R(θ_k)·Δt/d_k) (Alexandridis et al. 2008 adaptado;
la ponderación 1/√2 de las diagonales queda implícita en d_k). `ensemble: {n: N}` produce el mapa de probabilidad
de quemado.

### 4.6 Infraestructura

- **Caminos**: rasterizados; la celda camino reduce su carga en (1 − ancho/30) y solo se cruza si la longitud de
  llama del frente supera el umbral por tipo (pavimentado 2 m, ripio 1,5, tierra 1, huella 0,5). Un camino ≥ 30 m
  es `NO_COMBUSTIBLE`. Se informan km afectados y cortados.
- **Viviendas**: exposición (afectadas = dentro del área quemada; amenazadas = a < 100 m de celdas en combustión).
- **Red eléctrica**: km dentro del área quemada y en celdas en combustión. (Como fuente de ignición: usar un punto de
  la red en `ignicion`.)
- `modificador_combustible`: raster factor de carga (vacío por ahora) para la mitigación de la Etapa 3.
- *Spotting* experimental (`parametros.spotting.activo`, desactivado): probabilidad por intensidad de Byram y
  viento, distancia lognormal a sotavento, semilla fija.

### 4.7 Variables derivadas por celda
Hora de llegada (min desde t0), ROS máxima (m/min), intensidad de Byram máxima (kW/m), longitud de llama máxima
(m), rumbo de la cabeza, minuto de fin de combustión.

## 5. Salidas (`salidas/<fecha>_<nombre>/`)

| Producto | Archivo |
|---|---|
| Mapa por hora (hillshade + combustible, estados, isócronas, viviendas/red/caminos, flecha de viento, escala, norte, leyenda, indicadores, perímetro observado) | `mapa_hora_HH.png` |
| Animación y figura final de isócronas | `animacion.gif`, `isocronas_final.png` |
| Descripción por plantilla | `descripcion_hora_HH.txt` |
| Estado estructurado (contrato para los agentes Cronista y Asesor, `version` 1.0) | `estado_hora_HH.json` |
| GeoTIFF hora de llegada, intensidad, ROS, llama, estado final (+ probabilidad en ensembles) | `hora_llegada_min.tif`, `intensidad_max_kw_m.tif`, … |
| Perímetros por hora (WGS84) y serie de indicadores | `perimetros_horarios.geojson`, `serie_indicadores.csv` |
| Reproducibilidad | copia del YAML, `metadata.json` (semilla, versión, sha256 de los insumos), `log.txt` |
| En casos de prueba | `comparacion_observado.png`, `evaluacion.json`, `evaluacion.md`, `sim_<caso>_simulador_toa.tif` (compatible con `conjunto_pruebas/validacion/evaluar_simulacion.py`) |

Esquema de `estado_hora_HH.json` (v1.0): `superficie` {quemada_ha, incremento_ha, en_combustion_ha, consumida_ha},
`perimetro` {total_km, activo_km}, `frente` {rumbo_cabeza_deg/texto, velocidad_cabeza_m_min/km_h, ros_mediana_m_min,
intensidad_max_kw_m, longitud_llama_max_m, alcance_max_m, avance_alcance_m, celdas_activas}, `meteo` {temp_c, hr_pct,
viento_kmh, viento_dir_deg/texto, precip_mm_h, humedad_muerta_1h/10h/100h_pct}, `exposicion` {viviendas_afectadas,
amenazadas, a_salvo, total, tendido_km_quemado, tendido_km_en_combustion, caminos_km_afectados, caminos_km_cortados,
ids…}, `estado_celdas`, `centroide` {x, y, lon, lat}, `bbox`, `alertas`, `cambios` (respecto de la hora anterior).

## 6. Parámetros: bibliografía y a calibrar

| Parámetro | Valor | Estado |
|---|---|---|
| Tabla de los 40 modelos (cargas, SAV, profundidad, Mx, calor) | `datos/estaticos/combustible/parametros_sb40.csv` | Scott & Burgan (2005), transcripción |
| Constantes de Rothermel (ρ_p 32, S_T 0,0555, S_e 0,01, g_ij, límite de viento 0,9·I_R) | fijas | Rothermel (1972), Andrews (2018) |
| WAF sin dosel / bajo dosel | Andrews (2012) / 0,3 TU, 0,2 TL | bibliografía · **a calibrar** bajo dosel |
| Conversión 10 m → 20 ft | 1/0,87 | Turner & Lawson (1978) |
| LB de Anderson, tope 8 | fórmula | Anderson (1983), FARSITE |
| τ = 384/σ | fórmula | Anderson (1969) |
| EMC de Simard, piso 2 %; τ 1/10/100 h; lluvia +3/+1,5/+0,5 puntos/mm; exposición +2/+1 | ver 4.3 | método estándar · **a calibrar** (lluvia, exposición) |
| Humedad viva a, b, [min, max] | 120, 250, [50, 250] | **a calibrar** |
| Curado k, mínimo | 1,5, 0,3 | **a calibrar** |
| Ajuste topográfico del viento k_pend, k_relieve, [min, max] | 0,5, 0,3, [0,7; 1,3] | simplificación v1 · **a calibrar** |
| Anchos de camino por tipo; umbrales de llama | 8/7/5/3 m; 2/1,5/1/0,5 m | tabla propia · **a calibrar** |
| Buffer de amenaza a viviendas | 100 m | enunciado |
| radio_huygens_m, cfl, dt_sub_min | 300 m, 0,9, 0,1 min | numéricos (tests) |
| Spotting (p_max, I_ref, mediana, σ_log) | 0,05, 3000 kW/m, 150 m, 0,6 | **experimental** |

## 7. Caso de prueba y evaluación

`conjunto_prueba/las_lagunas_la_aguada_2023/` (ver su `LEEME.md`): cicatriz COE de 105,4 ha del incendio
"Las Lagunas y La Aguada" (31-08 → 01-09-2023), ventana 377 × 376 alineada al dominio, combustible pre-evento
(MapBiomas 2022 + NDVI verano 2023), meteorología ERA5 horaria desde 24 h antes, focos VIIRS, tres perímetros.
`python -m simulador caso <carpeta> --todas` corre la base y las variantes (t0 06/09/15/18 h, punto SNMF original,
vecindad 16, Δt 1 y 5 min) y escribe `evaluacion.md` con Sørensen, Jaccard, error de superficie, sesgo direccional,
comparación **a igual superficie** y la discusión. Los resultados y su discusión están en
`conjunto_prueba/las_lagunas_la_aguada_2023/evaluacion.md`.

Nota de inventario: el caso Las Huertas 2025 del enunciado cae fuera del dominio (menos del 2 % de la cicatriz
adentro, punto SNMF a 60 m del borde norte), por eso el primer caso pasó a ser este. El análisis quedó en
`../PLAN_simulador_etapa2.md`.

## 8. Validación del modelo (`tests/`)

- Simetría (4.5): círculo sin viento (error de radio < 10 %: 3,9 % con 8 y 16 vecinos), elipse con viento (LB dentro
  del 20 % de Anderson), elongación ladera arriba, área invariante al rumbo del viento 0/45/90° (< 5 %).
- Sensibilidad: Δt 1 vs 5 min (< 5 % de superficie); un factor a la vez (viento, HR, pendiente, humedad viva).
- Física: orden de magnitud de la ROS contra las fichas de S&B para GR1, GR2, GR4, SH2, SH5, TU1; monotonías;
  extinción por Mx; combinación vectorial; Byram; EMC; lluvia; elipse; WAF.
- E/S: ventanas alineadas, meteo inválida, interpolación del viento por componentes, manifiesto (sha alterado),
  carga de capas.
- **Pendiente**: comparación numérica contra BehavePlus para GR2, GR4, SH2, SH5 y TU1 con valores de referencia
  exactos (hoy solo lectura gráfica de las fichas, ±25 %).

## 9. Limitaciones declaradas

Fuego de superficie solamente (sin fuego de copas ni combustión de troncos); viento uniforme con ajuste topográfico
simple y sin acoplamiento fuego–atmósfera; meteorología de reanálisis ERA5 (celda de 0,25°) sin estaciones;
**sin supresión**: las corridas son de propagación libre, por lo que un incendio real contenido por bomberos
siempre quedará por debajo de lo simulado (de ahí la métrica a igual superficie); parámetros sin calibrar (tabla 6);
un solo caso de prueba y sin focos VIIRS sobre esa cicatriz; la tabla de S&B es una transcripción a revisar.

## Referencias

- Rothermel, R. C. (1972). *A mathematical model for predicting fire spread in wildland fuels*. INT-115.
- Scott, J. H.; Burgan, R. E. (2005). *Standard fire behavior fuel models*. RMRS-GTR-153.
- Anderson, H. E. (1983). *Predicting wind-driven wild land fire size and shape*. INT-305.
- Anderson, H. E. (1969). *Heat transfer and fire spread*. INT-69 (tiempo de residencia).
- Andrews, P. L. (2018). *The Rothermel surface fire spread model and associated developments*. RMRS-GTR-371.
- Andrews, P. L. (2012). *Modeling wind adjustment factor and midflame wind speed*. RMRS-GTR-266.
- Byram, G. M. (1959). Combustion of forest fuels. En *Forest Fire: Control and Use*.
- Simard, A. J. (1968). *The moisture content of forest fuels*. FF-X-14.
- Alexandridis, A. et al. (2008). A cellular automata model for forest fire spread prediction. *Appl. Math. Comput.* 204.
- Finney, M. A. (1998). *FARSITE: Fire Area Simulator*. RMRS-RP-4 (construcción de Huygens, combinación viento–pendiente).
