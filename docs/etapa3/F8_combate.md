# F8 — Combate del fuego: bomberos y medios aéreos

Fecha: 2026-11-24. Rama `combate`. Decisión D-E3-36. Contrato 1.6.

Hasta la F7 el simulador no incluía el combate (decisión D42 del plan, §1.2: "propagación libre más barreras y sin
combate"). Esta fase lo suma como dos mitigaciones nuevas, al lado de los cortafuegos y del viento a mano:

1. **Bomberos en tierra** (dotaciones que construyen línea).
2. **Medios aéreos** (descargas de avión hidrante o de helicóptero).

Se planeó en tres etapas, cada una probada sola:

| Etapa | Qué | Estado |
|---|---|---|
| 1 | Dotaciones de bomberos: antes de iniciar y en pausa, con la llegada estimada desde los cuarteles | hecha |
| 2 | Descargas aéreas marcadas en el mapa en pausa: agua (vence) o retardante | hecha |
| 3 | Táctica dibujada: línea de ataque de cada dotación y línea de descargas sucesivas | **no se hace**: el usuario probó las dos primeras el 2026-11-24, las dio por buenas y decidió dejar la fase ahí |

## 1. La decisión de fondo: un solo método para los dos motores

Los dos motores traen una contención propia (v3.1 `Simulacion._contener_hora`; v4.0 `ca/contencion.py`). Se parecen, pero no
son iguales: v3.1 trabaja al cambio de hora y v4.0 en cada paso de 2 minutos, y en las dos lo aéreo solo sube el umbral de
sostén de 1.700 a 3.500 kW/m, que en la evaluación de docs/v4.0/13 §7 no cambió ningún resultado.

El pedido fue que el combate sea **el mismo en los dos motores: el mismo método y todo**. Por eso la app no usa ninguna de
las dos contenciones. El combate se decide en un módulo aparte, `app/motores/combate.py`, que no importa ningún motor, con
las mismas reglas, los mismos parámetros y el mismo orden para los dos. Cada motor aporta solo lo que es suyo, por medio de
un adaptador (`combate_v40.py`, `combate_v31.py`):

| Lo decide el método común (`combate.py`) | Lo aporta cada motor (adaptador) |
|---|---|
| cuánta línea se produce y cuándo | qué celdas arden y pueden propagar |
| qué celdas del borde pueden recibir línea y cuáles se eligen | con qué intensidad arde cada celda hacia cada vecina |
| qué enlaces corta la línea | cómo se frena una celda en su autómata |
| cuándo escapa una celda y con qué sorteo | cómo vuelve a propagar una celda |
| qué moja una descarga, cuánto dura y qué pasa al secarse | cómo se bloquea y desbloquea una celda sin quemar; en qué celda cae un punto; qué hora del día es |

Es normal que los dos motores no combatan en el mismo lugar: el fuego de cada uno es distinto (v3.1 adelanta, v4.0 atrasa).
El método es el mismo; el frente sobre el que trabaja, no.

Consecuencias que hay que conocer:

- **No se toca ningún archivo de `src/`** (`congelado.json` sigue intacto). Los adaptadores usan las piezas que cada motor ya
  expone: en v4.0 el gancho `Automata.filtro_enlaces`, la física de celdas arbitrarias y la cola de igniciones; en v3.1 el
  estado CONTENIDA de su autómata y sus primitivas de numba.
- **Sin combate, nada cambia.** El adaptador prepara el motor recién con la primera intervención de combate
  (`habilitar()`). Una corrida sin dotaciones ni descargas es idéntica a las de siempre, bit a bit, y sigue dando lo mismo
  que la corrida offline (E-E3-1).
- **El combate no tiene corrida offline equivalente** (comparación B de E-E3-4): el motor offline no conoce este método. Su
  garantía de reproducibilidad es la **comparación A**: la reproducción desde la bitácora da la misma cadena de hash y 0
  celdas distintas, en la huella y en la línea. Los cortafuegos y el viento a mano de la misma corrida conservan sus archivos
  para la corrida offline, pero una corrida con combate ya no se puede repetir offline entera.
- **Una sola cadencia: una vez por hora.** El paso de combate corre en la hora en punto, después de las intervenciones de
  esa hora y con la meteorología de la hora que empieza. Es la única cadencia que los dos motores permiten por igual sin
  modificarlos (v3.1 solo ofrece ganchos al cambio de hora). Por eso todos los tiempos del combate se cuentan en horas
  enteras: el agua de una descarga dura una hora, y la línea que una dotación construye durante una hora se coloca al
  cumplirse esa hora.
- Si la corrida viene de un escenario que ya trae encendida la contención propia del motor (variantes `contencion`, `local`…),
  el combate de la app no se le suma: la intervención se rechaza con ese motivo.

## 2. El método

### 2.1 Línea

Una **celda de línea** no deja pasar el fuego: una celda que ardía cuando recibió la línea queda *frenada* (deja de
propagar y termina de quemarse por la regla normal del motor); una celda sin quemar queda *bloqueada* (no puede encenderse).
El fuego tampoco pasa a través de la línea: en diagonal por la esquina de dos celdas de línea, ni con los saltos de caballo
de la vecindad de 16 (`combate.cortado`, la misma regla que `_cortado_por_contencion` de v3.1 y `contencion.cortado` de
v4.0; las pruebas comprueban que dan lo mismo).

Cada celda de línea tiene una clase (línea de bomberos, agua, retardante), el minuto desde el que es línea y, si es
temporal, el minuto en que vence.

### 2.2 Dotaciones (etapa 1)

Intervención `dotacion`: `{bomberos, llegada_min, prioridad}`. Cada despacho suma `bomberos` personas que empiezan a
trabajar `llegada_min` minutos después y producen **20 m de línea por hora y por persona**. `{retirar: true}` retira a
todas.

En cada hora en punto:

1. **Producción.** Cada dotación acumula lo que produjo en la hora que terminó (prorrateado si llegó o se fue a mitad de la
   hora). Si no tiene dónde trabajar guarda, a lo sumo, una hora de producción.
2. **Dónde.** Candidatas: celdas que arden, sin línea, del **perímetro exterior** (con alguna vecina inmediata combustible,
   no cortada por la línea, conectada con el exterior del incendio; las islas sin quemar de adentro no justifican línea),
   cuya intensidad hacia sus vecinas libres es menor que **1.700 kW/m** (ataque directo). Con el frente más intenso no se
   puede trabajar.
3. **Táctica: ancla y flancos.** La línea crece por celdas contiguas (8 vecinas) a la que ya existe. Entre las contiguas
   se elige la de menor intensidad (`prioridad: flancos`) o la de mayor intensidad sostenible (`cabeza`). Sin contiguas se
   abre un ancla nueva en la celda de menor intensidad (la cola). Cada celda cuesta su resolución (30 m).

La línea de una hora se coloca **al cumplirse**, sobre el borde que tiene el fuego en ese momento. Un despacho hecho en la
pausa de la hora 5 con llegada 0 trabaja de la 5 a la 6 y su primera línea aparece en la hora 6.

### 2.3 Escapes

En cada hora, una celda frenada cuya intensidad potencial hacia alguna vecina libre supera **3.500 kW/m** escapa con
probabilidad **0,5**. El sorteo es un hash de la celda y la hora (el mismo splitmix64 de las barreras de los dos motores):
reproducible e independiente del orden. La celda sale de la línea y vuelve a propagar desde ese momento.

### 2.4 Descargas aéreas (etapa 2)

Intervención `descarga`, solo en pausa: `{medio, producto, xy_5345}` con dos puntos, dónde empieza la franja y hacia dónde
va. La franja es recta, con el largo y el ancho del medio:

| Medio | Franja | Tope por hora | Supuesto |
|---|---|---|---|
| `avion` (avión hidrante) | 150 × 20 m | 12 | AT-802, unos 3.000 L; ciclo de 20 minutos, hasta 4 aviones |
| `helicoptero` (con helibalde) | 45 × 15 m | 16 | unos 1.000 L; ciclo de 7 a 8 minutos, hasta 2 helicópteros |

Las celdas de la franja son las que toca su eje (muestreado cada 1/8 de celda, así no quedan huecos) y, si la franja fuera
más ancha que una celda, las que tienen el centro a menos de medio ancho. En la grilla de 30 m una franja tiene una celda de
ancho. Pasan a ser línea en el acto:

- las que **arden** quedan frenadas si su intensidad hacia las vecinas libres es menor que **3.500 kW/m**. Con más, la
  descarga no las frena (la intervención queda `recortada` y lo dice);
- las que **todavía no ardieron** quedan bloqueadas: el fuego no entra.

Con **agua** la línea es temporal: dura **una hora** y vence. Con **retardante** queda hasta el final. Solo se descarga **de
día** (de 11 a 22 UTC, de 8 a 19 h de Argentina) y hasta el tope por hora de cada medio.

**Al vencer el agua** las celdas dejan de ser línea. Las bloqueadas vuelven a ser combustible. Vuelven a propagar, si en ese
momento el fuego puede avanzar (intensidad mayor que cero hacia una vecina libre): las que estaban frenadas, y las celdas ya
quemadas pegadas a una celda que se seca. Las que todavía arden siguen solas. Si en ese momento el fuego no puede avanzar
(de noche, con humedad), ahí quedó apagado. **El agua no apaga: da tiempo.**

**Consolidación.** Las dotaciones, antes de construir línea nueva, aseguran el agua que está en contacto con el fuego (las
celdas frenadas y las bloqueadas pegadas a una celda afectada), primero la que vence antes: pasa a ser línea de bomberos,
que ya no vence. Es la forma de aprovechar la hora que da una descarga, y por eso en el paso horario va antes de los
vencimientos: es el trabajo de esa hora.

**Brechas.** Una celda bloqueada (agua o retardante sobre combustible sin quemar) a la que el fuego llega con más de
3.500 kW/m cede con probabilidad 0,5 por hora, con el mismo sorteo de los escapes (otro número de enlace en el hash).

### 2.5 Orden del paso horario

1. escapes y brechas;
2. producción de las dotaciones en la hora que terminó;
3. consolidación del agua en contacto con el fuego;
4. vencimientos;
5. línea nueva.

Va después de las intervenciones de la hora (en la pausa) y antes de que el fuego avance. En la pantalla, la línea que se
construye en la hora de una pausa aparece al reanudar.

## 3. Parámetros

Son los de docs/v4.0/10 y 13 (hauling chart de Andrews y Rothermel, reportes del SNMF). **Todos son supuestos sin calibrar
para esta herramienta** [HIPÓTESIS]. Se informan en `resultados.combate.parametros` de cada corrida.

| Parámetro | Valor | De dónde sale |
|---|---|---|
| Producción de línea | 20 m/h por bombero | docs/v4.0/13 §4 (`m_h_por_bombero`); el SNMF da 8 a 21 m/h por persona, con pocos datos |
| Ataque directo en tierra | hasta 1.700 kW/m | docs/v4.0/10 (llama de 2,4 m) |
| Escape | más de 3.500 kW/m, probabilidad 0,5 por hora | docs/v4.0/10 |
| Lo que una dotación puede guardar | 1 hora de producción | docs/v4.0/10 (`acumular_max_h`) |
| Costo de una celda | su resolución (30 m) | docs/v4.0/10 |
| Aviso y alistamiento (llegada estimada) | 30 min y 15 min, más el viaje por la red vial | docs/v4.0/13 §6 |
| Ataque directo desde el aire | hasta 3.500 kW/m | docs/v4.0/10 (`intensidad_sostener_aereo_kw_m`) |
| Franja y ciclo de cada medio | tabla de §2.4 | orden de magnitud de un AT-802 y de un helibalde; cantidad de aeronaves de docs/v4.0/13 §2.2 |
| Duración del agua | 1 hora | la menor que permite la cadencia horaria; en el terreno va de minutos a una hora |
| Horario de vuelo | de 11 a 22 UTC | docs/v4.0/13 §6 (`aereo_horas_vuelo_utc`) |

## 4. Dónde está cada cosa

| Pieza | Archivo |
|---|---|
| Método común | `app/motores/combate.py` |
| Adaptadores | `app/motores/combate_v40.py`, `app/motores/combate_v31.py`; el del motor simulado, en `proceso_simulado.py` |
| Validación de las intervenciones | `app/motores/intervenciones.py` |
| Enganche en los conductores | `motor_v40.py` (`AutomataControlado.paso_tiempo`), `motor_v31.py` (`SimulacionControlada._contener_hora`) |
| Aviso `combate` y línea en disco | `app/motores/control.py` (`combate`, `guardar_combate`; `combate_parcial.npy`) |
| Servidor | `app/servidor/app.py` (pedidos), `huella.py` (`linea_png`), `trazos.py` (`descargas_geojson`), `arribo.py` (llegada desde los cuarteles) |
| Pantalla | `app/web/app.js` (bloque «combate»), `index.html`, `estilo.css` |
| Pruebas | `test/app/test_combate.py` (método), `test_combate_v40.py`, `test_combate_v31.py` (+ `ayudante_combate_v31.py`), `test_servidor_combate.py`, `test_combate_motores.py` |

## 5. Límites que hay que decir

- El combate es un supuesto simplificado y **no está calibrado**. Sirve para comparar alternativas (con y sin dotaciones, más
  temprano o más tarde, flancos o cabeza), no para planificar un operativo ni para estimar cuántos bomberos hacen falta.
- La línea se coloca una vez por hora. Dentro de la hora el fuego corre libre: un frente rápido se aleja de la línea de la
  hora anterior.
- Con las intensidades que dan los motores en estos eventos, casi todo el borde es sostenible (menos de 1.700 kW/m) y casi
  no hay escapes (docs/v4.0/13 §7 ya lo observó). El resultado depende sobre todo de cuántos metros de línea por hora se
  despachan frente a cuánto crece el perímetro.
- En v4.0 el fuego arranca despacio: una dotación chica despachada temprano puede contenerlo entero en las primeras horas.
  En v3.1, con el mismo despacho, el fuego ya es mucho más grande. No es un error del combate: es la diferencia entre los
  motores, que la pantalla muestra lado a lado.
- v4.0 puede terminar antes por su regla de 12 horas sin avance cuando el fuego queda contenido; v3.1 sigue hasta el final
  por si hay escapes. Es una diferencia de cada motor en cómo da por terminada la corrida, no del combate.
- Una descarga moja una franja de una celda de ancho (30 m), aunque la franja real mida 15 o 20 m: es lo mínimo que la grilla
  puede representar, y favorece a la descarga.
- El agua dura exactamente una hora simulada y se seca toda junta. No depende del viento, de la temperatura ni del
  combustible.
- Una franja de 150 m es chica frente a un frente de kilómetros: hacen falta muchas descargas, y hay un tope por hora. Marcar
  de a una es lento. Lo habría resuelto la etapa 3 (una línea de descargas sucesivas), que no se hace.
- Las dotaciones no tienen posición ni tiempo de traslado: el método decide en cada hora dónde rinde más su trabajo (primero
  asegurar el agua en contacto con el fuego, después ancla y flancos) y las pone ahí en el acto, aunque la hora anterior
  hayan trabajado a kilómetros. También era parte de la etapa 3 (que el usuario dibuje dónde trabaja cada dotación).
- En el modo "ambos" la misma descarga cae sobre dos fuegos distintos: puede frenar fuego en un motor, mojar combustible sin
  quemar en el otro, o rechazarse en uno solo (si ahí esas celdas ya se quemaron).

## 6. Cómo probarlo

```
python app/servir.py
```

1. **Bomberos desde el inicio.** En «2. Configurar simulación», abajo de los cortafuegos, está «Combate: bomberos». Poner la
   cantidad, elegir un cuartel en «Estimar la llegada por la red vial» (o escribir los minutos) y «Sumar a la corrida». Se
   pueden sumar varias dotaciones con distintas llegadas.
2. **Bomberos y descargas en pausa.** Iniciar, poner una hora en «Pausar en la hora» y pausar. En «Intervenir en la hora N»
   aparecen «Combate: bomberos» (despachar más, o retirar a todos) y «Combate: medios aéreos»: elegir el medio y el
   producto, «Marcar descargas», y sobre el mapa apretar donde empieza la descarga, arrastrar hacia donde va y soltar.
   «Lanzar las descargas» las aplica.
3. **Qué mirar.** En el mapa, la línea de los bomberos en negro, el agua en azul y el retardante en magenta, hora por hora
   con el deslizador. En la tarjeta de cada motor, el bloque «Combate» (línea en pie, lo construido en la hora, borde sin
   línea, agua en pie, escapes) y la bitácora. «Reproducir» repite la corrida desde la bitácora.
4. **Con «Ambos»** se ve el mismo combate sobre los dos fuegos, lado a lado.
