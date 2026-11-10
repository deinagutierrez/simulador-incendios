/* Interfaz del simulador: mapa Leaflet + API FastAPI. La simulación corre en el backend; el navegador solo
   muestra superposiciones PNG por hora derivadas del tiempo de llegada (resultados originales de 30 m intactos). */
const API = "/api";
const $ = (id) => document.getElementById(id);
const estado = { areas: [], incendios: [], runs: [], incendio: null, area: null, run: null, serie: [], idx: 0, timer: null, capas: {}, capas2: {}, trabajo: null, poll: null, graf: {}, focos: null };

const mapa = L.map("mapa", { zoomControl: true }).setView([-32.6, -65.59], 10);
const base = { "OpenStreetMap": L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap" }),
               "Esri satélite": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18, attribution: "Esri" }) };
base["OpenStreetMap"].addTo(mapa);
const controlCapas = L.control.layers(base, {}, { collapsed: true, position: "topright" }).addTo(mapa);
L.control.scale({ metric: true, imperial: false }).addTo(mapa);
let mapa2 = null;

const fmt = (x, d = 0) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : Number(x).toLocaleString("es-AR", { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtHora = (s) => s ? s.replace("T", " ").replace("+00:00", " UTC").slice(0, 22) : "—";
function mensaje(txt, error = false) { const m = $("mensajes"); const p = document.createElement("div"); p.textContent = (error ? "⚠ " : "") + txt; m.prepend(p); while (m.children.length > 8) m.lastChild.remove(); }
async function api(url, opts) { const r = await fetch(API + url, opts); if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t.slice(0, 200)}`); } return r.json(); }

// ---------------------------------------------------------------- capas de contexto
function capaImagen(nombre, m, reg, evento) {
  const q = evento ? `?evento=${encodeURIComponent(evento)}` : "";
  return api(`/capas/${estado.area.id}/${nombre}/info${q}`).then(info => {
    const capa = L.imageOverlay(`${API}/capas/${estado.area.id}/${nombre}.png${q}`, info.bounds_lonlat, { opacity: 0.85, interactive: false });
    reg[nombre] = { capa, leyenda: info.leyenda };
    return capa;
  }).catch(e => { console.warn("capa", nombre, e.message); return null; });
}
function capaVector(nombre, estilo) {
  return api(`/vectores/${estado.area.id}/${nombre}.geojson`).then(gj => L.geoJSON(gj, estilo)).catch(e => { console.warn(nombre, e.message); return null; });
}
async function cargarContexto() {
  // limpiar
  for (const k in estado.capas) { try { controlCapas.removeLayer(estado.capas[k].capa); mapa.removeLayer(estado.capas[k].capa); } catch (e) {} }
  estado.capas = {};
  const ev = estado.incendio ? estado.incendio.id : null;
  const defs = [["sombras", "Topografía (sombreado)", true], ["pendiente", "Pendiente", false], ["combustible", "Mapa de combustibles", false], ["ndvi", "NDVI pre-incendio", false],
                ["ndmi", "NDMI pre-incendio", false], ["cicatriz", "Cicatriz observada (MapBiomas)", true], ["mascara", "Fuera del dominio", true]];
  for (const [n, titulo, visible] of defs) {
    const c = await capaImagen(n, mapa, estado.capas, (["combustible", "ndvi", "ndmi", "cicatriz"].includes(n)) ? ev : null);
    if (c) { controlCapas.addOverlay(c, titulo); if (visible) c.addTo(mapa); }
  }
  const vec = [["caminos", "Rutas y caminos", { style: f => ({ color: f.properties.clase === "ruta" || f.properties.clase === "autopista" ? "#444" : "#888", weight: f.properties.clase === "ruta" ? 2 : 1 }) }],
               ["electricidad_mt", "Tendido eléctrico (MT)", { style: { color: "#7b2cbf", weight: 1, dashArray: "4 3" } }],
               ["viviendas", "Viviendas", { pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 3, color: "#000", fillColor: "#ffd166", fillOpacity: .9, weight: 1 }), style: { color: "#b5651d", weight: 1, fillOpacity: .3 } }]];
  for (const [n, titulo, estilo] of vec) { const c = await capaVector(n, estilo); if (c) { estado.capas[n] = { capa: c }; controlCapas.addOverlay(c, titulo); } }
  // focos de calor e igniciones
  if (ev) {
    try {
      const f = await api(`/incendios/${ev}/focos`);
      if (f.n) {
        const g = L.layerGroup(f.focos.map(p => L.circleMarker([p.lat, p.lon], { radius: 2, color: "#e000e0", weight: 1, fillOpacity: .6 }).bindTooltip(`${f.fuente.toUpperCase()} ${p.date}`)));
        estado.capas.focos = { capa: g }; controlCapas.addOverlay(g, `Focos de calor (${f.fuente.toUpperCase()}, ${f.n})`);
      }
    } catch (e) {}
    const ign = L.layerGroup(estado.incendio.ignicion.puntos.map(p => L.marker([p.lat, p.lon]).bindTooltip(`Ignición SNMF: ${p.nombre}`)));
    ign.addTo(mapa); estado.capas.ignicion = { capa: ign }; controlCapas.addOverlay(ign, "Puntos de ignición (SNMF)");
  }
  dibujarLeyenda();
}
function dibujarLeyenda() {
  const d = $("leyenda"); d.innerHTML = "";
  const item = (color, txt) => { const e = document.createElement("div"); e.className = "item"; e.innerHTML = `<span class="sw" style="background:${color}"></span>${txt}`; d.appendChild(e); };
  item("#d9541e", "Superficie quemada simulada"); item("#ffd500", "Frente simulado (última hora)"); item("#1a3d8f", "Perímetro contenido (modelo v2)"); item("#00c8ff", "Cicatriz observada (MapBiomas)"); item("#e000e0", "Focos de calor"); item("#7b2cbf", "Tendido eléctrico MT"); item("#444", "Rutas"); item("#ffd166", "Viviendas");
  const comb = estado.capas.combustible && estado.capas.combustible.leyenda;
  if (comb && comb.clases) { const t = document.createElement("div"); t.textContent = "Clases de combustible v1:"; t.style.marginTop = "6px"; d.appendChild(t); comb.clases.forEach(c => item(c.color, `${c.codigo} · ${c.nombre}`)); }
  item("linear-gradient(90deg,#000,#fff)", "Pendiente 0–30° (magma) · NDVI 0–0,6 (YlGn) · NDMI −0,4–0,2 (BrBG)");
}

// ---------------------------------------------------------------- selección de incendio y corridas
async function cargarCatalogos() {
  [estado.areas, estado.incendios, estado.runs] = await Promise.all([api("/areas"), api("/incendios"), api("/simulaciones")]);
  const s = $("sel-incendio"); s.innerHTML = "";
  estado.incendios.forEach(e => { const o = document.createElement("option"); o.value = e.id; o.textContent = `${e.id} — ${e.nombre}${e.datos_preparados ? "" : " (sin datos preparados)"}`; s.appendChild(o); });
  const pref = estado.incendios.find(e => e.id === "SL-2024-LASLAGUNAS") || estado.incendios[0];
  $("sel-incendio").value = pref.id; await seleccionarIncendio(pref.id);
}
async function seleccionarIncendio(id) {
  estado.incendio = estado.incendios.find(e => e.id === id); estado.area = estado.areas.find(a => a.id === estado.incendio.dominio);
  const ev = estado.incendio;
  $("info-incendio").textContent = `${ev.nombre}\nReferencia: ${ev.referencia.fuente} · ${fmt(ev.referencia.superficie_ha)} ha\nInicio ${ev.inicio.fecha_local} (confianza ${ev.inicio.confianza}) · extinción ${ev.fin.fecha_extincion_snmf}\nIgnición: ${ev.ignicion.fuente}`;
  const sh = $("sel-hip"); sh.innerHTML = ""; ev.hipotesis_hora_utc.forEach((h, i) => { const o = document.createElement("option"); o.value = i; o.textContent = `${i}: ${h.replace("T", " ").replace("Z", " UTC")}`; sh.appendChild(o); });
  const si = $("sel-ign"); si.innerHTML = '<option value="snmf">punto(s) SNMF</option>'; (ev.ignicion_alternativas || []).forEach((a, i) => { const o = document.createElement("option"); o.value = `alt${i}`; o.textContent = `alternativa ${i} (hipótesis)`; si.appendChild(o); });
  $("t-ini").value = ev.hipotesis_hora_utc[0]; $("t-fin").value = ev.fin.fin_simulacion_utc;
  const bounds = estado.area.bounds_lonlat; mapa.fitBounds(bounds, { animate: false });
  tablaEscala();
  await cargarContexto();
  const sr = $("sel-run"); sr.innerHTML = '<option value="">— elegir —</option>';
  estado.runs.filter(r => r.evento === id && r.estado === "completada").forEach(r => { const o = document.createElement("option"); o.value = r.run_id; o.textContent = `${r.run_id} · ${fmt(r.ha_quemadas)} ha${r.iou != null ? " · IoU " + r.iou.toFixed(2) : ""}`; sr.appendChild(o); });
  // versión base: despacho local del SNMF (docs/13 §10), hora de ignición de referencia; luego corridas calibradas o de validación
  const ok = r => r.evento === id && r.estado === "completada";
  const pref = estado.runs.find(r => ok(r) && /_v2_local_ens_h0$/.test(r.run_id)) || estado.runs.find(r => ok(r) && /calibrado|validacion/.test(r.run_id)) || estado.runs.find(ok);
  if (pref) { sr.value = pref.run_id; await cargarRun(pref.run_id); } else { limpiarRun(); }
}
function tablaEscala(extra = {}) {
  const a = estado.area; const t = $("tabla-escala"); const filas = [["Área", a.nombre], ["Superficie de la grilla", `${fmt(a.superficie_grilla_km2, 1)} km²`], ["Superficie efectiva del dominio", `${fmt(a.superficie_dominio_km2, 1)} km²`],
    ["Resolución", `${a.resolucion_m} × ${a.resolucion_m} m`], ["Celdas de la grilla", fmt(a.celdas_grilla)], ["Celdas dentro del dominio", fmt(a.celdas_dominio)], ["CRS", a.crs], ["Dominio reducido", "no (2.500 km² completos)"]];
  for (const k in extra) filas.push([k, extra[k]]);
  t.innerHTML = filas.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}

// ---------------------------------------------------------------- corrida seleccionada
function limpiarRun() { estado.run = null; estado.serie = []; $("slider").max = 0; $("tabla-resultados").innerHTML = ""; $("metricas").textContent = ""; quitarResultado(); }
function quitarResultado() { ["sim", "perimetro", "viento"].forEach(k => { if (estado.capas[k]) { try { controlCapas.removeLayer(estado.capas[k].capa); mapa.removeLayer(estado.capas[k].capa); } catch (e) {} delete estado.capas[k]; } }); if (mapa2 && estado.capas2.sim) { mapa2.removeLayer(estado.capas2.sim); } }
async function cargarRun(runId) {
  limpiarRun();
  const r = await api(`/simulaciones/${runId}`); const s = await api(`/simulaciones/${runId}/serie`);
  estado.run = r; estado.serie = s.filas; estado.idx = 0;
  $("slider").max = Math.max(0, estado.serie.length - 1); $("slider").value = 0;
  const b = r.bounds_lonlat;
  const sim = L.imageOverlay(`${API}/simulaciones/${runId}/estado/0.png`, b, { opacity: 0.9, interactive: false }).addTo(mapa);
  estado.capas.sim = { capa: sim }; controlCapas.addOverlay(sim, "Superficie quemada simulada");
  const per = L.geoJSON(null, { style: { color: "#ffd500", weight: 2, fill: false } }); estado.capas.perimetro = { capa: per }; controlCapas.addOverlay(per, "Perímetro simulado (vector)");
  const vie = L.layerGroup(); estado.capas.viento = { capa: vie }; controlCapas.addOverlay(vie, "Viento 10 m (WindNinja)");
  vie.on("add", () => actualizarViento()); per.on("add", () => actualizarPerimetro());
  const reg = r.registro || {}; const m = (r.metricas && r.metricas.espacial) || [];
  $("metricas").textContent = m.map(x => `Evaluación ${fmtHora(x.t_eval_utc)}: IoU ${x.iou != null ? x.iou.toFixed(3) : "—"} · Dice ${x.dice != null ? x.dice.toFixed(3) : "—"} · sim ${fmt(x.ha_sim)} ha · ref ${fmt(x.ha_ref)} ha · omisión ${x.omision != null ? x.omision.toFixed(2) : "—"} · comisión ${x.comision != null ? x.comision.toFixed(2) : "—"}`).join("\n")
    + (r.metricas && r.metricas.temporal && r.metricas.temporal.disponible ? `\nFocos capturados al fin del día: ${(r.metricas.temporal.fraccion_capturada_al_fin_del_dia * 100).toFixed(0)} % · desfase mediano ${r.metricas.temporal.desfase_mediano_h != null ? r.metricas.temporal.desfase_mediano_h.toFixed(1) + " h" : "n/d"}` : "")
    + `\nMotivo de fin: ${reg.motivo_fin_texto || "—"}\nParámetros: k_clase ${JSON.stringify((reg.config || {}).k_clase || {})} · WAF×${(reg.config || {}).factor_waf ?? 1} · ignición ${(reg.entradas || {}).ignicion || "snmf"} · hipótesis ${(reg.entradas || {}).hipotesis_ignicion ?? "—"}`
    + (reg.v2 && (reg.v2.barreras_activo || reg.v2.contencion_activo) ? `\nModelo v2: ${reg.v2.barreras_activo ? "barreras (cruces " + fmt(reg.v2.cruces_barrera) + ", bloqueos " + fmt(reg.v2.bloqueos_barrera) + ")" : "sin barreras"} · ${reg.v2.contencion_activo ? "contención (" + fmt(reg.v2.celdas_contenidas_final) + " celdas, " + fmt(reg.v2.metros_linea) + " m de línea, " + fmt(reg.v2.escapes) + " escapes; despacho " + (reg.v2.despacho_modo === "snmf" ? "local SNMF" : "fijo") + (reg.v2.contencion_inicio_utc ? ", combate desde " + reg.v2.contencion_inicio_utc.slice(0, 16) + " UTC" : "") + (reg.v2.aereo_auto_desde_utc ? ", aéreos desde " + reg.v2.aereo_auto_desde_utc.slice(0, 16) + " UTC" : "") + ")" : "sin contención"}` : "\nModelo v1 (propagación libre)");
  tablaEscala({ "Tiempo de cómputo": `${fmt(reg.segundos_cpu, 1)} s`, "Pasos": fmt(reg.pasos), "Celdas quemadas (final)": fmt(reg.celdas_quemadas), "Memoria pico": reg.memoria_pico_gb ? `${reg.memoria_pico_gb} GB` : "—" });
  graficos(); mostrarIdx(0);
  if (r.bounds_incendio_lonlat) mapa.fitBounds(r.bounds_incendio_lonlat, { animate: false });   // acercar al incendio (simulado + cicatriz)
  if ($("chk-lado").checked) activarLadoALado(true);
}
function mostrarIdx(i) {
  if (!estado.run || !estado.serie.length) return;
  estado.idx = Math.max(0, Math.min(i, estado.serie.length - 1)); $("slider").value = estado.idx;
  const f = estado.serie[estado.idx]; const t = f.t_s;
  const url = `${API}/simulaciones/${estado.run.estado.run_id}/estado/${t}.png`;
  estado.capas.sim.capa.setUrl(url); if (mapa2 && estado.capas2.sim) estado.capas2.sim.setUrl(url);
  $("hora-sim").textContent = fmtHora(f.time_utc) + ` (+${(t / 3600).toFixed(0)} h)`;
  const ref = estado.incendio.referencia.superficie_ha; const dif = f.ha_quemadas - ref;
  const iou = estado.run.metricas && estado.run.metricas.espacial ? estado.run.metricas.espacial.find(x => Math.abs(new Date(x.t_eval_utc) - new Date(f.time_utc)) < 3.6e6) : null;
  $("tabla-resultados").innerHTML = [["Hora simulada", fmtHora(f.time_utc)], ["Superficie quemada", `${fmt(f.ha_quemadas)} ha`], ["Celdas quemadas", fmt(f.celdas_quemadas)], ["Celdas del frente activo", fmt(f.celdas_activas)],
    ["Superficie de referencia", `${fmt(ref)} ha`], ["Diferencia", `${dif >= 0 ? "+" : ""}${fmt(dif)} ha (${fmt(100 * dif / ref)} %)`], ["IoU en este instante", iou ? iou.iou.toFixed(3) : "solo en instantes de evaluación"],
    ["Temperatura", `${fmt(f.temperature_2m, 1)} °C`], ["Humedad relativa", `${fmt(f.relative_humidity_2m)} %`], ["Viento 10 m", `${fmt(f.wind_speed_10m, 1)} m/s desde ${fmt(f.wind_direction_10m)}°`], ["Humedad combustible 1 h", `${fmt(f.m_1h_pct, 1)} %`],
    ["Estado", estado.run.estado.estado], ["Motivo de fin", (estado.run.registro || {}).motivo_fin_texto || "—"]]
    .concat(f.celdas_contenidas !== undefined && (estado.run.registro || {}).v2 && (estado.run.registro.v2.contencion_activo || estado.run.registro.v2.barreras_activo)
      ? [["Celdas contenidas", fmt(f.celdas_contenidas)], ["Línea construida (hora)", `${fmt(f.metros_linea_hora)} m`], ["Escapes (hora)", fmt(f.escapes_hora)], ["Bloqueos en barreras (hora)", fmt(f.bloqueos_barrera_hora)], ["Intensidad máx. del frente", f.intensidad_max_kw_m != null ? `${fmt(f.intensidad_max_kw_m)} kW/m` : "—"]] : [])
    .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
  if (estado.graf.area) { estado.graf.area.options.plugins.annotation = undefined; estado.graf.area.data.datasets[1].data = [{ x: estado.idx, y: f.ha_quemadas }]; estado.graf.area.update("none"); }
  if (mapa.hasLayer(estado.capas.viento.capa)) actualizarViento(); if (mapa.hasLayer(estado.capas.perimetro.capa)) actualizarPerimetro();
}
let tViento = null;
function actualizarViento() {
  clearTimeout(tViento); tViento = setTimeout(async () => {
    const f = estado.serie[estado.idx]; const g = estado.capas.viento.capa; g.clearLayers();
    try { const gj = await api(`/simulaciones/${estado.run.estado.run_id}/viento/${f.t_s}.geojson`);
      gj.features.forEach(p => { const [lon, lat] = p.geometry.coordinates; const v = p.properties.vel_ms; const ang = p.properties.hacia_deg;
        const ic = L.divIcon({ className: "", html: `<div style="transform:rotate(${ang}deg);width:18px;height:18px;line-height:18px;text-align:center;color:#0b3d91;font-size:${12 + Math.min(v, 12)}px;font-weight:700">↑</div>`, iconSize: [18, 18] });
        L.marker([lat, lon], { icon: ic, interactive: true }).bindTooltip(`${v} m/s → ${ang}°`).addTo(g); });
    } catch (e) { mensaje("viento: " + e.message, true); }
  }, 150);
}
let tPer = null;
function actualizarPerimetro() { clearTimeout(tPer); tPer = setTimeout(async () => { const f = estado.serie[estado.idx]; try { const gj = await api(`/simulaciones/${estado.run.estado.run_id}/perimetro/${f.t_s}.geojson`); estado.capas.perimetro.capa.clearLayers(); estado.capas.perimetro.capa.addData(gj); } catch (e) {} }, 300); }
function graficos() {
  const xs = estado.serie.map((f, i) => i); const horas = estado.serie.map(f => fmtHora(f.time_utc).slice(5, 16));
  if (estado.graf.area) estado.graf.area.destroy(); if (estado.graf.meteo) estado.graf.meteo.destroy();
  estado.graf.area = new Chart($("graf-area"), { type: "line", data: { labels: horas, datasets: [{ label: "ha quemadas (simulado)", data: estado.serie.map(f => f.ha_quemadas), borderColor: "#c8471c", pointRadius: 0, borderWidth: 2 },
    { label: "instante", data: [{ x: 0, y: estado.serie[0].ha_quemadas }], type: "scatter", backgroundColor: "#000", pointRadius: 5 }, { label: "referencia (cicatriz final)", data: estado.serie.map(() => estado.incendio.referencia.superficie_ha), borderColor: "#00a0c8", borderDash: [4, 4], pointRadius: 0, borderWidth: 1 }] },
    options: { animation: false, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }, scales: { x: { ticks: { maxTicksLimit: 6, font: { size: 9 } } }, y: { ticks: { font: { size: 9 } } } }, onClick: (e, els) => { if (els.length) mostrarIdx(els[0].index); } } });
  estado.graf.meteo = new Chart($("graf-meteo"), { type: "line", data: { labels: horas, datasets: [{ label: "T °C", data: estado.serie.map(f => f.temperature_2m), borderColor: "#d62728", pointRadius: 0, borderWidth: 1, yAxisID: "y" },
    { label: "HR %", data: estado.serie.map(f => f.relative_humidity_2m), borderColor: "#1f77b4", pointRadius: 0, borderWidth: 1, yAxisID: "y" }, { label: "viento m/s", data: estado.serie.map(f => f.wind_speed_10m), borderColor: "#2ca02c", pointRadius: 0, borderWidth: 1, yAxisID: "y2" },
    { label: "hum. 1 h %", data: estado.serie.map(f => f.m_1h_pct), borderColor: "#9467bd", pointRadius: 0, borderWidth: 1, yAxisID: "y2" }] },
    options: { animation: false, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }, scales: { x: { ticks: { maxTicksLimit: 6, font: { size: 9 } } }, y: { ticks: { font: { size: 9 } } }, y2: { position: "right", ticks: { font: { size: 9 } } } } } });
}

// ---------------------------------------------------------------- reproducción
function play() { if (!estado.serie.length) return; pausa(); const dt = Number($("sel-vel").value); estado.timer = setInterval(() => { if (estado.idx >= estado.serie.length - 1) { pausa(); return; } mostrarIdx(estado.idx + 1); }, dt); }
function pausa() { if (estado.timer) { clearInterval(estado.timer); estado.timer = null; } }
$("btn-play").onclick = play; $("btn-pausa").onclick = pausa; $("btn-reinicio").onclick = () => { pausa(); mostrarIdx(0); };
$("slider").oninput = (e) => { pausa(); mostrarIdx(Number(e.target.value)); };
$("sel-vel").onchange = () => { if (estado.timer) play(); };
$("sel-incendio").onchange = (e) => { pausa(); seleccionarIncendio(e.target.value); };
$("sel-run").onchange = (e) => { pausa(); if (e.target.value) cargarRun(e.target.value); else limpiarRun(); };
$("sel-hip").onchange = (e) => { $("t-ini").value = estado.incendio.hipotesis_hora_utc[Number(e.target.value)]; };
$("btn-panel").onclick = () => $("panel").classList.toggle("abierto");

// ---------------------------------------------------------------- lado a lado
function activarLadoALado(on) {
  const d2 = $("mapa2");
  if (on) {
    d2.classList.remove("oculto");
    if (!mapa2) { mapa2 = L.map("mapa2", { zoomControl: false }); L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(mapa2);
      const sync = (a, b) => a.on("move", () => { if (a._sync) return; b._sync = true; b.setView(a.getCenter(), a.getZoom(), { animate: false }); b._sync = false; }); sync(mapa, mapa2); sync(mapa2, mapa);
      const et = L.control({ position: "topleft" }); et.onAdd = () => { const d = L.DomUtil.create("div", "etiqueta-mapa"); d.textContent = "Simulado"; return d; }; et.addTo(mapa2);
      const et1 = L.control({ position: "topleft" }); et1.onAdd = () => { const d = L.DomUtil.create("div", "etiqueta-mapa"); d.textContent = "Observado (cicatriz) + simulado"; return d; }; et1.addTo(mapa); }
    mapa2.setView(mapa.getCenter(), mapa.getZoom());
    if (estado.run) { if (estado.capas2.sim) mapa2.removeLayer(estado.capas2.sim); estado.capas2.sim = L.imageOverlay(`${API}/simulaciones/${estado.run.estado.run_id}/estado/${estado.serie[estado.idx].t_s}.png`, estado.run.bounds_lonlat, { opacity: 0.9 }).addTo(mapa2); }
    if (estado.capas.sombras) { if (estado.capas2.sombras) mapa2.removeLayer(estado.capas2.sombras); estado.capas2.sombras = L.imageOverlay(estado.capas.sombras.capa._url, estado.capas.sombras.capa.getBounds(), { opacity: .6 }).addTo(mapa2); }
    setTimeout(() => { mapa.invalidateSize(); mapa2.invalidateSize(); }, 50);
  } else { d2.classList.add("oculto"); setTimeout(() => mapa.invalidateSize(), 50); }
}
$("chk-lado").onchange = (e) => activarLadoALado(e.target.checked);

// ---------------------------------------------------------------- trabajos (simulación nueva)
$("btn-iniciar").onclick = async () => {
  if (!estado.incendio.datos_preparados) { mensaje("Los datos del incendio no están preparados; solicitando preparación (puede tardar 20–60 min).", true); try { const t = await api("/preparacion", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ evento: estado.incendio.id }) }); vigilar(t.run_id); } catch (e) { mensaje(e.message, true); } return; }
  const tfin = new Date($("t-fin").value); const tini = new Date($("t-ini").value); const horas = (tfin - tini) / 3.6e6;
  const body = { evento: estado.incendio.id, hipotesis: Number($("sel-hip").value), ignicion: $("sel-ign").value, factor_waf: Number($("waf").value) || 1.0, horas: horas > 0 ? horas : null, figuras: false };
  if ($("k-global").value) body.k_global = Number($("k-global").value);
  const v2 = $("chk-barreras").checked || $("chk-contencion").checked;
  body.modelo = v2 ? "modelo_v2" : "modelo_v1"; body.barreras = $("chk-barreras").checked ? "on" : "off"; body.contencion = $("chk-contencion").checked ? "on" : "off";
  if ($("chk-contencion").checked) body.despacho = $("sel-despacho").value;
  try { $("btn-iniciar").disabled = true; const t = await api("/simulaciones", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); mensaje(`Simulación ${t.run_id} iniciada.`); vigilar(t.run_id); }
  catch (e) { mensaje(e.message, true); $("btn-iniciar").disabled = false; }
};
$("btn-cancelar").onclick = async () => { if (!estado.trabajo) return; try { await api(`/simulaciones/${estado.trabajo}`, { method: "DELETE" }); mensaje("cancelación solicitada"); } catch (e) { mensaje(e.message, true); } };
function vigilar(runId) {
  estado.trabajo = runId; clearInterval(estado.poll); const t0 = Date.now();
  estado.poll = setInterval(async () => {
    try {
      const r = await api(`/simulaciones/${runId}`); const e = r.estado; const p = Math.round((e.progreso || 0) * 100);
      $("barra-progreso").style.width = p + "%"; $("estado-global").textContent = e.estado;
      $("estado-proceso").textContent = `${runId}\nEstado: ${e.estado} · ${p} %\n${e.hora_simulada_utc ? "Hora simulada: " + fmtHora(e.hora_simulada_utc) + " · " + fmt(e.ha_quemadas) + " ha · frente " + fmt(e.celdas_activas) + " celdas" : ""}\nTranscurrido: ${((Date.now() - t0) / 1000).toFixed(0)} s${e.mensaje ? "\n" + e.mensaje : ""}`;
      if (["completada", "fallida", "cancelada"].includes(e.estado)) {
        clearInterval(estado.poll); estado.trabajo = null; $("btn-iniciar").disabled = false;
        if (e.estado === "completada") { mensaje(`${runId} completada.`); estado.runs = await api("/simulaciones"); await seleccionarIncendio(estado.incendio.id); $("sel-run").value = runId; await cargarRun(runId); }
        else mensaje(`${runId}: ${e.estado}. ${e.mensaje || ""} ${e.error ? e.error.slice(-300) : ""}`, true);
      }
    } catch (err) { mensaje(err.message, true); }
  }, 2000);
}
cargarCatalogos().catch(e => mensaje("No se pudo cargar el catálogo: " + e.message, true));
