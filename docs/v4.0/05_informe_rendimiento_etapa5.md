# Etapa 5 — Informe de rendimiento y decisión sobre el dominio de ejecución

Fecha: 2026-10-14. Script: `scripts/benchmark.py` (secciones A–D). Resultados crudos: `data/resultados/benchmark/benchmark_20261014T194645.json` y `parcial.jsonl`. Hardware: AMD Ryzen 5 8600G (6 núcleos / 12 hilos), 31,2 GB RAM, Windows 11, Python 3.14, numba 0.68. Todos los valores son mediciones de este entorno.

## 1. Autómata celular: grillas crecientes (sección A)

Entradas sintéticas homogéneas (pastizal GR2, humedad 1 h 6 %, viento uniforme 6 m/s desde 250°), Δt = 60 s, 16 vecinos. A1: una ignición central, 48 h. A2: nueve igniciones en malla, 72 h (frente grande, quema 60–75 % del dominio).

| Dominio | Celdas | A1: tiempo | A1: ms/paso | A1: frente máx | A2: tiempo | A2: ms/paso | A2: quemadas | A2: frente máx | Memoria pico del proceso |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 km² | 555.025 | 1,28 s | 0,44 | 2.235 | 2,84 s | 0,66 | 413.473 (37.213 ha) | 11.374 | 0,26 GB |
| 1.000 km² | 1.110.916 | 1,78 s | 0,62 | 2.982 | 4,32 s | 1,00 | 752.813 (67.753 ha) | 15.984 | 0,34 GB |
| **1.500 km²** | 1.666.681 | 2,08 s | 0,72 | 3.660 | 5,29 s | 1,22 | 1.075.679 (96.811 ha) | 19.420 | 0,42 GB |
| **2.000 km²** | 2.223.081 | 2,01 s | 0,70 | 4.228 | 6,21 s | 1,44 | 1.388.124 (124.931 ha) | 22.687 | 0,51 GB |
| **2.500 km²** | 2.792.241 | 2,43 s | 0,84 | 4.756 | 7,25 s | 1,68 | 1.699.294 (152.937 ha) | 25.326 | 0,59 GB |

Lectura: el costo por paso crece con el tamaño del frente activo (≈ 0,06 µs por celda activa y vecino), no con el número de celdas de la grilla; la memoria crece linealmente con la grilla (≈ 0,13 GB por millón de celdas, por las capas estáticas y el tiempo de llegada). Quemar el 60 % de los 2.500 km² (153.000 ha) en 72 h cuesta 7 s.

## 2. Paso temporal y vecindad (sección B, 1.500 km², 48 h, una ignición)

| Δt | Pasos | Tiempo | Celdas quemadas | Frente máx |
|---|---:|---:|---:|---:|
| 30 s | 5.760 | 2,53 s | 233.238 | 3.659 |
| **60 s** | 2.880 | 2,02 s | 233.238 | 3.660 |
| 120 s | 1.440 | 1,78 s | 233.238 | 3.760 |
| 300 s | 576 | 1,62 s | 233.238 | 3.991 |
| 600 s | 288 | 1,58 s | 232.825 (−0,18 %) | 4.518 |
| 60 s, 8 vecinos | 2.880 | 1,76 s | 155.571 (−33 %: frente octogonal más lento en diagonales) | 2.150 |

El esquema de avance acumulado por enlace hace el resultado casi independiente de Δt (idéntico entre 30 y 300 s; −0,2 % a 600 s). Se mantiene **Δt = 60 s** como compromiso entre precisión temporal de los registros horarios (error de ignición ≤ Δt) y costo. Los 8 vecinos quedan descartados por el sesgo direccional (ya visto en la Etapa 4).

## 3. Composición del viento horario (sección D)

Biblioteca unitaria WindNinja (72 direcciones, 100 m) → interpolación angular, escalado lineal y remuestreo bilineal a la grilla de 30 m: **202 ms por hora** (dominado por el remuestreo de dos capas de 2,8 M celdas). Para 516 h ≈ 104 s, es decir, la mayor parte del tiempo de la simulación real (§4). Optimización disponible si hiciera falta: precalcular las 72 clases ya remuestreadas a 30 m (72 × 2 × 11 MB = 1,6 GB en disco, lectura por memoria mapeada) → ≈ 10 ms/h.

## 4. Evento real completo (sección C): `SL-2024-LASLAGUNAS`, 2024-09-18 15:00 UTC → 2024-10-10 03:00 UTC (516 h), sin calibrar (k = 1), sin mitigación

| Δt | Pasos | Tiempo total | ms/paso | Celdas quemadas | Frente máx | Memoria pico | Fin |
|---|---:|---:|---:|---:|---:|---:|---|
| 60 s | 27.780 | **128 s** | 4,6 | 2.663.501 (239.715 ha) | 18.338 (01/10 16 UTC) | 1,18 GB | 07/10 22:00 UTC: 12 h sin avance (tras lluvia, humedad 1 h 48 %) |
| 30 s | 55.560 | 146 s | 2,6 | 2.663.555 (239.720 ha) | 18.373 | 1,46 GB | ídem |

Progresión (Δt = 60 s): 4.054 ha a las 24 h, 15.894 ha a las 48 h, 37.895 ha a las 72 h, 92.090 ha a los 7 días, 225.638 ha a los 14 días. **Sin calibración ni mitigación el modelo quema prácticamente todo el combustible del dominio** (96 % de las celdas combustibles) hasta que la lluvia del 6–7 de octubre eleva la humedad por encima de la extinción. Esto no es un resultado de validación: muestra (a) que el dominio completo se simula en ~2 min incluso en el peor caso, y (b) que la calibración de las Etapas 6–7 deberá actuar sobre la velocidad (k_clase, WAF, humedad viva) y sobre la hipótesis de ignición, porque el incendio observado (40.048 ha) fue contenido por el combate y por la heterogeneidad real que la clasificación v1 no captura.

Almacenamiento por simulación completa: `t_llegada_s.tif` 11,2 MB (float32 LZW), `estado_final.tif` 0,04 MB, `serie_horaria.csv` 0,06 MB, `registro.json` < 0,01 MB. Instantáneas horarias derivadas (uint8 comprimido o PNG): 0,01–0,02 MB cada una; 516 h ≈ 10 MB si se materializan, aunque la interfaz puede derivarlas del tiempo de llegada.

## 5. Costos de preparación de datos (Etapa 3, medidos)

| Componente | Costo | Reutilización |
|---|---|---|
| DEM Copernicus (GEE, dominio + margen) | 75 s | por dominio |
| Meteorología Open-Meteo (16 puntos, 23 días) | 22 s | por evento (caché) |
| NDVI/NDMI Sentinel-2 (mediana de 40 escenas a 20 m) | 1.215 s | por evento (caché) |
| Biblioteca WindNinja 100 m (72 direcciones) | 72 × 35,1 s = 42,1 min; 5,76 GB pico | por dominio (todos los eventos) |
| Mapa de combustibles + humedad | < 2 s | por evento |
| Derivados en disco | 400 MB (viento 264 MB; DEM 76 MB; índices 28 MB; combustibles 24 MB) | |

WindNinja a 60 m es ejecutable (86 s y 15,3 GB por corrida; 72 corridas ≈ 1,7 h) pero no necesario para la cadena operativa.

## 6. Estimación del tiempo total de una simulación histórica

Con datos preparados: **≈ 2–3 min** por simulación completa de 21 días sobre 2.500 km² (incluido el viento horario), lo que permite calibración por barrido de parámetros (p. ej. 50 corridas ≈ 2 h) y análisis de sensibilidad. Primera ejecución para un dominio nuevo: + 45 min (WindNinja) + 20 min (índices) + 2 min (DEM, meteorología).

## 7. Decisión sobre el dominio

**Se mantiene el dominio completo de 2.500 km² a 30 × 30 m.** Ningún componente lo justifica reducir: el autómata procesa el peor caso (quema total) en 128 s con 1,2 GB; el viento cuesta 42 min una sola vez por dominio; la memoria pico total es < 6 GB (WindNinja) frente a 31 GB disponibles. Las alternativas de 2.000 y 1.500 km² no se activan. La resolución de 30 m no se modifica.

## 8. Componentes que dominarían el costo si se escalara

1. Composición del viento a 30 m (0,2 s/h): precalcular clases remuestreadas si se ejecutan cientos de simulaciones.
2. Índices GEE (20 min por evento): inherente al cálculo servidor; reutilizable.
3. WindNinja por dominio: lineal con el número de clases de dirección (reducir a 36 clases de 10° halvaría el costo; se evaluará si la interpolación angular lo justifica).
4. Dominios mayores (provincia completa, 76.000 km²): grilla de 84 M celdas → memoria del autómata ≈ 11 GB y WindNinja inviable a 100 m en una sola malla; requeriría teselado por subdominios. Fuera del alcance actual.
