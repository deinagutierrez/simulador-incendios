"""Índice HTML de las corridas de resultados/v4.0: una fila por corrida con su resumen y el enlace al visor.

Uso (desde src/v4.0):
  python scripts/exportar_indice.py [--todas] [--salida resultados/v4.0/index.html]

`--todas` genera también el visor (`<run_id>/visor.html`) de cada corrida que no lo tenga. Los enlaces son relativos a
la carpeta del índice; por defecto el índice queda en resultados/v4.0/index.html junto a las corridas.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from incendios_sl import config as cfgmod  # noqa: E402

PLANTILLA = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corridas v4.0</title>
<style>
:root{{--bg:#f3f1ec;--panel:#fff;--ink:#1c2430;--ink2:#5b6573;--line:#d8d4cb;--accent:#1f5f8b;--burn:#d9541e}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#171a1f;--panel:#1f242b;--ink:#e8e6e1;--ink2:#9aa3ae;--line:#343a43;--accent:#6fb3e0;--burn:#ff7a3d}}}}
:root[data-theme="dark"]{{--bg:#171a1f;--panel:#1f242b;--ink:#e8e6e1;--ink2:#9aa3ae;--line:#343a43;--accent:#6fb3e0;--burn:#ff7a3d}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
main{{max-width:1200px;margin:0 auto;padding:24px 16px}} h1{{font-size:24px;margin:0 0 4px}} p.sub{{color:var(--ink2);margin:0 0 20px}}
table{{width:100%;border-collapse:collapse;background:var(--panel);font-variant-numeric:tabular-nums}} th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--ink2);font-weight:600;font-size:13px}} td.n{{text-align:right}} a{{color:var(--accent)}} .burn{{color:var(--burn);font-weight:600}}
.wrap{{overflow-x:auto}} small{{color:var(--ink2)}}
</style></head><body><main>
<h1>Simulador de incendios San Luis v4.0 — corridas</h1>
<p class="sub">Código {version} (SIM). Cada fila es una ejecución de <code>scripts/correr_escenario.py</code>; el visor muestra la propagación hora a hora. {n} corridas, actualizado {fecha}.</p>
<div class="wrap"><table><thead><tr><th>Corrida</th><th>Fecha</th><th>Evento / caso</th><th>Modelo</th><th>Variante</th><th>Horas</th><th>ha final</th><th>ha a 72 h</th><th>IoU 1.ª eval.</th><th>Visor</th><th>Resumen</th></tr></thead><tbody>
{filas}
</tbody></table></div>
<p><small>Corridas en <code>escenarios/v4.0/corridas/</code>; insumos en <code>datos/inputSimulacion/</code> y <code>datos/procesados/v4.0/</code>.</small></p>
</main></body></html>"""


def _num(x, d=0):
    return "—" if x is None else f"{float(x):,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def main() -> int:
    ap = argparse.ArgumentParser(description="Índice HTML de las corridas de resultados/v4.0")
    ap.add_argument("--todas", action="store_true", help="generar el visor de las corridas que no lo tengan")
    ap.add_argument("--salida", help="archivo HTML (por defecto resultados/v4.0/index.html)")
    a = ap.parse_args()
    R = cfgmod.dir_resultados()
    out = Path(a.salida) if a.salida else R / "index.html"
    filas = []
    for d in cfgmod.corridas_guardadas():          # primer nivel y resultados/v4.0/<grupo>/<run_id> (E032)
        res = sorted(d.glob("resumen_*.json"))
        if not res or not (d / "registro.json").exists():
            continue
        r = json.loads(res[-1].read_text(encoding="utf-8"))
        visor = d / "visor.html"
        if a.todas and not visor.exists():
            from exportar_visor import exportar
            try:
                exportar(d.name, visor)
            except Exception as ex:  # una corrida incompleta no frena el índice
                print("sin visor", d.name, ex)
        rel = lambda p: html.escape(Path(os.path.relpath(p, out.parent)).as_posix())
        esp = (r.get("validacion") or {}).get("espacial") or []
        iou = f"{esp[0]['iou']:.2f}" if esp and esp[0].get("iou") is not None else "—"
        s = r.get("serie") or {}; mo = r.get("modelo") or {}
        md = sorted(d.glob("resumen_*.md"))
        origen = r.get("evento") or (f"{r.get('caso')} ({r.get('variante_caso')})" if r.get("caso") else "SIM")
        if r.get("evento"):
            origen += f" · h{r.get('hipotesis_ignicion')} · {r.get('ignicion')}"
        filas.append(f"<tr><td>{html.escape(d.name)}</td><td>{str(r.get('fecha_corrida', ''))[:16].replace('T', ' ')}</td><td>{html.escape(str(origen))}</td>"
                     f"<td>{html.escape(str(mo.get('nombre')))}</td><td>{html.escape(str(mo.get('variante') or '—'))}</td><td class='n'>{_num(r.get('horas_simuladas'), 1)}</td>"
                     f"<td class='n burn'>{_num((r.get('superficie') or {}).get('ha_quemadas_final'))}</td><td class='n'>{_num(s.get('ha_a_72h'))}</td><td class='n'>{iou}</td>"
                     f"<td>{f'<a href={chr(34)}{rel(visor)}{chr(34)}>abrir</a>' if visor.exists() else '—'}</td>"
                     f"<td>{f'<a href={chr(34)}{rel(md[-1])}{chr(34)}>resumen</a>' if md else ''}</td></tr>")
    from incendios_sl import __version__
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PLANTILLA.format(version=__version__, n=len(filas), fecha=datetime.now().strftime("%d/%m/%Y %H:%M"), filas="\n".join(filas)), encoding="utf-8")
    print("índice:", out, len(filas), "corridas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
