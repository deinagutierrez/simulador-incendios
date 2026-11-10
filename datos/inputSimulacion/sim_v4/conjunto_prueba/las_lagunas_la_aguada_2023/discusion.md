## Discusión

**1. Propagación libre contra un incendio contenido.** Todas las variantes queman entre 2.400 y 3.000 ha en 36 h,
contra 105 ha de la cicatriz COE (error > 2.000 %, comisión ≈ 96 %). La omisión, en cambio, es de 1,6 a 2 %: la
simulación cubre casi toda la cicatriz observada y sigue de largo. El parte SNMF registra seis cuarteles de bomberos
voluntarios y el incendio extinguido al día siguiente: la cicatriz es el resultado de la **supresión**, que esta etapa
no modela por diseño (sección "Rol y objetivo" del enunciado). Por eso las métricas finales no miden la calidad del
modelo de propagación sino la ausencia de mitigación; la tabla "a igual superficie" es la que permite comparar forma
y rumbo.

**2. Hora de ignición: cambia la forma, no el área.** La superficie final varía menos de 6 % entre t0 = 06:00 y 18:00
(la ventana de 36 h siempre incluye una tarde completa), pero la comparación a igual superficie cambia por completo:
con **t0 = 06:00** el Sørensen sube a 0,49 y el centroide simulado queda a 520 m del observado, mientras que con t0 =
12:00 (supuesto del conjunto anterior) es 0,03 y 1.230 m. La explicación está en la serie ERA5: el viento sopla del
S–SSE (165–182°) a 11–19 km/h desde la madrugada hasta las 09:00, rota al E a las 11:00 y al N a las 12:00. La
cicatriz COE se extiende **al norte** del punto del parte: solo una ignición temprana, con viento sur, propaga hacia
la cicatriz; las igniciones de la tarde empujan el fuego hacia el sur, fuera de ella. Conclusión operativa: o la
ignición fue de madrugada, o el punto del parte marca el flanco sur final y no el origen. En cualquier caso el t0 de
12:00 heredado de `conjunto_pruebas` (D18) no es compatible con la cicatriz y la meteorología.

**3. Punto de ignición.** Con el punto SNMF original (88,7 m fuera de la cicatriz, al sur) y viento del N, el fuego
simulado a igual superficie no toca la cicatriz (Sørensen 0): la ubicación del punto pesa tanto como la hora. El
punto proyectado al borde es una decisión razonable pero derivada, y queda declarada.

**4. Discretización.** Entre Δt = 1 y Δt = 5 min la superficie difiere 0,04 % (requisito: < 5 %), gracias a los
sub-pasos adaptativos. La vecindad de 16 da un 50 % más de superficie que la de 8 y alcanza la superficie observada
en 3,8 h en vez de 6,9 h. No es por saltar barreras (se exige que las celdas intermedias de cada salto de caballo
sean combustibles y el resultado casi no cambió): en los tests sintéticos homogéneos ambas vecindades coinciden
dentro del 4 %, así que el efecto aparece con el **mosaico de combustibles** a 30 m. La ROS que gobierna cada
transición es la de la celda emisora; con saltos de 67 m una celda de SH5 enciende directamente celdas a dos de
distancia sin "pagar" la velocidad de las celdas lentas (TU1, GS2) que hay en el medio. Por eso la vecindad de 8
queda como valor por defecto y la de 16 se reserva para terreno homogéneo; la mejora pendiente es ponderar la ROS
emisora con la receptora (tiempo de viaje mitad y mitad), que corrige este sesgo.

**5. Perímetros alternativos.** MapBiomas Fuego 2023 marca 143 ha quemadas en agosto dentro de la caja, con Sørensen
y error del mismo orden que el COE. El evento Sentinel-2/VIIRS "2023-007" (145 ha) es otra cicatriz 8 km al NO con el
mismo nombre de parte y 11 focos VIIRS del 01-09 a las 15:26 local: es el candidato natural para el próximo caso,
porque permitiría la comparación de tiempos de llegada que acá no es aplicable (ningún foco sobre esta cicatriz).

**6. Magnitudes físicas.** En la tarde del 31-08 (HR 21–26 %, 19 km/h del N, humedad 1 h ≈ 4 %) la ROS mediana del
frente ronda 15 m/min con máximos en SH5 de varias decenas de m/min e intensidades de Byram de miles de kW/m. Son
valores coherentes con Rothermel para arbustal denso con viento, pero probablemente altos para la zona: las mayores
incertidumbres son la humedad del combustible vivo (derivada del NDMI con una relación sin calibrar), el factor de
ajuste del viento bajo arbustal y la propia serie ERA5 (celda de 28 km, relieve suavizado). Recomendación: calibrar
`humedad.viva_*`, el WAF y el ajuste topográfico con los casos grandes del conjunto anterior (SM04 Paso Grande 2024,
1.624 ha; SM05 Las Lagunas–Potrerillos 2024, 38.631 ha), donde el peso relativo de la supresión es menor, y con los
tiempos de llegada VIIRS.

**7. Borde del dominio.** En casi todas las variantes el fuego libre alcanza el borde de la caja (5 km de buffer) antes
de las 36 h, y el estado horario lo avisa. Para análisis de propagación libre conviene una caja mayor; para la
métrica a igual superficie (≈ 7 h) el borde no interviene.
