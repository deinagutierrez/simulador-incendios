# v3.1 — Paso 2: hora de ignición acotada por los focos y barrido de `factor_waf`

Fecha: 2026-10-27. Script: `scripts/barrido_libre.py` (modos `hora`, `punto`, `waf`). Variante `libre_v2` (modelo_v2 sin
barreras ni contención). Métricas del paso 1 (`docs/v3.1/01`): forma = IoU a igual superficie; tiempo = fracción de primeras
detecciones VIIRS a tiempo; **puntaje = (IoU + fracción a tiempo) / 2** (Aguada, sin focos: sólo IoU).
Resultados: `resultados/v3.1/paso2_hora/` (`barrido_hora.csv`, `barrido_punto.csv`, `control_hora_puntos_nuevos.csv`) y
`resultados/v3.1/paso2_waf/` (`barrido_waf.csv`, `resumen_por_waf.csv`).

## 1. Hora de ignición (2a)
**Regla.** La ignición tiene que ser anterior a la primera detección y posterior a la pasada previa sin focos (≤ 12–13 h antes
con SNPP + NOAA-20). Candidatos: horas en punto cada 2 h en las 14 h previas a la primera detección (o a la `cota_superior_utc`
de la ficha si es anterior, caso Chacras), más las tres hipótesis de la ficha como referencia. Se elige el mejor puntaje dentro
de la ventana. Una hora fuera de la ventana no se acepta aunque puntúe más (contradice la observación).

**Acople hora–punto.** El punto de ignición de la búsqueda inversa se había elegido con la hipótesis 0. Al adelantar la hora el
viento es otro y ese punto puede dejar de servir (Piscu Yacu: IoU 0,50 → 0,11). Por eso, en los eventos donde cambió la hora, se
repitió la búsqueda del punto (~40 candidatos sobre la cicatriz, `--modo punto`) y se volvió a controlar la hora con el punto
elegido. Se cambia de punto sólo si el puntaje mejora ≥ 0,05.

| Evento | Primera detección (UTC) | Hora anterior → nueva (UTC) | Punto | Puntaje antes → después | IoU | A tiempo |
|---|---|---|---|---|---|---|
| Chilcas | 05/12 05:24 (3 focos débiles a 400 m de alt1) | 05/12 16 → **05/12 04** | alt1 (igual) | 0,40 → 0,46 | 0,43 → 0,30 | 0,38 → 0,63 |
| Pampita | 02/09 18:50 | 02/09 16 (igual) | SNMF | 0,66 | 0,56 | 0,75 |
| Piscu Yacu | 27/08 19:03 | 28/08 13 → **27/08 18** | **nuevo** (alt1) | 0,25 → **0,75** | 0,50 → 0,49 | 0,00 → **1,00** |
| Puertas | 12/01 18:19 | 12/01 16 → **12/01 17** | **nuevo** (alt1) | 0,26 → 0,43 | 0,31 → 0,21 | 0,21 → 0,65 |
| Renca | 06/09 05:12 (3 focos junto a alt1) | 06/09 16 → **05/09 18** | alt1 (igual) | 0,39 → 0,54 | 0,59 → 0,55 | 0,20 → 0,54 |
| Aguada | sin focos | 31/08 16 (igual) | alt1 | 0,52 | 0,52 | — |
| Chacras | 11/11 18:45 (cota de la ficha; NOAA-20 no está en el archivo) | 11/11 16 (igual) | alt1 | 0,29 | 0,58 | 0,00 (*) |
| Rincón | 19/09 05:25 (1 foco débil a 500 m de alt1) | 19/09 16 → **19/09 04** | **nuevo** (alt2) | 0,49 → **0,66** | 0,48 → 0,45 | 0,50 → 0,88 |
| Las Lagunas | 18/09 17:26 | 18/09 13 (igual; 06 UTC sólo +0,02) | alt0 | 0,27 | 0,37 | 0,18 |
| Mesilla | 02/09 17:28 | 02/09 16 → **02/09 11** (hipótesis 2 existente) | alt2 (igual) | 0,39 → **0,65** | 0,38 → 0,34 | 0,40 → **0,95** |
| **Media** | | | | **0,39 → 0,52** | 0,47 → 0,44 | 0,29 → 0,62 |

(*) Chacras: sólo 2 focos SNPP del 12/11 en el archivo provincial; el NOAA-20 del 11/11 (31 focos) sólo estaba en GEE. La
métrica temporal de Chacras no es confiable hasta recuperar esos focos.

**Lectura.** El tiempo mejora mucho (de 29 % a 62 % de primeras detecciones a tiempo) a costa de algo de forma (IoU 0,47 → 0,44):
la búsqueda inversa del punto había optimizado sólo la forma. Los focos de madrugada de Renca, Chilcas y Rincón caen a 400–500 m
de los puntos que la búsqueda inversa había encontrado sin mirar los focos: dos evidencias independientes del mismo origen.

**Fichas v3.1.** Cada ficha tiene un bloque `recomendada: {ignicion, hipotesis}` con la combinación elegida (la que usan los
barridos), las horas nuevas al final de `hora_utc_hipotesis` y los puntos nuevos al final de `ignicion_alternativas` (los
índices anteriores no cambian). v3.0 no se tocó.

## 2. `factor_waf` (2b)
Barrido 0,5–1,5 en los diez eventos con la combinación recomendada.

| factor_waf | 0,5 | 0,6 | 0,7 | 0,8 | 0,9 | **1,0** | 1,15 | 1,3 | 1,5 |
|---|---|---|---|---|---|---|---|---|---|
| Puntaje medio | 0,41 | 0,45 | 0,48 | 0,50 | 0,52 | **0,52** | 0,53 | 0,53 | 0,52 |
| IoU medio | 0,39 | 0,41 | 0,42 | 0,43 | 0,43 | **0,44** | 0,43 | 0,43 | 0,41 |
| A tiempo | 0,43 | 0,50 | 0,54 | 0,57 | 0,61 | **0,62** | 0,64 | 0,64 | 0,64 |
| Atrasado | 0,36 | 0,29 | 0,24 | 0,20 | 0,17 | **0,16** | 0,12 | 0,10 | 0,10 |

Mejor por evento: 0,7–0,8 en Chilcas, Pampita, Piscu Yacu y Mesilla (mejoras ≤ 0,015); 1,15–1,5 en Puertas, Renca, Aguada,
Rincón y Las Lagunas (Las Lagunas +0,09 con 1,5 y sigue subiendo; Renca +0,05).

**Lectura.**
1. **Frenar el viento no mejora la simulación libre**: con 0,5–0,8 crece el atraso y baja la forma. La idea de v3.0 de que la
   propagación era "demasiado rápida" no se sostiene contra los satélites una vez corregida la hora (paso 1).
2. El óptimo global (1,15–1,3) gana sólo +0,008 de puntaje y pierde forma; **se mantiene `factor_waf = 1,0`**.
3. Lo que queda es por evento y de signo opuesto: un factor de viento único no lo corrige. El caso grande es **Las Lagunas**,
   atrasada (error mediano +21 h con WAF 1; 18 % a tiempo) aun con WAF 1,5: el problema no es el viento sino la velocidad en
   bosque/arbustal o el salto de focos. Va al paso 3 (k por clase con el objetivo combinado).

## 3. Para la comparación final
La línea base libre / librev2 de v3.0 se corrió con la hipótesis horaria 0 (ver `docs/v3.1/README.md`, pendiente). Para que la
comparación sea justa hay que **repetir libre y librev2 con la combinación `recomendada` de las fichas v3.1** y medir con las
mismas métricas; así se separa lo que aporta la hora (este paso) de lo que aporten k (paso 3) y el viento local (paso 4).
