# Etapa 17 — Viento WindNinja en SIM, combustible de años secos y Fase 2 (calibración, pausada)

> **Actualización E036 (2026-10-28, D41):** `modelo_v3` pasó a viento `serie` por defecto. En la ablación E035 (docs/v4.0/18), WindNinja costó +66 % de cómputo sin cambiar IoU ni tiempos en los 9 eventos menores. Sigue disponible con `viento: windninja`. La Fase 2 sigue pausada; las condiciones propuestas para retomarla están en docs/v4.0/18 §5 (sin decidir).

Fecha: 2026-10-26. Estado: **viento WindNinja implementado y activo en `modelo_v3`**; regla de combustible 3.3b
implementada (opcional); **calibración de la Fase 2 pausada** (§4: dónde seguir).
Etiquetas: **[BIBLIO]** · **[MEDIDO]** · **[HIPÓTESIS]** · **[CALIBRAR]**.

## 1. Viento sobre el relieve (WindNinja)

**Motivo.** La mayor diferencia de algoritmo entre v3.0 y v4.0 era el viento: v3.0 usa un campo WindNinja por celda
(velocidad y dirección corregidas por el relieve) y SIM usaba una serie uniforme con un factor topográfico simple que
solo corrige la velocidad (informe 14).

**Implementación** (`src/v4.0/src/simulador/physics/viento.py`):
- `ParametrosViento.fuente`: `serie` (V.4) | `windninja`. `biblioteca`: ruta al `.nc` (por defecto la del dominio en
  `datos/inputSimulacion/viento/viento_unitario_las_lagunas_potrerillos_100m_brush_*.nc`, la misma de v3.0).
- `BibliotecaWindNinja` lee los campos unitarios (U este, V norte por m/s de entrada a 10 m; 72 direcciones cada 5°;
  100 m; conservación de masa, vegetación *brush*) con el controlador netCDF de GDAL (sin xarray ni netCDF4), bajo
  demanda por dirección.
- En cada sub-paso: U,V = velocidad₁₀ₘ · campo unitario de la dirección, interpolado entre las dos direcciones vecinas
  (igual que `BibliotecaViento.campo` de v3.0, solución lineal en la velocidad [BIBLIO, docs/v3.0/03]) y muestreado
  bilinealmente **solo en las celdas activas** (sin remuestrear la grilla entera). Da velocidad **y dirección** por celda;
  el factor topográfico simple no se aplica. Fuera de la biblioteca: serie uniforme.
- **Corrección de lectura** [MEDIDO]: GDAL entrega las variables de ese NetCDF de abajo hacia arriba; se invierten las
  filas. Verificación: correlación velocidad–relieve relativo +0,67 a +0,74 con las filas corregidas, ≈ 0 sin
  corregir (`test_viento_windninja.py::test_orientacion_contra_el_relieve`).
- `modelo_v3.yaml`: `viento.fuente: windninja`. `sim_v4_original.yaml` sigue con la serie (V.4 bit a bit, verificado).
- Corrida estándar: atajo `viento: windninja | serie`; en el cuaderno, selector **Viento**.

**Efecto medido** [MEDIDO]:

| Corrida | Viento | ha final | Cambio |
|---|---|---:|---|
| Las Lagunas 2024 h1, libre, 48 h (`comparar_viento_*_laslagunas_2024`) | serie | 29.289 | — |
|  | windninja | 29.292 | huellas con IoU 0,977 entre sí; 2,3 % de la huella cambia de lugar; llegada −66 a +71 min (p5–p95) |
| Caso La Aguada 2023, modelo_v3, 36 h | serie (`verif2_aguada_v3_libre`) | 1.348 | IoU contra la cicatriz 0,074 |
|  | windninja (`caso_aguada_2023_20261026-1357`) | 1.400 | IoU 0,071 |

Lectura: en este dominio el campo de WindNinja modifica la velocidad entre ×0,90 y ×1,08 (p5–p95) y la dirección en
±3°, con extremos de ×0,64–1,26 en crestas y valles: una amplitud media parecida a la del factor simple de V.4 (acotado
a ×0,7–1,3). Cambia **dónde y cuándo** llega el fuego (ritmo en laderas, desvíos locales), no la superficie total.
Mejoras posibles con más fidelidad [HIPÓTESIS]: biblioteca con el solver de momento o vientos diurnos (pendiente-valle),
que WindNinja 4 ofrece y v3.0 no usó; requiere regenerar la biblioteca con WindNinja (≈ 45 min por dominio, otra máquina).

## 2. Combustible de los años secos (regla 3.3b)

**Diagnóstico** [MEDIDO] (píxeles con la misma cobertura 2021–2023):

| Verano | NDVI mediano bosque / arbustal abierto | Bosque bajo el tercil bajo (TU1) | TU1 en el dominio |
|---|---|---:|---:|
| 2022 | 0,49 / 0,36 | 69 % | 34,5 % |
| 2023 | 0,59 / 0,44 | 22 % | 11,8 % |
| 2024 | 0,62 / 0,47 | 15 % | 6,7 % |

En invierno, la cadena independiente de v3.0 da NDVI parejos entre años (bosque 0,33 en 2022, 0,30–0,32 en 2024): no es
un sesgo de la fuente, es la **sequía del verano 2021/22** (también el NDMI baja). La regla 3.3 usa el NDVI de un solo
verano como proxy de estructura con terciles fijos, y entonces un año seco *reduce* la carga leñosa (más TU1).

**Regla 3.3b** (`simulador.fuel.generar_sb40.ndvi_estructural_anomalia`): en las clases leñosas (3, 4, 6, 9, 66, 77) el
NDVI estructural se recentra en la mediana de referencia de cada clase implícita en sus terciles, (p33 + p67)/2; las
herbáceas conservan el NDVI del año (la carga de pasto sí responde a la sequía). Resultado: TU5 ≈ 22 % y TU1 ≈ 16 % en
2022, 2023 y 2024. Se elige con `regla_combustible: 3.3b` (corrida), en el cuaderno (**Combustible**) o en el banco
(`sim_adaptador.preparar(regla_combustible=…)`). **No es el valor por defecto**: lo decide la Fase 2.

## 3. Fase 2 del protocolo — diseño (informe 16, §3.4 y §9)

- **Candidato M1-C**: SIM v4.0 `modelo_v3` + contención de v3.0 en modo **pronóstico** (sin la ficha: arribo vial desde
  el cuartel más cercano, despacho SNMF por región, medios aéreos sorteados) + parada SNMF de §4.3.
- **10 eventos elegibles** (8 ex-prueba de la Fase 1 + 2024 + SM01; Renca y Puertas no cumplen §3.2). SM01 no tiene
  el compuesto del mes previo (julio de 2023) en este equipo: se usa el del mes del evento, declarado en la procedencia.
- **3 parámetros libres** (máximo de §9 con 10 eventos): regla de combustible {3.3, 3.3b} × umbral de sostén I_s
  {800, 1700, 3500} kW/m (aéreo = max(3500, I_s)) × κ del despacho {1, 3, 10}; más las dos bases sin contención
  (20 configuraciones × 10 eventos = 200 corridas). Valores de v3.0: I_s 1700, κ 10.
- Función objetivo de §9; validación cruzada N−1; Skill_F contra B1; criterios de aceptación de §9.
- Código: `src/v4.0/app/banco/fase2.py` (`preparar`, `correr`, `analizar`); insumos en
  `datos/procesados/v4.0/banco_fase2/<evento>/<regla>/`; corridas en `resultados/v4.0/banco/fase2/corridas/`.

## 4. Estado y dónde seguir

**Pausada el 2026-10-26** (a pedido; antes, un apagado del equipo cortó la corrida). Resultados parciales, **con el
viento uniforme anterior** (no comparables con el modelo actual), guardados en
`resultados/v4.0/banco/fase2/corridas_pausa_viento_serie_20261026/` (14 completas + 6 incompletas):

| Evento | Configuración | IoU_eq | L(T80) | Δt (h) |
|---|---|---:|---:|---:|
| 2024 (41914) | 3.3 libre | 0,244 | 0,234 | −9,7 |
| 2024 | 3.3 con contención (9 combinaciones) | 0,233–0,246 | 0,189–0,225 | −7,4 a −9,4 |
| 2024 | **3.3b libre** | 0,242 | **0,022** | −1,2 |
| 2024 | 3.3b I_s 800, κ 1 | 0,241 | 0,020 | −1,1 |
| 2022 (43644) | 3.3 libre | 0,173 | 0,931 | −5,8 |
| 2022 | 3.3b I_s 1700, κ 3 | 0,260 | 1,418 | −7,7 |

Lectura preliminar [HIPÓTESIS]: en el evento grande la contención casi no actúa (la intensidad supera los umbrales) y la
regla 3.3b deja el área en T80 casi igual a la observada; en 43644 la 3.3b mejora la forma pero agranda el área. Hace
falta la grilla completa para decidir.

**Para reanudar** (desde `src/v4.0`, con el viento WindNinja):
```bash
python -I app/banco/fase2.py preparar        # rehace el contexto con el modelo vigente (minutos); obligatorio tras cambiar el viento
python -I app/banco/fase2.py correr --procesos 6     # 200 corridas; saltea las terminadas; ≈ 6 h en un equipo de 8 núcleos
python -I app/banco/fase2.py analizar        # validación cruzada N−1 → resultados_fase2.json, bitácora, por evento
```
- `correr` se niega a usar un contexto preparado con otro viento que el de `modelo_v3` (evita mezclar modelos).
- Costo: el evento 2024 tarda ≈ 2,3 h por corrida (249 h simuladas); los otros 9, ≈ 5 min. Si se corta, se vuelve a
  lanzar `correr`: solo se pierden las corridas en curso.
- Versión reducida (≈ 2–3 h): `--configs r33_libre,r33b_libre,r33_I1700_k10,r33b_I1700_k10` (bases + valores de v3.0).
- En Colab (2 núcleos) la grilla completa tarda días: correrla en un equipo local y subir `resultados/v4.0/banco/fase2/`.

**Comparar desde Colab** (cuaderno v4, celda 2):
- Viento: `comparar_viento_windninja_laslagunas_2024` contra `comparar_viento_serie_laslagunas_2024`.
- Calibración: `calibracion_comparar_ejemplo` (plantilla con `ajustes.contencion.intensidad_sostener_kw_m`,
  `snmf.kappa`, `regla_combustible` y `viento`); guardarla con otro nombre por cada combinación y comparar los
  `resumen_*.md` y `metricas.json` de `resultados/v4.0/`.
- Cuando la Fase 2 termine: copiar los valores elegidos a `escenarios/v4.0/modelos/modelo_v3.yaml` (o a un
  `modelo_v3_fase2.yaml` nuevo, para conservar el anterior) y volver a correr las corridas de comparación.

## 5. Otros cambios de esta etapa

- Escritura atómica de la caché de insumos por evento (`incendios_sl/eventos.py`): dos corridas simultáneas del mismo
  evento corrompían `combustible_pre_evento.tif` [MEDIDO].
- Adaptador del banco: `regla_combustible`, carpeta de insumos propia, parada SNMF sin L03 e índices de respaldo;
  evaluación separada en `evaluar_corrida` (sin cambio de resultados; la regla 3.3 reproduce byte a byte el combustible
  de V.4).
- Pruebas: `test_viento_windninja.py` (4) y `test_fase2.py` (3); suite completa en verde.
