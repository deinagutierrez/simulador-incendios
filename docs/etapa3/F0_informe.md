# F0 — Repositorio, congelamiento y comprobaciones: informe

Fecha: 2026-11-10 · Equipo: Windows 11, Python 3.14.7, git 2.56.0.
Rótulos: **(dato)** medido ese día en ese equipo · **(inferencia)** · **(sin verificar)**.

## 1. Qué quedó hecho

| Tarea de F0 | Estado |
|---|---|
| Repositorio nuevo clonado y primera subida preparada en local | hecho; **falta subir** (necesita nombre y correo de git, permiso de escritura y visto bueno) |
| Motores v3.1 y v4.0 copiados sin cambios y congelados | hecho |
| Datos mínimos, viento partido | hecho |
| Entorno único para los dos motores | verificado en Windows; **Linux sin verificar** |
| Verificación de clon (`herramientas/probar.py`) e integración continua | escritos; la integración continua corre recién al subir |
| Comprobaciones técnicas del plan | hechas (§5) |
| Decisiones registradas | `decisiones.md` |
| Prerregistros E-E3-1 a 4 | escritos en `prerregistros/`; **falta etiquetarlos** en git |
| Contrato entre los dos frentes | `contrato_servidor_motor.md`, versión 1 |
| Publicación con datos históricos y `bajar_historicos.py` | **no hecho** |
| Licencia, protección de `main`, reparto entre las dos personas | **pendiente de las personas del proyecto** |

## 2. Congelamiento

- (dato) `congelado.json`: 244 archivos en `src/v3.1` (75), `src/v4.0` (70), `test/v3.1` (14), `test/v4.0` (12),
  `escenarios/v3.1` (25) y `escenarios/v4.0` (48). sha256 del conjunto:
  `2b32757194d2510bcbc680056f803694be064fc968e35de9c1ab579c10621106`.
- (dato) Los 244 archivos son idénticos, byte a byte, a los de la copia de trabajo de la que salieron (0 diferencias).
- `.gitattributes` desactiva toda conversión de fin de línea (`* -text`), para que el sha256 sea el mismo en Windows y en Linux.

## 3. Pruebas de los motores: línea base

| Suite | Copia original | Clon mínimo | Clon con exclusiones |
|---|---|---|---|
| v3.1 | 68 pasan, 1 falla | 68 pasan, 1 se omite; con resultados presentes, 69 pasan | 69 pasan |
| v4.0 | 133 pasan, **4 fallan**, 10 se omiten | 130 pasan, 5 fallan, 12 se omiten | 130 pasan, 12 se omiten, 5 excluidas |

- (dato) El README de v4.0 dice "140 pruebas en verde". No es lo que se midió: en la copia original fallan 4.
- (dato) De esas 4, tres son pruebas que quedaron viejas: esperan viento `windninja` en `modelo_v3` (pasó a `serie` con D41) o
  contención activa en `prueba_rapida_v4` (apartada con D42). La cuarta pide `resultados/v4.0/banco`, que no estaba en la copia.
- (dato) En el clon se suma una que pide `banco_v4/entradas/indices_extra` (64 MB), que queda para el paquete histórico.
- Las cinco están en `herramientas/pruebas_excluidas.txt` con su motivo. Las versiones están congeladas, así que sus pruebas no
  se corrigen; cualquier otra falla es un error nuevo.
- (dato) En la copia original, v3.1 tiene 1 prueba que falla (`test_api`, depende de qué resultados haya en disco). En el clon
  pasa o se omite según existan resultados. (inferencia) Es sensible al estado de la carpeta de resultados, no al código.

## 4. Corridas cortas dentro del clon

| Motor | Escenario | Resultado | Tiempo |
|---|---|---|---|
| v3.1 | `prueba_rapida_v3` (Las Lagunas 2024, 6 h) | termina bien | 6 s |
| v4.0 | `prueba_rapida_v4` (Las Lagunas 2024, 6 h) | 47,43 ha en 6 h, motivo de fin "horizonte" | 18,5 s |

- (dato) v3.1 unió sola los cuatro trozos del viento en un `.nc` de 161,3 MB la primera vez. sha256 del archivo original:
  `c260efc76eb36bd600fc9628cb9ef74237a0c9069f5be070bf188d5df2811efc`. (sin verificar) Que el archivo unido tenga ese mismo
  sha256, y que v4.0 lo una por su cuenta: cuando corrió v4.0 ya estaba unido.
- (dato) v4.0 valida su manifiesto completo en cada corrida. Sin los casos La Aguada 2023 y Potrerillos 2024 no arranca, aunque
  la corrida no los use. Por eso están en el repositorio (54 MB).

## 5. Comprobaciones técnicas

| Pregunta del plan | Resultado |
|---|---|
| ¿Sirve un solo entorno para los dos motores? | (dato) Sí en Windows: numpy 2.5.2, numba 0.68.0, rasterio 1.5.1, pandas 3.0.5 (`requirements.txt`) |
| ¿Se pueden usar los dos motores sin instalarlos? | (dato) Sí, con `PYTHONPATH`. En este equipo había un `incendios_sl` instalado desde otra carpeta y `PYTHONPATH` tuvo prioridad |
| ¿Responde el pronóstico de Open-Meteo? | (dato) Sí: `ecmwf_ifs025` y `best_match`, 288 horas (5 días atrás, 7 adelante), sin huecos de viento |
| ¿Se pueden redirigir entradas y resultados? | (dato) Sí: los dos motores leen `INCENDIOS_SL_REPO`, `_INPUT`, `_RESULTADOS`, `_RAIZ`, `_DATOS`; v4.0 además `_SIM_DATOS` y `_PROCESADOS`. `_INPUT` redirige la carpeta entera, no superpone |
| ¿El algoritmo de barreras de v3.1 acepta trazos libres? | (dato) Sí: `preparar_barreras_enlaces` ya suma líneas de `barreras_extra` con atributo `ancho_m`. Pero escribe siempre el producto del dominio y recalcula todo el dominio a 7,5 m. Hace falta una envoltura que trabaje en una ventana y escriba en otro lugar |
| ¿Se lee Sentinel-2 en AWS sin token? | (dato) Sí: catálogo Earth Search y lectura de una ventana de 512 × 512 con rasterio en 3,6 s |

## 6. Tamaños de la primera subida

(dato) 476 MB en total: datos 443 MB, documentos 34 MB, código de los motores 1,1 MB, pruebas y escenarios menos de 1 MB.
Ningún archivo supera los 50 MB.

## 7. Primera subida y primera corrida de la integración continua

- (dato) Primera subida el 2026-11-10: cambio `2e4a4fd`, 528 archivos, con las etiquetas `prerregistro-E-E3-1` a `-4` y
  `contrato-v1`.
- (dato) La primera corrida de la integración continua **falló en Windows y en Linux**, en el paso de verificación.
- (dato) Causa, reproducida en local con un clon limpio y un entorno nuevo creado por `instalar.bat`: a `requirements.txt` le
  faltaban `firebench` y `scikit-image`, que v3.1 importa. Las pruebas de v3.1 daban 2 fallas y 22 errores por
  `ModuleNotFoundError`. La lista se había armado y probado con el Python del sistema, que ya tenía esas bibliotecas; nunca se
  había probado en un entorno creado solo con ella. Fue un error de método de esta F0.
- (dato) Con las dos bibliotecas agregadas, el clon limpio con entorno nuevo pasa todo en Windows: v3.1 69 pruebas, v4.0 130
  más 5 excluidas, y las dos corridas cortas.
- (sin verificar) Linux: recién se sabrá cuando la integración continua corra con la corrección.
- Regla que queda: `requirements.txt` se valida siempre con `instalar.bat` o `./instalar.sh` sobre un clon limpio.

## 8. Cosas que conviene saber

- `datos/inputSimulacion/sim_v4/manifiesto_datos.yaml` es parte de v4.0 y guarda, como procedencia, rutas absolutas del equipo
  donde se armó (`C:\Users\Usuario\Documents\…`). Quedan a la vista en un repositorio público. No contienen claves.
- Los dos motores traen un paquete llamado `incendios_sl`. Nunca instalarlos con `pip install -e`.
- Todavía no existe `app/` con código, ni `iniciar.bat` / `iniciar.sh`: llegan con las fases F1 a F3.
