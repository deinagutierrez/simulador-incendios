# Etapa 26: ¿por qué la forma acierta poco? (E046)

Fecha: 2026-10-29 · Bitácora: E046 · Alcance: solo v4.0, configuración vigente. Solo lectura; sin simulaciones nuevas.

**Fuentes:**
- `lote_E046/forma.py` y `_forma_E046.csv`.
- Huellas finales (`hora_llegada_min.tif`) de las 73 corridas de E038 (3.3b, `barreras`, viento serie, tope en la cicatriz).
- Cicatrices de referencia y la meteorología horaria de cada evento.

**Qué se mide:**
- **Eje:** rumbo del eje principal de la huella (análisis de componentes principales de las celdas), en grados desde el N, de 0 a 180.
- **Alargamiento:** √(λ1/λ2).
- **Desplazamiento:** distancia entre el centroide simulado y el de la cicatriz.
- **Viento durante el avance:** promedio vectorial de la dirección hacia la que sopla, ponderado por velocidad, desde la ignición hasta el fin simulado. La «constancia» vale 1 si siempre sopló en la misma dirección.

## 1. Resultados por evento (medianas sobre igniciones)

| Evento | IoU | Eje cicatriz / simulado (Δ) | Alargamiento cicatriz / simulado | Desplazamiento (m) / largo de la cicatriz | Eje de la cicatriz frente al viento | Constancia del viento |
|---|---|---|---|---|---|---|
| Chilcas 2022 | 0,14 | 178° / 21° (10°) | **4,2 / 1,6** | 1.483 / 3.980 | 5° | 0,57 |
| Pampita 2022 | 0,40 | 125° / 129° (8°) | 1,8 / 2,0 | 488 / 1.594 | 31° | 0,93 |
| Piscuyacu 2022 | 0,38 | 177° / 16° (17°) | 1,8 / 1,5 | 458 / 3.073 | 12° | 0,63 |
| Puertas 2022 | 0,17 | 160° / 165° (4°) | 2,8 / 2,1 | **4.294 / 8.544** | 19° | 0,82 |
| Renca 2022 | 0,09 | 154° / 173° (21°) | 1,6 / 2,0 | **5.202 / 8.760** | **40°** | 0,32 |
| Aguada 2023 | 0,16 | 168° / 162° (9°) | **3,0 / 2,3** | 857 / 2.185 | 6° | 0,97 |
| Chacras 2023 | 0,24 | 153° / 168° (19°) | 1,8 / 1,4 | 952 / 2.376 | **43°** | 0,40 |
| Rincón 2023 | 0,05 | 100° / 152° (**60°**) | 1,6 / 1,3 | **1.598 / 1.834** | **68°** | 0,60 |
| Las Lagunas 2024 | 0,22 | 47° / 145° (**82°**) | 1,6 / 1,1 | 9.178 / 28.623 | **70°** | 0,53 |
| Mesilla 2024 | 0,12 | 167° / 163° (3°) | **3,4 / 2,4** | 1.234 / 2.824 | 22° | 0,44 |

**Relaciones sobre las 73 corridas** (Spearman):
- IoU frente a desplazamiento / largo: **−0,73**;
- IoU frente a distancia ignición–centroide / largo: −0,58;
- IoU frente a la diferencia de eje: −0,31.

**Ignición dentro o fuera de la cicatriz:** IoU mediana **0,175** dentro (31 corridas) y **0,122** fuera (42).

**Rango del IoU entre igniciones de un mismo evento:**
- Pampita 0,07–0,48; Chacras 0,03–0,42; Mesilla 0,00–0,30; Renca 0,05–0,28; Rincón 0,00–0,22.
- En Puertas y Las Lagunas casi no varía (0,17–0,18 y 0,22–0,23).

## 2. Lectura (primero lo que no gusta)

1. **El error principal es dónde está el fuego, no hacia dónde va** (dato).
   - En 8 de 10 eventos el eje simulado está a ≤ 21° del de la cicatriz.
   - Pero el centro simulado queda corrido entre un 10 y un 90 % del largo de la cicatriz.
   - El desplazamiento es lo que más explica el IoU bajo (−0,73).
2. **La ignición pesa mucho y no la conocemos** (dato).
   - Cambiar solo el punto o la hora mueve el IoU de 0,0 a 0,3–0,5 en 5 eventos.
   - (inferencia) Con la ignición incierta, cualquier calibración de la física por IoU absorbe ese error.
3. **Lo simulado es más redondo que lo real** (dato). En 7 de 10 eventos el alargamiento simulado es menor: Chilcas 1,6 frente a 4,2; Mesilla 2,4 frente a 3,4; Aguada 2,3 frente a 3,0; Las Lagunas 1,1 frente a 1,6.
   - (inferencia) El fuego simulado se abre de flancos demasiado o corre poco de cabeza. En Rothermel con Huygens, la relación largo/ancho depende del viento a media llama, así que apunta al factor de ajuste del viento (WAF) o a la elipse.
   - (dato) WindNinja no lo cambió (E035).
4. **En 4 eventos el viento de la serie no explica la cicatriz** (dato).
   - En Las Lagunas (70°), Rincón (68°), Chacras (43°) y Renca (40°) el eje de la cicatriz forma un ángulo grande con el viento de la serie.
   - El eje simulado, en cambio, sigue al viento: 13°, 26°, 27° y 44°.
   - (inferencia) Ahí la única serie IFS de 9 km para todo el dominio no representa el viento local; en Rincón, un día calmo, probablemente dominó el relieve. En Renca, Chacras y Mesilla además el viento fue variable (constancia 0,32–0,44).

## 3. Opciones para el próximo paso

| Opción | Qué ataca | A favor | En contra | Costo |
|---|---|---|---|---|
| A. **Ignición desde la primera detección VIIRS** (el foco más temprano atribuido a la cicatriz, no derivado de su forma) como hipótesis nueva | desplazamiento (−0,73) | no es circular; usa un dato observado; en 4 fichas ya se corrigió la hora con VIIRS (D43) | solo sirve en eventos con focos tempranos (no en Aguada); los pixeles VIIRS son de 375 m | bajo: puntos nuevos en las fichas + 1 lote |
| B. **Cribado del alargamiento**: `factor_waf` 1,25 y 1,5 (más viento a media llama → elipse más larga) | forma redonda | apunta al sesgo en 7/10 | también acelera la cabeza (tiempo); hay que medir los dos | bajo: 2 × 73 corridas sin figuras |
| C. **Meteorología con más detalle** (otra fuente, o estación local) en los 4 eventos con viento discordante | dirección | ataca la causa en LL, Rincón, Chacras, Renca | conseguir datos; fuera del alcance inmediato | alto |
| D. **Métrica de forma independiente de la ignición** (comparar eje y alargamiento, o IoU después de alinear centroides) para calibrar la física sin el error de ubicación | separa física de ignición | evita sobreajustar a la ignición | es una métrica nueva: va con prerregistro | bajo |

**Recomendación** (confianza media):
1. **D + B juntas.** Fijar en un prerregistro una métrica de forma que no dependa de dónde se ubicó el fuego (diferencia de eje y razón de alargamiento) y cribar `factor_waf` 1,25 y 1,5 con ella, controlando también el tiempo.
2. **Después, A** como corrección de datos, que no requiere calibración.
3. C solo si los 4 eventos discordantes siguen mal.

**Límites:** eventos vistos; n = 10; la huella de las corridas paradas por el tope es la del momento en que igualan la superficie (comparable con la cicatriz, porque tienen la misma área).
