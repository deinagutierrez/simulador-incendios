# Contrato entre los dos frentes — versión 1.5

Es el único punto donde se tocan el frente A (motores y datos) y el frente B (servidor e interfaz). Se cambia solo por pedido
de integración aprobado por las dos personas, subiendo el número de versión.

**Cambios de la 1.0 a la 1.1** (propuestos al implementar la fase F1 y aprobados por las dos personas el 2026-11-11,
decisión D-E3-16):
`corrida.json` admite `base` para definir la corrida desde un escenario de los motores; el motor se lee de `corrida.json`;
el aviso `listo` trae la grilla de la huella; `final` y `error` traen más campos; las órdenes se consultan sin bloquear;
los resultados del motor quedan en `salida/`; `corrida.json` admite `configuracion` con la ignición, la hora de inicio y la
duración elegidas por el usuario, y `resultados.ignicion` informa el punto que usó el motor. La etiqueta `contrato-v1` apunta
a la 1.0.

**Cambios de la 1.1 a la 1.2** (fase F2, 2026-11-11; aprobados con el pedido de la F2, decisiones D-E3-19 y D-E3-20):
un punto elegido por el usuario que cae en una celda que no quema se corre a la combustible más cercana al clic, sin mirar la
cicatriz del evento base; el motor simulado existe (§3); el servidor existe y su interfaz está en §4; el servidor agrega a
`corrida.json` los campos `formato`, `id`, `creada_utc`, `grupo` y `programa`.

**Cambios de la 1.2 a la 1.3** (fase F3, 2026-11-11; **propuestos, pendientes de aprobación de la otra persona**):
pedidos nuevos del servidor para la pantalla (capas de fondo, vectores, contorno, exportación, comparación entre dos
corridas) y color plano en la imagen de la huella. La raíz `/` pasa a ser la pantalla; la página de prueba queda en `/prueba`.

**Cambios de la 1.3 a la 1.4** (fase F4, 2026-11-13; punto 19 del pedido de la F4, aprobado en D-E3-24; **la revisión
de la otra persona se hace con la rama `f4-datos` completa**): el proceso motor no cambia. Un evento de `base.definicion` puede
ser un **evento generado `RT-<AAAAMMDD>-<n>`** (datos bajados en el momento, §1.1); `corrida.json` pasa al formato
`incendios_sl.corrida/1.2` con los bloques `insumos` y `advertencias`; el servidor suma los pedidos de datos (§4.1).

**Cambios de la 1.4 a la 1.5** (fase F5, 2026-11-13; puntos 4-6, 14 y 17-23 del pedido de la F5, aprobado en D-E3-28;
**la revisión de la otra persona se hace con la rama `f5-intervenciones` completa**): cortafuegos antes de iniciar
(`configuracion.cortafuegos`) y en pausa, viento manual en pausa, `t_inicio_utc` solo en hora en punto, bitácora encadenada
con hash escrita en el momento (`bitacora.jsonl`) y enviada en los avisos, reproducción desde la bitácora hecha por el propio
proceso motor (`reproduccion`), orden `pausar` con hora objetivo, órdenes de un mismo bloque procesadas en orden, `ref` en
cada intervención, avisos `reanudado` y `detenido`, pedidos `/reproducir`, `/intervenciones`, `/cortafuegos.geojson` y de
grupo (`/api/grupos/<grupo>/pausar` e `/intervenciones`), `pausar` con cuerpo `{en_t_sim_min}` (§4.2).

## 1. Paquete de corrida

El archivo `corrida.json` vive en la carpeta de la corrida, `resultados/app/<id>/`. Su forma completa está en el Anexo C de
`00_plan.md`. Lo que el proceso motor lee hoy:

| Campo | Contenido |
|---|---|
| `motor` | `v4.0`, `v3.1-libre` o `v3.1-librev2` |
| `base.escenario` | nombre de un YAML de `escenarios/<versión>/corridas/`; la corrida es esa, tal cual |
| `base.definicion` | lo mismo que iría en ese YAML: `evento` (o `caso` en v4.0), `hipotesis`, `ignicion`, `horas`, `validar`, `figuras`… |

Hace falta `base.escenario` o `base.definicion`. Con `definicion`, lo que no se indique toma los valores de la decisión
D-E3-01: en v4.0, `variante: barreras` y `parar_en_cicatriz: off`; en v3.1, `variante: libre` o `libre_v2` según el motor.

**Lo que elige el usuario** va en `configuracion`, y solo se combina con `base.definicion` (con `base.escenario` se rechaza):

| Campo | Contenido |
|---|---|
| `configuracion.ignicion` | lista de puntos `{lon, lat}` en grados (WGS84), opcionalmente con `nombre`. Reemplaza a los puntos de la ficha del evento |
| `configuracion.t_inicio_utc` | hora de inicio con huso, por ejemplo `2024-09-19T16:00:00Z`. Reemplaza a la hora de la ficha. **Tiene que caer en hora en punto UTC** (desde la 1.5): con minutos o segundos el proceso la rechaza con un `error` fatal, porque el viento manual de v4.0 cambiaría la parte de la hora ya simulada |
| `configuracion.horas` | duración; pisa a `base.definicion.horas` |
| `configuracion.cortafuegos` | (desde la 1.5) trazos dibujados antes de iniciar: `[{"ancho_m": 10, "suelo_mineral": false, "xy_5345": [[x, y], …]}]`. `ancho_m` ∈ {3, 6, 10, 15, 25}; `suelo_mineral` (supuesto, por defecto `false`); `xy_5345`: polilínea en EPSG:5345 (metros), al menos dos puntos distintos. El proceso la normaliza (§2.1) y le agrega `longitud_dibujada_m`. Un trazo antes de iniciar da lo mismo que el mismo trazo aplicado en pausa a t = 0 |

El evento de `base.definicion` sigue aportando la meteorología, los índices y la cobertura; la hora de inicio tiene que caer
dentro de su serie meteorológica. Reglas:

- Un punto fuera del dominio o una hora fuera de la serie meteorológica se rechazan con un aviso `error` (`fatal: true`)
  antes de simular.
- Un punto sobre una celda combustible se usa tal cual (el fuego empieza en esa celda de 30 m).
- Un punto de `configuracion.ignicion` sobre una celda no combustible (agua, roca, urbano) lo corre el motor a la celda
  combustible **más cercana al clic**, con su propio mapa de combustible. La cicatriz del evento base no interviene: el
  programa se la oculta a ese paso (decisión D-E3-20). El corrimiento se informa en
  `resultados.ignicion.usada[].desplazada_m`; la pantalla debe mostrarlo.
- Con los puntos de la ficha (sin `configuracion.ignicion`) vale la regla de siempre de cada motor, que sí busca dentro de
  la cicatriz: es lo que hacen las corridas offline.

Al terminar, el proceso completa `corrida.json` con `bitacora` (§1.2), `bitacora_raiz` y `resultados` (`ha_final`,
`km2_final`, `t_simulado_h`, `s_computo`, `memoria_pico_mb`, `motivo_fin`, `completa`, `archivos`, `ignicion` =
`{pedida, usada: [{id, lon, lat, desplazada_m?}], t_inicio_utc}`, y `reproduccion` si la corrida fue una reproducción, §1.3).
Cómo informa cada motor los cortafuegos de `configuracion.cortafuegos` (longitud aplicada, celdas) va en `resultados`: lo
documenta el conductor de cada motor.

No existe `configuracion.viento`: el viento manual es solo una intervención en pausa (para tenerlo desde el inicio, se pausa
en t = 0).

### 1.1 Evento generado y procedencia de los insumos (desde la 1.4)

Un evento generado `RT-<AAAAMMDD>-<n>` lo arma el proceso de datos con una toma de meteorología y una de índices
(`app/datos/evento_rt.py`). Para los motores es un evento con ficha más: su ficha está en `escenarios/v3.1/eventos/` y
`escenarios/v4.0/eventos/`, y sus datos en `datos/inputSimulacion/{meteo, combustibles/RT-…, eventos/RT-…}` (git y el control
del congelado ignoran los `RT-*`). Diferencias con un evento histórico:

- no tiene cicatriz ni focos (`referencia_espacial: null`); por eso **la corrida tiene que traer `configuracion.ignicion`**
  (el servidor rechaza un pedido sin ignición) y se recomienda `configuracion.t_inicio_utc`;
- su procedencia está en `datos/inputSimulacion/eventos/RT-…/insumos_RT-….json`.

El servidor copia esa procedencia a `corrida.json` (formato `incendios_sl.corrida/1.2`):

| Campo | Contenido |
|---|---|
| `insumos.evento` | `id`, `creado_utc`, `archivos` (rutas relativas al repositorio) y `sha256` de cada uno |
| `insumos.meteo` | `toma`, `fuente`, `modelo`, `rotulo`, `descargado_utc`, `desde_utc`, `hasta_utc`, `sha256` |
| `insumos.indices_ventana` | `toma`, `fuente`, `rotulo`, `via` (`aws`, `gee` o `manual`), `ventana` [primer y último día], `escenas`, `ndmi_nir` (`B08` o `B8A`), `sha256`, `en_prueba` |
| `insumos.indices_verano` | `anio`, `archivos`, `faltan`, `sha256` de los compuestos de enero a marzo que usa v4.0 |
| `insumos.cobertura_anio` | año de la cobertura MapBiomas |
| `advertencias` | lista de textos para mostrar con la corrida: rótulos de la meteorología y de los índices ("escenario manual", "índices cargados a mano", "en prueba hasta E-E3-2"), avisos de cada toma y "sin cicatriz ni focos". Para un evento con ficha: `["EJEMPLO: datos de un evento histórico"]` |

`insumos` falta en las corridas de eventos con ficha, del motor simulado y de definiciones sin evento.

### 1.2 Bitácora encadenada (desde la 1.5)

Cada entrada es `{n, t_sim_min, t_vigor_min, tipo, datos, hash}`:

| Campo | Contenido |
|---|---|
| `n` | 1, 2, 3… sin huecos |
| `t_sim_min` | minuto simulado en que se anotó (la hora de la pausa), float |
| `t_vigor_min` | desde cuándo rige; igual a `t_sim_min` salvo que el motor diga otra cosa |
| `tipo` | `pausa`, `reanudacion`, `detencion`, `cortafuego` o `viento_manual` |
| `datos` | `{}` en pausa, reanudación y detención; en una intervención, los datos normalizados de la entrada (§2.1) más lo que agrega el motor al aplicarla |
| `hash` | sha256 de `{anterior, n, t_sim_min, t_vigor_min, tipo, datos}` en JSON canónico; `anterior` es el `hash` de la entrada previa o, en la primera, la **raíz** |

- Entran las pausas, las reanudaciones, la detención y las intervenciones `aceptada` o `recortada`. Las `rechazada` quedan
  solo como aviso (y en `eventos.jsonl` del servidor).
- **Raíz** = sha256 del JSON canónico de `{"configuracion_inicial": {formato, motor, base, configuracion, insumos,
  congelado_sha256}}`, con `configuracion` completa (sin claves vacías; los cortafuegos normalizados) y `congelado_sha256` =
  `programa.congelado_sha256`. Quedan fuera `id`, `creada_utc`, `grupo`, `advertencias`, `bitacora`, `resultados` y
  `reproduccion`, que cambian al reproducir o son derivados. En modo "ambos" cada corrida tiene su raíz (el motor es otro).
- **JSON canónico**: claves ordenadas, separadores `,` y `:` sin espacios, UTF-8 sin escapar, sin NaN ni infinito, y todo
  float entero escrito como entero (`360.0` → `360`), para que Python y JavaScript den el mismo hash. Las coordenadas van
  redondeadas a 0,01 m y los minutos a 3 decimales.
- Implementación de referencia: `app/motores/intervenciones.py` (`canon`, `raiz`, `hash_entrada`, `verificar_cadena`). No
  importa motores; el servidor la puede usar.
- **Se escribe en el momento**: cada entrada se agrega a `bitacora.jsonl` (una línea JSON por entrada) en la carpeta de la
  corrida al anotarla, y viaja en el campo `entrada` del aviso que la produce (`pausado`, `intervencion`, `reanudado`,
  `detenido`, §2). Al terminar, el proceso la copia a `corrida.json` (`bitacora`) junto con `bitacora_raiz`. Si el proceso se
  cae, `bitacora.jsonl` y los avisos ya recibidos la conservan.

### 1.3 Reproducción desde la bitácora (desde la 1.5)

Una corrida que trae `reproduccion` = `{"de": <id original>, "raiz": <bitacora_raiz original>, "bitacora": [...]}` es una
reproducción. Su `corrida.json` copia **tal cual** `formato`, `motor`, `base`, `configuracion`, `insumos` y `programa` de la
original (lo arma el servidor, §4.2). El proceso motor:

- aplica cada entrada de la bitácora original al llegar a su `t_sim_min`, sin pasar por la entrada estándar: las
  intervenciones por el mismo camino que en pausa, la detención detiene, y las pausas y reanudaciones se anotan sin esperar;
- anota todo igual que en la corrida original, así que la cadena tiene que salir idéntica;
- no acepta intervenciones nuevas (`rechazada`); las pausas a mano funcionan pero no entran en la cadena;
- al terminar deja `resultados.reproduccion` = `{de, raiz_original, raiz, raiz_igual, original_integra,
  original_primer_fallo, n_original, n, cadena_igual, primera_distinta, sin_aplicar}`. `cadena_igual` es verdadero si la
  raíz y todos los hash coinciden y la bitácora original verifica; `sin_aplicar` lista los `n` que no se llegaron a aplicar.

El criterio A de E-E3-4 (0 celdas distintas) se mide comparando las salidas de las dos corridas.

## 2. Proceso motor

El servidor lanza un proceso por corrida, con la entrada y la salida estándar como tuberías:

```
python app/motores/proceso.py --corrida resultados/app/<id>
```

No hace falta fijar `PYTHONPATH`: el proceso apunta solo al motor que le toca. Cada proceso carga un único motor.

**Órdenes** (servidor → motor, una línea JSON por la entrada estándar, terminada en salto de línea):

| Orden | Efecto |
|---|---|
| `{"orden": "pausar"}` | el motor termina la hora simulada en curso, avisa `pausado` y espera |
| `{"orden": "pausar", "en_t_sim_min": 360}` | (1.5) pausa al llegar a esa hora simulada (si ya pasó, en la hora actual). Las órdenes que llegan **después** esperan a esa pausa, salvo `detener` |
| `{"orden": "reanudar"}` | sigue. Si todavía no pausó, cancela la pausa pedida |
| `{"orden": "detener"}` | cierra la corrida y guarda lo simulado hasta ahí. Se atiende en el acto, aunque haya una pausa futura pendiente |
| `{"orden": "intervenir", "ref": "…", "entrada": {"tipo": …, "datos": {…}}}` | (1.5) solo en pausa. `ref` (texto o número, lo elige el servidor) vuelve en el aviso `intervencion`. Fuera de pausa: `rechazada` |

El motor mira las órdenes **al cumplirse cada hora simulada**, no en el medio. Una orden enviada a mitad de una hora se
atiende al terminar esa hora. Si el servidor cierra la tubería mientras la corrida está en pausa, el motor la da por detenida
y guarda.

**Órdenes en bloque** (1.5): las órdenes se procesan de a una, en el orden en que llegaron, con el estado de pausa al día.
`pausar` + `intervenir` + `reanudar` mandadas juntas pausan, intervienen y siguen en la misma hora; con
`pausar {en_t_sim_min: X}` delante, lo hacen al llegar a X. Así el servidor pausa las dos corridas de un modo "ambos" en la
misma hora y les manda la misma intervención.

**Avisos** (motor → servidor, una línea JSON por la salida estándar; por ahí no sale nada más):

| Aviso | Campos |
|---|---|
| `listo` | `t0_utc`, `grilla` = `{crs, xmin, ymax, res, filas, cols}`. Llega una vez, antes de la primera `hora` |
| `hora` | `h` (0, 1, 2…), `t_sim_min`, `ha`, `activas`, `s_computo`, `huella`. En v4.0 además `exposicion` (viviendas afectadas y amenazadas, km de tendido, km de caminos) y `meteo` |
| `pausado` | `t_sim_min`, siempre múltiplo de 60; (1.5) `entrada`: la entrada `pausa` de la bitácora (`null` en una pausa a mano durante una reproducción); `reproduccion: true` si la pausa la anotó una reproducción (no hay que esperar: sigue sola) |
| `reanudado` | (1.5) `t_sim_min`, `entrada` (la entrada `reanudacion`), `reproduccion?` |
| `intervencion` | `ref` (el de la orden), `n` (de la bitácora; `null` si rechazada), `estado` (`aceptada`, `recortada`, `rechazada`), `t_vigor_min`, `pleno_min` (opcional: desde cuándo rige del todo; v4.0 viento), `motivo`, `entrada` (la entrada de la bitácora completa, con `hash`; `null` si rechazada) |
| `detenido` | (1.5) `t_sim_min`, `entrada` (la entrada `detencion`). Llega antes de `final` |
| `final` | `motivo`, `texto`, `ha`, `t_sim_min`, `s_computo`, `memoria_pico_mb`, `completa` (falso si se detuvo), `salida`. Es el último aviso; el proceso termina con código 0 |
| `error` | `mensaje`, `fatal`. Con `fatal: true` el proceso termina con código 1 |

`s_computo` no cuenta el tiempo en pausa.

### 2.1 Intervenciones (desde la 1.5)

**Entradas** (lo que va en `entrada` de la orden `intervenir`). El proceso las valida y normaliza con
`intervenciones.validar_entrada`; si no sirven, responde `rechazada` con el motivo.

| `tipo` | `datos` que manda el servidor | `datos` normalizados |
|---|---|---|
| `cortafuego` | `{ancho_m, suelo_mineral?, xy_5345: [[x, y], …]}` | `{ancho_m: int ∈ {3,6,10,15,25}, suelo_mineral: bool, xy_5345: [[x, y], …] (redondeados a 0,01 m, sin repetidos seguidos), longitud_dibujada_m}` |
| `viento_manual` | `{vel_kmh, dir_desde}` o `{modo: "pronostico"}` | `{vel_kmh: 0-216, dir_desde: 0-360 (de dónde viene, 360 → 0)}`, redondeados a 0,01; o `{modo: "pronostico"}` (vuelve a la serie) |

**Aplicación.** Cada conductor pone `control.aplicar(entrada, t_sim_min) -> dict` y Control lo llama con la corrida en pausa
en `t_sim_min`, con la entrada ya normalizada. Devuelve `{estado, t_vigor_min, pleno_min?, motivo, datos}`; `datos` se suma a
los datos de la entrada en la bitácora. Si devuelve `rechazada` o lanza una excepción, no entra en la bitácora y el motor
tiene que quedar como estaba. Lo que cada motor agrega a `datos` de un cortafuego:

- `longitud_aplicada_m`: la de la parte del trazo que quedó después del recorte (la del criterio B de E-E3-4; la dibujada es
  `longitud_dibujada_m`);
- lo aplicado, para poder reproducirlo y compararlo: cantidad y sha256 de las celdas o enlaces
  (`intervenciones.sha256_indices`), con nombres que documenta cada conductor.

| | v3.1 | v4.0 | simulado |
|---|---|---|---|
| cortafuego | enlaces del trazo con `preparar_barreras_enlaces` (envuelta); se quitan los que llegan a celdas ya afectadas; suelo mineral: clase 0 y no combustible | `rasterizar_barreras_extra`; se quitan las celdas afectadas y las intermedias de diagonales entre afectadas; suelo mineral: `modificador_combustible` = 0 | celdas que toca el trazo, sin las ya quemadas |
| `t_vigor_min` | `t_sim_min` | `t_sim_min` | `t_sim_min` |
| viento manual | cambia de golpe en `t_sim_min` | gira durante la hora siguiente: `t_vigor_min` = `t_sim_min`, `pleno_min` = `t_sim_min` + 60; con WindNinja externo, `rechazada` | se acepta sin efecto |

**Lo que cada conductor deja para la corrida offline** (comparación B de E-E3-4), siempre dentro de la carpeta de la corrida:

| | v3.1 (`intervenciones_v31/`) | v4.0 (raíz de la carpeta; nombres en `resultados.archivos_offline`) |
|---|---|---|
| cortafuegos | `cortafuego_NN.npz` (enlaces aplicados, código, ancho, celdas minerales) y `barreras_enlaces.npz` (matriz final con el formato de `cargar_barreras_enlaces`) | `cortafuegos_aplicados.geojson` (geometría reproducible de cada trazo: la polilínea recortada, o los centros de las celdas si no rasteriza igual; `datos.geometria_offline` dice cuál) |
| suelo mineral | `suelo_mineral.npz` (celdas a clase 0) | `modificador_aplicado.tif` (grilla base, 0 en el trazo, nodata 1) |
| viento manual | `viento_horario.csv` (`time_utc`, `wind_speed_10m` m/s, `wind_direction_10m`) | `meteo_editada.csv` (serie completa con el formato de v4.0); en `datos`: `filas_editadas`, `desde_utc` |
| antes de iniciar | `resultados.cortafuegos_iniciales` | `resultados.cortafuegos_iniciales` |

Con la matriz de barreras vacía (punto 8 de la F5), v3.1 deja además `cruces_barrera.tif` y `bloqueos_barrera.tif` (en cero
sin cortafuegos) y `registro.json` anota `barreras_activo: true`. Los tiempos de llegada no cambian (E-E3-1 repetido el
2026-11-14: 0 celdas distintas en los siete pares); solo cambia la lista de archivos de `salida/` respecto de una corrida
offline sin barreras.

`estado`: `aceptada` si se aplicó entero; `recortada` si se quitó una parte (celdas ya quemadas, o fuera del dominio);
`rechazada` si no queda nada, el trazo cae fuera del dominio o el motor no puede aplicarla.

**Huella.** `t_llegada_parcial.npy` en la carpeta de la corrida: matriz `float32` con los minutos desde el inicio en que el
fuego llegó a cada celda, `NaN` donde no llegó. Su forma y su posición son las de `grilla` en el aviso `listo`: con un evento
es el dominio completo (1.671 × 1.672); con un caso de prueba de v4.0 es la ventana del caso. El motor la reescribe en cada
hora de forma atómica, así que siempre se puede leer entera.

**Otros archivos de la carpeta.** `salida/` con lo mismo que deja una corrida offline del motor (en v4.0,
`hora_llegada_min.tif`, `serie_indicadores.csv`, `estado_hora_HH.json`, `perimetros_horarios.geojson`…; en v3.1,
`t_llegada_s.tif`, `serie_horaria.csv`, `registro.json`…); `proceso.log` con todo lo que imprime el motor;
`escenario_base.yaml` si la corrida vino por `definicion`; (1.5) `bitacora.jsonl` (§1.2) y lo que cada conductor escriba
para los cortafuegos (siempre dentro de la carpeta de la corrida: nunca en `datos/` ni en otro insumo compartido).

## 3. Motor simulado

`app/motores/proceso_simulado.py` cumple este contrato con un fuego de mentira: un círculo que crece tres celdas por hora, sin
viento, combustible ni relieve. Recibe las mismas órdenes y manda los mismos avisos que el proceso real. Sirve para probar el
servidor y la interfaz en segundos. Su `corrida.json`:

```json
{"motor": "simulado",
 "configuracion": {"ignicion": [{"lon": -65.55, "lat": -32.64}], "horas": 12},
 "simulado": {"s_por_hora": 0.05, "fallar_en_h": null, "lado": 200}}
```

`s_por_hora` son los segundos reales por hora simulada; `fallar_en_h` hace que el proceso se caiga sin avisar en esa hora;
`lado` es el tamaño de la grilla en celdas. El servidor solo lo ofrece si se lo arranca con `--con-simulado`.

Desde la 1.5 acepta intervenciones, de juguete: un cortafuego vuelve incombustibles las celdas que toca su trazo (menos las
ya quemadas, que se recortan) y el fuego no llega a lo que queda separado del foco por los cortafuegos; el ancho y el suelo
mineral no cambian nada. Agrega a `datos` `longitud_aplicada_m`, `celdas`, `celdas_recortadas` y `celdas_sha256`. El viento
manual se acepta sin efecto. `configuracion.cortafuegos` se aplica antes de la hora 0 y se informa en
`resultados.cortafuegos_iniciales`. Bitácora y reproducción, como los motores reales.

## 4. Interfaz del servidor

`python app/servir.py` levanta el servidor en `http://127.0.0.1:8000` (o el puerto libre siguiente). Solo atiende pedidos de
su propia página: los que traen otro origen se rechazan con 403.

| Pedido | Qué hace |
|---|---|
| `GET /api/estado` | versión, motores, eventos con datos en el clon (con su rango meteorológico y los puntos de su ficha), recuadro del dominio, límite de corridas |
| `POST /api/corridas` | crea una corrida; con `motor: "ambos"` crea dos (v4.0 y v3.1 librev2) con el mismo `grupo`; con `iniciar: true` las lanza. Cuerpo: `motor`, `evento`, `ignicion` `[{lon, lat}]`, `t_inicio_utc`, `horas` (1 a 240), y opcionales `hipotesis`, `ignicion_ficha`. Uso avanzado: `definicion`, igual a `base.definicion` |
| `GET /api/corridas` | lista, de la más nueva a la más vieja |
| `GET /api/corridas/<id>` | estado, última hora avisada, recuadro de la huella, bitácora (1.5: también en marcha, §4.2); al terminar, resultados |
| `POST /api/corridas/<id>/{iniciar,pausar,reanudar,detener}` | control. Contesta 409 si la orden no corresponde al estado |
| `POST /api/corridas/<id>/pausar` | (1.5) cuerpo opcional `{en_t_sim_min}`: pausa al llegar a esa hora simulada, redondeada hacia arriba a la hora en punto (§4.2) |
| `POST /api/corridas/<id>/intervenciones` | solo en pausa; devuelve el aviso `intervencion` del motor (§4.2) |
| `POST /api/corridas/<id>/reproducir` | (1.5) crea una corrida que reproduce a esta desde su bitácora (§4.2) |
| `GET /api/corridas/<id>/cortafuegos.geojson` | (1.5) cortafuegos de la corrida en grados: los iniciales y los de la bitácora (§4.2) |
| `POST /api/grupos/<grupo>/pausar` | (1.5) pausa las dos corridas de un modo "ambos" en la misma hora simulada (§4.2) |
| `POST /api/grupos/<grupo>/intervenciones` | (1.5) la misma intervención a las dos corridas del grupo (§4.2) |
| `GET /api/corridas/<id>/eventos` | avance en vivo por un canal de una sola vía (`text/event-stream`). Cada evento es un aviso del motor o un cambio de estado, numerado con `n`; con `?desde=N` manda los posteriores al N. Cierra con un evento `cierre` |
| `GET /api/corridas/<id>/quemado.png?hora=N` | huella hasta la hora N (o completa), lista para superponer en un mapa web con el recuadro `huella.limites` |
| `GET /api/corridas/<id>/quemado.png?hora=N&color=rrggbb` | con `color`, la huella de un solo color (para comparar dos motores) |
| `GET /api/corridas/<id>/perimetro.geojson?hora=N` | contorno del área quemada hasta la hora N, en grados |
| `GET /api/corridas/<id>/exportar` | zip con `corrida.json`, las salidas del motor y `perimetros_por_hora.geojson` (1.5: más `bitacora.jsonl` y `cortafuegos.geojson`). Solo con la corrida terminada |
| `GET /api/comparacion?a=<id>&b=<id>&hora=N` | superficie de cada huella, de la parte común y de la envolvente, y su cociente (`iou`) |
| `GET /api/capas?evento=<id>` | capas de fondo disponibles, con leyenda y recuadro |
| `GET /api/capas/<capa>.png?evento=<id>` | capa ráster lista para superponer: `relieve`, `pendiente`, `cobertura`, `arribo`, y por evento `ndvi`, `ndmi`, `combustible`, `cicatriz` |
| `GET /api/vectores/<capa>.geojson` | `dominio`, `caminos`, `red_mt`, `viviendas`, `cuarteles` |
| `GET /` | la pantalla del simulador |
| `GET /prueba` | página mínima de prueba de la F2 |

**Estados de una corrida:** `creada` → `iniciando` → `corriendo` ⇄ `pausando` → `pausada`; y al final `terminada`, `detenida`,
`error` o `interrumpida`. `pausando` es el rato entre que se pide la pausa y que el motor llega a la hora en punto.
`interrumpida` es una corrida que estaba en marcha cuando el servidor se cerró sin poder guardarla; no se retoma.

**Límites:** como mucho dos corridas en marcha; la tercera se rechaza con 409. Al cerrarse, el servidor pide a los motores
que guarden lo simulado y espera hasta 15 segundos.

**Archivos que agrega el servidor a la carpeta de la corrida:** `estado.json` (estado y última hora; con esto reconstruye la
lista al volver a arrancar), `eventos.jsonl` (todos los eventos, numerados) y `arranque.log`.

Todavía no existen el visor autónomo (F7) ni el modo histórico (F6).

En `GET /api/estado`, cada evento de `eventos_base` trae `tiempo_real` (verdadero para los `RT-…`), `rotulos` y `avisos`
(los eventos con ficha llevan `EJEMPLO`) y, en los `RT-…`, `t_inicio_por_defecto_utc` e `ignicion_de_la_ficha` vacía.

### 4.1 Datos que cambian (desde la 1.4)

Cada pedido que baja o prepara datos lanza un **trabajo de datos**: un proceso aparte (`app/datos/proceso_datos.py`) con el
camino de v3.1, que avisa como los procesos motor (líneas JSON `progreso`, `final`, `error`). Se hace **uno a la vez**; el
segundo se rechaza con 409. Cada trabajo vive en `datos/procesados/app/trabajos/<id>/`. Si el servidor se cierra con un
trabajo en marcha, lo corta y lo marca `interrumpido`; al volver a arrancar barre los eventos `RT-…` que quedaron a medio armar.

| Pedido | Qué hace |
|---|---|
| `GET /api/datos` | tomas de meteorología e índices guardadas, eventos `RT-…`, trabajo actual o último, disponibilidad de Earth Engine (`gee.disponible`, `gee.motivo`), antigüedad del pronóstico (aviso desde 6 h) y de los índices (aviso desde 10 días), avisos |
| `POST /api/datos/meteo` | `{"fuente": "pronostico"}`: pronóstico de Open-Meteo (`ecmwf_ifs025`, respaldo `best_match`), 5 días atrás y 7 adelante, 16 puntos |
| `POST /api/datos/meteo/archivo?nombre=x.csv` | cuerpo: el CSV crudo (máx. 20 MB), formato de v3.x o de v4.0; el control de calidad lo hace el trabajo |
| `POST /api/datos/meteo/escenario` | `{desde_utc, horas, temp_c, hr_pct, viento_kmh, viento_dir_deg, precip_mm}`: serie con valores fijos (más 5 días previos iguales) |
| `POST /api/datos/indices` | `{"fuente": "aws"|"gee", "fecha_corrida"?}`: compuesto de ventana de 45 días que terminan el día anterior; `gee` contesta 409 con el motivo si no hay biblioteca o credenciales |
| `POST /api/datos/indices/archivo?banda=ndvi|ndmi&nombre=x.tif` | cuerpo: el GeoTIFF crudo (máx. 60 MB); queda en espera, no lanza trabajo |
| `POST /api/datos/indices/manual` | `{ventana: [d1, d2], ndmi_nir: "B08"|"B8A", descripcion}`: valida los dos TIF en espera (grilla exacta, int16 × 10000, nodata −32768, rango) y guarda lo declarado |
| `POST /api/datos/evento` | `{meteo?, indices?, nombre?}`: arma un evento `RT-…` (por defecto con la toma más nueva de cada tipo) |
| `DELETE /api/datos/eventos/<id>` | borra un `RT-…` (no si una corrida creada o en marcha lo usa, ni mientras se arma otro) |
| `GET /api/datos/trabajos/<id>` | estado, progreso, resultado o error |
| `GET /api/datos/trabajos/<id>/eventos` | avance en vivo (`text/event-stream`), como el de las corridas |

Objeto trabajo: `{id, tarea, parametros, estado (creado | corriendo | terminado | error | interrumpido), creado_utc,
terminado_utc, progreso {hechos, total, texto, s}, resultado, error, n_eventos}`.

### 4.2 Intervenciones, bitácora en vivo y reproducción (desde la 1.5)

Los implementa el servidor; el proceso motor ya cumple lo suyo (§1.2, §1.3, §2, §2.1).

- **`POST /api/corridas`** acepta `cortafuegos: [{ancho_m, suelo_mineral?, lonlat: [[lon, lat], …]}]` (o `xy_5345`). El
  servidor pasa `lonlat` a EPSG:5345 con pyproj (como `datos.py`) y lo deja en `configuracion.cortafuegos` con `xy_5345`.
  Rechaza con 422 un `t_inicio_utc` que no cae en hora en punto y cortafuegos inválidos (mismas reglas que
  `intervenciones.validar_cortafuego`); conviene revisar también que el trazo toque el dominio.
- **`POST /api/corridas/<id>/intervenciones`**, cuerpo `{tipo, datos}` con `datos` como en §2.1 (en un cortafuego, `lonlat`
  o `xy_5345`). 422 si el cuerpo no es válido; 409 si la corrida no está en pausa. El servidor genera un `ref` único, manda
  `{"orden": "intervenir", "ref", "entrada"}` y espera **hasta 30 s** el aviso `intervencion` con ese `ref` (el trazo de v3.1
  tarda unos 5 s); lo devuelve tal cual (200), o 504 si no llegó. Con un grupo "ambos", la pantalla manda la misma
  intervención a las dos corridas, que tienen que estar en pausa en el mismo `t_sim_min` (para pausarlas juntas:
  `pausar {en_t_sim_min}` con la misma hora a las dos).
- **Bitácora en vivo**: el servidor junta las `entrada` que llegan en los avisos `pausado`, `intervencion`, `reanudado` y
  `detenido` (las no nulas) y las muestra en `GET /api/corridas/<id>` como `bitacora` mientras la corrida está en marcha; al
  terminar vale la de `corrida.json`. Si la corrida queda `error` o `interrumpida`, la bitácora sale de `bitacora.jsonl`.
  Los avisos también llegan por el canal de eventos.
- **`POST /api/corridas/<id>/reproducir`** (solo con la corrida original terminada o detenida, y con bitácora; si no, 409):
  crea una corrida nueva cuyo `corrida.json` copia tal cual `formato`, `motor`, `base`, `configuracion`, `insumos` y
  `programa` de la original (sin rearmarlos desde el pedido), con `id`, `creada_utc` y `grupo` nuevos y
  `reproduccion = {de: <id>, raiz: <bitacora_raiz>, bitacora: <bitacora>}`; con `iniciar: true` la lanza. Una reproducción
  no acepta intervenciones (el motor las rechaza; el servidor puede contestar 409). El resultado de la comparación queda en
  `resultados.reproduccion` (§1.3).
- **Exportar** suma `bitacora.jsonl` (y `corrida.json` ya lleva la bitácora con hash) y `cortafuegos.geojson`.

Detalle de lo que implementa el servidor:

- `GET /api/estado` suma `intervenciones: {anchos_m: [3, 6, 10, 15, 25], vel_max_kmh: 216, espera_s: 30}`.
- Cortafuego en un pedido: `{ancho_m, suelo_mineral (por defecto false), lonlat | xy_5345}`, uno de los dos, de 2 a 10000
  puntos; otros campos dan 422. El trazo que cae entero fuera del recuadro del dominio da 422. Como mucho 100 por corrida.
- `POST /api/corridas/<id>/pausar` y `POST /api/grupos/<grupo>/pausar` aceptan `{en_t_sim_min}` (0 o más); el servidor lo
  redondea hacia arriba a la hora en punto. Con la corrida ya `pausando`, una pausa con hora reemplaza a la pedida.
- `POST /api/corridas/<id>/intervenciones`: la entrada que recibe el motor ya va en EPSG:5345 y normalizada. 409 también si la
  corrida es una reproducción.
- `POST /api/grupos/<grupo>/pausar` (404 si no existe el grupo; 409 si alguna corrida no está en marcha): pausa todas en la
  hora pedida o, si no se pide o ya pasó para alguna, en la primera hora en punto a la que todas pueden llegar; si alguna
  estaba en pausa antes, la reanuda hasta esa hora; si igual alguna se pasa, las vuelve a alinear en la hora de la que quedó
  más adelante. Contesta `{grupo, en_t_sim_min, corridas: [resumen…]}`; la pantalla espera que las dos queden `pausada` con
  el mismo `pausa_t_sim_min`.
- `POST /api/grupos/<grupo>/intervenciones`, mismo cuerpo que la de una corrida: 409 si alguna no está en pausa, si están en
  pausa en horas distintas o si alguna es una reproducción. Contesta `{grupo, t_sim_min, respuestas: [{id, motor, aviso,
  error?}]}` (`aviso` nulo y `error` si ese proceso no contestó en 30 s; 504 si no contestó ninguno).
- El resumen de una corrida suma `pausa_t_sim_min` (hora de la pausa actual), `pausa_en_t_sim_min` (hora pedida para la
  próxima) y `reproduccion_de`. El detalle suma `bitacora_raiz`, `bitacora_integra` (verificación de la cadena, o nulo sin
  raíz) y `cortafuegos_iniciales` (los de `configuracion.cortafuegos`, normalizados).
- `cortafuegos.geojson`: una `LineString` en grados por trazo, con `properties` `origen` (`inicial` | `intervencion`),
  `ancho_m`, `suelo_mineral`, `longitud_dibujada_m`, `t_sim_min`, `t_vigor_min`, y lo que agregó el motor (por ejemplo
  `longitud_aplicada_m`, `estado`); los iniciales llevan `i`, los de la bitácora `n`.

## 5. Advertencia para quien escriba el servidor o las pruebas

En Windows no hay que dejar un hilo bloqueado leyendo una tubería que sea la entrada estándar de un proceso que carga
bibliotecas numéricas: congela esa carga. El proceso motor lo evita consultando las órdenes sin bloquear
(`app/motores/control.py`). Detalle en `F1_informe.md`.
