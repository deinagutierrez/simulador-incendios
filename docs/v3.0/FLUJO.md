# Flujo de trabajo del simulador v3.0

Hay tres cosas distintas que se "corren", y conviene no mezclarlas. Es el mismo ciclo de v2.0; lo nuevo de v3 está
marcado.

## 1. Pruebas automáticas (`test/v3.0`)
Verifican que el código esté sano. Corren sobre grillas sintéticas: no descargan nada, no leen `datos/`, tardan
unos 20 segundos. Se ejecutan a mano (`python -m pytest -q` desde `src/v3.0`). **Nuevas en v3**: barreras y
contención (`test_barreras.py`), despacho del SNMF y arribo vial (`test_despacho.py`), humedad por retardo
(`test_humedad.py`). Si una falla, se rompió el código, no los datos.

## 2. Preparación de datos (`preparar_evento.py`) — una vez por evento
Es el único momento en que se descargan fuentes externas:

| Paso | Fuente | Requiere | Tiempo | Deja en |
| --- | --- | --- | --- | --- |
| DEM, pendiente, orientación | Copernicus GLO-30 vía Google Earth Engine | cuenta GEE | minutos | `inputSimulacion/dem/` |
| Biblioteca de viento (72 direcciones) | WindNinja local | WindNinja + 16 GB RAM | 45 min, una vez por dominio | `inputSimulacion/viento/` |
| NDVI/NDMI previos al evento | Sentinel-2 vía GEE | cuenta GEE | 20 min por evento | `procesados/indices/` → `inputSimulacion/combustibles/<evento>/` |
| Meteorología horaria | Open-Meteo (archivo ECMWF IFS) | internet | segundos | `inputSimulacion/meteo/` |
| Cicatriz de referencia, humedad del combustible (FFMC y retardo) | `datos/crudos/` + meteo | — | segundos | `inputSimulacion/eventos/<evento>/` |
| Focos VIIRS/MODIS | FIRMS vía GEE (`obtener_focos.py`) | cuenta GEE | minutos | `inputSimulacion/catalogo/hotspots/` |
| **Barreras sobre los enlaces del estencil** | caminos de `datos/crudos/` + anchos de `modelo_v2` | — | minutos, una vez por dominio | `inputSimulacion/barreras/` |
| **Tiempo de arribo desde los cuarteles** (`preparar_arribo.py`) | red vial + `bomberos_san_luis.geojson` | — | minutos, una vez por dominio | `inputSimulacion/infraestructura/arribo_<dominio>.npz` |

Para los diez eventos actuales esto ya está hecho y no hay que repetirlo. Solo se corre al agregar un evento o un
dominio nuevo. Si cambian los anchos de las vías en `modelo_v2.yaml`, `preparar_evento.py` regenera las barreras.

## 3. Correr un escenario (`correr_escenario.py`) — tantas veces como se quiera
```bash
cd src/v3.0
python scripts/correr_escenario.py --escenario local_mesilla_2024
```
Lee `escenarios/v3.0/corridas/local_mesilla_2024.yaml`, carga los datos del evento desde `inputSimulacion/`,
simula con el modelo indicado, valida si el YAML lo pide y escribe `resultados/v3.0/local_mesilla_2024_<fecha>/`
con el resumen estadístico.

El código de simulación es siempre el mismo (`src/incendios_sl/simulation/`); lo que cambia entre corridas es
el escenario. Para cambiar una "prueba":
- otra hipótesis de ignición, otros k, menos horas → editar el YAML o copiarlo con otro nombre;
- otro incendio ya preparado → cambiar `evento:` por cualquiera de los diez de `escenarios/v3.0/eventos/`;
- **con o sin mitigación** → `variante:` (`libre`, `libre_v2`, `barreras`, `contencion`, `ambas`, `local`,
  `local_pronostico`) o los campos `modelo`, `barreras`, `contencion`, `despacho`, `ajustes`, `parche`
  (ver `escenarios/v3.0/README.md`);
- un incendio nuevo → ficha en `escenarios/v3.0/eventos/`, luego el paso 2, luego el escenario;
- otro juego de parámetros físicos → copiar `escenarios/v3.0/modelos/modelo_v2.yaml` con otro nombre y usar
  `modelo: <nombre>` en el escenario.

Para estudios de muchos escenarios (ablación, barridos de κ, recalibración de k) siguen estando los scripts de la
etapa de investigación: `evaluar_v2.py`, `calibrar_k.py`, `evaluar_humedad.py`.

## Rutas en los informes por etapa
Los informes 01–13 se escribieron con la organización anterior del proyecto. Equivalencias:

| En los informes | En el repositorio |
| --- | --- |
| `config/dominio_*.yaml`, `config/eventos/`, `config/modelo_v*.yaml` | `escenarios/v3.0/dominios/`, `eventos/`, `modelos/` |
| `data/derivados/` | `datos/inputSimulacion/` |
| `data/catalogo/` | `datos/inputSimulacion/catalogo/` |
| `data/resultados/` | `resultados/v3.0/` |
| insumos en la raíz (`Electricidad/`, `caminos_…geojson`, `bomberos_san_luis.geojson`…) | `datos/crudos/` |

## Resumen
```
pytest (20 s, sin datos)  →  ¿el código funciona?
preparar_evento (1 vez)   →  ¿tengo los datos del evento?      descarga GEE / Open-Meteo / WindNinja
correr_escenario (n veces)→  ¿qué pasa con esta configuración?  lee inputSimulacion, escribe resultados/v3.0
```
