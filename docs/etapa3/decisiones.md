# Decisiones de la Etapa 3

Registro de decisiones del simulador interactivo. Cada entrada: qué se decidió, quién y cuándo, y qué se descartó.
El detalle y la justificación están en `00_plan.md` §8. Una decisión se cambia con una entrada nueva, nunca editando la vieja.

## 2026-11-10 — Aprobación del plan

El usuario aprobó las doce decisiones del plan, con dos correcciones (D-E3-06 y D-E3-09) y dos confirmaciones (repositorio y
datos).

| Código | Decisión | Estado |
|---|---|---|
| D-E3-01 | Motores y configuraciones congeladas: v4.0 `modelo_v3` variante `barreras` (línea principal); v3.1 `modelo_v2` librev2 y `modelo_v1` libre (control). Congelados con `congelado.json`: 244 archivos, sha256 del conjunto `2b32757194d2510bcbc680056f803694be064fc968e35de9c1ab579c10621106` | aprobada |
| D-E3-02 | Programa Python local con interfaz en el navegador; un proceso por motor; servidor solo en `127.0.0.1`. Descartado: HTML único con los motores traducidos a JavaScript | aprobada |
| D-E3-03 | v3.1 con la biblioteca WindNinja completa y velocidad escalar; v4.0 con serie y factor topográfico. No hace falta WindNinja instalado | aprobada |
| D-E3-04 | Pausa en hora en punto; intervenciones solo en pausa; cortafuegos recortados a celdas no afectadas | aprobada |
| D-E3-05 | Sin promedio entre motores; envolvente y aviso de discrepancia (IoU entre huellas menor que 0,5 a las 24 h) | aprobada |
| D-E3-06 | Solo computadoras y navegador de escritorio, **con Windows o con Linux** | aprobada, **corregida por el usuario**: se agrega Linux |
| D-E3-07 | Pronóstico Open-Meteo `ecmwf_ifs025` con `best_match` de respaldo, 16 puntos, 5 días hacia atrás | aprobada |
| D-E3-08 | Índices por Sentinel-2 L2A en AWS sin token como vía principal; compuesto de ventana de 45 días y mensuales de verano; GEE opcional | aprobada |
| D-E3-09 | **No hay v5.0.** La última versión del modelo es la v4.0. Lo nuevo vive en GitHub como `app/`, sin número de versión del modelo. En esta etapa no se abren los eventos no vistos X-49 | aprobada, **corregida por el usuario**: se elimina el nombre "v5.0" |
| D-E3-10 | Repositorio nuevo `deinagutierrez/simulador-incendios`, público, como único lugar de trabajo y distribución, en lugar de Drive y del repositorio viejo `gvcosta/Gemelos_Digitales_Incendios_UNSL`. Datos mínimos dentro, viento partido en cuatro, sin Git LFS | aprobada |
| D-E3-11 | Todos los datos se pueden publicar (confirmado por el usuario): red MT de EDESAL, cuarteles, registros del SNMF, viviendas y caminos. Fuentes y atribuciones en `DATOS.md` | aprobada. **Pendiente: licencia del código** |
| D-E3-12 | Trabajo de dos personas en dos frentes (motores y datos; servidor e interfaz), `main` protegida, revisión cruzada, prerregistros etiquetados en git | aprobada. **Pendiente: usuario de GitHub de la segunda persona y protección de `main`** |

También aprobado: los umbrales propuestos para el prerregistro E-E3-2 (índices por AWS contra GEE).

## Pendientes que solo pueden resolver las personas del proyecto

1. Licencia del código (el repositorio no tiene archivo `LICENSE`).
2. Nombre y correo de git para registrar los cambios, y permiso de escritura en el repositorio.
3. Protección de la rama `main` y revisión obligatoria (ajustes del repositorio, los hace la dueña).
4. Quién toma cada frente y quién escribe y quién evalúa cada prerregistro.
5. Si se traen a este repositorio `reporte_avance.md` y `decisiones.md` de las etapas anteriores.
