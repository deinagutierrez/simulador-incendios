# docs/v3.1 — mejoras de la simulación libre

> **Cerrada el 2026-10-29.** La siguiente vuelta sigue en `docs/v3.2/README.md` (copia de v3.1).

La v3.1 parte de una copia exacta de la v3.0 (código en `src/v3.1`, escenarios en `escenarios/v3.1`, pruebas en `test/v3.1`,
resultados en `resultados/v3.1`). La metodología e informes 01–13 siguen en `docs/v3.0`; acá sólo va lo nuevo.
Las fichas de `escenarios/v3.1/eventos` ya incluyen las igniciones de búsqueda inversa del 2026-10-27.

Plan (simulación libre, sin barreras ni contención):

| Paso | Qué | Informe | Estado |
|---|---|---|---|
| 1 | Focos VIIRS de los diez eventos y métrica temporal por primeras detecciones | `01_focos_y_metrica_temporal.md` | hecho |
| 2 | Hora de ignición acotada por los focos; barrido de `factor_waf` con forma + tiempo | `02_hora_ignicion_y_factor_waf.md` | hecho: horas nuevas en 6 eventos, 3 puntos nuevos; `factor_waf` se queda en 1,0 |
| 3 | Recalibración de k por clase con el objetivo combinado | `03_recalibracion_k.md` | hecho: no mejora en validación ciega; k se queda en 0,75 / 2 / 5 (Las Lagunas sí mejora con kB 3) |
| 4 | Viento local: promedio escalar, puntos IFS (IDW), WindNinja diurno horario | `04_viento_local.md` | V0–V3 hechos: sólo el promedio escalar mejora (+0,007) y **queda adoptado** (`viento.fuente_horaria: escalar` en modelo_v1 y modelo_v2); el diurno de WindNinja no cambia el campo fuera de laderas > 20°. V4 (WindNinja por puntos) pendiente, baja prioridad |

Al final, comparación v3.0 vs v3.1 con las mismas métricas: **hecha el 2026-10-28** en
`resultados/v3.1/comparacion_v30_vs_v31/comparacion_v30_vs_v31_20261028.md`. Puntaje librev2: v3.0 original 0,392 → v3.0 con
ignición recomendada 0,522 → v3.1 final 0,529 (libre: 0,326 → 0,422 → 0,447). Las 20 corridas finales con `visor.html` están en
`resultados/v3.1/<EVENTO>-<fecha>-h<n>-<ign>-libre|librev2`.

Nota de referencia: `velocidad_vs_focos.md` explica cómo se decide si el fuego simulado es muy rápido o muy lento con los
focos de calor (y por qué no con las fechas del SNMF), con la tabla de la línea base librev2.

**Pendiente para que la comparación sea justa (anotado el 2026-10-27):** si el paso 2 cambia la hora de ignición, la línea
base libre / librev2 (`resultados/v3.0/<EVENTO>-<AAAAMMDD>-h0-<ign>-libre|librev2`, corridas con la hipótesis horaria 0) ya
no es comparable. Hay que **volver a correr libre y librev2 con la combinación `recomendada` de cada ficha v3.1** (hora y punto;
el paso 2 cambió la hora en 6 eventos y el punto en Piscu Yacu, Puertas y Rincón), en `resultados/v3.1`, y comparar v3.1
contra esas corridas, no contra las de h0. Así se separa lo que aporta la hora de lo que aporta
el viento o k.
