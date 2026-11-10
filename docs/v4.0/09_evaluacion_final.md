# Etapa 9 — Evaluación final del proyecto

Fecha: 2026-10-14. Versión del código 0.1.0. Este documento distingue explícitamente entre **implementado**, **probado** (con pruebas automáticas o ejecuciones reales registradas) y **no verificado**.

## 1. Entregables y su estado

| # | Entregable | Ubicación | Estado |
|---|---|---|---|
| 1 | Script de adquisición meteorológica Open-Meteo | `scripts/adquirir_meteo.py`, `src/incendios_sl/meteorology/openmeteo.py` | implementado; probado con 3 eventos (556/172/148 h, QC sin huecos) y pruebas unitarias de QC y convención de viento |
| 2 | Módulo WindNinja | `src/incendios_sl/wind/windninja.py` | implementado; biblioteca de 72 direcciones generada (72 corridas, 35 s y 5,8 GB cada una); convenciones y linealidad verificadas |
| 3 | Script NDVI/NDMI GEE | `scripts/obtener_indices.py`, `remote_sensing/gee_indices.py` | implementado; ejecutado para 3 eventos (40/32/32 escenas, cobertura 100 %); Landsat implementado pero **no ejecutado** |
| 4 | Pipeline geoespacial | `data/preparar_dominio.py`, `scripts/preparar_evento.py` | implementado y ejecutado; procedencia por producto |
| 5 | Evaluación metodológica de combustibles | `docs/01` §8, `docs/02` §7 | realizada |
| 6 | Pipeline del mapa de combustibles | `fuels/tabla.py`, `fuels/clasificacion.py` | implementado; mapas para 3 eventos; pruebas unitarias |
| 7 | Catálogo de incendios del área | `data/catalogo/*.csv`, `docs/06` | 133 polígonos MapBiomas, 40 eventos SNMF, focos VIIRS/MODIS de 3 eventos |
| 8 | Condiciones iniciales | `config/eventos/*.yaml` | 3 fichas con hipótesis explícitas |
| 9 | Autómata celular | `simulation/` | implementado en numba; 11 pruebas sintéticas; Rothermel contrastado con referencia |
| 10 | Almacenamiento de resultados temporales | `simulation/motor.py` (`t_llegada_s.tif`, serie, registro) | implementado |
| 11 | Validación espacial y temporal | `validation/metricas.py`, `scripts/validar.py` | implementado y ejecutado (3 eventos) |
| 12 | API | `api/app.py`, `api/trabajos.py` | implementada; 5 pruebas; trabajo de extremo a extremo probado |
| 13 | Interfaz web | `web/` | implementada; verificada en navegador (carga, barra temporal, capas) |
| 14 | Pruebas automáticas y de rendimiento | `tests/` (46), `scripts/benchmark.py` | pasan; benchmark ejecutado |
| 15 | Documentación de instalación y ejecución | `README.md`, `requirements.txt` | hecha |
| 16 | Documentación científica | `docs/metodologia_cientifica.md`, `docs/02`, `docs/04` | hecha |
| 17 | Informe de la primera simulación histórica | `docs/informe_simulacion_SL-2024-LASLAGUNAS.md` | hecho |
| 18 | Registro de tiempos, memoria y superficie | `docs/05`, `data/resultados/benchmark/`, `registro.json` de cada corrida | hecho |
| 19 | Limitaciones e incertidumbres | este documento §4, `docs/07` §4–5 | hecho |
| 20 | Instrucciones para nuevas áreas e incendios | `README.md` | hechas |

## 2. Dominio, resolución y rendimiento (resumen de mediciones)
- Dominio completo de **2.500 km² a 30 m** en todas las corridas; nunca se redujo ni se cambió la resolución. Área efectiva 2.500,14 km² (2.777.934 celdas).
- Simulación completa de 21 días: 103–146 s, < 1,5 GB; peor caso (quema total del dominio) 128 s. Autómata: 0,7–1,7 ms/paso según el frente. WindNinja: 42 min una vez por dominio. Índices GEE: 20 min por evento. Meteorología: 22 s.

## 3. Resultados científicos
- Calibración (2024): IoU 0,39 / Dice 0,57 al final de la fase explosiva, 56 % de focos VIIRS alcanzados el mismo día, desfase mediano 5,5 h. Un factor global no supera 0,34; los factores por clase llevan la meseta a 0,38–0,40.
- Validación (2022): el modelo cubre las cicatrices (omisión 3–5 %) y llega a tiempo a los focos (31–80 %), pero sobreestima la superficie 7–10 veces por ausencia de mitigación y barreras, y por parámetros calibrados en un megaincendio (IoU 0,09–0,14; con k = 1, 0,15–0,18).
- Hallazgos sobre los datos: el punto SNMF de Renca no es el origen (contradice el viento); la asignación inicial de análogos de combustible estaba invertida (bosque serrano propaga más rápido que su análogo; pasturas de llanura menos); la hora de ignición es secundaria.

## 4. Limitaciones e incertidumbres (consolidadas)
1. **Sin mitigación ni barreras**: la causa principal de la comisión. Requiere al menos un modelo de contención de perímetro y de cruce de caminos/parcelas dependiente de la intensidad.
2. **Combustibles por analogía**: cargas, σ, profundidad y M_x de Scott & Burgan; k por clase absorbe el error. Sin medición de campo ni validación de los umbrales NDVI/NDMI.
3. **Humedad**: FFMC canadiense sin calibración local; LFMC desde NDMI por escalado lineal hipotético.
4. **Meteorología de modelo** (IFS 9 km) promediada en el dominio; sin observaciones de estación; no se probó ERA5 como fuente alternativa.
5. **Viento**: neutral, un tipo de vegetación, 100 m efectivos; sin brisas térmicas.
6. **Referencia**: cicatriz MapBiomas anual/mensual sin exactitud local conocida; sin perímetros intermedios (salvo focos de calor).
7. **Ignición**: lugares informados ≠ origen; hora desconocida.
8. **Modelo**: elipse de Anderson más ancha que las lenguas observadas; suma vectorial viento-pendiente sobrestima en viento cruzado; sin spotting ni fuego de copas; discretización de LFMC (10 clases) y curado (2 niveles).

## 5. No verificado
- Velocidad instantánea del frente y evolución del perímetro a escala horaria (solo focos diarios/horarios).
- Transferencia de la calibración a otros dominios o temporadas (la validación de verano fue negativa en extensión).
- Landsat como fuente de índices; Open-Meteo en modo pronóstico (implementado, no ejecutado).
- Ejecución en Linux/macOS; versiones de Python < 3.14.
- Uso concurrente de la API por varios usuarios.

## 6. Mejoras futuras recomendadas (en orden de impacto esperado)
1. Mitigación mínima y barreras lineales (caminos, cortafuegos, parcelas) con probabilidad de cruce por intensidad.
2. Más eventos de calibración/validación y perímetros intermedios (p. ej. VIIRS agrupados por paso satelital como perímetros horarios).
3. Relación largo/ancho dependiente del combustible y del viento efectivo; evaluar el modelo de Alexander (1985) o Anderson con ajustes.
4. WindNinja con cobertura de dosel por celda (LCP) y pruebas con `diurnal_winds`.
5. Segunda fuente meteorológica (ERA5) y análisis de sensibilidad meteorológica.
6. Calibración bayesiana o por ensambles de k, WAF, LFMC con cuantificación de incertidumbre.
7. Despliegue de la API con cola de trabajos y autenticación si se expone en red.

## 7. Reproducibilidad
Cada corrida guarda `registro.json` (configuración, k, versión del código, tiempo, memoria, motivo de fin, entradas), `metricas.json` y los rasters; cada producto derivado tiene JSON de procedencia con hashes SHA-256; las configuraciones están en `config/`; las versiones del entorno en `requirements.txt`; la biblioteca de viento es reutilizable y reanudable. Dos corridas con la misma configuración producen resultados idénticos bit a bit (prueba automática).
