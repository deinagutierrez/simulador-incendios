# 01 — Verificación de la etapa 3

Fecha: 2026-11-16 · Rama `f6-verificacion` (desde `f5-intervenciones`; `main` sigue en la F3) · Pedido aprobado:
`F6_pedido_de_aprobacion.md` (D-E3-30, D-E3-31). Punto 19 del pedido.
Rótulos: **(dato)** medido, con su archivo · **(inferencia)** · **(sin verificar)** · **PENDIENTE**: depende de la evaluación
de la otra persona (LisandroV2002) o de una corrida sobre un commit limpio, y se completa cuando llegue.

**Actualización del 2026-11-16 (evaluación de LisandroV2002, con Claude).** E-E3-2, E-E3-3 y E-E3-4 se corrieron sobre el
commit limpio `d4118d8` (rama `f7-entrega`, 0 archivos sin registrar) en Windows 11 (AMD Ryzen 5 8600G, 12 hilos, 31,7 GB,
Python 3.14.2), en un clon instalado con `instalar.bat`. Resultado: **E-E3-4 se cumple; E-E3-3 se cumple en lo evaluable;
E-E3-2 no se cumple** (falla v4.0). Los párrafos que cambiaron por esta evaluación llevan la marca "(act. 16/11)"; el resto
del informe es el original. Lo que sigue rotulado PENDIENTE no se tocó en esta evaluación.

Este informe junta lo que ya está escrito en los informes de fase y en los prerregistros; no trae cifras nuevas salvo las
de §2 (pruebas de hoy). Cada cifra lleva su fuente.

## 1. Alcance: qué se verifica y qué no

- **Qué verifica esta etapa** (plan §6.4): que el simulador **conduce a v3.1 y a v4.0 sin alterarlos**. El programa lanza
  los motores congelados (`src/v3.1`, `src/v4.0`, 244 archivos con sha256 en `congelado.json`) en procesos aparte, los
  pausa, les aplica intervenciones y lee sus salidas. Las preguntas son de identidad (¿da lo mismo que la corrida offline?),
  de reproducibilidad (¿se repite desde la bitácora?, ¿entre computadoras?) y de costo (tiempo y memoria).
- **Qué no verifica**: la **capacidad predictiva**. Es la de las versiones congeladas, ya informada (docs/v4.0/31 §7.2 y
  plan §6.4): sobre los 10 eventos vistos, IoU mediana 0,483 (v3.1 librev2) contra 0,360 (v4.0), con igniciones ajustadas a
  la cicatriz que inflan el IoU; en el evento no visto Las Chacras octubre 2023, puntaje (IoU a igual superficie + fracción a
  tiempo) / 2 de 0,45–0,46 (v3.1) contra 0,25–0,37 (v4.0). El modo histórico (§6) muestra esas cifras regeneradas por el
  simulador; **no** es una validación nueva ni sirve para calibrar.
- Tampoco verifica la cadena de datos en tiempo real contra la realidad: la de índices la mide E-E3-2 (no se cumple, §4.3; act. 16/11); la de
  meteorología (pronóstico IFS 0,25° en lugar del archivo de 9 km) no tiene prueba (mejora M4 del plan).

## 2. Pruebas automáticas (plan §6.1)

`./probar.sh` (= `herramientas/probar.py`) en Linux (AMD Ryzen 7 5700, 16 hilos, 16 GB, Fedora 44, Python 3.14.10), sobre la
rama `f6-verificacion` **con los cambios de la F6 sin commit**, 2026-11-16. Resumen literal en §2.1. La integración continua
(`.github/workflows/pruebas.yml`, Windows y Linux, desde la F6 en todas las ramas) corre lo mismo: **PENDIENTE** el primer
empuje de `f6-verificacion`, que es la primera vez que el código de F4, F5 y F6 pasa por Windows en máquinas limpias.

**(act. 16/11) (dato)** El empuje se hizo: el flujo `pruebas` terminó bien en `windows-latest` y en `ubuntu-latest` sobre
`f6-verificacion` (`114f488`) y sobre `f7-entrega` (`d4118d8`). Además `herramientas/probar.py` pasó completo en un clon
recién instalado en Windows 11 (la máquina de la evaluación, `d4118d8`): congelado intacto, v3.1 68 + 1 omitida, v4.0
129 + 13 omitidas y 5 excluidas, las dos corridas de 6 h y `test/app` 207 + 2 omitidas en 6 min 24 s. Con esto dejan de
estar pendientes las menciones a la integración continua de la tabla que sigue y de §7.

| Nivel (§6.1) | Qué hay | Estado | Número | Tiempo | Huecos |
|---|---|---|---|---|---|
| Entorno | suites de los motores en el entorno único; exclusiones con motivo en `herramientas/pruebas_excluidas.txt` | pasan | acá: v3.1 69; v4.0 130 + 12 omitidas, 5 excluidas (esta copia tiene resultados locales; en un clon limpio son 68 + 1 omitida y 129 + 13 omitidas, §6.1 corregido el 2026-11-14) | 16 s y 47 s | 4 de las 5 excluidas ya fallaban en la copia original; 1 pide datos históricos |
| Procesos motor | `test_procesos.py`: identidad de 6 h en Las Lagunas con los tres motores, avisos, pausa, detener, ignición libre | pasan | 23 | unos 2 min (todo `test/app`: 4 min 58 s) | la identidad larga (36–72 h) solo en E-E3-1, no en cada cambio |
| Intervenciones | `test_intervenciones_nucleo.py`, `_v31.py`, `_v40.py`: viento manual, recorte, reproducción, hash encadenado; `test_windows_y_caidas.py` (F6): cortafuego inicial rechazado corta la corrida en v3.1, v4.0 y el simulado (D-E3-31) | pasan | 35 + 8 + 14, más 3 de la F6 | — | la equivalencia de 48 h con la corrida offline es E-E3-4 (PENDIENTE) |
| Datos | `test_datos.py`, `test_servidor_datos.py`: control de calidad meteorológico, teselas locales, alineación, archivos mal formados; `test_windows_y_caidas.py` (F6): borrado de tomas de índices que falla (Windows) | pasan | 34 + 25, más 3 de la F6 | — | la cadena con red solo con `herramientas/probar_red.py`, a mano |
| Servidor | `test_servidor.py`, `test_servidor_intervenciones.py`; F6: `test_historico.py` (modo histórico, con la prueba lenta de las filas de v3.1 alt4) y `test_windows_y_caidas.py` (huella bloqueada o a medio escribir; **caída de un motor real**: v3.1 matado a mitad de corrida) | pasan | 14 + 27 + 16 + 7 | la lenta de `test_historico.py`, unos 30 s; la caída de v3.1, unos 4 s | los bloqueos de Windows se simulan en Linux con `monkeypatch`; de verdad, solo en la integración continua (PENDIENTE) |
| Interfaz | `herramientas/probar_pantalla.py` (F6, opcional, fuera de la integración continua): Chromium o Edge sin ventana con la biblioteca estándar; cargar, clic, 6 h con el simulado, pausar, dibujar, reanudar, exportar, sin errores en la consola | pasa acá (código 0, 2026-11-16) | 1 recorrido | 10 s | no recorre el panel del modo histórico ni el modo "ambos"; probado solo con Chromium en Linux; Edge y Firefox, sin probar |
| Clon nuevo | integración continua en Windows y Linux limpios: clonar, instalar, correr 6 h del evento de ejemplo con cada motor | verde en la F3 (`main`) | — | — | PENDIENTE para F4–F6 (primer empuje de la rama) |
| Versiones cerradas | `herramientas/congelado.py verificar` | intactas | 244 archivos, conjunto `2b32757194d2…` | segundos | — |

Total de `test/app`: 209 pruebas, 207 pasan y 2 se omiten (180 al cierre de la F5, 178 + 2, más 16 de `test_historico.py` y
13 de `test_windows_y_caidas.py`). Las 2 omitidas son de `test_procesos.py` y son a propósito: v3.1 libre usa el mismo conductor
que librev2 en esas dos pruebas. Ninguna usa internet: el servidor se levanta en `127.0.0.1` en un puerto libre.

### 2.1 Resumen literal de `./probar.sh` (2026-11-16)

```
Python 3.14.10 en linux · repositorio /home/deina/claude/proyecto_fuego_sim/simulador-incendios
1. Versiones congeladas (sha256)
   versiones congeladas intactas (244 archivos)
2. Datos del dominio
3. Pruebas del motor v3.1
   69 passed, 8 warnings in 15.63s
4. Pruebas del motor v4.0
   130 passed, 12 skipped, 5 deselected, 75 warnings in 46.67s
5. Corrida corta con el motor v3.1 (prueba_rapida_v3, 6 horas simuladas)
   resultado en /home/deina/claude/proyecto_fuego_sim/simulador-incendios/resultados/v3.1/prueba_rapida_v3_20261116-0900
   4 s
6. Corrida corta con el motor v4.0 (prueba_rapida_v4, 6 horas simuladas)
   INFO pyogrio._io: Created 7 records
   16 s
7. Pruebas del simulador (test/app): procesos motor y servidor; dan lo mismo que la corrida offline
   207 passed, 2 skipped, 59 warnings in 297.78s (0:04:57)

Resumen
   BIEN   versiones congeladas
   BIEN   datos del dominio
   BIEN   pruebas v3.1
   BIEN   pruebas v4.0
   BIEN   corrida v3.1
   BIEN   corrida v4.0
   BIEN   pruebas del simulador

Todo funciona.
```

## 3. Prerregistros

Los cuatro se escribieron y etiquetaron en la F0 (`prerregistro-E-E3-1` a `-4`, commit `2e4a4fd`, 2026-11-10), antes del
código que evalúan. Regla del plan (Anexo B): uno escribe y el otro evalúa.

| Código | Pregunta | Escribe | Evalúa | Etiqueta | Resultado | Desvíos y anexos declarados |
|---|---|---|---|---|---|---|
| E-E3-1 | ¿Conduce a los motores sin alterarlos? | el usuario (deinagutierrez), con Claude | **el mismo frente** (D-E3-13) | `prerregistro-E-E3-1` | **se cumple**: 0 celdas distintas en los 7 pares, con y sin pausa (`E-E3-1_resultado.md`, 2026-11-11, Windows, commit `7cbe5b4`) | D-E3-13: evaluó quien escribió el código (la otra persona no pudo); compensado con criterio binario etiquetado antes, guion sin pasos manuales y repetible. Las Chacras se corrió con los datos aún fuera de git; luego se subieron sin cambios (D-E3-15, mismo sha256 del conjunto `52d145b3c3df…`). v3.1 en Las Chacras cortó sola a las 45–46 h (motivo 3), igual offline y en el proceso |
| E-E3-2 | ¿Los índices por AWS equivalen a los de GEE? | deinagutierrez, con Claude | LisandroV2002 (D-E3-25) | `prerregistro-E-E3-2` (los nombres se agregaron después sin cambiar diseño ni criterio) | **no se cumple, en dos evaluaciones** (act. 16/11). Segunda, después de la revisión única de la máscara (D-E3-32; `E-E3-2_resultado.md`, commit `6acb38f`): v4.0 12,1 % de celdas cambian de clase e IoU a 48 h 0,910; v3.1 librev2 cumple. Por el prerregistro, GEE pasa a ser obligatorio (§4.3). Primera (`E-E3-2_resultado_primera_evaluacion.md`, Windows, commit `d4118d8`): criterio 1 se cumple (diferencia absoluta mediana 0,0007 a 0,0062); criterios 2 y 3 fallan en v4.0 (11,9 % de celdas cambian de clase; IoU a 48 h 0,895) y se cumplen en v3.1 librev2 (0,19 %; 0,997) | dos anexos escritos antes de evaluar y sin ver cifras de (b) ni (c): `E-E3-2_escala.md` (escala de reflectancia DN/10000, elegida contra (a) como pide el diseño) y `E-E3-2_aclaracion_c.md` (D-E3-27: en (c) el lado AWS de v4.0 usa también el verano hecho por AWS; sin eso el cambio de clase SB40 daba 0 % por construcción). Como no se cumple, la vía AWS sigue rotulada "en prueba" (`indices.AWS_EN_PRUEBA` sin cambiar) |
| E-E3-3 | ¿Cuánto tarda y cuánta memoria usa? | deinagutierrez, con Claude | LisandroV2002 (D-E3-30) | `prerregistro-E-E3-3` (nombres agregados después) | **medición completa** (act. 16/11; `E-E3-3_resultado.md`, Windows, commit `d4118d8`): v3.1 ≤ 0,5 s/h **se cumple** (medianas 0,297 a 0,316); modo "ambos" dentro de 16 GB **se cumple** (máximo muestreado 1.364 MB); v4.0 con unas 30.000 ha **no evaluable con el diseño** | la meta de v4.0 "≤ 3 s/h con unas 30.000 ha" **no se puede evaluar con el diseño** (ningún escenario de E-E3-1 pasa de 12.839 ha con v4.0); se informa así y se agrega aparte, rotulada "fuera del prerregistro", Las Chacras v4.0 libre 141 h (D-E3-30, punto 8). La memoria pico de Windows (`peak_wset`) y la de Linux (`ru_maxrss`) no son la misma métrica |
| E-E3-4 | ¿Las intervenciones son reproducibles? | deinagutierrez, con Claude | LisandroV2002 | `prerregistro-E-E3-4` y `prerregistro-E-E3-4-trazos` (`9fabd7c`, trazos y horas fijados antes del código de intervenciones) | **se cumple** (act. 16/11; `E-E3-4_resultado.md`, Windows, commit `d4118d8`): en las 5 corridas y los 3 motores, A con 0 celdas distintas y la misma cadena de hash; B con IoU 1,000000 y la misma longitud aplicada | el guion usa la ignición de la ficha (hipótesis 1), no `configuracion.ignicion`; "misma longitud" se mide con la geometría en v4.0 y con la identidad de celdas o enlaces cuando hay recorte (F5_informe §3, 5): conviene que quien evalúa lo acepte antes de correr. (act. 16/11) El guion se corrió tal como estaba, sin cambios; la aceptación expresa de esas dos decisiones por quien evalúa **no quedó anotada antes de correr** y falta registrarla en `decisiones.md` |

Además se corrió E-E3-1 **por el servidor** (F2, `herramientas/e_e3_1_servidor.py`, 2026-11-11, commit `aad2731`): 0 celdas
distintas en los 7 pares con y sin pausa y en 3 corridas detenidas. Es una comprobación de cierre, no reemplaza a la
evaluación formal. Y se repitió E-E3-1 en Linux el 2026-11-14 con código sin registrar (después de la F5): 0 celdas en los 7
pares; no vale como registro formal.

## 4. Fichas de comparabilidad (Anexo A)

Una por comparación. Lo que es igual en las dos columnas se escribe una vez.

### 4.1 E-E3-1 por el proceso motor

| Campo | A: offline (`scripts/correr_escenario.py` del motor) | B: simulador (`app/motores/proceso.py`) |
|---|---|---|
| Motor y versión | v3.1 y v4.0 congelados, conjunto `2b32757194d2…` | lo mismo, conducido por `proceso.py` del commit `7cbe5b4` |
| Modelo y variante; parámetros | v4.0 `modelo_v3` `barreras` sin parada; v3.1 `libre` y `libre_v2` (D-E3-01, D-E3-29); ningún parámetro cambiado | igual |
| Dominio / grilla | `las_lagunas_potrerillos`, EPSG:5345, 30 m | igual |
| Evento; rol | caso La Aguada 2023 (36 h, v4.0); Las Lagunas 2024 h1 SNMF (48 h; visto); Las Chacras oct. 2023 alt4 06 UTC (72 h; **no visto, X-49**) | igual |
| Ignición | la de la ficha / caso, sin desplazamiento | igual |
| Meteorología, viento, índices, combustible, humedad | los insumos del repositorio de cada evento (sha256 por archivo en `E-E3-1_resultados.json`) | igual |
| Barreras | caminos en v4.0 (`barreras`); ninguna en v3.1 | igual (v3.1 con matriz de barreras vacía desde la F5: 0 celdas distintas, F5_informe §2) |
| Parada y horizonte | horas del escenario; v3.1 corta sola en Las Chacras a las 45–46 h | igual; B se repite con una pausa y reanudación a mitad |
| Intervenciones | ninguna | ninguna (bitácora vacía) |
| Métrica, referencia | celdas con tiempo de llegada distinto (`hora_llegada_min.tif`, `t_llegada_s.tif`) | — |
| Evaluador | `herramientas/e_e3_1.py` | — |
| n y advertencias | 7 pares, una computadora (Windows 11, Intel de 20 hilos) | — |

**Resultado (dato)**: 0 celdas distintas en los 7 pares, sin pausa y con pausa (`E-E3-1_resultado.md`).
**Lectura al pie**: solo difiere quién lanza el motor. Se concluye que `proceso.py` no altera el resultado en estos 7 casos.
No se concluye nada sobre si las huellas son correctas, ni sobre ignición libre, intervenciones (E-E3-4) o pausas largas o
repetidas.

### 4.2 E-E3-1 por el servidor

| Campo | A: offline | B: simulador por HTTP (`POST /api/corridas`) |
|---|---|---|
| Motor y versión | congelados, `2b32757194d2…` | lo mismo, por el servidor del commit `aad2731` (F2), sin código sin registrar |
| Resto de los insumos | como en 4.1 | igual |
| Parada y horizonte | como en 4.1 | igual; además una corrida **detenida** por motor en Las Lagunas (hora 25) |
| Métrica | celdas distintas; en la detenida, las que ardieron **antes** del minuto de la detención | — |
| Evaluador | `herramientas/e_e3_1_servidor.py` | — |
| n y advertencias | 7 pares + 3 detenidas, Windows; la corrió quien escribió el código | — |

**Resultado (dato)**: 0 celdas distintas en todo (`F2_e_e3_1_por_servidor.json`, F2_informe §3.2).
**Lectura al pie**: el servidor (avisos, órdenes por HTTP, huella parcial) no altera la salida. Advertencia: la comparación
de la detenida se cambió de "hasta" a "antes de" el minuto de la detención **después** de ver 7 celdas distintas de 31.147 en
v4.0 (las enciende el paso que la detenida no llega a dar); queda declarado en F2_informe §4.

### 4.3 E-E3-2 (índices AWS contra GEE)

| Campo | A: GEE | B: AWS (Earth Search, máscara SCL) |
|---|---|---|
| Índices | (a) `ndvi_30m`/`ndmi_30m` de Las Lagunas 2024; (b) `NDVI_NDMI_2024_09.tif`; (c) compuestos del banco | (a) compuesto de ventana 30/07–17/09/2024; (b) mensual de septiembre de 2024; (c) los de AWS, con verano de AWS para v4.0 (D-E3-27) |
| Escala | la de GEE | DN/10000 sin restar 0,1 (`E-E3-2_escala.md`, elegida contra (a) antes de mirar (b) y (c)) |
| Motores en (c) | v4.0 y v3.1, Las Lagunas 48 h | igual |
| Métrica | diferencia absoluta mediana de NDVI y NDMI; % de celdas que cambian de clase de combustible; IoU entre huellas a las 48 h | — |
| Evaluador | `herramientas/e_e3_2.py`, LisandroV2002 | — |

Qué ya se sabía que difiere: método del compuesto (ventana contra mediana del banco) y, en (c), el verano para v4.0
(aclaración (c)).

**Primera evaluación (dato, act. 16/11; `E-E3-2_resultado_primera_evaluacion.md`, Windows, commit `d4118d8`): no se cumple.**

| Criterio | Umbral | Medido | |
|---|---|---|---|
| 1. Diferencia absoluta mediana | ≤ 0,02 | (a) NDVI 0,0053, NDMI 0,0062; (b) NDVI 0,0016, NDMI 0,0007 (2.793.912 celdas, 0 % sin dato) | se cumple |
| 2. Celdas que cambian de clase | < 3 % en cada motor | v4.0 11,943 % (333.667 celdas); v3.1 librev2 0,188 % (5.258) | **no se cumple** (v4.0) |
| 3. IoU de las huellas a 48 h | ≥ 0,95 en cada motor | v4.0 0,8946 (13.122 contra 13.272 ha); v3.1 librev2 0,9973 (38.142 contra 38.197 ha) | **no se cumple** (v4.0) |

Informativo, fuera del criterio: los compuestos de verano de 2024 hechos por AWS contra los de GEE dan una diferencia
absoluta mediana de NDVI de 0,0021 (enero), 0,0098 (febrero) y 0,0027 (marzo), con percentil 95 de 0,056, 0,075 y 0,089;
la ventana del evento (a) tiene percentil 95 de 0,022.

**Lectura al pie**: los índices por AWS reproducen los de GEE en la mediana y v3.1 da prácticamente la misma huella con unos
u otros. En v4.0 no: una de cada ocho celdas cambia de modelo SB40 y las huellas se apartan (IoU 0,895), aunque la superficie
total casi no cambia (1,14 %). **(inferencia, sin verificar)** El cambio viene de los compuestos de verano hechos por AWS,
que son los que usa la regla 3.3b para asignar el SB40, y no de la ventana del evento: según el guion, de ahí
sale el SB40 de v4.0, y su cola de diferencias es entre dos veces y media y cuatro veces más ancha que la de la ventana. No se midió qué
umbral de la regla ni qué mes lo causa. Un solo evento y una sola época (límite declarado en el prerregistro).
**Consecuencia** (plan, R5): la vía AWS no se habilita y sigue rotulada "en prueba"; queda por decidir si se ajusta el
método del compuesto de verano por AWS y se vuelve a evaluar, o si v4.0 exige los compuestos de GEE y se lo dice en la
pantalla. El criterio y los umbrales no se tocan.

**Segunda evaluación (dato, act. 16/11 noche; `E-E3-2_resultado.md`, Windows, commit `6acb38f`): no se cumple.** Es la
que permite el prerregistro después de la revisión única de la máscara de nubes (`E-E3-2_revision_mascara.md`, D-E3-32: sin
descartar teselas por nubes, clases SCL 2 y 7 descartadas, margen de 100 m), escrita y registrada antes de medir.

| Criterio | Primera (máscara 1.0) | Segunda (máscara 1.1) | |
|---|---|---|---|
| 1. Diferencia absoluta mediana | (a) 0,0053 y 0,0062; (b) 0,0016 y 0,0007 | (a) 0,0054 y 0,0068; (b) 0,0019 y 0,0008 | se cumple |
| 2. Cambio de clase | v4.0 11,943 %; v3.1 librev2 0,188 % | v4.0 **12,093 %**; v3.1 librev2 0,196 % | **no se cumple** (v4.0) |
| 3. IoU a 48 h | v4.0 0,8946; v3.1 librev2 0,9973 | v4.0 **0,9095**; v3.1 librev2 0,9970 | **no se cumple** (v4.0) |

La revisión sumó escenas (verano: 24 por mes contra 22, 21 y 18) y achicó la cola de marzo (percentil 95 del NDVI 0,069
contra 0,089), pero el cambio de clase de v4.0 no bajó. Coincide con el diagnóstico (`E-E3-2_diagnostico.md` §5): la regla
3.3b cambia de clase con diferencias de NDVI mucho menores que las que separan a una máscara SCL de Cloud Score+.
**Consecuencia (prerregistro, "Si no se cumple")**: no hay otra revisión. **GEE pasa a ser obligatorio para los índices** y
hay que declararlo en la guía de uso (F7). La vía AWS sigue rotulada "en prueba" y no se habilita. Queda por hacer: los
compuestos mensuales de verano por Earth Engine (F4_informe §6), rehacer por GEE el verano 2026 del repositorio, que hoy
está hecho por AWS, y decidir entre las dos personas si AWS se habilita solo para v3.1, que cumple los tres criterios en
las dos evaluaciones (sería un desvío: el criterio pide "en cada motor").

### 4.4 E-E3-4 A (en vivo contra reproducción desde la bitácora)

| Campo | A: corrida en vivo con intervenciones en pausa | B: reproducción desde `corrida.json` y `bitacora.jsonl` |
|---|---|---|
| Motor | v4.0, v3.1 librev2 y v3.1 libre por `proceso.py` | igual; la reproducción la hace el proceso motor (D-E3-28, 19) |
| Evento | Las Lagunas 2024, hipótesis 1, 48 h (visto) | igual |
| Intervenciones | las 5 corridas de `E-E3-4_trazos.json` (etiqueta `prerregistro-E-E3-4-trazos`) | las mismas, leídas de la bitácora (hash encadenado) |
| Métrica | celdas distintas en el tiempo de llegada; criterio 0 | — |
| Evaluador | `herramientas/e_e3_4.py`, LisandroV2002 | — |

**Resultado (dato, act. 16/11; `E-E3-4_resultado.md`, Windows, commit `d4118d8`): se cumple.** En los 15 pares (5 corridas
× 3 motores), 0 celdas distintas en el tiempo de llegada, la misma cadena de hash y ninguna entrada sin aplicar. Antes, en
las pruebas de humo de 3 h y en `test/app`, había dado lo mismo.
**Lectura al pie**: solo difiere de dónde salen las intervenciones (órdenes en pausa contra la bitácora). Se concluye que
una corrida con cortafuegos y viento manual se repite celda por celda desde su `corrida.json` y su `bitacora.jsonl`, en
los tres motores, en esta máquina. Un solo evento (Las Lagunas 2024); no se probó reproducir en otra computadora.

### 4.5 E-E3-4 B (en vivo contra offline con los mismos trazos desde el inicio)

| Campo | A: corrida en vivo | B: `correr_escenario.py` del motor con los trazos recortados desde t = 0 y la serie meteorológica editada |
|---|---|---|
| Barreras | cortafuegos aplicados en pausa, recortados a celdas no afectadas | los archivos que deja A para la corrida offline (`intervenciones_v31/`, `cortafuegos_aplicados.geojson`, `modificador_aplicado.tif`, `meteo_editada.csv`; el zip de exportación los incluye desde la F6, D-E3-31) |
| Viento | manual en pausa: v4.0 gira gradualmente en la hora siguiente, v3.1 cambia de golpe (esperado, no cuenta como falla) | la serie editada |
| Métrica | IoU de la huella final ≥ 0,99 y la misma longitud de cortafuego (la recortada, D-E3-28, 14) | — |

**Resultado (dato, act. 16/11; `E-E3-4_resultado.md`, Windows, commit `d4118d8`): se cumple.** En los 15 pares, IoU de la
huella final 1,000000 (0 celdas con tiempo de llegada distinto) y la misma longitud de cortafuego aplicada. En v3.1 el
trazo de 25 m de la hora 12 se recortó porque pasa en parte por celdas ya alcanzadas (corrida 3: quedan 6.580 m de 7.000
en librev2 y 5.280 m en libre; corrida 5: 4.440 m y 4.590 m); en v4.0 entró entero. La longitud que se compara es la
aplicada después del recorte (D-E3-28, 14).
**Lectura al pie**: se concluye que un cortafuego o un cambio de viento aplicados en pausa dan la misma huella que la
corrida offline del motor con esos mismos trazos (ya recortados) y la serie editada desde el inicio. No se concluye que el
trazo **sin recortar** cargado desde el inicio dé lo mismo, ni nada sobre si un cortafuego real detendría el fuego. Un solo
evento. Límite conocido: un trazo de suelo mineral antes de iniciar que pasa por la celda de ignición no da lo mismo que a
t = 0 (F5_informe §5); los trazos de E-E3-4 no pasan por ahí.

### 4.6 Modo "ambos" (v4.0 contra v3.1 librev2, la misma corrida)

| Campo | A: v4.0 | B: v3.1 librev2 |
|---|---|---|
| Motor y versión | v4.0 congelado | v3.1 congelado |
| Modelo y variante | `modelo_v3`, `barreras` (caminos probabilísticos, semilla 20261015) | `modelo_v2`, barreras de caminos **apagadas** (D-E3-29) |
| Dominio / grilla | 30 m, EPSG:5345 | igual grilla en la app |
| Evento e ignición | los que elige el usuario (iguales para las dos) | igual |
| Meteorología | serie del evento o pronóstico | igual serie |
| Motor | numpy, 8 vecinos, paso 2 min, sub-pasos CFL | numba, 16 vecinos, paso 60 s |
| Viento | serie uniforme + factor topográfico (D41), límite andrews_2013 | biblioteca WindNinja × velocidad escalar media de 16 puntos |
| Combustible | 40 modelos SB40, regla 3.3b (usa compuestos de verano, con su fórmula del NDMI) | 7 clases (`tabla_combustibles_v1.csv`) |
| Humedad muerta; lluvia | retardo NFDRS dentro del autómata, sin extinción por lluvia de 24 h | retardo de Simard, serie precalculada, extinción con 15 mm en 24 h |
| Métrica | coincidencia = área quemada por los dos / envolvente; aviso por debajo del 50 % a las 24 h (D-E3-05) | — |

**Resultado (dato, F3_informe §4)**: en Las Lagunas 2024, 30 h, v4.0 2.963 ha y v3.1 librev2 8.136 ha; coinciden en el 34 % a
las 24 h y la pantalla mostró el aviso de discrepancia. Memoria total de los dos a la vez (act. 16/11, E-E3-3, Las Lagunas 48 h, Windows):
1.364 MB de máximo muestreado por el servidor y 1.356 MB con dos procesos; la suma de los picos individuales, 1.404 y 1.419 MB.
**Lectura al pie**: difieren en casi todo lo que define el modelo (motor y vecindad, viento, combustible, barreras, humedad,
extinción por lluvia; plan §2.3 y §6.2).
La coincidencia mide cuánto discrepan dos modelos, **no** cuál acierta. No se puede atribuir la diferencia a un solo factor.

### 4.7 Modo histórico (simulador contra las cifras de docs/v4.0/31 §7.2)

| Campo | A: §7.2 (corridas offline originales, carpetas fuera del clon) | B: simulador (proceso motor + `app/motores/metricas_v31.py`) |
|---|---|---|
| Motor y versión | v3.1 y v4.0 congelados | iguales (`2b32757194d2…`) |
| Modelo y variante | filas 1–2: v3.1 librev2 y libre, alt4; fila 3: v4.0 **libre**, sin parada, 141 h | las mismas configuraciones (`historico_referencia.json`, `regenerar`) |
| Evento; rol | SL-2023-CHACRASOCT, **no visto (X-49)**: solo para mostrar | igual; la pantalla lo rotula |
| Ignición | alt4 = foco n04 del primer pase, 2023-10-17 06 UTC (hipótesis 4), **elegida con los focos de este mismo evento** | igual |
| Meteorología, viento, índices, combustible, humedad | los del evento en el repositorio | igual (F6_referencia_v40.md §4 para v4.0) |
| Métrica, referencia y máscara | métricas de v3.1 (`evaluar_x49.evaluar`, `validation/metricas.py`): IoU a igual superficie, horas hasta la superficie, fracción a tiempo, adelantada, atrasada, error mediano, puntaje; cicatriz MapBiomas (1.306 ha válidas), máscara del dominio y combustible > 0, 46 focos `hotspots_v3.1`, 30 primeras detecciones | lo mismo, en un proceso aparte con el camino de v3.1 (D-E3-30, 10); el servidor no importa ningún motor |
| Evaluador | el código de v3.1 | el mismo código, sin tocar (sha256 en el rótulo de `metricas_v31.json`) |
| n y advertencias | **un evento** no visto | ídem |

**Resultado (dato)**:
- Filas 1 y 2 (v3.1 librev2 y libre, alt4): iguales en todas las columnas, redondeadas como en el documento (puntaje 0,452 y
  0,439). Lo exige la prueba lenta `test_las_chacras_alt4_v31_da_las_cifras_documentadas` (pasa hoy, §2.1).
- Fila 3 (v4.0 libre, 141 h): una sola corrida, igual en todas las columnas (IoU 0,548; 61,7 h; a tiempo 0,20; puntaje 0,374;
  29.319 ha) (`F6_referencia_v40.md`). Hecha con código sin commit (diff de `app/motores` `54d40fd2b42f…`): repetirla sobre
  commit limpio es **PENDIENTE**.
- La configuración por defecto del simulador (v4.0 `barreras`) da otras cifras: puntaje 0,39 e IoU 0,579 a 72 h y a 141 h
  (24.047 ha a 141 h). Declarado en `historico_referencia.json` y en la pantalla.
- Filas 4 a 12 (alt3, SNMF, hipótesis 1, la fila 12 con parada): **no regeneradas todavía**.
**Lectura al pie**: se concluye que el simulador regenera las filas 1–3 con el código de v3.1. No se concluye nada sobre la
capacidad predictiva (un evento, ignición elegida con sus propios focos) ni que `barreras` mejore a v4.0 (+0,016 de puntaje,
un evento). Solo 2 de los 15 eventos con ficha tienen datos en el clon (Las Chacras octubre 2023 y Las Lagunas 2024); los
otros 13 esperan la publicación de datos históricos (F7) y los 4 del X-49 sin ignición recomendada se rechazan (D-E3-30, 12).

### 4.8 Entre computadoras

| Campo | A: Windows (desarrollo) | B: Linux (esta máquina) |
|---|---|---|
| Equipo | Windows 11, Intel de 20 hilos, Python 3.14.7 | Fedora 44, AMD Ryzen 7 5700 (16 hilos, sin AVX-512), 16 GB, Python 3.14.10 |
| Código | commit `7cbe5b4` (2026-11-11), limpio | `9fabd7c` + F5 sin commit (2026-11-14, 15 archivos sin registrar) |
| Motores e insumos | congelado `2b32757194d2…`; mismos datos | igual |
| Escenarios | los 7 pares de E-E3-1 | igual |
| Métrica | celdas quemadas, ha y motivo de fin por par; **sha256 del ráster de llegada** desde la F6 (`e_e3_1.py --referencia`) | — |

**Resultado (dato)**: los 7 pares dan las mismas celdas quemadas, las mismas ha y el mismo motivo de fin en las dos máquinas
(`E-E3-1_resultados.json` contra `resultados/app/E-E3-1/resultados.json`). Eso **no** prueba igualdad bit a bit: ninguna de las
dos corridas guardó el sha256 del ráster.
**Hecho (dato, 2026-11-16)**: E-E3-1 corrido acá sobre el commit limpio `c7730d0` (sin código sin registrar): 0 celdas
distintas en los 7 pares, con y sin pausa, y la tabla de sha256 de los rásteres de llegada quedó como referencia en
`docs/etapa3/prerregistros/E-E3-1_huellas.json` (offline, proceso y proceso con pausa iguales dentro de cada par).
**PENDIENTE**: (2) que LisandroV2002 lo corra con `--referencia docs/etapa3/prerregistros/E-E3-1_huellas.json` en su máquina;
(3) `.github/workflows/reproducibilidad.yml` (a pedido y los lunes, Windows y Linux), que necesita el primer empuje. Sin tolerancia: si una máquina da distinto se
informa y se investiga (por ejemplo, con `NPY_DISABLE_CPU_FEATURES=AVX512F`).
**Lectura al pie**: hoy solo se puede decir que dos máquinas distintas, con sistemas y procesadores distintos, dan la misma
superficie celda por celda en cantidad; la igualdad de los tiempos de llegada entre máquinas sigue **(sin verificar)**.

## 5. Reproducibilidad (plan §6.3)

| Qué | Estado |
|---|---|
| Misma corrida, misma computadora | (dato) E-E3-1: offline, proceso y proceso con pausa dan lo mismo; Las Chacras v4.0 72 h repetida en la F6 por otro camino (F6-referencia) es idéntica celda por celda a la de E-E3-1 |
| Reproducción desde la bitácora | (dato) en `test/app` y en las pruebas de humo de E-E3-4: misma cadena de hash y 0 celdas distintas. Formal (act. 16/11): E-E3-4 A **se cumple**, 0 celdas distintas y la misma cadena en los 15 pares |
| Equivalencia con la corrida offline con los mismos trazos | (dato) F5: 0 celdas distintas en los dos motores con un trazo en pausa, viento manual y suelo mineral. Formal (act. 16/11): E-E3-4 B **se cumple**, IoU 1,000000 y la misma longitud aplicada en los 15 pares |
| Entre computadoras | ver §4.8: mismas cantidades; referencia bit a bit fijada en Linux (`c7730d0`); las otras máquinas **PENDIENTE** |
| Rastreo de cada resultado | los guiones anotan commit, archivos sin registrar, sha256 del congelado y de los datos; desde la F6, también la ficha de la máquina (procesador, AVX-512, versiones) |

## 6. Rendimiento y requisitos (plan §2.7)

### 6.1 Medición formal: E-E3-3 (act. 16/11)

(dato) `E-E3-3_resultado.md`: Windows 11, AMD Ryzen 5 8600G (6 núcleos, 12 hilos, AVX-512), 31,7 GB, Python 3.14.2, commit
`d4118d8`; carga de fondo 5 % de CPU al empezar y al terminar. Tres repeticiones por par, la primera en frío; mediana y rango.

| Escenario | Motor | ha | s/h simulada | MB pico (`peak_wset`) | Hasta la 1.ª hora: frío / caliente (s) |
|---|---|---|---|---|---|
| La Aguada 36 h | v4.0 | 1.348 | 0,204 (0,204–0,205) | 223 | 2,5 / 2,5 |
| Las Lagunas 48 h | v4.0 | 12.839 | 0,981 (0,976–0,983) | 526 | 3,7 / 3,7 |
| Las Lagunas 48 h | v3.1 libre | 34.793 | 0,315 (0,314–0,362) | 872 | 5,9 / 3,5 |
| Las Lagunas 48 h | v3.1 librev2 | 32.915 | 0,316 (0,316–0,363) | 884 | 6,0 / 3,7 |
| Las Chacras 72 h | v4.0 | 2.356 | 0,375 (0,365–0,409) | 495 | 6,6 / 3,5 |
| Las Chacras 72 h | v3.1 libre | 1.526 | 0,297 (0,295–0,350) | 864 | 6,0 / 3,6 |
| Las Chacras 72 h | v3.1 librev2 | 3.065 | 0,300 (0,300–0,351) | 877 | 6,0 / 3,7 |

| Meta del prerregistro | Medido | |
|---|---|---|
| v3.1 ≤ 0,5 s por hora simulada (mediana de cada par) | 0,297 a 0,316; el máximo de todas las repeticiones, en frío, 0,363 | **se cumple** |
| Modo "ambos" dentro de 16 GB | 1.364 MB (servidor) y 1.356 MB (dos procesos) de máximo muestreado; suma de picos 1.404 y 1.419 MB | **se cumple** |
| v4.0 ≤ 3 s/h con unas 30.000 ha | ningún escenario del diseño pasa de 12.839 ha (0,981 s/h) | **no evaluable con el diseño** |

En el modo "ambos" v4.0 tardó 1,10 s/h y v3.1 librev2 0,44 s/h (contra 0,98 y 0,32 solos): la corrida de 48 h termina en 53 s.
**Fuera del prerregistro** (una corrida, en caliente): Las Chacras v4.0 libre 141 h, 29.319 ha, 0,770 s/h y 539 MB.

**Lectura al pie**: en esta máquina las dos metas evaluables se cumplen con margen, y el requisito de 16 GB para el modo
"ambos" es conservador: usa menos de 1,5 GB. La meta de v4.0 con 30.000 ha sigue sin evaluación formal; la corrida aparte
queda muy por debajo de 3 s/h, pero es un evento y no entra en el criterio. Es una sola computadora, de escritorio y sin
carga: no dice cuánto tarda en una máquina más chica, y no hay medición con 8 GB.

### 6.2 Antecedentes (antes de E-E3-3)

Lo que había antes de la medición formal (proceso sin órdenes, tandas de E-E3-1 y de la F6):

| Escenario | Motor | Windows, 2026-11-11 (s/h · memoria pico) | Linux, 2026-11-14 (s/h · memoria pico) |
|---|---|---|---|
| La Aguada 36 h (1.348 ha) | v4.0 | 0,35 · 226 MB | 0,21 · 302 MB |
| Las Lagunas 48 h (12.839 ha) | v4.0 | 1,77 · 536 MB | 0,90 · 656 MB |
| Las Lagunas 48 h (34.793 ha) | v3.1 libre | 0,55 · 865 MB | 0,32 · 1.013 MB |
| Las Lagunas 48 h (32.915 ha) | v3.1 librev2 | 0,34 · 878 MB | 0,35 · 1.030 MB |
| Las Chacras 72 h (2.356 ha) | v4.0 | 0,36 · 498 MB | 0,35 · 625 MB |
| Las Chacras 45 h (1.526 ha) | v3.1 libre | 0,31 · 864 MB | 0,29 · 1.002 MB |
| Las Chacras 46 h (3.065 ha) | v3.1 librev2 | 0,32 · 877 MB | 0,31 · 1.032 MB |

Fuentes: `E-E3-1_resultados.json` (Windows) y `resultados/app/E-E3-1/resultados.json` (Linux, código sin registrar).
Fuera del prerregistro (F6_referencia_v40.md, Linux): Las Chacras v4.0 libre 141 h (29.319 ha), 0,69 s/h y 669 MB; con
`barreras` 141 h, 0,88 s/h y 681 MB. El antecedente del plan para esa corrida era 2,7 s/h (offline, con figuras).

- (dato) v3.1 queda entre 0,29 y 0,55 s/h: la meta de ≤ 0,5 s/h se pasa solo una vez (0,55, Windows, Las Lagunas libre con
  35.000 ha). Las tandas se mueven (librev2 en Las Lagunas dio 0,57 y 0,34 en Windows en dos tandas, F1_informe §4).
- (dato) v4.0 por proceso usa 0,2 a 0,7 GB; v3.1, 0,9 a 1,0 GB. La memoria de Windows y la de Linux son métricas distintas
  (`peak_wset` contra `ru_maxrss`): no se comparan entre sí.
- (inferencia) Los dos motores a la vez usarían 1,4 a 1,7 GB (suma de los picos individuales de v4.0 y v3.1 librev2 en Las
  Lagunas: 0,54 + 0,88 en Windows, 0,66 + 1,03 en Linux): el requisito de 16 GB para el modo
  "ambos" del plan parece conservador y 8 GB alcanzarían con holgura. (act. 16/11) E-E3-3 lo confirma en la parte medida:
  1,36 GB de máximo muestreado (§6.1); que 8 GB alcancen sigue siendo inferencia, no se midió en una máquina de 8 GB. Se
  fija en la guía de uso (F7).
- La meta de v4.0 "≤ 3 s/h con unas 30.000 ha" no se puede evaluar con el diseño de E-E3-3; la corrida aparte de 29.319 ha
  queda muy por debajo (0,69 s/h acá), pero es un evento y una máquina.

## 7. Límites

- **Lo verificado es la conducción, no la predicción** (§1). Nada de este informe dice si las huellas son correctas.
- **Prerregistros** (act. 16/11): los cuatro están evaluados e informados. E-E3-1 y E-E3-4 se cumplen; E-E3-3 se cumple
  en las dos metas evaluables y la tercera no se puede evaluar con su diseño; **E-E3-2 no se cumple** (v4.0), tampoco
  después de la revisión única de la máscara: GEE pasa a ser obligatorio para los índices y la vía AWS sigue "en prueba"
  (§4.3). La revisión y la segunda evaluación las hizo la misma persona (D-E3-32). E-E3-1 lo evaluó quien escribió el código (D-E3-13); los otros tres, la otra persona. Con esto
  el criterio de la F6 ("todos los prerregistros evaluados e informados, se cumplan o no") **se cumple en esa parte**.
  Quedan abiertos hacer los compuestos de verano por GEE, si AWS se habilita solo para v3.1, y la aceptación expresa del
  guion de E-E3-4 (§3).
- **Windows**: los arreglos de la F6 (reemplazo de la huella con reintentos, lectura tolerante en el servidor, borrado
  comprobado de tomas de índices) se probaron en Linux simulando los errores. El código de F4, F5 y F6 no pasó todavía por la
  integración continua en Windows (**PENDIENTE**: primer empuje de la rama). (act. 16/11) Ya pasó: `pruebas` en verde en
  `windows-latest` sobre `114f488` y `d4118d8`, y `probar.py` completo en un Windows 11 real (§2).
- **Código sin commit**: las pruebas de §2.1 y la fila 3 del modo histórico se corrieron con los cambios de la F6 sin commit.
  Hay que repetirlas sobre el commit de la F6.
- **Modo histórico**: 2 de 15 eventos con datos en el clon; filas 4 a 12 de §7.2 sin regenerar; las cifras son de un evento no
  visto, solo para mostrar.
- **Pantalla**: la prueba automática es opcional y recorre el camino principal con el motor simulado; el panel del modo
  histórico y el modo "ambos" en el navegador se probaron a mano; Edge y Firefox sin probar.
- **Caída de un motor real**: probada matando v3.1 en Linux; en Windows la prueba corre recién con la integración continua
  (PENDIENTE); v4.0, sin probar.
