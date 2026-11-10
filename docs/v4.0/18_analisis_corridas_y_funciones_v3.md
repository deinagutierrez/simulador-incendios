# Etapa 18: análisis de las corridas de v4.0 y aporte de las funciones heredadas de v3.0

Fecha: 2026-10-28 · Bitácora: E033 (lote), E035 (ablación y este informe).

**Fuentes:**
- `resultados/v4.0/<evento>/<run_id>/`: 102 corridas del lote E033.
- `resultados/ablacion_E035/`: 408 corridas de ablación. Las tablas y scripts están en `_analisis/`: `corridas_E033.csv`, `eventos_E033.csv`, `ablacion_E035.csv` y `scripts/`.
- Tiempos observados: `datos/inputSimulacion/banco_v4/protocolo/eventos_fase1.csv` (primer y último pase VIIRS, T80, Tref) y fechas SNMF de las fichas.

**Alcance:** los 9 eventos menores. Las Lagunas 2024 queda fuera (6 corridas pendientes, `lote_E033/`). Todo es **desarrollo exploratorio**: no es una evaluación del protocolo v1.3 y no decide §9.

## 1. Ficha de comparabilidad

Cada cifra de la ablación compara una configuración (A) con su base (B: `libre`, o `local` para la parada) **igniciones emparejadas**.

| Campo | A | B |
|---|---|---|
| Instante de evaluación | última `evaluacion_utc` de la ficha, fijada antes de correr | igual |
| Referencia | cicatriz de referencia de v3.0 sobre celdas combustibles (`ha_ref`); tiempos: Tref del banco (mín. del último pase con focos y la contención SNMF) | igual |
| Dominio / grilla | las_lagunas_potrerillos, EPSG:5345, 30 m | igual |
| Eventos | los 9 menores; 51 igniciones (hora h0–h2 × punto) | igual |
| Rol del evento | **visto**: todos se usaron en desarrollo. Mesilla, Renca y Aguada sirvieron para calibrar k, κ, tasa y λ en v3.0 (E027) | igual |
| Ignición | ficha: SNMF o `altN`. **Los `altN` se derivaron de la cicatriz** (circular) | igual |
| Supresión | `libre`: no; `local`: combate SNMF | según la configuración |
| Parada | `parar_en_cicatriz: on` (D38–D40): la huella queda congelada al igualar la cicatriz | igual |
| Meteorología | ERA5/IFS horaria del evento | igual |
| Métrica | IoU de la última evaluación; Δt = h al alcanzar la cicatriz − Tref (solo si la alcanza); segundos de simulación sin figuras | igual |
| Calibración | ninguna: valores por defecto de `modelo_v3`; Fase 2 pausada | igual |
| Evaluador | `incendios_sl.resumen` del mismo código (sin cambios en E033–E035) | igual |
| Máscara | celdas combustibles (FBFM40 ≥ 101) | igual |
| n | 9 eventos (< 8 no concluyente; acá 9, pero dentro de la muestra y vistos) | igual |

**Lectura:** A y B solo difieren en la función probada, así que las diferencias son comparables. Las cifras absolutas (IoU, Δt) **no** son evidencia de validez: vienen de eventos vistos, ignición en parte circular y referencias temporales aproximadas. Que **9 de 9** eventos sean vistos limita todo a lo orientativo.

## 2. Qué muestran las corridas: primero lo que no gusta

1. **El combate «local» borra los incendios.** Es un dato (E033 y ablación).
   - Con la ficha, el combate empieza a los 58–140 min, con 0,1–3 ha quemadas, y los contiene con 0,1–9 km de línea.
   - Mediana del área final: 14,7 ha frente a 175 ha con «libre». IoU mediana 0,00. Solo 9/51 igniciones alcanzan la cicatriz.
   - En 5 de 9 eventos el área final mediana es menor que 3 ha, cuando los incendios observados fueron de 113 a 3.795 ha.
2. **El 89 % del tiempo de «local» se simula con el fuego ya contenido.** Es un dato.
   - La parada se suspende «por posibles escapes» (modo `v3`): 4.154 de las 4.685 h simuladas.
   - Con `parada.escapes: potencial`, el resultado es **idéntico en 51/51** (misma superficie) y el cómputo baja un 52 %.
3. **La forma acierta poco en todas las configuraciones.**
   - IoU mediana de «libre» = 0,13 (p90 0,37). Rincón y Mesilla con punto SNMF: 0,00.
   - Ninguna función de v3.0 la mueve más de ±0,01 en mediana.
4. **El error de tiempo cambia de signo según el evento** (Δt mediano de «libre», en h):

   | Evento | Δt (h) |
   |---|---|
   | Chacras 2023 | −37,5 |
   | Mesilla 2024 | −27,5 |
   | Piscuyacu 2022 | −7,4 |
   | Pampita 2022 | −3,6 |
   | Rincón 2023 | +4,2 |
   | Renca 2022 | +14,2 |
   | Chilcas 2022 | +29,9 |
   | Puertas 2022 | +32,6 |

   Ningún factor único de velocidad corrige errores de signo opuesto.
5. **Las horas de ignición de 4 fichas son posteriores a la primera detección VIIRS.** Es un dato; banco `primer_pase_utc` y `focos_calor.csv` de V.4.
   - Chilcas: 7,6–13,6 h antes de la hipótesis. Piscuyacu: 2–21 h. Renca: 7,8–31,8 h. Rincón: 5,6–10,6 h.
   - En Rincón hay un foco dentro de la cicatriz a las 02:25 local (FRP 0,8 MW), y la primera hipótesis es de las 08:00.
   - (inferencia) Parte del error de tiempo de esos eventos viene de la ficha y no del modelo. Corregido por la primera detección, Renca y Rincón quedan cerca de Δt ≈ 0.

## 3. Lo que sí se mueve

- **Combustible 3.3b** (función de v4.0, docs/v4.0/17; no es de v3.0):
  - Puertas pasa de +32,6 a −9,8 h, Renca de +14,2 a +6,1 h y Chilcas de +29,9 a +23,4 h.
  - Chacras y Mesilla casi no cambian: −36,0 y −25,2 h.
  - Alcanza la cicatriz en 51/51 (antes, 48). El IoU mejora en 4/9 eventos y empeora en 1. |Δt| mejora en 18 igniciones y empeora en 11. Cómputo: −33 %.
  - (inferencia) Coincide con el diagnóstico del informe 17: en las cicatrices de 2022 domina TU1 (161), entre el 31 % y el 67 %, mientras que en las de 2023–2024 dominan TU5 (165) o pastos. La sequía del verano 2021/22 alivianó el combustible leñoso con la regla 3.3.
- **Lo que queda rápido** son Chacras y Mesilla, en la sierra, con viento mediano de 22 km/h en las primeras 24 h (máx. 34–36). Ninguna configuración probada los corrige sin empeorar los lentos.

## 4. Funciones heredadas de v3.0: ¿aportan algo a v4.0?

Medido con ablación emparejada (51 igniciones, 9 eventos, sin figuras). «Costo» es la variación del tiempo de simulación frente a la base.

| # | Función de v3.0 | Probada | Efecto en forma (IoU) | Efecto en tiempo de avance | Costo de cómputo | Veredicto |
|---|---|---|---|---|---|---|
| 1 | Viento WindNinja sobre el relieve (vs uniforme de V.4) | sí | igual en 42/51, Δ mediana 0,000 | igual (Δt idéntico al décimo de hora) | **+66 %** (3.037 s vs 1.827 s) | **No aporta nada significativo; solo cuesta.** Coincide con docs/17 (huellas con IoU 0,977 entre sí) |
| 2 | Barreras viales probabilísticas | sí | 15 mejor / 16 igual / 20 peor; Δ mediana 0 | demora +2,9 h; agrava los lentos (Chilcas +42 h) | +6 % | **No aporta a la calibración.** Hace falta para simular cortafuegos (`barreras_extra`) |
| 3 | Contención por combate + despacho SNMF (ficha, arribo vial) | sí | **−0,10** (a 0,00) | 9/51 alcanzan la cicatriz; área 15 vs 175 ha | **+181 %** | **Empeora** con los valores de v3.0 (κ = 10, I_s = 1.700 kW/m, retardo vial). No usar para comparar mitigaciones hasta recalibrarlo |
| 4 | Parada suspendida por posibles escapes (`escapes: v3`) | sí (vs `potencial`) | idéntico 51/51 | idéntico | `potencial` ahorra **−52 %** | **Solo empeora el tiempo.** Cambiar a `potencial` |
| 5 | Humedad muerta FFMC de Van Wagner (vs retardo) | sí | peor en 6/9 eventos (28/51 igniciones) | frena todo: arregla Chacras (−37 → 0 h) pero empeora los lentos (Chilcas +41 h; Puertas y Piscuyacu no alcanzan) | +16 % | **Empeora**: mueve todo en la misma dirección |
| 6 | Humedad viva min–max (vs lineal de V.4) | sí | 13 mejor / 29 igual / 9 peor | acelera todo: Puertas −45 h, Chacras −40 h; |Δt| peor en 25, mejor en 9 | −30 % (porque termina antes) | **No aporta**: acelera también lo que ya era rápido |
| 7 | Medios aéreos (ficha y sorteo) | no | — | — | — | **Sin evidencia**: las 9 fichas tienen `aereo: []`; solo actuaría en Las Lagunas o en modo pronóstico |
| 8 | Factores k por familia y WAF | no (valor 1) | sin efecto con 1 | — | nulo | **Útil solo como perilla de la Fase 2**: candidato para el sesgo rápido de la sierra, con validación cruzada |
| 9 | Extinción por lluvia de 24 h | no (apagada) | — | — | nulo | **Sin efecto**: no hubo lluvia relevante en los eventos |
| 10 | Hipótesis de hora y punto de ignición | sí (E033) | el **punto** domina: rango de IoU por punto de 0,20–0,31 en Pampita, Chacras y Mesilla | la **hora** domina: hasta 14 h en Piscuyacu | ×3–9 corridas por evento | **Aporta** (muestra la incertidumbre), con dos problemas de datos: `altN` circulares y horas posteriores a VIIRS en 4/9 |
| 11 | Parada por horas sin avance y por contención | indirecta | — | — | ahorra | **Aporta** (con el punto 4 resuelto) |
| 12 | Variantes, precedencias, `ajustes`/`parche` | — | — | — | nulo | Infraestructura: sin costo |

## 5. Decisión

**Decisión que hay que tomar:** qué línea de trabajo seguir para que el modelo acierte mejor la velocidad de avance y el tiempo.

**Evidencia:**
- Ablación E035 y lote E033, con fuente en `_analisis/ablacion_E035.csv` y `corridas_E033.csv`. Cifras de las secciones 2–4: **dato**.
- Causas propuestas (sequía en la regla 3.3, ignición tardía): **inferencia**.

**Lo que no sabemos:**
- Si 3.3b mejora fuera de estos 9 eventos vistos, ni qué pasa en Las Lagunas.
- Cuánto del error de tiempo es de la referencia: Tref usa el último pase con focos, con 2 a 8 pases por evento.
- Por qué la sierra (Chacras, Mesilla) avanza tan rápido: no se probaron WAF, el límite de viento ni k por familia.
- Si el combate «local» falla por el retardo, por la tasa o por el umbral de sostén.

**Opciones:**

| Opción | A favor | En contra | Costo |
|---|---|---|---|
| A. Ajustes de costo sin tocar la física: `escapes: potencial` y viento `serie` para lotes | −52 % en «local» y −40 % en «libre», con resultados idénticos o equivalentes | WindNinja podría importar en otros relieves o vientos (sin evidencia acá) | bajo: dos claves de `modelo_v3.yaml` |
| B. Corregir las horas de ignición de 4 fichas con la primera detección VIIRS como cota | ataca un error de datos de 8–32 h, mayor que cualquier perilla física | toca fichas (datos de entrada): requiere decisión y versión nueva de las fichas | bajo |
| C. Adoptar 3.3b como combustible por defecto | único cambio que corrige los lentos de 2022 sin tocar los demás; −33 % de cómputo | probado solo en eventos vistos; la Fase 2 lo tenía como parámetro a decidir | bajo, pero conviene decidirlo en la Fase 2 |
| D. Retomar la Fase 2 (3.3/3.3b × I_s × κ, más WAF o k_grupo para la sierra) con validación cruzada | es el camino del protocolo para calibrar sin sobreajustar | ≈ 6 h por la grilla, más Las Lagunas | medio |
| E. Seguir con FFMC, min–max o barreras como palanca de velocidad | — | empeoran o no mueven nada | — |

**Recomendación**, con confianza **media**:
1. **A** ahora: no cambia resultados y reduce el cómputo a la mitad.
2. **B** como corrección de datos.
3. **C** dentro de **D**: la Fase 2 debe partir de 3.3b, `escapes: potencial` y la ignición corregida, y sumar una perilla para la sierra.
4. No usar el combate «local» para comparar mitigaciones hasta recalibrarlo.
5. Descartar E.

**Qué la cambiaría:**
- Que Las Lagunas (40.000 ha, otra escala) muestre que WindNinja o las barreras sí importan.
- Que 3.3b empeore en eventos no vistos.
- Que la corrección de ignición no reduzca el error de tiempo.

**Qué necesito del usuario:**
- Aprobar A, que cambia valores por defecto de `modelo_v3`.
- Decidir B, que toca fichas de evento.
- Decidir si se retoma la Fase 2 con las condiciones de C.

## 6. Notas

- Una corrida 3.3b (Pampita h0-alt0) falló la primera vez por una carrera al escribir la caché `combustible_pre_evento_33b.tif` entre procesos paralelos en Windows. Se repitió con los mismos parámetros y quedó bien; se borró el temporal huérfano. Para lotes, conviene generar la caché de cada evento antes de paralelizar.
- Lectura de antecedentes para este informe:
  - bitácora leída en E027–E034;
  - decisiones D37–D40;
  - informe 17.
  - No se releyó completo el reporte de avance.
