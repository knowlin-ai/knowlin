"""Updates und Neustart mit sichtbarem Fortschritt (seit 0.38.38).

Hinweise nach dem Update auf 0.38.37: „ggf kann bei in app Downloads oder Updates ein Fortschrittsbalken sein –
man sieht immer nicht was gerade passiert oder ob es hängt“ und „das Neustarten nach Updates hakt noch irgendwie“. Das
Protokoll zeigte: Installer 70 s, danach brauchte der erste Start zwei Minuten – und das Fenster sagte nach 90 s
„wird noch installiert“, obwohl Knowlin längst startete.
"""

import json
import shutil
import socket
import subprocess
import sys
import urllib.request

import pytest

from duckpilot.server.app import STATIC
from duckpilot.startstatus import StartStatus


def _frei() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_startstatus_meldet_schritt_ohne_version_und_gibt_den_port_frei():
    port = _frei()
    st = StartStatus("9.9.9")
    assert st.starten("127.0.0.1", port)
    st.setzen("Körper, Stimme und Gedächtnis werden aufgebaut")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=3) as r:
        p = json.load(r)
    # "app": ein zweiter Doppelklick erkennt das startende Knowlin; ohne "version": das Fenster lädt nicht zu früh neu
    assert p["app"] == "duckpilot" and p["startet"] and p["version_neu"] == "9.9.9" and "version" not in p
    assert p["schritt"] == "Körper, Stimme und Gedächtnis werden aufgebaut"
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
        seite = r.read().decode()
    assert "Knowlin startet" in seite and "location.reload()" in seite and "Gedächtnis" in seite
    st.beenden()
    with socket.socket() as s:                       # Port wieder frei für den eigentlichen Server
        if sys.platform != "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)     # wie uvicorn (asyncio) unter Linux/macOS
        s.bind(("127.0.0.1", port))


def test_startstatus_weicht_einem_belegten_port_aus():
    with socket.socket() as belegt:
        belegt.bind(("127.0.0.1", 0))
        belegt.listen()
        assert not StartStatus("9.9.9").starten("127.0.0.1", belegt.getsockname()[1])


def test_neustart_meldet_startschritte():
    from pathlib import Path

    import duckpilot

    quelle = (Path(duckpilot.__file__).parent / "__main__.py").read_text(encoding="utf-8")
    assert "StartStatus(__version__)" in quelle and "startstatus.beenden()" in quelle
    # der Statusdienst gibt den Port frei, bevor der eigentliche Server startet
    assert quelle.index("startstatus.beenden()") < quelle.index("server.run()")


FENSTER = r"""
const elemente = {};
const knoten = (id) => elemente[id] ||= {
  id, hidden: true, disabled: false, textContent: '', kinder: [], attrs: {}, handler: {}, verlauf: [],
  style: {}, klassen: new Set(),
  classList: { add(k) { this.k.add(k); }, remove(k) { this.k.delete(k); }, toggle(k, an) { an ? this.k.add(k) : this.k.delete(k); } },
  addEventListener(t, f) { this.handler[t] = f; },
  setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
  replaceChildren(...k) { this.kinder = k; }, append(...k) { this.kinder.push(...k); },
  querySelector(sel) { return sel === 'i' ? (this.i ||= { style: {} }) : null; },
  querySelectorAll() { return []; }, focus() {},
};
for (const k of Object.values(elemente)) k.classList.k = k.klassen;
const $ = (id) => { const k = knoten(id); k.classList.k = k.klassen; return k; };
const el = (tag, klasse, text) => ({ tag, klasse, textContent: text || '', kinder: [], attrs: {},
  setAttribute(k, v) { this.attrs[k] = v; }, append(...k) { this.kinder.push(...k); } });
// Texte mitschreiben, damit der Test auch Zwischenstände sieht
const beobachten = (id) => { const k = $(id); let t = ''; Object.defineProperty(k, 'textContent', {
  get: () => t, set: (v) => { t = v; k.verlauf.push(v); } }); };
['update-text', 'quit-done-title', 'quit-done-text'].forEach(beobachten);
globalThis.setTimeout = (f) => { Promise.resolve().then(f); return 0; };
globalThis.setInterval = () => 0; globalThis.clearInterval = () => {};
let neu = false;
globalThis.location = { reload() { neu = true; } };
// Was der Server antwortet: erst lädt das Update (zweimal Fortschritt), dann ist Knowlin weg, meldet sich beim Start
// mit seinem Schritt und kommt schließlich als neue Version
const fortschritt = [{ schritt: 'laden', geladen: 5 * 1048576, gesamt: 10 * 1048576 }, { schritt: 'pruefen' }];
let installiert = null;
const api = async (pfad, methode) => {
  if (pfad === '/api/update/fortschritt') return fortschritt.length ? fortschritt.shift() : { schritt: 'pruefen' };
  if (pfad === '/api/update/installieren') {
    await new Promise((r) => { installiert = r; });
    return { ok: true, version: '9.9.9' };
  }
  return null;
};
const pings = [null, null, { startet: true, version_neu: '9.9.9', schritt: 'Körper, Stimme und Gedächtnis werden aufgebaut' },
  { startet: true, version_neu: '9.9.9', schritt: 'Gleich fertig' }, { version: '9.9.9' }];
const schritte = [];
globalThis.fetch = async () => {
  const p = pings.length ? pings.shift() : { version: '9.9.9' };
  const ol = elemente['quit-schritte'];
  if (ol) schritte.push(ol.kinder.map((li) => `${li.klasse || ''}:${li.textContent}${li.kinder.length ? '/' + li.kinder[0].textContent : ''}`).join(' | '));
  if (!p) throw new Error('weg');
  return { json: async () => p };
};
const { initBeenden } = await import('MODUL');
const b = initBeenden({ $, api, el, toast: () => {}, isRemote: () => false });
b.update({ version: '1.0.0', kann: true, online: { neu: { version: '9.9.9', seite: 'x' }, kann: true } });
const klick = elemente['update-install'].handler.click();
for (let i = 0; i < 50; i++) await Promise.resolve();
installiert();
await klick;
for (let i = 0; i < 400 && !neu; i++) await Promise.resolve();
console.log(JSON.stringify({ text: elemente['update-text'].verlauf, titel: elemente['quit-done-title'].verlauf,
  schritte, neu, balken: elemente['quit-balken'].i.style.width }));
"""


def test_fenster_zeigt_update_schritt_fuer_schritt_und_laedt_neu():
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = FENSTER.replace("MODUL", (STATIC / "beenden.js").as_uri())
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "Lade das Update … 5,0 von 10 MB" in out["text"]           # echter Fortschritt beim Herunterladen
    assert "Prüfe die Prüfsumme …" in out["text"]
    assert out["titel"][0] == "Knowlin 9.9.9 wird installiert …"
    assert any("is-jetzt:Installieren" in s for s in out["schritte"])
    # der neue Knowlin meldet beim Hochfahren, wobei er ist – das Fenster zeigt es unter „Knowlin startet“
    assert any("is-jetzt:Knowlin startet/Körper, Stimme und Gedächtnis werden aufgebaut" in s for s in out["schritte"])
    assert "Knowlin 9.9.9 startet …" in out["titel"]
    assert out["neu"] and out["balken"] == "100%"                      # neue Version da → neu laden


LAUF = r"""
import sys, time
sys.path.insert(0, ROOT)
import duckpilot.desktop as d
d.find_browser = lambda: None
d.webbrowser.open = lambda u: print("FENSTER", u, flush=True)
d.refresh_shortcut_icons = lambda: None
import duckpilot.server.app as app
_alt = app.Runtime.__init__
def langsam(self, *a, **k):
    time.sleep(3)                     # wie ein langsamer Start unter Windows
    _alt(self, *a, **k)
app.Runtime.__init__ = langsam
from duckpilot.__main__ import main
main(["--app", "--port", PORT, "--no-memory"])
"""


def test_programmstart_zeigt_fenster_sofort_und_meldet_schritte(tmp_path):
    """Programmfenster: Das Fenster geht sofort auf (Statusseite), meldet den Schritt und erst dann ist Knowlin bereit –
    und es wird nur ein Fenster geöffnet."""
    import os
    import time
    from pathlib import Path

    port = _frei()
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, DUCKPILOT_SETTINGS=str(tmp_path / "settings.json"), XDG_DATA_HOME=str(tmp_path / "daten"),
               LOCALAPPDATA=str(tmp_path / "daten"), DUCKPILOT_OFFLINE="1")
    env.pop("ANTHROPIC_API_KEY", None)
    code = LAUF.replace("ROOT", repr(root)).replace("PORT", repr(str(port)))
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=tmp_path, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    gesehen = []
    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
                    p = json.load(r)
                gesehen.append("startet" if p.get("startet") else "bereit")
                if p.get("version"):
                    break
            except OSError:
                pass
            time.sleep(0.1)
    finally:
        proc.terminate()
        out = proc.communicate(timeout=20)[0]
    assert "startet" in gesehen and gesehen[-1] == "bereit", (gesehen[-5:], out[-800:])
    assert gesehen.index("startet") < gesehen.index("bereit")
    assert out.count("FENSTER") == 1, out[-800:]


def test_pip_fortschritt_wird_mitgelesen():
    """Nachinstallieren (Physik, Stimme, PyTorch): pips „Progress x of y“ füllt den Balken, landet aber nicht im
    Protokoll; die Datei kommt aus „Downloading …“, ohne die .metadata-Zeilen."""
    from duckpilot.voice.install import Installer

    job = {"zeilen": []}
    for z in ["Collecting torch", "  Downloading torch-2.5.1-cp313-cp313-win_amd64.whl.metadata (28 kB)",
              "Downloading torch-2.5.1-cp313-cp313-win_amd64.whl (203.1 MB)", "Progress 0 of 212963328",
              "Progress 106481664 of 212963328"]:
        Installer._line(job, z)
    assert job["laden"] == {"datei": "torch-2.5.1-cp313-cp313-win_amd64.whl", "geladen": 106481664, "gesamt": 212963328}
    assert job["dateien"] == 1 and not any(z.startswith("Progress") for z in job["zeilen"])
    Installer._line(job, "Installing collected packages: torch")
    assert job["laden"]["installiert"]


def test_pip_balken_nur_mit_passendem_pip(monkeypatch):
    from duckpilot.voice import install as I

    for ausgabe, erwartet in (("pip 26.2.1 from x", True), ("pip 24.1 from x", True), ("pip 23.3.2 from x", False),
                              ("", False)):
        I._PIP_ROH.clear()
        monkeypatch.setattr(I.subprocess, "run", lambda *a, _o=ausgabe, **k: type("R", (), {"stdout": _o})())
        assert I.pip_kann_roh("python") is erwartet, ausgabe


def test_installationsanzeige_mit_datei_mb_und_balken():
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = r"""
const { installStand, installBalken, dateiName } = await import('MODUL');
const el = (tag, klasse) => ({ tag, className: klasse || '', kinder: [], attrs: {}, style: {},
  classList: { add(k) { this.k = (this.k || '') + ' ' + k; } },
  append(...k) { this.kinder.push(...k); }, setAttribute(k, v) { this.attrs[k] = v; } });
const job = { laeuft: true, schritt: 2, schritte: 3, zeilen: ['x'],
  laden: { datei: 'https://download.pytorch.org/whl/rocm6.2/torch-2.5.1%2Brocm6.2-cp313-cp313-win_amd64.whl', geladen: 1288490188, gesamt: 2576980377 } };
const b = installBalken(el, job);
const leer = installBalken(el, { laeuft: true, zeilen: [] });
console.log(JSON.stringify({ text: installStand(job), name: dateiName(job.laden.datei), breite: b.kinder[0].style.width,
  wert: b.attrs['aria-valuenow'], leer: leer.classList.k, ohne: installStand({ schritt: 1, schritte: 1, zeilen: [] }) }));
""".replace("MODUL", (STATIC / "fortschritt.js").as_uri())
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True,
                                    check=True).stdout)
    assert out["name"] == "torch-2.5.1+rocm6.2"
    assert out["text"] == "Schritt 2 von 3 – lädt torch-2.5.1+rocm6.2: 1229 von 2458 MB"
    assert out["breite"] == "50%" and out["wert"] == "50"
    assert "is-busy" in out["leer"] and out["ohne"] == "startet …"
