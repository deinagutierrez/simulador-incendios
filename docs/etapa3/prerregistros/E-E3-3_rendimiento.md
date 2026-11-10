# Prerregistro E-E3-3 — Tiempo de cómputo y memoria

Escrito el 2026-11-10. Se congela con la etiqueta `prerregistro-E-E3-3`.
Escribe: ____ · Evalúa (la otra persona): ____

## Pregunta
¿Cuánto tarda y cuánta memoria usa cada motor conducido por el simulador, y qué computadora hace falta?

## Diseño
Los tres escenarios de E-E3-1, con cada motor, en la computadora de referencia de cada persona y en la integración continua.
Además, el modo "ambos" (los dos motores a la vez) en Las Lagunas 2024.

## Métricas
Segundos de cómputo por hora simulada; memoria pico por proceso; segundos desde "iniciar" hasta la primera hora simulada;
memoria pico total en el modo "ambos". Se anotan procesador, memoria y sistema de cada computadora.

## Criterio
Es una medición: se informa todo. Metas contra las que se compara:

| Meta | Valor | Antecedente |
|---|---|---|
| v3.1 | ≤ 0,5 s por hora simulada | 0,23 s por hora en Las Chacras octubre 2023 (46 h, 3.065 ha, 0,92 GB) |
| v4.0 con unas 30.000 ha | ≤ 3 s por hora simulada | 2,7 s por hora en Las Chacras octubre 2023 (141 h, 29.319 ha) |
| Modo "ambos" | dentro de 16 GB | sin medición previa de memoria por proceso en v4.0 |

## Si no se cumplen las metas
Se ajustan los requisitos de la guía de uso y se documenta. No es motivo para tocar los motores.

## Límites declarados
Los antecedentes son corridas offline con figuras y con otros procesos en la máquina. La memoria de v4.0 por proceso nunca se
midió antes.
