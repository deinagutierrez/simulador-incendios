# Etapa 31: cinco incendios no vistos para validar las versiones del simulador (lote X-49)

Fecha: 2026-11-04 · Cierra el pendiente X-49 del informe de síntesis ("Elegir 5 incendios no usados para validar: 5 de 12 candidatos, 391 a 1.308 ha; falta aprobar"). Alcance: fichas y insumos para v3.4 y v4.0; **ninguna corrida de evaluación todavía**.

## 1. De dónde salen los cinco

El conjunto local del banco V4 (docs/v4.0/16 §3.4) tiene 12 eventos: los 8 de la Fase 1 más 2024, SM01 (La Aguada 2023), Renca y Puertas. De esos 12, siete ya son parte de los diez eventos con los que se calibró v3.x y se corrieron todos los lotes de v4 (Las Lagunas, Renca, Puertas, La Aguada, Rincón, Chacras nov 2023 y Chilcas). Los **cinco restantes** son los únicos componentes MapBiomas del dominio que cumplen los cuatro criterios de elegibilidad del protocolo (≥ 100 ha, polígono ≥ 95 % dentro, ≥ 3 km del borde, focos VIIRS atribuibles con instante T80) y que nunca entraron en una calibración:

| Ficha (`escenarios/*/eventos/`) | Componente del banco | ha de referencia | Fecha (primer pase VIIRS S-NPP) | Pases / focos | Parte SNMF | Eje evaluable |
|---|---|---:|---|---|---|---|
| `SL-2023-CHACRASOCT` | MB_2023_26601_2023-10 | 1.308 | 17/10/2023 17:22 UTC | 7 / 46 | LAS CHACRAS 19 a 23/10 (a 1,05 km; combate: Merlo, Carpintería, La Toma, Tilisarao, PL Cuartel 6, brigada, 1 AT-802) | forma y tiempo |
| `SL-2023-LAGUNALARGA` | MB_2023_26597_2023-09-10 | 431 | 29/09/2023 18:00 UTC | 3 / 35 | ninguno | forma y tiempo |
| `SL-2022-LATOTORA` | MB_2022_43644_2022-11 | 391 | 16/11/2022 18:44 UTC | 4 / 33 | PARAJE LOS MOLLES ESCUELA LA TOTORA 16 a 19/11 (a 4,7 km, misma fecha; no emparejado por la regla de 2 km) | forma y tiempo |
| `SL-2022-LAJULI` | MB_2022_43580_2022-09-10 | 506 | 01/10/2022 18:07 UTC | 1 / 23 | ninguno | sólo forma (instante degenerado, §5 del protocolo) |
| `SL-2022-ALGARROBAL` | MB_2022_43638_2022-10 | 464 | 18/10/2022 05:25 UTC (nocturno) | 1 / 23 | ninguno | sólo forma (instante degenerado) |

Los nombres de los tres sin parte son provisorios, por el topónimo más cercano de `viviendas_sanluis_integrado.geojson`; el `oid` de MapBiomas es el identificador firme. Todos están en Libertador General San Martín (celdas F06-C10, F09-C11, F09-C08, F08-C09 y F08-C08 de la grilla de 10 km).

`SL-2023-CHACRASOCT` es el polígono 2023_26601 que docs/v4.0/06 había descartado por "73 ha vs 1.336 ha". Las 72,7 ha son el dNBR del compilador del archivo SNMF (columna `superficie_ha_sat`), no una cifra del SNMF; MapBiomas, los 46 focos en 7 pases repartidos sobre todo el polígono y el banco V4 lo tratan como un evento de 1.308 ha. Se lo incorpora con esa superficie y la discrepancia queda anotada en la ficha.

Lo que **no** sirve y por qué: Paso Grande 2024 (16 % dentro del dominio), San Martín 2023 (59 % dentro, en el borde N), 2025 (ninguna cicatriz ≥ 100 ha dentro del cuadrado; Las Huertas 2025 queda afuera) y 2026 (el único parte SNMF, Estancia Grande, Coronel Pringles, julio, está fuera del dominio). No hay todavía candidatos para la prueba prospectiva (Fase 3).

## 2. Qué tan "no vistos" son

- Ningún `k` de v3.1 a v3.4 ni ninguna decisión de los lotes de v4 (E033 a E059: regla 3.3b, WAF, `k_global`, pavesas, viento) se ajustó con ellos. Para esas versiones son **no vistos**.
- M1 (V4 original) y M2 (V2) los corrieron **una sola vez, congelados**, en la Fase 1 del banco (E023, X-11). Con viento uniforme, 43644 apareció en la Fase 2 pausada (docs/v4.0/17 §4, IoU 0,17). Eso no es calibración, pero debe decirse al informar.
- Regla del protocolo (§3.4): la prueba se abre **una sola vez por versión congelada**. Antes de correr un lote conviene fijar la configuración de cada motor (commit + sha256) y prerregistrar el criterio, como en E041, E045, E047, E051 y E059. La lista de eventos ya está fijada con sha256 en `datos/inputSimulacion/catalogo/eventos_no_vistos_X49.csv` (sha256 de cada ficha y de cada cicatriz de referencia).

## 3. Fichas

Misma forma que las diez de v3.0 (docs/v4.0/06), copiadas idénticas en `escenarios/v3.4/eventos/` y `escenarios/v4.0/eventos/`. Diferencias que hay que conocer:

1. **Ignición (`ignicion`, slot `snmf`)**: en los cinco es el **primer pase VIIRS S-NPP**, con todas sus detecciones como puntos (regla §4.1 del banco, docs/v4.0/16): la misma ignición que usó la Fase 1 (`sim_v4/conjunto_prueba/_banco/<componente>/ignicion.geojson`). No hay punto SNMF utilizable: LAJULI, ALGARROBAL y LAGUNALARGA no tienen parte; en LATOTORA el parte está a 4,7 km (la escuela) y en CHACRASOCT corresponde a la reactivación del 19/10, dos días después de los primeros focos.
2. **Alternativas** (`alt0`, `alt1`, `alt2`), todas rotuladas HIPÓTESIS: la detección de mayor FRP del primer pase como punto único; el extremo de la cicatriz a barlovento del viento IFS del día de ignición (en LAGUNALARGA también el extremo N, a barlovento del viento N que dominó la propagación del 30/09 al 02/10); y, donde existe, el punto SNMF.
3. **Hipótesis horarias**: cuatro por evento, todas anteriores a la `cota_superior_utc` (primer pase). Como en Rincón (E036), la hora es desconocida y se deja a los barridos elegirla.
4. **`referencia_espacial.mes` admite una lista** (`[9, 10]`) para los dos componentes que el raster mensual reparte entre dos meses (LAJULI y LAGUNALARGA). Cambio mínimo en `src/v3.4/src/incendios_sl/data/preparar_dominio.py` (`np.isin` en lugar de `==`); un entero sigue funcionando igual.
5. **Fin de simulación**: fin del día local siguiente al último pase con focos (o la extinción SNMF, si existe), acotado por la serie IFS que ya tenía el banco. En CHACRASOCT termina el 22/10 (fin de la serie), un día antes de la extinción SNMF.
6. **Combate**: sólo CHACRASOCT tiene cuarteles y medio aéreo documentados; LATOTORA tiene parte sin cuarteles identificables; los otros tres llevan `snmf: null`. Por lo tanto, en cuatro de cinco sólo se puede evaluar propagación libre.

## 4. Insumos sin red: `preparar_evento_desde_banco.py`

`preparar_evento.py` necesita GEE (índices) y Open-Meteo (meteorología). Como el banco V4 ya tenía esos dos insumos para los cinco componentes, el script nuevo `src/v3.4/scripts/preparar_evento_desde_banco.py` (`--todos` o `--evento <id> --banco <componente>`) deja los mismos productos, en el mismo lugar y con la misma procedencia, sin descargar nada:

| Producto | Origen | Verificación hecha |
|---|---|---|
| `eventos/<id>/cicatriz_referencia_<id>.tif` | polígono MapBiomas rasterizado y restringido al mes o meses | 506,2 / 463,9 / 391,3 / 430,7 / 1.308,2 ha = `ha_componente` de `eventos_fase1.csv` |
| `meteo/<id>_ecmwf_ifs_<ini>_<fin>_<hash>_dominio.csv` + `.json` | copia de `banco_v4/entradas/meteo_ifs/<componente>_*_dominio.csv` (IFS 9 km vía Open-Meteo, promedio de 16 puntos) | cubre `meteorologia.inicio_utc`–`fin_utc` de la ficha; v4 la convierte al formato de SIM sin huecos |
| `combustibles/<id>/ndvi_30m`, `ndmi_30m`, clase, curado, calidad | `indices_mes.tif` del banco (compuesto mensual previo a la ignición, método E020) convertido a float y clasificado con `generar_mapa_combustibles` | 100 % de celdas con índices válidos |
| `eventos/<id>/humedad_muerto_<id>.csv` | `serie_humedad` (FFMC y retardo) sobre la serie del dominio | rangos plausibles; ALGARROBAL llega a saturación tras los 15,6 mm del 19/10 |
| `catalogo/hotspots/viirs_<id>.csv` y `hotspots_v3.2/viirs_<id>.csv` | FIRMS S-NPP provincial del banco a ≤ 750 m de la cicatriz, en la ventana de la ficha (igual que `extraer_focos.py`; sin NOAA-20 local para estos eventos) | 23 / 23 / 33 / 35 / 46 focos = los atribuidos por el banco |

Lo que no genera: biblioteca de viento, barreras, tabla de combustibles (productos por dominio que ya existen). En v4.0 la primera corrida arma sola `datos/procesados/v4.0/<id>/` (combustible 3.3 y 3.3b con el verano de `indices_extra` 2022 o `dinamicos/indices` 2023, perímetro, focos).

Comprobado el 2026-11-04: `cargar_entradas_evento` de v3.4 (modelo_v2) e `insumos_evento` de v4.0 cargan los cinco eventos con todas sus igniciones (sólo `alt1` de CHACRASOCT se desplaza 30 m a una celda combustible); las corridas `libre_*` de las dos versiones traducen; dos pruebas de humo de 3 h (LATOTORA en v4.0: 328 ha; CHACRASOCT en v3.4: 68 ha) terminaron y se borraron.

## 5. Cómo correrlos

```bash
cd src/v4.0
python scripts/correr_escenario.py --escenario libre_chacrasoct_2023     # también libre_lajuli_2022, libre_algarrobal_2022, libre_latotora_2022, libre_lagunalarga_2023
cd ../v3.4
python scripts/correr_escenario.py --escenario libre_chacrasoct_2023     # mismos nombres, variante libre_v2
```

Para un lote con barrido de hora y punto, `src/v3.4/scripts/barrido_libre.py` y los lotes de v4 funcionan con estas fichas igual que con las diez (misma estructura; `hotspots_v3.2` ya tiene sus focos).

## 6. Advertencias para interpretar los resultados

- La ignición del primer pase VIIRS ya marca quemadas las celdas de las detecciones: en LAJULI y ALGARROBAL (23 detecciones sobre toda la cicatriz) eso es casi la cicatriz entera. Para esos dos, la comparación útil es con `alt0` (un punto) y sólo en forma.
- Los cinco son de temporada (septiembre a noviembre) y del rango 391 a 1.308 ha: cubren el hueco entre Piscu Yacu (420 ha) y Puertas (2.062 ha) de los diez, pero no agregan verano ni eventos > 2.000 ha.
- Sin NOAA-20 en los archivos locales (`viirs_noaa20_san_luis_eventos.csv` sólo cubre los diez eventos): `descargar_firms_noaa20.py` puede sumarlo después; los focos V1 y F5 quedarán más gruesos que en los diez hasta entonces.
- CHACRASOCT tiene lluvia de 7,8 mm el 18/10 entre dos días de focos: es la segunda prueba directa (con Chacras nov 2023) de la recuperación de la humedad del combustible muerto tras lluvia.

## 7. Primera corrida: Las Chacras octubre 2023 en v3.1 (libre, librev2) y v4.0 (libre)

Fecha: 2026-11-04. Sólo `SL-2023-CHACRASOCT`; los otros cuatro siguen sin correr. Hora y punto de ignición elegidos **con los focos, como en v3.1** (docs/v3.1/02): barrido de hora cada 2 h en las 14 h previas al primer pase VIIRS (17:22 UTC) más las hipótesis de la ficha, variante libre_v2 de v3.1, puntaje = (IoU a igual superficie + fracción de primeras detecciones a tiempo) / 2; después búsqueda de punto (40 candidatos sobre la cicatriz) a la hora elegida, cambio de punto sólo si el puntaje mejora ≥ 0,05. Corridas y tablas en `resultados/v3.1/paso2_hora_x49/` (`barrido_hora_chacrasoct.csv`, `barrido_punto_chacrasoct_06Z.csv`, `_13Z.csv`, `comparacion_chacrasoct_v31_v40.csv`). La ficha de v3.1 es la misma de v3.4 y v4.0 (copiada a `escenarios/v3.1/eventos`, focos a `catalogo/hotspots_v3.1`).

**Hora (33 corridas, tres igniciones de la ficha):**

| Ignición | Mejor hora (UTC) | Puntaje | IoU igual sup. | A tiempo | Error mediano (h) |
|---|---|---|---|---|---|
| `snmf` = 4 focos del primer pase | **17/10 06:00** (03 h local) | **0,430** | 0,49 | 0,37 | −11,1 |
| ídem | 17/10 13:00 (hipótesis 1) | 0,422 | 0,41 | 0,43 | 0,0 |
| `alt0` = foco de mayor FRP (punto único) | 17/10 08:00 | 0,379 | 0,39 | 0,37 | 0,0 |
| `alt1` = extremo E (barlovento) | cualquiera | ≤ 0,12 | ≤ 0,18 | ≤ 0,07 | −20 a −23 |

Ventana admisible: después del pase nocturno S-NPP sin focos (~05 UTC) y antes del primer pase (17:22 UTC); 06 UTC está en el borde inferior. Regla de v3.1: el mejor puntaje dentro de la ventana → **hipótesis 4 = 06 UTC**. La hipótesis 1 (13 UTC) empata a 0,008 y tiene error mediano nulo: se corre como sensibilidad.

**Punto (41 corridas por hora):** a las 06 UTC el mejor candidato (−65,7564, −32,6557) da 0,464 (+0,034 frente a los 4 focos); a las 13 UTC, (−65,7644, −32,6490) da 0,454 (+0,032). Ninguno llega al umbral de 0,05: **se mantienen los 4 focos del primer pase** (que ya están sobre esos candidatos). El punto de 06 UTC quedó en la ficha como `alt3` (no adoptado). Bloque `recomendada: {ignicion: snmf, hipotesis: 4}` en las tres fichas.

**Corridas finales** (misma máscara válida de v3 y los mismos 46 focos; v4.0 con `parar_en_cicatriz`, así que termina al igualar la superficie observada):

| Versión | Variante | Hora | IoU igual sup. | h hasta la sup. | A tiempo | Adelantado | Atrasado | Error mediano (h) | Puntaje | ha al final | IoU al final |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3.1 | libre (modelo_v1) | 06 UTC | 0,478 | 19,0 | 0,37 | 0,63 | 0,00 | −9,0 | 0,422 | 2.447 | 0,475 |
| v3.1 | libre | 13 UTC | 0,453 | 22,7 | 0,33 | 0,23 | 0,10 | 0,0 | 0,393 | 1.422 | 0,458 |
| v3.1 | librev2 (modelo_v2) | 06 UTC | **0,493** | 14,8 | 0,37 | 0,63 | 0,00 | −11,1 | **0,430** | 4.094 | 0,315 |
| v3.1 | librev2 | 13 UTC | 0,410 | 16,0 | **0,43** | 0,27 | 0,00 | 0,0 | 0,422 | 2.377 | 0,393 |
| v4.0 | libre (modelo_v3, 3.3b) | 06 UTC | 0,374 | 24,5 | 0,40 | **0,10** | 0,03 | 0,0 | 0,387 | 1.310 (parada) | 0,368 |
| v4.0 | libre | 13 UTC | 0,351 | 54,1 | 0,27 | 0,03 | 0,20 | 0,0 | 0,309 | 1.312 (parada) | 0,350 |

Carpetas: `resultados/v3.1/SL-2023-CHACRASOCT-20231017-h{4,1}-snmf-{libre,librev2}` (con `visor.html`) y `resultados/v4.0/SL-2023-CHACRASOCT/SL-2023-CHACRASOCT-20231017-h{4,1}-snmf-libre`.

**Lectura (dato e inferencia, un evento):**
1. (dato) v3.1 gana en forma (IoU 0,45 a 0,49 frente a 0,35 a 0,37) y v4.0 gana en tiempo: con la ignición de 06 UTC, v3.1 llega **antes** que el satélite al 63 % de las primeras detecciones (error mediano −9 a −11 h) mientras v4.0 queda a tiempo en el 40 %, adelantado sólo en el 10 % y atrasado en el 3 %. Es el patrón inverso al de los diez eventos (informe de síntesis §3.6: allí v3.1 también ganaba en tiempo, 0,82 contra 0,33). Con un evento no se generaliza.
2. (dato) La hora elegida por el puntaje (06 UTC) favorece la forma de v3.1 a costa de adelantarla; con 13 UTC v3.1 librev2 queda a tiempo (error 0) y pierde 0,08 de IoU. El puntaje es insensible entre las dos (0,430 contra 0,422). (inferencia) La ignición real está entre las dos horas y el modelo v3 corre demasiado rápido el primer día en este evento, como en Chilcas y Aguada de los diez.
3. (dato) Extensión: v3.1 no se detiene en la cicatriz; a la extinción simula 1,9× (libre) y 3,1× (librev2) la superficie observada, y termina "sin propagación físicamente posible" la madrugada del 19/10, después de la lluvia de 7,8 mm del 18/10; nunca reproduce la reactivación del 19/10 porque ya había quemado esas celdas. v4.0 alcanza la superficie observada a las 24,5 h (06 UTC) o 54 h (13 UTC) y se para.
4. (dato) Los 4 focos del primer pase son mejor ignición que el foco de mayor FRP solo (0,43 contra 0,38) y que el extremo a barlovento (≤ 0,12): el fuego del 17/10 no empezó en el extremo E de la cicatriz.

### 7.1 Segunda vuelta: punto único de ignición elegido con v3.1 librev2 (2026-11-04)

Hipótesis del usuario: las 4 detecciones del primer pase son el fuego ya desarrollado porque empezó antes; el origen fue un solo punto. Procedimiento: con v3.1 libre_v2 se evaluaron, a las 06 y 13 UTC, los 40 candidatos de grilla sobre la cicatriz y los 4 focos del primer pase **por separado** (90 corridas, `barrido_punto_unico_chacrasoct.csv`); con los dos mejores puntos se repitió el barrido de hora (22 corridas, `barrido_hora_punto_unico_chacrasoct.csv`).

- Mejor punto: candidato de grilla (−65,7564; −32,6557), a 400 m al E del foco n02, puntaje **0,464** (IoU 0,53; 40 % a tiempo) frente a 0,430 de los 4 focos juntos y 0,452 del mejor foco solo (n04). Queda como `alt3` y `recomendada: {ignicion: alt3, hipotesis: 4}` en las tres fichas.
- Hora: meseta entre 04 UTC (0,465) y 06 UTC (0,464); 08 UTC 0,417; 13 UTC 0,255. Se mantiene **06 UTC** (después del pase nocturno sin focos, ~05 UTC). (inferencia) La meseta apoya la hipótesis de un inicio nocturno, al menos 11 h antes del primer pase; antes de las 04 UTC no se probó porque contradice el pase sin focos.

| Versión | Variante | Ignición | IoU igual sup. | h hasta la sup. | A tiempo | Adelantado | Atrasado | Error mediano (h) | Puntaje | ha al final | IoU al final |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3.1 | librev2 | **punto único, 06 UTC** | **0,529** | 17,2 | **0,40** | 0,57 | 0,03 | −17,6 | **0,464** | 3.398 | 0,378 |
| v3.1 | libre | punto único, 06 UTC | 0,525 | 23,3 | 0,23 | 0,57 | 0,20 | −10,3 | 0,379 | 2.027 | 0,478 |
| v4.0 | libre | punto único, 06 UTC | 0,263 | 31,6 | 0,10 | 0,37 | 0,17 | −14,6 | 0,181 | 1.313 (parada) | 0,260 |
| v3.1 | librev2 | 4 focos, 06 UTC | 0,493 | 14,8 | 0,37 | 0,63 | 0,00 | −11,1 | 0,430 | 4.094 | 0,315 |
| v3.1 | libre | 4 focos, 06 UTC | 0,478 | 19,0 | 0,37 | 0,63 | 0,00 | −9,0 | 0,422 | 2.447 | 0,475 |
| v4.0 | libre | 4 focos, 06 UTC | 0,374 | 24,5 | 0,40 | 0,10 | 0,03 | 0,0 | 0,387 | 1.310 (parada) | 0,368 |
| v3.1 | librev2 | 4 focos, 13 UTC | 0,410 | 16,0 | 0,43 | 0,27 | 0,00 | 0,0 | 0,422 | 2.377 | 0,393 |
| v3.1 | libre | 4 focos, 13 UTC | 0,453 | 22,7 | 0,33 | 0,23 | 0,10 | 0,0 | 0,393 | 1.422 | 0,458 |
| v4.0 | libre | 4 focos, 13 UTC | 0,351 | 54,1 | 0,27 | 0,03 | 0,20 | 0,0 | 0,309 | 1.312 (parada) | 0,350 |

Carpetas nuevas: `resultados/v3.1/SL-2023-CHACRASOCT-20231017-h4-alt3-{libre,librev2}` y `resultados/v4.0/SL-2023-CHACRASOCT/SL-2023-CHACRASOCT-20231017-h4-alt3-libre`, todas con `visor.html` (formato v3.1).

**Lectura (dato e inferencia, un evento):**
1. (dato) El punto único mejora a v3.1 librev2 (0,430 → 0,464, IoU 0,49 → 0,53) y empeora a v3.1 libre (0,422 → 0,379) y, mucho, a v4.0 (0,387 → 0,181: IoU 0,26, 32 h hasta la superficie, 10 % a tiempo). Con punto único **gana v3.1 librev2** con claridad; con los 4 focos el resultado era parejo.
2. (inferencia) El punto se eligió maximizando el puntaje de v3.1 librev2, así que esa versión parte con ventaja: es una validación cruzada de la ignición, no una comparación neutra. v4.0 tiene menos velocidad inicial y desde un solo punto no alcanza a cubrir la cicatriz en el primer día; con los 4 focos como "fuego ya desarrollado" sí (como en los lotes de v4, que usan igniciones recomendadas de v3). Para comparar motores con un punto único habría que repetir la búsqueda del punto con v4.0, o fijar el punto con un criterio externo a los dos motores.
3. (dato) v3.1 librev2 sigue adelantada (57 % de las primeras detecciones, error mediano −17,6 h) y sobreestima la extensión final (3.398 ha, 2,6×): el punto único corrige la forma, no la velocidad.

### 7.2 Tercera vuelta: punto único elegido con v4.0 y comparación cruzada (2026-11-04)

Para que la comparación no dependa de qué motor eligió el punto, se repitió la búsqueda con **v4.0 modelo_v3 libre, sin parada en cicatriz** (90 corridas con los mismos 44 candidatos a las 06 y 13 UTC, más 22 de barrido de hora; evaluadas con las métricas de v3.1). Las carpetas de esas 112 corridas (376 MB) se borraron; quedan `resultados/v4.0/busqueda_punto_x49/barrido_punto_unico_chacrasoct_v40.csv` (métricas) y `corridas_punto.csv`, `corridas_hora.csv` (qué se corrió). Mejor punto para v4.0: el **foco n04** del primer pase (−65,7679; −32,6506), a 1,3 km del punto de v3.1; mejor hora, otra vez **06 UTC** (0,374; 04 UTC 0,343; 13 UTC 0,188). Queda como `alt4`.

Después se corrió cada motor con los dos puntos, con los 4 focos y con las dos horas. **Las corridas de v4.0 de esta tabla son sin parada en cicatriz** (`parar_en_cicatriz: off`, 141 h), como las de v3.1; las carpetas `h4-snmf` y `h4-alt3` de v4.0 se sobrescribieron con esa configuración (los valores de §7 y §7.1 para v4.0 eran con parada, que dejaba sin alcanzar los focos del 19 y 20/10). `h1-snmf` de v4.0 sigue con parada.

| Versión | Variante | Ignición | Hora | IoU igual sup. | h hasta la sup. | A tiempo | Adelantado | Atrasado | Error mediano (h) | Puntaje | ha al final |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3.1 | librev2 | alt4 = punto de v4.0 | 06 | 0,536 | 18,0 | 0,37 | 0,63 | 0,00 | −10,2 | 0,452 | 3.065 |
| v3.1 | libre | alt4 = punto de v4.0 | 06 | **0,578** | 27,7 | 0,30 | 0,50 | 0,10 | −3,3 | 0,439 | 1.526 |
| v4.0 | libre | alt4 = punto de v4.0 | 06 | 0,548 | 61,7 | 0,20 | 0,27 | 0,53 | +2,2 | 0,374 | 29.319 |
| v3.1 | librev2 | alt3 = punto de v3.1 | 06 | 0,529 | 17,2 | 0,40 | 0,57 | 0,03 | −17,6 | **0,464** | 3.398 |
| v3.1 | libre | alt3 = punto de v3.1 | 06 | 0,525 | 23,3 | 0,23 | 0,57 | 0,20 | −10,3 | 0,379 | 2.027 |
| v4.0 | libre | alt3 = punto de v3.1 | 06 | 0,262 | 31,8 | 0,23 | 0,43 | 0,33 | 0,0 | 0,248 | 33.286 |
| v3.1 | librev2 | 4 focos | 06 | 0,493 | 14,8 | 0,37 | 0,63 | 0,00 | −11,1 | 0,430 | 4.094 |
| v3.1 | libre | 4 focos | 06 | 0,478 | 19,0 | 0,37 | 0,63 | 0,00 | −9,0 | 0,422 | 2.447 |
| v4.0 | libre | 4 focos | 06 | 0,374 | 24,8 | **0,43** | 0,27 | 0,30 | 0,0 | 0,404 | 32.391 |
| v3.1 | librev2 | 4 focos | 13 | 0,410 | 16,0 | 0,43 | 0,27 | 0,00 | 0,0 | 0,422 | 2.377 |
| v3.1 | libre | 4 focos | 13 | 0,453 | 22,7 | 0,33 | 0,23 | 0,10 | 0,0 | 0,393 | 1.422 |
| v4.0 | libre (con parada) | 4 focos | 13 | 0,351 | 54,1 | 0,27 | 0,03 | 0,20 | 0,0 | 0,309 | 1.312 |

Visores (`visor.html`, formato v3.1) en todas las carpetas: `resultados/v3.1/SL-2023-CHACRASOCT-20231017-h4-{alt3,alt4,snmf}-{libre,librev2}`, `-h1-snmf-*` y `resultados/v4.0/SL-2023-CHACRASOCT/SL-2023-CHACRASOCT-20231017-h4-{alt3,alt4,snmf}-libre`, `-h1-snmf-libre`.

**Lectura (dato e inferencia, un evento):**
1. (dato) **Gana v3.1 en las dos direcciones**: con el punto que eligió v4.0, v3.1 librev2 da 0,452 y v3.1 libre 0,439 frente a 0,374 de v4.0; con el punto de v3.1, 0,464 frente a 0,248. La ventaja no venía de quién eligió el punto.
2. (dato) Los dos motores coinciden en la hora (06 UTC, 03 h local) y eligen puntos a 1,3 km: v4.0 prefiere el foco n04 (el de mayor FRP del primer pase); v3.1, un punto 1 km al E. Con el punto de v4.0, v3.1 libre logra la mejor forma de todas (IoU 0,58).
3. (dato) v4.0 llega a una forma comparable (IoU 0,55 con su punto) pero **tarde**: necesita 62 h para igualar la superficie y queda atrasada en el 53 % de las primeras detecciones. v3.1 es lo contrario: adelantada en el 50-63 %. La ignición de los 4 focos compensa la lentitud de v4.0 (a tiempo 0,43, el mejor valor de tiempo de la tabla) y por eso v4.0 con 4 focos (0,404) supera a v4.0 con punto único.
4. (dato) Sin parada, v4.0 no se detiene nunca: a las 141 h quema 29.000 a 33.000 ha (22 a 25 veces la cicatriz) porque modelo_v3 no apaga el fuego tras los 7,8 mm del 18/10, mientras que v3.1 termina "sin propagación físicamente posible" la madrugada del 19/10 con 1.500 a 4.100 ha. (inferencia) Es la misma limitación de extinción por lluvia vista en Chacras nov 2023, ahora del lado de v4.0; la regla de parada en cicatriz de los lotes de v4 la ocultaba.

## 8. Archivos

- Fichas: `escenarios/v4.0/eventos/` y `escenarios/v3.4/eventos/` (`SL-2022-LAJULI`, `SL-2022-ALGARROBAL`, `SL-2022-LATOTORA`, `SL-2023-LAGUNALARGA`, `SL-2023-CHACRASOCT`).
- Corridas: `escenarios/v4.0/corridas/libre_*.yaml` y `escenarios/v3.4/corridas/libre_*.yaml` (cinco por versión).
- Lista fija con sha256: `datos/inputSimulacion/catalogo/eventos_no_vistos_X49.csv`.
- Insumos: `datos/inputSimulacion/{eventos,meteo,combustibles}/<id>` y `catalogo/hotspots*/viirs_<id>.csv`; `resumen_focos.csv` de `hotspots_v3.2` ampliado.
- Código: `src/v3.4/scripts/preparar_evento_desde_banco.py` (nuevo) y `src/v3.4/src/incendios_sl/data/preparar_dominio.py` (`mes` como lista).
- Visores: las seis corridas de §7 tienen `visor.html` con el visor de v3.1 (tiempo de llegada, relieve, combustibles, cicatriz, infraestructura, focos, línea de tiempo y tabla de ajuste). Para las de v4.0 lo genera `src/v4.0/scripts/exportar_visor_v31.py --run-id <run_id>` (traduce `hora_llegada_min.tif`, `serie_indicadores.csv`, `registro.json` y `metricas.json` a lo que lee `src/v3.1/scripts/exportar_visor.py`); el visor nativo de SIM queda como `visor_sim.html`.
- v3.1 (§7): `escenarios/v3.1/eventos/SL-2023-CHACRASOCT.yaml` (copia), `catalogo/hotspots_v3.1/viirs_SL-2023-CHACRASOCT.csv`, `resultados/v3.1/paso2_hora_x49/` y las seis corridas finales de §7. La lista con sha256 se volvió a fijar después de agregar la hipótesis 4 y `recomendada` a la ficha de Las Chacras (sha256 de la lista 4199efd9…).
