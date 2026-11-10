# Evaluación · las_lagunas_la_aguada_2023

Incendio 'Las Lagunas y La Aguada' (parte SNMF, Libertador General San Martín), 31-08-2023 → 01-09-2023 (extinguido). Cicatriz COE de 105,4 ha, 100 % dentro del dominio Las Lagunas–Potrerillos. Caso SM01 de conjunto_pruebas adaptado al estándar 7.1. La hora de ignición es supuesta (12:00 local): no hay focos VIIRS sobre esta cicatriz.

## Métricas contra el perímetro observado

| Variante | t0 (local) | ha sim | ha obs | Error ha | Error % | Sørensen | Jaccard | Comisión % | Omisión % | Dist. centroides (m) | Rumbo obs→sim | Borde |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | 31-08 12:00 | 2782.98 | 106.02 | 2676.96 | 2525.0 | 0.072 | 0.037 | 96.3 | 1.7 | 2285.0 | 173.0° | sí |
| t0_06h | 31-08 06:00 | 2875.05 | 106.02 | 2769.03 | 2611.8 | 0.07 | 0.036 | 96.4 | 1.6 | 2415.0 | 174.0° | sí |
| t0_09h | 31-08 09:00 | 2889.27 | 106.02 | 2783.25 | 2625.2 | 0.07 | 0.036 | 96.4 | 1.6 | 2450.0 | 177.0° | sí |
| t0_15h | 31-08 15:00 | 2948.49 | 106.02 | 2842.47 | 2681.1 | 0.068 | 0.035 | 96.5 | 1.8 | 1813.0 | 175.0° | sí |
| t0_18h | 31-08 18:00 | 2870.28 | 106.02 | 2764.26 | 2607.3 | 0.07 | 0.036 | 96.4 | 1.8 | 1208.0 | 171.0° | no |
| ignicion_snmf_original | 31-08 12:00 | 2428.47 | 106.02 | 2322.45 | 2190.6 | 0.082 | 0.043 | 95.7 | 2.0 | 2287.0 | 170.0° | sí |
| vecindad_16 | 31-08 12:00 | 4164.21 | 106.02 | 4058.19 | 3827.8 | 0.05 | 0.025 | 97.5 | 0.1 | 2306.0 | 173.0° | sí |
| dt_1min | 31-08 12:00 | 2780.28 | 106.02 | 2674.26 | 2522.4 | 0.072 | 0.037 | 96.3 | 1.7 | 2285.0 | 173.0° | sí |
| dt_5min | 31-08 12:00 | 2781.45 | 106.02 | 2675.43 | 2523.5 | 0.072 | 0.037 | 96.3 | 1.7 | 2288.0 | 173.0° | sí |

## Comparación a igual superficie

Instante en que el área simulada alcanza la observada. Mide forma y rumbo de la propagación con independencia de la supresión, que esta etapa no modela (propagación libre).

| Variante | t (h desde t0) | Sørensen | Jaccard | Comisión % | Omisión % | Dist. centroides (m) | Rumbo obs→sim |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 6.9 | 0.027 | 0.014 | 97.3 | 97.3 | 1233.0 | 175.0° |
| t0_06h | 7.0 | 0.491 | 0.325 | 50.9 | 50.9 | 520.0 | 189.0° |
| t0_09h | 6.1 | 0.132 | 0.07 | 86.8 | 86.8 | 1047.0 | 184.0° |
| t0_15h | 7.2 | 0.068 | 0.035 | 93.2 | 93.2 | 1143.0 | 167.0° |
| t0_18h | 6.8 | 0.097 | 0.051 | 90.3 | 90.3 | 1107.0 | 165.0° |
| ignicion_snmf_original | 9.2 | 0.0 | 0.0 | 100.0 | 100.0 | 1463.0 | 163.0° |
| vecindad_16 | 3.8 | 0.02 | 0.01 | 98.0 | 98.0 | 1378.0 | 175.0° |
| dt_1min | 6.9 | 0.027 | 0.014 | 97.3 | 97.3 | 1233.0 | 175.0° |
| dt_5min | 6.9 | 0.027 | 0.014 | 97.3 | 97.3 | 1233.0 | 175.0° |

## Perímetros alternativos

| Variante | Perímetro | ha obs | Sørensen | Jaccard | Error % |
|---|---|---:|---:|---:|---:|
| base | mapbiomas_fuego_2023 | 142.92 | 0.091 | 0.048 | 1847.2 |
| t0_06h | mapbiomas_fuego_2023 | 142.92 | 0.089 | 0.046 | 1911.6 |
| t0_09h | mapbiomas_fuego_2023 | 142.92 | 0.088 | 0.046 | 1921.6 |
| t0_15h | mapbiomas_fuego_2023 | 142.92 | 0.086 | 0.045 | 1963.0 |
| t0_18h | mapbiomas_fuego_2023 | 142.92 | 0.089 | 0.046 | 1908.3 |
| ignicion_snmf_original | mapbiomas_fuego_2023 | 142.92 | 0.104 | 0.055 | 1599.2 |
| vecindad_16 | mapbiomas_fuego_2023 | 142.92 | 0.063 | 0.033 | 2813.7 |
| dt_1min | mapbiomas_fuego_2023 | 142.92 | 0.091 | 0.048 | 1845.3 |
| dt_5min | mapbiomas_fuego_2023 | 142.92 | 0.091 | 0.048 | 1846.2 |

## Tiempos de llegada contra focos VIIRS

No hay focos VIIRS dentro de la grilla de simulación para este caso: la comparación de tiempos de llegada no es aplicable.

## Figuras

- base: `salidas/20261007_111105_las_lagunas_la_aguada_2023_base/comparacion_observado.png` (corrida `20261007_111105_las_lagunas_la_aguada_2023_base`)
- t0_06h: `salidas/20261007_111155_las_lagunas_la_aguada_2023_t0_06h/comparacion_observado.png` (corrida `20261007_111155_las_lagunas_la_aguada_2023_t0_06h`)
- t0_09h: `salidas/20261007_111247_las_lagunas_la_aguada_2023_t0_09h/comparacion_observado.png` (corrida `20261007_111247_las_lagunas_la_aguada_2023_t0_09h`)
- t0_15h: `salidas/20261007_111330_las_lagunas_la_aguada_2023_t0_15h/comparacion_observado.png` (corrida `20261007_111330_las_lagunas_la_aguada_2023_t0_15h`)
- t0_18h: `salidas/20261007_111358_las_lagunas_la_aguada_2023_t0_18h/comparacion_observado.png` (corrida `20261007_111358_las_lagunas_la_aguada_2023_t0_18h`)
- ignicion_snmf_original: `salidas/20261007_111426_las_lagunas_la_aguada_2023_ignicion_snmf_original/comparacion_observado.png` (corrida `20261007_111426_las_lagunas_la_aguada_2023_ignicion_snmf_original`)
- vecindad_16: `salidas/20261007_111452_las_lagunas_la_aguada_2023_vecindad_16/comparacion_observado.png` (corrida `20261007_111452_las_lagunas_la_aguada_2023_vecindad_16`)
- dt_1min: `salidas/20261007_111538_las_lagunas_la_aguada_2023_dt_1min/comparacion_observado.png` (corrida `20261007_111538_las_lagunas_la_aguada_2023_dt_1min`)
- dt_5min: `salidas/20261007_111634_las_lagunas_la_aguada_2023_dt_5min/comparacion_observado.png` (corrida `20261007_111634_las_lagunas_la_aguada_2023_dt_5min`)

## Discusión

**1. Propagación libre contra un incendio contenido.** Todas las variantes queman entre 2.400 y 3.000 ha en 36 h,
contra 105 ha de la cicatriz COE (error > 2.000 %, comisión ≈ 96 %). La omisión, en cambio, es de 1,6 a 2 %: la
simulación cubre casi toda la cicatriz observada y sigue de largo. El parte SNMF registra seis cuarteles de bomberos
voluntarios y el incendio extinguido al día siguiente: la cicatriz es el resultado de la **supresión**, que esta etapa
no modela por diseño (sección "Rol y objetivo" del enunciado). Por eso las métricas finales no miden la calidad del
modelo de propagación sino la ausencia de mitigación; la tabla "a igual superficie" es la que permite comparar forma
y rumbo.

**2. Hora de ignición: cambia la forma, no el área.** La superficie final varía menos de 6 % entre t0 = 06:00 y 18:00
(la ventana de 36 h siempre incluye una tarde completa), pero la comparación a igual superficie cambia por completo:
con **t0 = 06:00** el Sørensen sube a 0,49 y el centroide simulado queda a 520 m del observado, mientras que con t0 =
12:00 (supuesto del conjunto anterior) es 0,03 y 1.230 m. La explicación está en la serie ERA5: el viento sopla del
S–SSE (165–182°) a 11–19 km/h desde la madrugada hasta las 09:00, rota al E a las 11:00 y al N a las 12:00. La
cicatriz COE se extiende **al norte** del punto del parte: solo una ignición temprana, con viento sur, propaga hacia
la cicatriz; las igniciones de la tarde empujan el fuego hacia el sur, fuera de ella. Conclusión operativa: o la
ignición fue de madrugada, o el punto del parte marca el flanco sur final y no el origen. En cualquier caso el t0 de
12:00 heredado de `conjunto_pruebas` (D18) no es compatible con la cicatriz y la meteorología.

**3. Punto de ignición.** Con el punto SNMF original (88,7 m fuera de la cicatriz, al sur) y viento del N, el fuego
simulado a igual superficie no toca la cicatriz (Sørensen 0): la ubicación del punto pesa tanto como la hora. El
punto proyectado al borde es una decisión razonable pero derivada, y queda declarada.

**4. Discretización.** Entre Δt = 1 y Δt = 5 min la superficie difiere 0,04 % (requisito: < 5 %), gracias a los
sub-pasos adaptativos. La vecindad de 16 da un 50 % más de superficie que la de 8 y alcanza la superficie observada
en 3,8 h en vez de 6,9 h. No es por saltar barreras (se exige que las celdas intermedias de cada salto de caballo
sean combustibles y el resultado casi no cambió): en los tests sintéticos homogéneos ambas vecindades coinciden
dentro del 4 %, así que el efecto aparece con el **mosaico de combustibles** a 30 m. La ROS que gobierna cada
transición es la de la celda emisora; con saltos de 67 m una celda de SH5 enciende directamente celdas a dos de
distancia sin "pagar" la velocidad de las celdas lentas (TU1, GS2) que hay en el medio. Por eso la vecindad de 8
queda como valor por defecto y la de 16 se reserva para terreno homogéneo; la mejora pendiente es ponderar la ROS
emisora con la receptora (tiempo de viaje mitad y mitad), que corrige este sesgo.

**5. Perímetros alternativos.** MapBiomas Fuego 2023 marca 143 ha quemadas en agosto dentro de la caja, con Sørensen
y error del mismo orden que el COE. El evento Sentinel-2/VIIRS "2023-007" (145 ha) es otra cicatriz 8 km al NO con el
mismo nombre de parte y 11 focos VIIRS del 01-09 a las 15:26 local: es el candidato natural para el próximo caso,
porque permitiría la comparación de tiempos de llegada que acá no es aplicable (ningún foco sobre esta cicatriz).

**6. Magnitudes físicas.** En la tarde del 31-08 (HR 21–26 %, 19 km/h del N, humedad 1 h ≈ 4 %) la ROS mediana del
frente ronda 15 m/min con máximos en SH5 de varias decenas de m/min e intensidades de Byram de miles de kW/m. Son
valores coherentes con Rothermel para arbustal denso con viento, pero probablemente altos para la zona: las mayores
incertidumbres son la humedad del combustible vivo (derivada del NDMI con una relación sin calibrar), el factor de
ajuste del viento bajo arbustal y la propia serie ERA5 (celda de 28 km, relieve suavizado). Recomendación: calibrar
`humedad.viva_*`, el WAF y el ajuste topográfico con los casos grandes del conjunto anterior (SM04 Paso Grande 2024,
1.624 ha; SM05 Las Lagunas–Potrerillos 2024, 38.631 ha), donde el peso relativo de la supresión es menor, y con los
tiempos de llegada VIIRS.

**7. Borde del dominio.** En casi todas las variantes el fuego libre alcanza el borde de la caja (5 km de buffer) antes
de las 36 h, y el estado horario lo avisa. Para análisis de propagación libre conviene una caja mayor; para la
métrica a igual superficie (≈ 7 h) el borde no interviene.

