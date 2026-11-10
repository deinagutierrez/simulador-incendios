# Caso de prueba · Las Lagunas y La Aguada · 2023

Adaptación del caso `conjunto_pruebas/casos/SM01_2023_LAS_LAGUNAS_Y_LA_AGUADA` al estándar de la sección 7.1 del simulador.
**La carpeta original no se modificó.** Preparado el 2026-10-07 por `scripts/preparar_datos.py`.

## Datos del evento

| | |
|---|---|
| Parte SNMF | LAS LAGUNAS Y LA AGUADA · inicio 2023-08-31 · fin 2023-09-01 (Extinguido) |
| Punto SNMF por defecto | lat -32.596694, lon -65.627417 (x 3534976.9, y 6393884.0) · fuera de la cicatriz |
| Cicatriz COE | 105.42 ha (AQ2023_0060), 1 fragmento(s), 100 % dentro del dominio |
| Otras superficies | SMF None ha · Sentinel-2 dNBR 145.5 ha (evento 2023-007: 145.4 ha recalculadas) |
| Caja de simulación | xmin 3529230 · ymin 6388890 · xmax 3540540 · ymax 6400170 → 377 × 376 celdas, alineada a la grilla del dominio |
| t0 base | 2023-08-31T12:00:00-03:00 (supuesta, 12:00 local) |
| Ventana base | 36 h |

## Mapeo desde el formato anterior

| Estándar 7.1 | Origen en conjunto_pruebas | Transformación |
|---|---|---|
| `caso.yaml` | `caso.json` | reescrito; conserva fechas, bbox, ignición y notas |
| `ignicion.geojson` | `ignicion.geojson` + focos VIIRS | atributos `id`, `hora_ignicion`, `usar`; por defecto el punto `snmf_proyectado` (dentro de la cicatriz) |
| `meteo_horaria.csv` | `meteo_horaria.csv` (ERA5/Open-Meteo) | ERA5 (ECMWF/C3S) vía Open-Meteo Historical Weather API, models=era5, celda (-32.5, -65.75), descargado 2026-10-07; punto = centroide de la cicatriz; desde 24 h antes de t0 |
| `combustible_pre_evento.tif` | — (generado) | MapBiomas Col.3 **2022** + NDVI/NDMI **verano 2023** con los terciles de `umbrales_ndvi.csv` (regla 3.3) |
| `indices_mes_evento.tif` | — | `NDVI_NDMI_2023_08.tif` del dominio (mes del incendio) |
| `ndvi_verano_previo.tif` | — | mediana NDVI ene–mar 2023 (para el curado) |
| `perimetro_observado.geojson` | `perimetro_final.geojson` | + `fecha`, `fuente` |
| `perimetro_mapbiomas_fuego_2023.geojson` | `Datos_SL_Completo/Fuego_MapBiomas` | quemado mensual 2023 vectorizado dentro de la caja (meses [7, 8, 9, 10, 11]) |
| `perimetro_s2_evento_2023-007.geojson` | `_anclado_viirs/evento_2023-007.geojson` | cicatriz distinta, 8 km al NO del perímetro COE; misma denominación en el parte SNMF |
| `focos_viirs.geojson` | FIRMS local (`viirs_snpp_san_luis_recortado.csv`) | 2023-08-28 → 2023-09-06, a < 10 km de la caja: 11 focos, **0 dentro de la caja, 0 dentro de la cicatriz** |
| `obs_perimetro_final_30m.tif`, `.gpkg`, `partes_diarios.csv`, `curva_area_tiempo.csv` | — | no se copian: la información está en `perimetro_observado.geojson` y en este LEEME |

El GeoTIFF `sim_SM01_2023_LAS_LAGUNAS_Y_LA_AGUADA_simulador_toa.tif` que escribe cada corrida es compatible con `conjunto_pruebas/validacion/evaluar_simulacion.py`
(misma grilla que `obs_perimetro_final_30m.tif`, minutos desde t0, NaN donde no arde).

## Combustible pre-evento dentro del perímetro COE

| Mapa | Distribución (%) |
|---|---|
| pre-evento (cob. 2022 + verano 2023) | {'SH2': np.float64(25.0), 'SH5': np.float64(24.4), 'GS2': np.float64(17.5), 'TU1': np.float64(16.4), 'GR2': np.float64(4.4), 'TU5': np.float64(3.7), 'GR4': np.float64(3.0), 'SH7': np.float64(2.8), 'GR1': np.float64(2.0), 'GR7': np.float64(0.8)} |
| anual 2023 (cob. 2023 + verano 2023) | {'SH2': np.float64(28.1), 'GS2': np.float64(24.3), 'TU1': np.float64(24.0), 'SH5': np.float64(12.9), 'TU5': np.float64(3.4), 'GR2': np.float64(3.1), 'GR4': np.float64(2.3), 'GR1': np.float64(1.0), 'GR7': np.float64(0.8), 'SH7': np.float64(0.2)} |

Coincidencia celda a celda entre ambos mapas en todo el dominio: 72.9 %. Para las clases leñosas el mapa anual usa el NDVI
promedio de tres veranos (2023–2025); el pre-evento usa solo el verano 2023 para no incorporar información posterior al incendio.

## Dos cicatrices con el mismo nombre

El parte "Las Lagunas y La Aguada" (un único registro, 31-08-2023) tiene asociado el evento satelital 2023-007 (145,5 ha), pero ese
evento está **8 km al noroeste** de la cicatriz COE que coincide con las coordenadas del parte. Los 11 focos VIIRS del 01-09-2023
(18:26 UTC, FRP máx. 43,8 MW) caen sobre la cicatriz NO. MapBiomas Fuego marca **ambas** como quemadas en agosto de 2023.
Son dos incendios distintos (probablemente uno por paraje). El caso simula la cicatriz COE, que es la del punto del parte; la cicatriz
NO queda documentada para un caso futuro con focos (permitiría comparar tiempos de llegada).

## Incertidumbres

- Hora de ignición desconocida: el parte da el día (31-08) pero no la hora. Variantes t0 06/09/12/15/18 h.
- Punto de ignición del parte a 88,7 m fuera de la cicatriz; se usa el punto proyectado al borde (derivado).
- El perímetro COE no tiene fecha propia; se asume el final del evento (01-09). La ventana de 36 h cubre hasta el fin del 01-09.
- La meteorología es reanálisis ERA5 (celda de 0,25°) en el punto de ignición; no hay estaciones.
- El evento Sentinel-2/VIIRS 2023-007 (145 ha, 8 km al NO) es otra cicatriz con el mismo nombre de parte; no se simula en el caso base.
