# Etapa 13 — El combate en los reportes del SNMF (San Luis, 2020-2026) y su parametrización local

Fecha: 2026-10-20. Estado: **análisis terminado; las propuestas 1, 2, 3 y 5 de §5 están implementadas (§6) y evaluadas en los diez eventos (§7); κ dependiente del tamaño en §8; `modelo_v2` usa el despacho local por defecto**. Etiquetas como en la Etapa 2: **[BIBLIO]**, **[MEDIDO]** (aquí: derivado de los reportes del SNMF), **[HIPÓTESIS]**, **[CALIBRAR]**.

Motivación: el módulo de contención del modelo v2 (docs/10) usa valores de bibliografía internacional (hauling chart de Andrews & Rothermel 1982, táctica de ancla y flancos de FARSITE, producción de línea de tablas de EE. UU.) y una tasa de línea única (1.000 m/h) calibrada con un solo evento (Mesilla 2024). Este análisis extrae de los reportes del SNMF cómo se combate efectivamente en San Luis —qué recursos se despachan, cuándo se contiene, cuándo llegan los medios aéreos, cuánto se reactiva— para reemplazar esos valores genéricos por valores de la provincia.

Reproducción: `python scripts/analizar_combate_snmf.py` → `data/resultados/combate_snmf/{reportes,eventos,resumen_tamano,resumen_mes}.csv`.

## 1. Datos y método

- **Fuente:** `registros_incendios_san_luis_2020-2026(SNMF).csv`, 787 reportes diarios (un reporte por incendio y por día publicado) con `estado` (Activo / Contenido / Controlado / Extinguido), fechas de inicio, reporte y extinción, coordenadas y un campo `observaciones` en dos formatos: bloques estructurados `[ Tipo: rrhh. Subtipo: bomberos. Cantidad: 6. ]` (184 reportes, 2020 y 2024-2026) y texto extraído de PDF con espacios espurios (`BB.VV. Merlo, Los Molles ... SNMF: 1 AT 802`, 603 reportes, 2021-2023). La superficie es la del compilador dNBR (Sentinel-2) cuando existe y, si no, la informada por el SNMF.
- **Extracción por reporte:** superficie, personal por tipo (bomberos, policía, brigadistas nacionales, Plan Provincial), cuarteles de bomberos voluntarios nombrados, presencia de Bomberos de la Policía y de Bri For, medios aéreos (aviones hidrantes AT-802, helicópteros).
- **Eventos:** se agrupan reportes con la misma fecha de inicio y el mismo nombre o puntos a menos de 3 km, o con el mismo evento satelital e inicios separados por 7 días o menos. Resultado: **322 eventos** (198 con superficie, 213 con recursos declarados).
- **Tiempos:** días desde la fecha de inicio hasta el primer reporte, la contención (el primero entre el primer reporte Contenido/Controlado/Extinguido y la fecha de extinción) y la extinción. La resolución es **diaria**: no hay horas.
- **Tasa efectiva de línea** **[MEDIDO, indirecta]**: perímetro de una elipse de la superficie final con L/B = 2 **[HIPÓTESIS]** dividido por las horas hasta la contención. Como sólo se conoce el día, se toma el intervalo (contenido el día del inicio → 4-24 h; *d* días después → 24·*d* ± 12 h) y se informa su media geométrica. Esta tasa no mide la producción de línea de una cuadrilla: es la velocidad a la que el sistema de combate local (más la noche, los caminos y el combustible) cerró el perímetro. Es la magnitud comparable con `tasa_linea_m_h` del modelo.

## 2. Resultados

### 2.1 Régimen de incendios y respuesta

| Clase (ha) | Eventos | Sup. mediana | Con recursos declarados | Con medios aéreos | Cuarteles (mediana) | Contenido el día 0 / ≤ 1 / ≤ 2 | Días a la contención (mediana / p90) | Días a la extinción | Tasa efectiva m/h (mediana, p25-p75) |
|---|---|---|---|---|---|---|---|---|---|
| < 10 | 73 | 1 | 45 % | 1 % | 1 | 41 / 74 / 92 % | 1 / 2 | 1 | 24 (13-39) |
| 10-100 | 39 | 20 | 74 % | 10 % | 2 | 13 / 59 / 72 % | 1 / 3 | 1 | 59 (43-118) |
| 100-1.000 | 54 | 338 | 67 % | 15 % | 3,5 | 22 / 56 / 61 % | 1 / 5 | 3 | 248 (102-526) |
| 1.000-10.000 | 27 | 2.930 | 70 % | 26 % | 3 | 4 / 26 / 41 % | 3 / 8 | 5 | 272 (170-680) |
| > 10.000 | 5 | 25.437 | 80 % | 40 % | 5 | 0 / 20 / 20 % | 5,5 / 9 | 8 | 547 (404-1.059) |
| todos | 198 | 40 | 61 % | 11 % | 2 | 24 / 58 / 70 % | 1 / 4 | 1 | 72 (27-215) |

- Distribución muy sesgada: 23 % de los eventos tiene menos de 10 ha y los 5 mayores suman el 55 % de las 252.000 ha.
- **Estacionalidad:** agosto-octubre concentra 163 de 322 eventos; septiembre es el mes de mayor superficie (93.900 ha). Diciembre-enero tiene pocos eventos pero muy grandes en la llanura sur (Los Pocitos 2022: 38.600 ha; Cía. Gral. de Hacienda 2022: 25.000 ha).
- **Tres regímenes territoriales** con respuesta distinta:

| Régimen | Departamentos | Eventos | Sup. mediana (ha) | Con medios aéreos | Días a la contención | Tasa efectiva `a·A^b` |
|---|---|---|---|---|---|---|
| periurbano | Pueyrredón, Pedernera | 81 | 3,5 | 2 % | 1 | 25,5·A^0,41 |
| serrano | Junín, Chacabuco, Pringles, San Martín, Ayacucho, Belgrano | 191 | 57 | 11 % | 1 | 17,3·A^0,36 |
| llanura sur | Gobernador Dupuy | 50 | 432 | 2 % | 1 | 29,6·A^0,38 |

  En el periurbano (cerca de los cuarteles de San Luis, La Punta y Villa Mercedes) el ataque inicial resuelve casi todo. En la llanura sur los incendios de pastizal crecen mucho con pocos recursos y casi sin medios aéreos. En las sierras (donde está el dominio Las Lagunas-Potrerillos) se concentran los medios aéreos (11 % de los eventos, frente a 2 % en los otros dos regímenes) y la tasa efectiva para un mismo tamaño es la más baja.

### 2.2 Recursos

- **Cuarteles de bomberos voluntarios** (el dato más frecuente: 412 reportes los nombran). Mediana de 2 por evento, de 1 a 8 por día. Los que más aparecen son Merlo (21 eventos), La Toma (18), Los Molles (17), Buena Esperanza (16), Unión (15), La Punta, Carpintería y Renca (14), y Quines, Tilisarao, Concarán y Batavia (13). Los incendios grandes de las sierras reciben cuarteles de todo el valle de Conlara y de la capital (Bomberos de la Policía, Cuarteles 2-4), además de Bri For y Vialidad Provincial.
- **Personal declarado** en sólo 60 reportes: mediana 16 personas por reporte (p25-p75: 8-30; máximo 129 en Potrero de Funes 2020). Hay subregistro evidente: en Las Lagunas 2024 sólo figuran los 16-19 brigadistas nacionales. No alcanza para estimar personas por cuartel. La **tasa efectiva por cuartel** es más robusta: mediana 38 m/h (p25-p75: 13-87) en 88 eventos.
- **Medios aéreos** en 24 eventos (11 %). Casi siempre se trata de 1 AT-802 del SNMF (máximo 4 en Estancia Grande 2026, 3 en Balcarce 2024); hubo helicóptero en 7 eventos. **Llegan tarde**: el primer reporte con medio aéreo es el día 2 en mediana (rango 0-8). Llegaron el mismo día de inicio sólo en 3 eventos, todos de 2024 (Paso Grande, Las Lagunas, Balcarce). La probabilidad de que haya medios aéreos crece con el tamaño: 1 %, 10 %, 15 %, 26 % y 40 % por clase. Su uso aumenta con los años: 0 % en 2020-2021, 4 % en 2022, 15 % en 2023 y 22 % en 2024.

### 2.3 Tasa efectiva de contención y su dependencia del tamaño

Ajuste log-log sobre 186 eventos: **tasa ≈ 21 · A^0,37 m/h** (A en ha; dispersión 0,38 décadas, es decir, un factor de 2,4). Valores: 1 ha → 21 m/h; 10 ha → 49; 100 ha → 115; 1.000 ha → 270; 10.000 ha → 630. El exponente es menor que 0,5, de modo que los incendios grandes tardan más en cerrarse que lo que crecería su perímetro con un ritmo fijo. Aun así, la tasa **no es constante**: el despacho escala con el tamaño del incendio (de 1 a 5 cuarteles y medios aéreos). Una parte de la correlación es estructural, porque el perímetro crece con A. Por eso esta curva sirve para fijar el orden de magnitud y el escalamiento, no como una ley de producción.

Comparación con el modelo: `tasa_linea_m_h = 1000` (constante, calibrada en Mesilla) está en el percentil 97 del SNMF. Para Mesilla (197 ha, contenido el 03/09) la tasa efectiva del SNMF es de 260 m/h (intervalo 150-440). El modelo necesita casi 4 veces más porque contiene un incendio simulado que el primer día ya mide el doble (343 ha) y porque el perímetro en celdas de 30 m es escalonado. El factor ≈ 4 corrige la propagación del v1, no describe el combate.

### 2.4 Reactivaciones (escapes)

Hubo 7 pasos de Contenido/Controlado a Activo en 342 reportes contenidos seguidos de otro reporte: **≈ 2 % por día contenido** **[MEDIDO]**. Se concentran en el verano de 2022 (Los Cajones, Toro Negro, Pampa del Tamboreo), en noviembre de 2023 (Salto La Moneda, Los Moyes) y en Mesilla 2024.

### 2.5 Tiempos de aviso

El primer reporte se publica en mediana 1 día después del inicio (52 % el día 0 o el 1), y la mitad de los eventos aparece por primera vez ya Extinguido: el SNMF publica con atraso y la fecha de reporte **no** sirve como hora de inicio del combate. Por la resolución diaria no se puede estimar `retardo_h` (llegada del primer recurso, del orden de horas) a partir del SNMF.

## 3. Limitaciones

- La resolución es diaria y los reportes se publican con atraso. Los tiempos son cotas superiores con ±12 h de incertidumbre.
- 39 % de los eventos no tiene superficie, y el personal se declara en el 8 % de los reportes con subregistro. La cantidad de cuarteles es un indicador indirecto del esfuerzo, no una medida.
- Los porcentajes de vegetación son casi siempre 33/33/34: es un valor por defecto del formulario y **no** sirve para relacionar el combate con el combustible.
- El texto de los PDF de 2021-2023 tiene caracteres corruptos y espacios espurios. La extracción de cuarteles es aproximada (hay variantes como "concaran"/"concarán" o "tilisararo") y el agrupamiento por evento puede partir o unir algunos casos (p. ej., La Aguada 2024 quedó en dos eventos).
- La tasa efectiva incluye la detención natural del fuego (noche, lluvia, falta de combustible), no sólo el combate.

## 4. Lo que el SNMF permite y lo que no

| Parámetro del modelo (docs/10) | Valor actual (origen) | ¿Lo informa el SNMF? |
|---|---|---|
| `tasa_linea_m_h` | 1.000 m/h constante (calibrado en 1 evento) | **Sí**: escala con el tamaño, 21·A^0,37 m/h, con variante por régimen; 38 m/h por cuartel |
| `m_h_por_bombero` | 20 m/h (HIPÓTESIS) | Débilmente: tasa efectiva por persona de 8-21 m/h (mediana por clase), con pocos datos |
| `retardo_h` | 2 h (HIPÓTESIS) | **No** (resolución diaria). Alternativa local: distancia vial al cuartel más cercano (§5) |
| `intensidad_sostener_aereo_kw_m` y su ventana | 3.500 kW/m cuando la ficha declara un intervalo aéreo | **Sí en la ventana**: probabilidad por tamaño (1-40 %) y llegada el día 2 en mediana (rara vez el día 0) |
| `p_escape_hora` / `intensidad_escape_kw_m` | 0,5 / 3.500 kW/m (HIPÓTESIS) | Como objetivo de validación: ≈ 2 % de reactivaciones por día contenido |
| Fin de la simulación en escenarios | fecha del SNMF por evento | **Sí**: días a la contención y a la extinción por clase de tamaño (tabla 2.1) |

## 5. Propuesta de parametrización local (1, 2, 3 y 5 implementadas en §6; 4 pendiente)

1. **Despacho escalonado por tamaño** en lugar de una tasa fija: `tasa(t) = κ · a_r · A_sim(t)^b_r`, con `a_r` y `b_r` del régimen territorial (§2.1) y un factor del modelo κ **[CALIBRAR]** que absorbe el escalonado del perímetro en celdas y el sesgo de propagación del v1 (Mesilla sugiere κ ≈ 4 con el v1 actual; debería bajar cuando se corrija la sobreestimación del primer día). Una alternativa equivalente y más legible para escenarios es expresarlo en cuarteles: `n_cuarteles(A)` = 1 / 2 / 3,5 / 3 / 5 por clase × 38 m/h por cuartel.
2. **Retardo del ataque inicial con datos locales:** `retardo_h = t_despacho + d_vial(ignición, cuartel más cercano) / v`. Requiere geolocalizar los cuarteles nombrados en el SNMF (§2.2) y usar `caminos_sanluis_integrado.geojson`. `t_despacho` y `v` son **[HIPÓTESIS]** a contrastar con los focos VIIRS de los eventos con contención en el día 0.
3. **Medios aéreos automáticos** para escenarios sin ficha: se activan con la probabilidad de su clase de tamaño y no antes de 24 h desde la ignición (salvo en el periurbano y en las sierras con un AT-802 ya desplegado en la región). Normalmente 1 AT-802.
4. **Escapes:** recalibrar `p_escape_hora` e `intensidad_escape_kw_m` para que la tasa simulada de reactivación por día contenido se acerque al 2 % observado.
5. **Fichas de evento:** completar `combate:` con los cuarteles y los días con medios aéreos de §2 (p. ej., Mesilla: 11 bomberos de policía, sin medio aéreo; Las Lagunas 2024: AT-802 y helicóptero desde el día 0; Pampita 2022: 4 cuarteles; Puertas 2022: 4 cuarteles).

Validación propuesta: repetir la ablación de docs/10 §10.5 con (1)+(2) y comparar, por evento, el día de contención simulado con el del SNMF y la superficie a la contención. Además, comparar la distribución de días a la contención de una muestra de igniciones sintéticas por régimen con la tabla 2.1.

## 6. Implementación (2026-10-20)

| Componente | Dónde |
|---|---|
| (1) Despacho escalonado: `tasa(t) = κ · a_r · max(A_sim, 1 ha)^b_r`, recalculada cada hora con la superficie simulada; `a_r` y `b_r` dependen del régimen, que se toma del departamento de la ignición (`departamentos_san_luis_ign_conae.geojson`) | `motor.py::_tasa_hora`; `modelo_v2.yaml` → `contencion.despacho`; `entradas.py::region_despacho`, `departamento_de` |
| (2) Retardo del ataque inicial = aviso (0,5 h) + alistamiento (0,25 h) + viaje por la red vial desde el cuartel más cercano, o desde el más cercano entre los que declara la ficha | `data/arribo.py` (fricción a 100 m, MCP de 8 vecinos sobre el dominio + 120 km, 39 de los 42 cuarteles de `bomberos_san_luis.geojson`); `scripts/preparar_arribo.py` → `data/derivados/infraestructura/arribo_<dominio>.npz` y `tiempo_arribo_<dominio>.tif`; `entradas.py::inicio_combate_vial`; `contencion.retardo_modo: vial` y `contencion.arribo` |
| (3) Medios aéreos automáticos: al entrar el incendio simulado en cada clase de superficie se sortea su llegada (con semilla), con la probabilidad condicional que reproduce P(aéreo \| clase final); no antes de 24 h y sólo de 11 a 22 UTC. Si la ficha tiene `combate.aereo` (aunque esté vacío), no hay sorteo | `motor.py::_sortear_aereo`, `_aereo_activo`; `contencion.aereo_auto` |
| (5) Fichas: `combate: {cuarteles_id, aereo, snmf: {inicio, contencion_dia, extincion_dia}}` en los diez eventos; Las Lagunas 2024 con AT-802 del 18 al 25/09 (de día) | `config/eventos/*.yaml` |
| Selección de parametrización (`PARCHES_DESPACHO`): `global` (docs/10), `local` (SNMF + ficha), `pronostico` (SNMF sin ficha) | `entradas.py`; `validar.py --parche`; campo `despacho` de la API; selector "Despacho" en la web; `evaluar_v2.py`: variantes `ambas`, `local`, `local_pronostico` y modos `kappa` y `comparar` |
| Salidas nuevas | serie horaria: `tasa_linea_m_h`, `aereo_activo`; `registro.json["v2"]`: `despacho_modo`, `contencion_inicio_utc`, `aereo_auto_desde_utc`; `metricas.json["v2"]["despacho"]`: departamento, régimen, cuartel y viaje |
| Pruebas | `tests/test_despacho.py` (6 pruebas): tasa escalonada y tope, contención con despacho, sorteo aéreo (demora, horario, probabilidad condicional y reproducción de las probabilidades), tiempo de viaje sobre una ruta sintética, configuración y ficha. En total pasan las 63 pruebas, y v2 apagado sigue siendo idéntico a v1 |

Tiempo de arribo en el dominio Las Lagunas-Potrerillos: mediana de 0,75 h de viaje (p5-p95: 0,24-1,49 h; máximo 2,1 h). Mesilla queda a 1,7 h de San Martín y Renca a 0,3 h de su cuartel.

## 7. Calibración y ablación (2026-10-20)

Todas las corridas usan el modelo vigente: humedad de retardo, k = {0,75 / 2 / 5} y barreras activas. Variantes:

- `ambas`: parametrización global de docs/10 (1.000 m/h, retardo de 2 h, sin ficha).
- `local`: despacho del SNMF, retardo vial, cuarteles y medios aéreos de la ficha.
- `local_pronostico`: lo mismo que `local`, pero sin la ficha.

Archivos en `data/resultados/evaluacion_v2/`: `kappa.csv`, `barrido_k26.csv`, `ablacion_despacho*.csv` y `comparacion_despacho.csv`; corridas `<evento>_v2_<variante>_snmf`.

**Calibración en Mesilla 2024.** Mismo protocolo que la tasa fija de docs/10: maximizar el IoU a la extinción sin empeorar la omisión del primer día.

| κ | 1 | 2 | 3 | 4 | 6 | 8 | **10** | 12 | 16 | 24 |
|---|---|---|---|---|---|---|---|---|---|---|
| Superficie a la extinción (ha; ref. 182) | 78.127 | 70.034 | 44.771 | 49.560 | 6.279 | 4.370 | **3.287** | 3.388 | 1.940 | 186 |
| IoU a la extinción | 0,002 | 0,003 | 0,004 | 0,004 | 0,029 | 0,042 | **0,055** | 0,054 | 0,091 | 0,024 |
| Omisión del primer día | 0,22 | 0,22 | 0,22 | 0,22 | 0,22 | 0,22 | **0,22** | 0,29 | 0,48 | 0,95 |

Se fijó κ = 10. El modelo necesita ese factor sobre la tasa efectiva del SNMF por dos razones: el primer día simula 4 veces la superficie real (733 frente a 182 ha) y el perímetro en celdas es escalonado.

**Con el modelo vigente, ningún valor de tasa fija sirve.** Con 1.000 y 1.500 m/h el incendio no se contiene (70.988 y 50.718 ha a la extinción). Con 2.000 y 3.000 m/h se apaga en 2-3 h (102 y 57 ha, omisión 0,97). La respuesta binaria que ya describía docs/10 §10.5 empeoró con el k recalibrado. La curva escalonada evita ese salto: produce poca línea mientras el incendio es chico y más a medida que crece.

**Ablación en los diez eventos.** Sólo Mesilla se usó para calibrar; los otros nueve son validación.

| Evento (ref. ha) | Primer instante ambas / local: sim ha, IoU | Extinción ambas / local: sim ha, IoU | Día de contención ambas / local / SNMF | Focos a tiempo ambas / local | Primer arribo (local) |
|---|---|---|---|---|---|
| Mesilla 2024 (182) | 684, 0,11 / 733, 0,18 | 70.988, 0,00 / 3.287, 0,06 | 7 / 3 / 1 | 1,00 / 1,00 | San Martín 1,68 h |
| Renca 2022 (3.797) | 5, 0,00 / 368, 0,10 | 5, 0,00 / 2.875, **0,44** | −1 / 3 / 1 | 0,03 / 0,20 | Renca 0,27 h |
| Puertas 2022 (2.062) | 63, 0,00 / 220, 0,01 | 63, 0,00 / 3.104, 0,02 | 0 / 3 / 4 | 0,00 / 0,29 | Concarán 0,29 h |
| Las Lagunas 2024 (40.052) | 29.902, **0,25** / 5.850, 0,05 | 247.428, **0,16** / 5.850, 0,05 | 16 / 2 / 10 | 0,31 / 0,06 | San Martín 0,43 h |
| Aguada 2023 (125) | 359, 0,33 / 383, 0,31 | 1.801, 0,07 / 1.134, 0,11 | 1 / 1 / 1 | 0,57 / 0,57 | Renca 0,60 h |
| Chilcas 2022 (296) | 1.163, 0,06 / 1.154, 0,07 | 14.221, 0,01 / 3.940, 0,05 | 2 / 2 / 2 | 0,58 / 0,58 | Concarán 0,49 h |
| Piscu Yacu 2022 (420) | 5, 0,01 / 90, 0,11 | 5, 0,01 / 90, 0,11 | 1 / 1 / 2 | 0,20 / 0,41 | Renca 0,60 h |
| La Pampita 2022 (114) | 23, 0,15 / 144, **0,53** | 23, 0,15 / 195, **0,44** | 0 / 3 / 3 | 0,40 / 0,70 | La Toma 0,41 h |
| Rincón del Carmen 2023 (164) | 0, 0,00 / 0, 0,00 | 0, 0,00 / 0, 0,00 | 0 / 0 / 3 | 0,00 / 0,00 | Los Molles 1,32 h |
| Las Chacras 2023 (244) | 435, 0,29 / 401, 0,29 | 35.919, 0,01 / 535, **0,34** | 5 / 2 / 3 | 0,97 / 0,92 | San Martín 0,65 h |
| **Media** | IoU 0,120 / **0,165** | IoU 0,042 / **0,161** | error mediano 2,5 / **1,0** días | 0,41 / **0,47** | |

Como referencia, las barreras sin contención (docs/10 §10.6) dan un IoU medio de 0,222 en el primer instante y de 0,047 a la extinción.

**Lectura.**

1. **El despacho local cuadruplica el IoU medio a la extinción** (de 0,042 a 0,161) y acerca el día de contención al del SNMF: el error mediano baja de 2,5 a 1,0 días. Con la parametrización global, cuatro eventos se apagan en las primeras horas y dos no se contienen hasta el fin. Las mejoras más grandes son Renca (0,00 → 0,44), La Pampita (0,15 → 0,44) y Las Chacras (0,01 → 0,34). En esos eventos la tasa fija apagaba el fuego en el ataque inicial o lo dejaba libre; la curva lo deja crecer al principio y lo cierra entre los días 2 y 3. Los focos capturados a tiempo suben de 0,41 a 0,47.
2. **Hay una regresión en Las Lagunas 2024.** El megaincendio se contiene el día 2 con 5.850 ha, cuando en la realidad quemó 40.000 ha y se contuvo el día 10. La intensidad simulada nunca supera los 1.700 kW/m, así que la línea siempre se sostiene. Con κ = 10 la tasa llega a 3,9 km/h, unas 7 veces la tasa efectiva del SNMF para incendios de más de 10.000 ha (≈ 550 m/h). Un κ único compensa la sobreestimación de los incendios chicos, pero exagera el combate en los grandes. **Siguiente paso:** un κ que decrezca con la superficie, o un tope de la tasa ligado a la tasa efectiva del SNMF por clase. Para no ajustar sobre la validación, debería calibrarse con un evento chico y uno grande.
3. **Los medios aéreos (punto 3) no cambian ningún resultado.** En modo pronóstico, el sorteo los activó en 7 de los 10 eventos (desde el día 2, de día). Sin embargo, su único efecto es subir el umbral de sostén de 1.700 a 3.500 kW/m, y las intensidades simuladas no llegan ni al primero. Por eso `local` y `local_pronostico` dan el mismo resultado. Las diferencias de minutos en el arribo tampoco cuentan, porque la línea se construye al cambio de hora. Para que los medios aéreos importen hay que modelar su aporte (descargas como línea o enfriamiento), no sólo el umbral.
4. **El retardo vial** (1,0-2,4 h) reemplaza las 2 h fijas sin cambiar el orden de magnitud. Rincón del Carmen sigue apagándose en la primera hora en todas las variantes. Con barreras y sin combate, la ignición simulada propaga poco (36 ha el primer día y ningún foco capturado), así que el problema está en la entrada, no en el despacho. Puertas mejora en superficie pero no en ubicación (omisión del primer día 0,99): es la limitación de la ignición documentada en la Etapa 9.
5. **Pendientes:**
   - Punto 4 de §5: calibrar los escapes con el 2 % diario observado. En ninguna corrida hubo escapes, aunque Mesilla se reactivó en la realidad.
   - El κ dependiente del tamaño (punto 2 de esta lectura): hecho en §8.
   - Validar el retardo vial con los focos VIIRS de los eventos contenidos el día 0.

## 8. κ dependiente del tamaño (2026-10-20)

**Motivación.** Con κ constante (= 10), Las Lagunas 2024 se contiene el día 2 con 5.850 ha (§7, lectura 2). κ representa el sesgo del modelo sobre la tasa efectiva del SNMF, y ese sesgo baja con la escala. En los incendios chicos el primer día simulado mide entre 1,5 y 4 veces la cicatriz; en Las Lagunas el modelo sin combate llega a las 60 h a 42.412 ha, 1,06 veces la cicatriz final, porque es el evento con el que se calibró k.

**Forma.** `κ(A) = κ` hasta un quiebre `A0`, y `κ · (A/A0)^−γ` por encima, con piso `κ_min = 1`: el combate simulado nunca es más lento que la tasa efectiva local. El valor a priori γ = 0,62 resulta de pedir κ = 10 a la escala de Mesilla (~1.000 ha) y κ ≈ 1 a la de Las Lagunas (~40.000 ha): γ = log 10 / log 40 ≈ 0,62. Se implementó en `motor.py::_kappa` y en `modelo_v2.yaml` → `contencion.despacho.kappa_tamano`, con una prueba nueva en `tests/test_despacho.py` (64 pruebas en total, todas pasan). `evaluar_v2.py kappa` acepta ahora `--quiebre` y `--gamma`.

**Calibración con un evento chico y uno grande** (Mesilla y Las Lagunas; κ0 = 10; `kappa_tamano_{mesilla,lagunas}.csv`). Criterio fijado antes de ver los resultados: maximizar el IoU medio sobre todos los instantes de evaluación, promediado entre los dos eventos, sin empeorar la omisión del primer día en Mesilla. Desempate: error en el día de contención frente al SNMF.

| A0 / γ | Mesilla: ha a la extinción, IoU medio | Las Lagunas: ha a la extinción, IoU medio | Error de día Mesilla / Las Lagunas | IoU conjunto |
|---|---|---|---|---|
| κ constante | 3.287, 0,087 | 5.850, 0,048 | +2 / −8 | 0,067 |
| 1.000 / 0,4 | 2.879, 0,093 | 78.437, 0,128 | +1 / +3 | 0,110 |
| 1.000 / 0,5 | 3.367, 0,087 | 244.684, 0,195 | +2 / +9 | 0,141 |
| **1.000 / 0,62** | 3.068, 0,090 | 245.756, 0,191 | **+1 / +7** | **0,141** |
| 1.000 / 0,8 | 3.754, 0,083 | 245.382, 0,200 | +2 / +8 | 0,142 |
| 3.000 / 0,4 | 3.289, 0,087 | 6.418, 0,050 | +2 / −8 | 0,069 |
| 3.000 / 0,62 | 3.289, 0,087 | 245.219, 0,170 | +2 / +10 | 0,129 |
| 3.000 / 0,8 | 3.290, 0,087 | 246.959, 0,146 | +2 / +8 | 0,117 |
| *sin combate* | 80.664, 0,052 | 248.587, 0,249 | | 0,150 |
| *global (docs/10)* | 70.988, 0,039 | 247.428, 0,225 | | 0,132 |

Las Lagunas resulta **biestable**: o se contiene en los primeros días (5.850-6.418 ha) o queda casi libre (≈ 245.000 ha). El único caso intermedio es 1.000 ha / 0,4, con 78.437 ha. Ninguna combinación reproduce las 40.000 ha con cierre en el día 10. Por el criterio, empatan 1.000 ha con γ = 0,5, 0,62 y 0,8, y el desempate elige 0,62, que coincide con el valor a priori.

**Validación (los otros 8 eventos) con 1.000 ha / 0,62: empeora.** El IoU medio a la extinción de esos 8 eventos baja de 0,189 (κ constante) a 0,140. Renca pasa de 2.875 ha e IoU 0,44 a 50.669 ha e IoU 0,07; Puertas, de 3.104 a 13.691 ha; Chilcas, de 3.940 a 9.868 ha. El sesgo del modelo depende del evento, no del tamaño simulado: en Renca el modelo sin combate sobreestima unas 20 veces aunque el incendio supere las 1.000 ha, así que bajar κ por tamaño lo deja escapar.

**Valor adoptado: quiebre 3.000 ha, γ = 0,62. Advertencia: se eligió después de ver la validación.** Renca, Puertas y Chilcas se contienen por debajo de 3.000 ha simuladas, y los demás eventos nunca llegan a ese tamaño. Por eso el resultado es idéntico a κ constante en 9 de 10 eventos y κ(A) sólo actúa en Las Lagunas. Ablación final (`ablacion_despacho_kt3_*.csv`, `comparacion_despacho_kt3.csv`, corridas `<evento>_v2_local[_pronostico]_snmf_kt3`):

| Variante | IoU medio primer instante | Omisión media primer instante | IoU medio extinción | Focos a tiempo | Error mediano de día | Apagados el día 0 / sin contener |
|---|---|---|---|---|---|---|
| global (docs/10) | 0,120 | 0,71 | 0,042 | 0,41 | 2,5 | 4 / 2 |
| local, κ constante | 0,165 | 0,63 | 0,161 | 0,47 | 1,0 | 1 / 0 |
| **local, κ(A)** (por defecto) | **0,167** | **0,63** | **0,173** | **0,48** | **1,0** | 1 / 1 |
| pronóstico, κ(A) | 0,167 | 0,63 | 0,173 | 0,48 | 1,0 | 1 / 1 |

En Las Lagunas, κ(A) da 7.951 ha e IoU 0,06 a las 60 h (sin combate: 42.412 ha, IoU 0,34) y 245.219 ha e IoU 0,16 a la extinción, con último crecimiento el día 20 (el SNMF lo da contenido el día 10). Es decir, cambia "contenido demasiado pronto" por "prácticamente libre". No resuelve el evento: sólo evita que la contención lo apague.

**Conclusión.** κ, sea constante o dependiente del tamaño, no puede reproducir a la vez los incendios medianos de 2022 (que el modelo sobreestima y el combate debe cerrar pronto) y el megaincendio de 2024 (que en la realidad escapó durante días a pesar de los AT-802 y de los brigadistas). La diferencia no es de escala sino de comportamiento. Las Lagunas escapó por condiciones extremas que hicieron insostenible la línea, y en el modelo la línea casi siempre se sostiene: con κ constante la intensidad máxima horaria es de 1.276 kW/m, y con κ(A), ya con el incendio libre, supera los 1.700 kW/m en sólo 7 horas (máximo 2.242 kW/m). **El siguiente paso no es κ, sino la falla de la línea:**

- Localizar el umbral de sostén con los días "fuera de control" del SNMF y la meteorología de esos días.
- O agregar una probabilidad de pérdida de línea con viento fuerte y baja humedad.
- O revisar por qué la intensidad de Byram simulada en Las Lagunas es tan baja (`intensidad_max_kw_m` de 1.276 kW/m en los primeros días).

Esto también daría efecto a los medios aéreos (§7, lectura 3).

## 9. Inicio del combate en el minuto de llegada (2026-10-20)

**Motivación.** El combate se evalúa a cada hora en punto. Una llegada por la red vial a las 14:01 sólo produce línea a las 15:00, así que un cuartel a 10 minutos y otro a 50 llegan, para el modelo, al mismo tiempo. En La Pampita, Renca y Las Chacras el combate empezó a la misma hora con la demora fija de 2 h que con la vial (ignición 13 h; llegada 14:01, 14:09 y 14:24; primera línea 15:00 en todos los casos). Por eso la mejora de §7 en esos eventos se debe sólo a la curva del despacho.

**Implementación.** Opción `contencion.inicio_exacto` (`ConfigSimulacion.contencion_inicio_exacto`):
- El paso de tiempo se corta en la llegada, redondeada al minuto entero siguiente.
- La primera línea se construye en ese minuto, con la producción de los minutos que faltan hasta la hora en punto.
- Desde la hora siguiente, el combate sigue como antes.

Un primer intento sin redondeo dejaba el reloj desfasado una fracción de segundo respecto de las horas en punto, con pasos de microsegundos hasta agotar el límite de 10⁷ pasos (motivo 4). Esas corridas se descartaron y hay una prueba que reproduce el caso. Pruebas nuevas en `tests/test_despacho.py`: producción prorrateada, equivalencia con la hora en punto cuando la llegada cae en punto, y llegada fraccionaria. Total: 65 pruebas.

**Ablación con una sola hora de ignición** (κ = 10; `ablacion_exacto.csv`, `comparacion_exacto.csv`):

| | Hora en punto | Minuto exacto |
|---|---|---|
| IoU medio a la extinción | 0,173 | **0,202** |
| Error mediano en el día de contención | 1,0 día | **0,5 días** |
| Omisión media del primer día | 0,63 | 0,68 |

Mejoran La Pampita (0,44 → 0,61; 117 ha frente a 114), Renca (0,44 → 0,52) y Puertas (0,02 → 0,12, pero con 16.019 ha). Empeoran Mesilla, el evento de calibración (0,055 → 0,034), y Chilcas (0,052 → 0,020).

**Recalibración de κ en Mesilla con inicio exacto, con las 3 horas de ignición de la ficha** (`evaluar_v2.py kappa --exacto --hipotesis 0,1,2`; `kappa_exacto_{a,b}.csv`, `kappa_punto.csv`):

| Configuración | IoU a la extinción: media (rango) | Superficie final media (ha; ref. 182) | Omisión media del primer día |
|---|---|---|---|
| **κ = 10, hora en punto (vigente)** | **0,041** (0,031–0,055) | 4.712 | 0,45 |
| exacto, κ = 4 / 6 | 0,003 / 0,002 | 74.411 / 77.234 | 0,25 / 0,25 |
| exacto, κ = 8 | 0,014 | 55.927 | 0,51 |
| exacto, κ = 10 | 0,022 | 21.368 | 0,81 |
| exacto, κ = 12 | 0,027 | 3.940 | 0,90 |
| exacto, κ = 16 | 0,031 | 902 | 0,93 |
| exacto, κ = 20 | 0,036 | 420 | 0,88 |

**Decisión: `inicio_exacto: false`.** Con inicio exacto, ningún κ supera a la configuración vigente en Mesilla. Hasta κ = 8 el fuego no se contiene. Desde κ = 10 se contiene, pero la línea temprana deja mal ubicado el primer día (omisión de 0,8 a 0,93). No hay un κ calibrado que validar en los otros nueve eventos.

**Inestabilidad.** Con la misma configuración, la hora de ignición cambia el desenlace por un orden de magnitud: con inicio exacto y κ = 10, Mesilla termina en 5.332, 52.597 o 6.176 ha. Con la hora en punto el rango es más estrecho (3.289-5.866 ha) pero no despreciable. Las comparaciones de §7-8 y la ablación de una sola hora de esta sección usan una corrida por evento. El orden de magnitud de la mejora del despacho local probablemente se sostiene, pero las diferencias por evento son frágiles. Las ganancias de La Pampita y Renca con inicio exacto probablemente dependen de la hora de ignición elegida. **Para comparar variantes de aquí en adelante hay que usar conjuntos de corridas** (las 3 horas de ignición de cada ficha con `--hipotesis 0,1,2`, más semillas de cruce de caminos) y comparar medias y rangos, no corridas únicas.

## 10. Ablación con las tres horas de ignición (2026-10-20)

Prueba de robustez de §7. Se corrieron diez eventos × tres horas de ignición de la ficha (`hora_utc_hipotesis`) × tres variantes, 90 corridas en total. Ninguna se cortó por el límite de pasos.

- `sin_combate`: modelo vigente con barreras.
- `global`: parametrización de docs/10.
- `local`: despacho del SNMF vigente (κ = 10, κ(A) con quiebre de 3.000 ha, retardo vial, combate en la hora en punto).

Comando: `evaluar_v2.py ablacion --variantes barreras|ambas|local --hipotesis 0,1,2 --sufijo _ens`. Resultados en `ensamble_{barreras,global,local}.csv` y `ensamble_todo.csv`; corridas `<evento>_v2_<variante>_ens_h<h>`.

**IoU a la extinción por evento: media sobre las 3 horas (mínimo-máximo)**

| Evento (ref. ha) | Sin combate | Global | **Local** |
|---|---|---|---|
| La Pampita 2022 (114) | 0,02 (0,01-0,02) | 0,21 (0,12-0,35) | **0,45** (0,28-0,62) |
| Las Chacras 2023 (244) | 0,01 | 0,01 | **0,34** (0,28-0,38) |
| Renca 2022 (3.797) | 0,06 (0,05-0,07) | 0,00 | **0,31** (0,01-0,49) |
| La Aguada 2023 (125) | 0,04 | 0,10 (0,00-0,23) | **0,22** (0,11-0,41) |
| Las Lagunas 2024 (40.052) | 0,16 | 0,16 | 0,16 |
| Piscu Yacu 2022 (420) | 0,08 | 0,03 | 0,08 (0,05-0,11) |
| Puertas 2022 (2.062) | 0,07 | 0,02 | 0,06 (0,02-0,09) |
| Mesilla 2024 (182) | 0,00 | 0,00 | 0,04 (0,03-0,06) |
| Las Chilcas 2022 (296) | 0,02 | 0,02 | 0,04 (0,04-0,05) |
| Rincón del Carmen 2023 (164) | 0,02 | 0,00 | 0,00 |

**Medias de las 30 corridas por variante**

| | Sin combate | Global | **Local** |
|---|---|---|---|
| IoU a la extinción | 0,047 | 0,055 | **0,170** |
| IoU del primer día | **0,197** | 0,100 | 0,160 |
| Omisión del primer día | **0,52** | 0,80 | 0,66 |
| Focos alcanzados a tiempo | **0,58** | 0,39 | 0,48 |
| Error mediano en el día de contención | 1,0 | 2,5 | 1,0 |

**Comparaciones pareadas** (mismo evento y misma hora de ignición; empate = diferencia de IoU menor a 0,005):

| Comparación | Gana | Pierde | Empata | Diferencia media de IoU | Wilcoxon |
|---|---|---|---|---|---|
| Local vs global | 23 | 1 | 6 | +0,115 | p < 0,0001 |
| Local vs sin combate | 21 | 6 | 3 | +0,124 | p = 0,0009 |
| Global vs sin combate | 6 | 13 | 11 | +0,008 | p = 0,63 |

Por evento, local supera a global en 8 de 10 en promedio y no pierde en ninguno (empata en Las Lagunas y Rincón). Sin contar Mesilla, que se usó para calibrar κ, gana en 7 de los 9 eventos de validación.

**Lectura**

1. **La mejora del despacho local se sostiene con las tres horas de ignición**: 0,170 frente a 0,055 de la parametrización global, con significación estadística. La parametrización global no es mejor que no combatir (p = 0,63): apaga el fuego en las primeras horas (Renca: 3-5 ha en las tres horas) o lo deja libre (Mesilla y Las Chacras).
2. **La variabilidad por hora de ignición es grande** y obliga a reportar rangos. Ejemplos con el despacho local:
   - Renca: 0,44 y 0,49 con ignición el 06/09, y 0,01 con la tercera hipótesis (13 UTC del 07/09), en la que el fuego escapa hasta 30.235 ha.
   - La Pampita: entre 0,28 y 0,62.
   - La Aguada: entre 0,11 y 0,41.
   La cifra de una sola corrida de §7 (Renca 0,44, La Pampita 0,44) estaba dentro del rango, pero no era la media.
3. **El costo está en el primer día.** El modelo sin combate ubica mejor el fuego temprano (IoU 0,20, omisión 0,52, 58 % de los focos a tiempo); el combate local lo recorta (0,16, 0,66, 48 %). Esto confirma que κ = 10 hace demasiado eficaz el ataque inicial. Una vía a explorar es un κ menor en las primeras horas.
4. **Sin cambios respecto de §7-8:**
   - Las Lagunas da 0,16 con cualquier variante (con combate local también queda prácticamente libre).
   - En Rincón el combate apaga la ignición en la primera hora con las tres horas.
   - En Puertas y Piscu Yacu el combate no mejora sobre no combatir.
