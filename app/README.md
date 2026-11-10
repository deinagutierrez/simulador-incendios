# app/ — simulador interactivo

Acá va el programa nuevo. **Todavía no hay código**: llega con las fases F1 a F5 del plan (`docs/etapa3/00_plan.md`).

| Carpeta prevista | Qué | Frente |
|---|---|---|
| `app/motores/` | un proceso por motor que conduce a v3.1 o a v4.0 sin modificarlos | A. Motores y datos |
| `app/datos/` | pronóstico de Open-Meteo, índices de Sentinel-2 por AWS, caché con procedencia | A. Motores y datos |
| `app/servidor/` | servidor local (solo `127.0.0.1`), gestor de corridas, bitácora | B. Servidor e interfaz |
| `app/web/` | interfaz en el navegador: mapa, panel, dibujo de cortafuegos, línea de tiempo | B. Servidor e interfaz |

Los dos frentes se encuentran en `docs/etapa3/contrato_servidor_motor.md`. Las pruebas van en `test/app/`.

Reglas: no modificar `src/v3.1`, `src/v4.0` ni sus pruebas y escenarios; no instalar los motores con `pip install -e`.
