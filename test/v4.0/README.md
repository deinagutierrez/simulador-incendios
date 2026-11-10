# test/v4.0 — pruebas automáticas del código v4.0

Pruebas unitarias con `pytest` del simulador SIM de V.4 integrado en `src/v4.0/src/simulador`: física (Rothermel contra
valores de referencia, humedades del combustible muerto y vivo, elipse y viento, `test_fisica.py`), simetría y sensibilidad
del autómata sobre grillas sintéticas (frente circular, viento, pendiente, `test_simetria.py`), grilla, manifiesto,
meteorología y carga de capas (`test_io.py`) y la supresión L03 desde cuarteles (`test_supresion.py`). A esto se suman las
pruebas de lo nuevo de v4.0: las correcciones de la verificación (factor de viento 10 m → 20 ft, humedad de equilibrio,
límite de viento, re-anclaje de Huygens, extinción reversible), las variaciones de v3.0 (barreras con cruce probabilístico,
contención y despacho SNMF, humedad seleccionable, k por grupo; `test_fisica_v4.py`, `test_contencion.py`), la capa
estándar `incendios_sl` (escenarios de corrida, variantes y resumen; `test_escenarios.py`) y el banco de V.4 (`test_banco.py`). El comportamiento de V.4 tal como se entregó se prueba con los interruptores del modelo
`sim_v4_original`. No usan red; las que necesitan los insumos de `datos/inputSimulacion/sim_v4/` se omiten si no están.

```bash
cd src/v4.0
python -m pytest -q            # todas (140), ~2 min
python -m pytest -q ../../test/v4.0/test_fisica.py -k viento   # un archivo o una prueba
```
`conftest.py` agrega `src/v4.0/src` al `sys.path`, así que también corren sin `pip install -e .`.
Para correrlas en GitHub Actions hay que agregar `.github/workflows/ci-v4.yml` (copia de `ci-v2.yml` con `v4.0`).
