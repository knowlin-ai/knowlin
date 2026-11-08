// Tanzen zu Musik und Choreomodus (seit 0.36).
// Ein Musikstück wird hier im Browser analysiert (Tempo, erster Schlag, Lautstärke je Takt) – die Datei geht nur an
// den eigenen duckpilot (Datenordner), nie ins Netz. Der Server plant daraus einen Tanz (choreo.plane), den man hier
// anpasst, probt und speichert. Die Ente tanzt im Takt, diese Seite spielt die Musik.

import { uebersetzeText } from './i18n.js';
import { initMitwippen } from './mitwippen.js';

const tr = (text) => uebersetzeText(text) || text;

const ARTEN = ['schritt', 'wiegen', 'drehen', 'nicken', 'wippen', 'wackeln', 'trick', 'pose', 'gefuehl', 'pause'];
const ART_TEXT = { schritt: 'Bein zu Bein', wiegen: 'Wiegen', nicken: 'Nicken', wippen: 'Wippen', wackeln: 'Wackeln', drehen: 'Drehen', trick: 'Tanzgeste', pose: 'Pose', gefuehl: 'Gefühl', pause: 'Pause' };
// Reachy Mini (seit 0.38.13): eigene Bewegungen im Takt (Kopf, Antennen, Drehung), Gefühle als Akzent – keine Entenschritte
const ARTEN_REACHY = ['trick', 'gefuehl', 'pause'];
const ART_TEXT_REACHY = { ...ART_TEXT, trick: 'Tanzbewegung' };
const ANALYSE_S = 240;   // so viel vom Stück wird angeschaut (wie choreo.plane max_s)
const WELLE_DT = 0.05;
const MIT_NAME = new Set(['trick', 'pose', 'gefuehl']);   // eine Säule der Wellenform je 50 ms

const zeit = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

// ── Analyse im Browser ────────────────────────────────────────────────
// Kleine FFT (Radix 2, in place) für das Klangbild je Takt
function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const w = -2 * Math.PI / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < len / 2; k++) {
        const c = Math.cos(w * k), s = Math.sin(w * k);
        const a = i + k, b = a + len / 2;
        const xr = re[b] * c - im[b] * s, xi = re[b] * s + im[b] * c;
        re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
      }
    }
  }
}

// Klangbild eines Takts (seit 0.38.23, für die Erkennung von Strophe, Refrain, Bridge – `musik_struktur.py`):
// zwölf Tonklassen (Harmonie, Melodie) und sechs Frequenzbänder (Klangfarbe), gemittelt über vier Fenster im Takt.
const FFT_N = 4096;
const BAENDER = [30, 120, 300, 800, 2000, 5000, 12000];
export function klangbild(samples, rate, von, bis) {
  const chroma = new Float64Array(12), band = new Float64Array(BAENDER.length - 1);
  const re = new Float64Array(FFT_N), im = new Float64Array(FFT_N);
  const fenster = 4;
  for (let w = 0; w < fenster; w++) {
    const a = Math.floor(von + (bis - von) * (w + 0.5) / fenster - FFT_N / 2);
    if (a < 0 || a + FFT_N > samples.length) continue;
    for (let i = 0; i < FFT_N; i++) { re[i] = samples[a + i] * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (FFT_N - 1))); im[i] = 0; }
    fft(re, im);
    for (let k = 1; k < FFT_N / 2; k++) {
      const f = k * rate / FFT_N;
      const mag = Math.hypot(re[k], im[k]);
      if (f >= 65 && f <= 2100) chroma[((Math.round(12 * Math.log2(f / 440) + 69) % 12) + 12) % 12] += mag;
      for (let b = 0; b < band.length; b++) if (f >= BAENDER[b] && f < BAENDER[b + 1]) { band[b] += mag; break; }
    }
  }
  const lo = (x) => Math.round(Math.log1p(x) * 100) / 100;
  return [...Array.from(chroma, lo), ...Array.from(band, lo)];
}

// Lautstärke-Hüllkurve in Rahmen (~86 je Sekunde) → Anstiege (Onsets) → Tempo per Autokorrelation (70–180 BPM,
// leicht zu 120 hin gewichtet, damit halbes/doppeltes Tempo selten gewinnt) → Phase des ersten Schlags → Energie je Takt.
export function analysiere(samples, rate) {
  const hop = 512;
  const n = Math.min(samples.length, Math.floor(rate * ANALYSE_S));
  const rahmen = Math.floor(n / hop);
  if (rahmen < 64) throw new Error('Das Stück ist zu kurz.');
  const fps = rate / hop;
  const rms = new Float32Array(rahmen);
  for (let f = 0; f < rahmen; f++) {
    let s = 0;
    for (let i = f * hop, e = i + hop; i < e; i++) s += samples[i] * samples[i];
    rms[f] = Math.sqrt(s / hop);
  }
  const onset = new Float32Array(rahmen);
  for (let f = 1; f < rahmen; f++) onset[f] = Math.max(0, Math.log1p(100 * rms[f]) - Math.log1p(100 * rms[f - 1]));
  const bis = Math.min(rahmen, Math.round(fps * 90));
  const korr = (bpm) => {
    const lag = 60 * fps / bpm;
    let s = 0;
    for (let f = 0; f + lag + 1 < bis; f++) {
      const l = Math.floor(f + lag);
      const a = f + lag - l;
      s += onset[f] * (onset[l] * (1 - a) + onset[l + 1] * a);
    }
    return s;
  };
  let grob = 120;
  let besteWert = -1;
  for (let b = 70; b <= 180; b += 0.5) {
    const w = korr(b) * Math.exp(-0.5 * (Math.log2(b / 120) / 0.6) ** 2);
    if (w > besteWert) { besteWert = w; grob = b; }
  }
  // Feinabstimmung: über viele Schläge summiert sich schon ein Zehntel BPM zu einem verrutschten Takt.
  // Kamm über die ganzen 90 s: Tempo und erster Schlag gemeinsam, so dass möglichst viele Schläge auf Anstiege fallen.
  let bpm = grob;
  let phase = 0;
  besteWert = -1;
  for (let b = grob * 0.97; b <= grob * 1.03 + 1e-4; b += 0.05) {      // ±3 % (vorher ±2 BPM – zu knapp)
    const lag = 60 * fps / b;
    for (let p = 0; p < lag; p += 0.5) {
      let s = 0;
      for (let f = p; f + 1 < bis; f += lag) s += Math.max(onset[Math.floor(f)], onset[Math.floor(f) + 1]);
      if (s > besteWert) { besteWert = s; bpm = b; phase = p; }
    }
  }
  // Seit 0.38.23: Schläge über das ganze Stück nachmessen und Tempo und ersten Schlag als Gerade durch die gefundenen
  // Anstiege legen (kleinste Quadrate) – der Kamm allein ließ Stücke um ein BPM daneben liegen, nach einer Minute war
  // der Takt dann um einen halben Schlag verrutscht, und die Teile des Stücks saßen falsch.
  for (let runde = 0; runde < 3; runde++) {
    const lag = 60 * fps / bpm;
    const spitzen = [];
    const fenster = Math.max(1, Math.round(lag * 0.12));
    for (let k = 0; phase + k * lag < rahmen - 1; k++) {
      const mitte = Math.round(phase + k * lag);
      let bestF = -1, bestW = 0;
      for (let f = Math.max(1, mitte - fenster); f <= Math.min(rahmen - 1, mitte + fenster); f++) if (onset[f] > bestW) { bestW = onset[f]; bestF = f; }
      if (bestF >= 0) spitzen.push([k, bestF, bestW]);
    }
    if (spitzen.length < 16) break;
    const ws = spitzen.map((s) => s[2]).sort((x, y) => x - y);
    const grenze = ws[Math.floor(ws.length * 0.5)];
    const gut = spitzen.filter((s) => s[2] >= grenze);
    if (gut.length < 12) break;
    let sk = 0, sf = 0, skk = 0, skf = 0;
    for (const [k, f] of gut) { sk += k; sf += f; skk += k * k; skf += k * f; }
    const n = gut.length, nenner = n * skk - sk * sk;
    if (!nenner) break;
    const neuLag = (n * skf - sk * sf) / nenner;
    const neuPhase = (sf - neuLag * sk) / n;
    if (!(neuLag > 0) || Math.abs(neuLag - lag) > lag * 0.03) break;
    bpm = 60 * fps / neuLag;
    phase = ((neuPhase % neuLag) + neuLag) % neuLag;
  }
  const besteLag = 60 * fps / bpm;
  // Erster Schlag des Takts (seit 0.38.23): Teile wechseln auf der Eins – von vier möglichen Lagen die, an der die
  // Lautstärke von Schlag zu Schlag am stärksten springt (Einsätze), dazu die Kraft der Anstiege auf der Eins
  {
    const schlagE = [];
    for (let f = phase; f + besteLag <= rahmen; f += besteLag) {
      let q = 0;
      const a0 = Math.round(f), e0 = Math.round(f + besteLag);
      for (let i = a0; i < e0; i++) q += rms[i];
      schlagE.push([q / Math.max(1, e0 - a0), onset[Math.min(rahmen - 1, a0)] + onset[Math.min(rahmen - 1, a0 + 1)]]);
    }
    const lautMittel = schlagE.reduce((s, x) => s + x[0], 0) / Math.max(1, schlagE.length) || 1;
    let besteLage = 0, besteSumme = -1;
    for (let lage = 0; lage < 4; lage++) {
      let summe = 0;
      for (let k = lage; k < schlagE.length; k += 4) {
        if (k > 0) summe += Math.abs(Math.log((schlagE[k][0] + 1e-4) / (schlagE[k - 1][0] + 1e-4))) * 2;
        summe += schlagE[k][1] * 0.25 * (schlagE[k][0] / lautMittel);
      }
      if (summe > besteSumme) { besteSumme = summe; besteLage = lage; }
    }
    phase += besteLage * besteLag;
    if (phase >= 4 * besteLag) phase -= 4 * besteLag;
  }
  bpm = Math.round(bpm * 10) / 10;
  const start = phase / fps;
  const takt = 4 * besteLag;
  const roh = [];
  for (let f = phase; f + takt <= rahmen; f += takt) {
    let s = 0;
    const a = Math.round(f);
    const e = Math.round(f + takt);
    for (let i = a; i < e; i++) s += rms[i];
    roh.push(s / (e - a));
  }
  const sortiert = [...roh].sort((x, y) => x - y);
  const lo = sortiert[Math.floor(sortiert.length * 0.05)] || 0;
  const hi = sortiert[Math.floor(sortiert.length * 0.95)] || 1;
  const energie = roh.map((v) => Math.round(Math.max(0, Math.min(1, (v - lo) / Math.max(1e-6, hi - lo))) * 100) / 100);
  const klang = roh.map((_, i) => klangbild(samples, rate, (phase + i * takt) * hop, (phase + (i + 1) * takt) * hop));
  return { bpm, start: Math.round(start * 1000) / 1000, energie, klang };
}

async function dekodiere(datei) {
  const puffer = await datei.arrayBuffer();
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  try {
    const audio = await ctx.decodeAudioData(puffer.slice(0));
    const kanaele = audio.numberOfChannels;
    const mono = new Float32Array(audio.length);
    for (let c = 0; c < kanaele; c++) {
      const d = audio.getChannelData(c);
      for (let i = 0; i < d.length; i++) mono[i] += d[i] / kanaele;
    }
    return { puffer, mono, rate: audio.sampleRate };
  } finally {
    ctx.close?.();
  }
}

// ── Nach Gehör (0.36.1): Mikrofon → Tempo, letzter Schlag, Lautstärke ──────
// Läuft ganz im Browser; an duckpilot gehen alle 1,5 s nur drei Zahlen. Ohne Echo-Unterdrückung, damit die Musik
// nicht weggefiltert wird.
export function tempoUndSchlag(onset, fps) {
  let besteLag = 0;
  let besteWert = -1;
  for (let bpm = 70; bpm <= 180; bpm += 1) {
    const lag = 60 * fps / bpm;
    let s = 0;
    for (let f = 0; f + lag + 1 < onset.length; f++) {
      const l = Math.floor(f + lag);
      const a = f + lag - l;
      s += onset[f] * (onset[l] * (1 - a) + onset[l + 1] * a);
    }
    const w = s * Math.exp(-0.5 * (Math.log2(bpm / 120) / 0.6) ** 2);
    if (w > besteWert) { besteWert = w; besteLag = lag; }
  }
  let phase = 0;
  let beste = -1;
  for (let p = 0; p < besteLag; p += 0.5) {
    let s = 0;
    for (let f = p; f + 1 < onset.length; f += besteLag) s += Math.max(onset[Math.floor(f)], onset[Math.floor(f) + 1]);
    if (s > beste) { beste = s; phase = p; }
  }
  const letzter = phase + Math.floor((onset.length - 1 - phase) / besteLag) * besteLag;
  return { bpm: Math.round(600 * fps / besteLag) / 10, schlagVorS: (onset.length - 1 - letzter) / fps };
}

function initGehoer({ $, api, toast }) {
  const knopf = $('gehoer-an');
  const status = $('gehoer-status');
  if (!knopf) return;
  let lauf = null;
  const melde = (txt) => { status.textContent = txt; };

  async function an() {
    if (!navigator.mediaDevices?.getUserMedia) { toast('Dieser Browser kann nicht aufs Mikrofon zugreifen'); return; }
    if ($('gehoer-quelle').value === 'pc' && !navigator.mediaDevices.getDisplayMedia) { toast('Dieser Browser kann den PC-Ton nicht teilen'); return; }
    let stream;
    const ohneFilter = { echoCancellation: false, noiseSuppression: false, autoGainControl: false };
    if ($('gehoer-quelle').value === 'pc') {
      // Ton dieses PCs (seit 0.36.2): über „Bildschirm teilen“ mit Systemaudio – das Bild wird sofort beendet
      try {
        stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: ohneFilter, systemAudio: 'include' });
      } catch { toast('Teilen abgebrochen'); return; }
      stream.getVideoTracks().forEach((t) => t.stop());
      if (!stream.getAudioTracks().length) { toast('Kein Ton geteilt – beim Teilen „Systemaudio teilen“ anhaken'); return; }
    } else {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: ohneFilter });
      } catch { toast('Kein Zugriff aufs Mikrofon'); return; }
    }
    const r = await api('/api/gehoer', 'POST', { aktion: 'start' }).catch(() => ({ ok: false }));
    if (!r.ok) { stream.getTracks().forEach((t) => t.stop()); toast(r.fehler || r.grund || 'Tanzen geht gerade nicht'); return; }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const quelle = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(1024, 1, 1);
    const hop = 512;
    const fps = ctx.sampleRate / hop;
    const rms = [];
    let spitze = 0.02;
    proc.onaudioprocess = (e) => {
      const d = e.inputBuffer.getChannelData(0);
      for (let i = 0; i + hop <= d.length; i += hop) {
        let s = 0;
        for (let j = i; j < i + hop; j++) s += d[j] * d[j];
        rms.push(Math.sqrt(s / hop));
      }
      while (rms.length > fps * 8) rms.shift();
    };
    quelle.connect(proc);
    proc.connect(ctx.destination);          // nötig, damit der Prozessor läuft – gibt nur Stille aus
    const takt = setInterval(async () => {
      if (rms.length < fps * 3) { melde('Höre zu …'); return; }
      const onset = rms.map((v, i) => (i ? Math.max(0, Math.log1p(100 * v) - Math.log1p(100 * rms[i - 1])) : 0));
      const { bpm, schlagVorS } = tempoUndSchlag(onset, fps);
      const jetzt = rms.slice(-Math.round(fps * 2)).reduce((a, b) => a + b, 0) / Math.round(fps * 2);
      spitze = Math.max(jetzt, spitze * 0.995);
      const energie = jetzt < 0.004 ? 0 : Math.min(1, jetzt / spitze);
      const stufe = energie < 0.08 ? 'still' : energie < 0.35 ? 'ruhig' : energie < 0.7 ? 'mittel' : 'laut';
      melde(`Hört mit · ${Math.round(bpm)} BPM · ${stufe}`);
      const m = await api('/api/gehoer', 'POST', { aktion: 'messung', bpm, schlag_vor_s: schlagVorS + 0.05, energie }).catch(() => null);
      if (m && m.laeuft === false) aus(false);   // Tanz vorbei (Stopp, Stille, Not-Aus)
    }, 1500);
    lauf = { stream, ctx, proc, takt };
    knopf.setAttribute('aria-pressed', 'true');
    melde('Höre zu …');
  }

  function aus(melden = true) {
    if (!lauf) return;
    clearInterval(lauf.takt);
    lauf.proc.disconnect();
    lauf.stream.getTracks().forEach((t) => t.stop());
    lauf.ctx.close?.();
    lauf = null;
    knopf.setAttribute('aria-pressed', 'false');
    melde(melden ? '' : 'Tanz beendet – Mikrofon ist aus.');
    if (melden) api('/api/gehoer', 'POST', { aktion: 'stopp' }).catch(() => {});
  }

  knopf.addEventListener('click', () => (lauf ? aus() : an()));
  $('gehoer-quelle')?.addEventListener('change', (e) => { $('gehoer-pc-tipp').hidden = e.target.value !== 'pc'; });
  window.addEventListener('beforeunload', () => aus());
}

// ── Seite ───────// Spitzen je 50 ms für die Wellenform der Zeitleiste
export function wellenform(mono, rate) {
  const n = Math.floor(rate * WELLE_DT);
  const out = new Float32Array(Math.ceil(mono.length / n));
  for (let k = 0; k < out.length; k++) {
    let m = 0;
    for (let i = k * n, e = Math.min(mono.length, i + n); i < e; i++) m = Math.max(m, Math.abs(mono[i]));
    out[k] = m;
  }
  return out;
}

// ── Seite ─────────────────────────────────────────────────────────────
// Aufbau wie bei Choreographer (Spot) und Licht-Sequenzern: oben Wellenform mit Taktraster, darunter die Teile des
// Stücks, dann eine Spur für Bewegungen und eine für Posen und Gesten. Klick setzt die Startmarke.
export function initTanz({ $, api, el, toast, send, gestenName = (k) => k }) {
  const box = $('tanz-schritte');
  if (!box) return { spielen() {}, neu() {} };
  initGehoer({ $, api, toast });
  const wippen = initMitwippen({ $, api, el, toast, tempoUndSchlag });
  const audio = $('tanz-audio');
  const leinwand = $('tanz-zeitleiste');
  let choreo = null;        // {bpm, start, schritte, abschnitte, dauer}
  let musik = '';           // Dateiname im Datenordner
  let welle = null;         // Spitzen je 50 ms
  let posen = [];
  let gesten = [];
  let ki = false;
  let reachy = false;       // Reachy Mini: Bewegungen und Gefühle aus seinem eigenen Vokabular (seit 0.38.13)
  let gefuehle = [];
  let namen = {};
  const artText = (a) => (reachy ? ART_TEXT_REACHY : ART_TEXT)[a] || a;
  const nameText = (n) => namen[n] || gestenName(n);
  let ende = 0;
  let marke = 0;

  const taktS = () => 240 / (choreo?.bpm || 110);
  const farbe = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
  const TEIL_FARBE = { Intro: '--ink-3', Outro: '--ink-3', Strophe: '--data-1', Refrain: '--accent', Bridge: '--warning', Drop: '--critical', Breakdown: '--data-2' };
  const TEIL_NAMEN = ['Intro', 'Strophe', 'Refrain', 'Bridge', 'Drop', 'Breakdown', 'Outro'];
  // „Refrain 2“: gleiche Teile durchgezählt, damit man sie in Zeitleiste und Liste wiederfindet (seit 0.38.23)
  function teilTitel() {
    const zaehler = {};
    return (choreo?.abschnitte || []).map((a) => {
      zaehler[a.name] = (zaehler[a.name] || 0) + 1;
      const mehrere = (choreo.abschnitte || []).filter((b) => b.name === a.name).length > 1;
      return mehrere ? `${tr(a.name)} ${zaehler[a.name]}` : tr(a.name);
    });
  }

  function laenge() { return Math.max(choreo?.dauer || 0, welle ? welle.length * WELLE_DT : 0, 1); }

  function zeitleiste() {
    if (!choreo || !leinwand) return;
    const dpr = window.devicePixelRatio || 1;
    const w = leinwand.clientWidth;
    const h = 150;
    if (!w) return;
    leinwand.width = Math.round(w * dpr);
    leinwand.height = Math.round(h * dpr);
    const g = leinwand.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const L = laenge();
    const x = (t) => (t / L) * w;
    g.font = `11px ${getComputedStyle(document.body).fontFamily}`;
    // Wellenform
    if (welle) {
      g.fillStyle = farbe('--ink-3');
      const mitte = 26;
      const step = Math.max(1, Math.floor(welle.length / w));
      for (let k = 0; k < welle.length; k += step) {
        const a = Math.min(1, welle[k] * 1.4) * 22;
        g.fillRect(x(k * WELLE_DT), mitte - a, Math.max(1, x(step * WELLE_DT) - 0.5), 2 * a);
      }
    }
    // Taktraster: dünne Linie je Takt, kräftiger je vier Takte (Phrase)
    const tl = taktS();
    let n = 0;
    for (let t = choreo.start; t < L; t += tl, n++) {
      g.fillStyle = n % 4 === 0 ? farbe('--line-strong') : farbe('--line-soft');
      g.fillRect(x(t), 0, 1, h);
    }
    // Teile des Stücks (durchgezählt)
    const titel = teilTitel();
    (choreo.abschnitte || []).forEach((a, i) => {
      g.fillStyle = farbe(TEIL_FARBE[a.name] || '--ink-3');
      g.globalAlpha = 0.85;
      g.fillRect(x(a.t) + 1, 54, Math.max(1, x(a.takte * tl) - 2), 16);
      g.globalAlpha = 1;
      g.fillStyle = farbe('--ink-on-accent');
      if (x(a.takte * tl) > 44) g.fillText(titel[i], x(a.t) + 5, 66);
    });
    // Spuren: Bewegung (oben), Pose und Geste (unten)
    for (const s of choreo.schritte) {
      const unten = s.art === 'pose' || s.art === 'gefuehl';
      const y = unten ? 112 : 78;
      g.fillStyle = farbe(s.art === 'pose' ? '--accent' : s.art === 'gefuehl' ? '--data-2' : s.art === 'pause' ? '--line' : s.art === 'trick' ? '--data-2' : '--data-1');
      g.fillRect(x(s.t) + 1, y, Math.max(2, x(s.takte * tl) - 2), 28);
      const text = tr(s.name ? (s.art === 'pose' ? s.name : nameText(s.name)) : artText(s.art));
      if (x(s.takte * tl) > 40) { g.fillStyle = farbe('--ink-on-accent'); g.fillText(text, x(s.t) + 4, y + 18); }
    }
    // Startmarke und Abspielkopf
    g.fillStyle = farbe('--warning');
    g.beginPath(); g.moveTo(x(marke) - 6, 0); g.lineTo(x(marke) + 6, 0); g.lineTo(x(marke), 9); g.fill();
    g.fillRect(x(marke), 0, 1, h);
    if (!audio.paused) { g.fillStyle = farbe('--critical'); g.fillRect(x(audio.currentTime), 0, 2, h); }
  }

  leinwand?.addEventListener('click', (ev) => {
    if (!choreo) return;
    const r = leinwand.getBoundingClientRect();
    const t = ((ev.clientX - r.left) / r.width) * laenge();
    const n = Math.max(0, Math.round((t - choreo.start) / taktS()));      // auf einen Taktanfang einrasten
    marke = Math.min(choreo.dauer, choreo.start + n * taktS());
    if (n === 0) marke = 0;
    $('tanz-marke').textContent = `Startmarke: ${zeit(marke)} (Takt ${n + 1})`;
    zeitleiste();
  });
  new ResizeObserver(() => zeitleiste()).observe(leinwand);

  function namenWahl(s) {
    const sel = el('select', 'input');
    sel.setAttribute('aria-label', 'Name');
    const liste = [...(s.art === 'pose' ? posen : reachy && s.art === 'gefuehl' ? gefuehle : gesten)];
    if (s.name && !liste.includes(s.name)) liste.unshift(s.name);
    for (const n of liste) sel.append(new Option(tr(s.art === 'pose' ? n : nameText(n)), n));
    sel.value = s.name || liste[0] || '';
    s.name = sel.value;
    sel.addEventListener('change', () => { s.name = sel.value; zeitleiste(); });
    return sel;
  }

  // Teil, in dem ein Zeitpunkt liegt
  function teilVon(t) {
    const tl = taktS();
    return (choreo.abschnitte || []).findIndex((a) => a.t - 1e-3 <= t && t < a.t + a.takte * tl - 1e-3);
  }

  // Überschrift je Teil in der Liste: Name wählbar (der Tanz dieses Teils wird dann neu geplant), „wie der erste tanzen“
  function teilKopf(i, titel) {
    const a = choreo.abschnitte[i];
    const li = el('li', 'tanz-teil');
    li.style.setProperty('--teil-farbe', `var(${TEIL_FARBE[a.name] || '--ink-3'})`);
    li.append(el('strong', '', titel[i]), el('span', 'field-help', `${zeit(a.t)} · ${a.takte} ${tr('Takte')}`));
    const wahl = el('select', 'input');
    wahl.setAttribute('aria-label', `${tr('Teil des Stücks')}: ${titel[i]}`);
    for (const n of TEIL_NAMEN) wahl.append(new Option(tr(n), n));
    wahl.value = a.name;
    wahl.addEventListener('change', () => teilNeu(i, wahl.value));
    li.append(wahl);
    const erster = choreo.abschnitte.findIndex((b) => b.name === a.name);
    if (erster !== i) {
      const gleich = el('button', 'btn btn--ghost btn--sm', 'Wie der erste tanzen');
      gleich.type = 'button';
      gleich.addEventListener('click', () => wieDerErste(i, erster));
      li.append(gleich);
    }
    return li;
  }

  // Schritte im Zeitraum eines Teils durch andere ersetzen (die übrigen Teile bleiben, wie man sie eingestellt hat)
  function ersetzeTeil(i, neue) {
    const a = choreo.abschnitte[i], ende = a.t + a.takte * taktS();
    const drin = (s) => s.t >= a.t - 1e-3 && s.t < ende - 1e-3;
    choreo.schritte = [...choreo.schritte.filter((s) => !drin(s)), ...neue.filter(drin)].sort((p, q) => p.t - q.t);
  }

  async function teilNeu(i, name) {
    choreo.abschnitte[i].name = name;
    if (!choreo.energie || !choreo.energie.length) { zeichne(); toast('Name geändert. Für einen neuen Tanz in diesem Teil das Stück noch einmal wählen.'); return; }
    const tl = taktS();
    const teile = choreo.abschnitte.map((a) => ({ takt: Math.round((a.t - choreo.start) / tl), takte: a.takte, name: a.name, ...(a.gruppe ? { gruppe: a.gruppe } : {}) }));
    const r = await api('/api/choreo/plan', 'POST', { analyse: { bpm: choreo.bpm, start: choreo.start, energie: choreo.energie, klang: choreo.klang, teile } }).catch(() => null);
    if (!r || !r.ok) { zeichne(); toast('Neu planen ging nicht – der Name ist trotzdem geändert.', true); return; }
    ersetzeTeil(i, r.choreo.schritte);
    zeichne();
    toast(`${tr(name)}: ${tr('neu getanzt')}`);
  }

  // Den Tanz des ersten gleichnamigen Teils übernehmen (wiederholt oder gekürzt, damit er genau passt)
  function wieDerErste(i, j) {
    const tl = taktS(), q = choreo.abschnitte[j], z = choreo.abschnitte[i];
    const vorlage = choreo.schritte.filter((s) => s.t >= q.t - 1e-3 && s.t < q.t + q.takte * tl - 1e-3);
    if (!vorlage.length) return;
    const neue = [];
    let takt = 0;
    while (takt < z.takte) {
      for (const s of vorlage) {
        const rel = Math.round((s.t - q.t) / tl);
        if (takt + rel >= z.takte) break;
        const n = Math.min(s.takte, z.takte - takt - rel);
        neue.push({ ...s, t: Math.round((z.t + (takt + rel) * tl) * 1000) / 1000, takte: n });
      }
      takt += q.takte;
    }
    ersetzeTeil(i, neue);
    zeichne();
  }

  function zeichne() {
    box.replaceChildren();
    if (!choreo) return;
    const titel = teilTitel();
    let teilDavor = -2;
    choreo.schritte.forEach((s, i) => {
      const teil = teilVon(s.t);
      if (teil >= 0 && teil !== teilDavor) box.append(teilKopf(teil, titel));
      teilDavor = teil;
      const li = el('li');
      li.dataset.i = String(i);
      li.append(el('span', 'tanz-zeit', zeit(s.t)));
      const takte = el('input', 'input');
      Object.assign(takte, { type: 'number', min: 1, max: 64, value: s.takte });
      takte.setAttribute('aria-label', 'Takte');
      takte.addEventListener('change', () => { s.takte = Math.max(1, Math.min(64, Number(takte.value) || 1)); neuTakten(); });
      const art = el('select', 'input');
      art.setAttribute('aria-label', 'Bewegung');
      const arten = reachy ? [...ARTEN_REACHY] : [...ARTEN];
      if (!arten.includes(s.art)) arten.push(s.art);     // älterer Tanz: Schritt bleibt sichtbar (Reachy übersetzt ihn)
      for (const a of arten) {
        const o = new Option(tr(artText(a)), a);
        if (a === 'pose' && !posen.length) o.disabled = true;
        art.append(o);
      }
      art.value = s.art;
      art.addEventListener('change', () => {
        s.art = art.value;
        if (!MIT_NAME.has(s.art)) delete s.name; else s.name = '';
        zeichne();
      });
      li.append(takte, art, MIT_NAME.has(s.art) ? namenWahl(s) : el('span'));
      box.append(li);
    });
    $('tanz-aktionen').hidden = false;
    $('tanz-speichern').hidden = false;
    $('tanz-zeit-box').hidden = false;
    $('tanz-ki').hidden = !ki;
    zeitleiste();
  }

  // Nach einer Änderung der Taktzahl rücken die folgenden Schritte nach (lückenlos ab dem ersten Schlag).
  function neuTakten() {
    let t = choreo.schritte[0]?.t ?? choreo.start;
    for (const s of choreo.schritte) { s.t = Math.round(t * 1000) / 1000; t += s.takte * taktS(); }
    choreo.dauer = Math.round(t * 100) / 100;
    zeichne();
  }

  async function welleLaden(datei) {
    welle = null;
    if (!datei) return;
    try {
      const r = await fetch(`/api/musik/${encodeURIComponent(datei)}`);
      if (!r.ok) return;
      const { mono, rate } = await dekodiere(r);
      welle = wellenform(mono, rate);
      zeitleiste();
    } catch { /* ohne Wellenform geht es auch */ }
  }

  async function oeffnen(name) {
    const r = await api(`/api/choreo/${encodeURIComponent(name)}`);
    if (!r.ok) { toast('Tanz nicht gefunden'); return; }
    choreo = r.choreo;
    musik = r.choreo.musik || '';
    marke = 0;
    $('tanz-name').value = name;
    $('tanz-analyse').textContent = `${name}: ${Math.round(choreo.bpm)} BPM, ${choreo.schritte.length} Schritte.`;
    zeichne();
    welleLaden(musik);
  }

  async function laden() {
    const d = await api('/api/choreo').catch(() => null);
    if (!d) return;
    posen = d.posen || [];
    gesten = d.gesten || [];
    ki = Boolean(d.ki);
    reachy = Boolean(d.reachy);
    gefuehle = d.gefuehle || [];
    namen = d.namen || {};
    const ul = $('tanz-liste');
    ul.replaceChildren();
    if (!d.taenze?.length) ul.append(el('li', 'field-help', 'Noch kein Tanz gespeichert.'));
    for (const t of d.taenze || []) {
      const li = el('li');
      const info = el('div');
      info.append(el('strong', '', t.name), el('span', 'field-help', ` · ${Math.round(t.bpm)} BPM · ${zeit(t.dauer || 0)}${t.musik ? '' : ` · ${tr('ohne Musik')}`}${t.koerper === 'reachy_mini' ? ` · ${tr('für Reachy')}` : ''}`));
      const knoepfe = el('div', 'input-row');
      const los = el('button', 'btn btn--primary', 'Tanzen');
      los.type = 'button';
      los.addEventListener('click', () => tanzen({ name: t.name }));
      const bearb = el('button', 'btn', 'Bearbeiten');
      bearb.type = 'button';
      bearb.addEventListener('click', () => oeffnen(t.name));
      const weg = el('button', 'btn btn--ghost', 'Löschen');
      weg.type = 'button';
      weg.addEventListener('click', async () => {
        await api('/api/choreo', 'DELETE', { name: t.name });
        laden();
      });
      knoepfe.append(los, bearb, weg);
      li.append(info, knoepfe);
      ul.append(li);
    }
    if (choreo) zeichne();
  }

  async function tanzen(body) {
    const r = await api('/api/choreo/tanzen', 'POST', body).catch(() => ({ ok: false }));
    if (!r.ok) { toast(r.fehler || r.text || 'Tanzen geht gerade nicht'); return false; }
    return true;
  }

  // Musik gehört zum Tanz (seit 0.37.1, Hinweis aus dem Test „wie kann ich Musik im Tanzmodus stoppen?“): Endet der Tanz –
  // Stopp, Not-Aus, Esc, ein anderer Befehl –, hört auch die Musik auf. Solange sie spielt, steht oben im Tanzbereich
  // eine Leiste mit Stopp-Knopf.
  let fuerTanz = false;
  let ohneTanzSeit = 0;
  let titel = '';
  const leiste = $('tanz-spielt');
  function leisteZeigen() {
    if (!leiste) return;
    leiste.hidden = audio.paused;
    $('tanz-spielt-titel').textContent = `${tr('Läuft:')} ${titel || tr('Musik')}`;
  }
  function pruefen(engine) {
    if (audio.paused || !fuerTanz) { ohneTanzSeit = 0; return; }
    if (String((engine && engine.aktuell) || '').startsWith('choreo')) { ohneTanzSeit = 0; return; }
    const jetzt = performance.now();
    if (!ohneTanzSeit) ohneTanzSeit = jetzt;
    else if (jetzt - ohneTanzSeit > 1200) { ohneTanzSeit = 0; audio.pause(); }   // kurz Luft: der Tanz startet ggf. erst
  }

  function spielen(datei, ab = 0, bis = 0) {
    if (!datei) return;
    const src = `/api/musik/${encodeURIComponent(datei)}`;
    if (!audio.src.endsWith(src)) audio.src = src;
    titel = (choreo && choreo.musik === datei && choreo.name) || datei.replace(/^[0-9a-f]{8,}[-_]/i, '').replace(/\.[a-z0-9]+$/i, '');
    fuerTanz = true;
    ohneTanzSeit = 0;
    ende = bis;
    const los = () => {
      audio.currentTime = ab || 0;
      audio.play().catch(() => toast('Musik kann nicht abgespielt werden – einmal auf die Seite tippen und erneut versuchen'));
    };
    if (audio.readyState >= 1) los(); else audio.addEventListener('loadedmetadata', los, { once: true });
  }

  // Nur Tanz und Musik anhalten – kein Not-Aus (seit 0.38.34; vorher folgte die 2-Minuten-Sperre). Der Not-Aus bleibt links.
  function stopp() {
    api('/api/choreo/stopp', 'POST').catch(() => null);
    audio.pause();
    for (const li of box.querySelectorAll('.is-jetzt')) li.classList.remove('is-jetzt');
    zeitleiste();
  }

  audio.addEventListener('timeupdate', () => {
    if (ende && audio.currentTime > ende + 1) audio.pause();
    if (!choreo) return;
    const t = audio.currentTime;
    const i = choreo.schritte.findIndex((s) => t >= s.t && t < s.t + s.takte * taktS());
    for (const li of box.children) li.classList.toggle('is-jetzt', Number(li.dataset.i) === i);
    zeitleiste();
  });
  audio.addEventListener('pause', () => { fuerTanz = false; zeitleiste(); leisteZeigen(); });
  audio.addEventListener('play', leisteZeigen);
  audio.addEventListener('ended', leisteZeigen);
  if (leiste) $('tanz-spielt-stopp').addEventListener('click', stopp);

  // Musikstück wählen (seit 0.37.10, Hinweis aus dem Test „Musikstück laden geht nicht mehr“): ein echter Knopf öffnet die
  // Dateiauswahl selbst – und das Stück lässt sich auch einfach auf die Karte ziehen
  $('tanz-waehlen').addEventListener('click', () => {
    const inp = $('tanz-datei');
    inp.value = '';                            // dasselbe Stück noch einmal wählen löst auch „change“ aus
    inp.click();
  });
  const ablage = $('tanz-ablage');
  ablage.addEventListener('dragover', (e) => { e.preventDefault(); ablage.classList.add('is-ziel'); });
  ablage.addEventListener('dragleave', () => ablage.classList.remove('is-ziel'));
  ablage.addEventListener('drop', (e) => {
    e.preventDefault();
    ablage.classList.remove('is-ziel');
    const d = e.dataTransfer?.files?.[0];
    if (d) stueckLaden(d);
  });
  $('tanz-datei').addEventListener('change', (ev) => { const d = ev.target.files?.[0]; if (d) stueckLaden(d); });

  async function stueckLaden(datei) {
    if (!datei) return;
    $('tanz-datei-name').textContent = `${datei.name} · ${(datei.size / 1048576).toLocaleString(document.documentElement.lang || 'de', { maximumFractionDigits: 1 })} MB`;
    const info = $('tanz-analyse');
    info.textContent = 'Höre mir das Stück an …';
    try {
      if (datei.size > 40 * 1024 * 1024) throw new Error('Die Datei ist größer als 40 MB.');
      const { puffer, mono, rate } = await dekodiere(datei);
      const analyse = analysiere(mono, rate);
      welle = wellenform(mono, rate);
      const hoch = await fetch(`/api/musik?name=${encodeURIComponent(datei.name)}`, { method: 'POST', body: puffer }).then((r) => r.json());
      if (!hoch.ok) throw new Error(hoch.fehler || 'Hochladen ging nicht.');
      musik = hoch.datei;
      const plan = await api('/api/choreo/plan', 'POST', { analyse });
      if (!plan.ok) throw new Error(plan.fehler || 'Kein Tanz geplant.');
      choreo = plan.choreo;
      marke = 0;
      $('tanz-name').value = datei.name.replace(/\.[^.]+$/, '').slice(0, 60);
      info.textContent = `${Math.round(analyse.bpm)} BPM, ${analyse.energie.length} Takte – ${choreo.schritte.length} Schritte geplant.`;
      zeichne();
    } catch (e) {
      // decodeAudioData meldet nur „EncodingError“ – sagen, was das heißt
      const msg = e && e.name === 'EncodingError'
        ? 'Dieses Format kann der Browser nicht lesen (z. B. kopiergeschützt oder WMA) – bitte mp3, m4a, ogg, wav oder flac.'
        : (e.message || e);
      info.textContent = `Das ging nicht: ${msg}`;
    }
  }

  $('tanz-probe').addEventListener('click', async () => {
    if (choreo && await tanzen({ choreo })) spielen(musik, 0, choreo.dauer);
  });
  $('tanz-ab').addEventListener('click', async () => {
    if (choreo && await tanzen({ choreo, ab: marke })) spielen(musik, marke, choreo.dauer);
  });
  $('tanz-stopp').addEventListener('click', stopp);
  $('tanz-ki').addEventListener('click', async () => {
    if (!choreo) return;
    const r = await api('/api/choreo/ki', 'POST', { name: $('tanz-name').value.trim(), musik, choreo }).catch(() => ({ ok: false }));
    toast(r.ok ? 'Die KI denkt sich einen Tanz aus – siehe Gespräch' : (r.fehler || 'Geht gerade nicht'));
  });
  $('tanz-speichern').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const name = $('tanz-name').value.trim();
    const r = await api('/api/choreo/speichern', 'POST', { name, choreo, musik });
    if (!r.ok) return toast(r.fehler || 'Speichern ging nicht');
    toast(`Tanz „${r.choreo.name}“ gespeichert`);
    laden();
  });

  const seite = box.closest('[data-part]');
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) laden(); }).observe(seite);
  return {
    spielen: (datei, ab) => spielen(datei, ab || 0, 0),
    pruefen: (engine) => { pruefen(engine); wippen.pruefen(engine); },
    // ein neu gespeicherter Tanz (z. B. von der KI): Liste auffrischen und im Editor öffnen
    neu: async (name) => { await laden(); if (name) oeffnen(name); },
    laden,
  };
}
