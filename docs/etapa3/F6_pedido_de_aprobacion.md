# F6 — Verificación: pedido de aprobación

Para leer antes de empezar la fase F6. Alcanza con contestar "apruebo todo" o con los números que se quieren distintos. Los
marcados **bloquea** hay que resolverlos antes de escribir código.

Estado del que se parte: rama `f6-verificacion`, creada desde `f5-intervenciones` (F4 y F5 terminadas; E-E3-2 y E-E3-4 con
guion listo, pendientes del evaluador). `main` sigue en la F3.

## 1. Qué pide el plan para F6

Pruebas automáticas; los prerregistros E-E3-1 a E-E3-4 evaluados; **modo histórico** (un evento con su meteorología real,
cicatriz, focos y las métricas de v3.1); informe `01_verificacion.md` con la ficha de comparabilidad (Anexo A). Criterio: todos
los prerregistros evaluados e informados, se cumplan o no, y el modo histórico muestra las cifras de Las Chacras octubre 2023.
Esfuerzo del plan: 6 días.

## 2. Qué se averiguó (2026-11-14, dos lecturas en paralelo, sin tocar el repositorio)

| Qué | Resultado |
|---|---|
| Integración continua | corre solo en `push` a `main` y en pull requests. **El código de F4 y F5 nunca pasó por Windows**; la última corrida (F3, en `main`) dio verde en Windows y Linux |
| Riesgos probables en Windows del código nuevo | (1) la huella parcial se reemplaza con `os.replace` mientras el servidor la puede estar leyendo: en Windows eso da error y cortaría la corrida, de forma intermitente; (2) en `indices.py`, borrar y renombrar una carpeta con un archivo abierto falla |
| Pruebas automáticas | 178 en `test/app` (unos 5 min acá). Huecos: ninguna prueba automática de la pantalla; la caída de un motor real no se prueba (solo con el simulado). La línea base del plan §6.1 (69 y 130/12) se midió con resultados locales: en un clon limpio son 68 + 1 omitida (v3.1) y 129 + 13 omitidas (v4.0) |
| Entre computadoras | E-E3-1 en Linux (acá) y en Windows (desarrollo) da las mismas celdas, ha y motivo de fin en los siete pares. No prueba igualdad bit a bit: el guion no guarda el sha256 de los rásteres. La corrida de Linux se hizo con código sin registrar: no vale como registro formal |
| E-E3-3 (rendimiento) | sin guion ni nombres. Su meta de v4.0 ("≤ 3 s por hora con unas 30.000 ha") **no se puede evaluar con su diseño**: ningún escenario de E-E3-1 pasa de 12.839 ha con v4.0. Linux da 0,90 s/h en v4.0 Las Lagunas contra 1,77 en el Windows de desarrollo; la memoria se mide distinto en cada sistema |
| Métricas del modo histórico | el código de v3.1 (`validation/metricas.py`, a través de `scripts/evaluar_x49.py`) se aplica a las salidas del simulador, de v3.1 y de v4.0, sin tocar nada: 0,6 s por corrida. Tiene que correr en un proceso aparte (paquete con el mismo nombre que v4.0). `resumen.metricas_evento` de v4.0 calcula otra cosa: no sirve para "con el código de v3.1" |
| Cifras de Las Chacras octubre 2023 (`docs/v4.0/31` §7.2) | las filas de **v3.1 libre y librev2 (alt4) se reproducen exactas** con las corridas del simulador (IoU a igual superficie, horas, fracción a tiempo, puntaje). La fila de v4.0 es **variante libre, sin parada, 141 h**; con la configuración del simulador (barreras, 72 h) da otra cosa (puntaje 0,39 contra 0,374) |
| Eventos disponibles para el modo histórico | **solo 2 de 15** tienen todos sus datos en el clon (Las Lagunas 2024 y Las Chacras octubre 2023). Los otros 13 dependen de la publicación de datos históricos, que todavía no existe; a 8 de ellos les faltan además los compuestos de verano 2021–2022 para v4.0 |
| Ignición recomendada | está en las fichas de **v3.1** (`recomendada: {ignicion, hipotesis}`). Las fichas de v3.1 y v4.0 difieren en 10 de 15 eventos (el servidor dice que son iguales: es falso). Las Lagunas recomienda `alt0`, que no existe en la ficha de v4.0 |
| Las Chacras octubre 2023 | es un evento **no visto** (X-49): se puede mostrar, no usar para ajustar |
| Plan §6.4 | "0,45–0,46 contra 0,25–0,37" son **puntajes** ((IoU + fracción a tiempo)/2), no IoU |

## 3. Quién y cómo

| N.º | Propuesta | |
|---|---|---|
| 1 | La F6 la hace el frente A (el usuario, con Claude); la evaluación de los prerregistros sigue cruzada | |
| 2 | **E-E3-3: escribe deinagutierrez, evalúa LisandroV2002**, como E-E3-2 y E-E3-4 | **bloquea** |
| 3 | La otra persona corre en su máquina los guiones de E-E3-2, E-E3-3 y E-E3-4 y, además, E-E3-1 (para la comparación entre máquinas). El informe se cierra con lo que haya; lo que falte queda escrito como pendiente | |

## 4. Integración continua y Windows

| N.º | Propuesta | Alternativa | |
|---|---|---|---|
| 4 | **La integración continua corre en todas las ramas** (y a pedido). Así el primer empuje de `f6-verificacion` prueba F4 y F5 en Windows y en Linux por primera vez | abrir un pull request de F5 a `main` solo para disparar la prueba | **bloquea** |
| 5 | **Arreglar los dos riesgos de Windows** dentro de `app/`: reintentar el reemplazo de la huella si el archivo está abierto (y que el servidor tolere una lectura fallida); en `indices.py`, no renombrar sobre una carpeta que no se pudo borrar | esperar a ver si falla | |
| 6 | **Comparación entre computadoras**: `e_e3_1.py` guarda además el sha256 de cada ráster de llegada y la ficha de la máquina (procesador, AVX-512 sí o no, memoria). Se corre en un commit limpio acá (Linux), en la máquina de la otra persona y en la integración continua (Windows y Linux, a pedido y una vez por semana: unos 15 min por sistema). Si una máquina da distinto, se informa y se investiga; **no se agrega tolerancia** (el criterio de E-E3-1 es 0 celdas) | correrlo en cada empuje: demasiado lento | |

## 5. E-E3-3 (rendimiento)

| N.º | Propuesta | |
|---|---|---|
| 7 | **Guion `herramientas/e_e3_3.py`**: los siete pares de E-E3-1 solo por el proceso, 3 repeticiones (mediana y rango), una primera corrida en frío (caché de numba vacía); modo "ambos" en Las Lagunas 48 h por el servidor y con dos procesos a la vez. Mide segundos por hora simulada, memoria pico por proceso, tiempo hasta la primera hora (y hasta `listo`) y memoria total del modo "ambos" (muestreo del RSS de los dos procesos cada 0,25 s). Declara que la memoria pico de Windows y de Linux son métricas distintas | |
| 8 | **La meta de v4.0 con 30.000 ha** se informa como no evaluable con el diseño del prerregistro, y se agrega **aparte, rotulada "fuera del prerregistro"**, la corrida de Las Chacras v4.0 libre de 141 h (29.319 ha) | **bloquea** |
| 9 | En la integración continua E-E3-3 es solo informativo (máquinas compartidas, con ruido) | |

## 6. Modo histórico

| N.º | Propuesta | Alternativa | |
|---|---|---|---|
| 10 | **Métricas con el código de v3.1** en un proceso aparte (`app/motores/metricas_v31.py`, con el camino de v3.1, como el proceso de datos), sobre la salida de cualquier corrida de un evento con ficha: IoU a igual superficie, horas hasta la superficie, fracción de primeras detecciones a tiempo, adelantadas, atrasadas, error mediano, puntaje, IoU en cada instante de evaluación de la ficha (marcando los que caen después del final de la corrida) y el aviso "no alcanza la superficie" cuando corresponde. Focos: `hotspots_v3.1` | las de v4.0 (`metricas_evento`): miden otra cosa | **bloquea** |
| 11 | **Corrida histórica con la ignición recomendada** (ficha de v3.1). En v4.0, si la ficha no tiene esa alternativa (Las Lagunas), se pasan los puntos y la hora de la ficha de v3.1 como ignición libre y se declara | solo la hipótesis 0 de la ficha de v4.0 | **bloquea** |
| 12 | **Solo los 2 eventos con datos en el clon.** Los otros 13 aparecen deshabilitados con la lista de lo que les falta, hasta que exista la publicación de datos históricos (F7). Los 4 del lote X-49 sin recomendación quedan fuera (§6.4) | armar ahora la publicación de los 13 | **bloquea** |
| 13 | **Pantalla**: panel "Modo histórico" con la cicatriz, los focos coloreados por pasada (a tiempo, adelantado, atrasado, no alcanzado), la tabla de métricas por corrida y, al lado, las cifras documentadas. Rótulo "evento no visto (X-49): solo para mostrar" en Las Chacras | | |
| 14 | **Cifras de referencia** en un archivo versionado (`docs/etapa3/historico_referencia.json`) con las filas de `docs/v4.0/31` §7.2, cómo se corre cada una y su fuente. **Criterio de la F6**: una prueba lenta exige que las filas de v3.1 (alt4) salgan iguales; la de v4.0 se corre una vez con su configuración documentada (libre, 141 h) y se informa con la ficha de comparabilidad. Se declara que la configuración por defecto del simulador (barreras, 72 h) da otras cifras | | **bloquea** |
| 15 | Correcciones de texto: el docstring falso de `servidor/datos.py` (las fichas de v3.1 y v4.0 no son iguales) y el plan §6.4 (son puntajes, no IoU) | | |

## 7. Pruebas e informe

| N.º | Propuesta | Alternativa | |
|---|---|---|---|
| 16 | **Prueba de la pantalla**: una herramienta opcional (`herramientas/probar_pantalla.py`) que maneja Chromium sin ventana con la biblioteca estándar (la que se usó en F3 y F5): cargar, marcar ignición, correr 6 h con el motor simulado, pausar, dibujar, reanudar, exportar, sin errores en la consola. Fuera de la integración continua; se corre en la máquina de cada persona | Playwright o Selenium: bibliotecas nuevas | |
| 17 | **Prueba de caída de un motor real**: matar el proceso de v3.1 a mitad y comprobar que el servidor lo informa | | |
| 18 | **Corregir la línea base del plan §6.1** (68 + 1 y 129 + 13 en un clon limpio) | | |
| 19 | **`docs/etapa3/01_verificacion.md`**: alcance; pruebas (tabla del §6.1 con estado y huecos); prerregistros (quién escribió, quién evaluó, etiqueta, resultado, desvíos declarados); una ficha del Anexo A para cada comparación (E-E3-1 por el proceso y por el servidor, E-E3-2, E-E3-4 A y B, modo "ambos", modo histórico, entre computadoras); reproducibilidad; rendimiento y requisitos (§2.7); límites. Lo que dependa de la otra persona queda marcado "pendiente" hasta que llegue | | |

## 8. Decisiones pendientes de la F5 (`F5_informe.md` §4)

| N.º | Propuesta | |
|---|---|---|
| 20 | Un cortafuego dibujado antes de iniciar que resulta rechazado (por ejemplo, fuera del dominio) **corta la corrida con error antes de simular** | |
| 21 | El viento manual en v4.0 con la biblioteca WindNinja (no es la configuración congelada) **se sigue aceptando**: es reproducible. Solo se rechaza con un campo de viento externo | |
| 22 | El zip de exportación **incluye los archivos para la corrida offline** (`intervenciones_v31/`, `cortafuegos_aplicados.geojson`, `modificador_aplicado.tif`, `meteo_editada.csv`) | |

## 9. Cómo contestar

"Apruebo todo", o los números con lo que se quiere distinto. Bloquean el inicio: **2, 4, 8, 10, 11, 12 y 14**.
