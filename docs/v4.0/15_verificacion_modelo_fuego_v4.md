# Etapa 15 — Verificación del modelo de simulación de fuego de V.4 (SIM)

Fecha: 2026-10-25. Estado: verificación completa; correcciones implementadas en v4.0 y configurables.
Etiquetas: **[BIBLIO]** valor de la literatura · **[MEDIDO]** resultado de una corrida o prueba · **[HIPÓTESIS]** · **[CALIBRAR]**.

Objeto: el simulador `SIM/` de V.4 (`V.4/app/simulador_incendios`, versión 0.1.0, 2026-10-22): autómata celular de 30 m
con Rothermel (1972) en la formulación de Andrews (2018), los 40 modelos de Scott y Burgan (2005), humedad muerta de
Simard con retardos de 1/10/100 h, viento a media llama con WAF, elipse de Anderson (1983) y construcción de Huygens
discreta por "origen heredado". En v4.0 vive en `src/v4.0/src/simulador`.

## 1. Método

1. **Verificación estática** [BIBLIO]: revisión línea por línea de `physics/`, `ca/`, `fuel/` e `io/meteo.py` contra
   Rothermel (1972), Albini (1976), Andrews (2018, RMRS-GTR-371), Andrews (2012, RMRS-GTR-266), Scott y Burgan (2005,
   tabla 7), Anderson (1983), Turner y Lawson (1978) y la versión NFDRS de Simard (1968); contraste con el motor de v3.0.
2. **Verificación dinámica** [MEDIDO]: los 33 tests de V.4 (pasan), `python -m simulador validar` (manifiesto v1.0, 51
   entradas válidas) y la corrida del caso de prueba `las_lagunas_la_aguada_2023` (base, 36 h): **2783,0 ha contra
   106 ha observadas**, Sørensen 0,072; idéntico a lo informado por V.4. Queda en
   `resultados/v4.0/verificacion_V4_original_aguada_2023_base_20261025-1539/`.
3. **Revisión adversarial** de cada corrección con scripts mínimos y comparación contra el código original de V.4 en
   un proceso aparte, y contra una solución de referencia de Huygens (suma de Minkowski en combustible homogéneo;
   tiempo mínimo por Dijkstra con ~80 direcciones en relieve).

## 2. Resultado de la verificación estática

El núcleo de Rothermel es correcto: reproducido a mano y con el código, GR2 da 72,06 ft/min y SH2 12,26 ft/min en
D1L1 (1 h 3 %, 10 h 4 %, 100 h 5 %, herbáceo 30 %, leñoso 60 %, curado 1) a 5 mi/h a media llama, contra 72,0 y 12,27
calculados con Andrews (2018) [BIBLIO]. La tabla SB40 coincide con la tabla 7 de Scott y Burgan en los modelos
revisados. Los defectos están alrededor del núcleo:

| # | Componente | Defecto en V.4 | Efecto | Corrección en v4.0 (interruptor) |
|---|---|---|---|---|
| P1 | `physics/viento.py:24` | Conversión 10 m → 20 ft invertida: ×1/0,87 = 1,149 en lugar de ×0,87 (U₂₀ft = U₁₀m/1,15) | viento a media llama ×1,32; φ_w ×1,5 en pastos; L/B 3,34 en vez de 2,41 (GR2, 20 km/h) | `viento.factor_10m_20ft: 0.87` |
| P2 | `physics/humedad.py:34-37` | EMC de Simard con coeficientes de la versión en °C aplicados a T en °F | 30 °C / 20 % → 2,67 % en vez de 4,16 %; 1 h −1,3 a −2 puntos; ROS +10–20 % | `humedad.emc: nfdrs` (coeficientes NFDRS, como v3.0) |
| P3 | `ca/automata.py:311-317, 346-356` | El origen heredado inicializa el avance con el rumbo y la excentricidad **actuales**: la elipse se redibuja hacia atrás en el tiempo cuando rota el viento o cambia la pendiente (efecto trinquete) | área +17 % tras una rotación de 90°, +67 % con viento oscilante ±40°; adelanto creciente de llegadas | `huygens: {tol_rumbo_deg: 15, tol_e: 0.05}`: forma guardada en el origen y re-anclaje por cambio de forma |
| P4 | `ca/automata.py:364-368` | Los caminos se cruzan con la llama **de cabeza** en todas las direcciones | flancos y cola cruzan caminos; el mosaico pierde su efecto de barrera | `barreras.llama: direccional` (L(θ)=L·(R(θ)/R_max)^0,46) |
| P5 | `ca/automata.py:419-423` | Extinción por humedad definitiva: el frente que se apaga de noche no retoma | subestima la reactivación del día siguiente | `extincion: reversible` |
| P6 | `physics/rothermel.py:149` | Límite de viento de 1972 (U ≤ 0,9·I_R) aplicado antes de la pendiente | resta ROS con viento fuerte | `limite_viento: andrews_2013` (U_eff ≤ 96,8·I_R^⅓, después de combinar) [BIBLIO] |
| P7 | `ca/automata.py:258` | El crédito de una celda nueva se cuenta desde la llegada: anula `ignicion_delay_min` | menor (0 por defecto) | `credito_desde_activacion: true` |
| P8 | `ca/automata.py:401-417` | Probabilidad de pavesas por sub-paso: depende del CFL | menor (desactivado por defecto) | `spotting.por_unidad_tiempo: true` |
| P9 | varios | curado aplicado a modelos no dinámicos; σ < 16 sin grupo; códigos desconocidos sin aviso | sin efecto con SB40 | `humedad.curado_solo_dinamicos`, aviso de códigos |

Defectos encontrados después, en la revisión adversarial de v4.0, y corregidos:

| # | Defecto | Corrección |
|---|---|---|
| H1, H3 | Con vecindad 16 los saltos de caballo saltaban caminos y cortafuegos sin evaluarlos; un cortafuego rasterizado a 45° dejaba pasar el fuego por las esquinas (89 y 87 celdas del otro lado de un muro) | en los modos `umbral` y `probabilistico` la barrera se evalúa por **enlace**: ancho = máximo de la receptora y las celdas intermedias (0 celdas del otro lado) |
| H2 | `parada.horas_sin_avance: 12` cortaba la extinción reversible en noches húmedas largas (25,6 ha en vez de 726 ha) | contador `n_latentes`; la parada se suspende hasta `parada.latentes_max_h` (24) |
| H6 | La logística de cruce de v3.0 tiene un piso P(L=0) = 1,8 % por enlace y hora | `barreras.normalizar: true` (P(0) = 0); `false` = fórmula de v3.0 |

## 3. Compatibilidad: V.4 se reproduce bit a bit

El modelo `escenarios/v4.0/modelos/sim_v4_original.yaml` vuelve a encender cada defecto (factor 1/0,87, EMC de V.4,
`huygens: null`, extinción definitiva, caminos con la llama de cabeza, crédito y pavesas de V.4, sin parada ni
contención). Con él [MEDIDO]:
- `test_fisica_v4.py::test_reproduce_v4_original_exacto` compara contra el código original de V.4 en un proceso aparte
  (determinista 8 y 16 vecinos, estocástico, pavesas y retardo de ignición): tiempo de llegada idéntico.
- El caso La Aguada 2023 corrido por la capa estándar da 2782,98 ha y `hora_llegada_min.tif` idéntico en bytes (0
  celdas distintas en los cinco rásteres) a la corrida de V.4.

## 4. Efecto de las correcciones (Huygens, combustible homogéneo, 6 h) [MEDIDO]

| Escenario | v4.0 | V.4 | AC puro (sin Huygens) |
|---|---|---|---|
| Viento constante | 97,6 % de la solución exacta | 97,6 % | 56 % |
| Rotación de viento de 90° | 99,5 % | 116,6 % | — |
| Rampa de 5 a 30 km/h | 95,8 % | 98,3 % | — |
| Viento oscilante ±40° | 95,6 % | 167 % | — |
| Relieve serrano (pendiente media 17°) | 111–113 % | 140–155 % | — |

## 5. Corridas de verificación con los datos reales (`resultados/v4.0/verif2_*`) [MEDIDO]

| Corrida | Configuración | ha final | Fin | Ajuste a la referencia |
|---|---|---:|---|---|
| `verif2_aguada_v4original` | caso La Aguada 2023, `sim_v4_original`, 36 h | 2782,98 | horizonte | S 0,072 · J 0,037 (idéntico a V.4) |
| `verif2_aguada_v3_libre` | `modelo_v3`, barreras, 36 h | 1348,11 | horizonte | S 0,138 · J 0,074 |
| `verif2_aguada_v3_libre_sinbarreras` | variante `libre` | 2687,49 | horizonte | S 0,076 |
| `verif2_aguada_v3_contencion` | contención, despacho global | 420,39 | horizonte (parada suspendida por escapes) | contra MapBiomas S 0,181 · J 0,099 |
| `verif2_aguada_v3_l03` | L03 de V.4 | 3,96 | sin avance, 20 h | S 0,025 |
| `verif2_laslagunas72_libre` | SL-2024-LASLAGUNAS h1, 72 h | 64 800 | horizonte | IoU a 60 h 0,260 (49 760 contra 39 649 ha) |
| `verif2_laslagunas72_local` | + barreras y contención SNMF (ficha, arribo vial) | 36 299 | horizonte | IoU a 60 h 0,134; 146 km de línea, 78 escapes |
| `verif2_laslagunas72_v4original` | `sim_v4_original` | 66 590 | horizonte | IoU a 60 h 0,265 |
| `verif2_mitigacion_cortafuego` / `_sin_cortafuego` | Mesilla alt1, 36 h | 3604 / 4956 | horizonte | el cortafuego retrasa 6,5 h la llegada y reduce el área 27 % |
| `verif2_ensemble5_local6` | ensemble de 5, contención | media 1067 | — | la contención actúa en modo estocástico (225 celdas, 6,75 km) |

Lecturas:
1. Con el mismo combustible, las correcciones bajan el área libre de La Aguada de 2783 a 1348 ha y mejoran el
   ajuste (Sørensen 0,072 → 0,138). La sobreestimación de V.4 en su Fase 1 (|L| mediana 2,46) tenía una parte
   numérica y física (P1–P4) además de la falta de supresión.
2. La cicatriz de La Aguada (106 ha) es el resultado de un combate; solo las variantes con contención se acercan, y
   todavía con sesgo [CALIBRAR] (umbral de sostén 1700 kW/m, tasas SNMF).
3. Las Lagunas 2024: a 60 h el modelo libre alcanza 49 760 ha frente a 39 649 ha de la cicatriz final, que en la
   realidad se completó hacia el 25/09; la contención SNMF reduce el área 44 % a 72 h.

## 6. Limitaciones que quedan (no son errores de código)

- **Combustible por año** [HIPÓTESIS]: la regla 3.3 con el verano 2022 deja TU1 en el 34,5 % del dominio (6,7 % con el
  de 2024); Renca 2022 propaga 25–33 veces menos que en v3.0. Puede ser sequía real o diferencia entre las fuentes de
  los compuestos (`banco_v4/entradas/indices_extra` frente a `sim_v4/dinamicos`); hay que revisarlo.
- **Modo estocástico** (heredado de V.4): sin herencia de origen quema 3 a 8 veces más que el determinista; usar los
  ensembles solo como mapa relativo hasta revisarlo.
- **[CALIBRAR]**: humedad viva (a, b), curado, ajuste topográfico del viento, WAF bajo dosel, umbrales de contención y
  despacho. La calibración sigue el protocolo de evaluación (informe 16, Fase 2 con validación cruzada N−1).
- Inicialización del 10 h y 100 h (P10): sigue arrancando en equilibrio con la primera hora de la serie.

## 7. Pruebas automáticas

`test/v4.0`: 140 pruebas (≈110 s). Las de esta etapa están en `test_fisica_v4.py` (referencias GR2/SH2, EMC NFDRS 30 °C
/ 20 % = 4,158 %, viento a 20 ft, sin encendido instantáneo con rotación de 90°, camino paralelo al viento cruzado solo
por la cabeza, extinción reversible, retardo de ignición, pavesas invariantes al CFL, barreras por enlace con 16
vecinos y en diagonal, reproducción exacta de V.4) y en `test_fisica.py` / `test_simetria.py` adaptados.
