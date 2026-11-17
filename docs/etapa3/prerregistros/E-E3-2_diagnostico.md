# E-E3-2 — Diagnóstico del cambio de clase de combustible en v4.0

Fecha: 2026-11-16 · Hecho por LisandroV2002 (quien evaluó), con Claude · Rama `f7-entrega`, sobre el commit `878ef1b`.
Guion: `herramientas/e_e3_2_diagnostico.py` (solo lee; necesita `resultados/app/E-E3-2/c/verano_aws/`, que deja la evaluación).
Rótulos: **(dato)** medido con el guion · **(inferencia)** · **(sin verificar)**.

**Qué es y qué no es.** Es un análisis **posterior al veredicto**: se hizo después de ver que E-E3-2 no se cumple
(hoy `E-E3-2_resultado_primera_evaluacion.md`). No cambia el resultado, el criterio ni los umbrales, y no es parte de la evaluación. Sirve para
decidir qué hacer según la sección "Si no se cumple" del prerregistro. No se volvió a correr ningún motor: mide el cambio
de clase (criterio 2), no las huellas (criterio 3).

## 1. Resumen

- El 11,943 % de celdas que cambian de modelo SB40 en v4.0 sale **casi todo del NDVI de los compuestos de verano hechos
  por AWS** (11,6 %); el NDMI aporta 0,3 %. Febrero es el mes que más pesa.
- **No hay sesgo** entre AWS y GEE (diferencia mediana con signo 0,0000): revisar la escala de reflectancia no cambia nada.
- La diferencia es **de cola**: la mitad del dominio difiere en menos de 0,005 de NDVI; un cuarto difiere en 0,02 o más y
  aporta el 70 % de los cambios.
- **La regla 3.3b es muy sensible**: un tercio del dominio está a menos de 0,02 de un umbral que cambia la clase. Con
  ruido sin sesgo, una diferencia absoluta mediana de 0,0034 ya da 3,2 % de cambio. El criterio 1 (≤ 0,02) y el criterio 2
  (< 3 %) **no son compatibles entre sí para v4.0**: cumplir el 2 exige una diferencia unas seis veces menor que la que
  admite el 1.

## 2. Comprobación de que se mide lo mismo que la evaluación

(dato) El guion arma el SB40 de cada lado con las funciones de v4.0 (`simulador/fuel/generar_sb40.py`, sin tocar),
siguiendo `incendios_sl.eventos.preparar_combustible` con la regla 3.3b: cobertura MapBiomas 2023, MDT, mediana por celda
de enero a marzo de 2024 y corrimiento de las leñosas. Da **333.667 celdas distintas de 2.793.912 (11,943 %)**, lo mismo
que `E-E3-2_resultados_primera_evaluacion.json` (`partes.c.por_motor.v4.0.clases`).

**Nota del 2026-11-16, después de la segunda evaluación**: todas las cifras de este documento son de la **primera**
evaluación (máscara 1.0). Sus intermedios quedaron en `resultados/app/E-E3-2_primera_evaluacion/`; el guion lee
`resultados/app/E-E3-2/`, que ahora tiene los de la segunda (máscara 1.1), así que corrido hoy describe la segunda.

## 3. Qué entrada lo causa

(dato) Celdas que cambian de clase respecto del SB40 del lado GEE, cambiando una sola cosa por vez:

| Qué se toma de AWS | Cambian |
|---|---|
| Todo (lo evaluado) | 11,943 % |
| Solo el NDVI de verano | 11,617 % |
| Solo el NDMI de verano | 0,337 % |
| Solo el corrimiento de las leñosas (el resto, de GEE) | 1,706 % |
| Todo, pero con el corrimiento de las leñosas de GEE | 11,404 % |
| Solo enero | 3,496 % |
| Solo febrero | 6,683 % |
| Solo marzo | 3,754 % |

El umbral de humedad (NDMI > 0,15 pasa las herbáceas a GR6) explica 9.428 celdas, el 2,8 % de los cambios. El corrimiento
de las leñosas difiere poco entre lados (bosques abiertos −0,0548 con GEE y −0,0583 con AWS; arbustales abiertos −0,0374 y
−0,0388).

## 4. Cómo es la diferencia entre los compuestos

(dato) Diferencia AWS − GEE, sobre las 2.793.912 celdas (ninguna sin dato en ninguno de los dos):

| | NDVI: mediana con signo | NDVI: media | NDVI: abs. mediana | NDVI: percentil 95 | NDMI: abs. mediana | NDMI: percentil 95 |
|---|---|---|---|---|---|---|
| Enero | +0,0000 | +0,0002 | 0,0021 | 0,0560 | 0,0008 | 0,0334 |
| Febrero | +0,0000 | +0,0135 | 0,0098 | 0,0746 | 0,0065 | 0,0528 |
| Marzo | +0,0000 | −0,0052 | 0,0027 | 0,0887 | 0,0006 | 0,0451 |
| Mediana de verano (la que usa la regla) | +0,0000 | +0,0043 | 0,0058 | 0,0626 | 0,0029 | 0,0413 |

| Diferencia absoluta del NDVI de verano | Del dominio | De las celdas que cambiaron |
|---|---|---|
| menos de 0,005 | 48,1 % | 9,1 % |
| menos de 0,01 | 58,9 % | 14,8 % |
| menos de 0,02 | 73,9 % | 30,2 % |
| menos de 0,05 | 92,5 % | 71,0 % |

De las celdas con diferencia de 0,02 o más (26,1 % del dominio), el 31,9 % cambia de clase.

**Febrero** (dato): en el 12,6 % del dominio el NDVI difiere en 0,05 o más; ahí la diferencia media es +0,063 y AWS es
mayor en el 80 % de las celdas. Se concentra en el norte y el oeste: por franjas de norte a sur, 12,6 · 17,2 · 18,5 ·
12,8 · 16,9 · 14,2 · 10,2 · 10,2 · 7,6 · 6,3 %; de oeste a este, 13,5 · 17,4 · 19,5 · 21,1 · 15,0 · 10,6 · 7,6 · 8,5 ·
5,8 · 7,4 %. El compuesto de AWS de febrero usó 21 escenas en 6 fechas (1, 6, 11, 16, 21 y 26).

**(inferencia, sin verificar)** Una diferencia grande, de un solo signo y acotada a una zona es lo que deja una fecha con
nubes o sombras enmascaradas en un producto y no en el otro, o una fecha que entra en uno y no en el otro. No se pudo
determinar cuál de los dos compuestos de febrero es el afectado: el archivo de GEE del repositorio no trae procedencia con
sus fechas ni su máscara.

## 5. Por qué la regla lo amplifica

(dato)

- El 94,5 % del dominio está en coberturas cuya clase depende del tercil de NDVI. Los terciles medios son angostos:
  0,044 (arbustales cerrados), 0,047 (arbustales abiertos), 0,050 (bosques abiertos), 0,064 (bosques cerrados), 0,075
  (herbáceas), 0,104 (pasturas).
- A menos de 0,005 de un umbral que cambia la clase está el 8,2 % del dominio; a menos de 0,01, el 16,2 %; a menos de
  0,02, el 32,1 %. En esa última franja está el 68,4 % de las celdas que cambiaron.
- Las transiciones van parejas en los dos sentidos: GS2→TU1 32.525 celdas y TU1→GS2 30.743; TU5→GS2 29.002 y GS2→TU5
  28.054; GR2→GR4 19.924 y GR4→GR2 18.896. Coincide con que la superficie quemada casi no cambie (1,14 %) aunque las
  huellas se aparten.
- Por cobertura, lo que más aporta son los bosques abiertos (30,6 % del dominio, cambia el 15,0 %, 38,5 % de los cambios)
  y los arbustales abiertos (19,0 %, 14,1 %, 22,4 %).
- Ruido gaussiano sin sesgo sumado al NDVI de verano de GEE (semilla 0):

| Desvío | Diferencia absoluta mediana equivalente | Cambian de clase |
|---|---|---|
| 0,002 | 0,0013 | 1,31 % |
| 0,005 | 0,0034 | 3,24 % |
| 0,010 | 0,0067 | 6,44 % |
| 0,020 | 0,0135 | 12,65 % |

**Lectura**: para quedar por debajo del 3 % de cambio de clase en v4.0, dos compuestos de verano tienen que diferir en
menos de unos 0,003 de mediana absoluta y sin cola. El criterio 1 del prerregistro admite 0,02. Los compuestos de AWS
están en 0,0058, dentro del criterio 1, y con ruido gaussiano de ese tamaño darían cerca de 6 %; dan 11,9 % por la cola.

## 6. Qué implica para la decisión

El prerregistro dice: se revisan la máscara de nubes y la escala, una sola vez y dejándolo escrito, y se repite; si sigue
sin cumplirse, GEE pasa a ser obligatorio para los índices y se declara en la guía de uso.

- **Escala**: no hay nada que revisar (sin sesgo; §4).
- **Máscara de nubes**: puede achicar la cola, sobre todo la de febrero. **(inferencia)** Es poco probable que alcance: aun
  sin cola, haría falta bajar de 0,0058 a unos 0,003 de diferencia mediana.
- **GEE obligatorio para v4.0**: es la salida que el prerregistro prevé. Hoy los compuestos mensuales de verano por Earth
  Engine no están hechos (F4_informe §6, punto 11): habría que escribirlos.
- **Fuera del prerregistro**, y por lo tanto desvíos a declarar si se eligen: habilitar AWS solo para v3.1 (que cumple
  los tres criterios con holgura), o proponer otro criterio para v4.0 porque el 2 es más estricto que el 1 para la regla
  3.3b. Cualquiera de las dos la deciden las dos personas y va en `decisiones.md`.
- **A tener en cuenta**: el verano 2026 que está en el repositorio se hizo por AWS con este mismo método y es el que v4.0
  usa hoy para un evento nuevo.

## 7. Límites

- Un solo evento y un solo verano (2024), como la evaluación.
- No dice cuál de los dos productos está más cerca de la realidad: compara AWS contra GEE, no contra el terreno.
- No mide el efecto sobre las huellas: no se sabe cuánto subiría el IoU de 0,895 con cada variante.
- La prueba de ruido usa ruido independiente por celda; las diferencias reales están agrupadas en el espacio, así que la
  tabla de §5 orienta sobre el tamaño, no predice el resultado de una revisión.
- La causa de la diferencia de febrero queda sin verificar (§4).

## Cómo repetirlo

```
python herramientas/e_e3_2.py --evaluador NOMBRE      (deja resultados/app/E-E3-2/c/verano_aws/)
python herramientas/e_e3_2_diagnostico.py
```
