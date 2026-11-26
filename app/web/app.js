/* Pantalla del simulador (fases F3 a F6). Habla con el servidor local por los pedidos de docs/etapa3/contrato_servidor_motor.md §4.
   Bibliotecas: Leaflet (app/web/vendor/leaflet) y Bootstrap 5.3.3 (CDN, o vendor/bootstrap sin internet). Si Bootstrap no
   carga, la pantalla sigue andando: las secciones se abren y cierran con el código de `seccion` y los (i) muestran su texto
   como sugerencia del navegador. */
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
const S = {estado: null, mapa: null, capas: {}, enMapa: {}, focos: [], usados: [], corridas: [], pedido: null,
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
// Textos para el usuario sin el detalle interno del proyecto: se sacan los códigos de decisiones y prerregistros
// (D-E3-…, E-E3-…) y las aclaraciones «en prueba» de la vía AWS. Los datos guardados no cambian (la procedencia los conserva).
const limpiar = t => String(t ?? "")
  .replace(/\s*\([^()]*(?:en prueba|\b[DE]-E3-\d+)[^()]*\)/gi, "")
  .replace(/\s*[,;:]?\s*\b[DE]-E3-\d+\b(?:,\s*punto\s*\d+)?/g, "").replace(/\s{2,}/g, " ").trim();
const avisoInterno = t => /en prueba/i.test(String(t ?? ""));                          // avisos de la vía AWS en prueba
const avisosVisibles = lista => (lista || []).filter(a => !avisoInterno(a)).map(limpiar).filter(Boolean);
const ev = () => S.estado.eventos_base.find(e => e.id === $("evento").value);

// ---------------------------------------------------------------- secciones del panel (acordeón)
// Cada sección abre siempre igual al cargar la página (no se recuerda lo que el usuario abrió o cerró). Con Bootstrap se usa
// su Collapse; sin Bootstrap (sin internet y sin la copia local), se cambia la clase a mano.
function seccion(id, abrir) {
  const el = $(id);
  if (!el) return;
  if (window.bootstrap?.Collapse) bootstrap.Collapse.getOrCreateInstance(el, {toggle: false})[abrir ? "show" : "hide"]();
  else el.classList.toggle("show", abrir);
  for (const b of document.querySelectorAll(`[data-bs-target="#${id}"]`)) { b.classList.toggle("collapsed", !abrir); b.setAttribute("aria-expanded", String(abrir)); }
}
const ABIERTAS_AL_INICIO = {"c-datos": true, "c-config": true, "c-capas": true,
                            "c-anteriores": false, "c-historico": false};
function seccionesIniciales() {
  for (const [id, abrir] of Object.entries(ABIERTAS_AL_INICIO)) seccion(id, abrir);
  $("avanzadas").open = false;
  elegirOrigen("actuales");
}
function prepararPanel() {
  if (!window.bootstrap) {
    for (const b of document.querySelectorAll('[data-bs-toggle="collapse"]')) {
      const id = b.dataset.bsTarget.slice(1);
      b.addEventListener("click", () => seccion(id, !$(id).classList.contains("show")));
    }
  } else {
    for (const e of document.querySelectorAll('[data-bs-toggle="popover"]')) {
      const texto = e.getAttribute("title");
      e.removeAttribute("title");
      new bootstrap.Popover(e, {content: texto, trigger: "hover focus", placement: "right", container: "body"});
    }
  }
}

// ---------------------------------------------------------------- arranque
async function arrancar() {
  S.estado = await pedir("/api/estado");
  $("version").textContent = `Programa ${S.estado.programa.version} · motores congelados ${String(S.estado.congelado_sha256).slice(0, 8)}…`;
  // El motor simulado (de prueba) no se ofrece en la pantalla, aunque el servidor lo tenga habilitado (--con-simulado).
  $("motor").innerHTML = S.estado.motores.filter(m => m.id !== "simulado")
    .map(m => `<option value="${m.id}">${MOTORES[m.id]?.largo || m.id}</option>`).join("");
  llenarEventos();

  const [[sur, oeste], [norte, este]] = S.estado.dominio.limites;
  // Sin el recuadro de fuentes dentro del mapa: los créditos están al pie del panel (index.html, «Fuentes de los datos»).
  S.mapa = L.map("mapa", {zoomSnap: 0.25, minZoom: 9, maxZoom: 16, attributionControl: false,
                         maxBounds: [[sur - 0.4, oeste - 0.5], [norte + 0.4, este + 0.5]]});
  for (const [nombre, z] of [["fondo", 200], ["tematica", 250], ["huella", 380], ["vectores", 420], ["viento", 425]]) {
    S.mapa.createPane(nombre).style.zIndex = z;
  }
  S.mapa.fitBounds([[sur, oeste], [norte, este]]);
  for (const [nombre, z] of [["linea", 385], ["cortafuegos", 430], ["trazos", 440]]) S.mapa.createPane(nombre).style.zIndex = z;
  S.mapa.on("click", e => { if (S.modo === "configurar" && !T.modo) agregarFoco(e.latlng.lat, e.latlng.lng); });
  for (const id of ["hora", "esc-hora"]) $(id).innerHTML = Array.from({length: 24}, (_, h) => `<option value="${dos(h)}:00">${dos(h)}:00</option>`).join("");

  $("evento").onchange = () => { proponerEvento(); cargarCapas(); };
  $("borrar-rt").onclick = borrarRT;
  prepararPanel();
  prepararDatos();
  prepararFocos();
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
  $("tarjetas").addEventListener("change", e => {
    const caja = e.target.closest("[data-ver]");
    const c = caja && S.corridas.find(x => x.id === caja.dataset.ver);
    if (c) { c.visible = caja.checked; mostrarCorrida(c); }
  });
  $("ver-viento").onchange = () => { S.verViento = $("ver-viento").checked; for (const c of S.corridas) actualizarViento(c); pintarViento(); };
  prepararCapaViento();
  prepararTrazos();
  prepararViento();
  prepararBomberos();
  prepararDescargas();
  prepararHistorico();

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
    `<optgroup label="Tiempo real">${rt.length ? rt.map(e => `<option value="${esc(e.id)}">${esc(cuandoRT(e))} · ${esc(limpiar(e.nombre) || e.id)}</option>`).join("")
      : '<option value="" disabled>Todavía no hay: armalo en «Datos»</option>'}</optgroup>` +
    `<optgroup label="Ejemplos (incendios históricos con ficha)">${ejemplos.map(e => `<option value="${esc(e.id)}">EJEMPLO · ${esc(limpiar(e.nombre) || e.id)}</option>`).join("")}</optgroup>`;
  const lagunas = ejemplos.find(e => e.id === "SL-2024-LASLAGUNAS");
  const elegido = todos.find(e => e.id === antes) || rt[0] || lagunas || ejemplos[0];
  if (elegido) $("evento").value = elegido.id;
}

// Cuándo se bajaron los datos de un evento de tiempo real (hora argentina). Si la meteorología es un CSV o un escenario no
// hubo descarga: se dice cuándo se armó el evento.
function cuandoRT(e) {
  if (e.descargado_utc) return `Descargado ${aLocal(normalizarUTC(e.descargado_utc)).texto}`;
  return e.creado_utc ? `Armado ${aLocal(normalizarUTC(e.creado_utc)).texto}` : e.id;
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
  const rotulos = (e.rotulos || []).map(limpiar).filter(Boolean);
  $("rotulos-evento").innerHTML = (e.tiempo_real ? '<span class="badge text-bg-info rotulo">tiempo real</span>' : "") +
    rotulos.map(r => `<span class="badge rotulo ${r === "EJEMPLO" || /escenario|mano/i.test(r) ? "text-bg-warning" : "text-bg-light border"}">${esc(r)}</span>`).join("");
  const avisos = avisosVisibles(e.avisos).filter(a => !(rotulos.includes("EJEMPLO") && /^EJEMPLO/.test(a)));
  if (!e.tiempo_real) avisos.unshift("Es un ejemplo: el tiempo y la vegetación son los de un incendio histórico, no los de hoy.");
  $("avisos-evento").innerHTML = avisos.length ? `<div class="alert alert-warning aviso">${avisos.length > 1 ? `<ul>${avisos.map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : esc(avisos[0])}</div>` : "";
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
      (e.tiempo_real ? " Este evento no trae focos de ignición: marcalos con clics en el mapa." : "");
  } else $("nota-evento").textContent = "";
  ponerFocos(e.ignicion_de_la_ficha || []);
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

// ---------------------------------------------------------------- focos de ignición
// Cada clic en el mapa agrega un foco (hasta MAX_FOCOS); cada uno se puede arrastrar o quitar de la lista. Van todos en
// `ignicion: [...]` del pedido, y los dos motores encienden todos (test/app/test_procesos.py, varios focos).
const MAX_FOCOS = 10;
const dentroDelDominio = (lat, lon) => { const [[sur, oeste], [norte, este]] = S.estado.dominio.limites; return lat >= sur && lat <= norte && lon >= oeste && lon <= este; };

function prepararFocos() {
  $("b-agregar-foco").onclick = () => {
    const lat = Number(String($("lat").value).replace(",", ".")), lon = Number(String($("lon").value).replace(",", "."));
    if ($("lat").value === "" || $("lon").value === "" || !Number.isFinite(lat) || !Number.isFinite(lon))
      return void ($("error").textContent = "Escribí la latitud y la longitud en grados (por ejemplo −32,64 y −65,55).");
    if (agregarFoco(lat, lon)) $("lat").value = $("lon").value = "";
  };
  $("b-quitar-focos").onclick = () => ponerFocos([]);
  $("lista-focos").addEventListener("click", e => { const b = e.target.closest("[data-quitar-foco]"); if (b) quitarFoco(Number(b.dataset.quitarFoco)); });
}

function agregarFoco(lat, lon, sinAviso) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
  if (!dentroDelDominio(lat, lon)) { if (!sinAviso) $("error").textContent = "Ese punto cae fuera del dominio."; return false; }
  if (S.focos.length >= MAX_FOCOS) { if (!sinAviso) $("error").textContent = `Se pueden marcar hasta ${MAX_FOCOS} focos.`; return false; }
  $("error").textContent = "";
  const f = {lat, lon, marcador: null};
  f.marcador = L.marker([lat, lon], {draggable: S.modo === "configurar", zIndexOffset: 1000, icon: iconoFoco(S.focos.length + 1)}).addTo(S.mapa);
  f.marcador.bindTooltip(() => `Foco ${S.focos.indexOf(f) + 1}${S.modo === "configurar" ? " · arrastralo para moverlo" : ""}`);
  f.marcador.on("dragend", () => {
    const p = f.marcador.getLatLng();
    if (dentroDelDominio(p.lat, p.lng)) { f.lat = p.lat; f.lon = p.lng; $("error").textContent = ""; }
    else { f.marcador.setLatLng([f.lat, f.lon]); $("error").textContent = "Ese punto cae fuera del dominio."; }
    pintarFocosIgnicion();
  });
  S.focos.push(f);
  pintarFocosIgnicion();
  return true;
}
const iconoFoco = n => L.divIcon({className: "", html: `<div class="punto-ignicion">${n}</div>`, iconSize: [22, 22], iconAnchor: [11, 11]});

function quitarFoco(i) {
  const f = S.focos[i];
  if (!f || S.modo !== "configurar") return;
  f.marcador.remove();
  S.focos.splice(i, 1);
  pintarFocosIgnicion();
}
function ponerFocos(puntos) {
  for (const f of S.focos) f.marcador.remove();
  S.focos = [];
  for (const p of puntos || []) agregarFoco(Number(p.lat), Number(p.lon), true);
  pintarFocosIgnicion();
}
function arrastrarFocos(si) { for (const f of S.focos) si ? f.marcador.dragging?.enable() : f.marcador.dragging?.disable(); }

function pintarFocosIgnicion() {
  S.focos.forEach((f, i) => f.marcador.setIcon(iconoFoco(i + 1)));
  const editable = S.modo === "configurar";
  $("lista-focos").innerHTML = S.focos.map((f, i) =>
    `<li class="list-group-item d-flex align-items-center gap-2 py-1"><span class="me-auto font-monospace">${num(f.lat, 5)}, ${num(f.lon, 5)}</span>` +
    (editable ? `<button type="button" class="btn-close" data-quitar-foco="${i}" aria-label="Quitar el foco ${i + 1}" title="Quitar este foco"></button>` : "") + "</li>").join("");
  $("lista-focos").hidden = !S.focos.length;
  $("b-quitar-focos").hidden = !editable || S.focos.length < 2;
  $("nota-focos").textContent = !S.focos.length ? "Marcá al menos un foco con un clic en el mapa."
    : S.focos.length >= MAX_FOCOS ? `Llegaste al máximo de ${MAX_FOCOS} focos.` : "";
  cargarCuarteles();                                                 // la llegada estimada de los bomberos sale de los focos
}

// ---------------------------------------------------------------- capas de fondo
const ESTILO_VECTOR = {
  dominio: () => ({color: "#3a3833", weight: 1.5, dashArray: "6 5", fill: false}),
  caminos: f => { const c = f.properties.clase; const fuerte = c === "ruta" || c === "autopista"; return {color: fuerte ? "#4a4741" : "#7d7a72", weight: fuerte ? 2 : 1, opacity: fuerte ? 0.95 : 0.75}; },
  red_mt: () => ({color: "#7a3ea8", weight: 1, opacity: 0.8, dashArray: "5 4"}),
};
const ENCENDIDAS = ["relieve", "dominio", "cobertura", "caminos"];       // al abrir; las demás, apagadas

async function cargarCapas() {
  const {capas} = await pedir(`/api/capas?evento=${encodeURIComponent($("evento").value)}`);
  const antes = new Set(Object.keys(S.enMapa));
  for (const id of antes) if (S.capas[id]?.por_evento) apagarCapa(id);            // las del evento anterior se sacan
  S.capas = Object.fromEntries(capas.map(c => [c.id, c]));
  const grupos = {};
  for (const c of capas) (grupos[c.grupo] ||= []).push(c);
  $("capas").innerHTML = Object.entries(grupos).map(([g, lista]) =>
    `<div class="grupo-capas"><div class="small text-body-secondary mt-2 mb-1">${g}</div>${lista.map(c => `<label class="form-check small mb-1"><input class="form-check-input" type="checkbox" data-capa="${c.id}"> ${c.titulo}</label>`).join("")}</div>`).join("");
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
  const vistas = S.corridas.filter(c => c.capa && c.visible);
  if (vistas.length) {
    const conRampa = vistas.filter(c => !c.plano), planas = vistas.filter(c => c.plano);
    let h = "<h3>Área quemada simulada</h3>";
    if (conRampa.length) h += `<div class="rampa" style="background:linear-gradient(90deg,#ffeda0,#feb24c,#f03b20,#800026)"></div><div class="extremos"><span>ardió primero</span><span>ardió último</span></div>${S.corridas.length > 1 ? `<div class="item">${MOTORES[conRampa[0].motor].nombre}</div>` : ""}`;
    for (const c of planas) h += `<div class="item"><i style="background:${c.color};opacity:.55"></i>${MOTORES[c.motor].nombre}</div>`;
    bloques.push(h);
  }
  const bv = bloqueLeyendaViento();
  if (bv) bloques.push(bv);
  const conCf = S.corridas.some(c => c.cortafuegos.length), recortes = S.corridas.some(c => c.cortafuegos.some(f => f.properties._recortado));
  if (conCf || T.borradores.length) {
    bloques.push("<h3>Cortafuegos</h3>" + (conCf ? '<div class="item"><span class="linea-cf"></span>aplicado</div>' : "") +
      (recortes ? '<div class="item"><span class="linea-cf recortado"></span>recortado (ya quemado o fuera de la zona simulada)</div>' : "") +
      (T.borradores.length ? '<div class="item"><span class="linea-cf borrador"></span>dibujado, sin enviar</div>' : ""));
  }
  if (S.corridas.some(c => c.capaLinea && c.visible) || D.borradores.length) {
    const hay = p => D.borradores.some(b => b.producto === p) || S.corridas.some(c => (c.descargas || []).some(f => f.properties.producto === p));
    bloques.push(`<h3>Combate</h3><div class="item"><i style="background:${COLOR_LINEA}"></i>línea de los bomberos</div>` +
      (hay("agua") ? `<div class="item"><i style="background:${COLOR_PRODUCTO.agua}"></i>agua de una descarga (se seca)</div>` : "") +
      (hay("retardante") ? `<div class="item"><i style="background:${COLOR_PRODUCTO.retardante}"></i>retardante</div>` : ""));
  }
  for (const id of Object.keys(S.enMapa)) {
    const c = S.capas[id], l = c?.leyenda;
    if (!l) continue;
    if (l.tipo === "categorica") bloques.push(`<h3>${c.titulo}</h3>` + l.items.map(i => `<div class="item"><i style="background:${i.color}"></i>${esc(i.nombre)}</div>`).join("") +
      (l.nota ? `<div class="nota-leyenda ms-0">${esc(l.nota)}</div>` : ""));
    else {
      const p = l.paradas, a = p[0].valor, b = p[p.length - 1].valor;
      const grad = p.map(x => `${x.color} ${((x.valor - a) / (b - a) * 100).toFixed(0)}%`).join(",");
      bloques.push(`<h3>${c.titulo}</h3><div class="rampa" style="background:linear-gradient(90deg,${grad})"></div><div class="extremos"><span>${num(a, 1)}</span><span>${num(b, 1)} ${l.unidad || ""}</span></div>`);
    }
  }
  bloques.push(...bloquesLeyendaHistorico());
  $("leyenda").hidden = !bloques.length;
  $("leyenda").innerHTML = bloques.map(b => `<div class="bloque">${b}</div>`).join("");
}

// ---------------------------------------------------------------- lanzar y seguir
async function iniciar() {
  $("error").textContent = "";
  const horas = Number($("horas").value);
  const e = ev();
  if (!e) return void ($("error").textContent = "Elegí los datos del terreno y del tiempo.");
  if (!S.focos.length) return void ($("error").textContent = e.tiempo_real
    ? "Este evento de tiempo real no trae focos de ignición: marcá al menos uno con un clic en el mapa." : "Marcá al menos un foco de ignición con un clic en el mapa.");
  if (!$("fecha").value || !$("hora").value) return void ($("error").textContent = "Falta el día o la hora de inicio.");
  if (!(horas >= 1 && horas <= 240)) return void ($("error").textContent = "Las horas a simular van de 1 a 240.");
  if (e.meteo_desde_utc && e.meteo_hasta_utc) {
    const t = new Date(aUTC($("fecha").value, $("hora").value)).getTime();
    if (t < new Date(e.meteo_desde_utc).getTime() || t >= new Date(e.meteo_hasta_utc).getTime())
      return void ($("error").textContent = `La hora de inicio cae fuera de los datos del tiempo (del ${aLocal(e.meteo_desde_utc).texto} al ${aLocal(e.meteo_hasta_utc).texto}).`);
  }
  const pedido = {motor: $("motor").value, evento: $("evento").value, horas, iniciar: true,
                  ignicion: S.focos.map(f => ({lat: Number(f.lat.toFixed(6)), lon: Number(f.lon.toFixed(6))})),
                  t_inicio_utc: aUTC($("fecha").value, $("hora").value)};
  if (T.borradores.length) pedido.cortafuegos = T.borradores.map(cuerpoTrazo);
  if (B.iniciales.length) pedido.dotaciones = B.iniciales.map(d => ({...d}));
  $("iniciar").disabled = true;
  try {
    const r = await pedir("/api/corridas", pedido);
    S.pedido = pedido;
    B.iniciales = [];
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
                                         bitacora: [], integra: null, cortafuegos: [], capaCf: null, mascaras: {},
                                         combate: [], capaLinea: null, urlLinea: null, vLinea: 0, descargas: [], capaDescargas: null,
                                         visible: true, viento: null, vientos: {}, sinViento: false, pidiendoViento: null}));
  const otros = ["#159e8a", "#7c3aed"];                    // v3.1 libre y librev2 comparten color: si van juntas, otro
  S.corridas.forEach((c, i) => { if (S.corridas.slice(0, i).some(x => x.color === c.color)) c.color = otros.shift() || c.color; });
  arrastrarFocos(false); pintarFocosIgnicion();
  vaciarBorradores(); ponerHerramienta("pausa");
  $("respuestas").innerHTML = ""; $("error-intervenir").textContent = ""; $("pausar-en").value = "";
  panelEnCorrida(true);
  const p = S.corridas[0].pedido, ign = p.ignicion || [];
  const hist = p.historico;
  $("resumen-config").innerHTML = `<b>${MOTORES[pedido.motor || p.motor]?.largo || S.corridas.map(c => MOTORES[c.motor]?.nombre || c.motor).join(" · ")}</b><br>` +
    `${esc(limpiar((S.estado.eventos_base.find(e => e.id === p.evento) || {}).nombre) || p.evento || "sin evento")}<br>` +
    (hist ? `Modo histórico: ignición ${esc(hist.ignicion)}, hipótesis ${esc(hist.hipotesis)}${esX49({rol: hist.rol}) ? " · <b>evento no visto (X-49): solo para mostrar</b>" : ""}<br>` : "") +
    (ign.length === 1 ? `Ignición en ${num(ign[0].lat, 4)}, ${num(ign[0].lon, 4)}<br>`
      : ign.length > 1 ? `${ign.length} focos de ignición: ${ign.map((x, i) => `${i + 1}) ${num(x.lat, 4)}, ${num(x.lon, 4)}`).join(" · ")}<br>` : "") +
    ((p.t_inicio_utc || hist?.t_inicio_utc) ? `Inicio: ${aLocal(p.t_inicio_utc || hist.t_inicio_utc).texto} (hora argentina)<br>` : "") + `Duración pedida: ${num(horasDe(p))} h` +
    ((p.cortafuegos || []).length ? `<br>Cortafuegos desde el inicio: ${p.cortafuegos.length}` : "") +
    ((p.dotaciones || []).length ? `<br>Bomberos despachados desde el inicio: ${num(p.dotaciones.reduce((s, d) => s + (d.bomberos || 0), 0))}` : "") +
    (S.corridas[0].reproduccionDe ? `<br><b>Reproducción</b> de la corrida ${esc(S.corridas[0].reproduccionDe)}: aplica su bitácora, sin intervenciones nuevas` : "");
  for (const c of S.corridas) { escuchar(c); vigilarMetricas(c); }
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
      pedir(`/api/corridas/${c.id}`).then(d => { c.limites = d.huella?.limites; tomarBitacora(c, d); actualizarHuella(c); actualizarLinea(c); refrescarCortafuegos(c); refrescarDescargas(c); pintarTodo(); });
    }
    else if (AVISOS_BITACORA.includes(e.aviso)) {
      if (e.entrada) sumarEntrada(c, e.entrada);
      if (e.aviso === "intervencion" && e.entrada?.tipo === "cortafuego") refrescarCortafuegos(c);
      if (e.aviso === "intervencion" && TIPOS_COMBATE.includes(e.entrada?.tipo)) { c.vLinea++; actualizarLinea(c); }
      if (e.aviso === "intervencion" && e.entrada?.tipo === "descarga") refrescarDescargas(c);
    }
    else if (e.aviso === "combate") { c.combate[e.h] = e; c.vLinea++; actualizarLinea(c); }
    else if (e.aviso === "hora") {
      c.horas[e.h] = {h: e.h, ha: e.ha, activas: e.activas, s: e.s_computo, meteo: e.meteo, exposicion: e.exposicion};
      if (S.enVivo) S.horaVista = horaMaxima();
      actualizarHuella(c);
      for (const x of S.corridas) actualizarViento(x);
    } else if (e.aviso === "error" && e.fatal) c.error = e.mensaje;
    pintarTodo();
  };
  c.canal.addEventListener("cierre", () => c.canal.close());
  c.canal.onerror = () => { if (FINALES.includes(c.estado)) c.canal.close(); };
}

async function alTerminar(c) {
  try { c.detalle = await pedir(`/api/corridas/${c.id}`); tomarBitacora(c, c.detalle); } catch (e) { /* queda sin detalle */ }
  refrescarCortafuegos(c); refrescarDescargas(c);
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
  for (const c of S.corridas) { if (c.canal) c.canal.close(); if (c.capa) c.capa.remove(); if (c.capaCf) c.capaCf.remove(); if (c.capaLinea) c.capaLinea.remove(); if (c.capaDescargas) c.capaDescargas.remove(); }
  vaciarDescargas();
  for (const m of S.usados) m.remove();
  S.usados = []; S.corridas = []; S.comparacion = null;
  pintarViento();
}
// Durante una corrida: «Simulación» arriba y abierta; Datos, Configurar y Capas se cierran; la configuración queda fija y el
// pie muestra Pausar / Reanudar / Detener. Al volver («Nueva simulación»), todo como al abrir la página.
function panelEnCorrida(si) {
  $("sec-simulacion").hidden = !si;
  $("tiempo").hidden = !si;
  $("pie-configurar").hidden = si; $("pie-corrida").hidden = !si;
  $("config-campos").disabled = si; $("nota-config-fija").hidden = !si;
  if (si) { seccion("c-simulacion", true); for (const id of ["c-datos", "c-config", "c-capas"]) seccion(id, false); }
  else seccionesIniciales();
  $("panel-cuerpo").scrollTop = 0;
}

function nuevaSimulacion() {
  limpiarCorridas();
  S.modo = "configurar";
  arrastrarFocos(true); pintarFocosIgnicion();
  panelEnCorrida(false);
  B.iniciales = [];
  vaciarBorradores(); ponerHerramienta("config");
  $("anteriores").value = "";
  if (H.focosDe) { H.focosDe = null; pintarFocos(); }
  pintarResultadosHistoricos();
  dibujarLeyenda();
}

// ---------------------------------------------------------------- huella y línea de tiempo
const horaMaxima = c => c ? c.horas.length - 1 : Math.max(0, ...S.corridas.map(x => x.horas.length - 1));
const horasDe = p => p?.horas ?? p?.definicion?.horas ?? p?.historico?.horas ?? p?.historico?.horas_hasta_fin ?? null;   // la histórica sin horas va hasta el fin de la ficha
const horasPedidas = () => Math.max(1, ...S.corridas.map(c => Number(horasDe(c.pedido)) || 0), horaMaxima());

function actualizarHuella(c) {
  if (!c.limites || !c.horas.length) return;
  const h = Math.min(S.horaVista, horaMaxima(c));
  const url = `/api/corridas/${c.id}/quemado.png?hora=${h}` + (c.plano ? `&color=${c.color.slice(1)}` : "") + `&v=${c.horas.length}`;
  if (c.url === url) return;
  if (c.cargando) { c.pendiente = url; return; }
  c.url = url;
  if (!c.capa) {
    c.capa = L.imageOverlay(url, c.limites, {pane: "huella", opacity: c.visible ? OPACIDAD_HUELLA : 0, className: "huella"}).addTo(S.mapa);
    c.capa.on("load error", () => { c.cargando = false; if (c.pendiente) { const p = c.pendiente; c.pendiente = null; c.url = null; actualizarHuellaCon(c, p); } });
    dibujarLeyenda();
  }
  actualizarHuellaCon(c, url);
}
function actualizarHuellaCon(c, url) { c.cargando = true; c.url = url; c.capa.setUrl(url); }

// Ver u ocultar en el mapa la huella y el viento de una corrida (casilla «Ver en el mapa» de su tarjeta). Los cortafuegos
// quedan siempre a la vista: son lo que dibujó el usuario.
const OPACIDAD_HUELLA = 0.85;
function mostrarCorrida(c) {
  if (c.capa) c.capa.setOpacity(c.visible ? OPACIDAD_HUELLA : 0);
  if (c.capaLinea) c.capaLinea.setOpacity(c.visible ? 1 : 0);
  pintarViento(); dibujarLeyenda();
}

function verHora(h, delUsuario) {
  S.horaVista = h;
  if (delUsuario) { detenerReproduccion(); S.enVivo = h >= horaMaxima(); }
  for (const c of S.corridas) { actualizarHuella(c); actualizarLinea(c); dibujarDescargas(c); actualizarViento(c); }
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
function pintarTodo() { pintarBotones(); pintarIntervenir(); pintarTarjetas(); pintarComparacion(); pintarTiempo(); pintarGrafico(); pintarResultadosHistoricos(); }

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
  const unicos = [...new Set(e)], badge = $("estado-simulacion");
  badge.textContent = unicos.map(x => ESTADOS[x] || x).join(" · ");
  badge.className = "badge ms-2 " + (unicos.some(x => ["error", "interrumpida"].includes(x)) ? "text-bg-danger"
    : unicos.some(x => ["pausando", "pausada"].includes(x)) ? "text-bg-warning"
    : todasFinales ? "text-bg-success" : enMarcha ? "text-bg-primary" : "text-bg-secondary");
  const pedidas = S.corridas.filter(c => c.estado === "pausando").map(c => c.pausaEn);
  $("nota-pausa").textContent = !pausando ? ""
    : pedidas.some(x => x != null) ? `Pausando en la hora ${num(Math.max(...pedidas.filter(x => x != null)) / 60)}…` : "Pausando al terminar la hora en curso…";
}

function motivo(c) {
  const r = c.detalle?.resultados;
  if (c.estado === "error" || c.estado === "interrumpida") return c.error || "La corrida no terminó bien.";
  if (!r) return "";
  if (c.estado === "detenida") return "Detenida por el usuario.";
  if (r.completa && r.t_simulado_h >= (Number(horasDe(c.pedido)) || 0) - 1e-6) return "Se cumplieron las horas pedidas.";
  return `El motor cortó antes de las horas pedidas: ${r.motivo_fin_texto || r.motivo_fin}.`;
}

function pintarTarjetas() {
  $("tarjetas").innerHTML = S.corridas.map(c => {
    const u = c.horas[Math.min(S.horaVista, horaMaxima(c))] || c.horas[c.horas.length - 1], fin = c.detalle?.resultados;
    const ult = c.horas[c.horas.length - 1];
    const ritmo = ult && ult.h > 0 ? ult.s / ult.h : null;
    let h = `<div class="tarjeta${c.visible ? "" : " oculta"}"><header><span class="marca" style="background:${c.color}"></span><span class="nombre">${MOTORES[c.motor]?.nombre || c.motor}</span><span class="estado">${ESTADOS[c.estado] || c.estado}</span></header>`;
    h += `<label class="form-check small ver-mapa" title="Muestra u oculta en el mapa el área quemada y el viento de este motor"><input class="form-check-input" type="checkbox" data-ver="${esc(c.id)}"${c.visible ? " checked" : ""}> Ver en el mapa</label>`;
    h += `<p class="cifra">${u ? num(u.ha, u.ha < 100 ? 1 : 0) + " ha" : "—"}<small>${u ? num(u.ha / 100, 2) + " km² · hora " + u.h : "esperando la primera hora"}</small></p><dl>`;
    if (u) h += `<dt>Celdas con fuego activo</dt><dd>${num(u.activas)}</dd>`;
    if (ritmo != null) h += `<dt>Cómputo</dt><dd>${num(ult.s, 1)} s (${num(ritmo, 2)} s por hora simulada)</dd>`;
    if (u?.meteo) h += `<dt>Viento</dt><dd>${num(u.meteo.viento_kmh, 0)} km/h del ${u.meteo.viento_dir_texto || "—"}</dd><dt>Temperatura · humedad</dt><dd>${num(u.meteo.temp_c, 0)} °C · ${num(u.meteo.hr_pct, 0)} %</dd>`;
    if (u?.exposicion) {
      const x = u.exposicion;
      h += `<dt>Viviendas afectadas · amenazadas</dt><dd>${num(x.viviendas_afectadas)} · ${num(x.viviendas_amenazadas)}</dd><dt>Red eléctrica quemada</dt><dd>${num(x.tendido_km_quemado, 1)} km</dd><dt>Caminos afectados</dt><dd>${num(x.caminos_km_afectados, 1)} km</dd>`;
    }
    h += "</dl>";
    if (u && !u.exposicion && c.motor.startsWith("v3.1")) h += `<p class="linea">Esta corrida no informa viviendas, red eléctrica ni caminos alcanzados.</p>`;
    h += htmlCombate(c);
    h += htmlBitacora(c);
    if (FINALES.includes(c.estado)) {
      h += `<p class="linea">${motivo(c)}${fin ? ` Tiempo simulado: ${num(fin.t_simulado_h, 0)} h.` : ""}</p>`;
      if (fin?.reproduccion) h += htmlReproduccion(fin.reproduccion);
      const usadas = fin?.ignicion?.usada || [], corridos = usadas.map((x, i) => [i + 1, x]).filter(([, x]) => x.desplazada_m);
      if (corridos.length === 1 && usadas.length === 1) h += `<div class="alert alert-warning aviso"><b>El fuego no empezó donde hiciste clic.</b>Esa celda no quema; el motor lo corrió ${num(corridos[0][1].desplazada_m)} m, a la celda combustible más cercana.</div>`;
      else if (corridos.length) h += `<div class="alert alert-warning aviso"><b>${corridos.length === 1 ? `El foco ${corridos[0][0]} no empezó` : `Los focos ${corridos.map(([i]) => i).join(", ")} no empezaron`} donde hiciste clic.</b>` +
        `Esas celdas no queman; el motor corrió cada foco a la celda combustible más cercana (${corridos.map(([i, x]) => `foco ${i}: ${num(x.desplazada_m)} m`).join(", ")}).</div>`;
      if (c.estado !== "error") h += `<p class="linea"><a href="/api/corridas/${c.id}/exportar">Descargar resultados (zip)</a></p>`;
      if (["terminada", "detenida"].includes(c.estado) && c.bitacora.length && S.estado.motores.some(m => m.id === c.motor))
        h += `<div class="mt-2"><button class="btn btn-sm btn-outline-secondary" data-reproducir="${esc(c.id)}" title="Corre de nuevo la misma configuración aplicando la bitácora, y compara las dos">Reproducir</button></div>`;
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
    h += `<div class="alert alert-warning aviso"><b>Los motores discrepan.</b>A la hora ${ref.hora} coinciden en menos de la mitad del área. No hay un resultado "promedio": mirá la envolvente como el área posible y cada huella como una hipótesis.</div>`;
  }
  h += `<p class="linea" style="color:var(--suave);margin:6px 0 0">Coincidencia = zona quemada por los dos dividida por la envolvente. ${MOTORES[a.motor].nombre}: relleno de amarillo a rojo. ${MOTORES[b.motor].nombre}: azul.</p>`;
  caja.innerHTML = h;
}

// ---------------------------------------------------------------- gráfico de superficie contra tiempo
function pintarGrafico() {
  const caja = $("grafico"), series = S.corridas.filter(c => c.horas.length);
  if (!series.length) { caja.innerHTML = '<p class="form-text nota">El gráfico aparece cuando llega la primera hora.</p>'; $("tabla").innerHTML = ""; return; }
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
  caja.innerHTML = clave + s + '<div id="globo" hidden></div><p class="form-text nota">Hectáreas quemadas (vertical) contra horas simuladas (horizontal).</p>';

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
// Cortafuegos: aplicado, azul punteado con reborde blanco; dibujado sin enviar, punteado cian y blanco (el fuego es
// rojo-naranja, así que ninguno de los dos se confunde con la huella); tramo recortado, gris punteado.
const COLOR_BORRADOR = "#00FFFF", COLOR_CF = "#1d6fd6", COLOR_RECORTE = "#8a877f";
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

const trazosHabilitados = () => !T.ocupado && (S.modo === "configurar" ? !$("config-campos").disabled : puedeIntervenir());

function ponerHerramienta(donde) {
  $(donde === "config" ? "lugar-trazos-config" : "lugar-trazos-pausa").appendChild($("herr-cortafuegos"));
  $("trazos-cuando").textContent = donde === "config" ? "(opcional, desde la hora 0)" : "";
  $(donde === "config" ? "lugar-combate-config" : "lugar-combate-pausa").appendChild($("herr-bomberos"));
  $("bomberos-cuando").textContent = donde === "config" ? "(opcional, desde la hora 0)" : "";
  $("error-bomberos").textContent = "";
  elegirHerramienta(null);
  pintarBomberos();
}

function elegirHerramienta(modo) {
  if (modo && !trazosHabilitados()) modo = null;
  if (modo && D.modo) marcarDescargas(false);                         // una herramienta de dibujo a la vez
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
  T.linea = L.polyline(T.trazo, {pane: "trazos", color: COLOR_BORRADOR, weight: 3, interactive: false, className: "trazo-vivo"}).addTo(T.capa);
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
  b.capa = L.layerGroup([L.polyline(lls, {pane: "trazos", color: "#1c1b19", weight: 5, opacity: 0.45, interactive: false}),
                         L.polyline(lls, {pane: "trazos", color: "#fff", weight: 3, interactive: false}),
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
  const n = T.borradores.length + D.borradores.length;
  if (!n) return true;
  if (!confirm(`Hay ${n} ${n === 1 ? "dibujo (trazo o descarga) que no se aplicó" : "dibujos (trazos o descargas) que no se aplicaron"}. Si seguís (${accion}), se ${n === 1 ? "descarta" : "descartan"}.`)) return false;
  vaciarBorradores(); vaciarDescargas();
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
  $("b-dibujar").classList.toggle("active", T.modo === "dibujar"); $("b-borrador").classList.toggle("active", T.modo === "borrar");
  $("b-dibujar").textContent = T.modo === "dibujar" ? "Dibujando…" : "Dibujar";
  $("b-deshacer").disabled = !T.hechos.length || T.ocupado;
  $("lista-trazos").innerHTML = T.borradores.map((b, i) => `<li><div class="fila"><span>${b.ancho_m} m de ancho · ${num(b.largo)} m${b.suelo_mineral ? " · a suelo mineral" : ""}</span>` +
    `<button class="btn btn-sm btn-outline-secondary py-0" data-borrar="${b.id}" aria-label="Borrar el trazo ${i + 1}" title="Borrar este trazo"${T.ocupado ? " disabled" : ""}>×</button></div>` +
    (b.error ? `<p class="text-danger small error">${esc(b.error)}</p>` : "") + "</li>").join("");
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
  if (!si) { if (antes || T.modo) elegirHerramienta(null); if (D.modo || D.borradores.length) vaciarDescargas(); return; }
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
  pintarBomberos();
  pintarDescargas();
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

function ocupar(si) { T.ocupado = si; pintarIntervenir(); pintarTrazos(); pintarBomberos(); pintarDescargas(); }

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

// ---------------------------------------------------------------- combate (contrato 1.6): dotaciones de bomberos y línea
// El método es el mismo para los dos motores (app/motores/combate.py): cada despacho suma bomberos que, desde que llegan,
// construyen metros de línea por hora; la línea de cada hora se coloca al cumplirse, sobre el borde del fuego de ese momento
// y solo donde la intensidad permite el ataque directo. Antes de iniciar, las dotaciones van con el pedido de la corrida; en
// pausa son una intervención más (tipo `dotacion`), que queda en la bitácora.
const B = {iniciales: [], cuarteles: null, clave: null};
const TIPOS_COMBATE = ["dotacion", "descarga"];
const COLOR_LINEA = "#111111";
const PRIORIDAD = {flancos: "por los flancos", cabeza: "por la cabeza"};
const tasaDe = n => n * (S.estado?.combate?.parametros?.m_h_por_bombero || 20);

function prepararBomberos() {
  const lim = S.estado.combate || {};
  $("b-cantidad").max = lim.max_bomberos || 500;
  $("b-llegada").max = lim.max_llegada_min || 1440;
  $("b-cantidad").oninput = $("b-prioridad").onchange = pintarBomberos;
  $("b-llegada").oninput = () => { $("b-cuartel").value = ""; pintarBomberos(); };       // escrita a mano: ya no es la estimada
  $("b-cuartel").onchange = () => {
    const q = B.cuarteles?.cuarteles?.[Number($("b-cuartel").value)];
    if ($("b-cuartel").value !== "" && q) $("b-llegada").value = llegadaDesde(q);
    pintarBomberos();
  };
  $("b-despachar").onclick = despachar;
  $("b-retirar").onclick = retirarDotaciones;
  $("lista-dotaciones").addEventListener("click", e => {
    const b = e.target.closest("[data-quitar]");
    if (b) { B.iniciales.splice(Number(b.dataset.quitar), 1); pintarBomberos(); }
  });
  pintarBomberos();
}

// Llegada estimada por la red vial: desde los cuarteles más cercanos al centro de los focos de ignición. Antes de iniciar
// cuenta el aviso, el alistamiento y el viaje; en una pausa el despacho se decide en el momento: alistamiento y viaje.
function puntoDeReferencia() {
  const pts = S.modo === "configurar" ? S.focos : (S.corridas[0]?.pedido?.ignicion || []);
  if (!pts.length) return null;
  return {lat: pts.reduce((s, p) => s + Number(p.lat), 0) / pts.length, lon: pts.reduce((s, p) => s + Number(p.lon), 0) / pts.length};
}
const llegadaDesde = q => (S.modo === "configurar" ? B.cuarteles.aviso_min : 0) + B.cuarteles.alistamiento_min + q.viaje_min;
async function cargarCuarteles() {
  const p = puntoDeReferencia(), clave = `${S.modo === "configurar" ? "c" : "p"}:` + (p ? `${p.lat.toFixed(3)},${p.lon.toFixed(3)}` : "");
  if (clave === B.clave) return;
  B.clave = clave; B.cuarteles = null;
  if (p) { try { B.cuarteles = await pedir(`/api/arribo?lat=${p.lat.toFixed(5)}&lon=${p.lon.toFixed(5)}`); } catch (e) { B.cuarteles = null; } }
  if (clave !== B.clave) return;                                     // cambió mientras se esperaba la respuesta
  $("b-cuartel").innerHTML = '<option value="">A mano (sin estimar)</option>' +
    (B.cuarteles?.cuarteles || []).map((q, i) => `<option value="${i}">${esc(q.nombre)} · llega en ${num(llegadaDesde(q))} min</option>`).join("");
}

function datosDotacion() {
  const n = Number($("b-cantidad").value), ll = Number($("b-llegada").value || 0);
  const max = Number($("b-cantidad").max) || 500, maxLl = Number($("b-llegada").max) || 1440;
  if ($("b-cantidad").value === "" || !Number.isInteger(n) || n < 1 || n > max) return {error: `Los bomberos van de 1 a ${num(max)} (número entero).`};
  if (!Number.isInteger(ll) || ll < 0 || ll > maxLl) return {error: `La llegada va de 0 a ${num(maxLl)} minutos (número entero).`};
  return {datos: {bomberos: n, llegada_min: ll, prioridad: $("b-prioridad").value}};
}
const textoDotacion = d => `${num(d.bomberos)} bomberos (${num(tasaDe(d.bomberos))} m/h), ` +
  `${d.llegada_min ? `llegan en ${num(d.llegada_min)} min` : "ya en el lugar"}, ${PRIORIDAD[d.prioridad] || ""}`;
function textoDespacho(e) {
  const d = e.datos || {};
  if (d.retirar) return `<span class="marca-linea"></span>Se retiran las dotaciones${d.bomberos_retirados ? ` (${num(d.bomberos_retirados)} bomberos)` : ""}`;
  const desde = d.desde_min ?? ((e.t_sim_min || 0) + (d.llegada_min || 0));
  return `<span class="marca-linea"></span>Despacho de ${num(d.bomberos)} bomberos (${num(d.tasa_m_h ?? tasaDe(d.bomberos))} m/h): trabajan desde la ${horaDe(desde)}, ${PRIORIDAD[d.prioridad] || ""}`;
}
// ¿Queda alguna dotación despachada y sin retirar? (de la bitácora y del pedido inicial)
function hayDotaciones() {
  return S.corridas.some(c => {
    let n = (c.pedido?.dotaciones || []).length;
    for (const e of c.bitacora) if (e.tipo === "dotacion") n = e.datos?.retirar ? 0 : n + 1;
    return n > 0;
  });
}

function pintarBomberos() {
  if (!S.estado || !S.mapa) return;
  const pausa = S.modo !== "configurar";
  const si = pausa ? puedeIntervenir() && !T.ocupado : !$("config-campos").disabled;
  for (const id of ["b-cantidad", "b-llegada", "b-cuartel", "b-prioridad", "b-despachar", "b-retirar"]) $(id).disabled = !si;
  const r = datosDotacion(), t = horaDePausa();
  $("b-despachar").textContent = pausa ? `Despachar en la hora ${t != null ? num(t / 60) : ""}` : "Sumar a la corrida";
  $("b-retirar").hidden = !pausa || !hayDotaciones();
  $("nota-bomberos").textContent = r.error ? r.error
    : `${num(r.datos.bomberos)} bomberos construyen ${num(tasaDe(r.datos.bomberos))} m de línea por hora (${num(tasaDe(1))} m cada uno, supuesto). ` +
      (pausa && t != null ? `Trabajan desde la ${horaDe(t + r.datos.llegada_min)}. ` : "") +
      "La línea de cada hora se coloca al cumplirse, sobre el borde que tenga el fuego y solo donde la intensidad lo permite.";
  $("lista-dotaciones").innerHTML = pausa ? "" : B.iniciales.map((d, i) => `<li><div class="fila"><span>${textoDotacion(d)}</span>` +
    `<button class="btn btn-sm btn-outline-secondary py-0" data-quitar="${i}" aria-label="Quitar la dotación ${i + 1}" title="Quitar esta dotación"${si ? "" : " disabled"}>×</button></div></li>`).join("");
  cargarCuarteles();
}

async function despachar() {
  const r = datosDotacion();
  $("error-bomberos").textContent = "";
  if (r.error) return void pintarBomberos();
  if (S.modo === "configurar") {
    const max = S.estado.combate?.max_dotaciones_iniciales || 20;
    if (B.iniciales.length >= max) return void ($("error-bomberos").textContent = `Antes de iniciar se pueden sumar hasta ${max} dotaciones.`);
    B.iniciales.push(r.datos);
    return void pintarBomberos();
  }
  await intervenirCombate(`Despacho de ${textoDotacion(r.datos)}`, {tipo: "dotacion", datos: r.datos});
}
const retirarDotaciones = () => intervenirCombate("Retiro de las dotaciones", {tipo: "dotacion", datos: {retirar: true}});
async function intervenirCombate(titulo, cuerpo) {
  if (!puedeIntervenir() || T.ocupado) return;
  $("error-bomberos").textContent = "";
  ocupar(true);
  try { anotarRespuestas(titulo, await intervenir(cuerpo)); }
  catch (e) { $("error-bomberos").textContent = e.message; }
  finally { ocupar(false); }
  pintarTarjetas();
}

// Línea de combate en el mapa: una imagen con una celda de color por celda de línea en pie en la hora que se mira.
function actualizarLinea(c) {
  if (!c.limites || !(c.combate.length || c.vLinea)) return;
  const h = Math.min(S.horaVista, horaMaxima(c));
  const url = `/api/corridas/${c.id}/combate.png?hora=${h}&v=${c.vLinea}`;
  if (c.urlLinea === url) return;
  c.urlLinea = url;
  if (c.capaLinea) return void c.capaLinea.setUrl(url);
  c.capaLinea = L.imageOverlay(url, c.limites, {pane: "linea", opacity: c.visible ? 1 : 0, className: "linea-combate", interactive: false}).addTo(S.mapa);
  dibujarLeyenda();
}

// Combate en la tarjeta: el último paso de combate hasta la hora que se mira.
function htmlCombate(c) {
  let x = null;
  for (let i = Math.min(S.horaVista, horaMaxima(c), c.combate.length - 1); i >= 0 && !x; i--) x = c.combate[i] || null;
  if (!x) return "";
  const sinLinea = x.frente_celdas != null ? x.frente_celdas - (x.celdas_nuevas || 0) : null;
  const intensas = x.frente_celdas != null ? x.frente_celdas - x.frente_sostenible : 0;
  return `<div class="combate"><h4>Combate <span class="suave fw-normal">· hora ${x.h}</span></h4><dl class="mt-0">` +
    `<dt>Línea en pie</dt><dd>${num((x.linea_en_pie_m || 0) / 1000, 2)} km</dd>` +
    `<dt>Construida en la hora</dt><dd>${num(x.linea_m_hora)} m</dd>` +
    `<dt>Bomberos trabajando</dt><dd>${num(x.bomberos)}${x.bomberos ? ` (${num(x.tasa_m_h)} m/h)` : ""}</dd>` +
    (sinLinea != null ? `<dt>Borde del fuego sin línea</dt><dd>${num(sinLinea)} celdas${intensas ? ` · ${num(intensas)} demasiado intensas` : ""}</dd>` : "") +
    (x.descargas ? `<dt>Descargas · agua en pie</dt><dd>${num(x.descargas)} · ${num(x.celdas_agua)} celdas</dd>` : "") +
    (x.consolidadas_hora ? `<dt>Agua asegurada por los bomberos</dt><dd>${num(x.consolidadas_hora)} celdas en la hora</dd>` : "") +
    (x.vencidas_hora || x.brechas_hora ? `<dt>Agua que se secó · línea que cedió</dt><dd>${num(x.vencidas_hora || 0)} · ${num(x.brechas_hora || 0)} celdas en la hora</dd>` : "") +
    `<dt>Escapes</dt><dd>${num(x.escapes)}${x.escapes_hora ? ` (${num(x.escapes_hora)} en la hora)` : ""}</dd></dl></div>`;
}

// ---------------------------------------------------------------- combate: descargas aéreas (contrato 1.6)
// Solo en pausa. Cada descarga es una franja recta: se aprieta donde empieza, se arrastra hacia donde va y se suelta; el
// largo y el ancho son los del medio elegido (los informa el servidor). Lo marcado queda sin enviar hasta «Lanzar»: cada
// franja va como una intervención `descarga` y queda en la bitácora. Las franjas aplicadas se dibujan con el contorno del
// color del producto; las celdas que quedaron mojadas o frenadas salen en la imagen de la línea de combate, hora por hora.
const D = {modo: false, borradores: [], puntero: null, inicio: null, vivo: null, capa: null, siguiente: 1};
const COLOR_PRODUCTO = {agua: "#1565c0", retardante: "#d81b60"};
const NOMBRE_MEDIO = {avion: "Avión hidrante", helicoptero: "Helicóptero"};
const NOMBRE_PRODUCTO = {agua: "agua", retardante: "retardante"};
const medios = () => S.estado?.combate?.parametros?.medios || {};
const productos = () => S.estado?.combate?.parametros?.productos || {};

function prepararDescargas() {
  $("a-medio").innerHTML = Object.keys(medios()).map(k => `<option value="${esc(k)}">${esc(NOMBRE_MEDIO[k] || k)}</option>`).join("");
  $("a-producto").innerHTML = Object.entries(productos()).map(([k, p]) =>
    `<option value="${esc(k)}">${esc(k === "agua" ? `Agua (dura ${num(p.dura_h)} h)` : "Retardante (no vence)")}</option>`).join("");
  D.capa = L.layerGroup().addTo(S.mapa);
  $("a-medio").onchange = $("a-producto").onchange = pintarDescargas;
  $("a-marcar").onclick = () => marcarDescargas(!D.modo);
  $("a-lanzar").onclick = lanzarDescargas;
  $("lista-descargas").addEventListener("click", e => { const b = e.target.closest("[data-quitar-descarga]"); if (b) quitarDescarga(Number(b.dataset.quitarDescarga)); });
  const cont = S.mapa.getContainer();
  cont.addEventListener("pointerdown", empezarDescarga, true);          // en captura, como los trazos: el mapa no se mueve
  cont.addEventListener("pointermove", seguirDescarga, true);
  cont.addEventListener("pointerup", terminarDescarga, true);
  cont.addEventListener("pointercancel", terminarDescarga, true);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && D.modo) marcarDescargas(false); });
  pintarDescargas();
}

// Franja de una descarga en el mapa: rectángulo de `largo` × `ancho` metros que sale de `a` hacia `b` (aproximación plana
// alrededor de `a`; la franja oficial la calcula el motor en EPSG:5345). Devuelve las esquinas y el punto final.
function franja(a, b, largo, ancho) {
  const kLat = 111320, kLon = 111320 * Math.cos(a.lat * Math.PI / 180);
  let ux = (b.lng - a.lng) * kLon, uy = (b.lat - a.lat) * kLat;
  const d = Math.hypot(ux, uy) || 1;
  ux /= d; uy /= d;
  const p = (x, y) => L.latLng(a.lat + y / kLat, a.lng + x / kLon), nx = -uy * ancho / 2, ny = ux * ancho / 2;
  return {fin: p(ux * largo, uy * largo), esquinas: [p(nx, ny), p(ux * largo + nx, uy * largo + ny), p(ux * largo - nx, uy * largo - ny), p(-nx, -ny)]};
}

// Hora UTC del día en la pausa, para saber si los medios aéreos vuelan (de día).
function horaUTCDeLaPausa() {
  const t = horaDePausa(), t0 = S.corridas.find(c => c.t0)?.t0;
  return t == null || !t0 ? null : new Date(new Date(t0).getTime() + t * 60e3).getUTCHours();
}
function hechasEnLaHora(medio) {                                        // descargas de ese medio ya aplicadas en esta pausa
  const t = horaDePausa();
  return Math.max(0, ...S.corridas.map(c => c.bitacora.filter(e => e.tipo === "descarga" && e.datos?.medio === medio && Math.abs(e.t_sim_min - t) < 1e-6).length));
}
function cupo(medio) {
  const m = medios()[medio];
  return m ? m.max_por_hora - hechasEnLaHora(medio) - D.borradores.filter(b => b.medio === medio).length : 0;
}
function deDia() {
  const h = horaUTCDeLaPausa(), [a, b] = S.estado?.combate?.parametros?.horas_vuelo_utc || [11, 22];
  return h == null || (h >= a && h < b);
}

function marcarDescargas(si) {
  if (si && (!puedeIntervenir() || T.ocupado || !deDia() || cupo($("a-medio").value) <= 0)) si = false;
  if (si && T.modo) elegirHerramienta(null);                            // una herramienta de dibujo a la vez
  if (!si && D.puntero != null) cancelarDescarga();
  D.modo = si;
  const cont = S.mapa.getContainer();
  cont.classList.toggle("marcando", si);
  if (!T.modo) for (const h of ["dragging", "doubleClickZoom", "boxZoom", "touchZoom"]) if (S.mapa[h]) si ? S.mapa[h].disable() : S.mapa[h].enable();
  pintarDescargas();
}

function empezarDescarga(e) {
  if (!D.modo || D.puntero != null || (e.pointerType === "mouse" && e.button !== 0)) return;
  if (e.target.closest && e.target.closest(".leaflet-control-container")) return;
  e.preventDefault(); e.stopPropagation();
  try { S.mapa.getContainer().setPointerCapture(e.pointerId); } catch (x) { /* sin captura igual se marca */ }
  D.puntero = e.pointerId;
  S.mapa.scrollWheelZoom.disable();
  D.inicio = S.mapa.mouseEventToLatLng(e);
  D.xy = [e.clientX, e.clientY];
  $("error-aereos").textContent = "";
}
function seguirDescarga(e) {
  if (D.puntero == null || e.pointerId !== D.puntero) return;
  e.preventDefault(); e.stopPropagation();
  const m = medios()[$("a-medio").value];
  const f = franja(D.inicio, S.mapa.mouseEventToLatLng(e), m.largo_m, m.ancho_m);
  if (D.vivo) D.vivo.setLatLngs(f.esquinas);
  else D.vivo = L.polygon(f.esquinas, {pane: "trazos", color: COLOR_PRODUCTO[$("a-producto").value], weight: 2, fillOpacity: 0.35, interactive: false}).addTo(D.capa);
}
function cancelarDescarga() {
  if (D.vivo) D.vivo.remove();
  D.vivo = D.inicio = D.puntero = null;
  S.mapa.scrollWheelZoom.enable();
}
function terminarDescarga(e) {
  if (D.puntero == null || e.pointerId !== D.puntero) return;
  e.preventDefault(); e.stopPropagation();
  try { S.mapa.getContainer().releasePointerCapture(e.pointerId); } catch (x) { /* ya estaba suelta */ }
  const inicio = D.inicio, movido = Math.hypot(e.clientX - D.xy[0], e.clientY - D.xy[1]), hacia = S.mapa.mouseEventToLatLng(e);
  cancelarDescarga();
  if (e.type === "pointercancel" || !inicio) return;
  const medio = $("a-medio").value, producto = $("a-producto").value, m = medios()[medio];
  const [[sur, oeste], [norte, este]] = S.estado.dominio.limites;
  const fallo = movido < 6 ? "Apretá donde empieza la descarga y arrastrá hacia donde va: así se marca la dirección."
    : !(inicio.lat >= sur && inicio.lat <= norte && inicio.lng >= oeste && inicio.lng <= este) ? "La descarga empieza fuera del dominio."
    : cupo(medio) <= 0 ? `No quedan descargas de ${(NOMBRE_MEDIO[medio] || medio).toLowerCase()} en esta hora.` : "";
  if (fallo) return void ($("error-aereos").textContent = fallo);
  const f = franja(inicio, hacia, m.largo_m, m.ancho_m);
  const b = {id: D.siguiente++, medio, producto, esquinas: f.esquinas, capa: null, error: "",
             lonlat: [inicio, f.fin].map(p => [Number(p.lng.toFixed(7)), Number(p.lat.toFixed(7))])};
  b.capa = L.polygon(f.esquinas, {pane: "trazos", color: COLOR_PRODUCTO[producto], weight: 2, dashArray: "5 4", fillOpacity: 0.3})
    .bindTooltip(() => `Descarga ${D.borradores.indexOf(b) + 1} sin lanzar · ${NOMBRE_MEDIO[medio]} con ${NOMBRE_PRODUCTO[producto]}`, {sticky: true}).addTo(D.capa);
  D.borradores.push(b);
  if (cupo(medio) <= 0) marcarDescargas(false); else pintarDescargas();
}
function quitarDescarga(id) {
  if (T.ocupado) return;
  const i = D.borradores.findIndex(b => b.id === id);
  if (i < 0) return;
  D.borradores[i].capa?.remove();
  D.borradores.splice(i, 1);
  pintarDescargas();
}
function vaciarDescargas() {
  for (const b of D.borradores) b.capa?.remove();
  D.borradores = [];
  if ($("error-aereos")) $("error-aereos").textContent = "";
  if (S.mapa && D.capa) marcarDescargas(false);
}

function pintarDescargas() {
  if (!S.estado || !D.capa) return;
  const si = puedeIntervenir() && !T.ocupado, dia = deDia(), medio = $("a-medio").value, m = medios()[medio], quedan = cupo(medio);
  if (D.modo && (!si || !dia)) return void marcarDescargas(false);
  for (const id of ["a-medio", "a-producto"]) $(id).disabled = !si || !dia;
  $("a-marcar").disabled = !si || !dia || (quedan <= 0 && !D.modo);
  $("a-marcar").textContent = D.modo ? "Marcando… (Esc para salir)" : "Marcar descargas";
  $("a-marcar").classList.toggle("active", D.modo); $("a-marcar").setAttribute("aria-pressed", String(D.modo));
  $("nota-aereos").textContent = !m ? "" : !dia ? "Los medios aéreos operan de día (de 8 a 19 h): en esta hora no se puede descargar."
    : D.modo ? "Apretá donde empieza la descarga, arrastrá hacia donde va y soltá. El mapa no se mueve mientras marcás."
    : `Cada descarga moja una franja de ${num(m.largo_m)} × ${num(m.ancho_m)} m (${m.detalle}). Frena el fuego que toca si no es demasiado intenso y no deja ` +
      `entrar al que llega. ${$("a-producto").value === "agua" ? "El agua da tiempo, no apaga: al secarse el fuego puede seguir, salvo que los bomberos aseguren esa franja. " : ""}` +
      `Quedan ${num(Math.max(0, quedan))} en esta hora.`;
  $("lista-descargas").innerHTML = D.borradores.map((b, i) => `<li><div class="fila"><span>${esc(NOMBRE_MEDIO[b.medio] || b.medio)} con ${esc(NOMBRE_PRODUCTO[b.producto] || b.producto)}</span>` +
    `<button class="btn btn-sm btn-outline-secondary py-0" data-quitar-descarga="${b.id}" aria-label="Quitar la descarga ${i + 1}" title="Quitar esta descarga"${T.ocupado ? " disabled" : ""}>×</button></div>` +
    (b.error ? `<p class="text-danger small error">${esc(b.error)}</p>` : "") + "</li>").join("");
  const t = horaDePausa();
  $("a-lanzar").hidden = !D.borradores.length;
  $("a-lanzar").disabled = !si;
  $("a-lanzar").textContent = D.borradores.length === 1 ? `Lanzar la descarga en la hora ${t != null ? num(t / 60) : ""}` : `Lanzar las ${D.borradores.length} descargas en la hora ${t != null ? num(t / 60) : ""}`;
  dibujarLeyenda();
}

async function lanzarDescargas() {
  if (!puedeIntervenir() || !D.borradores.length || T.ocupado) return;
  marcarDescargas(false);
  $("error-aereos").textContent = "";
  ocupar(true);
  try {
    for (const b of [...D.borradores]) {
      b.error = "";
      try {
        const rs = await intervenir({tipo: "descarga", datos: {medio: b.medio, producto: b.producto, lonlat: b.lonlat}});
        anotarRespuestas(`Descarga de ${(NOMBRE_MEDIO[b.medio] || b.medio).toLowerCase()} con ${NOMBRE_PRODUCTO[b.producto] || b.producto}`, rs);
        if (rs.some(x => x.aviso && x.aviso.estado !== "rechazada")) { b.capa?.remove(); D.borradores.splice(D.borradores.indexOf(b), 1); }
        else b.error = rs.map(x => x.aviso?.motivo || x.error).filter(Boolean).join("; ") || "El motor no la aplicó.";
      } catch (e) {
        b.error = e.message;
        if (!puedeIntervenir()) break;
      }
    }
  } finally { ocupar(false); }
  for (const c of S.corridas) refrescarDescargas(c);
  pintarTarjetas();
}

// Franjas aplicadas (de la bitácora), por corrida: se ven desde la hora en que se lanzaron.
async function refrescarDescargas(c) {
  let fc;
  try { fc = await pedir(`/api/corridas/${c.id}/descargas.geojson`); } catch (e) { return; }
  if (!S.corridas.includes(c)) return;
  c.descargas = fc.features || [];
  dibujarDescargas(c);
}
function dibujarDescargas(c) {
  if (c.capaDescargas) { c.capaDescargas.remove(); c.capaDescargas = null; }
  const t = S.horaVista * 60, visibles = (c.descargas || []).filter(f => (f.properties.t_sim_min ?? 0) <= t + 1e-6);
  if (visibles.length) {
    c.capaDescargas = L.layerGroup(visibles.map(f => {
      const p = f.properties, anillo = f.geometry.coordinates[0].map(([lon, lat]) => [lat, lon]);
      const vencida = p.vence_min != null && p.vence_min <= t + 1e-6;
      return L.polygon(anillo, {pane: "cortafuegos", color: COLOR_PRODUCTO[p.producto] || "#555", weight: 1.5, opacity: vencida ? 0.45 : 0.95,
                                dashArray: vencida ? "3 4" : null, fillOpacity: vencida ? 0 : 0.12})
        .bindTooltip(`${S.corridas.length > 1 ? `${MOTORES[c.motor]?.nombre || c.motor} · ` : ""}${textoDescargaPlano(p)}${vencida ? " · ya se secó" : ""}`, {sticky: true});
    })).addTo(S.mapa);
  }
  dibujarLeyenda();
}
function textoDescargaPlano(d) {
  return `${NOMBRE_MEDIO[d.medio] || d.medio} con ${NOMBRE_PRODUCTO[d.producto] || d.producto}: moja ${num(d.celdas_mojadas)} ${d.celdas_mojadas === 1 ? "celda" : "celdas"} sin quemar y frena ${num(d.celdas_frenadas)} con fuego` +
    (d.celdas_intensas ? `; ${num(d.celdas_intensas)} del frente con demasiada intensidad` : "") + (d.vence_min != null ? ` · dura hasta la ${horaDe(d.vence_min)}` : " · no vence");
}
const textoDescarga = e => {
  const t = textoDescargaPlano(e.datos || {});
  return `<span class="marca-linea ${esc(e.datos?.producto || "")}"></span>Descarga de ${esc(t.charAt(0).toLowerCase() + t.slice(1))}`;
};

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
  for (const d of c.pedido?.dotaciones || []) filas.push(["inicio", textoDespacho({datos: d, t_sim_min: 0})]);
  for (const e of c.bitacora) {
    const cuando = horaDe(e.t_sim_min);
    if (e.tipo === "cortafuego") {
      const f = c.cortafuegos.find(x => x.properties.origen === "intervencion" && x.properties.n === e.n);
      filas.push([cuando, textoCortafuego({...(e.datos || {}), ...(f ? f.properties : {})})]);
    } else if (e.tipo === "viento_manual") filas.push([cuando, textoVientoManual(e)]);
    else if (e.tipo === "dotacion") filas.push([cuando, textoDespacho(e)]);
    else if (e.tipo === "descarga") filas.push([cuando, textoDescarga(e)]);
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
  return `<div class="alert alert-warning aviso"><b>La reproducción de ${esc(r.de)} no salió igual.</b>${por.join("; ") || "Revisá el detalle en los resultados."}.</div>`;
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
                      : L.polyline(t.pts, {pane: "cortafuegos", color: COLOR_CF, weight: 3, dashArray: "7 5"}).bindTooltip(texto, {sticky: true}));
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

// ---------------------------------------------------------------- viento sobre el mapa (casilla «Viento» de la barra de tiempo)
// Cada motor guarda el viento que usó, muestreado cada ~1 km (GET /api/corridas/<id>/viento?hora=N): v3.1, el campo de
// WindNinja; v4.0, el viento de la hora con la velocidad ajustada por el relieve. Se dibuja con flechas del color de cada
// motor en un lienzo propio, sincronizado con la hora que se ve (en vivo y al recorrer la corrida). Al alejar el mapa se
// muestra una flecha de cada tantas para que no se encimen.
const VIENTO_MIN_PX = 42;                       // separación mínima entre flechas en pantalla
const V = {lienzo: null};

function prepararCapaViento() {
  V.lienzo = L.DomUtil.create("canvas", "capa-viento", S.mapa.getPane("viento"));
  S.mapa.on("moveend zoomend resize viewreset", pintarViento);
  S.mapa.on("zoomstart", () => { V.lienzo.style.visibility = "hidden"; });
}

async function actualizarViento(c) {
  if (!S.verViento || c.sinViento || !c.horas.length || !S.corridas.includes(c)) return;
  const h = Math.min(S.horaVista, horaMaxima(c)), final = FINALES.includes(c.estado);
  if (c.vientos[h]) {
    if (c.viento !== c.vientos[h]) { c.viento = c.vientos[h]; pintarViento(); dibujarLeyenda(); }
    return;
  }
  if (c.pidiendoViento === h) return;
  c.pidiendoViento = h;
  try {
    const r = await fetch(`/api/corridas/${c.id}/viento?hora=${h}`);
    if (r.status === 404) { if (final) { c.sinViento = true; c.viento = null; } }
    else if (r.ok) {
      const d = await r.json();
      if (d.hora === h || final) c.vientos[h] = d;      // en vivo, v3.1 guarda el viento de la hora recién al terminarla
      if (Math.min(S.horaVista, horaMaxima(c)) === h) c.viento = d;
    }
  } catch (e) { /* sin viento esta vez: se vuelve a pedir con la próxima hora */ }
  finally { if (c.pidiendoViento === h) c.pidiendoViento = null; }
  pintarViento(); dibujarLeyenda();
}

function pintarViento() {
  const lz = V.lienzo;
  if (!lz) return;
  const tam = S.mapa.getSize(), dpr = window.devicePixelRatio || 1;
  lz.width = tam.x * dpr; lz.height = tam.y * dpr;
  lz.style.width = `${tam.x}px`; lz.style.height = `${tam.y}px`;
  L.DomUtil.setPosition(lz, S.mapa.containerPointToLayerPoint([0, 0]));
  lz.style.visibility = "";
  const ctx = lz.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, tam.x, tam.y);
  if (!S.verViento) return;
  const centro = S.mapa.getCenter();
  const mPorPx = 40075016.686 * Math.cos(centro.lat * Math.PI / 180) / Math.pow(2, S.mapa.getZoom() + 8);
  for (const c of S.corridas.filter(x => x.visible && x.viento)) {
    const w = c.viento, pasoPx = w.paso_m / mPorPx;
    const salto = Math.max(1, Math.ceil(VIENTO_MIN_PX / pasoPx));
    const largoMax = Math.max(12, Math.min(pasoPx * salto * 0.8, 46));
    for (const [lat, lon, vel, desde, f, k] of w.flechas) {
      if (f % salto || k % salto) continue;
      const p = S.mapa.latLngToContainerPoint([lat, lon]);
      if (p.x < -50 || p.y < -50 || p.x > tam.x + 50 || p.y > tam.y + 50) continue;
      dibujarFlecha(ctx, p.x, p.y, desde, Math.min(largoMax, 8 + vel * 0.9), c.color);
    }
  }
}

function dibujarFlecha(ctx, x, y, desde, largo, color) {
  const a = (desde + 180) * Math.PI / 180, dx = Math.sin(a), dy = -Math.cos(a);     // hacia donde va (pantalla: y abajo)
  const x0 = x - dx * largo / 2, y0 = y - dy * largo / 2, x1 = x + dx * largo / 2, y1 = y + dy * largo / 2;
  const punta = Math.min(7, largo * 0.45), ax = -dy, ay = dx;                         // ax, ay: perpendicular
  const cabeza = [[x1, y1], [x1 - dx * punta + ax * punta * 0.55, y1 - dy * punta + ay * punta * 0.55],
                  [x1 - dx * punta - ax * punta * 0.55, y1 - dy * punta - ay * punta * 0.55]];
  for (const [ancho, tinta] of [[4.5, "rgba(255,255,255,.9)"], [2, color]]) {
    ctx.strokeStyle = tinta; ctx.fillStyle = tinta; ctx.lineWidth = ancho; ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1 - dx * punta * 0.6, y1 - dy * punta * 0.6); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(...cabeza[0]); ctx.lineTo(...cabeza[1]); ctx.lineTo(...cabeza[2]); ctx.closePath();
    if (ancho > 2) ctx.stroke(); else ctx.fill();
  }
}

const iconoFlecha = (color, desde) => `<svg class="flecha-leyenda" viewBox="-7 -7 14 14" aria-hidden="true" style="transform:rotate(${(desde + 180) % 360}deg)">` +
  `<path d="M0 6V-3" stroke="${color}" stroke-width="2" stroke-linecap="round"/><path d="M0 -6.5L-3.6 -1.5H3.6Z" fill="${color}"/></svg>`;

function bloqueLeyendaViento() {
  if (!S.verViento) return "";
  const cs = S.corridas.filter(c => c.visible && c.horas.length);
  if (!cs.length) return "";
  let h = "<h3>Viento</h3>";
  for (const c of cs) {
    const w = c.viento, nombre = MOTORES[c.motor]?.nombre || c.motor;
    if (!w) { h += `<div class="item suave">${iconoFlecha(c.color, 0)}<span>${esc(nombre)}: ${c.sinViento ? "esta corrida no guardó el viento" : "esperando la primera hora…"}</span></div>`; continue; }
    const cuando = w.momento === "intervalo" ? `de la hora ${w.hora} a la ${w.hora + 1}` : `en la hora ${w.hora}`;
    h += `<div class="item">${iconoFlecha(c.color, w.dir_media)}<span>${esc(nombre)}: ${num(w.vel_media_kmh)} km/h del ${rumbo(w.dir_media)} <span class="suave">· ${cuando}</span></span></div>` +
      `<div class="nota-leyenda">${esc(w.campo)}</div>`;
  }
  return h + '<div class="nota-leyenda">La flecha apunta hacia donde sopla; cuanto más larga, más fuerte.</div>';
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
  const p = grupo[0].pedido || {};
  if (p.evento && S.estado.eventos_base.some(e => e.id === p.evento) && $("evento").value !== p.evento) { $("evento").value = p.evento; await cargarCapas(); }
  if ((p.ignicion || []).length) ponerFocos(p.ignicion);
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

// «Obtener datos actuales»: tres trabajos seguidos, cada uno cuando termina el anterior. Si uno falla, la cadena se corta
// ahí y se ofrece reintentar desde ese paso (los pasos ya hechos no se repiten). El evento se arma con las dos tomas que
// bajó la cadena; si se reintenta solo ese paso tras recargar la página, con las más nuevas guardadas.
const PASOS = [
  {nombre: "Pronóstico del tiempo (Open-Meteo)", tarea: "pronostico", hacer: () => pedir("/api/datos/meteo", {fuente: "pronostico"})},
  {nombre: "Índices de vegetación (Sentinel-2)", tarea: "indices_aws", hacer: () => pedir("/api/datos/indices", {fuente: "aws"})},
  {nombre: "Evento de tiempo real", tarea: "evento", hacer: () => {
    const cuerpo = {};
    if (C.tomas.pronostico) cuerpo.meteo = C.tomas.pronostico;
    if (C.tomas.indices_aws) cuerpo.indices = C.tomas.indices_aws;
    return pedir("/api/datos/evento", cuerpo);
  }},
];
const ESTADO_PASO = {espera: ["en espera", "text-bg-light border"], curso: ["en curso", "text-bg-primary"], listo: ["listo", "text-bg-success"], error: ["error", "text-bg-danger"]};
const C = {activa: false, paso: -1, estados: PASOS.map(() => "espera"), tomas: {}, error: "", linea: ""};

function obtenerDatos(desde = 0) {
  if (enMarcha()) return;
  for (let i = desde; i < PASOS.length; i++) C.estados[i] = "espera";
  C.activa = true; C.error = ""; C.linea = "";
  correrPaso(desde);
}
async function correrPaso(i) {
  C.paso = i; C.estados[i] = "curso"; C.linea = ""; pintarPasos();
  const ok = await lanzar(PASOS[i].hacer);
  if (!ok) fallaPaso(i, $("error-datos").textContent);
}
function fallaPaso(i, motivo) {
  C.estados[i] = "error"; C.activa = false; C.error = motivo || "El trabajo no terminó bien."; C.linea = "";
  pintarPasos();
}
// Llamada al terminar cualquier trabajo: si es el paso en curso de la cadena, la avanza o la corta.
function avanzarCadena(t) {
  if (!C.activa || C.paso < 0 || PASOS[C.paso].tarea !== t.tarea) return;
  const i = C.paso;
  if (t.estado !== "terminado") return fallaPaso(i, t.error);
  C.estados[i] = "listo";
  if (t.resultado?.id) C.tomas[t.tarea] = t.resultado.id;
  if (i + 1 < PASOS.length) correrPaso(i + 1);
  else { C.activa = false; C.linea = ""; pintarPasos(); }
}

function pintarPasos() {
  // acá y no en pintarTrabajo: la cadena termina (o falla) sin que cambie el trabajo, y el botón tiene que volver
  $("b-obtener").textContent = C.activa ? "Obteniendo datos actuales…" : "Obtener datos actuales";
  $("pasos").hidden = C.paso < 0;
  $("pasos").innerHTML = PASOS.map((p, i) => {
    const [texto, clase] = ESTADO_PASO[C.estados[i]];
    const linea = C.estados[i] === "curso" && C.linea ? `<div class="form-text mt-0 text-truncate" title="${esc(C.linea)}">${esc(C.linea)}</div>` : "";
    return `<li class="list-group-item d-flex justify-content-between align-items-start gap-2 py-1"><div class="ms-1 me-auto min-w-0">${esc(p.nombre)}${linea}</div>` +
      `<span class="badge ${clase}">${texto}</span></li>`;
  }).join("");
  const fallo = C.estados.indexOf("error");
  $("reintentar").hidden = fallo < 0 || C.activa;
  if (fallo >= 0) {
    $("reintentar-texto").innerHTML = `<b>Falló el paso ${fallo + 1}: ${esc(PASOS[fallo].nombre)}.</b><br>${esc(limpiar(C.error))}`;
    $("b-reintentar").textContent = `Reintentar desde el paso ${fallo + 1}`;
    $("b-reintentar").onclick = () => obtenerDatos(fallo);
    $("b-reintentar").disabled = enMarcha();
  }
}

// «1. Datos» ofrece un camino por cada origen de los datos (actuales, desde archivos, escenario); cada camino termina en su
// propio botón «Preparar datos para simular», que arma el evento de tiempo real y lo deja elegido en «2. Configurar».
function elegirOrigen(o) {
  $(`origen-${o}`).checked = true;
  for (const c of document.querySelectorAll(".camino")) c.hidden = c.id !== `camino-${o}`;
}

// Camino «Desde archivos»: las tomas cargadas en esta visita. Lo que falte se completa con la toma más nueva guardada.
const A = {meteo: null, indices: null};
// Camino «Escenario»: al terminar la toma del escenario se arma el evento con los índices elegidos.
const E = {pendiente: null};

function prepararDatos() {
  for (const r of document.querySelectorAll('input[name="origen"]')) r.onchange = () => elegirOrigen(r.value);
  $("b-obtener").onclick = () => { S.origenEvento = "actual"; obtenerDatos(0); };
  $("b-gee").onclick = () => lanzar(() => pedir("/api/datos/indices", {fuente: "gee"}));
  $("b-evento").onclick = armarEvento;
  $("b-evento-archivos").onclick = armarEventoArchivos;
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
  const avisos = avisosVisibles(d.avisos);
  $("datos-avisos").innerHTML = avisos.length
    ? `<div class="alert alert-warning aviso"><b>Para tener en cuenta</b><ul>${avisos.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";

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
      `<dt>Fuente</dt><dd>${esc(limpiar(ind.rotulo || ind.fuente) || "—")}</dd>` +
      (ind.n_escenas != null ? `<dt>Escenas</dt><dd>${num(ind.n_escenas)}${ultima ? ` · la última del ${fechaCorta(ultima)}` : ""}</dd>` : "") +
      (ind.celdas_sin_dato_pct ? `<dt>Celdas sin dato</dt><dd>${num(ind.celdas_sin_dato_pct, 1)} %</dd>` : "") +
      `<dt>Antigüedad</dt><dd class="${a.indices_dias > a.indices_viejos_dias ? "viejo" : ""}">${a.indices_dias == null ? "—" : a.indices_dias === 0 ? "de hoy" : a.indices_dias === 1 ? "de ayer" : `${num(a.indices_dias)} días`}</dd>`
    : '<dd class="vacio">No hay índices guardados.</dd>';
  pintarEstadoDatos(pron, ind, a);
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
  const tomasInd = d.indices || [], antesEsc = $("sel-indices-esc").value;
  $("sel-indices-esc").innerHTML = tomasInd.length
    ? tomasInd.map((t, i) => `<option value="${esc(t.id)}">${i ? "" : "La más nueva: "}${esc(etiquetaToma(t, "índices"))}</option>`).join("")
    : '<option value="">No hay índices guardados</option>';
  if (tomasInd.some(t => t.id === antesEsc)) $("sel-indices-esc").value = antesEsc;
  pintarArchivos();
  pintarTrabajo();
}

// Rótulo del encabezado: qué datos actuales hay y de cuándo (verde al día, amarillo viejos, gris sin datos).
function pintarEstadoDatos(pron, ind, a) {
  const b = $("estado-datos");
  const viejo = (pron && a.pronostico_horas > a.pronostico_viejo_horas) || (ind && a.indices_dias > a.indices_viejos_dias);
  const partes = [];
  if (pron) partes.push(`pronóstico del ${aLocal(normalizarUTC(pron.hora_de_la_toma_utc || pron.creada_utc)).texto} (${hace(a.pronostico_horas)})`);
  if (ind) partes.push(`índices ${a.indices_dias == null ? "" : a.indices_dias === 0 ? "de hoy" : a.indices_dias === 1 ? "de ayer" : `de hace ${num(a.indices_dias)} días`}`);
  b.textContent = partes.length ? `Datos actuales: ${partes.join(" · ")}` : "Sin datos actuales: obtenelos en «1. Datos» o usá un ejemplo";
  b.className = "badge text-wrap text-start " + (!pron || !ind ? "text-bg-secondary" : viejo ? "text-bg-warning" : "text-bg-success");
  b.title = viejo ? "Hay datos viejos: conviene volver a obtenerlos" : "";
}

function etiquetaToma(t, que) {
  if (que === "índices") {
    const v = t.ventana || [];
    return `${limpiar(t.rotulo || t.fuente) || t.id} · ${fechaCorta(v[0])} a ${fechaCorta(v[1])}`;
  }
  return `${limpiar(t.rotulo || t.fuente) || t.id} ·${t.desde_utc ? aLocal(t.desde_utc).texto.slice(0, 10) + " a " + aLocal(t.hasta_utc).texto.slice(0, 10) : ""} · tomada ${aLocal(normalizarUTC(t.creada_utc)).texto}`;
}

function enMarcha() { return S.ocupado || (S.trabajo && !TRABAJO_FINAL.includes(S.trabajo.estado)); }

function pintarTrabajo() {
  const t = S.trabajo, ocupado = enMarcha(), d = S.datos || {};
  for (const b of document.querySelectorAll("#sec-datos button.lanza")) b.disabled = ocupado;
  if (!d.gee?.disponible) $("b-gee").disabled = true;
  if (!(d.meteo || []).length || !(d.indices || []).length) $("b-evento").disabled = true;
  $("b-evento").title = $("b-evento").disabled && !ocupado ? "Hace falta al menos una toma de meteorología y una de índices" : "";
  const [mA, iA] = tomasArchivos();
  if (!(A.meteo || A.indices) || !mA || !iA) $("b-evento-archivos").disabled = true;
  $("b-evento-archivos").title = !(A.meteo || A.indices) ? "Primero cargá la meteorología, los índices o los dos"
    : !mA || !iA ? "Falta la otra mitad y no hay nada guardado para completarla" : "";
  if (!(d.indices || []).length) $("b-escenario").disabled = true;
  $("b-escenario").title = !(d.indices || []).length ? "Hacen falta índices de vegetación: obtené los actuales o cargalos desde archivos" : "";
  $("trabajo").hidden = !t;
  if (!t) { pintarPasos(); return; }
  // la caja del trabajo va junto al botón que lo lanzó
  const lugar = {meteo_manual: "lugar-trabajo-csv", indices_manual: "lugar-trabajo-manual", escenario: "lugar-trabajo-escenario",
                 evento: `lugar-trabajo-${S.origenEvento || "actual"}`}[t.tarea] || "lugar-trabajo-actual";
  if ($("trabajo").parentElement.id !== lugar) $(lugar).appendChild($("trabajo"));
  $("trabajo-nombre").textContent = TAREAS[t.tarea] || t.tarea;
  $("trabajo-estado").textContent = ESTADOS_TRABAJO[t.estado] || t.estado;
  const p = t.progreso, barra = $("trabajo-barra");
  const corre = !TRABAJO_FINAL.includes(t.estado), indefinida = corre && !(p && p.total > 0);
  barra.classList.toggle("progress-bar-striped", indefinida); barra.classList.toggle("progress-bar-animated", indefinida);
  barra.classList.toggle("bg-danger", ["error", "interrumpido"].includes(t.estado)); barra.classList.toggle("bg-success", t.estado === "terminado");
  barra.style.width = !corre ? "100%" : indefinida ? "100%" : `${Math.min(100, p.hechos / p.total * 100)}%`;
  let texto = "";
  if (corre) texto = p ? `${p.texto || ""}${p.total > 0 ? ` (${num(p.hechos)} de ${num(p.total)})` : ""}${p.s != null ? ` · ${num(p.s)} s` : ""}` : "Arrancando el proceso de datos…";
  if (C.activa && C.paso >= 0 && PASOS[C.paso].tarea === t.tarea) C.linea = corre ? texto : "";
  pintarPasos();
  if (corre) { /* el texto ya es el avance */ }
  else if (t.estado === "terminado") texto = resumenResultado(t);
  else if (t.terminado_utc) texto = `Terminó el ${aLocal(normalizarUTC(t.terminado_utc)).texto}.`;
  $("trabajo-texto").textContent = texto;
  $("trabajo-error").textContent = t.estado === "error" || t.estado === "interrumpido" ? (t.error || "El trabajo no terminó bien.") : "";
  pintarSinRed(t);
}

function resumenResultado(t) {
  const r = t.resultado || {}, cuando = t.terminado_utc ? ` el ${aLocal(normalizarUTC(t.terminado_utc)).texto}` : "";
  if (t.tarea === "evento") return `Datos listos${cuando}. Quedaron elegidos en «2. Configurar simulación»: seguí con el día, la hora y los focos.`;
  if (t.tarea === "escenario") return `Escenario guardado${cuando}${r.horas ? `, ${num(r.horas)} horas` : ""}.`;
  const usar = ["meteo_manual", "indices_manual"].includes(t.tarea) ? " Seguí con el paso siguiente." : "";
  if (t.tarea.startsWith("indices")) return `Toma ${r.id || ""} guardada${cuando}${r.n_escenas != null ? `, con ${num(r.n_escenas)} escenas` : ""}.${usar}`;
  return `Toma ${r.id || ""} guardada${cuando}${r.horas ? `, ${num(r.horas)} horas` : ""}.${usar}`;
}

// Sin red: si la descarga falla y no hay ninguna toma de ese tipo guardada, se dice claro qué queda por hacer.
function pintarSinRed(t) {
  const caja = $("trabajo-sin-red"), d = S.datos || {};
  const bajada = ["pronostico", "indices_aws", "indices_gee"].includes(t.tarea);
  const sinTomas = t.tarea === "pronostico" ? !(d.meteo || []).length : !(d.indices || []).length;
  caja.hidden = !(bajada && t.estado === "error" && sinTomas);
  if (caja.hidden) return;
  caja.className = "alert alert-warning aviso sin-red";
  caja.innerHTML = `<b>No se pudo bajar ${t.tarea === "pronostico" ? "el pronóstico" : "los índices"} y no hay nada guardado.</b>` +
    `Puede ser que la computadora no tenga internet. Podés ${t.tarea === "pronostico" ? "cargar un CSV de meteorología o armar un escenario" : "cargar los TIF de NDVI y NDMI"} (en «Desde archivos» y «Escenario»), o simular con un evento de EJEMPLO, que no necesita red.` +
    `<br><button class="btn btn-sm btn-outline-secondary mt-2" id="usar-ejemplo">Usar un ejemplo</button>`;
  $("usar-ejemplo").onclick = usarEjemplo;
}

function usarEjemplo() {
  if (S.modo !== "configurar") return;
  const ejemplo = S.estado.eventos_base.find(e => e.id === "SL-2024-LASLAGUNAS") || S.estado.eventos_base.find(e => !e.tiempo_real);
  if (!ejemplo) return;
  $("evento").value = ejemplo.id; proponerEvento(); cargarCapas();
  seccion("c-config", true);
  $("sec-config").scrollIntoView({behavior: "smooth", block: "start"});
}

// Lanza un trabajo: `hacer` hace el pedido y devuelve {trabajo}. Un solo trabajo a la vez (el servidor contesta 409 si no).
// Devuelve true si el trabajo arrancó.
async function lanzar(hacer, siempre) {
  if (enMarcha()) return false;
  $("error-datos").textContent = "";
  S.ocupado = true; pintarTrabajo();
  let ok = false;
  try {
    const r = await hacer();
    S.trabajo = r.trabajo;
    seguirTrabajo(r.trabajo);
    if (siempre) siempre();
    ok = true;
  } catch (e) {
    $("error-datos").textContent = e.message;
  } finally {
    S.ocupado = false; pintarTrabajo();
  }
  return ok;
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
  if (t.estado !== "terminado") return avanzarCadena(t);
  const id = t.resultado?.id;
  if (t.tarea === "evento") {
    try { await refrescarEventos(S.modo === "configurar" ? id : undefined); } catch (e) { $("error-datos").textContent = e.message; }
    if (S.modo === "configurar" && id) {          // el usuario sigue en «2. Configurar simulación»
      seccion("c-config", true);
      $("sec-config").scrollIntoView({behavior: "smooth", block: "start"});
    }
  } else if (id && t.tarea === "meteo_manual") { A.meteo = id; pintarArchivos(); pintarTrabajo(); }
  else if (id && t.tarea === "indices_manual") { A.indices = id; pintarArchivos(); pintarTrabajo(); }
  else if (id && t.tarea === "escenario" && E.pendiente) {
    const cuerpo = {meteo: id, ...E.pendiente};
    E.pendiente = null;
    S.origenEvento = "escenario";
    lanzar(() => pedir("/api/datos/evento", cuerpo), () => { $("nombre-esc").value = ""; });
  }
  if (t.tarea === "escenario" && t.estado !== "terminado") E.pendiente = null;
  avanzarCadena(t);
}

function armarEvento() {
  const cuerpo = {};
  if ($("sel-meteo").value) cuerpo.meteo = $("sel-meteo").value;
  if ($("sel-indices").value) cuerpo.indices = $("sel-indices").value;
  if ($("nombre-rt").value.trim()) cuerpo.nombre = $("nombre-rt").value.trim();
  S.origenEvento = "combinar";
  lanzar(() => pedir("/api/datos/evento", cuerpo), () => { $("nombre-rt").value = ""; });
}

// Qué tomas usaría «Preparar datos para simular» del camino «Desde archivos»: las cargadas, o si no las más nuevas guardadas.
function tomasArchivos() {
  const d = S.datos || {};
  const de = (lista, id) => (lista || []).find(t => t.id === id) || (lista || [])[0] || null;
  return [de(d.meteo, A.meteo), de(d.indices, A.indices)];
}
function pintarArchivos() {
  const [m, i] = tomasArchivos();
  for (const [id, cargada, n] of [["ok-meteo", A.meteo, "1"], ["ok-indices", A.indices, "2"]]) {
    $(id).textContent = cargada ? "✓" : n;
    $(id).className = `badge rounded-pill ${cargada ? "text-bg-success" : "text-bg-secondary"}`;
    $(id).title = cargada ? "Cargado" : "";
  }
  const fila = (nombre, t, cargada, que) => `<dt>${nombre}</dt><dd>${!t ? '<span class="vacio">nada guardado</span>'
    : cargada ? "la que cargaste" : `<span class="text-body-secondary">lo más nuevo guardado:</span> ${esc(etiquetaToma(t, que))}`}</dd>`;
  $("resumen-archivos").innerHTML = fila("Meteorología", m, !!A.meteo, "meteorología") + fila("Índices", i, !!A.indices, "índices");
}
function armarEventoArchivos() {
  const [m, i] = tomasArchivos();
  if (!m || !i) return;
  const cuerpo = {meteo: m.id, indices: i.id};
  if ($("nombre-archivos").value.trim()) cuerpo.nombre = $("nombre-archivos").value.trim();
  S.origenEvento = "archivos";
  lanzar(() => pedir("/api/datos/evento", cuerpo), () => { $("nombre-archivos").value = ""; A.meteo = A.indices = null; pintarArchivos(); });
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
  if (!$("sel-indices-esc").value) return void ($("error-datos").textContent = "Hacen falta índices de vegetación: obtené los actuales o cargalos desde archivos.");
  const pendiente = {indices: $("sel-indices-esc").value};
  if ($("nombre-esc").value.trim()) pendiente.nombre = $("nombre-esc").value.trim();
  E.pendiente = pendiente;
  lanzar(() => pedir("/api/datos/meteo/escenario", cuerpo)).then(ok => { if (!ok) E.pendiente = null; });
}


// ---------------------------------------------------------------- modo histórico (fase F6, D-E3-30 punto 13)
// GET /api/historicos (eventos con ficha, disponibilidad, ignición recomendada, cifras documentadas), POST
// /api/historicos/<evento>/corrida (una corrida por motor), GET /api/corridas/<id>/metricas_v31 (evaluador de v3.1 sin cambios)
// y GET /api/historicos/<evento>/focos.geojson[?corrida=<id>] (focos VIIRS con su pasada y, con la corrida, su clase).
const MOTORES_HISTORICO = ["v3.1-librev2", "v3.1-libre", "v4.0"];
const CLASES = {
  a_tiempo: {nombre: "a tiempo", color: "#15803d"},
  adelantado: {nombre: "adelantado (el modelo llega antes)", corto: "adelantado", color: "#0891b2"},
  atrasado: {nombre: "atrasado (el modelo llega después)", corto: "atrasado", color: "#c026d3"},
  no_alcanzado: {nombre: "no alcanzado", color: "#1c1b19"},
};
const COLOR_SIN_CLASE = "#fff";
const H = {eventos: [], referencia: null, elegido: null, metricas: {}, sondeos: {}, cicatriz: null, focos: null, focosClave: null,
           focosDe: null, focosLeyenda: null, turnoFocos: 0, firma: null};
const nombreCorto = e => String(e?.nombre || e?.id || "").split(" (")[0];
const esX49 = e => /^no visto/i.test(e?.rol || "");
const hev = id => H.eventos.find(e => e.id === id);
const frac = v => v == null ? "—" : num(v, 2);
const horasConSigno = v => v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${num(Math.abs(v), 1)} h`;

function prepararHistorico() {
  for (const [nombre, z] of [["cicatriz", 390], ["focos", 425]]) S.mapa.createPane(nombre).style.zIndex = z;   // sobre la huella simulada
  $("h-lista").addEventListener("click", e => { const b = e.target.closest("[data-evento]"); if (b) elegirHistorico(b.dataset.evento); });
  $("h-ver-cicatriz").onchange = () => verCicatriz($("h-ver-cicatriz").checked);
  $("h-ver-focos").onchange = () => pintarFocos();
  $("h-iniciar").onclick = correrHistorico;
  $("h-doc-tabla").addEventListener("click", e => { const b = e.target.closest("[data-fila]"); if (b) correrFila(Number(b.dataset.fila), b); });
  $("h-resultados").addEventListener("change", e => { if (e.target.id === "h-focos-corrida") { H.focosDe = e.target.value || null; pintarFocos(); } });
  cargarHistoricos();
}

async function cargarHistoricos() {
  try {
    const r = await pedir("/api/historicos");
    H.eventos = r.eventos || []; H.referencia = r.referencia || null;
  } catch (e) { $("h-error-lista").textContent = "No se pudo leer la lista de eventos históricos: " + e.message; return; }
  $("h-error-lista").textContent = "";
  pintarListaHistoricos();
  const corriendo = S.corridas.map(c => eventoDe(c)).find(id => hev(id));
  if (!H.elegido) elegirHistorico(corriendo || (H.eventos.find(e => e.se_puede_correr && esX49(e)) || H.eventos.find(e => e.se_puede_correr) || H.eventos[0])?.id, true);
  for (const c of S.corridas) vigilarMetricas(c);
}

function estadoCorto(e) {
  if (e.se_puede_correr) return {clase: "si", texto: e.faltan_v40?.length ? "se puede correr (a v4.0 le faltan datos)" : "se puede correr"};
  if (esX49(e) && !e.recomendada) return {clase: "no", texto: "X-49 sin ignición recomendada: no se corre"};
  if ((e.faltan || []).length) return {clase: "no", texto: `faltan ${e.faltan.length} archivos (llegan en F7)`};
  return {clase: "no", texto: e.motivo || "no se puede correr"};
}

function pintarListaHistoricos() {
  const orden = [...H.eventos].sort((a, b) => (b.se_puede_correr - a.se_puede_correr) || String(a.id).localeCompare(String(b.id)));
  $("h-lista").innerHTML = orden.map(e => {
    const s = estadoCorto(e);
    return `<li><button data-evento="${esc(e.id)}" aria-pressed="${e.id === H.elegido}" class="btn btn-sm btn-outline-secondary${e.se_puede_correr ? "" : " apagado"}">` +
      `<span class="h-nombre">${esc(nombreCorto(e))}${esX49(e) ? ' <span class="badge text-bg-warning rotulo">X-49</span>' : ""}</span>` +
      `<span class="h-estado ${s.clase}">${esc(s.texto)}</span></button></li>`;
  }).join("");
}

async function elegirHistorico(id, inicial) {
  const e = hev(id);
  if (!e) return;
  const cambio = H.elegido !== id;
  H.elegido = id;
  pintarListaHistoricos();
  pintarDetalleHistorico();
  if (cambio) {
    if (H.focosDe && eventoDe(S.corridas.find(c => c.id === H.focosDe)) !== id) H.focosDe = null;
    $("h-ver-cicatriz").checked = e.disponible && !inicial;
    $("h-ver-focos").checked = e.n_focos > 0 && !inicial;
    await verCicatriz($("h-ver-cicatriz").checked);
    await pintarFocos();
  }
  pintarResultadosHistoricos(true);
}

function pintarDetalleHistorico() {
  const e = hev(H.elegido);
  $("h-detalle").hidden = !e;
  if (!e) return;
  const x49 = esX49(e), r = e.recomendada;
  $("h-titulo").textContent = e.nombre || e.id;
  $("h-rotulos").innerHTML = `<span class="badge text-bg-light border rotulo">${esc(e.id)}</span>` +
    (x49 ? '<span class="badge text-bg-warning rotulo" title="Lote X-49: eventos que no se usaron para ajustar ningún parámetro">evento no visto (X-49): solo para mostrar</span>'
         : '<span class="badge text-bg-light border rotulo">visto</span>');
  const avisos = [];
  if (e.advertencia) avisos.push(`<div class="alert ${x49 ? "alert-warning" : "alert-light"} aviso">${x49 ? "<b>Evento no visto (X-49): solo para mostrar.</b>" : ""}${esc(limpiar(e.advertencia))}</div>`);
  if (!e.se_puede_correr && e.motivo) avisos.push(`<div class="alert alert-warning aviso"><b>No se puede correr en este clon.</b>${esc(e.motivo.split(":")[0])}.` +
    ((e.faltan || []).length ? `<details class="h-faltan"><summary>Qué falta (${e.faltan.length})</summary><ul>${e.faltan.map(f => `<li><code>${esc(f)}</code></li>`).join("")}</ul></details>` : "") + "</div>");
  if (e.se_puede_correr && (e.faltan_v40 || []).length) avisos.push(`<div class="alert alert-warning aviso"><b>A v4.0 le faltan los compuestos de verano.</b>Sin ellos el resultado de v4.0 cambia: ${e.faltan_v40.map(esc).join(", ")}.</div>`);
  if (r && /libre/.test(r.v40 || "")) avisos.push(`<div class="alert alert-warning aviso"><b>v4.0 con ignición libre.</b>${esc(limpiar(r.v40))}.</div>`);
  $("h-avisos").innerHTML = avisos.join("");
  const eval_ = (e.evaluacion_utc || []).map(t => aLocal(t).texto.slice(0, 10)).join(" · ");
  let ficha = `<dt>Cicatriz observada</dt><dd>${e.superficie_ha != null ? num(e.superficie_ha) + " ha" : "—"}</dd>` +
    `<dt>Focos VIIRS</dt><dd>${num(e.n_focos)} en ${num(e.n_pasadas)} pasadas</dd>`;
  if (r) {
    ficha += `<dt>Ignición recomendada</dt><dd>${esc(r.ignicion)}, hipótesis ${esc(r.hipotesis)}</dd>` +
      `<dt>Inicio</dt><dd>${aLocal(r.t_inicio_utc).texto} (hora argentina)</dd>` +
      (r.puntos || []).map((p, i) => `<dt>${(r.puntos.length > 1 ? `Foco ${i + 1}` : "Punto")}</dt><dd title="${esc(p.nombre)}">${num(p.lat, 4)}, ${num(p.lon, 4)}</dd>`).join("") +
      `<dt>Hasta el fin de la ficha</dt><dd>${num(r.horas_hasta_fin)} h</dd>`;
  }
  if (eval_) ficha += `<dt>Evaluación (00 h)</dt><dd>${eval_}</dd>`;
  if (e.fin_simulacion_utc) ficha += `<dt>Fin de la ficha</dt><dd>${aLocal(e.fin_simulacion_utc).texto}</dd>`;
  if (e.x49) ficha += `<dt>Fijado (X-49)</dt><dd title="ficha ${esc(e.x49.sha256_ficha)} · cicatriz ${esc(e.x49.sha256_cicatriz)}">${esc(e.x49.fijado)} · ficha ${esc(String(e.x49.sha256_ficha).slice(0, 8))}…</dd>`;
  $("h-ficha").innerHTML = ficha;
  $("h-ver-cicatriz").disabled = !e.disponible;
  $("h-ver-focos").disabled = !(e.n_focos > 0);

  $("h-correr").hidden = !e.se_puede_correr;
  if (e.se_puede_correr) {
    const hay = new Set(S.estado.motores.map(m => m.id));
    const antes = new Set([...$("h-motores").querySelectorAll("input:checked")].map(i => i.value));
    const motores = MOTORES_HISTORICO.filter(m => hay.has(m));
    $("h-motores").innerHTML = motores.map(m => `<label class="form-check small"><input class="form-check-input" type="checkbox" value="${m}"${(antes.size ? antes.has(m) : m !== "v4.0") ? " checked" : ""}>` +
      `<span><i class="marca" style="background:${MOTORES[m].color}"></i>${esc(MOTORES[m].largo)}${m === "v4.0" ? ' <span class="suave">(variante barreras)</span>' : ""}</span></label>`).join("");
    const h = $("h-horas");
    h.max = r.horas_hasta_fin;
    if (!h.value || Number(h.value) > r.horas_hasta_fin || h.dataset.evento !== e.id) h.value = r.horas_hasta_fin;
    h.dataset.evento = e.id;
    $("h-horas-nota").textContent = `(hasta ${num(r.horas_hasta_fin)}: el fin de la ficha)`;
  }

  const filas = e.cifras_documentadas || [];
  $("h-documentadas").hidden = !filas.length;
  if (filas.length) {
    $("h-doc-n").textContent = `(${filas.length} filas)`;
    const ref = H.referencia && H.referencia.evento === e.id ? H.referencia : null;
    $("h-doc-tabla").innerHTML = `<p class="form-text nota">Fuente: ${esc(ref?.fuente || "docs/v4.0/31 §7.2")}. Se pueden volver a correr con el pedido de cada fila.</p>` +
      `<div class="tabla-ancha"><table class="h-tabla"><thead><tr><th>#</th><th>Motor</th><th>Ignición</th><th>Hip.</th><th>Inicio</th>` +
      `<th title="IoU a igual superficie">IoU</th><th title="Horas hasta alcanzar la superficie de la cicatriz">h</th><th>A tiempo</th><th>Adel.</th><th>Atras.</th>` +
      `<th title="Error mediano de las primeras detecciones">Error</th><th>Puntaje</th><th>ha</th><th></th></tr></thead><tbody>` +
      filas.map(f => {
        const c = f.cifras || {};
        return `<tr title="${esc(`${f.variante} · ${f.horas} h · ${f.parada}${f.verificada ? " · verificada " + f.verificada : ""}`)}">` +
          `<td>${f.fila}</td><td class="izq">${esc(MOTORES[f.motor]?.nombre || f.motor)} <span class="suave">${esc(String(f.variante || "").split(" ")[0])}</span></td>` +
          `<td class="izq" title="${esc(f.ignicion_texto)}">${esc(f.ignicion)}</td><td>${esc(f.hipotesis)}</td><td>${aLocal(f.hora_utc).hora}</td>` +
          `<td>${frac(c.iou_igual_sup)}</td><td>${num(c.horas_hasta_sup, 1)}</td><td>${frac(c.frac_a_tiempo)}</td><td>${frac(c.frac_adelantado)}</td><td>${frac(c.frac_atrasado)}</td>` +
          `<td>${horasConSigno(c.error_mediano_h)}</td><td><b>${num(c.puntaje, 3)}</b></td><td>${num(c.ha_final)}</td>` +
          `<td>${f.regenerar?.cuerpo && e.se_puede_correr ? `<button class="btn btn-sm btn-outline-secondary py-0 chico" data-fila="${f.fila}" title="${esc(f.regenerar.pedido + " " + JSON.stringify(f.regenerar.cuerpo))}">Correr</button>` : ""}</td></tr>`;
      }).join("") + "</tbody></table></div>" +
      `<p class="form-text nota">Inicio en hora argentina. Puntaje = (IoU a igual superficie + fracción a tiempo) / 2.</p>` +
      (ref?.configuracion_por_defecto_del_simulador ? `<div class="alert alert-warning aviso"><b>La v4.0 del simulador no es la de la tabla.</b>${esc(ref.configuracion_por_defecto_del_simulador)}</div>` : "") +
      ((ref?.notas || []).length ? `<ul class="h-notas">${ref.notas.map(n => `<li>${esc(limpiar(n))}</li>`).join("")}</ul>` : "");
  }
}

// ---- capas: cicatriz y focos
async function verCicatriz(si) {
  if (H.cicatriz) { H.cicatriz.remove(); H.cicatriz = null; }
  const id = H.elegido, e = hev(id);
  if (si && e?.disponible) {
    try {
      const {capas} = await pedir(`/api/capas?evento=${encodeURIComponent(id)}`);
      const c = capas.find(x => x.id === "cicatriz");
      const url = c ? await contornoDe(c.url) : null;
      if (url && H.elegido === id && $("h-ver-cicatriz").checked && !H.cicatriz)
        H.cicatriz = L.imageOverlay(url, c.limites, {pane: "cicatriz", className: "cicatriz"}).addTo(S.mapa);
    } catch (x) { $("h-error").textContent = "No se pudo cargar la cicatriz: " + x.message; }
  }
  dibujarLeyenda();
}

// La cicatriz va encima de la huella simulada: se dibuja su borde (y un relleno tenue) para que se vean las dos.
const COLOR_CICATRIZ = [30, 58, 138];
async function contornoDe(url) {
  const img = new Image();
  img.src = url;
  await img.decode();
  const w = img.naturalWidth, h = img.naturalHeight, lienzo = document.createElement("canvas");
  lienzo.width = w; lienzo.height = h;
  const cx = lienzo.getContext("2d");
  cx.drawImage(img, 0, 0);
  const a = cx.getImageData(0, 0, w, h), d = a.data, out = cx.createImageData(w, h), o = out.data;
  const dentro = (x, y) => x >= 0 && y >= 0 && x < w && y < h && d[(y * w + x) * 4 + 3] > 0;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (!dentro(x, y)) continue;
    const borde = !dentro(x - 1, y) || !dentro(x + 1, y) || !dentro(x, y - 1) || !dentro(x, y + 1);
    const i = (y * w + x) * 4;
    [o[i], o[i + 1], o[i + 2]] = COLOR_CICATRIZ; o[i + 3] = borde ? 255 : 55;
  }
  cx.putImageData(out, 0, 0);
  return lienzo.toDataURL("image/png");
}

async function pintarFocos() {
  const id = H.elegido, e = hev(id), si = $("h-ver-focos").checked && e?.n_focos > 0;
  const de = H.focosDe && H.metricas[H.focosDe]?.estado === "lista" ? H.focosDe : null;
  const clave = si ? `${id}|${de || ""}` : null;
  if (clave === H.focosClave) return;
  const turno = ++H.turnoFocos;
  if (H.focos) { H.focos.remove(); H.focos = null; }
  H.focosClave = null; H.focosLeyenda = null;
  $("h-focos-de").textContent = "";
  if (!si) return void dibujarLeyenda();
  let fc;
  try { fc = await pedir(`/api/historicos/${encodeURIComponent(id)}/focos.geojson${de ? `?corrida=${encodeURIComponent(de)}` : ""}`); }
  catch (x) { $("h-error").textContent = "No se pudieron cargar los focos: " + x.message; return; }
  if (turno !== H.turnoFocos) return;
  const conClase = !!fc.clase_por_foco, n = fc.n_pasadas;
  H.focos = L.geoJSON(fc, {
    pane: "focos",
    pointToLayer: (f, ll) => {
      const p = f.properties, cl = conClase ? CLASES[p.clase_pasada] : null;
      return L.circleMarker(ll, {pane: "focos", radius: p.primera ? 5.5 : 3.5, color: cl ? "#fff" : "#1c1b19", weight: p.primera ? 2 : 1,
                                 fillColor: cl ? cl.color : COLOR_SIN_CLASE, fillOpacity: 0.95});
    },
    onEachFeature: (f, capa) => {
      const p = f.properties;
      let t = `<b>Foco VIIRS</b> · pasada ${p.pasada} de ${n}<br>${aLocal(p.t_det_utc).texto} (hora argentina) · ${esc(p.sat)} · ${num(p.frp, 1)} MW` +
        (p.daynight === "0" || p.daynight === "N" ? " · de noche" : "");
      if (conClase) {
        if (p.clase_pasada) t += `<br>Pasada: <b>${CLASES[p.clase_pasada].corto || CLASES[p.clase_pasada].nombre}</b>` +
          (p.pasada_cuenta ? ` (${num(p.pasada_cuenta.a_tiempo)} a tiempo de ${num(p.pasada_cuenta.n_primeras)} primeras)` : "");
        else t += "<br>Pasada sin primeras detecciones";
        if (p.primera) t += `<br>Primera detección: ${CLASES[p.clase]?.corto || CLASES[p.clase]?.nombre || "—"}` +
          (p.error_h != null && p.clase !== "a_tiempo" ? `, error ${horasConSigno(p.error_h)}` : "") +
          (p.t_sim_h != null ? ` · el fuego simulado llega a la hora ${num(p.t_sim_h, 1)}` : "");
      }
      capa.bindTooltip(t, {sticky: true});
    },
  }).addTo(S.mapa);
  H.focosClave = clave;
  const c = de && S.corridas.find(x => x.id === de);
  H.focosLeyenda = {conClase, corrida: de ? (MOTORES[c?.motor]?.nombre || de) : null};
  $("h-focos-de").textContent = de ? `(clasificados con ${H.focosLeyenda.corrida})` : "(sin clasificar)";
  dibujarLeyenda();
}

function bloquesLeyendaHistorico() {
  const b = [];
  if (H.cicatriz) b.push(`<h3>Modo histórico</h3><div class="item"><i style="background:rgba(${COLOR_CICATRIZ},.22);border:2px solid rgb(${COLOR_CICATRIZ})"></i>Cicatriz observada</div>`);
  if (H.focos && H.focosLeyenda) {
    const l = H.focosLeyenda;
    let h = `<h3>Focos VIIRS${l.conClase ? ` por pasada · ${esc(l.corrida)}` : ""}</h3>`;
    if (l.conClase) {
      h += Object.values(CLASES).map(c => `<div class="item"><i class="punto" style="background:${c.color}"></i>${c.nombre}</div>`).join("") +
        `<div class="item"><i class="punto" style="background:${COLOR_SIN_CLASE};border-color:#1c1b19"></i>pasada sin primeras detecciones</div>` +
        '<div class="item suave">Punto grande: primera detección del lugar</div>';
    } else h += `<div class="item"><i class="punto" style="background:${COLOR_SIN_CLASE};border-color:#1c1b19"></i>foco (sin clasificar: falta una corrida con métricas)</div>`;
    b.push(h);
  }
  return b;
}

// ---- lanzar
async function correrHistorico() {
  $("h-error").textContent = "";
  const e = hev(H.elegido);
  if (!e?.se_puede_correr) return;
  const motores = [...$("h-motores").querySelectorAll("input:checked")].map(i => i.value);
  const horas = Number($("h-horas").value), max = e.recomendada.horas_hasta_fin;
  if (!motores.length || motores.length > 3) return void ($("h-error").textContent = "Elegí de uno a tres motores.");
  if (!(Number.isInteger(horas) && horas >= 1 && horas <= max)) return void ($("h-error").textContent = `Las horas van de 1 a ${num(max)} (el fin de la ficha).`);
  if (!puedeLanzarOtra()) return;
  const cuerpo = {motores, iniciar: true};
  if (horas !== max) cuerpo.horas = horas;
  $("h-iniciar").disabled = true;
  try {
    const r = await pedir(`/api/historicos/${encodeURIComponent(e.id)}/corrida`, cuerpo);
    if (r.historico) H.eventos = H.eventos.map(x => x.id === r.historico.id ? r.historico : x);
    await mostrarCorridaHistorica(r.corridas, e);
  } catch (x) { $("h-error").textContent = x.message; }
  $("h-iniciar").disabled = false;
}

async function correrFila(n, boton) {
  $("h-error").textContent = "";
  const e = hev(H.elegido), f = (e?.cifras_documentadas || []).find(x => x.fila === n);
  if (!f?.regenerar?.cuerpo || !puedeLanzarOtra()) return;
  if (f.horas > 72 && f.motor === "v4.0" && !confirm(`La fila ${n} es v4.0 ${f.variante} a ${f.horas} h: puede tardar bastante. ¿Correrla?`)) return;
  boton.disabled = true;
  const ruta = String(f.regenerar.pedido || "").replace(/^POST\s+/, "").replace("<evento>", encodeURIComponent(e.id)) || "/api/corridas";
  try {
    const r = await pedir(ruta.startsWith("/api/") ? ruta : "/api/corridas", f.regenerar.cuerpo);
    if (r.historico) H.eventos = H.eventos.map(x => x.id === r.historico.id ? r.historico : x);
    await mostrarCorridaHistorica(r.corridas, e);
  } catch (x) { $("h-error").textContent = `Fila ${n}: ${x.message}`; }
  boton.disabled = false;
}

function puedeLanzarOtra() {
  if (S.corridas.some(c => !FINALES.includes(c.estado))) {
    $("h-error").textContent = "Hay una simulación en marcha en la pantalla: esperá a que termine o detenela.";
    return false;
  }
  return descartarBorradores("correr el evento histórico");
}

async function mostrarCorridaHistorica(corridas, e) {
  if (S.estado.eventos_base.some(x => x.id === e.id) && $("evento").value !== e.id) {
    $("evento").value = e.id;
    proponerEvento();
    await cargarCapas();
  }
  if ((e.recomendada?.puntos || []).length) ponerFocos(e.recomendada.puntos);
  seguir(corridas, {motor: corridas.length === 1 ? corridas[0].motor : "historico"});
  seccion("c-historico", true);
  $("sec-historico").scrollIntoView({block: "start", behavior: "smooth"});
}

// ---- métricas de v3.1 por corrida
const eventoDe = c => c?.pedido?.historico?.evento || c?.pedido?.evento || c?.pedido?.definicion?.evento || null;

function vigilarMetricas(c) {
  const e = hev(eventoDe(c));
  if (!e || !e.disponible || c.motor === "simulado" || H.sondeos[c.id]) return;
  const m = H.metricas[c.id];
  if (m && ["lista", "error", "no_aplica"].includes(m.estado)) return;
  H.sondeos[c.id] = true;
  const vuelta = async () => {
    if (!S.corridas.some(x => x.id === c.id)) return void delete H.sondeos[c.id];
    let espera = 2000;
    try {
      const r = await fetch(`/api/corridas/${encodeURIComponent(c.id)}/metricas_v31`, {cache: "no-store"});
      const d = await r.json().catch(() => ({}));
      if (r.status === 404) H.metricas[c.id] = {estado: "no_aplica", motivo: typeof d.detail === "string" ? d.detail : "sin métricas"};
      else if (r.ok) H.metricas[c.id] = {estado: d.estado, motivo: d.motivo, datos: d.metricas_v31};
      else { H.metricas[c.id] = {estado: "fallo", motivo: d.detail || `error ${r.status}`}; espera = 5000; }
    } catch (x) { espera = 5000; }
    const m2 = H.metricas[c.id];
    if (m2?.estado === "lista" && !H.focosDe && eventoDe(c) === H.elegido) { H.focosDe = c.id; $("h-ver-focos").checked = true; pintarFocos(); }
    pintarResultadosHistoricos();
    if (m2 && ["lista", "error", "no_aplica"].includes(m2.estado)) return void delete H.sondeos[c.id];
    if (!m2 || m2.estado === "esperando_fin") espera = FINALES.includes(c.estado) ? 1500 : 4000;
    setTimeout(vuelta, espera);
  };
  vuelta();
}

function filaDocumentada(c, met) {
  const e = hev(met?.evento || eventoDe(c)), ig = met?.ignicion || {};
  const filas = (e?.cifras_documentadas || []).filter(f => f.motor === c.motor && f.ignicion === ig.ignicion && Number(f.hipotesis) === Number(ig.hipotesis) &&
    (!met?.t_inicio_utc || new Date(normalizarUTC(f.hora_utc)).getTime() === new Date(normalizarUTC(met.t_inicio_utc)).getTime()));
  if (!filas.length) return null;
  const def = JSON.stringify(c.pedido?.definicion || null);
  const igual = filas.find(f => JSON.stringify(f.regenerar?.cuerpo?.definicion || null) === def);
  return {fila: igual || filas[0], misma: !!igual};
}

const FILAS_METRICAS = [
  ["iou_igual_sup", "IoU a igual superficie", v => num(v, 3)],
  ["horas_hasta_sup", "Horas hasta la superficie", v => v == null ? "—" : num(v, 1) + " h"],
  ["frac_a_tiempo", "A tiempo", frac],
  ["frac_adelantado", "Adelantado", frac],
  ["frac_atrasado", "Atrasado", frac],
  ["frac_no_alcanzado", "No alcanzado", frac],
  ["error_mediano_h", "Error mediano", horasConSigno],
  ["puntaje", "Puntaje", v => v == null ? "—" : `<b>${num(v, 3)}</b>`],
  ["ha_final", "Superficie al final", v => v == null ? "—" : num(v) + " ha"],
];

function htmlMetricas(c) {
  const m = H.metricas[c.id], nombre = MOTORES[c.motor]?.nombre || c.motor;
  let h = `<div class="tarjeta h-metricas"><header><span class="marca" style="background:${c.color}"></span><span class="nombre">${esc(nombre)}</span>` +
    `<span class="estado">${esc(estadoMetricas(c, m))}</span></header>`;
  if (!m || !["lista", "error"].includes(m.estado)) {
    if (m?.estado === "no_aplica" || m?.estado === "fallo") h += `<p class="linea">${esc(m.motivo)}</p>`;
    return h + "</div>";
  }
  if (m.estado === "error" || !m.datos || m.datos.error) return h + `<p class="text-danger small error">${esc(m.datos?.error || m.motivo || "El evaluador dio error.")}</p></div>`;
  const d = m.datos, x = d.metricas || {}, ig = d.ignicion || {}, doc = filaDocumentada(c, d), fd = doc?.fila, cd = fd?.cifras || {};
  h += `<p class="linea">${esc(ig.ignicion || "")}${ig.hipotesis != null ? `, hipótesis ${esc(ig.hipotesis)}` : ""} · inicio ${aLocal(normalizarUTC(d.t_inicio_utc)).texto}` +
    ` · ${num((d.t_simulado_min || 0) / 60, 1)} h simuladas</p>`;
  h += `<div class="tabla-ancha"><table class="h-tabla h-comparada"><thead><tr><th class="izq">Métrica</th><th>Esta corrida</th>` +
    (fd ? `<th title="${esc(`${fd.variante} · ${fd.horas} h · ${fd.parada}`)}">Documentada<br><span class="suave">fila ${fd.fila}${doc.misma ? "" : " · otra config."}</span></th>` : "") +
    `</tr></thead><tbody>`;
  for (const [k, titulo, f] of FILAS_METRICAS) {
    if (k === "frac_no_alcanzado" && !x[k] && !cd[k]) continue;
    const marca = k === "iou_igual_sup" && x.alcanza_sup === false ? ' <span class="marca-aviso" title="No alcanza la superficie de la cicatriz">*</span>' : "";
    h += `<tr><td class="izq">${titulo}</td><td>${f(x[k])}${marca}</td>${fd ? `<td>${k in cd ? f(cd[k]) : "—"}</td>` : ""}</tr>`;
  }
  h += "</tbody></table></div>";
  h += `<p class="form-text nota">${num(x.n_primeras)} primeras detecciones${d.error_absoluto_medio_h != null ? ` · error absoluto medio ${num(d.error_absoluto_medio_h, 1)} h` : ""}.</p>`;
  if (x.alcanza_sup === false) h += `<div class="alert alert-warning aviso"><b>* No alcanza la superficie de la cicatriz.</b>La simulación quemó menos que lo observado (${num(x.ha_final)} ha contra ${num(d.referencia?.ha_ref_valida)} ha): la IoU es con la huella final, no a igual superficie, y las horas son las del final.</div>`;
  if (fd && !doc.misma) h += `<div class="alert alert-warning aviso"><b>La fila ${fd.fila} es otra configuración.</b>${esc(fd.variante)}, ${esc(fd.horas)} h, ${esc(fd.parada)}. Esta corrida usa ${c.pedido?.definicion ? esc(JSON.stringify(c.pedido.definicion)) : "la configuración de la app"}: no se espera que coincidan.</div>`;
  else if (fd) {
    const tol = k => k === "ha_final" ? 1 : k.endsWith("_h") || k === "horas_hasta_sup" ? 0.051 : 0.0051;
    const distintas = FILAS_METRICAS.filter(([k]) => k in cd && x[k] != null && !(Math.abs(Number(x[k]) - Number(cd[k])) <= tol(k)));
    const hSim = (d.t_simulado_min || 0) / 60, masCorta = hSim < Number(fd.horas) - 1e-6;
    h += !distintas.length ? `<p class="linea bien">Coincide con la fila ${fd.fila} documentada (con su redondeo).</p>`
      : distintas.length === 1 && distintas[0][0] === "ha_final" && masCorta
        ? `<p class="linea bien">Coincide con la fila ${fd.fila} salvo la superficie final: esta corrida simuló ${num(hSim, 1)} h y la fila, ${num(fd.horas)} h.</p>`
        : `<p class="linea">Difiere de la fila ${fd.fila} documentada en: ${distintas.map(([, t]) => t.toLowerCase()).join(", ")}${masCorta ? ` (esta corrida simuló ${num(hSim, 1)} h; la fila, ${num(fd.horas)} h)` : ""}.</p>`;
  }
  const inst = d.por_instante || [];
  if (inst.length) {
    h += `<h4>IoU en cada instante de evaluación</h4><div class="tabla-ancha"><table class="h-tabla"><thead><tr><th class="izq">Instante</th><th>h</th><th>IoU</th><th>ha sim.</th><th>ha obs.</th></tr></thead><tbody>` +
      inst.map(i => `<tr class="${i.despues_del_fin ? "despues" : ""}${i.antes_de_la_ignicion ? " antes" : ""}"><td class="izq">${aLocal(normalizarUTC(i.t_eval_utc)).texto.slice(0, 10)}` +
        `${i.despues_del_fin ? '<br><span class="badge text-bg-warning rotulo" title="Posterior al fin de la corrida: la huella ya no cambia">después del fin</span>' : ""}` +
        `${i.antes_de_la_ignicion ? '<br><span class="badge text-bg-light border rotulo">antes de la ignición</span>' : ""}</td>` +
        `<td>${num(i.horas_desde_ignicion, 0)}</td><td>${num(i.iou, 3)}</td><td>${num(i.ha_sim)}</td><td>${num(i.ha_ref)}</td></tr>`).join("") + "</tbody></table></div>";
    if (inst.some(i => i.despues_del_fin)) h += `<p class="form-text nota">«Después del fin»: el instante cae después de la última hora simulada (${num((d.t_simulado_min || 0) / 60, 1)} h); se compara la huella congelada del final.</p>`;
  }
  const pp = d.por_pasada || [];
  if (pp.length) {
    h += `<details class="h-pasadas"><summary>Primeras detecciones por pasada (${pp.length})</summary><div class="tabla-ancha"><table class="h-tabla"><thead><tr><th class="izq">Pasada</th><th>n</th>` +
      `<th title="a tiempo"><i class="punto" style="background:${CLASES.a_tiempo.color}"></i></th><th title="adelantado"><i class="punto" style="background:${CLASES.adelantado.color}"></i></th>` +
      `<th title="atrasado"><i class="punto" style="background:${CLASES.atrasado.color}"></i></th><th title="no alcanzado"><i class="punto" style="background:${CLASES.no_alcanzado.color}"></i></th><th>Error</th></tr></thead><tbody>` +
      pp.map(p => `<tr><td class="izq">${aLocal(normalizarUTC(p.t_det_utc)).texto}</td><td>${num(p.n)}</td><td>${num(p.a_tiempo)}</td><td>${num(p.adelantado)}</td><td>${num(p.atrasado)}</td><td>${num(p.no_alcanzado)}</td><td>${horasConSigno(p.error_mediano_h)}</td></tr>`).join("") +
      "</tbody></table></div></details>";
  }
  for (const a of d.avisos || []) h += `<p class="form-text nota">${esc(a)}</p>`;
  const cod = Object.values(d.evaluador?.codigo || {}), intacto = cod.length && cod.every(v => v.igual_al_congelado);
  h += `<p class="form-text nota evaluador" title="${esc(Object.entries(d.evaluador?.codigo || {}).map(([k, v]) => `${k}: ${v.sha256}`).join("\n"))}">${esc(d.evaluador?.rotulo || "")}` +
    `${cod.length ? (intacto ? " · código igual al congelado" : ' · <b class="mal">el código del evaluador no es el congelado</b>') : ""}</p>`;
  return h + "</div>";
}

function estadoMetricas(c, m) {
  if (!m) return FINALES.includes(c.estado) ? "pidiendo las métricas…" : "las métricas se calculan al terminar";
  return {lista: "métricas listas", error: "el evaluador dio error", esperando_fin: "las métricas se calculan al terminar", pendiente: "métricas en espera…",
          calculando: "calculando las métricas…", no_aplica: "sin métricas", fallo: "no se pudieron pedir"}[m.estado] || m.estado;
}

function pintarResultadosHistoricos(forzar) {
  const cs = S.corridas.filter(c => hev(eventoDe(c)) && c.motor !== "simulado");
  const firma = JSON.stringify([H.elegido, H.focosDe, cs.map(c => [c.id, c.estado === "terminada" || FINALES.includes(c.estado), H.metricas[c.id]?.estado])]);
  if (!forzar && firma === H.firma) return;
  H.firma = firma;
  const caja = $("h-resultados");
  caja.hidden = !cs.length;
  if (!cs.length) return;
  // corridas nuevas del modo histórico en pantalla: se abre la sección una vez (no con una corrida común sobre un ejemplo)
  const ids = cs.filter(c => c.pedido?.historico).map(c => c.id).join(",");
  if (ids && ids !== H.abiertaPara) { H.abiertaPara = ids; seccion("c-historico", true); }
  const e = hev(eventoDe(cs[0])), x49 = cs.some(c => esX49(hev(eventoDe(c))));
  const listas = cs.filter(c => H.metricas[c.id]?.estado === "lista");
  let h = `<h3>Métricas contra lo observado</h3>`;
  if (x49) h += '<p><span class="badge text-bg-warning rotulo">evento no visto (X-49): solo para mostrar</span></p>';
  if (e && e.id !== H.elegido) h += `<p class="form-text nota">Corridas de ${esc(nombreCorto(e))}. <button class="btn btn-link btn-sm p-0 align-baseline" data-evento-ver="${esc(e.id)}">Ver ese evento</button></p>`;
  h += `<p class="form-text nota"><b>Puntaje = (IoU a igual superficie + fracción a tiempo) / 2.</b> La IoU se mide cuando la simulación llega a la superficie de la cicatriz. ` +
    `Un foco está a tiempo si el fuego simulado llega a menos de ${num(listas[0] ? H.metricas[listas[0].id].datos.referencia?.tolerancia_m ?? 375 : 375)} m ` +
    `entre ${num(listas[0] ? H.metricas[listas[0].id].datos.referencia?.ventana_h ?? 13 : 13)} h antes y 1 h después de su primera detección; adelantado si llega antes, atrasado si llega después. Error negativo: el modelo llega antes.</p>`;
  if (listas.length) h += `<label class="form-label small mb-1" for="h-focos-corrida">Colorear los focos según</label><select class="form-select form-select-sm" id="h-focos-corrida">` +
    listas.map(c => `<option value="${esc(c.id)}"${c.id === H.focosDe ? " selected" : ""}>${esc(MOTORES[c.motor]?.nombre || c.motor)}</option>`).join("") + "</select>";
  h += cs.map(htmlMetricas).join("");
  caja.innerHTML = h;
  const b = caja.querySelector("[data-evento-ver]");
  if (b) b.onclick = () => elegirHistorico(b.dataset.eventoVer);
}

arrancar().catch(e => { $("error").textContent = "No se pudo hablar con el servidor: " + e.message; });
