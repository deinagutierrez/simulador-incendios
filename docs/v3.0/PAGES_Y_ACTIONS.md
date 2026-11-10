# Cómo funciona la publicación web

- `escenarios/v3.0/corridas/*.yaml` → **Actions "Simular escenario"** → `resultados/v3.0/<run_id>/` (commit automático)
- `scripts/exportar_visor.py` convierte una corrida en `docs/visor/<run_id>.html` (autónomo, 3 MB)
- `scripts/exportar_indice.py` arma `docs/index.html` con todas las corridas
- **Actions "Publicar visores"** sube `docs/` a GitHub Pages en cada cambio
- **Actions "pruebas simulador v3.0"** corre `pytest` en cada cambio de código

Localmente, los mismos pasos: `python scripts/correr_escenario.py --escenario X`, `python scripts/exportar_visor.py --run-id <run_id>`,
`python scripts/exportar_indice.py`, y abrir `docs/index.html` en el navegador.
