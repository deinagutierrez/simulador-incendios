# Datos: qué hay, de dónde viene y con qué licencia

El equipo del proyecto confirmó el 2026-11-10 que todos los datos de este repositorio se pueden publicar.
La columna de licencia repite lo que declaran los documentos del proyecto (`src/v4.0/README.md`); donde dice "a confirmar",
el proyecto no tiene registrada la licencia exacta.

## En el repositorio (datos mínimos, 464 MB)

| Carpeta | Contenido | Fuente | Licencia o condición |
|---|---|---|---|
| `datos/inputSimulacion/dem` | elevación, pendiente y orientación a 30 m | Copernicus DEM GLO-30 | uso libre con atribución a Copernicus / ESA |
| `datos/inputSimulacion/cobertura` | cobertura del suelo 2021 a 2025 | MapBiomas Argentina, Colección 3 | CC-BY 4.0 |
| `datos/inputSimulacion/infraestructura` | caminos, viviendas, red eléctrica de media tensión, tiempo de arribo desde cuarteles | OpenStreetMap, IGN, SIG de San Luis; EDESAL; Ministerio de Seguridad de San Luis | OpenStreetMap: ODbL, con atribución. EDESAL y Ministerio de Seguridad: publicación confirmada por el equipo; licencia a confirmar |
| `datos/inputSimulacion/barreras` | caminos como barreras por enlace (producto de v3.x) | derivado de los caminos | la de los caminos |
| `datos/inputSimulacion/viento` | biblioteca de viento sobre el relieve, 72 direcciones, 100 m, **partida en cuatro archivos** | generada por el proyecto con WindNinja 4.0.0 sobre el DEM | producto propio |
| `datos/inputSimulacion/grilla`, `sim_v4/dominio` | grilla y máscara del dominio | producto propio | — |
| `datos/inputSimulacion/sim_v4/estaticos` | topografía, combustibles SB40 e infraestructura en el formato de v4.0 | derivados de las capas anteriores; parámetros de Scott y Burgan (2005) | las de sus fuentes |
| `datos/inputSimulacion/sim_v4/dinamicos` | compuestos mensuales NDVI/NDMI 2023 y 2024 | Sentinel-2 (Copernicus), procesado en Google Earth Engine | datos Copernicus Sentinel, uso libre con atribución |
| `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_2026_0{1,2,3}.tif` | compuestos mensuales NDVI/NDMI de enero a marzo de 2026 (verano que usa v4.0 para eventos de 2026), con su `.json` de procedencia (escenas, fechas, método) | Sentinel-2 L2A (Copernicus) en AWS, catálogo Earth Search de Element 84, generado el 2026-11-13 con `app/datos/sentinel2.py` (método de SIM: NDMI con B8A, 30 m, vecino más cercano; máscara SCL en lugar de Cloud Score+) | datos Copernicus Sentinel, uso libre con atribución |
| `datos/inputSimulacion/sim_v4/conjunto_prueba` | casos La Aguada 2023 y Potrerillos 2024 (v4.0 los exige para arrancar) | cicatrices del COE, MapBiomas Fuego, focos VIIRS, ERA5 | MapBiomas CC-BY 4.0; FIRMS de uso libre; ERA5 CC-BY 4.0; COE a confirmar |
| `datos/inputSimulacion/{combustibles,eventos,meteo}/SL-2024-LASLAGUNAS` | evento de ejemplo: índices, combustibles, cicatriz, meteorología | Sentinel-2, MapBiomas Fuego, ECMWF IFS vía Open-Meteo | Open-Meteo CC-BY 4.0; el resto como arriba |
| `datos/inputSimulacion/{combustibles,eventos,meteo}/SL-2023-CHACRASOCT` | Las Chacras octubre 2023 (21 MB), agregado el 2026-11-11 para que cualquiera pueda repetir el prerregistro E-E3-1 (decisión D-E3-15). **Es uno de los cinco eventos no vistos (X-49)**: v3.1 y v4.0 ya se evaluaron una vez contra él; no usarlo para ajustar nada | las mismas | las mismas |
| `datos/inputSimulacion/catalogo` | focos de calor por evento, incendios y registros del dominio | NASA FIRMS (VIIRS, MODIS); MapBiomas Fuego; Servicio Nacional de Manejo del Fuego | FIRMS de uso libre; SNMF: publicación confirmada por el equipo |
| `datos/crudos` | cuarteles, departamentos, dominio, registros del SNMF 2020–2026, focos NOAA-20 | Ministerio de Seguridad de San Luis; IGN / CONAE; SNMF; NASA FIRMS | como arriba |

La biblioteca de viento pesa 161 MB y GitHub no acepta archivos de más de 100 MB. Está partida en `*.nc.part00` a `.part03`;
los motores arman el archivo completo la primera vez que lo usan. El archivo armado no se sube (`.gitignore`).
sha256 del archivo original: `c260efc76eb36bd600fc9628cb9ef74237a0c9069f5be070bf188d5df2811efc`.

## Fuera del repositorio (datos históricos)

No hacen falta para instalar ni para el simulador en tiempo real. Sirven para el modo histórico y para repetir las
validaciones. **Todavía no están publicados**; se subirán como archivo adjunto de una publicación de GitHub, con un script
que los baje y verifique.

| Contenido | Tamaño aproximado |
|---|---|
| Meteorología, índices, combustibles, cicatriz y focos de los otros 13 eventos | 310 MB |
| Banco de evaluación de v4.0 (`banco_v4`) y casos del banco | 290 MB |
| Datos crudos pesados: caminos y viviendas de toda la provincia, MapBiomas cobertura y fuego | 190 MB |
| Resultados de corridas de referencia | a definir |

## Datos que el simulador bajará al usarse

| Dato | Servicio | Clave |
|---|---|---|
| Meteorología y pronóstico | Open-Meteo (CC-BY 4.0) | no necesita |
| NDVI y NDMI recientes | Sentinel-2 L2A en AWS, catálogo Earth Search | no necesita |
| Focos de calor activos (opcional) | NASA FIRMS | clave personal del usuario, por variable de entorno |
| Índices por Google Earth Engine (opcional) | Google Earth Engine | credenciales personales |

Lo bajado queda en `datos/procesados/app/` (no se sube): tomas de pronóstico (`meteo/`), tomas de índices (`indices/`),
escenas ya leídas (`sentinel2/escenas/`) y trabajos de datos (`trabajos/`), cada producto con su JSON de procedencia. Los eventos
generados `RT-…` se escriben en `escenarios/*/eventos/` y `datos/inputSimulacion/` y tampoco se suben (`.gitignore`).

## Biblioteca de terceros incluida

`app/web/vendor/leaflet/`: Leaflet 1.9.4 (mapas en el navegador), © Volodymyr Agafonkin, licencia BSD de 2 cláusulas
(archivo `LICENSE` en esa carpeta). Bajada de `unpkg.com/leaflet@1.9.4` el 2026-11-11.

## Atribuciones a mostrar

Relieve: Copernicus DEM GLO-30 · Cobertura y cicatrices: MapBiomas · Meteorología: Open-Meteo, ECMWF · Imágenes: datos
Copernicus Sentinel modificados · Focos: NASA FIRMS · Caminos y viviendas: © colaboradores de OpenStreetMap, IGN ·
Red de media tensión: EDESAL · Cuarteles: Ministerio de Seguridad de San Luis · Registros de incendios: SNMF.
