# Simulador de propagación de incendios forestales — San Luis · código v4.0

Autómata celular de 30 × 30 m sobre el dominio Las Lagunas–Potrerillos (2.500 km², EPSG:5345) con el motor **SIM de
V.4**: tiempos de llegada con construcción de Huygens por origen heredado y sub-pasos CFL, Rothermel (1972) en la
formulación de Andrews (2018) con los 40 modelos de Scott y Burgan (2005), humedad muerta por retardo (Simard/NFDRS) o
FFMC, humedad viva por NDMI y curado por NDVI, caminos, viviendas y red eléctrica, salidas horarias para agentes
(`estado_hora_HH.json`). Sobre ese motor se integraron las variaciones de flexibilidad de v3.0.

Novedades respecto de v3.0:

| Tema | Qué cambia | Documento |
| --- | --- | --- |
| Motor | SIM de V.4 reemplaza al autómata de v3.0; los eventos, escenarios y resultados siguen el mismo estándar | `docs/v4.0/14` |
| Verificación del modelo de fuego | viento 10 m → 20 ft, EMC de Simard, Huygens hacia atrás en el tiempo, caminos con llama de cabeza, extinción definitiva, límite de viento (corregidos y con interruptor) | `docs/v4.0/15` |
| Reproducir V.4 | `modelo: sim_v4_original` (o `variante: v4_original`) da exactamente las corridas de V.4 | `docs/v4.0/15` §3 |
| Barreras | cruce probabilístico de v3.0 sobre los caminos de SIM y cortafuegos propios (`mitigacion.barreras_extra`), evaluado por enlace | `docs/v4.0/14` §3 |
| Contención y despacho | línea con anclaje, escapes, medios aéreos y despacho SNMF de v3.0, más la supresión L03 de V.4 | `docs/v4.0/14`, `docs/v3.0/10`, `13` |
| Humedad y factores | humedad muerta retardo / FFMC / fija, viva lineal / min–max / fija, Mx por familia, k por familia SB40, factor WAF | `docs/v4.0/14` §3 |
| Viento sobre el relieve | biblioteca WindNinja de v3.0 (72 direcciones, 100 m) leída por SIM: velocidad y dirección por celda; `viento: serie` vuelve al viento uniforme de V.4 | `docs/v4.0/17` |
| Combustible de años secos | regla 3.3b opcional: la sequía del verano ya no se confunde con menos carga leñosa | `docs/v4.0/17` |
| Casos de prueba y banco | casos con evaluación automática (`caso:`) y el banco de evaluación de V.4 (protocolo, Fase 1, L03) | `docs/v4.0/16` |

`modelo_v3` (escenarios/v4.0/modelos) es el modelo por defecto: física corregida, barreras activas y contención solo si
la pide la variante o el campo `contencion`.

Esta carpeta contiene solo código; todo lo demás vive en el resto del repositorio:

| Carpeta del repositorio | Qué hay | Lo usa |
| --- | --- | --- |
| `src/v4.0/` | `src/simulador` (motor), `src/incendios_sl` (capa estándar), `scripts/`, `web/`, `app/` (banco de V.4) | — |
| `test/v4.0/` | pruebas automáticas (140; sin red) | `python -m pytest` |
| `escenarios/v4.0/` | dominios y eventos (de v3.0), modelos, corridas, `sim/` (YAML nativos de SIM), `mitigacion/` | `correr_escenario.py` |
| `datos/inputSimulacion/` | productos de v2.0/v3.0 (compartidos) + **`sim_v4/`** (manifiesto y datos del dominio de SIM, casos de prueba) y **`banco_v4/`** (insumos y protocolo del banco) | todo |
| `datos/procesados/v4.0/` | insumos de SIM armados desde cada ficha (regenerables) | `incendios_sl.eventos` |
| `resultados/v4.0/` | una carpeta por corrida; `banco/` (corridas, Fase 1 y web de V.4) | se escribe acá |
| `docs/v4.0/` | informes 01–13 (de v3.0), 14 integración, 15 verificación, 16 protocolo del banco, `FLUJO.md` | — |

El código encuentra esas carpetas cuando está en `<repo>/src/v4.0`. Para otra disposición, las variables de entorno de
v3.0 (`INCENDIOS_SL_REPO`, `INCENDIOS_SL_INPUT`, `INCENDIOS_SL_RESULTADOS`, …) más `INCENDIOS_SL_SIM_DATOS`.

## Instalación
Python ≥ 3.12 (verificado con 3.14.7 en Windows 11). Desde `src/v4.0`:
```bash
pip install -r requirements.txt
pip install -e . --no-deps
python -m pytest -q                                              # 140 pruebas, ~2 min, sin red
python scripts/correr_escenario.py --escenario prueba_rapida_v4  # 6 h de Las Lagunas 2024 con barreras y contención
```
No necesita WindNinja ni numba. Google Earth Engine solo para preparar compuestos NDVI/NDMI de meses nuevos.

## Comandos
```bash
# correr un escenario (escenarios/v4.0/corridas/<nombre>.yaml) → resultados/v4.0/<nombre>_<fecha>/
python scripts/correr_escenario.py --escenario local_mesilla_2024 [--sin-sha]
python scripts/correr_escenario.py --archivo mi_corrida.yaml
# visor autónomo de una corrida e índice de corridas
python scripts/exportar_visor.py --run-id <run_id>
python scripts/exportar_indice.py
# SIM directo (manifiesto en datos/inputSimulacion/sim_v4)
python -m simulador validar
python -m simulador run --config ../../escenarios/v4.0/sim/ejemplo_las_lagunas_2023.yaml
python -m simulador caso ../../datos/inputSimulacion/sim_v4/conjunto_prueba/las_lagunas_la_aguada_2023 --todas
# banco de evaluación de V.4 (protocolo: docs/v4.0/16)
python app/motores/sim_adaptador.py --evento MB_2022_43580_2022-09-10 [--modelo modelo_v3] [--l03 500] [--solo-preparar]
python app/banco/registro.py; python app/banco/fase1.py; python app/banco/l03_resumen.py; python app/web/construir.py
```
(`python -m simulador` necesita `src` en el `PYTHONPATH` o el paquete instalado con `pip install -e .`.)

## Estructura del código
```
src/simulador/      rutas (repositorio estándar), config (valores por defecto = modelo_v3), corrida, sintetico
                    ca/ (automata: Huygens, barreras por enlace · contencion: combate v3.0 · supresion: L03)
                    physics/ (rothermel, humedad, viento, elipse) | fuel/ (SB40, generador MapBiomas→SB40)
                    io/ (grilla, manifiesto, capas, meteo) | outputs/ | evaluacion/
src/incendios_sl/   config (API de v3.0), eventos (ficha → insumos de SIM), arribo, escenario (variantes), resumen
scripts/            correr_escenario.py (punto de entrada), exportar_visor.py, exportar_indice.py, preparar_datos.py (V.4)
web/                plantilla del visor autónomo
app/                banco de V.4: motores/ (adaptador, despacho), banco/, evaluador/, evaluacion/, web/, preprocesamiento/
config/             rutas.yaml (banco) y herramientas.ejemplo.yaml
```

Licencias de datos: MapBiomas (CC-BY 4.0), Open-Meteo y ERA5 (CC-BY 4.0), Copernicus DEM, Sentinel-2, VIIRS/MODIS
(NASA FIRMS), SNMF (Argentina), OSM/IGN/Secretaría de Energía, Ministerio de Seguridad de San Luis (cuarteles).
