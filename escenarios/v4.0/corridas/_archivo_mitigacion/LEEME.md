# Escenarios con mitigación (archivados en E036, D42)

Corridas guardadas que usan combate (contención SNMF, despacho, L03) o cortafuegos (`mitigacion.barreras_extra`). Se sacaron
del menú del cuaderno porque por ahora no se simulan mitigaciones (pedido del usuario, 2026-10-28). No se borraron: se pueden
correr con `python scripts/correr_escenario.py --archivo ../../escenarios/v4.0/corridas/_archivo_mitigacion/<nombre>.yaml`
desde `src/v4.0`. El código del motor (variantes `local`, `local_pronostico`, `ambas`, `contencion`, `l03`) sigue disponible.

Ojo: desde D41, `modelo_v3` usa viento `serie` y `parada.escapes: potencial`; para repetir una corrida anterior a E036 hay que
fijar `viento: windninja` (y, con combate, `ajustes: {parada: {escapes: v3}}`). Las rutas relativas de `mitigacion` se
corrigieron para esta carpeta (`../../mitigacion/…`).
