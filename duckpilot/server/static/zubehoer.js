// Zubehör der Microduck (seit 0.47): Rollen, Arena-Rennen mit Uhr und Geisterente, NFC-Polaroid.
// Server: /api/zubehoer (routes/zubehoer.py). Meldungen kommen als Ereignis „knowlin:zubehoer“ (rennen, polaroid),
// die Lage als „knowlin:state“. Das Polaroid-Bild malt dieser Browser – mit den sechs Farben farbiger E-Ink und
// Fehlerstreuung, damit es aussieht wie auf der Karte. Nichts davon verlässt den Browser, außer du speicherst es.
import { initRollen3D } from './rollen3d.js';
import { uebersetzeText } from './i18n.js';
import * as THREE from './vendor/three.module.min.js';

const tr = (t) => uebersetzeText(t) || t;
const PALETTE = [[18, 18, 18], [250, 250, 245], [200, 40, 40], [240, 200, 40], [40, 80, 170], [50, 140, 70]];
const HIMMEL = { froh: ['#ffe27a', '#fff6d6'], schwer: ['#5b6fa8', '#c9d3ee'], gemischt: ['#9fd4a6', '#fff1b8'],
  ruhig: ['#22336b', '#6c7fbf'] };
const sek = (s) => `${s.toFixed(1).replace('.', ',')} s`;

function einfaerben(ctx, w, h) {
  // Floyd–Steinberg auf die E-Ink-Palette
  const img = ctx.getImageData(0, 0, w, h), d = img.data;
  const f = new Float32Array(d.length);
  for (let i = 0; i < d.length; i++) f[i] = d[i];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      let best = PALETTE[0], bd = Infinity;
      for (const p of PALETTE) {
        const dd = (f[i] - p[0]) ** 2 + (f[i + 1] - p[1]) ** 2 + (f[i + 2] - p[2]) ** 2;
        if (dd < bd) { bd = dd; best = p; }
      }
      for (let c = 0; c < 3; c++) {
        const err = f[i + c] - best[c];
        d[i + c] = best[c];
        if (x + 1 < w) f[i + 4 + c] += err * 7 / 16;
        if (y + 1 < h) {
          if (x > 0) f[i + w * 4 - 4 + c] += err * 3 / 16;
          f[i + w * 4 + c] += err * 5 / 16;
          if (x + 1 < w) f[i + w * 4 + 4 + c] += err / 16;
        }
      }
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}

export function malePolaroid(canvas, t) {
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const w = canvas.width, h = canvas.height;
  const [oben, unten] = HIMMEL[t.stimmung] || HIMMEL.ruhig;
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, oben);
  g.addColorStop(1, unten);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  // Traumwolke
  ctx.fillStyle = '#fafaf5';
  for (const [x, y, r] of [[100, 92, 62], [52, 104, 34], [148, 104, 34], [78, 66, 30], [124, 66, 30]]) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }
  for (const [x, y, r] of [[34, 160, 9], [20, 178, 6]]) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); }
  if (t.stimmung === 'ruhig') {
    ctx.fillStyle = '#f0c828';
    for (const [x, y] of [[18, 20], [180, 26], [166, 150], [40, 40]]) ctx.fillRect(x, y, 3, 3);
  }
  const motive = t.motive || [];
  const groesse = motive.length === 1 ? 64 : motive.length === 2 ? 50 : 40;
  const plaetze = motive.length === 1 ? [[100, 94]] : motive.length === 2 ? [[72, 94], [128, 94]] : [[58, 98], [100, 80], [142, 98]];
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `${groesse}px "Noto Color Emoji", "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
  motive.forEach((m, i) => { const [x, y] = plaetze[i] || plaetze[0]; ctx.fillText(m.zeichen, x, y); });
  einfaerben(ctx, w, h);
  // Schrift erst nach dem Einfärben: auf E-Ink bleibt Text scharf schwarz auf weiß
  ctx.fillStyle = '#fafaf5';
  ctx.fillRect(0, h - 30, w, 30);
  ctx.fillStyle = '#121212';
  ctx.font = '600 13px system-ui, sans-serif';
  const worte = motive.map((m) => m.wort).join(' · ');
  ctx.fillText(worte.length > 28 ? `${worte.slice(0, 27)}…` : worte, w / 2, h - 15);
}

// Foto wie bei Pollen (seit 0.48, Pollens photo.take): das Bild ihrer Kopfkamera aus dem Simulator, auf E-Ink gebracht
export function malFoto(canvas, scene) {
  const w = canvas.width, h = canvas.height;
  const ziel = new THREE.WebGLRenderTarget(w, h);
  ziel.texture.colorSpace = THREE.SRGBColorSpace;
  scene._placePovCam(1);
  const r = scene.renderer, vorher = r.getRenderTarget();
  r.setRenderTarget(ziel);
  r.render(scene.scene, scene.povCam);
  r.setRenderTarget(vorher);
  const px = new Uint8Array(w * h * 4);
  r.readRenderTargetPixels(ziel, 0, 0, w, h, px);
  ziel.dispose();
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const img = ctx.createImageData(w, h);
  for (let y = 0; y < h; y++) img.data.set(px.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);   // WebGL steht Kopf
  ctx.putImageData(img, 0, 0);
  einfaerben(ctx, w, h);
  ctx.fillStyle = '#fafaf5';
  ctx.fillRect(0, h - 24, w, 24);
  ctx.fillStyle = '#121212';
  ctx.font = '600 12px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(new Date().toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }), w / 2, h - 12);
}

export function initZubehoer({ $, api, toast, showView }) {
  if (!$('zb-karten')) return { laden() {} };
  let d3 = null;                                     // die 3D-Ansicht gibt es erst, wenn app.js fertig ist
  const drei = new Proxy({}, { get: (_, k) => (...a) => {
    if (!d3 && window.duckpilot?.scene) d3 = initRollen3D(window.duckpilot.scene);
    return d3 ? d3[k](...a) : null;
  } });
  let stand = null, rollen = null, uhrStart = null, uhrLauf = 0, aus = 0, geistWeg = null;

  const zeigeRollen = (z) => {
    const an = !!(z && z.rollen), geduckt = !!(z && z.geduckt);
    const key = `${an}${geduckt}`;
    if (key === rollen) return;
    rollen = key;
    $('zb-rollen-stand').textContent = tr(an ? (geduckt ? 'Rollen dran – geduckt' : 'Rollen dran') : 'Rollen ab');
    $('zb-rollen-an').hidden = an;
    $('zb-rollen-ab').hidden = !an;
    $('zb-geduckt-feld').hidden = !an;
    $('zb-geduckt').checked = geduckt;
  };
  const zeigeBest = (b, arten) => {
    $('zb-best').replaceChildren(...Object.entries(arten || {}).flatMap(([k, name]) => {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = tr(name);
      dd.textContent = b && b[k] ? sek(b[k]) : '–';
      return [dt, dd];
    }));
  };
  const rennenLaeuft = (ja) => {
    $('zb-rennen-selbst').hidden = ja;
    $('zb-rennen-lenken').hidden = ja;
    $('zb-rennen-stopp').hidden = !ja;
  };
  const uhr = () => {
    if (uhrStart == null) return;
    $('zb-uhr').textContent = sek((performance.now() - uhrStart) / 1000);
    uhrLauf = requestAnimationFrame(uhr);
  };
  const fehler = (r) => toast(tr((r && r.fehler) || 'Das ging nicht'), true);

  async function laden() {
    stand = await api('/api/zubehoer').catch(() => null);
    if (!stand) return;
    $('zb-grund').hidden = stand.verfuegbar;
    $('zb-grund').textContent = stand.grund ? tr(stand.grund) : '';
    for (const id of ['zb-rollen-an', 'zb-rennen-selbst', 'zb-rennen-lenken', 'zb-polaroid-halten', 'zb-polaroid-foto']) $(id).disabled = !stand.verfuegbar;
    rollen = null;
    zeigeRollen(stand.zubehoer);
    zeigeBest(stand.bestzeiten, stand.arten);
    rennenLaeuft(!!stand.laeuft);
  }

  const rollenSetzen = async (body) => {
    const r = await api('/api/zubehoer/rollen', 'POST', body).catch((e) => ({ fehler: e.message }));
    if (!r || r.ok === false) fehler(r); else { toast(tr(r.text)); zeigeRollen(r.zubehoer); }
  };
  $('zb-rollen-an').addEventListener('click', () => rollenSetzen({ an: true }));
  $('zb-rollen-ab').addEventListener('click', () => rollenSetzen({ an: false }));
  $('zb-geduckt').addEventListener('change', (e) => rollenSetzen({ an: true, geduckt: e.target.checked }));

  const starten = async (selbst) => {
    const r = await api('/api/zubehoer/rennen', 'POST', { aktion: 'start', selbst }).catch((e) => ({ fehler: e.message }));
    if (!r || r.ok === false) { fehler(r); return; }
    showView('cockpit');
  };
  $('zb-rennen-selbst').addEventListener('click', () => starten(true));
  $('zb-rennen-lenken').addEventListener('click', () => starten(false));
  $('zb-rennen-stopp').addEventListener('click', () => api('/api/zubehoer/rennen', 'POST', { aktion: 'stopp' }).catch(() => null));

  $('zb-polaroid-foto').addEventListener('click', () => {
    const scene = window.duckpilot?.scene;
    if (!scene || !scene.povCam) { toast(tr('Die 3D-Ansicht ist noch nicht bereit.'), true); return; }
    const c = $('zb-polaroid-bild');
    try { malFoto(c, scene); } catch (e) { toast(`${tr('Foto ging nicht')}: ${e.message || e}`, true); return; }
    c.setAttribute('aria-label', tr('Polaroid: Foto aus ihrer Kamera'));
    $('zb-polaroid-text').textContent = tr('Foto aus ihrer Kamera.');
    const a = $('zb-polaroid-laden');
    a.href = c.toDataURL('image/png');
    a.download = 'knowlin-foto.png';
    a.hidden = false;
  });
  $('zb-polaroid-halten').addEventListener('click', async () => {
    const r = await api('/api/zubehoer/polaroid', 'POST', {}).catch((e) => ({ fehler: e.message }));
    if (!r || r.ok === false) fehler(r);
  });

  window.addEventListener('knowlin:state', (ev) => { if (!d3) drei.strecke(null); zeigeRollen((ev.detail || {}).zubehoer); });
  window.addEventListener('knowlin:zubehoer', (ev) => {
    const m = ev.detail || {};
    if (m.type === 'polaroid') {
      const c = $('zb-polaroid-bild');
      malePolaroid(c, m);
      c.setAttribute('aria-label', `Polaroid: ${m.text}`);
      $('zb-polaroid-text').textContent = m.text;
      const a = $('zb-polaroid-laden');
      a.href = c.toDataURL('image/png');
      a.download = 'knowlin-traum.png';
      a.hidden = false;
      return;
    }
    if (m.text) $('zb-rennen-text').textContent = m.text;
    clearTimeout(aus);
    if (m.phase === 'bereit') {
      rennenLaeuft(true);
      drei.strecke(m.tore);
      drei.naechstes(0);
      drei.geist(null);
      $('zb-uhr').textContent = sek(0);
      uhrStart = null;
      geistWeg = m.geist;
    } else if (m.phase === 'tor') {
      if (m.start) { uhrStart = performance.now(); cancelAnimationFrame(uhrLauf); uhr(); drei.geist(geistWeg); }
      drei.naechstes((m.tor + 1) % (stand?.tore?.length || 5));
    } else if (m.phase === 'ziel' || m.phase === 'ende') {
      uhrStart = null;
      cancelAnimationFrame(uhrLauf);
      if (m.phase === 'ziel') $('zb-uhr').textContent = sek(m.zeit);
      if (m.bestzeiten) zeigeBest(m.bestzeiten, stand?.arten);
      rennenLaeuft(false);
      aus = setTimeout(() => { drei.strecke(null); drei.geist(null); }, 6000);
    }
  });
  laden();
  return { laden };
}
