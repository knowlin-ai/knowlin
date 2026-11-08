// Sprache: Erkennung (Browser oder lokales Whisper), Vorlesen, Entenlaute.
import { sprache } from './i18n.js';

// ── Entenlaute, synthetisch (WebAudio) ─────────────────────────────────
let audioCtx = null;
function ctx() {
  audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  return audioCtx;
}
// Browser erlauben Ton erst nach einer Bedienung der Seite. Wer nur per Stimme spricht, hat nie geklickt –
// deshalb den Ton beim ersten Tastendruck oder Klick freischalten (seit 0.37.6).
for (const ev of window.addEventListener ? ['pointerdown', 'keydown'] : []) {
  window.addEventListener(ev, () => { try { ctx(); } catch { /* ohne WebAudio */ } }, { capture: true, passive: true });
}

function quack(at, { f0 = 520, f1 = 380, dur = 0.16, gain = 0.25, bright = 1400, ort = null } = {}) {
  const a = ctx();
  const osc = a.createOscillator();
  osc.type = 'sawtooth';
  const k = klangRate();                    // Klangsignatur
  osc.frequency.setValueAtTime(f0 * k, at);
  osc.frequency.exponentialRampToValueAtTime(Math.max(60, f1 * k), at + dur);
  const nasal = a.createBiquadFilter();
  nasal.type = 'bandpass';
  nasal.frequency.setValueAtTime(bright * (1 + 0.35 * klang.farbe), at);
  nasal.Q.value = 3.5;
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, at);
  g.gain.exponentialRampToValueAtTime(gain, at + 0.015);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  const p = raum(a, ort);
  (p ? osc.connect(nasal).connect(g).connect(p) : osc.connect(nasal).connect(g)).connect(a.destination);
  osc.start(at);
  osc.stop(at + dur + 0.02);
}

// ── Die echte Stimme: Pollens Synthesizer, vorab gerendert (sounds/voice) ──
const BASE = new URL('./sounds/', import.meta.url);
const raw = new Map();       // Datei → Promise<ArrayBuffer>: früh geladen, damit der erste Ton nicht hinterherhinkt
const buffers = new Map();   // Datei → Promise<AudioBuffer>: dekodiert beim ersten Abspielen (braucht den AudioContext)
let bank = null;

function fetchRaw(path) {
  if (!raw.has(path)) {
    raw.set(path, fetch(new URL(path, BASE)).then((r) => {
      if (!r.ok) throw new Error(r.status);
      return r.arrayBuffer();
    }).catch(() => null));
  }
  return raw.get(path);
}
// Vorladen: Stimmbank und Pollens Emotions-Töne (zusammen ≈ 0,5 MB, nur einmal pro Sitzung)
fetch(new URL('voice/index.json', BASE)).then((r) => (r.ok ? r.json() : null)).then((j) => {
  bank = j;
  for (const files of Object.values((j && j.tags) || {})) for (const f of files) fetchRaw(`voice/${f}`);
}).catch(() => {});
fetch(new URL('emotions/index.json', BASE)).then((r) => (r.ok ? r.json() : null)).then((j) => {
  for (const f of (j && j.dateien) || []) fetchRaw(`emotions/${f}`);
}).catch(() => {});

async function buffer(path) {
  if (!buffers.has(path)) {
    buffers.set(path, fetchRaw(path).then((b) => (b ? ctx().decodeAudioData(b.slice(0)) : null)).catch(() => null));
  }
  return buffers.get(path);
}

// Klangsignatur (seit 0.36.1): Tonhöhe in Halbtönen und Klangfarbe −1 (dunkler) … +1 (heller), für alle Laute
let klang = { hoehe: 0, farbe: 0 };
export function setKlang(hoehe = 0, farbe = 0) { klang = { hoehe: Number(hoehe) || 0, farbe: Number(farbe) || 0 }; }
const klangRate = () => 2 ** (klang.hoehe / 12);
function klangFilter(a) {
  const f = a.createBiquadFilter();
  f.type = 'highshelf';
  f.frequency.value = 1800;
  f.gain.value = klang.farbe * 9;          // ± 9 dB über 1,8 kHz
  return f;
}

// Räumlicher Klang (seit 0.38.4): Laute anderer Roboter kommen von dort, wo sie stehen – links, rechts, vorn,
// hinten, nah oder fern, gehört aus der Sicht der eigenen Verkörperung. `ort` = {x, y} in Metern relativ zur Verkörperung
// (x vorn, y links); ohne `ort` klingt es wie bisher mittig.
function raum(a, ort) {
  if (!ort) return null;
  const p = a.createPanner();
  p.panningModel = 'HRTF';
  p.distanceModel = 'inverse';
  p.refDistance = 0.4;
  p.rolloffFactor = 1.3;
  p.maxDistance = 12;
  // Web Audio: Hörer schaut nach −z, x rechts, y oben
  const x = -ort.y, z = -ort.x;
  if (p.positionX) { p.positionX.value = x; p.positionY.value = 0; p.positionZ.value = z; } else p.setPosition(x, 0, z);
  return p;
}

// Wie am Roboter (robotd sound.rs): ein neuer Laut beendet den vorigen – kein Durcheinander. Andere Roboter haben
// ihre eigene Stimme und unterbrechen die eigene Verkörperung nicht.
let current = null;
async function playFile(path, gain = 0.85, rate = 1, ort = null) {
  let a;
  try { a = ctx(); } catch { return false; }
  const buf = await buffer(path);
  if (!buf) return false;
  if (current && !ort) { try { current.stop(); } catch { /* schon vorbei */ } }
  const src = a.createBufferSource();
  src.buffer = buf;
  src.playbackRate.value = rate * klangRate();
  const g = a.createGain();
  g.gain.value = gain;
  const kette = src.connect(klangFilter(a)).connect(g);
  const p = raum(a, ort);
  (p ? kette.connect(p) : kette).connect(a.destination);
  if (!ort) {
    src.onended = () => { if (current === src) current = null; };
    current = src;
  }
  src.start();
  return true;
}

function synthSound(tag, ort = null) {
  let t;
  try { t = ctx().currentTime + 0.01; } catch { return; }
  switch (tag) {
    case 'greet': quack(t, { ort }); quack(t + 0.2, { f0: 600, f1: 430, ort }); break;
    case 'inquire': quack(t, { f0: 380, f1: 720, dur: 0.26, bright: 1600, ort }); break;
    case 'alarm': quack(t, { f0: 700, f1: 520, dur: 0.32, gain: 0.35, bright: 1900, ort }); break;
    case 'coo': quack(t, { f0: 300, f1: 240, dur: 0.45, gain: 0.12, bright: 700, ort }); break;
    case 'peck': quack(t, { f0: 220, f1: 140, dur: 0.09, gain: 0.3, bright: 500, ort }); break;
    case 'wheee': quack(t, { f0: 420, f1: 980, dur: 0.6, gain: 0.2, bright: 1800, ort }); break;
    default: quack(t, { ort });
  }
}

// Nie zweimal hintereinander dieselbe Variante. Wie Pollen: keine Verstimmung beim Abspielen – die Abwechslung
// kommt aus 10–12 vorgerenderten Varianten je Ton mit der Stimme der Ente (tools/render_voice.py).
const lastPick = new Map();
function pickVariant(key, files) {
  if (files.length < 2) return files[0];
  let f;
  do { f = files[Math.floor(Math.random() * files.length)]; } while (f === lastPick.get(key));
  lastPick.set(key, f);
  return f;
}
const detune = (cents) => 2 ** ((Math.random() * 2 - 1) * cents / 1200);

// Ton-Tag der Stimmbank: eine Variante der echten Entenstimme, sonst synthetisch
export async function playSound(tag, eigeneStimme, ort = null) {
  // Weitere Enten (0.36.3) bringen ihre Klangsignatur mit [Höhe, Farbe] – nur für diesen einen Laut
  const vorher = klang;
  if (Array.isArray(eigeneStimme)) klang = { hoehe: Number(eigeneStimme[0]) || 0, farbe: Number(eigeneStimme[1]) || 0 };
  try {
    const files = bank && bank.tags && bank.tags[tag];
    if (files && files.length && await playFile(`voice/${pickVariant(tag, files)}`, 0.85, 1, ort)) return;
    synthSound(tag, ort);
  } finally {
    klang = vorher;
  }
}

// Laut zu einer Geste: Pollens Emotionen (emotions/…) oder die eigenen Gesten (gesten/…)
export function playClip(name) {
  const m = /^(gesten\/)?([a-z_]+?)(_\d+)?$/.exec(name || '');
  if (!m) return;
  if (m[1]) playFile(`${name}.ogg`, 0.9, detune(15));
  else playFile(`emotions/${name}.ogg`, 0.9);
}

// ── Vorlesen ───────────────────────────────────────────────────────────
let germanVoice = null;
let preferredVoice = null;
try { preferredVoice = localStorage.getItem('duckpilot.voice'); } catch { /* egal */ }

// Sprache der Ente (seit 0.34): Erkennen und Vorlesen in der eingestellten Sprache
const langCode = () => (sprache() === 'en' ? 'en-US' : 'de-DE');

export function germanVoices() {
  const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  const pre = langCode().slice(0, 2);
  return voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith(pre));
}

function pickVoice() {
  const de = germanVoices();
  // gewählte Stimme, sonst lokale Stimmen bevorzugen (bleiben auf dem Gerät)
  germanVoice = de.find((v) => v.name === preferredVoice) || de.find((v) => v.localService) || de[0] || null;
}
if (window.speechSynthesis) {
  pickVoice();
  speechSynthesis.addEventListener('voiceschanged', pickVoice);
}

export function setVoice(name) {
  preferredVoice = name || null;
  try { localStorage.setItem('duckpilot.voice', name || ''); } catch { /* egal */ }
  pickVoice();
}

export function currentVoice() { return germanVoice ? germanVoice.name : null; }

export function speak(text, { onStart, onEnd, goofy = false, mood = 'ausgeglichen', energie = 0.5 } = {}) {
  if (!window.speechSynthesis || !text) { onEnd && onEnd(); return; }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/\(.*?\)/g, ''));
  u.lang = langCode();
  if (!germanVoice || !germanVoice.lang.toLowerCase().startsWith(u.lang.slice(0, 2))) pickVoice();
  if (germanVoice) u.voice = germanVoice;
  // Stimme folgt Temperament, Stimmung und Albernheit – dezent, damit es natürlich bleibt
  const tone = { begeistert: [0.08, 0.15], 'fröhlich': [0.04, 0.08], frustriert: [-0.04, -0.1], angestrengt: [0, -0.05],
    erschrocken: [0.06, 0.12], 'mitfühlend': [-0.12, -0.08] }[mood] || [0, 0];
  u.rate = (goofy ? 1.1 + Math.random() * 0.12 : 1.0) + (energie - 0.5) * 0.16 + tone[0];
  u.pitch = (goofy ? 1.4 + Math.random() * 0.25 : 1.15) + tone[1];
  u.onstart = () => onStart && onStart();
  u.onend = u.onerror = () => onEnd && onEnd();
  speechSynthesis.speak(u);
}

export function stopSpeaking() {
  if (window.speechSynthesis) speechSynthesis.cancel();
  const ende = laufendEnde;
  stopPlan();
  if (ende) ende();      // angehalten: Mikrofon wieder an, sonst bliebe es nach dem Stopp stumm (seit 0.37.6)
}

// ── Die eigene Stimme: Sätze vom PC (Piper / Qwen3-TTS) und Entenlaute dazwischen ──
// plan = { motor: 'browser'|'piper'|'qwen', teile: [{art:'text', text, id?} | {art:'laut', ton}] }
let planToken = 0;
let planSource = null;
let laufendEnde = null;   // onEnd des laufenden Plans – für stopSpeaking()
const LAUT_MS = { greet: 520, inquire: 420, chirp: 330, coo: 600, alarm: 480, peck: 220, wheee: 720 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function stopPlan() {
  planToken += 1;
  if (planSource) { try { planSource.stop(); } catch { /* schon zu Ende */ } planSource = null; }
}

async function fetchClip(id) {
  const r = await fetch(`/api/stimme/clip/${id}.wav`);
  if (!r.ok) {
    let why = `HTTP ${r.status}`;
    try { why = (await r.json()).fehler || why; } catch { /* egal */ }
    throw new Error(why);
  }
  return ctx().decodeAudioData(await r.arrayBuffer());
}

// → true = abgespielt; false = der Browser gibt den Ton nicht frei (dann spricht die Browser-Stimme)
async function playBuffer(buf) {
  const a = ctx();
  if (a.state !== 'running') await Promise.race([a.resume().catch(() => {}), sleep(400)]);
  if (a.state !== 'running') return false;
  return new Promise((resolve) => {
    const src = a.createBufferSource();
    src.buffer = buf;
    const g = a.createGain();
    g.gain.value = 0.95;
    src.connect(g).connect(a.destination);
    let fertig = false;
    const ende = () => { if (fertig) return; fertig = true; if (planSource === src) planSource = null; resolve(true); };
    src.onended = ende;
    setTimeout(ende, buf.duration * 1000 + 1500);     // falls „ended“ ausbleibt, hängt das Gespräch nicht
    planSource = src;
    src.start();
  });
}

// Wie lange ein Satz vom PC höchstens auf sich warten lässt, bevor die Browser-Stimme einspringt (seit 0.37.6)
export const STIMME = { clipWartenMs: 15000 };
const mitFrist = (p, ms) => Promise.race([p, sleep(ms).then(() => new Error('zu langsam'))]);

function speakOnce(text, opts) {
  return new Promise((resolve) => speak(text, { ...opts, onStart: opts.onStart, onEnd: resolve }));
}

/**
 * Eine Antwort abspielen. Die Sätze holt sie vom PC (dort schon im Entstehen), Laute
 * schickt sie per `send` an duckpilot – am Roboter quakt dann die echte Ente.
 * hooks: send(msg), onStart(), onEnd(), onError(text), mood, goofy, energie
 */
export async function playPlan(plan, hooks = {}) {
  stopPlan();
  if (window.speechSynthesis) speechSynthesis.cancel();
  const token = planToken;
  const parts = (plan && plan.teile) || [];
  if (!parts.length) { hooks.onEnd && hooks.onEnd(); return; }
  const live = () => token === planToken;
  // alle Sätze gleich anfordern – der PC rechnet sie der Reihe nach, der erste ist schnell da
  const clips = parts.map((p) => (p.art === 'text' && p.id ? fetchClip(p.id).catch((e) => e) : null));
  let started = false;
  let beendet = false;
  const ende = () => { if (beendet) return; beendet = true; if (laufendEnde === ende) laufendEnde = null; hooks.onEnd && hooks.onEnd(); };
  const start = () => { if (!started) { started = true; laufendEnde = ende; hooks.onStart && hooks.onStart(); } };
  let fellBack = false;
  for (let i = 0; i < parts.length && live(); i++) {
    const p = parts[i];
    if (p.art === 'laut') {
      start();
      hooks.send && hooks.send({ type: 'laut', ton: p.ton });
      await sleep(LAUT_MS[p.ton] || 400);
      continue;
    }
    // Wartezeit je Antwort aus dem gemessenen Tempo (seit 0.37.9); einmal auf die Browser-Stimme gewechselt, bleibt
    // die ganze Antwort dabei – kein Hin und Her zwischen zwei Stimmen
    const frist = Math.max(STIMME.clipWartenMs, ((plan && plan.warten_s) || 0) * 1000);
    const buf = clips[i] && !fellBack ? await mitFrist(clips[i], frist) : (clips[i] ? new Error('') : null);
    if (!live()) break;
    start();
    let gespielt = false;
    if (buf && !(buf instanceof Error)) {
      hooks.send && hooks.send({ type: 'speaking', id: p.id });
      gespielt = await playBuffer(buf);
      if (!gespielt) hooks.send && hooks.send({ type: 'speaking_end' });
    }
    if (!gespielt) {
      const why = buf instanceof Error ? buf.message : buf ? 'Ton gesperrt' : '';
      if (why && !fellBack) { fellBack = true; hooks.onError && hooks.onError(why); }
      hooks.send && hooks.send({ type: 'speaking', sekunden: Math.max(0.6, p.text.length / 14) });
      await speakOnce(p.text, { goofy: hooks.goofy, mood: hooks.mood, energie: hooks.energie });
    }
    hooks.send && hooks.send({ type: 'speaking_end' });
    if (i < parts.length - 1 && live()) await sleep(110);
  }
  if (live()) ende();
  else if (laufendEnde === ende) laufendEnde = null;
}

// ── Erkennung ──────────────────────────────────────────────────────────
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

// Weckwort finden (seit 0.37.5, Hinweis aus dem Test „Weckwort reagiert nicht richtig“): als ganzes Wort (nicht in „Rente“
// oder „Enten“), am Satzanfang (die ersten drei Wörter) und mit den häufigsten Verhörern der Spracherkennung.
// → Rest des Satzes nach dem Weckwort ('' = nur das Weckwort) oder null.
const VERHOERER = { ente: ['ente', 'ende', 'änte', 'endte', 'entе'], duck: ['duck', 'doc', 'dock', 'ducky', 'duc'] };
export function findeWeckwort(text, wake) {
  const woerter = String(text || '').toLowerCase().replace(/[^\p{L}\p{N}\s'-]+/gu, ' ').split(/\s+/).filter(Boolean);
  const varianten = VERHOERER[wake] || [wake];
  const teile = wake.split(/\s+/).filter(Boolean);
  for (let i = 0; i < Math.min(3, woerter.length); i++) {
    const passt = teile.length > 1
      ? teile.every((t, k) => woerter[i + k] === t)
      : varianten.includes(woerter[i]);
    if (!passt) continue;
    // „Hey Ente“, „Hallo Ente“ – davor darf nur eine Anrede stehen
    if (i > 0 && !woerter.slice(0, i).every((w) => ['hey', 'hallo', 'hi', 'ok', 'okay', 'he', 'du', 'na', 'liebe', 'kleine'].includes(w))) continue;
    const rest = String(text).trim().split(/\s+/).slice(i + teile.length).join(' ').replace(/^[\s,.!?:;-]+/, '');
    return rest;
  }
  return null;
}

export class Listener {
  // mode: 'browser' | 'whisper' | 'aus'
  constructor({ mode, wakeWord, onPartial, onFinal, onState, onError }) {
    this.mode = mode;
    this.wake = (wakeWord || 'ente').toLowerCase();
    if (this.wake === 'ente' && sprache() === 'en') this.wake = 'duck';   // Standard-Weckwort auf Englisch (0.34)
    this.cb = { onPartial, onFinal, onState, onError };
    this.active = false;   // Push-to-Talk läuft
    this.always = false;   // Dauerhören mit Weckwort
    this.muted = false;    // während die Ente spricht
    this.rec = null;
    this.media = null;
    this.level = 0;
  }

  get supported() {
    if (!window.isSecureContext) return false;   // Mikrofon nur über localhost/https – im WLAN per http nicht
    if (this.mode === 'browser') return !!SR;
    if (this.mode === 'whisper') return !!(navigator.mediaDevices && window.MediaRecorder);
    return false;
  }

  _state(s) { this.cb.onState && this.cb.onState(s); }

  // Push-to-Talk
  async start() {
    if (this.inWindow) this.closeWindow();
    if (this.active || !this.supported) return;
    this.active = true;
    this._state('listening');
    if (this.mode === 'browser') this._startBrowser(false);
    else await this._startRecorder();
  }

  dispose() {
    this.always = false;
    this.active = false;
    try { this.rec && this.rec.abort(); } catch { /* egal */ }
    this.rec = null;
  }

  stop() {
    if (!this.active) return;
    this.active = false;
    if (this.mode === 'browser' && this.rec) this.rec.stop();
    if (this.mode === 'whisper' && this.media) this.media.stop();
  }

  // Gesprächsfenster (Plaudern): nach der Antwort kurz ohne Weckwort zuhören
  openWindow(seconds = 8) {
    if (this.mode !== 'browser' || !SR || this.active || this.muted) return false;
    this.active = true;
    this.inWindow = true;
    this._state('window');
    this._startBrowser(false);
    clearTimeout(this._windowTimer);
    this._windowTimer = setTimeout(() => { if (this.inWindow) this.closeWindow(); }, seconds * 1000);
    return true;
  }

  closeWindow() {
    clearTimeout(this._windowTimer);
    if (!this.inWindow) return;
    this.inWindow = false;
    if (this.active) { this.active = false; try { this.rec && this.rec.abort(); } catch { /* egal */ } }
    this._state(this.always ? 'always' : 'idle');
    if (this.always) setTimeout(() => this._startBrowser(true), 250);
  }

  setAlways(on) {
    this.always = on && this.mode === 'browser' && !!SR;
    if (this.always) this._startBrowser(true);
    else if (this.rec && !this.active) this.rec.abort();
    this._state(this.always ? 'always' : 'idle');
    return this.always;
  }

  pause(on) {
    this.muted = on;
    if (on && this.rec && this.always && !this.active) this.rec.abort();
    if (!on && this.always && !this.active) setTimeout(() => { if (this.always && !this.active && !this.muted) this._startBrowser(true); }, 300);
  }

  _startBrowser(continuous) {
    if (this.rec) { try { this.rec.abort(); } catch { /* egal */ } }
    const rec = new SR();
    rec.lang = langCode();
    rec.interimResults = true;
    rec.continuous = continuous;
    rec.maxAlternatives = 1;
    let finalText = '';
    rec.onresult = (e) => {
      if (this.rec !== rec) return;
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          if (continuous && !this.active) this._wakeCheck(r[0].transcript);
          else finalText += r[0].transcript;
        } else interim += r[0].transcript;
      }
      if (continuous && !this.active && !this._wachBis && interim && findeWeckwort(interim, this.wake) !== null) {
        this._state('window');                     // sofort zeigen, dass sie zuhört
      }
      this.cb.onPartial && this.cb.onPartial((finalText + ' ' + interim).trim());
    };
    rec.onerror = (e) => {
      if (e.error !== 'aborted' && e.error !== 'no-speech') this.cb.onError && this.cb.onError(`Spracherkennung: ${e.error}`);
    };
    rec.onend = () => {
      // ein abgelöster Erkenner (z. B. Dauerhören, als die Sprechtaste gedrückt wurde) darf nichts mehr anstoßen –
      // bis 0.37.5 startete er 250 ms später das Dauerhören neu und brach die Sprechtaste ab
      if (this.rec !== rec) return;
      if (!continuous || this.active) {
        if (this.inWindow) { this.inWindow = false; this.active = false; clearTimeout(this._windowTimer); }
        this._state(this.always ? 'always' : 'idle');
        if (finalText.trim()) this.cb.onFinal(finalText.trim(), 'stimme');
        else this.cb.onPartial && this.cb.onPartial('');
        if (this.always) setTimeout(() => this._startBrowser(true), 250);
      } else if (this.always && !this.muted && this.rec === rec) {
        setTimeout(() => this._startBrowser(true), 250); // Chrome beendet Dauerhören gelegentlich von selbst
      }
    };
    this.rec = rec;
    try { rec.start(); } catch { /* läuft schon */ }
  }

  _wakeCheck(transcript) {
    if (this.muted) return;
    // nur das Weckwort gehört („Ente“ … Pause … „lauf vor“): der nächste Satz in 6 s gilt als Befehl – bis 0.37.5
    // brauchte auch der wieder das Weckwort und wurde verschluckt
    if (this._wachBis && performance.now() < this._wachBis) {
      this._wachBis = 0;
      const rest = findeWeckwort(transcript, this.wake);
      const befehl = (rest === null ? transcript : rest).trim();
      if (befehl.length > 1) { this._state('always'); this.cb.onFinal(befehl, 'weckwort'); }
      return;
    }
    const rest = findeWeckwort(transcript, this.wake);
    if (rest === null) return;
    if (rest.length > 1) { this.cb.onFinal(rest, 'weckwort'); return; }
    this._wachBis = performance.now() + 6000;
    this._state('window');
    this.cb.onPartial && this.cb.onPartial(`„${this.wake}“ gehört – sprich weiter …`);
    clearTimeout(this._wachTimer);
    this._wachTimer = setTimeout(() => {
      if (this._wachBis) { this._wachBis = 0; this._state(this.always ? 'always' : 'idle'); this.cb.onPartial && this.cb.onPartial(''); }
    }, 6000);
  }

  async _startRecorder() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const chunks = [];
      const media = new MediaRecorder(stream);
      media.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      media.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        this._state('working');
        try {
          const blob = new Blob(chunks, { type: media.mimeType || 'audio/webm' });
          const res = await fetch('/api/stt', { method: 'POST', body: blob });
          const data = await res.json();
          if (data.error) throw new Error(data.error);
          if (data.text) this.cb.onFinal(data.text, 'stimme');
          else this.cb.onPartial && this.cb.onPartial('Nichts verstanden – nochmal, etwas näher am Mikrofon.');
        } catch (err) {
          this.cb.onError && this.cb.onError(`Lokale Erkennung: ${err.message}`);
        }
        this._state('idle');
      };
      this.media = media;
      media.start();
      if (!this.active) media.stop(); // schon losgelassen
    } catch (err) {
      this.active = false;
      this._state('idle');
      this.cb.onError && this.cb.onError(`Mikrofon: ${err.message}`);
    }
  }
}
