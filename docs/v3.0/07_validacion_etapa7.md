# Etapa 7 — Calibración y validación con cicatrices observadas

Fecha: 2026-10-14. Scripts: `scripts/calibrar.py`, `scripts/evaluar_barrido.py`, `scripts/validar.py`. Resultados crudos en `data/resultados/` (cada corrida: `t_llegada_s.tif`, `estado_final.tif`, `serie_horaria.csv`, `registro.json`, `metricas.json`, mapas PNG y `animacion.gif` cuando se pidieron figuras). Todos los valores son mediciones; ninguno se ha ajustado a mano.

## 1. Protocolo
- **Calibración** solo con `SL-2024-LASLAGUNAS`; **validación** con `SL-2022-RENCA` y `SL-2022-PUERTAS` usando los parámetros resultantes sin retoque; corridas adicionales de sensibilidad etiquetadas como tales.
- Dominio de comparación: celdas dentro del dominio y con combustible. Métricas: IoU, Dice, superficies, omisión, comisión (`validation/metricas.py`), evaluadas en varios instantes (`evaluacion_utc` de cada ficha). Acuerdo temporal con focos de calor: fracción de detecciones (VIIRS 375 m para 2024; MODIS 1 km para 2022) cuyo entorno está quemado en la simulación al final del día local de la detección, y desfase mediano (sólo VIIRS, con hora de paso).
- Sin mitigación en ninguna corrida. Por eso la comparación relevante es en el instante en que termina la propagación principal observada (antes de que el combate domine); las evaluaciones posteriores se informan igualmente.

## 2. Calibración (SL-2024-LASLAGUNAS)

### 2.1 Barrido 1: factor global k × factor de viento a media llama × hora de ignición (45 corridas, 40–48 s cada una)
- La hora de ignición (10, 12, 14 h local del 18/09) es irrelevante: diferencias de IoU < 0,005.
- Mejor IoU 0,34 (k = 3, WAF × 0,5) al final del 20/09; 0,34 (k = 1,5, WAF × 0,5) el 25/09. Ningún valor global supera 0,34.
- Diagnóstico por clase de combustible: la comisión se concentra en pastizal, pastura y arbustal abierto de la llanura sur y este (clases 1–3); la omisión en bosque abierto y cerrado de la sierra al norte y oeste (clases 5–6), que el incendio real recorrió el 20/09 con viento del sur. La asignación de análogos de Scott & Burgan (GR1/GR2/GS2 para llanura; GS2/TU1 con abrigo de dosel para bosque) tiene el sentido invertido respecto de lo observado. Tabla completa: `data/resultados/calibracion_SL-2024-LASLAGUNAS/barrido_reevaluado.csv`, gráfico `barrido_iou.png`.

### 2.2 Barridos 2 y 3: factores por grupo de clases (12 + 16 corridas)
Grupos: k_bajo (clases 1–3), k_bosque_abierto (4–5), k_bosque_cerrado (6–7), WAF × {0,75; 1; 1,5}. Resultados al final del 20/09 (21/09 03 UTC) y del 21/09:

| k 1–3 | k 4–5 | k 6–7 | WAF | IoU fin 20/09 | ha sim | omisión | comisión | IoU fin 21/09 | focos al día | desfase h |
|---|---|---|---|---|---|---|---|---|---|---|
| 0,25 | 5 | 3 | 0,75 | **0,399** | 51.812 | 0,35 | 0,49 | 0,319 | 0,58 | −4,7 |
| **0,5** | **3** | **5** | **1,0** | 0,393 | 46.665 | 0,39 | 0,48 | **0,344** | 0,56 | −4,1 |
| 0,5 | 4 | 4 | 1,0 | 0,387 | 63.088 | 0,28 | 0,54 | 0,300 | 0,65 | −6,1 |
| 1 (sin calibrar) | 1 | 1 | 1,0 | 0,226 | 20.807 | 0,72 | 0,46 | 0,230 | 0,21 | +29,4 |

El óptimo es una meseta (IoU 0,38–0,40). Se adopta **k = {1: 0,5; 2: 0,5; 3: 0,5; 4: 3; 5: 3; 6: 5; 7: 5}, WAF × 1,0** (segunda fila): mejor IoU al día siguiente, superficie simulada más próxima a la referencia (46.665 vs 40.052 ha) y desfase temporal de −4 h (ligeramente adelantado). Guardado en `config/modelo_v1.yaml` con la anotación de calibración; los valores iniciales eran 1,0.

### 2.3 Corrida completa calibrada (`data/resultados/SL-2024-LASLAGUNAS_calibrado`, 21 días, 129 s)

| Instante (UTC) | Significado | IoU | Dice | ha sim | ha ref | omisión | comisión |
|---|---|---|---|---|---|---|---|
| 21/09 03:00 | fin del 20/09 local (fase explosiva, 87 % de los focos) | **0,393** | 0,565 | 46.665 | 40.052 | 0,39 | 0,48 |
| 22/09 03:00 | fin del 21/09 | 0,344 | 0,512 | 75.992 | 40.052 | 0,26 | 0,61 |
| 25/09 03:00 | fin de propagación principal | 0,272 | 0,427 | 129.356 | 40.052 | 0,10 | 0,72 |
| 28/09 03:00 | contenido (SNMF) | 0,225 | 0,367 | 173.715 | 40.052 | 0,02 | 0,77 |
| 10/10 03:00 | extinguido | 0,161 | 0,278 | 248.587 | 40.052 | 0,00 | 0,84 |

Focos VIIRS: 100 % capturados en algún momento, **56 % al final de su día de detección**, desfase mediano +5,5 h (simulación ligeramente retrasada en promedio). Figuras: `mapa_2024MMDDT03.png` y `animacion.gif` (cuadros cada 12 h).

Lectura: durante la fase explosiva el modelo reproduce la extensión al norte y al este y la cronología a escala de horas; la comisión restante está en la llanura sur y este, donde la cicatriz real tiene bordes rectos (líneas de contención, parcelas) que un modelo sin mitigación no puede reproducir; la omisión en las laderas del noroeste persiste. A partir del 22/09 la simulación sigue quemando mientras el incendio real estaba siendo contenido: esas evaluaciones miden la ausencia de mitigación, no la propagación.

## 3. Validación (parámetros calibrados, sin retoque)

### 3.1 SL-2022-RENCA (Renca – San Felipe, 06–11/09/2022, referencia 3.797 ha)

| Ignición | Hora | IoU 09/09 (contenido) | ha sim | omisión | comisión | IoU 12/09 | focos MODIS al día |
|---|---|---|---|---|---|---|---|
| punto SNMF (extremo sur) | 13 h / 10 h / 07-09 10 h | 0,067 / 0,066 / 0,104 | 13.011 / 13.708 / 5.040 | 0,72 / 0,71 / 0,78 | 0,92 / 0,92 / 0,83 | 0,10–0,13 | 0,14 |
| **hipótesis a barlovento** (extremo norte de la cicatriz) | 13 h | **0,139** | 26.001 | **0,05** | 0,86 | 0,057 | 0,31 |
| ídem, k = 1 (sin calibrar; sensibilidad) | 13 h | 0,079 | 2.356 | 0,88 | 0,81 | 0,147 | 0,04 |

Hallazgo: con viento del norte a 5–7 m/s durante el 06 y 07/09, el punto SNMF (en el extremo sur de la cicatriz) no puede ser el origen; la simulación desde él se propaga fuera del dominio por el sur y no toca la cicatriz. Con la ignición en el extremo norte (hipótesis explícita, no observación) el modelo cubre el 95 % de la cicatriz, pero quema 7 veces su superficie. La variante sin calibrar es demasiado lenta (omisión 0,88 a la contención).

### 3.2 SL-2022-PUERTAS (Puertas Coloradas, 12–16/01/2022, verano, referencia 2.062 ha)

| Configuración | Hora | IoU 15/01 | ha sim | omisión | comisión | IoU 17/01 | focos MODIS al día |
|---|---|---|---|---|---|---|---|
| calibrado | 13 h / 10 h / 16 h | 0,090 / 0,084 / — | 22.283 / 24.502 | 0,03 / 0,01 | 0,91 / 0,92 | 0,06 | 0,70 / 0,80 |
| k = 1 (sensibilidad) | 13 h | **0,180** | 5.979 | 0,40 | 0,79 | 0,184 | 0,30 |
| k = 0,25 (sensibilidad) | 13 h | 0,006 | 309 | 0,99 | 0,96 | 0,036 | 0,07 |

Hallazgo: la cicatriz real es una lengua estrecha de 2.000 ha orientada NNO–SSE; el modelo calibrado la cubre casi por completo (omisión 1–3 %) y llega a tiempo a los focos (70–80 %), pero produce una mancha redondeada 10 veces mayor. Con k = 1 la superficie baja a 6.000 ha pero la omisión sube a 0,40.

## 4. Conclusiones de la validación (sin suavizar)
1. **Lo que el modelo reproduce:** dirección y cronología de la fase explosiva del incendio de 2024 (IoU 0,39, 56 % de focos a tiempo, desfase de horas); cobertura de las cicatrices de 2022 (omisión ≤ 5 %) y llegada a tiempo a los focos cuando la ignición está a barlovento.
2. **Lo que no reproduce:** la extensión final de incendios contenidos. Sin mitigación, sin barreras efectivas (caminos, cortafuegos, parcelas) y con parámetros calibrados sobre un megaincendio, la comisión es de 0,8–0,9 en 2022 y de 0,5–0,8 en 2024 después del 21/09. La forma elíptica de Anderson produce frentes más anchos que las lenguas observadas en 2022.
3. **Los parámetros calibrados no son transferibles tal cual** a incendios pequeños: k = 1 da mejor IoU en Puertas (0,18 vs 0,09) pero peor en Renca y mucho peor en 2024. La calibración del factor k absorbe a la vez la carga de combustible (hipótesis por analogía) y la ausencia de supresión; separar ambos efectos exige modelar la mitigación o disponer de perímetros intermedios.
4. **La ubicación de ignición informada por el SNMF no siempre es el origen** (caso Renca); la hora de ignición es secundaria frente a la meteorología de los días siguientes.
5. Validación temporal: solo a escala diaria (MODIS) en 2022 y horaria (VIIRS) en 2024; no se ha validado la velocidad instantánea del frente.

## 5. Incertidumbres cuantificadas o identificadas
- Ignición: cambiar el punto de Renca de sotavento a barlovento pasa la omisión de 0,72 a 0,05.
- Hora: < 0,005 de IoU en 2024; < 0,04 en 2022.
- Factores por clase: meseta de IoU 0,38–0,40 en 2024 con variaciones de ×2 en k; en 2022, k entre 0,25 y 1 cambia la superficie en un factor 20.
- Meteorología de modelo (9 km): no evaluada con otra fuente (pendiente: repetir con `era5`).
- Referencia: cicatriz anual/mensual MapBiomas sin exactitud local; separación por mes en 2022.

## 6. Recomendaciones para la siguiente iteración del modelo (fuera del alcance de la v1)
Modelar barreras lineales (caminos y parcelas como reducción de probabilidad de cruce según intensidad), una representación mínima de supresión (tasa de contención de perímetro), relación largo/ancho más elongada o dependiente del combustible, calibración por clase con más eventos y perímetros intermedios, y verificación del viento con una segunda fuente.
