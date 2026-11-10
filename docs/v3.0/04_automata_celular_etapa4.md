# Etapa 4 — Autómata celular de propagación: implementación, verificación y rendimiento

Fecha: 2026-10-14. Implementa el diseño §4 de la Etapa 2. Todo valor numérico de este documento fue medido en este entorno.

## 1. Módulos

| Módulo | Contenido |
|---|---|
| `src/incendios_sl/simulation/rothermel.py` | Rothermel (1972) + Albini (1976) multiclase (1 h, 10 h, 100 h, herbáceo vivo, leñoso vivo) según Andrews (2018): factores de ponderación f_i y g_i, σ característica, cargas netas, humedad de extinción del vivo, amortiguación por humedad y minerales, velocidad de reacción, razón de flujo propagante, sumidero de calor, coeficientes de viento (C, B, E) y pendiente. Transferencia de curado para modelos dinámicos (fracción `curado` del herbáceo vivo pasa a muerto con la humedad del 1 h). Regla explícita: si la humedad del muerto ≥ M_x no hay propagación. Variante `albini=False` (A y w_n de Rothermel 1972) solo para contraste. Sin límite de viento (Andrews, Cruz & Rothermel 2013). |
| `src/incendios_sl/simulation/propagacion.py` | Viento a media llama (WAF · U10, dirección "hacia"); pendiente convertida en viento virtual cuesta arriba (inversa de φ_w) y suma vectorial → θ_max, U_eff, φ_c (Rothermel 1983 / Finney 1998 en Andrews 2018); elipse de Anderson (1983): LB(U_eff), e, R(θ). Funciones compiladas con numba. |
| `src/incendios_sl/simulation/automata.py` | Núcleo numba: estencil de 8 o 16 vecinos con distancias reales (30 / 42,43 / 67,08 m); avance acumulado por enlace f += Δt·R(θ)/d; ignición en el instante exacto del cruce y propagación encadenada dentro del paso (sin límite CFL); frente activo en estructura compacta (slots con swap-remove); una celda pasa a quemada cuando no le quedan vecinos combustibles; sin reencendido. |
| `src/incendios_sl/simulation/motor.py` | Bucle horario: tablas R0 por (clase × bin de humedad viva × nivel de curado) y coeficientes por (clase × curado) recalculados cada hora con la humedad muerta del FFMC; campo de viento horario desde la biblioteca WindNinja (escalado lineal + interpolación angular + bilineal a 30 m); igniciones programadas; condiciones de fin (1 fin documentado, 2 fin de meteorología, 3 N horas sin avance, 4 límite computacional, 5 frente agotado, 6 desbordamiento); serie horaria; persistencia (`t_llegada_s.tif`, `estado_final.tif`, `serie_horaria.csv`, `registro.json`). |
| `src/incendios_sl/simulation/entradas.py`, `scripts/simular.py` | Carga de los productos de la Etapa 3 para un evento y ejecución por línea de comandos (`--evento`, `--hipotesis`, `--horas`, `--k`, `--dt`). |
| `src/incendios_sl/simulation/sintetico.py` | Entradas sintéticas (grilla homogénea, viento uniforme, pendiente, barreras) para pruebas. |

Estados: 255 fuera de dominio, 0 no combustible, 1 combustible, 2 frente activo, 3 quemada. Cada celda guarda además `t_llegada` (s desde el inicio, float32).

## 2. Verificación del modelo de velocidad (Rothermel)

- **Contraste con implementación de referencia** (`firebench` 0.10.0, variante WRF-SFIRE de Rothermel 1972) para una sola clase muerta en 5 casos (cargas 0,3–1,5 kg/m², σ 750–2.200 ft⁻¹, humedad 6–14 %, viento 0–4 m/s, pendiente 0–25°): la variante `albini=False` coincide con error **≤ 0,023 %**; la variante Albini (usada en producción) difiere < 0,35 % en combustibles finos y −15,5 % en el caso σ = 750 ft⁻¹, diferencia esperada por el distinto exponente A (documentado en Andrews 2018). Nota: en `firebench` la humedad de extinción debe pasarse como fracción pese a que su docstring dice porcentaje; con porcentaje su amortiguación por humedad queda anulada (−40 % sistemático en nuestra primera comparación).
- Comportamiento (modelo GR2, curado 0,8, LFMC 60 %): R0 = 0,61 / 0,51 / 0,35 m/min para humedad 1 h de 4 / 8 / 12 %; 0,01 a 14,9 %; **0 a ≥ 15 %** (M_x). Monotonía con viento, pendiente y curado verificada por pruebas.
- Combinación vectorial: con solo viento del oeste θ_max = 90° y φ_c = φ_w; con solo pendiente cuesta arriba al norte θ_max = 0° y φ_c = φ_s. Elipse: R(cabeza) = R, R(cola) = R(1 − e)/(1 + e), flanco intermedio; e = 0 sin viento ni pendiente; LB acotado a [1, 8].

## 3. Verificación del autómata con escenarios sintéticos (pruebas automáticas `tests/test_automata.py`)

| Escenario | Resultado medido | Criterio |
|---|---|---|
| Homogéneo GR2, sin viento ni pendiente, 24 h, 121 × 121 | 16 vecinos: velocidad efectiva radial media 0,00899 m/s vs R0 teórica 0,00911 (error −0,4 % … −2,5 % según azimut); área 2.097 celdas vs círculo teórico 2.160 (−2,9 %). 8 vecinos: error hasta −6,7 % (frente octogonal). | isotropía < 4 %, área ± 6 % |
| Viento del oeste 5 m/s, 6 h | alcance este 106 celdas, oeste 5, norte 10: cabeza/cola 21 (teórico de la elipse 18,6 con e = 0,898), cabeza/flanco 10,6; θ_max = 90° | este > 5·oeste y > 3·norte; simetría N/S |
| Pendiente 20° que sube al norte, 6 h | norte 38 celdas vs sur 6 (ratio 6,3) | norte > 3·sur |
| Barrera no combustible de 3 celdas y franja fuera de dominio | 0 celdas quemadas tras la barrera y fuera del dominio | 0 |
| Humedad 1 h = 20 % (≥ M_x) | 1 celda quemada; fin por "sin propagación física" a las 12 h (configurable) | motivo 3 |
| Meteorología más corta que el periodo | fin por "fin de datos meteorológicos" | motivo 2 |
| Reproducibilidad | dos corridas idénticas → `t_llegada` y `estado` bit a bit iguales | igualdad |
| Paso temporal | Δt = 600 s vs 60 s con viento 8 m/s: alcance de cabeza igual ± 10 % (el esquema no limita la velocidad a una celda por paso) | |
| Persistencia | guardado y recuperación de `t_llegada` | |

Suite completa: 41 pruebas (`python -m pytest -q`, 4,5 s), todas sin red.

## 4. Rendimiento (grilla completa 1.671 × 1.671 = 2,79 M celdas, pastizal homogéneo, viento 6 m/s, Δt = 60 s, 16 vecinos)

| Duración | Pasos | Tiempo de simulación | ms/paso | Celdas quemadas | Frente máximo | Memoria RSS |
|---|---|---|---|---|---|---|
| 24 h | 1.440 | 1,1 s | 0,8 | 69.187 (6.227 ha) | 2.544 | 0,33 GB |
| 72 h | 4.320 | 3,1 s | 0,7 | 448.981 (40.408 ha) | 4.756 | 0,33 GB |

El costo es proporcional al tamaño del frente activo, no al número de celdas de la grilla. Compilación numba inicial: ~2 s (caché en disco).

## 5. Prueba de humo con datos reales (`scripts/simular.py --evento SL-2024-LASLAGUNAS --hipotesis 1 --horas 72`)

- Entradas reales de la Etapa 3 (clases, curado, LFMC desde NDMI, pendiente/orientación Copernicus, meteorología IFS, FFMC, biblioteca WindNinja), ignición en los dos focos SNMF a las 12:00 local del 18/09/2024, `k_clase = 1` (sin calibrar).
- 4.320 pasos en **16,8 s de CPU** (incluye composición horaria del viento y remuestreo a 30 m); frente máximo 10.182 celdas; 37.895 ha a las 72 h (motivo de fin: periodo solicitado alcanzado).
- Comparación preliminar con la cicatriz final (40.054 ha rasterizadas): IoU 0,248, Dice 0,397, omisión 0,61, comisión 0,59. **No es una validación**: compara 72 h simuladas con la cicatriz de 21 días, sin calibración ni ajuste de ignición. Muestra que el frente simulado avanza principalmente hacia el sur (viento del norte del 19 al 21/09) mientras la cicatriz observada se extiende al norte y oeste; esto orienta las hipótesis a explorar en las Etapas 6–7 (hora y lugar de ignición del 18/09 con viento del SO, factores k por clase, WAF, humedad viva). Figura: `docs/fig_etapa4_prueba_72h_SL-2024.png`.

## 6. Limitaciones del núcleo (registradas)
- El orden de procesamiento dentro de un paso puede retrasar hasta Δt la ignición de una celda alcanzable por dos vecinos; error acotado por Δt (60 s).
- Las tablas de ROS discretizan la humedad viva en 10 bins y el curado en 2 niveles; las humedades muertas son uniformes en el dominio por hora.
- Sin spotting, sin fuego de copas, sin mitigación, sin dependencia de la intensidad para el salto de barreras (una celda no combustible de 30 m detiene el fuego).
- Suma vectorial viento–pendiente: sobrestimación conocida en viento cruzado fuerte (Sharples 2008).
- El viento de WindNinja es neutral y con un único tipo de vegetación.
