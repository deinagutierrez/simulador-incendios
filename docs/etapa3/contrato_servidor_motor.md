# Contrato entre los dos frentes — versión 1.3

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
| `configuracion.t_inicio_utc` | hora de inicio con huso, por ejemplo `2024-09-19T16:00:00Z`. Reemplaza a la hora de la ficha |
| `configuracion.horas` | duración; pisa a `base.definicion.horas` |

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

Al terminar, el proceso completa `corrida.json` con `bitacora` (pausas, reanudaciones y detención, con su minuto simulado) y
`resultados` (`ha_final`, `km2_final`, `t_simulado_h`, `s_computo`, `memoria_pico_mb`, `motivo_fin`, `completa`, `archivos`,
e `ignicion` = `{pedida, usada: [{id, lon, lat, desplazada_m?}], t_inicio_utc}`).

**Todavía no**: viento manual y cortafuegos (fase F5), y eventos armados con datos bajados en el momento (fase F4).
Hasta entonces los datos son los de un evento con ficha.

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
| `{"orden": "reanudar"}` | sigue |
| `{"orden": "detener"}` | cierra la corrida y guarda lo simulado hasta ahí |
| `{"orden": "intervenir", "entrada": {…}}` | solo en pausa. Hoy responde `rechazada`: llega con la fase F5 |

El motor mira las órdenes **al cumplirse cada hora simulada**, no en el medio. Una orden enviada a mitad de una hora se
atiende al terminar esa hora. Si el servidor cierra la tubería mientras la corrida está en pausa, el motor la da por detenida
y guarda.

**Avisos** (motor → servidor, una línea JSON por la salida estándar; por ahí no sale nada más):

| Aviso | Campos |
|---|---|
| `listo` | `t0_utc`, `grilla` = `{crs, xmin, ymax, res, filas, cols}`. Llega una vez, antes de la primera `hora` |
| `hora` | `h` (0, 1, 2…), `t_sim_min`, `ha`, `activas`, `s_computo`, `huella`. En v4.0 además `exposicion` (viviendas afectadas y amenazadas, km de tendido, km de caminos) y `meteo` |
| `pausado` | `t_sim_min`, siempre múltiplo de 60 |
| `intervencion` | `n`, `estado` (`aceptada`, `recortada`, `rechazada`), `t_vigor_min`, `motivo` |
| `final` | `motivo`, `texto`, `ha`, `t_sim_min`, `s_computo`, `memoria_pico_mb`, `completa` (falso si se detuvo), `salida`. Es el último aviso; el proceso termina con código 0 |
| `error` | `mensaje`, `fatal`. Con `fatal: true` el proceso termina con código 1 |

`s_computo` no cuenta el tiempo en pausa.

**Huella.** `t_llegada_parcial.npy` en la carpeta de la corrida: matriz `float32` con los minutos desde el inicio en que el
fuego llegó a cada celda, `NaN` donde no llegó. Su forma y su posición son las de `grilla` en el aviso `listo`: con un evento
es el dominio completo (1.671 × 1.672); con un caso de prueba de v4.0 es la ventana del caso. El motor la reescribe en cada
hora de forma atómica, así que siempre se puede leer entera.

**Otros archivos de la carpeta.** `salida/` con lo mismo que deja una corrida offline del motor (en v4.0,
`hora_llegada_min.tif`, `serie_indicadores.csv`, `estado_hora_HH.json`, `perimetros_horarios.geojson`…; en v3.1,
`t_llegada_s.tif`, `serie_horaria.csv`, `registro.json`…); `proceso.log` con todo lo que imprime el motor;
`escenario_base.yaml` si la corrida vino por `definicion`.

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

## 4. Interfaz del servidor

`python app/servir.py` levanta el servidor en `http://127.0.0.1:8000` (o el puerto libre siguiente). Solo atiende pedidos de
su propia página: los que traen otro origen se rechazan con 403.

| Pedido | Qué hace |
|---|---|
| `GET /api/estado` | versión, motores, eventos con datos en el clon (con su rango meteorológico y los puntos de su ficha), recuadro del dominio, límite de corridas |
| `POST /api/corridas` | crea una corrida; con `motor: "ambos"` crea dos (v4.0 y v3.1 librev2) con el mismo `grupo`; con `iniciar: true` las lanza. Cuerpo: `motor`, `evento`, `ignicion` `[{lon, lat}]`, `t_inicio_utc`, `horas` (1 a 240), y opcionales `hipotesis`, `ignicion_ficha`. Uso avanzado: `definicion`, igual a `base.definicion` |
| `GET /api/corridas` | lista, de la más nueva a la más vieja |
| `GET /api/corridas/<id>` | estado, última hora avisada, recuadro de la huella; al terminar, bitácora y resultados |
| `POST /api/corridas/<id>/{iniciar,pausar,reanudar,detener}` | control. Contesta 409 si la orden no corresponde al estado |
| `POST /api/corridas/<id>/intervenciones` | solo en pausa; devuelve el aviso `intervencion` del motor (hoy `rechazada`) |
| `GET /api/corridas/<id>/eventos` | avance en vivo por un canal de una sola vía (`text/event-stream`). Cada evento es un aviso del motor o un cambio de estado, numerado con `n`; con `?desde=N` manda los posteriores al N. Cierra con un evento `cierre` |
| `GET /api/corridas/<id>/quemado.png?hora=N` | huella hasta la hora N (o completa), lista para superponer en un mapa web con el recuadro `huella.limites` |
| `GET /api/corridas/<id>/quemado.png?hora=N&color=rrggbb` | con `color`, la huella de un solo color (para comparar dos motores) |
| `GET /api/corridas/<id>/perimetro.geojson?hora=N` | contorno del área quemada hasta la hora N, en grados |
| `GET /api/corridas/<id>/exportar` | zip con `corrida.json`, las salidas del motor y `perimetros_por_hora.geojson`. Solo con la corrida terminada |
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

Todavía no existen los pedidos del borrador del plan (Anexo D) para bajar datos (F4), el visor autónomo (F7) ni el modo
histórico (F6).

## 5. Advertencia para quien escriba el servidor o las pruebas

En Windows no hay que dejar un hilo bloqueado leyendo una tubería que sea la entrada estándar de un proceso que carga
bibliotecas numéricas: congela esa carga. El proceso motor lo evita consultando las órdenes sin bloquear
(`app/motores/control.py`). Detalle en `F1_informe.md`.
