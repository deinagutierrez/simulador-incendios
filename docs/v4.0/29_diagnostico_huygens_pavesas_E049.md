# Etapa 29: radio de Huygens y pavesas (diagnóstico E049)

Fecha: 2026-10-29 · Bitácora: E049 · Antecedente: docs/v4.0/28. **Solo diagnóstico: no se adopta nada.** Alcance: solo v4.0.

**Fuentes:**
- `lote_E049/diagnostico.py`, `medir.py` y `_diagnostico_E049.csv`.
- Corridas: `resultados/diagnostico_E049/` (54, sin figuras).

## Qué se probó

Sobre la base vigente (E038), en las 15 igniciones de Chilcas y las 3 de Las Lagunas:
- **H1000 y H3000:** `radio_huygens_m` 1.000 y 3.000 m (base 300).
- **SP:** pavesas activas (`spotting.activo: true`, valores por defecto: intensidad de referencia 3.000 kW/m, p_max 0,05, distancia mediana 150 m).

Control: 54/54 ok; radio y pavesas leídos en `metadata.json` iguales a lo pedido. En SP, mediana de 404 saltos por corrida.

## Resultados (medianas)

| Evento | Configuración | Alargamiento (cicatriz / simulado) | Δeje | IoU | Δt (h) |
|---|---|---|---|---|---|
| Chilcas | base | 4,21 / 1,64 | 10° | 0,135 | +34,2 |
| Chilcas | H1000 / H3000 | 4,21 / 1,64 | 4° | 0,135 | +34,2 |
| Chilcas | **SP** | 4,21 / **2,95** | 6° | 0,095 | **+4,1** |
| Las Lagunas | base | 1,61 / 1,09 | 82° | 0,223 | +3,6 |
| Las Lagunas | H1000 / H3000 | 1,61 / 1,09 | 85° | 0,223 | +3,6 |
| Las Lagunas | **SP** | 1,61 / 1,09 | **34°** | 0,137 | **−34,4** |

## Lectura

1. (dato) **El radio de Huygens no influye:** alargamiento, IoU y tiempo son iguales a la base. Queda descartado.
2. (dato) **Las pavesas son una palanca fuerte:**
   - En Chilcas alargan mucho la huella (1,64 → 2,95) y corrigen casi todo el atraso (+34 → +4 h).
   - En Las Lagunas acercan el eje (82° → 34°), pero la adelantan 34 h.
   - En los dos eventos baja el IoU (0,135 → 0,095 y 0,223 → 0,137): la huella se estira, pero no necesariamente hacia donde estuvo la cicatriz.
3. (inferencia) **Lo redondo de Chilcas se explica en buena parte por la falta de transporte de fuego a distancia** en un día extremo (ola de calor). Con los valores por defecto, en cambio, las pavesas aceleran de más en otros eventos.
4. **Límites:**
   - 2 eventos;
   - las pavesas son estocásticas: los resultados dependen de la semilla, y aquí se usó una sola, la del modelo;
   - los valores de las pavesas son los de V.4, sin calibrar.

## Próximo paso sugerido

Prerregistrar las pavesas sobre los 10 eventos con la métrica de E047 (forma independiente de la ubicación + tiempo asimétrico) y la salvaguarda de IoU:
- **Perilla:** `spotting.p_max` ∈ {0 (apagado, base); 0,01; 0,05}, o el umbral `intensidad_ref_kw_m`. Un solo parámetro libre.
- **Varias semillas por corrida** (3, por ejemplo), para que el resultado no dependa de una en particular.
- **Validación cruzada** dejando un evento afuera y el mismo criterio de adopción.
