# escenarios/v4.0 — qué se simula con la versión 4.0

Seis carpetas de YAML (y una de capas de mitigación), todas leídas por el código de `src/v4.0`. El motor es SIM
(autómata celular de 30 m, Rothermel + Scott & Burgan 40) con las correcciones de la verificación y la flexibilidad de v3.0:

| Carpeta | Un archivo por… | Define |
| --- | --- | --- |
| `dominios/` | área de estudio | copia de v3.0 (grilla EPSG:5345 de 30 m, fuentes y `combate:` con cuarteles y departamentos). SIM solo cubre `las_lagunas_potrerillos` (manifiesto de `datos/inputSimulacion/sim_v4`) |
| `eventos/` | incendio histórico (10 + 5 **no vistos** del lote X-49, docs/v4.0/31) | fichas de v3.0 sin cambios: fechas SNMF, hipótesis de hora y punto de ignición (`ignicion`, `ignicion_alternativas`), fin de la simulación, fechas de evaluación y `combate:` (cuarteles, medios aéreos, inicio). En los cinco del lote X-49 `ignicion` es el primer pase VIIRS (regla §4.1 del banco) y `mes` puede ser una lista |
| `modelos/` | juego de parámetros físicos (YAML parcial sobre `simulador/config.py` DEFAULTS) | `modelo_v3` (SIM corregido y flexible, el de por defecto) y `sim_v4_original` (V.4 tal como se entregó; *V4 original* en el panel) |
| `corridas/` | escenario a ejecutar | evento, caso o sim + hipótesis + modelo + mitigación + horas + si se valida |
| `sim/` | escenario nativo de SIM | YAML completo de `python -m simulador run` (rutas relativas a la carpeta); se puede correr desde una corrida con `sim:` |
| `mitigacion/` | medida de mitigación | GeoJSON de líneas con `ancho_m` (cortafuegos, líneas de control) o GeoTIFF de factor de carga, citados desde `mitigacion:` |

`corridas/` es lo que se ejecuta: `python scripts/correr_escenario.py --escenario <nombre>` desde `src/v4.0`
(o `--archivo <ruta.yaml>`), o el menú del cuaderno `Simulador_Incendios_v4.ipynb`. El resultado queda en
`resultados/v4.0/<run_id>/` y `python scripts/exportar_visor.py --run-id <run_id>` arma su visor HTML (el nativo de SIM: perímetros
horarios); `python scripts/exportar_visor_v31.py --run-id <run_id>` arma en cambio el visor de v3.1 (tiempo de llegada, relieve,
combustibles, cicatriz, infraestructura, focos y tabla de ajuste) a partir de las mismas salidas.

Los insumos de SIM de cada evento (meteorología horaria con huso −03:00 y viento en km/h, combustible pre-evento con la
regla de SIM, NDVI/NDMI ×10000, perímetro observado, focos VIIRS) se derivan de los productos de v3.0 la primera vez y
quedan en `datos/procesados/v4.0/<evento>/`, cada uno con un `.json` de procedencia; se regeneran solos si cambia la fuente
o la versión de la regla (`version_regla` en la procedencia).

**Combustible pre-evento (regla 3.3 de V.4, igual celda a celda a la de `sim_adaptador.py`/`preparar_datos.py`):**
cobertura MapBiomas del año anterior al evento (o `cobertura_anio` de la ficha si es anterior) + MDT + **mediana NDVI/NDMI
de enero–marzo** con los compuestos mensuales `NDVI_NDMI_AAAA_MM.tif` (`datos/inputSimulacion/sim_v4/dinamicos/indices/` o
`banco_v4/entradas/indices_extra/`); los terciles de `umbrales_ndvi.csv` están calibrados con el verano. El verano es el del
año del evento, o el del año anterior si el evento es de enero–marzo (sin escenas posteriores a la ignición). La misma
mediana NDVI es `ndvi_verano_previo.tif`; `indices_mes_evento.tif` sigue siendo el compuesto pre-evento de v3.0.
Respaldo (con aviso en el log y `regla_indices` en la procedencia): si falta un mes, la mediana de los que haya
(`verano_parcial`); si no hay ninguno, el compuesto pre-evento de v3.0 (`respaldo_compuesto_evento`, sin `ndvi_verano`).
Hoy solo `SL-2022-PUERTAS` (enero de 2022 → verano 2021, sin compuestos) usa el respaldo; su compuesto de v3.0 (25/11/2021–11/01/2022) ya es de comienzos del verano.

## Campos de un escenario de corrida

| Campo | Valores | Por defecto |
| --- | --- | --- |
| `evento` | id de `eventos/` | una de las tres fuentes es obligatoria |
| `caso` (+ `variante_caso`) | carpeta de `datos/inputSimulacion/sim_v4/conjunto_prueba` y una variante de su `caso.yaml` (`t0_06h`, `dt_5min`…) | — (`variante_caso: base`) |
| `sim` | YAML nativo de SIM (`sim/<x>.yaml`, relativo a la corrida, a `escenarios/v4.0` o al repositorio) | — |
| `hipotesis` | índice de `inicio.hora_utc_hipotesis` de la ficha | 0 |
| `ignicion` | `snmf` o `alt0`, `alt1`… (`ignicion_alternativas` de la ficha) | snmf |
| `horas` | limitar la duración (con `caso`/`sim` reemplaza `duracion_h`) | hasta `fin.fin_simulacion_utc` |
| `variante` | atajo: `libre`, `barreras`, `v4_original` (en el panel). Con combate, solo por YAML y sin uso por ahora (D42): `contencion`, `ambas`, `local`, `local_pronostico`, `l03` | — |
| `modelo` | `modelo_v3` / `sim_v4_original` / otro de `modelos/` (se fusiona sin su `descripcion`) | modelo_v3 |
| `barreras`, `contencion` | `auto` (lo que diga la variante o el modelo) / `on` / `off` | auto |
| `despacho` | `auto` / `global` / `local` / `pronostico` / `l03` | auto |
| `ajustes` | se fusiona en `parametros` de SIM, p. ej. `{contencion: {tasa_linea_m_h: 500, retardo_h: 3}, barreras: {modo: umbral, lambda: 1.5}, parada: {horas_sin_avance: 24}}` | — |
| `parche` | se fusiona en el cfg completo de SIM, p. ej. `{dt_min: 1.0, vecindad: 16, salidas: {png_cada_h: 6}}` | — |
| `combate` | bloque de despacho de esta capa (`usar_ficha`, `retardo_modo`, `precedencia`, `arribo`…; ver más abajo), después del preset del despacho | el del modelo |
| `k_grupo`, `k_codigo`, `k_global`, `factor_waf` | multiplicadores de R0 por familia S&B (`{GR: 1.2, SH: 0.8}`), por código, global, y del WAF | 1 |
| `humedad` | atajo a `parametros.humedad` (`metodo_muerto: retardo / ffmc_vanwagner / fija`, `fija_m1`…, `viva_metodo`, `mx_grupo`…). **No recomendados (E035, docs/v4.0/18)**: `ffmc_vanwagner` y `viva_metodo: minmax` de v3.0 mueven todos los eventos en la misma dirección y empeoran el conjunto | la del modelo |
| `viento` | `windninja` (campo sobre el relieve, biblioteca de v3.0) / `serie` (uniforme + factor topográfico, V.4) o un dict de `parametros.viento` | `serie` (en `modelo_v3` desde E036, D41; antes `windninja`) |
| `regla_combustible` | `3.3` (V.4) / `3.3b` (estructura leñosa sin la anomalía interanual del verano; docs/v4.0/17 y 20) | `3.3b` en `modelo_v3` desde E043 (D46, provisorio); `3.3` en `sim_v4_original` |
| `semilla` | una sola semilla para el modo estocástico, los cruces de barrera y los escapes | la del modelo |
| `ensemble` | `n` miembros (modo estocástico y mapa de probabilidad de quemado) | 0 |
| `mitigacion` | `{barreras_extra: <GeoJSON de líneas>, modificador_combustible: <GeoTIFF factor 0–2>}` (rutas relativas a la corrida) | — |
| `parar_en_cicatriz` | `auto` / `on` / `off`: termina en el sub-paso en que la superficie afectada iguala o supera la observada (evento: cicatriz de referencia sobre celdas combustibles = `ha_ref` de la validación; caso/sim: celdas del perímetro observado). Motivo de fin `superficie_observada` | `auto` = on con `evento` y `caso` (también con `variante: v4_original`), off con `sim` |
| `validar`, `figuras` | métricas contra la cicatriz y los focos (evento) o `simulador.evaluacion` (caso); mapas PNG y animación | true |
| `run_id`, `nombre`, `descripcion` | carpeta del resultado (por defecto `<escenario>_<AAAAMMDD-HHMM>`) y texto libre | — |

Precedencia: **variante → campos sueltos → despacho → ajustes → parche** (cada paso pisa al anterior). `k_clase` de v3.0 no
existe en v4 (las clases de combustible de v3.0 no son las de Scott & Burgan): usar `k_grupo`.

## Variantes y despacho

| Variante | Modelo | Barreras | Contención | Despacho |
| --- | --- | --- | --- | --- |
| `libre` | modelo_v3 | off (los caminos solo reducen la carga) | off | — |
| `barreras` | modelo_v3 | on (cruce probabilístico según L/W) | off | — |
| `contencion` | modelo_v3 | off | on | global |
| `ambas` | modelo_v3 | on | on | global |
| `local` | modelo_v3 | on | on | local |
| `local_pronostico` | modelo_v3 | on | on | pronostico |
| `l03` | modelo_v3 | la del modelo | off | l03 |
| `v4_original` | sim_v4_original | la de V.4 (umbral por tipo de camino, llama de cabeza) | off | — (sin supresión) |

| Despacho | Qué hace |
| --- | --- |
| `global` (v3.0 docs/10) | `contencion.despacho: fijo` con `tasa_linea_m_h`, inicio a `retardo_h` de la ignición, sin medios aéreos automáticos ni ficha |
| `local` (v3.0 docs/13) | tasa SNMF κ·a·A^b con a, b de la región del departamento de la ignición (periurbano, llanura_sur, serrano); inicio = aviso 0,5 h + despacho 0,25 h + viaje por la red vial desde el cuartel más cercano (entre los `cuarteles_id` de la ficha) o `combate.inicio_utc` de la ficha; medios aéreos de la ficha o, si no los declara, sorteados |
| `pronostico` | como `local` sin la ficha (cuartel más cercano, aéreos sorteados): como ante un incendio nuevo |
| `l03` | supresión L03 de V.4 (`parametros.supresion`): 3 dotaciones que llegan a los 30 min + viaje vial de los 3 cuarteles más rápidos, 500 m/h cada una, ataque directo con llama < 2,4 m |

El arribo sale del producto de v3.0 `datos/inputSimulacion/infraestructura/arribo_las_lagunas_potrerillos.npz`
(`src/v3.0/scripts/preparar_arribo.py`) y, como las llegadas L03, se cuenta desde la ignición (si `t_inicio` es anterior
a la ignición, se suma el desfase). `combate.inicio_utc` de la ficha sin huso se toma como UTC.

### Bloque `combate` de la corrida e inicio del combate

`combate:` (opcional) se fusiona **después** del preset del despacho, así que puede cambiar lo que fija la variante:
`usar_ficha`, `retardo_modo` (`fijo` | `vial`), `arribo` (`t_aviso_h` 0,5, `t_despacho_h` 0,25), `regiones`, `region_defecto`,
`m_h_por_bombero` (20), `l03` y `precedencia`. Por ejemplo `variante: local` con `combate: {retardo_modo: fijo}` usa
`retardo_h` en lugar del arribo vial.

`combate.precedencia` decide quién fija el inicio del combate (`contencion.inicio_min`):

| `precedencia` | Orden (gana el primero que exista) |
| --- | --- |
| `contrato` (por defecto) | `inicio_min` o `retardo_h` en `ajustes`/`parche` > `combate.inicio_utc` de la ficha > arribo vial > `retardo_h` del modelo |
| `v3` (como v3.0) | `inicio_min` en `ajustes`/`parche` > ficha > `retardo_h` en `ajustes`/`parche` (anula el arribo vial) > arribo vial > `retardo_h` del modelo |

Con `contrato` un `retardo_h` de `ajustes` gana a la ficha (sigue la precedencia general de la corrida); con `v3` la ficha
gana a ese retardo, como en `src/v3.0` (`entradas.py`). El resumen muestra el inicio real (`metadata.json`, `contencion.inicio_min`).

## Ejemplos incluidos

Desde E036 (D42) no se simulan mitigaciones: las corridas con combate o cortafuegos (`local_laslagunas_2024`, `local_mesilla_2024`, `l03_laslagunas_2024`,
`pronostico_puertas_2022`, `mitigacion_cortafuego_ejemplo`, `personalizado_ejemplo`, `calibracion_comparar_ejemplo`) están en `corridas/_archivo_mitigacion/`
(ver su LEEME). Las barreras del ambiente siguen: celdas sin combustible siempre y caminos con la variante `barreras`.

| Corrida | Qué muestra |
| --- | --- |
| `prueba_rapida_v4` | 6 h de Las Lagunas 2024 con la variante `barreras` y la parada anticipada apagada, para que siempre simule las 6 h (prueba de humo de la instalación) |
| `libre_laslagunas_2024` | línea base sin barreras ni combate |
| `caso_aguada_2023`, `v4_original_aguada_2023` | el caso de prueba de SIM con el modelo corregido y con V.4 tal como se entregó; las dos terminan al igualar el perímetro observado (sin tope, `parar_en_cicatriz: off`, V.4 original da 2783,0 ha en 36 h, igual que la verificación) |
| `comparar_viento_windninja_laslagunas_2024`, `comparar_viento_serie_laslagunas_2024` | lo mismo con y sin el viento sobre el relieve (docs/v4.0/17 y 18) |
| `libre_lajuli_2022`, `libre_algarrobal_2022`, `libre_latotora_2022`, `libre_lagunalarga_2023`, `libre_chacrasoct_2023` | propagación libre de los cinco eventos **no vistos** del lote X-49 (docs/v4.0/31); insumos sin red con `src/v3.4/scripts/preparar_evento_desde_banco.py` |

## Evento nuevo

1. Ficha en `eventos/` con la forma de las de v3.0 (dominio `las_lagunas_potrerillos`).
2. Productos de v3.0 desde `src/v3.0`: `preparar_evento.py` (meteorología del dominio, cicatriz de referencia),
   `obtener_indices.py` (NDVI/NDMI pre-evento) y `obtener_focos.py` (focos VIIRS, opcional).
3. Una corrida en `corridas/` con `evento: <id>`. La primera ejecución genera los insumos de SIM en `datos/procesados/v4.0/<id>/`.

Un incendio fuera del dominio necesita primero extender el manifiesto de SIM (`datos/inputSimulacion/sim_v4`, `scripts/preparar_datos.py`).

Cada versión del simulador tiene su propia carpeta (`v2.0/`, `v3.0/`, `v4.0/`), así una corrida vieja siempre se puede
repetir con el código y los escenarios de su versión.
