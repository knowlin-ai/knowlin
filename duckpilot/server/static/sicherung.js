// Sicherungspunkte (seit 0.38.24): Verlauf, anlegen, wiederherstellen, exportieren, importieren, löschen und
// Bereiche zurücksetzen. Wunsch: „wie im Leben – manchmal will man bestimmte Erlebnisse wieder rückgängig machen“.
// Zurücksetzen, Wiederherstellen und Löschen brauchen einen zweiten Klick; vorher legt der Server einen Punkt an.
import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

const ARTEN = {
  hand: 'Selbst angelegt', auto: 'Täglich', 'vor-zuruecksetzen': 'Vor dem Zurücksetzen',
  'vor-wiederherstellen': 'Vor dem Wiederherstellen', import: 'Importiert',
};
const TITEL = {
  gedaechtnis: 'Gedächtnis', erfahrung: 'Erfahrungsnetz', charakter: 'Charakter', uebungen: 'Übungen', taenze: 'Tänze', raum: 'Raum',
};

// Kurz, was drinsteckt: „12 Erinnerungen · 340 Verbindungen · 2 Tänze“
function inhalt(zahlen = {}) {
  const teile = [];
  const g = zahlen.gedaechtnis;
  if (g) teile.push(`${(g.wissen || 0) + (g.vorlieben || 0) + (g.orte || 0) + (g.tricks || 0)} ${tr('Erinnerungen')}`);
  if (zahlen.erfahrung) teile.push(`${zahlen.erfahrung.verbindungen || 0} ${tr('Verbindungen')}`);
  if (zahlen.uebungen && (zahlen.uebungen.uebungen || zahlen.uebungen.posen)) {
    teile.push(`${(zahlen.uebungen.uebungen || 0) + (zahlen.uebungen.posen || 0)} ${tr('Übungen')}`);
  }
  if (zahlen.taenze && zahlen.taenze.taenze) teile.push(`${zahlen.taenze.taenze} ${tr('Tänze')}`);
  return teile.join(' · ');
}

function zeit(iso) {
  const d = new Date(iso || '');
  if (Number.isNaN(d.getTime())) return iso || '';
  const lang = document.documentElement.lang === 'en' ? 'en-GB' : 'de-DE';
  return d.toLocaleString(lang, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// Zwei Klicks: der erste fragt nach, der zweite führt aus (wie bei „Alles vergessen“)
function zweiKlicks(knopf, frage, tun) {
  let scharf = null;
  const text = knopf.textContent;
  knopf.addEventListener('click', async () => {
    if (!scharf) {
      knopf.textContent = tr(frage);
      knopf.classList.add('armed');
      scharf = setTimeout(() => { scharf = null; knopf.textContent = text; knopf.classList.remove('armed'); }, 5000);
      return;
    }
    clearTimeout(scharf);
    scharf = null;
    knopf.textContent = text;
    knopf.classList.remove('armed');
    knopf.disabled = true;
    try { await tun(); } finally { knopf.disabled = false; }
  });
}

export function initSicherung({ $, api, el, toast, isRemote, showView }) {
  const karte = $('set-sicherung');
  if (!karte) return { laden() {} };
  let daten = null;

  const meldung = (t) => { $('sich-msg').textContent = t || ''; };

  async function senden(body) {
    const res = await fetch('/api/sicherung', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const d = await res.json().catch(() => ({ ok: false, fehler: res.statusText }));
    if (!d.ok) { meldung(tr(d.fehler || 'Das hat nicht geklappt.')); return null; }
    zeigen(d);
    return d;
  }

  function haken(id, an, text, zusatz) {
    const l = el('label', 'sich-haken');
    const i = el('input');
    i.type = 'checkbox'; i.value = id; i.checked = an;
    const t = el('span', null, tr(text));
    if (zusatz) t.append(el('small', null, zusatz));
    l.append(i, t);
    return l;
  }

  function wiederherstellenFeld(p, li) {
    const offen = li.querySelector('.sich-zurueck');
    if (offen) { offen.remove(); return; }
    const box = el('div', 'sich-zurueck');
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', tr('Was zurückholen?'));
    const wahl = el('div', 'sich-bereiche');
    for (const b of p.bereiche) wahl.append(haken(b, true, TITEL[b] || b));
    const los = el('button', 'btn btn--sm', tr('Jetzt wiederherstellen'));
    los.type = 'button';
    zweiKlicks(los, 'Wirklich? Nochmal klicken – vorher wird gesichert', async () => {
      const bereiche = [...wahl.querySelectorAll('input:checked')].map((i) => i.value);
      const d = await senden({ aktion: 'wiederherstellen', id: p.id, bereiche, bestaetigt: true });
      if (d) { toast(tr('Wiederhergestellt')); meldung(`${tr('Wiederhergestellt')}: ${bereiche.map((b) => tr(TITEL[b] || b)).join(', ')}`); }
    });
    box.append(el('p', 'field-help', tr('Was zurückholen? Der jetzige Stand wird vorher gesichert.')), wahl, los);
    li.append(box);
    wahl.querySelector('input')?.focus();
  }

  function punktZeile(p) {
    const li = el('li', `sich-punkt sich-punkt--${p.art}`);
    const kopf = el('div', 'sich-kopf');
    const titel = el('b', null, zeit(p.zeit));
    const was = el('span', 'sich-art', p.name ? `${p.name} · ${tr(ARTEN[p.art] || '')}` : tr(ARTEN[p.art] || ''));
    kopf.append(titel, was, el('small', null, inhalt(p.zahlen)));
    const knoepfe = el('div', 'sich-knoepfe');
    const zurueck = el('button', 'btn btn--sm', tr('Wiederherstellen …'));
    zurueck.type = 'button';
    zurueck.addEventListener('click', () => wiederherstellenFeld(p, li));
    const export_ = el('a', 'btn btn--ghost btn--sm', tr('Exportieren'));
    export_.href = `/api/sicherung/${encodeURIComponent(p.id)}/export`;
    export_.download = `knowlin-sicherung-${p.id}.zip`;
    const weg = el('button', 'btn btn--ghost btn--sm', tr('Löschen'));
    weg.type = 'button';
    zweiKlicks(weg, 'Löschen? Nochmal klicken', async () => {
      if (await senden({ aktion: 'loeschen', id: p.id, bestaetigt: true })) meldung(tr('Sicherungspunkt gelöscht.'));
    });
    knoepfe.append(zurueck, export_, weg);
    li.append(kopf, knoepfe);
    return li;
  }

  function zeigen(d) {
    daten = d;
    const liste = $('sich-liste');
    liste.replaceChildren(...(d.punkte.length ? d.punkte.map(punktZeile)
      : [el('li', 'field-help', tr('Noch kein Sicherungspunkt – der erste entsteht beim nächsten Start oder hier mit „Sicherungspunkt anlegen“.'))]));
    const wahl = $('sich-bereiche');
    const vorher = new Set([...wahl.querySelectorAll('input:checked')].map((i) => i.value));
    wahl.replaceChildren(...d.bereiche.map((b) => {
      const z = inhalt({ [b.id]: b.zahlen });
      return haken(b.id, vorher.has(b.id), b.titel, z ? `${tr(b.text)} – ${z}` : tr(b.text));
    }));
    $('sich-reset').disabled = !vorher.size;
  }

  async function laden() {
    if (isRemote && isRemote()) return;
    const d = await api('/api/sicherung').catch(() => null);
    if (d && d.ok) zeigen(d);
  }

  // Vom Gedächtnis aus („Sicherungspunkte“ neben „Alles vergessen“) direkt hierher
  for (const k of document.querySelectorAll('[data-zu-sicherung]')) {
    k.addEventListener('click', () => {
      showView?.('settings');
      requestAnimationFrame(() => { karte.scrollIntoView({ block: 'start' }); $('sich-anlegen').focus({ preventScroll: true }); });
    });
  }
  $('sich-bereiche').addEventListener('change', () => {
    $('sich-reset').disabled = !$('sich-bereiche').querySelector('input:checked');
  });
  $('sich-anlegen').addEventListener('click', async () => {
    const d = await senden({ aktion: 'anlegen', name: $('sich-name').value.trim() });
    if (d) { $('sich-name').value = ''; meldung(tr('Sicherungspunkt angelegt.')); }
  });
  zweiKlicks($('sich-reset'), 'Wirklich zurücksetzen? Nochmal klicken', async () => {
    const bereiche = [...$('sich-bereiche').querySelectorAll('input:checked')].map((i) => i.value);
    const d = await senden({ aktion: 'zuruecksetzen', bereiche, bestaetigt: true });
    if (d) {
      for (const i of $('sich-bereiche').querySelectorAll('input')) i.checked = false;
      $('sich-reset').disabled = true;
      meldung(`${tr('Zurückgesetzt')}: ${bereiche.map((b) => tr(TITEL[b] || b)).join(', ')}. ${tr('Rückgängig: „Vor dem Zurücksetzen“ wiederherstellen.')}`);
    }
  });
  $('sich-import').addEventListener('change', async (e) => {
    const datei = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!datei) return;
    const res = await fetch('/api/sicherung/import', { method: 'POST', body: datei });
    const d = await res.json().catch(() => ({ ok: false }));
    if (!d.ok) { meldung(tr(d.fehler || 'Die Datei ließ sich nicht lesen.')); return; }
    zeigen(d);
    meldung(tr('Importiert – zum Übernehmen „Wiederherstellen …“ wählen.'));
  });

  return { laden, get daten() { return daten; } };
}
