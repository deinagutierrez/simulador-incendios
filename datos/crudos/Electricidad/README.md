# Tendidos eléctricos de San Luis – Visor SIG Secretaría de Energía

Fuente: Visor Espacial WebGIS de la Secretaría de Energía de la Nación
(https://sig.energia.gob.ar/v/), servicio WFS `https://sig.energia.gob.ar/wmspubmap`.
Descargado el 10/09/2026. CRS de todos los archivos: EPSG:4326 (WGS 84).

Recorte: las capas nacionales se recortaron con el límite de la Provincia de San Luis
del IGN (capa `ign:provincia`, WFS https://wms.ign.gob.ar/geoserver). Las líneas de
transmisión que cruzan el límite quedan cortadas en el límite provincial.

| Archivo | Capa del visor (menú Eléctrica) | Capa WFS origen | Geometría | Entidades |
|---|---|---|---|---|
| lineas_transmision_electrica_SL.geojson | Transporte → Líneas de transmisión eléctrica | union_cammesa_lineas_transporte | MultiLineString | 20 |
| estaciones_transformadoras_AT_MT_SL.geojson | Transporte → Estaciones transformadoras eléctricas AT/MT | electrica_transporte_visor_eett | Point | 1 (ET Luján 500 kV) |
| estructuras_cables_AT_SL.geojson | Transporte → Estructuras de cables eléctricos AT | electrica_transporte_visor_estructuras | Point | 489 |
| centrales_generacion_SL.geojson | Generación → Centrales de generación de energía | visor_centrales_unificacion | Point | 16 |
| red_distribucion_MT_EDESAL_SL.geojson | Distribución → San Luis - Cables eléctricos MT | edesal_red_mt | LineString | 88.387 |
| limite_provincia_san_luis_IGN.geojson | (límite usado para el recorte) | ign:provincia | MultiPolygon | 1 |

Notas:
- La capa nacional de estaciones transformadoras solo trae 323 estaciones en todo el país
  (principalmente red de 500 kV de Transener); en San Luis solo figura Luján. Las ET de 132 kV
  (San Luis, Villa Mercedes, La Toma, Tilisarao, Santa Rosa, Merlo, etc.) no están en el visor
  como puntos, pero se deducen de los nombres de las líneas de transmisión.
- La red de media tensión de EDESAL tiene un único atributo (`tension_kv`, 13.2 y 33 kV).
- Las estructuras AT (postes/torres) traen `id_linea` y `fuente` (Transener, Distrocuyo, etc.).
