# Contrato entre los dos frentes — versión 1.1

Es el único punto donde se tocan el frente A (motores y datos) y el frente B (servidor e interfaz). Se cambia solo por pedido
de integración aprobado por las dos personas, subiendo el número de versión.

**Cambios de la 1.0 a la 1.1** (propuestos al implementar la fase F1, 2026-11-11; pendientes de aprobación de la otra persona):
`corrida.json` admite `base` para definir la corrida desde un escenario de los motores; el motor se lee de `corrida.json`;
el aviso `listo` trae la grilla de la huella; `final` y `error` traen más campos; las órdenes se consultan sin bloquear;
los resultados del motor quedan en `salida/`. La etiqueta `contrato-v1` apunta a la 1.0.

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

Al terminar, el proceso completa `corrida.json` con `bitacora` (pausas, reanudaciones y detención, con su minuto simulado) y
`resultados` (`ha_final`, `km2_final`, `t_simulado_h`, `s_computo`, `memoria_pico_mb`, `motivo_fin`, `completa`, `archivos`).

**Todavía no**: `configuracion.ignicion` con un punto libre (el clic en el mapa), viento manual y cortafuegos. Llegan con la
segunda parte de F1 y con F5; hasta entonces la ignición es la de la ficha del evento (`ignicion: snmf | altN`).

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

Para que el frente B no espere al A: `app/motores/proceso_simulado.py` cumple este contrato con un fuego de mentira (un círculo
que crece). Lo escribe el frente B y se usa en las pruebas del servidor. Desde el 2026-11-11 también se puede probar contra
los procesos reales, que ya cumplen este contrato.

## 4. Interfaz del servidor

La lista de pedidos HTTP está en el Anexo D de `00_plan.md`.

## 5. Advertencia para quien escriba el servidor o las pruebas

En Windows no hay que dejar un hilo bloqueado leyendo una tubería que sea la entrada estándar de un proceso que carga
bibliotecas numéricas: congela esa carga. El proceso motor lo evita consultando las órdenes sin bloquear
(`app/motores/control.py`). Detalle en `F1_informe.md`.
