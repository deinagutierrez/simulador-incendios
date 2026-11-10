# Etapa 23: validación cruzada de la calibración del combustible por familia (E041)

Fecha: 2026-10-29 · Bitácora: E042 · Prerregistro: `lote_E041/PRERREGISTRO.md` (2026-10-28, antes de correr) · Alcance: solo v4.0.

**Fuentes:**
- `lote_E041/_puntajes_E041.csv` y `_validacion_cruzada_E041.csv`, producidos por `lote_E041/evaluar.py`.
- Workflow `wf_c61d7ebd-c6d`: el agente principal ejecutó `evaluar.py`; **dos verificadores** recalcularon todo desde el prerregistro sin leer ese script.

## 1. Verificación

Las tres implementaciones coinciden en todo: J de las 9 configuraciones, S_e, las 10 vueltas de la validación cruzada y el veredicto. Las diferencias aparecen recién en la cuarta cifra decimal o más abajo, por redondeo.

**Controles de los verificadores:**
- Están las 657 carpetas (9 configuraciones × 73 igniciones).
- `k_grupo` coincide con la configuración en todas.
- La hora de ignición es igual a `t_inicio`.
- 654 corridas alcanzan la cicatriz y 3 llegan al horizonte.

**Ambigüedades del prerregistro** (todas resueltas igual por los tres):
- un empate exacto (Rincón, diferencia 0) no cuenta como mejora;
- |Δt| = 12 h exacto entra en la tolerancia;
- la mediana de un número par de valores es el promedio de los dos centrales.

## 2. Resultados

J es la mediana de S_e sobre los 10 eventos; cuanto menor, mejor.

| SH \ TU | 1 | 1,5 | 2 |
|---|---|---|---|
| **1** | **0,8906** (base) | 0,9110 | 0,9698 |
| **1,5** | 0,8849 | 0,9240 | 0,9671 |
| **2** | **0,8838** (elegida con los 10) | 0,9323 | 0,9655 |

**Validación cruzada, dejando un evento afuera:**

| Evento afuera | Elegida (SH, TU) | S elegida | S base | Diferencia |
|---|---|---|---|---|
| Chilcas 2022 | (2; 1) | 1,532 | 1,829 | **−0,297** |
| Pampita 2022 | (1; 1,5) | 0,591 | 0,601 | −0,010 |
| Piscuyacu 2022 | (1; 1,5) | 0,896 | 0,765 | **+0,130** |
| Puertas 2022 | (1; 1,5) | 0,849 | 0,834 | +0,015 |
| Renca 2022 | (2; 1) | 0,940 | 0,940 | +0,000 |
| Aguada 2023 | (1; 1,5) | 0,839 | 0,841 | −0,003 |
| Chacras 2023 | (2; 1) | 1,203 | 1,187 | +0,016 |
| Rincón 2023 | (2; 1) | 1,000 | 1,000 | 0 |
| Las Lagunas 2024 | (1; 1,5) | 0,753 | 0,777 | −0,024 |
| Mesilla 2024 | (2; 1) | 1,255 | 1,244 | +0,011 |

**Criterio prerregistrado:**
- mejora en **4 de 10** eventos (se exigían ≥ 6);
- mediana de la diferencia **+0,0002** (se exigía < 0).

**Veredicto: NO SE ADOPTA.** `k_grupo` SH y TU quedan en 1.

## 3. Lectura

1. **No generaliza** (dato).
   - La mejora de J con (2; 1) frente a la base, de 0,8906 a 0,8838, sale casi entera de **Chilcas**: −0,297 por menos atraso.
   - Cuando Chilcas queda afuera, la elección cambia. La elegida es **inestable**: 5 vueltas eligen (2; 1) y 5 eligen (1; 1,5).
   - Lo que mejora un evento empeora otro (Piscuyacu +0,130).
2. **Lo que falta mejorar es la forma, no el tiempo** (dato).
   - En la base, la mediana sobre eventos del término de tiempo es **0**: con la tolerancia de ±12 h y el medio peso de los adelantos, el evento típico ya queda dentro.
   - El término de forma (1 − IoU) vale 0,82–0,84 en todas las configuraciones: **es lo que domina J**.
   - Subir el bosque (TU 2) agrega penalización de tiempo (0,07–0,09) sin mejorar la forma.
3. (inferencia) La calibración por familia de combustible **ya no tiene margen** con este objetivo. El error que queda es de dónde va el fuego (IoU ≈ 0,13–0,16), no de cuándo llega.
   - Candidatos: el punto de ignición (los `altN` circulares y los SNMF fuera de la cicatriz), el viento de una sola serie para todo el dominio y la forma de la cicatriz de referencia.
4. **Límites:**
   - Eventos vistos; n = 10.
   - La tolerancia de 12 h y el medio peso de los adelantos son supuestos fijados de antemano.
   - Con otro objetivo, por ejemplo simétrico, el veredicto podría cambiar. Eso sería un prerregistro nuevo, no una relectura de este.

## 4. Próximo paso sugerido

1. **Mantener SH = TU = 1** y dar por cerrada la calibración por familia con estos 10 eventos.
2. **Decisión pendiente del usuario desde el informe 20:** si `regla_combustible: 3.3b` pasa a ser el valor por defecto de `modelo_v3`. Hoy es la base de todas estas comparaciones, pero el valor por defecto sigue en 3.3.
3. **Orientar la mejora a la forma.** Hay dos opciones:
   - analizar por qué el IoU es bajo: dirección del frente frente a la cicatriz, ignición, viento;
   - o tomar el IoU con la superficie fijada como la métrica principal del próximo prerregistro.
