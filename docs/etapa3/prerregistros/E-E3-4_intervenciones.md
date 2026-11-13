# Prerregistro E-E3-4 — Las intervenciones son reproducibles

Escrito el 2026-11-10, antes de escribir el código de intervenciones. Se congela con la etiqueta `prerregistro-E-E3-4`.
Escribe: deinagutierrez · Evalúa (la otra persona): LisandroV2002 (decidido por el usuario el 2026-11-13). El diseño y el criterio
no cambian respecto de la etiqueta; solo se agregan los nombres.

## Pregunta
¿Una corrida con cortafuegos dibujados y cambios de viento hechos en pausa se puede reproducir, primero desde su bitácora y
después con el motor offline?

## Diseño
Cinco corridas sobre Las Lagunas 2024, de 48 h, en cada motor (v4.0, v3.1 librev2 y v3.1 libre):

| Corrida | Intervenciones |
|---|---|
| 1 | un cortafuego de 10 m dibujado antes de iniciar |
| 2 | un cortafuego de 10 m agregado en pausa a las 6 h, delante del frente |
| 3 | dos cortafuegos (6 m y 25 m) agregados en pausas a las 6 h y a las 12 h; uno de ellos pasa en parte sobre celdas ya quemadas |
| 4 | viento manual a las 8 h (cambio de dirección de 90°) y vuelta al pronóstico a las 20 h |
| 5 | combinación de 3 y 4 |

Los trazos y las horas se fijan en un archivo que se sube junto con este prerregistro antes de correr.

## Comparaciones
- **A. Desde la bitácora**: el simulador repite la corrida leyendo `corrida.json`.
- **B. Offline**: `correr_escenario.py` del motor, con los mismos trazos cargados desde el inicio (recortados a las celdas que
  no estaban quemadas en el momento de la pausa) y la serie meteorológica editada por horas.

## Criterio, fijado antes de correr
- A: **0 celdas distintas** en el tiempo de llegada.
- B: IoU de la huella final ≥ 0,99 y la misma longitud de cortafuego, en cada motor.

En v4.0 el viento manual gira de forma gradual durante la hora siguiente y en v3.1 cambia de golpe en la hora de la pausa: es
lo esperado y no cuenta como falla.

## Si no se cumple
Se revisan el recorte de los trazos y el momento en que entra en vigor cada intervención. No se toca el motor.

## Límites declarados
Un solo evento. No dice si un cortafuego real detendría el fuego: solo que el programa hace lo que registra.
