# app/ — simulador interactivo

El programa nuevo. Plan: `docs/etapa3/00_plan.md`.

| Carpeta | Qué | Frente | Estado |
|---|---|---|---|
| `app/motores/` | un proceso por corrida que conduce a v3.1 o a v4.0 sin modificarlos | A. Motores y datos | fase F1, primera parte: corre, avisa, pausa y detiene |
| `app/datos/` | pronóstico de Open-Meteo, índices de Sentinel-2 por AWS, caché con procedencia | A. Motores y datos | sin empezar |
| `app/servidor/` | servidor local (solo `127.0.0.1`), gestor de corridas, bitácora | B. Servidor e interfaz | sin empezar |
| `app/web/` | interfaz en el navegador: mapa, panel, dibujo de cortafuegos, línea de tiempo | B. Servidor e interfaz | sin empezar |

Los dos frentes se encuentran en `docs/etapa3/contrato_servidor_motor.md`. Las pruebas están en `test/app/`.

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

## Archivos de `app/motores/`

| Archivo | Qué hace |
|---|---|
| `proceso.py` | punto de entrada: lee `corrida.json`, separa avisos del resto de la salida, elige el motor, completa `corrida.json` |
| `control.py` | avisos, órdenes sin bloquear, pausa en hora en punto, huella parcial |
| `motor_v40.py` | conduce a v4.0: mismos pasos que su `correr_escenario.py`, con una subclase de `Automata` como punto de control |
| `motor_v31.py` | conduce a v3.1: mismos pasos que su `correr_escenario.py`, con una subclase de `Simulacion` como punto de control |

Reglas: no modificar `src/v3.1`, `src/v4.0` ni sus pruebas y escenarios; no instalar los motores con `pip install -e`.
