# Prerregistro E-E3-1 — El simulador conduce a los motores sin alterarlos

Escrito el 2026-11-10, antes de que exista código de `app/`. Se congela con la etiqueta de git `prerregistro-E-E3-1`.
Escribe: ____ · Evalúa (la otra persona): ____

## Pregunta
¿Una corrida lanzada desde el simulador da exactamente lo mismo que la misma corrida lanzada con `correr_escenario.py` del
motor correspondiente?

## Diseño
Tres escenarios, sin intervenciones, y cada uno repetido con una pausa y una reanudación a mitad de la corrida:

| Escenario | Motores | Horas |
|---|---|---|
| Caso La Aguada 2023 (`sim_v4/conjunto_prueba/las_lagunas_la_aguada_2023`) | v4.0 `modelo_v3` `barreras` | 36 |
| Las Lagunas 2024, hipótesis 1, ignición SNMF | v4.0, v3.1 libre, v3.1 librev2 | 48 |
| Las Chacras octubre 2023, ignición `alt4`, 06 UTC | v4.0, v3.1 libre, v3.1 librev2 | 72 |

Referencia: corrida offline hecha en la misma computadora, el mismo día, con el mismo `congelado.json`.
Las Chacras necesita el paquete de datos históricos.

## Métrica
Número de celdas cuyo tiempo de llegada difiere entre las dos corridas (`hora_llegada_min.tif` en v4.0, `t_llegada_s.tif` en
v3.1), y diferencia de superficie final.

## Criterio, fijado antes de correr
**0 celdas distintas** en los siete pares escenario–motor, sin pausa y con pausa. Cada motor se informa por separado.

## Si no se cumple
Se corrige el simulador y se repite todo. No se toca ningún parámetro ni ningún archivo de los motores.

## Límites declarados
Compara el programa contra el motor, no el motor contra la realidad. Una sola computadora por corrida; la igualdad entre
computadoras se mira aparte, en la integración continua.
