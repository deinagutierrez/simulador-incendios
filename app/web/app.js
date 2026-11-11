/* Pantalla del simulador (fase F3). Habla con el servidor local por los pedidos de docs/etapa3/contrato_servidor_motor.md §4.
   Sin bibliotecas salvo Leaflet (app/web/vendor/leaflet). */
"use strict";

const $ = id => document.getElementById(id);
const FINALES = ["terminada", "detenida", "error", "interrumpida"];
const MOTORES = {
  "v4.0": {nombre: "v4.0", largo: "v4.0 (línea principal)", color: "#eb6834"},
  "v3.1-librev2": {nombre: "v3.1 librev2", largo: "v3.1 librev2 (control)", color: "#2a78d6"},
  "v3.1-libre": {nombre: "v3.1 libre", largo: "v3.1 libre (control)", color: "#2a78d6"},
  "ambos": {nombre: "Ambos", largo: "Ambos: v4.0 y v3.1 librev2"},
  "simulado": {nombre: "Simulado", largo: "Motor simulado (de prueba, no es un incendio)", color: "#6250d6"},
};
const ESTADOS = {creada: "creada", iniciando: "cargando datos…", corriendo: "simulando", pausando: "pausando…", pausada: "en pausa",
                 deteniendo: "deteniendo…", terminada: "terminada", detenida: "detenida", error: "con error", interrumpida: "interrumpida"};
const HUSO_H = -3;                                   // hora argentina, sin horario de verano
const S = {estado: null, mapa: null, capas: {}, enMapa: {}, marcador: null, usados: [], corridas: [], pedido: null,
           modo: "configurar", horaVista: 0, enVivo: true, reproduccion: null};

// ---------------------------------------------------------------- utilidades
async function pedir(ruta, cuerpo) {
  const r = await fetch(ruta, cuerpo === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(cuerpo)});
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = datos.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => `${(x.loc || []).slice(-1)[0]}: ${x.msg}`).join("; ") : `error ${r.status}`);
  }
  return datos;
}
const num = (v, dec = 0) => v == null ? "—" : Number(v).toLocaleString("es-AR", {minimumFractionDigits: dec, maximumFractionDigits: dec});
const dos = n => String(n).padStart(2, "0");
function aLocal(utc) {                               // instante → {fecha "AAAA-MM-DD", hora "HH:MM", texto}
  const d = new Date(new Date(utc).getTime() + HUSO_H * 3600e3);
  const fecha = `${d.getUTCFullYear()}-${dos(d.getUTCMonth() + 1)}-${dos(d.getUTCDate())}`, hora = `${dos(d.getUTCHours())}:${dos(d.getUTCMinutes())}`;
  return {fecha, hora, texto: `${dos(d.getUTCDate())}/${dos(d.getUTCMonth() + 1)}/${d.getUTCFullYear()} ${hora}`};
}
function aUTC(fecha, hora) {                         // hora argentina → "AAAA-MM-DDTHH:MM:SSZ"
  const [a, m, d] = fecha.split("-").map(Number), [h, mi] = hora.split(":").map(Number);
  return new Date(Date.UTC(a, m - 1, d, h - HUSO_H, mi || 0)).toISOString().replace(".000Z", "Z");
}
const normalizarUTC = t => String(t).replace(" ", "T").replace("+00:00", "Z");
const ev = () => S.estado.eventos_base.find(e => e.id === $("evento").value);

// ---------------------------------------------------------------- arranque
async function arrancar() {
  S.estado = await pedir("/api/estado");
  $("version").textContent = `Programa ${S.estado.programa.version} · motores congelados ${String(S.estado.congelado_sha256).slice(0, 8)}…`;
  $("motor").innerHTML = S.estado.motores.map(m => `<option value="${m.id}">${MOTORES[m.id]?.largo || m.id}</option>`).join("");
  $("evento").innerHTML = S.estado.eventos_base.map(e => `<option value="${e.id}">${e.nombre || e.id}</option>`).join("");
  const lagunas = S.estado.eventos_base.find(e => e.id === "SL-2024-LASLAGUNAS");
  if (lagunas) $("evento").value = lagunas.id;

  const [[sur, oeste], [norte, este]] = S.estado.dominio.limites;
  S.mapa = L.map("mapa", {zoomSnap: 0.25, minZoom: 9, maxZoom: 16, attributionControl: true,
                         maxBounds: [[sur - 0.4, oeste - 0.5], [norte + 0.4, este + 0.5]]});
  S.mapa.attributionControl.setPrefix("");
  S.mapa.attributionControl.addAttribution("Relieve: Copernicus DEM · Cobertura: MapBiomas · Caminos: © OpenStreetMap, IGN · Red MT: EDESAL · Cuarteles: Min. de Seguridad de San Luis");
  for (const [nombre, z] of [["fondo", 200], ["tematica", 250], ["huella", 380], ["vectores", 420]]) {
    S.mapa.createPane(nombre).style.zIndex = z;
  }
  S.mapa.fitBounds([[sur, oeste], [norte, este]]);
  S.mapa.on("click", e => { if (S.modo === "configurar") ponerPunto(e.latlng.lat, e.latlng.lng); });

  $("evento").onchange = () => { proponerEvento(); cargarCapas(); };
  for (const id of ["lat", "lon"]) $(id).onchange = () => ponerPunto(Number($("lat").value), Number($("lon").value), true);
  $("iniciar").onclick = iniciar;
  $("pausar").onclick = () => ordenar("pausar");
  $("reanudar").onclick = () => ordenar("reanudar");
  $("detener").onclick = () => ordenar("detener");
  $("nueva").onclick = nuevaSimulacion;
  $("deslizador").oninput = () => verHora(Number($("deslizador").value), true);
  $("reproducir").onclick = reproducir;
  $("ver-tabla").onclick = () => { $("tabla").hidden = !$("tabla").hidden; $("ver-tabla").textContent = $("tabla").hidden ? "Ver como tabla" : "Ocultar la tabla"; };
  $("en-linea").onchange = mapaEnLinea;
  $("anteriores").onchange = () => { if ($("anteriores").value) abrirAnterior($("anteriores").value); };

  proponerEvento();
  await cargarCapas();
  await listarAnteriores();
}

function proponerEvento() {
  const e = ev();
  if (!e) return;
  const inicio = e.inicios_de_la_ficha_utc[0] || e.meteo_desde_utc;
  if (inicio) { const l = aLocal(normalizarUTC(inicio)); $("fecha").value = l.fecha; $("hora").value = l.hora; }
  if (e.meteo_desde_utc) {
    $("fecha").min = aLocal(e.meteo_desde_utc).fecha; $("fecha").max = aLocal(e.meteo_hasta_utc).fecha;
    $("nota-evento").textContent = `Hay datos del tiempo del ${aLocal(e.meteo_desde_utc).texto} al ${aLocal(e.meteo_hasta_utc).texto} (hora argentina).`;
  }
  const p = e.ignicion_de_la_ficha[0];
  if (p) ponerPunto(p.lat, p.lon, true); else quitarPunto();
}

// ---------------------------------------------------------------- punto de ignición
function ponerPunto(lat, lon, sinAviso) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  const [[sur, oeste], [norte, este]] = S.estado.dominio.limites;
  if (lat < sur || lat > norte || lon < oeste || lon > este) {
    if (!sinAviso) $("error").textContent = "Ese punto cae fuera del dominio.";
    return;
  }
  $("error").textContent = "";
  $("lat").value = lat.toFixed(5); $("lon").value = lon.toFixed(5);
  if (!S.marcador) {
    S.marcador = L.marker([lat, lon], {draggable: true, zIndexOffset: 1000, icon: L.divIcon({className: "", html: '<div class="punto-ignicion"></div>', iconSize: [18, 18], iconAnchor: [9, 9]})}).addTo(S.mapa);
    S.marcador.bindTooltip("Punto de ignición");
    S.marcador.on("dragend", () => { const p = S.marcador.getLatLng(); ponerPunto(p.lat, p.lng); });
  } else S.marcador.setLatLng([lat, lon]);
}
function quitarPunto() { if (S.marcador) { S.marcador.remove(); S.marcador = null; } $("lat").value = $("lon").value = ""; }

// ---------------------------------------------------------------- capas de fondo
const ESTILO_VECTOR = {
  dominio: () => ({color: "#3a3833", weight: 1.5, dashArray: "6 5", fill: false}),
  caminos: f => { const c = f.properties.clase; const fuerte = c === "ruta" || c === "autopista"; return {color: fuerte ? "#4a4741" : "#7d7a72", weight: fuerte ? 2 : 1, opacity: fuerte ? 0.95 : 0.75}; },
  red_mt: () => ({color: "#7a3ea8", weight: 1, opacity: 0.8, dashArray: "5 4"}),
};
const ENCENDIDAS = ["relieve", "dominio", "caminos"];

async function cargarCapas() {
  const {capas} = await pedir(`/api/capas?evento=${encodeURIComponent($("evento").value)}`);
  const antes = new Set(Object.keys(S.enMapa));
  for (const id of antes) if (S.capas[id]?.por_evento) apagarCapa(id);            // las del evento anterior se sacan
  S.capas = Object.fromEntries(capas.map(c => [c.id, c]));
  const grupos = {};
  for (const c of capas) (grupos[c.grupo] ||= []).push(c);
  $("capas").innerHTML = Object.entries(grupos).map(([g, lista]) =>
    `<div class="grupo-capas"><span>${g}</span>${lista.map(c => `<label class="casilla"><input type="checkbox" data-capa="${c.id}"> ${c.titulo}</label>`).join("")}</div>`).join("");
  for (const casilla of $("capas").querySelectorAll("input")) {
    const id = casilla.dataset.capa;
    casilla.checked = (antes.size ? antes.has(id) : ENCENDIDAS.includes(id));
    casilla.onchange = () => casilla.checked ? prenderCapa(id) : apagarCapa(id);
    if (casilla.checked) prenderCapa(id);
  }
}

async function prenderCapa(id) {
  const c = S.capas[id];
  if (!c || S.enMapa[id]) return;
  if (c.tipo === "imagen") {
    S.enMapa[id] = L.imageOverlay(c.url, c.limites, {pane: id === "relieve" ? "fondo" : "tematica", opacity: id === "relieve" ? 1 : 0.8}).addTo(S.mapa);
  } else {
    S.enMapa[id] = L.layerGroup().addTo(S.mapa);                      // reserva el lugar mientras baja
    const datos = await (await fetch(c.url)).json();
    if (!S.enMapa[id]) return;
    const capa = L.geoJSON(datos, {
      pane: "vectores", style: ESTILO_VECTOR[id],
      pointToLayer: (f, ll) => id === "cuarteles"
        ? L.marker(ll, {icon: L.divIcon({className: "", html: '<div class="cuartel"></div>', iconSize: [12, 12], iconAnchor: [6, 6]})})
        : L.circleMarker(ll, {pane: "vectores", radius: 3.5, color: "#fff", weight: 1, fillColor: "#2b2a27", fillOpacity: 1}),
      onEachFeature: (f, capaF) => {
        const p = f.properties || {};
        const texto = id === "cuarteles" ? `Cuartel: ${p.nombre || ""}${p.localidad ? " (" + p.localidad + ")" : ""}`
          : id === "caminos" ? [p.nombre, p.clase, p.superficie !== "desconocido" ? p.superficie : null].filter(Boolean).join(" · ")
          : id === "red_mt" ? `Media tensión${p.tension_kv ? " " + p.tension_kv + " kV" : ""}` : id === "viviendas" ? (p.nombre || "Vivienda") : p.nombre;
        if (texto) capaF.bindTooltip(texto, {sticky: true});
      },
    });
    S.enMapa[id].addLayer(capa);
  }
  dibujarLeyenda();
}
function apagarCapa(id) { if (S.enMapa[id]) { S.enMapa[id].remove(); delete S.enMapa[id]; } dibujarLeyenda(); }

function mapaEnLinea() {
  if ($("en-linea").checked) {
    S.enLinea = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {pane: "fondo", maxZoom: 19, opacity: 0.9, attribution: "Mapa en línea: © colaboradores de OpenStreetMap"}).addTo(S.mapa);
    if (S.enMapa.relieve) S.enMapa.relieve.setOpacity(0.35);
  } else if (S.enLinea) { S.enLinea.remove(); S.enLinea = null; if (S.enMapa.relieve) S.enMapa.relieve.setOpacity(1); }
}

function dibujarLeyenda() {
  const bloques = [];
  if (S.corridas.some(c => c.capa)) {
    const conRampa = S.corridas.filter(c => !c.plano), planas = S.corridas.filter(c => c.plano);
    let h = "<h3>Área quemada simulada</h3>";
    if (conRampa.length) h += `<div class="rampa" style="background:linear-gradient(90deg,#ffeda0,#feb24c,#f03b20,#800026)"></div><div class="extremos"><span>ardió primero</span><span>ardió último</span></div>${S.corridas.length > 1 ? `<div class="item">${MOTORES[conRampa[0].motor].nombre}</div>` : ""}`;
    for (const c of planas) h += `<div class="item"><i style="background:${c.color};opacity:.55"></i>${MOTORES[c.motor].nombre}</div>`;
    bloques.push(h);
  }
  for (const id of Object.keys(S.enMapa)) {
    const c = S.capas[id], l = c?.leyenda;
    if (!l) continue;
    if (l.tipo === "categorica") bloques.push(`<h3>${c.titulo}</h3>` + l.items.map(i => `<div class="item"><i style="background:${i.color}"></i>${i.nombre}</div>`).join(""));
    else {
      const p = l.paradas, a = p[0].valor, b = p[p.length - 1].valor;
      const grad = p.map(x => `${x.color} ${((x.valor - a) / (b - a) * 100).toFixed(0)}%`).join(",");
      bloques.push(`<h3>${c.titulo}</h3><div class="rampa" style="background:linear-gradient(90deg,${grad})"></div><div class="extremos"><span>${num(a, 1)}</span><span>${num(b, 1)} ${l.unidad || ""}</span></div>`);
    }
  }
  $("leyenda").hidden = !bloques.length;
  $("leyenda").innerHTML = bloques.map(b => `<div class="bloque">${b}</div>`).join("");
}

// ---------------------------------------------------------------- lanzar y seguir
async function iniciar() {
  $("error").textContent = "";
  const horas = Number($("horas").value);
  if (!$("lat").value || !$("lon").value) return void ($("error").textContent = "Marcá el punto de ignición con un clic en el mapa.");
  if (!$("fecha").value || !$("hora").value) return void ($("error").textContent = "Falta el día o la hora de inicio.");
  if (!(horas >= 1 && horas <= 240)) return void ($("error").textContent = "Las horas a simular van de 1 a 240.");
  const pedido = {motor: $("motor").value, evento: $("evento").value, horas, iniciar: true,
                  ignicion: [{lat: Number($("lat").value), lon: Number($("lon").value)}], t_inicio_utc: aUTC($("fecha").value, $("hora").value)};
  $("iniciar").disabled = true;
  try {
    const r = await pedir("/api/corridas", pedido);
    S.pedido = pedido;
    seguir(r.corridas, pedido);
  } catch (e) { $("error").textContent = e.message; }
  $("iniciar").disabled = false;
}

function seguir(resumenes, pedido) {
  limpiarCorridas();
  S.modo = "corriendo"; S.enVivo = true; S.horaVista = 0;
  S.corridas = resumenes.map((r, i) => ({id: r.id, motor: r.motor, color: MOTORES[r.motor]?.color || "#555", estado: r.estado, horas: [], plano: resumenes.length > 1 && i > 0,
                                         pedido: r.pedido || pedido, t0: null, limites: null, capa: null, cargando: false, pendiente: null, detalle: null, error: null}));
  if (S.marcador) S.marcador.dragging.disable();
  $("sec-config").hidden = true; $("sec-control").hidden = false; $("sec-grafico").hidden = false; $("tiempo").hidden = false;
  const p = S.corridas[0].pedido, ign = (p.ignicion || [])[0];
  $("resumen-config").innerHTML = `<b>${MOTORES[pedido.motor || p.motor]?.largo || p.motor}</b><br>` +
    `${(S.estado.eventos_base.find(e => e.id === p.evento) || {}).nombre || p.evento || "sin evento"}<br>` +
    (ign ? `Ignición en ${num(ign.lat, 4)}, ${num(ign.lon, 4)}<br>` : "") +
    (p.t_inicio_utc ? `Inicio: ${aLocal(p.t_inicio_utc).texto} (hora argentina)<br>` : "") + `Duración pedida: ${p.horas} h`;
  for (const c of S.corridas) escuchar(c);
  pintarTodo();
}

function escuchar(c) {
  c.canal = new EventSource(`/api/corridas/${c.id}/eventos`);
  c.canal.onmessage = m => {
    const e = JSON.parse(m.data);
    if (e.aviso === "estado") { c.estado = e.estado; if (e.motivo) c.error = e.motivo; if (FINALES.includes(e.estado)) alTerminar(c); }
    else if (e.aviso === "listo") { c.t0 = normalizarUTC(e.t0_utc); pedir(`/api/corridas/${c.id}`).then(d => { c.limites = d.huella?.limites; actualizarHuella(c); }); }
    else if (e.aviso === "hora") {
      c.horas[e.h] = {h: e.h, ha: e.ha, activas: e.activas, s: e.s_computo, meteo: e.meteo, exposicion: e.exposicion};
      if (S.enVivo) S.horaVista = horaMaxima();
      actualizarHuella(c);
    } else if (e.aviso === "error" && e.fatal) c.error = e.mensaje;
    pintarTodo();
  };
  c.canal.addEventListener("cierre", () => c.canal.close());
  c.canal.onerror = () => { if (FINALES.includes(c.estado)) c.canal.close(); };
}

async function alTerminar(c) {
  try { c.detalle = await pedir(`/api/corridas/${c.id}`); } catch (e) { /* queda sin detalle */ }
  const usada = c.detalle?.resultados?.ignicion?.usada || [];
  for (const u of usada) if (u.desplazada_m) {
    S.usados.push(L.marker([u.lat, u.lon], {icon: L.divIcon({className: "", html: '<div class="punto-usado"></div>', iconSize: [12, 12], iconAnchor: [6, 6]})})
      .bindTooltip(`${MOTORES[c.motor].nombre}: el fuego empezó acá, a ${num(u.desplazada_m)} m del clic (la celda marcada no quema)`).addTo(S.mapa));
  }
  if (S.corridas.every(x => FINALES.includes(x.estado))) {
    S.modo = "terminada";
    if (S.corridas.length === 2) await comparar();
    listarAnteriores();
  }
  pintarTodo();
}

async function comparar() {
  const [a, b] = S.corridas, h = Math.min(horaMaxima(a), horaMaxima(b));
  if (!(h > 0)) return;
  const horas = h >= 24 ? [24, h] : [h];
  try { S.comparacion = await Promise.all([...new Set(horas)].map(x => pedir(`/api/comparacion?a=${a.id}&b=${b.id}&hora=${x}`))); } catch (e) { S.comparacion = null; }
}

async function ordenar(orden) {
  $("error-control").textContent = "";
  const sirve = {pausar: ["iniciando", "corriendo"], reanudar: ["pausando", "pausada"], detener: ["iniciando", "corriendo", "pausando", "pausada"]}[orden];
  for (const c of S.corridas.filter(x => sirve.includes(x.estado))) {
    try { const r = await pedir(`/api/corridas/${c.id}/${orden}`, {}); c.estado = r.estado; } catch (e) { $("error-control").textContent = e.message; }
  }
  pintarTodo();
}

function limpiarCorridas() {
  detenerReproduccion();
  for (const c of S.corridas) { if (c.canal) c.canal.close(); if (c.capa) c.capa.remove(); }
  for (const m of S.usados) m.remove();
  S.usados = []; S.corridas = []; S.comparacion = null;
}
function nuevaSimulacion() {
  limpiarCorridas();
  S.modo = "configurar";
  if (S.marcador) S.marcador.dragging.enable();
  $("sec-config").hidden = false; $("sec-control").hidden = true; $("sec-grafico").hidden = true; $("tiempo").hidden = true;
  $("anteriores").value = "";
  dibujarLeyenda();
}

// ---------------------------------------------------------------- huella y línea de tiempo
const horaMaxima = c => c ? c.horas.length - 1 : Math.max(0, ...S.corridas.map(x => x.horas.length - 1));
const horasPedidas = () => Math.max(1, ...S.corridas.map(c => Number(c.pedido?.horas) || 0), horaMaxima());

function actualizarHuella(c) {
  if (!c.limites || !c.horas.length) return;
  const h = Math.min(S.horaVista, horaMaxima(c));
  const url = `/api/corridas/${c.id}/quemado.png?hora=${h}` + (c.plano ? `&color=${c.color.slice(1)}` : "") + `&v=${c.horas.length}`;
  if (c.url === url) return;
  if (c.cargando) { c.pendiente = url; return; }
  c.url = url;
  if (!c.capa) {
    c.capa = L.imageOverlay(url, c.limites, {pane: "huella", opacity: 0.85, className: "huella"}).addTo(S.mapa);
    c.capa.on("load error", () => { c.cargando = false; if (c.pendiente) { const p = c.pendiente; c.pendiente = null; c.url = null; actualizarHuellaCon(c, p); } });
    dibujarLeyenda();
  }
  actualizarHuellaCon(c, url);
}
function actualizarHuellaCon(c, url) { c.cargando = true; c.url = url; c.capa.setUrl(url); }

function verHora(h, delUsuario) {
  S.horaVista = h;
  if (delUsuario) { detenerReproduccion(); S.enVivo = h >= horaMaxima(); }
  for (const c of S.corridas) actualizarHuella(c);
  pintarTarjetas(); pintarTiempo(); pintarGrafico();
}
function reproducir() {
  if (S.reproduccion) return detenerReproduccion();
  if (S.horaVista >= horaMaxima()) S.horaVista = 0;
  S.enVivo = false; $("reproducir").textContent = "⏸";
  S.reproduccion = setInterval(() => {
    if (S.horaVista >= horaMaxima()) { S.enVivo = true; return detenerReproduccion(); }
    verHora(S.horaVista + 1);
  }, 350);
}
function detenerReproduccion() { if (S.reproduccion) clearInterval(S.reproduccion); S.reproduccion = null; $("reproducir").textContent = "▶"; }

function pintarTiempo() {
  const max = horaMaxima(), d = $("deslizador");
  d.max = max; d.value = Math.min(S.horaVista, max);
  const t0 = S.corridas.find(c => c.t0)?.t0;
  const cuando = t0 ? aLocal(new Date(new Date(t0).getTime() + S.horaVista * 3600e3)).texto : "";
  $("rotulo-hora").innerHTML = `Hora ${S.horaVista} de ${horasPedidas()} <small>· ${cuando}</small>`;
  $("barra").style.width = `${Math.min(100, max / horasPedidas() * 100)}%`;
  $("reproducir").disabled = max < 1;
}

// ---------------------------------------------------------------- panel de la simulación
function pintarTodo() { pintarBotones(); pintarTarjetas(); pintarComparacion(); pintarTiempo(); pintarGrafico(); }

function pintarBotones() {
  const e = S.corridas.map(c => c.estado);
  const enMarcha = e.some(x => ["iniciando", "corriendo"].includes(x)), enPausa = e.some(x => ["pausando", "pausada"].includes(x));
  const todasFinales = e.length > 0 && e.every(x => FINALES.includes(x));
  $("pausar").hidden = !enMarcha || todasFinales; $("reanudar").hidden = !enPausa || enMarcha || todasFinales;
  $("detener").hidden = todasFinales; $("nueva").hidden = !todasFinales;
}

function motivo(c) {
  const r = c.detalle?.resultados;
  if (c.estado === "error" || c.estado === "interrumpida") return c.error || "La corrida no terminó bien.";
  if (!r) return "";
  if (c.estado === "detenida") return "Detenida por el usuario.";
  if (r.completa && r.t_simulado_h >= (Number(c.pedido?.horas) || 0) - 1e-6) return "Se cumplieron las horas pedidas.";
  return `El motor cortó antes de las horas pedidas: ${r.motivo_fin_texto || r.motivo_fin}.`;
}

function pintarTarjetas() {
  $("tarjetas").innerHTML = S.corridas.map(c => {
    const u = c.horas[Math.min(S.horaVista, horaMaxima(c))] || c.horas[c.horas.length - 1], fin = c.detalle?.resultados;
    const ult = c.horas[c.horas.length - 1];
    const ritmo = ult && ult.h > 0 ? ult.s / ult.h : null;
    let h = `<div class="tarjeta"><header><span class="marca" style="background:${c.color}"></span><span class="nombre">${MOTORES[c.motor]?.nombre || c.motor}</span><span class="estado">${ESTADOS[c.estado] || c.estado}</span></header>`;
    h += `<p class="cifra">${u ? num(u.ha, u.ha < 100 ? 1 : 0) + " ha" : "—"}<small>${u ? num(u.ha / 100, 2) + " km² · hora " + u.h : "esperando la primera hora"}</small></p><dl>`;
    if (u) h += `<dt>Celdas con fuego activo</dt><dd>${num(u.activas)}</dd>`;
    if (ritmo != null) h += `<dt>Cómputo</dt><dd>${num(ult.s, 1)} s (${num(ritmo, 2)} s por hora simulada)</dd>`;
    if (u?.meteo) h += `<dt>Viento</dt><dd>${num(u.meteo.viento_kmh, 0)} km/h del ${u.meteo.viento_dir_texto || "—"}</dd><dt>Temperatura · humedad</dt><dd>${num(u.meteo.temp_c, 0)} °C · ${num(u.meteo.hr_pct, 0)} %</dd>`;
    if (u?.exposicion) {
      const x = u.exposicion;
      h += `<dt>Viviendas afectadas · amenazadas</dt><dd>${num(x.viviendas_afectadas)} · ${num(x.viviendas_amenazadas)}</dd><dt>Red eléctrica quemada</dt><dd>${num(x.tendido_km_quemado, 1)} km</dd><dt>Caminos afectados</dt><dd>${num(x.caminos_km_afectados, 1)} km</dd>`;
    }
    h += "</dl>";
    if (u && !u.exposicion && c.motor.startsWith("v3.1")) h += `<p class="linea">v3.1 no informa viviendas, red eléctrica ni caminos alcanzados.</p>`;
    if (FINALES.includes(c.estado)) {
      const pausas = (c.detalle?.bitacora || []).filter(b => b.tipo === "pausa").map(b => `hora ${Math.round(b.t_sim_min / 60)}`);
      h += `<p class="linea">${motivo(c)}${fin ? ` Tiempo simulado: ${num(fin.t_simulado_h, 0)} h.` : ""}${pausas.length ? ` Pausas: ${pausas.join(", ")}.` : ""}</p>`;
      const corrido = (fin?.ignicion?.usada || []).find(x => x.desplazada_m);
      if (corrido) h += `<div class="aviso"><b>El fuego no empezó donde hiciste clic.</b>Esa celda no quema; el motor lo corrió ${num(corrido.desplazada_m)} m, a la celda combustible más cercana.</div>`;
      if (c.estado !== "error") h += `<p class="linea"><a href="/api/corridas/${c.id}/exportar">Descargar resultados (zip)</a></p>`;
    }
    return h + "</div>";
  }).join("");
}

function pintarComparacion() {
  const caja = $("comparacion"), comp = S.comparacion;
  caja.hidden = !comp || !comp.length;
  if (caja.hidden) return;
  const [a, b] = S.corridas;
  let h = "<h3>Comparación entre los dos motores</h3>";
  for (const c of comp) {
    h += `<dl><dt>Coincidencia a la hora ${c.hora}</dt><dd>${c.iou == null ? "—" : num(c.iou * 100, 0) + " %"}</dd>` +
         `<dt>Zona quemada por los dos</dt><dd>${num(c.ha_comun)} ha</dd><dt>Envolvente (por alguno de los dos)</dt><dd>${num(c.ha_envolvente)} ha</dd></dl>`;
  }
  const ref = comp[0];
  if (ref.iou != null && ref.iou < 0.5) {
    h += `<div class="aviso"><b>Los motores discrepan.</b>A la hora ${ref.hora} coinciden en menos de la mitad del área. No hay un resultado "promedio": mirá la envolvente como el área posible y cada huella como una hipótesis.</div>`;
  }
  h += `<p class="linea" style="color:var(--suave);margin:6px 0 0">Coincidencia = zona quemada por los dos dividida por la envolvente. ${MOTORES[a.motor].nombre}: relleno de amarillo a rojo. ${MOTORES[b.motor].nombre}: azul.</p>`;
  caja.innerHTML = h;
}

// ---------------------------------------------------------------- gráfico de superficie contra tiempo
function pintarGrafico() {
  const caja = $("grafico"), series = S.corridas.filter(c => c.horas.length);
  if (!series.length) { caja.innerHTML = '<p class="nota">El gráfico aparece cuando llega la primera hora.</p>'; $("tabla").innerHTML = ""; return; }
  const W = 336, H = 178, m = {i: 46, d: series.length > 1 ? 78 : 14, a: 10, b: 26};
  const xMax = horasPedidas(), yBruto = Math.max(1, ...series.flatMap(c => c.horas.map(p => p.ha)));
  const paso = pasoLindo(yBruto / 4), yMax = Math.ceil(yBruto / paso) * paso;
  const x = h => m.i + h / xMax * (W - m.i - m.d), y = v => H - m.b - v / yMax * (H - m.a - m.b);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Superficie quemada en hectáreas contra horas simuladas"><g class="rejilla">`;
  for (let v = 0; v <= yMax + 1e-9; v += paso) s += `<line x1="${m.i}" x2="${W - m.d}" y1="${y(v)}" y2="${y(v)}"/>`;
  s += '</g><g class="eje">';
  for (let v = 0; v <= yMax + 1e-9; v += paso) s += `<text x="${m.i - 6}" y="${y(v) + 4}" text-anchor="end">${num(v)}</text>`;
  const pasoX = pasoLindo(xMax / 5);
  for (let h = 0; h <= xMax; h += pasoX) s += `<text x="${x(h)}" y="${H - 8}" text-anchor="middle">${h}</text>`;
  s += `<text x="${W - m.d}" y="${H - 8}" text-anchor="end" dx="${m.d - 2}">${series.length > 1 ? "" : ""}</text></g>`;
  const fines = [];
  for (const c of series) {
    const puntos = c.horas.map(p => `${x(p.h).toFixed(1)},${y(p.ha).toFixed(1)}`).join(" ");
    s += `<polyline class="serie" stroke="${c.color}" points="${puntos}"/>`;
    const u = c.horas[c.horas.length - 1];
    fines.push({c, cx: x(u.h), cy: y(u.ha)});
  }
  if (series.length > 1) {                             // rótulos directos al final de cada línea, separados si se pisan
    fines.sort((p, q) => p.cy - q.cy);
    if (fines[1].cy - fines[0].cy < 13) { const medio = (fines[0].cy + fines[1].cy) / 2; fines[0].cy = medio - 6.5; fines[1].cy = medio + 6.5; }
    for (const f of fines) s += `<text class="rotulo" x="${W - m.d + 6}" y="${Math.max(10, f.cy + 4)}">${MOTORES[f.c.motor].nombre}</text>`;
  }
  const hv = Math.min(S.horaVista, xMax);
  s += `<line class="cursor" x1="${x(hv)}" x2="${x(hv)}" y1="${m.a}" y2="${H - m.b}"/>`;
  for (const c of series) { const p = c.horas[Math.min(hv, c.horas.length - 1)]; if (p) s += `<circle cx="${x(p.h)}" cy="${y(p.ha)}" r="4" fill="${c.color}" stroke="#fff" stroke-width="2"/>`; }
  s += `<rect id="zona" x="${m.i}" y="${m.a}" width="${W - m.i - m.d}" height="${H - m.a - m.b}" fill="transparent"/></svg>`;
  const clave = series.length > 1 ? `<div class="clave">${series.map(c => `<span><i style="background:${c.color}"></i>${MOTORES[c.motor].nombre}</span>`).join("")}</div>` : "";
  caja.innerHTML = clave + s + '<div id="globo" hidden></div><p class="nota">Hectáreas quemadas (vertical) contra horas simuladas (horizontal).</p>';

  const zona = caja.querySelector("#zona"), globo = caja.querySelector("#globo"), svg = caja.querySelector("svg");
  zona.addEventListener("mousemove", e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
    const h = Math.max(0, Math.min(horaMaxima(), Math.round((px - m.i) / (W - m.i - m.d) * xMax)));
    globo.hidden = false;
    globo.innerHTML = `<b>Hora ${h}</b><br>` + series.map(c => { const p = c.horas[Math.min(h, c.horas.length - 1)]; return `<i style="background:${c.color}"></i>${MOTORES[c.motor].nombre}: ${p ? num(p.ha, p.ha < 100 ? 1 : 0) + " ha" : "—"}`; }).join("<br>");
    globo.style.left = `${x(h) / W * r.width}px`; globo.style.top = `${(m.a + 6) / H * r.height + caja.querySelector(".clave")?.offsetHeight || 0}px`;
  });
  zona.addEventListener("mouseleave", () => { globo.hidden = true; });
  zona.addEventListener("click", e => { const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W; verHora(Math.max(0, Math.min(horaMaxima(), Math.round((px - m.i) / (W - m.i - m.d) * xMax))), true); });

  const filas = [];
  for (let h = 0; h <= horaMaxima(); h++) filas.push(`<tr><td>${h}</td>${series.map(c => `<td>${c.horas[h] ? num(c.horas[h].ha, 1) : "—"}</td>`).join("")}</tr>`);
  $("tabla").innerHTML = `<table><thead><tr><th>Hora</th>${series.map(c => `<th>${MOTORES[c.motor].nombre} (ha)</th>`).join("")}</tr></thead><tbody>${filas.join("")}</tbody></table>`;
}
function pasoLindo(v) { const p = Math.pow(10, Math.floor(Math.log10(Math.max(v, 1e-9)))); const f = v / p; return Math.max(1, (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p); }

// ---------------------------------------------------------------- simulaciones anteriores
async function listarAnteriores() {
  const {corridas} = await pedir("/api/corridas");
  const vistos = new Set(), opciones = [];
  for (const c of corridas.filter(x => FINALES.includes(x.estado) && x.ultima_hora)) {
    const clave = c.grupo || c.id;
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    const grupo = corridas.filter(x => (x.grupo || x.id) === clave);
    const cuando = aLocal(c.creada_utc).texto, motor = grupo.length > 1 ? "Ambos" : (MOTORES[c.motor]?.nombre || c.motor);
    opciones.push(`<option value="${clave}">${cuando} · ${motor} · ${c.ultima_hora.h} h · ${num(c.ultima_hora.ha)} ha</option>`);
  }
  $("anteriores").innerHTML = '<option value="">Elegir…</option>' + opciones.join("");
}
async function abrirAnterior(clave) {
  const {corridas} = await pedir("/api/corridas");
  const grupo = corridas.filter(x => (x.grupo || x.id) === clave).sort((a, b) => (a.motor === "v4.0" ? -1 : 1) - (b.motor === "v4.0" ? -1 : 1));
  if (!grupo.length) return;
  const p = grupo[0].pedido || {}, ign = (p.ignicion || [])[0];
  if (p.evento && S.estado.eventos_base.some(e => e.id === p.evento) && $("evento").value !== p.evento) { $("evento").value = p.evento; await cargarCapas(); }
  if (ign) ponerPunto(ign.lat, ign.lon, true);
  seguir(grupo, {motor: grupo.length > 1 ? "ambos" : grupo[0].motor});
  $("anteriores").value = clave;
}

arrancar().catch(e => { $("error").textContent = "No se pudo hablar con el servidor: " + e.message; });
