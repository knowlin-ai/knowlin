// Raum kennenlernen (seit 0.37): Kartierungsmodus, „Zuletzt gesehen“ und „Bring mir …“ – seit 0.38 im Bereich Umgebung.
// Die Karte erscheint auf Wunsch als Raster auf dem Boden der 3D-Ansicht (nur am PC – remote.PC_ONLY).

import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

function wieLange(s) {
  if (s < 30) return tr('gerade eben');
  if (s < 90) return tr('vor einer Minute');
  if (s < 3600) return tr(`vor ${Math.round(s / 60)} Minuten`);
  if (s < 7200) return tr('vor einer Stunde');
  if (s < 86400) return tr(`vor ${Math.round(s / 3600)} Stunden`);
  return tr('vor über einem Tag');
}

// Piktogramme für die 2D-Karte (seit 0.37.11, Wunsch des Maintainers „Objekte markieren und mit Piktogramm einzeichnen“)
const PIKTO = [[/ball/i, '⚽'], [/sock/i, '🧦'], [/klötz|kloetz|block/i, '🟦'], [/baustein|brick/i, '🧱'],
  [/schach|figur|chess/i, '♟️'], [/sofa|couch(?!tisch)|sessel/i, '🛋️'], [/regal|shelf|schrank/i, '📚'],
  [/kiste|box|truhe/i, '📦'], [/tisch|table/i, '☕'], [/pflanze|plant|blume/i, '🪴'], [/hocker|stuhl|stool|chair/i, '🪑'],
  [/ente|duck|kiki|pip|lotte|bruno/i, '🦆']];
function piktogramm(s) {
  const p = PIKTO.find(([re]) => re.test(s.name || '') || re.test(s.art || ''));
  return p ? p[1] : '•';
}

export function initRaum({ $, api, el, scene, toast, zumCockpit, lagebild }) {
  const karte = $('raum-karte');
  if (!karte) return { laden() {} };
  let timer = null;
  let letzte = null;
  let leerenScharf = false;
  const zeigen3d = $('raum-zeigen');
  const spiegel = $('opt-raum');            // derselbe Schalter im Ansicht-Menü des Cockpits (seit 0.37.14)
  try { zeigen3d.checked = localStorage.getItem('duckpilot.raum.zeigen') !== '0'; } catch { /* privat */ }
  if (spiegel) spiegel.checked = zeigen3d.checked;
  function setzeZeigen(on) {
    zeigen3d.checked = on;
    if (spiegel) spiegel.checked = on;
    try { localStorage.setItem('duckpilot.raum.zeigen', on ? '1' : '0'); } catch { /* privat */ }
    if (letzte) zeigen(letzte); else laden();
  }

  function zeigen(d) {
    letzte = d;
    const m2 = (d.flaeche_m2 || 0).toLocaleString(document.documentElement.lang || 'de', { maximumFractionDigits: 1 });
    $('raum-status').textContent = d.kartiert
      ? tr(`Erkundet gerade … ${m2} m²`)
      : d.messungen ? tr(`${m2} m² erkundet · ${d.dinge} Dinge gemerkt`) : tr('Noch nichts erkundet.');
    const start = $('raum-start');
    start.textContent = d.kartiert ? tr('Erkunden beenden') : tr('Raum erkunden (2 Minuten)');
    start.setAttribute('aria-pressed', String(!!d.kartiert));
    $('raum-leeren').hidden = !d.messungen;          // nichts erkundet: nichts zu löschen (statt grauem Text-Knopf)
    const dinge = (d.sichtungen || []).filter((s) => s.art !== 'möbel').slice(0, 12);
    $('raum-liste').replaceChildren(...(dinge.length ? dinge.map((s) => {
      const li = el('li');
      li.append(el('strong', '', tr(s.name)), el('span', 'field-help', ` · ${wieLange(s.vor_s)}`));
      return li;
    }) : [el('li', 'field-help', tr('Noch nichts gesehen.'))]));
    scene.setKarte(zeigen3d.checked ? d.karte : null, zeigen3d.checked ? dinge : []);
    if (lagebild) lagebild(d.karte);
    plan(d);
  }

  // ── 2D-Karte von oben mit Piktogrammen für Dinge und Möbel ──
  const leinwand = $('raum-plan');
  function farbe(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || 'gray'; }
  function plan(d) {
    if (!leinwand) return;
    const ctx = leinwand.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const css = leinwand.clientWidth || 360;
    if (leinwand.width !== Math.round(css * dpr)) { leinwand.width = leinwand.height = Math.round(css * dpr); }
    const W = leinwand.width;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, W);
    const k = d.karte || {};
    const z = k.zelle_m || 0.05;
    const dinge = d.sichtungen || [];
    // Ausschnitt: alles Bekannte, mindestens 2 m, etwas Rand
    const xs = [], ys = [];
    for (const [i, j] of [...(k.frei || []), ...(k.belegt || [])]) { xs.push((i + 0.5) * z); ys.push((j + 0.5) * z); }
    for (const s of dinge) { xs.push(s.x); ys.push(s.y); }
    if (d.ente) { xs.push(d.ente.x); ys.push(d.ente.y); }
    if (!xs.length) { xs.push(0); ys.push(0); }
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const span = Math.max(2, Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) + 0.6;
    const m = W / span;                                  // Pixel je Meter
    const px = (x) => W / 2 + (x - cx) * m;
    const py = (y) => W / 2 - (y - cy) * m;              // Norden oben
    const zp = Math.max(1, z * m);
    ctx.fillStyle = farbe('--raum-frei');
    for (const [i, j] of k.frei || []) ctx.fillRect(px(i * z), py((j + 1) * z), zp + 0.5, zp + 0.5);
    ctx.fillStyle = farbe('--raum-belegt');
    for (const [i, j] of k.belegt || []) ctx.fillRect(px(i * z), py((j + 1) * z), zp + 0.5, zp + 0.5);
    // Dinge und Möbel: Kreis als Markierung, Piktogramm, Name
    const schrift = Math.round(11 * dpr);
    for (const s of dinge) {
      const x = px(s.x), y = py(s.y);
      const moebel = s.art === 'möbel';
      ctx.beginPath();
      ctx.arc(x, y, (moebel ? 13 : 10) * dpr, 0, Math.PI * 2);
      ctx.fillStyle = moebel ? 'rgba(0,0,0,.35)' : farbe('--raum-ding');
      ctx.globalAlpha = moebel ? 1 : 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.font = `${Math.round((moebel ? 15 : 12) * dpr)}px "Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji",sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(piktogramm(s), x, y + dpr);
      ctx.font = `${schrift}px "IBM Plex Sans", sans-serif`;
      ctx.fillStyle = farbe('--ink-2');
      ctx.textBaseline = 'top';
      ctx.fillText(tr(s.name), x, y + (moebel ? 15 : 12) * dpr);
    }
    // die Ente mit Blickrichtung
    if (d.ente) {
      const x = px(d.ente.x), y = py(d.ente.y), w = -d.ente.yaw;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(w);
      ctx.beginPath();
      ctx.moveTo(11 * dpr, 0);
      ctx.lineTo(-7 * dpr, 7 * dpr);
      ctx.lineTo(-4 * dpr, 0);
      ctx.lineTo(-7 * dpr, -7 * dpr);
      ctx.closePath();
      ctx.fillStyle = farbe('--raum-ente');
      ctx.fill();
      ctx.restore();
    }
    // Maßstab: 1 m
    ctx.fillStyle = farbe('--ink-3');
    ctx.fillRect(8 * dpr, W - 10 * dpr, m, 2 * dpr);
    ctx.font = `${schrift}px "IBM Plex Sans", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('1 m', 8 * dpr, W - 13 * dpr);
    const n = dinge.filter((s) => s.art !== 'möbel').length;
    leinwand.setAttribute('aria-label', d.messungen
      ? tr(`Erkundeter Bereich von oben: ${(d.flaeche_m2 || 0).toLocaleString(document.documentElement.lang || 'de', { maximumFractionDigits: 1 })} m², ${n} Dinge und ${dinge.length - n} Möbel eingezeichnet`)
      : tr('Erkundeter Bereich von oben: noch leer'));
  }
  async function laden() {
    const d = await api('/api/raum').catch(() => null);
    if (d) zeigen(d);
  }
  async function aktion(body) {
    try { zeigen(await api('/api/raum', 'POST', body)); } catch (e) { toast(e.message || String(e), true); }
  }
  // Kartieren: daneben wächst die Karte von oben (2D-Vorschau, seit 0.37.11 – Wunsch des Maintainers), in 3D im Cockpit
  $('raum-start').addEventListener('click', () => aktion({ aktion: letzte && letzte.kartiert ? 'stopp' : 'start', sekunden: 120 }));
  $('raum-3d').addEventListener('click', () => {
    if (!zeigen3d.checked) setzeZeigen(true);
    if (zumCockpit) zumCockpit();
  });
  $('raum-leeren').addEventListener('click', () => {
    const b = $('raum-leeren');
    if (!leerenScharf) {                      // zweiter Klick löscht – kein Versehen
      leerenScharf = true;
      b.textContent = tr('Wirklich löschen?');
      b.classList.add('btn--danger');
      setTimeout(() => { leerenScharf = false; b.textContent = tr('Erkundetes löschen'); b.classList.remove('btn--danger'); }, 4000);
      return;
    }
    leerenScharf = false;
    b.textContent = tr('Erkundetes löschen');
    b.classList.remove('btn--danger');
    aktion({ aktion: 'karte_leeren' });
  });
  zeigen3d.addEventListener('change', () => setzeZeigen(zeigen3d.checked));
  if (spiegel) spiegel.addEventListener('change', () => setzeZeigen(spiegel.checked));
  for (const b of karte.querySelectorAll('[data-bring]')) {
    b.addEventListener('click', () => aktion({ aktion: 'apportieren', ding: b.dataset.bring }));
  }
  // Karte im Blick halten: alle 2 s, solange die Karte sichtbar ist oder gerade kartiert wird
  function takt() {
    clearInterval(timer);
    timer = setInterval(() => { if (sichtbar || (letzte && letzte.kartiert)) laden(); }, 2000);
  }
  let sichtbar = false;
  new IntersectionObserver((e) => {
    sichtbar = e.some((x) => x.isIntersecting);
    if (sichtbar) laden();
  }).observe(karte);
  laden();
  takt();
  return { laden };
}
