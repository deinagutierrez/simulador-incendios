# E-E3-2 — Aclaración de la parte (c), antes de evaluar

Escrita el 2026-11-13 por quien escribe el prerregistro (deinagutierrez, con Claude), antes de correr la evaluación y sin
haber visto cifras de (b) ni de (c). Decisión D-E3-27. No cambia la pregunta, las métricas ni el criterio del prerregistro
(etiqueta `prerregistro-E-E3-2`); precisa qué índices cambian en (c).

## Qué dice el prerregistro

(c) "mapa de combustible de cada motor y corrida de Las Lagunas 2024 de 48 h con unos y otros índices, v4.0 y v3.1 librev2".

## Qué faltaba precisar

Cada motor usa los índices de forma distinta:

| Motor | Qué índices usa | De dónde salen en la operación en tiempo real |
|---|---|---|
| v3.1 | compuesto de ventana (45 días): clases de combustible, curado, humedad viva | AWS (o GEE, o manual) |
| v4.0 | compuesto de ventana como `indices_mes_evento` (humedad viva, curado) **y** compuestos de verano (enero a marzo) para el SB40 de la regla 3.3b y el NDVI de verano | ventana: AWS; verano 2026: AWS (generado el 2026-11-13) |

Con el diseño literal, el verano de los dos lados de v4.0 eran los compuestos de 2024 del repositorio, hechos con GEE. El SB40
iba a ser idéntico en los dos lados y el criterio 2 se iba a cumplir por construcción en v4.0, sin medir nada.

## Cómo se corre (c)

- Lado **GEE**: ventana = `ndvi_30m`/`ndmi_30m` del evento; verano = `sim_v4/dinamicos/indices/NDVI_NDMI_2024_0{1,2,3}.tif`.
- Lado **AWS**: ventana = el compuesto de (a); verano = enero, febrero y marzo de 2024 por AWS con el método de SIM
  (`sentinel2.compuesto_mensual`, el mismo de los compuestos de verano 2026), en `resultados/app/E-E3-2/c/verano_aws/`.
- v3.1 no usa el verano: sin cambios.
- La corrida de v4.0 del lado AWS pasa por `herramientas/e_e3_2_motor.py`, que ejecuta `app/motores/proceso.py` sin cambios
  con la carpeta de verano de AWS primera en la búsqueda de compuestos. Ningún archivo congelado ni del repositorio cambia.
- El guion comprueba en la procedencia de cada SB40 que el lado AWS usó los tres compuestos de `verano_aws` y el lado GEE los
  tres del repositorio; si no, (c) se da por fallida.
- Se informa además la diferencia entre los compuestos de verano de AWS y los de GEE (mediana y p95 de |dif|). Es
  informativa: el criterio 1 sigue midiendo (a) y (b).
