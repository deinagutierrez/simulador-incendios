"""Servidor local del simulador interactivo (fases F2 a F4).

Lanza y controla los procesos motor y los procesos de datos (pronóstico, índices, evento generado), guarda el estado de cada
corrida y de cada trabajo de datos en disco y lo ofrece al navegador. No carga ningún motor: solo lee los avisos de los
procesos y lo que dejan en disco. Contrato: docs/etapa3/contrato_servidor_motor.md.
"""
VERSION = "0.3.0"
