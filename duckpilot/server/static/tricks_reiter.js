// Reiter je Quelle auf der Seite „Tricks“ (seit 0.38.66, Wunsch des Maintainers: „bei Tricks sind die Listen oft sehr
// lang – entweder ausklappen, Reiter oder andere Übersichtlichkeit je nach Quelle“; entschieden: Reiter je Quelle, die
// Suche geht über alle).
//
// Die Quellen ergeben sich aus der Seite selbst: jeder Abschnitt mit Überschrift (Pollens Emotionen, Got a Talent,
// Bellos Tricks, Gesten am Arm …), sichtbar je nach Körper. „Alle“ zeigt wie bisher alles untereinander. Wer sucht,
// sucht immer in allen Quellen – solange im Suchfeld etwas steht, ist die Auswahl des Reiters ausgesetzt.

import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const KACHELN = '.emo, article.move, article.talent, li.gait';
const AUS = 'reiter-aus';
const SPEICHER = 'duckpilot.tricks.reiter';

/** Abschnitte der Seite als Quellen: Überschrift und alles bis zur nächsten Überschrift (oder der ganze Abschnitt). */
export function quellen(bereich) {
  const out = [];
  for (const kopf of bereich.querySelectorAll('.section-head')) {
    const titel = kopf.querySelector('h3')?.textContent.trim();
    if (!titel) continue;
    const huelle = kopf.parentElement;
    let teile;
    if (huelle.matches('section') && huelle.firstElementChild === kopf) {
      teile = [huelle];                                   // eigener Abschnitt (Erweiterung, Pollens Apps)
    } else {
      teile = [kopf];
      for (let n = kopf.nextElementSibling; n && !n.classList.contains('section-head'); n = n.nextElementSibling) {
        if (n.matches('section') && n.querySelector(':scope > .section-head')) break;   // eigener Abschnitt folgt
        teile.push(n);
      }
    }
    out.push({ titel, kopf, teile });
  }
  return out;
}

export function initTricksReiter({ $, el }) {
  const bereich = document.querySelector('#view-tricks .tricks-links');
  const leiste = $('tricks-reiter');
  const feld = $('tricks-suche');
  if (!bereich || !leiste) return { aktualisieren() {} };
  let aktiv = 'alle';
  try { aktiv = localStorage.getItem(SPEICHER) || 'alle'; } catch { /* privat */ }
  let liste = [];

  function sichtbar(q) {
    for (const t of q.teile) t.classList.remove(AUS);
    return !!q.kopf.getClientRects().length;
  }

  function anwenden() {
    const suchen = !!feld?.value.trim();
    const gibt = liste.some((q) => q.titel === aktiv);
    for (const q of liste) {
      const aus = !suchen && gibt && aktiv !== 'alle' && q.titel !== aktiv;
      for (const t of q.teile) t.classList.toggle(AUS, aus);
    }
    for (const b of leiste.querySelectorAll('button')) {
      const an = suchen ? b.dataset.quelle === 'alle' : b.dataset.quelle === (gibt ? aktiv : 'alle');
      b.setAttribute('aria-pressed', String(an));
    }
    leiste.classList.toggle('tricks-reiter--suche', suchen);
  }

  function aktualisieren() {
    for (const q of liste) for (const t of q.teile) t.classList.remove(AUS);
    liste = quellen(bereich).filter(sichtbar);
    leiste.hidden = liste.length < 2;                     // eine Quelle: Reiter wären nur Ballast
    if (leiste.hidden) return;
    const knopf = (quelle, text, n) => {
      const b = el('button', 'chip');
      b.type = 'button';
      b.dataset.quelle = quelle;
      b.textContent = n ? `${text} · ${n}` : text;
      b.addEventListener('click', () => {
        aktiv = quelle;
        try { localStorage.setItem(SPEICHER, quelle); } catch { /* privat */ }
        if (feld && feld.value) { feld.value = ''; feld.dispatchEvent(new Event('input')); }
        anwenden();
      });
      return b;
    };
    const alle = liste.reduce((s, q) => s + q.teile.reduce((n, t) => n + t.querySelectorAll(KACHELN).length, 0), 0);
    leiste.replaceChildren(knopf('alle', tr('Alle'), alle),
      ...liste.map((q) => knopf(q.titel, q.titel, q.teile.reduce((n, t) => n + t.querySelectorAll(KACHELN).length, 0))));
    anwenden();
  }

  let warten = 0;
  const bald = () => { clearTimeout(warten); warten = setTimeout(aktualisieren, 200); };
  // Kataloge vom Hub kommen später, Körper wechseln: Quellen und Zahlen neu – aber nicht bei den eigenen Klassen
  new MutationObserver((m) => { if (m.some((x) => x.type === 'childList')) bald(); })
    .observe(bereich, { childList: true, subtree: true });
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) aktualisieren(); }).observe(leiste.parentElement);
  feld?.addEventListener('input', anwenden);              // sofort alle zeigen – die Suche filtert danach über alle
  return { aktualisieren };
}
