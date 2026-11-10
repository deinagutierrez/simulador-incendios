# ¿El fuego simulado es muy rápido o muy lento? Cómo se mide con los focos de calor

Fecha: 2026-10-28. Script: `src/v3.1/scripts/velocidad_vs_focos.py`. Tabla: `resultados/v3.1/evaluacion_temporal/velocidad_vs_focos_linea_base_librev2.csv`.
Corridas evaluadas: la línea base `librev2` con la combinación recomendada de cada ficha (`resultados/v3.0/<EVENTO>-…-librev2`,
`resultados/v3.0/comparacion_libre_vs_librev2_recomendada_20261027.md`). Focos: `datos/inputSimulacion/catalogo/hotspots_v3.1/`
(FIRMS VIIRS SNPP provincial + NOAA-20 de GEE, `docs/v3.1/01`).

## 1. Qué referencia NO sirve
**La fecha de "Contenido" o de extinción del SNMF no mide la velocidad de propagación.** En los incendios chicos el combate
estuvo desde el primer día: esa fecha dice cuándo lo frenaron, no cuánto tardaba el fuego libre en recorrer la cicatriz.
Comparar la simulación libre con esa fecha hacía parecer al modelo "4–10 veces más rápido" (primer diagnóstico del
2026-10-27, descartado). Tampoco sirve comparar sólo el tiempo total hasta quemar la superficie de la cicatriz: Las Lagunas
parecía "a la velocidad correcta" con ese criterio y es el caso más lento.

## 2. Qué referencia sí sirve: la primera detección de cada lugar
Los satélites VIIRS (SNPP y NOAA-20) pasan unas dos veces por día cada uno; cada pasada marca los píxeles de 375 m que están
ardiendo. De ahí sale, para cada lugar, una **ventana** de cuándo llegó el fuego:

```
  pasada anterior (sin foco en ese lugar)            pasada con la primera detección
  ─────────┼────────────────────────────────────────────────┼──────────────▶ tiempo
           │◀──────────── el fuego llegó acá ──────────────▶│
       detección − 13 h                                  detección
```

- Sólo se usa la **primera** detección de cada lugar (ningún foco anterior a ≤ 375 m). Un píxel que sigue ardiendo en las
  pasadas siguientes no dice cuándo llegó el fuego, sólo que sigue encendido.
- La pasada anterior está, como mucho, unas 13 h antes (con dos satélites y nubes ocasionales puede ser más).
- Para cada primera detección se toma la **llegada simulada** más temprana a ≤ 375 m del foco y se calcula
  `diferencia = llegada simulada − detección` (en horas).

| Diferencia | Interpretación |
|---|---|
| entre −13 h y +1 h | **en ventana**: el modelo llega cuando corresponde |
| menor que −13 h | **demasiado rápido**: llega antes de una pasada que no vio fuego ahí |
| mayor que +1 h | **demasiado lento**: el satélite ya veía fuego y el modelo todavía no llegó (o la ignición simulada es posterior) |
| nunca llega | el modelo no quema ese lugar (error de dirección o de forma) |

Por evento se informa la mediana de la diferencia, el rango intercuartil (p25 a p75) y el porcentaje de lugares en cada clase.
Una mediana negativa dentro de la ventana es lo esperable (el fuego llega antes que la pasada que lo detecta).

## 3. Resultado: línea base `librev2` con la combinación recomendada

| Evento | Ignición simulada (UTC) | Primer foco (UTC) | Primeras detecciones | Diferencia mediana (p25 a p75) | Rápido | En ventana | Lento | Diagnóstico |
|---|---|---|---|---|---|---|---|---|
| Piscu Yacu 2022 | 27/08 18:00 | 27/08 19:03 | 28 | −5,3 h (−7,3 a −2,0) | 0 % | **100 %** | 0 % | velocidad correcta |
| Mesilla 2024 | 02/09 11:00 | 02/09 17:28 | 20 | −3,3 h (−3,9 a −1,9) | 5 % | **95 %** | 0 % | velocidad correcta |
| Rincón 2023 | 19/09 04:00 | 19/09 05:25 | 8 | −4,2 h (−11,1 a −2,3) | 12 % | **88 %** | 0 % | velocidad correcta |
| Pampita 2022 | 02/09 16:00 | 02/09 18:50 | 8 | −2,8 h (−5,4 a −0,6) | 12 % | 75 % | 12 % | correcta |
| Puertas 2022 | 12/01 17:00 | 12/01 18:19 | 86 | −3,9 h (−8,4 a −0,2) | 14 % | 65 % | 21 % | correcta, con dispersión |
| Chilcas 2022 | 05/12 04:00 | 05/12 05:24 | 8 | −4,4 h (−7,4 a +3,3) | 12 % | 62 % | 25 % | correcta, algo lenta en partes |
| Renca 2022 | 05/09 18:00 | 06/09 05:12 | 127 | −3,5 h (−16,2 a −0,4) | **29 %** | 54 % | 17 % | mixta: una parte llega muy temprano (dirección/forma) |
| **Las Lagunas 2024** | 18/09 13:00 | 18/09 17:26 | 2.635 | **+21,2 h** (+1,9 a +59,5) | 4 % | 18 % | **78 %** | **demasiado lenta** |
| Chacras 2023 | 11/11 16:00 | 12/11 17:35 (*) | 2 | −23,9 h | 100 % | 0 % | 0 % | no evaluable (*) |
| Aguada 2023 | 31/08 16:00 | — | 0 | — | — | — | — | no evaluable (sin focos) |

(*) El primer foco real de Chacras es del 11/11 18:45 UTC (31 focos NOAA-20), que sólo estaban en GEE y no en el archivo
provincial; con los 2 focos del día siguiente el modelo parece "adelantado", pero es un artefacto de los datos.

## 4. Lectura
1. **Tan mal no estamos.** En siete de los ocho eventos evaluables el modelo libre llega a la mayoría de los lugares dentro de
   la ventana del satélite (54–100 %). Los incendios chicos no son "demasiado rápidos": se veían así porque se los comparaba
   con la fecha en que el combate los frenó.
2. **El único problema claro de velocidad es Las Lagunas** (megaincendio, 40.000 ha): llega en mediana 21 h tarde y en un
   cuarto de los lugares más de 2,5 días tarde. Ninguna hora de ignición ni `factor_waf` lo corrigió (`docs/v3.1/02`); es la
   pista para el paso 3 (k de arbustal cerrado y bosque) y, si no alcanza, para procesos que el autómata no representa
   (salto de focos / *spotting*, focos secundarios).
3. **Renca** tiene un problema de **dirección**, no de velocidad media: una parte del fuego simulado llega a lugares mucho antes
   que el satélite (29 % rápido) y otra parte tarde.
4. **Salvedad importante:** la hora de ignición de cada evento se eligió con esta misma métrica (`docs/v3.1/02`), así que en los
   incendios chicos el "en ventana" está en parte construido por ese ajuste. Las Lagunas no tiene ese sesgo (ninguna hora lo
   arreglaba), por eso es el mejor indicador de un error real de velocidad.
5. Pendiente de datos: recuperar los focos NOAA-20 de Chacras (y de 2022–2023 en general) para evaluarla; Aguada no tiene
   focos VIIRS.

## 5. Cómo repetirlo
Desde `src/v3.1`:
```
python scripts/velocidad_vs_focos.py --corridas ../../resultados/v3.0/SL-2024-MESILLA-20240902-h2-alt2-librev2 ... --salida tabla.csv
```
La clasificación por evento (en ventana / adelantado / atrasado) también está en `scripts/evaluar_temporal.py` y
`incendios_sl.validation.metricas.metricas_primera_deteccion`, que es lo que usan los barridos (`scripts/barrido_libre.py`).
