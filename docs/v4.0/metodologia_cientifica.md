# Metodología científica consolidada

Este documento reúne las ecuaciones, variables, unidades, supuestos y referencias del simulador tal como está implementado (versión 0.1.0). Para cada elemento se indica su origen: **[BIBLIO]** publicado, **[MEDIDO]** obtenido de datos o pruebas en este proyecto, **[CALIBRADO]** ajustado con el evento 2024, **[HIPÓTESIS]** supuesto por falta de información.

## 1. Dominio y grilla
- CRS EPSG:5345 (POSGAR 2007 / Argentina faja 3); grilla 1.672 × 1.671 celdas de 30 m (2.793.912), dominio exacto de 2.500,14 km² (2.777.934 celdas) [MEDIDO]. Superficie de celda 900 m².
- DEM Copernicus GLO-30 (GEE `COPERNICUS/DEM/GLO30_2024_1`), remuestreo bilineal a 30 m; pendiente y orientación por el operador de Horn (1981) sobre 3 × 3 (misma convención que `gdaldem`) [BIBLIO/MEDIDO]. Comparado con ASTER GDEM: diferencia media 0,2 m, desvío 4,6 m [MEDIDO].

## 2. Meteorología
- Open-Meteo Historical Weather API, modelo `ecmwf_ifs` (análisis IFS 9 km, desde 2017) para 2022–2025; `era5` (25 km) alternativo. Son datos de modelo, no observaciones. 16 puntos (4 × 4) sobre dominio + 10 km; serie del dominio por promedio aritmético (T, HR, lluvia) y vectorial del viento (U = −v·sin θ, V = −v·cos θ con θ dirección "desde") [MEDIDO: convención verificada contra componentes U/V de ERA5-Land].
- Control de calidad: rangos físicos, duplicados, huecos (rechazo si > 2 h consecutivas sin datos obligatorios).

## 3. Viento ajustado al relieve (WindNinja 4.0.0)
- Solver de conservación de masa (Forthofer, Butler & Wagenbrenner 2014) [BIBLIO], malla 100 m, vegetación `brush`, estabilidad neutra, salida a 10 m sobre la vegetación; dominio ampliado 10.020 m.
- Linealidad: campo(a·U) = a·campo(U) con error < 0,15 % [MEDIDO]; por ello se calcula una biblioteca de 72 campos unitarios (clases de 5°) y cada hora se obtiene como v_h · campo(θ_h) con interpolación angular entre clases vecinas. Remuestreo bilineal de U y V a 30 m. Resolución efectiva del viento: 100 m.
- Limitaciones: sin brisas térmicas (`diurnal_winds` desactivado), un solo tipo de vegetación, condición de contorno uniforme, estados estacionarios por hora.

## 4. Combustibles
### 4.1 Clases (v1) [HIPÓTESIS con reglas explícitas]
Cobertura MapBiomas Col. 3 del año anterior al evento → 8 clases locales (tabla `data/derivados/combustibles/tabla_combustibles_v1.csv`): 0 no combustible (agua, urbano, desnudo), 1 pastizal natural (GR2), 2 pastura/cultivo (GR1; no combustible si NDVI < 0,15), 3 arbustal abierto/mosaico (GS2), 4 arbustal cerrado (SH2), 5 bosque abierto (GS2), 6 bosque cerrado/inundable (TU1), 7 plantación (TL2). Los parámetros físicos (cargas por clase de tiempo de retardo, σ, profundidad, M_x, poder calorífico) son los del modelo análogo de Scott & Burgan (2005) [BIBLIO], convertidos a SI, **no medidos localmente**.
### 4.2 Curado herbáceo [HIPÓTESIS]
Fracción de la carga herbácea viva transferida a muerta (modelos dinámicos): 0,8 si NDVI pre-incendio < 0,35; 0,5 si ≥ 0,35. Alternativa estándar disponible: T = (1,20 − LFMC)/0,90 acotado a [0, 1] (Scott & Burgan 2005).
### 4.3 Índices
NDVI = (B8 − B4)/(B8 + B4); NDMI = (B8 − B11)/(B8 + B11), Sentinel-2 SR Harmonized, máscara Cloud Score+ (`cs_cdf ≥ 0,6`), mediana de las escenas de las 7 semanas previas a la ignición, salida 20 m → promedio a 30 m [MEDIDO]. Landsat 8/9 C2 L2 como respaldo (sin mezclar sensores).
### 4.4 Humedad del combustible
- Muerto fino (1 h): FFMC horario de Van Wagner (1977) y Van Wagner & Pickett (1985), implementación portada de `cffdrs` (R) [BIBLIO]; m = 147,27·(101 − F)/(59,5 + F) (%). Entradas: T (°C), HR (%), viento 10 m (km/h), lluvia (mm/h); inicialización F = 85 un día antes. 10 h = 1 h + 1 %; 100 h = 1 h + 2 % [HIPÓTESIS]. Lluvia 24 h ≥ 5 mm → sin propagación esa hora [HIPÓTESIS].
- Vivo: LFMC_herb = 30 + 90·clip((NDMI + 0,1)/0,5, 0, 1) (%); LFMC_leñoso = 60 + 90·(ídem) [HIPÓTESIS/CALIBRAR; Yebra et al. 2013 documentan la relación y su incertidumbre]. En el simulador se discretiza en 10 clases.

## 5. Velocidad de propagación (Rothermel 1972 con Albini 1976; Andrews 2018)
Unidades internas imperiales (lb, ft, min, BTU); interfaz en SI. Para cada clase de combustible y hora:
- Pesos: A_i = σ_i w_{0,i}/ρ_p; f_i = A_i/Σ_cat A; f_muerto = A_muerto/A_T, f_vivo = A_vivo/A_T; σ característica por categoría y total.
- Carga neta: w_{n,i} = w_{0,i}(1 − S_T), agrupada por intervalos de σ con factores g_i (Albini 1976). S_T = 0,0555, S_e = 0,010, ρ_p = 32 lb/ft³.
- Humedad de extinción del vivo: M_{x,vivo} = max(2,9·W·(1 − M_{f,fino}/M_x) − 0,226, M_x), W = Σ_muerto w_0 e^{−138/σ} / Σ_vivo w_0 e^{−500/σ}.
- Amortiguación: η_M = 1 − 2,59 r + 5,11 r² − 3,52 r³ con r = min(M_f/M_x, 1); η_s = 0,174·S_e^{−0,19}. Regla explícita: si M_{f,muerto} ≥ M_x, R = 0.
- β = ρ_b/ρ_p, ρ_b = Σw_0/δ; β_op = 3,348·σ^{−0,8189}; Γ'_max = σ^{1,5}/(495 + 0,0594·σ^{1,5}); A = 133·σ^{−0,7913}; Γ' = Γ'_max (β/β_op)^A e^{A(1 − β/β_op)}.
- I_R = Γ'·(w_{n,muerto} h η_{M,muerto} + w_{n,vivo} h η_{M,vivo})·η_s; ξ = e^{(0,792 + 0,681 σ^{0,5})(β + 0,1)}/(192 + 0,2595 σ).
- Sumidero: ρ_b ε Q_ig = ρ_b Σ_cat f_cat Σ_i f_i e^{−138/σ_i}(250 + 1116 M_{f,i}).
- R_0 = I_R ξ/(ρ_b ε Q_ig) (ft/min). Viento: φ_w = C·U^B·(β/β_op)^{−E}, C = 7,47 e^{−0,133 σ^{0,55}}, B = 0,02526 σ^{0,54}, E = 0,715 e^{−3,59·10^{−4} σ}, U en ft/min a media llama. Pendiente: φ_s = 5,275 β^{−0,3} tan²α.
- Verificación: coincide con la implementación de referencia de `firebench` (variante WRF-SFIRE) dentro del 0,02 % para una clase muerta [MEDIDO]. Sin límite de viento (Andrews, Cruz & Rothermel 2013).
- Factor de ajuste por clase k_c (multiplica R): calibrado {1–3: 0,5; 4–5: 3; 6–7: 5} [CALIBRADO con 2024]; absorbe carga real y ausencia de supresión.

## 6. Viento a media llama y combinación con la pendiente
- WAF sin abrigo (Baughman & Albini 1980; Andrews 2012): U_mf/U_ref = 1,83 / ln((z_ref + 0,36 H)/(0,13 H)) con z_ref = 10 m sobre la vegetación y H la profundidad del lecho [BIBLIO]; factor de abrigo de dosel {clases 4: 0,8; 5: 0,6; 6–7: 0,4} [HIPÓTESIS].
- Vector de viento a media llama (dirección "hacia") + vector de pendiente cuesta arriba de módulo U_s tal que φ_w(U_s) = φ_s → U_eff y θ_max; φ_c = φ_w(U_eff); R_cabeza = k·R_0·(1 + φ_c) (método de Rothermel 1983 / Finney 1998, Andrews 2018) [BIBLIO]. Limitación: sobrestimación en viento cruzado fuerte (Sharples 2008).
- Elipse de Anderson (1983): LB = 0,936 e^{0,2566 U} + 0,461 e^{−0,1548 U} − 0,397 (U_eff en mph, LB ≤ 8); e = √(LB² − 1)/LB; R(θ) = R_cabeza (1 − e)/(1 − e cos(θ − θ_max)) [BIBLIO].

## 7. Autómata celular
- Estados: 255 fuera, 0 no combustible, 1 combustible, 2 frente activo, 3 quemada; sin reencendido.
- Estencil de 16 vecinos con distancias reales (30; 42,43; 67,08 m) para reducir el sesgo direccional de la grilla (error de isotropía ≤ 2,5 % frente a 6,7 % con 8 vecinos) [MEDIDO].
- Avance por enlace: f_{ij} ← f_{ij} + Δt·R_i(θ_{ij})/d_{ij}; ignición de j cuando f ≥ 1 en el instante exacto del cruce; j propaga en el resto del paso (sin límite de una celda por paso); Δt = 60 s; resultado independiente de Δt entre 30 y 300 s [MEDIDO]. Es la versión discreta del principio de tiempo mínimo de viaje (Finney 2002).
- Meteorología y viento constantes dentro de cada hora; tablas de R_0 por (clase × 10 clases de LFMC × 2 niveles de curado) recalculadas cada hora.
- Fin: fecha documentada, fin de meteorología, N = 12 h sin avance (humedad ≥ M_x o lluvia), límite computacional, frente agotado.

## 8. Validación
- Espacial: IoU, Dice, superficies, omisión, comisión sobre celdas del dominio con combustible; referencia MapBiomas Fuego Col. 1 (polígono, o píxeles del mes para eventos fusionados).
- Temporal: fracción de focos VIIRS (375 m) / MODIS (1 km) cuyo entorno está quemado al final del día local de detección; desfase mediano (horas) entre llegada simulada y hora de paso (VIIRS). Formalismo inspirado en Filippi, Mallet & Nader (2014).
- Separación calibración (2024) / validación (2022 × 2) / sensibilidad.

## 9. Referencias (verificadas en línea durante el proyecto)
- Albini, F. A. (1976). *Estimating wildfire behavior and effects.* USDA FS GTR INT-30.
- Anderson, H. E. (1983). *Predicting wind-driven wild land fire size and shape.* USDA FS Res. Pap. INT-305.
- Andrews, P. L. (2012). *Modeling wind adjustment factor and midflame wind speed for Rothermel's surface fire spread model.* RMRS-GTR-266.
- Andrews, P. L.; Cruz, M. G.; Rothermel, R. C. (2013). Examination of the wind speed limit function in the Rothermel surface fire spread model. *Int. J. Wildland Fire* 22: 959–969.
- Andrews, P. L. (2018). *The Rothermel surface fire spread model and associated developments: A comprehensive explanation.* RMRS-GTR-371.
- Baughman, R. G.; Albini, F. A. (1980). Estimating midflame windspeeds. *Proc. 6th Conf. Fire and Forest Meteorology.*
- Filippi, J.-B.; Mallet, V.; Nader, B. (2014). Representation and evaluation of wildfire propagation simulations. *Int. J. Wildland Fire* 23: 46–57.
- Finney, M. A. (1998). *FARSITE: Fire Area Simulator — model development and evaluation.* RMRS-RP-4.
- Finney, M. A. (2002). Fire growth using minimum travel time methods. *Can. J. For. Res.* 32: 1420–1424.
- Forthofer, J. M.; Butler, B. W.; Wagenbrenner, N. S. (2014). A comparison of three approaches for simulating fine-scale surface winds in support of wildland fire management. Part I. *Int. J. Wildland Fire* 23: 969–981.
- Rothermel, R. C. (1972). *A mathematical model for predicting fire spread in wildland fuels.* INT-115.
- Scott, J. H.; Burgan, R. E. (2005). *Standard fire behavior fuel models.* RMRS-GTR-153.
- Sharples, J. J. (2008). Review of formal methodologies for wind–slope correction of wildfire rate of spread. *Int. J. Wildland Fire* 17: 179–193.
- Van Wagner, C. E. (1977). *A method of computing fine fuel moisture content throughout the diurnal cycle.* CFS Inf. Rep. PS-X-69; Van Wagner, C. E.; Pickett, T. L. (1985). *Equations and FORTRAN program for the Canadian Forest Fire Weather Index System.* For. Tech. Rep. 33.
- Yebra, M. et al. (2013). A global review of remote sensing of live fuel moisture content for fire danger assessment. *Remote Sens. Environ.* 136: 455–468.
- Documentación oficial: WindNinja (GitHub firelab/windninja, CLI 4.0.0), Open-Meteo (docs y términos), Google Earth Engine (catálogo), MapBiomas Argentina (metadatos de descarga), cffdrs (GitHub cffdrs/cffdrs_r), firebench 0.10.0.

Nota: las fichas bibliográficas de Albini 1976, Anderson 1983, Andrews et al. 2013, Baughman & Albini 1980, Finney 1998 y Van Wagner & Pickett 1985 provienen del conocimiento previo del equipo y de su cita en Andrews (2018); las demás se verificaron en línea durante la Etapa 2. Ninguna ecuación se tomó de una fuente no identificada.
