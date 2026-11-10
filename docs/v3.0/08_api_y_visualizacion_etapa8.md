# Etapa 8 — API y visualización interactiva

Fecha: 2026-10-14. Código: `src/incendios_sl/api/` (FastAPI), `web/` (Leaflet + Chart.js, sin paso de compilación), `scripts/servir.py`. Pruebas: `tests/test_api.py` (5 pruebas; las que requieren productos o resultados se omiten si no existen).

## 1. Ejecución

```bash
python scripts/servir.py --puerto 8000
```

Abre `http://127.0.0.1:8000/` (interfaz) y `http://127.0.0.1:8000/docs` (documentación OpenAPI generada). Requisitos: datos de la Etapa 3 preparados para al menos un evento y la biblioteca de viento del dominio.

## 2. API (`/api`)

| Método y ruta | Función |
|---|---|
| `GET /info` | versión, configuración del modelo vigente (incluidos los k calibrados), lista de estados de trabajo |
| `GET /areas` | dominios configurados: CRS, resolución, celdas de la grilla y del dominio, superficies, bounds lon/lat, DEM, si existe biblioteca de viento |
| `GET /incendios`, `GET /incendios/{id}` | fichas de eventos (referencia, inicio/fin, hipótesis de hora, igniciones y alternativas, ventanas de datos, notas, si los datos están preparados) |
| `GET /incendios/{id}/focos` | focos de calor VIIRS (o MODIS) del catálogo |
| `POST /preparacion` `{evento, sin_viento}` | lanza `scripts/preparar_evento.py` como proceso independiente; estado `preparando_datos` |
| `POST /simulaciones` `{evento, hipotesis, k_global?, k_clase?, factor_waf, horas?, ignicion, run_id?, figuras}` | lanza `scripts/validar.py` como proceso independiente (409 si los datos no están preparados o el `run_id` existe) |
| `GET /simulaciones` | listado de corridas con estado, evento, superficie, motivo de fin, IoU en el primer instante de evaluación |
| `GET /simulaciones/{run_id}` | estado + registro + métricas + bounds del resultado |
| `DELETE /simulaciones/{run_id}` | cancela el proceso (estado `cancelada`) |
| `GET /simulaciones/{run_id}/serie` | serie horaria (superficie, celdas activas, meteorología, humedad, tiempo de cómputo) |
| `GET /simulaciones/{run_id}/estado/{t_s}.png` | superposición PNG (EPSG:3857) del estado a `t_s` segundos desde la ignición: quemado (naranja) y frente de la última hora (amarillo); derivada del tiempo de llegada, sin re-simular |
| `GET /simulaciones/{run_id}/perimetro/{t_s}.geojson` | perímetro vectorial simplificado (60 m) en WGS84 |
| `GET /simulaciones/{run_id}/viento/{t_s}.geojson` | flechas de viento a 10 m de la hora (campo WindNinja escalado, muestreo cada 2 km) |
| `GET /simulaciones/{run_id}/archivo/{nombre}` | descarga de archivos de la corrida (rasters, CSV, JSON, figuras) |
| `GET /capas/{dominio}/{nombre}.png` (+ `/info`) | capas estáticas reproyectadas a Web Mercator: `sombras`, `pendiente`, `mascara`, y por evento `combustible`, `ndvi`, `ndmi`, `cicatriz` |
| `GET /vectores/{dominio}/{nombre}.geojson` | `caminos`, `viviendas`, `electricidad_mt` simplificados (30 m) en WGS84 |

### 2.1 Trabajos y estados
Cada trabajo corre en un **proceso independiente** (`subprocess`) y persiste `estado.json` en `data/resultados/<run_id>/` con escritura atómica; la API nunca bloquea durante la preparación de datos, GEE, WindNinja ni la simulación. Estados: `pendiente → ejecutando_simulacion (progreso por hora simulada, superficie, frente activo, tiempo transcurrido) → guardando_resultados → completada | fallida | cancelada`; preparación: `preparando_datos → completada | fallida`. **`completada` se asigna solo tras verificar** que existen y se abren `t_llegada_s.tif`, `estado_final.tif`, `serie_horaria.csv`, `registro.json` y `metricas.json`. Los errores se exponen en `estado.mensaje`/`estado.error` con la cola del registro del proceso (sin credenciales: el proceso no recibe secretos). Las corridas anteriores sin `estado.json` se reconocen como completadas si tienen sus archivos.

Prueba de extremo a extremo realizada: `POST /simulaciones` (6 h del evento 2024) → sondeo de estado → `completada` con resultados verificados; `DELETE` sobre un trabajo en curso → `cancelada`.

### 2.2 Representación para la web
Los resultados originales (30 m, EPSG:5345) no se modifican. Para Leaflet se reproyecta una vez por corrida el tiempo de llegada a EPSG:3857 (caché en memoria) y cada instante se obtiene por umbral (PNG RGBA de ~10–20 KB). Las capas de contexto se reproyectan una vez y se cachean. Ninguna capa dibuja celdas como polígonos; los perímetros se generan bajo demanda y simplificados.

## 3. Interfaz web (`web/`)
- **Mapa Leaflet** con mapas base (OpenStreetMap, Esri satélite), control de capas y escala; capas: área (máscara fuera del dominio), sombreado y pendiente, mapa de combustibles, NDVI/NDMI, cicatriz observada (cian), superficie quemada simulada (naranja) y frente (amarillo), perímetro vectorial, viento (flechas orientadas hacia donde sopla, tamaño por velocidad), rutas y caminos, tendido eléctrico MT, viviendas, focos de calor por día, puntos de ignición.
- **Controles:** selector de incendio, información del área y del evento, simulación guardada, hipótesis de hora de ignición, ignición (SNMF o alternativa), fecha-hora inicial/final (UTC), k global (vacío = calibrado por clase) y factor WAF, botón iniciar (lanza la preparación si faltan datos), cancelar, barra de progreso, estado del proceso, mensajes de error; reproducir / pausa / reiniciar, barra temporal, velocidad de reproducción, hora simulada; vista lado a lado (dos mapas sincronizados).
- **Panel de resultados:** hora simulada, superficie y celdas quemadas, celdas del frente, superficie de referencia, diferencia absoluta y relativa, IoU (solo en instantes de evaluación, con las demás métricas en el bloque de métricas), temperatura, HR, viento, humedad del combustible, estado y motivo de fin; gráficos de superficie quemada vs tiempo (con referencia) y de meteorología.
- **Escala y rendimiento:** superficie de la grilla y efectiva del dominio, resolución, número de celdas, CRS, dominio no reducido, tiempo de cómputo, pasos, memoria.
- **Diseño:** panel lateral de 380 px y mapa a pantalla completa; en pantallas < 900 px el panel se pliega (botón ☰) y los controles se apilan.
- Al mover la barra temporal se cambia la URL de la superposición; no se vuelve a ejecutar la simulación.

Verificado en el navegador integrado: carga de catálogos y capas, selección del evento 2024 con la corrida calibrada, barra temporal (hora 60 → 47.883 ha, 21/09 03 UTC), control de capas; consola sin errores.

## 4. Limitaciones
- Los mapas base requieren acceso a Internet (teselas externas); sin conexión se ven solo las capas propias.
- Un trabajo de simulación a la vez por `run_id`; no hay cola con prioridad ni autenticación (uso local).
- Las flechas de viento muestran el campo de WindNinja a 100 m remuestreado; su resolución efectiva se indica en el GeoJSON.
- La vista lado a lado replica solo sombreado y superficie simulada en el segundo mapa.
