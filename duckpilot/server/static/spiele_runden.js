// „Mach mir nach“ und „Schere, Stein, Papier“ mit Reachy (seit 0.38.14) – Teil der Kamera-Spiele (kamera_spiele.js).
// Kamera, Erkennung (Hand oder Bewegung), Bühne, Not-Aus und Ende kommen über `ctx` aus kamera_spiele.js; hier steht
// nur der Ablauf. An duckpilot gehen nur Wörter: eine Richtung („links“ …) oder eine Geste („stein“ …).
// Die Rechenschritte (Richtung, Stabilität, häufigste Geste) sind reine Funktionen in hand.js.

import { haeufigste, richtungAus, stabil } from './hand.js';

export const PFEIL = { links: '←', rechts: '→', oben: '↑', unten: '↓' };
export const ANTWORT_S = { leicht: 12, mittel: 9, schwer: 7 };   // so lange hat man je Schritt Zeit
export const SSP_NAME = { schere: 'Schere', stein: 'Stein', papier: 'Papier' };
const STUFE_NAME = { leicht: 'Leicht', mittel: 'Mittel', schwer: 'Schwer' };

// ── Mach mir nach ───────────────────────────────────────────────────────
export function initSpiegel(ctx) {
  const { $ } = ctx;
  const knopf = $('ks-sp-start');
  if (!knopf) return;

  function zeige(zustand, richtung, text) {
    $('ks-sp-zeige').dataset.zustand = zustand;
    $('ks-sp-pfeil').textContent = richtung && PFEIL[richtung] ? PFEIL[richtung] : '';
    $('ks-sp-text').textContent = text;
  }
  function werte(r) {
    if (r.runde != null) $('ks-sp-runde').textContent = `${r.runde} von ${r.runden || 6}`;
    if (r.leben != null) $('ks-sp-leben').textContent = String(r.leben);
    if (r.punkte != null) $('ks-sp-punkte').textContent = String(r.punkte);
  }
  function rekord() {
    const stufe = $('ks-sp-stufe').value;
    const b = ctx.best('spiegel')[stufe] || {};
    $('ks-sp-best').textContent = b.punkte != null ? `${b.punkte} (${STUFE_NAME[stufe]})` : '–';
  }
  // Reachy macht vor: jede Richtung als Pfeil und Wort, im Takt seiner Bewegung
  async function vormachen(folge, schritt, gen) {
    for (let i = 0; i < folge.length; i++) {
      const r = folge[i];
      zeige('reachy', r, folge.length > 1 ? `Reachy: ${r} (${i + 1} von ${folge.length})` : `Reachy: ${r}`);
      ctx.ansage(`Reachy schaut nach ${r}.`);
      if (!(await ctx.warte(schritt * 0.65, gen))) return false;
      zeige('reachy', null, '…');
      if (!(await ctx.warte(schritt * 0.35, gen))) return false;
    }
    return true;
  }
  // Warten, bis die Hand eine Richtung zeigt: erst zurück zur Mitte (oder Hand weg), dann ein paar Bilder dieselbe
  // Richtung. Nach `sekunden` ohne Antwort: 'keine'.
  function richtungAbwarten(gen, sekunden) {
    const verlauf = [];
    let frei = false;
    const t0 = performance.now();
    return ctx.schleife(gen, () => {
      const m = ctx.erfassen();
      const r = m && m.x != null ? richtungAus(m.x, m.y) : null;
      if (!frei) {
        if (r === null || r === 'mitte') frei = true;
      } else {
        verlauf.push(r);
        const s = stabil(verlauf, ctx.mitHand() ? 4 : 3);
        if (s) return s;
      }
      if (performance.now() - t0 > sekunden * 1000) return 'keine';
      return undefined;
    }, 80);
  }

  async function spielen() {
    if (ctx.laeuft() === 'spiegel') { ctx.ende(null); zeige('aus', null, 'Spiel beendet.'); ctx.ansage('Spiel beendet. Die Webcam ist aus.'); return; }
    const stufe = $('ks-sp-stufe').value;
    const r0 = await ctx.starten('spiegel', { stufe });
    if (!r0) return;
    const gen = ctx.gen();
    werte({ runde: 0, runden: 6, leben: 3, punkte: 0 });
    rekord();
    while (gen === ctx.gen()) {
      const r = await ctx.post('/api/spiele/spiegel', { aktion: 'zeigen' });
      if (!r || gen !== ctx.gen()) return;
      werte(r);
      zeige('reachy', null, 'Schau genau hin …');
      ctx.ansage('Reachy macht vor – schau genau hin.');
      if (!(await ctx.warte(0.8, gen))) return;
      if (!(await vormachen(r.folge, r.schritt_s, gen))) return;
      let a = null;
      for (let i = 0; i < r.folge.length; i++) {
        const text = r.folge.length > 1 ? `Du bist dran: ${i + 1}. Bewegung von ${r.folge.length}` : 'Du bist dran!';
        zeige('du', null, text);
        ctx.ansage(text);
        const richtung = await richtungAbwarten(gen, ANTWORT_S[stufe] || 9);
        if (richtung == null || gen !== ctx.gen()) return;
        a = await ctx.post('/api/spiele/spiegel', { aktion: 'antwort', richtung });
        if (!a || gen !== ctx.gen()) return;
        werte(a);
        let ergebnis;
        if (a.richtig) ergebnis = `Richtig: ${richtung}!`;
        else if (richtung === 'keine') ergebnis = `Zu langsam – es war ${a.erwartet}.`;
        else ergebnis = `Fast – es war ${a.erwartet}, nicht ${richtung}. Noch ${a.leben} Leben.`;
        zeige(a.richtig ? 'richtig' : 'falsch', a.richtig ? richtung : a.erwartet, ergebnis);
        ctx.ansage(ergebnis);
        if (!a.richtig || a.vorbei) break;
        if (!(await ctx.warte(0.5, gen))) return;
      }
      if (a && a.vorbei) {
        const text = `${a.gewonnen ? 'Gewonnen!' : 'Spiel vorbei.'} ${a.punkte} Punkte${a.neuer_rekord ? ' – neuer Rekord!' : '.'}`;
        zeige(a.gewonnen ? 'richtig' : 'aus', null, text);
        ctx.ansage(text);
        if (a.bestpunkte != null) {
          const best = ctx.best('spiegel');
          best[stufe] = { ...(best[stufe] || {}), punkte: a.bestpunkte };
        }
        rekord();
        if (!(await ctx.warte(4, gen))) return;
        ctx.ende(null);
        zeige('aus', null, text);
        return;
      }
      if (!(await ctx.warte(1.6, gen))) return;
    }
  }

  knopf.addEventListener('click', spielen);
  $('ks-sp-stufe').addEventListener('change', rekord);
  ctx.beiKnoepfen(() => {
    const l = ctx.laeuft();
    knopf.disabled = !!l && l !== 'spiegel';
    knopf.setAttribute('aria-pressed', String(l === 'spiegel'));
    knopf.textContent = l === 'spiegel' ? 'Mach mir nach beenden' : 'Mach mir nach starten';
    knopf.classList.toggle('btn--primary', l !== 'spiegel');
    $('ks-sp-stufe').disabled = !!l;
    rekord();
  });
  ctx.beimEnde((grund, war) => {
    if (war === 'spiegel' && grund) zeige('aus', null, grund);
  });
}

// ── Schere, Stein, Papier (nur mit Handerkennung) ───────────────────────
export function initSsp(ctx) {
  const { $ } = ctx;
  const start = $('ks-ssp-start');
  const runde = $('ks-ssp-runde');
  if (!start) return;
  let rundeLaeuft = false;
  let sammeln = null;           // Gesten im Moment nach „Schnuck!“

  function stand(s) { $('ks-ssp-stand').textContent = `Du ${s.mensch} : ${s.reachy} Reachy`; }
  function siege() {
    const b = ctx.best('ssp').alle || {};
    $('ks-ssp-siege').textContent = String(b.siege || 0);
  }
  function anzeige(zustand, du, reachy, takt = '') {
    $('ks-ssp-anzeige').dataset.zustand = zustand;
    if (du != null) $('ks-ssp-du').textContent = du;
    if (reachy != null) $('ks-ssp-reachy').textContent = reachy;
    $('ks-ssp-takt').textContent = takt;
  }

  async function spielen() {
    if (ctx.laeuft() === 'ssp') { ctx.ende(null); ctx.ansage('Spiel beendet. Die Webcam ist aus.'); return; }
    const r0 = await ctx.starten('ssp');
    if (!r0) return;
    const gen = ctx.gen();
    stand({ mensch: 0, reachy: 0 });
    siege();
    anzeige('bereit', '–', '–');
    $('ks-ssp-ergebnis').textContent = 'Zeig deine Hand und drück „Schnick, Schnack, Schnuck!“.';
    // Vorschau: die Handpunkte und was gerade erkannt wird – nach „Schnuck!“ werden die Gesten gesammelt
    ctx.schleife(gen, () => {
      const m = ctx.erfassen();
      if (!m) return undefined;
      if (sammeln) sammeln.push(m.geste);
      if (!rundeLaeuft) $('ks-ssp-du').textContent = m.geste ? SSP_NAME[m.geste] : (m.punkte ? '?' : '–');
      return undefined;
    }, 90);
  }

  async function schnick() {
    if (rundeLaeuft || ctx.laeuft() !== 'ssp') return;
    rundeLaeuft = true;
    ctx.knoepfe();
    const gen = ctx.gen();
    anzeige('zaehlen', '…', '…');
    const z = await ctx.post('/api/spiele/ssp', { aktion: 'zaehlen' });
    if (!z || gen !== ctx.gen()) return;
    const takt = (z.zaehl_s || 1.8) / 3;
    for (const wort of ['Schnick', 'Schnack', 'Schnuck!']) {
      anzeige('zaehlen', null, null, wort);
      ctx.ansage(wort);
      if (!(await ctx.warte(takt, gen))) return;
    }
    sammeln = [];
    if (!(await ctx.warte(0.7, gen))) return;
    const geste = haeufigste(sammeln, 2);
    sammeln = null;
    const r = await ctx.post('/api/spiele/ssp', { aktion: 'zug', geste: geste || 'unklar' });
    rundeLaeuft = false;
    if (!r || gen !== ctx.gen()) return;
    if (r.unklar) {
      anzeige('unklar', 'nicht erkannt', '–');
      $('ks-ssp-ergebnis').textContent = 'Nicht erkannt – halt die Hand ruhig in die Kamera und versuch es noch mal.';
    } else {
      const wer = { mensch: 'Punkt für dich!', reachy: 'Punkt für Reachy.', gleich: 'Unentschieden.' }[r.sieger];
      anzeige(r.sieger, SSP_NAME[r.mensch], SSP_NAME[r.reachy]);
      stand(r.stand);
      $('ks-ssp-ergebnis').textContent = `Du: ${SSP_NAME[r.mensch]}, Reachy: ${SSP_NAME[r.reachy]} – ${wer}`;
    }
    ctx.ansage($('ks-ssp-ergebnis').textContent);
    ctx.knoepfe();
    if (r.vorbei) {
      const text = r.gewonnen ? 'Du hast das Spiel gewonnen!' : 'Reachy hat das Spiel gewonnen – Revanche?';
      $('ks-ssp-ergebnis').textContent += ` ${text}`;
      ctx.ansage(text);
      if (r.siege != null) ctx.best('ssp').alle = { siege: r.siege };
      siege();
      if (!(await ctx.warte(4, gen))) return;
      ctx.ende(null);
    }
  }

  start.addEventListener('click', spielen);
  runde.addEventListener('click', schnick);
  ctx.beiKnoepfen(() => {
    const l = ctx.laeuft();
    const handDa = ctx.hand.an();
    start.disabled = (!!l && l !== 'ssp') || (!l && !handDa);
    start.setAttribute('aria-pressed', String(l === 'ssp'));
    start.textContent = l === 'ssp' ? 'Schere, Stein, Papier beenden' : 'Schere, Stein, Papier starten';
    start.classList.toggle('btn--primary', l !== 'ssp');
    runde.disabled = l !== 'ssp' || rundeLaeuft;
    $('ks-ssp-braucht').hidden = handDa;
    siege();
  });
  ctx.beimEnde((grund, war) => {
    if (war !== 'ssp') return;
    rundeLaeuft = false;
    sammeln = null;
    anzeige('aus', null, null);
    if (grund) $('ks-ssp-ergebnis').textContent = grund;
  });
}
