/* Pantalla del simulador (fases F3 a F5). Habla con el servidor local por los pedidos de docs/etapa3/contrato_servidor_motor.md §4.
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
           modo: "configurar", horaVista: 0, enVivo: true, reproduccion: null,
           datos: null, trabajo: null, canalTrabajo: null, ocupado: false};

// ---------------------------------------------------------------- utilidades
async function pedir(ruta, cuerpo, metodo) {
  const opciones = cuerpo === undefined ? (metodo ? {method: metodo} : {})
    : {method: metodo || "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(cuerpo)};
  return responder(await fetch(ruta, opciones));
}
async function subir(ruta, archivo) {                // archivo crudo como cuerpo del pedido (sin formularios multipart)
  return responder(await fetch(ruta, {method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: archivo}));
}
async function responder(r) {
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
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
const fechaCorta = d => d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—";      // "AAAA-MM-DD" → "DD/MM/AAAA"
const ev = () => S.estado.eventos_base.find(e => e.id === $("evento").value);

// ---------------------------------------------------------------- arranque
async function arrancar() {
  S.estado = await pedir("/api/estado");
  $("version").textContent = `Programa ${S.estado.programa.version} · motores congelados ${String(S.estado.congelado_sha256).slice(0, 8)}…`;
  $("motor").innerHTML = S.estado.motores.map(m => `<option value="${m.id}">${MOTORES[m.id]?.largo || m.id}</option>`).join("");
  llenarEventos();

  const [[sur, oeste], [norte, este]] = S.estado.dominio.limites;
  S.mapa = L.map("mapa", {zoomSnap: 0.25, minZoom: 9, maxZoom: 16, attributionControl: true,
                         maxBounds: [[sur - 0.4, oeste - 0.5], [norte + 0.4, este + 0.5]]});
  S.mapa.attributionControl.setPrefix("");
  S.mapa.attributionControl.addAttribution("Relieve: Copernicus DEM · Cobertura: MapBiomas · Caminos: © OpenStreetMap, IGN · Red MT: EDESAL · Cuarteles: Min. de Seguridad de San Luis");
  for (const [nombre, z] of [["fondo", 200], ["tematica", 250], ["huella", 380], ["vectores", 420]]) {
    S.mapa.createPane(nombre).style.zIndex = z;
  }
  S.mapa.fitBounds([[sur, oeste], [norte, este]]);
  for (const [nombre, z] of [["cortafuegos", 430], ["trazos", 440]]) S.mapa.createPane(nombre).style.zIndex = z;
  S.mapa.on("click", e => { if (S.modo === "configurar" && !T.modo) ponerPunto(e.latlng.lat, e.latlng.lng); });
  for (const id of ["hora", "esc-hora"]) $(id).innerHTML = Array.from({length: 24}, (_, h) => `<option value="${dos(h)}:00">${dos(h)}:00</option>`).join("");

  $("evento").onchange = () => { proponerEvento(); cargarCapas(); };
  $("borrar-rt").onclick = borrarRT;
  prepararDatos();
  for (const id of ["lat", "lon"]) $(id).onchange = () => ponerPunto(Number($("lat").value), Number($("lon").value), true);
  $("iniciar").onclick = iniciar;
  $("pausar").onclick = pausar;
  $("reanudar").onclick = () => { if (descartarBorradores("reanudar")) ordenar("reanudar"); };
  $("detener").onclick = () => ordenar("detener");
  $("nueva").onclick = nuevaSimulacion;
  $("deslizador").oninput = () => verHora(Number($("deslizador").value), true);
  $("reproducir").onclick = reproducir;
  $("ver-tabla").onclick = () => { $("tabla").hidden = !$("tabla").hidden; $("ver-tabla").textContent = $("tabla").hidden ? "Ver como tabla" : "Ocultar la tabla"; };
  $("en-linea").onchange = mapaEnLinea;
  $("anteriores").onchange = () => {
    if (!$("anteriores").value) return;
    if (!descartarBorradores("abrir otra simulación")) return void ($("anteriores").value = "");
    abrirAnterior($("anteriores").value);
  };
  $("tarjetas").addEventListener("click", e => { const b = e.target.closest("[data-reproducir]"); if (b) reproducirCorrida(b.dataset.reproducir, b); });
  prepararTrazos();
  prepararViento();

  proponerEvento();
  cargarDatos();                                     // no se espera: la zona de datos no frena el mapa
  await cargarCapas();
  await listarAnteriores();
}

// ---------------------------------------------------------------- selector de evento: tiempo real y ejemplos
// Los eventos generados (RT-…) van primero; los eventos con ficha se ofrecen rotulados EJEMPLO (plan §4.2).
function llenarEventos(elegir) {
  const antes = elegir || $("evento").value;
  const todos = S.estado.eventos_base;
  const rt = todos.filter(e => e.tiempo_real).sort((a, b) => String(b.creado_utc || b.id).localeCompare(String(a.creado_utc || a.id)));
  const ejemplos = todos.filter(e => !e.tiempo_real);
  $("evento").innerHTML =
    `<optgroup label="Tiempo real">${rt.length ? rt.map(e => `<option value="${esc(e.id)}">${esc(e.nombre || e.id)}</option>`).join("")
      : '<option value="" disabled>Todavía no hay: armalo en «Datos»</option>'}</optgroup>` +
    `<optgroup label="Ejemplos (incendios históricos con ficha)">${ejemplos.map(e => `<option value="${esc(e.id)}">EJEMPLO · ${esc(e.nombre || e.id)}</option>`).join("")}</optgroup>`;
  const lagunas = ejemplos.find(e => e.id === "SL-2024-LASLAGUNAS");
  const elegido = todos.find(e => e.id === antes) || rt[0] || lagunas || ejemplos[0];
  if (elegido) $("evento").value = elegido.id;
}

async function refrescarEventos(elegir) {
  const previo = $("evento").value;
  S.estado = await pedir("/api/estado");
  llenarEventos(elegir);
  if (S.modo === "configurar" && $("evento").value !== previo) { proponerEvento(); await cargarCapas(); }
  else if (S.modo === "configurar") pintarRotulosEvento(ev());
}

function pintarRotulosEvento(e) {
  if (!e) { $("rotulos-evento").innerHTML = $("avisos-evento").innerHTML = ""; $("borrar-rt").hidden = true; return; }
  const rotulos = e.rotulos || [];
  $("rotulos-evento").innerHTML = (e.tiempo_real ? '<span class="rotulo rt">tiempo real</span>' : "") +
    rotulos.map(r => `<span class="rotulo${r === "EJEMPLO" ? " ejemplo" : /prueba|escenario|mano/i.test(r) ? " prueba" : ""}">${esc(r)}</span>`).join("");
  const avisos = (e.avisos || []).filter(a => !(rotulos.includes("EJEMPLO") && /^EJEMPLO/.test(a)));
  if (!e.tiempo_real) avisos.unshift("Es un ejemplo: el tiempo y la vegetación son los de un incendio histórico, no los de hoy.");
  $("avisos-evento").innerHTML = avisos.length ? `<div class="aviso">${avisos.length > 1 ? `<ul>${avisos.map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : esc(avisos[0])}</div>` : "";
  $("borrar-rt").hidden = !e.tiempo_real;
}

function proponerEvento() {
  const e = ev();
  pintarRotulosEvento(e);
  if (!e) return;
  let inicio = e.tiempo_real ? e.t_inicio_por_defecto_utc : (e.inicios_de_la_ficha_utc || [])[0];
  inicio = inicio || e.meteo_desde_utc;
  if (inicio && e.meteo_desde_utc && e.meteo_hasta_utc) {                // dentro del rango de la meteorología
    const t = new Date(normalizarUTC(inicio)).getTime(), a = new Date(e.meteo_desde_utc).getTime(), b = new Date(e.meteo_hasta_utc).getTime() - 3600e3;
    inicio = new Date(Math.min(Math.max(t, a), Math.max(a, b))).toISOString();
  }
  if (inicio) {                                                        // las corridas empiezan en hora en punto (D-E3-28, 6)
    const t = Math.floor(new Date(normalizarUTC(inicio)).getTime() / 3600e3) * 3600e3;
    const desde = e.meteo_desde_utc ? Math.ceil(new Date(e.meteo_desde_utc).getTime() / 3600e3) * 3600e3 : t;
    const l = aLocal(new Date(Math.max(t, desde)).toISOString()); $("fecha").value = l.fecha; $("hora").value = l.hora;
  }
  if (e.meteo_desde_utc) {
    $("fecha").min = aLocal(e.meteo_desde_utc).fecha; $("fecha").max = aLocal(e.meteo_hasta_utc).fecha;
    $("nota-evento").textContent = `Hay datos del tiempo del ${aLocal(e.meteo_desde_utc).texto} al ${aLocal(e.meteo_hasta_utc).texto} (hora argentina).` +
      (e.tiempo_real ? " Este evento no trae punto de ignición: marcalo con un clic en el mapa." : "");
  } else $("nota-evento").textContent = "";
  const p = (e.ignicion_de_la_ficha || [])[0];
  if (p) ponerPunto(p.lat, p.lon, true); else quitarPunto();
}

async function borrarRT() {
  const e = ev();
  if (!e || !e.tiempo_real) return;
  if (!confirm(`¿Borrar el evento ${e.id}? Se borran su ficha, su meteorología y su combustible. Las tomas de datos quedan.`)) return;
  $("error").textContent = "";
  try {
    await pedir(`/api/datos/eventos/${encodeURIComponent(e.id)}`, undefined, "DELETE");
    await refrescarEventos("");
    cargarDatos();
  } catch (x) { $("error").textContent = x.message; }
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
  const conCf = S.corridas.some(c => c.cortafuegos.length), recortes = S.corridas.some(c => c.cortafuegos.some(f => f.properties._recortado));
  if (conCf || T.borradores.length) {
    bloques.push("<h3>Cortafuegos</h3>" + (conCf ? '<div class="item"><span class="linea-cf"></span>aplicado</div>' : "") +
      (recortes ? '<div class="item"><span class="linea-cf recortado"></span>recortado (ya quemado o fuera de la zona simulada)</div>' : "") +
      (T.borradores.length ? '<div class="item"><span class="linea-cf borrador"></span>dibujado, sin enviar</div>' : ""));
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
  const e = ev();
  if (!e) return void ($("error").textContent = "Elegí los datos del terreno y del tiempo.");
  if (!$("lat").value || !$("lon").value) return void ($("error").textContent = e.tiempo_real
    ? "Este evento de tiempo real no trae punto de ignición: marcalo con un clic en el mapa." : "Marcá el punto de ignición con un clic en el mapa.");
  if (!$("fecha").value || !$("hora").value) return void ($("error").textContent = "Falta el día o la hora de inicio.");
  if (!(horas >= 1 && horas <= 240)) return void ($("error").textContent = "Las horas a simular van de 1 a 240.");
  if (e.meteo_desde_utc && e.meteo_hasta_utc) {
    const t = new Date(aUTC($("fecha").value, $("hora").value)).getTime();
    if (t < new Date(e.meteo_desde_utc).getTime() || t >= new Date(e.meteo_hasta_utc).getTime())
      return void ($("error").textContent = `La hora de inicio cae fuera de los datos del tiempo (del ${aLocal(e.meteo_desde_utc).texto} al ${aLocal(e.meteo_hasta_utc).texto}).`);
  }
  const pedido = {motor: $("motor").value, evento: $("evento").value, horas, iniciar: true,
                  ignicion: [{lat: Number($("lat").value), lon: Number($("lon").value)}], t_inicio_utc: aUTC($("fecha").value, $("hora").value)};
  if (T.borradores.length) pedido.cortafuegos = T.borradores.map(cuerpoTrazo);
  $("iniciar").disabled = true;
  try {
    const r = await pedir("/api/corridas", pedido);
    S.pedido = pedido;
    vaciarBorradores();
    seguir(r.corridas, pedido);
  } catch (e) { $("error").textContent = e.message; }
  $("iniciar").disabled = false;
}

function seguir(resumenes, pedido) {
  limpiarCorridas();
  S.modo = "corriendo"; S.enVivo = true; S.horaVista = 0;
  S.corridas = resumenes.map((r, i) => ({id: r.id, motor: r.motor, color: MOTORES[r.motor]?.color || "#555", estado: r.estado, horas: [], plano: resumenes.length > 1 && i > 0,
                                         pedido: r.pedido || pedido, t0: null, limites: null, capa: null, cargando: false, pendiente: null, detalle: null, error: null,
                                         grupo: r.grupo || null, reproduccionDe: r.reproduccion_de || null, pausaT: r.pausa_t_sim_min ?? null, pausaEn: r.pausa_en_t_sim_min ?? null,
                                         bitacora: [], integra: null, cortafuegos: [], capaCf: null, mascaras: {}}));
  if (S.marcador) S.marcador.dragging.disable();
  vaciarBorradores(); ponerHerramienta("pausa");
  $("respuestas").innerHTML = ""; $("error-intervenir").textContent = ""; $("pausar-en").value = "";
  $("sec-config").hidden = true; $("sec-control").hidden = false; $("sec-grafico").hidden = false; $("tiempo").hidden = false;
  const p = S.corridas[0].pedido, ign = (p.ignicion || [])[0];
  $("resumen-config").innerHTML = `<b>${MOTORES[pedido.motor || p.motor]?.largo || p.motor}</b><br>` +
    `${(S.estado.eventos_base.find(e => e.id === p.evento) || {}).nombre || p.evento || "sin evento"}<br>` +
    (ign ? `Ignición en ${num(ign.lat, 4)}, ${num(ign.lon, 4)}<br>` : "") +
    (p.t_inicio_utc ? `Inicio: ${aLocal(p.t_inicio_utc).texto} (hora argentina)<br>` : "") + `Duración pedida: ${p.horas} h` +
    ((p.cortafuegos || []).length ? `<br>Cortafuegos desde el inicio: ${p.cortafuegos.length}` : "") +
    (S.corridas[0].reproduccionDe ? `<br><b>Reproducción</b> de la corrida ${esc(S.corridas[0].reproduccionDe)}: aplica su bitácora, sin intervenciones nuevas` : "");
  for (const c of S.corridas) escuchar(c);
  pintarTodo();
}

function escuchar(c) {
  c.canal = new EventSource(`/api/corridas/${c.id}/eventos`);
  c.canal.onmessage = m => {
    const e = JSON.parse(m.data);
    if (e.aviso === "estado") {
      c.estado = e.estado; if (e.motivo) c.error = e.motivo;
      if (e.estado === "pausada") { c.pausaT = e.t_sim_min ?? c.pausaT; c.pausaEn = null; }
      else if (e.estado === "pausando") c.pausaT = null;
      else if (e.estado === "corriendo") c.pausaT = c.pausaEn = null;
      if (FINALES.includes(e.estado)) alTerminar(c);
    }
    else if (e.aviso === "listo") {
      c.t0 = normalizarUTC(e.t0_utc);
      pedir(`/api/corridas/${c.id}`).then(d => { c.limites = d.huella?.limites; tomarBitacora(c, d); actualizarHuella(c); refrescarCortafuegos(c); pintarTodo(); });
    }
    else if (AVISOS_BITACORA.includes(e.aviso)) {
      if (e.entrada) sumarEntrada(c, e.entrada);
      if (e.aviso === "intervencion" && e.entrada?.tipo === "cortafuego") refrescarCortafuegos(c);
    }
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
  try { c.detalle = await pedir(`/api/corridas/${c.id}`); tomarBitacora(c, c.detalle); } catch (e) { /* queda sin detalle */ }
  refrescarCortafuegos(c);
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
  for (const c of S.corridas) { if (c.canal) c.canal.close(); if (c.capa) c.capa.remove(); if (c.capaCf) c.capaCf.remove(); }
  for (const m of S.usados) m.remove();
  S.usados = []; S.corridas = []; S.comparacion = null;
}
function nuevaSimulacion() {
  limpiarCorridas();
  S.modo = "configurar";
  if (S.marcador) S.marcador.dragging.enable();
  $("sec-config").hidden = false; $("sec-control").hidden = true; $("sec-grafico").hidden = true; $("tiempo").hidden = true;
  vaciarBorradores(); ponerHerramienta("config");
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
function pintarTodo() { pintarBotones(); pintarIntervenir(); pintarTarjetas(); pintarComparacion(); pintarTiempo(); pintarGrafico(); }

function pintarBotones() {
  const e = S.corridas.map(c => c.estado);
  const enMarcha = e.some(x => ["iniciando", "corriendo"].includes(x)), enPausa = e.some(x => ["pausando", "pausada"].includes(x));
  const todasFinales = e.length > 0 && e.every(x => FINALES.includes(x));
  const repro = S.corridas.some(c => c.reproduccionDe);
  const pausando = e.some(x => x === "pausando");
  $("pausar").hidden = repro || todasFinales || !(enMarcha || pausando);
  $("pausar").textContent = pausando && !enMarcha ? "Cambiar la hora de la pausa" : "Pausar";
  $("caja-pausar-en").hidden = $("pausar").hidden;
  $("reanudar").hidden = !enPausa || enMarcha || todasFinales;
  $("detener").hidden = todasFinales; $("nueva").hidden = !todasFinales;
  const pedidas = S.corridas.filter(c => c.estado === "pausando").map(c => c.pausaEn);
  $("nota-pausa").textContent = !pausando ? ""
    : pedidas.some(x => x != null) ? `Pausando en la hora ${num(Math.max(...pedidas.filter(x => x != null)) / 60)}…` : "Pausando al terminar la hora en curso…";
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
    h += htmlBitacora(c);
    if (FINALES.includes(c.estado)) {
      h += `<p class="linea">${motivo(c)}${fin ? ` Tiempo simulado: ${num(fin.t_simulado_h, 0)} h.` : ""}</p>`;
      if (fin?.reproduccion) h += htmlReproduccion(fin.reproduccion);
      const corrido = (fin?.ignicion?.usada || []).find(x => x.desplazada_m);
      if (corrido) h += `<div class="aviso"><b>El fuego no empezó donde hiciste clic.</b>Esa celda no quema; el motor lo corrió ${num(corrido.desplazada_m)} m, a la celda combustible más cercana.</div>`;
      if (c.estado !== "error") h += `<p class="linea"><a href="/api/corridas/${c.id}/exportar">Descargar resultados (zip)</a></p>`;
      if (["terminada", "detenida"].includes(c.estado) && c.bitacora.length && S.estado.motores.some(m => m.id === c.motor))
        h += `<div class="botones"><button data-reproducir="${esc(c.id)}" title="Corre de nuevo la misma configuración aplicando la bitácora, y compara las dos">Reproducir</button></div>`;
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

// ---------------------------------------------------------------- intervenciones (fase F5): pausa, cortafuegos, viento, bitácora
// Contrato 1.5 §4.2. Las intervenciones van solo con la corrida en pausa (en hora en punto); en el modo "ambos", por el grupo,
// a las dos corridas en la misma hora. Los trazos se dibujan a mano alzada con los eventos del puntero: el mapa queda quieto
// mientras se dibuja y el trazo se simplifica (Douglas-Peucker) al soltar. La longitud que se ve es aproximada (en la esfera);
// la oficial la calcula el servidor en EPSG:5345.
const AVISOS_BITACORA = ["pausado", "reanudado", "intervencion", "detenido"];
const ANCHOS_M = [3, 6, 10, 15, 25];
const MAX_TRAZOS = 100, MAX_PUNTOS = 10000;
const COLOR_BORRADOR = "#1d6fd6", COLOR_CF = "#1c1b19", COLOR_RECORTE = "#8a877f";
const T = {modo: null, borradores: [], hechos: [], trazo: null, linea: null, puntero: null, capa: null, siguiente: 1, ocupado: false};
const RUMBOS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"];
const rumbo = g => RUMBOS[Math.round((((Number(g) % 360) + 360) % 360) / 22.5) % 16];
const metros = lls => lls.slice(1).reduce((s, p, i) => s + lls[i].distanceTo(p), 0);
const horaDe = t => `hora ${num(t / 60, Number.isInteger(t / 60) ? 0 : 1)}`;
const cuerpoTrazo = b => ({ancho_m: b.ancho_m, suelo_mineral: b.suelo_mineral, lonlat: b.lonlat});

function prepararTrazos() {
  const anchos = S.estado.intervenciones?.anchos_m || ANCHOS_M;
  $("ancho").innerHTML = anchos.map(a => `<option value="${a}"${a === 10 ? " selected" : ""}>${a} m</option>`).join("");
  T.capa = L.layerGroup().addTo(S.mapa);
  $("b-dibujar").onclick = () => elegirHerramienta(T.modo === "dibujar" ? null : "dibujar");
  $("b-borrador").onclick = () => elegirHerramienta(T.modo === "borrar" ? null : "borrar");
  $("b-deshacer").onclick = deshacer;
  $("b-enviar-trazos").onclick = enviarTrazos;
  $("lista-trazos").addEventListener("click", e => { const b = e.target.closest("[data-borrar]"); if (b) borrarTrazo(Number(b.dataset.borrar)); });
  const cont = S.mapa.getContainer();
  cont.addEventListener("pointerdown", empezarTrazo, true);          // en captura: Leaflet no se entera del gesto
  cont.addEventListener("pointermove", seguirTrazo, true);
  cont.addEventListener("pointerup", terminarTrazo, true);
  cont.addEventListener("pointercancel", terminarTrazo, true);
  document.addEventListener("keydown", e => {
    const escribiendo = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "");
    if (e.key === "Escape" && T.modo) elegirHerramienta(null);
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !escribiendo && T.hechos.length) { e.preventDefault(); deshacer(); }
  });
  ponerHerramienta("config");
}

const trazosHabilitados = () => !T.ocupado && (S.modo === "configurar" ? !$("sec-config").hidden : puedeIntervenir());

function ponerHerramienta(donde) {
  $(donde === "config" ? "lugar-trazos-config" : "lugar-trazos-pausa").appendChild($("herr-cortafuegos"));
  $("trazos-cuando").textContent = donde === "config" ? "(opcional, desde la hora 0)" : "";
  elegirHerramienta(null);
}

function elegirHerramienta(modo) {
  if (modo && !trazosHabilitados()) modo = null;
  if (!modo && T.puntero != null) cancelarTrazo();
  T.modo = modo;
  const cont = S.mapa.getContainer();
  cont.classList.toggle("dibujando", modo === "dibujar");
  cont.classList.toggle("borrando", modo === "borrar");
  for (const h of ["dragging", "doubleClickZoom", "boxZoom", "touchZoom"]) if (S.mapa[h]) modo === "dibujar" ? S.mapa[h].disable() : S.mapa[h].enable();
  pintarTrazos();
}

function empezarTrazo(e) {
  if (T.modo !== "dibujar" || T.puntero != null || (e.pointerType === "mouse" && e.button !== 0)) return;
  if (e.target.closest && e.target.closest(".leaflet-control-container")) return;
  e.preventDefault(); e.stopPropagation();
  try { S.mapa.getContainer().setPointerCapture(e.pointerId); } catch (x) { /* sin captura igual se dibuja */ }
  T.puntero = e.pointerId;
  S.mapa.scrollWheelZoom.disable();
  T.trazo = [S.mapa.mouseEventToLatLng(e)];
  T.linea = L.polyline(T.trazo, {pane: "trazos", color: COLOR_BORRADOR, weight: 3, interactive: false}).addTo(T.capa);
  $("error-trazos").textContent = "";
  mostrarLargo(e, 0);
}

function seguirTrazo(e) {
  if (T.puntero == null || e.pointerId !== T.puntero) return;
  e.preventDefault(); e.stopPropagation();
  const ll = S.mapa.mouseEventToLatLng(e), ult = T.trazo[T.trazo.length - 1];
  if (S.mapa.latLngToContainerPoint(ll).distanceTo(S.mapa.latLngToContainerPoint(ult)) < 2) return;
  T.trazo.push(ll); T.linea.addLatLng(ll);
  mostrarLargo(e, metros(T.trazo));
}

function cancelarTrazo() {
  if (T.linea) T.linea.remove();
  T.linea = T.trazo = T.puntero = null;
  S.mapa.scrollWheelZoom.enable();
  $("largo-trazo").hidden = true;
}

function terminarTrazo(e) {
  if (T.puntero == null || e.pointerId !== T.puntero) return;
  e.preventDefault(); e.stopPropagation();
  try { S.mapa.getContainer().releasePointerCapture(e.pointerId); } catch (x) { /* ya estaba suelta */ }
  const crudo = T.trazo;
  cancelarTrazo();
  if (e.type === "pointercancel" || !crudo) return;
  const ll = simplificar(crudo);
  const [[sur, oeste], [norte, este]] = S.estado.dominio.limites;
  const fallo = ll.length < 2 || metros(ll) < 5 ? "El trazo es muy corto: apretá sobre el mapa y arrastrá."
    : !ll.some(p => p.lat >= sur && p.lat <= norte && p.lng >= oeste && p.lng <= este) ? "El trazo cae entero fuera del dominio."
    : T.borradores.length >= MAX_TRAZOS ? `Se pueden mandar hasta ${MAX_TRAZOS} trazos juntos.` : "";
  if (fallo) return void ($("error-trazos").textContent = fallo);
  const b = {id: T.siguiente++, lonlat: ll.map(p => [Number(p.lng.toFixed(7)), Number(p.lat.toFixed(7))]), largo: metros(ll),
             ancho_m: Number($("ancho").value), suelo_mineral: $("mineral").checked, capa: null, error: ""};
  T.borradores.push(b); T.hechos.push({accion: "agregar", b});
  dibujarBorrador(b); pintarTrazos();
}

// Douglas-Peucker en píxeles de la vista actual: lo que se ve dibujado es lo que se manda (tolerancia de 1,5 px).
function simplificar(lls) {
  let tol = 1.5, out = lls;
  const pts = lls.map(p => S.mapa.latLngToLayerPoint(p));
  do {
    const queda = new Uint8Array(pts.length);
    queda[0] = queda[pts.length - 1] = 1;
    const pila = [[0, pts.length - 1]];
    while (pila.length) {
      const [a, b] = pila.pop();
      let max = 0, k = -1;
      for (let i = a + 1; i < b; i++) { const d = L.LineUtil.pointToSegmentDistance(pts[i], pts[a], pts[b]); if (d > max) { max = d; k = i; } }
      if (k > 0 && max > tol) { queda[k] = 1; pila.push([a, k], [k, b]); }
    }
    out = lls.filter((_, i) => queda[i]).filter((p, i, xs) => i === 0 || !p.equals(xs[i - 1]));
    tol *= 2;
  } while (out.length > MAX_PUNTOS);
  return out;
}

function mostrarLargo(e, m) {
  const caja = $("largo-trazo"), r = $("mapa").getBoundingClientRect();
  caja.hidden = false;
  caja.style.left = `${e.clientX - r.left}px`; caja.style.top = `${e.clientY - r.top}px`;
  caja.textContent = `${num(m)} m · ancho ${$("ancho").value} m`;
}

function dibujarBorrador(b) {
  const lls = b.lonlat.map(([lon, lat]) => L.latLng(lat, lon));
  const toque = L.polyline(lls, {pane: "trazos", color: COLOR_BORRADOR, weight: 16, opacity: 0, className: "trazo-borrador"})
    .on("click", ev => { if (T.modo === "borrar") { L.DomEvent.stopPropagation(ev); borrarTrazo(b.id); } })
    .bindTooltip(() => `Trazo ${T.borradores.indexOf(b) + 1} sin enviar · ${b.ancho_m} m de ancho · ${num(b.largo)} m${T.modo === "borrar" ? " · tocalo para borrarlo" : ""}`, {sticky: true});
  b.capa = L.layerGroup([L.polyline(lls, {pane: "trazos", color: "#fff", weight: 6, opacity: 0.8, interactive: false}),
                         L.polyline(lls, {pane: "trazos", color: COLOR_BORRADOR, weight: 3, dashArray: "7 5", interactive: false}), toque]).addTo(T.capa);
}

function quitarBorrador(b) {
  const i = T.borradores.indexOf(b);
  if (i < 0) return -1;
  T.borradores.splice(i, 1);
  if (b.capa) { b.capa.remove(); b.capa = null; }
  return i;
}

function borrarTrazo(id) {
  if (T.ocupado) return;
  const b = T.borradores.find(x => x.id === id);
  if (!b) return;
  const i = quitarBorrador(b);
  T.hechos.push({accion: "borrar", b, i});
  pintarTrazos();
}

function deshacer() {
  if (T.ocupado) return;
  const h = T.hechos.pop();
  if (!h) return;
  if (h.accion === "agregar") quitarBorrador(h.b);
  else { T.borradores.splice(Math.min(h.i, T.borradores.length), 0, h.b); dibujarBorrador(h.b); }
  pintarTrazos();
}

function vaciarBorradores() {
  for (const b of T.borradores) if (b.capa) b.capa.remove();
  T.borradores = []; T.hechos = [];
  $("error-trazos").textContent = "";
  if (S.mapa) elegirHerramienta(null);
}

// Antes de reanudar, abrir otra corrida…: los trazos sin enviar se pierden; se pregunta.
function descartarBorradores(accion) {
  if (!T.borradores.length) return true;
  const n = T.borradores.length;
  if (!confirm(`Hay ${n} ${n === 1 ? "trazo dibujado que no se aplicó" : "trazos dibujados que no se aplicaron"}. Si seguís (${accion}), se ${n === 1 ? "descarta" : "descartan"}.`)) return false;
  vaciarBorradores();
  return true;
}

function pintarTrazos() {
  if (!S.mapa) return;
  const si = trazosHabilitados(), pausa = S.modo !== "configurar";
  $("b-dibujar").disabled = $("b-borrador").disabled = !si;
  $("b-borrador").disabled ||= !T.borradores.length;
  if (T.modo === "borrar" && !T.borradores.length) { T.modo = null; S.mapa.getContainer().classList.remove("borrando"); }
  $("b-dibujar").setAttribute("aria-pressed", String(T.modo === "dibujar"));
  $("b-borrador").setAttribute("aria-pressed", String(T.modo === "borrar"));
  $("b-dibujar").textContent = T.modo === "dibujar" ? "Dibujando…" : "Dibujar";
  $("b-deshacer").disabled = !T.hechos.length || T.ocupado;
  $("lista-trazos").innerHTML = T.borradores.map((b, i) => `<li><div class="fila"><span>${b.ancho_m} m de ancho · ${num(b.largo)} m${b.suelo_mineral ? " · a suelo mineral" : ""}</span>` +
    `<button data-borrar="${b.id}" aria-label="Borrar el trazo ${i + 1}" title="Borrar este trazo"${T.ocupado ? " disabled" : ""}>×</button></div>` +
    (b.error ? `<p class="error">${esc(b.error)}</p>` : "") + "</li>").join("");
  const total = T.borradores.reduce((s, b) => s + b.largo, 0);
  $("nota-trazos").textContent = T.modo === "dibujar" ? "Apretá sobre el mapa, arrastrá y soltá. El mapa no se mueve mientras dibujás (Esc para salir)."
    : T.modo === "borrar" ? "Tocá un trazo sin enviar para borrarlo."
    : T.borradores.length ? `${T.borradores.length} ${T.borradores.length === 1 ? "trazo" : "trazos"} · ${num(total)} m dibujados (aproximado: la longitud oficial la da el servidor).`
    : pausa ? "Dibujá los cortafuegos y aplicalos: rigen desde la hora de la pausa, solo sobre lo que el fuego todavía no alcanzó."
    : "Dibujalos con «Dibujar». Van con el pedido de la corrida y rigen desde el inicio.";
  $("b-enviar-trazos").hidden = !pausa || !T.borradores.length;
  $("b-enviar-trazos").disabled = T.ocupado || !puedeIntervenir();
  $("b-enviar-trazos").textContent = T.borradores.length === 1 ? "Aplicar el trazo" : `Aplicar los ${T.borradores.length} trazos`;
  dibujarLeyenda();
}

// ---- pausa
const grupoDe = () => S.corridas.length > 1 && S.corridas[0].grupo && S.corridas.every(c => c.grupo === S.corridas[0].grupo) ? S.corridas[0].grupo : null;

async function pausar() {
  $("error-control").textContent = "";
  const v = $("pausar-en").value.trim(), cuerpo = {};
  if (v !== "") {
    const h = Number(v);
    if (!Number.isFinite(h) || h < 0) return void ($("error-control").textContent = "La hora de la pausa es un número de 0 en adelante (o vacío: la próxima).");
    cuerpo.en_t_sim_min = Math.ceil(h) * 60;
  }
  const g = grupoDe();
  try {
    if (g) tomarResumenes((await pedir(`/api/grupos/${encodeURIComponent(g)}/pausar`, cuerpo)).corridas);
    else for (const c of S.corridas.filter(x => ["iniciando", "corriendo"].includes(x.estado) || (x.estado === "pausando" && v !== ""))) {
      tomarResumenes([await pedir(`/api/corridas/${c.id}/pausar`, cuerpo)]);
    }
  } catch (e) { $("error-control").textContent = e.message; }
  pintarTodo();
}

// Las respuestas pueden llegar después de los avisos del canal: el estado solo avanza de "en marcha" a "pausando".
function tomarResumenes(lista) {
  for (const r of lista || []) {
    const c = S.corridas.find(x => x.id === r.id);
    if (!c) continue;
    if (r.estado === "pausando" && ["iniciando", "corriendo", "pausando"].includes(c.estado)) { c.estado = "pausando"; c.pausaEn = r.pausa_en_t_sim_min ?? null; }
  }
}

function horaDePausa() {
  const cs = S.corridas;
  if (!cs.length || cs.some(c => c.estado !== "pausada" || c.pausaT == null)) return null;
  return cs.every(c => Math.abs(c.pausaT - cs[0].pausaT) < 1e-6) ? cs[0].pausaT : null;
}
const puedeIntervenir = () => horaDePausa() != null && !S.corridas.some(c => c.reproduccionDe);

function pintarIntervenir() {
  const t = horaDePausa(), si = puedeIntervenir();
  const cs = S.corridas;
  if (!si && cs.length > 1 && cs.every(c => c.estado === "pausada") && t == null)
    $("nota-pausa").textContent = "Las dos corridas quedaron en pausa en horas distintas; el servidor las alinea en la más avanzada. Esperá un momento…";
  else if (cs.some(c => c.reproduccionDe) && cs.some(c => ["pausando", "pausada"].includes(c.estado)))
    $("nota-pausa").textContent = "Es una reproducción: aplica la bitácora original y no acepta intervenciones nuevas.";
  const antes = !$("intervenir").hidden;
  $("intervenir").hidden = !si;
  if (!si) { if (antes || T.modo) elegirHerramienta(null); return; }
  $("hora-pausa").textContent = num(t / 60);
  $("v-hora").textContent = num(t / 60);
  $("aviso-v40").hidden = !cs.some(c => c.motor === "v4.0");
  if (!antes) {                                                    // al entrar en la pausa: viento de la última hora, para partir de ahí
    const m = cs.map(c => c.horas[c.horas.length - 1]?.meteo).find(Boolean);
    if (m && $("v-vel").value === "" && m.viento_kmh != null) $("v-vel").value = Math.round(m.viento_kmh);
    const dir = m?.viento_dir_deg ?? m?.viento_dir;
    if ($("v-dir").value === "" && Number.isFinite(Number(dir))) $("v-dir").value = Math.round(Number(dir)) % 360;
    textoDelViento();
  }
  pintarTrazos();
  for (const b of ["b-viento", "b-pronostico-viento"]) $(b).disabled = T.ocupado;
}

// ---- intervenir (una corrida o el grupo)
async function intervenir(cuerpo) {
  const g = grupoDe();
  if (g) {
    const r = await pedir(`/api/grupos/${encodeURIComponent(g)}/intervenciones`, cuerpo);
    return (r.respuestas || []).map(x => ({id: x.id, motor: x.motor, aviso: x.aviso, error: x.error}));
  }
  const c = S.corridas[0];
  return [{id: c.id, motor: c.motor, aviso: await pedir(`/api/corridas/${c.id}/intervenciones`, cuerpo)}];
}

const ESTADO_INTERVENCION = {aceptada: "aplicado", recortada: "aplicado con recorte", rechazada: "rechazado"};
function anotarRespuestas(titulo, respuestas) {
  const lineas = [];
  for (const r of respuestas) {
    const c = S.corridas.find(x => x.id === r.id) || (S.corridas.length === 1 ? S.corridas[0] : null);
    const a = r.aviso, nombre = MOTORES[r.motor]?.nombre || r.motor;
    if (a?.entrada && c) sumarEntrada(c, a.entrada);
    const estado = a ? a.estado : "rechazada";
    lineas.push(`<span class="${estado}">${S.corridas.length > 1 ? `${esc(nombre)}: ` : ""}${ESTADO_INTERVENCION[estado] || esc(estado)}` +
      (a?.pleno_min != null ? `; rige del todo desde la ${horaDe(a.pleno_min)}` : "") +
      (a?.motivo ? ` — ${esc(a.motivo)}` : r.error ? ` — ${esc(r.error)}` : !a ? " — el motor no contestó" : "") + "</span>");
  }
  const li = document.createElement("li");
  li.innerHTML = `<b>${esc(titulo)}</b> · ${lineas.join("<br>")}`;
  $("respuestas").prepend(li);
  while ($("respuestas").children.length > 8) $("respuestas").lastElementChild.remove();
}

function ocupar(si) { T.ocupado = si; pintarIntervenir(); pintarTrazos(); }

async function enviarTrazos() {
  if (!puedeIntervenir() || !T.borradores.length || T.ocupado) return;
  elegirHerramienta(null);
  $("error-intervenir").textContent = "";
  ocupar(true);
  try {
    for (const b of [...T.borradores]) {
      b.error = "";
      try {
        const rs = await intervenir({tipo: "cortafuego", datos: cuerpoTrazo(b)});
        anotarRespuestas(`Cortafuego de ${b.ancho_m} m (${num(b.largo)} m dibujados)`, rs);
        if (rs.some(x => x.aviso && x.aviso.estado !== "rechazada")) quitarBorrador(b);
        else b.error = rs.map(x => x.aviso?.motivo || x.error).filter(Boolean).join("; ") || "El motor no lo aplicó.";
      } catch (e) {
        b.error = e.message;
        if (!puedeIntervenir()) break;                               // la corrida salió de la pausa: no tiene sentido seguir
      }
    }
  } finally {
    T.hechos = T.hechos.filter(h => T.borradores.includes(h.b));    // deshacer: solo lo que no se mandó
    ocupar(false);
  }
  for (const c of S.corridas) refrescarCortafuegos(c);
  pintarTarjetas();
}

function prepararViento() {
  $("v-vel").max = S.estado.intervenciones?.vel_max_kmh || 216;
  $("v-vel").oninput = $("v-dir").oninput = textoDelViento;
  $("b-viento").onclick = () => aplicarViento(false);
  $("b-pronostico-viento").onclick = () => aplicarViento(true);
}

function textoDelViento() {
  const v = Number($("v-vel").value), d = Number($("v-dir").value);
  const bien = $("v-vel").value !== "" && $("v-dir").value !== "" && v >= 0 && d >= 0 && d <= 360;
  $("v-texto").textContent = bien ? `${num(v)} km/h del ${rumbo(d)}: sopla hacia el ${rumbo(d + 180)}.` : "";
}

async function aplicarViento(pronostico) {
  if (!puedeIntervenir() || T.ocupado) return;
  $("error-intervenir").textContent = "";
  const max = Number($("v-vel").max) || 216, v = Number($("v-vel").value), d = Number($("v-dir").value);
  let cuerpo, titulo;
  if (pronostico) { cuerpo = {tipo: "viento_manual", datos: {modo: "pronostico"}}; titulo = "Volver al viento del pronóstico"; }
  else {
    if ($("v-vel").value === "" || !(v >= 0 && v <= max)) return void ($("error-intervenir").textContent = `La velocidad del viento va de 0 a ${num(max)} km/h.`);
    if ($("v-dir").value === "" || !(d >= 0 && d <= 360)) return void ($("error-intervenir").textContent = "La dirección de donde viene el viento va de 0 a 360 grados.");
    cuerpo = {tipo: "viento_manual", datos: {vel_kmh: v, dir_desde: d % 360}};
    titulo = `Viento de ${num(v)} km/h del ${rumbo(d)} (${num(d % 360)}°)`;
  }
  ocupar(true);
  try { anotarRespuestas(titulo, await intervenir(cuerpo)); }
  catch (e) { $("error-intervenir").textContent = e.message; }
  finally { ocupar(false); }
  pintarTarjetas();
}

// ---- bitácora en la tarjeta
function tomarBitacora(c, d) {
  if (!d || !Array.isArray(d.bitacora)) return;
  if (FINALES.includes(d.estado)) c.bitacora = [...d.bitacora];
  else for (const e of d.bitacora) sumarEntrada(c, e);
  c.integra = d.bitacora_integra ?? null;
}
function sumarEntrada(c, e) {
  if (!e || !Number.isInteger(e.n) || c.bitacora.some(x => x.n === e.n)) return;
  c.bitacora.push(e);
  c.bitacora.sort((a, b) => a.n - b.n);
  c.integra = null;                                   // se vuelve a verificar con el próximo detalle
}

function textoCortafuego(p) {
  const recortado = p.estado === "recortada" || p._recortado;
  return `<span class="marca-cf${recortado ? " recortado" : ""}"></span>Cortafuego de ${num(p.ancho_m)} m${p.suelo_mineral ? ", a suelo mineral (supuesto)" : ""}` +
    ` · dibujado ${num(p.longitud_dibujada_m)} m` + (p.longitud_aplicada_m != null ? ` · aplicado ${num(p.longitud_aplicada_m)} m` : "") +
    (p.estado === "rechazada" ? ` · no se aplicó${p.motivo ? `: ${esc(p.motivo)}` : ""}` : recortado ? " · recortado" : "");
}
function textoVientoManual(e) {
  const d = e.datos || {};
  if (d.modo === "pronostico") return "Vuelve al viento del pronóstico";
  return `Viento a mano: ${num(d.vel_kmh)} km/h del ${rumbo(d.dir_desde)} (${num(d.dir_desde)}°)` + (d.pleno_min != null ? `; pleno desde la ${horaDe(d.pleno_min)}` : "");
}

function htmlBitacora(c) {
  const filas = [];
  for (const f of c.cortafuegos.filter(x => x.properties.origen === "inicial")) filas.push(["inicio", textoCortafuego(f.properties)]);
  for (const e of c.bitacora) {
    const cuando = horaDe(e.t_sim_min);
    if (e.tipo === "cortafuego") {
      const f = c.cortafuegos.find(x => x.properties.origen === "intervencion" && x.properties.n === e.n);
      filas.push([cuando, textoCortafuego({...(e.datos || {}), ...(f ? f.properties : {})})]);
    } else if (e.tipo === "viento_manual") filas.push([cuando, textoVientoManual(e)]);
    else if (e.tipo === "pausa") filas.push([cuando, "Pausa"]);
    else if (e.tipo === "detencion") filas.push([cuando, "Detenida"]);
  }
  if (!filas.length) return "";
  const MAX = 12, ocultas = Math.max(0, filas.length - MAX);
  const integra = c.integra === true ? '<span class="integra"> · cadena de hash verificada</span>'
    : c.integra === false ? '<span class="integra mal"> · la cadena de hash no verifica</span>' : "";
  return `<ul class="bitacora"><li><span class="cuando">Bitácora</span><span class="que">${c.bitacora.length} ${c.bitacora.length === 1 ? "entrada" : "entradas"}${integra}</span></li>` +
    (ocultas ? `<li><span class="cuando"></span><span class="que suave">… y ${ocultas} anteriores</span></li>` : "") +
    filas.slice(ocultas).map(([a, b]) => `<li><span class="cuando">${a}</span><span class="que">${b}</span></li>`).join("") + "</ul>";
}

function htmlReproduccion(r) {
  const sinAplicar = Array.isArray(r.sin_aplicar) ? r.sin_aplicar : [];
  if (r.cadena_igual && r.raiz_igual && r.original_integra && !sinAplicar.length)
    return `<p class="linea">Reproduce la corrida ${esc(r.de)}: misma configuración y la misma bitácora (${num(r.n)} entradas, hash por hash).</p>`;
  const por = [];
  if (r.original_integra === false) por.push(`la bitácora original no verifica (falla en la entrada ${r.original_primer_fallo ?? "?"})`);
  if (r.raiz_igual === false) por.push("la configuración inicial no coincide");
  if (!r.cadena_igual && r.primera_distinta != null) por.push(`las bitácoras se separan en la entrada ${r.primera_distinta} (${num(r.n_original)} en la original, ${num(r.n)} en esta)`);
  if (sinAplicar.length) por.push(`quedaron sin aplicar las entradas ${sinAplicar.join(", ")}`);
  return `<div class="aviso"><b>La reproducción de ${esc(r.de)} no salió igual.</b>${por.join("; ") || "Revisá el detalle en los resultados."}.</div>`;
}

async function reproducirCorrida(id, boton) {
  $("error-control").textContent = "";
  if (boton) boton.disabled = true;
  try {
    const r = await pedir(`/api/corridas/${encodeURIComponent(id)}/reproducir`, {iniciar: true});
    seguir(r.corridas, {motor: r.corridas[0].motor});
  } catch (e) { $("error-control").textContent = e.message; if (boton) boton.disabled = false; }
}

// ---- cortafuegos de la corrida en el mapa (cortafuegos.geojson). La parte recortada se dibuja de otro color: se estima con
// la huella a la hora de la intervención (lo que ya había quemado) y con el recuadro de la zona simulada.
async function refrescarCortafuegos(c) {
  const turno = c.turnoCf = (c.turnoCf || 0) + 1;
  let fc;
  try { fc = await pedir(`/api/corridas/${c.id}/cortafuegos.geojson`); } catch (e) { return; }
  if (!S.corridas.includes(c) || turno !== c.turnoCf) return;
  const figuras = fc.features || [];
  const capas = await capasDeCortafuegos(c, figuras);
  if (!S.corridas.includes(c) || turno !== c.turnoCf) return;
  c.cortafuegos = figuras;
  if (c.capaCf) c.capaCf.remove();
  c.capaCf = L.layerGroup(capas).addTo(S.mapa);
  pintarTarjetas(); dibujarLeyenda();
}

async function capasDeCortafuegos(c, figuras) {
  const bordes = [], lineas = [];
  for (const f of figuras) {
    const p = f.properties || {}, lls = (f.geometry?.coordinates || []).map(([lon, lat]) => L.latLng(lat, lon));
    if (lls.length < 2) continue;
    let tramos = [{r: false, pts: lls}];
    const recorte = p.estado === "recortada" || (p.celdas_recortadas || 0) > 0 || (p.enlaces_recortados || 0) > 0;
    if (recorte && c.limites) {
      const hora = p.origen === "intervencion" ? Math.round((Number(p.t_sim_min) || 0) / 60) : 0;
      const m = hora > 0 ? await mascara(c, hora) : null;
      tramos = partir(lls, q => { const u = enImagen(c.limites, q); return u.fuera || (m ? quemadoEn(m, u) : false); });
    }
    p._recortado = tramos.some(t => t.r);
    const texto = `${S.corridas.length > 1 ? `${MOTORES[c.motor]?.nombre || c.motor} · ` : ""}Cortafuego de ${num(p.ancho_m)} m` +
      ` · ${p.origen === "inicial" ? "desde el inicio" : `desde la ${horaDe(p.t_vigor_min ?? p.t_sim_min)}`}` +
      ` · dibujado ${num(p.longitud_dibujada_m)} m${p.longitud_aplicada_m != null ? ` · aplicado ${num(p.longitud_aplicada_m)} m` : ""}`;
    for (const t of tramos) {
      bordes.push(L.polyline(t.pts, {pane: "cortafuegos", color: "#fff", weight: 6, opacity: 0.85, interactive: false}));
      lineas.push(t.r ? L.polyline(t.pts, {pane: "cortafuegos", color: COLOR_RECORTE, weight: 3, dashArray: "4 5"}).bindTooltip(texto + " · tramo recortado (estimado con la huella)", {sticky: true})
                      : L.polyline(t.pts, {pane: "cortafuegos", color: COLOR_CF, weight: 3}).bindTooltip(texto, {sticky: true}));
    }
  }
  return bordes.concat(lineas);
}

function mascara(c, hora) {
  return c.mascaras[hora] ||= new Promise(resolver => {
    const img = new Image();
    img.onload = () => {
      const lienzo = document.createElement("canvas");
      lienzo.width = img.naturalWidth; lienzo.height = img.naturalHeight;
      const ctx = lienzo.getContext("2d", {willReadFrequently: true});
      ctx.drawImage(img, 0, 0);
      resolver({w: lienzo.width, h: lienzo.height, a: ctx.getImageData(0, 0, lienzo.width, lienzo.height).data});
    };
    img.onerror = () => { delete c.mascaras[hora]; resolver(null); };
    img.src = `/api/corridas/${c.id}/quemado.png?hora=${hora}&color=000000`;
  });
}

function enImagen(lim, q) {                           // la huella está en Web Mercator, estirada sobre `lim` (sur-oeste, norte-este)
  const P = ll => L.CRS.EPSG3857.project(ll);
  const no = P(L.latLng(lim[1][0], lim[0][1])), se = P(L.latLng(lim[0][0], lim[1][1])), p = P(q);
  const fx = (p.x - no.x) / (se.x - no.x), fy = (no.y - p.y) / (no.y - se.y);
  return {fx, fy, fuera: !(fx >= 0 && fx < 1 && fy >= 0 && fy < 1)};
}
const quemadoEn = (m, u) => !u.fuera && m.a[(Math.floor(u.fy * m.h) * m.w + Math.floor(u.fx * m.w)) * 4 + 3] > 0;

function partir(lls, recortado) {                     // tramos seguidos con el mismo estado, muestreando cada ~8 m
  const pts = [];
  for (let i = 0; i + 1 < lls.length; i++) {
    const a = lls[i], b = lls[i + 1], n = Math.min(400, Math.max(1, Math.ceil(a.distanceTo(b) / 8)));
    for (let k = 0; k < n; k++) pts.push(L.latLng(a.lat + (b.lat - a.lat) * k / n, a.lng + (b.lng - a.lng) * k / n));
  }
  pts.push(lls[lls.length - 1]);
  const tramos = [];
  let actual = null;
  for (let j = 0; j + 1 < pts.length; j++) {
    const medio = L.latLng((pts[j].lat + pts[j + 1].lat) / 2, (pts[j].lng + pts[j + 1].lng) / 2), r = !!recortado(medio);
    if (!actual || actual.r !== r) { actual = {r, pts: [pts[j]]}; tramos.push(actual); }
    actual.pts.push(pts[j + 1]);
  }
  return tramos;
}

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
    opciones.push(`<option value="${clave}">${cuando} · ${motor} · ${c.ultima_hora.h} h · ${num(c.ultima_hora.ha)} ha${c.reproduccion_de ? " · reproducción" : ""}</option>`);
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

// ---------------------------------------------------------------- zona de datos (fase F4)
// Cada pedido que baja o prepara datos lanza un trabajo en un proceso aparte, uno a la vez; se sigue por su canal de eventos.
const TAREAS = {pronostico: "Bajar el pronóstico", meteo_manual: "Cargar la meteorología (CSV)", escenario: "Armar el escenario",
                indices_aws: "Bajar los índices (AWS)", indices_gee: "Bajar los índices (Earth Engine)",
                indices_manual: "Cargar los índices (TIF)", evento: "Armar el evento en tiempo real"};
const ESTADOS_TRABAJO = {creado: "por empezar…", corriendo: "en marcha…", terminado: "listo", error: "con error", interrumpido: "interrumpido"};
const TRABAJO_FINAL = ["terminado", "error", "interrumpido"];
const MAX_CSV_MB = 20, MAX_TIF_MB = 60;

function prepararDatos() {
  $("b-pronostico").onclick = () => lanzar(() => pedir("/api/datos/meteo", {fuente: "pronostico"}));
  $("b-aws").onclick = () => lanzar(() => pedir("/api/datos/indices", {fuente: "aws"}));
  $("b-gee").onclick = () => lanzar(() => pedir("/api/datos/indices", {fuente: "gee"}));
  $("b-evento").onclick = armarEvento;
  $("b-csv").onclick = cargarCSV;
  $("b-tif").onclick = cargarTIF;
  $("b-escenario").onclick = armarEscenario;
  const ahora = aLocal(new Date(Math.ceil(Date.now() / 3600e3) * 3600e3).toISOString());
  $("esc-fecha").value = ahora.fecha; $("esc-hora").value = ahora.hora;
}

async function cargarDatos() {
  try { S.datos = await pedir("/api/datos"); }
  catch (e) { $("error-datos").textContent = "No se pudo leer el estado de los datos: " + e.message; return; }
  const t = S.datos.trabajo;
  if (t && (!S.trabajo || S.trabajo.id !== t.id)) {            // el mismo trabajo ya se sigue por su canal
    S.trabajo = t;
    if (!TRABAJO_FINAL.includes(t.estado)) seguirTrabajo(t);
  }
  pintarDatos();
}

function hace(horas) {
  if (horas == null) return "—";
  if (horas < 1) return "hace menos de 1 h";
  if (horas < 48) return `hace ${num(horas)} h`;
  return `hace ${num(horas / 24)} días`;
}

function pintarDatos() {
  const d = S.datos;
  if (!d) return;
  const a = d.antiguedad || {};
  $("datos-avisos").innerHTML = (d.avisos || []).length
    ? `<div class="aviso"><b>Para tener en cuenta</b><ul>${d.avisos.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";

  const pron = (d.meteo || []).find(t => String(t.id || "").endsWith("-pronostico"));
  $("datos-pronostico").innerHTML = pron
    ? `<dt>Toma</dt><dd>${aLocal(normalizarUTC(pron.hora_de_la_toma_utc || pron.creada_utc)).texto}</dd>` +
      `<dt>Modelo</dt><dd>${esc(pron.modelo || pron.fuente || "—")}</dd>` +
      `<dt>Cubre</dt><dd>${aLocal(pron.desde_utc).texto} a ${aLocal(pron.hasta_utc).texto}</dd>` +
      `<dt>Antigüedad</dt><dd class="${a.pronostico_horas > a.pronostico_viejo_horas ? "viejo" : ""}">${hace(a.pronostico_horas)}</dd>`
    : '<dd class="vacio">No hay ningún pronóstico guardado.</dd>';

  // Se muestra la toma con los datos más recientes (la misma que mide la antigüedad), no la última cargada.
  const ultimaDe = t => t.ultima_fecha || (t.ventana || [])[1] || "";
  const ind = [...(d.indices || [])].sort((x, y) => ultimaDe(y).localeCompare(ultimaDe(x)))[0];
  const ultima = ind ? ultimaDe(ind) : null;
  $("datos-indices").innerHTML = ind
    ? `<dt>Ventana</dt><dd>${fechaCorta((ind.ventana || [])[0])} a ${fechaCorta((ind.ventana || [])[1])}</dd>` +
      `<dt>Fuente</dt><dd>${esc(ind.rotulo || ind.fuente || "—")}</dd>` +
      (ind.n_escenas != null ? `<dt>Escenas</dt><dd>${num(ind.n_escenas)}${ultima ? ` · la última del ${fechaCorta(ultima)}` : ""}</dd>` : "") +
      (ind.celdas_sin_dato_pct ? `<dt>Celdas sin dato</dt><dd>${num(ind.celdas_sin_dato_pct, 1)} %</dd>` : "") +
      `<dt>Antigüedad</dt><dd class="${a.indices_dias > a.indices_viejos_dias ? "viejo" : ""}">${a.indices_dias == null ? "—" : a.indices_dias === 0 ? "de hoy" : a.indices_dias === 1 ? "de ayer" : `${num(a.indices_dias)} días`}</dd>`
    : '<dd class="vacio">No hay índices guardados.</dd>';
  $("en-prueba").hidden = !(ind && ind.via === "aws" && ind.en_prueba);
  const gee = d.gee || {};
  $("nota-gee").hidden = !!gee.disponible;
  $("nota-gee").textContent = gee.disponible ? "" : `Earth Engine no está disponible: ${gee.motivo || "sin credenciales"}.`;
  $("b-gee").title = gee.disponible ? "" : `No disponible: ${gee.motivo || "sin credenciales"}`;

  const nuevo = (lista, que) => lista.length ? `<option value="">La más nueva (${esc(etiquetaToma(lista[0], que))})</option>` : `<option value="">No hay tomas de ${que}</option>`;
  for (const [id, lista, que] of [["sel-meteo", d.meteo || [], "meteorología"], ["sel-indices", d.indices || [], "índices"]]) {
    const antes = $(id).value;
    $(id).innerHTML = nuevo(lista, que) + lista.map(t => `<option value="${esc(t.id)}">${esc(etiquetaToma(t, que))}</option>`).join("");
    if (lista.some(t => t.id === antes)) $(id).value = antes;
  }
  pintarTrabajo();
}

function etiquetaToma(t, que) {
  if (que === "índices") {
    const v = t.ventana || [];
    return `${t.rotulo || t.fuente || t.id} · ${fechaCorta(v[0])} a ${fechaCorta(v[1])}`;
  }
  return `${t.rotulo || t.fuente || t.id} · ${t.desde_utc ? aLocal(t.desde_utc).texto.slice(0, 10) + " a " + aLocal(t.hasta_utc).texto.slice(0, 10) : ""} · tomada ${aLocal(normalizarUTC(t.creada_utc)).texto}`;
}

function enMarcha() { return S.ocupado || (S.trabajo && !TRABAJO_FINAL.includes(S.trabajo.estado)); }

function pintarTrabajo() {
  const t = S.trabajo, ocupado = enMarcha(), d = S.datos || {};
  for (const b of document.querySelectorAll("#sec-datos button.lanza")) b.disabled = ocupado;
  if (!d.gee?.disponible) $("b-gee").disabled = true;
  if (!(d.meteo || []).length || !(d.indices || []).length) $("b-evento").disabled = true;
  $("b-evento").title = $("b-evento").disabled && !ocupado ? "Hace falta al menos una toma de meteorología y una de índices" : "";
  $("trabajo").hidden = !t;
  if (!t) return;
  $("trabajo-nombre").textContent = TAREAS[t.tarea] || t.tarea;
  $("trabajo-estado").textContent = ESTADOS_TRABAJO[t.estado] || t.estado;
  const p = t.progreso, barra = $("trabajo-barra");
  const corre = !TRABAJO_FINAL.includes(t.estado);
  barra.classList.toggle("indefinida", corre && !(p && p.total > 0));
  barra.style.width = !corre ? (t.estado === "terminado" ? "100%" : "0") : p && p.total > 0 ? `${Math.min(100, p.hechos / p.total * 100)}%` : "";
  let texto = "";
  if (corre) texto = p ? `${p.texto || ""}${p.total > 0 ? ` (${num(p.hechos)} de ${num(p.total)})` : ""}${p.s != null ? ` · ${num(p.s)} s` : ""}` : "Arrancando el proceso de datos…";
  else if (t.estado === "terminado") texto = resumenResultado(t);
  else if (t.terminado_utc) texto = `Terminó el ${aLocal(normalizarUTC(t.terminado_utc)).texto}.`;
  $("trabajo-texto").textContent = texto;
  $("trabajo-error").textContent = t.estado === "error" || t.estado === "interrumpido" ? (t.error || "El trabajo no terminó bien.") : "";
  pintarSinRed(t);
}

function resumenResultado(t) {
  const r = t.resultado || {}, cuando = t.terminado_utc ? ` el ${aLocal(normalizarUTC(t.terminado_utc)).texto}` : "";
  if (t.tarea === "evento") return `Evento ${r.id || ""} armado${cuando}. Ya se puede elegir en «Configurar».`;
  if (t.tarea.startsWith("indices")) return `Toma ${r.id || ""} guardada${cuando}${r.n_escenas != null ? `, con ${num(r.n_escenas)} escenas` : ""}.`;
  return `Toma ${r.id || ""} guardada${cuando}${r.horas ? `, ${num(r.horas)} horas` : ""}.`;
}

// Sin red: si la descarga falla y no hay ninguna toma de ese tipo guardada, se dice claro qué queda por hacer.
function pintarSinRed(t) {
  const caja = $("trabajo-sin-red"), d = S.datos || {};
  const bajada = ["pronostico", "indices_aws", "indices_gee"].includes(t.tarea);
  const sinTomas = t.tarea === "pronostico" ? !(d.meteo || []).length : !(d.indices || []).length;
  caja.hidden = !(bajada && t.estado === "error" && sinTomas);
  if (caja.hidden) return;
  caja.className = "aviso sin-red";
  caja.innerHTML = `<b>No se pudo bajar ${t.tarea === "pronostico" ? "el pronóstico" : "los índices"} y no hay nada guardado.</b>` +
    `Puede ser que la computadora no tenga internet. Podés ${t.tarea === "pronostico" ? "cargar un CSV de meteorología o armar un escenario" : "cargar los TIF de NDVI y NDMI"} (abajo, en «Cargar datos a mano» y «Modo escenario»), o simular con un evento de EJEMPLO, que no necesita red.` +
    `<br><button id="usar-ejemplo">Usar un ejemplo</button>`;
  $("usar-ejemplo").onclick = usarEjemplo;
}

function usarEjemplo() {
  if (S.modo !== "configurar") return;
  const ejemplo = S.estado.eventos_base.find(e => e.id === "SL-2024-LASLAGUNAS") || S.estado.eventos_base.find(e => !e.tiempo_real);
  if (!ejemplo) return;
  $("evento").value = ejemplo.id; proponerEvento(); cargarCapas();
  $("sec-config").scrollIntoView({behavior: "smooth", block: "start"});
}

// Lanza un trabajo: `hacer` hace el pedido y devuelve {trabajo}. Un solo trabajo a la vez (el servidor contesta 409 si no).
async function lanzar(hacer, siempre) {
  if (enMarcha()) return;
  $("error-datos").textContent = "";
  S.ocupado = true; pintarTrabajo();
  try {
    const r = await hacer();
    S.trabajo = r.trabajo;
    seguirTrabajo(r.trabajo);
    if (siempre) siempre();
  } catch (e) {
    $("error-datos").textContent = e.message;
  } finally {
    S.ocupado = false; pintarTrabajo();
  }
}

function seguirTrabajo(t) {
  if (S.canalTrabajo) S.canalTrabajo.close();
  const canal = S.canalTrabajo = new EventSource(`/api/datos/trabajos/${encodeURIComponent(t.id)}/eventos`);
  const cerrar = async () => {
    canal.close();
    if (S.canalTrabajo === canal) S.canalTrabajo = null;
    try { S.trabajo = await pedir(`/api/datos/trabajos/${encodeURIComponent(t.id)}`); } catch (e) { /* queda lo que llegó por el canal */ }
    await alTerminarTrabajo(S.trabajo);
  };
  canal.onmessage = m => {
    const e = JSON.parse(m.data);
    if (!S.trabajo || S.trabajo.id !== t.id) return;
    if (e.aviso === "estado") S.trabajo.estado = e.estado;
    else if (e.aviso === "progreso") S.trabajo.progreso = {hechos: e.hechos, total: e.total, texto: e.texto, s: e.s};
    else if (e.aviso === "final") S.trabajo.resultado = e.resultado;
    else if (e.aviso === "error") S.trabajo.error = e.mensaje;
    pintarTrabajo();
  };
  canal.addEventListener("cierre", cerrar);
  canal.onerror = () => { if (S.trabajo && TRABAJO_FINAL.includes(S.trabajo.estado)) cerrar(); };
}

async function alTerminarTrabajo(t) {
  if (!t) return;
  await cargarDatos();
  if (t.estado !== "terminado") return;
  const id = t.resultado?.id;
  if (t.tarea === "evento") {
    try { await refrescarEventos(S.modo === "configurar" ? id : undefined); } catch (e) { $("error-datos").textContent = e.message; }
  } else if (id && ["meteo_manual", "escenario"].includes(t.tarea)) $("sel-meteo").value = id;    // lista para armar el evento
  else if (id && t.tarea === "indices_manual") $("sel-indices").value = id;
}

function armarEvento() {
  const cuerpo = {};
  if ($("sel-meteo").value) cuerpo.meteo = $("sel-meteo").value;
  if ($("sel-indices").value) cuerpo.indices = $("sel-indices").value;
  if ($("nombre-rt").value.trim()) cuerpo.nombre = $("nombre-rt").value.trim();
  lanzar(() => pedir("/api/datos/evento", cuerpo), () => { $("nombre-rt").value = ""; });
}

function cargarCSV() {
  const f = $("archivo-csv").files[0];
  if (!f) return void ($("error-datos").textContent = "Elegí el archivo CSV de meteorología.");
  if (f.size > MAX_CSV_MB * 1048576) return void ($("error-datos").textContent = `El CSV pasa el máximo de ${MAX_CSV_MB} MB.`);
  lanzar(() => subir(`/api/datos/meteo/archivo?nombre=${encodeURIComponent(f.name)}`, f), () => { $("archivo-csv").value = ""; });
}

function cargarTIF() {
  const ndvi = $("archivo-ndvi").files[0], ndmi = $("archivo-ndmi").files[0];
  const d1 = $("ventana-desde").value, d2 = $("ventana-hasta").value;
  const falta = (!ndvi ? ["el TIF de NDVI"] : []).concat(!ndmi ? ["el TIF de NDMI"] : [], !d1 || !d2 ? ["las dos fechas de la ventana"] : []);
  if (falta.length) return void ($("error-datos").textContent = `Falta ${falta.join(", ")}.`);
  if (d2 < d1) return void ($("error-datos").textContent = "La ventana termina antes de empezar.");
  for (const f of [ndvi, ndmi]) if (f.size > MAX_TIF_MB * 1048576) return void ($("error-datos").textContent = `${f.name} pasa el máximo de ${MAX_TIF_MB} MB.`);
  lanzar(async () => {
    $("trabajo-texto").textContent = "Subiendo los archivos…";
    await subir(`/api/datos/indices/archivo?banda=ndvi&nombre=${encodeURIComponent(ndvi.name)}`, ndvi);
    await subir(`/api/datos/indices/archivo?banda=ndmi&nombre=${encodeURIComponent(ndmi.name)}`, ndmi);
    return pedir("/api/datos/indices/manual", {ventana: [d1, d2], ndmi_nir: $("ndmi-nir").value, descripcion: $("descripcion-tif").value.trim()});
  }, () => { $("archivo-ndvi").value = $("archivo-ndmi").value = ""; });
}

function armarEscenario() {
  const v = id => Number($(id).value);
  const campos = [["esc-horas", "Horas", 1, 240], ["esc-temp", "Temperatura", -40, 50], ["esc-hr", "Humedad", 0, 100],
                  ["esc-viento", "Viento", 0, 216], ["esc-dir", "Dirección", 0, 360], ["esc-lluvia", "Lluvia", 0, 200]];
  if (!$("esc-fecha").value || !$("esc-hora").value) return void ($("error-datos").textContent = "Falta el día o la hora de inicio del escenario.");
  for (const [id, nombre, a, b] of campos) {
    if ($(id).value === "" || !(v(id) >= a && v(id) <= b)) return void ($("error-datos").textContent = `${nombre}: un valor de ${a} a ${b}.`);
  }
  const cuerpo = {desde_utc: aUTC($("esc-fecha").value, $("esc-hora").value), horas: Math.round(v("esc-horas")), temp_c: v("esc-temp"),
                  hr_pct: v("esc-hr"), viento_kmh: v("esc-viento"), viento_dir_deg: v("esc-dir"), precip_mm: v("esc-lluvia")};
  lanzar(() => pedir("/api/datos/meteo/escenario", cuerpo));
}

arrancar().catch(e => { $("error").textContent = "No se pudo hablar con el servidor: " + e.message; });
