# Prerregistro E-E3-2 — Los índices por AWS equivalen a los de Google Earth Engine

Escrito el 2026-11-10, antes de escribir el módulo de índices. Se congela con la etiqueta `prerregistro-E-E3-2`.
Escribe: deinagutierrez · Evalúa (la otra persona): LisandroV2002 (D-E3-25, 2026-11-13). El diseño y el criterio no cambian
respecto de la etiqueta; solo se agregan los nombres.

## Pregunta
¿NDVI y NDMI calculados desde Sentinel-2 L2A en AWS (catálogo Earth Search, máscara de nubes SCL) reemplazan a los que el
proyecto calculó con Google Earth Engine (Cloud Score+ ≥ 0,6) sin cambiar el resultado del modelo?

## Diseño
| Parte | Qué se reconstruye por AWS | Contra qué se compara |
|---|---|---|
| (a) Compuesto de ventana | Las Lagunas 2024, ventana 30/07 a 17/09/2024 (las 40 escenas que devuelve el catálogo), mediana, NDVI con B8 y B4, NDMI con B8 y B11, lectura a 20 m y promedio a 30 m | `datos/inputSimulacion/combustibles/SL-2024-LASLAGUNAS/ndvi_30m_*.tif` y `ndmi_30m_*.tif` |
| (b) Compuesto mensual | septiembre de 2024, mediana, NDMI con B8A y B11, directo a 30 m | `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_2024_09.tif` |
| (c) Efecto en el modelo | mapa de combustible de cada motor y corrida de Las Lagunas 2024 de 48 h con unos y otros índices, v4.0 y v3.1 librev2 | las mismas corridas con los índices de GEE |

Antes de medir se resuelve con números la escala de reflectancia: los metadatos de las escenas dicen a la vez "corrección ya
aplicada" y "restar 0,1". Se prueba cada lectura contra (a) y se elige la que da el menor error; esa elección se anota antes de
mirar (b) y (c).

## Métricas
Diferencia absoluta mediana y percentil 95 de NDVI y de NDMI sobre celdas válidas en los dos productos; fracción de celdas sin
dato; fracción de celdas que cambian de clase de combustible (SB40 en v4.0, 7 clases en v3.1); IoU entre las huellas de las dos
corridas a las 24 h y a las 48 h; diferencia de superficie.

## Criterio, fijado antes de correr (aprobado por el usuario el 2026-11-10)
La vía AWS se habilita como principal si se cumplen las tres:
1. diferencia absoluta mediana ≤ 0,02 en NDVI y en NDMI, en (a) y en (b);
2. menos del 3 % de las celdas cambia de clase de combustible, en cada motor;
3. IoU entre huellas ≥ 0,95 a las 48 h, en cada motor.

Todo se informa, se cumpla o no.

## Si no se cumple
Se revisan la máscara de nubes y la escala, una sola vez y dejándolo escrito, y se repite. Si sigue sin cumplirse, GEE pasa a
ser obligatorio para los índices y se declara en la guía de uso.

## Límites declarados
Un solo evento y una sola época del año (fin de invierno, año seco). Los umbrales son juicio propio, sin antecedente en el
proyecto. Dos zonas UTM en el mosaico. La comparación (c) usa un evento visto.
