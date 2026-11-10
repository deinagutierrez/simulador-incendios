# Flujo de trabajo del simulador v4.0

Hay tres cosas distintas que se "corren", y conviene no mezclarlas. Es el mismo ciclo de v2.0 y v3.0; lo nuevo de v4
está marcado. **El motor es el SIM de V.4** (informe 14), corregido (informe 15).

## 1. Pruebas automáticas (`test/v4.0`)
Verifican que el código esté sano. Corren sobre grillas sintéticas y, si están, sobre los datos de `sim_v4`; no
descargan nada y tardan unos dos minutos (`python -m pytest -q` desde `src/v4.0`). **Nuevas en v4**: física corregida
y reproducción exacta de V.4 (`test_fisica_v4.py`), contención y despacho en SIM (`test_contencion.py`), traducción de
escenarios (`test_escenarios.py`), banco de V.4 (`test_banco.py`); las de SIM (`test_fisica`, `test_simetria`,
`test_io`, `test_supresion`). Si una falla, se rompió el código, no los datos.

## 2. Preparación de datos — una vez por evento
Los diez eventos de v3.0 ya tienen todo en `datos/inputSimulacion/` (meteorología, índices, cicatrices, focos, arribo).
**Nuevo en v4**: SIM necesita además sus datos del dominio en `datos/inputSimulacion/sim_v4/` (manifiesto, MDT,
pendiente, orientación, SB40, infraestructura, compuestos NDVI/NDMI mensuales) y genera solo, la primera vez que se
corre un evento, sus insumos en `datos/procesados/v4.0/<evento>/`:

| Insumo de SIM | Se arma desde | Regla |
| --- | --- | --- |
| `meteo_horaria.csv` | `inputSimulacion/meteo/<evento>_*_dominio.csv` | m/s → km/h, UTC → −03:00, sin huecos |
| `combustible_pre_evento.tif` | cobertura MapBiomas del año anterior + mediana NDVI/NDMI de enero–marzo | regla 3.3 de V.4 (`generar_sb40`) |
| `indices_mes_evento.tif`, `ndvi_verano_previo.tif` | `inputSimulacion/combustibles/<evento>/` y los compuestos mensuales | int16 ×10000 |
| perímetro observado, focos | `inputSimulacion/eventos/<evento>/` y `catalogo/hotspots/` | GeoJSON |

Para un evento nuevo siguen valiendo los pasos de v3.0 (`src/v3.0/scripts/preparar_evento.py`: GEE, Open-Meteo,
cicatriz) y, si su verano no está entre los compuestos de `sim_v4/dinamicos/indices` o `banco_v4/entradas/indices_extra`,
`src/v4.0/app/preprocesamiento/indices_mensuales_banco.py` (GEE).

## 3. Correr un escenario (`correr_escenario.py`) — tantas veces como se quiera
```bash
cd src/v4.0
python scripts/correr_escenario.py --escenario local_mesilla_2024
python scripts/exportar_visor.py --run-id <run_id>
```
Lee `escenarios/v4.0/corridas/local_mesilla_2024.yaml`, arma los insumos de SIM, simula con el modelo indicado
(`modelo_v3` por defecto), valida si el YAML lo pide y escribe `resultados/v4.0/<run_id>/` con el resumen estadístico.

Para cambiar una "prueba":
- otra hipótesis de ignición, otro punto, menos horas → `hipotesis`, `ignicion`, `horas`;
- otro incendio ya preparado → `evento:` (cualquiera de los diez) **o `caso:` (casos de prueba de SIM con su
  perímetro) o `sim:` (un YAML nativo de SIM)**;
- con o sin mitigación → `variante:` (`libre`, `barreras`, `contencion`, `ambas`, `local`, `local_pronostico`,
  **`l03`, `v4_original`**) o los campos `modelo`, `barreras`, `contencion`, `despacho`, `ajustes`, `parche`;
- **medidas de mitigación** → `mitigacion: {barreras_extra: <cortafuegos.geojson>, modificador_combustible: <tif>}`;
- **otra física** → `humedad` (método del muerto, humedades fijas, viva), `k_grupo`, `k_global`, `factor_waf`, o un
  modelo propio copiado de `escenarios/v4.0/modelos/modelo_v3.yaml`;
- **reproducir V.4** → `modelo: sim_v4_original` o `variante: v4_original`;
- **viento y combustible** → `viento: windninja | serie` (WindNinja sobre el relieve es el de `modelo_v3`) y
  `regla_combustible: 3.3 | 3.3b`; comparación lista en `comparar_viento_*` y `calibracion_comparar_ejemplo` (informe 17).

**Calibración (Fase 2, pausada)**: estado, resultados parciales y cómo reanudarla en `docs/v4.0/17_viento_windninja_y_fase2.md`.

**Banco de evaluación de V.4** (protocolo del informe 16): `app/motores/sim_adaptador.py --evento <id>
[--modelo modelo_v3] [--l03 500]`, luego `app/banco/registro.py`, `app/banco/fase1.py`, `app/web/construir.py`
(resultados en `resultados/v4.0/banco/`).

## Rutas en los informes por etapa
Los informes 01–13 son los de v3.0 (motor anterior). Equivalencias, además de las de v3.0
(`config/` → `escenarios/`, `data/derivados/` → `datos/inputSimulacion/`):

| En V.4 / en el informe 16 | En el repositorio |
| --- | --- |
| `app/simulador_incendios/` (SIM) | `src/v4.0/src/simulador/` |
| `SIM/datos/`, `SIM/conjunto_prueba/`, `manifiesto_datos.yaml` | `datos/inputSimulacion/sim_v4/` |
| `SIM/salidas/` | `resultados/v4.0/` |
| `datos/entradas/`, `datos/protocolo/` | `datos/inputSimulacion/banco_v4/` |
| `datos/banco/` | `resultados/v4.0/banco/` |
| `../Contexto/extraido/…/Analisis de Situación de Incendios` | `datos/crudos/` |

## Resumen
```
pytest (2 min, sin red)    →  ¿el código funciona?
datos del evento (1 vez)   →  ¿tengo los datos?        v3.0 preparar_evento + sim_v4 (los insumos de SIM se arman solos)
correr_escenario (n veces) →  ¿qué pasa con esta configuración?  escribe resultados/v4.0/<run_id>
```
