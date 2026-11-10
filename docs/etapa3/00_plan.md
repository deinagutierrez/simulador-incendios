# Etapa 3 — Plan de trabajo: simulador interactivo en tiempo real

Fecha: 2026-11-10 · Estado: **plan aprobado el 10/11; fase F0 en curso** (ver `F0_informe.md` y `decisiones.md` en esta carpeta).
Repositorio: `https://github.com/deinagutierrez/simulador-incendios` (público).

**No existe una "v5.0".** La última versión del modelo es la v4.0. Lo nuevo es un programa que conduce a los motores v3.1 y
v4.0 sin cambiarlos, y vive en este repositorio con nombre propio: carpeta `app/` para el código, `test/app/` para sus pruebas
y `docs/etapa3/` para sus documentos. Sus versiones se marcan con etiquetas de git (`1.0.0`, …).

**Cambios respecto de la primera versión del plan (5/11)**, decididos por el usuario el 10/11:

1. **Programa Python local con la interfaz en el navegador**, en lugar de un único HTML con los motores traducidos a JavaScript.
   Corren los motores reales de v3.1 y v4.0, sin traducción.
2. **WindNinja completo**: v3.1 usa su biblioteca de 72 direcciones tal como está. No hace falta tener WindNinja instalado.
3. **NDVI/NDMI sin token**: la vía principal pasa a ser Sentinel-2 L2A público en AWS, leído desde Python. Google Earth Engine
   queda como alternativa cuando hay credenciales.
4. **Solo computadoras, con Windows o con Linux**: se elimina todo lo referido a celulares.
5. Correcciones de datos: ventana de 45 días previos para los índices (método de v3.1 y de v4.0 con eventos estándar), fórmulas
   de NDMI distintas según el producto, y viento escalar de v3.1.
6. **GitHub en lugar de Drive**: el trabajo vive en un repositorio de GitHub. Cualquiera tiene que poder clonarlo, instalar y
   que funcione (§2.8). Se deja de copiar carpetas a Drive y de listar archivos cambiados.
7. **Equipo de dos personas**: reparto por frentes, revisión cruzada y calendario en §3.1.

Las carpetas `src/v3.1`, `src/v4.0` y sus pruebas y escenarios están en el repositorio tal como eran, porque el simulador
ejecuta ese código. Quedan congeladas: no se modifica ningún archivo suyo y la integración continua lo controla con
`congelado.json` (sha256 por archivo).

**Sobre qué se basa.** La copia de trabajo de la que salió este repositorio no incluía `Contexto/informes/reporte_avance.md`
ni `decisiones.md` (el informe de síntesis los cita en `D:\informes\`). El estado se reconstruyó desde `docs/v3.1` a `v3.4`,
`docs/v4.0/14` a `31`, `INFORME_TECNICO_MOTOR_V4.md`, el protocolo v1.3 (`docs/v4.0/16`), el código de `src/v3.1` y
`src/v4.0` y los datos de `datos/inputSimulacion`. Las decisiones de esta etapa están en `docs/etapa3/decisiones.md`.

Etiquetas: **[DATO]** medido o leído en el repositorio · **[VERIFICADO 10/11]** probado en esta máquina ese día ·
**[ESTIMACIÓN]** cálculo propio, a medir en la fase indicada · **[SUPUESTO]** sin verificar · **[DECISIÓN]** a aprobar.

---

## 1. Resumen y alcance

### 1.1 Qué se construye

Un programa que se inicia con un comando en la computadora, abre el navegador en `http://localhost:8000` y permite:

1. ver el dominio Las Lagunas–Potrerillos (EPSG:5345, 30 m, 1.672 × 1.671 celdas, 2.500 km²) con topografía, caminos, viviendas
   y red eléctrica;
2. bajar la meteorología actual y el pronóstico (Open-Meteo) y los índices NDVI/NDMI recientes (Sentinel-2 en AWS, sin token);
3. elegir la ignición con un clic, el viento (manual o pronóstico), cortafuegos dibujados a mano alzada y las horas a simular;
4. correr **v4.0 `modelo_v3`** (línea principal) y **v3.1 `modelo_v1` / `modelo_v2`** (simulación libre y librev2, control),
   cada uno en su propio proceso, con propagación libre más barreras y sin combate;
5. ver el avance animado, la superficie en ha y km², el tiempo simulado y de cómputo, la exposición (viviendas, red, caminos)
   y la bitácora de intervenciones; recorrer la corrida con una línea de tiempo y exportarla para reproducirla.

### 1.2 Qué entra y qué queda fuera

| Entra | Queda fuera (y por qué) |
|---|---|
| Motores reales v3.1 y v4.0 en procesos Python, configuración congelada | **Traducción de los motores a JavaScript y HTML único autónomo**: descartado en esta etapa. La interfaz se escribe en HTML/JS igual, así que queda reutilizable si más adelante se quiere |
| Uso en computadoras de escritorio y portátiles con Windows o Linux y navegador actual (Chrome, Edge, Firefox) | **Celulares y tabletas**: no se diseña ni se prueba para ellos |
| Un usuario por computadora; el servidor escucha solo en `127.0.0.1` | Servidor compartido en red o en la nube, cuentas de usuario |
| Distribución por GitHub: clonar, instalar e iniciar | Copias por Drive |
| Propagación libre y barreras (caminos y cortafuegos) | **Combate, contención y despacho**: D42 los apartó; la Fase 2 está pausada (docs/v4.0/17, 18 §2). El tiempo de arribo de cuarteles se muestra como capa informativa |
| Biblioteca WindNinja existente (72 direcciones, 100 m) | Regenerar la biblioteca: solo hace falta WindNinja instalado para otro dominio, otro relieve u otra física |
| Sentinel-2 por AWS sin token; GEE opcional | Estaciones del SMN/INTA: no hay estaciones en el proyecto (D28) |
| Dominio único, grilla fija | Otros dominios (protocolo §3.5) |
| Pavesas y modo estocástico apagados | Están descartados (D50) o sin revisar |
| Verificación de que el programa reproduce las corridas offline; modo histórico sobre eventos vistos | Abrir los cinco eventos no vistos (X-49): se "queman" una vez por versión congelada y esta etapa no cambia el modelo (§6.4) |

### 1.3 Resultado esperado al cierre

- Repositorio de GitHub al día, con todo lo necesario para que un clon nuevo funcione en una computadora limpia, y una
  integración continua que lo comprueba en cada cambio.
- `app/` con el servidor, la interfaz web, los procesos de motor y el instalador; `test/app/` en verde sin red.
- `docs/etapa3/01_verificacion.md` con la ficha de comparabilidad y los prerregistros E-E3-1 a E-E3-4 evaluados.
- `docs/etapa3/02_guia_de_uso.md` con instalación, uso y límites del modelo.
- **El modelo no cambia**: El simulador no recalibra nada.

---

## 2. Arquitectura

### 2.1 Vista general

```
 ┌──────────────────────────── Computadora del usuario (Windows o Linux) ─────────────────────┐
 │                                                                                             │
 │  Navegador  http://localhost:8000                                                           │
 │  ┌───────────────────────────────────────────────┐                                          │
 │  │ Interfaz (HTML + JS, Leaflet)                 │                                          │
 │  │  mapa y capas · panel · clic de ignición ·    │                                          │
 │  │  dibujo de cortafuegos · línea de tiempo ·    │                                          │
 │  │  resultados · bitácora                        │                                          │
 │  └───────────────▲───────────────────────────────┘                                          │
 │                  │ HTTP (pedidos) + eventos de avance, solo 127.0.0.1                        │
 │  ┌───────────────▼───────────────────────────────┐        ┌──────────────────────────────┐  │
 │  │ Servidor (FastAPI, paquete `gemelo_sl`)  │ lanza  │ Proceso motor v4.0           │  │
 │  │  · sirve la interfaz y las capas              ├───────►│  PYTHONPATH = src/v4.0/src   │  │
 │  │  · datos dinámicos: Open-Meteo, Sentinel-2    │ y      │  `simulador` + `incendios_sl`│  │
 │  │  · caché en disco con procedencia y sha256    │ manda  ├──────────────────────────────┤  │
 │  │  · gestor de corridas y bitácora              ├───────►│ Proceso motor v3.1           │  │
 │  │  · no importa ningún motor                    │ órdenes│  PYTHONPATH = src/v3.1/src   │  │
 │  └───────────────┬───────────────────────────────┘        │  `incendios_sl` (numba)      │  │
 │                  │                                        └──────────────┬───────────────┘  │
 │   datos/inputSimulacion (dem, viento WindNinja, barreras, infraestructura, cobertura)       │
 │   datos/procesados/app (caché de pronóstico e índices) · resultados/app/<corrida>         │
 └──────────────────┼──────────────────────────────────────────────────────────────────────────┘
                    │ internet (solo para datos dinámicos)
        Open-Meteo (pronóstico)        Earth Search + AWS (Sentinel-2 L2A, sin token)
```

**Por qué un proceso por motor.** Los dos motores traen un paquete Python con el mismo nombre, `incendios_sl`, con contenido
distinto **[DATO: `src/v3.1/src/incendios_sl`, `src/v4.0/src/incendios_sl`]**. No pueden convivir en un mismo proceso. Separados,
cada uno importa su versión congelada sin tocarla. Además aísla fallos, permite correr los dos a la vez en el modo "ambos" y
simplifica pausar y detener. El servidor de v3.1 ya trabaja así: lanza cada simulación con `subprocess` y guarda el estado en
disco (`api/trabajos.py`).

### 2.2 Flujo de una corrida

```
 configurar ─► preparar insumos ─► lanzar proceso motor ─► bucle por hora simulada ─► fin
   ignición      meteo y humedad     carga con las           motor avanza 1 h           Detener o
   viento        índices → mapa de   funciones de su         ├─ manda avance al         horas cumplidas:
   cortafuegos   combustible, vivo,  versión congelada       │  servidor → navegador     guarda resultados
   horas         curado (cada motor                          └─ atiende órdenes:         y bitácora
   motor         con sus funciones)                             pausar, intervenir,
                                                                reanudar, detener
```

**Corrida en tiempo real como "evento generado".** Los cargadores de los dos motores trabajan por evento: una ficha YAML más
archivos con nombres fijos (`cargar_entradas_evento` en v3.1, `insumos_evento` en v4.0). El simulador genera una ficha `RT-<fecha>-<n>`
y escribe sus insumos (meteo del dominio, índices a 30 m, año de cobertura) en el formato estándar. Así los cargadores
congelados funcionan sin cambios, igual que se hizo con los cinco eventos de X-49 (`preparar_evento_desde_banco.py`). Dónde se
escriben esos archivos (carpeta propia del simulador con las variables `INCENDIOS_SL_*`, o subcarpetas `RT-` dentro de
`datos/inputSimulacion`) se decide en F0 después de comprobar qué rutas admiten redirección **[DECISIÓN técnica de F0]**.

### 2.3 Qué se reutiliza de cada motor y cómo se eligen

| Pieza | v3.1 | v4.0 | En el simulador |
|---|---|---|---|
| Motor | `simulation/motor.py` + `automata.py` (numba, 16 vecinos, paso 60 s) | `simulador/ca/automata.py` + `corrida.py` (numpy, 8 vecinos, paso 2 min, sub-pasos CFL, Huygens) | se ejecutan tal cual, cada uno en su proceso |
| Combustible | 7 clases (`fuels/clasificacion.py`, `tabla_combustibles_v1.csv`, k 0,75 / 2 / 5) | 40 modelos SB40, regla 3.3b (`fuel/generar_sb40.py`) | cada motor arma su mapa con sus funciones, a partir de los mismos índices y cobertura |
| Humedad muerta | retardo de Simard, serie precalculada (`fuels/humedad.py`), extinción con 15 mm en 24 h | retardo de Simard NFDRS dentro del autómata, sin extinción por lluvia | ídem |
| Viento | **biblioteca WindNinja** × velocidad **escalar** media de 16 puntos; dirección vectorial (`viento.fuente_horaria: escalar`) | serie uniforme + factor topográfico (D41); `viento: windninja` disponible como opción | cada motor con su configuración congelada |
| Barreras | por enlace, códigos precalculados a 7,5 m (`preparar_barreras_enlaces`) | caminos rasterizados + `barreras.extra` (GeoJSON con `ancho_m`) | caminos: sin cambios. Cortafuegos del usuario: §2.6 |
| Servidor y visor | `api/app.py`, `api/trabajos.py`, `api/capas.py`, `web/` (eventos históricos, capas PNG, corrida por subproceso) | `scripts/exportar_visor_v31.py` (traduce salidas de v4 al formato de v3.1) | **base del servidor y de la interfaz del simulador** (copiados al paquete nuevo, no importados) |
| Datos | `meteorology/openmeteo.py` (ya admite `tipo: pronostico`), `remote_sensing/gee_indices.py` | `app/preprocesamiento/descargar_ndvi_ndmi_gee.py` | cliente de pronóstico reutilizado; módulo nuevo para Sentinel-2 en AWS |

**Configuraciones congeladas** (D-E3-01): v4.0 `modelo_v3` variante `barreras` (viento `serie`, regla 3.3b, `limite_viento`
andrews_2013, `k_global` 1, pavesas y contención apagadas, sin parada en cicatriz); v3.1 `modelo_v2` librev2 (barreras de
caminos activas, contención apagada) y `modelo_v1` libre. Son las de los lotes de comparación (E058, docs/v4.0/31 §7.2).

**Cómo se elige.** Selector con tres opciones y un modo "ambos" que lanza los dos procesos y dibuja las dos huellas. No se
promedian: el control v3.1 contra v4 dio R3, no concluyente (IoU mediana 0,483 contra 0,360, X-46), y en el evento no visto
Chacras octubre 2023 v3.1 se adelanta mientras v4 se atrasa (docs/v4.0/31 §7.2). La combinación que se muestra es la
envolvente: unión (escenario conservador) e intersección (coincidencia), con un aviso cuando el IoU entre huellas a 24 h es
menor que 0,5 **[umbral SUPUESTO, D-E3-05]**.

### 2.4 Control de la corrida sin tocar las versiones cerradas

Cada proceso motor es un script del simulador (`gemelo_sl/motores/proceso_v31.py`, `proceso_v40.py`) que importa su versión congelada
y la envuelve:

- **v3.1**: subclase de `Simulacion` que redefine `_tablas_hora`. Ese método se llama al comenzar cada hora simulada, antes de
  calcular el viento de esa hora (`motor.py:386-398`), así que es el punto para atender órdenes. El viento manual se aplica
  envolviendo la función `viento` de las entradas; los cortafuegos, modificando en memoria `barrera` y `ancho_tab`.
- **v4.0**: subclase de `Automata` que redefine `paso_tiempo` y atiende órdenes cuando el reloj cae en hora en punto. En el
  proceso del simulador se sustituye `simulador.corrida.Automata` por la subclase antes de llamar a `ejecutar` (no se edita ningún
  archivo de v4.0). El viento manual se aplica editando la serie horaria en memoria; los cortafuegos, con
  `rasterizar_barreras_extra` y actualizando las tablas derivadas del autómata (`factor_carga`, `es_camino`, `estado`) en las
  celdas tocadas.

Comunicación servidor ↔ proceso: órdenes y avances como líneas JSON por la entrada y salida estándar; la huella de cada hora se
deja en disco (`t_llegada` parcial) y el servidor la convierte en la imagen que pide el navegador, como hoy `api/capas.py`.

**Pausar** siempre cae en hora en punto simulada: el motor termina la hora en curso y espera. A 0,2–3 s de cómputo por hora
simulada **[DATO, §2.7]** el usuario lo percibe como inmediato.

### 2.5 Interfaz

Se parte de `src/v3.1/web/` (Leaflet, capas del servidor, línea de tiempo, gráficos) y del visor autónomo
(`visor_plantilla.html`). Pantalla de escritorio, ancho mínimo 1.280 px. Requisitos (lista de aceptación de F3):

1. Mapa con capas conmutables: relieve sombreado, pendiente, caminos, viviendas, red MT, cuarteles y tiempo de arribo, NDVI,
   NDMI, mapa de combustible (SB40 o 7 clases según el motor), cobertura MapBiomas, máscara del dominio, quemado simulado
   (acumulado y última hora), cortafuegos; en modo histórico, cicatriz y focos VIIRS. Mapa base en línea opcional (OSM, Esri).
2. Panel lateral: resumen de la configuración (motor, ignición, hora, viento, horas, fecha de los índices y del pronóstico,
   cortafuegos), zona de datos (actualizar pronóstico e índices, cargar archivos propios), botones Iniciar / Pausar / Detener /
   Reiniciar, estado del proceso (hora simulada, celdas activas, segundos por hora simulada).
3. Línea de tiempo: barra de progreso durante la corrida y deslizador paso a paso al terminar.
4. Salidas: superficie en ha y km², tiempo simulado y de cómputo, motivo de fin, exposición (viviendas afectadas y amenazadas
   a 100 m, km de red MT, km de caminos), medidas de mitigación (cortafuegos con longitud y ancho, cambios de viento con su
   hora, pausas), gráfico de ha contra tiempo.
5. Exportar: carpeta de la corrida (`resultados/app/<corrida>/` con los mismos archivos que una corrida offline),
   `corrida.json` (Anexo C), perímetros por hora en GeoJSON, visor autónomo con el formato de v3.1 (`exportar_visor`).

### 2.6 Cortafuegos a mano alzada e intervenciones durante la simulación

**Dibujo.** Herramienta sobre el mapa: trazo libre con el ratón, borrador y deshacer; ancho a elegir entre 3, 6, 10, 15 y 25 m
(los de `barreras.ancho_m` de `modelo_v2.yaml`). Cada trazo se guarda como polilínea en EPSG:5345 con su ancho, que es lo
reproducible; la longitud informada es la de la polilínea.

- En **v4.0** el trazo entra como `barreras.extra`, la vía que el motor ya tiene: mismo cruce por longitud de llama que los
  caminos.
- En **v3.1** se usa el mismo algoritmo que para los caminos (`preparar_barreras_enlaces`, detección de cruces a 7,5 m) aplicado
  a los trazos. Al ser el código real de v3.1, no hay aproximación. Si la función solo acepta las capas del dominio, en F1 se
  escribe una envoltura que le pase los trazos **[a confirmar en F0]**. La variante libre (`modelo_v1`, sin barreras) arranca con
  una matriz de barreras vacía para poder recibir cortafuegos; se prueba que eso da el mismo resultado que barreras apagadas.
- Opción "a suelo mineral" por trazo: además de barrera, la celda queda sin combustible (`modificador_combustible` de v4;
  en v3.1, clase 0). Rotulada como supuesto.

**Durante la simulación.** Viable en los dos motores, con la corrida en pausa (D-E3-04):

| Intervención | v3.1 | v4.0 | Reproducción offline |
|---|---|---|---|
| Viento manual | cambia de golpe en la hora de la pausa (el motor usa un valor por hora) | gira en forma gradual durante la hora siguiente (el motor interpola entre valores horarios; se edita la serie desde la hora siguiente para no alterar lo ya simulado) | serie meteorológica editada por horas |
| Cortafuego nuevo | activo desde la hora de la pausa; se recorta a celdas todavía no afectadas | ídem | el mismo trazo cargado desde el inicio: como el fuego no había tocado esas celdas, el resultado es igual (se verifica en E-E3-4) |
| Más horas | extiende el horizonte si el pronóstico cubre | ídem | `horas` del escenario |
| Cambiar motor, ignición o índices | no se admite en una corrida iniciada: exige Reiniciar | ídem | — |

**Bitácora.** Cada intervención se registra como `{n, t_sim_min, t_vigor_min, tipo, datos, hash}`. El `hash` encadena cada
entrada con la anterior y con la configuración inicial, de modo que una corrida exportada no se puede editar sin que se note.
Reproducir es "configuración inicial + bitácora en orden"; una prueba automática lo exige idéntico (§6.3).

### 2.7 Rendimiento y requisitos de la computadora

Tiempos de los motores reales **[DATO, `registro.json` de Las Chacras octubre 2023, punto alt4, 06 UTC]**:

| Motor | Horas simuladas | Superficie final | Cómputo | Por hora simulada | Memoria pico |
|---|---|---|---|---|---|
| v3.1 librev2 | 46 | 3.065 ha | 10,4 s | 0,23 s | 0,92 GB |
| v4.0 libre (sin parada) | 141 | 29.319 ha | 381,7 s | 2,7 s | sin medición individual |

Otros datos de v4.0 **[DATO, informe técnico §3.12]**: mediana de 60 s por corrida en los 9 eventos menores; Las Lagunas 2024
con barreras, 148 s por 59,9 h. La memoria por proceso de v4.0 no está medida; con 5 procesos a la vez el equipo usó 11,6 GB
(unos 2,3 GB por proceso si se reparte parejo, **[SUPUESTO]**). Se mide en F1 (E-E3-3).

Requisitos **[ESTIMACIÓN, se confirman en F7]**: Windows 10 u 11, o una distribución de Linux reciente, de 64 bits; Python 3.12
o superior con las bibliotecas de `requirements.txt` de la raíz. Un solo entorno sirve para los dos motores **[VERIFICADO
10/11 en Windows 11 con Python 3.14.7]**; en Linux lo comprueba la integración continua, y hasta que corra por primera vez es
**[SUPUESTO]**. Indicio a favor: los lotes de v4.0 se corrieron en un equipo donde dos corridas murieron con código −9
(informe técnico §3.12), que es una señal propia de Linux; 8 GB de RAM como mínimo y 16 GB para el
modo "ambos"; 0,5 GB de disco para los datos del dominio (DEM 74 MB, viento 165 MB, infraestructura 35 MB, más cobertura,
barreras e índices) y 1,5 GB si se incluyen los eventos históricos.

### 2.8 Repositorio en GitHub: clonar y que funcione

**Repositorio nuevo** (decisión del usuario del 10/11, D-E3-10). No se usa el que cita el proyecto,
`gvcosta/Gemelos_Digitales_Incendios_UNSL`, que quedó en v2.0 (último cambio 16/10/2026, solo `src/v1.0` y `src/v2.0`, sin
licencia ni flujos de Actions **[VERIFICADO 10/11]**) y sigue como archivo histórico. El nuevo es
`deinagutierrez/simulador-incendios`, público, creado el 10/11/2026. El usuario confirmó ese día que todos los datos se pueden
publicar (D-E3-11). Al ser público, la integración continua es gratuita.

**Qué versiones entran.** Solo lo que el programa necesita para funcionar: `src/v3.1` y `src/v4.0` (los motores congelados),
`app/`, y sus pruebas, escenarios y documentos, más los documentos de versiones anteriores a los que esos remiten
(`docs/v3.0`, que tiene la metodología). Las demás versiones (v2.0, v3.0, v3.2 a v3.4) se quedan en Drive y en el repositorio
viejo como archivo; se pueden sumar después sin tocar nada **[DECISIÓN de F0]**. La primera subida es una copia exacta de esas
carpetas, con su sha256 registrado: es el punto de congelamiento de v3.1 y v4.0.

**Qué va al repositorio y qué no.** Tamaños de la copia actual **[DATO]**: código de todas las versiones 15 MB, pruebas y
escenarios menos de 1 MB, documentos 75 MB, datos 1.680 MB, resultados 2.205 MB en 8.892 archivos.

| Contenido | Tamaño | Dónde | Motivo |
|---|---|---|---|
| Código (`src/v3.1`, `src/v4.0`, `app/`), pruebas, escenarios, documentos | menos de 90 MB | en el repositorio | es lo que se versiona |
| Datos mínimos: dominio (DEM y derivados, infraestructura, cobertura, barreras, viento, tablas, `sim_v4`), el evento de ejemplo Las Lagunas 2024 y los dos casos de prueba que el manifiesto de v4.0 exige para arrancar | 390 MB **[MEDIDO 10/11]** | **en el repositorio** | sin ellos los motores no arrancan; así un clon funciona sin pasos extra. v4.0 valida su manifiesto completo en cada corrida, por eso entran los casos La Aguada 2023 y Potrerillos 2024 |
| Biblioteca de viento (161 MB) | 161 MB | en el repositorio, **partida en cuatro archivos** de hasta 45 MB | GitHub rechaza archivos de más de 100 MB y avisa desde 50 MB; es el único que lo supera. Los dos motores unen solos los archivos `.part00`, `.part01`, … la primera vez que se usan (`config.py`, `unir_partes`) **[VERIFICADO 10/11 con v3.1]** |
| Eventos históricos (meteorología, índices y combustibles por evento, compuestos mensuales 2023–2024, banco) | ~1,3 GB | **publicación de GitHub** (archivo adjunto), bajado por un script con verificación sha256 | solo los necesita el modo histórico; mantiene liviano el clon |
| Resultados de corridas (`resultados/`) | 2,2 GB | **no se suben**; `.gitignore` | son regenerables. Las pocas corridas de referencia de la verificación van en la publicación |
| Caché de pronóstico e índices (`datos/procesados/app/`) | variable | no se sube | se baja en cada computadora |
| Claves (FIRMS, GEE) | — | nunca | por variables de entorno, como hoy `FIRMS_MAP_KEY` |

No se usa Git LFS: su cuota gratuita de almacenamiento y de descargas es chica y cada clon la consume **[SUPUESTO sobre la
cuota vigente]**. La primera subida pesa 476 MB **[MEDIDO 10/11]**, dentro de lo que GitHub recomienda.

**Camino de quien clona** (criterio de aceptación de F7):

```
git clone https://github.com/deinagutierrez/simulador-incendios.git
cd simulador-incendios
instalar.bat   (Windows)      ./instalar.sh   (Linux)
               crea el entorno .venv, instala las bibliotecas con versiones fijas y comprueba que todo funciona
iniciar.bat    (Windows)      ./iniciar.sh    (Linux)
               arranca el servidor y abre el navegador en localhost   [llega con las fases F2 y F3]
```

`instalar` existe desde F0 y termina con `herramientas/probar.py`: versiones congeladas intactas, datos presentes, pruebas
de los dos motores y una corrida de 6 horas con cada uno. El modo histórico agregará un paso opcional:
`python herramientas/bajar_historicos.py`.

Los motores **no se instalan con `pip install -e`**: los dos paquetes se llaman `incendios_sl` y se pisarían. Se usan por
`PYTHONPATH`, cada uno en su proceso.

**Integración continua** (GitHub Actions, `.github/workflows/pruebas.yml`, en máquinas limpias con **Windows y con Linux**):

- en cada cambio: `herramientas/probar.py` completo. Cuando exista `test/app/`, se suma;
- un control que falla si el cambio toca `src/v3.1`, `src/v4.0` o sus escenarios: es la regla de "versiones cerradas", ahora
  automática;
- al etiquetar una versión: arma la publicación con los datos históricos y su lista de sha256.

**Reglas de trabajo en el repositorio:**

- rama `main` protegida: solo entra código por pedido de integración, con la aprobación de la otra persona y las pruebas en
  verde;
- una rama por tarea; las tareas y los hitos H0 a H6 se llevan como incidencias e hitos de GitHub;
- **prerregistros**: cada `PRERREGISTRO.md` se sube y se etiqueta (`prerregistro-E-E3-1`, …) antes de escribir el código que
  evalúa. El identificador del cambio y la fecha que guarda GitHub reemplazan al sha256 anotado a mano;
- **decisiones y bitácora**: `decisiones.md` y `reporte_avance.md` pasan al repositorio (`docs/etapa3/`), para que los dos
  puedan escribir y quede historial. Hoy no están en esta copia;
- un `LICENSE` para el código y un `DATOS.md` con la fuente y la licencia de cada capa (D-E3-11).

---

## 3. Fases, entregables, hitos y esfuerzo

Esfuerzo en días-persona **[ESTIMACIÓN]**. El trabajo lo hacen dos personas; el reparto y el calendario están en §3.1.

| Fase | Entregable | Depende de | Criterio de aceptación | Esfuerzo |
|---|---|---|---|---|
| **F0 Repositorio, congelar y preparar** | plan aprobado; **repositorio nuevo creado** con la primera subida (motores congelados, datos mínimos, viento partido, `.gitignore`, `LICENSE`, `DATOS.md`), rama `main` protegida e integración continua funcionando (§2.8); publicación con los datos históricos; decisiones §8 en `docs/etapa3/decisiones.md`; sha256 de `src/v3.1` y `src/v4.0`; prerregistros E-E3-1 a 4 subidos y etiquetados (Anexo B); entorno único verificado (las suites `test/v3.1` y `test/v4.0` pasan); **contrato entre los dos frentes fijado** (Anexos C y D); comprobaciones técnicas: redirección de rutas, envoltura de `preparar_barreras_enlaces`, llamada de prueba a Open-Meteo pronóstico | — | un clon nuevo en una máquina limpia pasa las suites de v3.1 y v4.0 en la integración continua; prerregistros etiquetados antes de escribir código de motor; decisión tomada sobre dónde viven los insumos `RT-` | 7 d |
| **F1 Procesos motor** | `proceso_v40.py` y `proceso_v31.py`: corrida desde un evento generado, avance por hora, órdenes pausar / reanudar / detener, huella parcial en disco, salidas iguales a las de una corrida offline | F0 | **E-E3-1**: sin intervenciones, el proceso da el mismo `t_llegada` que `correr_escenario.py` de su versión en los 3 escenarios fijados (0 celdas distintas); pausar y reanudar no cambia el resultado; medición de tiempo y memoria de E-E3-3 | 8 d |
| **F2 Servidor** | paquete `gemelo_sl` (FastAPI): interfaz y capas, gestor de corridas con estado en disco, canal de avance al navegador, bitácora, `servir.py` que abre el navegador; solo `127.0.0.1` | F1 | una corrida de 48 h se lanza, se pausa, se reanuda y se detiene desde la API; el servidor sobrevive a la caída de un proceso motor y lo informa; pruebas de API sin red | 5 d |
| **F3 Interfaz** | mapa, capas, panel, ignición por clic, horas, selector de motor, línea de tiempo, salidas, exportación | F2 | lista de §2.5 cumplida en Chrome, Edge y Firefox de escritorio; la interfaz sigue respondiendo durante la corrida | 9 d |
| **F4 Datos dinámicos** | pronóstico Open-Meteo con caché y control de calidad; índices Sentinel-2 por AWS (compuesto de ventana y compuestos mensuales de verano); GEE opcional; preparación de combustible, humedad viva y curado por motor; carga manual; indicador de fuente y antigüedad | F1 | **E-E3-2** evaluado; sin red, el programa arranca con la caché o con un evento de ejemplo y lo rotula; con red, pronóstico en menos de 10 s; verano 2026 generado | 8 d |
| **F5 Intervenciones** | dibujo de cortafuegos (trazo, borrador, ancho, deshacer, longitud), aplicación en los dos motores, viento manual durante la corrida, bitácora encadenada, reproducción | F1, F3 | **E-E3-4**: reproducción desde bitácora idéntica; equivalencia con la corrida offline que carga los mismos trazos desde el inicio | 6 d |
| **F6 Verificación** | pruebas automáticas; lotes E-E3-1 a 4; modo histórico (evento con meteo real, cicatriz, focos y métricas de v3.1); informe `01_verificacion.md` con ficha de comparabilidad | F1–F5 | todos los prerregistros evaluados e informados, se cumplan o no; el modo histórico muestra las cifras de las carpetas `resultados/v3.1` y `resultados/v4.0` de Las Chacras octubre 2023 | 6 d |
| **F7 Instalación y entrega** | `instalar.bat` (crea el entorno, instala bibliotecas, verifica los datos por sha256), `iniciar.bat`, `bajar_historicos.py`, `README.md` del repositorio con los cuatro pasos de §2.8, guía de uso, pantalla de límites del modelo, etiqueta `1.0.0` con su publicación | F6 | **una tercera persona, que no participó, clona el repositorio en una computadora limpia y lo hace funcionar siguiendo solo el `README.md`**; la prueba de humo de la integración continua pasa; requisitos de §2.7 confirmados | 4 d |

**Hitos:** H0 (F0) repositorio, plan y prerregistros listos · H1 (F1) motores reales controlables y verificados · H2 (F2 + F3)
simulador usable con datos de ejemplo · H3 (F4) datos en tiempo real · H4 (F5) intervenciones reproducibles · H5 (F6) informe
de verificación · H6 (F7) entrega. Cada hito es un hito de GitHub con sus incidencias.

**Total: 57 días-persona**: 53 de las fases más 4 de coordinación y revisión cruzada.

### 3.1 Reparto entre dos personas y calendario

Dos frentes que se tocan en un solo lugar, el contrato de los Anexos C y D (formato de la corrida y mensajes entre servidor y
motor). Fijarlo en F0 permite que cada uno avance sin esperar al otro: el frente B desarrolla contra un proceso motor simulado
que emite avances de mentira, y el frente A prueba sus procesos desde la línea de comandos.

| Frente | Persona | Fases | Días |
|---|---|---|---|
| **A. Motores y datos** | A | F1 procesos motor (8) · F4 datos dinámicos (8) · parte de motores de F5 (3) | 19 |
| **B. Servidor e interfaz** | B | F2 servidor (5) · F3 interfaz (9) · parte de dibujo e interfaz de F5 (3) | 17 |
| **Compartido** | A y B | F0 (7) · F6 verificación (6) · F7 entrega (4) · coordinación y revisión (4) | 21 |

Calendario **[ESTIMACIÓN]**, con dedicación plena de los dos:

| Semana | Persona A | Persona B | Se juntan en |
|---|---|---|---|
| 1 | F0: congelar motores, datos al repositorio, prerregistros | F0: repositorio, integración continua, contrato | H0 |
| 2 | F1 procesos motor | F2 servidor con motor simulado | — |
| 3 | F1 (cierre, E-E3-1 y E-E3-3) · inicio de F4 | F3 interfaz | H1: el servidor pasa del motor simulado a los reales |
| 4 | F4 datos dinámicos (E-E3-2) | F3 interfaz | H2 |
| 5 | F4 (cierre) · F5 intervenciones en los motores | F5 dibujo de cortafuegos y bitácora | H3, H4 |
| 6 | F6: evalúa lo que hizo B | F6: evalúa lo que hizo A | H5 |
| 7 | F7 instalación y entrega · margen | F7 guía y prueba con tercera persona · margen | H6 |

**Unas 7 semanas**, con alrededor de una semana de margen por persona (cada una tiene unos 28 a 30 días de trabajo). Si la dedicación es parcial, el calendario se estira en proporción;
el reparto no cambia.

**Revisión cruzada.** Ningún cambio entra a `main` sin la aprobación de la otra persona. En la verificación el cruce es
deliberado: quien escribió un prerregistro no es quien lo evalúa. Sigue la práctica de "verificación independiente" que el
proyecto ya usa en sus lotes (docs/v4.0/19 §1), ahora con dos personas reales.

**Riesgo de depender de una sola persona.** Cada frente tiene un único dueño. Se compensa con la revisión cruzada, que obliga
a que los dos lean todo el código, y con la bitácora en el repositorio.

---

## 4. Estrategia de datos

### 4.1 Capas fijas (precargadas, no editables)

Se usan los productos que ya existen, sin convertir **[DATO]**:

| Capa | Producto | Fuente |
|---|---|---|
| Topografía | `dem/dem_copernicus_glo30_*.tif`, `pendiente_*.tif`, `orientacion_*.tif`; para v4.0, `sim_v4/estaticos/topografia/` | Copernicus GLO-30 |
| Caminos | `infraestructura/caminos_*.gpkg`; `barreras/barreras_enlaces_*.npz` (v3.1); `sim_v4/estaticos/infraestructura.gpkg` (v4.0) | OSM / IGN integrado |
| Viviendas | `infraestructura/viviendas_*.gpkg` (325 entidades) | OSM / IGN |
| Red eléctrica | `infraestructura/electricidad_mt_*.gpkg` (5.543 tramos) | EDESAL |
| Viento sobre el relieve | `viento/viento_unitario_*_100m_brush_c26e461c0ecb.nc` (72 direcciones, 100 m, 169 MB) | WindNinja 4.0.0, generado una vez en octubre de 2026 |
| Cuarteles y arribo | `datos/crudos/bomberos_san_luis.geojson` (42), `infraestructura/tiempo_arribo_*.tif` | Ministerio de Seguridad de San Luis |
| Cobertura | `cobertura/cobertura_mapbiomas_col3_{2021..2025}_*.tif` | MapBiomas Col. 3 |

Al arrancar, el servidor verifica existencia, grilla (forma y transformación) y sha256 de cada capa contra un manifiesto, con
el mismo criterio que `manifiesto_datos.yaml` de SIM. Si algo no coincide, se detiene con un mensaje claro.

**Viento.** WindNinja no se ejecuta al simular. v3.1 lee la biblioteca y calcula, por hora, campo = velocidad × campo unitario
de la dirección, interpolando entre las dos direcciones vecinas (`BibliotecaViento.campo`). La velocidad es el promedio escalar
de los 16 puntos del pronóstico y la dirección el promedio vectorial (adoptado en v3.1, docs/v3.1/04: el vectorial pierde 5–10 %
de velocidad). Con viento manual, el valor que escribe el usuario se usa directo. Límite a declarar en la guía: la biblioteca
supone un viento de entrada igual en todo el dominio y atmósfera neutra; no representa brisas de valle.

### 4.2 Meteorología actual y pronóstico

| Aspecto | Plan |
|---|---|
| Fuente | **Open-Meteo Forecast API**, con el cliente de v3.1 (`openmeteo.py`, `tipo: pronostico`): misma malla de 4 × 4 = 16 puntos, UTC, m/s. Variables: temperatura, humedad relativa, velocidad y dirección del viento a 10 m, precipitación, ráfagas. Sin clave. Modelo: `ecmwf_ifs025` como principal y `best_match` de respaldo **[DECISIÓN D-E3-07]**. Se documenta que la calibración usó el archivo `ecmwf_ifs` de 9 km y que docs/v3.3/05 halló que las fuentes coinciden entre sí en unos 10° de dirección |
| Frecuencia | al iniciar y a pedido; el pronóstico se renueva cada 6 h; el programa no consulta solo más de una vez por hora |
| Resolución | 0,25° interpolado a los 16 puntos; horaria; 5 días hacia atrás (para la humedad del combustible muerto) y 7 hacia adelante |
| Preprocesamiento | control de calidad de v3.1 (rangos físicos, duplicados, huecos de más de 2 h → rechazo); serie del dominio: promedio de escalares, promedio vectorial del viento y promedio escalar de la velocidad; se escribe en los dos formatos que leen los motores (`_dominio.csv` de v3.x y `meteo_horaria.csv` de v4.0, km/h y hora local); humedad muerta con las funciones de cada motor |
| Si falla | (1) última descarga en caché, con su fecha visible y aviso de antigüedad; (2) carga manual de un CSV en cualquiera de los dos formatos, con el mismo control de calidad; (3) evento de ejemplo (Las Lagunas 2024 o Las Chacras octubre 2023) rotulado EJEMPLO en el mapa y en la exportación; (4) modo escenario: viento, temperatura y humedad constantes puestos a mano |
| Alineación | es una serie del dominio, no una grilla. La variación espacial entra por la biblioteca WindNinja (v3.1) o por el factor topográfico (v4.0) |
| "Actual" | Open-Meteo entrega el análisis del modelo para la hora en curso; no son observaciones (D28). Se muestra con ese nombre |

### 4.3 NDVI / NDMI

**Fuente principal: Sentinel-2 L2A en AWS, sin token ni cuenta** (D-E3-08). **[VERIFICADO 10/11]**:

- el catálogo Earth Search (`earth-search.aws.element84.com/v1`, colección `sentinel-2-l2a`) responde sin credenciales;
- el dominio cae en cuatro teselas (19HGD, 19HGE, 20HKJ, 20HKK), en dos zonas UTM (19 y 20, por el meridiano 66° O);
- la escena más reciente era del 7/11/2026, con pasada cada 5 días;
- para la ventana 30/07–17/09/2024 devuelve 40 escenas, las mismas 10 fechas × 4 teselas que usó el proyecto con GEE;
- `rasterio` 1.5.1 de este equipo abre una banda remota y lee una ventana de 512 × 512 en 3,6 s. Niveles disponibles en las
  bandas de 20 m: 20, 40, 80 y 160 m.

Sentinel-2 no tiene 30 m nativos (rojo e infrarrojo a 10 m; B8A y SWIR a 20 m), ni en AWS ni en GEE: en los dos casos los 30 m
se obtienen remuestreando.

Dos productos, cada uno con el método que ya usa el proyecto:

| Producto | Para qué | Ventana | Fórmulas | Paso a 30 m | Método de origen |
|---|---|---|---|---|---|
| **Compuesto de ventana** | humedad viva, curado y clases de v3.1; `indices_mes_evento` de v4.0 | **45 días que terminan el día anterior** a la corrida, mediana | NDVI = (B8 − B4)/(B8 + B4); NDMI = (**B8** − B11)/(B8 + B11) | lectura a 20 m (B4 y B8 promediados desde 10 m) y promedio a la grilla | `gee_indices.py` + `clasificacion.py` de v3.x; es el que usaron los dos motores en las corridas con eventos estándar |
| **Compuestos mensuales de verano** (enero a marzo) | mapa de combustible de v4.0 (regla 3.3b) y denominador del curado | cada mes calendario, mediana; después mediana de los tres | NDVI igual; NDMI = (**B8A** − B11)/(B8A + B11) | directo a la grilla de 30 m, vecino más cercano | `descargar_ndvi_ndmi_gee.py` de SIM |

La diferencia de banda en el NDMI (B8 contra B8A) existe hoy entre los dos productos del proyecto **[DATO]**; el simulador la conserva
y la anota en la ficha de comparabilidad.

| Aspecto | Plan |
|---|---|
| Frecuencia | compuesto de ventana: a pedido, antes de simular (hay imagen nueva cada 5 días); verano: una vez por año, cuando termina marzo. Hoy solo existen los veranos 2023 y 2024 **[DATO]**: hay que generar el de 2026 |
| Volumen | 61,7 MB por banda de 20 m y tesela **[VERIFICADO]**; el dominio ocupa alrededor de un quinto de cada tesela. Unos 40 MB por fecha, 9 fechas en 45 días, menos las descartadas por nubes: entre 150 y 350 MB por actualización **[ESTIMACIÓN]**. Las escenas bajadas quedan en caché y solo se piden las nuevas |
| Preprocesamiento | búsqueda en el catálogo por recuadro y fechas; descarte de teselas con más de 80 % de nubes; máscara con la capa SCL (sombras, nubes medias y altas, cirros, nieve, sin dato); reproyección de las dos zonas UTM a la grilla EPSG:5345; mediana; salida en int16 × 10000 con nodata −32768, los mismos archivos que hoy (`ndvi_30m_*.tif`, `ndmi_30m_*.tif`, `NDVI_NDMI_AAAA_MM.tif`); procedencia con la lista de escenas |
| Diferencias con lo calibrado | (1) máscara SCL en lugar de Cloud Score+ ≥ 0,6; (2) la escala de reflectancia: los metadatos de cada escena dicen a la vez "corrección ya aplicada" y "restar 0,1", hay que resolverlo con números; (3) mosaico de dos zonas UTM. Las tres se miden en **E-E3-2** contra los compuestos de GEE que ya están en el repositorio, antes de habilitar la vía |
| Si falla | (1) último compuesto en caché, con su fecha y aviso "índices de hace N días"; (2) GEE, si la computadora tiene credenciales (`earthengine authenticate`); (3) carga manual de los TIF; (4) sin índices: humedad viva por defecto y curado de Scott y Burgan, rotulado |
| Alineación | todo producto se escribe en la grilla exacta del dominio y se verifica al cargar (forma 1.671 × 1.672, transformación, CRS); nodata con el tratamiento de cada motor |

### 4.4 Cobertura y combustibles

MapBiomas Col. 3 es anual y se publica con cerca de un año de demora; hay 2021 a 2025 en el repositorio. Cada motor arma su
mapa con sus propias funciones a partir de la cobertura del año anterior y de los índices de §4.3: v4.0 con la regla 3.3b
(`generar_sb40`), v3.1 con la clasificación de 7 clases y sus umbrales de NDVI. En 2026 se usa la cobertura 2025 y se avisa.
Dynamic World y WorldCover no se adoptan: v3.4 mostró que no mejoran. Cuando MapBiomas publique un año nuevo, se agrega el
ráster alineado y nada más.

### 4.5 Caché, procedencia y validación

Todo lo descargado va a `datos/procesados/app/` con un JSON de procedencia (fuente, parámetros, fecha, sha256), como
`procedencia.py` de v3.x. Cada corrida guarda el sha256 de todos sus insumos. Nada se corrige en silencio: un archivo que no
pasa la validación se rechaza con mensaje o se acepta con rótulo visible.

---

## 5. Decisiones de ingeniería que condicionan el calendario

1. **Motores reales, sin traducir**: elimina el riesgo de que una traducción se aparte de lo validado y ahorra las pruebas de
   equivalencia entre lenguajes.
2. **Un proceso por motor**: lo impone el nombre de paquete repetido y además aísla, paraleliza y simplifica el control.
3. **Envolver, no editar**: subclases y funciones del simulador alrededor del código congelado; ningún archivo de v3.1 ni de v4.0
   cambia.
4. **Corrida en tiempo real como evento generado**: los cargadores congelados se usan tal cual.
5. **Pausa en hora en punto e intervenciones solo en pausa**: mantiene cada corrida reproducible con las versiones congeladas.
6. **Sin recalibrar**: si una verificación falla, se corrige el simulador, nunca el modelo.
7. **Formato de salida de v3.1**: el visor y el modo histórico reutilizan lo que ya existe (pedido del usuario, docs/v4.0/31 §8).
8. **Repositorio nuevo en GitHub con los datos mínimos adentro**: un clon funciona sin pasos manuales; lo pesado va en una
   publicación aparte.
9. **Contrato entre frentes fijado al principio**: dos personas avanzan en paralelo sin bloquearse.

---

## 6. Verificación y validación

### 6.1 Pruebas automáticas (`pytest`, sin red)

| Nivel | Qué | Fuente de verdad |
|---|---|---|
| Entorno | las suites de los motores pasan en el entorno único. Línea base **[MEDIDO 10/11]**: v3.1, 69 pruebas; v4.0, 130 pasan, 12 se omiten y 5 se excluyen con motivo (`herramientas/pruebas_excluidas.txt`): 4 ya fallaban en la copia original (3 quedaron viejas tras D41 y D42, 1 pide resultados del banco) y 1 pide datos históricos. El README de v4.0 dice "140 en verde"; no es lo que se midió | las propias suites y la lista de exclusiones |
| Procesos motor | corrida corta sintética; pausar y reanudar no cambia `t_llegada`; detener deja salidas válidas; matriz de barreras vacía en libre = barreras apagadas | corrida sin control |
| Intervenciones | viento manual, cortafuego en pausa recortado a celdas no afectadas, reproducción desde bitácora, hash encadenado | pruebas nuevas |
| Datos | control de calidad meteorológico; lectura y mosaico de teselas con archivos locales de muestra; alineación a la grilla; rechazo de archivos mal formados | pruebas nuevas |
| Servidor | API completa con el cliente de pruebas; caída de un proceso motor; dos corridas a la vez | pruebas nuevas |
| Interfaz | humo en navegador de escritorio: cargar, clic, correr 6 h, pausar, dibujar, reanudar, exportar | pruebas nuevas |
| Clon nuevo | en la integración continua, sobre máquinas limpias con Windows y con Linux: clonar, instalar, correr 6 h del evento de ejemplo con cada motor | §2.8 |
| Versiones cerradas | falla si un cambio toca `src/v3.1`, `src/v4.0` o sus escenarios | sha256 de la primera subida |

### 6.2 Comparación con la simulación offline (E-E3-1)

Escenarios fijos, con insumos que ya están en el repositorio:

| Escenario | Motores | Horas | Referencia offline |
|---|---|---|---|
| Caso La Aguada 2023 (`sim_v4/conjunto_prueba/las_lagunas_la_aguada_2023`) | v4.0 | 36 | corrida nueva de `correr_escenario.py` con `modelo_v3` `barreras` |
| Las Lagunas 2024, h1, SNMF | v4.0, v3.1 libre, v3.1 librev2 | 48 | `resultados/v4.0/SL-2024-LASLAGUNAS/…-h1-SNMF-barreras` y corridas nuevas de v3.1 |
| Las Chacras octubre 2023, alt4, 06 UTC | v4.0, v3.1 libre, v3.1 librev2 | 72 | `resultados/v4.0/SL-2023-CHACRASOCT/…-h4-alt4-libre` y `resultados/v3.1/…-h4-alt4-{libre,librev2}` |

Como es el mismo código con los mismos insumos, el criterio es identidad: 0 celdas distintas en el tiempo de llegada. Cualquier
diferencia indica un error del simulador y se corrige ahí. Antes de comparar cifras **entre motores** (v3.1 contra v4.0) se llena la
ficha de comparabilidad (Anexo A): difieren en viento, combustible, vecindad, barreras, extinción por lluvia y fórmula del NDMI
de verano, y eso se declara junto a cada cifra.

### 6.3 Reproducibilidad

- Misma corrida, misma computadora: resultado idéntico (los motores son deterministas con pavesas y contención apagadas; el
  cruce de barreras usa un sorteo por semilla independiente del orden).
- Corrida con intervenciones: reproducción desde la bitácora idéntica, y equivalente a la corrida offline armada con los mismos
  trazos y la serie meteorológica editada (E-E3-4).
- Entre computadoras: mismas versiones de bibliotecas fijadas en `requirements.txt`. La igualdad bit a bit entre máquinas es un
  supuesto no verificado (informe técnico §3.11). Ahora se comprueba sola: la integración continua corre E-E3-1 en una máquina
  distinta de las dos de desarrollo, y cada persona lo corre en la suya.

### 6.4 Validación contra cicatrices e incendios históricos

- **Qué valida esta etapa**: que conduce a v3.1 y v4.0 sin alterarlos. La capacidad predictiva es la de esas versiones, ya
  informada: sobre los 10 eventos vistos, IoU mediana 0,483 (v3.1 librev2) contra 0,360 (v4.0) y primeras detecciones a tiempo
  0,818 contra 0,329, con igniciones ajustadas a la cicatriz, que inflan el IoU (X-46); en el evento no visto Las Chacras
  octubre 2023, v3.1 gana en las dos direcciones (0,45–0,46 contra 0,25–0,37) y v4.0 sin parada no se apaga tras 7,8 mm de
  lluvia (docs/v4.0/31 §7.2). Esas cifras y sus límites van en la pantalla "Sobre el modelo".
- **Modo histórico** (F6): se elige uno de los 15 eventos con ficha; el programa usa su meteorología real, sus índices previos
  y su ignición recomendada, muestra la cicatriz y los focos VIIRS y calcula IoU a igual superficie y fracción de primeras
  detecciones a tiempo con el código de v3.1. Sirve para demostrar, enseñar y detectar regresiones, no para calibrar.
- **Pronóstico contra análisis**: lo que esta etapa agrega de verdad al modelo es la cadena de datos en tiempo real. La de índices se
  mide en E-E3-2. La de meteorología (pronóstico IFS 0,25° en lugar del archivo de 9 km) no tiene todavía una prueba; se propone
  como mejora M4.
- **Eventos no vistos (X-49)**: no se corren en esta etapa. Si se decide abrirlos para v3.1 y v4.0 congeladas, se hace con el
  protocolo (lista fijada con sha256, prerregistro, una apertura por versión).

---

## 7. Mejoras más allá de lo pedido (priorizadas)

| # | Mejora | Prioridad | Justificación | Costo **[ESTIMACIÓN]** |
|---|---|---|---|---|
| M1 | Bitácora encadenada y corrida exportable y reproducible (ya en el diseño) | Alta | sin esto no hay trazabilidad de una corrida usada en una decisión | incluido |
| M2 | Modo histórico con cicatriz, focos y métricas (ya en F6) | Alta | hace visible la validación; la base existe en la API de v3.1 | incluido |
| M3 | Exposición: viviendas afectadas y amenazadas, km de red MT, caminos, hora estimada de llegada a cada vivienda | Alta | v4.0 ya lo calcula (`outputs/indicadores.py`); es el núcleo de "mitigación" | 2 d |
| M4 | Prueba de pronóstico contra análisis: repetir eventos históricos con el pronóstico archivado de Open-Meteo y comparar con la corrida hecha con el análisis | Alta | es la única parte de la cadena en tiempo real sin medir; requiere prerregistro propio | 3 d |
| M5 | Conjunto de corridas con el viento perturbado (dirección ± 20°, velocidad ± 25 %, hora de ignición) en procesos paralelos → mapa de probabilidad de quemado | Media | v3.3 midió que el fuego real se aparta 9–49° del viento después del primer día; muestra un rango en lugar de una línea. Se rotula "perturbación de entradas" | 4 d |
| M6 | Pantalla de límites del modelo y rótulo permanente "sin combate; herramienta de apoyo" en el mapa y en cada exportación | Alta | evita que una corrida se tome como pronóstico oficial | 0,5 d |
| M7 | Tiempo de arribo de cuarteles como capa y "hora estimada de primer ataque", sin simular combate | Media | el producto ya existe (`tiempo_arribo_*.tif`, 42 cuarteles) y no contradice D42 | 1 d |
| M8 | "Qué pasa si" de combustible: polígono con factor de carga (quema prescripta, pastoreo) | Media | v4.0 ya tiene `modificador_combustible`; conecta con "prevención"; se rotula como escenario | 3 d |
| M9 | Focos activos VIIRS (FIRMS) con la clave del usuario, y "encender desde un foco" | Media | ignición real en lugar de un clic a ojo; el proyecto ya usa FIRMS con `FIRMS_MAP_KEY` | 2 d |
| M10 | Pronóstico re-sincronizado con focos (método de v3.2, `pronostico_resincronizado.py`) como modo aparte | Media | en v3.2 subió el puntaje a 24 h de 0,30 a 0,46; es código de v3.2, no de v3.1, y exige decidir si entra | 5 d |
| M11 | Ejecutable empaquetado, sin instalar Python | Baja | facilita repartirlo; numba, rasterio y geopandas son difíciles de empaquetar en Windows | 4 d, incierto |

---

## 8. Decisiones (aprobadas por el usuario el 2026-11-10; registro en `decisiones.md`)

| Código | Decisión | Alternativas descartadas |
|---|---|---|
| D-E3-01 | Motores y configuraciones congeladas: v4.0 `modelo_v3` `barreras`; v3.1 `modelo_v2` librev2 y `modelo_v1` libre; sha256 de `src/v3.1` y `src/v4.0` registrados | v3.4 (el usuario pidió v3.1); v4 con `k_global` 2–2,5 (E059 dio R3) |
| D-E3-02 | **Programa Python local con interfaz en el navegador**; un proceso por motor; servidor solo en `127.0.0.1` | HTML único con motores en JavaScript (versión del 5/11); servidor compartido; complemento de QGIS |
| D-E3-03 | **v3.1 con la biblioteca WindNinja completa y velocidad escalar; v4.0 con serie y factor topográfico** (cada motor como está congelado) | reemplazar WindNinja por viento uniforme en v3.1 (error de velocidad del 26 % en el p99, medido el 10/11) |
| D-E3-04 | Pausa en hora en punto; intervenciones solo en pausa; cortafuegos recortados a celdas no afectadas | intervenciones en cualquier minuto (no reproducibles con las versiones congeladas) |
| D-E3-05 | Sin promedio entre motores; envolvente y aviso de discrepancia | promedio ponderado de huellas |
| D-E3-06 | **Solo computadoras, con Windows o con Linux, y navegador de escritorio** (Linux agregado por el usuario el 10/11) | celulares y tabletas; solo Windows |
| D-E3-07 | Open-Meteo `ecmwf_ifs025` + `best_match`, 16 puntos, 5 días hacia atrás, control de calidad de v3.x | un solo punto central (D29) |
| D-E3-08 | **Índices por Sentinel-2 en AWS sin token** como vía principal; compuesto de ventana de 45 días (método v3) y mensuales de verano (método SIM); GEE opcional | depender de GEE; "último mes cerrado" como ventana |
| D-E3-09 | **No hay v5.0**: la última versión del modelo es la v4.0; lo nuevo vive en GitHub como `app/`, sin número de versión del modelo (corrección del usuario del 10/11). En esta etapa no se abren los eventos no vistos X-49 | llamar v5.0 al programa nuevo; correr X-49 con él |
| D-E3-10 | **Repositorio nuevo en GitHub** como único lugar de trabajo y de distribución; datos mínimos dentro (viento partido en cuatro archivos), históricos y resultados de referencia en una publicación; sin Git LFS. Es `deinagutierrez/simulador-incendios`, público; entran solo v3.1 y v4.0 | seguir con copias en Drive; actualizar el repositorio viejo `gvcosta/Gemelos_Digitales_Incendios_UNSL`; todos los datos por descarga aparte |
| D-E3-11 | **Todos los datos se pueden publicar** (confirmado por el usuario el 10/11): red MT de EDESAL, cuarteles, registros del SNMF, viviendas y caminos. Fuente y atribución de cada capa en `DATOS.md`. **Pendiente: elegir la licencia del código** | — |
| D-E3-12 | Trabajo de dos personas en dos frentes (motores y datos; servidor e interfaz), `main` protegida, revisión cruzada obligatoria, prerregistros etiquetados en git, bitácora y decisiones dentro del repositorio | una sola persona en serie; decisiones fuera del repositorio |

---

## 9. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación | Señal temprana |
|---|---|---|---|---|---|
| R1 | Un clon nuevo no funciona en otra computadora o en Linux (Python 3.14, numba, rasterio, geopandas; datos faltantes; rutas y mayúsculas de archivos) | Media | Alto | `instalar.bat` e `instalar.sh` con versiones fijadas y verificación de datos; prueba de clon nuevo en la integración continua desde F0; prueba con una tercera persona en F7; M11 como alternativa | F0: la integración continua pasa las dos suites desde un clon limpio |
| R2 | Un entorno común no satisface a los dos motores | **Resuelto en Windows [VERIFICADO 10/11]**: con numpy 2.5.2 y rasterio 1.5.1 pasan las dos suites y las dos corridas cortas. **También en Linux**: la integración continua pasó en Ubuntu el 10/11 | Medio | la integración continua lo prueba en Linux en la primera subida; si falla, un entorno por proceso motor | primera corrida de la integración continua |
| R3 | v4.0 lento en incendios grandes (2,7 s por hora simulada con 29.000 ha) o memoria alta en el modo "ambos" | Media | Medio | medir en E-E3-3; mostrar progreso y permitir Detener; recomendar 16 GB para "ambos" | F1 |
| R4 | Open-Meteo o el catálogo de AWS caídos, o cambio de sus interfaces | Baja | Medio | caché en disco, carga manual, evento de ejemplo rotulado, GEE opcional; versiones de las interfaces fijadas | llamadas de prueba en F0 |
| R5 | Los índices por AWS no reproducen los de GEE (máscara de nubes, escala de reflectancia, dos zonas UTM) | Media | Alto | E-E3-2 antes de habilitar la vía; si falla, ajustar la máscara o exigir GEE y decirlo | F4 |
| R6 | Calidad del pronóstico: direcciones que difieren ~10° entre fuentes, error que crece con el horizonte | Alta | Alto | mostrar horizonte y antigüedad; recomendar corridas de hasta 24 h; M4 y M5 | es inherente |
| R7 | Incertidumbre del modelo: IoU 0,36–0,48 en eventos vistos, v3.1 adelanta y v4.0 atrasa, sin combate | Alta | Alto | M6; envolvente de los dos motores; cifras de validación en cada exportación | — |
| R8 | Las envolturas dependen de detalles internos de los motores (`_tablas_hora`, `paso_tiempo`) | Media | Medio | E-E3-1 exige identidad; las versiones están congeladas, así que esos detalles no cambian | F1 |
| R9 | Cortafuego agregado en pausa no equivale al mismo trazo cargado desde el inicio | Media | Medio | recorte a celdas no afectadas; E-E3-4 lo mide en los dos motores | F5 |
| R10 | Falta el compuesto de verano 2026 o los índices quedan viejos | Alta | Medio | generarlo en F4; aviso de antigüedad en la interfaz | fecha visible |
| R11 | Uso indebido: decisiones de evacuación sobre una corrida | Media | Alto | M6; la interfaz habla de "escenario", no de "pronóstico"; la guía aclara que la autoridad es el COE / SNMF | — |
| R12 | **Datos de terceros en un repositorio público**: la red MT de EDESAL, los cuarteles y los registros del SNMF no tienen licencia abierta declarada en el proyecto; una vez subidos quedan en el historial | Media | Alto | D-E3-11: revisar antes de la primera subida; lo dudoso va a una publicación privada o se pide permiso; `DATOS.md` con fuente y licencia por capa; pie de mapa con atribuciones | F0, antes de subir |
| R13 | Límites de GitHub: archivo de más de 100 MB rechazado; repositorio que crece si se suben resultados o cachés | Media | Medio | viento partido en dos; `.gitignore` para `resultados/` y `datos/procesados/`; control de tamaño en la integración continua | primera subida en F0 |
| R14 | Dos personas: los frentes se desalinean o los cambios chocan | Media | Medio | contrato de los Anexos C y D fijado en F0 y cambiado solo por pedido de integración aprobado por ambos; ramas cortas; integración del servidor con los motores reales al final de la semana 3 | H1 |
| R15 | Cada frente depende de una sola persona | Media | Medio | revisión cruzada obligatoria; bitácora en el repositorio; margen en el calendario | — |

---

## Anexo A. Ficha de comparabilidad (plantilla para toda comparación de cifras)

| Campo | Corrida A | Corrida B |
|---|---|---|
| Motor y versión (sha256 del código; versión del simulador) | | |
| Modelo y variante; parámetros que difieren del YAML congelado | | |
| Dominio / grilla | | |
| Evento o escenario; rol (visto / no visto / tiempo real) | | |
| Ignición (punto, hora, cómo se eligió; desplazamiento aplicado) | | |
| Meteorología (fuente, modelo, puntos, periodo, sha256; análisis o pronóstico) | | |
| Viento (biblioteca WindNinja + escalar / serie + factor topográfico / manual) | | |
| Índices (fuente AWS o GEE; ventana; fórmula del NDMI; máscara de nubes) y cobertura (año) | | |
| Mapa de combustible (regla 3.3b / clases v1) | | |
| Humedad muerta y viva; extinción por lluvia | | |
| Barreras (caminos, modo, semilla; cortafuegos) | | |
| Parada y horizonte | | |
| Intervenciones (bitácora, hash) | | |
| Métrica, instante de evaluación, referencia y máscara | | |
| Evaluador (código y versión) | | |
| n y advertencias (eventos vistos, igniciones ajustadas a la cicatriz) | | |

**Lectura obligatoria al pie:** qué difiere entre A y B, qué se puede concluir y qué no.

## Anexo B. Prerregistros de la etapa (se escriben, se suben y se etiquetan en F0; uno escribe y el otro evalúa)

| Código | Pregunta | Diseño | Criterio fijado antes | Si no se cumple |
|---|---|---|---|---|
| E-E3-1 | ¿El programa conduce a los motores sin alterarlos? | 3 escenarios × motores (§6.2), sin intervenciones; además, cada uno con una pausa y reanudación | 0 celdas distintas en el tiempo de llegada respecto de `correr_escenario.py`; cada motor por separado | se corrige el simulador y se repite completo |
| E-E3-2 | ¿Los índices por AWS equivalen a los de GEE? | (a) compuesto de ventana de Las Lagunas 2024 (30/07–17/09/2024, 40 escenas) contra `ndvi_30m` y `ndmi_30m` del evento; (b) mensual de septiembre de 2024 contra `NDVI_NDMI_2024_09.tif`; (c) efecto en el modelo: celdas que cambian de clase de combustible, y la corrida de Las Lagunas 48 h con unos y otros índices en los dos motores | se informa todo; se habilita la vía si la diferencia absoluta mediana de NDVI y de NDMI es ≤ 0,02, cambian de clase de combustible menos del 3 % de las celdas y el IoU entre las dos huellas es ≥ 0,95. Umbrales **[SUPUESTO, a confirmar al escribir el prerregistro]** | se revisa la máscara de nubes y la escala; si persiste, GEE pasa a obligatorio y se declara |
| E-E3-3 | ¿Cuánto tarda y cuánta memoria usa? | 3 escenarios × motores en la computadora de referencia; modo "ambos" | se **informa**: s por hora simulada, memoria pico por proceso, tiempo hasta la primera hora. Metas: v3.1 ≤ 0,5 s/h; v4.0 ≤ 3 s/h con 30.000 ha; "ambos" dentro de 16 GB | se ajustan los requisitos de §2.7 y se documenta |
| E-E3-4 | ¿Las intervenciones son reproducibles? | 5 corridas con 2 o 3 cortafuegos y 1 o 2 cambios de viento, en los dos motores | reproducción desde bitácora: idéntica; contra la corrida offline con los mismos trazos desde el inicio y la serie editada: IoU final ≥ 0,99 y la misma longitud de línea | se revisa el recorte y el momento de vigencia; no se toca el motor |

## Anexo C. Esquema del paquete de corrida (`corrida.json`)

```json
{
  "formato": "incendios_sl.corrida/1.0",
  "programa": {"version": "1.0.0", "sha256_src_v31": "…", "sha256_src_v40": "…"},
  "motor": {"nombre": "v4.0", "modelo": "modelo_v3", "variante": "barreras"},
  "dominio": {"id": "las_lagunas_potrerillos", "manifiesto_sha256": "…"},
  "insumos": {
    "meteo": {"fuente": "open-meteo ecmwf_ifs025 (pronóstico)", "descargado_utc": "…", "sha256": "…"},
    "indices_ventana": {"fuente": "sentinel-2-l2a AWS", "ventana": ["2026-09-26", "2026-11-09"], "escenas": 28, "sha256": "…"},
    "indices_verano": {"anio": 2026, "sha256": "…"},
    "cobertura_anio": 2025
  },
  "configuracion": {
    "ignicion": [{"lon": -65.7679, "lat": -32.6506, "t_utc": "…", "desplazada_m": 0}],
    "viento": {"modo": "pronostico"}, "horas": 48, "cortafuegos": []
  },
  "bitacora": [
    {"n": 1, "t_sim_min": 360, "t_vigor_min": 360, "tipo": "viento_manual", "datos": {"vel_kmh": 35, "dir_desde": 300}, "hash": "…"},
    {"n": 2, "t_sim_min": 660, "t_vigor_min": 660, "tipo": "cortafuego", "datos": {"ancho_m": 10, "suelo_mineral": false, "xy_5345": [[3540100, 6390200], [3540900, 6389400]]}, "hash": "…"}
  ],
  "resultados": {
    "ha_final": 1234.5, "km2_final": 12.35, "t_simulado_h": 48, "t_computo_s": 130.2, "motivo_fin": "horizonte",
    "exposicion": {"viviendas_afectadas": 0, "viviendas_amenazadas": 3, "red_mt_km": 0.4, "caminos_km": 1.2},
    "mitigacion": {"cortafuegos_m": {"10": 820}, "cambios_viento": 1},
    "archivos": ["hora_llegada_min.tif", "serie_indicadores.csv", "perimetros_horarios.geojson"]
  },
  "advertencias": ["sin combate"]
}
```

## Anexo D. Interfaz del servidor (borrador)

| Pedido | Qué hace |
|---|---|
| `GET /api/estado` | versión, motores disponibles, verificación de capas, fecha del pronóstico y de los índices |
| `GET /api/capas/<nombre>.png`, `/api/vectores/<nombre>.geojson` | capas de fondo (como `api/capas.py` de v3.1) |
| `POST /api/datos/meteo`, `POST /api/datos/indices` | actualizar pronóstico o índices; devuelven un trabajo con progreso |
| `POST /api/corridas` | crear una corrida con su configuración (Anexo C); `motor: ambos` crea dos |
| `POST /api/corridas/<id>/{iniciar,pausar,reanudar,detener}` | control |
| `POST /api/corridas/<id>/intervenciones` | viento manual o cortafuego, solo en pausa; devuelve la entrada de bitácora o el motivo del rechazo |
| `GET /api/corridas/<id>/eventos` | canal de avance: una entrada por hora simulada (superficie, celdas activas, exposición, segundos) |
| `GET /api/corridas/<id>/quemado/<hora>.png`, `/perimetro/<hora>.geojson` | huella para el mapa |
| `GET /api/corridas/<id>/exportar` | `corrida.json`, carpeta de resultados, visor autónomo |
| `GET /api/historicos`, `POST /api/historicos/<evento>/corrida` | modo histórico |

Entre el servidor y cada proceso motor: órdenes (`pausar`, `reanudar`, `detener`, `intervenir`) y avances (`hora`, `pausado`,
`final`, `error`) como líneas JSON.

## Anexo E. Inventario de lo que ya existe y se reutiliza

- Servidor y web de v3.1: `src/v3.1/src/incendios_sl/api/{app,trabajos,capas}.py`, `src/v3.1/web/`, `scripts/servir.py`.
- Visor autónomo de v3.1 y traductor desde v4.0: `scripts/exportar_visor.py`, `src/v4.0/scripts/exportar_visor_v31.py`.
- Clientes de datos: `openmeteo.py` (control de calidad, malla, serie del dominio, pronóstico), `gee_indices.py`,
  `descargar_ndvi_ndmi_gee.py` (GEE opcional).
- Preparación por evento: `preparar_evento.py` (v3.x), `incendios_sl/eventos.py` (v4.0), `preparar_evento_desde_banco.py`
  (v3.4, ejemplo de cómo dejar insumos sin red).
- Capas del dominio: `datos/inputSimulacion/{dem, grilla, infraestructura, cobertura, viento, barreras}` y `sim_v4/estaticos`.
- Fichas y resultados de referencia: `escenarios/v4.0/eventos` (15), `resultados/v3.1`, `resultados/v4.0`,
  `sim_v4/conjunto_prueba`.
- Para GitHub: `unir_partes` y `unir_todas_las_partes` en `incendios_sl/config.py` de los dos motores (unen solos los archivos
  `.part00`, `.part01`); `docs/v4.0/PAGES_Y_ACTIONS.md` describe tres flujos de Actions (simular escenario, publicar visores,
  pruebas) que sirven de guía, aunque no hay ningún archivo de flujo en esta copia.
- Bibliotecas ya instaladas en este equipo **[VERIFICADO 10/11]**: fastapi, uvicorn, numba, geopandas, rasterio 1.5.1
  (GDAL 3.12.4), xarray, netCDF4, requests, earthengine-api. No hace falta ninguna nueva para leer Sentinel-2 en AWS.

## Anexo F. Mediciones del 10/11/2026 que respaldan las decisiones

- **Catálogo y bandas de Sentinel-2 sin token**: ver §4.3.
- **Biblioteca WindNinja**: recortada al dominio son 72 × 504 × 504 celdas; la velocidad unitaria tiene mediana 0,994 y
  percentiles 1 y 99 de 0,80 y 1,17. Reemplazarla por viento uniforme da un error de velocidad de 2,8 % en la mediana y 26 % en
  el percentil 99, y 8,4° de dirección en el percentil 99. Con Python local se usa completa, así que no hay error que medir.
  Si alguna vez se retoma un HTML autónomo: con 18 direcciones y 1 byte por valor ocupa 2,9 MB, con error de velocidad de 1,1 %
  y de dirección de 0,65° en el percentil 99.
