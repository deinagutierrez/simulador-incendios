# F1 — Procesos motor: informe

Fecha: 2026-11-11 · Rama: `f1-procesos-motor` · Equipo: Windows 11, Intel de 20 núcleos lógicos, 32 GB, Python 3.14.7.
Rótulos: **(dato)** medido ese día en ese equipo · **(inferencia)** · **(sin verificar)**.

## 1. Qué quedó hecho y qué no

| Entregable de F1 en el plan | Estado |
|---|---|
| Un proceso por corrida que conduce a v4.0 o a v3.1 sin modificarlos | hecho (`app/motores/`) |
| Avance por hora simulada, con huella parcial en disco | hecho |
| Órdenes pausar, reanudar y detener | hecho |
| Salidas iguales a las de una corrida offline | hecho y verificado (§3) |
| Medición de tiempo y memoria (prerregistro E-E3-3) | hecha en un equipo (§4); falta el modo "ambos" y un segundo equipo |
| Ignición en un punto libre y a una hora libre | hecho (§8): `configuracion` en `corrida.json` |
| Corrida desde un evento **generado** (con datos bajados en el momento) | no hecho: hoy los datos son los de un evento con ficha. Llega con la fase de datos (F4) |
| Decisión sobre dónde viven los insumos de una corrida en tiempo real | **no tomada**; se toma al armar el primer evento generado (F4) |
| Intervenciones (viento manual, cortafuegos) | fase F5. La orden `intervenir` ya existe y responde `rechazada` |

## 2. Cómo se conduce cada motor sin tocarlo

- **v4.0** (`motor_v40.py`): los mismos pasos que `src/v4.0/scripts/correr_escenario.py`. El punto de control es una subclase de
  `Automata` que redefine `paso_tiempo`: cuando el reloj cae en hora en punto y antes de avanzar, avisa, guarda la huella y
  atiende órdenes. La subclase reemplaza a `simulador.corrida.Automata` dentro del proceso. Para detener se lanza una excepción
  propia, porque el bucle de SIM no ofrece otra salida; el proceso la atrapa y escribe los rásteres con `exportar_rasters`.
- **v3.1** (`motor_v31.py`): el camino sin validación de `src/v3.1/scripts/correr_escenario.py`. El punto de control es una
  subclase de `Simulacion` que redefine `_tablas_hora`, que el motor llama al empezar cada hora, antes de calcular el viento.
  Para detener se pone `max_pasos` en 0: el motor corta al terminar el paso en curso y guarda por su camino normal.
- Los dos paquetes se llaman `incendios_sl`: cada proceso carga uno solo, apuntando `sys.path` a su carpeta.
- (dato) Después de todas las corridas, `herramientas/congelado.py verificar` da los 244 archivos intactos.

Diferencias entre los dos conductores que conviene conocer:

| | v4.0 | v3.1 |
|---|---|---|
| Aviso `hora` | trae `exposicion` y `meteo` (los calcula SIM) | solo superficie y celdas activas |
| Hora 0 | 0,18 ha: la celda de ignición ya cuenta | 0 ha: la ignición entra en el primer paso |
| Corrida detenida | deja los rásteres y los `estado_hora_HH.json` hasta ese momento; sin `registro.json` ni resumen | deja todas las salidas normales, con motivo de fin 4 en `registro.json` |
| Valor por defecto de `definicion` | `variante: barreras`, `parar_en_cicatriz: off` | `variante: libre` o `libre_v2` |

Con un evento que tiene cicatriz, v4.0 activa sola la parada al igualar la superficie observada. En tiempo real no hay
cicatriz y la decisión D-E3-01 dice sin parada, por eso `definicion` la apaga salvo que se pida lo contrario.

## 3. Identidad con la corrida offline (prerregistro E-E3-1)

**Evaluación formal hecha el 2026-11-11 sobre el cambio `7cbe5b4`: se cumple.** Detalle, condiciones y límites en
`prerregistros/E-E3-1_resultado.md`. Por cada par: corrida offline con el guion del motor, proceso sin órdenes, y proceso con
una pausa y una reanudación a mitad de camino.

| Escenario | Motor | Horas simuladas | Superficie final | Celdas quemadas | Celdas distintas | Distintas con pausa |
|---|---|---|---|---|---|---|
| Caso La Aguada 2023 | v4.0 | 36 | 1.348 ha | 14.979 | **0** | **0** |
| Las Lagunas 2024, h1, SNMF | v4.0 | 48 | 12.839 ha | 142.659 | **0** | **0** |
| Las Lagunas 2024, h1, SNMF | v3.1 libre | 48 | 34.793 ha | 386.588 | **0** | **0** |
| Las Lagunas 2024, h1, SNMF | v3.1 librev2 | 48 | 32.915 ha | 365.724 | **0** | **0** |
| Las Chacras oct. 2023, alt4 | v4.0 | 72 | 2.356 ha | 26.181 | **0** | **0** |
| Las Chacras oct. 2023, alt4 | v3.1 libre | 45 de 72 | 1.526 ha | 16.954 | **0** | **0** |
| Las Chacras oct. 2023, alt4 | v3.1 librev2 | 46 de 72 | 3.065 ha | 34.054 | **0** | **0** |

- (dato) El criterio prerregistrado, 0 celdas distintas, se cumple en los siete pares, con y sin pausa.
- La evaluó el mismo frente que escribió el código, porque la otra persona no pudo (decisión D-E3-13).
- Los datos de Las Chacras salieron de la copia de trabajo anterior. Se corrió con ellos sin registrar en git; después se
  subieron al repositorio, sin cambios (decisión D-E3-15).
- (dato) En Las Chacras, v3.1 cortó sola a las 45–46 h por falta de propagación, igual offline que en el proceso.
- Además, `test/app/test_procesos.py` repite la identidad en 6 horas de Las Lagunas con los tres motores en cada cambio
  (19 pruebas, unos dos minutos), más avisos, pausa, detener e ignición libre.

## 4. Tiempo y memoria (prerregistro E-E3-3, medición parcial)

Medido en la tanda de la evaluación formal (proceso sin órdenes).

| Escenario | Motor | Segundos de cómputo | Por hora simulada | Memoria pico |
|---|---|---|---|---|
| La Aguada 36 h (1.348 ha) | v4.0 | 12,5 | 0,35 s | 226 MB |
| Las Lagunas 48 h (12.839 ha) | v4.0 | 85,1 | 1,77 s | 536 MB |
| Las Lagunas 48 h (34.793 ha) | v3.1 libre | 26,5 | 0,55 s | 865 MB |
| Las Lagunas 48 h (32.915 ha) | v3.1 librev2 | 16,1 | 0,34 s | 878 MB |
| Las Chacras 72 h (2.356 ha) | v4.0 | 25,5 | 0,35 s | 498 MB |
| Las Chacras 45 h (1.526 ha) | v3.1 libre | 14,0 | 0,31 s | 864 MB |
| Las Chacras 46 h (3.065 ha) | v3.1 librev2 | 14,9 | 0,32 s | 877 MB |

- (dato) La memoria de v4.0 por proceso, que nunca se había medido, es de unos 0,2 a 0,5 GB. La de v3.1, 0,9 GB.
  (inferencia) Los dos motores a la vez caben holgados en 8 GB; el requisito de 16 GB para el modo "ambos" del plan parece
  conservador. Falta medirlo corriendo los dos juntos.
- (dato) Metas del prerregistro: v3.1 ≤ 0,5 s por hora y v4.0 ≤ 3 s por hora con unas 30.000 ha. v3.1 dio entre 0,31 y
  0,55 s; el valor más alto, apenas por encima de la meta, es con un incendio de 35.000 ha. v4.0 dio 1,77 s con 12.839 ha:
  cumple, pero con menos superficie que la de la meta.
- (dato) La medición se mueve entre tandas: Las Lagunas con v3.1 librev2 dio 0,57 s por hora en la tanda anterior y 0,34 s en
  esta. (sin verificar) Por qué. No es la medición formal de E-E3-3.
- (dato) El tiempo incluye la carga de insumos: unos 4 s en cada motor antes de la primera hora.
- (sin verificar) Un segundo equipo y Linux.

## 5. Problema encontrado: el proceso se colgaba en la primera hora

- (dato) Lanzado a mano funcionaba. Lanzado con la entrada estándar como tubería, que es como lo lanza el servidor, avisaba la
  hora 0 y no avanzaba más.
- (dato) Volcado de hilos: el hilo principal estaba dentro de la carga de una biblioteca (`scipy.linalg`, que numba importa
  en la primera compilación) y otro hilo estaba bloqueado leyendo la entrada estándar.
- (inferencia) En Windows, una lectura bloqueante pendiente sobre esa tubería traba a cualquier otro uso del mismo extremo, y
  las bibliotecas numéricas en Fortran consultan la entrada estándar al iniciarse.
- (dato) Solución: no hay ningún hilo esperando. Las órdenes se consultan sin bloquear al cumplirse cada hora simulada
  (`PeekNamedPipe` en Windows, `select` en Linux), que es cuando se atienden de todos modos. Con eso los dos motores corren y
  cierran solos.
- Queda como advertencia en el contrato (§5) para quien escriba el servidor.
- Para diagnosticar algo parecido: con la variable de entorno `SIMULADOR_DIAGNOSTICO_S=25`, el proceso vuelca a `proceso.log`
  dónde está cada hilo cada 25 segundos.

## 6. Cambios al contrato

El contrato pasa de la versión 1.0 a la 1.1 (`contrato_servidor_motor.md`). Lo que cambia para el frente B: la corrida se
define con `base` en `corrida.json`; el aviso `listo` trae la grilla de la huella; los resultados del motor quedan en
`salida/`; las órdenes se atienden en hora en punto. Aprobado por las dos personas el 2026-11-11 (decisión D-E3-16).

## 7. Lo que sigue

1. Fase de datos (F4): pronóstico e índices bajados en el momento, y con ellos el primer evento generado.
2. Paquete de datos históricos y `bajar_historicos.py`, para los otros 13 eventos.
3. Medir el modo "ambos" y repetir las mediciones en un segundo equipo y en Linux.

## 8. Segunda parte: ignición en un punto y una hora elegidos

**Cómo funciona.** Los dos motores sacan los puntos y la hora de ignición de la ficha del evento, con la misma función
(`incendios_sl.config.cargar_evento`). `app/motores/ignicion.py` envuelve esa función dentro del proceso y le entrega al motor
la misma ficha con dos datos cambiados: los puntos y la hora de inicio. No se escribe ningún archivo en `escenarios/` ni en
`datos/`, y ningún archivo de los motores cambia. El evento sigue aportando la meteorología, los índices y la cobertura.

**Cómo se pide.** En `corrida.json`, junto a `base.definicion`:

```json
"configuracion": {"ignicion": [{"lon": -65.55, "lat": -32.64}], "t_inicio_utc": "2024-09-19T16:00:00Z", "horas": 24}
```

**Qué se verificó** (dato, `test/app/test_procesos.py`, tres motores):

| Prueba | Resultado |
|---|---|
| Pedir por `configuracion` los mismos puntos y la misma hora que trae la ficha de Las Lagunas 2024 da la misma huella que la corrida offline | 0 celdas distintas en v4.0, v3.1 libre y v3.1 librev2 |
| Pedir un punto sobre pastizal y otra hora (19/9/2024 16 UTC, 3 h): el fuego empieza en la celda pedida y a la hora pedida | pasa en los tres |
| Pedir un punto fuera del dominio | rechazado con aviso de error, sin simular |
| Pedir una hora fuera de la serie meteorológica del evento | rechazado con aviso de error, sin simular |

**Límites.**

- Si el punto cae en una celda que no quema, cada motor lo corre a la celda combustible más cercana, con su regla de siempre.
  Cuando el evento base tiene cicatriz de referencia, la busca **dentro de la cicatriz**, que puede estar lejos del clic. El
  proceso informa el corrimiento en `resultados.ignicion.usada[].desplazada_m` y la pantalla tiene que mostrarlo. Con un
  evento generado, que no tiene cicatriz, el corrimiento es a la combustible más cercana.
- La hora de inicio tiene que caer dentro de la serie meteorológica del evento base. Si cae afuera, el proceso la rechaza
  antes de simular, con un aviso de error que dice de cuándo a cuándo hay datos.
- Todos los puntos empiezan a la misma hora. No hay igniciones escalonadas.
- No es todavía "tiempo real": falta bajar el pronóstico y los índices (F4).
