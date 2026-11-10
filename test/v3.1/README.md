# test/v3.1 — pruebas automáticas del código v3.1

Pruebas unitarias con `pytest`: autómata sobre grillas sintéticas (frente circular, elipse con viento,
pendiente, barreras, reproducibilidad), Rothermel contra valores de referencia, combustibles, humedad,
control de calidad meteorológico, convenciones de viento, grilla y API. Nuevas en v3: barreras lineales y contención
(`test_barreras.py`), despacho del SNMF y tiempo de arribo (`test_despacho.py`) y humedad por retardo (`test_humedad.py`). No usan red ni los datos de
`datos/`; las dos que necesitan un insumo se omiten si no está.

```bash
cd src/v3.1
python -m pytest -q            # todas, ~10 s
python -m pytest -q ../../test/v3.1/test_automata.py -k viento   # un archivo o una prueba
```
Para correrlas en GitHub Actions hay que agregar `.github/workflows/ci-v3.yml` (copia de `ci-v2.yml` con `v3.1`).
