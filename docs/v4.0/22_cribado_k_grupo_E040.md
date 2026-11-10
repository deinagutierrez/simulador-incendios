# Etapa 22: cribado de la calibración del combustible por familia (E040)

Fecha: 2026-10-28 · Bitácora: E040 · Antecedente: docs/v4.0/21 · Alcance: solo v4.0.

**Fuentes:**
- Corridas: `resultados/cribado_E040/<evento>/<run_id>/` (219, sin figuras).
- Comparación: `lote_E040/_comparacion_E040.csv`, armada con `lote_E040/comparar.py`. La base es E038 (`lote_E038/_comparacion_E038.csv`).

## 1. Qué se corrió

Sobre la base de E038, con las mismas 73 igniciones, se cambió una sola familia por vez con `k_grupo`, que multiplica la velocidad de propagación de esa familia:
- pastos (GR) × 0,5;
- arbustos (SH) × 2;
- bosque o sotobosque (TU) × 2.

La base de E038 es combustible 3.3b, `barreras`, viento serie y tope en la cicatriz.

**Resultado de la corrida:**
- 219/219 ok, 0 fallos. El factor quedó aplicado en las 219 (`metadata.json → parametros.propagacion.k_grupo`).
- Duración: 24 min (10:52–11:17), 14 a la vez.

**Comparabilidad:**
- Es emparejada con E038: cambia solo `k_grupo` (y las figuras, que no afectan las métricas).
- Eventos vistos; n = 10. Es un cribado para elegir qué perillas entran en la calibración, no la calibración.

## 2. Resultados (base E038: IoU mediana 0,142 · |Δt| mediana 18,9 h · 68/70 alcanzan la cicatriz)

| Configuración | IoU mediana (mejor / igual / peor) | \|Δt\| mediana (mejor / peor) | Alcanzan | Las Lagunas: t80 − T80 · IoU |
|---|---|---|---|---|
| GR × 0,5 | 0,153 (23 / 33 / 14) | **20,1 h** (17 / 27) | 68 | **+15 a +20 h** · 0,21–0,23 |
| SH × 2 | 0,154 (**31** / 28 / 11) | 18,6 h (21 / 24) | 70 | −5 a −3 h · 0,23 |
| TU × 2 | 0,154 (29 / 24 / 17) | **15,4 h** (25 / 25) | 70 | −8 a −5 h · **0,26** |

Base: Las Lagunas t80 − T80 = +4 a +6 h, IoU 0,22.

**Δt mediano por evento (h):**

| Evento | Base E038 | GR × 0,5 | SH × 2 | TU × 2 |
|---|---|---|---|---|
| Chilcas 2022 | +33,1 | +34,8 | +29,0 | **+15,4** |
| Pampita 2022 | −2,6 | +0,2 | −6,1 | −2,7 |
| Piscuyacu 2022 | −18,3 | −16,6 | −24,2 | **−29,3** |
| Puertas 2022 | +6,5 | **+25,4** | −1,9 | **−20,8** |
| Renca 2022 | +3,5 | +10,2 | −6,0 | −8,9 |
| Chacras 2023 | −34,5 | −30,6 | −35,9 | −39,1 |
| Rincón 2023 | +3,9 | +6,1 | +3,4 | +2,8 |
| Mesilla 2024 | −24,4 | −21,9 | −26,0 | −27,3 |

Lo que no gusta primero (dato):
- **Bajar los pastos casi no frena la sierra:** Chacras −34,5 → −30,6 h y Mesilla −24,4 → −21,9 h. En cambio, retrasa bastante los demás: Puertas +6,5 → +25,4, Renca +3,5 → +10,2 y Las Lagunas +4 → +16 h. Baja el IoU de Pampita (0,40 → 0,22) y de Mesilla (0,125 → 0,098).
- **Subir el bosque acelera de más a Piscuyacu y Puertas** (−29 y −21 h), y también a la sierra.
- **Ninguna configuración corrige la sierra** (Chacras, Mesilla).

Lo que mejora (dato):
- **TU × 2** da el menor error de tiempo (15,4 h). Corrige Chilcas (+33 → +15 h) y da la mejor forma en Las Lagunas (IoU 0,22 → 0,26).
- **SH × 2** da la mejor relación forma/tiempo: IoU mejor en 31 igniciones y peor en 11; |Δt| parejo. Lleva Puertas a −1,9 h y Las Lagunas a −4 h.

## 3. Lectura

1. (inferencia) La selectividad del informe 21 se confirma a medias. **Arbustos y bosque sí estaban lentos**: subirlos mejora la forma en la mayoría de las igniciones y ordena el tiempo de los eventos leñosos. **Los pastos no son la causa del exceso de velocidad de la sierra**: Chacras tiene solo 11 % de pasto. El rechazo a los pastos del informe 21 debe ser, en buena parte, manejo del suelo.
2. (inferencia) Lo que queda rápido en la sierra no depende de la familia de combustible. Hay tres candidatos, que no se probaron:
   - el ajuste de viento a media llama (WAF) o el límite de viento;
   - la pendiente;
   - **referencias de tiempo débiles**: Chacras tiene 3 focos en el banco frente a 31 en la ficha, y Mesilla usa la contención SNMF como Tref. Antes de calibrar contra esos dos eventos hay que revisar su referencia.
3. (dato) Las respuestas son de signo opuesto entre eventos, porque un mismo factor acelera a todos. Hace falta una calibración conjunta con validación cruzada, no elegir el factor que mejor queda en un evento.

## 4. Recomendación (confianza media)

1. **Calibrar SH y TU juntos.** GR queda fijo en 1.
   - Grilla SH {1; 1,5; 2} × TU {1; 1,5; 2}: 9 configuraciones × 73 = 657 corridas, unos 75 min sin figuras.
   - **Validación cruzada dejando un evento afuera.**
   - La función objetivo se fija **antes** de correr, por ejemplo la mediana sobre eventos de |ΔT| (en Las Lagunas, contra T80) normalizada, más (1 − IoU).
   - 2 parámetros libres con 10 eventos, dentro del límite de 3 del protocolo §9.
2. **Antes, revisar las referencias de tiempo de Chacras y Mesilla:** comparar la cota de la ficha con el Tref del banco. Si están mal, la sierra puede no estar tan rápida.
3. **Para la sierra, después de 1 y 2:** un cribado de `factor_waf` (0,8 y 0,6) sobre la mejor combinación de SH y TU.
4. GR × 0,5 queda descartado como palanca.
