// Visor del banco de pruebas: lee datos/indice.json (generado por app/web/construir.py) y las capas GeoJSON por evento.
const COLOR = { SIM: getCss('--sim'), 'SIM-L03': getCss('--l03'), MOD: getCss('--mod'), B1: getCss('--b1'), ref: getCss('--ref') };
function getCss(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
const fmt = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x)) ? '—' : Number(x).toFixed(d);
const ha = x => (x === null || x === undefined) ? '—' : Math.round(x).toLocaleString('es-AR');

const mapa = L.map('mapa', { preferCanvas: true, maxZoom: 17 });
const base = {
  'OpenStreetMap': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }),
  'Satélite (Esri)': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: '© Esri' })
};
base['Satélite (Esri)'].addTo(mapa);
const control = L.control.layers(base, {}, { collapsed: false }).addTo(mapa);
let capas = [];
let datos = null;
// estado del evento abierto: capas horarias y registros por corrida
let actual = { ev: null, horas: {}, horario: {}, color: {}, h: 0, hMax: 0, reproduciendo: null };

async function json(url) { const r = await fetch(url); if (!r.ok) throw new Error(url); return r.json(); }
function limpiar() { capas.forEach(c => { mapa.removeLayer(c); control.removeLayer(c); }); capas = []; }
function agregar(capa, nombre, visible = true) { capas.push(capa); control.addOverlay(capa, nombre); if (visible) capa.addTo(mapa); return capa; }

async function mostrar(ev) {
  document.querySelectorAll('.evento').forEach(e => e.classList.toggle('activo', e.dataset.id === ev.id));
  pausar();
  limpiar();
  actual = { ev, horas: {}, horario: {}, color: {}, h: 0, hMax: 0, reproduciendo: null };
  const dir = `datos/${ev.id}/`;
  const ref = agregar(L.geoJSON(await json(dir + ev.capas.referencia), { style: { color: COLOR.ref, weight: 2.5, fill: false } }), 'Cicatriz observada (MapBiomas)');
  if (ev.capas.B1) agregar(L.geoJSON(await json(dir + ev.capas.B1), { style: { color: COLOR.B1, weight: 2, dashArray: '6 5', fill: false } }), 'B1 elipse escalada');
  for (const r of ev.corridas) {
    const c = COLOR[r.motor] || '#888';
    if (r.archivos.isocronas) {
      const iso = await json(dir + r.archivos.isocronas);
      const max = Math.max(...iso.features.map(f => f.properties.hasta_h));
      agregar(L.geoJSON(iso, { style: f => ({ color: c, weight: 0.5, fillColor: c, fillOpacity: 0.12 + 0.45 * (1 - f.properties.hasta_h / max) }),
        onEachFeature: (f, l) => l.bindTooltip(`${r.motor}: llega antes de ${f.properties.hasta_h} h`) }), `${r.motor} · isócronas hasta T80`, false);
    }
    if (r.archivos.T80) agregar(L.geoJSON(await json(dir + r.archivos.T80), { style: { color: c, weight: 2, fillOpacity: 0.08 } }), `${r.motor} · huella en T80`, false);
    if (r.archivos.igual_superficie) agregar(L.geoJSON(await json(dir + r.archivos.igual_superficie), { style: { color: c, weight: 1.5, dashArray: '2 4', fill: false } }), `${r.motor} · a igual superficie`, false);
    if (r.archivos.horas) {
      const capa = L.geoJSON(await json(dir + r.archivos.horas), { style: { color: c, weight: 0, fillColor: c, fillOpacity: 0.45 } });
      actual.color[r.run_id] = c;
      actual.horas[r.run_id] = agregar(capa, `${r.motor} ${r.variante.replace('indices_previo', '').replace('_L03_', '')} · avance a la hora elegida`, r.motor === 'SIM' || r.variante.endsWith('P500'));
      actual.hMax = Math.max(actual.hMax, ...capa.getLayers().map(l => l.feature.properties.hora));
    }
    if (r.archivos.horario) actual.horario[r.run_id] = await json(dir + r.archivos.horario);
  }
  agregar(L.geoJSON(await json(dir + ev.capas.ignicion), { pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 5, color: '#fff', weight: 1.5, fillColor: '#e01e1e', fillOpacity: 1 }) }), 'Ignición');
  if (ev.capas.focos) agregar(L.geoJSON(await json(dir + ev.capas.focos), { pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 2.5, color: '#ffd400', weight: 0, fillOpacity: 0.9 }),
    onEachFeature: (f, l) => l.bindTooltip(`VIIRS ${f.properties.acq_date} ${String(f.properties.acq_time).padStart(4, '0')} UTC`) }), 'Focos VIIRS atribuidos', false);
  const limites = L.latLngBounds([]);
  capas.forEach(c => { const b = c.getBounds && c.getBounds(); if (b && b.isValid()) limites.extend(b); });
  mapa.invalidateSize();
  mapa.fitBounds(limites.isValid() ? limites : ref.getBounds(), { padding: [20, 20], maxZoom: 15 });
  detalle(ev);
  const h80 = Math.max(1, Math.round(ev.T80_h || 1));
  irAHora(Math.min(h80, actual.hMax || h80));
}

// ---------------------------------------------------------------- barra de tiempo
function irAHora(h) {
  actual.h = h;
  for (const [run, capa] of Object.entries(actual.horas)) {
    const c = actual.color[run] || '#888';
    capa.eachLayer(l => l.setStyle(l.feature.properties.hora <= h ? { fillOpacity: 0.45, fillColor: c } : { fillOpacity: 0 }));
  }
  const s = document.getElementById('hora'); if (s) { s.max = Math.max(1, actual.hMax); s.value = h; }
  tablaHora();
  grafico();
}
function pausar() { if (actual.reproduciendo) { clearInterval(actual.reproduciendo); actual.reproduciendo = null; } const b = document.getElementById('play'); if (b) b.textContent = '▶'; }
function alternar() {
  if (actual.reproduciendo) return pausar();
  if (actual.h >= actual.hMax) irAHora(0);
  document.getElementById('play').textContent = '❚❚';
  actual.reproduciendo = setInterval(() => { if (actual.h >= actual.hMax) return pausar(); irAHora(actual.h + 1); }, 350);
}
function filaEn(serie, h) {
  let mejor = null;
  for (const f of serie) { if (f.h <= h + 1e-6) mejor = f; else break; }
  return mejor || serie[0];
}
function focosEn(h) {
  const fa = actual.ev.focos_acumulados || []; let p = 0;
  for (const f of fa) { if (f.h <= h) p = f.pct; else break; }
  return fa.length ? p : null;
}
function tablaHora() {
  const ev = actual.ev; const h = actual.h;
  const cuerpo = ev.corridas.map(r => {
    const s = actual.horario[r.run_id]; if (!s || !s.length) return '';
    const f = filaEn(s, h);
    return `<tr><td class="${r.motor.toLowerCase()}">${r.motor} <span class="chip">${r.variante.replace('indices_previo', '').replace('_L03_', '')}</span></td><td>${ha(f.ha)}</td><td>${fmt(f.pct_obs, 0)} %</td><td>${ha(f.ha_combustion)}</td>
      <td>${fmt(f.temp_c, 1)}</td><td>${fmt(f.hr_pct, 0)}</td><td>${fmt(f.viento_kmh, 0)} ${f.viento_dir || ''}</td><td>${fmt(f.h1_pct, 1)}</td>
      <td>${fmt(f.h10_pct, 1)}</td><td>${fmt(f.vel_cabeza_km_h, 2)}</td><td>${ha(f.intensidad_max_kw_m)}</td><td>${fmt(f.llama_max_m, 1)}</td>
      <td>${f.viviendas_amenazadas ?? '—'}</td><td>${f.dotaciones ?? '—'}</td><td>${f.linea_km ?? '—'}</td></tr>`;
  }).join('');
  const t0 = new Date(ev.t0_utc);
  const tl = new Date(t0.getTime() + h * 3600e3).toLocaleString('es-AR', { timeZone: 'America/Argentina/San_Luis', dateStyle: 'short', timeStyle: 'short' });
  const fo = focosEn(h);
  document.getElementById('lectura').innerHTML = `Hora <b>${h}</b> desde t0 · ${tl} (hora local) · T80 = ${fmt(ev.T80_h, 1)} h · focos VIIRS acumulados: <b>${fo === null ? '—' : fmt(fo, 0) + ' %'}</b>`;
  document.getElementById('tabla-hora').innerHTML = `<table><thead><tr><th>Modelo</th><th>ha quemadas</th><th>% de la cicatriz</th><th>ha en combustión</th>
    <th>T (°C)</th><th>HR (%)</th><th>Viento (km/h)</th><th>Hum. 1 h (%)</th><th>Hum. 10 h (%)</th><th>Cabeza (km/h)</th><th>I máx (kW/m)</th><th>Llama máx (m)</th><th>Viviendas amenazadas</th><th>Dotaciones</th><th>Línea (km)</th></tr></thead>
    <tbody>${cuerpo}</tbody></table>`;
}
function grafico() {
  const ev = actual.ev; const W = 640, H = 190, m = { l: 46, r: 12, t: 10, b: 26 };
  const hMax = Math.max(1, actual.hMax);
  const series = ev.corridas.filter(r => actual.horario[r.run_id]).map(r => ({ motor: r.motor, s: actual.horario[r.run_id] }));
  const yMax = Math.max(ev.ha_obs * 1.2, ...series.flatMap(x => x.s.filter(f => f.h <= hMax).map(f => f.ha)));
  const X = h => m.l + (W - m.l - m.r) * h / hMax, Y = v => H - m.b - (H - m.t - m.b) * v / yMax;
  const linea = (pts, c, extra = '') => `<polyline fill="none" stroke="${c}" stroke-width="2" ${extra} points="${pts.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}"/>`;
  let svg = series.map(x => linea(x.s.filter(f => f.h <= hMax).map(f => [f.h, f.ha]), COLOR[x.motor] || '#888', x.motor === 'SIM-L03' ? 'stroke-opacity="0.75"' : '')).join('');
  const fa = ev.focos_acumulados || [];
  if (fa.length) svg += linea(fa.filter(f => f.h <= hMax).map(f => [f.h, ev.ha_obs * f.pct / 100]), '#d4a600', 'stroke-dasharray="4 3"');
  svg += `<line x1="${X(0)}" x2="${X(hMax)}" y1="${Y(ev.ha_obs)}" y2="${Y(ev.ha_obs)}" stroke="${COLOR.ref}" stroke-width="1" stroke-dasharray="2 3"/>`;
  if (ev.T80_h <= hMax) svg += `<line x1="${X(ev.T80_h)}" x2="${X(ev.T80_h)}" y1="${m.t}" y2="${H - m.b}" stroke="${COLOR.ref}" stroke-width="1"/><text x="${X(ev.T80_h) + 3}" y="${m.t + 10}" font-size="10" fill="currentColor">T80</text>`;
  svg += `<line x1="${X(actual.h)}" x2="${X(actual.h)}" y1="${m.t}" y2="${H - m.b}" stroke="#e01e1e" stroke-width="1.5"/>`;
  svg += `<text x="${m.l}" y="${H - 6}" font-size="10" fill="currentColor">0 h</text><text x="${W - m.r}" y="${H - 6}" font-size="10" text-anchor="end" fill="currentColor">${hMax} h</text>`;
  svg += `<text x="${m.l - 4}" y="${Y(ev.ha_obs) + 3}" font-size="10" text-anchor="end" fill="currentColor">cicatriz</text><text x="${m.l - 4}" y="${m.t + 8}" font-size="10" text-anchor="end" fill="currentColor">${ha(yMax)} ha</text>`;
  document.getElementById('grafico').innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Superficie quemada por hora">${svg}</svg>
    <div class="nota"><span class="sim">— SIM</span> · <span class="sim-l03">— SIM con L03 (una línea por valor de P)</span> · <span class="mod">— MOD</span> · <span style="color:#d4a600">- - focos VIIRS acumulados (escalados a la cicatriz)</span> · línea punteada = superficie de la cicatriz · rojo = hora elegida</div>`;
}

function detalle(ev) {
  const filas = ev.corridas.map(r => {
    const m = r.metricas;
    return `<tr><td class="${r.motor.toLowerCase()}">${r.motor} <span class="chip">${r.variante}</span></td>
      <td>${fmt(m.iou_eq, 3)}</td><td>${fmt(m.skill_F, 2)}</td><td>${ha(m.ha_sim_T80)}</td><td>${fmt(m.L_T80, 2)}</td>
      <td>${fmt(m.dt_h_T80, 1)}</td><td>${m.truncado_T80 ? 'sí' : 'no'}</td><td>${fmt(m.iou_T80, 3)}</td><td>${fmt(m.focos_frac_12h, 2)}</td><td>${fmt(m.precision_focos, 2)}</td></tr>`;
  }).join('');
  const b1 = ev.B1 ? `<tr><td class="b1">B1 (elipse)</td><td>${fmt(ev.B1.iou_eq, 3)}</td><td>0</td><td colspan="7" style="text-align:left">viento desde ${fmt(ev.B1.viento_desde_deg, 0)}°, ${fmt(ev.B1.u10_ms, 1)} m/s · L/B ${fmt(ev.B1.LB, 2)} · ${ev.B1.fuente_viento}</td></tr>` : '';
  document.getElementById('detalle').innerHTML = `
    <h2 style="margin:0 0 4px;font-size:15px">${ev.id} ${ev.nombre ? '· ' + ev.nombre : ''} <span class="chip">${ev.rol}</span>${ev.degenerado ? '<span class="chip">instante degenerado: solo forma</span>' : ''}</h2>
    <div class="nota">Cicatriz ${ha(ev.ha_obs)} ha · t0 ${ev.t0_utc.replace('T', ' ').replace('Z', ' UTC')} · T80 ${ev.T80_utc.replace('+00:00', ' UTC')} · ${ev.n_focos} focos VIIRS</div>
    <div class="tiempo"><button id="play" type="button" aria-label="Reproducir">▶</button>
      <input id="hora" type="range" min="0" max="${Math.max(1, actual.hMax)}" step="1" value="0" aria-label="Hora desde t0"><span id="lectura" class="nota"></span></div>
    <div id="grafico"></div>
    <h3>Registro de la hora elegida</h3><div id="tabla-hora"></div>
    <h3>Métricas del protocolo (en T80)</h3>
    <table><thead><tr><th>Modelo</th><th>IoU igual sup.</th><th>Skill_F</th><th>ha en T80</th><th>L (T80)</th><th>Δt (h)</th><th>Truncado</th><th>IoU T80</th><th>Focos ±12 h</th><th>Precisión focos</th></tr></thead>
    <tbody>${filas}${b1}</tbody></table>
    <div class="nota">IoU a igual superficie: forma con independencia del tamaño. Skill_F: mejora sobre B1 (0 = igual, &lt; 0 = peor). L = ln(sup. simulada / observada) en T80 (0 = exacta; ±0,69 = factor 2). Δt: horas entre que el modelo alcanza la superficie observada y T80 (negativo = el modelo llega antes). "% de la cicatriz" = superficie simulada / superficie observada final.</div>`;
  document.getElementById('hora').addEventListener('input', e => { pausar(); irAHora(Number(e.target.value)); });
  document.getElementById('play').addEventListener('click', alternar);
}

function fase1(f) {
  if (!f) { document.getElementById('fase1').innerHTML = '<div class="nota">Sin resultados de la Fase 1 todavía.</div>'; return; }
  const fila = (k, m) => `<tr><td class="${k.toLowerCase()}">${k}</td>
    <td>${fmt(m.skill_F_mediana_IC90[0], 2)}<br><span class="nota">[${fmt(m.skill_F_mediana_IC90[1], 2)}; ${fmt(m.skill_F_mediana_IC90[2], 2)}]</span></td>
    <td>${fmt(m.abs_L_mediana_IC90[0], 2)}</td><td>${fmt(m.abs_dt_h_mediana_IC90[0], 1)}</td>
    <td class="${m.eje_forma_cumple ? 'ok' : 'mal'}">${m.eje_forma_cumple ? 'sí' : 'no'}</td><td class="${m.eje_extension_cumple ? 'ok' : 'mal'}">${m.eje_extension_cumple ? 'sí' : 'no'}</td></tr>`;
  const ms = f.motores || {};
  document.getElementById('fase1').innerHTML = `<table><thead><tr><th></th><th>Skill_F (IC 90 %)</th><th>|L|</th><th>|Δt| h</th><th>Forma</th><th>Ext.</th></tr></thead>
    <tbody>${Object.entries(ms).map(([k, m]) => fila(k, m)).join('')}</tbody></table>
    <div class="nota">${Object.entries(ms).map(([k, m]) => `${k}: n forma ${m.n_forma}, n extensión ${m.n_extension}${m.fallos.length ? `, ${m.fallos.length} sin corrida` : ''}${(m.no_alcanza_A_obs || []).length ? `; no alcanza la superficie observada en ${m.no_alcanza_A_obs.length} evento(s) (Skill_F con huella final: ${fmt(m.skill_F_sensibilidad_huella_final_IC90[0], 2)} [${fmt(m.skill_F_sensibilidad_huella_final_IC90[1], 2)}; ${fmt(m.skill_F_sensibilidad_huella_final_IC90[2], 2)}])` : ''}`).join(' · ')}.
    Con n &lt; 8 los IC no son concluyentes (protocolo §7). Criterios: §9 del protocolo ${f.protocolo}. Ningún motor es aceptable si falla un eje.</div>`;
}

(async () => {
  datos = await json('datos/indice.json');
  document.getElementById('meta').textContent = `Protocolo ${datos.protocolo} · generado ${datos.generado.replace('T', ' ')}`;
  fase1(datos.fase1);
  const cont = document.getElementById('eventos');
  for (const rol of ['prueba_fase1', 'desarrollo']) {
    const evs = datos.eventos.filter(e => e.rol === rol);
    if (!evs.length) continue;
    cont.insertAdjacentHTML('beforeend', `<div class="nota">${rol === 'prueba_fase1' ? 'Prueba (Fase 1)' : 'Desarrollo (ya vistos)'}</div>`);
    for (const e of evs) {
      const motores = e.corridas.map(r => r.motor).join(' · ') || 'sin corridas';
      cont.insertAdjacentHTML('beforeend', `<div class="evento" data-id="${e.id}"><div class="t">${e.id}</div><div class="s">${ha(e.ha_obs)} ha · ${motores}${e.degenerado ? ' · solo forma' : ''}</div></div>`);
    }
  }
  cont.querySelectorAll('.evento').forEach(el => el.addEventListener('click', () => mostrar(datos.eventos.find(e => e.id === el.dataset.id))));
  const primero = datos.eventos.find(e => e.corridas.length) || datos.eventos[0];
  if (primero) mostrar(primero);
})();
