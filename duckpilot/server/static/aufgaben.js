// Selbstständige Aufgaben (seit 0.55): Linie folgen, Farbe folgen, dir folgen, ausweichen, tragen – wie in Hiwonders
// Studio für die WonderDuck. Server: /api/aufgaben (routes/aufgaben.py); gestartet wird über die üblichen Werkzeuge, damit
// Not-Aus, Sperre und „nur was der Körper kann“ gelten. Die Klebeband-Linie im Simulator zeichnet diese Datei selbst.
import * as THREE from './vendor/three.module.min.js';
import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const BAND_M = 0.025, HOEHE_M = 0.002;

// Die Linie als flaches dunkles Band auf dem Boden (Welt: x vorn, y links → three.js: x, −z)
function bandAus(punkte) {
  const n = punkte.length, pos = [], idx = [];
  for (let i = 0; i < n; i++) {
    const [x, y] = punkte[i], [ax, ay] = punkte[(i - 1 + n) % n], [bx, by] = punkte[(i + 1) % n];
    const dx = bx - ax, dy = by - ay, l = Math.hypot(dx, dy) || 1;
    const nx = -dy / l * BAND_M / 2, ny = dx / l * BAND_M / 2;
    pos.push(x + nx, HOEHE_M, -(y + ny), x - nx, HOEHE_M, -(y - ny));
    const a = 2 * i, b = 2 * ((i + 1) % n);
    idx.push(a, a + 1, b, a + 1, b + 1, b);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x24262b, roughness: 0.85, side: THREE.DoubleSide }));
  m.receiveShadow = true;
  m.name = 'linie';
  return m;
}

export function initAufgaben({ $, api, toast, send }) {
  if (!$('af-karten')) return { laden() {} };
  let band = null, stand = null;
  const meldung = (t) => { $('af-meldung').textContent = tr(t); };

  const zeichnen = (punkte) => {
    const scene = window.duckpilot?.scene;
    if (!scene || !scene.scene) { if (punkte) setTimeout(() => zeichnen(punkte), 1000); return; }
    if (band) { scene.scene.remove(band); band.geometry.dispose(); band = null; }
    if (punkte && punkte.length > 2) { band = bandAus(punkte); scene.scene.add(band); }
  };
  const zeigen = (s) => {
    stand = s;
    const liegt = !!(s && s.linie);
    $('af-linie-legen').hidden = liegt;
    $('af-linie-weg').hidden = !liegt;
    for (const e of document.querySelectorAll('.af-nur-sim')) e.hidden = !(s && s.simulator);
    for (const e of document.querySelectorAll('.af-nur-roboter')) e.hidden = !!(s && s.simulator);
    $('af-grund').hidden = !(s && s.grund);
    $('af-grund').textContent = (s && s.grund) || '';
    zeichnen(s && s.linie);
  };
  async function laden() {
    zeigen(await api('/api/aufgaben').catch(() => null));
  }
  const werkzeug = (name, args, text) => {
    send({ type: 'tool', name, args });
    meldung(text);
  };
  const linie = async (an) => {
    const r = await api('/api/aufgaben/linie', 'POST', { an }).catch((e) => ({ ok: false, fehler: e.message }));
    if (r.ok === false) return toast(r.fehler || 'Ging nicht', 'err');
    zeigen(r);
  };

  $('af-linie-legen').addEventListener('click', () => linie(true));
  $('af-linie-weg').addEventListener('click', () => linie(false));
  $('af-linie-los').addEventListener('click', () => {
    if (stand && stand.simulator && !stand.linie) return toast(tr('Erst die Linie legen.'));
    const tempo = Number(document.querySelector('input[name=af-tempo]:checked')?.value || 0.1);
    werkzeug('linie_folgen', { seconds: 120, tempo }, 'Sie sucht die Linie und läuft los.');
  });
  $('af-farbe-los').addEventListener('click', () => {
    const farbe = document.querySelector('input[name=af-farbe]:checked')?.value || 'rot';
    werkzeug('farbe_folgen', { farbe, seconds: 120 }, 'Sie sucht die Farbe.');
  });
  $('af-tragen-los').addEventListener('click', () => {
    const ding = $('af-ding').value, zu = $('af-ziel').value;
    werkzeug('apportieren', zu ? { ding, zu } : { ding }, 'Sie holt es.');
  });
  for (const b of document.querySelectorAll('[data-af-tool]')) {
    b.addEventListener('click', () => werkzeug(b.dataset.afTool, JSON.parse(b.dataset.afArgs || '{}'), 'Los geht’s.'));
  }
  for (const b of document.querySelectorAll('.af-stopp')) {
    b.addEventListener('click', () => { send({ type: 'tool', name: 'stop', args: {} }); meldung('Angehalten.'); });
  }
  window.addEventListener('knowlin:linie', (ev) => zeigen({ ...(stand || {}), linie: (ev.detail || {}).linie }));
  laden();
  return { laden };
}
