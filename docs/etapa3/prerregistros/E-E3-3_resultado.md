# Resultado del prerregistro E-E3-3 — Tiempo de cómputo y memoria

Medición generada por `herramientas/e_e3_3.py`. Prerregistro: `E-E3-3_rendimiento.md` (etiqueta `prerregistro-E-E3-3`, líneas cambiadas desde la etiqueta: 3). Escribe deinagutierrez; evalúa LisandroV2002 (D-E3-30).

## Veredicto

**Medición: completa.** Pares hechos: 7 de 7.

| Meta | Valor | Resultado |
|---|---|---|
| v3.1 | ≤ 0,5 s por hora simulada (mediana de cada par) | **se cumple** |
| v4.0 con unas 30.000 ha | ≤ 3 s por hora simulada | **no evaluable con el diseño**: ningún escenario de E-E3-1 llega a esa superficie con v4.0 (máximo medido: 12839.31 ha) |
| Modo "ambos" | dentro de 16 GB | **se cumple** |

## Quién y con qué

| | |
|---|---|
| Fecha | 2026-11-16 14:48 |
| Evaluó | LisandroV2002 |
| Código | cambio de git `d4118d82d039` (rama `f7-entrega`); código sin registrar: 0 archivo(s) |
| Motores congelados | sha256 del conjunto `2b32757194d2510bcbc680056f803694be064fc968e35de9c1ab579c10621106`; intactos antes: sí; después: sí |
| Alcance | 7 pares × 3 repeticiones; modo ambos 48 h por el servidor y con dos procesos; más la corrida fuera del prerregistro |

## Ficha de la máquina

| | |
|---|---|
| Sistema | Windows-11-10.0.26300-SP0 |
| Procesador | AMD Ryzen 5 8600G w/ Radeon 760M Graphics (6 núcleos, 12 hilos; 4351 MHz; AVX-512: sí) |
| Memoria | 31,7 GB |
| Disco del repositorio | 830 GB, 281 GB libres |
| Batería | sin batería |
| Versiones | python 3.14.2, numpy 2.5.2, numba 0.68.0, rasterio 1.5.1, psutil 7.2.2, uvicorn 0.54.0, fastapi 0.143.1 |
| Memoria pico por proceso | `peak_wset` |
| Carga de fondo al empezar | CPU 5 %, carga media [0.0, 0.0, 0.0], 20,3 GB disponibles, 195 procesos |
| Carga de fondo al terminar | CPU 5 %, carga media [0.01, 0.04, 0.03], 20,1 GB disponibles, 200 procesos |

## Por par escenario–motor (3 repeticiones: mediana y rango)

| Escenario | Motor | h | ha | s/h simulada | s/h en frío | s cómputo | MB pico | RSS máx. muestreado (MB) | Hasta `listo`: frío / caliente (s) | Hasta la 1.ª hora: frío / caliente (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| aguada_36h | v4.0 | 36 | 1.348 | 0,204 (0,204–0,205) | 0,204 | 7,4 (7,3–7,4) | 223 (222–223) | 227 (226–227) | 2,5 / 2,4 (2,4–2,4) | 2,5 / 2,5 (2,5–2,5) |
| laslagunas_48h | v4.0 | 48 | 12.839 | 0,981 (0,976–0,983) | 0,976 | 47,1 (46,8–47,2) | 526 (518–528) | 520 (509–523) | 3,4 / 3,4 (3,4–3,5) | 3,7 / 3,7 (3,7–3,7) |
| laslagunas_48h | v3.1-libre | 48 | 34.793 | 0,315 (0,314–0,362) | 0,362 | 15,1 (15,1–17,4) | 872 (872–936) | 876 (874–940) | 3,0 / 3,0 (3,0–3,0) | 5,9 / 3,5 (3,5–3,5) |
| laslagunas_48h | v3.1-librev2 | 48 | 32.915 | 0,316 (0,316–0,363) | 0,363 | 15,2 (15,2–17,4) | 884 (884–948) | 886 (886–952) | 3,2 / 3,2 (3,2–3,2) | 6,0 / 3,7 (3,7–3,7) |
| chacrasoct_72h | v4.0 | 72 | 2.356 | 0,375 (0,365–0,409) | 0,409 | 27,0 (26,3–29,4) | 495 (490–524) | 495 (480–502) | 6,3 / 3,3 (3,3–3,3) | 6,6 / 3,5 (3,5–3,5) |
| chacrasoct_72h | v3.1-libre | 72 | 1.526 | 0,297 (0,295–0,350) | 0,350 | 13,3 (13,3–15,8) | 864 (863–928) | 869 (868–933) | 3,1 / 3,0 (3,0–3,1) | 6,0 / 3,6 (3,5–3,6) |
| chacrasoct_72h | v3.1-librev2 | 72 | 3.065 | 0,300 (0,300–0,351) | 0,351 | 13,8 (13,8–16,2) | 877 (876–941) | 881 (881–945) | 3,2 / 3,2 (3,2–3,2) | 6,0 / 3,7 (3,7–3,7) |

## Modo "ambos" (Las Lagunas 2024, 48 h; v4.0 y v3.1 librev2)

| Forma | Motor | s/h simulada | s cómputo | MB pico (`final`) | RSS máx. del árbol (MB) | Hasta `listo` (s) | Hasta la 1.ª hora (s) | Fin (s) |
|---|---|---|---|---|---|---|---|---|
| servidor | v4.0 | 1,103 | 53,0 | 520 | 525 | 3,6 | 3,9 | 53,2 |
| servidor | v3.1-librev2 | 0,440 | 21,1 | 884 | 888 | 3,4 | 4,1 | 21,4 |
| dos_procesos | v4.0 | 1,099 | 52,7 | 535 | 510 | 3,7 | 4,0 | 53,0 |
| dos_procesos | v3.1-librev2 | 0,438 | 21,0 | 884 | 888 | 3,4 | 4,1 | 53,0 |

| Forma | RSS máx. total muestreado (MB) | Suma de picos individuales (MB, cota superior) | Muestras | Dentro de 16 GB |
|---|---|---|---|---|
| servidor | 1.364 | 1.404 | 202 | sí |
| dos_procesos | 1.356 | 1.419 | 201 | sí |

La serie del RSS (cada 0,25 s) está en el JSON, en `ambos[].memoria.serie`.

## v4.0: segundos por hora contra superficie

| Escenario | ha | s/h simulada (mediana) |
|---|---|---|
| aguada_36h | 1.348 | 0,204 |
| laslagunas_48h | 12.839 | 0,981 |
| chacrasoct_72h | 2.356 | 0,375 |

## Fuera del prerregistro: Las Chacras octubre 2023, v4.0 libre, 141 h

> **Fuera del prerregistro.** Se agrega porque la meta de v4.0 con unas 30.000 ha no se puede evaluar con el diseño (D-E3-30, punto 8). Una sola corrida, en caliente.

Definición: `{"evento": "SL-2023-CHACRASOCT", "hipotesis": 4, "ignicion": "alt4", "horas": 141, "variante": "libre", "parar_en_cicatriz": "off", "validar": false, "figuras": false}`. Referencia: docs/v4.0/31 §7.2: v4.0 libre, alt4, 06 UTC, sin parada, 141 h, 29.319 ha; 2,7 s por hora en el antecedente del prerregistro (corrida offline con figuras).

| ha al final | Horas simuladas | s cómputo | s/h simulada | MB pico | RSS máx. muestreado (MB) | Hasta `listo` (s) | Hasta la 1.ª hora (s) | Motivo de fin |
|---|---|---|---|---|---|---|---|---|
| 29.319 | 141,0 | 108,5 | 0,770 | 539 | 544 | 3,3 | 3,5 | horizonte |

## Lo que hay que saber para leerlo

- Memoria pico por proceso (aviso `final`): en Windows es `peak_wset` (conjunto de trabajo pico) y en Linux `ru_maxrss` (RSS máximo). **No son la misma métrica** y no se comparan entre sistemas; en E-E3-1, Linux dio 15–30 % más que Windows en las mismas corridas. Esta máquina usa `peak_wset`.
- RSS muestreado: psutil cada 0,25 s, sumando el proceso y sus descendientes. Es la misma medida en los dos sistemas (en Windows psutil informa el conjunto de trabajo como RSS), pero puede perder un pico más corto que el intervalo: por eso se informa además la suma de los picos individuales, que es una cota superior del total del modo "ambos".
- Segundos de cómputo (`s_computo`): los cuenta el proceso motor desde que crea su control, sin el tiempo en pausa; no incluye el arranque de Python ni las importaciones. Sí incluye la compilación de numba de v3.1 en la corrida fría. Por eso se informa también el reloj de pared desde `Popen` (o desde el POST) hasta `listo` y hasta la primera hora.
- Frío y caliente: la primera repetición de cada par usa una carpeta de caché de numba nueva y vacía (`NUMBA_CACHE_DIR`); las otras dos, la misma carpeta ya llena. No se vacía la caché de archivos del sistema operativo: la primera corrida de cada par puede leer los insumos del disco y las demás de la memoria. v4.0 no usa numba.
- La meta de v3.1 se compara con la mediana de las 3 repeticiones de cada par, y la de "ambos" con el máximo muestreado (fijado por quien escribe antes de ver resultados).
- Modo "ambos" por el servidor: los instantes de `listo`, primera hora y `final` los anota el servidor al recibir el aviso (se envuelve el método del gestor en esta instancia, sin cambiar el código); van desde el POST, que también incluye crear las dos carpetas. Con dos procesos lanzados a la vez, cada tiempo va desde su `Popen`.
- Las corridas son las de E-E3-1 (`herramientas/e_e3_1.py`: Las Lagunas 2023 aguada 36 h en v4.0; Las Lagunas 2024 48 h y Las Chacras octubre 2023 72 h con los tres motores), con la configuración por defecto del simulador (v4.0 variante barreras sin parada, D-E3-01).
- La meta de v4.0 con unas 30.000 ha **no se puede evaluar con el diseño del prerregistro**: ninguno de esos escenarios llega a esa superficie con v4.0. La corrida de Las Chacras v4.0 libre de 141 h se agrega aparte y va rotulada **fuera del prerregistro** (D-E3-30, punto 8): no cambia el diseño ni el criterio.
- Es una medición en una sola computadora: el resultado vale para esta máquina con la carga de fondo anotada. En la integración continua E-E3-3 es solo informativo (máquinas compartidas, con ruido).

## Cómo repetirlo

```
python herramientas/e_e3_3.py --evaluador NOMBRE
```
