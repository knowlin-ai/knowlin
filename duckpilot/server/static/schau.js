// „Schau mich an“ (seit 0.39, Stack-chan „wie ab Werk“): Der Kopf folgt deinem Gesicht vor der Webcam.
// Das Gesicht findet dieser Browser selbst (MediaPipe Face Detection, Apache-2.0, vom eigenen Server geladen – nie von
// einem CDN); an Knowlin gehen nur die Mitte des Gesichts (0 … 1) und ob eins zu sehen ist – kein Bild, und wer du bist,
// erkennt es nicht. Geladen wird die Erkennung nur nach dem Klick, einmal je PC (modell/gesicht.py).
// Aus: noch einmal tippen, Not-Aus (Knopf, Esc), Fenster verlassen – oder wenn Knowlin ablehnt (Sperre, Schlaf).
import { toast } from './ui.js';
import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const BASIS = '/api/schau/dateien/';
const TAKT_MS = 125;                       // höchstens 8 Blickziele je Sekunde

async function api(pfad, method = 'GET', body) {
  const res = await fetch(pfad, { method, headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined });
  return res.json().catch(() => ({ ok: false }));
}

// Größtes Gesicht → Mitte im Bild (0 … 1); null, wenn keins da ist
export function mitteVon(detections) {
  let best = null;
  for (const d of detections || []) {
    const b = d && d.boundingBox;
    if (b && (!best || b.width * b.height > best.width * best.height)) best = b;
  }
  return best ? { x: best.xCenter, y: best.yCenter } : null;
}

function skriptLaden(src) {
  return new Promise((ok, fehler) => {
    if (window.FaceDetection) { ok(); return; }
    const s = document.createElement('script');
    s.src = src;
    s.onload = () => ok();
    s.onerror = () => fehler(new Error('Gesichtserkennung nicht ladbar'));
    document.head.append(s);
  });
}

function initSchau() {
  const knoepfe = [...document.querySelectorAll('[data-schau]')];   // je Körper mit Kopf und Kamera einer (Stacki, Reachy)
  const info = document.getElementById('schau-info');
  if (!knoepfe.length || !info) return;
  let stream = null, video = null, erkenner = null, laeuft = false, takt = 0, unterwegs = false, mitte = null;

  const sagen = (t) => { info.hidden = !t; info.textContent = t ? tr(t) : ''; };
  const zustand = (an) => { laeuft = an; for (const k of knoepfe) k.setAttribute('aria-pressed', String(an)); };
  const sperren = (ja) => { for (const k of knoepfe) k.disabled = ja; };

  async function laden() {
    let s = await api('/api/schau');
    if (s.bereit) return true;
    if (s.offline) { sagen('Offline-Modus – die Gesichtserkennung wird nicht geladen.'); return false; }
    const r = await api('/api/schau/laden', 'POST');
    if (!r.ok && !/schon/.test(r.fehler || '')) { sagen(r.fehler || 'Ging nicht.'); return false; }
    for (let i = 0; i < 600; i++) {                     // höchstens fünf Minuten
      await new Promise((ok) => setTimeout(ok, 700));
      s = await api('/api/schau');
      if (s.bereit) return true;
      const job = s.job || {};
      if (!job.laeuft && job.fehler) { sagen(`Gesichtserkennung nicht geladen: ${job.fehler}`); return false; }
      sagen(job.text || 'lade die Gesichtserkennung …');
    }
    return false;
  }

  async function erkennerBauen() {
    if (erkenner) return erkenner;
    await skriptLaden(`${BASIS}face_detection.js`);
    const fd = new window.FaceDetection({ locateFile: (f) => BASIS + f });
    fd.setOptions({ model: 'short', minDetectionConfidence: 0.5 });
    fd.onResults((r) => { mitte = mitteVon(r.detections); });
    await fd.initialize();
    erkenner = fd;
    return fd;
  }

  async function aus(grund) {
    const war = laeuft;
    zustand(false);
    clearInterval(takt);
    if (stream) for (const t of stream.getTracks()) t.stop();
    stream = null;
    if (video) video.srcObject = null;
    const cam = document.getElementById('badge-cam');
    if (cam) cam.hidden = true;
    if (war) await api('/api/schau/stopp', 'POST', {});
    sagen(grund || '');
  }

  // Zwei Takte: Erkennen so schnell es der PC schafft, Senden fest mit 8 Hz (auch wenn das Erkennen stockt –
  // sonst endet das Schauen auf langsamen PCs nach der Frist von selbst)
  async function erkennen() {
    while (laeuft) {
      const t0 = performance.now();
      try { await erkenner.send({ image: video }); } catch { /* ein Bild verpasst – weiter */ }
      await new Promise((ok) => setTimeout(ok, Math.max(0, 66 - (performance.now() - t0))));
    }
  }

  function senden() {
    if (!laeuft) { clearInterval(takt); return; }
    if (unterwegs) return;
    unterwegs = true;
    const m = mitte;
    api('/api/schau/blick', 'POST', m ? { x: m.x, y: m.y, gesicht: true } : { gesicht: false }).then((r) => {
      unterwegs = false;
      if (laeuft && r && r.ok === false) aus(r.fehler || 'Schauen beendet.');
    });
    sagen(m ? 'Ich sehe dich.' : 'Ich suche dein Gesicht …');
  }

  async function an() {
    const s = await api('/api/schau');
    if (s.grund) { sagen(s.grund); toast(tr(s.grund)); return; }
    if (!navigator.mediaDevices?.getUserMedia) { sagen('Diese Ansicht kann keine Webcam öffnen.'); return; }
    sperren(true);
    try {
      if (!(await laden())) return;
      sagen('Webcam startet …');
      await erkennerBauen();
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      video = video || Object.assign(document.createElement('video'), { muted: true, playsInline: true });
      video.srcObject = stream;
      await video.play();
      const r = await api('/api/schau/start', 'POST', {});
      if (!r.ok) { await aus(r.fehler || 'Ging nicht.'); return; }
      const cam = document.getElementById('badge-cam');
      if (cam) cam.hidden = false;
      zustand(true);
      mitte = null;
      sagen('Ich suche dein Gesicht …');
      erkennen();
      takt = setInterval(senden, TAKT_MS);
    } catch (e) {
      await aus(e && e.name === 'NotAllowedError' ? 'Webcam nicht freigegeben.' : `Ging nicht: ${(e && e.message) || e}`);
    } finally {
      sperren(false);
    }
  }

  for (const k of knoepfe) k.addEventListener('click', () => (laeuft ? aus('Schauen beendet. Die Webcam ist aus.') : an()));
  document.getElementById('stop')?.addEventListener('click', () => { if (laeuft) aus('Not-Aus – Schauen beendet. Die Webcam ist aus.'); });
  window.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && laeuft) aus('Not-Aus – Schauen beendet. Die Webcam ist aus.'); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && laeuft) aus('Schauen beendet. Die Webcam ist aus.'); });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initSchau);
else initSchau();
