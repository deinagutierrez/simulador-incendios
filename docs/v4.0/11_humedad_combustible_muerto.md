# Etapa 11 — Humedad del combustible muerto: modelo de tiempo de retardo y prueba con focos

Fecha: 2026-10-20. Estado: **implementado y evaluado**; la recalibración de k con la humedad nueva queda pendiente (§6).

## 1. Problema
El v1 calcula la humedad del combustible muerto de 1 h con el FFMC horario canadiense (Van Wagner 1977) y deriva las de 10 h y 100 h sumando desplazamientos fijos. El FFMC describe la capa de hojarasca de coníferas: su constante de secado da un tiempo de respuesta efectivo de 6 a 10 h a 25 °C, el de un combustible de 10 h, no de 1 h. En Las Chacras 2023 (docs/06 §2.6) el modelo partía de 37 % de humedad al mediodía del 11/11 tras 3,6 mm de lluvia la víspera, bajaba a 10,5 % recién entre las 21 y 23 UTC y volvía a 20 % a las 00 UTC: el fuego simulado avanzó 4 horas y se apagó con 79 ha, mientras VIIRS registraba 31 detecciones con FRP 113 MW a las 18:45 UTC con HR 21 %.

## 2. Modelo implementado (`fuels/humedad.py`, variante `retardo_simard`)
- Humedad de equilibrio de **Simard (1968)** en función de temperatura y humedad relativa **[BIBLIO]**.
- Relajación exponencial hacia el equilibrio con tiempos de retardo **τ = 1, 10 y 100 h** por clase **[BIBLIO: Fosberg 1970; Bradshaw et al. 1978, NFDRS]**: `m(t+Δt) = EMC + (m − EMC)·exp(−Δt/τ)`.
- Lluvia: incremento de humedad de la ecuación del FFMC (Van Wagner 1987, BIBLIO) aplicado íntegro al 1 h y multiplicado por 0,5 y 0,25 para 10 h y 100 h **[HIPÓTESIS]**, con topes de saturación 35 / 40 / 45 % **[HIPÓTESIS]**; después la clase seca con su τ.
- La regla de extinción por lluvia acumulada de 24 h pasa de 5 a 15 mm en v2 **[HIPÓTESIS]**: con el modelo de retardo la lluvia actúa a través de la humedad.
- **Humedad de extinción por clase** calibrable: `humedad.mx_muerto_pct_clase` en el YAML reemplaza la del análogo de Scott & Burgan (15–25 %) en `motor.py`.
- Selección por configuración: `humedad.muerto_1h: ffmc_horario_vanwagner_1977` (v1, sin cambios, reproducible bit a bit) o `retardo_simard` (v2). `serie_humedad` escribe ambas variantes en `humedad_muerto_<evento>.csv` (columnas `*_rt` y `emc_pct`); `scripts/actualizar_humedad.py` las recalcula para todos los eventos a partir de la meteorología ya descargada (sin tocar índices ni combustibles).
- Pruebas: `tests/test_humedad.py` (equilibrio de Simard, secado en horas frente a días del FFMC, faltantes, tope por lluvia).

Comparación en Las Chacras, 11/11/2023 (lluvia 3,6 mm el 10-11/11; 28 °C, HR 21 % a las 18 UTC):

| Hora UTC | 12 | 15 | 18 | 21 | 00 (12/11) |
|---|---|---|---|---|---|
| FFMC (v1), % | 37,4 | 26,0 | 16,1 | 10,9 | 14,1 |
| Retardo (v2), % | ≈ 9 | ≈ 6 | ≈ 5 | ≈ 5 | ≈ 9 |

## 3. Prueba con focos (`scripts/evaluar_humedad.py`)
Cada foco VIIRS (con hora) o MODIS (sin hora: se asume la pasada de Aqua, 17:30 UTC, HIPÓTESIS) atestigua que a esa hora, en esa celda, el fuego avanzaba; la humedad simulada de 1 h debe ser menor que la humedad de extinción de la clase. Fracción de focos "no ardibles" según el modelo, 9.923 focos de los 10 eventos (`data/resultados/evaluacion_humedad/focos_vs_humedad.csv`):

| Variante | Mx del análogo | Mx = 12 % | Mx = 15 % | Mx = 20 % |
|---|---|---|---|---|
| FFMC (v1) | 0,5 % (Las Chacras: **66 %**) | 2,6 % (Chacras 92 %, Pampita 100 %) | 0,6 % | 0 |
| Retardo (v2) | **0** en los 10 eventos | 0 | 0 | 0 |

Medianas de humedad de 1 h en las horas de los focos: FFMC 4,8–16,1 %; retardo 3,5–5,7 % (equilibrio 3,4–5,7 %). El modelo de retardo es compatible con todos los focos; el FFMC falla exactamente en el evento con lluvia previa. La prueba no acota Mx por abajo (todo Mx ≥ 12 % pasa) porque los focos ocurren con humedad muy baja; para acotarla haría falta la prueba complementaria (horas y celdas sin propagación con humedad intermedia), pendiente.

## 4. Efecto en la propagación del primer día (v1 con FFMC frente a humedad de retardo, resto igual: k de 2024, WAF 1, sin barreras ni contención)
Corridas `<evento>_v2hum_*`. Primer instante = fin del día de ignición.

| Evento (ref. ha) | FFMC: sim / omisión / IoU | Retardo: sim / omisión / IoU |
|---|---|---|
| Las Chacras 2023 (244) | 79 / 0,86 / 0,12 (se apaga) | **839 / 0,06 / 0,27** (focos a tiempo 1,00) |
| Rincón del Carmen 2023 (164) | 44 / 1,00 / 0,00 | 85 / 1,00 / 0,00 |
| La Pampita 2022 (114) | 68 / 0,51 / 0,44 | **165 / 0,18 / 0,51** |
| Piscu Yacu 2022 (420) | 259 / 0,64 / 0,29 | **428 / 0,46 / 0,37** |
| La Aguada 2023 (125), alt0 | 224 / 0,50 / 0,22 | 569 / 0,00 / 0,22 |
| Las Chilcas 2022 (296) | 1.919 / 0,66 / 0,05 | 2.277 / 0,66 / 0,04 |
| Mesilla 2024 (182), alt1 | 516 / 0,45 / 0,17 | 938 / 0,37 / 0,11 |
| Renca 2022 (3.797), alt0 | 26.001 / 0,05 / 0,14 | 35.045 / 0,00 / 0,11 |
| Puertas 2022 (2.062) | 22.283 / 0,03 / 0,09 | 23.801 / 0,01 / 0,09 |
| Las Lagunas 2024 (40.052), h1 | 46.665 / 0,39 / 0,39 | 58.394 / 0,31 / 0,39 |

## 5. Lectura
1. El modelo de retardo **corrige el régimen de subestimación**: Las Chacras pasa de apagarse a recorrer la cicatriz (omisión 0,86 → 0,06) y mejora Pampita y Piscu Yacu; los tres eventos que el v1 subestimaba eran eventos húmedos o posteriores a lluvia. Rincón del Carmen no mejora: su problema es el viento (tarde calma en el modelo de 9 km), no la humedad.
2. Como el combustible queda más seco en todas las horas (medianas 3,5–5,7 % frente a 5–16 %), la propagación se acelera en todos los eventos: la **sobreestimación de los eventos ventosos empeora** (Mesilla 516 → 938 ha, Renca 26.000 → 35.000 ha). Eso es esperable, porque k se calibró con la humedad del FFMC y absorbía su sesgo húmedo. El IoU del evento de calibración no cambia (0,39) porque allí el FFMC ya estaba seco.
3. Con la humedad corregida, el error del primer día pasa a tener un único signo (sobreestimación, de 1,1× en Las Lagunas a 7× en Chilcas) y ya tiene sentido **recalibrar k por clase sobre los diez eventos**, separando calibración y validación (docs/06 §2.6, docs/10 §10.5). Es el paso siguiente; hasta entonces `modelo_v2.yaml` usa la humedad de retardo con los k de 2024.

## 6. Pendientes
- Recalibrar k por clase con la humedad de retardo (diez eventos; calibración 6, validación 4) y volver a evaluar barreras y contención.
- Prueba complementaria para acotar Mx por arriba (horas sin propagación observada con humedad intermedia).
- Factores de lluvia de 10 h y 100 h y topes de saturación: hipótesis sin dato local.
- Humedad viva: el escalado NDMI → LFMC sigue sin calibrar; revisar con Puertas y Chilcas (verano) después de k.
- Meteorología de estación (red provincial REM San Luis) para humedad relativa y viento locales; caso de prueba: Rincón del Carmen.
