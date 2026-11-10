# Etapa 20: combustible 3.3b con la configuración vigente (lote E038)

Fecha: 2026-10-28 · Bitácora: E038 · Antecedentes: docs/v4.0/17 (regla 3.3b), 18 (ablación E035) y 19 (lote E037).

**Fuentes:**
- Lote E038: `resultados/v4.0/<evento>/<…>-barreras-3.3b/`, con tablas en `resultados/v4.0/resumen_lote_E038.md/.csv` y la comparación en `lote_E038/_comparacion_E038.csv` (script `lote_E038/comparar.py`).

## 1. Qué se corrió y comparabilidad

- **Qué:** las mismas 73 igniciones de E037 (10 eventos, h0–h4 × puntos), con la misma configuración:
  - variante `barreras`;
  - viento `serie`, `escapes: potencial`;
  - tope en la cicatriz;
  - validación y figuras.
- **Único cambio:** `regla_combustible: 3.3b`. La caché `combustible_pre_evento_33b.tif` de Las Lagunas se generó antes de paralelizar; las otras 9 venían de E035.
- **Resultado de la corrida:** 73/73 ok, 0 fallos. `verificar.py` revisó 73/73 sin problemas. Duración: 12 min (10:33–10:45), 12 a la vez y después 3.
- **Ficha:** E037 y E038 coinciden en todo (instante, referencia, máscara, evaluador, igniciones, carga de la máquina) menos el combustible. La comparación es emparejada y válida para el **efecto de 3.3b**.
- **Límite:** son eventos vistos; los `altN` derivan de la cicatriz. Es orientativo, no decide §9.

## 2. Resultados (primero lo que no gusta)

**Lo que empeora** (dato):
- **Piscuyacu** pasa a ser rápido: Δt mediano −7,9 → −18,3 h.
- **Chacras** baja la forma: IoU 0,27 → 0,24.
- **Mesilla** baja la forma: IoU 0,13 → 0,12.
- **Las Lagunas** se vuelve algo lenta: t80 − T80 de −7/−6 h pasa a +4/+6 h, e IoU 0,235 → 0,223.
- La **sierra sigue rápida**: Chacras −34,5 h y Mesilla −24,4 h, casi sin cambio.

**Lo que mejora** (dato), sobre las 70 igniciones de los 9 menores:
- **IoU mediana:** 0,131 → 0,142. Mejor / igual / peor: 25 / 32 / 13.
- **|Δt| mediana:** 25,2 → 18,9 h. Mejor en 31 igniciones, peor en 10.
- **Alcanzan la cicatriz:** 64 → 68 de 70.
- **Horas simuladas:** 2.655 → 2.188 (−18 %).
- **Renca:** Δt +24,5 → +3,5 h.
- **Puertas:** pasa de 0/3 a 2/3 igniciones que alcanzan la cicatriz, con Δt +6,5 h e IoU 0,05 → 0,17.
- **Chilcas:** Δt +41,9 → +33,1 h.
- **Pampita:** IoU 0,21 → 0,40.
- **Frente al punto de partida E033** (51 igniciones h0–h2): IoU 0,131 → 0,131 y |Δt| 24,9 → 20,9 h. 3.3b compensa la demora que agregan las barreras y además mejora el tiempo.

**Lectura** (inferencia): 3.3b corrige lo que apuntaba el diagnóstico (TU1 de los veranos secos). Los eventos de 2022 lentos se acercan, sobre todo Renca y Puertas. Piscuyacu y Las Lagunas se mueven en la dirección esperada, pero pasan de largo o quedan algo lentos. El exceso de velocidad de la sierra no depende del combustible.

## 3. Decisión

**Decisión que hay que tomar:** si `regla_combustible: 3.3b` pasa a ser el valor por defecto de `modelo_v3`.

**Lo que no sabemos:**
- Si la mejora se sostiene en eventos no vistos.
- Por qué Piscuyacu se acelera tanto.
- Qué corrige la sierra.

**Opciones:**

| Opción | A favor | En contra | Costo |
|---|---|---|---|
| A. 3.3b por defecto en `modelo_v3` | mejora el tiempo en 31/41 igniciones con cambio y la forma en 25/38; −18 % de horas simuladas | eventos vistos; Piscuyacu y la forma en la sierra empeoran algo | bajo: una clave de `modelo_v3.yaml` |
| B. Dejar 3.3 y usar 3.3b solo por corrida | no toca el valor por defecto hasta la Fase 2 | la configuración por defecto queda con el sesgo conocido de 2022 | nulo |
| C. Pasar directo a la perilla de la sierra (`factor_waf`, `k_grupo` GR) sobre 3.3b | ataca el sesgo que queda (−24 a −35 h) | conviene fijar antes el combustible para no mezclar efectos | bajo |

**Recomendación**, con confianza **media**:
1. Adoptar **A**, documentada como provisoria hasta una validación con eventos no vistos.
2. Después, una ablación corta para la sierra (**C**): `factor_waf` 0,8 y 0,6, y `k_grupo` GR 0,8, cada uno por separado sobre E038, en unos 15–25 min por configuración.

**Qué la cambiaría:** que la perilla de la sierra interactúe con 3.3b y empeore los eventos de 2022, o que una validación fuera de muestra no repita la mejora.
