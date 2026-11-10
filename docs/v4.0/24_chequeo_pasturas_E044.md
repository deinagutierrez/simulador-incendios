# Etapa 24: ¿los pastos que el fuego evitó son pastizal natural o pastura? (E044)

Fecha: 2026-10-29 · Bitácora: E044 · Antecedente: docs/v4.0/21 (sección «qué limita esta evidencia»). Solo lectura; sin simulaciones nuevas.

**Fuentes:**
- `lote_E038/combustible_anillo_clases.py` y `_anillo_clases_E044.csv`.
- Cobertura `datos/inputSimulacion/cobertura/cobertura_mapbiomas_col3_<año>_las_lagunas_potrerillos.tif`, del año que usa cada combustible.
- Combustible 3.3b y cicatrices de referencia.
- Comisión: huellas finales de las 73 corridas de E038.

## Resultados (dato)

**1. ¿De qué clase son las celdas de pasto (GR)?** Fracción del total de celdas GR de cada zona, en 10 eventos:

| Clase MapBiomas | Anillo no quemado | Cicatriz |
|---|---|---|
| Pastizal natural (12) | 52 % | 82 % |
| **Pastura (15)** | **48 %** | **18 %** |

**2. Selectividad por clase** (fracción dentro / fracción en el anillo; mediana sobre eventos):

| Clase | Dentro / anillo | Eventos con < 1 |
|---|---|---|
| Arbustal abierto (77) | 1,25 | 3/10 |
| Bosque cerrado (3) | 1,24 | 4/10 |
| Bosque abierto (4) | 1,10 | 4/10 |
| Pastizal natural (12) | 0,72 | 7/10 |
| **Pastura (15)** | **0,10** | **10/10** |
| Mosaico arbustos-herbáceas (63) | 0,00 | 10/10 (0,2 % del área quemada) |

- En Mesilla (1,26), Renca (1,49) y Rincón (1,10) el pastizal natural se quemó más que su disponibilidad.
- Las tierras agropecuarias (15, 18, 19, 21, 36) son el 2–20 % del anillo y el 0–3,5 % de las cicatrices.

**3. ¿Cuánto quema el modelo en pasturas?**
- Del área que el modelo quema fuera de la cicatriz (comisión), la mediana en pastura es **7,8 %**: Renca 25 %, Las Lagunas 17 %, Rincón 12 %, Pampita 11 %.
- En pastizal natural es 10,5 %.

## Lectura

1. (inferencia) **El «rechazo» a los pastos del informe 21 viene sobre todo de las pasturas**, que son tierra manejada (pastoreo, potreros, riego). El fuego las evitó en los 10 eventos. El pastizal natural se evita poco, y en 3 eventos se eligió.
2. (dato) La tabla de combustible les da a las **pasturas los modelos de pasto más rápidos**: GR2, GR4 y GR7 según el tercil de NDVI. Al pastizal natural de baja altura le da GR1, GR2 y GR4. Es decir, el modelo trata como más inflamable justamente lo que el fuego evitó.
3. (inferencia) **Hay margen de mejora en la tabla, acotado y concentrado:**
   - una sola clase, las pasturas;
   - con justificación física: el pastoreo baja la carga y la continuidad del pasto;
   - el efecto debería verse sobre todo en la forma de Renca y Las Lagunas, donde el 17–25 % de la comisión cae en pasturas.
   - El techo es modesto: en la mediana de los eventos, la pastura explica menos del 8 % del área quemada de más.
4. **Lo que no conviene tocar:**
   - el pastizal natural: la señal es mixta;
   - los factores por familia: cerrados en D45.

## Propuesta (confianza media)

Una sola prueba, con prerregistro:
- **qué cambia:** las pasturas (clase 15) pasan a **GR1** en los tres terciles (pasto corto y escaso, como un potrero pastoreado), en lugar de GR2/GR4/GR7;
- **todo lo demás** igual a la configuración vigente: 3.3b, `barreras`, viento serie y tope en la cicatriz;
- **cómo se implementa:** como una regla nueva, `regla_combustible: "3.3c"` (3.3b + pasturas GR1), sin cambiar la regla vigente;
- **cómo se evalúa:** con la función objetivo y el criterio de E041 (asimétrico; validación cruzada dejando un evento afuera; mejora en ≥ 6/10 y mediana < 0). Como no hay parámetro libre, la validación cruzada se reduce a comparar evento por evento con la base.
- **costo:** 73 corridas, unos 15–20 min.

Si no pasa el criterio, el combustible queda cerrado y el trabajo pasa a la forma (ignición, dirección del frente, viento).
