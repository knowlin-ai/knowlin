// Suche auf der Seite „Tricks“ (seit 0.38.61, Maintainer: „für Tricks und Fähigkeiten vllt eine Suchfunktion – z. B. bei
// Microduck ist die Liste ja sehr lang aus unterschiedlichen Quellen“). Filtert alle Kacheln der Seite – Pollens
// Emotionen, Erweiterungen (Got a Talent, Bewegungen aus Pollens Apps, Gangarten), eigene Gesten, Leerlauf, Gesten und
// Aufträge des Arms, Reachys Emotionen und Tänze – nach Titel und Beschreibung. Abschnitte ohne Treffer verschwinden.
// Kacheln, die erst später vom Hub kommen, werden gleich mitgefiltert. Groß/klein und ä/ae sind egal; mehrere Wörter
// müssen alle vorkommen.

const KACHELN = '.emo, article.move, article.talent, li.gait';
const GRUPPEN = '.emo-grid, .move-grid, .talent-grid, .gait-list';
const AUS = 'such-aus';

// „Gefieder putzen“ findet man auch mit „gefieder“, „PUTZEN“ oder „putzen gefi“; „über“ auch mit „ueber“
export function falten(text) {
  return String(text || '').toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .normalize('NFD').replace(/[̀-ͯ]/g, '');
}

export function passt(text, anfrage) {
  const t = falten(text);
  return falten(anfrage).split(/\s+/).filter(Boolean).every((w) => t.includes(w));
}

export function initTricksSuche({ $ }) {
  const feld = $('tricks-suche');
  const bereich = document.querySelector('#view-tricks .tricks-links');
  if (!feld || !bereich) return { anwenden() {} };
  const info = $('tricks-suche-info');
  const leer = $('tricks-suche-leer');

  function anwenden() {
    const q = feld.value.trim();
    for (const e of bereich.querySelectorAll(`.${AUS}`)) e.classList.remove(AUS);
    if (leer) leer.hidden = true;
    if (!q) { if (info) info.textContent = ''; return; }
    // nur, was ohne Suche zu sehen wäre (andere Körper, ausgeschaltete Bereiche zählen nicht mit)
    const sichtbar = [...bereich.querySelectorAll(KACHELN)].filter((k) => k.getClientRects().length);
    let treffer = 0;
    for (const k of sichtbar) {
      if (passt(k.textContent, q)) treffer += 1;
      else k.classList.add(AUS);
    }
    for (const g of bereich.querySelectorAll(GRUPPEN)) {
      if (!g.getClientRects().length || g.querySelector(`:is(${KACHELN}):not(.${AUS})`)) continue;
      g.classList.add(AUS);
      const kopf = g.previousElementSibling;
      if (kopf && kopf.classList.contains('section-head')) kopf.classList.add(AUS);
    }
    for (const s of bereich.querySelectorAll('.pack-section')) {
      if (!s.querySelector(`:is(${KACHELN}):not(.${AUS})`)) s.classList.add(AUS);
    }
    if (info) info.textContent = `${treffer} von ${sichtbar.length}`;
    if (leer) leer.hidden = treffer > 0;
  }

  let warten = 0;
  const bald = () => { clearTimeout(warten); warten = setTimeout(anwenden, 120); };
  feld.addEventListener('input', bald);
  // Kataloge vom Hub kommen später – neue Kacheln gleich mitfiltern
  new MutationObserver(() => { if (feld.value.trim()) bald(); }).observe(bereich, { childList: true, subtree: true });
  return { anwenden };
}
