# escenarios/v3.1 — qué se simula con la versión 3.0

Cuatro carpetas de YAML, todas leídas por el código de `src/v3.1`:

| Carpeta | Un archivo por… | Define |
| --- | --- | --- |
| `dominios/` | área de estudio | grilla (EPSG:5345, 30 m), máscara, fuentes de DEM, cobertura, cicatrices, infraestructura y, nuevo en v3, `combate:` (cuarteles y departamentos) |
| `eventos/` | incendio histórico (10) | fechas SNMF, hipótesis de hora y punto de ignición, ventana meteorológica y de índices, fechas de evaluación y, nuevo en v3, `combate:` (cuarteles, medios aéreos y días de contención del SNMF) |
| `modelos/` | juego de parámetros físicos | `modelo_v1` (el de v2.0) y `modelo_v2` (humedad por retardo, k recalibrados, barreras, contención y despacho) |
| `corridas/` | escenario a ejecutar | evento + hipótesis + modelo + mitigación + horas + si se valida |

`corridas/` es lo que se ejecuta: `python scripts/correr_escenario.py --escenario <nombre>` desde `src/v3.1`,
o el menú del cuaderno `Simulador_Incendios_v3.ipynb`.

## Campos de un escenario de corrida

| Campo | Valores | Por defecto |
| --- | --- | --- |
| `evento` | id de `eventos/` | (obligatorio) |
| `hipotesis` | índice de la hora de ignición de la ficha | 0 |
| `ignicion` | `snmf` o `alt0`, `alt1`… (`ignicion_alternativas` de la ficha) | snmf |
| `horas` | limitar la duración | hasta el fin documentado |
| `variante` | atajo: `libre` (modelo_v1), `libre_v2`, `barreras`, `contencion`, `ambas`, `local`, `local_pronostico`, `local_exacto` | — |
| `modelo` | `modelo_v1` / `modelo_v2` | modelo_v1 |
| `barreras`, `contencion` | `auto` (lo que diga el modelo) / `on` / `off` | auto |
| `despacho` | `auto` / `global` (tasa fija, docs/10) / `local` (SNMF + ficha) / `pronostico` (SNMF sin ficha, docs/13) | auto |
| `ajustes` | campos de `ConfigSimulacion`, p. ej. `{tasa_linea_m_h: 500, contencion_retardo_h: 3}` | — |
| `parche` | cambios al YAML del modelo, p. ej. `{barreras: {cruce: {lambda: 1.5}}}` | — |
| `k_clase`, `k_global`, `factor_waf` | factores de propagación | los del modelo |
| `validar`, `figuras` | métricas contra la cicatriz y focos, mapas y animación | true |

`variante` fija modelo, barreras, contención y despacho; los campos sueltos que se escriban después la modifican.

Ejemplos incluidos: `prueba_rapida_v3` (6 h, prueba de humo), `libre_laslagunas_2024` (línea base sin mitigación),
`local_laslagunas_2024` y `local_mesilla_2024` (modelo completo), `pronostico_puertas_2022` (como ante un incendio nuevo)
y `personalizado_ejemplo` (plantilla campo por campo para ensayar medidas de mitigación).

Para un evento nuevo: ficha en `eventos/`, `obtener_focos.py` y `preparar_evento.py`; luego un escenario.
Cada versión del simulador tiene su propia carpeta (`v2.0/`, `v3.1/`…), así una corrida vieja siempre se puede
repetir con el código y los escenarios de su versión.
