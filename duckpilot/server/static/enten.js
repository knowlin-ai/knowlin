// Mehrere Enten (seit 0.36.3): Übersicht und Gruppenbefehle auf Steuern → Team (seit 0.38). Die Anzahl ist eine Einstellung
// (data-set="weitere_enten"), der Modus gilt für die laufende Sitzung.

import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

export function initEnten({ $, api, el }) {
  const karte = $('enten-karte');
  if (!karte) return;
  let timer = null;

  function zeigen(d) {
    $('enten-hinweis').textContent = d.verfuegbar
      ? 'Weitere Enten mit eigener Stimme laufen im Simulator herum, begegnen und begrüßen sich, folgen dir oder tanzen mit. Sie bleiben bis zum Beenden – Knowlin startet immer mit einer Ente.'
      : d.grund;
    for (const b of karte.querySelectorAll('[data-enten-modus]')) {
      b.setAttribute('aria-pressed', String(d.verfuegbar && d.anzahl > 0 && b.dataset.entenModus === d.modus));
      b.disabled = !d.verfuegbar || !d.anzahl;
    }
    $('enten-mittanzen').checked = d.mittanzen !== false;
    for (const sel of document.querySelectorAll('[data-set="weitere_enten"]')) {
      if (sel.type === 'radio') sel.checked = sel.value === String(d.anzahl || 0);   // Zahlenreihe 0 … 8 (seit 0.38.24)
      else if (document.activeElement !== sel) sel.value = String(d.anzahl || 0);   // auch ohne geladene Einstellungen
      sel.disabled = !d.verfuegbar;          // seit 0.37.1: in der Physik und am Roboter ausgegraut, mit Grund
    }
    const n = d.anzahl || 0;
    if ($('enten-zahl-text')) $('enten-zahl-text').textContent = n ? `· ${n + 1} ${tr('Enten im Zimmer')}` : `· ${tr('nur deine Ente')}`;
    for (const p of document.querySelectorAll('[data-enten-hinweis]')) {
      p.textContent = d.verfuegbar
        ? tr('Jede Ente tanzt an ihrem eigenen Platz im selben Takt – im einfachen Simulator. Mehr unter Steuern → Team.')
        : tr(d.grund);
    }
    $('enten-mittanzen').disabled = !d.verfuegbar;
    // Teamarbeit (seit 0.37.4): was gerade läuft, die letzte Meldung, Auftrag beenden
    const a = d.auftrag;
    $('enten-auftrag').hidden = !a;
    if (a) {
      const letzte = a.fertig ? a.ergebnis : (a.meldungen || []).slice(-1)[0] || '';
      $('enten-auftrag-text').textContent = `${tr(a.art === 'suchen' ? 'Suchtrupp' : 'Aufräum-Team')}: ${tr(letzte)}`;
      $('enten-auftrag-stopp').hidden = !!a.fertig;
    }
    const ul = $('enten-liste');
    ul.replaceChildren(...(d.enten || []).map((e) => {
      const li = el('li');
      li.append(el('strong', '', e.name), el('span', 'field-help', ` · ${e.tut}`));
      return li;
    }));
  }
  async function laden() {
    const d = await api('/api/enten').catch(() => null);
    if (d) zeigen(d);
  }
  for (const b of karte.querySelectorAll('[data-enten-modus]')) {
    b.addEventListener('click', async () => { const d = await api('/api/enten', 'POST', { modus: b.dataset.entenModus }); zeigen(d); });
  }
  $('enten-auftrag-stopp').addEventListener('click', async () => zeigen(await api('/api/enten', 'POST', { auftrag: 'stopp' })));
  $('enten-mittanzen').addEventListener('change', async (e) => zeigen(await api('/api/enten', 'POST', { mittanzen: e.target.checked })));
  for (const s of document.querySelectorAll('[data-set="weitere_enten"]')) s.addEventListener('change', () => setTimeout(laden, 400));
  // auch die Auswahl unter Tanzen → Vorschau aktuell halten, sobald sie sichtbar wird
  const io = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) laden(); });
  for (const s of document.querySelectorAll('[data-set="weitere_enten"]')) io.observe(s);
  laden();                                   // gleich beim Start: die Auswahl zeigt sonst „allein“, bis man sie ansieht
  // nur abfragen, solange die Karte sichtbar ist
  new IntersectionObserver((e) => {
    const sichtbar = e.some((x) => x.isIntersecting);
    clearInterval(timer);
    if (sichtbar) { laden(); timer = setInterval(laden, 2000); }
  }).observe(karte);
}
