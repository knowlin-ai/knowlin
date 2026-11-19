// Tagesrückblick (seit 0.39, Erfahrungsnetz 2): was Knowlin an einem Tag erlebt hat – aus dem Tagebuch, ohne
// Sprachmodell zusammengefasst (duckpilot/tagebuch.py). Tag wählen, worum es ging, Neues, die stärksten Momente; ein
// Moment, der nicht stimmt, lässt sich löschen (nur am PC). „In der Galaxie zeigen“ hebt die Sterne des Tages hervor.

import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;

function tagName(tag) {
  const heute = new Date();
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const gestern = new Date(heute.getTime() - 86400000);
  if (tag === iso(heute)) return tr('Heute');
  if (tag === iso(gestern)) return tr('Gestern');
  const [j, m, t] = tag.split('-').map(Number);
  return new Date(j, m - 1, t).toLocaleDateString(document.documentElement.lang || 'de',
    { weekday: 'short', day: 'numeric', month: 'numeric' });
}

export function initTagesrueckblick({ api, toast }) {
  const karte = document.getElementById('tages-karte');
  if (!karte) return;
  const wahl = document.getElementById('tages-tag');
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  let aktuell = '';
  let ids = [];

  function zeigen(r) {
    if (!r || r.an === false) { karte.hidden = true; return; }
    karte.hidden = false;
    aktuell = r.tag;
    ids = r.ids || [];
    const tage = r.tage && r.tage.length ? r.tage : [r.tag];
    if (!tage.includes(r.tag)) tage.unshift(r.tag);
    wahl.replaceChildren(...tage.map((t) => { const o = el('option', '', tagName(t)); o.value = t; o.selected = t === r.tag; return o; }));
    document.getElementById('tages-text').textContent = r.text || '';
    const worum = document.getElementById('tages-worum');
    worum.replaceChildren(...(r.haeufig || []).map((h) => el('li', 'chip', `${tr(h.name)} · ${h.n}×`)));
    document.getElementById('tages-worum-box').hidden = !(r.haeufig || []).length;
    const neu = document.getElementById('tages-neu');
    neu.replaceChildren(...(r.neu || []).map((n) => el('li', 'chip', tr(n))));
    document.getElementById('tages-neu-box').hidden = !(r.neu || []).length;
    const momente = document.getElementById('tages-momente');
    momente.replaceChildren(...(r.momente || []).map((m) => {
      const li = el('li', 'tages-moment');
      li.append(el('span', 'tages-zeit', m.zeit), el('span', 'tages-warum', tr(m.warum)));
      const weg = el('button', 'btn btn--ghost btn--sm pc-only', tr('Löschen'));
      weg.type = 'button';
      weg.setAttribute('aria-label', `${tr('Moment löschen')}: ${m.zeit} ${tr(m.warum)}`);
      weg.addEventListener('click', async () => {
        const d = await api('/api/erfahrung/rueckblick/loeschen', 'POST', { tag: aktuell, t: m.t });
        if (d && d.ok) { zeigen(d); toast(tr('Moment gelöscht.')); } else toast(tr('Ging nicht – bitte noch einmal.'));
      });
      li.append(weg);
      return li;
    }));
    document.getElementById('tages-momente-box').hidden = !(r.momente || []).length;
    const galaxie = document.getElementById('tages-galaxie');
    if (galaxie) galaxie.hidden = !ids.length;
  }

  async function laden(tag = aktuell) {
    const d = await api(`/api/erfahrung/rueckblick${tag ? `?tag=${encodeURIComponent(tag)}` : ''}`).catch(() => null);
    zeigen(d);
  }

  wahl.addEventListener('change', () => laden(wahl.value));
  document.getElementById('tages-galaxie')?.addEventListener('click', () => {
    window.dispatchEvent(new CustomEvent('knowlin:hirn-tag', { detail: { tag: aktuell, ids, name: tagName(aktuell) } }));
    document.getElementById('card-brain')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) laden(); }).observe(karte.parentElement);
}
