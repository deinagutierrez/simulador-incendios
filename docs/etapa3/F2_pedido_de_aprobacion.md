# F2 — Servidor: pedido de aprobación

Para leer antes de empezar la fase F2. Cada punto trae una propuesta; alcanza con contestar "apruebo todo" o con la lista de
números que se quieren cambiar. Los puntos marcados **bloquea** hay que resolverlos antes de escribir código; los demás se
pueden contestar mientras la fase avanza.

Estado del que se parte: F1 terminada en la rama `f1-procesos-motor` (procesos motor, ignición en punto y hora libres,
prerregistro E-E3-1 evaluado). Contrato servidor–motor 1.1 aprobado por las dos personas.

## 1. Qué pide el plan para F2

Un servidor local que lanza y controla las corridas. Criterio de aceptación del plan (`00_plan.md` §3): una corrida de 48 h se
lanza, se pausa, se reanuda y se detiene desde la interfaz del servidor; el servidor sobrevive a la caída de un proceso motor y
lo informa; las pruebas corren sin internet. Esfuerzo estimado en el plan: 5 días.

## 2. Quién y cómo (cambios a la regla de trabajo)

| N.º | Propuesta | Por qué hace falta aprobarlo | |
|---|---|---|---|
| 1 | **La F2 la hace el frente que hizo la F1** (el usuario, con Claude), no el frente B como decía el plan | cambia el reparto de la decisión D-E3-12 | **bloquea** |
| 2 | **La rama `f1-procesos-motor` se une a `main` antes de empezar**, y la F2 se trabaja en una rama nueva, `f2-servidor` | la regla pide que la otra persona revise antes de unir a `main`. Hay que decir si la revisa o si autoriza a unirla sin revisión | **bloquea** |
| 3 | **La F2 se revisa al final**, de una vez, cuando la rama `f2-servidor` esté completa y con las pruebas en verde | para saber cuándo se le pide tiempo a quien revisa | |
| 4 | **Se anota en `decisiones.md` que el contrato 1.1 quedó aprobado**, con la fecha | hoy el contrato todavía dice "pendiente de aprobación" | |
| 5 | **El motor simulado** (contrato §3, un fuego de mentira para pruebas rápidas del servidor) **lo escribe el mismo frente** | el contrato decía que lo escribía el frente B | |

## 3. Qué entra en la F2 y qué no

| N.º | Entra | No entra (y cuándo llega) | |
|---|---|---|---|
| 6 | Crear una corrida eligiendo motor, punto de ignición, hora de inicio y duración; iniciar, pausar, reanudar y detener; avance hora por hora; lista de corridas; bitácora; huella de cada hora como imagen para el mapa | La pantalla completa (F3). En F2 hay solo una página mínima de prueba, sin diseño | **bloquea** |
| 7 | Los datos salen de un **evento con ficha** (hoy Las Lagunas 2024 y Las Chacras octubre 2023), como en la F1 | Bajar pronóstico e índices en el momento (F4). Los pedidos `/api/datos/…` del plan no se escriben todavía | **bloquea** |
| 8 | El pedido de intervenciones existe y contesta "rechazada" | Viento manual y cortafuegos (F5) | |
| 9 | **Modo "ambos"**: dos corridas a la vez, una por motor. Sirve además para medir la memoria que falta del prerregistro E-E3-3 | Comparación entre huellas y aviso de discrepancia (F3) | |
| 10 | — | Exportar el visor autónomo y el modo histórico con cicatriz, focos y métricas (F6 y F7) | |

## 4. Decisiones técnicas que se apartan del borrador del plan

| N.º | Propuesta | Alternativa descartada | |
|---|---|---|---|
| 11 | **El código va en `app/servidor/`**, y se arranca con un solo comando (`python app/servir.py`) que abre el navegador | un paquete instalable llamado `gemelo_sl`, como decía el plan: obliga a instalarlo y no aporta nada | |
| 12 | **El avance llega al navegador por un canal de una sola vía** (el servidor manda, el navegador escucha; técnica "eventos enviados por el servidor"). Las órdenes van por pedidos comunes | canal de dos vías (WebSocket): más piezas y más formas de fallar, y acá no hace falta | **bloquea** |
| 13 | **`corrida.json` sigue la forma del contrato 1.1** (`motor`, `base`, `configuracion`). El servidor agrega la versión del programa, el sha256 del congelado, la fecha de creación y el estado. Los campos del Anexo C que dependen de F4 y F5 (insumos bajados, viento, cortafuegos) se agregan en esas fases | escribir ya el Anexo C completo, con campos vacíos | **bloquea** |
| 14 | **El servidor no carga ningún motor.** Solo lanza procesos y lee sus avisos y la huella en disco | — (ya estaba en el plan; se confirma) | |
| 15 | **Como mucho dos corridas corriendo a la vez.** Una tercera se rechaza con un mensaje claro | cola de espera: complica el estado y hoy no hay caso de uso | |
| 16 | **Si el servidor se cierra con corridas en marcha, al volver las marca "interrumpida"** y conserva lo que quedó en disco. No las retoma | retomar una corrida a mitad: los motores no lo permiten sin tocarlos | |
| 17 | **Seguridad mínima:** el servidor escucha solo en `127.0.0.1` y además rechaza pedidos que no vengan de su propia página. Sin usuarios ni contraseñas | confiar solo en `127.0.0.1`: cualquier página abierta en el navegador podría mandarle órdenes | |
| 18 | **Puerto 8000**; si está ocupado prueba los siguientes y muestra la dirección | puerto fijo que falla si está ocupado | |
| 19 | **Sin bibliotecas nuevas.** FastAPI y uvicorn ya están en `requirements.txt`. Si hiciera falta otra, se pregunta antes | — | |

## 5. Pruebas y verificación

| N.º | Propuesta | |
|---|---|---|
| 20 | **Pruebas rápidas con el motor simulado** (segundos) para todo el control: crear, iniciar, pausar, reanudar, detener, caída del proceso, dos corridas a la vez, pedido desde otra página rechazado | |
| 21 | **Pocas pruebas con los motores reales**: una corrida de 6 h por motor lanzada por el servidor, comparada celda a celda con la corrida offline. Criterio: 0 celdas distintas | |
| 22 | **Las pruebas del servidor se suman a la verificación del clon y a la integración continua** (Windows y Linux). La verificación completa hoy tarda unos 5 minutos; se estima que sumará uno o dos | |
| 23 | **Al cerrar la F2 se repiten los siete pares de E-E3-1 lanzados por el servidor**, como comprobación. No reemplaza a la evaluación formal ya hecha, que fue sobre el proceso motor; si la otra persona puede, la evalúa ella | |

## 6. Un cambio chico de la F1 que conviene decidir ahora

| N.º | Propuesta | |
|---|---|---|
| 24 | **Si el clic cae en una celda que no quema, el programa corre el punto a la celda combustible más cercana antes de pasárselo al motor**, y avisa cuántos metros lo corrió. Hoy lo corre el motor con su regla vieja, que con un evento histórico busca dentro de la cicatriz y puede llevar el fuego lejos del clic. No toca los motores. Cambia una frase del contrato (pasaría a 1.2) | |

## 7. Lo que no bloquea la F2 pero sigue pendiente

- Protección de la rama `main` (la configura la dueña del repositorio).
- Licencia del código: el repositorio es público y no tiene archivo de licencia.
- Quién evalúa los prerregistros E-E3-2, E-E3-3 y E-E3-4. La excepción anotada (D-E3-13) vale solo para E-E3-1.
- La F1 se cerró sin "evento generado" (datos bajados en el momento): pasó a la F4. Falta anotarlo como decisión.

## 8. Cómo contestar

"Apruebo todo", o los números con lo que se quiere distinto. Los que bloquean el inicio son **1, 2, 6, 7, 12 y 13**. Lo que se
apruebe se anota en `decisiones.md` con la fecha y quién lo aprobó.
