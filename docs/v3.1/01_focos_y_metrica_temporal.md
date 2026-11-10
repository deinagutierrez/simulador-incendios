# v3.1 — Paso 1: focos VIIRS de los diez eventos y métrica temporal de la propagación libre

Fecha: 2026-10-27. Scripts: `scripts/extraer_focos.py`, `scripts/evaluar_temporal.py`. Funciones nuevas en
`incendios_sl/validation/metricas.py`: `iou_igual_superficie` y `metricas_primera_deteccion`. Prueba: `test/v3.1/test_metricas_v31.py`.
Resultados: `resultados/v3.1/evaluacion_temporal/linea_base_v3.0_libre_vs_librev2.csv` (+ `.por_pasada.json`).

## 1. Para qué
La v3.0 evalúa la velocidad contra la fecha de extinción o el "Contenido" del SNMF. En los incendios chicos el fuego se
detuvo por el combate, así que esa fecha no mide la propagación libre. La única evidencia de propagación libre son las
pasadas satelitales de las primeras horas. Este paso arma esa evidencia para los diez eventos y una métrica para usarla en
los pasos 2 (viento, `factor_waf`) y 3 (k por clase).

## 2. Focos (`catalogo/hotspots_v3.1/`)
Fuente principal: `datos/crudos/viirs_snpp_san_luis_recortado.csv` (FIRMS, VIIRS SNPP, toda la provincia, 2012–2026,
57.952 detecciones; hora `acq_time` en UTC). Se suman los NOAA-20 ya descargados de GEE en `catalogo/hotspots/` (Las Lagunas
y Mesilla); de esos archivos se descartan las pasadas SNPP que repiten una de FIRMS (mismo satélite a ≤ 10 min).
Filtro: del día anterior a la primera hipótesis de ignición hasta el fin de la simulación, a ≤ 750 m de la cicatriz.
La carpeta es nueva para que v3.0 siga leyendo `catalogo/hotspots/` sin cambios.

| Evento | Focos | Pasadas | Primera detección (UTC) | Hipótesis 0 de la ficha (UTC) |
|---|---|---|---|---|
| Chilcas 2022 | 8 | 2 | 05/12 05:24 (3 focos débiles, FRP ≤ 1,2 MW, borde N) | 05/12 16:00 |
| Pampita 2022 | 10 | 2 | 02/09 18:50 | 02/09 16:00 |
| Piscu Yacu 2022 | 45 | 4 | **27/08 19:03** (junto al punto SNMF) | 28/08 13:00 |
| Puertas 2022 | 110 | 7 | 12/01 18:19 | 12/01 16:00 |
| Renca 2022 | 177 | 8 | **06/09 05:12** (3 focos en el extremo N, donde está la ignición alt1) | 06/09 16:00 |
| Aguada 2023 | 0 | 0 | — (sin VIIRS SNPP) | — |
| Chacras 2023 | 3 | 2 | 12/11 17:35 (falta NOAA-20 del 11/11, no está en el archivo) | 11/11 16:00 |
| Rincón 2023 | 10 | 2 | 19/09 05:25 (1 foco débil, dentro de la cicatriz) | 19/09 16:00 |
| Las Lagunas 2024 | 6.855 | 36 | 18/09 17:26 (NOAA-20) | 18/09 13:00 |
| Mesilla 2024 | 55 | 7 | 02/09 17:28 (NOAA-20) | 02/09 16:00 |

**Las horas de ignición de Piscu Yacu y Renca son tardías**: hay focos antes que cualquiera de las tres hipótesis de la ficha.
Renca ya tiene 71 focos en una franja de 10 km N–S a las 17:35 UTC del 06/09, 1,5 h después de la hipótesis 0. En Chilcas y Rincón
hay focos débiles de madrugada; pueden ser el inicio o una quema menor (a confirmar).

## 3. Métricas
- **IoU a igual superficie** (forma): IoU en el instante en que la simulación quemó tantas celdas como la cicatriz. No depende de la velocidad.
- **Primeras detecciones** (velocidad): sólo cuenta la primera detección de cada lugar (sin otro foco anterior a ≤ 375 m); un píxel
  que sigue ardiendo no dice cuándo llegó el fuego. El fuego llegó entre la pasada anterior (≤ 13 h antes con SNPP/NOAA-20) y la
  detección. Para cada foco, con la llegada simulada más temprana a ≤ 375 m:
  `a_tiempo` (det − 13 h ≤ sim ≤ det + 1 h), `adelantado` (sim < det − 13 h: demasiado rápido), `atrasado` (sim > det + 1 h:
  demasiado lento o ignición posterior), `no_alcanzado`. Error con signo en horas (0 si está a tiempo).

## 4. Línea base: las 20 corridas libre / librev2 de v3.0 (ignición recomendada, hipótesis horaria 0)

| Evento | IoU igual sup. libre / v2 | Primeras det. | A tiempo libre / v2 | Adelantado v2 | Atrasado v2 | Error mediano v2 (h) |
|---|---|---|---|---|---|---|
| Chilcas | 0,46 / 0,43 | 8 | 0,38 / 0,38 | 0,00 | 0,63 | +1,7 |
| Pampita | 0,57 / 0,56 | 8 | 0,50 / **0,75** | 0,13 | 0,13 | 0,0 |
| Piscu Yacu | 0,47 / 0,50 | 28 | 0,00 / 0,00 | 0,00 | **1,00** | +19,6 |
| Puertas | 0,30 / 0,31 | 86 | 0,16 / 0,21 | **0,45** | 0,34 | 0,0 |
| Renca | 0,55 / 0,59 | 127 | 0,20 / 0,20 | 0,06 | **0,74** | +9,6 |
| Aguada | 0,49 / 0,52 | 0 | — | — | — | — |
| Chacras | 0,04 / 0,58 | 2 | 0,00 / 0,00 | **1,00** | 0,00 | −10,9 |
| Rincón | 0,47 / 0,48 | 8 | 0,50 / 0,50 | 0,00 | 0,50 | +1,9 |
| Las Lagunas | 0,41 / 0,37 | 2.635 | 0,20 / 0,18 | 0,04 | **0,78** | +21,2 |
| Mesilla | 0,28 / 0,38 | 20 | 0,05 / **0,40** | 0,05 | 0,55 | +1,4 |

## 5. Lectura
1. **Contra los satélites, la propagación libre no es demasiado rápida: en general llega tarde.** Sólo Puertas (45 % adelantado) y
   Chacras (2 focos) muestran exceso de velocidad. "Demasiado rápido" (v3.0) venía de comparar con la extinción en incendios que
   el combate detuvo.
2. **Gran parte del atraso es la hora de ignición**, no la física: en Piscu Yacu y Renca hay focos antes de la ignición simulada.
   En Las Lagunas la primera pasada (17:26 UTC, 4,5 h después de la hipótesis 0) ya muestra 85 focos en 5,5 km.
3. libre_v2 está más a tiempo que libre en Pampita y Mesilla (humedad de retardo), igual en el resto.
4. Limitaciones: Aguada sin focos; Chacras con 2 focos (falta el NOAA-20 del 11/11, que sólo estaba en GEE); MODIS no se usa
   (1 km). La ventana de 13 h supone una pasada cada ~12 h; con nubes, la pasada anterior útil puede ser más vieja.

## 6. Consecuencia para los pasos siguientes
Antes de tocar el viento (paso 2) hay que **fijar la hora de ignición con las primeras detecciones**; si no, `factor_waf`
compensaría un error de hora con un error de física. Propuesta para el paso 2: (a) nuevas hipótesis horarias acotadas por la
primera detección (Piscu Yacu 27/08, Renca madrugada del 06/09, Las Lagunas y Mesilla mañana del día de detección); (b) recién
entonces, el barrido de `factor_waf` con las dos métricas.
