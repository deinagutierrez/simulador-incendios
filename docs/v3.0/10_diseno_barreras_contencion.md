# Etapa 10 — Diseño: barreras lineales y contención por combate (modelo v2)

Fecha: 2026-10-15. Estado: **implementado** (§10 registra las decisiones tomadas durante la implementación y los resultados; el diseño original de §1–§9 se conserva tal como se aprobó). Etiquetas como en la Etapa 2: **[BIBLIO]** valor o forma tomada de la bibliografía, **[MEDIDO]** dato observado, **[HIPÓTESIS]** supuesto propio, **[CALIBRAR]** parámetro a ajustar con eventos.

## 1. Problema que resuelve

El modelo v1 propaga libremente hasta la fecha de extinción del SNMF. En los cuatro eventos la omisión es ≈ 0 pero la comisión domina: Renca y Puertas sobreestiman 7–10 veces; Mesilla del Cura (contenido a las 24 h) 350 veces a la extinción; en Las Lagunas 2024 los bordes rectos de la cicatriz al E y al S coinciden con líneas de contención o parcelas (Etapa 6 §2.1). Dos mecanismos ausentes explican esto: (a) **barreras lineales** que el fuego no cruza o cruza con probabilidad decreciente (rutas, caminos, cortafuegos, ríos secos, límites de parcela); (b) **combate**, que construye línea de contención y la sostiene mientras la intensidad del frente lo permite.

Principio de diseño: v1 debe seguir siendo reproducible bit a bit. Los dos módulos se activan por configuración (`barreras.activo`, `contencion.activo`, ambos `false` por defecto hasta calibrar) y toda aleatoriedad usa una semilla declarada.

## 2. Datos disponibles

| Dato | Estado | Uso en v2 |
|---|---|---|
| Caminos (`data/derivados/infraestructura/caminos_<dominio>.gpkg`, 825 tramos, 2.625 km; 1.353 km sin duplicados) con `clase` (autopista, ruta, camino, calle, senda, huella, servicio), `superficie` (pavimentado, consolidado, tierra, desconocido en 535 tramos) y `dup_probable` | **[MEDIDO]** OSM + SIG SL + IGN | barreras lineales con ancho por clase |
| Red eléctrica MT (5.543 tramos) | **[MEDIDO]** | no es barrera; queda para exposición (Etapa futura) |
| Viviendas (79 polígonos) | **[MEDIDO]** | no es barrera en v2 (superficie < 1 celda) |
| Agua, urbano, suelo desnudo | clase 0 de combustible | ya bloquean (sin cambios) |
| Cortafuegos, límites de parcela, alambrados | **no disponibles** | entrada opcional por GeoJSON en la ficha de dominio (`barreras_extra`); documentar ausencia |
| Reportes SNMF: estado diario (Activo/Contenido/Controlado/Extinguido), recursos en `observaciones` (bomberos con cantidad en 15 de 100 reportes, aviones AT-802 en 11, sin maquinaria) | **[MEDIDO]**, parcial y no estructurado | estado: **solo validación** (no entra al modelo, para no ser circular); recursos: parámetro opcional por evento cuando existan |
| Intensidad de reacción `I_R` y σ por clase (Rothermel ya implementado) | calculado | intensidad del frente (Byram) |

## 3. Barreras lineales

### 3.1 Representación
Las rutas miden 5–20 m y la celda 30 m: rasterizarlas como celdas no combustibles crearía franjas de 30–42 m y partiría el dominio en exceso. Se representan **sobre los enlaces** del estencil: para cada celda y cada uno de sus 16 vecinos se precalcula si el segmento entre centros cruza una barrera y con qué ancho. Producto nuevo por dominio: `barreras_enlaces_<dominio>.npy`, uint8 (nfil, ncol, 16) = 44 MB para 2.500 km², con el código de la barrera más ancha cruzada (0 = ninguna). Tabla de códigos → ancho efectivo (m) y tipo.

Anchos efectivos por defecto **[HIPÓTESIS, verificar con imágenes]**: autopista 25 m (calzadas + banquinas), ruta pavimentada 14 m, ruta consolidada/tierra 10 m, camino 6 m, calle 8 m, servicio 4 m, huella 3 m, senda 1,5 m, vado y ferrocarril 6 m. `superficie = desconocido` toma el ancho de su clase. Tramos con `dup_probable = True` se descartan para no duplicar barreras. `barreras_extra` (GeoJSON con atributo `ancho_m`) se suma con el mismo mecanismo.

### 3.2 Regla de cruce
Intensidad lineal de Byram **[BIBLIO: Byram 1959; Andrews 2018]**: `I_B = I_R · t_r · R(θ)` con `t_r = 384/σ` min (Anderson 1969) y `R(θ)` la ROS direccional hacia el vecino (ya calculada en el autómata). En kW/m con I_R en kW/m², t_r en s, R en m/s. Longitud de llama `L = 0,0775 · I_B^0,46` m **[BIBLIO: Byram 1959]**.

Probabilidad de cruce por intento **[HIPÓTESIS de forma, CALIBRAR]**: `P = 1 / (1 + exp(−β · (L/W − λ)))`, con W el ancho de la barrera, λ el cociente L/W al que P = 0,5 (inicial 1,0) y β la pendiente (inicial 4). Base bibliográfica a verificar: Wilson (1988) encontró que la probabilidad de que un fuego de pastizal cruce un cortafuego depende del cociente longitud de llama / ancho y de la presencia de árboles cercanos **[BIBLIO, forma exacta a confirmar en la implementación]**. Esta P engloba implícitamente el *spotting* de corta distancia, que v1 no modela.

Dinámica: cuando el avance acumulado sobre un enlace con barrera llega a f = 1, se sortea el cruce. Si falla, el enlace queda **bloqueado durante esa hora** y se vuelve a sortear en cada cambio horario de ROS mientras la celda siga activa (un fuego detenido en una ruta puede cruzarla cuando el viento aumenta). Un enlace bloqueado no cuenta como pendiente para mantener la celda activa (si todos sus enlaces están quemados o bloqueados, la celda pasa a quemada; se reactiva solo por un vecino nuevo). Aleatoriedad: generador por enlace y hora a partir de `semilla`, `fila`, `col`, `k`, `hora` (hash determinista) → reproducible bit a bit, independiente del orden de procesamiento.

Opción determinista para análisis: `modo: umbral` cruza si y solo si L/W > λ.

## 4. Contención por combate

### 4.1 Capacidad de sostener línea
Umbrales de intensidad de la "hauling chart" **[BIBLIO: Andrews & Rothermel 1982; Alexander & Cruz 2019]**:

| I_B (kW/m) | L (m) | Capacidad |
|---|---|---|
| < 350 | < 1,2 | ataque directo con herramientas manuales |
| 350–1.700 | 1,2–2,4 | autobombas, maquinaria; ataque directo difícil a mano |
| 1.700–3.500 | 2,4–3,4 | solo medios aéreos y ataque indirecto |
| > 3.500 | > 3,4 | incontrolable en el frente |

### 4.2 Modelo
Se modela la **construcción de línea** sobre el perímetro activo, a la manera de FARSITE/Prometheus **[BIBLIO: Finney 1998]**, simplificado a celdas:

- Inicio `t_c`: por defecto, el instante de ignición + `retardo_h` **[CALIBRAR, inicial 2 h]**; si la ficha del evento declara `combate.inicio_utc` (p. ej. primer reporte SNMF con hora), se usa ese.
- Tasa de producción de línea `P_L` (m/h) **[CALIBRAR]**: valor único por evento (inicial 300 m/h, orden de magnitud de una dotación de 10–20 bomberos con herramientas manuales en pastizal-arbustal **[BIBLIO: tablas de producción de línea, p. ej. Broyles 2011; a verificar]**). Si la ficha declara recursos (`bomberos: 11`), `P_L = n · p_persona` con `p_persona` **[CALIBRAR, inicial 20 m/h]`.
- Cada hora, con un presupuesto `P_L · 1 h` de metros, se "aseguran" celdas del perímetro activo en orden creciente de intensidad direccional máxima hacia vecinos no quemados (primero cola y flancos, nunca la cabeza), solo si `I_B < I_sostener` **[BIBLIO: 1.700 kW/m para medios terrestres]**. Asegurar una celda cuesta 30 m de línea (42 m en diagonal). Celda asegurada: todos sus enlaces bloqueados, estado `CONTENIDA` (nuevo valor 4 en `estado`), hora registrada en un raster `t_contencion_s`.
- **Escape**: en cada cambio horario, una celda contenida cuyo vecino no quemado tendría `I_B > I_escape` **[CALIBRAR, inicial 3.500 kW/m]** se reactiva con probabilidad `P_escape` **[HIPÓTESIS, inicial 0,5 por hora]**. Esto reproduce reactivaciones como la de Mesilla el 04/09 (contenido el 03/09, activo con viento S de 9,6 m/s).
- Medios aéreos: si la ficha declara `aereo: true` para un intervalo, `I_sostener` sube a 3.500 kW/m en ese intervalo **[HIPÓTESIS]**. Sin modelo de descargas.
- El modelo no usa el estado "Contenido" del SNMF como entrada; ese dato queda para validar el instante en que la simulación deja de crecer.

### 4.3 Interacción con barreras
Una línea de contención se trata como barrera de ancho 3 m **[HIPÓTESIS]** con la misma regla de cruce (§3.2) en lugar de `P_escape`, si se prefiere un único mecanismo; se decide en la implementación comparando ambas variantes en Mesilla.

## 5. Configuración

`config/modelo_v2.yaml` (copia de v1 + bloques nuevos):
```yaml
barreras:
  activo: false
  ancho_m: {autopista: 25, ruta_pavimentado: 14, ruta: 10, camino: 6, calle: 8, servicio: 4, huella: 3, senda: 1.5, vado: 6, ferrocarril: 6, contencion: 3}
  cruce: {modo: probabilistico, lambda: 1.0, beta: 4.0}
  semilla: 20261015
contencion:
  activo: false
  retardo_h: 2
  tasa_linea_m_h: 300
  m_h_por_bombero: 20
  intensidad_sostener_kw_m: 1700
  intensidad_sostener_aereo_kw_m: 3500
  intensidad_escape_kw_m: 3500
  p_escape_hora: 0.5
```
Ficha de evento (opcional): `combate: {inicio_utc: "...", bomberos: 11, aereo: [["2024-09-03T13:00Z", "2024-09-04T22:00Z"]]}`. Ficha de dominio (opcional): `barreras_extra: ruta.geojson`.

## 6. Salidas nuevas
- Rasters: `t_contencion_s.tif`, `estado_final.tif` con valor 4 = contenida; `cruces_barrera.tif` (conteo de cruces exitosos por celda) y `bloqueos_barrera.tif`.
- Serie horaria: metros de línea construidos, metros de perímetro activo, intensidad máxima del frente (kW/m), celdas contenidas, escapes.
- Métricas: las actuales más `ha_sim / ha_ref` a la extinción y hora en que la simulación deja de crecer (comparable con "Contenido" del SNMF).
- Web: capa de caminos con ancho, perímetro contenido en otro color, y los dos interruptores (barreras, contención) en el panel de simulación.

## 7. Validación y calibración
1. **Pruebas sintéticas** (`tests/`): fuego en pastizal uniforme contra una barrera recta de ancho W con viento fijo → la fracción de corridas que cruza converge a P(L/W); contención con `P_L` conocida sobre un fuego circular → el perímetro se cierra en el tiempo esperado; reproducibilidad bit a bit con semilla fija; v2 con ambos módulos apagados ≡ v1.
2. **Ablación por evento**: cuatro corridas (sin nada, solo barreras, solo contención, ambas) en los cuatro eventos; se informa IoU, omisión y comisión a cada instante de evaluación y la captura de focos.
3. **Calibración** de `lambda`, `beta`, `retardo_h`, `tasa_linea_m_h` por barrido en **Mesilla 2024 y Renca 2022** (eventos contenidos en 1–3 días); objetivo: IoU a la extinción sin degradar la omisión del primer día ni la captura de focos.
4. **Validación** en Puertas 2022 y Las Lagunas 2024 con los parámetros fijados; en 2024 se mira en particular si los bordes rectos E y S aparecen.
5. Criterio de éxito mínimo: comisión a la extinción < 0,7 en Renca y Mesilla (hoy 0,99–1,00) con omisión < 0,15.

## 8. Plan de trabajo
| Paso | Contenido | Esfuerzo estimado |
|---|---|---|
| 1 | Producto `barreras_enlaces` (preparar_dominio) + tabla de anchos + pruebas | medio día |
| 2 | Intensidad de Byram y longitud de llama en `rothermel.py`/`automata.py` (ya hay I_R y σ) | 2 h |
| 3 | Cruce probabilístico en `paso` con hash determinista; bloqueo por hora | medio día |
| 4 | Módulo de contención (selección por intensidad, presupuesto de línea, escape) | 1 día |
| 5 | Config v2, fichas, salidas, figuras, web | medio día |
| 6 | Ablación, calibración y validación en los 4 eventos; documento de etapa | 1 día |

## 9. Hipótesis e incertidumbres registradas
- Anchos de vía por clase sin verificación de campo; 535 tramos con superficie desconocida; OSM incompleto en caminos vecinales; sin parcelas ni alambrados (en Las Lagunas 2024 los bordes rectos pueden ser parcelas, no caminos).
- La intensidad del frente hereda las incertidumbres de los combustibles por analogía y del factor k (I_B escala con R y por lo tanto con k).
- Recursos del SNMF esporádicos y en texto libre; la tasa de línea será en la práctica un parámetro calibrado por evento, no una medición.
- La regla de cruce agrupa cruce directo y spotting corto; no se modela spotting de larga distancia ni fuego de copas.
- Una contención calibrada con dos eventos puede no transferirse a incendios con otro nivel de respuesta.

## 10. Implementación (2026-10-15)

### 10.1 Dónde está cada cosa
| Pieza | Archivo |
|---|---|
| Producto de barreras sobre enlaces (`barreras_enlaces_<dominio>.npz`: códigos uint8 (nfil, ncol, 16), ancho por código, procedencia) | `data/preparar_dominio.py::preparar_barreras_enlaces`; paso `barreras` de `scripts/preparar_evento.py` (14 s; 155.481 celdas y 750.692 enlaces con barrera en el dominio; 7 anchos: 1,5–14 m; sin autopistas en el dominio) |
| Intensidad de Byram, longitud de llama, probabilidad de cruce, hash determinista `u01` | `simulation/automata.py` (`longitud_llama`, `p_cruce`, `u01`); tablas `IR_tab` (kW/m²) y `tr_tab` (s) por clase/humedad/curado en `motor.py::_tablas_hora` |
| Cruce en el autómata (bits de bloqueo por hora, contadores de cruces y bloqueos) | `automata.py::paso` |
| Contención: intensidad máxima por celda activa, línea de ancla y flancos, escapes | `automata.py` (`intensidad_maxima_activas`, `vecino_exterior`, `contener_slots`, `escapes`), `motor.py` (`_contener_hora`, `_elegir_linea`, `_exterior`) |
| Configuración | `config/modelo_v2.yaml` (v1 + bloques `intensidad`, `barreras`, `contencion`); `entradas.py::config_v2`; ficha de evento opcional `combate: {inicio_utc, bomberos, tasa_linea_m_h, aereo}` |
| CLI / API / web | `validar.py --modelo modelo_v2 --barreras on|off --contencion on|off --v2 clave=valor,...`; `POST /api/simulaciones` campos `modelo`, `barreras`, `contencion`, `v2`; casillas "Barreras lineales" y "Contención por combate" en la interfaz; perímetro contenido en azul oscuro |
| Salidas nuevas | `t_contencion_s.tif`, `cruces_barrera.tif`, `bloqueos_barrera.tif`; `estado_final` valor 4 = contenida; serie horaria con `celdas_contenidas`, `metros_linea_hora`, `escapes_hora`, `bloqueos_barrera_hora`, `intensidad_max_kw_m`; `registro.json["v2"]`; `metricas.json["v2"]` con `ultimo_crecimiento_utc` y `ha_final_sobre_ref` |
| Pruebas | `tests/test_barreras.py` (8): uniformidad y determinismo del hash, Byram/logística, v2 apagado ≡ v1 bit a bit, umbral bloquea/deja pasar, fracción de cruces ≈ P, contención reduce área y marca celdas, umbral de sostén nulo = libre, reproducibilidad v2 |
| Ablación y calibración | `scripts/evaluar_v2.py ablacion|barrido` → `data/resultados/evaluacion_v2/{ablacion,barrido}.csv` |

### 10.2 Decisiones que modifican o precisan el diseño
1. **Anclaje en caminos (§4.2):** la intensidad que decide si una celda es sostenible se pondera, enlace por enlace, por la probabilidad de cruce de su barrera: `I_ef = I_B · P(L/W)`. Un frente detenido en una ruta ancha es sostenible aunque su intensidad bruta supere el umbral (ataque indirecto apoyado en caminos).
2. **Línea continua de ancla y flancos (§4.2, "orden creciente de intensidad"):** la selección por intensidad sin contigüidad producía celdas contenidas dispersas que el fuego rodeaba (a las 17 h sólo 1/3 de las contenidas seguía en el perímetro). Ahora la línea crece por celdas contiguas (8 vecinos) a la línea ya construida, eligiendo en cada paso la contigua de menor intensidad (`prioridad: flancos`, defecto) o la de mayor intensidad sostenible (`cabeza`); sin contiguas se abre un nuevo anclaje en la celda de menor intensidad (la cola). Es la táctica de FARSITE (Finney 1998).
3. **Sólo perímetro exterior:** las candidatas deben tener, entre sus 8 vecinos inmediatos, combustible conectado con el exterior del incendio (componentes 8-conexas de celdas combustibles que tocan el borde de la ventana que envuelve al fuego, `scipy.ndimage.label` cada hora). Las celdas de segunda fila (que sólo alcanzan el exterior por saltos de caballo) y las que lindan con islas interiores no gastan línea. Sin este filtro la línea tenía 2–4 celdas de espesor.
4. **Impermeabilidad de la línea con 16 vecinos:** un enlace queda cortado si atraviesa una línea de contención: en los saltos de caballo si alguna celda intermedia está contenida; en las diagonales si alguna de las dos celdas ortogonales lo está (sin esto la línea de una celda se filtraba por las esquinas y por los saltos de 2 celdas). Los enlaces cortados no mantienen activa a la celda.
5. **Trabajo nocturno:** las celdas del borde con I = 0 (frente detenido de noche) son candidatas; la línea se cierra de noche, como en los incendios reales. La producción no gastada de día (frente demasiado intenso) se acumula como línea indirecta hasta `acumular_max_h` horas (8; efecto pequeño en las pruebas).
6. **Terminación:** con contención activa el reloj sigue hasta el fin documentado aunque no queden celdas activas (posibles escapes); motivo de fin 7 = "incendio contenido". La regla de 12 h sin propagación no se aplica mientras haya celdas contenidas.
7. **Escapes:** `escapes` sortea por celda y hora (`u01` con k = 99) si la intensidad efectiva hacia algún vecino supera `intensidad_escape_kw_m`; en Mesilla no se produjo ninguno con 3.500 kW/m (intensidades máximas del frente 150–1.900 kW/m).

### 10.3 Primeras corridas en SL-2024-MESILLA (ignición alt1, barreras + contención, umbral 1.700 kW/m)
| Tasa de línea | Fin del 02/09: sim / omisión / IoU | Extinción: sim / IoU / comisión | Último crecimiento |
|---|---|---|---|
| v1 (libre) | 516 ha / 0,45 / 0,17 | 63.116 ha / 0,003 / 1,00 | 10/09 |
| 600 m/h | 464 ha / 0,45 / 0,18 | 48.987 ha / 0,004 / 1,00 | 10/09 (escapa) |
| **1.000 m/h** | 405 ha / 0,46 / 0,20 | **577 ha / 0,20 / 0,78** | 04/09 10 UTC |
| 1.500 m/h | 150 ha / 0,87 / 0,08 | 151 ha / 0,08 / 0,84 | 03/09 17 UTC |

La respuesta es casi binaria (la línea cierra o no cierra), con una zona útil estrecha de tasa de línea que depende de la escala del incendio simulado. Sólo barreras: el fuego cruza los caminos tras varias horas (4.000 cruces frente a 80.000 bloqueos) y el resultado final no cambia; su efecto es retrasar y dar puntos de anclaje a la contención.

### 10.4 Ablación y barrido (2026-10-15; `scripts/evaluar_v2.py`, `data/resultados/evaluacion_v2/`)
**Ablación con los parámetros iniciales del YAML (tasa 300 m/h, umbral 1.700 kW/m, λ = 1; `ablacion.csv`):** 14 de 16 corridas (las dos de contención de Las Lagunas 2024 se repitieron con la tasa calibrada, §10.5).

| Evento | Variante | Primer instante: sim / omisión / IoU | Extinción: sim / IoU / comisión | Focos a tiempo |
|---|---|---|---|---|
| Mesilla 2024 (182 ha) | libre / barreras / contención / ambas | 516 / 0,45 / 0,17 · 515 / 0,45 / 0,17 · 476 / 0,45 / 0,18 · 512 / 0,45 / 0,17 | 63.116 · 61.230 · 60.953 · 57.504 ha, IoU 0,00 | 0,99 en todas |
| Renca 2022 (3.797 ha) | libre / barreras / contención / ambas | 26.001 / 0,05 / 0,14 · 24.433 / 0,05 / 0,15 · 25.671 / 0,05 / 0,14 · 23.531 / 0,05 / 0,15 | 66.096 · 62.878 · 65.382 · 61.866 ha, IoU 0,06 | 0,31 / 0,30 / 0,31 / 0,29 |
| Puertas 2022 (2.062 ha) | libre / barreras / contención / ambas | 22.283 / 0,03 / 0,09 · 20.893 / 0,04 / 0,09 · 22.121 / 0,03 / 0,09 · 18.385 / 0,10 / 0,10 | 33.294 · 31.664 · 33.207 · 30.843 ha, IoU 0,06–0,07 | 0,70 / 0,68 / 0,70 / 0,62 |
| Las Lagunas 2024 (40.052 ha) | libre / barreras | 46.665 / 0,39 / 0,39 · 44.914 / 0,41 / 0,39 | 248.587 ha en ambas, IoU 0,16 | 0,56 / 0,55 |

Lectura: con 300 m/h la contención no cierra en ningún evento (sólo recorta 3–10 % de superficie); las barreras solas reducen 3–8 % la superficie final y retrasan el frente sin cambiar el desenlace. Ningún módulo degrada la captura de focos.

**Barrido en Mesilla 2024** (ambos módulos; 16 combinaciones: tasa 800/1.000/1.200/1.500 m/h × umbral 350/1.700 kW/m × λ 1/2; el barrido de Renca no llegó a correr):

| Tasa (m/h) | λ | Fin del 02/09: sim / omisión | Extinción: sim / IoU / comisión | Último crecimiento |
|---|---|---|---|---|
| 800 | 1 | 456 ha / 0,45 | 44.528 ha / 0,00 / 1,00 (escapa) | 10/09 |
| 800 | 2 | 368 ha / 0,52 | **681 ha / 0,20 / 0,79** | 04/09 23 UTC |
| 1.000 | 1 | 405 ha / 0,46 | **577 ha / 0,20 / 0,78** | 04/09 10 UTC |
| 1.000 | 2 | 272 ha / 0,68 | 571 ha / 0,14 / 0,84 | 04/09 10 UTC |
| 1.200 | 1 | 364 ha / 0,60 | 596 ha / 0,16 / 0,82 | 04/09 17 UTC |
| 1.200 | 2 | 234 ha / 0,70 | 337 ha / 0,17 / 0,77 | 04/09 01 UTC |
| 1.500 | 1 | 277 ha / 0,68 | 355 ha / 0,19 / 0,76 | 04/09 01 UTC |
| 1.500 | 2 | 41 ha / 0,98 | 41 ha / 0,02 / 0,91 | 02/09 21 UTC |

El umbral de sostén (350 frente a 1.700 kW/m) no cambia el resultado con λ = 1 (la línea de ancla y flancos elige celdas de baja intensidad) y sólo importa con λ = 2 y tasas altas. Conclusiones provisionales: (i) la tasa de línea útil para Mesilla está entre 800 y 1.200 m/h, con IoU 0,20 a la extinción frente a 0,003 del v1 y comisión 0,78 frente a 1,00 (el criterio de éxito de §7.5, comisión < 0,7, no se alcanza todavía porque el primer día ya sobreestima 2–3 veces la superficie); (ii) λ = 2 (caminos más difíciles de cruzar) permite contener con menos línea pero aumenta la omisión; (iii) por encima de 1.200 m/h el modelo apaga el fuego en horas, antes de que recorra la cicatriz.

### 10.5 Tasa calibrada y validación cruzada (2026-10-20)
Se fijó `tasa_linea_m_h: 1000` en `modelo_v2.yaml` (λ = 1, umbral 1.700 kW/m, retardo 2 h) y se repitió la ablación completa con ese valor (`ablacion_t1000.csv`, corridas `<evento>_v2_<variante>_t1000`) y el barrido de Renca (`barrido.csv`):

| Evento | Variante | Primer instante: sim / omisión / IoU | Extinción: sim / IoU / comisión | Contenidas | Último crecimiento |
|---|---|---|---|---|---|
| Mesilla 2024 (182 ha) | contención | 343 ha / 0,69 / 0,12 | 635 ha / 0,12 / 0,86 | 1.096 | 04/09 03 UTC |
| Mesilla 2024 | **ambas** | 405 ha / 0,46 / 0,20 | **577 ha / 0,20 / 0,78** | 746 | 04/09 10 UTC |
| Renca 2022 (3.797 ha) | contención y ambas | 4 ha / 1,00 / 0,00 | 4 ha (apagado en la 1.ª hora de combate) | 25 | 06/09 17 UTC |
| Puertas 2022 (2.062 ha) | contención y ambas | 1 ha / 1,00 / 0,00 | 1 ha (apagado en la 1.ª hora) | 13 | 12/01 17 UTC |
| Las Lagunas 2024 (40.052 ha) | contención | 45.629 ha / 0,40 / 0,39 | 232.953 ha / 0,17 / 0,83 | 11.857 | 07/10 |
| Las Lagunas 2024 | ambas | 34.960 ha / 0,54 / 0,33 | 234.731 ha / 0,17 / 0,83 | 13.962 | 07/10 |

Las 16 combinaciones del barrido de Renca (800–1.500 m/h × 350/1.700 kW/m × λ 1/2) dan el mismo resultado: 4 ha. Con el combate iniciado en la fecha de inicio del SNMF (Renca 07/09 13 UTC, 21 h tras la ignición; 08/09 13 UTC, primer reporte) o en el primer reporte de Puertas (13/01 13 UTC): Renca 48.013 / 58.091 ha a la extinción (IoU 0,06), Puertas 31.441 ha (IoU 0,07), es decir, igual que el modelo libre.

**Lectura.** (i) En Mesilla el v2 calibrado reproduce la contención: 577 ha e IoU 0,20 a la extinción, frente a 63.116 ha e IoU 0,003 del v1; las barreras aportan los puntos de anclaje (sin ellas la contención deja omisión 0,52). (ii) En Renca y Puertas el resultado es binario y depende sólo del tamaño del fuego cuando empieza el combate: con 2 h de retardo el fuego tiene 15–40 celdas y 33 celdas/h lo apagan en una hora; con un día de retardo ya tiene 20.000 ha simuladas (7–10 veces lo observado, limitación del v1 documentada en la Etapa 9) y ninguna tasa razonable lo cierra. La contención no puede corregir una propagación libre que ya está 7 veces sobreestimada el primer día. (iii) En Las Lagunas 2024 la contención recorta 6 % la superficie final y, combinada con barreras, reduce 25 % la del primer instante a costa de omisión 0,54: con 1.000 m/h un megaincendio no se contiene, lo que es coherente con lo observado (40.000 ha con combate). (iv) La captura de focos no se degrada en ningún caso salvo Las Lagunas "ambas" (0,36 frente a 0,56).

**Conclusión y pendientes.** El módulo funciona como se diseñó y es útil donde el v1 acierta la propagación del primer día (Mesilla). Para Renca y Puertas el paso previo es corregir la sobreestimación del v1 en 2022 (k calibrado con el megaincendio, combustibles por analogía), no la contención. Quedan: (a) ligar el inicio del combate y la tasa a los datos del SNMF por evento (`combate.inicio_utc`, `combate.bomberos`) en lugar del retardo fijo; (b) instante de evaluación al segundo día para el criterio de éxito; (c) recalibrar k por estación antes de volver a evaluar v2 en los eventos de 2022.


### 10.6 Barreras solas con humedad de retardo y k recalibrado (2026-10-20)
Ablación `libre_v2` (modelo_v2 sin barreras ni contención) frente a `barreras` (contención apagada) en los diez eventos, con `humedad.muerto_1h: retardo_simard` y k = {0,75 / 2 / 5} (docs/11–12). `scripts/evaluar_v2.py ablacion --variantes libre_v2,barreras --sufijo _k26 --salida ablacion_barreras_k26.csv`; corridas `<evento>_v2_{libre_v2,barreras}_k26`. Primer instante = primer instante de evaluación de la ficha (fin del día de ignición; en Renca y Puertas no es el instante de calibración de docs/12).

| Evento (ref. ha) | Primer instante libre / barreras: sim ha, IoU | Extinción libre / barreras: sim ha, IoU | Cruces / bloqueos | Focos a tiempo libre / barreras |
|---|---|---|---|---|
| Las Lagunas 2024 (40.052) | 44.300, 0,34 / 42.413, 0,34 | 248.587, 0,16 / 248.587, 0,16 | 13.617 / 411.670 | 0,50 / 0,49 |
| Mesilla 2024 (182) | 802, 0,17 / 787, 0,17 | 83.489, 0,00 / 80.664, 0,00 | 5.123 / 108.580 | 1,00 / 1,00 |
| Renca 2022 (3.797) | 525, 0,13 / 516, 0,13 | 80.444, 0,05 / 77.058, 0,05 | 3.738 / 138.810 | 0,29 / 0,28 |
| Chilcas 2022 (296) | 1.287, 0,06 / 1.206, 0,07 | 15.745, 0,02 / 15.188, 0,02 | 630 / 21.679 | 0,63 / 0,58 |
| Aguada 2023 (125) | 497, 0,25 / 449, 0,27 | 3.592, 0,04 / 3.400, 0,04 | 66 / 2.729 | 0,62 / 0,57 |
| Piscu Yacu 2022 (420) | 341, 0,36 / 319, 0,37 | 4.223, 0,09 / 3.991, 0,10 | 161 / 6.365 | 0,63 / 0,63 |
| Puertas 2022 (2.062) | 347, 0,02 / 297, 0,02 | 31.872, 0,07 / 29.902, 0,07 | 1.194 / 42.629 | 0,68 / 0,64 |
| La Pampita 2022 (114) | 229, 0,45 / 177, **0,55** | 7.371, 0,02 / 6.499, 0,02 | 507 / 18.270 | 0,70 / 0,70 |
| Rincón del Carmen 2023 (164) | 103, 0,00 / 36, 0,00 | 11.973, 0,01 / 10.599, 0,02 | 493 / 18.533 | 0,05 / 0,00 |
| Las Chacras 2023 (244) | 549, 0,30 / 507, 0,31 | 50.269, 0,01 / 48.767, 0,01 | 3.804 / 65.186 | 0,97 / 0,97 |
| **Media** | IoU 0,208 / 0,222 | IoU 0,046 / 0,047 | | 0,61 / 0,59 |

Lectura: igual que con el modelo de 2024 (§10.4), las barreras solas no cambian el desenlace. Recortan 0–12 % la superficie a la extinción (0 % en Las Lagunas, donde ambas variantes queman todo el combustible alcanzable) y 2–22 % la del primer día; el fuego cruza los caminos en 3–4 % de los intentos por hora y termina pasando todos. La única mejora clara es La Pampita (IoU 0,45 → 0,55, comisión 0,54 → 0,42), donde la cicatriz está limitada por caminos. En Rincón del Carmen las barreras empeoran: el primer día pasa de 103 a 36 ha y no alcanza ningún foco. La captura de focos baja ligeramente en seis eventos (media 0,61 → 0,59). El módulo sigue valiendo como anclaje de la contención, no como corrector de la comisión.

### 10.7 Despacho local del SNMF (2026-10-20)
La tasa fija y el retardo fijo de este documento se reemplazaron por una parametrización con datos de San Luis: una tasa que escala con la superficie simulada según los reportes del SNMF (κ = 10, calibrado en Mesilla), un retardo calculado por la red vial desde los cuarteles de bomberos y medios aéreos sorteados por clase de tamaño. Ver docs/13 §6-7. Con el modelo vigente ninguna tasa fija entre 1.000 y 3.000 m/h es útil en Mesilla (o no contiene, o apaga el fuego en 2-3 h). El despacho local sube el IoU medio a la extinción de los diez eventos de 0,042 a 0,161, con una regresión en Las Lagunas 2024. La parametrización de este documento sigue disponible como `despacho: global`.
