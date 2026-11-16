# F6 — Fila de v4.0 de Las Chacras octubre 2023: ficha de comparabilidad

Fecha: 2026-11-14 (corridas) y 2026-11-16 (métricas y ficha) · Rama `f6-verificacion` · Pedido aprobado: `F6_pedido_de_aprobacion.md`
(D-E3-30, punto 14; D-E3-31). Cifras en `docs/etapa3/historico_referencia.json` (fila 3, bloque `medida`, y
`configuracion_por_defecto_medida`).

## 1. Qué se corrió

Una sola corrida de la fila 3 de docs/v4.0/31 §7.2 (v4.0 libre, `alt4`, hipótesis 4, 06 UTC, sin parada en cicatriz, 141 h) y,
para declarar la diferencia, la configuración por defecto del simulador (variante `barreras`, D-E3-01) a 72 h y a 141 h.
Las tres por `app/motores/proceso.py --corrida <carpeta>` con un `corrida.json` que trae solo `base.definicion` (sin bitácora);
las métricas, con `app/motores/metricas_v31.py --corrida <carpeta>`, el mismo proceso que lanza el servidor.

| Corrida | `base.definicion` | Carpeta (`resultados/app/F6-referencia/`) |
|---|---|---|
| A: fila 3 | `{evento: SL-2023-CHACRASOCT, hipotesis: 4, ignicion: alt4, variante: libre, parar_en_cicatriz: off, horas: 141}` | `v40_libre_141h` |
| B: por defecto, 72 h | `{evento: SL-2023-CHACRASOCT, hipotesis: 4, ignicion: alt4, horas: 72}` | `v40_barreras_72h` |
| B': por defecto, hasta el fin | ídem con `horas: 141` (lo que corre `POST /api/historicos/.../corrida` sin `horas`) | `v40_barreras_141h` |

141 h = de 2023-10-17T06:00Z a `fin.fin_simulacion_utc` = 2023-10-23T03:00Z de la ficha, como en §7.2.

Código: commit `bcdf4c6` de `f6-verificacion` con cambios sin commit en `app/motores` (sha256 de `git diff HEAD -- app/motores`
= `54d40fd2b42f…`, el mismo antes de las corridas y al escribir esta ficha); `herramientas/congelado.py`: "versiones congeladas
intactas (244 archivos)", conjunto `2b32757194d2`. `src/v4.0` y `src/v3.1` son los congelados.

## 2. Resultado

| | IoU igual sup. | h hasta la sup. | A tiempo | Adelantado | Atrasado | No alcanzado | Error mediano (h) | Puntaje | ha al final |
|---|---|---|---|---|---|---|---|---|---|
| §7.2, fila 3 (documentada) | 0,548 | 61,7 | 0,20 | 0,27 | 0,53 | — | +2,2 | 0,374 | 29.319 |
| A: libre, 141 h (medida) | **0,548** | **61,7** | **0,20** | **0,267** | **0,533** | 0 | **+2,2** | **0,374** | **29.319,21** |
| B: barreras, 72 h | 0,579 | 62,6 | 0,20 | 0,267 | 0,50 | 0,033 | +2,2 | 0,390 | 2.356,29 |
| B': barreras, 141 h | 0,579 | 62,6 | 0,20 | 0,267 | 0,533 | 0 | +2,2 | 0,390 | 24.047,37 |

**A coincide con la fila documentada en todas las columnas**, redondeadas como en el documento (`precision` de
`historico_referencia.json`; 30 primeras detecciones). Las carpetas originales de §7.2 no están en el clon, así que la comparación es
por cifras, no celda por celda.

Comprobaciones adicionales:
- B tiene la hora de llegada **idéntica celda por celda** a la de E-E3-1 (`resultados/app/E-E3-1/chacrasoct_72h/v4_0/proceso` y
  `offline`, sha256 del raster `33e35e96deed…`), y sus cifras son las que ya anotaba `configuracion_por_defecto_del_simulador`.
- B' recortado a 72 h es idéntico a B (26.181 celdas): alargar el horizonte no cambia lo anterior.
- IoU por instante de la ficha (A): 0,171 (18/10 03Z), 0,393 (20/10), 0,107 (21/10), 0,046 (23/10, 28.209 ha válidas contra 1.306).

## 3. Tiempo de cómputo

AMD Ryzen 7 5700 (16 hilos), 16 GB, Linux, Python 3.14; un proceso por corrida, medido con `/usr/bin/time`.

| Corrida | Motor (pared) | s por hora simulada | Memoria pico | Métricas de v3.1 |
|---|---|---|---|---|
| A: libre, 141 h | 97,3 s | 0,69 | 669 MB (685 MB de RSS) | 1,2 s |
| B: barreras, 72 h | 23,9 s | 0,33 | 627 MB de RSS | 0,6 s |
| B': barreras, 141 h | 123,8 s | 0,88 | 681 MB (697 MB de RSS) | 0,7 s |

Las tres quedan dentro de la meta de E-E3-3 para v4.0 (≤ 3 s por hora con 30.000 ha). El costo crece con el frente activo: menos de
2.000 celdas activas hasta las 72 h y entre 4.500 y 9.000 desde las 96 h (más con barreras, que alargan el frente).

## 4. Ficha de comparabilidad (Anexo A del plan)

| Campo | A: §7.2 fila 3, regenerada | B / B': configuración por defecto del simulador |
|---|---|---|
| Motor y versión | v4.0 congelado (`src/v4.0`, conjunto `2b32757194d2`), versión 4.0.0, conducido por `app/motores/proceso.py` (commit `bcdf4c6` + diff de `app/motores` `54d40fd2b42f`) | igual |
| Modelo y variante; parámetros que difieren del YAML congelado | modelo_v3, variante `libre`: barreras de caminos **apagadas**, sin contención; ningún parámetro cambiado | modelo_v3, variante `barreras` (D-E3-01): barreras de caminos **activas**, probabilísticas, semilla 20261015; sin contención; ningún parámetro cambiado |
| Dominio / grilla | `las_lagunas_potrerillos`, EPSG:5345, 30 m, 1671 × 1672 | igual |
| Evento; rol | SL-2023-CHACRASOCT, **no visto (X-49)**: solo para mostrar, no para ajustar. Ficha sha256 `dc1c4c99…` = la de `eventos_no_vistos_X49.csv` | igual |
| Ignición | `alt4`: punto único = foco n04 del primer pase (−65,767908; −32,650586), 2023-10-17 06:00 UTC (hipótesis 4). **HIPÓTESIS** elegida con v4.0 libre sin parada sobre este mismo evento (§7.2); sin desplazamiento | igual |
| Meteorología | IFS 9 km del banco V4 vía Open-Meteo (análisis, promedio de 16 puntos), `meteo_horaria.csv` sha256 `9a911cb737ce…` | igual |
| Viento | serie, factor 10 m → 20 ft 0,87, `k_pendiente` 0,5, `k_relieve` 0,3, límite de Andrews 2013; sin WindNinja | igual |
| Índices y cobertura | los de `datos/procesados/v4.0/SL-2023-CHACRASOCT` (mes del evento y verano previo, del banco, GEE) | igual |
| Mapa de combustible | regla 3.3b, `combustible_pre_evento_33b.tif` sha256 `0c3468647a92…` | igual |
| Humedad; extinción por lluvia | muerta por retardo (EMC NFDRS), viva lineal; extinción `reversible`, sin umbral de lluvia de 24 h | igual |
| Barreras | ninguna (variante libre); sin cortafuegos | caminos, modo probabilístico, llama direccional, semilla 20261015; sin cortafuegos |
| Parada y horizonte | sin parada en cicatriz; 141 h (hasta `fin_simulacion_utc`); termina por horizonte | sin parada; 72 h (B) o 141 h (B'); termina por horizonte |
| Intervenciones | ninguna (bitácora vacía) | ninguna |
| Métrica, instante, referencia y máscara | métricas de v3.1: IoU en el instante en que la simulación iguala la superficie de la cicatriz; primeras detecciones VIIRS (ventana 13 h, holgura 1 h, 375 m); puntaje = (IoU + a tiempo) / 2. Cicatriz MapBiomas 2023_26601 de octubre (sha256 `a448db3d…`), 1.306 ha válidas; máscara del dominio y combustible de v3 > 0; 46 focos de `hotspots_v3.1` | igual |
| Evaluador | `app/motores/metricas_v31.py` sobre `evaluar_x49.evaluar` y `validation/metricas.py` de `src/v3.1`, iguales al congelado | igual |
| n y advertencias | **un evento**, 30 primeras detecciones; la ignición y la hora se eligieron con los focos de este mismo evento (el puntaje está a favor de A por construcción) | ídem; además, la ignición se eligió con la variante libre, no con la de barreras |

**Lectura al pie.**
- Qué difiere: solo la variante (barreras de caminos) y, en B, el horizonte. Insumos, ignición, evaluador y código son los mismos.
- Qué se puede concluir: el simulador reproduce la fila 3 de §7.2 con su configuración; el camino por `proceso.py` no altera v4.0
  (lo mismo que E-E3-1 mostró celda por celda para B). Con la configuración por defecto la app muestra para Las Chacras otras
  cifras que las del documento: IoU 0,579 en vez de 0,548 y puntaje 0,39 en vez de 0,374, con el mismo tiempo (0,20 a tiempo, +2,2 h);
  las barreras frenan la extensión final (24.047 contra 29.319 ha a las 141 h) pero no la corrigen: las dos siguen quemando 18 a 22
  veces la cicatriz porque modelo_v3 no apaga el fuego tras la lluvia del 18/10 (§7.2, lectura 4).
- Qué no se puede concluir: que las barreras mejoren v4.0 en general (un evento, diferencia de 0,016 de puntaje, ignición elegida con la
  variante libre) ni nada sobre la calibración: el evento es no visto y no se ajusta con él. Las cifras de B a 72 h y 141 h solo difieren
  en los focos del 19/10 18:25Z (atrasado 0,50 + no alcanzado 0,033 a 72 h; atrasado 0,533 a 141 h).
