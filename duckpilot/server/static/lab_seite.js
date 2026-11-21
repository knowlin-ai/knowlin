// Knowlin Lab als eigener Bereich (seit 0.50): Lernwege aller Körper, Gelerntes, Raum aus der Quest.
// Server: /api/lab (routes/lab.py). Lädt, sobald die Seite sichtbar wird.
import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;

function plan(raum) {
  // Grundriss als SVG: Boden und Möbel von oben, Maßstab passt sich an
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  const pad = 0.2, w = raum.breite + 2 * pad, h = raum.tiefe + 2 * pad;
  svg.setAttribute('viewBox', `${-w / 2} ${-h / 2} ${w} ${h}`);
  svg.setAttribute('class', 'lab-plan');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${tr('Grundriss')}: ${raum.breite} × ${raum.tiefe} m, ${raum.moebel.length} ${tr('Möbel')}`);
  const rect = (x, y, rw, rh, cls) => {
    const r = document.createElementNS(ns, 'rect');
    Object.entries({ x: x - rw / 2, y: -y - rh / 2, width: rw, height: rh, class: cls }).forEach(([k, v]) => r.setAttribute(k, v));
    svg.append(r);
  };
  rect(0, 0, raum.breite, raum.tiefe, 'lab-plan-boden');
  for (const m of raum.moebel) rect(m.x, m.y, m.sx, m.sy, 'lab-plan-moebel');
  return svg;
}

export function initLabSeite({ $, api, toast, showView }) {
  const seite = $('view-lab');
  if (!seite) return { laden() {} };
  const fehler = (r) => toast(tr((r && r.fehler) || 'Das ging nicht'), true);

  function zeigen(d) {
    $('lab-wege').replaceChildren(...d.lernwege.map((w) => {
      const li = document.createElement('li');
      li.className = `lab-weg${w.jetzt ? ' lab-weg--jetzt' : ''}`;
      const kopf = document.createElement('div');
      const b = document.createElement('b');
      b.textContent = tr(w.name);
      const p = document.createElement('p');
      p.className = 'field-help';
      p.textContent = tr(w.satz);
      kopf.append(b, p);
      const wer = document.createElement('p');
      wer.className = 'lab-wer';
      wer.textContent = w.koerper.length ? `${tr('Kann')}: ${w.koerper.join(', ')}` : tr('Noch kein Körper');
      li.append(kopf, wer);
      if (w.jetzt) {
        const knopf = document.createElement('button');
        knopf.type = 'button';
        knopf.className = 'btn btn--sm';
        knopf.textContent = tr('Öffnen');
        knopf.setAttribute('aria-label', `${tr(w.name)} ${tr('öffnen')}`);
        knopf.addEventListener('click', () => showView(w.ansicht, w.teil || undefined));
        li.append(knopf);
      }
      return li;
    }));
    $('lab-gelernt').replaceChildren(...(d.gelernt.length ? d.gelernt : [null]).map((z) => {
      const li = document.createElement('li');
      if (!z) { li.className = 'field-help'; li.textContent = tr('Noch nichts gelernt – such dir oben einen Lernweg aus.'); return li; }
      const b = document.createElement('b');
      b.textContent = z.titel;
      li.append(b, document.createTextNode(` · ${z.stand}`));
      return li;
    }));
    const r = d.raum;
    const box = $('lab-raum');
    if (!r) box.replaceChildren(Object.assign(document.createElement('p'), { className: 'field-help', textContent: tr('Noch kein Zimmer gemessen.') }));
    else {
      const t = document.createElement('p');
      t.textContent = `${r.breite.toFixed(1).replace('.', ',')} × ${r.tiefe.toFixed(1).replace('.', ',')} m · ${r.moebel.length} ${tr('Möbel')} · ${r.zeit}${r.aktiv ? ` · ${tr('im Simulator')}` : ''}`;
      box.replaceChildren(plan(r), t);
    }
    $('lab-raum-an').hidden = !r || r.aktiv || !d.kann_raum;
    $('lab-raum-aus').hidden = !r || !r.aktiv || !d.kann_raum;
    $('lab-raum-weg').hidden = !r;
  }

  async function laden() {
    const d = await api('/api/lab').catch(() => null);
    if (d && d.ok) zeigen(d);
  }
  const aktiv = async (an) => {
    const r = await api('/api/lab/raum/aktiv', 'POST', { aktiv: an }).catch((e) => ({ fehler: e.message }));
    if (!r.ok) return fehler(r);
    zeigen(r);
    toast(tr(r.text));
  };
  $('lab-raum-an').addEventListener('click', () => aktiv(true));
  $('lab-raum-aus').addEventListener('click', () => aktiv(false));
  $('lab-raum-weg').addEventListener('click', async () => {
    const r = await api('/api/lab/raum', 'DELETE').catch((e) => ({ fehler: e.message }));
    if (!r.ok) return fehler(r);
    zeigen(r);
  });
  new MutationObserver(() => { if (!seite.hidden) laden(); }).observe(seite, { attributes: true, attributeFilter: ['hidden'] });
  return { laden };
}
