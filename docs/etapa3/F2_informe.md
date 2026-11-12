# F2 — Servidor: informe

Fecha: 2026-11-11 · Rama: `f2-servidor` · Equipo: Windows 11, Intel de 20 núcleos lógicos, 32 GB, Python 3.14.7.
Rótulos: **(dato)** medido ese día en ese equipo · **(inferencia)** · **(sin verificar)**.
Aprobaciones previas: `F2_pedido_de_aprobacion.md`, decisiones D-E3-16 a D-E3-21.

## 1. Qué pedía el plan y cómo quedó

| Criterio de aceptación de la F2 (`00_plan.md` §3) | Estado |
|---|---|
| Una corrida de 48 h se lanza, se pausa, se reanuda y se detiene desde el servidor | cumplido con los tres motores (§3.2) |
| El servidor sobrevive a la caída de un proceso motor y lo informa | cumplido, probado con el motor simulado (§3.1) |
| Pruebas del servidor sin internet | cumplido: 11 pruebas, unos 20 segundos |

| Entregable | Estado |
|---|---|
| Servidor local en `127.0.0.1`, arranque con un comando que abre el navegador | hecho (`app/servir.py`, `app/servidor/`) |
| Gestor de corridas con estado en disco | hecho; al volver a arrancar encuentra las corridas anteriores |
| Avance en vivo al navegador | hecho, por un canal de una sola vía |
| Huella para el mapa | hecha: imagen PNG ya pasada a la proyección de los mapas web, con su recuadro en grados |
| Modo "ambos" (v4.0 y v3.1 librev2 a la vez) | hecho |
| Motor simulado | hecho (`app/motores/proceso_simulado.py`) |
| Página mínima de prueba | hecha (`app/web/prueba.html`); no es la pantalla del simulador |
| Intervenciones | el pedido existe y el motor contesta "rechazada" (fase F5) |
| Bajar pronóstico e índices, perímetro por hora, exportación, modo histórico | no entran en la F2 (fases F3, F4, F6 y F7) |

## 2. Cómo funciona

- **Un proceso por corrida.** El servidor no carga ningún motor: lanza `app/motores/proceso.py`, lee sus avisos por la salida
  estándar y le escribe las órdenes por la entrada estándar, según el contrato (ahora versión 1.2).
- **Estado en disco.** Cada corrida tiene su carpeta en `resultados/app/<id>/` con `corrida.json` (lo pedido y, al final, los
  resultados), `estado.json`, `eventos.jsonl` y lo que escribe el motor.
- **Estados.** `creada` → `iniciando` → `corriendo` ⇄ `pausando` → `pausada`; al final `terminada`, `detenida`, `error` o
  `interrumpida`.
- **Límite.** Dos corridas en marcha como máximo; la tercera se rechaza con un mensaje.
- **Cierre.** Al cerrarse, el servidor pide a los motores que guarden y espera hasta 15 segundos. Una corrida que no llega a
  guardar queda `interrumpida` y no se retoma.
- **Seguridad.** Escucha solo en `127.0.0.1` y rechaza los pedidos que no vengan de su propia página (otro origen, otro
  nombre de servidor).
- **Sin bibliotecas nuevas.** Usa FastAPI y uvicorn, que ya estaban en `requirements.txt`.

Cambio a la F1 incluido acá (decisión D-E3-20): si el punto elegido cae en una celda que no quema, el motor lo corre a la
combustible más cercana al clic, sin mirar la cicatriz del evento base. (dato) Con un clic a 13 km de la cicatriz de Las
Lagunas, los dos motores lo corrieron 190 m; antes lo habrían llevado a la cicatriz.

## 3. Verificación

### 3.1 Pruebas automáticas (`test/app/test_servidor.py`)

Levantan el servidor de verdad en un puerto libre y le hablan por HTTP.

| Prueba | Motor | Resultado |
|---|---|---|
| Estado general: motores, eventos con datos, recuadro del dominio | — | pasa |
| Corrida completa: una hora por evento, estados en orden, huella PNG, retomar el canal desde un evento | simulado | pasa |
| Pausar, intervenir (rechazada) y reanudar; en pausa no avanza | simulado | pasa |
| Detener: guarda lo simulado y ya no acepta órdenes | simulado | pasa |
| Caída del proceso motor: la corrida queda en `error` con el motivo y el servidor sigue atendiendo | simulado | pasa |
| Dos corridas a la vez; la tercera se rechaza; cuando se libera lugar, entra | simulado | pasa |
| Pedidos de otra página o con otro nombre de servidor: rechazados, y no crean nada | — | pasa |
| Pedidos inválidos: motor desconocido, evento sin datos, punto fuera del dominio, hora fuera de la serie, sin horas | — | pasa |
| Al volver a arrancar, las corridas que estaban en marcha quedan `interrumpida` | — | pasa |
| Al cerrar el servidor, las corridas en marcha guardan y quedan `detenida` | simulado | pasa |
| Modo "ambos", 6 h de Las Lagunas 2024, contra la corrida offline de cada motor | v4.0 y v3.1 librev2 | 0 celdas distintas |

(dato) `herramientas/probar.py` completo: ver §3.4.

### 3.2 Los siete pares de E-E3-1, lanzados por el servidor

Comprobación de cierre (punto 23 del pedido de aprobación). **No reemplaza a la evaluación formal de E-E3-1**, que se hizo
sobre el proceso motor. Herramienta: `herramientas/e_e3_1_servidor.py`. Cada par se corrió por HTTP sin órdenes y con una pausa
y una reanudación a mitad de camino, y se comparó con la corrida offline hecha en la misma tanda.

Código: cambio de git `aad2731`, sin archivos de código sin registrar; congelado `2b327571…`. Archivo completo:
`F2_e_e3_1_por_servidor.json`.

| Escenario | Motor | Horas simuladas | Superficie final | Distintas | Distintas con pausa | Pausa en la hora |
|---|---|---|---|---|---|---|
| Caso La Aguada 2023 | v4.0 | 36 | 1.348 ha | **0** | **0** | 20 |
| Las Lagunas 2024, h1, SNMF | v4.0 | 48 | 12.839 ha | **0** | **0** | 25 |
| Las Lagunas 2024, h1, SNMF | v3.1 libre | 48 | 34.793 ha | **0** | **0** | 25 |
| Las Lagunas 2024, h1, SNMF | v3.1 librev2 | 48 | 32.915 ha | **0** | **0** | 25 |
| Las Chacras oct. 2023, alt4 | v4.0 | 72 | 2.356 ha | **0** | **0** | 37 |
| Las Chacras oct. 2023, alt4 | v3.1 libre | 45 de 72 | 1.526 ha | **0** | **0** | 37 |
| Las Chacras oct. 2023, alt4 | v3.1 librev2 | 46 de 72 | 3.065 ha | **0** | **0** | 37 |

En Las Lagunas 48 h se sumó una tercera corrida por motor, **detenida** desde el servidor a mitad de camino. Se comparó lo
que ardió antes de la hora de la detención con la misma parte de la corrida offline:

| Motor | Detenida en la hora | Celdas quemadas hasta ahí | Celdas distintas |
|---|---|---|---|
| v4.0 | 25 | 31.140 | **0** |
| v3.1 libre | 25 | 101.115 | **0** |
| v3.1 librev2 | 25 | 122.274 | **0** |

- (dato) 0 celdas distintas en los siete pares, sin pausa y con pausa, y en las tres corridas detenidas.
- (dato) Las superficies y las horas simuladas son las mismas que en la evaluación formal de E-E3-1.
- La corrió quien escribió el código. Si la otra persona puede, la repite con `python herramientas/e_e3_1_servidor.py`
  (unos 20 minutos).

### 3.3 En el navegador

(dato) Con `python app/servir.py --con-simulado`, desde la página de prueba se lanzó Las Lagunas 2024 en modo "ambos", 12 h:
las dos corridas terminaron (v4.0, 370 ha; v3.1 librev2, 1.261 ha), los avisos llegaron hora por hora y la huella se dibujó.
Sin errores en la consola del navegador.

### 3.4 Verificación completa del clon

(dato) `python herramientas/probar.py`, sobre el cambio `aad2731`: "Todo funciona."

| Paso | Resultado |
|---|---|
| Versiones congeladas | 244 archivos intactos |
| Pruebas de v3.1 | 69 pasan |
| Pruebas de v4.0 | 130 pasan, 12 se omiten, 5 excluidas con motivo (igual que en la F0) |
| Corridas cortas de los dos motores | bien |
| Pruebas del simulador (`test/app`) | 32 pasan, 2 se omiten: 21 de procesos motor y 11 del servidor |

Toda la verificación tarda unos 4 minutos en este equipo.

## 4. Lo que se encontró

- **Celdas en el minuto exacto de la detención (v4.0).** (dato) La primera comparación de la corrida detenida tomaba las
  celdas con tiempo de llegada "hasta" el minuto de la detención y dio 7 celdas distintas de 31.147 en v4.0. Las 7 tienen
  tiempo de llegada igual a ese minuto: las enciende el paso que empieza ahí, y la corrida detenida no llega a darlo. Se
  cambió la comparación a "antes de" ese minuto. No es una diferencia del modelo; es dónde cae el corte. Queda dicho porque
  el criterio se ajustó después de ver el resultado.
- **La pausa pedida por HTTP llega una hora o dos después.** (dato) Pedida al recibir la hora 24, la pausa cayó en la hora 25
  en los tres motores (en v3.1, pedida directo al proceso, caía en la 24). El pedido viaja por HTTP mientras el motor sigue
  avanzando; se atiende en la siguiente hora en punto. Con v3.1, que simula una hora en un tercio de segundo, el usuario va a
  ver que la pausa "se pasa" una o dos horas. Es lo que dice el contrato; conviene que la pantalla lo muestre (estado
  `pausando`).
- **`localhost` y `127.0.0.1`.** El servidor acepta los dos nombres. (dato) Probado con `localhost` en el navegador y con
  `127.0.0.1` en las pruebas.

## 5. Límites y cosas sin verificar

- (sin verificar) **Linux.** Todo se corrió en Windows. La integración continua lo corre en Linux al subir la rama.
- (sin verificar) **Ctrl+C en una consola real.** El cierre ordenado se probó llamando al cierre del servidor desde las
  pruebas, con el motor simulado. No se probó apretando Ctrl+C con un motor real en marcha.
- (sin verificar) **Memoria total del modo "ambos"** en una corrida larga (prerregistro E-E3-3). (inferencia) Por los picos
  de cada proceso medidos por separado, unos 0,5 GB de v4.0 más 0,9 GB de v3.1.
- (sin verificar) Varios navegadores mirando la misma corrida a la vez, y corridas de más de 72 horas.
- La caída del proceso motor se probó con el motor simulado, no matando un motor real.
- La página de prueba muestra el dominio entero y la huella se ve chica; es para probar, no para usar.
- El servidor no tiene usuarios ni contraseñas: está pensado para una sola computadora.
- Los datos siguen saliendo de un evento con ficha (Las Lagunas 2024 o Las Chacras octubre 2023).

## 6. Lo que sigue

1. Revisión de la rama `f2-servidor` por la otra persona y unión a `main` (decisión D-E3-17: se revisa al final).
2. F3, la pantalla: mapa, clic de ignición, línea de tiempo, comparación entre motores.
3. F4, datos bajados en el momento, y con ellos el primer evento generado.
4. Pendientes de siempre: licencia del código, protección de `main`, quién evalúa E-E3-2, E-E3-3 y E-E3-4.
