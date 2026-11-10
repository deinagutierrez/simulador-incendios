# Etapa 30: pavesas (`spotting.p_max`) sobre los 10 eventos (prueba E051)

Fecha: 2026-10-31 · Bitácora: E052 · Decisión: D50 · Prerregistro: `lote_E051/PRERREGISTRO.md` (sha256 c109f19a…, escrito el 2026-10-30 antes de correr) · Antecedentes: docs/v4.0/26, 27 y 29. Alcance: solo v4.0.

**Fuentes:**
- `lote_E051/prueba.py`, `evaluar.py`, `_puntajes_E051.csv` y `_validacion_cruzada_E051.csv`.
- Corridas: `resultados/prueba_E051/` (438, sin figuras).

## Qué se probó

`spotting.p_max` ∈ {0; 0,01; 0,05} con `spotting.activo: true`, en las 73 igniciones de los 10 eventos. Semillas 42, 43 y 44. Todo lo demás, como en la base (E038).
- `p_max` = 0 es la base E038 (determinista) y no se volvió a correr.
- 2 valores × 3 semillas × 73 igniciones = **438 corridas**, 438 `ok`, 0 fallos.
- Métrica idéntica a E047: F = Δeje/90 + |ln(A_sim/A_cic)|/ln 2, más la penalización asimétrica de tiempo (±12 h). s = F + P(Δt). s_i = mediana de las semillas; S_e = mediana de las igniciones; J = mediana de los 10 S_e.

## Veredicto: no se adoptan las pavesas (`spotting.activo` queda en `false`)

Criterio prerregistrado, aplicado con validación cruzada dejando un evento afuera (en las 10 vueltas se eligió `p_max` = 0,01):

| Condición del prerregistro | Umbral | Resultado | ¿Se cumple? |
|---|---|---|---|
| 1. Mejora de S_e frente a la base, en la validación cruzada | ≥ 6 de 10 eventos | **5 de 10** | **No** |
| 2. Mediana de (S_e elegida − S_e base) | < 0 | −0,035 | Sí |
| 3. Salvaguarda: mediana sobre eventos del IoU mediano | no baja más de 0,01 | 0,163 → 0,160 (−0,003) | Sí |

**Como la condición 1 no se cumple, no se adopta.** Falla por un evento. Las condiciones 2 y 3 sí se cumplen, pero el prerregistro pide las tres.

## Datos que justifican la decisión

### J, con los 10 eventos

| `p_max` | J | Mediana de Δeje/90 | Mediana de error de alargamiento / ln 2 | Mediana de P(Δt) | IoU (mediana de eventos) | Fracción que alcanza la cicatriz |
|---|---|---|---|---|---|---|
| 0 (base) | 0,837 | 0,153 | 0,432 | 0,000 | 0,163 | 0,973 |
| 0,01 | **0,696** | 0,143 | 0,332 | 0,178 | 0,160 | 1,000 |
| 0,05 | 1,031 | 0,120 | 0,432 | 0,254 | 0,145 | 1,000 |

(dato) Con 0,01 J baja 0,141 frente a la base; con 0,05 sube 0,194. Las pavesas mejoran el alargamiento y el eje, pero empeoran el tiempo: la penalización de tiempo pasa de 0 a 0,178 y 0,254.
Mediana de saltos por corrida: 0 (base), 34 (0,01) y 138 (0,05).

### Puntaje S_e por evento (menor es mejor)

| Evento | S_e base | S_e 0,01 | S_e 0,05 | Δt base → 0,01 → 0,05 (h) | IoU base → 0,01 → 0,05 |
|---|---|---|---|---|---|
| Chilcas | 2,656 | 0,814 | 0,496 | +34,2 → +14,3 → +4,1 | 0,135 → 0,073 → 0,093 |
| Pampita | 0,308 | 0,521 | 0,649 | −2,6 → −3,1 → −4,7 | 0,399 → 0,417 → 0,423 |
| Piscuyacu | 0,535 | 0,538 | 1,222 | −18,3 → −24,4 → −32,6 | 0,381 → 0,219 → 0,178 |
| Puertas | 0,481 | 0,528 | 1,112 | +10,6 → −24,6 → −47,6 | 0,166 → 0,211 → 0,180 |
| Renca | 0,788 | 0,578 | 1,080 | +3,5 → −13,3 → −16,3 | 0,086 → 0,051 → 0,046 |
| La Aguada | 0,534 | 0,417 | 0,373 | sin término de tiempo | 0,159 → 0,131 → 0,149 |
| Chacras | 1,088 | 1,092 | 0,982 | −34,5 → −39,2 → −42,6 | 0,239 → 0,189 → 0,168 |
| Rincón | 1,005 | 0,931 | 1,113 | +3,9 → +3,6 → +2,0 | 0,045 → 0,034 → 0,030 |
| Las Lagunas | 1,468 | 1,042 | 1,271 | +3,6 → −26,4 → −34,4 | 0,223 → 0,234 → 0,140 |
| Mesilla | 0,886 | 1,121 | 0,804 | −24,4 → −28,0 → −32,1 | 0,125 → 0,032 → 0,009 |

(dato) Con 0,01, S_e baja en 5 eventos (Chilcas, Renca, La Aguada, Rincón, Las Lagunas) y sube en los otros 5 (Pampita, Piscuyacu, Puertas, Chacras, Mesilla). Con 0,05 pasa lo mismo: mejora en 5 y empeora en 5.

### Validación cruzada (se deja un evento afuera; en las 10 vueltas se elige 0,01)

| Evento afuera | S_e elegida (0,01) | S_e base | Diferencia |
|---|---|---|---|
| Chilcas | 0,814 | 2,656 | **−1,843** |
| Pampita | 0,521 | 0,308 | +0,214 |
| Piscuyacu | 0,538 | 0,535 | +0,003 |
| Puertas | 0,528 | 0,481 | +0,047 |
| Renca | 0,578 | 0,788 | −0,210 |
| La Aguada | 0,417 | 0,534 | −0,117 |
| Chacras | 1,092 | 1,088 | +0,004 |
| Rincón | 0,931 | 1,005 | −0,073 |
| Las Lagunas | 1,042 | 1,468 | −0,426 |
| Mesilla | 1,121 | 0,886 | +0,236 |

(dato) 5 diferencias negativas (mejora) y 5 positivas. Dos de las positivas son casi empates (Piscuyacu +0,003, Chacras +0,004), y el prerregistro dice que un empate no cuenta como mejora. La mediana es −0,035.

### Dispersión entre semillas

Rango de s entre las 3 semillas por ignición (mediana global): **0,373** con `p_max` 0,01 y **0,447** con 0,05. Por evento va de 0,16 a 0,66 (Piscuyacu 0,63–0,66, Las Lagunas 0,66 y 0,17, Rincón 0,34 y 0,66).
(dato) La dispersión entre semillas (0,37) es mayor que la diferencia de J entre 0,01 y la base (0,14). El prerregistro dice que, si la dispersión es comparable con la diferencia entre valores, el resultado no es concluyente aunque el criterio se cumpla. Aquí el criterio ni siquiera se cumple.

### Controles

- **Reproducción de E049:** Chilcas y Las Lagunas con `p_max` 0,05 y semilla 42 (18 corridas) dan lo mismo que E049 (SP): IoU y Δt idénticos, y diferencia máxima de `s` de 1,4·10⁻¹⁵. (dato) El control del prerregistro se cumple.
- **Lectura de metadatos:** `p_max` y `spotting.activo` leídos en `metadata.json` coinciden con lo pedido en 0,01 y 0,05 (`p_max_leido` 0,01 y 0,05, `activo` verdadero). En la base, `activo` es falso y los saltos son 0.
- 438 de 438 corridas `ok`.

## Lectura

1. (dato) **No hay una mejora general:** con 0,01, 5 eventos mejoran y 5 empeoran; con 0,05 pasa igual y J empeora (1,031 frente a 0,837).
2. (dato) **La ganancia de J con 0,01 la sostiene en buena parte Chilcas:** su diferencia (−1,84) es la mayor de lejos, y corrige el atraso (+34 → +14 h). Con 0,05 se corrige casi todo (+4 h), pero no el resto.
3. (dato) **Con 0,05 se adelantan los eventos de sierra** (Puertas −48 h, Piscuyacu −33 h, Mesilla −32 h, Las Lagunas −34 h), lo que el prerregistro ya anticipaba como un resultado que cuenta en contra.
4. (dato) **Las pavesas bajan el IoU** en la mayoría de los eventos (por ejemplo Mesilla 0,125 → 0,009), aunque la mediana de eventos cae solo 0,003 con 0,01.
5. (exploratorio, no prerregistrado) Sin Chilcas, J con 0,01 sigue por debajo de la base (0,578 frente a 0,788) y con 0,05 queda por encima (1,080). Se informa solo como contexto: **no cambia el veredicto**, que se fijó antes de ver los resultados.
6. (inferencia) Las pavesas parecen útiles solo en el tipo de evento de Chilcas (día extremo, huella muy alargada, A = 4,21). Un modelo de pavesas dependiente de la intensidad o del viento podría separar ese caso del resto, pero **eso sería otra hipótesis, con su propio prerregistro**.

## Límites

- Eventos vistos (desarrollo); n = 10.
- Tres semillas son pocas; solo permiten ver que la variabilidad es grande.
- Solo se varió `p_max`: la distancia, la intensidad de referencia y la dirección de las pavesas siguen sin calibrar.
- Los pesos de la métrica (90°, ln 2) y del tiempo (12 h, 0,5) son supuestos.
- Los incendios reales tuvieron combate y el simulador no.
- La métrica de forma no mide la ubicación (error de ignición, E046).

## Incidente durante la ejecución (registrado por transparencia)

Al reanudar la prueba el 31/10 en este equipo, el primer lanzamiento **no ejecutó nada**: el equipo no tenía las dependencias (`pandas`, etc.) y una comprobación encadenada con `&&` impidió el arranque. Un segundo lanzamiento con el Python del sistema generó 384 estados `fallo` por `ModuleNotFoundError`, que se borraron (solo esos). Después se creó un entorno virtual con `requirements.txt` y se relanzó. Las 54 corridas previas (30/10) quedaron intactas y las 384 restantes se corrieron de cero. Ningún resultado de este informe proviene de corridas fallidas.

## Qué queda

- Las pavesas siguen apagadas en `modelo_v3`.
- (propuesta, sin hacer) Si se quiere volver a las pavesas, el candidato es una forma que dependa de la intensidad o del viento, con prerregistro nuevo y, de ser posible, eventos no vistos.
