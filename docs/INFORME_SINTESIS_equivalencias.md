# Equivalencias de códigos del informe de síntesis

Tabla de trazabilidad entre los códigos del informe de síntesis del simulador (X-NN, DEC-NN) y las referencias internas del proyecto.

**Fuentes:**
- Bitácora: `Contexto/informes/reporte_avance.md` §8, entradas E0NN. La copia consultada está en `D:\informes\reporte_avance.md`; el número de línea va como RA:nnn.
- Decisiones: `Contexto/informes/decisiones.md`, códigos D0NN. Copia consultada en `D:\informes\decisiones.md`; el número de línea va como DEC:nnn.
- Documentos de versión: `docs/<versión>/`.

## Versiones

| Código | Referencia interna |
|---|---|
| V1 | Prototipo `Sim_modelo/` (MOD), paquete `incendios-sl` 0.1.0; datos en el release `v1.0-artefacto` (`simulador_v1.zip`) |
| V2 | `src/v2.0` (MOD reempaquetado, `modelo_v1`; motor «M2» del banco) |
| V3 | `src/v3.0` (`modelo_v2`) |
| V3.1 a V3.4 | `src/v3.1` a `src/v3.4` |
| V4 original | `SIM/` (simulador V.4 entregado, `sim_v4_original`; motor «M1» del banco) |
| V4 | `src/v4.0` (`modelo_v3`) |
| «libre V2» / «libre V3» | Variantes `libre` (`modelo_v1`) y `librev2` / `libre_v2` (`modelo_v2`) de v3.x |

## Experimentos

| Código | Entrada de bitácora / fuente | Decisión original | Nota |
|---|---|---|---|
| X-01 | sin entrada; `docs/v2.0/07_validacion_etapa7.md` L12-L27 | — | k global vs k por clase |
| X-02 | sin entrada; `docs/v2.0/05_informe_rendimiento_etapa5.md` L28-L30 | — | 8 vs 16 vecinos |
| X-03 | E008 (RA:458) | D21, D22 | Comparación inicial SIM vs MOD en 2024 |
| X-04 | E012 (RA:515) | — | Fuga de ignición en MOD |
| X-05 | E014 + E015 (RA:539, RA:554) | — | Ablación de MOD |
| X-06 | sin entrada; `docs/v3.0/11_humedad_combustible_muerto.md` | — | Humedad por retardo |
| X-07 | sin entrada; `docs/v3.0/12_recalibracion_k.md` | — | Recalibración de k |
| X-08 | sin entrada; `docs/v3.0/10_diseno_barreras_contencion.md` L210-L212 | — | Barreras en v3.0 |
| X-09 | sin entrada; `docs/v3.0/13_combate_snmf_san_luis.md` L125-L181 | — | Despacho SNMF en v3.0 |
| X-10 | E018 (RA:577) | D32 | Índices del mes previo |
| X-11 | E023 (RA:644) | D33, D35 | Fase 1 del banco |
| X-12 | E026 (RA:679) | D37 | Supresión L03 |
| X-13 | E027 (RA:706) | — (protocolo v1.4 en borrador) | Corte en A_obs |
| X-14 | E029, E030, E031, E032 (RA:754, 774, 783, 792) | D38, D39, D40, D44 | `parar_en_cicatriz` |
| X-15 | E033 (RA:814) | — | Lote E033 |
| X-16 | E035 (RA:840) | D41 | Ablación: WindNinja vs serie |
| X-17 | E035 (RA:840) | D41 | Ablación: `escapes: potencial` |
| X-18 | E035 (RA:840) | D42 (README: «no recomendada») | Ablación: FFMC |
| X-19 | E035 (RA:840) | D42 (README: «no recomendada») | Ablación: humedad viva min–max |
| X-20 | E033 + E035 (RA:814, RA:840); `docs/v4.0/18` | D42 | Combate «local» |
| X-21 | sin entrada; `docs/v3.1/02`, `resultados/v3.1/comparacion_v30_vs_v31` | — | Hora y punto acotados por VIIRS |
| X-22 | sin entrada; `docs/v3.1/02` L48-L61 | — | `factor_waf` en v3.1 |
| X-23 | sin entrada; `docs/v3.1/03` | — | k por grupo en v3.1 |
| X-24 | sin entrada; `docs/v3.1/04` | — | Viento escalar, IDW y WindNinja diurno |
| X-25 | E036 + E037 (RA:876, RA:908); `docs/v4.0/19` | D41, D42, D43 | Lote E037 |
| X-26 | E038 + E043 (RA:944, RA:1085); `docs/v4.0/20` | D46 | Regla 3.3b |
| X-27 | E039 (RA:975); `docs/v4.0/21` | — | Selectividad del combustible |
| X-28 | E040 (RA:1003); `docs/v4.0/22` | — | Cribado `k_grupo` |
| X-29 | E041 + E042 (RA:1042, RA:1060); `docs/v4.0/23` | D45 | Grilla SH×TU con CV |
| X-30 | E044 (RA:1103); `docs/v4.0/24` | — | Pasturas |
| X-31 | E045 (RA:1126); `docs/v4.0/25` | D47 | Regla 3.3c |
| X-32 | E046 (RA:1157); `docs/v4.0/26` | — | Análisis de forma |
| X-33 | E047 (RA:1180); `docs/v4.0/27` | D48 | `factor_waf` 1,25 / 1,5 |
| X-34 | E048 (RA:1205); `docs/v4.0/28` | — | Límite de viento y dirección fija |
| X-35 | E049 (RA:1230); `docs/v4.0/29` | — | Radio de Huygens (y pavesas exploratorias) |
| X-36 | sin entrada; `docs/v3.2/01`, `resultados/v3.2/comparacion_v31_vs_v32` | — | Focos NOAA-20 |
| X-37 | sin entrada; `docs/v3.2/03` | — | `factor_lb` |
| X-38 | sin entrada; `docs/v3.2/04` | — | Barrera verde |
| X-39 | sin entrada; `docs/v3.2/06` | — | Pronóstico re-sincronizado |
| X-40 | sin entrada; `docs/v3.3/06`, `resultados/v3.3/comparacion_v32_vs_v33` | — | `pronostico.factor_lb` 1,5 |
| X-41 | sin entrada; `docs/v3.3/07`, `resultados/v3.3/paso7_progresion` | — | Progresión datada |
| X-42 | sin entrada; `docs/v3.4/03`, `resultados/v3.4/comparacion_v33_vs_v34` | — | Mapas de combustible estructura y dw |
| X-43 | E049, E051, E052 (RA:1230, RA:1274, RA:1294); `docs/v4.0/30` | D49, D50 | Pavesas prerregistradas |
| X-44 | E053 (RA:1329) | D51 | Líneas C, D, E y GOES-R |
| X-45 | E054, E055, E056, E060 (RA:1356, 1377, 1395, 1475) | D51, D52 | Ensamble B + A (`lote_E054`) |
| X-46 | sin entrada propia (RA:1418, 1429, 1444-1447); `lote_E058`; `docs/v4.0/INFORME_TECNICO_MOTOR_V4.md` §7.4 | — | Control v3.1 vs v4 |
| X-47 | E057 (RA:1414) | — | Cocientes de tiempo; v4.1 descartada |
| X-48 | E057 + E058 (RA:1414, RA:1436); `lote_E059`; `INFORME_TECNICO_MOTOR_V4.md` §7.5 | no registrada (pendiente, RA:1459) | Barrido `k_global`, R3 |
| X-49 | E059 (RA:1462); carpeta `lote_E060` | — (pendiente de aprobación) | Eventos no vistos |
| X-50 | sin entrada; `resultados/v4.0/resumen_lote_E063.md/.csv` | — | Lote E063 (libre con tope, 73 igniciones) |

## Decisiones

| Código | Decisión original | Entrada de bitácora | Estado original |
|---|---|---|---|
| DEC-01 | D22 + D23 (DEC:26, DEC:27) | E008, E010 | Protocolo v1.0 (reemplazado) |
| DEC-02 | D24 (DEC:28) | E016 | Interrumpida por D36 |
| DEC-03 | D31 (DEC:35) | E017 | Protocolo v1.1 (reemplazado) |
| DEC-04 | D32 (DEC:36) | E020 | Protocolo v1.2 (reemplazado) |
| DEC-05 | D33 (DEC:37) | E021 | Ejecutada |
| DEC-06 | D35 (DEC:39) | E022 | Aprobada; afectada por D42 y D53 |
| DEC-07 | D36 (DEC:40) | E024 | Vigente |
| DEC-08 | D37 (DEC:41) | E026 | Protocolo v1.3 vigente |
| DEC-09 | D38 (DEC:42) | E029 | Vigente (excepción reemplazada por D40) |
| DEC-10 | D39 + D40 (DEC:43, DEC:44) | E031, E032 | Vigente |
| DEC-11 | D41 (DEC:45) | E036 | Vigente |
| DEC-12 | D42 (DEC:46) | E036 | Modificada en parte por D53 |
| DEC-13 | D43 (DEC:47) | E036 | Vigente |
| DEC-14 | D44 (DEC:48) | E036 | Vigente (documental) |
| DEC-15 | D45 (DEC:49) | E042 | Vigente |
| DEC-16 | D46 (DEC:50) | E043 | Vigente, provisoria |
| DEC-17 | D47 (DEC:51) | E045 | Vigente |
| DEC-18 | D48 (DEC:52) | E047 | Vigente |
| DEC-19 | D49 (DEC:53) | E051 | Cumplida |
| DEC-20 | D50 (DEC:54) | E052 | Vigente |
| DEC-21 | D51 (DEC:55) | E053 | Vigente |
| DEC-22 | D52 (DEC:56) | E054 | Ejecutada (cierre en E060) |
| DEC-23 | D53 (DEC:57) | E062 | Vigente; probada solo fuera de Colab |

Decisiones de `decisiones.md` sin código DEC en el informe, por ser de organización del trabajo y no del simulador: D01–D20, D21, D25–D30 y D34.

Notas de numeración de la bitácora:
- Hay dos entradas E032.
- El lote `lote_E059` se registra en las entradas E057 y E058.
- La carpeta `lote_E060` corresponde a la entrada E059.
- El lote `lote_E054` se cierra en la entrada E060.
- El lote E063 no tiene entrada de bitácora: la última entrada es E062.
