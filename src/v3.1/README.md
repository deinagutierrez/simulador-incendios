# Simulador de propagación de incendios forestales — San Luis · código v3.1

Autómata celular de 30 × 30 m sobre el dominio Las Lagunas–Potrerillos (2.500 km²), con meteorología horaria
(Open-Meteo), viento ajustado al relieve (WindNinja), combustibles Scott & Burgan derivados de MapBiomas y
Sentinel-2, y validación contra cicatrices MapBiomas Fuego y focos VIIRS/MODIS. API (FastAPI) e interfaz web
(Leaflet).

**v3.1** es una copia de v3.0 para mejorar la simulación libre sin tocar v3.0 (plan y estado en `docs/v3.1/README.md`).
Agrega `scripts/extraer_focos.py` (focos VIIRS por evento desde el archivo provincial de FIRMS → `catalogo/hotspots_v3.1/`),
`scripts/evaluar_temporal.py` (forma a igual superficie + velocidad por primeras detecciones, para corridas de cualquier
versión) y las funciones `iou_igual_superficie` y `metricas_primera_deteccion` (`docs/v3.1/01`).

Novedades respecto de v2.0 (el autómata de v2.0 es `modelo_v1` y sigue disponible sin cambios):

| Tema | Qué cambia | Documento |
| --- | --- | --- |
| Barreras lineales | rutas y caminos bloquean la propagación según su ancho y la longitud de llama (cruce probabilístico) | `docs/v3.0/10` |
| Contención por combate | línea de ancla y flancos, umbrales de intensidad, escapes, medios aéreos | `docs/v3.0/10` |
| Humedad del combustible muerto | modelo de retardo (Simard 1968, τ = 1/10/100 h) en lugar del FFMC | `docs/v3.0/11` |
| Recalibración de k | k por grupo de clases con 6 eventos y la humedad nueva (0,75 / 2 / 5) | `docs/v3.0/12` |
| Despacho según el SNMF | tasa de línea escalonada con la superficie por régimen territorial, arribo vial desde 42 cuarteles | `docs/v3.0/13` |
| Eventos | 10 incendios del dominio (1 de calibración + 9 de validación) | `docs/v3.0/06` |

Todo eso se activa con `modelo: modelo_v2` en el escenario (`escenarios/v3.1/modelos/modelo_v2.yaml`).
Con barreras y contención apagadas, `modelo_v2` da el mismo resultado que `modelo_v1` con la humedad y los k nuevos.

Esta carpeta contiene solo código; todo lo demás vive en el resto del repositorio:

| Carpeta del repositorio | Qué hay | Lo usa |
| --- | --- | --- |
| `src/v3.1/` | código, scripts, interfaz web | — |
| `test/v3.1/` | pruebas automáticas (no necesitan datos ni red) | `python -m pytest` |
| `escenarios/v3.1/` | dominios, eventos, modelos y corridas (YAML) | `cargar_dominio/evento/modelo/corrida` |
| `datos/crudos/` | fuentes externas sin modificar (v3 suma `bomberos_san_luis.geojson`) | `preparar_evento.py`, `preparar_arribo.py` |
| `datos/procesados/` | intermedios regenerables (índices Sentinel-2, caché WindNinja) | `preparar_evento.py` |
| `datos/inputSimulacion/` | productos alineados a la grilla (v3 suma `barreras/` e `infraestructura/arribo_*.npz`) | `simular`, `validar`, `correr_escenario`, API |
| `resultados/v3.1/` | corridas con su resumen estadístico y fecha | se escribe acá |
| `docs/v3.0/` | metodología, informes por etapa (01–13), flujo de trabajo (`FLUJO.md`) | — |

Los datos son compartidos con v2.0: v3 solo agrega archivos y columnas (las series de humedad tienen además las
columnas `*_rt` del modelo de retardo), así que v2.0 sigue funcionando sobre la misma carpeta `datos/`.

El código encuentra esas carpetas solo cuando está en `<repo>/src/v3.1`. Para otra disposición, variables de
entorno: `INCENDIOS_SL_REPO`, `INCENDIOS_SL_INPUT`, `INCENDIOS_SL_CRUDOS`, `INCENDIOS_SL_PROCESADOS`,
`INCENDIOS_SL_ESCENARIOS`, `INCENDIOS_SL_RESULTADOS`.

## Instalación
Python ≥ 3.12. Desde `src/v3.1`:
```bash
pip install -r requirements.txt
pip install -e . --no-deps
python -m pytest -q                 # 65 pruebas, ~20 s, sin red ni datos
python scripts/correr_escenario.py --escenario prueba_rapida_v3    # 6 h simuladas con barreras y contención, prueba de humo con datos
```
Herramientas externas solo para preparar eventos nuevos: WindNinja 4.0 (ruta en `config/herramientas.yaml`,
copiar `herramientas.ejemplo.yaml`) y una cuenta de Google Earth Engine.

## Comandos
```bash
# correr un escenario (escenarios/v3.1/corridas/<nombre>.yaml) → resultados/v3.1/<nombre>_<fecha>/
python scripts/correr_escenario.py --escenario local_mesilla_2024
# simular y validar a mano, con el modelo v2 (barreras + contención)
python scripts/validar.py --evento SL-2024-MESILLA --ignicion alt1 --modelo modelo_v2 --run-id mesilla_v2   # --barreras on|off --contencion on|off --v2 tasa_linea_m_h=1000
# ablación por variantes (libre, barreras, contención, ambas, local, local_pronostico) → resultados/v3.1/evaluacion_v2/
python scripts/evaluar_v2.py ablacion --variantes ambas,local,local_pronostico --sufijo _snmf --salida ablacion_despacho.csv
python scripts/evaluar_v2.py comparar --entradas ablacion_despacho.csv
# humedad del combustible muerto (docs/11) y recalibración de k (docs/12)
python scripts/actualizar_humedad.py; python scripts/evaluar_humedad.py; python scripts/calibrar_k.py
# combate según el SNMF (docs/13): análisis de reportes y tiempo de arribo desde los cuarteles
python scripts/analizar_combate_snmf.py
python scripts/preparar_arribo.py
# preparar los datos de un evento nuevo (GEE + Open-Meteo + WindNinja + barreras) → datos/inputSimulacion/
python scripts/preparar_evento.py --evento <id>
# visor autónomo de una corrida e índice de corridas
python scripts/exportar_visor.py --run-id <run_id>
python scripts/exportar_indice.py
# API + interfaz web
python scripts/servir.py --puerto 8000
```
Ver `docs/v3.0/FLUJO.md` para el ciclo completo: pruebas, preparación de datos, escenarios y resultados.

## Estructura del código
```
src/incendios_sl/   grilla, config (rutas del repo), procedencia | data/ (dominio, barreras, arribo) meteorology/ remote_sensing/
                    wind/ fuels/ (humedad FFMC y retardo) | simulation/ (entradas, motor, autómata con barreras y contención)
                    validation/ (métricas, figuras, resumen) | api/
scripts/            CLIs de cada etapa; correr_escenario.py es el punto de entrada habitual
web/                interfaz Leaflet y plantilla del visor autónomo
config/             solo herramientas.ejemplo.yaml (rutas locales, no se versiona el real)
```

Licencias de datos: MapBiomas (CC-BY 4.0), Open-Meteo (CC-BY 4.0), Copernicus DEM, Sentinel-2, VIIRS/MODIS
(NASA FIRMS), SNMF (Argentina), OSM/IGN/Secretaría de Energía, Ministerio de Seguridad de San Luis (cuarteles).
