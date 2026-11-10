# v3.1 — Paso 4: viento local (promedio escalar, puntos IFS, WindNinja diurno horario)

Fecha: 2026-10-28. Script: `scripts/barrido_libre.py --modo viento --fuentes ...`. Variante `libre_v2`, `factor_waf` 1,0, k 0,75 / 2 / 5,
combinación `recomendada` de cada ficha. Objetivo: **puntaje = (IoU a igual superficie + fracción de primeras detecciones a tiempo) / 2**
(`docs/v3.1/01`). Resultados: `resultados/v3.1/paso4_viento/barrido_v0_v2.csv`, `barrido_v3.csv` y la unión `barrido_v0_v3.csv`.

## 1. Qué se cambia
El viento de v3.0 es **un solo viento por hora para todo el dominio**: el promedio *vectorial* de los 16 puntos Open-Meteo
(ECMWF IFS, ~9 km) multiplicado por la biblioteca unitaria de WindNinja (72 direcciones, sólo relieve, sin hora del día).
La fuente se elige con `viento.fuente_horaria` (código: `wind/horario.py`, `simulation/entradas.py::viento_por_fuente`):

| Variante | `fuente_horaria` | Qué hace |
|---|---|---|
| V0 | `biblioteca` | v3.0: promedio vectorial × biblioteca |
| V1 | `escalar` | misma dirección, velocidad = promedio *escalar* de los 16 puntos (el vectorial pierde 5–10 % en mediana) |
| V2 | `idw_puntos` | cada punto IFS con su viento, interpolado por distancia (IDW, potencia 2) sobre la biblioteca |
| V3 | `windninja_diurno` | WindNinja corrido **hora por hora** con `diurnal_winds` (temperatura, nubosidad estimada, fecha y hora local) |
| V4 | `windninja_puntos` | WindNinja hora por hora con los 16 puntos como estaciones + diurno — **pendiente** |

V3 y V4 necesitan los campos generados antes con `scripts/generar_viento_horario.py` (malla 100 m, vegetación `brush`; horas desde la
ignición recomendada hasta max(ignición + 24 h, último foco + 2 h), tope 120 h; 512 horas en los diez eventos, ~45 s cada una,
~1 MB por hora en `datos/inputSimulacion/viento/horario/<evento>_<fuente>/`). Fuera de ese período se usa la biblioteca
(sólo pasa en Las Lagunas después de la hora 120).

## 2. Resultados (10 eventos)

| Variante | Puntaje | IoU igual sup. | A tiempo | Atrasado | Adelantado | Error mediano (h) |
|---|---|---|---|---|---|---|
| V0 biblioteca | 0,522 | 0,436 | 0,618 | 0,157 | 0,211 | 1,1 |
| **V1 escalar** | **0,529** | **0,440** | **0,629** | **0,144** | 0,212 | **0,5** |
| V2 idw_puntos | 0,506 | 0,421 | 0,599 | 0,161 | 0,212 | 0,8 |
| V3 windninja_diurno | 0,523 | 0,437 | 0,618 | 0,157 | 0,211 | 1,2 |

Puntaje por evento:

| Evento | V0 | V1 | V2 | V3 |
|---|---|---|---|---|
| Chilcas | 0,463 | 0,463 | 0,427 | 0,462 |
| Pampita | 0,656 | 0,653 | 0,556 | 0,656 |
| Piscu Yacu | 0,747 | 0,747 | 0,741 | 0,747 |
| Puertas | 0,430 | **0,448** | 0,408 | 0,430 |
| Renca | 0,544 | 0,557 | **0,603** | 0,544 |
| Aguada | 0,518 | 0,521 | 0,520 | 0,519 |
| Chacras | 0,288 | 0,289 | 0,290 | 0,289 |
| Rincón | 0,661 | **0,673** | 0,581 | 0,664 |
| Las Lagunas | 0,271 | **0,298** | 0,276 | 0,271 |
| Mesilla | 0,646 | 0,641 | 0,658 | 0,646 |

Las Lagunas (error mediano de los focos): V0 +21,2 h, V1 +15,1 h, V2 +18,1 h, V3 +21,2 h.

## 3. Por qué V3 da igual que V0
V3 coincide con V0 en todos los eventos (diferencias ≤ 0,003). Se verificó que no es un error de conexión:
- El simulador usa el campo horario en todas las horas (`horas_sin_campo_horario` = 0, salvo Las Lagunas después de 120 h).
- Comparando el campo diurno con la biblioteca para la misma hora y el mismo viento de dominio (Renca, Rincón, Las Lagunas, Mesilla;
  278 horas), la diferencia mediana es **< 1° en dirección y 1–2 % en velocidad**, aun con viento calmo (Rincón, 1,4 m/s).
- Prueba directa con `diurnal_winds` true / false (Rincón, 19/09/2023 15 h local, 1,5 m/s, cielo despejado: el caso más
  favorable para flujos de ladera). WindNinja sí activa el módulo diurno (lee la hora, la inicialización pasa de 0,6 a 2,8 s), pero:

| Pendiente | % del dominio | Diferencia vectorial media | % celdas con > 0,5 m/s |
|---|---|---|---|
| 0–5° | 78 % | 0,02 m/s | 0,1 % |
| 5–10° | 15 % | 0,04 m/s | 0,7 % |
| 10–20° | 4 % | 0,11 m/s | 4,8 % |
| > 20° | 2 % | 0,28 m/s | 18 % |

El flujo diurno de WindNinja sólo aparece en las laderas de más de 20°, que a malla de 100 m son el 2 % del dominio, y ahí no
se queman los incendios estudiados (pastizal y arbustal de piedemonte y llanura). **El viento diurno no explica el error**.

## 4. Decisión y lectura
1. **V3 no aporta**: se descarta como mejora general. Los campos quedan generados (~0,5 GB) por si se quiere usar para Las Lagunas a
   malla más fina, pero no conviene subirlos a Drive.
2. **V2 empeora** (−0,016): con puntos IFS a 9 km la variación espacial es ruido del modelo, no estructura real; sólo Renca mejora
   (dirección), y Pampita y Rincón caen mucho. **V4 combina V2 con el diurno de V3**, así que lo esperable es un resultado parecido
   a V2. Queda pendiente, pero con baja prioridad.
3. **V1 (escalar) es la única mejora**: +0,007 de puntaje, +0,004 de IoU, +0,011 de focos a tiempo, error mediano de 1,1 a 0,5 h.
   Mejora en Puertas, Renca, Rincón y Las Lagunas, y baja apenas en Pampita (−0,003) y Mesilla (−0,005). No es una calibración
   (no se ajusta ningún parámetro): corrige un sesgo conocido del promedio vectorial, que frena el viento cuando los puntos no
   apuntan igual. **Adoptada el 2026-10-28**: `viento.fuente_horaria: escalar` en `escenarios/v3.1/modelos/modelo_v1.yaml` y
   `modelo_v2.yaml` (en los dos, para que libre y librev2 sigan siendo comparables). Para reproducir v3.0, `fuente_horaria: biblioteca`.
4. Las Lagunas sigue atrasado con cualquier viento (+15 h en el mejor caso). Junto con el paso 3 (sólo mejora con kB más alto), esto
   apunta a algo que el modelo no tiene (régimen de sequía extrema, salto de focos), no al viento.
