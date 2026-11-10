# Contrato entre los dos frentes — versión 1

Es el único punto donde se tocan el frente A (motores y datos) y el frente B (servidor e interfaz). Se cambia solo por pedido
de integración aprobado por las dos personas, subiendo el número de versión.

## 1. Paquete de corrida

El archivo `corrida.json` está definido en el Anexo C de `00_plan.md`. Campos obligatorios para lanzar una corrida:
`motor` (`v4.0` | `v3.1-libre` | `v3.1-librev2`), `configuracion.ignicion[]` (`lon`, `lat`, `t_utc`),
`configuracion.viento` (`{"modo": "pronostico"}` o `{"modo": "manual", "vel_kmh": …, "dir_desde": …}`),
`configuracion.horas`, `configuracion.cortafuegos[]` (`ancho_m`, `suelo_mineral`, `xy_5345`), e `insumos` con el sha256 de
cada archivo.

## 2. Proceso motor

El servidor lanza un proceso por corrida:

```
python app/motores/proceso.py --motor <v4.0|v3.1-libre|v3.1-librev2> --corrida <carpeta>
```

`<carpeta>` es `resultados/app/<id>/` y contiene `corrida.json`. El proceso fija su propio `PYTHONPATH` al motor que le toca.

**Órdenes** (servidor → motor, una línea JSON por la entrada estándar):

| Orden | Efecto |
|---|---|
| `{"orden": "pausar"}` | el motor termina la hora simulada en curso y espera |
| `{"orden": "reanudar"}` | sigue |
| `{"orden": "intervenir", "entrada": {…}}` | solo en pausa; `entrada` es una entrada de bitácora sin `hash` (`tipo`: `viento_manual`, `viento_pronostico`, `cortafuego`, `mas_horas`) |
| `{"orden": "detener"}` | cierra la corrida y guarda resultados |

**Avisos** (motor → servidor, una línea JSON por la salida estándar; todo lo demás va al archivo `proceso.log`):

| Aviso | Contenido |
|---|---|
| `{"aviso": "listo", "t0_utc": …, "grilla": {…}}` | insumos cargados |
| `{"aviso": "hora", "h": n, "t_sim_min": …, "ha": …, "activas": …, "exposicion": {…}, "meteo": {…}, "s_computo": …, "huella": "t_llegada_parcial.npy"}` | al terminar cada hora simulada |
| `{"aviso": "pausado", "t_sim_min": …}` | en hora en punto |
| `{"aviso": "intervencion", "n": …, "estado": "aceptada" \| "recortada" \| "rechazada", "t_vigor_min": …, "motivo": …}` | respuesta a `intervenir` |
| `{"aviso": "final", "motivo": …, "ha": …, "t_sim_min": …, "s_computo": …}` | salidas escritas |
| `{"aviso": "error", "mensaje": …}` | y código de salida distinto de 0 |

**Huella.** `t_llegada_parcial.npy` en la carpeta de la corrida: matriz `float32` de 1.671 × 1.672 con los minutos desde el
inicio en que el fuego llegó a cada celda, `NaN` donde no llegó. El motor la reescribe de forma atómica en cada hora.

**Salidas finales.** Las mismas que una corrida offline del motor correspondiente, más `corrida.json` completado con
`bitacora` y `resultados`.

## 3. Motor simulado

Para que el frente B no espere al A: `app/motores/proceso_simulado.py` cumple este contrato con un fuego de mentira (un círculo
que crece). Lo escribe el frente B en la semana 2 y se usa en las pruebas del servidor.

## 4. Interfaz del servidor

La lista de pedidos HTTP está en el Anexo D de `00_plan.md`.
