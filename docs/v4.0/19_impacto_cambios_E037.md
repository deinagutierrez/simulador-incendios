# Etapa 19: impacto de los cambios D41–D43 (lote E037) y próximo paso

Fecha: 2026-10-28 · Bitácora: E037.

**Fuentes:**
- Lote E037: 73 corridas en `resultados/v4.0/<evento>/<evento>-<fecha>-h<N>-<punto>-barreras/`, con tablas en `resultados/v4.0/resumen_lote_E037.md/.csv` y la comparación en `lote_E037/_comparacion_E037.csv` (script `lote_E037/comparar.py`).
- Bases de comparación: lote E033 («libre», WindNinja) y ablación E035 (`resultados/ablacion_E035/_analisis/`).
- Tiempos observados: banco `eventos_fase1.csv`, con T80 y Tref = mín(último pase con focos, contención SNMF).

## 1. Qué se corrió

Todas las combinaciones de hora y punto de ignición de los 10 eventos (73), con la configuración vigente del panel:
- variante `barreras`: caminos como barrera, sin combate (D42);
- viento `serie` y `parada.escapes: potencial` (D41);
- horas h3/h4 en 4 fichas y `alt1` en Chilcas (D43);
- tope en la cicatriz (D38–D40, D44);
- validación y figuras.

**Resultado de la corrida:**
- 71 corridas nuevas y 2 salteadas, porque ya existían de E036 con la misma configuración. Les faltaba `visor.html` y se generó.
- 0 fallos. La verificación independiente encontró 73/73 carpetas completas, con los parámetros esperados y la hora de ignición igual a la de la ficha.
- Duración: 18 min los 9 eventos menores (12 a la vez) y 2,5 min Las Lagunas (3 a la vez).
- La estimación previa para Las Lagunas (45–90 min) fue **muy alta**: con el tope, cada corrida termina a las 59–61 h simuladas.

## 2. Ficha de comparabilidad

| Campo | E037 (nuevo) | E033 (base) | E035 «barreras» (base del viento) |
|---|---|---|---|
| Igniciones | las 51 h0–h2 de los 9 menores (para comparar) | las mismas | las mismas |
| Variante / barreras | `barreras` (caminos activos) | `libre` (caminos solo reducen la carga) | `barreras` |
| Viento | serie | WindNinja | WindNinja |
| Parada | escapes potencial (sin efecto sin combate) | escapes v3 | escapes v3 |
| Tope, instante de evaluación, referencia, máscara, evaluador | iguales (última `evaluacion_utc`; cicatriz sobre celdas combustibles; mismo código) | iguales | iguales |
| Figuras / carga de la máquina | con figuras, 12 a la vez | con figuras, 9 a la vez | sin figuras, 14 a la vez |
| Rol de los eventos | **vistos** (desarrollo); los `altN` derivan de la cicatriz | igual | igual |
| n | 9 eventos (10 con Las Lagunas) | igual | igual |

**Lectura:**
- E037 frente a E033 mide el **efecto conjunto** de barreras y viento. E037 frente a E035 «barreras» aísla el **viento**.
- Los **segundos** no son comparables entre lotes, porque cambian las figuras y la carga de la máquina: el costo se toma de E035, que es emparejado.
- Todo es orientativo: los eventos son vistos y n < 10 eventos independientes por grupo.

## 3. Resultados (primero lo que no gusta)

1. **El conjunto no mejoró.** Comparado con E033, sobre las mismas 51 igniciones (dato):
   - IoU mediana: 0,131 → 0,131.
   - |Δt| mediana: 24,9 → 24,5 h.
   - Alcanzan la cicatriz: 48 → 47.
   - IoU mejor / igual / peor: 17 / 13 / 21.
2. **Las barreras de caminos agravan los eventos lentos** (dato; Δt mediano E033 → E037):
   - Chilcas: +29,9 → +42,2 h.
   - Renca: +14,2 → +24,5 h.
   - Puertas: alcanzaba la cicatriz en 1 de 3 igniciones; ahora en 0 de 3.
   - El IoU baja en Pampita (0,40 → 0,21), Puertas (0,15 → 0,05) y Aguada (0,21 → 0,15).
   - Los eventos rápidos casi no cambian: Chacras −37,5 → −34,9 h y Mesilla −27,5 → −26,9 h.
   - Chacras mejora la forma (0,19 → 0,27).
3. **El viento uniforme no cambió nada** (dato, frente a E035 «barreras» con WindNinja): Δ de IoU mediana +0,000; Δ de horas hasta el tope +0,00. Confirma D41: la ganancia es solo de cómputo, −40 % emparejado en E035.
4. **Las horas nuevas (h3/h4) mejoran algo la forma, pero no el tiempo** (dato):
   - IoU mediana h0–h2 → h3–h4: Chilcas 0,12 → 0,14; Piscuyacu 0,25 → 0,36; Renca 0,08 → 0,12; Rincón 0,03 → 0,05.
   - |Δt| mejora en Chilcas (42 → 32 h) y Rincón (5,9 → 2,0 h). Empeora en Piscuyacu (3,1 → 11,0 h: pasa a ser rápido) y Renca (24 → 31 h).
   - (inferencia) La hora corregida no compensa la lentitud de Chilcas y Renca, que viene del combustible.
5. **Chilcas `alt1` (extremo N) da la mejor forma y el peor tiempo** (dato):
   - IoU mediana 0,17 (máx. 0,21), frente a 0,12 de `alt0` y 0,14 del SNMF.
   - Tarda +54 h en igualar la cicatriz: el fuego simulado necesita unas 59 h para recorrer los 5,5 km N–S, y los focos muestran que el real lo hizo en el día.
   - (inferencia) La velocidad en el TU1 de 2022 (67 % de la cicatriz) es baja; es lo que corrige 3.3b.
6. **Las Lagunas 2024 queda cerca en tiempo** (dato):
   - Alcanza la cicatriz (39.649 ha) a las 58,9–61,1 h, con IoU de 0,23–0,24.
   - Llega al 80 % de la superficie a las 54–57 h, frente a un **T80 observado de 60–64 h: Δ de −6 a −7 h**.
   - Contra Tref (contención SNMF, unas 147 h), Δ ≈ −88 h, pero ese Tref incluye semanas de focos residuales: para este evento T80 es la referencia adecuada (protocolo v1.3 §5).
   - (inferencia) No es comparable con la Fase 1, que no tenía tope ni barreras de caminos.
7. **Sesgo que persiste** (dato, todo E037):
   - La sierra, en los eventos 2023–2024, avanza demasiado rápido: Chacras −35 h, Mesilla −27 h.
   - Los incendios de 2022 avanzan demasiado lento: Chilcas +42 h, Renca +24 h y Puertas, que no llega a 2.062 ha en 107 h.
   - Pampita, Piscuyacu y Rincón quedan dentro de ±8 h.

## 4. Decisión

**Decisión que hay que tomar:** qué parámetros cambiar o revisar ahora para acercar la velocidad de avance y el tiempo.

**Evidencia:** secciones 3.1–3.7 (dato) y E035 (combustible 3.3b: corrige Puertas, reduce Renca y Chilcas, −33 % de cómputo).

**Lo que no sabemos:**
- Si 3.3b sumado a las barreras de caminos corrige los eventos lentos sin acelerar los rápidos: no se probó junto.
- Qué perilla explica el exceso de velocidad en la sierra (WAF, límite de viento, k de pastos): no se probaron.
- Si el resultado se mantiene en eventos no vistos.

**Opciones:**

| Opción | A favor | En contra | Costo |
|---|---|---|---|
| 1. Lote E038 = E037 con `regla_combustible: 3.3b` (73 corridas, ~20 min) y, si mejora, adoptarla por defecto | es la única palanca que en E035 corrigió los lentos de 2022; las barreras los hicieron más lentos, así que ahora la necesidad es mayor | eventos vistos; la Fase 2 la tenía como parámetro a decidir | bajo |
| 2. Para la sierra (Chacras, Mesilla), ablación de 1–2 perillas: `factor_waf` (0,8 / 0,6) o `k_grupo` de pastos GR (0,8) | ataca el único sesgo que ninguna prueba movió | con 10 eventos, más de 3 parámetros libres sobreajusta (protocolo §9) | bajo–medio |
| 3. Retomar la Fase 2 con validación cruzada sobre 3.3b y la perilla elegida | es el camino del protocolo para fijar valores | ≈ 6 h; la grilla original incluía combate (ya no aplica) y hay que rediseñarla | medio |
| 4. Volver a «Fuego libre» por defecto | en E033 los eventos lentos lo eran menos | contradice el criterio de barreras del ambiente (D42); no resuelve el sesgo de fondo | nulo |
| 5. Usar h3/h4 como hipótesis principal en esas 4 fichas | mejora la forma en 4 de 4 | el tiempo empeora en 2 de 4; es una regla derivada (cota − 1 h) | nulo |

**Recomendación**, con confianza **media**:
1. **Correr ya la opción 1** (E038, 3.3b) y decidir el valor por defecto con esos números.
2. Si los lentos se corrigen, seguir con la **opción 2** para la sierra.
3. Con ambas, rediseñar y **retomar la Fase 2** (opción 3) con 2–3 parámetros libres como máximo y validación cruzada dejando un evento afuera.
4. Mantener las barreras de caminos (criterio D42) y no tocar todavía las hipótesis principales.
5. Para lotes exploratorios, usar `figuras: false` y generar figuras solo de las corridas finales: los eventos grandes con mapas horarios son los que más tiempo agregan (inferencia por el costo de E037, no medido aislado).

**Qué la cambiaría:**
- Que 3.3b con barreras acelere los eventos 2023–2024 o baje el IoU en más de la mitad de los eventos.
- Que la perilla de la sierra empeore Las Lagunas, que hoy está a −7 h del T80.

**Qué necesito del usuario:** aprobar el lote E038 (3.3b) y decidir si la Fase 2 se rediseña sin combate.
