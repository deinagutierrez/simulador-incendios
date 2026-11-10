# Etapa 25: prueba de la regla de combustible 3.3c (pasturas → GR1), E045

Fecha: 2026-10-29 · Bitácora: E045 · Prerregistro: `lote_E045/PRERREGISTRO.md` (escrito y aprobado antes de correr) · Alcance: solo v4.0.

**Fuentes:**
- Evaluación: `lote_E045/evaluar.py` y `_puntajes_E045.csv`.
- Corridas: `resultados/prueba_E045/` (73, sin figuras). La base es E038, en `resultados/v4.0/`.

## Corrida

- 73/73 ok, 0 fallos (07:52–08:09).
- Control: cada corrida usó su combustible (`combustible_pre_evento_33b.tif` en la base y `…_33c.tif` en la prueba).

## Resultados (S_e: puntaje por evento; menor es mejor)

| Evento | S 3.3b | S 3.3c | Diferencia | Forma 3.3b → 3.3c | Δt mediano 3.3b → 3.3c (h) |
|---|---|---|---|---|---|
| Chilcas 2022 | 1,829 | 1,921 | +0,092 | 0,865 → 0,843 | +34,2 → +36,3 |
| Pampita 2022 | 0,601 | 0,719 | +0,118 | 0,601 → 0,719 | −2,6 → −1,1 |
| Piscuyacu 2022 | 0,765 | 0,762 | −0,003 | 0,619 → 0,621 | −18,3 → −16,7 |
| **Puertas 2022** | 0,834 | **1,816** | **+0,983** | 0,834 → 0,915 | **+10,6 → +33,6** |
| Renca 2022 | 0,940 | 0,950 | +0,010 | 0,914 → 0,903 | +3,5 → +12,0 |
| Aguada 2023 | 0,841 | 0,819 | −0,022 | 0,841 → 0,819 | — |
| Chacras 2023 | 1,187 | 1,173 | −0,014 | 0,761 → 0,758 | −34,5 → −33,3 |
| Rincón 2023 | 1,000 | 1,000 | 0 | 0,955 → 0,923 | +3,9 → +12,8 |
| **Las Lagunas 2024** | 0,777 | **1,021** | **+0,244** | 0,777 → 0,754 | **+3,6 → +18,6** (contra T80) |
| Mesilla 2024 | 1,244 | 1,198 | −0,046 | 0,875 → 0,847 | −24,4 → −22,9 |

**J:** 3.3b = 0,8906 · 3.3c = **1,0106** (peor).

**Criterio prerregistrado:**
- mejora en **4/10** (se exigían ≥ 6);
- mediana de la diferencia **+0,0048** (se exigía < 0).

**Veredicto: NO SE ADOPTA.** Queda 3.3b; 3.3c queda disponible solo por corrida.

## Lectura

1. (dato) **La forma mejora un poco, pero el tiempo empeora mucho.**
   - El término de forma baja en 6 de 10 eventos, entre −0,01 y −0,03 en IoU (Chilcas, Renca, Aguada, Rincón, Las Lagunas, Mesilla).
   - Al frenar las pasturas, los incendios tardan más en llegar a la superficie: Puertas +23 h, Las Lagunas +15 h, Rincón +9 h, Renca +8 h.
   - Pampita pierde forma: su IoU baja de 0,40 a 0,28.
2. (inferencia) **En el modelo, las pasturas funcionan como corredores rápidos.** Por ahí el fuego simulado llega antes a la superficie final. Quitarlos mejora algo dónde va el fuego, pero a costa de cuándo llega.
   - El 3.3b ya había corregido el atraso de 2022; volver a frenar abre ese atraso otra vez (Puertas).
3. (dato) La comisión en pastura bajó poco: por ejemplo, Renca 24,9 → 23,4 % y Rincón 12,3 → 7,1 %. Las pasturas explicaban una parte chica del error de forma, como anticipaba el informe 24.
4. **Límite:** eventos vistos y regla derivada de ellos (circular). Un resultado negativo en esas condiciones es una señal fuerte de que esta corrección no sirve tal como está.

## Conclusión sobre el combustible

Con estos 10 eventos, **la calibración del combustible queda cerrada**:
- **3.3b adoptada** (D46);
- **`k_grupo` por familia no adoptado** (D45);
- **pasturas a GR1 no adoptado** (D47).

El error que queda es sobre todo de **forma**: 1 − IoU ≈ 0,8, es decir, IoU 0,13–0,16. Ninguna perilla de combustible lo mueve más de unas centésimas.

**Próximo paso sugerido:** pasar a la forma.
- Comparar la dirección de avance simulada con la de la cicatriz (rumbo principal y elongación) por evento.
- Ver cuánto depende el IoU del punto de ignición, que en los `altN` está derivado de la cicatriz.
- Ver cuánto depende de que el viento sea una sola serie para todo el dominio.
