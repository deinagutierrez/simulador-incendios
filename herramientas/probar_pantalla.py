"""Prueba de humo de la pantalla en un navegador de verdad (F6, D-E3-30 punto 16). Fuera de la integración continua: se corre
a mano en la máquina de cada persona.

    python herramientas/probar_pantalla.py
    python herramientas/probar_pantalla.py --navegador "C:/Program Files/Google/Chrome/Application/chrome.exe"
    python herramientas/probar_pantalla.py --capturas capturas_pantalla      guarda una captura por paso
    python herramientas/probar_pantalla.py --con-ventana                      muestra el navegador mientras prueba

Levanta `app/servir.py --con-simulado` en un puerto libre y maneja Chromium, Chrome o Edge (sin ventana) por su protocolo de
depuración, con un cliente WebSocket mínimo hecho con la biblioteca estándar: no hace falta Playwright ni Selenium. Recorre,
con el motor simulado (un fuego de mentira, sin los motores reales):

  1. cargar la pantalla;
  2. marcar la ignición con un clic en el mapa;
  3. correr 6 h;
  4. pausar (en la hora 3);
  5. dibujar un cortafuego a mano alzada y aplicarlo;
  6. reanudar hasta el final;
  7. exportar (el zip de la corrida).

Falla si un paso no se cumple o si hubo errores en la consola del navegador (excepciones, `console.error`, recursos que no
cargaron). Las advertencias se listan pero no hacen fallar. Las corridas del motor simulado quedan en `resultados/app/`
(no se versiona). No usa internet (el mapa en línea queda apagado).

Códigos de salida: 0 todo bien; 1 falló algún paso o hubo errores en la consola; 2 no se encontró el navegador o no arrancó.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HORAS = 6
PAUSA_EN = 3
S_POR_HORA = 0.5           # el motor simulado va lento para que la pausa caiga donde se pidió

NOMBRES = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "microsoft-edge",
           "microsoft-edge-stable", "msedge"]


def rutas_comunes() -> list[Path]:
    """Lugares donde suele estar el navegador en Windows, Linux y macOS."""
    out = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            out += [Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                    Path(base) / "Chromium" / "Application" / "chrome.exe",
                    Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"]
    out += [Path(p) for p in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
                              "/usr/bin/google-chrome-stable", "/snap/bin/chromium", "/usr/bin/microsoft-edge",
                              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                              "/Applications/Chromium.app/Contents/MacOS/Chromium")]
    return out


def buscar_navegador(pedido: str | None) -> Path | None:
    if pedido:
        p = Path(pedido)
        return p if p.is_file() else (Path(shutil.which(pedido)) if shutil.which(pedido) else None)
    if os.environ.get("NAVEGADOR_PRUEBAS"):
        return buscar_navegador(os.environ["NAVEGADOR_PRUEBAS"])
    for nombre in NOMBRES:
        encontrado = shutil.which(nombre)
        if encontrado:
            return Path(encontrado)
    return next((p for p in rutas_comunes() if p.is_file()), None)


# ------------------------------------------------------------------ cliente mínimo del protocolo de depuración (CDP)
class CDP:
    """WebSocket a mano (RFC 6455, solo texto, sin extensiones) y llamadas JSON del protocolo de depuración."""

    def __init__(self, ws_url: str, tope_s: float = 30.0):
        if not ws_url.startswith("ws://"):
            raise ValueError(f"dirección de depuración inesperada: {ws_url}")
        hostport, ruta = ws_url[5:].split("/", 1)
        host, puerto = hostport.rsplit(":", 1)
        self.s = socket.create_connection((host, int(puerto)), timeout=tope_s)
        clave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{ruta} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {clave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            d = self.s.recv(4096)
            if not d:
                raise ConnectionError("el navegador cerró la conexión de depuración")
            buf += d
        cabecera, self.buf = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in cabecera.split(b"\r\n")[0]:
            raise ConnectionError(f"el navegador rechazó la conexión de depuración: {cabecera[:200]!r}")
        self.n = 0
        self.eventos: list[dict] = []

    def _enviar(self, texto: str) -> None:
        datos = texto.encode("utf-8")
        mascara = os.urandom(4)
        n = len(datos)
        if n < 126:
            cab = bytes([0x81, 0x80 | n])
        elif n < 65536:
            cab = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        else:
            cab = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(cab + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(datos)))

    def _leer(self, n: int) -> bytes:
        while len(self.buf) < n:
            d = self.s.recv(1 << 20)
            if not d:
                raise ConnectionError("el navegador cerró la conexión de depuración")
            self.buf += d
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _mensaje(self) -> dict:
        partes = b""
        while True:
            b0, b1 = self._leer(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._leer(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._leer(8))[0]
            datos = self._leer(n)
            codigo = b0 & 0x0F
            if codigo == 0x8:
                raise ConnectionError("el navegador cerró la conexión de depuración")
            if codigo in (0x9, 0xA):                 # ping / pong: no traen mensajes
                continue
            partes += datos
            if b0 & 0x80:
                return json.loads(partes.decode("utf-8"))

    def llamar(self, metodo: str, **params) -> dict:
        self.n += 1
        mi = self.n
        self._enviar(json.dumps({"id": mi, "method": metodo, "params": params}))
        while True:
            m = self._mensaje()
            if m.get("id") == mi:
                if "error" in m:
                    raise RuntimeError(f"{metodo}: {m['error']}")
                return m.get("result", {})
            self.eventos.append(m)

    def evaluar(self, expr: str):
        r = self.llamar("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError(f"JavaScript: {(d.get('exception') or {}).get('description') or d.get('text')}")
        return r["result"].get("value")

    def esperar(self, expr: str, que: str, tope_s: float = 60.0, paso_s: float = 0.2):
        limite = time.monotonic() + tope_s
        while True:
            v = self.evaluar(expr)
            if v:
                return v
            if time.monotonic() > limite:
                raise Falla(f"no se cumplió en {tope_s:g} s: {que}")
            time.sleep(paso_s)

    def cerrar(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass


class Falla(Exception):
    """Un paso de la prueba que no se cumplió."""


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ servidor y navegador
def levantar_servidor(registro: Path) -> tuple[subprocess.Popen, str]:
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    entorno.pop("PYTHONPATH", None)
    salida = open(registro, "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen([sys.executable, str(RAIZ / "app" / "servir.py"), "--sin-navegador", "--con-simulado",
                          "--puerto", str(puerto_libre())], cwd=RAIZ, env=entorno, stdout=salida, stderr=subprocess.STDOUT)
    salida.close()
    limite = time.monotonic() + 60
    base = None
    while time.monotonic() < limite:
        if p.poll() is not None:
            raise Falla(f"el servidor no arrancó (código {p.returncode}); ver {registro}")
        texto = registro.read_text(encoding="utf-8", errors="replace")
        if base is None and "Simulador en " in texto:
            base = texto.split("Simulador en ", 1)[1].split()[0]
        if base:
            try:
                with urllib.request.urlopen(base + "/api/estado", timeout=5) as r:
                    if r.status == 200:
                        return p, base
            except OSError:
                pass
        time.sleep(0.2)
    p.kill()
    raise Falla(f"el servidor no respondió en 60 s; ver {registro}")


def lanzar_navegador(ruta: Path, perfil: Path, con_ventana: bool, registro: Path) -> tuple[subprocess.Popen, int]:
    args = [str(ruta), "--remote-debugging-port=0", f"--user-data-dir={perfil}", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--disable-background-networking",
            "--disable-component-update", "--disable-sync", "--window-size=1440,950"]
    if not con_ventana:
        args += ["--headless=new", "--disable-gpu"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")                    # Chromium no arranca como root con el aislamiento puesto
    args.append("about:blank")
    salida = open(registro, "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(args, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    salida.close()
    archivo = perfil / "DevToolsActivePort"           # el navegador escribe acá el puerto que eligió
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        if p.poll() is not None:
            raise OSError(f"el navegador terminó al arrancar (código {p.returncode}); ver {registro}")
        if archivo.exists():
            lineas = archivo.read_text(encoding="utf-8", errors="replace").split()
            if lineas and lineas[0].isdigit():
                return p, int(lineas[0])
        time.sleep(0.1)
    p.kill()
    raise OSError(f"el navegador no abrió el puerto de depuración en 30 s; ver {registro}")


def pagina(puerto: int) -> str:
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/json/list", timeout=5) as r:
                for t in json.load(r):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return t["webSocketDebuggerUrl"]
        except OSError:
            pass
        time.sleep(0.1)
    raise OSError("el navegador no tiene ninguna pestaña para manejar")


def cerrar_proceso(p: subprocess.Popen | None) -> None:
    if p is None or p.poll() is not None:
        return
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(10)


# ------------------------------------------------------------------ el recorrido
class Recorrido:
    def __init__(self, b: CDP, base: str, capturas: Path | None):
        self.b = b
        self.base = base
        self.capturas = capturas
        self.n_captura = 0

    def paso(self, texto: str) -> None:
        print(f"  · {texto}", flush=True)

    def captura(self, nombre: str) -> None:
        if not self.capturas:
            return
        self.n_captura += 1
        d = self.b.llamar("Page.captureScreenshot", format="png")["data"]
        (self.capturas / f"{self.n_captura}_{nombre}.png").write_bytes(base64.b64decode(d))

    def clic(self, selector: str) -> None:
        ok = self.b.evaluar(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e || e.disabled) return false;"
                            " e.click(); return true; })()")
        if not ok:
            raise Falla(f"no se encontró o está deshabilitado: {selector}")

    def punto(self, lat: float, lon: float) -> tuple[float, float]:
        return tuple(self.b.evaluar(
            f"(() => {{ const p = S.mapa.latLngToContainerPoint([{lat}, {lon}]); const r = S.mapa.getContainer()"
            ".getBoundingClientRect(); return [p.x + r.left, p.y + r.top]; })()"))

    def raton(self, tipo: str, x: float, y: float, botones: int = 0, **extra) -> None:
        self.b.llamar("Input.dispatchMouseEvent", type=tipo, x=x, y=y, buttons=botones, **extra)

    def clic_mapa(self, lat: float, lon: float) -> None:
        x, y = self.punto(lat, lon)
        self.raton("mouseMoved", x, y)
        self.raton("mousePressed", x, y, 1, button="left", clickCount=1)
        self.raton("mouseReleased", x, y, 0, button="left", clickCount=1)
        time.sleep(0.3)

    def trazo(self, puntos: list[tuple[float, float]], pasos: int = 12) -> None:
        """Arrastre del ratón (eventos reales del puntero) por los puntos [lat, lon]."""
        xy = [self.punto(*p) for p in puntos]
        self.raton("mouseMoved", *xy[0])
        self.raton("mousePressed", *xy[0], 1, button="left", clickCount=1)
        for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
            for k in range(1, pasos + 1):
                self.raton("mouseMoved", x0 + (x1 - x0) * k / pasos, y0 + (y1 - y0) * k / pasos, 1, button="left")
        self.raton("mouseReleased", *xy[-1], 0, button="left", clickCount=1)
        time.sleep(0.3)

    def correr(self) -> dict:
        b = self.b
        res: dict = {}
        b.llamar("Runtime.enable")
        b.llamar("Log.enable")
        b.llamar("Page.enable")
        b.llamar("Emulation.setDeviceMetricsOverride", width=1440, height=950, deviceScaleFactor=1, mobile=False)

        self.paso("1. cargar la pantalla")
        b.llamar("Page.navigate", url=self.base + "/")
        b.esperar("typeof S !== 'undefined' && !!S.estado && !!S.mapa && document.querySelectorAll('#motor option').length > 0 "
                  "&& document.querySelectorAll('#hora option').length > 0", "la pantalla terminó de cargar", 60)
        time.sleep(1.0)
        if not b.evaluar("[...document.querySelectorAll('#motor option')].some(o => o.value === 'simulado')"):
            raise Falla("el motor simulado no aparece en la lista (¿el servidor no se levantó con --con-simulado?)")
        if b.evaluar("$('en-linea').checked"):
            b.evaluar("$('en-linea').checked = false; mapaEnLinea()")
        self.captura("cargada")

        self.paso("2. marcar la ignición con un clic en el mapa")
        (sur, oeste), (norte, este) = b.evaluar("S.estado.dominio.limites")
        lat0 = float(b.evaluar("Number($('lat').value) || 0")) or (sur + norte) / 2
        lon0 = float(b.evaluar("Number($('lon').value) || 0")) or (oeste + este) / 2
        lat, lon = lat0 + 0.002, lon0 + 0.002
        b.evaluar(f"void S.mapa.setView([{lat}, {lon}], 14, {{animate: false}})")
        time.sleep(0.5)
        self.clic_mapa(lat, lon)
        marcado = b.evaluar("[Number($('lat').value), Number($('lon').value), !!S.marcador]")
        if not (marcado[2] and abs(marcado[0] - lat) < 2e-4 and abs(marcado[1] - lon) < 2e-4):
            raise Falla(f"el clic en el mapa no marcó la ignición en {lat:.5f}, {lon:.5f} (quedó {marcado})")
        res["ignicion"] = marcado[:2]

        self.paso(f"3. correr {HORAS} h con el motor simulado")
        b.evaluar("$('motor').value = 'simulado'; $('motor').dispatchEvent(new Event('change'))")
        b.evaluar(f"$('horas').value = '{HORAS}'; $('horas').dispatchEvent(new Event('input'))")
        # el motor simulado va más lento solo en esta prueba: se agrega `simulado` al pedido que arma la pantalla
        b.evaluar("(() => { const f = window.fetch; window.fetch = (u, o) => {"
                  " if (u === '/api/corridas' && o && o.method === 'POST') { const c = JSON.parse(o.body);"
                  f" c.simulado = {{s_por_hora: {S_POR_HORA}}}; o = {{...o, body: JSON.stringify(c)}}; window.ultimoPedido = c; }}"
                  " return f(u, o); }; })()")
        self.captura("configurada")
        self.clic("#iniciar")
        b.esperar("S.corridas.length === 1 && ['corriendo', 'pausando', 'pausada'].includes(S.corridas[0].estado)",
                  "la corrida arrancó", 30, 0.05)
        error = b.evaluar("$('error').textContent")
        if error:
            raise Falla(f"la pantalla mostró un error al iniciar: {error}")

        self.paso(f"4. pausar en la hora {PAUSA_EN}")
        b.evaluar(f"$('pausar-en').value = '{PAUSA_EN}'")
        self.clic("#pausar")
        b.esperar("S.corridas[0].estado === 'pausada'", "la corrida quedó en pausa", 60)
        b.esperar("!$('intervenir').hidden", "apareció el panel para intervenir", 20)
        res["pausa_t_sim_min"] = b.evaluar("S.corridas[0].pausaT")
        time.sleep(0.5)
        horas_en_pausa = b.evaluar("S.corridas[0].horas.length")
        self.captura("pausada")

        self.paso("5. dibujar un cortafuego y aplicarlo")
        b.evaluar(f"void S.mapa.setView([{lat}, {lon}], 15, {{animate: false}})")
        time.sleep(0.4)
        self.clic("#b-dibujar")
        self.trazo([(lat + 0.006, lon - 0.006), (lat + 0.0065, lon), (lat + 0.006, lon + 0.006)])
        self.clic("#b-dibujar")
        if b.evaluar("T.borradores.length") != 1:
            raise Falla(f"el trazo no quedó como borrador (hay {b.evaluar('T.borradores.length')})")
        self.clic("#b-enviar-trazos")
        b.esperar("!T.ocupado && $('respuestas').children.length >= 1", "respuesta al cortafuego", 40)
        res["respuesta_cortafuego"] = b.evaluar("$('respuestas').innerText")
        b.esperar("S.corridas[0].cortafuegos.length >= 1", "el cortafuego aparece en el mapa", 20)
        if "rechazado" in res["respuesta_cortafuego"]:
            raise Falla(f"el motor rechazó el cortafuego: {res['respuesta_cortafuego']}")
        if b.evaluar("S.corridas[0].horas.length") != horas_en_pausa:
            raise Falla("la corrida avanzó estando en pausa")
        self.captura("cortafuego")

        self.paso("6. reanudar hasta el final")
        b.evaluar("window.confirm = () => true")
        self.clic("#reanudar")
        b.esperar("S.modo === 'terminada'", "la corrida terminó", 90)
        time.sleep(1.0)
        res["horas_vistas"] = b.evaluar("S.corridas[0].horas.length - 1")
        if res["horas_vistas"] != HORAS:
            raise Falla(f"la pantalla muestra {res['horas_vistas']} h y se pidieron {HORAS}")
        res["estado_final"] = b.evaluar("S.corridas[0].estado")
        if res["estado_final"] != "terminada":
            raise Falla(f"la corrida terminó en {res['estado_final']}")
        res["bitacora"] = b.evaluar("(S.corridas[0].bitacora || []).map(e => e.tipo)")
        if res["bitacora"][:3] != ["pausa", "cortafuego", "reanudacion"]:
            raise Falla(f"la bitácora no es pausa, cortafuego y reanudación: {res['bitacora']}")
        self.captura("terminada")

        self.paso("7. exportar")
        href = b.esperar("(document.querySelector('#tarjetas a[href$=\"/exportar\"]') || {}).href", "el enlace para exportar", 20)
        zip_ = b.evaluar(f"fetch({json.dumps(href)}).then(async r => {{ const a = new Uint8Array(await r.arrayBuffer());"
                         " return [r.status, r.headers.get('Content-Type'), a.length, a[0], a[1]]; })")
        if not (zip_[0] == 200 and zip_[3:] == [0x50, 0x4B] and zip_[2] > 200):
            raise Falla(f"la exportación no devolvió un zip: {zip_[:3]}")
        res["zip_bytes"] = zip_[2]
        res["corrida"] = b.evaluar("S.corridas[0].id")
        return res


def errores_de_consola(eventos: list[dict]) -> tuple[list[str], list[str]]:
    errores, advertencias = [], []
    for m in eventos:
        metodo, p = m.get("method"), m.get("params") or {}
        if metodo == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails") or {}
            errores.append("excepción: " + ((d.get("exception") or {}).get("description") or d.get("text") or str(d)))
        elif metodo == "Runtime.consoleAPICalled":
            texto = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args") or [])
            if p.get("type") in ("error", "assert"):
                errores.append("consola: " + texto)
            elif p.get("type") == "warning":
                advertencias.append("consola: " + texto)
        elif metodo == "Log.entryAdded":
            e = p.get("entry") or {}
            texto = f"{e.get('source', '')}: {e.get('text', '')} {e.get('url', '')}".strip()
            if e.get("level") == "error":
                errores.append(texto)
            elif e.get("level") == "warning":
                advertencias.append(texto)
    return errores, advertencias


def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba de humo de la pantalla con Chromium/Chrome sin ventana (motor simulado)")
    ap.add_argument("--navegador", help="ruta o nombre del ejecutable (si no, se busca; también NAVEGADOR_PRUEBAS)")
    ap.add_argument("--capturas", type=Path, help="carpeta donde guardar una captura por paso")
    ap.add_argument("--con-ventana", action="store_true", help="muestra el navegador (por defecto, sin ventana)")
    a = ap.parse_args()

    navegador = buscar_navegador(a.navegador)
    if navegador is None:
        print("No se encontró Chromium, Chrome ni Edge. Instalá uno o indicá cuál usar con --navegador RUTA "
              "(o la variable NAVEGADOR_PRUEBAS). Rutas buscadas: " + ", ".join(NOMBRES) + " en el PATH y "
              + ", ".join(str(p) for p in rutas_comunes()), file=sys.stderr)
        return 2
    if a.capturas:
        a.capturas.mkdir(parents=True, exist_ok=True)
    trabajo = Path(tempfile.mkdtemp(prefix="probar_pantalla_"))
    servidor = nav = b = None
    print(f"Prueba de la pantalla con {navegador}", flush=True)
    try:
        try:
            nav, puerto_dep = lanzar_navegador(navegador, trabajo / "perfil", a.con_ventana, trabajo / "navegador.log")
            b = CDP(pagina(puerto_dep))
        except OSError as e:
            print(f"No se pudo usar el navegador {navegador}: {e}", file=sys.stderr)
            return 2
        servidor, base = levantar_servidor(trabajo / "servidor.log")
        print(f"Servidor en {base}", flush=True)
        t0 = time.monotonic()
        res = Recorrido(b, base, a.capturas).correr()
        b.llamar("Runtime.evaluate", expression="1")          # recoge los avisos que hayan quedado en camino
        errores, advertencias = errores_de_consola(b.eventos)
        res["segundos"] = round(time.monotonic() - t0, 1)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        for w in advertencias:
            print(f"  advertencia: {w}")
        if errores:
            print(f"FALLA: {len(errores)} errores en la consola del navegador:", file=sys.stderr)
            for e in errores:
                print(f"  {e}", file=sys.stderr)
            return 1
        print("Todo bien: la pantalla cargó, corrió, pausó, aplicó un cortafuego, reanudó y exportó sin errores en la consola.")
        return 0
    except (Falla, RuntimeError, ConnectionError, OSError) as e:
        errores, _ = errores_de_consola(b.eventos) if b else ([], [])
        print(f"FALLA: {e}", file=sys.stderr)
        for x in errores:
            print(f"  consola: {x}", file=sys.stderr)
        if a.capturas and b:
            try:
                Recorrido(b, "", a.capturas).captura("falla")
            except Exception:
                pass
        return 1
    finally:
        if b:
            b.cerrar()
        cerrar_proceso(nav)
        cerrar_proceso(servidor)
        shutil.rmtree(trabajo, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
