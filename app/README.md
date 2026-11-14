# app/ — simulador interactivo

El programa nuevo. Plan: `docs/etapa3/00_plan.md`.

| Carpeta | Qué | Frente | Estado |
|---|---|---|---|
| `app/motores/` | un proceso por corrida que conduce a v3.1 o a v4.0 sin modificarlos; motor simulado para pruebas | A. Motores y datos | fase F1 hecha: corre, avisa, pausa y detiene; ignición en un punto y una hora elegidos |
| `app/datos/` | pronóstico de Open-Meteo, índices de Sentinel-2 (AWS, Earth Engine o TIF a mano), CSV a mano, modo escenario, evento generado `RT-…`, caché con procedencia | A. Motores y datos | fase F4 hecha (ver `docs/etapa3/F4_informe.md`); E-E3-2 pendiente de evaluar |
| `app/servidor/` | servidor local (solo `127.0.0.1`), gestor de corridas, avance en vivo, huella para el mapa | B. Servidor e interfaz | fase F2 hecha |
| `app/web/` | interfaz en el navegador: mapa con capas, panel, línea de tiempo, gráfico, comparación entre motores | B. Servidor e interfaz | fases F3, F4 y F5 hechas (cortafuegos a mano alzada, viento manual, bitácora y reproducción) |

Los dos frentes se encuentran en `docs/etapa3/contrato_servidor_motor.md`. Las pruebas están en `test/app/`.

## Arrancar el simulador

```
python app/servir.py
```

Abre el navegador en `http://127.0.0.1:8000` con la pantalla del simulador: se elige el motor, se marca el punto de ignición
con un clic en el mapa, se pone día, hora y duración, y se ve la huella crecer hora por hora. La página mínima de prueba de
la F2 sigue en `/prueba`. Se cierra con Ctrl+C; antes, el servidor pide a las corridas en
marcha que guarden lo simulado. Opciones: `--sin-navegador`, `--puerto 8010`, `--con-simulado` (agrega un motor de mentira
que sirve para probar sin esperar). Los pedidos HTTP están en `docs/etapa3/contrato_servidor_motor.md`, §4.

## Probar el proceso motor a mano

Crear una carpeta con un `corrida.json` y lanzar el proceso. Ejemplo, 6 horas de Las Lagunas 2024 con v4.0:

```
mkdir resultados/app/prueba
```

`resultados/app/prueba/corrida.json`:

```json
{"motor": "v4.0", "base": {"definicion": {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "horas": 6, "validar": false, "figuras": false}}}
```

```
python app/motores/proceso.py --corrida resultados/app/prueba
```

Por la pantalla salen los avisos, una línea JSON por hora simulada. Los resultados quedan en `resultados/app/prueba/salida/`
y lo que imprime el motor, en `proceso.log`. Cambiando `motor` por `v3.1-libre` o `v3.1-librev2` corre el otro motor.

Para empezar el fuego en otro punto y a otra hora, con los datos del mismo evento, se agrega `configuracion`:

```json
{"motor": "v4.0",
 "base": {"definicion": {"evento": "SL-2024-LASLAGUNAS", "validar": false, "figuras": false}},
 "configuracion": {"ignicion": [{"lon": -65.55, "lat": -32.64}], "t_inicio_utc": "2024-09-19T16:00:00Z", "horas": 6}}
```

Al terminar, `corrida.json` trae en `resultados.ignicion` el punto que usó el motor. Si el clic cae en una celda que no
quema, el motor lo corre a la combustible más cercana y lo informa en `desplazada_m`.

## Archivos de `app/motores/`

| Archivo | Qué hace |
|---|---|
| `proceso.py` | punto de entrada: lee `corrida.json`, separa avisos del resto de la salida, elige el motor, completa `corrida.json` |
| `control.py` | avisos, órdenes sin bloquear, pausa en hora en punto, huella parcial |
| `ignicion.py` | ignición y hora elegidas por el usuario: entrega al motor la ficha del evento con esos dos datos cambiados |
| `proceso_simulado.py` | motor simulado: un círculo que crece; mismas órdenes y avisos que el real |
| `motor_v40.py` | conduce a v4.0: mismos pasos que su `correr_escenario.py`, con una subclase de `Automata` como punto de control |
| `motor_v31.py` | conduce a v3.1: mismos pasos que su `correr_escenario.py`, con una subclase de `Simulacion` como punto de control |

## Archivos de `app/datos/`

| Archivo | Qué hace |
|---|---|
| `proceso_datos.py` | proceso de datos: un trabajo por vez (pronóstico, CSV, escenario, índices AWS/GEE/manual, evento), con el camino de v3.1; avisa como los procesos motor |
| `meteo.py` | pronóstico con las funciones de v3.1 (16 puntos en paralelo), CSV a mano, escenario con valores fijos |
| `sentinel2.py` | catálogo Earth Search, lectura de los COG de Sentinel-2, máscara SCL, compuesto de ventana (v3.1) y mensual (SIM) |
| `indices.py` | tomas de índices: AWS, Earth Engine (código de v3.1, opcional) y TIF cargados a mano |
| `evento_rt.py` | arma un evento `RT-…` que los dos motores corren sin cambios; lo borra; barre los que quedaron a medio armar |
| `comun.py` | rutas, grillas del dominio, escritura de rásteres, procedencia |

Prueba con red, opcional: `python herramientas/probar_red.py` (pronóstico, índices, evento y 6 h con cada motor).

## Archivos de `app/servidor/`

| Archivo | Qué hace |
|---|---|
| `corridas.py` | gestor: carpeta de cada corrida, lanzamiento del proceso motor, lectura de avisos, órdenes, estado en disco, cierre ordenado |
| `app.py` | pedidos HTTP, canal de avance en vivo, control de que el pedido venga de la propia página |
| `huella.py` | pasa la huella a la proyección de los mapas web y la pinta como PNG; contorno en GeoJSON; comparación entre dos huellas |
| `capas.py` | capas de fondo: relieve, pendiente, cobertura, arribo, índices, combustible, cicatriz y vectores; con caché en `datos/procesados/app/capas/` |
| `datos.py` | qué eventos tienen datos en el clon (con ficha = EJEMPLO, o generados `RT-…`), recuadro del dominio, bloque `insumos` de `corrida.json` (no carga motores) |
| `trabajos.py` | gestor de trabajos de datos: lanza `app/datos/proceso_datos.py`, uno a la vez, lee sus avisos, estado en disco |
| `../servir.py` | arranque: busca un puerto libre, levanta el servidor y abre el navegador |

## Archivos de `app/web/`

| Archivo | Qué es |
|---|---|
| `index.html`, `app.js`, `estilo.css` | la pantalla del simulador, sin más bibliotecas que Leaflet |
| `vendor/leaflet/` | Leaflet 1.9.4 con su licencia, copiada acá para que funcione sin internet |
| `prueba.html` | página mínima de prueba del servidor (fase F2) |

Reglas: no modificar `src/v3.1`, `src/v4.0` ni sus pruebas y escenarios; no instalar los motores con `pip install -e`.
