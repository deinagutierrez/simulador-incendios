# v3.1 — Paso 3: recalibración de k por grupo de clases con forma + tiempo

Fecha: 2026-10-28. Script: `scripts/barrido_libre.py --modo k`. Variante `libre_v2`, `factor_waf` 1,0, combinación `recomendada`
de cada ficha (hora + punto, `docs/v3.1/02`). Objetivo: **puntaje = (IoU a igual superficie + fracción de primeras detecciones a
tiempo) / 2** (`docs/v3.1/01`, `velocidad_vs_focos.md`). Resultados: `resultados/v3.1/paso3_k/barrido_calibracion.csv` y `validacion.csv`.

## 1. Diseño
- **Grupos** (como `docs/v3.0/12`): A = pastizal, pastura/cultivo, arbustal abierto (clases 1–3); B = arbustal cerrado, bosque abierto
  (4–5); C = bosque cerrado, plantación (6–7). Valor vigente: **kA 0,75 / kB 2 / kC 5**.
- **Grilla**: kA ∈ {0,5; 0,75; 1; 1,5} × kB ∈ {1; 2; 3; 5} × kC ∈ {3; 5; 8} = 48 combinaciones.
- **Calibración** (mismos seis eventos que `docs/v3.0/12`): Las Lagunas, Mesilla, Renca, Chilcas, Aguada, Piscu Yacu — 288 corridas.
- **Validación ciega**: Puertas, Pampita, Rincón, Chacras, con el k vigente y los tres mejores candidatos.

## 2. Calibración
La superficie vuelve a ser plana: las 12 mejores combinaciones están entre 0,532 y 0,547.

| k (A / B / C) | Puntaje | IoU igual sup. | A tiempo | Atrasado | Adelantado |
|---|---|---|---|---|---|
| **1 / 3 / 5** (mejor) | **0,547** | 0,418 | 0,711 | 0,131 | 0,133 |
| 0,75 / 3 / 5 | 0,546 | 0,422 | 0,702 | 0,147 | 0,126 |
| 0,75 / 3 / 3 | 0,541 | 0,436 | 0,673 | 0,156 | 0,121 |
| 0,75 / 2 / 5 (vigente) | 0,532 | 0,429 | 0,658 | 0,215 | 0,102 |

Por evento, la mejora es **sólo de Las Lagunas** (0,27 → 0,39 con 1 / 3 / 5); Chilcas, Aguada y Renca empeoran levemente y Mesilla
y Piscu Yacu no cambian. El óptimo de cada evento está en lugares distintos de la grilla (Renca 1,5 / 1 / 3; Las Lagunas 0,5 / 5 / 3;
Mesilla 1 / 1 / 3), otra vez sin un k común que los satisfaga a todos.

## 3. Validación ciega

| k (A / B / C) | Puntaje validación (4) | Puntaje calibración (6) | **Puntaje 10 eventos** | IoU 10 eventos | A tiempo 10 eventos |
|---|---|---|---|---|---|
| **0,75 / 2 / 5 (vigente)** | **0,509** | 0,532 | 0,522 | **0,436** | 0,618 |
| 0,75 / 3 / 5 | 0,504 | 0,546 | **0,529** | 0,427 | 0,644 |
| 1 / 3 / 5 | 0,500 | 0,547 | 0,528 | 0,426 | 0,645 |
| 0,75 / 3 / 3 | 0,480 | 0,541 | 0,516 | 0,429 | 0,614 |

En validación todos los candidatos quedan **por debajo** del vigente (Rincón cae a 0,57 con kC 3; Puertas −0,02). Sobre los diez
eventos la mejor alternativa gana +0,007 de puntaje y pierde 0,009 de IoU: **no hay mejora**.

## 4. Decisión y lectura
1. **Se mantiene k = 0,75 / 2 / 5.** La ganancia en calibración es de un solo evento y no se transfiere a los eventos que no se
   usaron para ajustar; cambiar k sería sobreajustar a Las Lagunas.
2. **Las Lagunas sí responde a kB** (arbustal cerrado / bosque abierto): con kB 3 el puntaje sube de 0,27 a 0,40, la forma de 0,37
   a 0,43 y los focos a tiempo de 18 % a 37 %. Que un megaincendio necesite propagar más rápido en bosque que los incendios chicos
   apunta a condiciones que el modelo no distingue (sequía extrema, curado, combustible acumulado) o a procesos que el autómata
   no tiene (salto de focos). Queda registrado como hipótesis para un factor de "régimen extremo" o para el paso 4; aun con kB 3,
   el 60 % de los lugares de Las Lagunas sigue atrasado.
3. Mismo resultado que `docs/v3.0/12` con otra métrica: el error que queda no es de k global.

## 5. Estado de v3.1 tras los pasos 1–3
Cambios que quedan: horas de ignición acotadas por los focos y puntos recalculados (`recomendada` en las fichas). `factor_waf` y k
quedan en los valores de v3.0. El puntaje medio de la simulación libre (librev2) pasa de 0,39 (h0) a 0,52, todo por la ignición.
