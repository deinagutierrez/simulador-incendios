# E-E3-2 — Revisión de la máscara de nubes (única, escrita antes de volver a medir)

Fecha: 2026-11-16 · Escribe LisandroV2002, con Claude · Rama `f7-entrega`.
Prerregistro: `E-E3-2_indices_aws.md`, sección "Si no se cumple": *"Se revisan la máscara de nubes y la escala, una sola vez
y dejándolo escrito, y se repite. Si sigue sin cumplirse, GEE pasa a ser obligatorio para los índices y se declara en la
guía de uso."*

Este archivo se registra en git **antes** de cambiar el código y antes de correr nada con la máscara nueva. El criterio y los
umbrales del prerregistro no cambian. Es la única revisión: si la segunda evaluación no se cumple, no hay otro ajuste.

## 1. De dónde se parte

Primera evaluación (2026-11-16, commit `d4118d8`, `E-E3-2_resultado_primera_evaluacion.md`): **no se cumple**. El criterio 1
se cumple; el 2 y el 3 fallan en v4.0 (11,943 % de celdas cambian de clase; IoU a 48 h 0,8946) y se cumplen en v3.1 librev2.

## 2. Qué se miró antes de elegir la revisión (declarado)

1. El diagnóstico `E-E3-2_diagnostico.md`: el cambio de clase sale del NDVI de los compuestos de verano por AWS; no hay
   sesgo (la escala no se toca); la diferencia es de cola.
2. El script que hizo los compuestos calibrados, `src/v4.0/app/preprocesamiento/descargar_ndvi_ndmi_gee.py`: máscara Cloud
   Score+ `cs_cdf >= 0,60`, **sin** descartar teselas por porcentaje de nubes.
3. Los compuestos de enero, febrero y marzo de 2024 por AWS, fecha por fecha, con las escenas que la primera evaluación dejó
   en caché, comparados con los mensuales de GEE:
   - el NDVI cambia rápido dentro del mes (febrero: 0,471 de media el día 1 y 0,555 el día 16), así que la mediana depende
     de qué fechas son válidas en cada celda;
   - a AWS le quedan pocas fechas válidas por celda: en febrero el 68 % del dominio tiene 2 o 3; en marzo el 78 % tiene 1 o 2;
   - con más fechas la diferencia con GEE baja (febrero: 0,0022 de diferencia absoluta mediana con 4 fechas, 0,0306 con 2);
   - el filtro de 80 % de nubes por tesela sacó 11 teselas del verano (2 en enero, 3 en febrero, 6 en marzo);
   - en las fechas parcialmente nubladas quedan valores bajos que la capa SCL no descarta (26 de febrero: el 29,5 % de las
     celdas con dato está 0,15 o más por debajo de la mediana de las otras fechas).

**Advertencia.** Los compuestos de GEE del verano 2024 que se miraron en el punto 3 son los mismos que usa la parte (c) de la
evaluación. La revisión se eligió leyendo el script de GEE y esas cifras, **no probando variantes**: no se calculó ningún
compuesto con la máscara revisada, ni entero ni parcial, antes de escribir este archivo. Aun así, quien elige la revisión
ya vio en qué difieren los dos productos; es un límite de esta revisión y queda dicho.

## 3. La revisión

Cloud Score+ no está disponible en AWS, así que no se puede usar la misma máscara. Los tres cambios acercan el método de
AWS al del script de GEE con lo que sí hay (la capa SCL):

| | Antes (versión 1.0) | Revisada (versión 1.1) | Motivo |
|---|---|---|---|
| Teselas con muchas nubes | se descarta la tesela entera si `eo:cloud_cover` > 80 % | **no se descarta ninguna tesela**; decide la máscara por píxel | el script de GEE no filtra teselas; así cada celda conserva más fechas |
| Clases SCL descartadas | 0 sin dato, 1 saturado, 3 sombra de nube, 8 nube media, 9 nube alta, 10 cirros, 11 nieve | las mismas **más 2 (área oscura) y 7 (sin clasificar)** | Cloud Score+ ≥ 0,60 es más estricto que SCL; las clases 2 y 7 son donde SCL deja sombras y bordes de nube sin marcar |
| Margen | ninguno | se descartan además las celdas cuyo centro está **a 100 m o menos** de una celda de sombra o nube (clases 3, 8, 9 y 10) | los bordes de nube y de sombra quedan fuera de la máscara SCL y bajan el NDVI |

Se aplica igual a los dos productos de AWS (el de ventana y el mensual). **No se toca**: la escala de reflectancia
(DN/10000, `E-E3-2_escala.md`), las fórmulas, el remuestreo, la lectura de las bandas de 10 m desde su nivel de 20 m, el
mosaico por fecha ni la mediana de las fechas. El margen se calcula en la grilla de salida de cada producto (20 m en el de
ventana, 30 m en el mensual), sobre la capa SCL ya llevada a esa grilla.

Los valores (clases 2 y 7; 100 m) se fijan acá y no se ajustan después de ver el resultado.

## 4. Qué se vuelve a medir y cómo

- `python herramientas/e_e3_2.py --evaluador LisandroV2002`, una sola vez, sobre un commit limpio, sin cambiar el guion.
  Se vuelven a medir las tres partes y los tres criterios, también en v3.1: la máscara cambia todos los productos de AWS.
- El resultado de la primera evaluación se conserva como `E-E3-2_resultado_primera_evaluacion.md` y
  `E-E3-2_resultados_primera_evaluacion.json`; el guion escribe el de la segunda en `E-E3-2_resultado.md` y
  `E-E3-2_resultados.json`.
- El guion informa "escenas en el catálogo (≤ 100 % de nubes por tesela)": es el texto que arma con el parámetro, que ahora
  vale 100.

## 5. Qué pasa después

- Si los tres criterios se cumplen en los dos motores: la vía AWS se habilita (`AWS_EN_PRUEBA = False`) y hay que rehacer
  con la máscara revisada los compuestos de verano 2026 que están en el repositorio.
- Si no: GEE pasa a ser obligatorio para los índices y se declara en la guía de uso, como dice el prerregistro. Cualquier
  otra salida (por ejemplo, habilitar AWS solo para v3.1) es un desvío que hay que decidir y declarar aparte.

## 6. Desvíos declarados

- **Quién revisa y quién evalúa**: la revisión la escribe y la evalúa la misma persona (LisandroV2002), sin la otra persona
  (D-E3-32). El plan pide que quien escribe no evalúe. Se compensa como en D-E3-13: criterio binario etiquetado antes,
  revisión escrita y registrada antes de medir, guion sin pasos manuales y repetible por cualquiera.
- **Expectativa de quien revisa, escrita antes de medir**: se espera que el cambio de clase de v4.0 baje pero quede por
  encima del 3 %, porque cambiando solo enero (el mes con mejor cobertura) ya da 3,5 % y la regla 3.3b es muy sensible
  (`E-E3-2_diagnostico.md` §5).
