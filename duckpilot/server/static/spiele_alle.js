// Spiele für jeden Körper (seit 0.44): „Ente sagt“, Verstecken, Elfmeter (routes/spiel.py).
// „Ente sagt“ liest das Handzeichen wahlweise aus der Webcam (hand.js, nur im Browser – heraus geht nur ein Wort wie
// „stein“) oder aus den Knöpfen. Verstecken legt einen Vorhang über die 3D-Ansicht (Not-Aus und Leiste bleiben frei),
// beim Elfmeter bist du der Torwart. Texte vom Server landen nur über textContent im Dokument.
import { HandErkenner, haeufigste } from './hand.js';

export function initAlleSpiele({ $, api, toast, showView }) {
  if (!$('sp-sagt')) return;
  const fehler = (r) => toast((r && r.fehler) || 'Keine Antwort', true);

  // ── „Ente sagt“ ─────────────────────────────────────────────────────
  const erkenner = new HandErkenner();
  let stream = null, frist = null, zeichen = 'keine', proben = [], spielt = false, schleife = null;

  function name() {
    const n = $('sp-sagt-name').textContent;
    for (const e of document.querySelectorAll('.sp-sagt-wer')) e.textContent = n;
  }
  function stand(s) {
    $('sp-sagt-stand').textContent = `Punkte ${s.punkte ?? 0} · Leben ${s.leben ?? 3} · Bestwert ${s.best ?? 0}`;
  }
  function knoepfe(an) {
    for (const b of document.querySelectorAll('#sp-sagt [data-zeichen]')) b.setAttribute('aria-pressed', String(b.dataset.zeichen === an));
  }
  async function kameraAn() {
    const h = await api('/api/spiele/hand').catch(() => null);
    if (!h || !h.bereit) { toast('Erst die Handerkennung laden (unten auf dieser Seite, nur am PC)', true); return false; }
    try {
      await erkenner.laden();
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
    } catch (e) { toast(`Webcam geht nicht: ${e.message || e}`, true); return false; }
    const v = $('sp-sagt-video');
    v.srcObject = stream;
    v.hidden = false;
    await v.play().catch(() => {});
    const blick = () => {
      if (!stream) return;
      const r = erkenner.erkennen(v);
      if (r && !r.fehler) { proben.push(r.hand ? r.geste || 'keine' : 'keine'); if (proben.length > 12) proben.shift(); knoepfe(proben.at(-1)); }
      schleife = requestAnimationFrame(blick);
    };
    blick();
    return true;
  }
  function kameraAus() {
    cancelAnimationFrame(schleife);
    if (stream) for (const t of stream.getTracks()) t.stop();
    stream = null;
    $('sp-sagt-video').hidden = true;
  }
  function runde(r) {
    $('sp-sagt-ansage').textContent = r.text;
    $('sp-sagt-ansage').dataset.zustand = '';
    proben = [];
    clearTimeout(frist);
    frist = setTimeout(antworten, r.frist_s * 1000);
  }
  async function antworten() {
    if (!spielt) return;
    const gezeigt = stream ? (haeufigste(proben.slice(-6), 2) || 'keine') : zeichen;
    const r = await api('/api/spiel/sagt', 'POST', { aktion: 'antwort', zeichen: gezeigt }).catch(() => null);
    if (!r || r.ok === false) { fehler(r); ende(); return; }
    $('sp-sagt-ansage').textContent = r.satz;
    $('sp-sagt-ansage').dataset.zustand = r.richtig ? 'richtig' : 'falsch';
    stand({ ...r, best: r.bestwert ? r.punkte : undefined });
    if (r.vorbei) { ende(); return; }
    setTimeout(() => { if (spielt) runde(r.runde); }, 1300);
  }
  function ende() {
    spielt = false;
    clearTimeout(frist);
    kameraAus();
    $('sp-sagt-start').hidden = false;
    $('sp-sagt-stopp').hidden = true;
    laden();
  }
  $('sp-sagt-start').addEventListener('click', async () => {
    if ($('sp-sagt-kamera').checked && !(await kameraAn())) $('sp-sagt-kamera').checked = false;
    const r = await api('/api/spiel/sagt', 'POST', { aktion: 'start' }).catch(() => null);
    if (!r || r.ok === false) { fehler(r); kameraAus(); return; }
    spielt = true;
    zeichen = 'keine';
    knoepfe('keine');
    $('sp-sagt-start').hidden = true;
    $('sp-sagt-stopp').hidden = false;
    stand(r);
    runde(r.runde);
  });
  $('sp-sagt-stopp').addEventListener('click', () => { api('/api/spiel/sagt', 'POST', { aktion: 'stopp' }).catch(() => {}); ende(); });
  for (const b of document.querySelectorAll('#sp-sagt [data-zeichen]')) {
    b.addEventListener('click', () => { zeichen = b.dataset.zeichen; knoepfe(zeichen); });
  }

  // ── Verstecken ──────────────────────────────────────────────────────
  const vorhang = $('sp-vorhang');
  function vorhangText(t) { $('sp-vorhang-text').textContent = t; }
  function orteZeigen(orte) {
    $('sp-vorhang-orte').replaceChildren(...(orte || []).map((o) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn--sm';
      b.textContent = o;
      b.addEventListener('click', async () => {
        const r = await api('/api/spiel/verstecken', 'POST', { aktion: 'raten', moebel: o }).catch(() => null);
        if (!r || r.ok === false) { fehler(r); return; }
        vorhangText(r.satz);
        b.disabled = !r.treffer;
        if (r.treffer || r.ende) versteckEnde(r.satz);
      });
      return b;
    }));
  }
  function versteckEnde(satz) {
    $('sp-versteck-ansage').textContent = satz;
    $('sp-vorhang-orte').replaceChildren();
    setTimeout(() => { vorhang.hidden = true; }, 1800);
    $('sp-versteck-start').hidden = false;
    $('sp-versteck-stopp').hidden = true;
    laden();
  }
  $('sp-versteck-start').addEventListener('click', async () => {
    const r = await api('/api/spiel/verstecken', 'POST', { aktion: 'start' }).catch(() => null);
    if (!r || r.ok === false) { fehler(r); return; }
    showView('cockpit');
    vorhangText('Augen zu! Ich zähle bis zehn …');
    $('sp-vorhang-orte').replaceChildren();
    vorhang.hidden = false;
    $('sp-versteck-ansage').textContent = 'Er versteckt sich …';
    $('sp-versteck-start').hidden = true;
    $('sp-versteck-stopp').hidden = false;
  });
  const aufgeben = async () => {
    const r = await api('/api/spiel/verstecken', 'POST', { aktion: 'aufgeben' }).catch(() => null);
    if (r && r.ok !== false) versteckEnde(r.satz); else { vorhang.hidden = true; fehler(r); }
  };
  $('sp-versteck-stopp').addEventListener('click', aufgeben);
  $('sp-vorhang-aufgeben').addEventListener('click', aufgeben);

  // ── Elfmeter ────────────────────────────────────────────────────────
  const torwart = $('sp-torwart');
  function hechtKnoepfe(an) { for (const b of torwart.querySelectorAll('[data-hechten]')) b.disabled = !an; }
  for (const b of torwart.querySelectorAll('[data-hechten]')) {
    b.addEventListener('click', async () => {
      const r = await api('/api/spiel/elfmeter', 'POST', { aktion: 'hechten', seite: b.dataset.hechten }).catch(() => null);
      if (r && r.ok) { $('sp-torwart-text').textContent = `Du hechtest: ${b.textContent.replace(/[⬅➡]/g, '').trim()}`; hechtKnoepfe(false); }
    });
  }
  function elferEnde() {
    setTimeout(() => { torwart.hidden = true; }, 3000);
    $('sp-elfer-start').hidden = false;
    $('sp-elfer-stopp').hidden = true;
    laden();
  }
  $('sp-elfer-start').addEventListener('click', async () => {
    const r = await api('/api/spiel/elfmeter', 'POST', { aktion: 'start' }).catch(() => null);
    if (!r || r.ok === false) { fehler(r); return; }
    showView('cockpit');
    torwart.hidden = false;
    $('sp-torwart-text').textContent = 'Du bist im Tor';
    hechtKnoepfe(true);
    $('sp-elfer-start').hidden = true;
    $('sp-elfer-stopp').hidden = false;
  });
  $('sp-elfer-stopp').addEventListener('click', async () => {
    await api('/api/spiel/elfmeter', 'POST', { aktion: 'stopp' }).catch(() => null);
    elferEnde();
  });

  // ── Meldungen vom Server ────────────────────────────────────────────
  window.addEventListener('knowlin:spiel', (ev) => {
    const m = ev.detail || {};
    if (m.art === 'verstecken') {
      vorhangText(m.text || '');
      if (m.phase === 'raten') orteZeigen(m.orte);
      if (m.phase === 'gefunden' || m.phase === 'aufgedeckt') versteckEnde(m.text || '');
    }
    if (m.art === 'elfmeter') {
      if (m.neu && !('tor' in m)) { $('sp-torwart-text').textContent = `Schuss ${m.schuss} von ${m.schuesse} – wohin hechtest du?`; hechtKnoepfe(true); }
      if ('tor' in m) {
        $('sp-torwart-text').textContent = m.satz || '';
        $('sp-elfer-stand').textContent = `Tore ${m.tore} von ${m.schuss}`;
        $('sp-elfer-ansage').textContent = m.satz || '';
        if (m.ende) elferEnde();
      }
    }
  });

  async function laden() {
    const s = await api('/api/spiel').catch(() => null);
    if (!s) return;
    $('sp-sagt-name').textContent = s.wer || 'Knowlin';
    name();
    const b = s.bestwerte || {};
    stand({ ...(s.sagt || {}), best: b.ente_sagt || 0 });
    $('sp-elfer-stand').textContent = `Tore 0 von 0 · Bestwert ${b.elfmeter ?? 0}`;
    if (b.verstecken) $('sp-versteck-ansage').textContent = `Bestwert: gefunden nach ${b.verstecken} ${b.verstecken === 1 ? 'Versuch' : 'Versuchen'}`;
  }
  laden();
  return { laden };
}
