# F5 — Intervenciones: pedido de aprobación

Para leer antes de empezar la fase F5. Cada punto trae una propuesta. Alcanza con contestar "apruebo todo" o con la lista de
números que se quieren cambiar. Los puntos marcados **bloquea** hay que resolverlos antes de escribir código.

Estado del que se parte: rama `f5-intervenciones`, creada desde `f4-datos` (F4 terminada; E-E3-2 pendiente de evaluar). El
prerregistro E-E3-4 está etiquetado desde la F0 (`prerregistro-E-E3-4`): escribe deinagutierrez y evalúa LisandroV2002
(decidido por el usuario el 2026-11-13).

## 1. Qué pide el plan para F5

Dibujar cortafuegos a mano alzada (trazo, borrador, ancho, deshacer, longitud), aplicarlos en los dos motores antes de iniciar
o con la corrida en pausa, cambiar el viento a mano durante la corrida, llevar una bitácora encadenada y poder reproducir una
corrida desde ella (`00_plan.md` §2.4, §2.6). Criterio de aceptación: **E-E3-4**, es decir, la reproducción desde la bitácora
da 0 celdas distintas, y la corrida offline con los mismos trazos desde el inicio da IoU ≥ 0,99 y la misma longitud de
cortafuego. Esfuerzo del plan: 6 días.

## 2. Qué se averiguó leyendo y probando los motores (2026-11-13)

Tres lecturas en paralelo, con pruebas en una carpeta aparte, sin tocar el repositorio:

| Qué | Resultado |
|---|---|
| v3.1: agregar barreras en pausa | **se puede**: el motor lee `barrera`, `ancho_tab`, `bloq` y `estado` en cada paso, y cambiarlos dentro de `_tablas_hora` rige desde esa hora. No recompila numba |
| v3.1: trazo en pausa contra el mismo trazo cargado desde el inicio, en Las Lagunas 2024 (14 h, libre_v2, con viento manual y suelo mineral) | **0 celdas distintas**, recortando los enlaces que llegan a celdas ya afectadas. Sin recorte: 3.492 celdas distintas |
| v3.1: las dos variantes del simulador (`libre` y `libre_v2`) | **tienen las barreras apagadas**, también `libre_v2` (así está en `evaluar_v2.py`). El plan §2.3 dice "librev2 (barreras de caminos activas)": **no coincide con el código** (§5, punto 9) |
| v3.1: arrancar con una matriz de barreras vacía | da lo mismo que barreras apagadas: comprobado en Las Lagunas 24 h, en `libre` y en `libre_v2`, con 0 celdas distintas |
| v3.1: códigos de un trazo propio | la función real (`preparar_barreras_enlaces`) solo acepta un archivo de dominio y escribe sobre el producto compartido del dominio; envuelta, con las rutas desviadas a una carpeta temporal, tarda 4,5 s. Una copia de su núcleo limitada a una ventana alrededor del trazo da el mismo resultado bit a bit en 8 ms |
| v3.1: suelo mineral | hay que poner clase 0 **y** estado no combustible, y siempre junto con la barrera: una línea de clase 0 de una celda la cruzan los saltos de caballo de la vecindad 16 |
| v3.1: viento | un valor por hora; se cambia envolviendo la función `viento` de las entradas (cambio de golpe en la hora de la pausa). La humedad muerta es una serie precalculada y no cambia con el viento manual |
| v4.0: agregar un cortafuego en pausa | **se puede** con su propia función (`rasterizar_barreras_extra`) más el recálculo de cuatro tablas en las celdas tocadas. Da t_llegada, estado, cruces y bloqueos **idénticos** al trazo cargado desde el inicio, si el recorte es más estricto que "celdas no afectadas" (§4, punto 13). Con el recorte del plan falló en 3 de 12 casos (diferencias de 0,0001 min) |
| v4.0: viento | se reemplaza la serie horaria desde la fila siguiente a la pausa: el viento gira de forma gradual durante esa hora (plan §2.6). Comprobado idéntico a la serie editada desde el inicio. **Requiere que la corrida empiece en hora en punto**: con inicio 12:30 cambia la media hora ya simulada (126 celdas distintas) |
| v4.0: suelo mineral | `modificador_combustible` en memoria; idéntico a cargarlo desde el inicio |
| Simulador hoy | una intervención llega al motor y vuelve "rechazada"; la bitácora solo guarda pausas, se escribe al final (se pierde si el proceso se cae) y no tiene hash. Una orden `intervenir` que llega en el mismo bloque que `pausar` se rechaza; la respuesta no se puede emparejar con su pedido |
| Reproducción offline (E-E3-4 B) | v4.0: `mitigacion.barreras_extra`, `mitigacion.modificador_combustible` y `parche.meteo` en el YAML. v3.1: no tiene claves para eso; se corre con una copia espejo de `datos/inputSimulacion` (barreras, meteo y clase editadas) por `INCENDIOS_SL_INPUT`. Comprobado en v3.1: 0 celdas distintas |

## 3. Quién y cómo

| N.º | Propuesta | |
|---|---|---|
| 1 | **La F5 completa la hace el frente A** (el usuario, con Claude), también el dibujo en la pantalla, que el plan daba al frente B. Es el mismo cambio que en la F2 y la F3 (D-E3-17, D-E3-22). Se revisa al final, con la rama completa | |
| 2 | **E-E3-4: escribe deinagutierrez, evalúa LisandroV2002** (ya anotado en el prerregistro) | |
| 3 | **El archivo de trazos y horas del prerregistro** se escribe, se sube y se etiqueta (`prerregistro-E-E3-4-trazos`) **antes de escribir el código de intervenciones**, como pide E-E3-4. Lo armo yo: cinco juegos de trazos y horas sobre Las Lagunas 2024, hipótesis 1, con los anchos y las horas que fija el prerregistro. Para poner los trazos "delante del frente" miro solo la huella a las 6 y 12 h de una corrida sin intervenciones, que no es ninguna de las comparaciones | **bloquea** |

## 4. Diseño

| N.º | Propuesta | Alternativa descartada | |
|---|---|---|---|
| 4 | **Cortafuegos**: polilínea en EPSG:5345 con ancho de 3, 6, 10, 15 o 25 m y la opción "a suelo mineral" (rotulada supuesto). Se dibujan antes de iniciar (`configuracion.cortafuegos`) o con la corrida en pausa (intervención). El servidor pasa los trazos de grados a EPSG:5345 | — | **bloquea** |
| 5 | **Viento manual en pausa**: velocidad (km/h) y dirección (de dónde viene), desde la hora de la pausa; y "volver al pronóstico". En v3.1 cambia de golpe; en v4.0 gira durante la hora siguiente (plan §2.6) | — | **bloquea** |
| 6 | **Las corridas empiezan siempre en hora en punto** (UTC). Hoy se aceptan minutos; con minutos, el viento manual de v4.0 cambiaría lo ya simulado. Se rechaza un `t_inicio_utc` con minutos, con mensaje claro. No cambia nada de lo hecho: las fichas y la pantalla ya usan horas enteras | aceptar minutos y rechazar solo el viento manual: confuso | **bloquea** |
| 7 | **v3.1, códigos del trazo con la función real** (`preparar_barreras_enlaces`, envuelta: rutas desviadas a una carpeta de la corrida, capa de caminos vacía, archivo único por llamada). Unos 4,5 s por trazo, con la corrida en pausa. Es lo que pedía el plan ("el código real de v3.1, sin aproximación"). Una prueba automática compara contra la copia de 8 ms por si después se quiere cambiar | copia del núcleo en `app/` (8 ms): más rápida, pero es código de v3.1 reescrito fuera del congelado | **bloquea** |
| 8 | **v3.1, las dos variantes arrancan con una matriz de barreras vacía**, para poder recibir cortafuegos. Comprobado que da lo mismo que barreras apagadas; además entra en las pruebas y en E-E3-1 repetido | — | **bloquea** |
| 9 | **Se corrige el plan §2.3**: `librev2` de v3.1 es `modelo_v2` **sin** barreras de caminos (así se validó y así lo corre el simulador desde la F1). No cambia ningún resultado; los cortafuegos del usuario igual funcionan (punto 8) | activar las barreras de caminos en librev2: cambiaría el motor validado | **bloquea** |
| 10 | **Recorte en v3.1**: se sacan del trazo los enlaces que llegan a una celda ya afectada (llegada finita). Se conservan los que salen de celdas en llamas, que son los que frenan el frente pegado a la línea | recortar por celda de origen: deja pasar el fuego desde las celdas en llamas | |
| 11 | **Suelo mineral**: v3.1 pone clase 0 y estado no combustible en las celdas del trazo que todavía no quemaron, siempre con la barrera; v4.0 usa `modificador_combustible` = 0 | — | |
| 12 | **Cortafuegos antes de iniciar**: v4.0 por la vía que ya tiene (`mitigacion.barreras_extra` y `modificador_combustible`, archivos en la carpeta de la corrida); v3.1 los combina en las barreras antes de crear la simulación. Un trazo antes de iniciar tiene que dar lo mismo que el mismo trazo aplicado a t = 0 (prueba automática) | — | |
| 13 | **Recorte en v4.0 más estricto que el del plan**: además de las celdas ya afectadas, se sacan las celdas no afectadas que son la intermedia de un enlace diagonal entre dos celdas afectadas (en v4.0 ese enlace ya se sorteó contra la barrera antes de la pausa). Con esta regla, 12 de 12 casos idénticos. Cambia la frase del plan "recortado a celdas no afectadas" | la regla del plan: rompe la identidad en casos de borde | **bloquea** |
| 14 | **Longitud que se informa**: la de la polilínea **dibujada** (plan §2.6) y, aparte, la de la parte que quedó después del recorte. El criterio B de E-E3-4 ("misma longitud") se mide con la recortada, que es la que entra en la corrida offline. Se anota en el archivo de trazos | — | **bloquea** |
| 15 | **"Más horas" durante la corrida no se ofrece**: los dos motores fijan el horizonte al empezar (v4.0 también calcula la humedad solo hasta el final). Para más horas se reinicia la corrida. Cambia la tabla del plan §2.6 | extender en caliente: no reproducible sin tocar los motores | |
| 16 | **Viento manual con WindNinja externo en v4.0**: se rechaza con su motivo (no aplica a la configuración congelada, que usa la serie) | — | |

## 5. Bitácora, reproducción y contrato

| N.º | Propuesta | Alternativa descartada | |
|---|---|---|---|
| 17 | **Bitácora encadenada**: cada entrada `{n, t_sim_min, t_vigor_min, tipo, datos, hash}`; `hash` = sha256 de la entrada (JSON canónico, números normalizados: coordenadas a 0,01 m) junto con el hash anterior. La primera se encadena con la configuración inicial: `formato`, `motor`, `base`, `configuracion` (con cortafuegos), `insumos` y el sha256 del congelado (sin `id`, fecha ni grupo, que cambian al reproducir). Entran pausas, reanudaciones, intervenciones aceptadas o recortadas y la detención; las rechazadas quedan solo en `eventos.jsonl` | — | **bloquea** |
| 18 | **La bitácora se escribe en el momento** (`bitacora.jsonl` en la carpeta de la corrida) y viaja en cada aviso: no se pierde si el proceso se cae. La pantalla la muestra en vivo | escribirla al final, como hoy | |
| 19 | **Reproducir desde la bitácora lo hace el propio proceso motor**: `corrida.json` lleva `reproduccion` (la bitácora de la corrida original) y el proceso aplica cada intervención en su hora, sin pasar por el servidor. Pedido nuevo `POST /api/corridas/<id>/reproducir`, que copia la configuración tal cual. Al terminar compara las dos cadenas de hash | que el servidor pause y mande cada intervención: la pausa hoy no tiene hora objetivo | **bloquea** |
| 20 | **`pausar` con hora objetivo** (`en_t_sim_min`, opcional) y órdenes de un mismo bloque procesadas en orden (pausar e intervenir juntos). En modo "ambos", la pantalla pausa las dos corridas en la misma hora y les manda la misma intervención | — | |
| 21 | **Cada intervención lleva `ref`** y la respuesta vuelve con el mismo `ref`; el servidor espera hasta 30 s (el trazo de v3.1 tarda unos 5 s) | 5 s fijos, sin emparejar | |
| 22 | **Contrato 1.5** con todo lo anterior. Se escribe antes del código y lo aprueba la otra persona con la rama | — | |
| 23 | **El motor simulado acepta intervenciones** (un cortafuego frena el círculo; el viento se registra sin efecto), para probar servidor y pantalla en segundos | — | |

## 6. Pantalla

| N.º | Propuesta | |
|---|---|---|
| 24 | **Trazo a mano alzada sin bibliotecas nuevas**: con los eventos del puntero sobre Leaflet, el mapa quieto mientras se dibuja, simplificación del trazo al soltar, borrador, deshacer, selector de ancho, casilla "a suelo mineral (supuesto)" y longitud en vivo (la oficial la da el servidor). Disponible antes de iniciar y en pausa | |
| 25 | **Panel de viento manual** en pausa (km/h, de dónde viene, "aplicar desde la hora H", "volver al pronóstico"), con el aviso de que v4.0 gira durante la hora siguiente | |
| 26 | **Bitácora y mitigación en las tarjetas**: cortafuegos con ancho y longitud (dibujada y aplicada), cambios de viento con su hora, pausas; la parte recortada del trazo se dibuja de otro color. Botón "Reproducir" en una corrida terminada | |
| 27 | **Exportación**: `cortafuegos.geojson` y la bitácora con hash dentro del zip | |

## 7. Pruebas y verificación

| N.º | Propuesta | |
|---|---|---|
| 28 | **Pruebas automáticas sin red**: matriz vacía igual a barreras apagadas (v3.1); trazo antes de iniciar igual a trazo a t = 0; trazo en pausa igual al mismo trazo recortado desde el inicio, en los tres motores, en una corrida corta; viento manual en pausa igual a la serie editada; hash que detecta una bitácora editada; reproducción con 0 celdas distintas; pedidos inválidos (422) y fuera de pausa (409); servidor y pantalla con el motor simulado | |
| 29 | **Guion de evaluación de E-E3-4** (`herramientas/e_e3_4.py`), como el de E-E3-2: las cinco corridas en los tres motores, comparación A (desde la bitácora) y B (offline con `correr_escenario.py` de cada motor), resultado en JSON y Markdown. Lo corre quien evalúa; quien escribe lo prueba solo con datos de prueba | |
| 30 | **E-E3-1 repetido** al cerrar (los siete pares, sin intervenciones), para comprobar que la matriz vacía y el resto no cambiaron nada | |

## 8. Cómo contestar

"Apruebo todo", o los números con lo que se quiere distinto. Los que bloquean el inicio son **3, 4, 5, 6, 7, 8, 9, 13, 14, 17
y 19**. Lo que se apruebe se anota en `decisiones.md` con la fecha.
