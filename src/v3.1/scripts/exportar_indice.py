"""Genera docs/index.html: la página de inicio de GitHub Pages con la lista de corridas, su resumen y el link al visor.

Uso: python scripts/exportar_indice.py [--todas]   (--todas exporta también el visor de cada corrida que no lo tenga)
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402

PLANTILLA = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gemelo digital de incendios · San Luis · corridas</title>
<style>
:root{{--bg:#f3f1ec;--panel:#fff;--ink:#1c2430;--ink2:#5b6573;--line:#d8d4cb;--accent:#1f5f8b;--burn:#d9541e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171a1f;--panel:#1f242b;--ink:#e8e6e1;--ink2:#9aa3ae;--line:#343a43;--accent:#6fb3e0}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px}} h1{{font-size:24px;margin:0 0 4px}} p.sub{{color:var(--ink2);margin:0 0 20px}}
table{{width:100%;border-collapse:collapse;background:var(--panel);font-variant-numeric:tabular-nums}} th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--ink2);font-weight:600;font-size:13px}} td.n{{text-align:right}} a{{color:var(--accent)}} .burn{{color:var(--burn);font-weight:600}}
.wrap{{overflow-x:auto}} small{{color:var(--ink2)}}
</style></head><body><main>
<h1>Simulador de incendios San Luis — corridas publicadas</h1>
<p class="sub">Versión {version} del código. Cada fila es una ejecución; el visor muestra la propagación hora a hora sobre el mapa. {n} corridas, actualizado {fecha}.</p>
<div class="wrap"><table><thead><tr><th>Corrida</th><th>Fecha</th><th>Evento</th><th>Hip.</th><th>Horas</th><th>ha final</th><th>ha a 72 h</th><th>IoU 1ª eval.</th><th>Visor</th><th>Archivos</th></tr></thead><tbody>
{filas}
</tbody></table></div>
<p><small>Lanzar una corrida nueva: pestaña Actions → «Simular escenario» → Run workflow. Escenarios en <code>escenarios/{version}/corridas/</code>. Datos de entrada en <code>datos/inputSimulacion/</code>.</small></p>
</main></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--todas", action="store_true"); a = ap.parse_args()
    repo = cfgmod.raiz_repositorio(); R = cfgmod.dir_resultados(); V = repo / "docs" / "visor"; V.mkdir(parents=True, exist_ok=True)
    filas = []
    for d in sorted(R.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        res = sorted(d.glob("resumen_*.json")) if d.is_dir() else []
        if not res:
            continue
        r = json.load(open(res[-1], encoding="utf-8"))
        visor = V / f"{d.name}.html"
        if a.todas and not visor.exists() and (d / "t_llegada_s.tif").exists():
            from exportar_visor import exportar
            try:
                exportar(d.name, visor)
            except Exception as ex:
                print("sin visor", d.name, ex)
        esp = (r.get("validacion") or {}).get("espacial") or []
        iou = f"{esp[0]['iou']:.2f}" if esp else "—"
        s = r.get("serie") or {}
        link = f'<a href="visor/{d.name}.html">abrir</a>' if visor.exists() else "—"
        md = sorted(d.glob("resumen_*.md"))
        arch = f'<a href="../resultados/{cfgmod.VERSION_RESULTADOS}/{d.name}/{md[-1].name}">resumen</a>' if md else ""
        filas.append(f"<tr><td>{html.escape(d.name)}</td><td>{str(r.get('fecha_corrida',''))[:16].replace('T',' ')}</td><td>{r.get('evento')}</td><td>{r.get('hipotesis_ignicion')}</td>"
                     f"<td class='n'>{r.get('horas_simuladas')}</td><td class='n burn'>{r['superficie']['ha_quemadas_final']:,.0f}</td><td class='n'>{s.get('ha_a_72h', 0):,.0f}</td><td class='n'>{iou}</td><td>{link}</td><td>{arch}</td></tr>".replace(",", "."))
    from datetime import datetime
    out = repo / "docs" / "index.html"
    out.write_text(PLANTILLA.format(version=cfgmod.VERSION_RESULTADOS, n=len(filas), fecha=datetime.now().strftime("%d/%m/%Y %H:%M"), filas="\n".join(filas)), encoding="utf-8")
    (repo / "docs" / ".nojekyll").touch()
    print("índice:", out, len(filas), "corridas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
