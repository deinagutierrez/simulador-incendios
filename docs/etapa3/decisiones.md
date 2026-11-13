# Decisiones de la Etapa 3

Registro de decisiones del simulador interactivo. Cada entrada: qué se decidió, quién y cuándo, y qué se descartó.
El detalle y la justificación están en `00_plan.md` §8. Una decisión se cambia con una entrada nueva, nunca editando la vieja.

## 2026-11-10 — Aprobación del plan

El usuario aprobó las doce decisiones del plan, con dos correcciones (D-E3-06 y D-E3-09) y dos confirmaciones (repositorio y
datos).

| Código | Decisión | Estado |
|---|---|---|
| D-E3-01 | Motores y configuraciones congeladas: v4.0 `modelo_v3` variante `barreras` (línea principal); v3.1 `modelo_v2` librev2 y `modelo_v1` libre (control). Congelados con `congelado.json`: 244 archivos, sha256 del conjunto `2b32757194d2510bcbc680056f803694be064fc968e35de9c1ab579c10621106` | aprobada |
| D-E3-02 | Programa Python local con interfaz en el navegador; un proceso por motor; servidor solo en `127.0.0.1`. Descartado: HTML único con los motores traducidos a JavaScript | aprobada |
| D-E3-03 | v3.1 con la biblioteca WindNinja completa y velocidad escalar; v4.0 con serie y factor topográfico. No hace falta WindNinja instalado | aprobada |
| D-E3-04 | Pausa en hora en punto; intervenciones solo en pausa; cortafuegos recortados a celdas no afectadas | aprobada |
| D-E3-05 | Sin promedio entre motores; envolvente y aviso de discrepancia (IoU entre huellas menor que 0,5 a las 24 h) | aprobada |
| D-E3-06 | Solo computadoras y navegador de escritorio, **con Windows o con Linux** | aprobada, **corregida por el usuario**: se agrega Linux |
| D-E3-07 | Pronóstico Open-Meteo `ecmwf_ifs025` con `best_match` de respaldo, 16 puntos, 5 días hacia atrás | aprobada |
| D-E3-08 | Índices por Sentinel-2 L2A en AWS sin token como vía principal; compuesto de ventana de 45 días y mensuales de verano; GEE opcional | aprobada |
| D-E3-09 | **No hay v5.0.** La última versión del modelo es la v4.0. Lo nuevo vive en GitHub como `app/`, sin número de versión del modelo. En esta etapa no se abren los eventos no vistos X-49 | aprobada, **corregida por el usuario**: se elimina el nombre "v5.0" |
| D-E3-10 | Repositorio nuevo `deinagutierrez/simulador-incendios`, público, como único lugar de trabajo y distribución, en lugar de Drive y del repositorio viejo `gvcosta/Gemelos_Digitales_Incendios_UNSL`. Datos mínimos dentro, viento partido en cuatro, sin Git LFS | aprobada |
| D-E3-11 | Todos los datos se pueden publicar (confirmado por el usuario): red MT de EDESAL, cuarteles, registros del SNMF, viviendas y caminos. Fuentes y atribuciones en `DATOS.md` | aprobada. **Pendiente: licencia del código** |
| D-E3-12 | Trabajo de dos personas en dos frentes (motores y datos; servidor e interfaz), `main` protegida, revisión cruzada, prerregistros etiquetados en git | aprobada. **Pendiente: usuario de GitHub de la segunda persona y protección de `main`** |

También aprobado: los umbrales propuestos para el prerregistro E-E3-2 (índices por AWS contra GEE).

## Pendientes que solo pueden resolver las personas del proyecto

1. Licencia del código (el repositorio no tiene archivo `LICENSE`).
2. Nombre y correo de git para registrar los cambios, y permiso de escritura en el repositorio.
3. Protección de la rama `main` y revisión obligatoria (ajustes del repositorio, los hace la dueña).
4. Quién toma cada frente y quién escribe y quién evalúa cada prerregistro.
5. Si se traen a este repositorio `reporte_avance.md` y `decisiones.md` de las etapas anteriores.

## 2026-11-11 — Quién evalúa el prerregistro E-E3-1

| Código | Decisión | Estado |
|---|---|---|
| D-E3-13 | La evaluación formal de E-E3-1 la hace el mismo frente que escribió `app/motores/` (el usuario, con Claude), porque la otra persona no puede hacerla. Es una **desviación declarada** de la regla "escribe una persona, evalúa la otra" de D-E3-12, y vale solo para E-E3-1. Lo que la compensa: el criterio es binario y estaba fijado y etiquetado antes de escribir el código (0 celdas distintas); la evaluación es un guion sin pasos manuales (`herramientas/e_e3_1.py`) que cualquiera puede repetir; el resultado se guarda con el cambio de git, el sha256 del congelado y los sha256 de los datos usados. La otra persona puede repetirla cuando pueda, y ese resultado reemplaza a este | decidida por el usuario |
| D-E3-14 | Los tres pares de Las Chacras octubre 2023 se corren con los datos del evento tomados de la copia de trabajo anterior (Drive), copiados a `datos/inputSimulacion/` del clon sin registrarlos en git, porque el paquete de datos históricos todavía no existe. Los archivos se listan con su sha256 en el resultado. Descartado: esperar al paquete, que dejaba la evaluación incompleta | decidida por Claude, **a confirmar por el usuario** |

## 2026-11-11 — Los datos de Las Chacras entran al repositorio

| Código | Decisión | Estado |
|---|---|---|
| D-E3-15 | Los datos del evento Las Chacras octubre 2023 (15 archivos, 21 MB) se registran en el repositorio, en `datos/inputSimulacion/`. **Reemplaza a D-E3-14.** Son los mismos archivos de la evaluación formal de E-E3-1 (mismo sha256 del conjunto, `52d145b3c3df…`), así que cualquiera que clone puede repetir los siete pares. El repositorio pasa de 476 a 497 MB. Es uno de los cinco eventos no vistos (X-49); tenerlo en el repositorio no lo abre de nuevo: E-E3-1 compara el programa contra el motor, sin mirar la cicatriz. El resto de los eventos históricos sigue yendo en el paquete aparte | decidida por el usuario |

## 2026-11-11 — Aprobaciones para empezar la F2

La otra persona del proyecto leyó `F2_pedido_de_aprobacion.md` y lo aprobó completo; lo informó el usuario en la sesión de
trabajo. También aprobó el contrato servidor–motor 1.1.

| Código | Decisión | Estado |
|---|---|---|
| D-E3-16 | Contrato servidor–motor **1.1 aprobado** por las dos personas | aprobada |
| D-E3-17 | **La F2 (servidor) la hace el frente que hizo la F1** (el usuario, con Claude), y también el motor simulado. Cambia el reparto de D-E3-12, que se la daba al frente B. La F2 se revisa al final, con la rama completa | aprobada |
| D-E3-18 | **La rama `f1-procesos-motor` se une a `main` sin revisión previa**, autorizado por la otra persona. La F2 se trabaja en la rama `f2-servidor` | aprobada |
| D-E3-19 | **Alcance y decisiones técnicas de la F2**: los puntos 6 a 23 de `F2_pedido_de_aprobacion.md` (solo servidor y página mínima; datos de un evento con ficha; modo "ambos"; código en `app/servidor/`; avance por canal de una sola vía; `corrida.json` según el contrato 1.1; dos corridas a la vez como máximo; corridas interrumpidas no se retoman; el servidor rechaza pedidos que no vengan de su página; sin bibliotecas nuevas; pruebas con motor simulado y pocas con motores reales; repetición de los siete pares de E-E3-1 por el servidor al cerrar) | aprobada |
| D-E3-20 | **El programa corre el punto de ignición a la celda combustible más cercana al clic antes de pasárselo al motor** (punto 24 del pedido). El contrato pasa a 1.2 | aprobada |
| D-E3-21 | **La F1 se cerró sin "evento generado"** (datos bajados en el momento). Esa parte pasa a la F4, porque depende de la descarga de pronóstico e índices | informada en el pedido de la F2, sin objeción |

Siguen pendientes: protección de `main`, licencia del código, y quién evalúa los prerregistros E-E3-2, E-E3-3 y E-E3-4.

## 2026-11-11 — La F3 (pantalla)

| Código | Decisión | Estado |
|---|---|---|
| D-E3-22 | **La F3 (pantalla) la hace el mismo frente que la F1 y la F2**, por pedido del usuario. Cambia otra vez el reparto de D-E3-12. A diferencia de la F2, no tuvo pedido de aprobación previo: las decisiones de diseño están en `F3_informe.md` §5 y el contrato 1.3 queda **pendiente de aprobación de la otra persona** | decidida por el usuario; diseño a revisar |
| D-E3-23 | **Leaflet 1.9.4 se copia dentro del repositorio** (`app/web/vendor/leaflet/`, licencia BSD de 2 cláusulas) para que la pantalla funcione sin internet. Es la biblioteca que nombra el plan (§2.1) | decidida por Claude, a revisar |

## 2026-11-13 — Aprobaciones para empezar la F4

El usuario aprobó `F4_pedido_de_aprobacion.md` completo, con los cambios del 12/11 (puntos 10b, 11 y 12 dentro de la fase).

| Código | Decisión | Estado |
|---|---|---|
| D-E3-24 | **Alcance y decisiones técnicas de la F4**: puntos 1 a 26 de `F4_pedido_de_aprobacion.md`. Entre ellos: los insumos de una corrida en tiempo real viven en `escenarios/<versión>/eventos/RT-….yaml` y `datos/inputSimulacion/…/RT-…` (punto 13, la decisión que el plan dejó abierta en §2.2); la preparación con código de v3.1 corre en un proceso aparte (14); la vía AWS queda rotulada "en prueba" hasta que E-E3-2 se cumpla (21); verano 2026 al repositorio (17) | aprobada |
| D-E3-25 | **E-E3-2: escribe el usuario (deinagutierrez) y evalúa la otra persona (LisandroV2002)**. Vuelve a la regla de D-E3-12. El prerregistro ya estaba etiquetado desde la F0 (`prerregistro-E-E3-2`, `2e4a4fd`) y su texto no cambió; la etiqueta no se mueve | aprobada |
| D-E3-26 | **Entran en la F4 la carga manual de índices en TIF, Google Earth Engine como alternativa y el modo escenario con valores fijos** (puntos 10b, 11 y 12), porque son necesarios para la implementación final. Suman unos 3 días a los 8 del plan | decidida por el usuario el 2026-11-12 |
