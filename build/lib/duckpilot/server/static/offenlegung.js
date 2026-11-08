// Progressive Offenlegung in den Einstellungen (seit 0.38.14, Wunsch des Maintainers): Zusatzfelder erscheinen erst, wenn
// die zugehörige Wahl aktiv ist – z. B. Anbieter, Schlüssel und Modell erst bei „Anderes Modell“.
//
//   data-zeige-wenn="#fern-an"          Schalter mit dieser id ist an
//   data-zeige-wenn="gehirn=lokal"      Auswahl (Radiogruppe name=… oder Feld data-set=…) hat diesen Wert
//   data-zeige-wenn="stt!=aus"          … hat nicht diesen Wert; mehrere Werte mit „|“
//
// Ausgeblendet wird mit `hidden` (auch für Screenreader weg), der steuernde Schalter bekommt aria-controls und – bei
// Schaltern – aria-expanded. Steckt der Fokus in einem Feld, das gerade verschwindet, geht er auf den Schalter zurück.

function steuerung(ausdruck) {
  if (ausdruck.startsWith('#')) {
    const el = document.getElementById(ausdruck.slice(1));
    return { els: el ? [el] : [], an: () => !!el?.checked };
  }
  const m = ausdruck.match(/^([\w-]+)(!?=)(.+)$/);
  if (!m) return { els: [], an: () => true };
  const [, key, op, werte] = m;
  const liste = werte.split('|');
  const els = [...document.querySelectorAll(`input[type=radio][name="${key}"], [data-set="${key}"]:not([type=radio])`)];
  const wert = () => {
    const radio = els.find((e) => e.type === 'radio' && e.checked);
    if (radio) return radio.value;
    const feld = els.find((e) => e.type !== 'radio');
    return feld ? (feld.type === 'checkbox' ? String(feld.checked) : feld.value) : '';
  };
  return { els, an: () => (op === '=') === liste.includes(wert()) };
}

export function offenlegen(wurzel = document) {
  for (const ziel of wurzel.querySelectorAll('[data-zeige-wenn]')) {
    const s = steuerung(ziel.dataset.zeigeWenn);
    if (!s.els.length) continue;
    const zeigen = s.an();
    if (!zeigen && ziel.contains(document.activeElement)) (s.els.find((e) => e.checked) || s.els[0]).focus();
    ziel.hidden = !zeigen;
    if (ziel.id) {
      for (const e of s.els) {
        const ids = new Set((e.getAttribute('aria-controls') || '').split(' ').filter(Boolean));
        ids.add(ziel.id);
        e.setAttribute('aria-controls', [...ids].join(' '));
        if (e.type === 'checkbox') e.setAttribute('aria-expanded', String(zeigen));
      }
    }
  }
}

export function initOffenlegung() {
  // Klicks des Menschen sofort; Werte, die Skripte setzen (Laden der Einstellungen), über offenlegen() danach
  document.addEventListener('change', () => offenlegen());
  offenlegen();
  return { offenlegen };
}
