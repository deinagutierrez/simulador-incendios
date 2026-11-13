# F4 — Datos dinámicos: pedido de aprobación

Para leer antes de empezar la fase F4. Cada punto trae una propuesta. Alcanza con contestar "apruebo todo" o con la lista de
números que se quieren cambiar. Los puntos marcados **bloquea** hay que resolverlos antes de escribir código; los demás se
pueden contestar mientras la fase avanza.

Estado del que se parte: F1, F2 y F3 unidas a `main` el 2026-11-12 (`16d199a`). La verificación completa pasa en Linux con
las suites de v3.1 y v4.0, las corridas cortas de los dos motores y 35 pruebas del simulador. La F4 se trabaja en la rama
`f4-datos`.

## 1. Qué pide el plan para F4

Bajar los datos que cambian (pronóstico meteorológico e índices de vegetación) y con ellos armar una corrida "en tiempo real".
Hoy el simulador solo corre eventos con ficha (Las Lagunas 2024 y Las Chacras octubre 2023). Criterio de aceptación
(`00_plan.md` §3): **E-E3-2 evaluado**; sin red, el programa arranca con la caché o con un evento de ejemplo y lo rotula; con
red, el pronóstico llega en menos de 10 s; el verano 2026 queda generado. Esfuerzo estimado en el plan: 8 días.

La F1 dejó pendiente el "evento generado" (D-E3-21): llega en esta fase.

## 2. Comprobaciones hechas hoy (2026-11-12)

| Qué | Resultado |
|---|---|
| Open-Meteo pronóstico, `ecmwf_ifs025`, 5 días atrás y 7 adelante, sin clave | responde: 288 horas, del 07/11 al 18/11 |
| Catálogo Earth Search de Sentinel-2 L2A, del 26/09 al 11/11/2026, sin clave | responde: 44 escenas en las cuatro teselas (19HGD, 19HGE, 20HKJ, 20HKK); la última es del 07/11 |
| Dónde leen los motores la ficha de un evento | `escenarios/<versión>/eventos/<id>.yaml` (`cargar_evento`). Esas carpetas están congeladas |
| Dónde leen los datos de un evento | `datos/inputSimulacion/{meteo, combustibles/<id>, eventos/<id>}` en v3.1; v4.0 los toma de ahí mismo y arma su caché en `datos/procesados/v4.0/<id>` |
| Lo que dejó preparado la F0 | `.gitignore` ya excluye `escenarios/**/RT-*` y `datos/inputSimulacion/**/RT-*`, y la comprobación del congelado ya ignora los nombres que empiezan con `RT-` |
| Verano para un evento de noviembre de 2026 | v4.0 busca enero a marzo de 2026 (`NDVI_NDMI_2026_0{1,2,3}.tif`). Hoy no existen: solo hay 2023 y 2024 |
| Cobertura para 2026 | v4.0 y v3.1 usan la del año anterior: 2025 está en el repositorio |

## 3. Quién y cómo

| N.º | Propuesta | Por qué hace falta aprobarlo | |
|---|---|---|---|
| 1 | **La F4 la hace el frente A** (el usuario, con Claude), como dice el plan | ya coincide con el plan; se pide para dejarlo escrito | |
| 2 | **La rama `f4-datos` se revisa al final**, completa y con las pruebas en verde, igual que la F2 | para saber cuándo se le pide tiempo a quien revisa | |
| 3 | **Quién evalúa E-E3-2.** Propuesta: la otra persona corre el guion de evaluación (`herramientas/e_e3_2.py`, sin pasos manuales). Si no puede, se aplica la misma excepción declarada que en D-E3-13 | la regla dice "escribe uno, evalúa el otro"; D-E3-13 vale solo para E-E3-1 | **bloquea** el cierre de la fase, no el código |
| 4 | **El prerregistro E-E3-2 se completa (quién escribe y quién evalúa) y se etiqueta `prerregistro-E-E3-2` antes de escribir el módulo de índices** | el plan exige la etiqueta antes del código que evalúa. Hoy el archivo existe pero no tiene etiqueta ni nombres | **bloquea** |

## 4. Qué entra en la F4 y qué no

| N.º | Entra | No entra (y cuándo llega) | |
|---|---|---|---|
| 5 | **Pronóstico Open-Meteo** con el cliente de v3.1 (`openmeteo.adquirir`, `tipo: pronostico`): 16 puntos, `ecmwf_ifs025` con `best_match` de respaldo (D-E3-07), 5 días hacia atrás y 7 hacia adelante, control de calidad de v3.1. Se renueva a pedido o cada 6 h; el programa no consulta solo más de una vez por hora | — | **bloquea** |
| 6 | **Índices de Sentinel-2 por AWS**, sin clave: compuesto de ventana de 45 días que terminan el día anterior a la corrida, y compuestos mensuales de verano (enero a marzo) con el método de cada motor (§4.3 del plan) | — | **bloquea** |
| 7 | **Evento generado `RT-<fecha>-<n>`**: con el pronóstico y los índices se escribe una ficha y sus archivos en el formato de un evento con ficha, y los dos motores lo corren con sus cargadores congelados, sin cambios | — | **bloquea** |
| 8 | **Zona de datos en la pantalla**: botones "Actualizar pronóstico" y "Actualizar índices", fecha y fuente de cada uno, aviso de antigüedad, y la opción "Tiempo real" junto a los eventos con ficha | — | |
| 9 | **Sin red**: el programa arranca con la última descarga guardada, con su fecha a la vista. Si no hay ninguna, ofrece los eventos con ficha rotulados **EJEMPLO** | — | |
| 10 | **Carga manual de meteorología**: un CSV en cualquiera de los dos formatos de los motores, con el mismo control de calidad | — | |
| 10b | **Carga manual de índices en TIF** (GeoTIFF). Controles al cargar: grilla exacta del dominio (forma, transformación, CRS), escala int16 × 10000, nodata −32768 y rango −1 a 1. Quien carga **declara** la ventana de fechas y la fórmula del NDMI (B8 o B8A), porque el programa no puede comprobarlas. La corrida queda rotulada "índices cargados a mano" y esos datos van a `corrida.json` | — | |
| 11 | **Google Earth Engine como alternativa** cuando la computadora tiene credenciales (`earthengine authenticate`), con el código que ya existe (`gee_indices.py` de v3.1 para la ventana; el método de `descargar_ndvi_ndmi_gee.py` para los mensuales), corrido en el proceso de datos. Si no hay credenciales, la opción aparece deshabilitada con el motivo. Si E-E3-2 no se cumple, pasa a ser la vía principal, como dice el prerregistro | — | |
| 12 | **Modo escenario**: viento, temperatura, humedad relativa y precipitación constantes puestos a mano, con un evento generado igual que los demás y rotulado "escenario manual" (§4.2 "si falla" (4)). No reemplaza al viento manual durante la corrida, que sigue en F5 | — | |

**Decisión del usuario del 2026-11-12:** los puntos 10, 10b, 11 y 12 entran en la F4, porque son necesarios para la
implementación final. Suman unos 3 días a los 8 del plan (estimación: carga de TIF 1 d, GEE 1,5 d, modo escenario 0,5 d).

## 5. Decisiones técnicas

| N.º | Propuesta | Alternativa descartada | |
|---|---|---|---|
| 13 | **Dónde viven los insumos de una corrida en tiempo real** (decisión que el plan dejó para F0 y que pasó a F4): la ficha va en `escenarios/v3.1/eventos/RT-….yaml` y `escenarios/v4.0/eventos/RT-….yaml`, y los datos en `datos/inputSimulacion/{meteo, combustibles/RT-…, eventos/RT-…}`. Git y la comprobación del congelado ya los ignoran (F0). Los cargadores congelados los encuentran sin redirigir nada | (a) redirigir con `INCENDIOS_SL_ESCENARIOS` e `INCENDIOS_SL_INPUT`: redirigen la carpeta entera, no superponen, así que habría que copiar o enlazar todo el dominio, y en Windows los enlaces piden permisos de administrador; (b) reemplazar `cargar_evento` dentro del proceso motor: funciona, pero es otro punto de enganche que no hace falta | **bloquea** |
| 14 | **El servidor sigue sin cargar ningún motor** (D-E3-19). La preparación que usa código de v3.1 (cliente de Open-Meteo, mapa de 7 clases, humedad muerta) corre en un proceso aparte con el `PYTHONPATH` de v3.1, como los procesos motor. v4.0 arma sus propios insumos al correr, como ya hace | importar el cliente de v3.1 en el servidor: rompe la regla de un proceso por motor | **bloquea** |
| 15 | **El módulo de Sentinel-2 es código nuevo en `app/datos/`**: búsqueda en el catálogo con `requests`, lectura de las bandas remotas con `rasterio` (lee solo la ventana del dominio y el nivel de resolución que hace falta), máscara SCL, reproyección de las dos zonas UTM a EPSG:5345 y mediana. Sale en el mismo formato que hoy: int16 × 10000, nodata −32768 | `pystac-client` o `stackstac`: bibliotecas nuevas que no hacen falta | |
| 16 | **Compuesto de ventana para v3.1**: se escribe a 20 m en la grilla de índices del dominio (`grilla_indices`), igual que la salida de `gee_indices.py`. El promedio a 30 m lo hace la función de v3.1 (`generar_mapa_combustibles`), que también escribe `ndvi_30m` y `ndmi_30m`. v4.0 toma esos mismos `ndvi_30m` y `ndmi_30m` como `indices_mes_evento`, como hace con los eventos con ficha | escribir directo a 30 m: se saltearía el paso de v3.1 y el resultado dejaría de ser el de la versión congelada | |
| 17 | **Verano 2026**: se generan `NDVI_NDMI_2026_01.tif`, `_02` y `_03` con el método de SIM (NDMI con B8A, directo a 30 m, vecino más cercano) y **se suben al repositorio** en `datos/inputSimulacion/sim_v4/dinamicos/indices/`, como los de 2023 y 2024 (unos 9 MB cada uno). Así un clon nuevo no tiene que bajarlos | dejarlos solo en la caché de cada computadora: cada clon tendría que bajar unos 3 GB de escenas para generarlos | |
| 18 | **Caché en `datos/procesados/app/`** con un JSON de procedencia por producto: fuente, parámetros, fecha de descarga, lista de escenas y sha256. Las escenas ya bajadas no se vuelven a pedir | — | |
| 19 | **La corrida guarda la procedencia de sus insumos** en `corrida.json`, en el bloque `insumos` del Anexo C (fuente, modelo, ventana, escenas, sha256, año de cobertura). El contrato pasa a 1.4 | — | |
| 20 | **La escala de reflectancia se resuelve con números antes de medir**, como manda E-E3-2: se prueban las dos lecturas (con y sin restar 0,1) contra el compuesto de GEE de Las Lagunas 2024 y se anota la elegida antes de mirar las partes (b) y (c) | — | |
| 21 | **La vía AWS queda deshabilitada hasta que E-E3-2 se cumpla.** Mientras tanto, la pantalla la ofrece rotulada "en prueba". Si E-E3-2 no se cumple, se revisan máscara y escala una vez, por escrito, y si sigue sin cumplirse se aplica lo que dice el prerregistro (GEE obligatorio) | habilitarla sin la prueba | **bloquea** |
| 22 | **Sin bibliotecas nuevas.** `requests` y `rasterio` ya están en `requirements.txt`. Si hiciera falta otra, se pregunta antes | — | |

## 6. Pruebas y verificación

| N.º | Propuesta | |
|---|---|---|
| 23 | **Pruebas sin red**: respuestas de Open-Meteo y del catálogo guardadas como archivos de muestra, y teselas chicas sintéticas para la lectura, la máscara, el mosaico de las dos zonas UTM y la alineación a la grilla. Rechazo de archivos mal formados. Se suman a `test/app/` y a la integración continua | |
| 24 | **Una prueba con red, aparte y opcional** (`--red`): baja el pronóstico de hoy, arma un evento generado y lo corre 6 h con cada motor. No entra en la integración continua para que no falle cuando un servicio externo esté caído | |
| 25 | **E-E3-2 con un guion** (`herramientas/e_e3_2.py`) que reconstruye por AWS la ventana de Las Lagunas 2024 y septiembre de 2024, compara con los productos de GEE del repositorio y corre las dos corridas de 48 h por motor. Guarda el resultado con el cambio de git y los sha256 | |
| 26 | **Medición del tiempo del pronóstico** (criterio de menos de 10 s) y del tiempo de una actualización de índices, en esta computadora | |

## 7. Lo que no bloquea la F4 pero sigue pendiente

- Protección de la rama `main`: el 12/11 se pudo empujar directo a `main`, así que hoy no está protegida.
- Licencia del código: el repositorio es público y no tiene archivo de licencia.
- Aprobación del contrato 1.3 (F3) por la otra persona (D-E3-22).
- Quién evalúa E-E3-3 y E-E3-4.

## 8. Cómo contestar

"Apruebo todo", o los números con lo que se quiere distinto. Los que bloquean el inicio son **4, 5, 6, 7, 13, 14 y 21**; el
**3** bloquea el cierre. Lo que se apruebe se anota en `decisiones.md` con la fecha y quién lo aprobó.
