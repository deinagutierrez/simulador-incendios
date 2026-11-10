# Etapa 21: ¿hace falta una calibración nueva del combustible en v4.0?

Fecha: 2026-10-28 · Bitácora: E039 · Alcance: solo el modelo v4.0 (`modelo_v3` con la regla 3.3b del lote E038).

**Fuentes:**
- Scripts y tablas: `lote_E038/combustible_selectividad.py`, `_selectividad_combustible.csv`, `_ros_por_codigo.csv` y `_comparacion_E038.csv`.
- Datos: combustible `datos/procesados/v4.0/<evento>/combustible_pre_evento_33b.tif`, cicatrices de referencia y `ros_max_m_min.tif` de las 73 corridas de E038.

## 1. Cómo se arma hoy el combustible

`simulador/fuel/generar_sb40.py` asigna un modelo Scott & Burgan a cada celda en dos pasos:
1. Toma la clase de MapBiomas (cobertura del año anterior).
2. Elige uno de 3 modelos según el tercil de NDVI de verano. Los terciles de `estaticos/combustible/umbrales_ndvi.csv` son percentiles de la distribución, no un ajuste a comportamiento de fuego.

Ejemplos de la tabla:
- Pastizal (12) → GR1 / GR2 / GR4; pasturas (15) → GR2 / GR4 / GR7.
- Arbustal cerrado (66) → SH2 / SH5 / SH7; arbustal abierto (77) → GS2 / SH2 / SH5.
- Bosques (3 y 4) → TU1 / TU5.

**La tabla y los terciles son decisiones expertas de V.4: nunca se calibraron contra incendios observados** (dato, por lectura del código y del CSV). La regla 3.3b (E038) corrige solo la anomalía de NDVI de las clases leñosas en años secos; no toca la tabla.

## 2. Evidencia

**a) El fuego eligió arbustos y bosque, y evitó los pastos.** Es un dato: se compara la fracción de cada código dentro de la cicatriz con la de un anillo de 0–2 km alrededor, que no se quemó, en 10 eventos.

| Código | Dentro / anillo (mediana) | Velocidad simulada (m/min, E038) |
|---|---|---|
| SH2 | **1,50** | 2,1 |
| SH5 | **1,39** | 30,4 |
| TU5 | 1,16 | 2,1 |
| TU1 | 1,01 | **0,7** |
| GS2 | 0,93 | 7,1 |
| GR1 | 0,43 | 2,9 |
| GR4 | 0,35 | **24,3** |
| GR2 | 0,35 | 8,5 |
| GR7 | 0,03 | **44,2** |
| GR6 | 0,00 | **28,6** |

- Los pastos quedan con proporción < 1 en **9 de 10** eventos. Los arbustos quedan > 1 en **7 de 10**.
- **La velocidad que el modelo da a cada combustible va al revés de lo que el fuego eligió:** Spearman −0,56 sobre 11 códigos. Los pastos (GR4, GR6, GR7) son lo más rápido del modelo y lo menos quemado. TU1, SH2 y TU5 son lo más lento y lo más quemado.

**b) El sesgo de tiempo sigue al tipo de combustible.** Es un dato; Δt mediano de E038, con Las Lagunas medida contra T80.
- Correlación de Spearman entre la fracción de la cicatriz y Δt, con n = 9 (sin Las Lagunas, n = 8):
  - pastos (GR): −0,60 (−0,79);
  - pastizal-arbustal (GS): −0,64 (−0,69);
  - bosque (TU): +0,58 (+0,50).
- Más pasto, más adelantado; más bosque, más atrasado. Mesilla (53 % GR) va −24 h; Chilcas (72 % TU, sobre todo TU1) va +33 h.

**Qué limita esta evidencia:**
- (supuesto) El anillo no quemado incluye potreros pastoreados o cultivados (clases 12 y 15), caminos y zonas que el combate protegió. Parte del «rechazo» a los pastos puede ser manejo del suelo y no física.
- (dato) Son eventos vistos, con n = 9–10, y los `altN` derivan de la cicatriz. Con n < 10 cualquier correlación es orientativa.
- (supuesto) MapBiomas Fuego detecta mejor las quemas en vegetación leñosa: puede sobrerrepresentar las celdas leñosas dentro de la cicatriz.

## 3. Respuesta

**Sí, hace falta una calibración nueva del combustible**, con confianza **media**. Dos razones:
1. La asignación combustible → velocidad **nunca se calibró** con datos locales.
2. Dos señales independientes apuntan al mismo lado: la selectividad observada y el sesgo de tiempo por evento. Los **pastos van demasiado rápido** en el modelo, y los **bosques y arbustos (TU1, TU5, SH2) demasiado lentos**.

Esto explica también por qué ninguna perilla global (viento, humedad, barreras) corrigió los dos sesgos a la vez: tienen signo opuesto según el combustible.

## 4. Cómo calibrar (sin tocar los datos crudos ni el protocolo)

| Opción | Qué es | A favor | En contra |
|---|---|---|---|
| A. **Factores de velocidad por familia** (`k_grupo`: GR, SH, TU) | multiplicadores de R0 que el motor ya trae | 3 parámetros, el máximo que admite §9 con 10 eventos; reversible; sin rehacer mapas | no distingue dentro de la familia (GR4 vs GR1) |
| B. Rehacer la tabla clase → modelo (p. ej. pasturas 15 a GR1/GR2, arbustales 66/77 a SH5/SH7) | cambia `TABLA` en `generar_sb40.py` | ataca la causa si está en la asignación | muchos grados de libertad, difícil de justificar con 10 eventos; regenera todos los combustibles |
| C. Recalcular los terciles de NDVI con varios veranos | `umbrales_ndvi.csv` multianual | quita la dependencia de un solo verano también en las herbáceas | no cambia el orden de velocidades, que es el problema principal |

**Recomendación:** opción **A**, en dos pasos.
1. **Cribado rápido**, sobre E038, cambiando una familia por vez: `k_grupo` GR 0,5; SH 2; TU 2. Son 3 lotes de 73 corridas, unos 15–20 min cada uno sin figuras. Sirve para ver cuánto mueve cada familia los Δt y el IoU.
2. Con lo que mueva, una **grilla chica** (2–3 valores por familia elegida) con **validación cruzada dejando un evento afuera**, según el protocolo. Los valores se eligen en 9 eventos y se prueban en el que queda afuera.

La opción B solo si A no alcanza. La C queda como mejora de fondo, no urgente.

**Qué cambiaría esta conclusión:**
- Que el anillo no quemado sea mayormente potrero o cultivo. Se puede comprobar cruzando con la clase de MapBiomas; en ese caso la señal de los pastos se debilita.
- Que el cribado muestre que bajar GR acelera la sierra en vez de frenarla.
