# Simulador v4.0: guía breve y adaptación a Google Drive / Colab

Proyecto: gemelo digital para la prevención y mitigación de incendios en la provincia de San Luis, Argentina.
Fecha: 2026-11-02 (actualizada el 2026-11-03: el panel vuelve a ofrecer combate, D53). Audiencia: quien use o mantenga el simulador. Versión corta; el detalle técnico está en `INFORME_TECNICO_MOTOR_V4.md`.

## 1. Qué es y cómo funciona

El simulador v4.0 calcula **cuándo llega el fuego a cada punto** de un mapa de 30 m.

1. Cada celda quemándose empuja el fuego hacia sus 8 vecinas.
2. La velocidad en cada dirección la da el modelo de Rothermel con los 40 tipos de combustible de Scott y Burgan.
3. Esa velocidad depende del **viento, la pendiente, la humedad del combustible y el tipo de vegetación**.
4. El fuego avanza en forma de elipse, más rápido a favor del viento.
5. Los caminos y las celdas sin combustible (agua, roca) frenan o frenan en parte el avance.
6. La corrida termina al cumplirse las horas pedidas, al quedar sin avance 12 h, o al igualar la superficie de la cicatriz observada.

Es **determinista**: con las mismas entradas da siempre el mismo resultado.

**Estado:** la física de superficie está verificada contra valores de referencia, pero la fidelidad frente a incendios reales solo se midió sobre los 10 eventos usados para desarrollarlo. No hay evidencia de capacidad predictiva sobre eventos nuevos. No incluye fuego de copas.

## 2. Qué entra

| Entrada | Qué es | Dónde |
|---|---|---|
| **Fuente de la corrida** | Una de tres: `evento` (incendio histórico), `caso` (caso de prueba de V.4) o `sim` (YAML nativo del motor) | campo `evento`, `caso` o `sim` del escenario |
| **Ignición** | Hora y punto de inicio. En un evento se elige una hipótesis de hora (`h0`, `h1`…) y un punto (`snmf`, `alt0`…) | `hipotesis`, `ignicion` |
| **Duración** | Horas a simular | `horas` |
| **Terreno** | Altura, pendiente y orientación | `datos/inputSimulacion/sim_v4/` |
| **Combustible** | Mapa de combustible antes del evento, armado con cobertura del suelo y NDVI/NDMI | se genera solo la primera vez |
| **Meteorología** | Serie horaria de viento, temperatura, humedad y lluvia, sin huecos | `datos/inputSimulacion/meteo/` |
| **Caminos** | Red vial y otras barreras | `datos/inputSimulacion/barreras/` |

Los 10 eventos disponibles: Chilcas, Pampita, Piscuyacu, Puertas, Renca, Aguada, Chacras, Rincón, Las Lagunas y Mesilla (fichas en `escenarios/v4.0/eventos/`). El dominio de simulación es Las Lagunas–Potrerillos.

**Un escenario** es un YAML corto en `escenarios/v4.0/corridas/`. Ejemplo:

```yaml
descripcion: Las Lagunas 2024, caminos como barrera
evento: SL-2024-LASLAGUNAS
hipotesis: h1
ignicion: snmf
horas: 72
variante: barreras
```

## 3. Qué se puede ajustar

Los valores por defecto son los vigentes y **no conviene cambiarlos sin una prueba**. Los ajustes probados (multiplicadores de velocidad, viento sobre el relieve, pavesas, otro combustible) no mejoraron el resultado de forma consistente.

| Ajuste | Opciones | Por defecto |
|---|---|---|
| **Los caminos frenan el fuego** (casilla; `variante` `barreras` o `libre`) | sí: los caminos y las celdas sin combustible frenan el avance · no: los caminos solo reducen la carga | sí |
| **Aplicar combate** (casilla) y **Tipo de combate** (selector) | no · sí, con tipo `pronostico` (como ante un incendio nuevo: cuartel más cercano, medios aéreos sorteados) o `local` (recursos reales de la ficha del SNMF; solo sirve para validar). Se escribe como `local_pronostico` / `local`; sin caminos y con combate, `libre` + `contencion: on` + `despacho` | no |
| **V4 original** (casilla de opciones avanzadas; `variante: v4_original`) | reproduce V.4 tal como se entregó; ignora las casillas anteriores | no |
| Viento (`viento`) | `serie`: uniforme, el de la estación · `windninja`: sobre el relieve, necesita archivo extra y cuesta +66 % de cómputo | `serie` |
| Combustible (`regla_combustible`) | `3.3b` (corrige años secos) · `3.3` (estándar de V.4) | `3.3b` |
| Terminar al igualar la cicatriz (`parar_en_cicatriz`) | sí / no. Sin tope el incendio simulado crece hasta el borde del dominio | sí, en evento y caso |
| Humedad del combustible muerto (`humedad.metodo_muerto`) | `retardo` · `ffmc_vanwagner` · `fija` | `retardo` |
| Multiplicador de velocidad (`k_global`, `k_grupo`) | número | 1 (sin cambio) |
| Factor de exposición al viento (`factor_waf`) | número | 1 |
| Pavesas (`spotting.activo`) | sí / no | no |
| Semilla (`semilla`) | entero | 42 |
| Ajuste fino (`ajustes`, `parche`) | cualquier parámetro del YAML del modelo | vacío |

El combate (`pronostico` y `local`) está en el panel desde el 2026-11-03 (D53), **sin validar con eventos no vistos**. Con `local` el resultado depende de los cuarteles y medios aéreos que declara la ficha del incendio real: sirve para comparar con lo que pasó, no para pronosticar. Los cortafuegos, el despacho con tasa fija (`contencion`, `ambas`) y la supresión L03 existen en el código pero **están fuera del panel y sin validar**.

## 4. Qué sale

Cada corrida crea una carpeta en `resultados/v4.0/<evento>/<corrida>/` con:

- `hora_llegada_min.tif`: el mapa principal, minutos desde la ignición hasta que llega el fuego.
- `intensidad_max_kw_m.tif`, `ros_max_m_min.tif`, `longitud_llama_max_m.tif`: intensidad, velocidad y llama máximas.
- `perimetros_horarios.geojson` y `mapa_hora_HH.png`: perímetro y mapa cada hora.
- `animacion.gif` y `isocronas_final.png`.
- `resumen_*.md` y `registro.json`: hectáreas quemadas, motivo de fin y tiempo de cómputo.
- `metricas.json`: comparación con la cicatriz observada (solo evento y caso).
- `visor.html`: visor interactivo.

Una corrida de prueba de 6 h pesa unos 17 MB. Un evento completo de 70 h, bastante más. En un equipo local una corrida tarda de 25 s a 3,5 min según el evento.

## 5. Cómo se usa hoy en Colab

`Simulador_Incendios_v4.ipynb`, en este orden:

1. **Celda 1 – Preparar:** monta Drive, localiza la carpeta `Incendios_SanLuis`, instala dependencias (2–3 min por sesión) y comprueba que estén los datos.
2. **Celda 2 – Simular:** panel con tres pasos (incendio y ignición; qué simular, con las casillas de caminos y de combate y el tipo de combate; nombre y ejecutar). Guarda el escenario, corre el motor y muestra el resumen y el visor.
3. **Celda 3 – Ver corridas anteriores.**
4. **Celda 4 – Respaldo en GitHub** (opcional).

**No se probó en Colab desde que se ajustó el modelo.** Todo lo que sigue sale de leer el cuaderno y el código, no de ejecutarlo en Colab.

## 6. Qué hay que cambiar para que funcione bien en Drive

El **motor no necesita cambios de física**. En el código y los YAML no hay rutas de Windows (solo un ejemplo de configuración de WindNinja y un comentario). Las rutas se resuelven desde la carpeta del proyecto (el cuaderno define `INCENDIOS_SL_REPO` e `INCENDIOS_SL_RAIZ`; el resto se deduce de ahí y puede cambiarse con variables `INCENDIOS_SL_*`). Lo que hay que adaptar es el cuaderno y el empaquetado.

### Aplicado en el cuaderno (2026-11-02)

Ya están hechos en `Simulador_Incendios_v4.ipynb` y `src/v4.0/requirements-colab.txt`:

- **Punto 1:** la celda 1 instala `requirements-colab.txt` (sin versiones fijas) si existe.
- **Punto 3:** el sha256 se verifica en la primera corrida de la sesión; las siguientes usan `--sin-sha`.
- **Punto 4:** casilla opcional *Copiar datos del motor al disco de Colab* (copia solo `sim_v4`, 271 MB). **Experimental y apagada por defecto.**
- **Punto 5:** aviso de la celda 1 y etiqueta del panel corregidos.
- **Puntos 6, 7, 8 y 10:** celda nueva **2b · Correr varios casos**: elegís escenarios, los corre de a uno, guarda cada corrida al terminar, salta las ya hechas y escribe un CSV resumen. Las figuras vienen apagadas.

**Qué se probó y qué no.** Se probó en un equipo local, con un Python limpio, que `requirements-colab.txt` instala y que la celda 2b corre `prueba_rapida_v4` (47,43 ha en 6 h, igual al valor vigente), escribe el CSV y la salta si se repite. **No se probó en Colab**: ni la instalación allí, ni la copia a disco local, ni los tiempos, ni la memoria.

### Panel con combate (2026-11-03, D53)

La celda 2 deja de ofrecer una lista de variantes. «Qué simular» son dos casillas (*Los caminos frenan el fuego*, *Aplicar combate*) y un selector (*Tipo de combate*, solo con combate). *V4 original* pasa a las opciones avanzadas. El cuaderno traduce las casillas a la `variante` del YAML; el motor y `escenario.py` no cambiaron.

| Caminos | Combate | Tipo | Se escribe |
|---|---|---|---|
| no | no | – | `libre` |
| sí | no | – | `barreras` |
| sí | sí | incendio nuevo | `local_pronostico` |
| sí | sí | recursos reales | `local` |
| no | sí | cualquiera | `libre` + `contencion: on` + `despacho` |

Ya no se ofrecen `contencion`, `ambas`, `l03` ni *Personalizado*. Un escenario guardado que use una de ellas se corre igual mientras no se cambien las casillas; si se cambian, se reemplaza.

**Qué se probó y qué no.** Probado fuera de Colab, con el código real de la celda 2 y `escenario.traducir`: las 6 combinaciones dan la configuración esperada (barreras, contención, despacho) y los 13 escenarios guardados (6 de `corridas/` y 7 de `_archivo_mitigacion/`) dan la misma configuración que antes. **No se corrió ninguna simulación y no se probó en Colab** (ni cómo se ve el panel allí). La combinación «sin caminos y con combate» no existía como variante y no tiene corridas previas; conviene probarla primero. El combate no está validado con eventos no vistos.

**Para subir a Drive** (misma ruta, reemplaza al existente): `Simulador_Incendios_v4.ipynb` y `docs/v4.0/GUIA_V4_Y_COLAB.md`.

### Imprescindible

| # | Problema | Cambio propuesto |
|---|---|---|
| 1 | **Dependencias fijadas para Python 3.14 en Windows** (`numpy==2.5.4`, `pandas==3.0.6`, `rasterio==1.5.2`…). La celda 1 las instala con `pip install -r`. Puede fallar o reemplazar paquetes de Colab y pedir reinicio. No verifiqué la versión de Python de Colab. | Crear `requirements-colab.txt` sin versiones fijas (o con mínimos) y probarlo en una sesión limpia. Dejar fuera `pytest`, `earthengine-api` y `tabulate`, que solo usa el banco de evaluación. |
| 2 | **Datos de v4.** La celda 1 solo descarga los datos viejos (1,4 GB, release `v1.0-artefacto`) y avisa si falta `sim_v4`, `banco_v4`, las barreras, el arribo o las fichas de eventos. En la copia de Drive del 31/10 esos datos **ya están** (`datos/inputSimulacion` es idéntico al local). | Nada que subir. Queda el aviso por si se arma una carpeta nueva; para eso haría falta un paquete único de datos (`datos/inputSimulacion/`, 882 MB), que no se armó. |
| 3 | **Se verifica el sha256 de todos los insumos en cada corrida**, leyéndolos desde Drive (el cuaderno nunca pasa `--sin-sha`). Con archivos grandes en Drive eso se paga cada vez. No medí cuánto. | Verificar el sha **una vez por sesión** y correr con `--sin-sha`, o poner la casilla en el panel. |
| 4 | **Lectura lenta desde Drive.** El motor lee muchos rásteres. Drive montado es más lento que el disco de Colab. No medido. | Al iniciar la sesión copiar `datos/inputSimulacion/` y `escenarios/` al disco local de Colab (`/content/`) y apuntar ahí las variables `INCENDIOS_SL_*`. Los resultados se copian a Drive al terminar cada corrida. |
| 5 | **Viento sobre el relieve (`windninja`).** Usa la biblioteca precalculada `viento_unitario_*.nc` (162 MB, ya en Drive), por lo que **funciona en Colab**. Lo que no funciona en Colab es generar una biblioteca nueva (el ejemplo de configuración apunta a un `.exe` de Windows). Cuesta +66 % de cómputo. | Dejar `serie` por defecto (ya lo es) y corregir el aviso de la celda 1, que decía que sin la biblioteca fallaban todas las corridas con `modelo_v3`. |

### Recomendable

| # | Problema | Cambio propuesto |
|---|---|---|
| 6 | **El panel corre una sola corrida por vez.** Para varios casos hay que repetirlo a mano. | Agregar una celda **«Correr varios casos»**: lista de escenarios (o evento × hipótesis × ignición), los corre uno tras otro con `correr_escenario.py --escenario`, y guarda una tabla resumen (`resumen_lote.csv`) con hectáreas, tiempo y métricas. |
| 7 | **Memoria de Colab (≈ 12 GB).** En local, con 5 corridas simultáneas murieron 2 (SIGKILL, causa no confirmada); con 2 procesos terminaron bien. | En Colab correr **de a una** (o de a dos como máximo). Mostrar un aviso si el evento es Las Lagunas (el más pesado). |
| 8 | **Sesiones que se cortan.** Una corrida larga se pierde si Colab desconecta. | Guardar cada corrida en cuanto termina (punto 4). En el lote, saltar las corridas que ya tienen `registro.json`. |
| 9 | **Instalación en cada sesión** (2–3 min). | Aceptable. Si molesta, instalar solo lo que falte, comprobando antes con `import`. |
| 10 | **Carpetas de resultados muy pesadas.** `resultados/v4.0` local suma 15 GB. | Casilla «guardar GIF y PNG» (apagada por defecto en lotes). Las figuras son lo que más pesa. |

### Orden sugerido

1. Puntos 1 y 2: sin ellos la celda 1 no deja el entorno usable.
2. Probar una corrida corta (6 h) en una sesión limpia de Colab y anotar el tiempo real.
3. Puntos 3, 4 y 5.
4. Punto 6 (el lote por casos) y el resto.

## 7. Qué no cubre esta guía

- Cómo se llegó a cada valor por defecto, ni los experimentos de calibración.
- El modo probabilístico (ensamble) y el banco de evaluación, que no están en el panel.
- La preparación de un evento nuevo (meteorología, cicatriz, índices con Earth Engine). Ver `FLUJO.md`.
