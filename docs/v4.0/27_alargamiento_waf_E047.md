# Etapa 27: alargamiento con `factor_waf` (E047)

Fecha: 2026-10-29 · Bitácora: E047 · Prerregistro: `lote_E047/PRERREGISTRO.md`, aprobado antes de correr. El sha256 de `PRERREGISTRO.md`, `evaluar.py` y `prueba.py` no cambió entre el registro y la evaluación. Alcance: solo v4.0.

**Fuentes:**
- `lote_E047/evaluar.py`, `_puntajes_E047.csv` y `_validacion_cruzada_E047.csv`.
- Corridas: `resultados/prueba_E047/` (146, sin figuras). La base es E038.

## Corrida y control

146/146 ok, 0 fallos (08:22–08:50). El `factor_waf` leído en `metadata.json` coincide con cada configuración.

## Resultados

**J** (forma independiente de la ubicación + tiempo; menor es mejor):

| factor_waf | 1 (base) | 1,25 | 1,5 |
|---|---|---|---|
| J | 0,8368 | **0,7354** | 0,7739 |

**Alargamiento simulado frente al de la cicatriz** (mediana por evento):

| Evento | Cicatriz | WAF 1 | WAF 1,25 | WAF 1,5 |
|---|---|---|---|---|
| Chilcas | **4,21** | 1,64 | 1,70 | 1,78 |
| Mesilla | 3,44 | 2,35 | 2,79 | 3,13 |
| Aguada | 2,99 | 2,28 | 2,43 | 2,51 |
| Puertas | 2,78 | 2,06 | 2,08 | 2,07 |
| Piscuyacu | 1,77 | 1,53 | 1,79 | 2,21 |
| Las Lagunas | 1,61 | 1,09 | 1,11 | 1,13 |

**Validación cruzada (dejando un evento afuera):**
- La elegida es WAF 1,25 en 9 de 10 vueltas. Cuando sale Mesilla, gana WAF 1 y la diferencia queda en 0.
- Mejoran: Chilcas −0,32, Piscuyacu −0,14, Las Lagunas −0,11, Aguada −0,09, Rincón −0,01.
- Empeoran: Pampita +0,10, Renca +0,06, Puertas +0,05, Chacras +0,04.

**Criterio prerregistrado:**
- mejora en **5/10** (se exigían ≥ 6): ✗;
- mediana de la diferencia **−0,0046** (< 0): ✓;
- IoU mediana 0,163 → 0,167, no baja más de 0,01: ✓.

**Veredicto: NO SE ADOPTA.** `factor_waf` queda en 1.

## Lectura

1. (dato) **Falló por un evento.** La elección es estable (9/10) y J mejora un 12 %, pero el criterio fijado de antemano no se cumple. No se reinterpreta: aflojarlo ahora sería ajustar la regla después de ver el resultado.
2. (dato) **El WAF alarga poco la mayoría de las huellas.**
   - Mesilla se acerca a su cicatriz: 2,35 → 3,13 frente a 3,44.
   - **Chilcas** (1,64 → 1,78, frente a 4,21) y **Las Lagunas** (1,09 → 1,13, frente a 1,61) casi no se mueven.
   - (inferencia) Lo redondo de esos eventos no viene de que el modelo subestime el viento a media llama. Dos causas posibles, no verificadas:
     - el viento cambia de dirección durante el incendio (constancia 0,53–0,57; E046);
     - el límite de viento efectivo (Andrews 2013) recorta el efecto con vientos fuertes, que se declaró como posible antes de correr.
3. (dato) **Efectos secundarios:**
   - el tiempo de Puertas mejora (+10,6 → −2,2 h);
   - el de Las Lagunas empeora (+3,6 → +8,6 h a WAF 1,5);
   - el IoU casi no cambia.
4. **Límites:** eventos vistos, n = 10, pesos de la métrica supuestos.

## Próximo paso sugerido

- **Mantener WAF = 1.** Volver a probar 1,25 solo cuando haya eventos **no vistos**, con este mismo prerregistro. Es la forma limpia de saber si el 5/10 fue mala suerte.
- **La forma redonda de Chilcas y Las Lagunas** apunta a la variabilidad del viento o al límite de viento, no al WAF. Se puede diagnosticar con una corrida sin el límite (`limitar_viento: false`) en esos dos eventos, solo como diagnóstico, sin adoptar nada.
- **Lo que más pesa en el IoU sigue siendo la ubicación** (E046). El paso de mayor rendimiento esperado es la **ignición desde la primera detección VIIRS**: es un dato, no una calibración.
