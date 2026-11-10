# Informe de la primera simulación histórica: Las Lagunas – Potrerillos, 18/09/2024 – 10/10/2024

Corrida: `data/resultados/SL-2024-LASLAGUNAS_calibrado` (parámetros calibrados en la Etapa 7; figuras `mapa_*.png`, `animacion.gif`; copias en `docs/fig_informe_*`). Fecha: 2026-10-14.

## 1. Configuración
| Elemento | Valor |
|---|---|
| Dominio | Las Lagunas – Potrerillos, 2.500,14 km² efectivos (2.777.934 celdas de 30 m; grilla 1.672 × 1.671) — sin reducción |
| Referencia | MapBiomas Fuego Col. 1, polígono 2024_41914: 40.052 ha rasterizadas (SNMF informó 48.226 ha) |
| Ignición | dos focos SNMF (Las Lagunas −65,5477/−32,6367; Potrerillos −65,6232/−32,6422), 18/09/2024 15:00 UTC (12:00 local; hipótesis; VIIRS acota a < 17:26 UTC) |
| Fin | 10/10/2024 03:00 UTC (extinción SNMF 09/10) |
| Meteorología | Open-Meteo IFS 9 km, 16 puntos, 556 h; sin huecos |
| Viento | WindNinja 4.0.0, masa, 100 m, `brush`, biblioteca de 72 direcciones |
| Combustibles | clases v1 (cobertura 2023 + NDVI/NDMI S2 30/07–17/09/2024, 40 escenas); humedad 1 h por FFMC; LFMC por NDMI |
| Parámetros | k = {1: 0,5; 2: 0,5; 3: 0,5; 4: 3; 5: 3; 6: 5; 7: 5}; WAF × 1; 16 vecinos; Δt 60 s; sin mitigación |

## 2. Ejecución
| Métrica | Valor |
|---|---|
| Pasos | 24.964 (el frente se agotó el 05/10 23:04 UTC: motivo "frente agotado: no quedan celdas activas") |
| Tiempo de cómputo | 102,9 s (incluye viento horario y remuestreo); memoria pico 0,91 GB |
| Celdas quemadas al final | 2.762.078 (248.587 ha = 99 % del combustible del dominio) |
| Almacenamiento | t_llegada 11,2 MB; estado 0,04 MB; serie 0,06 MB; animación 8,5 MB |

## 3. Progresión simulada (fin de cada día local, 03 UTC)
| Día | ha simuladas | frente (celdas) | humedad 1 h % | viento m/s / desde |
|---|---:|---:|---:|---|
| 18/09 | 3.228 | 2.997 | 8,8 | 5,0 / 15° |
| 19/09 | 19.636 | 6.687 | 5,2 | 5,5 / 183° |
| 20/09 | **47.883** | 9.683 | 6,2 | 5,2 / 357° |
| 21/09 | 76.710 | 11.900 | 11,4 | 5,1 / 345° |
| 22/09 | 88.532 | 12.495 | 11,7 | 4,3 / 198° |
| 24/09 | 130.979 | 16.461 | 9,2 | 3,5 / 193° |
| 27/09 | 174.293 | 10.449 | 10,3 | 3,3 / 333° |
| 01/10 | 237.792 | 5.780 | 9,5 | 5,6 / 169° |
| 04/10 | 248.420 | 274 | 7,9 | 4,1 / 335° |

Observado (VIIRS): 393 detecciones el 18/09, 1.913 el 19/09, **5.037 el 20/09**, 1.152 el 21/09, residuales hasta el 26/09; contenido el 28/09; extinguido el 09/10.

## 4. Comparación con la cicatriz
| Instante (UTC) | IoU | Dice | ha sim | omisión | comisión |
|---|---|---|---|---|---|
| 21/09 03:00 (fin del 20/09, fase explosiva) | **0,393** | 0,565 | 46.665 | 0,39 | 0,48 |
| 22/09 03:00 | 0,344 | 0,512 | 75.992 | 0,26 | 0,61 |
| 25/09 03:00 | 0,272 | 0,427 | 129.356 | 0,10 | 0,72 |
| 28/09 03:00 (contenido) | 0,225 | 0,367 | 173.715 | 0,02 | 0,77 |
| 10/10 03:00 (extinguido) | 0,161 | 0,278 | 248.587 | 0,00 | 0,84 |

Acuerdo temporal con 9.333 focos VIIRS: 100 % alcanzados en algún momento; **56 % al final de su día de detección**; desfase mediano +5,5 h (p10 −27 h, p90 +110 h). Por día: 18/09 25 % (desfase +23 h: el modelo arranca más lento que el fuego real en su primera tarde), 19/09 63 % (+1,8 h), 20/09 53 % (+10 h), 21/09 43 %, 22–26/09 88–100 % (adelantado).

## 5. Lectura
- El modelo reproduce la **dirección y el orden de magnitud de la fase explosiva**: 47.883 ha simuladas al fin del 20/09 frente a 40.052 ha de cicatriz final, con el frente alcanzando la sierra al norte y el este el mismo día que los focos observados.
- La **omisión** (39 % al fin del 20/09) se concentra en las laderas del noroeste y la lengua norte; la **comisión** (48 %) en la llanura sur y este, donde la cicatriz real muestra bordes rectos compatibles con líneas de contención y límites de parcelas.
- A partir del 21/09 la simulación sin mitigación sigue quemando hasta agotar el combustible del dominio (248.587 ha); el incendio real fue contenido entre el 24 y el 28/09. Esas cifras no describen el fuego real sino la ausencia de supresión y de barreras efectivas en el modelo.
- La hora de ignición no cambia el resultado (± 0,005 de IoU); los parámetros de combustible por clase sí (de 0,23 a 0,39).

## 6. Qué es y qué no es este resultado
Es una reconstrucción calibrada con el propio evento (los factores k se ajustaron sobre esta cicatriz): sirve para evaluar la coherencia del modelo con la meteorología y el relieve, no como validación independiente. La validación independiente (eventos de 2022) está en `docs/07_validacion_etapa7.md`.
