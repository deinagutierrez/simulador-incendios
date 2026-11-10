# Etapa 28: diagnóstico de la forma redonda en Chilcas y Las Lagunas (E048)

Fecha: 2026-10-29 · Bitácora: E048 · Antecedente: docs/v4.0/27. **Solo diagnóstico: no se adopta nada.** Alcance: solo v4.0.

**Fuentes:**
- `lote_E048/diagnostico.py`, `medir.py` y `_diagnostico_E048.csv`.
- Corridas: `resultados/diagnostico_E048/` (54, sin figuras).
- Series de dirección fija: `lote_E048/meteo/`, copias de la meteo con la dirección constante. Los datos originales no se tocaron.

## Qué se probó

Sobre la base vigente (E038), en las 15 igniciones de Chilcas y las 3 de Las Lagunas:
- **L:** sin el límite de viento efectivo (`limitar_viento: false`).
- **D:** dirección del viento fija, igual a la media vectorial ponderada por velocidad de las primeras 72 h: Chilcas desde 357°, Las Lagunas desde 336°. La velocidad horaria es la real.
- **L + D:** las dos juntas.

Control: 54/54 ok; cada corrida tiene aplicada su palanca (`limitar_viento` y la ruta de meteo leídas en `metadata.json`).

## Resultados (medianas por evento)

| Evento | Configuración | Alargamiento (cicatriz / simulado) | Δeje | IoU | Δt (h) |
|---|---|---|---|---|---|
| Chilcas | base | 4,21 / 1,64 | 10° | 0,135 | +34,2 |
| Chilcas | L | 4,21 / 1,64 | 10° | 0,135 | +34,2 |
| Chilcas | D y L + D | 4,21 / **1,73** | 7° | 0,143 | +33,4 |
| Las Lagunas | base | 1,61 / 1,09 | 82° | 0,223 | +3,6 |
| Las Lagunas | L | 1,61 / 1,09 | 82° | 0,223 | +3,6 |
| Las Lagunas | D y L + D | 1,61 / 1,18 | 78° | **0,114** | −0,4 |

## Lectura

1. (dato) **El límite de viento no actúa:** L da exactamente lo mismo que la base. No es la causa.
2. (dato) **La variabilidad del viento tampoco.** Con 25–28 km/h desde el N todo el día, Chilcas apenas pasa de 1,64 a 1,73, frente a 4,21. En Las Lagunas, fijar la dirección baja el IoU a la mitad: la cicatriz se extiende hacia el NE, en contra del viento medio, que sopla hacia el SSE.
3. (dato) **Tampoco es el factor de viento bajo dosel de los TU** (0,3 fijo en `sb40.waf()`): sin dosel, la fórmula de profundidad daría 0,33 (TU1) y 0,36 (TU5), casi lo mismo. Hay una correlación moderada entre la fracción TU y el déficit de alargamiento (Spearman −0,44, n = 10), pero un ajuste de esa magnitud no la explicaría.
4. (inferencia) **La forma redonda es del propio modelo:** cómo arma la huella, no qué viento recibe. Quedan dos candidatos sin probar:
   - **`radio_huygens_m` = 300 m:** la elipse se re-ancla cada 300 m de recorrido. Con un radio chico, la huella es la unión de muchas elipses cortas, que tiende a redondearse. Es una de las correcciones de la verificación (informe 15).
   - **Pavesas apagadas** (`spotting.activo: false`) y **sin fuego de copas** en el motor. En la ola de calor de Chilcas (36 °C, HR 13 %), saltos de fuego por pavesas alargarían las corridas de cabeza.
5. En Las Lagunas además el eje está mal (82°): ahí el problema es la dirección del viento local, no solo la forma. Eso apunta a la meteorología (opción C del informe 26).

## Próximo paso sugerido

1. **Otro diagnóstico corto**, sobre las mismas 18 igniciones: `radio_huygens_m` 1.000 y 3.000 m, y pavesas activas con los valores por defecto. Solo para ver si alguno alarga Chilcas; unas 54 corridas, ≈ 10 min.
2. Si alguno alarga sin romper el tiempo, prerregistrarlo sobre los 10 eventos con la métrica de E047.
3. Las Lagunas: queda para la meteorología con más detalle.
