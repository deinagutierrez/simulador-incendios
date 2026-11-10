# Caso de prueba · Las Lagunas – Potrerillos · 2024 (caso de estrés)

Adaptación del caso `conjunto_pruebas/casos/SM05_2024_LAS_LAGUNAS_POTRERILLOS` al estándar de la sección 7.1 del simulador.
**La carpeta original no se modificó.** Preparado el 2026-10-07 por `scripts/preparar_datos.py`.

## Datos del evento

| | |
|---|---|
| Parte SNMF | LAS LAGUNAS / POTRERILLOS · inicio 2024-09-18 · fin 2024-10-09 (Extinguido) |
| Punto SNMF por defecto | lat -32.6367, lon -65.5477 (x 3542441.6, y 6389418.4) · dentro de la cicatriz |
| Cicatriz COE | 38631.18 ha (AQ2024_0001, AQ2024_0076), 9 fragmento(s), 100 % dentro del dominio |
| Otras superficies | SMF 48226.0 ha · Sentinel-2 dNBR 25437.0 ha (evento 2024-003: 25423.0 ha recalculadas) |
| Caja de simulación | xmin 3514620 · ymin 6370890 · xmax 3560550 · ymax 6411570 → 1531 × 1356 celdas, alineada a la grilla del dominio |
| t0 base | 2024-09-18T15:43:00-03:00 (hora del primer pase VIIRS) |
| Ventana base | 72 h |

## Mapeo desde el formato anterior

| Estándar 7.1 | Origen en conjunto_pruebas | Transformación |
|---|---|---|
| `caso.yaml` | `caso.json` | reescrito; conserva fechas, bbox, ignición y notas |
| `ignicion.geojson` | `ignicion.geojson` + focos VIIRS | atributos `id`, `hora_ignicion`, `usar`; por defecto los focos del primer pase dentro de la cicatriz |
| `meteo_horaria.csv` | `meteo_horaria.csv` (ERA5/Open-Meteo) | ERA5 (ECMWF/C3S) vía Open-Meteo Historical Weather API, models=era5, celda (-32.5, -65.5), descargado 2026-10-07; punto = centroide de la cicatriz; desde 24 h antes de t0 |
| `combustible_pre_evento.tif` | — (generado) | MapBiomas Col.3 **2023** + NDVI/NDMI **verano 2024** con los terciles de `umbrales_ndvi.csv` (regla 3.3) |
| `indices_mes_evento.tif` | — | `NDVI_NDMI_2024_09.tif` del dominio (mes del incendio) |
| `ndvi_verano_previo.tif` | — | mediana NDVI ene–mar 2024 (para el curado) |
| `perimetro_observado.geojson` | `perimetro_final.geojson` | + `fecha`, `fuente` |
| `perimetro_mapbiomas_fuego_2024.geojson` | `Datos_SL_Completo/Fuego_MapBiomas` | quemado mensual 2024 vectorizado dentro de la caja (meses [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]) |
| `perimetro_s2_evento_2024-003.geojson` | `_anclado_viirs/evento_2024-003.geojson` | mismo evento (Sentinel-2 dNBR anclado en VIIRS, 25.437 ha); subestima la cicatriz COE |
| `focos_viirs.geojson` | FIRMS local (`viirs_snpp_san_luis_recortado.csv`) | 2024-09-15 → 2024-10-10, a < 10 km de la caja: 2092 focos, **1988 dentro de la caja, 1350 dentro de la cicatriz** |
| `obs_perimetro_final_30m.tif`, `.gpkg`, `partes_diarios.csv`, `curva_area_tiempo.csv` | — | no se copian: la información está en `perimetro_observado.geojson` y en este LEEME |

El GeoTIFF `sim_SM05_2024_LAS_LAGUNAS_POTRERILLOS_simulador_toa.tif` que escribe cada corrida es compatible con `conjunto_pruebas/validacion/evaluar_simulacion.py`
(misma grilla que `obs_perimetro_final_30m.tif`, minutos desde t0, NaN donde no arde).

## Combustible pre-evento dentro del perímetro COE

| Mapa | Distribución (%) |
|---|---|
| pre-evento (cob. 2023 + verano 2024) | {'TU5': np.float64(49.0), 'GS2': np.float64(12.3), 'SH5': np.float64(10.4), 'TU1': np.float64(8.7), 'GR4': np.float64(6.3), 'SH2': np.float64(3.2), 'NB3': np.float64(2.7), 'GR2': np.float64(2.5), 'GR7': np.float64(2.3), 'GR1': np.float64(1.4), 'GR6': np.float64(0.7), 'SH7': np.float64(0.3), 'GS1': np.float64(0.1), 'NB9': np.float64(0.0), 'NB1': np.float64(0.0)} |
| anual 2024 (cob. 2024 + verano 2024) | {'TU1': np.float64(31.3), 'TU5': np.float64(22.3), 'GS2': np.float64(18.4), 'SH2': np.float64(7.5), 'SH5': np.float64(5.9), 'GR4': np.float64(4.8), 'NB3': np.float64(3.4), 'GR7': np.float64(2.2), 'GR2': np.float64(2.0), 'GR1': np.float64(1.4), 'GR6': np.float64(0.4), 'SH7': np.float64(0.2), 'GS1': np.float64(0.1), 'NB9': np.float64(0.0), 'NB1': np.float64(0.0)} |

Coincidencia celda a celda entre ambos mapas en todo el dominio: 68.7 %. Para las clases leñosas el mapa anual usa el NDVI
promedio de tres veranos (2023–2025); el pre-evento usa solo el verano 2024 para no incorporar información posterior al incendio.

## Focos VIIRS e ignición múltiple

El primer pase VIIRS S-NPP del evento (18-09-2024 18:43 UTC, 15:43 local) detecta 50 focos entre x 3.528.572 y 3.537.174 (9 km de
este a oeste, y ≈ 6.389.600), con FRP de hasta 110 MW. El parte "Potrerillos" (3.535.349, 6.388.840) cae dentro de ese cúmulo; el
parte "Las Lagunas" (3.542.442, 6.389.418) queda 5 km al este del foco más oriental. Los pases siguientes (19-09 01:00 y 03:00
local, 15:00 local; 20-09 02:00 y 15:00 local, con 544 y 579 focos) muestran la expansión hacia el norte y el este. La actividad
termina el 24-09; los partes siguen hasta el 09-10 (contenido desde el 28-09).

La ignición base reproduce el estado observado en el primer pase: los focos de ese pase que caen dentro de la cicatriz COE se
encienden a las 15:43. Es una ignición múltiple **observada**, no un supuesto. Las variantes desde los puntos de los partes a las
12:00 permiten ver si un único foco explica la extensión del primer pase.

## Incertidumbres

- Ignición: dos partes SNMF a 7 km (Las Lagunas y Potrerillos) y 50 focos VIIRS a lo largo de 9 km en el primer pase (15:43 local): varias igniciones o un fuego de la mañana. Base = focos del primer pase; variantes desde cada parte a las 12:00.
- El perímetro COE es el acumulado de 21 días con supresión (6 brigadas, aviones); la corrida base es de 72 h de propagación libre. La variante de 144 h cubre el período de actividad VIIRS (18 → 24-09).
- Superficies discrepantes entre fuentes: COE 38.631 ha, SMF 48.226 ha, Sentinel-2 dNBR 25.437 ha.
- Un solo punto ERA5 (celda de 0,25°) para una caja de 46 × 41 km con relieve serrano: el viento real varió dentro del área.
- El combustible pre-evento usa cobertura 2023 + NDVI verano 2024; no se corrigen áreas quemadas en 2022–2023 dentro de la caja.
- Las variantes bosque_gs2 / agricola_gr1 reasignan TU5 y TU1 → GS2 y NB3 → GR1: son hipótesis de calibración, no datos.
