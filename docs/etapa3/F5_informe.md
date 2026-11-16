# F5 — Intervenciones: informe

Fecha: 2026-11-14 · Rama `f5-intervenciones` · Pedido aprobado: `F5_pedido_de_aprobacion.md` (D-E3-28, D-E3-29).
Hecho por el frente A (el usuario, con Claude). Para revisar: la otra persona, con la rama completa.

## 1. Qué se pidió y qué quedó

| Criterio de aceptación del plan (§3) | Estado |
|---|---|
| E-E3-4: reproducción desde la bitácora idéntica | **pendiente de la otra persona** (LisandroV2002). Guion listo: `herramientas/e_e3_4.py --evaluador LisandroV2002`. Trazos y horas fijados y etiquetados antes del código (`prerregistro-E-E3-4-trazos`) |
| E-E3-4: equivalencia con la corrida offline con los mismos trazos desde el inicio | ídem |

Lo que hace ahora el simulador:

- **Cortafuegos a mano alzada** en la pantalla, antes de iniciar o con la corrida en pausa: trazo libre, borrador, deshacer,
  ancho de 3, 6, 10, 15 o 25 m, "a suelo mineral (supuesto)", longitud en vivo. El servidor los pasa a EPSG:5345.
- **Viento manual en pausa** y vuelta al pronóstico. v3.1 cambia de golpe; v4.0 gira durante la hora siguiente.
- **Bitácora encadenada** con hash (sha256), escrita en el momento (`bitacora.jsonl`) y visible en vivo; la pantalla dice si la
  cadena verifica.
- **Reproducir** una corrida desde su bitácora (botón en la tarjeta; `POST /api/corridas/<id>/reproducir`).
- **Modo "ambos"**: pausa e intervención por grupo, las dos corridas en la misma hora.
- **Las corridas empiezan en hora en punto** (D-E3-28, punto 6).
- **Contrato 1.5** (`contrato_servidor_motor.md`).

## 2. Verificación (2026-11-14)

| Qué | Resultado |
|---|---|
| `./probar.sh` | "Todo funciona": congelado intacto (244 archivos), suites de v3.1 y v4.0, corridas cortas, `test/app` 178 pasan y 2 se omiten |
| E-E3-1 repetido (los siete pares, sin intervenciones) | **0 celdas distintas** en los siete, con y sin pausa: la matriz de barreras vacía de v3.1 y el resto de los cambios no alteran nada |
| v3.1: matriz vacía contra barreras apagadas (12 h, `libre` y `libre_v2`) | 0 celdas distintas |
| v3.1: función real `preparar_barreras_enlaces` envuelta contra la copia en ventana (4 trazos) | iguales; 4,9 a 5,2 s la real, 0,04 s la copia; el producto compartido del dominio no se toca |
| v3.1 y v4.0: trazo en pausa contra el mismo trazo recortado desde el inicio, con viento manual y suelo mineral, por `correr_escenario.py` | 0 celdas distintas en los dos motores |
| v3.1 y v4.0: reproducción desde la bitácora | cadena de hash igual y 0 celdas distintas |
| v3.1 y v4.0: trazo antes de iniciar contra el mismo trazo a t = 0 | 0 celdas distintas |
| v4.0: casos sintéticos (diagonal, a través de lo quemado, vecindad 16, suelo mineral, modo umbral) | t_llegada, estado, cruces y bloqueos idénticos |
| v4.0: tiempo por cortafuego en el dominio completo | 0,07 a 0,10 s; viento 0,01 s |
| Pantalla, en Chromium sin ventana, con el motor simulado | dibujar, deshacer, borrar, iniciar con trazo, pausar, cortafuego recortado, viento y vuelta al pronóstico, tarjeta con la bitácora verificada y reproducción: sin errores |
| Guion E-E3-4, `--solo-revisar` y pruebas de humo de 3 h (los tres motores) | "todo listo"; en las de humo, A y B se cumplen. No se corrió la evaluación |

## 3. Decisiones tomadas al implementar (a revisar)

1. **Hash**: los números enteros se escriben sin decimales (360.0 → 360), para que el navegador y Python den el mismo hash.
2. **Reproducción**: mientras reproduce, el proceso rechaza intervenciones nuevas, y las pausas a mano no entran en la cadena.
3. **Pausa en una hora fija**: las órdenes que llegan detrás de una pausa con hora futura esperan; `detener` se atiende en el acto.
4. **v4.0, geometría para la corrida offline**: la polilínea recortada si al rasterizarla da exactamente las mismas celdas;
   si no, los centros de las celdas (`datos.geometria_offline` dice cuál).
5. **E-E3-4**: el guion usa la ignición de la ficha (hipótesis 1) y no `configuracion.ignicion`, para que el foco sea el mismo
   con el que se eligieron los trazos. "Misma longitud" se mide con la geometría de la línea en v4.0 y con la identidad de
   celdas o enlaces cuando hay recorte (anotado en las notas del guion; conviene que quien evalúa lo acepte antes de correr).
6. **Parte recortada en el mapa**: se dibuja aproximada (se deduce de la huella); el tooltip lo dice.

## 4. Para decidir

1. **Cortafuego antes de iniciar que resulta rechazado** (por ejemplo, fuera del dominio): hoy la corrida sigue y lo informa en
   `resultados.cortafuegos_iniciales`. ¿Debería cortar la corrida con error?
2. **Viento manual con la biblioteca WindNinja en v4.0** (`viento.fuente: windninja`, no es la configuración congelada): se
   acepta, porque toma velocidad y dirección de la serie y es reproducible. Solo se rechaza con un campo de viento externo.
   ¿Era eso lo que pedía el punto 16?
3. **Exportación**: ¿el zip suma los archivos para la corrida offline (§2.1 del contrato)?

## 5. Límites conocidos

- Un trazo con suelo mineral antes de iniciar que pasa por la celda de ignición no da lo mismo que el mismo trazo a t = 0 (a
  t = 0 esa celda ya está alcanzada y se recorta). Las pruebas usan trazos lejos de la ignición.
- La pantalla en modo "ambos" (pausa e intervención por grupo) se probó en el servidor, no en el navegador.
- Falta probar en Edge y Firefox.

## 6. Lo que queda

- **E-E3-4**: que LisandroV2002 corra `python herramientas/e_e3_4.py --evaluador LisandroV2002`. Son unas 45 corridas de 48 h:
  calcular varias horas.
- Responder §4.
- Aprobación del contrato 1.5 por la otra persona.
