# Evaluación · las_lagunas_potrerillos_2024

Complejo Las Lagunas–Potrerillos (partes SNMF 'LAS LAGUNAS' y 'POTRERILLOS' del 18-09-2024, unidos por el evento satelital 2024-003), 18-09-2024 → 09-10-2024 (extinguido). Cicatriz COE de 38.631 ha (un polígono de 38.541 ha + parches), 100 % dentro del dominio: es el incendio que motivó el dominio Las Lagunas–Potrerillos. Caso SM05 de conjunto_pruebas (tipo estrés) adaptado al estándar 7.1. Hay 2.006 focos VIIRS S-NPP: el primer pase (18-09 15:43 local) ya muestra 50 focos a lo largo de 9 km, por lo que la ignición base es múltiple (los focos del primer pase) y t0 es la hora de ese pase.

## Métricas contra el perímetro observado

| Variante | t0 (local) | ha sim | ha obs | Error ha | Error % | Sørensen | Jaccard | Comisión % | Omisión % | Dist. centroides (m) | Rumbo obs→sim | Borde |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | 18-09 15:43 | 89766.9 | 38632.14 | 51134.76 | 132.4 | 0.343 | 0.207 | 75.4 | 42.9 | 9345.0 | 228.0° | sí |
| parte_potrerillos_12h | 18-09 12:00 | 52575.03 | 38632.14 | 13942.89 | 36.1 | 0.353 | 0.214 | 69.4 | 58.3 | 8602.0 | 202.0° | sí |
| parte_las_lagunas_12h | 18-09 12:00 | 0.0 | 38632.14 | -38632.14 | -100.0 | 0.0 | 0.0 | None | 100.0 | None | None° | no |
| dos_partes_12h | 18-09 12:00 | 52575.03 | 38632.14 | 13942.89 | 36.1 | 0.353 | 0.214 | 69.4 | 58.3 | 8602.0 | 202.0° | sí |
| duracion_144h | 18-09 15:43 | 149293.53 | 38632.14 | 110661.39 | 286.4 | 0.384 | 0.238 | 75.8 | 6.6 | 6001.0 | 237.0° | sí |
| dt_5min | 18-09 15:43 | 89754.75 | 38632.14 | 51122.61 | 132.3 | 0.343 | 0.207 | 75.4 | 43.0 | 9348.0 | 228.0° | sí |

## Comparación a igual superficie

Instante en que el área simulada alcanza la observada. Mide forma y rumbo de la propagación con independencia de la supresión, que esta etapa no modela (propagación libre).

| Variante | t (h desde t0) | Sørensen | Jaccard | Comisión % | Omisión % | Dist. centroides (m) | Rumbo obs→sim |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 35.2 | 0.315 | 0.187 | 68.5 | 68.5 | 8270.0 | 218.0° |
| parte_potrerillos_12h | 57.1 | 0.349 | 0.211 | 65.1 | 65.1 | 8510.0 | 206.0° |
| dos_partes_12h | 57.1 | 0.349 | 0.211 | 65.1 | 65.1 | 8510.0 | 206.0° |
| duracion_144h | 35.2 | 0.315 | 0.187 | 68.5 | 68.5 | 8270.0 | 218.0° |
| dt_5min | 35.2 | 0.315 | 0.187 | 68.5 | 68.5 | 8273.0 | 218.0° |

## Perímetros alternativos

| Variante | Perímetro | ha obs | Sørensen | Jaccard | Error % |
|---|---|---:|---:|---:|---:|
| base | mapbiomas_fuego_2024 | 40641.75 | 0.384 | 0.238 | 120.9 |
| base | sentinel2_2024-003 | 25726.68 | 0.265 | 0.153 | 248.9 |
| parte_potrerillos_12h | mapbiomas_fuego_2024 | 40641.75 | 0.401 | 0.251 | 29.4 |
| parte_potrerillos_12h | sentinel2_2024-003 | 25726.68 | 0.283 | 0.165 | 104.4 |
| parte_las_lagunas_12h | mapbiomas_fuego_2024 | 40641.75 | 0.0 | 0.0 | -100.0 |
| parte_las_lagunas_12h | sentinel2_2024-003 | 25726.68 | 0.0 | 0.0 | -100.0 |
| dos_partes_12h | mapbiomas_fuego_2024 | 40641.75 | 0.401 | 0.251 | 29.4 |
| dos_partes_12h | sentinel2_2024-003 | 25726.68 | 0.283 | 0.165 | 104.4 |
| duracion_144h | mapbiomas_fuego_2024 | 40641.75 | 0.393 | 0.244 | 267.3 |
| duracion_144h | sentinel2_2024-003 | 25726.68 | 0.26 | 0.15 | 480.3 |
| dt_5min | mapbiomas_fuego_2024 | 40641.75 | 0.384 | 0.238 | 120.8 |
| dt_5min | sentinel2_2024-003 | 25726.68 | 0.265 | 0.153 | 248.9 |

## Tiempos de llegada contra focos VIIRS

**base**: 1194 focos comparables, sesgo -986.0 min, RMSE 2129.0 min, 794 focos no alcanzados por la simulación.

Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.

| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |
|---|---:|---:|---:|---:|---|---:|
| 18-09 15:43 | 50 | 50 | 0 | 0 | 0 / 108 | 109.86 |
| 19-09 01:21 | 40 | 40 | 0 | -42 | -333 / 324 | 20.18 |
| 19-09 03:02 | 54 | 54 | 0 | -187 | -489 / 330 | 21.1 |
| 19-09 15:24 | 291 | 291 | 0 | -34 | -863 / 1316 | 199.94 |
| 20-09 02:43 | 544 | 144 | 400 | -20 | -1251 / 2149 | 172.31 |
| 20-09 15:06 | 562 | 278 | 284 | -814 | -2050 / 636 | 176.77 |
| 21-09 02:24 | 102 | 57 | 45 | -614 | -1608 / -326 | 17.87 |
| 21-09 14:47 | 129 | 110 | 19 | -1892 | -2693 / -1077 | 203.19 |
| 22-09 02:05 | 18 | 12 | 6 | -1918 | -2099 / -1438 | 9.4 |
| 22-09 14:28 | 37 | 20 | 17 | -2796 | -3009 / -2572 | 41.51 |
| 22-09 16:08 | 13 | 0 | 13 | – | – | 19.42 |
| 23-09 01:46 | 9 | 8 | 1 | -3850 | -4510 / -3662 | 11.22 |
| 23-09 03:27 | 4 | 4 | 0 | -3890 | -3945 / -3787 | 8.51 |
| 23-09 14:09 | 50 | 46 | 4 | -5228 | -6351 / -4456 | 94.06 |
| 23-09 15:49 | 81 | 76 | 5 | -5348 | -6407 / -4502 | 40.44 |
| 24-09 01:27 | 2 | 2 | 0 | -4746 | -4868 / -4624 | 0.92 |
| 24-09 15:30 | 2 | 2 | 0 | -5621 | -5622 / -5620 | 12.6 |

**parte_potrerillos_12h**: 955 focos comparables, sesgo -253.0 min, RMSE 2050.0 min, 1033 focos no alcanzados por la simulación.

Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.

| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |
|---|---:|---:|---:|---:|---|---:|
| 18-09 15:43 | 50 | 50 | 0 | 1618 | 321 / 2616 | 109.86 |
| 19-09 01:21 | 40 | 40 | 0 | 1182 | 38 / 2286 | 20.18 |
| 19-09 03:02 | 54 | 54 | 0 | 1598 | -41 / 2268 | 21.1 |
| 19-09 15:24 | 291 | 262 | 29 | 766 | -176 / 2475 | 199.94 |
| 20-09 02:43 | 544 | 90 | 454 | 904 | -292 / 1966 | 172.31 |
| 20-09 15:06 | 562 | 205 | 357 | 238 | -770 / 1223 | 176.77 |
| 21-09 02:24 | 102 | 11 | 91 | -1280 | -1435 / -566 | 17.87 |
| 21-09 14:47 | 129 | 76 | 53 | -1228 | -2084 / -202 | 203.19 |
| 22-09 02:05 | 18 | 9 | 9 | -1382 | -1676 / -1102 | 9.4 |
| 22-09 14:28 | 37 | 20 | 17 | -2368 | -2540 / -2110 | 41.51 |
| 22-09 16:08 | 13 | 0 | 13 | – | – | 19.42 |
| 23-09 01:46 | 9 | 8 | 1 | -3474 | -3560 / -3399 | 11.22 |
| 23-09 03:27 | 4 | 4 | 0 | -3597 | -3711 / -3559 | 8.51 |
| 23-09 14:09 | 50 | 46 | 4 | -4366 | -4693 / -4166 | 94.06 |
| 23-09 15:49 | 81 | 76 | 5 | -4424 | -4893 / -4159 | 40.44 |
| 24-09 01:27 | 2 | 2 | 0 | -4434 | -4593 / -4276 | 0.92 |
| 24-09 15:30 | 2 | 2 | 0 | -4568 | -4579 / -4556 | 12.6 |

**parte_las_lagunas_12h**: 0 focos comparables, sesgo – min, RMSE – min, 1988 focos no alcanzados por la simulación.

Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.

| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |
|---|---:|---:|---:|---:|---|---:|
| 18-09 15:43 | 50 | 0 | 50 | – | – | 109.86 |
| 19-09 01:21 | 40 | 0 | 40 | – | – | 20.18 |
| 19-09 03:02 | 54 | 0 | 54 | – | – | 21.1 |
| 19-09 15:24 | 291 | 0 | 291 | – | – | 199.94 |
| 20-09 02:43 | 544 | 0 | 544 | – | – | 172.31 |
| 20-09 15:06 | 562 | 0 | 562 | – | – | 176.77 |
| 21-09 02:24 | 102 | 0 | 102 | – | – | 17.87 |
| 21-09 14:47 | 129 | 0 | 129 | – | – | 203.19 |
| 22-09 02:05 | 18 | 0 | 18 | – | – | 9.4 |
| 22-09 14:28 | 37 | 0 | 37 | – | – | 41.51 |
| 22-09 16:08 | 13 | 0 | 13 | – | – | 19.42 |
| 23-09 01:46 | 9 | 0 | 9 | – | – | 11.22 |
| 23-09 03:27 | 4 | 0 | 4 | – | – | 8.51 |
| 23-09 14:09 | 50 | 0 | 50 | – | – | 94.06 |
| 23-09 15:49 | 81 | 0 | 81 | – | – | 40.44 |
| 24-09 01:27 | 2 | 0 | 2 | – | – | 0.92 |
| 24-09 15:30 | 2 | 0 | 2 | – | – | 12.6 |

**dos_partes_12h**: 955 focos comparables, sesgo -253.0 min, RMSE 2050.0 min, 1033 focos no alcanzados por la simulación.

Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.

| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |
|---|---:|---:|---:|---:|---|---:|
| 18-09 15:43 | 50 | 50 | 0 | 1618 | 321 / 2616 | 109.86 |
| 19-09 01:21 | 40 | 40 | 0 | 1182 | 38 / 2286 | 20.18 |
| 19-09 03:02 | 54 | 54 | 0 | 1598 | -41 / 2268 | 21.1 |
| 19-09 15:24 | 291 | 262 | 29 | 766 | -176 / 2475 | 199.94 |
| 20-09 02:43 | 544 | 90 | 454 | 904 | -292 / 1966 | 172.31 |
| 20-09 15:06 | 562 | 205 | 357 | 238 | -770 / 1223 | 176.77 |
| 21-09 02:24 | 102 | 11 | 91 | -1280 | -1435 / -566 | 17.87 |
| 21-09 14:47 | 129 | 76 | 53 | -1228 | -2084 / -202 | 203.19 |
| 22-09 02:05 | 18 | 9 | 9 | -1382 | -1676 / -1102 | 9.4 |
| 22-09 14:28 | 37 | 20 | 17 | -2368 | -2540 / -2110 | 41.51 |
| 22-09 16:08 | 13 | 0 | 13 | – | – | 19.42 |
| 23-09 01:46 | 9 | 8 | 1 | -3474 | -3560 / -3399 | 11.22 |
| 23-09 03:27 | 4 | 4 | 0 | -3597 | -3711 / -3559 | 8.51 |
| 23-09 14:09 | 50 | 46 | 4 | -4366 | -4693 / -4166 | 94.06 |
| 23-09 15:49 | 81 | 76 | 5 | -4424 | -4893 / -4159 | 40.44 |
| 24-09 01:27 | 2 | 2 | 0 | -4434 | -4593 / -4276 | 0.92 |
| 24-09 15:30 | 2 | 2 | 0 | -4568 | -4579 / -4556 | 12.6 |

**duracion_144h**: 1838 focos comparables, sesgo 796.0 min, RMSE 3073.0 min, 150 focos no alcanzados por la simulación.

Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.

| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |
|---|---:|---:|---:|---:|---|---:|
| 18-09 15:43 | 50 | 50 | 0 | 0 | 0 / 108 | 109.86 |
| 19-09 01:21 | 40 | 40 | 0 | -42 | -333 / 324 | 20.18 |
| 19-09 03:02 | 54 | 54 | 0 | -187 | -489 / 330 | 21.1 |
| 19-09 15:24 | 291 | 291 | 0 | -34 | -863 / 1316 | 199.94 |
| 20-09 02:43 | 544 | 505 | 39 | 3825 | -675 / 5713 | 172.31 |
| 20-09 15:06 | 562 | 475 | 87 | 104 | -1669 / 5007 | 176.77 |
| 21-09 02:24 | 102 | 84 | 18 | -492 | -1516 / 4136 | 17.87 |
| 21-09 14:47 | 129 | 127 | 2 | -1613 | -2646 / 2395 | 203.19 |
| 22-09 02:05 | 18 | 18 | 0 | -1676 | -2067 / 3657 | 9.4 |
| 22-09 14:28 | 37 | 35 | 2 | -2585 | -2949 / 2612 | 41.51 |
| 22-09 16:08 | 13 | 11 | 2 | 2372 | 63 / 2602 | 19.42 |
| 23-09 01:46 | 9 | 9 | 0 | -3725 | -4507 / -2587 | 11.22 |
| 23-09 03:27 | 4 | 4 | 0 | -3890 | -3945 / -3787 | 8.51 |
| 23-09 14:09 | 50 | 50 | 0 | -5103 | -6345 / -4238 | 94.06 |
| 23-09 15:49 | 81 | 81 | 0 | -5250 | -6383 / -4368 | 40.44 |
| 24-09 01:27 | 2 | 2 | 0 | -4746 | -4868 / -4624 | 0.92 |
| 24-09 15:30 | 2 | 2 | 0 | -5621 | -5622 / -5620 | 12.6 |

**dt_5min**: 1193 focos comparables, sesgo -990.0 min, RMSE 2131.0 min, 795 focos no alcanzados por la simulación.

Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.

| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |
|---|---:|---:|---:|---:|---|---:|
| 18-09 15:43 | 50 | 50 | 0 | 0 | 0 / 108 | 109.86 |
| 19-09 01:21 | 40 | 40 | 0 | -42 | -333 / 324 | 20.18 |
| 19-09 03:02 | 54 | 54 | 0 | -187 | -489 / 330 | 21.1 |
| 19-09 15:24 | 291 | 291 | 0 | -34 | -864 / 1316 | 199.94 |
| 20-09 02:43 | 544 | 143 | 401 | -27 | -1255 / 2130 | 172.31 |
| 20-09 15:06 | 562 | 278 | 284 | -814 | -2049 / 635 | 176.77 |
| 21-09 02:24 | 102 | 57 | 45 | -616 | -1608 / -325 | 17.87 |
| 21-09 14:47 | 129 | 110 | 19 | -1928 | -2698 / -1082 | 203.19 |
| 22-09 02:05 | 18 | 12 | 6 | -1921 | -2099 / -1438 | 9.4 |
| 22-09 14:28 | 37 | 20 | 17 | -2795 | -3010 / -2572 | 41.51 |
| 22-09 16:08 | 13 | 0 | 13 | – | – | 19.42 |
| 23-09 01:46 | 9 | 8 | 1 | -3883 | -4668 / -3669 | 11.22 |
| 23-09 03:27 | 4 | 4 | 0 | -3902 | -3955 / -3787 | 8.51 |
| 23-09 14:09 | 50 | 46 | 4 | -5227 | -6350 / -4456 | 94.06 |
| 23-09 15:49 | 81 | 76 | 5 | -5348 | -6408 / -4502 | 40.44 |
| 24-09 01:27 | 2 | 2 | 0 | -4744 | -4863 / -4624 | 0.92 |
| 24-09 15:30 | 2 | 2 | 0 | -5622 | -5622 / -5621 | 12.6 |


## Figuras

- base: `salidas/20261007_120529_las_lagunas_potrerillos_2024_base/comparacion_observado.png` (corrida `20261007_120529_las_lagunas_potrerillos_2024_base`)
- parte_potrerillos_12h: `salidas/20261007_121318_las_lagunas_potrerillos_2024_parte_potrerillos_12h/comparacion_observado.png` (corrida `20261007_121318_las_lagunas_potrerillos_2024_parte_potrerillos_12h`)
- parte_las_lagunas_12h: `salidas/20261007_121901_las_lagunas_potrerillos_2024_parte_las_lagunas_12h/comparacion_observado.png` (corrida `20261007_121901_las_lagunas_potrerillos_2024_parte_las_lagunas_12h`)
- dos_partes_12h: `salidas/20261007_122036_las_lagunas_potrerillos_2024_dos_partes_12h/comparacion_observado.png` (corrida `20261007_122036_las_lagunas_potrerillos_2024_dos_partes_12h`)
- duracion_144h: `salidas/20261007_122618_las_lagunas_potrerillos_2024_duracion_144h/comparacion_observado.png` (corrida `20261007_122618_las_lagunas_potrerillos_2024_duracion_144h`)
- dt_5min: `salidas/20261007_124025_las_lagunas_potrerillos_2024_dt_5min/comparacion_observado.png` (corrida `20261007_124025_las_lagunas_potrerillos_2024_dt_5min`)

