> **Repetición del 2026-11-17, después de la decisión D-E3-35 (cruce por umbral en v3.1). No es la evaluación formal.**
> La evaluación formal de E-E3-4 es `E-E3-4_resultado.md` (2026-11-16, commit `d4118d8`) y sigue valiendo para el código de
> ese commit. Esta repetición usa el mismo guion, los mismos trazos etiquetados y el mismo criterio, sobre el commit
> `54a0bdd` (rama `v31-cruce-umbral`), para comprobar que las intervenciones siguen siendo reproducibles con la regla nueva.
> La corrió quien hizo el cambio (LisandroV2002, con Claude), no la otra persona.

# Resultado del prerregistro E-E3-4 — Las intervenciones son reproducibles

Evaluación generada por `herramientas/e_e3_4.py`. Prerregistro: `E-E3-4_intervenciones.md` (etiqueta `prerregistro-E-E3-4`); trazos y horas: `E-E3-4_trazos.json` (etiqueta `prerregistro-E-E3-4-trazos`: el archivo es el de la etiqueta).

## Veredicto

**Global: se cumple.** Pares corrida–motor hechos: 15 de 15; planes de intervención cumplidos en todos: sí.

| Criterio | Umbral | Resultado |
|---|---|---|
| A. Desde la bitácora | 0 celdas distintas en el tiempo de llegada y la misma cadena | **se cumple** |
| B. Offline | IoU ≥ 0,99 y la misma longitud de cortafuego (la aplicada) | **se cumple** |

## Quién y con qué

| | |
|---|---|
| Fecha | 2026-11-17 10:08 |
| Evaluó | LisandroV2002 (repeticion tras D-E3-35, no es la evaluacion formal) |
| Código | cambio de git `54a0bddbd0ed` (rama `v31-cruce-umbral`); código sin registrar: 0 archivo(s) |
| Motores congelados | sha256 del conjunto `2b32757194d2510bcbc680056f803694be064fc968e35de9c1ab579c10621106`; intactos antes: sí; después: sí |
| Insumos sin cambios | sí |
| Equipo | Windows-11-10.0.26300-SP0, 20 núcleos, Python 3.14.7 |
| Alcance | 5 corridas × 3 motores, 48 h, comparaciones A y B |

## Insumos (sha256)

| Insumo | Archivo | sha256 |
|---|---|---|
| prerregistro | `docs/etapa3/prerregistros/E-E3-4_intervenciones.md` | `7183d6188a3299df…` |
| trazos | `docs/etapa3/prerregistros/E-E3-4_trazos.json` | `06a4c909b743a6ea…` |
| ficha_v31 | `escenarios/v3.1/eventos/SL-2024-LASLAGUNAS.yaml` | `730c4aca89ead23a…` |
| ficha_v40 | `escenarios/v4.0/eventos/SL-2024-LASLAGUNAS.yaml` | `8ff452244d6a2169…` |
| meteo_dominio | `datos/inputSimulacion/meteo/SL-2024-LASLAGUNAS_ecmwf_ifs_20240917T00_20241010T03_b839008a1f1545e2_dominio.csv` | `a2496054ef2cd3ff…` |
| clase_v31 | `datos/inputSimulacion/combustibles/SL-2024-LASLAGUNAS/combustible_clase_SL-2024-LASLAGUNAS.tif` | `32ed159618fdb348…` |
| barreras_enlaces_v31 | `datos/inputSimulacion/barreras/barreras_enlaces_las_lagunas_potrerillos.npz` | `b4602bf795ac2f55…` |

## Por corrida y motor

| Corrida | Motor | Intervenciones (aplicadas / esperadas) | Plan cumplido | A: celdas distintas | A: cadena igual | B: IoU final | B: longitud aplicada | B: misma longitud | Sup. vivo / offline |
|---|---|---|---|---|---|---|---|---|---|
| 1 | v4.0 | 0 / 0 | sí | 0 | sí | 1,000000 | 8506,11 m | sí | 12234,6 / 12234,6 ha |
| 1 | v3.1-librev2 | 0 / 0 | sí | 0 | sí | 1,000000 | 8506,11 m | sí | 31162,6 / 31162,6 ha |
| 1 | v3.1-libre | 0 / 0 | sí | 0 | sí | 1,000000 | 8506,11 m | sí | 33916,0 / 33916,0 ha |
| 2 | v4.0 | 1 / 1 | sí | 0 | sí | 1,000000 | 8506,11 m | sí | 12234,6 / 12234,6 ha |
| 2 | v3.1-librev2 | 1 / 1 | sí | 0 | sí | 1,000000 | 8506,11 m | sí | 31162,6 / 31162,6 ha |
| 2 | v3.1-libre | 1 / 1 | sí | 0 | sí | 1,000000 | 8506,11 m | sí | 33916,0 / 33916,0 ha |
| 3 | v4.0 | 2 / 2 | sí | 0 | sí | 1,000000 | 17008,00 m | sí | 12627,0 / 12627,0 ha |
| 3 | v3.1-librev2 | 2 / 2 | sí | 0 | sí | 1,000000 | 16588,00 m | sí | 30642,8 / 30642,8 ha |
| 3 | v3.1-libre | 2 / 2 | sí | 0 | sí | 1,000000 | 15288,00 m | sí | 32678,5 / 32678,5 ha |
| 4 | v4.0 | 2 / 2 | sí | 0 | sí | 1,000000 | — | sí | 12875,6 / 12875,6 ha |
| 4 | v3.1-librev2 | 2 / 2 | sí | 0 | sí | 1,000000 | — | sí | 31404,5 / 31404,5 ha |
| 4 | v3.1-libre | 2 / 2 | sí | 0 | sí | 1,000000 | — | sí | 34337,9 / 34337,9 ha |
| 5 | v4.0 | 4 / 4 | sí | 0 | sí | 1,000000 | 17008,00 m | sí | 12745,3 / 12745,3 ha |
| 5 | v3.1-librev2 | 4 / 4 | sí | 0 | sí | 1,000000 | 14448,00 m | sí | 30944,0 / 30944,0 ha |
| 5 | v3.1-libre | 4 / 4 | sí | 0 | sí | 1,000000 | 14598,00 m | sí | 33725,4 / 33725,4 ha |

## Cortafuegos

| Corrida | Motor | Origen | t (min) | Ancho | Dibujada | Aplicada | Offline | Geometría offline | Igual |
|---|---|---|---|---|---|---|---|---|---|
| 1 | v4.0 | inicial | 0 | 10 m | 8506,11 m | 8506,11 m | 8506,11 m | polilinea | sí |
| 1 | v3.1-librev2 | inicial | 0 | 10 m | 8506,11 m | 8506,11 m | — | enlaces | sí |
| 1 | v3.1-libre | inicial | 0 | 10 m | 8506,11 m | 8506,11 m | — | enlaces | sí |
| 2 | v4.0 | pausa | 360 | 10 m | 8506,11 m | 8506,11 m | 8506,11 m | polilinea | sí |
| 2 | v3.1-librev2 | pausa | 360 | 10 m | 8506,11 m | 8506,11 m | — | enlaces | sí |
| 2 | v3.1-libre | pausa | 360 | 10 m | 8506,11 m | 8506,11 m | — | enlaces | sí |
| 3 | v4.0 | pausa | 360 | 6 m | 10008,00 m | 10008,00 m | 10008,00 m | polilinea | sí |
| 3 | v4.0 | pausa | 720 | 25 m | 7000,00 m | 7000,00 m | 7000,00 m | polilinea | sí |
| 3 | v3.1-librev2 | pausa | 360 | 6 m | 10008,00 m | 10008,00 m | — | enlaces | sí |
| 3 | v3.1-librev2 | pausa | 720 | 25 m | 7000,00 m | 6580,00 m | — | enlaces | sí |
| 3 | v3.1-libre | pausa | 360 | 6 m | 10008,00 m | 10008,00 m | — | enlaces | sí |
| 3 | v3.1-libre | pausa | 720 | 25 m | 7000,00 m | 5280,00 m | — | enlaces | sí |
| 5 | v4.0 | pausa | 360 | 6 m | 10008,00 m | 10008,00 m | 10008,00 m | polilinea | sí |
| 5 | v4.0 | pausa | 720 | 25 m | 7000,00 m | 7000,00 m | 7000,00 m | polilinea | sí |
| 5 | v3.1-librev2 | pausa | 360 | 6 m | 10008,00 m | 10008,00 m | — | enlaces | sí |
| 5 | v3.1-librev2 | pausa | 720 | 25 m | 7000,00 m | 4440,00 m | — | enlaces | sí |
| 5 | v3.1-libre | pausa | 360 | 6 m | 10008,00 m | 10008,00 m | — | enlaces | sí |
| 5 | v3.1-libre | pausa | 720 | 25 m | 7000,00 m | 4590,00 m | — | enlaces | sí |

## Desvíos del plan e intervenciones recortadas o rechazadas

- corrida 3 · v3.1-librev2: `720-0` recortada — se quitaron 235 enlaces que llegan a celdas ya alcanzadas por el fuego
- corrida 3 · v3.1-libre: `720-0` recortada — se quitaron 981 enlaces que llegan a celdas ya alcanzadas por el fuego
- corrida 5 · v3.1-librev2: `720-0` recortada — se quitaron 1529 enlaces que llegan a celdas ya alcanzadas por el fuego
- corrida 5 · v3.1-libre: `720-0` recortada — se quitaron 1439 enlaces que llegan a celdas ya alcanzadas por el fuego

## Lo que hay que saber para leerlo

- Ignición: la definición es la del evento con la hipótesis 1 y los puntos de la ficha (`hipotesis: 1`, `ignicion: snmf`), como en E-E3-1; se comprueba que la ficha diga la misma hora que el archivo de trazos y se informa la que usó cada corrida (`t_inicio_utc`).
- Intervenciones en vivo: `pausar` con `en_t_sim_min` y, en cada pausa, `intervenir` por la entrada estándar y `reanudar` (el camino del servidor). La reproducción (A) la hace el propio proceso motor con `reproduccion` = {de, raiz, bitacora}.
- Longitud de cortafuego (criterio B, D-E3-28 punto 14), cómo se mide (lo fijó quien escribe, antes de ver resultados): v4.0 carga geometrías; para las líneas se mide la longitud dentro de la grilla de la geometría que carga la corrida offline y se compara con la aplicada en vivo (tolerancia 0,011 m por el redondeo a 0,01 m), y además que toque las mismas celdas. Si la geometría offline son los centros de las celdas (cuando la polilínea recortada no rasteriza exacto), no tiene longitud: se compara que cargue las mismas celdas. v3.1 no carga líneas sino enlaces: se compara que la matriz offline tenga exactamente los enlaces aplicados (sha256 de cada trazo, unión y espejo); con eso, la longitud de lo cargado es la aplicada.
- En v4.0 el viento manual gira durante la hora siguiente a la pausa y en v3.1 cambia de golpe en la hora de la pausa; en los dos casos la corrida offline usa la serie editada del mismo modo, así que no cuenta como diferencia.
- B se mide sobre la huella final (celdas con tiempo de llegada); se informa también la cantidad de celdas con tiempo de llegada distinto, que no es criterio.
- Un solo evento (Las Lagunas 2024), como declara el prerregistro. No dice si un cortafuego real detendría el fuego.

## Cómo repetirlo

```
python herramientas/e_e3_4.py --evaluador NOMBRE
```
