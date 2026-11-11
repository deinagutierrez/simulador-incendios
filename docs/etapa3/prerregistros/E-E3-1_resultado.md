# Resultado del prerregistro E-E3-1 — El simulador conduce a los motores sin alterarlos

Evaluación formal. Fecha: 2026-11-11. Prerregistro: `E-E3-1_identidad.md`, etiqueta de git `prerregistro-E-E3-1`.
Rótulos: **(dato)** medido · **(inferencia)** · **(sin verificar)**.

## Veredicto

**Se cumple.** (dato) 0 celdas distintas en los siete pares escenario–motor, sin pausa y con pausa.

## Quién escribió y quién evaluó

Escribió `app/motores/`: el usuario, con Claude. Evaluó: **el mismo frente**. El prerregistro pedía que evaluara la otra
persona; no pudo, y el usuario decidió hacerlo así (decisión D-E3-13). Es una desviación del procedimiento y queda declarada.
Lo que la compensa: el criterio era binario y estaba etiquetado antes de escribir el código; la evaluación es un guion sin
pasos manuales; cualquiera puede repetirla con el comando del final. Si la otra persona la repite, ese resultado reemplaza a
este.

## Con qué se corrió

| | |
|---|---|
| Código | cambio de git `7cbe5b4` (rama `f1-procesos-motor`), sin archivos de código sin registrar |
| Motores | `congelado.json`, sha256 del conjunto `2b32757194d2…621106`; los 244 archivos intactos antes y después |
| Equipo | Windows 11, Intel de 20 núcleos lógicos, Python 3.14.7. Una sola computadora |
| Herramienta | `python herramientas/e_e3_1.py`, 2026-11-11 10:41 |
| Referencia | corrida offline con `scripts/correr_escenario.py` de cada motor, hecha en la misma tanda |
| Archivo completo | `E-E3-1_resultados.json` (junto a este documento) |

## Resultado

Por cada par se hicieron tres corridas: offline, proceso sin órdenes, y proceso con una pausa y una reanudación a mitad de
camino. Se cuenta en cuántas celdas difiere el tiempo de llegada del fuego.

| Escenario | Motor | Horas pedidas | Horas simuladas | Superficie final | Celdas quemadas | Distintas | Distintas con pausa | Pausa en la hora |
|---|---|---|---|---|---|---|---|---|
| Caso La Aguada 2023 | v4.0 | 36 | 36 | 1.348 ha | 14.979 | **0** | **0** | 18 |
| Las Lagunas 2024, h1, SNMF | v4.0 | 48 | 48 | 12.839 ha | 142.659 | **0** | **0** | 25 |
| Las Lagunas 2024, h1, SNMF | v3.1 libre | 48 | 48 | 34.793 ha | 386.588 | **0** | **0** | 24 |
| Las Lagunas 2024, h1, SNMF | v3.1 librev2 | 48 | 48 | 32.915 ha | 365.724 | **0** | **0** | 24 |
| Las Chacras oct. 2023, alt4, 06 UTC | v4.0 | 72 | 72 | 2.356 ha | 26.181 | **0** | **0** | 37 |
| Las Chacras oct. 2023, alt4, 06 UTC | v3.1 libre | 72 | 45 | 1.526 ha | 16.954 | **0** | **0** | 36 |
| Las Chacras oct. 2023, alt4, 06 UTC | v3.1 librev2 | 72 | 46 | 3.065 ha | 34.054 | **0** | **0** | 36 |

La diferencia de superficie final entre proceso y offline es 0 ha en los siete pares (se sigue de las 0 celdas distintas).

## Lo que hay que saber para leerlo

- **Datos de Las Chacras.** El prerregistro decía que este evento necesita el paquete de datos históricos, que todavía no
  existe. Se usaron los archivos del evento tomados de la copia de trabajo anterior (Drive), copiados a `datos/inputSimulacion/`
  sin registrarlos en git (decisión D-E3-14, a confirmar por el usuario). Son 15 archivos, 21 MB; están listados con su sha256
  en `E-E3-1_resultados.json`. Quien clone el repositorio hoy puede repetir cuatro de los siete pares; los tres de Las Chacras,
  recién cuando exista el paquete.
- **v3.1 en Las Chacras no llegó a las 72 horas.** (dato) Cortó sola a las 45 h (libre) y a las 46 h (librev2) con su motivo 3,
  "sin propagación físicamente posible según el modelo". Pasa igual en la corrida offline y en el proceso, así que no afecta la
  comparación, pero la corrida comparada es de 45–46 horas y no de 72. La pausa se hizo en la hora 36, antes del corte.
- **Momento de la pausa.** La orden se envía al recibir el aviso de la hora de la mitad y el motor la atiende en la siguiente
  hora en punto que le toca mirar: v3.1 pausa en esa misma hora, v4.0 una hora después (25 y 37 en vez de 24 y 36). La pausa
  dura lo que tarda la respuesta; no se probaron pausas largas ni varias pausas en una corrida.
- **Configuración.** v4.0 con `modelo_v3`, variante `barreras` y sin parada en la cicatriz; v3.1 con `libre` y `libre_v2`
  (decisión D-E3-01). Sin validación ni figuras en ninguna de las dos corridas de cada par.

## Límites

- Compara el programa contra el motor, no el motor contra la realidad. No dice nada sobre si las huellas son correctas.
- Una sola computadora, con Windows. (sin verificar) La identidad en Linux a estas duraciones; la integración continua la
  mira en corridas de 6 horas.
- No cubre la ignición en un punto libre (tiene sus propias pruebas en `test/app/`) ni las intervenciones (prerregistro
  E-E3-4).
- La evaluó quien escribió el código (ver arriba).

## Cómo repetirlo

```
python herramientas/e_e3_1.py
```

Deja la tabla en `resultados/app/E-E3-1/resultados.json`. Los escenarios sin datos en el clon se informan como "sin datos".
