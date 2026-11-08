// Handerkennung für die Kamera-Spiele (seit 0.38.14): MediaPipe Hand Landmarker (Apache-2.0) im Browser.
// - Nichts beim Start: Laufzeit und Modell lädt duckpilot erst nach dem Klick „Handerkennung laden“ (fester Stand,
//   Prüfsummen, Datenordner – duckpilot/modell/hand.py). Der Browser holt sie danach vom eigenen Server
//   (/api/spiele/hand/dateien/…), nie von einem CDN.
// - Ausgewertet wird hier: Das Webcam-Bild geht nur an die WebAssembly-Laufzeit in diesem Browser. Heraus kommen
//   21 Handpunkte; daraus werden Handmitte, Richtung und Geste (Schere, Stein, Papier). An duckpilot gehen nur diese
//   Wörter und Zahlen. Kein Bild verlässt den Browser, nichts wird gespeichert, keine Gesichter, keine Personen.
// - Ohne Modell bleibt die Bewegungserkennung (Bilddifferenz in kamera_spiele.js) – ehrlich so beschriftet.
// Die Rechenschritte sind reine Funktionen (exportiert, mit node getestet: tests/test_spiele.py).

export const BASIS = '/api/spiele/hand/dateien';

// Verbindungen der 21 Punkte (Handgelenk 0; Daumen 1–4, Zeige- 5–8, Mittel- 9–12, Ring- 13–16, kleiner Finger 17–20)
export const VERBINDUNGEN = [
  [0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20],
];
const FINGER = [[5, 6, 8], [9, 10, 12], [13, 14, 16], [17, 18, 20]];   // Grundgelenk, Mittelgelenk, Spitze
export const ZONE = 0.16;                 // so weit (Bildanteil) muss die Hand aus der Mitte, damit es eine Richtung ist

// Abstand zweier Punkte im Bild (x, y je 0 … 1; das Bild ist 4 : 3, also x breiter)
function abstand(a, b, seitenverhaeltnis = 4 / 3) {
  return Math.hypot((a.x - b.x) * seitenverhaeltnis, a.y - b.y);
}

// Welche Finger sind gestreckt? [Daumen, Zeige-, Mittel-, Ring-, kleiner Finger] – unabhängig davon, wie die Hand
// gedreht ist: Eine gestreckte Fingerspitze liegt weiter vom Handgelenk weg als ihr Mittelgelenk.
export function gestreckt(lm) {
  if (!Array.isArray(lm) || lm.length < 21) return null;
  const w = lm[0];
  const finger = FINGER.map(([, pip, tip]) => abstand(w, lm[tip]) > abstand(w, lm[pip]) * 1.12);
  // Daumen: Spitze weit weg vom Grundgelenk des kleinen Fingers (abgespreizt)
  const daumen = abstand(lm[4], lm[17]) > abstand(lm[3], lm[17]) * 1.08 && abstand(lm[4], lm[5]) > abstand(lm[0], lm[5]) * 0.45;
  return [daumen, ...finger];
}

// Geste für „Schere, Stein, Papier“ – oder null, wenn es keine klare ist
export function gesteAus(lm) {
  const f = gestreckt(lm);
  if (!f) return null;
  const [, zeige, mittel, ring, klein] = f;
  const zahl = [zeige, mittel, ring, klein].filter(Boolean).length;
  if (zahl === 0) return 'stein';
  if (zeige && mittel && !ring && !klein) return 'schere';
  if (zahl >= 4 || (zahl === 3 && f[0])) return 'papier';
  return null;
}

// Handmitte: Mittel aus Handgelenk und den vier Fingergrundgelenken (ruhiger als eine Fingerspitze)
export function handMitte(lm) {
  if (!Array.isArray(lm) || lm.length < 21) return null;
  const ids = [0, 5, 9, 13, 17];
  const x = ids.reduce((s, i) => s + lm[i].x, 0) / ids.length;
  const y = ids.reduce((s, i) => s + lm[i].y, 0) / ids.length;
  return { x, y };
}

// Richtung aus Sicht des Menschen (Bild gespiegelt wie ein Spiegel): 'links' | 'rechts' | 'oben' | 'unten' | 'mitte'.
// x, y sind Kamerabild-Koordinaten (ungespiegelt, 0 … 1). Hebt der Mensch die Hand nach links (seine Sicht), liegt sie
// im Kamerabild rechts (x > 0,5) – gespiegelt also links.
export function richtungAus(x, y, zone = ZONE) {
  if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  const dx = (1 - x) - 0.5, dy = y - 0.5;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < zone) return 'mitte';
  if (Math.abs(dx) >= Math.abs(dy)) return dx < 0 ? 'links' : 'rechts';
  return dy < 0 ? 'oben' : 'unten';
}

// Stabil? Die letzten n Werte sind gleich und eine echte Richtung (nicht 'mitte', nicht null)
export function stabil(werte, n = 4) {
  if (!Array.isArray(werte) || werte.length < n) return null;
  const letzte = werte.slice(-n);
  const r = letzte[0];
  if (!r || r === 'mitte') return null;
  return letzte.every((v) => v === r) ? r : null;
}

// Häufigste klare Geste in einer Reihe (für den Moment nach „Schnuck!“) – mindestens `min` Treffer
export function haeufigste(werte, min = 2) {
  const zahl = new Map();
  for (const v of werte || []) if (v) zahl.set(v, (zahl.get(v) || 0) + 1);
  let best = null, n = 0;
  for (const [v, k] of zahl) if (k > n) { best = v; n = k; }
  return n >= min ? best : null;
}

// ── MediaPipe im Browser (erst, wenn ein Spiel sie braucht) ────────────
export class HandErkenner {
  constructor(basis = BASIS) {
    this.basis = basis;
    this.lm = null;
    this._laedt = null;
    this._letzt = 0;
    this._zuletzt = null;     // letztes Ergebnis (nur Zahlen), bis wieder Zeit zum Rechnen ist
    this._frei = 0;
    this.ms = 0;              // wie lange ein Bild im Mittel dauert
  }
  get bereit() { return !!this.lm; }
  // Laufzeit (vom eigenen Server), dann das Modell. Gerechnet wird auf dem Prozessor (WebAssembly, XNNPACK): das reicht
  // für eine Hand gut und kommt der 3D-Ansicht nicht auf der Grafikkarte in die Quere.
  async laden() {
    if (this.lm) return true;
    if (!this._laedt) {
      this._laedt = (async () => {
        const vision = await import(`${this.basis}/vision_bundle.mjs`);
        const dateien = await vision.FilesetResolver.forVisionTasks(this.basis);
        this.lm = await vision.HandLandmarker.createFromOptions(dateien, {
          baseOptions: { modelAssetPath: `${this.basis}/hand_landmarker.task`, delegate: 'CPU' },
          runningMode: 'VIDEO', numHands: 1,
          minHandDetectionConfidence: 0.5, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5,
        });
        // Aufwärmen: das erste Bild dauert am längsten (Rechengraph) – lieber jetzt, vor dem Spiel, mit einem leeren Bild
        const leer = document.createElement('canvas');
        leer.width = 64; leer.height = 48;
        this._letzt = performance.now();
        this.lm.detectForVideo(leer, this._letzt);
        return true;
      })().catch((e) => { this._laedt = null; throw e; });
    }
    return this._laedt;
  }
  // Ein Bild auswerten: { hand, mitte, geste, punkte, ms } – das Bild selbst bleibt im Video-Element.
  // Wirft die Laufzeit einen Fehler, kommt { fehler } zurück (die Spiele fallen dann auf die Bewegung zurück).
  erkennen(video) {
    if (!this.lm || !video || video.readyState < 2) return null;
    let t = performance.now();
    // Langsamer Rechner: nicht öfter rechnen, als Zeit ist – der Rest der Seite (Knöpfe, Not-Aus) bleibt flüssig
    if (this._zuletzt && t < this._frei) return this._zuletzt;
    if (t <= this._letzt) t = this._letzt + 1;            // Zeitstempel müssen steigen
    this._letzt = t;
    let r;
    try {
      r = this.lm.detectForVideo(video, t);
    } catch (e) {
      return { fehler: e && e.message ? e.message : String(e) };
    }
    const dauer = performance.now() - t;
    this.ms = this.ms ? this.ms * 0.8 + dauer * 0.2 : dauer;
    this._frei = performance.now() + this.ms * 1.5;
    const punkte = r && r.landmarks && r.landmarks[0];
    this._zuletzt = punkte ? { hand: true, mitte: handMitte(punkte), geste: gesteAus(punkte), punkte }
      : { hand: false, mitte: null, geste: null, punkte: null };
    return this._zuletzt;
  }
  schliessen() {
    try { if (this.lm) this.lm.close(); } catch { /* egal */ }
    this.lm = null;
    this._laedt = null;
  }
}

// ── Karte „Handerkennung“: Stand, Laden auf Klick, an/aus ─────────────
export function initHandKarte(h) {
  const { $, api, toast, isRemote } = h;
  const erkenner = new HandErkenner();
  let stand = { bereit: false };
  let poll = null;
  const beiAenderung = new Set();
  const schalter = $('ks-hand-an');
  const knopf = $('ks-hand-laden');

  function zeigen() {
    const job = stand.job || {};
    const bereit = !!stand.bereit;
    const karte = $('ks-hand');
    if (karte) karte.dataset.bereit = String(bereit);
    let text;
    if (job.laeuft) text = `Handerkennung wird geladen: ${job.text || '…'}`;
    else if (bereit) text = 'Handerkennung bereit – liegt auf diesem PC (MediaPipe Hand Landmarker).';
    else if (job.fehler) text = `Laden fehlgeschlagen: ${job.fehler}. Ohne Modell folgen die Spiele der Bewegung.`;
    else text = 'Nicht geladen – die Spiele folgen der Bewegung vor der Kamera (ohne Modell).';
    $('ks-hand-status').textContent = text;
    knopf.hidden = bereit;
    knopf.disabled = !!job.laeuft || !!stand.offline;
    knopf.textContent = `Handerkennung laden (≈ ${stand.laden_mb || '14 MB'})`;
    schalter.disabled = !bereit;
    if (!bereit) schalter.checked = false;
    $('ks-hand-offline').hidden = !stand.offline;
    for (const f of beiAenderung) f();
  }
  async function aktualisieren() {
    const r = await api('/api/spiele/hand').catch(() => null);
    if (!r) return;
    const warBereit = !!stand.bereit;
    stand = r;
    if (r.bereit && !warBereit) schalter.checked = true;      // frisch geladen: gleich benutzen
    zeigen();
    if (!(r.job && r.job.laeuft)) { clearInterval(poll); poll = null; }
  }
  knopf.addEventListener('click', async () => {
    if (isRemote()) { toast('Die Handerkennung lädt nur am PC', true); return; }
    const r = await api('/api/spiele/hand/laden', 'POST', {}).catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return; }
    stand = { ...stand, job: { laeuft: true, text: 'startet …' } };
    zeigen();
    clearInterval(poll);
    poll = setInterval(aktualisieren, 1000);
  });
  schalter.addEventListener('change', zeigen);
  aktualisieren();

  return {
    erkenner,
    // Handerkennung benutzen? Nur, wenn geladen und eingeschaltet
    an: () => !!stand.bereit && schalter.checked,
    bereit: () => !!stand.bereit,
    beiAenderung: (f) => beiAenderung.add(f),
    aktualisieren,
  };
}
