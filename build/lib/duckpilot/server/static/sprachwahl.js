// Sprachauswahl als Dropdown mit Flaggen (seit 0.36.1, Wunsch des Maintainers). Ein natives <select> kann keine Bilder
// zeigen, deshalb Knopf + Liste nach dem ARIA-Muster „Listbox“: Pfeiltasten, Enter, Esc, Klick daneben schließt.
// Die Wahl geht über das versteckte Feld [data-set="sprache"] – gespeichert und neu geladen wie jede Einstellung.

export function initSprachwahl({ $ }) {
  const knopf = $('sprache-knopf');
  const liste = $('sprache-liste');
  const wert = $('sprache-wert');
  if (!knopf || !liste || !wert) return;
  const optionen = [...liste.querySelectorAll('[role="option"]')];
  let aktiv = 0;

  const aktuell = () => wert.value || document.documentElement.lang || 'de';
  function zeigeWahl() {
    const o = optionen.find((x) => x.dataset.wert === aktuell()) || optionen[0];
    knopf.replaceChildren(...[...o.childNodes].map((n) => n.cloneNode(true)));
    for (const x of optionen) x.setAttribute('aria-selected', String(x === o));
  }
  function markiere(i) {
    aktiv = (i + optionen.length) % optionen.length;
    optionen.forEach((x, j) => x.classList.toggle('is-aktiv', j === aktiv));
    liste.setAttribute('aria-activedescendant', optionen[aktiv].id);
  }
  function oeffnen() {
    zeigeWahl();
    liste.hidden = false;
    knopf.setAttribute('aria-expanded', 'true');
    markiere(Math.max(0, optionen.findIndex((x) => x.dataset.wert === aktuell())));
    liste.focus();
  }
  function schliessen(fokus = true) {
    liste.hidden = true;
    knopf.setAttribute('aria-expanded', 'false');
    if (fokus) knopf.focus();
  }
  function waehle(o) {
    schliessen();
    if (o.dataset.wert === aktuell()) return;
    wert.value = o.dataset.wert;
    zeigeWahl();
    wert.dispatchEvent(new Event('input'));          // speichern und neu laden (app.js)
  }
  optionen.forEach((o, i) => {
    o.id = `sprache-opt-${o.dataset.wert}`;
    o.addEventListener('click', () => waehle(o));
    o.addEventListener('pointermove', () => markiere(i));
  });
  knopf.addEventListener('click', () => (liste.hidden ? oeffnen() : schliessen()));
  knopf.addEventListener('keydown', (e) => { if (['ArrowDown', 'ArrowUp'].includes(e.key)) { e.preventDefault(); oeffnen(); } });
  liste.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); markiere(aktiv + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); markiere(aktiv - 1); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); waehle(optionen[aktiv]); }
    else if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); schliessen(); }
  });
  document.addEventListener('pointerdown', (e) => { if (!liste.hidden && !e.target.closest('.sprachwahl')) schliessen(false); });
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) zeigeWahl(); }).observe(knopf);   // Einstellungen geladen
  zeigeWahl();
  return { zeigeWahl };
}
