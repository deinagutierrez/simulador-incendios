# Etapa 14 — Integración de V.4 (SIM) como v4.0 y flexibilidad de la simulación heredada de v3.0

Fecha: 2026-10-25. Estado: integrado; 140 pruebas automáticas en verde; V.4 reproducible bit a bit.

## 1. Qué es v4.0

v4.0 cambia el **motor**: el simulador `SIM/` de V.4 (autómata celular de 30 m con tiempos de llegada, Rothermel +
Scott y Burgan 40, Huygens por origen heredado, sub-pasos CFL, salidas horarias para agentes) reemplaza al autómata
`incendios_sl.simulation` de v2.0/v3.0. Se conserva todo lo demás del estándar: datos compartidos, eventos históricos,
escenarios YAML con los mismos campos, resultados por corrida con resumen estadístico, visor y cuaderno de Colab.

| Origen | Qué aporta a v4.0 |
|---|---|
| V.4 `app/simulador_incendios` (SIM) | motor, física SB40, humedad viva por NDMI y curado por NDVI, caminos e infraestructura (viviendas, red eléctrica), modificador de combustible, viento externo, ensembles, pavesas, L03, casos de prueba con evaluación automática |
| V.4 `app/` (banco) | adaptador del protocolo, despacho por red vial, registro de corridas, evaluador externo, Fase 1, L03, web del banco |
| v3.0 | eventos y dominio, **barreras probabilísticas**, **contención por combate** (línea con anclaje, escapes, medios aéreos), **despacho SNMF** (tasa escalonada, regiones, κ(A), arribo vial desde 42 cuarteles), humedad muerta FFMC, humedad viva min–max, factores k y WAF, variantes y precedencias de escenario |
| Verificación (informe 15) | correcciones P1–P9, H1–H6, con interruptor para volver a V.4 |

## 2. Disposición en el repositorio

| V.4 | v4.0 |
|---|---|
| `app/simulador_incendios/simulador/` | `src/v4.0/src/simulador/` (versión 4.0.0; `rutas.py` nuevo) |
| `app/simulador_incendios/{datos, manifiesto_datos.yaml, conjunto_prueba}` | `datos/inputSimulacion/sim_v4/` (rutas del manifiesto relativas a esa carpeta) |
| `app/simulador_incendios/escenarios/` | `escenarios/v4.0/sim/` |
| `app/simulador_incendios/salidas/` | `resultados/v4.0/<run_id>/` |
| `app/simulador_incendios/tests/` | `test/v4.0/` (más los nuevos) |
| `app/{banco, evaluador, motores, evaluacion, web, preprocesamiento}`, `config/rutas.yaml` | `src/v4.0/app/`, `src/v4.0/config/rutas.yaml` |
| `datos/entradas`, `datos/protocolo` | `datos/inputSimulacion/banco_v4/` (cobertura, máscara y fuego mensual no se copian: son idénticos a los de v3.0 y se leen de su lugar) |
| `datos/banco` (corridas, Fase 1, web) | `resultados/v4.0/banco/` |
| `docs/protocolo_evaluacion.md` | `docs/v4.0/16_protocolo_evaluacion_banco.md` |
| `../Contexto/extraido` (no existe en este equipo) | `datos/crudos/` (SNMF, dominio, caminos, cuarteles) |

La capa nueva `src/v4.0/src/incendios_sl/` mantiene la API de v3.0 que usa el cuaderno (`config.dir_escenarios()`,
`dir_resultados()`, `cargar_evento()`…) y traduce una corrida estándar a la configuración de SIM:
`eventos.py` (ficha → insumos de SIM en `datos/procesados/v4.0/<evento>/`: meteo horaria, combustible pre-evento por la
regla 3.3 con la mediana NDVI/NDMI de enero–marzo, índices del evento, cicatriz y focos), `arribo.py` (arribo vial y
región de despacho), `escenario.py` (variantes y precedencias) y `resumen.py` (registro, resumen y métricas).

## 3. Flexibilidad de v3.0 integrada en SIM

| Variación de v3.0 | En v4.0 | Clave |
|---|---|---|
| Selección de modelo + `parche` + `ajustes` | `escenarios/v4.0/modelos/*.yaml` se fusiona sobre los valores por defecto de SIM | `modelo`, `parche`, `ajustes` |
| Variantes de ablación | `libre`, `barreras`, `contencion`, `ambas`, `local`, `local_pronostico`, **`l03`**, **`v4_original`** | `variante` |
| Barreras lineales con cruce probabilístico P = σ(β(L/W − λ)), sorteo por enlace y hora, bloqueo hasta la hora siguiente | sobre los caminos de SIM y los cortafuegos de `barreras.extra`, con llama direccional y evaluación por enlace | `barreras: auto/on/off`, `parametros.barreras.{modo, llama, lambda, beta, semilla, normalizar, extra}` |
| Contención: línea con anclaje y flancos, umbral de sostén 1700/3500 kW/m, escapes, acumulación | `simulador/ca/contencion.py` | `contencion: auto/on/off`, `parametros.contencion.*` |
| Despacho global / local / pronóstico | igual que v3.0 (más `l03`, la supresión desde cuarteles de V.4) | `despacho` |
| Tasa SNMF κ(A)·a·A^b por región; arribo vial desde los cuarteles | producto `arribo_las_lagunas_potrerillos.npz` de v3.0 | `contencion.snmf`, `combate` |
| Medios aéreos de la ficha y sorteo automático | intervalos UTC y sorteo condicional por clase | `contencion.aereo_*` |
| Humedad muerta FFMC o retardo (Simard) | `retardo` (EMC NFDRS), `ffmc_vanwagner`, **`fija`** (escenarios D/L de S&B) | `humedad.metodo_muerto`, `fija_m1/m10/m100` |
| Extinción por lluvia de 24 h, Mx por clase | por familia o código SB40 | `humedad.lluvia_24h_mm_extincion`, `mx_grupo`, `mx_codigo` |
| Humedad viva min–max (herbáceo y leñoso) | además de la lineal de V.4 y un valor fijo | `humedad.viva_metodo` |
| `k_clase`, `k_global`, `factor_waf` | por familia (GR, GS, SH, TU, TL, SB) o código SB40 | `k_grupo`, `k_global`, `factor_waf` |
| Hipótesis de hora (h0/h1/h2) y puntos alternativos | igual que v3.0, con los 10 eventos | `hipotesis`, `ignicion` |
| Parada por horas sin avance y por contención | suspendida mientras puede haber escapes, pavesas o celdas latentes | `parametros.parada` |
| (nuevo de V.4) casos de prueba, ensembles, pavesas, modificador de combustible, viento externo | disponibles desde la corrida estándar | `caso`, `ensemble`, `mitigacion` |

Con la contención apagada la salida es idéntica a la de SIM sin ella; con `sim_v4_original` es idéntica a V.4.

## 4. Decisiones

- **Modelo por defecto `modelo_v3`** (tercer juego de parámetros del repositorio): física corregida, barreras activas,
  contención solo si la pide la variante o el campo `contencion`. `modelo_v1`/`modelo_v2` no se copian: pertenecen al
  motor anterior y siguen disponibles en `escenarios/v2.0` y `v3.0`.
- **Precedencia del inicio del combate**: los `ajustes` de la corrida ganan a la ficha (contrato de v4.0);
  `combate: {precedencia: v3}` restituye la regla de v3.0 (la ficha gana).
- **Intensidad de decisión de la contención** = la de v3.0 (máximo de I_B·P(cruce) hacia las vecinas pendientes); la
  de avance de V.4 queda como opción (`contencion.intensidad: avance`).
- **L03 conserva su criterio** para reproducir el banco de V.4 (`supresion.intensidad: avance`).
- **Banco**: el adaptador corre por defecto con `sim_v4_original` para reproducir la Fase 1 de V.4 (`--modelo
  modelo_v3` para el modelo corregido). La Fase 1 regenerada desde las corridas registradas da los mismos valores.

## 5. Pendientes

- Visor: no dibuja la línea de contención ni la de L03.
- Calibración (Fase 2 del protocolo, informe 16): umbrales de sostén y despacho, humedad viva, curado; revisar el
  combustible del verano 2022 y el modo estocástico (informe 15, §6).
- ~~Biblioteca de viento WindNinja de v3.0~~: resuelto el 2026-10-26, SIM la lee directamente (`viento.fuente: windninja`,
  activo en `modelo_v3`); ver informe 17.
- Calibración de la Fase 2: pausada; estado y cómo reanudarla en el informe 17.
- `.github/workflows` (CI) no existe en el repositorio, como en v2.0/v3.0.
