# Protocolo de evaluación de simuladores de propagación — dominio Las Lagunas–Potrerillos (San Luis)

**Estado: v1.3, APROBADO y CONGELADO.** Aprobación del usuario del 2026-10-22 sobre v1.2 (sha256 `4f0f630b80acef78…`, D32, archivada en `Contexto/procesado/protocolo_v1/protocolo_evaluacion_v1.2.md`), con los cambios del anexo D. Versiones anteriores: v1.1 (`9539025ab63213a9…`, D31, anexo C), v1.0 (`f8d6e7aee0bd4292…`, D23, anexo B), borrador v0.1 (`bf55ccd46feb4f8c…`, anexo A). Vale para el proyecto `V.4/` (D36). El sha256 de este archivo se registra en `Contexto/informes/decisiones.md` (D37).

Cualquier cambio es una **versión nueva** (v1.1, …): se registra con su motivo **antes** de correr lo que afecta. Cambiar un umbral, un instante o la lista de eventos después de ver resultados de prueba es una violación del protocolo y se informa como tal junto al resultado.

Abreviaturas (v1.3): `SIM/` = `V.4/app/simulador_incendios/` (antes `REPO/app/simulador_incendios/`) · `MOD/` = `Sim_modelo/` · `CP/` = conjunto de pruebas (`REPO/app/conjunto_pruebas/`) · O = cicatriz observada · S_m(t) = celdas quemadas por el modelo m hasta t · A = superficie.

---

## 1. Pregunta y alcance

1. ¿Algún motor reproduce, en eventos que **no** se usaron para ajustarlo, (a) la **forma** y (b) la **extensión y el tiempo** de los incendios del dominio mejor que modelos de referencia simples?
2. (Fase 1, cerrada) ¿Hay diferencia demostrable entre `SIM/` y `MOD/`? Respondida en E023: no distinguibles. Desde D36 se trabaja solo con `SIM/`.
3. (v1.3) ¿Agregar supresión y barreras (L03, §2.4) acerca la extensión y el tiempo a lo observado sin empeorar la forma?
4. Según el eje que falle: ¿conviene mejorar el motor elegido o probar otros (§9)?

**Fuera de alcance**: la mitigación como parámetro libre (R7) y la evaluación operativa en modo pronóstico.

**Desarrollo libre.** Con la prueba cerrada (antes de abrirla y entre aperturas), se puede desarrollar sin restricciones sobre el **conjunto de desarrollo** (§3.4): explorar, calibrar, hacer ablación y cambiar código. Ese trabajo nunca toca los eventos de prueba ni sus resultados.

## 2. Modelos evaluados

| ID | Modelo | Versión que se congela | Rol |
|---|---|---|---|
| M1 | `SIM/` tal como está, corrido con el adaptador `REPO/app/motores/sim_adaptador.py`. **Índices NDVI/NDMI del mes previo a la ignición**, no los del mes del evento (v1.2, anexo C) | commit `4ae3cbe` + sha256 de `manifiesto_datos.yaml` + sha256 del adaptador | candidato |
| M2 | `MOD/` tal como está, con la **única** corrección de la fuga de ignición (§4.1), aplicada en un envoltorio fuera de `MOD/` (D20) | `incendios_sl` 0.1.0 + sha256 de `config/modelo_v1.yaml` + sha256 del envoltorio | candidato |
| M2₀ | M2 con `k = 1` en todas las clases | ídem | diagnóstico (solo Fase 1) |
| **M1-L03** (v1.3) | M1 + supresión desde cuarteles y parada por contención SNMF (§2.4, §4.3). Mismo motor y mismos insumos que M1 | commit de `V.4` + sha256 del adaptador, de `ca/supresion.py` y de `motores/despacho.py` + valor de la producción de línea | candidato (Fase 2 y 3) |
| B1 | Elipse escalada (§2.1) | código del evaluador | referencia del eje de forma |
| B2 | Climatología de tasa base (§2.2) | ídem | referencia del Brier (v1.1) |
| B3 | Modelo empírico de probabilidad de quema (§2.3) | ídem + semilla | referencia de los dos ejes y del Brier (v1.1) |

Los motores externos (C2F-W, ELMFIRE) solo se activan por la regla de §9. Desde D36, M2 y M2₀ quedan como antecedente y no se corren en `V.4`.

### 2.4 L03 — supresión desde cuarteles (v1.3, D35)
No hay registros de dotaciones, vehículos ni intervenciones: los valores fijos son supuestos bibliográficos, declarados como tales.
1. **Despacho**: los **3 cuarteles** más rápidos por la red vial provincial (`caminos_sanluis_integrado.geojson`) llegan cada uno en t_llegada = t0 + demora de despacho (**30 min**, supuesto) + viaje por la red, con velocidades por clase de camino (autopista 80, ruta 60, calle y camino 30, servicio 25, huella 15, vado y otros 10, senda 5 km/h; supuesto). Desde el cuartel al nodo más cercano y desde el último nodo hasta la ignición, a pie a 4 km/h. t0 = primer pase VIIRS (§4.1): la detección real pudo ser antes o después, sin dato.
2. **Ataque**: desde su llegada, cada cuartel aporta una dotación que construye **P metros de línea por hora** (único parámetro libre). Cada paso de tiempo, el presupuesto P·n·Δt se gasta conteniendo celdas del **frente activo** (celdas en combustión con vecinas todavía no alcanzadas) con longitud de llama menor que **2,4 m** (límite de ataque directo con autobombas, guía NWCG; supuesto), de menor a mayor llama (primero flancos y cola). Cada celda contenida consume 30 m de línea y deja de propagar.
3. **Caminos**: la regla de cruce por longitud de llama de `SIM/` (§4.6 de su README) se mantiene sin cambios.
4. **Parada**: §4.3.
5. **Valor inicial** de P = 500 m/h por dotación (supuesto, orden de magnitud de autobomba en pastizal). Se calibra en la Fase 2 en [100, 3.000] m/h.

### 2.1 B1 — elipse escalada
- Foco trasero en el centroide de la ignición (§4.1).
- Eje mayor hacia donde va el viento, según el vector medio ponderado por velocidad entre t0 y T80, con la meteorología de M2.
- Relación largo/ancho de Anderson (1983) con viento a media llama = 0,4 × la velocidad media a 10 m.
- Sin relieve ni combustible. Se escala hasta que su área iguala A_obs, recortada **al dominio**. No se recorta a celdas combustibles, porque cada motor tiene su propio mapa de combustible y la referencia dejaría de ser común (v1.1, cambio 4; así está implementada en `REPO/app/evaluador/evaluador.py`).

### 2.2 B2 — climatología de tasa base
p_clim es constante en R_e (§6) e igual a la fracción quemada media en las regiones R de los eventos de **desarrollo**. **Especificación congelada; ejecución en v1.1.**

### 2.3 B3 — modelo empírico de probabilidad de quema
**Especificación congelada; ejecución en v1.1.**
- **Datos de entrenamiento**: polígonos MapBiomas Fuego Col. 1 de la provincia (2.679; 2022–2025) con ignición determinable por §4.1. Se excluyen todos los eventos de prueba de Fase 1 y los de la prueba prospectiva (§3.5).
- **Variables por celda**: distancia a la ignición; coseno entre el rumbo ignición→celda y el viento medio; velocidad media; clase MapBiomas del año previo; NDVI y NDMI previos; pendiente; alineación con la ladera; distancia a caminos.
- **Modelo**: regresión logística con splines naturales de 4 gl por variable continua. Salida p(celda); área esperada = Σp; forma con las A_obs celdas de mayor p.

## 3. Conjunto de eventos

### 3.1 Estado de partida (E008, E010)
- Eventos con insumos listos en los dos motores: **1** (2024 Las Lagunas–Potrerillos), con conflicto de roles: calibración en `MOD/` y validación en `CP/` (SM05).
- 2025 no sirve como año reservado: en el dominio no hay ningún evento ≥ 100 ha (E008). La cifra "3 incendios / 45 ha" del COE proviene del informe del 29-09 §5.2, que usa el dominio original de 1.690 km², cicatrices COE ≥ 10 ha y asignación por centroide (verificado en E010). No contradice E008: los criterios son distintos.

### 3.2 Elegibilidad
**Unidad de evento**: componente (polígono MapBiomas Fuego, mes de quema). Se obtiene cruzando el polígono con el ráster **mensual** de MapBiomas Fuego del dominio, como hizo `MOD/` con Renca 2022. Dos componentes del mismo polígono se unen si un mismo grupo de focos (§4.1) cubre a los dos.

Criterios:
1. **Tamaño y ubicación**: componente ≥ 100 ha; polígono con ≥ 95 % dentro del dominio; componente a ≥ 3 km del borde del dominio.
2. **Fecha**: parte SNMF emparejado (regla de `CP/` D12: punto a ≤ 2 km, fecha dentro de la ventana del mes) o ≥ 1 foco VIIRS atribuible (§4.1).
3. **Ignición** determinable por §4.1 sin usar la geometría de O.
4. **Instante** T80 determinable por §5. Sin instante determinable, el evento **no es elegible** (regla aprobada en v0.1, omitida por error en el texto de v1.0 y aplicada igual en E011; v1.1, cambio 3).
5. **Insumos**: **no** es criterio de entrada. La lista se fija **antes** de preparar insumos (§3.3).

### 3.3 Lista fija antes de preparar insumos
- La lista nominal de Fase 1 se calcula **solo** con los criterios 1–4 y se registra con sha256 **antes** de preparar insumos de cualquier motor.
- Si la preparación de un evento falla (GEE, meteorología, combustible o cualquier insumo de M1 o M2), se informa como **fallo de preparación** de ese evento y motor. **No hay reemplazo.**
- La métrica agregada se informa con y sin esos eventos, y el fallo cuenta como resultado del motor afectado.

### 3.4 Roles: Fase 1, Fase 2 y prueba prospectiva (Fase 3)
- **Desarrollo**: los eventos ya vistos por algún motor: 2024 Las Lagunas–Potrerillos, 2022 Renca (setiembre), 2022 Puertas Coloradas (enero) y 2023 Las Lagunas y La Aguada (SM01). Además, cualquier evento sobre el que se haya corrido un motor antes de congelar la lista. Sobre este conjunto vale el desarrollo libre de §1.
- **Fase 1 — prueba en el dominio.** M1 y M2 **congelados tal como están** (M2 solo con la fuga corregida). Prueba = **todos** los eventos elegibles no vistos del dominio. Compara M1 y M2 contra las referencias y mide si la calibración actual de `MOD/` generaliza. No se recalibra nada antes de abrirla.
- **Fase 2 — recalibración con validación cruzada.** Recalibración sobre los eventos locales (desarrollo + Fase 1, ya abiertos) con validación cruzada N−1. Se informa **siempre rotulada como validación cruzada, nunca como validación independiente**: no hay segundo dominio (L10 descartada, D29). Las versiones de los motores que salgan de la Fase 2 se congelan (commit + sha256 de la configuración) y son las que entran a la Fase 3.
- **Fase 3 — prueba prospectiva** (§3.5). Es la única prueba fuera de muestra después de la Fase 1.
- **Estado al 2026-10-22 (v1.3)**: la Fase 1 está abierta y usada (D33, E023). Los 8 eventos de prueba pasan a **desarrollo**. El conjunto local para la Fase 2 son **12 eventos**: 8 ex-prueba + 2024 + SM01 + Renca y Puertas (estos dos no cumplen §3.2: entran solo como desarrollo exploratorio, no a la validación cruzada). Validación cruzada sobre los **10 elegibles**; con 10 eventos el límite de §9 admite 3 parámetros libres; M1-L03 usa 1.
- **Semilla** `20261015`: fija el **orden** de procesamiento y de presentación de los eventos (`sha256(f"20261015:{id_evento}")`). Ya no asigna roles.
- La estratificación por tamaño, estación y combustible solo se usa para **informar** los resultados por estrato.
- **Motivo del cambio**: con 40 % de prueba quedaban 4–6 eventos, y el límite inferior del IC 90 % equivalía a ganar en todos.
- Los roles de `CP/` (semilla 42) quedan como antecedente; para la decisión rigen estos.
- La prueba de cada fase se abre **una sola vez** por versión congelada de los modelos. Una segunda apertura exige versión nueva, y se informan ambos resultados.

### 3.5 Prueba prospectiva (Fase 3)
- **Eventos**: incendios del dominio con inicio **posterior al 2026-10-20** (congelación de v1.1) que cumplan §3.2. Cada evento se agrega a la lista con sha256 apenas se lo detecta, **antes** de correr cualquier motor.
- **Modelos**: las versiones congeladas al cerrar la Fase 2. Si un evento ocurre antes de ese cierre, se corre con las versiones de la Fase 1 y se informa aparte.
- **Referencia**: MapBiomas Fuego Col. 1 llega hasta 2025. Para eventos de 2026 en adelante, la decisión usa MapBiomas cuando se publique el año. Mientras tanto se informa un resultado **provisional** contra cicatriz COE, dNBR Sentinel-2 y focos VIIRS, rotulado como tal.
- **Apertura**: cada evento se evalúa una sola vez por versión. Los criterios de §9 se aplican al conjunto acumulado, con la regla de n < 8 de §7.
- El segundo dominio (L10) queda fuera (D29). Adaptar el simulador a otras zonas desplazando la grilla es trabajo futuro, fuera de este protocolo.

### 3.6 Referencia
- **Primaria: MapBiomas Fuego Col. 1** (componente del mes).
- **Sensibilidad** (se informa, no decide): cicatriz COE y dNBR Sentinel-2 cuando existan.
- **Techo**: se informa el IoU entre fuentes.

### 3.7 Integración con `CP/`
- Los casos de `CP/` cuyo componente MapBiomas cumple §3.2 entran a la lista; los ya vistos van a desarrollo. La conciliación caso por caso está en E010.
- Se **reutiliza el estándar de `CP/`**: `00_metadatos/esquema_columnas.md`, formato `casos/<id>/caso.json`, `ignicion.geojson`, `meteo_horaria.csv` (ERA5 vía Open-Meteo), `perimetro_final.geojson`, `obs_perimetro_final_30m.tif`, `focos_calor.csv` y el contrato ToA de `validacion/README_validacion.md`.
- **Diferencias documentadas** entre el protocolo y `CP/`:

| Aspecto | `CP/` | Protocolo v1.2 |
|---|---|---|
| Referencia | cicatriz COE | MapBiomas Fuego (COE como sensibilidad) |
| Unidad de evento | componente conexo de cicatriz COE por año | componente (polígono MapBiomas, mes) |
| Ámbito espacial | cuadrantes LGSM (centroide de un fragmento) | dominio de 2.500 km², ≥ 95 % adentro y ≥ 3 km del borde |
| Fecha | solo partes SNMF (focos PENDIENTES) | partes SNMF o focos VIIRS S-NPP (`REPO/datos/crudos/FIRMS/`) |
| t0 e ignición | 12:00 local supuesta; punto del parte | primer pase VIIRS atribuible; parte solo si no hay focos |
| Grilla | bbox de la cicatriz + 5 km | dominio completo (sin truncamiento) |
| Instante | ventana sugerida (tope 72 h) | T80 para forma, extensión y Δt (§5) |
| Roles | semilla 42, calibración/validación 3/3 | Fase 1, Fase 2 (validación cruzada) y Fase 3 prospectiva, §3.4 |
| Meteorología | ERA5 en el punto de ignición | nativa de cada motor (Exp. A); ERA5 común (Exp. B) |

## 4. Condiciones iniciales

### 4.1 Ignición (regla jerárquica; sin "barlovento")
**Atribución de focos**:
- Detecciones VIIRS S-NPP (FIRMS, `type = 0`) a ≤ 1 km del componente, dentro de la ventana [inicio del mes − 10 días, fin del mes + 3 días], o de [inicio SNMF − 1 día, fin SNMF + 1 día] si hay parte.
- Se agrupan en el tiempo (un hueco > 3 días separa grupos) y se toma el grupo con más detecciones.
- MODIS y NOAA-20 solo existen para los 3 eventos de `MOD/`; se usan donde existan.

**Regla**:
1. **Con focos**: las celdas que contienen las detecciones del primer pase del grupo se marcan quemadas en t0 = hora de ese pase.
2. **Sin focos**: punto SNMF emparejado, con t0 = 12:00 local del día de inicio. Si el punto cae en una celda no combustible, se mueve a la combustible más cercana **sin usar O**.
3. Sin focos ni parte: el evento no es elegible (§3.2).

**Fuga corregida**: `MOD/src/incendios_sl/simulation/entradas.py` restringe ese desplazamiento a celdas dentro de la cicatriz (`cand &= (ref == 1)`). M2 se corre con un envoltorio que recalcula la ignición sin esa restricción. `MOD/` no se modifica.

**Prohibido en las métricas principales**: igniciones derivadas de O (centroide, extremo a barlovento, proyección a la cicatriz). Solo se admiten en tablas de sensibilidad rotuladas.

### 4.2 Forzantes
- **Experimento A (decide)**: cada motor con sus insumos nativos, la misma ignición y el mismo dominio (grilla de `MOD/`, idéntica a la de `SIM/`). `SIM/` corre sobre el dominio completo, sin la caja chica.
- **Experimento B (explica, no decide)**: meteorología ERA5 común; las diferencias residuales quedan documentadas.

### 4.3 Parada por contención del SNMF (v1.3, D35)
- Si el SNMF registra el estado **"Contenido"** para el incidente emparejado y **no** hay ningún parte "Activo" con fecha posterior, la simulación termina al **final de ese día local** (00:00 del día siguiente, UTC−3). "Controlado" no se usa.
- Si no hay parte, o el parte no pasa por "Contenido", la simulación termina en máx(T80, T100) + 48 h, como en v1.2.
- La parada vale para M1-L03. M1 de la Fase 1 se corrió sin esta regla.

## 5. Instantes
- **Curva acumulada** de focos atribuidos (§4.1).
- **T80** = fin del pase en que el acumulado llega al 80 %, si hay ≥ 20 focos. Si no: fin del día "contenido" del SNMF; si tampoco, fin del día `fecha_fin` del SNMF. Si no hay ninguno, el evento no es elegible (§3.2, criterio 4). **T80 es la referencia de todas las métricas de extensión y tiempo, L y Δt** (v1.1, cambio 2), además de IoU, Dice, omisión y comisión.
- **Instante degenerado** (v1.1, cambio 1): si los focos atribuidos tienen **un solo pase**, o si T80 ≤ t0, el evento entra **solo al eje de forma** (IoU a igual superficie, Skill_F, centroide) y a las métricas secundarias de focos. Queda **fuera** de los agregados del eje de extensión y tiempo, y se informa por separado. En la lista de E011 son 2 eventos: MB_2022_43638 y MB_2022_43580.
- **Secundarios** (se informan, no deciden): T50; **T100** (último pase con focos atribuidos, con el que se informa un Δt de sensibilidad); contención SNMF; extinción; T80 + 24 h.
- **Motivo del cambio de referencia**: en la ablación exploratoria (E014–E015), Δt de 2024 da −96 h contra T100 y −11 h contra T80. T100 queda dominado por los focos residuales posteriores al crecimiento principal.
- Ningún instante se elige mirando métricas.

## 6. Región de evaluación (fija por evento)
R_e = [buffer(O, 1 km) ∪ ⋃_m buffer(S_m(T80), 1 km)] ∩ dominio ∩ celdas combustibles.

- m recorre todos los modelos de §2 que se corran en esa versión.
- Brier, ROC y confiabilidad se calculan solo en R_e. IoU y Dice no dependen de R.
- **Truncamiento**: si S_m(t) toca el borde del dominio antes de T80, el modelo queda marcado "truncado" en ese evento. Su error de área se trata como censurado por exceso.

## 7. Métricas

### Eje F — forma
- **IoU a igual superficie** (se corta el ToA en A_sim = A_obs).
- **Skill_F** = (IoU_eq,m − IoU_eq,B1) / (1 − IoU_eq,B1), por evento.
- Diagnósticos: desplazamiento del centroide y error de rumbo.

### Eje E — extensión y tiempo
- **L** = ln(A_sim(T80) / A_obs).
- **Δt** = t_m(A_obs) − T80, en horas.
- **Modelo que no alcanza A_obs** (v1.3): el IoU a igual superficie se reemplaza por el **IoU de la huella final** del modelo, y queda marcado como "no alcanza". Δt queda **censurado por defecto**: en la mediana cuenta como |Δt| > 24 h y en la función objetivo como el tope (§9).
- Sesgo: mediana con signo de L y de Δt.

### Secundarias
- IoU, Dice, omisión y comisión en T80 y en los instantes secundarios.
- ToA contra focos: mediana con signo y fracción de focos a ±12 h.
- **Precisión respecto de focos**: fracción de S_m(T80) a ≤ 750 m de un foco atribuido hasta T80.
- Sensibilidad a la referencia.

### Probabilísticas (v1.1)
- Brier en R_e; BSS_clim = 1 − BS_m / BS_B2; BSS contra B3.
- Confiabilidad (10 bins); CRPS del área.

### Agregación
- **Cada evento por separado** y mediana con IC 90 % por *bootstrap* de eventos (10.000 remuestreos).
- Con n < 8 eventos, el IC **no es concluyente** y se informa así.
- M1 contra M2: diferencias **pareadas** por evento.

## 8. Ensambles (especificación congelada; ejecución en v1.1)

| Factor | Perturbación |
|---|---|
| Hora de ignición | Con focos: U[t_pase − 6 h, t_pase]. Con SNMF: U[08:00, 18:00 local] del día de inicio |
| Lugar | Normal isótropa, σ = 375 m (VIIRS) o 1 km (MODIS/SNMF), truncada a celdas combustibles a 3σ |
| Velocidad del viento | Factor lognormal σ_ln = 0,25, AR(1) horario τ = 6 h |
| Dirección | + N(0, 20°), mismo AR(1) |
| Humedad 1 h | + N(0; 1,5 puntos %), mínimo 2 % |
| LFMC | Factor U[0,8; 1,2] |
| Fuente meteorológica | Mitad IFS, mitad ERA5 (si existen las dos) |
| M2 | k por grupo log-uniforme [×0,5; ×2]; WAF U[0,75; 1,5] |
| M1 | equivalentes de su modo estocástico (a mapear en v1.1) |

- N = 50; si el error estándar *bootstrap* del Brier supera el 5 % del Brier, N = 100.
- Semilla del miembro i = `sha256(20261015:evento:i)`.

## 9. Criterio de decisión (dos ejes; aprobar uno solo no alcanza)

**Un motor es aceptable en la prueba de una fase si cumple los dos ejes**:
- **Forma**: mediana de Skill_F > 0 y límite inferior del IC 90 % > 0.
- **Extensión y tiempo**: mediana de |L| ≤ ln 2, **y** mediana de |Δt| ≤ 24 h, **y** a lo sumo un tercio de los eventos con |L| > ln 4.
- **Uso operativo** (v1.1, no elige motor): BSS_clim > 0 con límite inferior del IC > 0.

**M1 contra M2** (se informa; los dos se conservan, D24): un motor se aproxima mejor solo si el IC de la diferencia pareada lo favorece en un eje sin perjudicarlo significativamente en el otro. Si no, se informan como "no distinguibles". Con n < 8, la Fase 1 puede terminar en "no distinguibles" por falta de potencia; eso se informa como tal y no como empate.

| Forma | Extensión/tiempo | Acción |
|---|---|---|
| ✓ | ✓ | Mejorar sobre esa base (L03, L06) |
| ✓ | ✗ | Barreras y mitigación como restricción externa (R7), cargas y humedad; no cambiar de motor |
| ✗ | ✓ | Ablación (§11) para localizar el componente; si nada lo corrige, probar C2F-W |
| ✗ | ✗ | Probar C2F-W (Windows nativo) y ELMFIRE (WSL2) con los mismos insumos; si B3 supera a todos, informarlo |

**Sobreajuste**:
- Parámetros libres calibrados ≤ (eventos de calibración) / 3.
- **Estado actual de `MOD/`**: sus 3 factores `k` por grupo (más el WAF probado) se ajustaron con **un solo evento** (2024), en barridos de 45 + 12 + 16 = 73 configuraciones (`MOD/docs/07` §2). Con 1 evento, el límite admite 0,33 parámetros: `MOD/` lo **excede**. M2 entra igual a la Fase 1 tal como está, porque la Fase 1 mide justamente si esa calibración generaliza. En Fase 2, la recalibración debe respetar el límite.
- Cada configuración probada se registra en la bitácora, y su total se informa con el resultado.
- Función objetivo de calibración (Fase 2, v1.3): media sobre los eventos de **(1 − IoU_eq) + 0,5·|L| + 0,5·min(|Δt| / 24 h, 3)**. Δt censurado suma el tope 3. Los eventos con instante degenerado aportan solo el término de forma. Validación cruzada dejando un evento afuera: el P calibrado sin el evento i se evalúa en el evento i, y solo esas evaluaciones se informan como resultado de la Fase 2.

## 10. Evaluador externo (común a todos los modelos)
- **Ubicación**: `REPO/app/evaluador/`. **No importa nada** de `SIM/` ni de `MOD/`.
- **Entrada**:
  1. Estado horario (GeoTIFF multibanda) o ToA (float32, minutos desde t0, NaN = no quema; mismo contrato que `CP/validacion/`), con `t0_utc`.
  2. Polígono de referencia.
  3. Manifiesto del evento (id, t0, T80, marca de instante degenerado, T100 como secundario, focos, máscaras, b, semilla).
- **Proceso**: reproyecta a la grilla común (EPSG:5345, 30 m), rasteriza O, construye R_e, calcula §7 y aplica las marcas.
- **Salida**: `metricas.json` y una fila CSV en el formato largo de `CP/validacion/plantilla_metricas.csv` (case_id, run, metrica, hora, valor), con sha256 de las entradas y versión del evaluador y del protocolo.
- **Prueba de aceptación**:
  - reproduce `SIM/.../las_lagunas_potrerillos_2024/evaluacion.md` (89.767 ha y Sørensen 0,343 a 72 h contra COE);
  - reproduce `MOD/.../SL-2024-LASLAGUNAS_calibrado/metricas.json` (IoU 0,393 el 21/09 03 UTC);
  - coincide con `CP/validacion/evaluar_simulacion.py` en los ToA sintéticos de `CP/validacion/_sintetico/`;
  - pasa casos sintéticos con respuesta conocida.

## 11. Ablación (R5)
- Sobre los **3 eventos de desarrollo de `MOD/`**, desde la caché, sin L08. Las salidas van a `Contexto/procesado/`; `MOD/` no se escribe.
- Variantes sin tocar el motor: viento (WindNinja / uniforme / sin viento), WAF, k calibrado / k = 1, vecindad 8/16, humedad FFMC / EMC, IFS / ERA5 (con red).
- Variantes que requieren cambiar el motor (no en v1.0): elipse alternativa, FBFM40 en `MOD/`.
- Es exploratoria: los eventos son de desarrollo y nunca deciden el criterio de §9.

## 12. Motores externos (verificado en E008, no instalados)
- **C2F-W**: binario Windows, GPL-3.0, modo Scott & Burgan. Falta confirmar la codificación de combustibles.
- **ELMFIRE**: Linux (WSL2/Docker), AGPL-3.0 + Commons Clause. Lee ráster FBFM de 16 bits. Falta confirmar la tabla FBFM40 y las capas de dosel.
- Mapas FBFM40 locales: `AS/Combustibles/modelos_SB40_{2023,2024,2025}.tif` (grilla del dominio, 30 m).

## 13. Estado de las decisiones de v0.1

| # | Tema | Estado (v1.1) |
|---|---|---|
| 1 | Referencia MapBiomas y mínimo de 100 ha | Aprobado |
| 2 | Proporción y semilla de roles | Reemplazado por las fases (§3.4); la semilla `20261015` solo ordena |
| 3 | T80 y mínimo de 20 focos | Aprobado; en v1.1, L y Δt contra T80 y T100 como secundario (§5) |
| 4 | Buffer b = 1 km | Aprobado |
| 5 | Ensambles | Especificación congelada; ejecución en v1.1 |
| 6 | Umbrales de los ejes, límite de parámetros, peso de la objetivo | Aprobado |
| 7 | B3 | Especificación congelada; ejecución en v1.1 (B2 también) |
| 8 | Regla del segundo dominio | Sin efecto: L10 descartada (D29); reemplazada por la prueba prospectiva (§3.5) |
| 9 | Cifra COE 2025 | Cerrado (§3.1) |

**Punto abierto de v1.0, resuelto en v1.1**: L y Δt se miden los dos contra T80. Sesgo conocido y aceptado: A_obs es la superficie final; si el incendio siguió creciendo después de T80, L tiende a mostrar una sobreestimación aparente. T100 se informa como sensibilidad.

**Pendiente para una versión futura** (no afecta la Fase 1, porque Brier y ensambles se ejecutan después): R_e (§6) todavía dice "∩ celdas combustibles". Antes de calcular el Brier hay que definir una máscara de combustible común a todos los motores, o quitarla con el mismo criterio que B1.

---

## Anexo A. Cambios de v0.1 a v1.0 (aprobación del usuario, 2026-10-15)
1. Evaluación en dos fases en lugar de la asignación 60/40 (§3.4).
2. Δt contra T100 o contención SNMF; T80 queda para forma y extensión (§5).
3. Lista fija antes de preparar insumos, sin reemplazo de fallos; recuadro L10 con criterios 1–3 y antes de entrenar B3 (§3.3, §3.5).
4. Desarrollo libre sobre el conjunto de desarrollo con la prueba cerrada (§1).
5. Estado de §13; nota sobre los `k` de `MOD/` y el límite de parámetros (§9).
6. Integración con el estándar de `CP/` y tabla de diferencias (§3.7).
7. Unidad de evento (polígono, mes), atribución de focos VIIRS S-NPP de FIRMS y corrección de la fuga en un envoltorio (§3.2, §4.1). Concretan v0.1 con las fuentes verificadas en E008/E010; no cambian criterios.

## Anexo B. Cambios de v1.0 a v1.1 (aprobación del usuario, 2026-10-20)
1. **Instante degenerado** (§5): con un solo pase de focos o con T80 ≤ t0, el evento cuenta solo en el eje de forma.
2. **L y Δt contra T80** (§5, §7); T100 pasa a secundario. Resuelve el punto abierto de v1.0.
3. **"Sin instante determinable, no es elegible"** restaurado como criterio 4 de §3.2 (estaba en v0.1, se omitió en v1.0 y se aplicó igual en E011).
4. **Máscara de B1 = dominio** (§2.1), como está implementado en el evaluador.
5. **Fase 2 sin L10** (D29): recalibración con validación cruzada N−1, rotulada como tal, y **Fase 3 prospectiva** con los incendios del dominio posteriores al 2026-10-20 (§3.4, §3.5). Se ajustan §2.3 (B3) y §13.
6. **L01 resuelta** (D24): la comparación M1–M2 se informa, no elige motor (§1, §3.4, §9).

Efecto sobre la lista nominal de E011: la elegibilidad no cambia (8 eventos de prueba). El eje de extensión y tiempo queda con 6 eventos y el de forma con 8.

## Anexo C. Cambio de v1.1 a v1.2 (aprobación del usuario, 2026-10-21)
1. **M1 usa los índices NDVI/NDMI del mes previo a la ignición** (§2). Los casos de `SIM/` (`scripts/preparar_datos.py`, `mes_evento`) usan el compuesto mensual del mes del incendio. Ese compuesto incluye escenas posteriores a la ignición, es decir, información de la cicatriz: es una fuga equivalente a la de M2 (§4.1). Con el cambio, M1 y M2 cumplen la misma regla: ningún insumo posterior a la ignición. Evidencia en E018 (evento de desarrollo 2024): con el mes del evento, IoU a igual superficie 0,238; con el mes previo, 0,252. Ese evento no muestra ventaja por la fuga, pero el riesgo existe en otros.

## Anexo D. Cambios de v1.2 a v1.3 (aprobación del usuario, 2026-10-22; proyecto V.4, D36)
1. **Δt en la función objetivo** de calibración (§9), con tope de 3 días.
2. **Parada por contención del SNMF** (§4.3, D35).
3. **Modelo que no alcanza la superficie observada** (§7): IoU de la huella final y Δt censurado. Cubre el caso que el agregador de E023 manejaba como sensibilidad.
4. **M1-L03 como versión nueva** de M1 (§2, §2.4): supresión desde cuarteles con 1 parámetro libre (producción de línea).
5. Estado de las fases (§3.4): Fase 1 usada; conjunto local de 12 eventos (10 elegibles) para la Fase 2. `MOD/` queda como antecedente (D36).
