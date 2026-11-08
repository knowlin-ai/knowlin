// Kamera-Spiele mit Reachy Mini (seit 0.38.13, ausgebaut 0.38.14; Steuern → Spiele): „Rotes Licht, grünes Licht“,
// „Hand folgen“, „Mach mir nach“ und „Schere, Stein, Papier“ (die beiden letzten in spiele_runden.js).
// Wie in Pollens Reachy-Apps, aber ohne Bildverarbeitung auf dem Server:
// - Die Webcam läuft nur, solange ein Spiel läuft, nur am PC (nie vom Handy/Fernzugang), oben „● Webcam · Spiel“.
// - Ausgewertet wird hier im Browser. Ohne Modell: kleine Graubilder (64 × 48) werden verglichen (Bilddifferenz) –
//   heraus kommen nur Anteil bewegter Punkte und ihr Schwerpunkt. Mit Handerkennung (hand.js, MediaPipe, nur nach
//   Klick geladen): 21 Handpunkte → Handmitte, Richtung, Geste. Kein Bild verlässt den Browser, nichts wird
//   gespeichert, keine Gesichter, keine Personen. An duckpilot gehen nur Grad, Stärke, Phase, Richtung oder Geste.
// - Ohne Roboter (Simulator) schiebt sich beim Start die Spielkarte zur Seite und Reachy erscheint daneben in der
//   3D-Ansicht (dieselbe Leinwand wie im Cockpit, sie zieht um); am echten Roboter nur ein Hinweis.
// - Not-Aus (Knopf, Esc, „Stopp“, Gamepad) beendet sofort: hier lokal und auf dem Server (Nachricht „spiel“).
// Die Rechenschritte sind reine Funktionen (exportiert, mit node getestet: tests/test_spiele.py).

import { initHandKarte, VERBINDUNGEN, ZONE } from './hand.js';
import { initSpiegel, initSsp } from './spiele_runden.js';

export const BREITE = 64;
export const HOEHE = 48;
export const PIXEL_SCHWELLE = 28;     // Grauwert-Unterschied, ab dem ein Punkt als bewegt zählt (Rauschen liegt darunter)
export const GRENZE_MIN = 0.012;      // Ampel: mindestens so viel Anteil bewegter Punkte gilt als „bewegt“
export const FOLGEN_MIN = 0.004;      // Hand folgen: darunter ist nichts los (Schwerpunkt wäre Rauschen)

// RGBA (aus getImageData) → Grauwerte (eine Zahl je Punkt)
export function grauwerte(rgba, n = BREITE * HOEHE) {
  const g = new Uint8Array(n);
  for (let i = 0, j = 0; i < n; i++, j += 4) g[i] = (rgba[j] * 77 + rgba[j + 1] * 150 + rgba[j + 2] * 29) >> 8;
  return g;
}

// Bilddifferenz: Anteil bewegter Punkte (0 … 1) und ihr Schwerpunkt (x, y je 0 … 1, im Bild der Kamera, ungespiegelt)
export function bewegung(vorher, jetzt, breite = BREITE, hoehe = HOEHE, schwelle = PIXEL_SCHWELLE) {
  const n = breite * hoehe;
  if (!vorher || !jetzt || vorher.length !== n || jetzt.length !== n) return { anteil: 0, x: null, y: null };
  let zahl = 0, sx = 0, sy = 0;
  for (let i = 0; i < n; i++) {
    if (Math.abs(jetzt[i] - vorher[i]) > schwelle) {
      zahl++;
      sx += i % breite;
      sy += (i / breite) | 0;
    }
  }
  if (!zahl) return { anteil: 0, x: null, y: null };
  return { anteil: zahl / n, x: (sx / zahl + 0.5) / breite, y: (sy / zahl + 0.5) / hoehe };
}

// Schwelle der Ampel aus der Ruhemessung (Anteile, während niemand sich bewegt) und der Empfindlichkeit (1 = normal,
// höher = strenger). Rauschen der Kamera zählt nie als Bewegung: mindestens das 2,5-Fache des lautesten Ruhewerts.
export function grenzeAusRuhe(werte, empfindlichkeit = 1) {
  const e = Math.max(0.3, Math.min(3, Number(empfindlichkeit) || 1));
  const laut = (werte || []).filter((v) => Number.isFinite(v)).reduce((m, v) => Math.max(m, v), 0);
  return Math.max(GRENZE_MIN / e, laut * 2.5 + 0.004 / e);
}

// Bewegt? Erst, wenn zwei Messungen nacheinander über der Grenze liegen (ein Flackern der Belichtung zählt nicht)
export function erwischt(anteile, grenze) {
  const n = anteile.length;
  return n >= 2 && anteile[n - 1] > grenze && anteile[n - 2] > grenze;
}

// Schwerpunkt im Kamerabild → Blickziel für Reachy (Grad, relativ zur Grundrichtung seines Sockels).
// Reachy und die Webcam stehen beide dem Menschen gegenüber und schauen in dieselbe Richtung: Was im (ungespiegelten)
// Kamerabild links liegt, liegt auch links von Reachy – und links ist bei Reachy + (wie head_yaw). Hebt der Mensch die
// rechte Hand, sieht die Kamera sie links → Reachy dreht nach links, also zur Hand. Oben im Bild = hochschauen
// (Nicken −). Die Vorschau zeigen wir gespiegelt wie einen Spiegel; das ändert an der Rechnung nichts.
export function blickAusBild(x, y, { yawSpanne = 70, pitchSpanne = 20 } = {}) {
  const yaw = (0.5 - x) * 2 * yawSpanne;
  const pitch = (y - 0.5) * 2 * pitchSpanne;
  return { yaw: Math.round(yaw * 10) / 10, pitch: Math.round(pitch * 10) / 10 };
}

// Sanft folgen: exponentielle Glättung
export function glaetten(alt, neu, a = 0.35) {
  return alt == null ? neu : alt + (neu - alt) * a;
}

// Ampel: Stufen (wie lange grün, wie streng, wie lange nach „Rotes Licht“ gemessen wird)
export const STUFEN_AMPEL = {
  leicht: { empf: 0.6, gruen: [4, 8], messen: 2.0 },
  mittel: { empf: 1, gruen: [3, 7], messen: 2.5 },
  schwer: { empf: 1.6, gruen: [2, 5], messen: 3.0 },
};
export const GRUEN_S = STUFEN_AMPEL.mittel.gruen;
export const MESSEN_S = STUFEN_AMPEL.mittel.messen;
export const NACH_ROT_S = (drehS) => Math.max(1.0, Math.min(2.0, (Number(drehS) || 0) * 0.5));

// 75 → „1:15“
export function zeitText(sekunden) {
  if (sekunden == null || !Number.isFinite(Number(sekunden))) return '–';
  const s = Math.max(0, Math.round(Number(sekunden)));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const TEXTE = {
  aus: 'Bereit',
  kalibrieren: 'Bitte still stehen …',
  gruen: 'Grünes Licht – los!',
  rot: 'Rotes Licht – nicht bewegen!',
  erwischt: 'Erwischt!',
  geschafft: 'Geschafft!',
};
const STUFE_NAME = { leicht: 'Leicht', mittel: 'Mittel', schwer: 'Schwer' };
const REDUZIERT = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

export function initKameraSpiele(h) {
  const { $, api, toast, isRemote, scene } = h;
  const karte = $('ks-ampel');
  if (!karte) return { nachricht() {}, notAus() {} };
  const hand = initHandKarte(h);
  let stream = null;
  let video = null;
  let vorher = null;
  let laeuft = null;            // 'ampel' | 'folgen' | 'spiegel' | 'ssp' | null
  let nutztHand = false;        // läuft das Spiel mit Handerkennung (sonst Bewegung)?
  let simulator = false;
  let zustand = 'aus';
  let generation = 0;           // jede neue Runde/jeder Stopp macht alte Zeitgeber wirkungslos
  let bestwerte = {};
  const timer = new Set();
  const knopfHaken = [];
  const endeHaken = [];
  const klein = document.createElement('canvas');
  klein.width = BREITE; klein.height = HOEHE;
  const kctx = klein.getContext('2d', { willReadFrequently: true });

  // ── Webcam (nur während eines Spiels) ────────────────────────────────
  async function kameraAn(gross) {
    if (stream) return true;
    if (isRemote()) { toast('Die Kamera-Spiele gehen nur am PC', true); return false; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { toast('Diese Ansicht kann keine Webcam öffnen', true); return false; }
    const groesse = gross ? { width: { ideal: 640 }, height: { ideal: 480 } } : { width: { ideal: 320 }, height: { ideal: 240 } };
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: groesse, audio: false });
    } catch (e) {
      toast(`Webcam nicht freigegeben (${e.name})`, true);
      return false;
    }
    video = document.createElement('video');
    video.muted = true; video.playsInline = true;
    video.srcObject = stream;
    await video.play().catch(() => {});
    $('badge-spiel-cam').hidden = false;
    vorher = null;
    return true;
  }
  function kameraAus() {
    if (stream) for (const t of stream.getTracks()) t.stop();
    stream = null;
    if (video) video.srcObject = null;
    video = null;
    vorher = null;
    $('badge-spiel-cam').hidden = true;
  }
  // Bewegung: kleines Graubild, Differenz zum letzten – das Bild selbst wird sofort wieder überschrieben
  function bewegungMessen() {
    if (!video || video.readyState < 2) return null;
    kctx.drawImage(video, 0, 0, BREITE, HOEHE);
    const jetzt = grauwerte(kctx.getImageData(0, 0, BREITE, HOEHE).data);
    const m = bewegung(vorher, jetzt);
    vorher = jetzt;
    return m;
  }
  function messen() {
    const m = bewegungMessen();
    if (m) zeichnen({ x: m.x, y: m.y, anteil: m.anteil });
    return m;
  }
  // Ein Schritt für die Hand-Spiele: Hand (Modell) oder – als Rückfall – Bewegung. Nur Zahlen und ein Wort.
  function erfassen() {
    if (nutztHand) {
      const r = hand.erkenner.erkennen(video);
      if (r && r.fehler) {                                   // Laufzeit streikt: ehrlich auf Bewegung zurückfallen
        nutztHand = false;
        toast(`Handerkennung ausgefallen (${r.fehler}) – das Spiel folgt jetzt der Bewegung.`, true);
        erkennungZeigen();
        return null;
      }
      if (!r) return null;
      const m = { quelle: 'hand', x: r.mitte ? r.mitte.x : null, y: r.mitte ? r.mitte.y : null,
        staerke: r.hand ? 0.6 : 0, geste: r.geste, punkte: r.punkte };
      zeichnen(m);
      return m;
    }
    const b = bewegungMessen();
    if (!b) return null;
    const da = b.anteil >= FOLGEN_MIN && b.x != null;
    const m = { quelle: 'bewegung', x: da ? b.x : null, y: da ? b.y : null, anteil: b.anteil,
      staerke: Math.min(1, b.anteil / 0.08), geste: null, punkte: null };
    zeichnen(m);
    return m;
  }

  // Vorschau: nie das Kamerabild – nur Handpunkte oder der Schwerpunkt der Bewegung, gespiegelt wie ein Spiegel
  function leinwand() {
    return $({ spiegel: 'ks-sp-bild', ssp: 'ks-ssp-bild' }[laeuft] || 'ks-bild');
  }
  // Ruhige Anzeige (seit 0.38.23, Hinweis: „wenn nur der Punkt ist, flimmert er zu sehr, abhängig von der
  // Erkennung“): Punkte und Schwerpunkt werden geglättet, fehlt eine Messung kurz, bleibt die Hand stehen und blendet
  // weich aus statt zu springen. Mit Handerkennung: Handfläche, Fingerknochen und leuchtende Fingerspitzen.
  // Die Leinwand zeichnet in voller Auflösung (devicePixelRatio), nicht mehr als 160 × 120 Punkte.
  const anzeige = new Map();                                 // je Leinwand: { punkte, x, y, r, sicht }
  const SPITZEN = [4, 8, 12, 16, 20];
  const FLAECHE = [0, 1, 5, 9, 13, 17];
  function aufloesung(bild) {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round((bild.clientWidth || 160) * dpr), h = Math.round((bild.clientHeight || 120) * dpr);
    if (w > 0 && h > 0 && (bild.width !== w || bild.height !== h)) { bild.width = w; bild.height = h; }
    return dpr;
  }
  function zeichnen(m, bild = leinwand()) {
    const dpr = aufloesung(bild);
    const bctx = bild.getContext('2d');
    const w = bild.width, hh = bild.height;
    bctx.clearRect(0, 0, w, hh);
    const css = getComputedStyle(bild);
    const linie = css.getPropertyValue('--ks-linie').trim() || css.color;
    const punkt = css.getPropertyValue('--ks-punkt').trim() || css.color;
    bctx.strokeStyle = linie;
    bctx.lineWidth = dpr;
    bctx.globalAlpha = 0.6;
    bctx.beginPath(); bctx.moveTo(w / 2, 0); bctx.lineTo(w / 2, hh); bctx.moveTo(0, hh / 2); bctx.lineTo(w, hh / 2); bctx.stroke();
    if (bild.id === 'ks-sp-bild') bctx.strokeRect(w * (0.5 - ZONE), hh * (0.5 - ZONE), w * ZONE * 2, hh * ZONE * 2);
    bctx.globalAlpha = 1;
    let a = anzeige.get(bild);
    if (!m) { if (a) a.sicht = 0; anzeige.set(bild, a = a || { sicht: 0 }); }
    if (!a) anzeige.set(bild, a = { sicht: 0 });
    // Hand: Punkte glätten (neue Messung zählt zur Hälfte), sonst die alte Hand ausblenden
    if (m && m.punkte) {
      const neu = m.punkte.map((q) => ({ x: 1 - q.x, y: q.y }));
      a.punkte = a.punkte && a.punkte.length === neu.length && a.sicht > 0.2
        ? a.punkte.map((q, i) => ({ x: q.x + (neu[i].x - q.x) * 0.5, y: q.y + (neu[i].y - q.y) * 0.5 })) : neu;
      a.sicht = 1;
      a.x = null;
    } else if (m && m.x != null) {
      const x = 1 - m.x, y = m.y, r = 0.05 + Math.min(0.12, (m.anteil || 0) * 1.4);
      const glatt = a.x != null && a.sicht > 0.2 ? 0.3 : 1;  // Schwerpunkt springt stark: ruhiger nachziehen
      a.x = a.x == null || glatt === 1 ? x : a.x + (x - a.x) * glatt;
      a.y = a.y == null || glatt === 1 ? y : a.y + (y - a.y) * glatt;
      a.r = a.r == null || glatt === 1 ? r : a.r + (r - a.r) * 0.25;
      a.sicht = Math.min(1, a.sicht + 0.5);
      a.punkte = null;
    } else {
      a.sicht = Math.max(0, a.sicht - 0.22);                 // kurz nichts erkannt: stehen lassen, weich weg
    }
    if (a.sicht <= 0) return;
    bctx.globalAlpha = a.sicht;
    if (a.punkte) {
      const P = a.punkte.map((q) => [q.x * w, q.y * hh]);
      // Handfläche als zarte Fläche
      bctx.beginPath();
      FLAECHE.forEach((i, k) => (k ? bctx.lineTo(...P[i]) : bctx.moveTo(...P[i])));
      bctx.closePath();
      bctx.fillStyle = punkt; bctx.globalAlpha = a.sicht * 0.16; bctx.fill();
      // Knochen: runde, kräftige Linien mit leichtem Schein
      bctx.globalAlpha = a.sicht * 0.9;
      bctx.strokeStyle = punkt; bctx.lineWidth = 3 * dpr; bctx.lineCap = 'round'; bctx.lineJoin = 'round';
      bctx.shadowColor = punkt; bctx.shadowBlur = 8 * dpr;
      bctx.beginPath();
      for (const [i, j] of VERBINDUNGEN) { bctx.moveTo(...P[i]); bctx.lineTo(...P[j]); }
      bctx.stroke();
      // Gelenke klein und hell, Fingerspitzen größer mit Schein
      bctx.shadowBlur = 0;
      bctx.fillStyle = css.color;
      for (let i = 0; i < P.length; i++) {
        if (SPITZEN.includes(i)) continue;
        bctx.beginPath(); bctx.arc(...P[i], 2.2 * dpr, 0, Math.PI * 2); bctx.fill();
      }
      bctx.shadowColor = punkt; bctx.shadowBlur = 12 * dpr; bctx.fillStyle = punkt;
      for (const i of SPITZEN) { bctx.beginPath(); bctx.arc(...P[i], 4.5 * dpr, 0, Math.PI * 2); bctx.fill(); }
      bctx.shadowBlur = 0; bctx.globalAlpha = 1;
      return;
    }
    if (a.x == null) { bctx.globalAlpha = 1; return; }
    // Bewegung: weicher Lichtfleck statt harter Scheibe
    const cx = a.x * w, cy = a.y * hh, r = a.r * Math.min(w, hh) * 1.6;
    const v = bctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    v.addColorStop(0, punkt); v.addColorStop(1, 'transparent');
    bctx.fillStyle = v; bctx.beginPath(); bctx.arc(cx, cy, r, 0, Math.PI * 2); bctx.fill();
    bctx.globalAlpha = 1;
  }

  // ── Bühne: Übergang zum Simulator (ohne Roboter) ────────────────────
  let heimat = null;            // wo die 3D-Leinwand vorher war und wie die Kamera stand
  const dauerToken = (name, sonst) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name)) || sonst;
  const kurveToken = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || 'ease-out';
  function karteVon(art) { return document.querySelector(`.ks-karte[data-spiel="${art}"]`); }
  function buehne(an, art) {
    const raster = $('ks-raster');
    karteVon(art)?.classList.toggle('laeuft', an);        // Anzeigen des Spiels nur, solange es läuft (seit 0.38.21)
    $('ks-echt').hidden = !(an && !simulator);
    if (an && !simulator) { ansage('Reachy spielt am echten Roboter – schau zu ihm hin.'); return; }
    const aktiv = karteVon(art);
    if (!raster || !aktiv) return;
    const ruhig = REDUZIERT();
    const vorher = !ruhig && aktiv.animate ? aktiv.getBoundingClientRect() : null;
    if (an) {
      raster.dataset.spielt = art;
      aktiv.classList.add('is-aktiv');
      for (const k of raster.querySelectorAll('.ks-karte')) k.hidden = k !== aktiv;   // so zählt das Raster nur die zwei
      $('ks-sim').hidden = false;
      simAn();
    } else {
      if (!raster.dataset.spielt) return;
      delete raster.dataset.spielt;
      for (const k of raster.querySelectorAll('.ks-karte')) { k.hidden = false; k.classList.remove('is-aktiv'); }
      $('ks-sim').hidden = true;
      simAus();
    }
    if (vorher) {                // FLIP: die Karte gleitet von ihrem alten Platz an den neuen
      const nach = aktiv.getBoundingClientRect();
      const dx = vorher.left - nach.left, dy = vorher.top - nach.top;
      if (Math.abs(dx) + Math.abs(dy) > 1) {
        aktiv.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }],
          { duration: dauerToken('--duration-slow-02', 700), easing: kurveToken('--ease-out') });
      }
    }
    if (an && raster.getBoundingClientRect().top < 0) raster.scrollIntoView({ block: 'start', behavior: ruhig ? 'auto' : 'smooth' });
  }
  function simAn() {
    if (!scene || !scene.canvas) return;
    const box = $('ks-sim-ansicht');
    heimat = { parent: scene.canvas.parentElement, paused: scene.paused,
      kamera: scene.camera.position.clone(), ziel: scene.controls.target.clone() };
    box.prepend(scene.canvas);
    scene.paused = false;
    requestAnimationFrame(() => { scene.resize(); if (scene.anfahren) scene.anfahren(); });
  }
  function simAus() {
    if (!scene || !heimat) return;
    if (scene.canvas.parentElement === $('ks-sim-ansicht')) {     // sonst hat die Navigation sie schon zurückgeholt
      heimat.parent.prepend(scene.canvas);
      scene.paused = heimat.paused;
      scene.intro = null;
      scene.camera.position.copy(heimat.kamera);
      scene.controls.target.copy(heimat.ziel);
      requestAnimationFrame(() => scene.resize());
    }
    heimat = null;
  }

  // ── Anzeige ─────────────────────────────────────────────────────────
  function ansage(text) { $('ks-live').textContent = text; }
  function setzeZustand(z, extra = '') {
    zustand = z;
    karte.dataset.zustand = z;
    $('ks-ampel-text').textContent = TEXTE[z] + (extra ? ` ${extra}` : '');
    ansage($('ks-ampel-text').textContent);
  }
  let grenze = GRENZE_MIN;
  function balken(anteil) {
    const rel = grenze > 0 ? anteil / grenze : 0;
    const proz = Math.round(Math.min(2, rel) * 100);
    $('ks-balken-wert').style.width = `${proz / 2}%`;
    const b = $('ks-balken');
    b.setAttribute('aria-valuenow', String(proz));
    b.setAttribute('aria-valuetext', `Bewegung ${proz} % der Grenze`);
    b.classList.toggle('is-over', rel > 1);
  }
  const zielRunden = () => Number($('ks-runden-zahl').value) || 4;
  function runden(n) { $('ks-runden').textContent = `${n} von ${zielRunden()}`; }
  function bestAmpel() {
    const stufe = $('ks-stufe').value;
    const b = (bestwerte.ampel || {})[stufe] || {};
    $('ks-ampel-best').textContent = b.bestzeit_s != null ? `${zeitText(b.bestzeit_s)} (${STUFE_NAME[stufe]})` : '–';
  }
  function erkennungZeigen() {
    const mitHand = laeuft && laeuft !== 'ampel' ? nutztHand : hand.an();
    for (const el of document.querySelectorAll('[data-erkennung]')) {
      el.textContent = mitHand ? 'Erkennung: Hand (MediaPipe, hier im Browser)' : 'Erkennung: Bewegung (ohne Modell) – folgt allem, was sich bewegt';
      el.dataset.hand = String(mitHand);
    }
    knoepfe();
  }
  function knoepfe() {
    $('ks-ampel-start').disabled = !!laeuft;
    $('ks-ampel-geschafft').disabled = laeuft !== 'ampel';
    $('ks-ampel-stopp').disabled = laeuft !== 'ampel';
    const f = $('ks-folgen-start');
    f.disabled = !!laeuft && laeuft !== 'folgen';
    f.setAttribute('aria-pressed', String(laeuft === 'folgen'));
    f.textContent = laeuft === 'folgen' ? 'Hand folgen stoppen' : 'Hand folgen starten';
    f.classList.toggle('btn--primary', laeuft !== 'folgen');
    $('ks-stufe').disabled = !!laeuft;
    $('ks-runden-zahl').disabled = !!laeuft;
    for (const fn of knopfHaken) fn();
  }

  // ── Zeitgeber, die mit dem Spiel enden ──────────────────────────────
  const warte = (s, gen) => new Promise((res) => {
    const id = setTimeout(() => { timer.delete(id); res(gen === generation); }, s * 1000);
    timer.add(id);
  });
  // Wiederholt fn alle ms, bis fn etwas zurückgibt (≠ undefined) – oder das Spiel endet
  function schleife(gen, fn, ms) {
    return new Promise((res) => {
      const id = setInterval(() => {
        if (gen !== generation) { clearInterval(id); timer.delete(id); res(null); return; }
        const fertig = fn();
        if (fertig !== undefined) { clearInterval(id); timer.delete(id); res(fertig); }
      }, ms);
      timer.add(id);
    });
  }
  function zeitgeberAus() {
    for (const id of timer) { clearTimeout(id); clearInterval(id); }
    timer.clear();
  }

  // ── Ende (auch Not-Aus) ─────────────────────────────────────────────
  function ende(grund, { server = true } = {}) {
    const war = laeuft;
    generation++;
    zeitgeberAus();
    laeuft = null;
    kameraAus();
    buehne(false, war);
    nutztHand = false;
    balken(0);
    if (zustand !== 'geschafft' || grund) setzeZustand('aus');
    for (const fn of endeHaken) fn(grund, war);
    erkennungZeigen();
    zeichnen(null, $('ks-bild')); zeichnen(null, $('ks-sp-bild')); zeichnen(null, $('ks-ssp-bild'));
    if (grund) { $('ks-folgen-info').textContent = grund; ansage(grund); }
    if (server && war) api('/api/spiele/stopp', 'POST', {}).catch(() => {});
  }
  function notAus() { if (laeuft) ende('Not-Aus – Spiel beendet. Die Webcam ist aus.', { server: false }); }
  // Not-Aus wirkt hier sofort, ohne auf den Server zu warten (der beendet das Spiel selbst auch)
  $('stop').addEventListener('click', notAus);
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') notAus(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && laeuft) ende('Fenster nicht sichtbar – Spiel beendet. Die Webcam ist aus.'); });

  async function starten(art, extra = {}) {
    if (laeuft) return null;
    // Handerkennung zuerst starten (WebAssembly übersetzen dauert) – erst dann das Spiel am Server
    let mitHand = art !== 'ampel' && hand.an();
    if (mitHand) {
      ansage('Handerkennung startet …');
      try {
        await hand.erkenner.laden();
      } catch (e) {
        mitHand = false;
        toast(`Handerkennung konnte nicht starten (${e && e.message ? e.message : e}) – das Spiel folgt der Bewegung.`, true);
      }
    }
    if (art === 'ssp' && !mitHand) { toast('„Schere, Stein, Papier“ braucht die Handerkennung', true); return null; }
    const r = await api('/api/spiele/start', 'POST', { art, ...extra }).catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return null; }
    if (!(await kameraAn(mitHand))) { api('/api/spiele/stopp', 'POST', {}).catch(() => {}); return null; }
    laeuft = art;
    nutztHand = mitHand;
    simulator = !!r.simulator;
    bestwerte = { ...bestwerte, [art]: r.bestwerte || {} };
    buehne(true, art);
    erkennungZeigen();
    return r;
  }
  // Antwort des Servers prüfen: läuft das Spiel dort nicht mehr (Not-Aus, Körperwechsel), hier sofort aufhören
  function pruefen(r) {
    if (r && r.ok) return true;
    if (laeuft) ende(r && r.fehler ? r.fehler : 'Keine Antwort von Knowlin – Spiel beendet.', { server: false });
    return false;
  }
  async function post(pfad, nutzlast) {
    const r = await api(pfad, 'POST', nutzlast).catch(() => null);
    return pruefen(r) ? r : null;
  }

  // ── Rotes Licht, grünes Licht ───────────────────────────────────────
  async function phase(name) {
    const r = await api('/api/spiele/ampel', 'POST', { phase: name }).catch(() => null);
    if (!pruefen(r)) return null;
    if (r.punkte != null) $('ks-ampel-punkte').textContent = String(r.punkte);
    return r;
  }
  // Messreihe über `sekunden`: liefert die Anteile (alle 80 ms)
  function reihe(sekunden, gen, stoppBei) {
    const werte = [];
    const t0 = performance.now();
    vorher = null;
    return schleife(gen, () => {
      const m = messen();
      if (m && vorher) { werte.push(m.anteil); balken(m.anteil); }
      if ((stoppBei && stoppBei(werte)) || performance.now() - t0 > sekunden * 1000) return werte;
      return undefined;
    }, 80);
  }
  let ampelStart = 0;
  async function ampel() {
    const stufe = $('ks-stufe').value;
    const s = STUFEN_AMPEL[stufe] || STUFEN_AMPEL.mittel;
    if (!(await starten('ampel', { stufe }))) return;
    const gen = generation;
    runden(0);
    $('ks-ampel-punkte').textContent = '0';
    $('ks-ampel-zeit').textContent = '0:00';
    bestAmpel();
    setzeZustand('kalibrieren');
    const ruhe = await reihe(2.0, gen);
    if (!ruhe) return;
    grenze = grenzeAusRuhe(ruhe.slice(2), s.empf);
    balken(0);
    ampelStart = performance.now();
    schleife(gen, () => { $('ks-ampel-zeit').textContent = zeitText((performance.now() - ampelStart) / 1000); }, 1000);
    while (gen === generation) {
      if (!(await phase('gruen')) || gen !== generation) return;
      setzeZustand('gruen');
      const [lo, hi] = s.gruen;
      if (!(await warte(lo + Math.random() * (hi - lo), gen))) return;
      const rot = await phase('rot');
      if (!rot || gen !== generation) return;
      setzeZustand('rot');
      if (!(await warte(NACH_ROT_S(rot.dreh_s), gen))) return;
      const werte = await reihe(s.messen, gen, (w) => erwischt(w, grenze));
      if (!werte) return;
      if (erwischt(werte, grenze)) {
        if (!(await phase('erwischt'))) return;
        setzeZustand('erwischt', 'Du hast dich bewegt – zurück an den Start.');
        runden(0);
        if (!(await warte(3, gen))) return;
        continue;
      }
      runden(rot.runde);
      if (rot.runde >= zielRunden()) { await geschafft(gen); return; }
    }
  }
  async function geschafft(gen = generation) {
    if (laeuft !== 'ampel') return;
    generation++;
    zeitgeberAus();
    const r = await phase('geschafft');
    if (!r) return;
    const zeit = r.zeit_s != null ? ` In ${zeitText(r.zeit_s)} – ${r.punkte} Punkte.` : '';
    setzeZustand('geschafft', `Reachy freut sich mit dir.${zeit}${r.neue_bestzeit ? ' Neue Bestzeit!' : ''}`);
    if (r.zeit_s != null) $('ks-ampel-zeit').textContent = zeitText(r.zeit_s);
    const stufe = $('ks-stufe').value;
    if (r.bestzeit_s != null) bestwerte.ampel = { ...(bestwerte.ampel || {}), [stufe]: { ...((bestwerte.ampel || {})[stufe] || {}), bestzeit_s: r.bestzeit_s } };
    bestAmpel();
    await new Promise((res) => setTimeout(res, 3000));
    if (gen + 1 === generation && laeuft === 'ampel') ende(null);
  }

  // ── Hand folgen ─────────────────────────────────────────────────────
  async function folgen() {
    if (laeuft === 'folgen') { ende(null); $('ks-folgen-info').textContent = 'Hand folgen beendet. Die Webcam ist aus.'; return; }
    if (!(await starten('folgen'))) return;
    const gen = generation;
    let gx = null, gy = null;
    let gesendet = { yaw: null, pitch: null, at: 0 };
    let unterwegs = false;
    let zuletztDa = performance.now();
    $('ks-folgen-info').textContent = nutztHand
      ? 'Zeig deine Hand – Reachy schaut zu ihr, bei großen Winkeln dreht er sich mit.'
      : 'Langsam winken – Reachy schaut zur Bewegung, bei großen Winkeln dreht er sich mit.';
    ansage('Hand folgen läuft.');
    vorher = null;
    schleife(gen, () => {
      const m = erfassen() || { x: null, y: null, staerke: 0 };
      const jetzt = performance.now();
      if (m.x != null) { gx = glaetten(gx, m.x); gy = glaetten(gy, m.y); zuletztDa = jetzt; }
      else if (jetzt - zuletztDa > 2500 && gx != null) { gx = glaetten(gx, 0.5, 0.08); gy = glaetten(gy, 0.5, 0.08); }  // Hand weg: langsam zurück zur Mitte
      if (unterwegs || jetzt - gesendet.at < 125) return undefined;           // höchstens 8 Ziele je Sekunde
      const z = gx == null ? { yaw: 0, pitch: 0 } : blickAusBild(gx, gy);     // noch nichts gesehen: zum Menschen
      const neu = gesendet.yaw == null || Math.abs(z.yaw - gesendet.yaw) > 1.5 || Math.abs(z.pitch - gesendet.pitch) > 1.5;
      if (!neu && jetzt - gesendet.at < 1000) return undefined;                // ab und zu ein Lebenszeichen
      unterwegs = true;
      gesendet = { ...z, at: jetzt };
      api('/api/spiele/blick', 'POST', { yaw: z.yaw, pitch: z.pitch, staerke: m.staerke })
        .catch(() => null)
        .then((r) => { unterwegs = false; if (gen === generation) pruefen(r); });
      return undefined;
    }, 66);
  }

  $('ks-ampel-start').addEventListener('click', ampel);
  $('ks-ampel-geschafft').addEventListener('click', () => geschafft());
  $('ks-ampel-stopp').addEventListener('click', () => { ende(null); ansage('Spiel beendet. Die Webcam ist aus.'); });
  $('ks-folgen-start').addEventListener('click', folgen);
  $('ks-stufe').addEventListener('change', bestAmpel);
  $('ks-runden-zahl').addEventListener('change', () => runden(0));

  // „Mach mir nach“ und „Schere, Stein, Papier“ teilen Kamera, Ende, Bühne und Erkennung mit diesem Modul
  const ctx = {
    $, toast, ansage, starten, ende, post, warte, schleife, erfassen, hand, knoepfe,
    laeuft: () => laeuft, gen: () => generation, mitHand: () => nutztHand,
    best: (art) => (bestwerte[art] ||= {}),
    beiKnoepfen: (fn) => knopfHaken.push(fn),
    beimEnde: (fn) => endeHaken.push(fn),
  };
  initSpiegel(ctx);
  initSsp(ctx);
  hand.beiAenderung(erkennungZeigen);
  runden(0);
  erkennungZeigen();
  zeichnen(null, $('ks-bild')); zeichnen(null, $('ks-sp-bild')); zeichnen(null, $('ks-ssp-bild'));
  // Bestwerte (nur Zahlen) – vom Handy aus lehnt der Server ab, dann bleibt es bei „–“
  api('/api/spiele').then((s) => { if (s && s.bestwerte) { bestwerte = s.bestwerte; bestAmpel(); for (const fn of knopfHaken) fn(); } }).catch(() => {});

  return {
    // Server: Spiel beendet (Not-Aus per Sprache/Werkzeug, Körperwechsel, keine Ziele mehr)
    nachricht(msg) { if (msg && !msg.laeuft && laeuft) ende(msg.notaus ? 'Not-Aus – Spiel beendet. Die Webcam ist aus.' : `Spiel beendet: ${msg.grund || ''}`, { server: false }); },
    notAus,
    laeuft: () => laeuft,
  };
}
