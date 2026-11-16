# Resultado del prerregistro E-E3-2 — Índices por AWS frente a Google Earth Engine

Evaluación formal generada por `herramientas/e_e3_2.py`. Prerregistro: `E-E3-2_indices_aws.md` (etiqueta `prerregistro-E-E3-2`); escala elegida antes de medir: `E-E3-2_escala.md` (desplazamiento 0.0).

## Veredicto

**Global: no se cumple.**

| Criterio | Umbral | Resultado |
|---|---|---|
| 1. Diferencia absoluta mediana de NDVI y NDMI, en (a) y en (b) | ≤ 0,02 | **se cumple** ((a): **se cumple**; (b): **se cumple**) |
| 2. Celdas que cambian de clase de combustible, en cada motor | < 3 % | **no se cumple** |
| 3. IoU entre huellas a las 48 h, en cada motor | ≥ 0,95 | **no se cumple** |

## Quién y con qué

| | |
|---|---|
| Fecha | 2026-11-16 14:59 |
| Evaluó | LisandroV2002 |
| Código | cambio de git `d4118d82d039` (rama `f7-entrega`); código sin registrar: 0 archivo(s) |
| Motores congelados | sha256 del conjunto `2b32757194d2510bcbc680056f803694be064fc968e35de9c1ab579c10621106`; intactos antes: sí; después: sí |
| Equipo | Windows-11-10.0.26300-SP0, 12 núcleos, Python 3.14.2 |
| Alcance | (a), (b) y (c) |
| Archivo completo | `E-E3-2_resultados.json` |

## Insumos (sha256)

| Insumo | Archivo | sha256 |
|---|---|---|
| ficha_v31 | `escenarios/v3.1/eventos/SL-2024-LASLAGUNAS.yaml` | `730c4aca89ead23a…` |
| ficha_v40 | `escenarios/v4.0/eventos/SL-2024-LASLAGUNAS.yaml` | `8ff452244d6a2169…` |
| ndvi_30m_gee | `datos/inputSimulacion/combustibles/SL-2024-LASLAGUNAS/ndvi_30m_SL-2024-LASLAGUNAS.tif` | `9caecd1b1e02ec4d…` |
| ndmi_30m_gee | `datos/inputSimulacion/combustibles/SL-2024-LASLAGUNAS/ndmi_30m_SL-2024-LASLAGUNAS.tif` | `c8dbfe3b53a19f97…` |
| clase_v31_evento | `datos/inputSimulacion/combustibles/SL-2024-LASLAGUNAS/combustible_clase_SL-2024-LASLAGUNAS.tif` | `32ed159618fdb348…` |
| mensual_gee | `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_2024_09.tif` | `f3aca19f4a224520…` |
| meteo_dominio | `datos/inputSimulacion/meteo/SL-2024-LASLAGUNAS_ecmwf_ifs_20240917T00_20241010T03_b839008a1f1545e2_dominio.csv` | `a2496054ef2cd3ff…` |
| verano_v40_01 | `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_2024_01.tif` | `f28c9ca1adbef044…` |
| verano_v40_02 | `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_2024_02.tif` | `3c6a511dd5ef9755…` |
| verano_v40_03 | `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_2024_03.tif` | `b88b647dac7e57e6…` |
| cobertura_2023 | `datos/inputSimulacion/cobertura/cobertura_mapbiomas_col3_2023_las_lagunas_potrerillos.tif` | `7434bea474fa40d3…` |

## (a) Compuesto de ventana, Las Lagunas 2024, a 30 m

32 escenas en el catálogo (≤ 80 % de nubes por tesela), 8 fechas con datos. Celdas con dato en los dos productos.

| Índice | Celdas comparadas | Dif. abs. mediana | Percentil 95 | Dif. mediana (AWS − GEE) | Sin dato AWS | Sin dato GEE |
|---|---|---|---|---|---|---|
| NDVI | 2.793.912 | 0,0053 | 0,022 | 0,0032 | 0,00 % | 0,00 % |
| NDMI | 2.793.912 | 0,0062 | 0,024 | -0,0034 | 0,00 % | 0,00 % |

## (b) Compuesto mensual, septiembre de 2024

24 escenas en el catálogo (≤ 80 % de nubes por tesela), 6 fechas con datos. Celdas con dato en los dos productos.

| Índice | Celdas comparadas | Dif. abs. mediana | Percentil 95 | Dif. mediana (AWS − GEE) | Sin dato AWS | Sin dato GEE |
|---|---|---|---|---|---|---|
| NDVI | 2.793.912 | 0,0016 | 0,030 | 0,0000 | 0,00 % | 0,00 % |
| NDMI | 2.793.912 | 0,0007 | 0,019 | 0,0000 | 0,00 % | 0,00 % |

## (c) Efecto en el modelo

Dos eventos generados con `app/datos/evento_rt.py` (RT-20240921-1 con índices de GEE, RT-20240921-2 con índices de AWS), la misma serie meteorológica del evento, ignición en los puntos de la ficha a las 2024-09-18T15:00:00Z (hipótesis 1), 48 h. Cobertura: evento real 2023, eventos generados {'gee': 2023, 'aws': 2023}, SB40 de v4.0 {'gee': 2023, 'aws': 2023} (coincide).

| Motor | Cambio de clase | Sobre celdas combustibles | IoU 24 h | IoU 48 h | Sup. 48 h GEE | Sup. 48 h AWS | Dif. 48 h |
|---|---|---|---|---|---|---|---|
| v4.0 | 11,943 % | 12,632 % | 0,9096 | 0,8946 | 13122 ha | 13272 ha | 150 ha (1,14 %) |
| v3.1-librev2 | 0,188 % | 0,190 % | 0,9966 | 0,9973 | 38142 ha | 38197 ha | 56 ha (0,15 %) |

Control (no es criterio): fracción de celdas con clase distinta entre el evento generado con GEE y el mapa del evento real; mide cuánto agrega el camino de los eventos generados (paso por int16 × 10000).

- v4.0: 0,0000 %
- v3.1-librev2: 0,5839 %

## Lo que hay que saber para leerlo

- Denominador del cambio de clase (criterio 2): todas las celdas del dominio con dato en los dos mapas; se informa también sobre las celdas combustibles en alguno de los dos. Lo fijó quien escribe, antes de ver resultados.
- En (c) los dos eventos generados reciben los índices a 30 m en int16 × 10000 (la carga manual de índices); los de GEE salen de `ndvi_30m`/`ndmi_30m` del evento y los de AWS de (a). Recorren el mismo camino; la única diferencia es el índice.
- En v4.0 los índices de la ventana entran como `indices_mes_evento`, y el combustible SB40 (regla 3.3b) y el NDVI de verano salen de los compuestos de enero a marzo. Opción A (D-E3-27, decidida antes de evaluar): el lado AWS de v4.0 usa enero a marzo de 2024 hechos por AWS (`verano_aws`) y el lado GEE los del repositorio; la procedencia del SB40 lo comprueba. La comparación de esos compuestos con los de GEE es informativa: no entra en el criterio.
- La cobertura MapBiomas la elige `evento_rt` (año anterior a la fecha de inicio por defecto del evento generado); se comprueba que coincida con la del evento real (`cobertura_anio` de la ficha) y si no coincide (c) no se corre.
- Un solo evento y una sola época (fin de invierno de un año seco); la comparación (c) usa un evento visto (límites declarados en el prerregistro).

## Cómo repetirlo

```
python herramientas/e_e3_2.py --evaluador NOMBRE
```
