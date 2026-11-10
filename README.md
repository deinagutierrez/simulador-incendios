# Simulador de incendios — San Luis

Gemelo digital para la prevención y mitigación de incendios forestales en la provincia de San Luis, Argentina (UNSL).
Dominio Las Lagunas–Potrerillos: 2.500 km², celdas de 30 m.

Este repositorio reúne los dos motores de propagación del proyecto, tal como quedaron validados, y el **simulador interactivo**
que se está construyendo sobre ellos: un programa que corre en la computadora y se maneja desde el navegador.

> **Estado al 2026-11-10: fase F0.** Están los motores, los datos mínimos y la verificación de que un clon funciona.
> El simulador interactivo (`app/`) todavía no tiene código. Plan completo: [docs/etapa3/00_plan.md](docs/etapa3/00_plan.md).

## Empezar

Hace falta **git** y **Python 3.12 o superior** (verificado con 3.14.7). Windows o Linux. Unos 2 GB de disco.

```
git clone https://github.com/deinagutierrez/simulador-incendios.git
cd simulador-incendios
```

Windows:

```
instalar.bat
```

Linux:

```
./instalar.sh
```

`instalar` crea un entorno propio en `.venv`, instala las bibliotecas con versiones fijas y comprueba que todo funciona:
versiones congeladas intactas, datos presentes, pruebas de los dos motores y una corrida de 6 horas simuladas con cada uno.
Tarda unos minutos. Al final tiene que decir **"Todo funciona."**

Para volver a comprobar más tarde: `probar.bat` o `./probar.sh` (con `--rapido` omite las corridas).

La integración continua de GitHub repite esta comprobación en Windows y en Linux en cada cambio. Pasa en los dos desde el
2026-11-10.

## Qué hay

| Carpeta | Qué |
|---|---|
| `src/v3.1`, `src/v4.0` | los dos motores, **congelados**: no se modifican. v4.0 es la línea principal; v3.1 es el control (simulación libre) |
| `test/`, `escenarios/` | pruebas y escenarios de cada motor |
| `datos/` | datos mínimos del dominio y un evento de ejemplo (Las Lagunas 2024). Fuentes y licencias: [DATOS.md](DATOS.md) |
| `app/` | el simulador interactivo (todavía vacío) |
| `docs/etapa3/` | plan, decisiones, informe de F0, prerregistros y contrato entre los dos frentes de trabajo |
| `docs/v3.0`, `docs/v3.1`, `docs/v4.0` | documentos de los motores |
| `herramientas/` | verificación del clon y control de versiones congeladas |

## Correr un motor a mano

Los dos motores traen un paquete con el mismo nombre (`incendios_sl`). **No instalarlos con `pip install -e`**: se usan
indicando la carpeta con `PYTHONPATH`.

Windows (PowerShell), con el entorno activado (`.venv\Scripts\Activate.ps1`):

```
cd src\v4.0
$env:PYTHONPATH = "src"
python scripts\correr_escenario.py --escenario prueba_rapida_v4
```

Linux, con el entorno activado (`. .venv/bin/activate`):

```
cd src/v4.0
PYTHONPATH=src python scripts/correr_escenario.py --escenario prueba_rapida_v4
```

Los resultados quedan en `resultados/`, que no se sube al repositorio.

## Reglas de trabajo

- `src/v3.1`, `src/v4.0` y sus pruebas y escenarios no se tocan. `herramientas/congelado.py verificar` lo controla, y la
  integración continua falla si cambian.
- Todo cambio entra por pedido de integración, con la aprobación de la otra persona y las pruebas en verde.
- Cada comparación de resultados se prerregistra antes de correrla (`docs/etapa3/prerregistros/`).
- Resultados, cachés y claves no se suben.

## Límites del modelo

Los motores simulan propagación libre y barreras. **No simulan el combate del fuego.** En los incendios usados para validar,
la coincidencia de forma con la cicatriz real (IoU) estuvo entre 0,36 y 0,48, v3.1 tiende a adelantarse y v4.0 a atrasarse.
Es una herramienta de apoyo para explorar escenarios, no un pronóstico oficial. El detalle está en
`docs/v4.0/INFORME_TECNICO_MOTOR_V4.md` §7 y en `docs/v4.0/31_eventos_no_vistos_X49.md`.

## Licencia

**Pendiente.** El equipo todavía no eligió la licencia del código. Los datos tienen sus propias fuentes y licencias: ver
[DATOS.md](DATOS.md).
