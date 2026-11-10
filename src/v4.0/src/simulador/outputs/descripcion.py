"""Descripción horaria por plantilla (sin LLM). Estilo operativo, sin adjetivos."""

from __future__ import annotations


def _n(x, dec=1):
    if x is None:
        return "s/d"
    s = f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def descripcion_hora(d: dict) -> str:
    s = d["superficie"]; p = d["perimetro"]; fr = d["frente"]; m = d["meteo"]; ex = d["exposicion"]
    h = d["hora_indice"]
    lineas = [f"PARTE HORARIO · hora {h:02d} · {d['timestamp'][:16].replace('T', ' ')} (hora local)"]
    lineas.append("")
    lineas.append(f"Superficie afectada: {_n(s['quemada_ha'])} ha (+{_n(s['incremento_ha'])} ha en la última hora). "
                  f"En combustión: {_n(s['en_combustion_ha'])} ha; consumida: {_n(s['consumida_ha'])} ha.")
    lineas.append(f"Perímetro total: {_n(p['total_km'], 2)} km; frente activo: {_n(p['activo_km'], 2)} km.")
    if fr["rumbo_cabeza_deg"] is not None and fr["velocidad_cabeza_m_min"] > 0:
        lineas.append(f"Cabeza del incendio con rumbo {fr['rumbo_cabeza_texto']} ({int(fr['rumbo_cabeza_deg'])}°), "
                      f"velocidad máxima {_n(fr['velocidad_cabeza_m_min'], 2)} m/min ({_n(fr['velocidad_cabeza_km_h'], 2)} km/h), "
                      f"ROS mediana {_n(fr['ros_mediana_m_min'], 2)} m/min. Intensidad máxima {_n(fr['intensidad_max_kw_m'], 0)} kW/m, "
                      f"longitud de llama máxima {_n(fr['longitud_llama_max_m'], 1)} m. Alcance máximo desde la ignición: {_n(fr['alcance_max_m'], 0)} m "
                      f"(+{_n(fr['avance_alcance_m'], 0)} m en la hora).")
    else:
        lineas.append("Sin propagación nueva en la última hora.")
    lineas.append(f"Meteorología: {_n(m['temp_c'])} °C, HR {int(m['hr_pct'])} %, viento {_n(m['viento_kmh'])} km/h del {m['viento_dir_texto']} "
                  f"({int(m['viento_dir_deg'])}°), precipitación {_n(m['precip_mm_h'])} mm/h. "
                  f"Humedad del combustible muerto: 1 h {_n(m['humedad_muerta_1h_pct'])} %, 10 h {_n(m['humedad_muerta_10h_pct'])} %, "
                  f"100 h {_n(m['humedad_muerta_100h_pct'])} %.")
    lineas.append(f"Exposición: viviendas afectadas {ex['viviendas_afectadas']}, amenazadas {ex['viviendas_amenazadas']} "
                  f"(de {ex['viviendas_total']} en el área). Tendido eléctrico en área quemada {_n(ex['tendido_km_quemado'], 2)} km "
                  f"({_n(ex['tendido_km_en_combustion'], 2)} km en celdas en combustión). Caminos afectados {_n(ex['caminos_km_afectados'], 2)} km, "
                  f"cortados {_n(ex['caminos_km_cortados'], 2)} km.")
    co = d.get("contencion")
    if co:
        if co["combate_iniciado"]:
            aereo = " (medio aéreo activo)" if co["aereo_activo"] else ""
            escapes = f"; escapes en la hora: {co['escapes_hora']}" if co["escapes_hora"] else ""
            lineas.append(f"Combate: {co['celdas_contenidas']} celdas contenidas; línea construida {_n(co['metros_linea_hora'], 0)} m en la hora "
                          f"({_n(co['linea_km'], 2)} km en total), producción {_n(co['tasa_linea_m_h'], 0)} m/h, umbral de sostén "
                          f"{_n(co['umbral_sostener_kw_m'], 0)} kW/m{aereo}{escapes}.")
        else:
            lineas.append(f"Combate: sin iniciar (inicio previsto a los {_n(co['inicio_min'] / 60.0, 1)} h de t0).")
    c = d.get("cambios")
    if c:
        partes = []
        if c["superficie_ha"] > 0:
            partes.append(f"superficie +{_n(c['superficie_ha'])} ha")
        if c["viviendas_afectadas"]:
            partes.append(f"viviendas afectadas {c['viviendas_afectadas']:+d}")
        if c["viviendas_amenazadas"]:
            partes.append(f"viviendas amenazadas {c['viviendas_amenazadas']:+d}")
        if abs(c["viento_kmh"]) >= 3:
            partes.append(f"viento {c['viento_kmh']:+.1f} km/h".replace(".", ","))
        if abs(c["hr_pct"]) >= 5:
            partes.append(f"HR {int(c['hr_pct']):+d} puntos")
        if abs(c["perimetro_activo_km"]) >= 0.1:
            partes.append(f"frente activo {c['perimetro_activo_km']:+.2f} km".replace(".", ","))
        if c["tendido_km_quemado"] > 0:
            partes.append(f"tendido +{_n(c['tendido_km_quemado'], 2)} km")
        if c["caminos_km_afectados"] > 0:
            partes.append(f"caminos +{_n(c['caminos_km_afectados'], 2)} km")
        lineas.append("Cambios respecto de la hora anterior: " + ("; ".join(partes) if partes else "sin cambios relevantes") + ".")
    for a in d.get("alertas", []):
        lineas.append(f"AVISO: {a}")
    return "\n".join(lineas) + "\n"
