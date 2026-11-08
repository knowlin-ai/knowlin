// Gedächtnis-Seite: Tricks, Orte, Vorlieben, Wissen und Protokoll – mit Vorführen, Hingehen und Vergessen
// (seit 0.38.17 aus app.js ausgelagert)
import { el } from './ui.js';
import { eventItem } from './dashboard.js';
import { uebersetzeText } from './i18n.js';
import { herkunftName } from './herkunft.js';
import { initWelt } from './welt.js';

export function initGedaechtnis({ $, api, send, showView, toast, scene, map, addLine, num }) {
  let daten = null;                       // letzte Nachricht „memory“ (auch fürs Dashboard)
  const welt = initWelt({ $, api });      // „Was Knowlin über deine Welt weiß“ (G1, 0.38.27)

  function memRow(title, detail, buttons) {
    const li = el('li');
    const txt = el('div', 'mem-text');
    txt.append(el('span', 'mem-name', title));
    if (detail) txt.append(el('span', 'mem-detail', detail));
    li.append(txt);
    const acts = el('div', 'mem-acts');
    for (const [label, fn, cls] of buttons) {
      const b = el('button', `btn btn--sm${cls === 'btn-go' ? ' btn--primary' : ''}`, label);
      b.type = 'button';
      b.addEventListener('click', fn);
      acts.append(b);
    }
    li.append(acts);
    return li;
  }

  function fillSection(id, rows) {
    const sec = $(id);
    sec.querySelector('ul, ol').replaceChildren(...rows);
    sec.hidden = rows.length === 0;
    return rows.length;
  }

  const forget = (kind, name) => send({ type: 'memory_forget', kind, name });

  function onMemory(msg) {
    // Der Reiter bleibt immer da: ausgeschaltet zeigt die Seite nur den Schalter
    $('mem-body').hidden = !msg.enabled;
    if (!msg.enabled) {
      scene.setPlaces([]);
      map.setPlaces([]);
      return;
    }
    daten = msg;
    const d = msg.data;
    const tricks = Object.entries(d.tricks);
    const places = Object.entries(d.orte);
    const here = places.filter(([, p]) => p.koerper === msg.body).map(([name, p]) => ({ name, x: p.x, y: p.y }));
    scene.setPlaces(here);
    map.setPlaces(here);
    const facts = d.wissen || [];
    const n = tricks.length + places.length + d.vorlieben.length + facts.length;
    $('memory-count').hidden = !n;
    $('memory-count').textContent = n;
    let total = 0;
    total += fillSection('mem-tricks', tricks.map(([name, t]) => memRow(
      name,
      [t.beschreibung, t.benutzt ? `${t.benutzt}× vorgeführt` : 'noch nie vorgeführt',
        t.version > 1 ? `Fassung ${t.version}` : '', t.gut ? `${t.gut}× gelobt` : '', t.schlecht ? `${t.schlecht}× verbessert gewünscht` : '',
        (t.notizen || []).slice(-1)[0] || ''].filter(Boolean).join(', '),
      [['Vorführen', () => { send({ type: 'memory_run', kind: 'trick', name }); showView('cockpit'); }, 'btn-go'], ['Vergessen', () => forget('trick', name)]],
    )));
    total += fillSection('mem-places', places.map(([name, p]) => {
      const mine = p.koerper === msg.body;
      const detail = mine ? `x ${num(p.x)} m, y ${num(p.y)} m${p.notiz ? ', ' + p.notiz : ''}`
        : `gilt nur für ${p.koerper === 'sim' ? 'den Simulator' : 'den echten Roboter'}`;
      const buttons = mine ? [['Hingehen', () => { send({ type: 'memory_run', kind: 'ort', name }); showView('cockpit'); }, 'btn-go']] : [];
      buttons.push(['Vergessen', () => forget('ort', name)]);
      return memRow(name, detail, buttons);
    }));
    const von = (x) => (x.von ? `${uebersetzeText('gemerkt von') || 'gemerkt von'} ${herkunftName(x.von, msg.herkuenfte)}` : null);   // 0.38.10
    total += fillSection('mem-prefs', d.vorlieben.map((p) => memRow(p.text, von(p), [['Vergessen', () => forget('vorliebe', p.id)]])));
    total += fillSection('mem-facts', facts.map((f) => memRow(f.text, von(f), [['Vergessen', () => forget('wissen', f.id)]])));
    const logRows = d.protokoll.slice(-12).reverse().map((e) => {
      const kind = { Sturz: 'fall', Abgelehnt: 'reflex', 'Nicht geschafft': 'kick_miss' }[e.art] || 'kick_miss';
      const li = eventItem({ type: kind, message: `${e.text}${e.anzahl > 1 ? ` (${e.anzahl}×)` : ''}`, t: Date.parse(e.zeit) / 1000 });
      li.querySelector('.lvl').textContent = e.art;
      return li;
    });
    fillSection('mem-log', logRows);
    $('memory-empty').hidden = total + logRows.length > 0;
    $('memory-path').textContent = `Gespeichert in ${msg.path}`;
    if (msg.error) addLine('err', msg.error);
  }

  $('mem-log-clear').addEventListener('click', () => forget('protokoll'));
  let clearArmed = null;
  $('mem-clear').addEventListener('click', (e) => {
    const b = e.currentTarget;
    if (!clearArmed) {
      b.textContent = 'Wirklich alles vergessen? Nochmal klicken (vorher wird gesichert)';
      b.classList.add('armed');
      clearArmed = setTimeout(() => { clearArmed = null; b.textContent = 'Alles vergessen'; b.classList.remove('armed'); }, 4000);
      return;
    }
    clearTimeout(clearArmed);
    clearArmed = null;
    b.textContent = 'Alles vergessen';
    b.classList.remove('armed');
    send({ type: 'memory_clear' });
  });
  document.querySelectorAll('[data-open-folder]').forEach((b) => b.addEventListener('click', async () => {
    const r = await api('/api/open-folder', 'POST', { which: b.dataset.openFolder });
    if (!r.ok) toast(r.fehler || 'Ordner ließ sich nicht öffnen');
  }));

  return { onMemory, welt, get daten() { return daten; } };
}
