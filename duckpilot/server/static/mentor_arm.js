// Vormachen (seit 0.38.57, erster Schritt zum Mentor aus 0.44): Ari folgt deiner Hand vor der Webcam.
// Maintainer: „dann bin ich sozusagen die Körperschnittstelle“. Wie die Kamera-Spiele (kamera_spiele.js):
// - Webcam nur am PC, nur solange das Fenster offen ist, sichtbar „● Webcam“; beim Schließen ist sie aus.
// - Erkannt wird hier im Browser (hand.js, MediaPipe, nur nach Klick geladen). An Knowlin gehen nur 21 Handpunkte –
//   kein Bild, nichts wird gespeichert, keine Gesichter.
// - Gerechnet wird auf dem Server (`duckpilot/mentor.py`): Handmitte → Lage der Greiferspitze, Daumen und Zeigefinger
//   zusammen → Greifer zu. Ari prüft jeden Weg wie sonst; Not-Aus, Hindernisse und Reichweite gelten.

import { HandErkenner, VERBINDUNGEN } from './hand.js';

export const TAKT_MS = 66;        // so oft gehen Handpunkte an Knowlin (≈ 15 je Sekunde)

// Handpunkte (MediaPipe: x, y je 0…1 im Kamerabild, z relativ) → Nachricht an den Server, Zahlen gerundet
export function nachricht(punkte, seite = '') {
  return { type: 'mentor_hand', seite, punkte: punkte.map((p) => [+p.x.toFixed(4), +p.y.toFixed(4), +(p.z || 0).toFixed(4)]) };
}

export function initMentor(h) {
  const { $, api, send, toast, isRemote } = h;
  const panel = $('mentor-panel');
  if (!panel) return { aus() {} };
  const video = $('mentor-video');
  const punkteBild = $('mentor-punkte');
  const text = $('mentor-text');
  const laden = $('mentor-laden');
  const erkenner = new HandErkenner();
  let stream = null;
  let takt = null;
  let poll = null;
  let ohneHand = 0;

  function sagen(t) { text.textContent = t; }

  function zeichnen(punkte) {
    const c = punkteBild.getContext('2d');
    c.clearRect(0, 0, punkteBild.width, punkteBild.height);
    if (!punkte) return;
    const w = punkteBild.width, hh = punkteBild.height;
    const px = (p) => [(1 - p.x) * w, p.y * hh];                     // gespiegelt wie das Video
    c.strokeStyle = getComputedStyle(panel).getPropertyValue('--data-1') || '#f6a94b';
    c.lineWidth = 2;
    for (const [a, b] of VERBINDUNGEN) {
      const [ax, ay] = px(punkte[a]); const [bx, by] = px(punkte[b]);
      c.beginPath(); c.moveTo(ax, ay); c.lineTo(bx, by); c.stroke();
    }
  }

  async function kameraAn() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { sagen('Diese Ansicht kann keine Webcam öffnen.'); return false; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
    } catch (e) {
      sagen(e && e.name === 'NotAllowedError' ? 'Webcam nicht erlaubt – im Browser freigeben.' : 'Keine Webcam gefunden.');
      return false;
    }
    video.srcObject = stream;
    await video.play().catch(() => {});
    $('mentor-kamera').hidden = false;
    $('badge-mentor-cam').hidden = false;
    return true;
  }

  function kameraAus() {
    clearInterval(takt); takt = null;
    if (stream) for (const t of stream.getTracks()) t.stop();
    stream = null;
    video.srcObject = null;
    $('mentor-kamera').hidden = true;
    $('badge-mentor-cam').hidden = true;
    zeichnen(null);
  }

  function schritt() {
    const r = erkenner.erkennen(video);
    if (!r) return;
    if (r.fehler) { sagen(`Handerkennung: ${r.fehler}`); return; }
    zeichnen(r.punkte);
    if (r.punkte) {
      ohneHand = 0;
      send(nachricht(r.punkte));
      sagen('Ari macht nach. Daumen und Zeigefinger zusammen: Greifer zu.');
    } else if (++ohneHand === 8) {
      sagen('Keine Hand im Bild – Ari wartet. Halte deine Hand ruhig in die Mitte.');
    }
  }

  async function starten() {
    if (isRemote()) { sagen('Vormachen geht nur am PC – die Webcam bleibt am Handy aus.'); return; }
    const s = await api('/api/spiele/hand').catch(() => null);
    if (!s || !s.bereit) {
      laden.hidden = false;
      laden.disabled = !!(s && (s.offline || (s.job && s.job.laeuft)));
      laden.textContent = `Handerkennung laden (≈ ${(s && s.laden_mb) || '14 MB'})`;
      sagen(s && s.offline ? 'Offline-Modus – die Handerkennung wird nicht geladen.'
        : 'Einmalig nötig: die Handerkennung (MediaPipe, Apache-2.0) – sie bleibt auf diesem PC.');
      return;
    }
    laden.hidden = true;
    sagen('Handerkennung startet …');
    try { await erkenner.laden(); } catch (e) { sagen(`Handerkennung startet nicht: ${e.message || e}`); return; }
    if (!(await kameraAn())) return;
    sagen('Halte deine Hand ruhig in die Mitte – das ist Aris Mitte.');
    ohneHand = 0;
    takt = setInterval(schritt, TAKT_MS);
  }

  function aus() {
    if (panel.hidden) return;
    kameraAus();
    send({ type: 'mentor_ende' });
    panel.hidden = true;
  }

  laden.addEventListener('click', async () => {
    const r = await api('/api/spiele/hand/laden', 'POST', {}).catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return; }
    laden.disabled = true;
    sagen('Handerkennung wird geladen …');
    clearInterval(poll);
    poll = setInterval(async () => {
      const s = await api('/api/spiele/hand').catch(() => null);
      if (!s) return;
      if (s.job && s.job.laeuft) { sagen(`Handerkennung wird geladen: ${s.job.text || '…'}`); return; }
      clearInterval(poll); poll = null;
      if (s.bereit) starten(); else sagen(`Laden fehlgeschlagen: ${(s.job && s.job.fehler) || 'unbekannt'}`);
    }, 1000);
  });
  $('mentor-zu').addEventListener('click', aus);
  $('vormachen-btn').addEventListener('click', () => {
    if (!panel.hidden) { aus(); return; }
    panel.hidden = false;
    starten();
  });

  return {
    aus,                                                     // Not-Aus, Körperwechsel, Seitenwechsel
    meldung(m) { if (!panel.hidden && m && !m.ok && m.grund) sagen(m.grund); },
  };
}
