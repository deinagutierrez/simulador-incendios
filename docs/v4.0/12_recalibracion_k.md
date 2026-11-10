# Etapa 12 — Recalibración de k por grupo de clases con diez eventos y humedad de retardo

Fecha: 2026-10-20. Script: `scripts/calibrar_k.py`. Resultados: `data/resultados/calibracion_k_v2/` (`barrido.csv`, `resumen_barrido.csv`, `validacion.csv`, `mejor.json`; la primera grilla, con el instante del primer día también para Renca y Puertas, se conserva como `*_grilla1_instante_dia1.csv`).

## 1. Diseño
- **Parámetros:** un factor k por grupo de clases: A = pastizal, pastura/cultivo, arbustal abierto (1–3); B = arbustal cerrado, bosque abierto (4–5); C = bosque cerrado, plantación (6–7). Grilla final kA ∈ {0,5; 0,75; 1,0} × kB ∈ {2; 3; 5} × kC ∈ {3; 5} (18 combinaciones; la primera grilla, más baja, dio el óptimo en su borde superior).
- **Modelo:** `modelo_v2` con humedad de retardo (docs/11), WAF 1, sin barreras ni contención; ignición de referencia por evento (`evaluar_v2.REFERENCIA`).
- **Objetivo:** IoU medio, con peso igual por evento, entre la simulación y la cicatriz al **instante de calibración** de cada ficha: fin del día de ignición en los incendios de un día; fin de la propagación principal en los de varios días (Las Lagunas 60 h, Renca y Puertas 59 h). Las corridas se recortan a ese instante (6–30 s cada una).
- **Conjuntos:** calibración = Las Lagunas 2024, Mesilla 2024, Renca 2022, Chilcas 2022, Aguada 2023, Piscu Yacu 2022; validación ciega = Puertas 2022, Pampita 2022, Rincón del Carmen 2023, Chacras 2023 (un verano, un invierno ventoso, uno calmo, uno posterior a lluvia).

## 2. Barrido (eventos de calibración)
| kA | kB | kC | IoU medio | Dice | Omisión media | Comisión media |
|---|---|---|---|---|---|---|
| **0,75** | **2** | **5** | **0,221** | 0,350 | 0,318 | 0,713 |
| 0,5 | 2 | 5 | 0,221 | 0,351 | 0,441 | 0,685 |
| 0,75 | 2 | 3 | 0,218 | 0,347 | 0,350 | 0,710 |
| 0,5 | 2 | 3 | 0,212 | 0,341 | 0,482 | 0,684 |
| 0,5 | 3 | 5 (k de 2024) | 0,207 | 0,323 | 0,299 | 0,750 |
| 1,0 | 2 | 3 | 0,201 | 0,322 | 0,296 | 0,748 |
| 0,75 | 3 | 5 | 0,190 | 0,299 | 0,250 | 0,781 |

La superficie objetivo es plana: las ocho mejores combinaciones están entre 0,19 y 0,22. Se adopta **kA = 0,75, kB = 2, kC = 5** (empata con kA = 0,5 y tiene menor omisión; para prevención la omisión pesa más que la comisión). Respecto de 2024 sube el herbáceo-arbustal abierto (0,5 → 0,75) y baja el arbustal cerrado-bosque abierto (3 → 2).

Por evento con el k adoptado (sim / ref ha, omisión, comisión, IoU): Las Lagunas 44.300 / 40.052, 0,46, 0,51, **0,34**; Mesilla 802 / 182, 0,22, 0,82, 0,17; Renca 25.641 / 3.797, 0,00, 0,85, 0,15; Chilcas 1.287 / 296, 0,69, 0,93, 0,06; Aguada 497 / 125, 0,01, 0,75, 0,25; Piscu Yacu 341 / 420, 0,52, 0,41, **0,36**.

## 3. Validación ciega (k adoptado, eventos no usados en el ajuste)
| Evento (ref. ha) | Instante | sim / omisión / comisión | IoU | Focos a tiempo |
|---|---|---|---|---|
| Puertas 2022 (2.062) | fin propagación principal | 16.244 ha / 0,03 / 0,88 | 0,12 (v1: 0,09) | 0,68 |
| La Pampita 2022 (114) | fin del día | 229 ha / 0,07 / 0,54 | **0,45** (v1: 0,44) | 0,70 |
| Rincón del Carmen 2023 (164) | fin del día | 103 ha / 1,00 / 1,00 | 0,00 (v1: 0,00) | 0,05 |
| Las Chacras 2023 (244) | fin del día | 549 ha / 0,25 / 0,67 | **0,30** (v1: 0,12, se apagaba) | 0,76 |

IoU medio en validación 0,22, igual que en calibración (0,22): el ajuste **transfiere** y no sobreajusta, pero el nivel es bajo.

## 4. Lectura
1. Con la humedad corregida, k apenas cambia respecto de 2024 y el IoU medio sube de 0,207 a 0,221. **El error restante no es de k.** La comisión media (0,7) y los casos extremos (Chilcas 4×, Renca 7×, Puertas 8× de superficie) señalan tres fuentes que un factor multiplicativo no puede representar: el combate desde el primer día en incendios chicos, los límites de parcelas y cortafuegos que no están en los datos (bordes rectos), y el viento local del modelo de 9 km (Rincón: 0 de IoU con cualquier k; el modelo nunca quema la cicatriz en la tarde calma).
2. La única ganancia clara es en los eventos que el v1 subestimaba (Chacras, Pampita) y viene de la humedad (docs/11), no de k.
3. El evento de calibración original baja de 0,39 a 0,34 al repartir el ajuste entre seis eventos: lo que se gana en generalidad se paga en el megaincendio.
4. Siguiente orden de trabajo: (a) evaluar barreras y contención con el k y la humedad nuevos en los diez eventos, con inicio de combate desde el SNMF; (b) meteorología de estación (REM San Luis) y WindNinja con vientos diurnos, con Rincón del Carmen como caso de prueba; (c) humedad viva por estación (Puertas, Chilcas); (d) recién después, otra vuelta de k.

## 5. Parámetros vigentes (`config/modelo_v2.yaml`)
`k_clase: {1: 0.75, 2: 0.75, 3: 0.75, 4: 2.0, 5: 2.0, 6: 5.0, 7: 5.0}` con `humedad.muerto_1h: retardo_simard`. El v1 (`modelo_v1.yaml`, k de 2024 y FFMC) no cambia.
