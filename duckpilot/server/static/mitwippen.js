// Mitwippen (seit 0.38.13, Reachy Mini – wie Pollens App „Reachy Mini Radio“): Ein Stück vom PC oder ein Webradio
// läuft hier im Browser, Reachy wippt ruhig im Takt mit. Der Takt kommt aus einer Analyse im Browser (Anstiege der
// Lautstärke, wie „Nach Gehör“) – an duckpilot gehen alle 1,5 s nur Tempo, letzter Schlag und Lautstärke.
// Erlaubt ein Radiosender das Mitlesen nicht (CORS), läuft er trotzdem, und Reachy wippt ehrlich in einem ruhigen
// Grundtakt. Nichts wird aufgenommen oder gespeichert – nur die zuletzt genutzten Radio-Adressen (Einstellungen,
// höchstens fünf). Not-Aus, Esc und jedes Ende des Tanzes stoppen auch die Musik.

import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

const GRUNDTAKT_BPM = 96;     // ruhiger Grundtakt, wenn der Stream nicht lesbar ist
const ZULETZT_MAX = 5;
const MELDEN_MS = 1500;

// Adresse eines Streams prüfen: nur http(s), keine Zugangsdaten in der Adresse
export function streamAdresse(text) {
  let u;
  try { u = new URL(String(text || '').trim()); } catch { return null; }
  if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password || !u.hostname) return null;
  return u.href.length <= 300 ? u.href : null;
}

export function initMitwippen({ $, api, el, toast, tempoUndSchlag }) {
  const box = $('mitwippen');
  if (!box) return { pruefen() {}, stopp() {} };
  const status = $('mitwippen-status');
  let lauf = null;          // { audio, ctx, proc, takt, blob, grundtakt, seit, ohneTanzSeit }
  let zuletzt = [];
  const melde = (text) => { status.textContent = text; };

  // ── Zuletzt gehörte Sender ────────────────────────────────────────────
  function kurz(url) {
    try { const u = new URL(url); return `${u.hostname}${u.pathname.length > 1 ? u.pathname : ''}`.slice(0, 48); } catch { return url.slice(0, 48); }
  }
  function zuletztZeigen() {
    const liste = $('mitwippen-zuletzt');
    const dl = $('mitwippen-zuletzt-liste');
    liste.replaceChildren();
    dl.replaceChildren();
    for (const url of zuletzt) {
      const b = el('button', 'chip chip--btn', kurz(url));
      b.type = 'button';
      b.title = url;
      b.setAttribute('aria-label', `${tr('Radio abspielen')}: ${url}`);
      b.addEventListener('click', () => { $('mitwippen-url').value = url; radio(url); });
      liste.append(b);
      dl.append(new Option(url, url));
    }
  }
  async function zuletztLaden() {
    const s = await api('/api/settings').catch(() => null);
    zuletzt = (s && s.werte && Array.isArray(s.werte.radio_adressen)) ? s.werte.radio_adressen.slice(0, ZULETZT_MAX) : [];
    zuletztZeigen();
  }
  async function merken(url) {
    zuletzt = [url, ...zuletzt.filter((u) => u !== url)].slice(0, ZULETZT_MAX);
    zuletztZeigen();
    await api('/api/settings', 'POST', { radio_adressen: zuletzt }).catch(() => null);
  }

  // ── Abspielen ─────────────────────────────────────────────────────────
  // Ein Wiedergabe-Element je Lauf: eine WebAudio-Quelle lässt sich nur einmal an ein Element hängen, und ein nicht
  // lesbarer Stream darf nicht durch WebAudio laufen (er wäre dort stumm).
  function abspielen(src, mitLesen) {
    return new Promise((ok, fehler) => {
      const audio = new Audio();
      audio.preload = 'auto';
      if (mitLesen) audio.crossOrigin = 'anonymous';
      const weg = () => { clearTimeout(uhr); audio.removeEventListener('playing', los); audio.removeEventListener('error', kaputt); };
      const los = () => { weg(); ok(audio); };
      const kaputt = () => { weg(); audio.removeAttribute('src'); audio.load(); fehler(new Error('abspielen')); };
      const uhr = setTimeout(kaputt, 15000);
      audio.addEventListener('playing', los);
      audio.addEventListener('error', kaputt);
      audio.src = src;
      audio.play().catch((e) => { if (e && e.name === 'NotAllowedError') kaputt(); });
    });
  }

  function lesen(audio) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    ctx.resume?.();
    const quelle = ctx.createMediaElementSource(audio);
    quelle.connect(ctx.destination);                     // hören wie vorher
    const proc = ctx.createScriptProcessor(1024, 1, 1);
    const hop = 512;
    const fps = ctx.sampleRate / hop;
    const rms = [];
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
    proc.connect(ctx.destination);                       // nötig, damit der Prozessor läuft – gibt nur Stille aus
    return { ctx, proc, rms, fps };
  }

  // Erst spielt die Musik, dann wippt Reachy mit – so wartet er nie auf einen Stream, der lädt (ohne Meldung hört er
  // nach 6 s auf). Lehnt der Körper ab (Not-Aus-Sperre, schläft), geht die Musik gleich wieder aus.
  async function starten(art, src, titel, url = '') {
    await stopp(true, '');                               // ein laufendes Mitwippen erst ganz beenden
    const jetzt = { art, blob: art === 'datei' ? src : '', seit: performance.now(), ohneTanzSeit: 0, grundtakt: false, spitze: 0.02 };
    lauf = jetzt;
    melde(tr(art === 'radio' ? 'Verbinde mit dem Radio …' : 'Starte das Stück …'));
    let audio = null;
    try {
      audio = await abspielen(src, true);
    } catch {
      if (art === 'radio' && lauf === jetzt) {         // Sender erlaubt kein Mitlesen? Dann ohne – mit Grundtakt
        try { audio = await abspielen(src, false); jetzt.grundtakt = true; } catch { audio = null; }
      }
    }
    if (lauf !== jetzt) { if (audio) { audio.pause(); audio.removeAttribute('src'); } return; }   // inzwischen gestoppt
    if (!audio) {
      stopp(false, tr(art === 'radio' ? 'Der Stream lässt sich nicht abspielen – stimmt die Adresse?' : 'Dieses Format kann der Browser nicht abspielen.'));
      return;
    }
    jetzt.audio = audio;
    const r = await api('/api/gehoer', 'POST', { aktion: 'start', ruhig: true }).catch(() => ({ ok: false }));
    if (lauf !== jetzt) return;
    if (!r.ok) {
      stopp(false, '');
      toast(r.fehler || r.grund || tr('Reachy kann gerade nicht mitwippen'), true);
      return;
    }
    jetzt.seit = performance.now();
    if (!jetzt.grundtakt) {
      try { Object.assign(jetzt, lesen(audio)); } catch { jetzt.grundtakt = true; }
    }
    audio.addEventListener('ended', () => { if (lauf === jetzt) stopp(true, tr('Das Stück ist zu Ende.')); });
    audio.addEventListener('error', () => { if (lauf === jetzt) stopp(true, tr('Die Musik ist abgebrochen.')); });
    $('mitwippen-titel').textContent = `${tr('Läuft:')} ${titel}`;
    $('mitwippen-laeuft').hidden = false;
    melde(tr(jetzt.grundtakt ? 'Takt nicht lesbar – Reachy wippt in einem ruhigen Grundtakt' : 'Höre mir den Takt an …'));
    if (art === 'radio' && url) merken(url);
    jetzt.takt = setInterval(() => messen(jetzt), MELDEN_MS);
    messen(jetzt);
  }

  async function messen(jetzt) {
    if (lauf !== jetzt || !jetzt.audio || jetzt.audio.paused) return;
    const alter = (performance.now() - jetzt.seit) / 1000;
    let bpm = GRUNDTAKT_BPM;
    let schlagVorS = alter % (60 / GRUNDTAKT_BPM);
    let energie = 0.3;
    if (!jetzt.grundtakt) {
      const { rms, fps } = jetzt;
      if (rms.length >= fps * 3) {
        const onset = rms.map((v, i) => (i ? Math.max(0, Math.log1p(100 * v) - Math.log1p(100 * rms[i - 1])) : 0));
        ({ bpm, schlagVorS } = tempoUndSchlag(onset, fps));
        const n = Math.round(fps * 2);
        const laut = rms.slice(-n).reduce((a, b) => a + b, 0) / n;
        jetzt.spitze = Math.max(laut, jetzt.spitze * 0.995);
        energie = laut < 0.004 ? 0 : Math.min(1, laut / jetzt.spitze);
        melde(`${tr('Reachy wippt mit')} · ${Math.round(bpm)} BPM`);
      } else if (alter < 4) {
        return;                                          // noch zu wenig gehört – Reachy wartet bis zu 6 s
      }
    }
    const m = await api('/api/gehoer', 'POST', { aktion: 'messung', bpm, schlag_vor_s: schlagVorS + 0.05, energie }).catch(() => null);
    if (m && m.laeuft === false && lauf === jetzt) stopp(false, tr('Reachy hat aufgehört – die Musik ist aus.'));
  }

  // Musik aus, Mitwippen aus. `melden`: auch den Tanz beenden (sonst ist er schon vorbei – Not-Aus, Stopp, Ende)
  function stopp(melden = true, text = null) {
    const war = lauf;
    lauf = null;
    $('mitwippen-laeuft').hidden = true;
    if (text !== null) melde(text);
    if (!war) return Promise.resolve();
    clearInterval(war.takt);
    if (war.audio) { war.audio.pause(); war.audio.removeAttribute('src'); war.audio.load(); }
    try { war.proc?.disconnect(); } catch { /* schon getrennt */ }
    war.ctx?.close?.();
    if (war.blob) URL.revokeObjectURL(war.blob);
    if (text === null) melde(tr('Mitwippen beendet.'));
    return melden ? api('/api/gehoer', 'POST', { aktion: 'stopp' }).catch(() => {}) : Promise.resolve();
  }

  function radio(text) {
    const url = streamAdresse(text);
    if (!url) { toast(tr('Bitte eine Adresse mit http:// oder https:// eingeben'), true); return; }
    if (location.protocol === 'https:' && url.startsWith('http:')) {
      toast(tr('Diese Seite läuft über https – dort spielt der Browser nur https-Streams'), true);
      return;
    }
    let titel = url;
    try { titel = new URL(url).hostname; } catch { /* bleibt die Adresse */ }
    starten('radio', url, titel, url);
  }

  $('mitwippen-radio').addEventListener('submit', (e) => { e.preventDefault(); radio($('mitwippen-url').value); });
  $('mitwippen-stueck').addEventListener('click', () => {
    const inp = $('mitwippen-datei');
    inp.value = '';
    inp.click();
  });
  $('mitwippen-datei').addEventListener('change', (e) => {
    const d = e.target.files?.[0];
    if (!d) return;
    starten('datei', URL.createObjectURL(d), d.name.replace(/\.[^.]+$/, ''));      // bleibt im Browser, kein Hochladen
  });
  $('mitwippen-stopp').addEventListener('click', () => stopp(true));
  // Not-Aus gewinnt: Pilz, Esc – die Musik hört sofort auf (den Tanz stoppt der Server schon)
  $('stop')?.addEventListener('click', () => { if (lauf) stopp(false, tr('Not-Aus – Musik und Mitwippen gestoppt.')); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && lauf) stopp(false, tr('Not-Aus – Musik und Mitwippen gestoppt.')); });
  window.addEventListener('beforeunload', () => stopp(true));
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) zuletztLaden(); }).observe(box);

  // Endet das Mitwippen auf dem Server (Not-Aus per Sprache oder Gamepad, anderer Befehl), hört auch die Musik auf
  function pruefen(engine) {
    if (!lauf || !lauf.takt || performance.now() - lauf.seit < 3000) return;
    if (String((engine && engine.aktuell) || '').startsWith('mitwippen')) { lauf.ohneTanzSeit = 0; return; }
    const jetzt = performance.now();
    if (!lauf.ohneTanzSeit) lauf.ohneTanzSeit = jetzt;
    else if (jetzt - lauf.ohneTanzSeit > 1200) stopp(false, tr('Reachy hat aufgehört – die Musik ist aus.'));
  }

  return { pruefen, stopp };
}
