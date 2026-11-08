// „Was Knowlin über deine Welt weiß“ (G1, seit 0.38.27; Wunsch „der Nutzen der Funktion soll zum Tragen kommen“):
// Themenkarten aus dem Erfahrungsnetz – Menschen, Orte, Dinge, Tätigkeiten mit Umfang, Gefühlston (Zeichen + Wort,
// nie Farbe allein), Frische und Sicherheit. Klick auf ein Thema öffnet es im Netz („womit verknüpft und warum“).
import { el } from './ui.js';
import { uebersetzeText } from './i18n.js';

const tr = (s) => uebersetzeText(s) || s;

export function initWelt({ $, api }) {
  const box = $('welt-gruppen');
  if (!box) return { laden() {} };
  let zuletzt = 0;

  function thema(e) {
    const li = el('li', 'welt-thema');
    const knopf = el('button', 'welt-name', e.name);
    knopf.type = 'button';
    knopf.title = tr('Im Erfahrungsnetz ansehen: womit verknüpft und warum');
    knopf.addEventListener('click', () => {
      const pick = $('brain-pick');
      if (!pick || ![...pick.options].some((o) => o.value === e.id)) return;
      pick.value = e.id;
      pick.dispatchEvent(new Event('change'));
      $('card-brain')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    const ton = el('span', `welt-ton welt-ton--${e.ton.zeichen === '+' ? 'gut' : e.ton.zeichen === '−' ? 'heikel' : 'neutral'}`);
    ton.append(el('span', 'welt-zeichen', e.ton.zeichen), document.createTextNode(` ${tr(e.ton.wort)}`));
    const kopf = el('div', 'welt-kopf');
    kopf.append(knopf, ton);
    li.append(kopf);
    const fakten = el('p', 'welt-fakten');
    fakten.append(el('span', null, tr(`${e.erlebnisse}× erlebt`)), el('span', null, tr(`${e.verbindungen} Verknüpfungen`)),
      el('span', null, tr(`zuletzt ${e.zuletzt.wort}`)), el('span', null, tr(e.sicherheit)));
    li.append(fakten);
    if (e.mit && e.mit.length) li.append(el('p', 'welt-mit', `${tr('verknüpft mit')} ${e.mit.join(', ')}`));
    return li;
  }

  function zeigen(d) {
    const gruppen = (d.gruppen || []).filter((g) => g.eintraege.length);
    $('welt-leer').hidden = gruppen.length > 0;
    box.replaceChildren(...gruppen.map((g) => {
      const sec = el('section', 'welt-gruppe');
      const h = el('h4', null, tr(g.titel));
      if (g.anzahl > g.eintraege.length) h.append(el('small', null, ` ${tr(`${g.eintraege.length} von ${g.anzahl}`)}`));
      const ul = el('ul', 'welt-liste');
      ul.append(...g.eintraege.map(thema));
      sec.append(h, ul);
      return sec;
    }));
  }

  // beim Öffnen der Gedächtnis-Seite und höchstens alle 15 s nachladen (das Netz ändert sich langsam)
  async function laden(sofort = false) {
    if (!sofort && performance.now() - zuletzt < 15000) return;
    zuletzt = performance.now();
    const d = await api('/api/erfahrung/themen').catch(() => null);
    if (d && d.ok) { $('welt').hidden = !d.an; zeigen(d); }
  }
  return { laden };
}
