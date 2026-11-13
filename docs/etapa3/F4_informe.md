# F4 — Datos dinámicos: informe

Fecha: 2026-11-13 · Rama `f4-datos` · Pedido aprobado: `F4_pedido_de_aprobacion.md` (D-E3-24 a D-E3-26).
Hecho por el frente A (el usuario, con Claude). Para revisar: la otra persona, con la rama completa.

## 1. Qué se pidió y qué quedó

| Criterio de aceptación del plan (§3) | Estado |
|---|---|
| E-E3-2 evaluado | **pendiente de la otra persona** (D-E3-25). El guion está listo: `herramientas/e_e3_2.py --evaluador LisandroV2002` (§5.1 resuelto con la opción A) |
| Sin red, el programa arranca con la caché o con un evento de ejemplo y lo rotula | hecho: las tomas guardadas se ofrecen con su fecha y antigüedad; los eventos con ficha van rotulados **EJEMPLO** en la pantalla y en `corrida.json` (`advertencias`). Las 94 pruebas de `test/app` pasan sin red (comprobado con la red cortada) |
| Con red, pronóstico en menos de 10 s | hecho: **1,4 a 2,0 s** (16 puntos en paralelo). Con el cliente de v3.1 tal cual tardaba 12 s (§4) |
| Verano 2026 generado | hecho: `NDVI_NDMI_2026_01`, `_02` y `_03` en `datos/inputSimulacion/sim_v4/dinamicos/indices/`, con su `.json` de procedencia |

Punto por punto del pedido:

| N.º | Qué | Estado |
|---|---|---|
| 5 | Pronóstico Open-Meteo `ecmwf_ifs025` con respaldo `best_match`, 16 puntos, 5 días atrás y 7 adelante, control de calidad de v3.1 | hecho. Se renueva a pedido; la pantalla avisa cuando tiene más de 6 h. No hay consultas automáticas |
| 6 | Índices de Sentinel-2 por AWS: ventana de 45 días hasta el día anterior (v3.1) y mensuales de verano (SIM) | hecho (`app/datos/sentinel2.py`) |
| 7 | Evento generado `RT-<AAAAMMDD>-<n>` corrido por los dos motores sin cambios | hecho (`app/datos/evento_rt.py`); probado con red y sin red, 6 h por motor |
| 8 | Zona de datos en la pantalla | hecho (`app/web/`); falta probar en vivo un trabajo completo en el navegador (§6) |
| 9 | Sin red: caché o ejemplos rotulados | hecho |
| 10 | Carga manual de meteorología (CSV de v3.x o v4.0) | hecho |
| 10b | Carga manual de índices en TIF con controles y lo declarado | hecho |
| 11 | Google Earth Engine como alternativa | hecho para el compuesto de ventana (código de v3.1); **no** para los mensuales de verano (§6). En esta computadora no está instalada la biblioteca: la opción aparece deshabilitada con el motivo |
| 12 | Modo escenario con valores fijos | hecho |
| 13 | Insumos `RT-…` en `escenarios/<versión>/eventos/` y `datos/inputSimulacion/` | hecho; git y el congelado los ignoran (244 archivos intactos) |
| 14 | El servidor no carga motores; lo de v3.1 corre en un proceso de datos | hecho; una prueba comprueba que el servidor no importa `incendios_sl` |
| 15, 22 | Módulo nuevo sin bibliotecas nuevas | hecho (`requests` y `rasterio`). Las subidas de archivos van como cuerpo crudo para no sumar `python-multipart` |
| 16 | Ventana a 20 m en la grilla de índices; el paso a 30 m lo hace la función de v3.1 | hecho |
| 17 | Verano 2026 al repositorio | hecho (27 MB) |
| 18, 19 | Caché con procedencia; `insumos` en `corrida.json`; contrato 1.4 | hecho; `contrato_servidor_motor.md` pasa a 1.4 |
| 20 | Escala de reflectancia elegida antes de medir | hecho: `prerregistros/E-E3-2_escala.md` (DN/10000, sin restar 0,1) |
| 21 | AWS rotulado "en prueba" hasta E-E3-2 | hecho (`indices.AWS_EN_PRUEBA`) |
| 23 | Pruebas sin red | hecho: `test/app/test_datos.py` (34) y `test/app/test_servidor_datos.py` (25) |
| 24 | Prueba con red opcional | hecho: `herramientas/probar_red.py` (no entra en la integración continua) |
| 25 | Guion de E-E3-2 | hecho: `herramientas/e_e3_2.py`; solo se probó con `--solo-revisar` y con datos falsos, para no ver las cifras antes que quien evalúa |
| 26 | Mediciones de tiempo | §3 |

## 2. Cómo se usa

En la pantalla, panel **Datos**: "Actualizar pronóstico", "Actualizar índices (AWS)" o "(Earth Engine)", o cargar un CSV, dos
TIF o un escenario; después "Armar evento en tiempo real". El evento aparece en el selector, separado de los ejemplos, con sus
rótulos. Para correrlo hay que marcar la ignición en el mapa. Desde la línea de comandos: `python herramientas/probar_red.py`
hace la cadena completa.

## 3. Mediciones (esta computadora, Linux, 2026-11-13)

| Paso | Tiempo |
|---|---|
| Pronóstico, 16 puntos, 294 horas | 1,4 a 2,0 s (12 s con `adquirir` de v3.1, pedidos de a uno) |
| Índices AWS, 45 días, 29 escenas, 9 fechas | 63 s la primera vez; 8 s con las escenas en la caché |
| Índices AWS, ventana de Las Lagunas 2024 (32 escenas, 8 fechas) | 52 s |
| Compuesto mensual de verano | 28 a 44 s por mes (17 a 23 escenas) |
| Armar el evento `RT-…` (mapa de 7 clases y humedad de v3.1) | 0,7 a 1,1 s |
| Corrida de 6 h del evento generado | v3.1 librev2: 4,5 s; v4.0: 6 a 7 s (incluye armar su SB40) |

## 4. Decisiones tomadas al implementar (a revisar)

1. **Pronóstico con las funciones de v3.1 en paralelo** (`meteo.adquirir_en_paralelo`): mismo pedido por punto
   (`_consultar`), mismo control de calidad, misma serie del dominio y mismos archivos que `openmeteo.adquirir`, pero los 16
   pedidos a la vez. Es la única forma de cumplir los 10 s sin tocar v3.1.
2. **Teselas con más de 80 % de nubes se descartan** (lo dice el plan §4.3). GEE no hacía ese filtro: de las 40 escenas de
   Las Lagunas 2024 quedan 32. Es una diferencia de método que E-E3-2 mide.
3. **Bandas de 10 m leídas desde el nivel de 20 m del COG** (B4 y B8), como dice el plan. En el mensual se pasa de ahí a
   30 m por vecino más cercano; GEE leía 10 m.
4. **Identificadores**: toma de pronóstico `M-<hora>-pronostico` (una por hora; la misma hora se reemplaza), escenario y CSV con
   sufijo propio, índices `I-<último día>-<vía>[-<sha>]`. Un evento `RT-…` copia los datos y guarda sus sha256, así que
   reemplazar una toma no lo altera.
5. **Avisos de antigüedad**: pronóstico desde 6 h, índices desde 10 días (dos pasadas de Sentinel-2).
6. **Eventos `RT-…` a medio armar** (proceso cortado) se barren al arrancar el servidor.
7. **Earth Engine sigue opcional**: la biblioteca `earthengine-api` no se agrega a `requirements.txt` (ya estaba como
   comentario); sin ella o sin credenciales, la opción aparece deshabilitada con el motivo.
8. **Regla del verano** para un evento de enero a marzo: v4.0 usa el verano del año anterior (es la regla de
   `eventos.indices_verano`; `evento_rt` la repite para avisar si faltan compuestos).

## 5. Para decidir antes de evaluar E-E3-2

### 5.1 La parte (c) no mide el efecto de AWS en el combustible de v4.0

El SB40 de v4.0 (regla 3.3b) se arma con los **compuestos de verano** (enero a marzo), no con el compuesto de ventana. En el
diseño de (c), los dos eventos de Las Lagunas 2024 usan el mismo verano 2024, que es de GEE. Así v4.0 solo cambia
`indices_mes_evento` (humedad viva y curado), y la fracción de celdas SB40 que cambian de clase va a dar 0 % por construcción.
En la operación real, en cambio, el verano 2026 se hizo por AWS.

**Resuelto (D-E3-27, opción A):** el guion genera por AWS enero a marzo de 2024 y el lado AWS de v4.0 los usa, a través de
`herramientas/e_e3_2_motor.py`, sin tocar los compuestos del repositorio. La procedencia del SB40 lo comprueba. Detalle en
`prerregistros/E-E3-2_aclaracion_c.md`. Probado con datos de 2026 (no los de la evaluación): v4.0 tomó los compuestos de la
carpeta indicada.

### 5.2 Denominador del criterio 2

El guion cuenta el cambio de clase sobre todas las celdas del dominio con dato en los dos mapas, e informa además la fracción
sobre celdas combustibles (SB40 > 100). Lo eligió quien escribe, antes de ver resultados. Conviene que quien evalúa lo confirme.

## 6. Lo que queda

- **E-E3-2**: que LisandroV2002 corra `python herramientas/e_e3_2.py --evaluador LisandroV2002`. Con el
  resultado, `AWS_EN_PRUEBA` pasa a `False` o GEE pasa a obligatorio (prerregistro).
- Pantalla: probar en Chrome, Edge y Firefox el ciclo en vivo de un trabajo de datos, la subida de CSV y TIF y el borrado de un
  evento `RT-…` (se probó la carga de la página en Chromium sin ventana, sin errores en la consola).
- Mensuales de verano por Earth Engine (punto 11): solo existe la ventana. Hace falta solo si E-E3-2 no se cumple.
- Aprobación del contrato 1.4 por la otra persona.

## 7. Verificación

`./probar.sh`: congelado intacto (244 archivos), v3.1 69 pruebas, v4.0 130, corridas cortas de los dos motores, `test/app`
94 pasan y 2 se omiten: "Todo funciona". `herramientas/probar_red.py`: la cadena completa con red funciona.
