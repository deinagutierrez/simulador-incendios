"""Resumen estadístico de una corrida: un JSON y un Markdown por ejecución, con la fecha de la corrida en el nombre.

Se escribe al terminar la simulación (motor.Simulacion.guardar) y se vuelve a escribir, ya con métricas de
validación, al terminar scripts/validar.py. Ambos archivos quedan en el directorio de la corrida, dentro de
resultados/<versión>/.
"""
from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .. import config as cfgmod


def _cargar(p: Path, defecto: Any = None) -> Any:
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return defecto


def resumen_de_corrida(out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    reg = _cargar(out_dir / "registro.json", {})
    met = _cargar(out_dir / "metricas.json")
    serie = pd.read_csv(out_dir / "serie_horaria.csv") if (out_dir / "serie_horaria.csv").exists() else pd.DataFrame()
    ent = reg.get("entradas", {})
    r: dict[str, Any] = {
        "run_id": out_dir.name,
        "fecha_corrida": reg.get("fecha_corrida") or datetime.now().astimezone().isoformat(timespec="seconds"),
        "version_codigo": reg.get("version_codigo"),
        "version_resultados": cfgmod.VERSION_RESULTADOS,
        "maquina": platform.node(),
        "evento": ent.get("evento"), "dominio": ent.get("dominio"),
        "hipotesis_ignicion": ent.get("hipotesis_ignicion"), "igniciones": ent.get("igniciones"),
        "t_inicio_utc": ent.get("t_inicio_utc"), "t_fin_simulado_utc": reg.get("t_simulado_utc"),
        "horas_simuladas": round(float(reg.get("t_simulado_s", 0)) / 3600, 1),
        "motivo_fin": reg.get("motivo_fin_texto"),
        "parametros": {"k_clase": reg.get("config", {}).get("k_clase"), "k_global": reg.get("config", {}).get("k_global"),
                       "factor_waf": reg.get("config", {}).get("factor_waf"), "dt_s": reg.get("config", {}).get("dt_s"),
                       "vecindad": reg.get("config", {}).get("vecindad")},
        "costo": {"pasos": reg.get("pasos"), "segundos_cpu": reg.get("segundos_cpu"), "memoria_pico_gb": reg.get("memoria_pico_gb")},
        "superficie": {"ha_quemadas_final": reg.get("ha_quemadas"), "celdas_quemadas": reg.get("celdas_quemadas")},
    }
    # v3: modelo, humedad muerta, barreras y contención (docs/10-13)
    v2 = reg.get("v2") or {}
    r["modelo"] = {"nombre": ent.get("modelo_nombre", "modelo_v1"), "humedad_muerta": ent.get("humedad_muerta"),
                   "barreras": bool(v2.get("barreras_activo")), "contencion": bool(v2.get("contencion_activo"))}
    if v2.get("barreras_activo") or v2.get("contencion_activo"):
        r["mitigacion"] = {k: v2.get(k) for k in ("cruces_barrera", "bloqueos_barrera", "celdas_contenidas_final", "escapes", "metros_linea",
                                                  "despacho_modo", "contencion_inicio_utc", "aereo_auto_desde_utc")} | {"despacho": ent.get("despacho")}
    if len(serie):
        inc = serie["ha_quemadas"].diff().fillna(serie["ha_quemadas"])
        i = int(inc.idxmax())
        r["serie"] = {
            "horas": int(len(serie)),
            "ha_a_24h": float(serie["ha_quemadas"].iloc[min(23, len(serie) - 1)]),
            "ha_a_72h": float(serie["ha_quemadas"].iloc[min(71, len(serie) - 1)]),
            "max_ha_por_hora": round(float(inc.max()), 1), "hora_pico_utc": str(serie["time_utc"].iloc[i]),
            "max_celdas_activas": int(serie["celdas_activas"].max()),
            "viento_10m_ms": {"media": round(float(serie["wind_speed_10m"].mean()), 2), "max": round(float(serie["wind_speed_10m"].max()), 2)},
            "humedad_relativa_pct": {"media": round(float(serie["relative_humidity_2m"].mean()), 1), "min": round(float(serie["relative_humidity_2m"].min()), 1)},
            "temperatura_c": {"media": round(float(serie["temperature_2m"].mean()), 1), "max": round(float(serie["temperature_2m"].max()), 1)},
        }
    if met:
        r["validacion"] = {
            "espacial": [{k: m.get(k) for k in ("t_eval_utc", "horas_desde_ignicion", "ha_sim", "ha_ref", "iou", "dice", "omision", "comision")} for m in met.get("espacial", [])],
            "temporal": met.get("temporal"),
        }
    return r


def _md(r: dict[str, Any]) -> str:
    f = lambda x, d=0: "—" if x is None else f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    L = [f"# Resumen de la corrida `{r['run_id']}`", "",
         f"Fecha de la corrida: {r['fecha_corrida']} · código {r.get('version_codigo')} · resultados {r['version_resultados']} · máquina {r['maquina']}", "",
         f"Evento **{r.get('evento')}** en el dominio {r.get('dominio')}, hipótesis de ignición {r.get('hipotesis_ignicion')}, desde {r.get('t_inicio_utc')} hasta {r.get('t_fin_simulado_utc')} ({r['horas_simuladas']} h). Fin: {r.get('motivo_fin')}.", "",
         "| Indicador | Valor |", "| --- | --- |",
         f"| Superficie quemada final (ha) | {f(r['superficie']['ha_quemadas_final'])} |",
         f"| Pasos / segundos de CPU / memoria pico (GB) | {f(r['costo']['pasos'])} / {f(r['costo']['segundos_cpu'], 1)} / {f(r['costo']['memoria_pico_gb'], 2)} |",
         f"| k por clase | {r['parametros']['k_clase']} |", f"| Factor WAF / dt (s) | {r['parametros']['factor_waf']} / {r['parametros']['dt_s']} |"]
    mo = r.get("modelo") or {}
    if mo:
        L.append(f"| Modelo / humedad muerta | {mo.get('nombre')} / {mo.get('humedad_muerta') or '—'} |")
        L.append(f"| Barreras / contención | {'sí' if mo.get('barreras') else 'no'} / {'sí' if mo.get('contencion') else 'no'} |")
    mi = r.get("mitigacion")
    if mi:
        L += [f"| Cruces / bloqueos de barrera | {f(mi.get('cruces_barrera'))} / {f(mi.get('bloqueos_barrera'))} |",
              f"| Celdas contenidas / escapes / línea (m) | {f(mi.get('celdas_contenidas_final'))} / {f(mi.get('escapes'))} / {f(mi.get('metros_linea'))} |",
              f"| Despacho / inicio del combate (UTC) | {mi.get('despacho_modo')} / {(mi.get('contencion_inicio_utc') or '—')[:16]} |"]
    s = r.get("serie")
    if s:
        L += [f"| Superficie a 24 h / 72 h (ha) | {f(s['ha_a_24h'])} / {f(s['ha_a_72h'])} |",
              f"| Máximo avance horario (ha/h) y hora | {f(s['max_ha_por_hora'], 1)} · {s['hora_pico_utc']} |",
              f"| Viento 10 m media / máx (m/s) | {s['viento_10m_ms']['media']} / {s['viento_10m_ms']['max']} |",
              f"| Humedad relativa media / mín (%) | {s['humedad_relativa_pct']['media']} / {s['humedad_relativa_pct']['min']} |",
              f"| Temperatura media / máx (°C) | {s['temperatura_c']['media']} / {s['temperatura_c']['max']} |"]
    v = r.get("validacion")
    if v and v.get("espacial"):
        L += ["", "## Ajuste contra la cicatriz", "", "| Evaluación (UTC) | h | ha sim | ha ref | IoU | Dice | Omisión | Comisión |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for m in v["espacial"]:
            L.append(f"| {m['t_eval_utc']} | {m['horas_desde_ignicion']} | {f(m['ha_sim'])} | {f(m['ha_ref'])} | {m['iou']:.3f} | {m['dice']:.3f} | {m['omision']:.2f} | {m['comision']:.2f} |")
        t = v.get("temporal") or {}
        if t.get("fraccion_capturada_total") is not None:
            L += ["", f"Focos de calor: capturados {t['fraccion_capturada_total']:.2f} del total, {t['fraccion_capturada_al_fin_del_dia']:.2f} al fin del día; desfase mediano {'—' if t.get('desfase_mediano_h') is None else f"{float(t['desfase_mediano_h']):.1f}"} h."]
    return "\n".join(L) + "\n"


def escribir_resumen(out_dir: Path) -> tuple[Path, Path]:
    """Escribe resumen_<run_id>_<fecha>.json y .md en el directorio de la corrida y devuelve sus rutas."""
    out_dir = Path(out_dir)
    r = resumen_de_corrida(out_dir)
    marca = datetime.fromisoformat(r["fecha_corrida"]).strftime("%Y%m%d-%H%M")
    nombre = r["run_id"] if r["run_id"].endswith(marca) else f"{r['run_id']}_{marca}"
    pj = out_dir / f"resumen_{nombre}.json"; pm = pj.with_suffix(".md")
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2, ensure_ascii=False, default=str)
    pm.write_text(_md(r), encoding="utf-8")
    return pj, pm
