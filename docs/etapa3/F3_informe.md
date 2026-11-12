# F3 — Pantalla del simulador: informe

Fecha: 2026-11-11 · Rama: `f3-interfaz` (sale de `f2-servidor`) · Equipo: Windows 11, Python 3.14.7.
Rótulos: **(dato)** medido ese día en ese equipo · **(inferencia)** · **(sin verificar)**.
La hizo el mismo frente que la F1 y la F2, por pedido del usuario (decisión D-E3-22). **No tuvo pedido de aprobación previo
como la F2**: las decisiones de diseño de esta fase están en §5, para que la otra persona las revise.

## 1. Qué es

`python app/servir.py` abre el navegador en la pantalla del simulador (`app/web/index.html`): un mapa del dominio a la derecha
y un panel a la izquierda. Se elige el motor, se marca el punto de ignición con un clic, se pone día, hora y duración, y se
inicia. La huella crece en el mapa hora por hora. La página mínima de la F2 sigue en `/prueba`.

## 2. Lista de aceptación del plan (`00_plan.md` §2.5)

| Requisito | Hecho | Falta |
|---|---|---|
| 1. Mapa con capas | relieve sombreado, pendiente, caminos, viviendas, red de media tensión, cuarteles, tiempo de arribo, NDVI, NDMI, combustible de 7 clases (v3.1), cobertura MapBiomas, borde del dominio, área quemada simulada, cicatriz del incendio histórico, mapa de calles en línea opcional (OpenStreetMap) | mapa de combustible SB40 de v4.0; "quemado en la última hora" como capa aparte; cortafuegos (F5); focos VIIRS (F6); mapa base de Esri |
| 2. Panel lateral | configuración (motor, ignición, día y hora, horas), resumen de lo pedido, botones Iniciar, Pausar, Reanudar, Detener y Nueva simulación, estado (hora simulada, celdas activas, segundos por hora simulada) | viento en la configuración (F5); fecha de índices y de pronóstico, y la zona para actualizar o cargar datos (F4) |
| 3. Línea de tiempo | barra de avance durante la corrida, deslizador hora por hora, botón de reproducir | — |
| 4. Salidas | superficie en ha y km², tiempo simulado y de cómputo, motivo de fin, pausas, gráfico de hectáreas contra tiempo con tabla; viviendas, red eléctrica y caminos alcanzados **solo con v4.0** | la exposición con v3.1 (ese motor no la calcula); cortafuegos y cambios de viento (F5) |
| 5. Exportar | zip por corrida con `corrida.json`, las salidas del motor y los perímetros por hora en GeoJSON | visor autónomo con el formato de v3.1 (F7) |
| Comparación entre motores (decisión D-E3-05) | las dos huellas superpuestas, coincidencia a las 24 h y al final, envolvente, aviso si coinciden en menos de la mitad | — |
| Criterio: Chrome, Edge y Firefox de escritorio | (dato) probada en el navegador integrado de la herramienta, que es de la familia de Chrome | **Edge y Firefox, sin verificar** |
| Criterio: la interfaz responde durante la corrida | (dato) se pausó, reanudó y detuvo una corrida de 48 h mientras avanzaba | — |

## 3. Qué se agregó

| Parte | Archivos | Qué hace |
|---|---|---|
| Pantalla | `app/web/index.html`, `app.js`, `estilo.css` | mapa, panel, línea de tiempo, gráfico, comparación, simulaciones anteriores |
| Biblioteca de mapas | `app/web/vendor/leaflet/` | Leaflet 1.9.4, copiada dentro del repositorio para que funcione sin internet (licencia BSD de 2 cláusulas, incluida) |
| Capas de fondo | `app/servidor/capas.py` | pasa cada capa a la proyección de los mapas web, la pinta y la guarda en `datos/procesados/app/capas/`; entrega los vectores en GeoJSON |
| Huella | `app/servidor/huella.py` | color plano para comparar, contorno en GeoJSON, comparación entre dos huellas |
| Pedidos nuevos | `app/servidor/app.py` | capas, vectores, contorno, exportación y comparación (contrato §4, versión 1.3) |

## 4. Verificación

- (dato) **Pruebas del servidor**: 14, de las cuales 3 son nuevas (pantalla y archivos, capas de fondo, contorno + comparación
  + exportación). Verificación completa del clon: ver al final.
- (dato) **En el navegador**, con los motores reales sobre Las Lagunas 2024:
  - modo "ambos", 30 h: las dos corridas terminaron (v4.0, 2.963 ha; v3.1 librev2, 8.136 ha), se dibujaron las dos huellas,
    el gráfico con las dos líneas y la comparación: coinciden en el 34 % del área a las 24 h, y la pantalla mostró el aviso
    de discrepancia;
  - punto de ignición marcado con un clic en el mapa;
  - v4.0, 48 h: pausa (quedó en la hora 29 y no avanzó), reanudación y detención (hora 43); el resumen mostró "Detenida por
    el usuario" y la pausa;
  - deslizador en la hora 12: la huella y el gráfico pasaron a esa hora;
  - una simulación anterior se volvió a abrir desde la lista;
  - capas de combustible, viviendas y cuarteles con su leyenda;
  - sin errores de la pantalla en la consola del navegador.
- Lo que **no** tiene prueba automática: la pantalla en sí (los clics). Se probó a mano en una sola sesión.

## 5. Decisiones de diseño de esta fase, a revisar

1. **Leaflet copiada en el repositorio** (150 KB) en lugar de cargarla de internet: el simulador tiene que andar sin conexión.
2. **Sin mapa de calles por defecto.** El fondo es el relieve propio; el mapa en línea de OpenStreetMap es una casilla
   opcional que necesita internet.
3. **Hora argentina (UTC−3) en la pantalla**; al servidor se le manda en UTC.
4. **Modo "ambos": v4.0 con relleno de amarillo a rojo y v3.1 librev2 en azul**, superpuestos. No se dibuja un promedio.
5. **La coincidencia entre motores** es el área quemada por los dos dividida por la envolvente. El aviso salta por debajo del
   50 % a las 24 h (decisión D-E3-05).
6. **La leyenda de cobertura** agrupa las clases de MapBiomas como las agrupa el modelo de v3.1 (`CLASES_V1`); los códigos 63
   y 77 figuran juntos como "arbustal abierto".
7. **El motivo de fin se traduce**: si se cumplieron las horas pedidas dice eso, aunque v3.1 lo llame "fin documentado del
   incendio"; si el motor cortó antes, muestra el texto del motor.
8. **Colores de las series**: naranja para v4.0 y azul para v3.1, los dos primeros de una paleta de referencia pensada para
   que se distingan con daltonismo. (sin verificar) No se corrió el validador de la paleta en este equipo; no hay Node.

## 6. Límites y cosas sin verificar

- (sin verificar) Edge, Firefox y Linux.
- (sin verificar) Pantallas de menos de 1.280 px de ancho; se probó a 1.366.
- (sin verificar) El mapa en línea de OpenStreetMap: la casilla está, pero no se probó con la red.
- Las imágenes de las capas continuas pesan hasta 4,6 MB cada una; en la misma computadora no molesta.
- La exposición (viviendas, red eléctrica, caminos) solo aparece con v4.0.
- (dato) En una corrida de Las Lagunas, v4.0 informó 5 % de humedad relativa a la hora 30. Es el valor que entrega el motor
  con los datos del evento; no se revisó si es correcto.
- Los datos siguen saliendo de un evento con ficha. La pantalla lo dice al pie.
- No hay todavía pantalla "Sobre el modelo" con las cifras de validación y sus límites, que el plan pide (§6.4).

## 7. Lo que sigue

1. Revisión de `f2-servidor` y `f3-interfaz` por la otra persona, incluida la lista de §5.
2. Probar en Edge, Firefox y Linux.
3. F4, datos bajados en el momento; F5, cortafuegos y viento manual.

## 8. Verificación completa del clon

(dato) `python herramientas/probar.py` con todo lo de esta fase: "Todo funciona." Versiones congeladas intactas (244
archivos), 69 pruebas de v3.1, 130 de v4.0 y 35 del simulador (procesos motor y servidor) pasan; 2 se omiten.
