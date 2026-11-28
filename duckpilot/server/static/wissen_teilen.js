// Ein Kopf, viele Körper (seit 0.56): was alle Verkörperungen teilen und welche Tricks eine von der anderen übernimmt.
// Server: /api/wissen/koerper, /api/wissen/trick_uebernehmen (brain/wissen_teilen.py). Lädt, wenn die Karte sichtbar wird.
import { el } from './ui.js';
import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const vonText = (von) => Object.entries(von || {}).map(([wer, n]) => `${wer} ${n}`).join(' · ');

export function initWissenTeilen({ api, toast }) {
  const karte = document.getElementById('kw-karte');
  if (!karte) return;
  const geteilt = document.getElementById('kw-geteilt');
  const andere = document.getElementById('kw-andere');
  const leer = document.getElementById('kw-leer');

  function zeile(titel, wert, detail) {
    const li = el('li', 'kw-zeile');
    li.append(el('span', 'kw-titel', tr(titel)), el('span', 'kw-wert', wert));
    if (detail) li.append(el('span', 'kw-detail', detail));
    return li;
  }

  function zeigen(u) {
    if (!u || !u.ok) return;
    const g = u.geteilt;
    const z = g.orte.zimmer || {};
    geteilt.replaceChildren(
      zeile('Wissen', String(g.wissen.anzahl), g.wissen.anzahl ? `${tr('gelernt von')} ${vonText(g.wissen.von)}` : ''),
      zeile('Vorlieben', String(g.vorlieben.anzahl), g.vorlieben.anzahl ? `${tr('gelernt von')} ${vonText(g.vorlieben.von)}` : ''),
      zeile('Orte', String(g.orte.anzahl), [z.simulator ? `${tr('Simulator')} ${z.simulator}` : '',
        z.echt ? `${tr('echtes Zimmer')} ${z.echt}` : ''].filter(Boolean).join(' · ')));
    andere.replaceChildren();
    for (const a of u.andere) {
      const box = el('div', 'kw-figur');
      box.append(el('h4', null, `${a.name} · ${a.art}`));
      if (!a.passt) box.append(el('p', 'field-help', tr('Anderer Körper – seine Tricks passen nicht auf diesen.')));
      const ul = el('ul', 'kw-tricks');
      for (const t of a.tricks) {
        const li = el('li', null);
        li.append(el('span', null, t.name));
        if (a.passt && !t.schon_da) {
          const b = el('button', 'btn btn--sm', tr('Übernehmen'));
          b.type = 'button';
          b.addEventListener('click', async () => {
            const r = await api('/api/wissen/trick_uebernehmen', 'POST', { von: a.modul, name: t.name })
              .catch((e) => ({ ok: false, fehler: e.message }));
            if (!r.ok) return toast(r.fehler || tr('Ging nicht'), 'err');
            toast(`${tr('Übernommen')}: ${t.name}`);
            zeigen(r);
          });
          li.append(b);
        } else if (t.schon_da) li.append(el('span', 'kw-detail', tr('schon da')));
        ul.append(li);
      }
      box.append(ul);
      andere.append(box);
    }
    leer.hidden = u.andere.length > 0;
  }

  async function laden() {
    zeigen(await api('/api/wissen/koerper').catch(() => null));
  }
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) laden(); }).observe(karte);
}
