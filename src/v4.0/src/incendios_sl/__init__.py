"""Gemelo digital de incendios de San Luis, versión 4.0: capa estándar del repositorio sobre el simulador SIM.

`incendios_sl` resuelve las rutas del repositorio (`config`), traduce las fichas de evento de v3.0 a insumos de SIM
(`eventos`), calcula el arribo vial desde los cuarteles (`arribo`), arma la configuración de SIM a partir de una corrida
estándar (`escenario`) y escribe el registro, el resumen y las métricas de cada corrida (`resumen`). El motor es
`simulador` (src/v4.0/src/simulador).
"""
__version__ = "4.0.0"
