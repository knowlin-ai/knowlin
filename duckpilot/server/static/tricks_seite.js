// Seite „Tricks“: Gefühle zum Abspielen (Pollens, eigene, Charakter) und Tricks vom Hugging Face Hub
// (seit 0.38.17 aus app.js ausgelagert)
import { setIdleRepertoire } from './personality.js';
import { vorschauKachel } from './skills.js';

export function initTricksSeite({ $, api, el, toast, send, showView, getConfig, skillPacks, reachy }) {
  const PLAY_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.5v9l7-4.5z"/></svg>';
  const EMO_DE = {
    freude: 'Freude', traurig: 'traurig', neugierig: 'neugierig', ueberrascht: 'überrascht', muede: 'müde', wuetend: 'wütend',
    ja: 'ja', nein: 'nein', begruessen: 'begrüßen', begeistert: 'begeistert', frustriert: 'frustriert', erleichtert: 'erleichtert',
    stolz: 'stolz', einfuehlsam: 'einfühlsam', schuetteln: 'schütteln', trotzig: 'trotzig', stolpern: 'stolpern', verlegen: 'verlegen',
    staunen: 'staunen', betruebt: 'betrübt', am_boden: 'am Boden', was_was: 'Was? Was?', hmm: 'Hmm?', jawohl: 'jawohl', jep: 'jep',
    noe: 'nö', wer_sagt_das: 'Wer sagt das?', grummelig: 'grummelig', naeaeae: 'Nänänä', aufgeregt: 'aufgeregt',
    ungeduldig: 'ungeduldig', lachen: 'lachen', tot_stellen: 'tot stellen',
    gaehnen: 'gähnen', doesen: 'dösen', seufzen: 'seufzen', himmel_gucken: 'Himmel gucken', gefieder_putzen: 'Gefieder putzen',
    wippen: 'wippen', aufhorchen: 'aufhorchen', umherspaehen: 'umherspähen', traellern: 'trällern', hibbeln: 'hibbeln',
    mustern: 'mustern', haltung: 'Haltung annehmen', nicken: 'nicken', niesen: 'niesen', schluckauf: 'Schluckauf',
    erschrecken: 'erschrecken',
  };
  let emotionCatalog = null;
  async function catalog() {
    if (!emotionCatalog) {
      emotionCatalog = api('/api/emotions').catch(() => { emotionCatalog = null; return []; });
    }
    return emotionCatalog;
  }
  catalog().then(setIdleRepertoire);   // Leerlauf-Gesten kennen den Katalog
  $('tricks-zu-erweiterungen')?.addEventListener('click', () => showView('tricks', 'pakete'));
  let emotionsLoaded = false;
  async function loadTricks(p = 'tricks') {
    if (!emotionsLoaded) {
      emotionsLoaded = true;
      const list = await catalog();
      const mk = (e) => {
        const b = el('button', 'emo');
        b.type = 'button';
        const t = el('b', null, EMO_DE[e.name] || e.name);
        t.insertAdjacentHTML('beforeend', PLAY_ICON);
        const who = e.art === 'charakter' && e.bei && e.bei.length ? ` – ${e.bei.join(', ')}` : '';
        b.append(t, el('span', null, (e.text || `${String(e.dauer).replace('.', ',')} s`) + who));
        b.addEventListener('click', () => {
          send({ type: 'tool', name: 'emote', args: { emotion: e.name } });
          b.classList.add('playing');
          setTimeout(() => b.classList.remove('playing'), Math.max(800, e.dauer * 1000));
          // Mit Vorschau daneben bleibt die Seite stehen; nur ohne (schmales Fenster, Vorschau verdeckt) ins Cockpit
          const vs = $('tricks-vorschau');
          if (vs && vs.querySelector('canvas') && vs.getBoundingClientRect().bottom > 0) return;
          toast(`${EMO_DE[e.name] || e.name} – in der 3D-Ansicht`);
          showView('cockpit');
        });
        return b;
      };
      $('emo-pollen').replaceChildren(...list.filter((e) => e.pollen).map(mk));
      $('emo-own').replaceChildren(...list.filter((e) => e.art === 'eigen').map(mk));
      $('emo-idle').replaceChildren(...list.filter((e) => e.art === 'charakter').map(mk));
    }
    skillPacks().refresh();
    if (getConfig().modul === 'reachy_mini') reachy().laden();
    if (p === 'hub' && !$('hub-list').children.length) searchHub();
  }

  let hubData = null;
  async function searchHub() {
    const q = $('hub-q').value.trim() || 'microduck';
    const list = $('hub-list');
    list.replaceChildren(el('div', 'empty', 'Frage den Hub …'));
    try {
      hubData = await api(`/api/tricks?q=${encodeURIComponent(q)}`);
    } catch {
      hubData = { ok: false, fehler: 'Knowlin antwortet nicht', tricks: [], vorgemerkt: [] };
    }
    renderHub();
  }
  $('hub-form').addEventListener('submit', (e) => { e.preventDefault(); searchHub(); });

  function renderHub() {
    const list = $('hub-list');
    const d = hubData;
    const robot = d.koerper === 'robotd' || d.koerper === 'physik';
    const saved = new Set(d.vorgemerkt || []);
    const cards = [];
    const known = new Set((d.tricks || []).map((t) => t.repo));
    // Vorgemerkte zuerst, auch wenn der Hub gerade nicht erreichbar ist
    for (const repo of saved) if (!known.has(repo)) cards.push(trickCard({ repo, name: repo.split('/')[1].replace(/^microduck[-_]/, ''), herkunft: repo.startsWith('pollen-robotics/') ? 'offiziell' : 'community', geht: true }, robot, true, d.skills || []));
    for (const t of d.tricks || []) cards.push(trickCard(t, robot, saved.has(t.repo), d.skills || []));
    if (!d.ok) {
      // Klartext zuerst, die technische Meldung nur zum Aufklappen
      const box = el('div', 'empty');
      box.append(el('p', null, 'Der Hugging Face Hub ist gerade nicht erreichbar. Vorgemerkte Tricks stehen trotzdem hier.'));
      if (d.fehler) {
        const det = el('details', 'explain');
        det.append(el('summary', null, 'Technische Details'), el('p', null, d.fehler));
        box.append(det);
      }
      cards.unshift(box);
    } else if (!d.tricks.length) {
      cards.unshift(el('div', 'empty', 'Nichts gefunden. Probier „microduck“ oder den Namen eines Autors.'));
    }
    list.replaceChildren(...cards);
  }

  function trickCard(t, robot, isSaved, skills) {
    const card = el('article', `card trick${isSaved ? ' saved' : ''}`);
    const top = el('div', 'trick-top');
    top.append(el('span', `chip${t.herkunft === 'offiziell' ? ' chip--accent' : ''}`, t.herkunft === 'offiziell' ? 'offiziell' : 'Community'));
    if (isSaved) top.append(el('span', 'chip chip--data', 'vorgemerkt'));
    const loaded = skills.includes(t.name);
    if (loaded) top.append(el('span', 'chip chip--solid-accent', 'auf der Ente'));
    card.append(top);
    if (t.vorschau) card.append(vorschauKachel(t.vorschau, el, t.name || t.repo, card));   // Standbild statt Knopf (0.38.26)
    card.append(el('h4', 'trick-name', t.name || t.repo), el('p', 'trick-repo', t.repo));
    if (t.beschreibung) {
      const p = el('p', 'trick-desc');
      const q = el('q', null, t.beschreibung);
      p.append(q);
      card.append(p);
    }
    const stats = el('div', 'trick-stats');
    if (t.likes != null) stats.append(el('span', null, `${t.likes} Likes`));
    if (t.downloads != null) stats.append(el('span', null, `${t.downloads} Downloads`));
    if (t.dauer) stats.append(el('span', null, `${String(Math.round(t.dauer * 10) / 10).replace('.', ',')} s`));
    if (stats.children.length) card.append(stats);
    if (t.hinweis) card.append(el('p', 'trick-warn', t.hinweis));
    const acts = el('div', 'trick-acts');
    if (loaded) {
      const run = el('button', 'btn btn--accent btn--sm', 'Vorführen');
      run.addEventListener('click', () => { send({ type: 'tool', name: 'skill', args: { name: t.name } }); showView('cockpit'); });
      acts.append(run);
    } else if (t.geht !== false) {
      const add = el('button', `btn btn--sm${robot ? ' btn--primary' : ''}`, robot ? 'Auf die Ente laden' : (isSaved ? 'Vorgemerkt' : 'Vormerken'));
      if (!robot && isSaved) add.disabled = true;
      add.addEventListener('click', async () => {
        add.classList.add('is-busy');
        const r = await api('/api/tricks', 'POST', { repo: t.repo, datei: t.datei || undefined }).catch(() => ({ ok: false, grund: 'keine Antwort' }));
        add.classList.remove('is-busy');
        if (r.ok) toast(`Geladen: ${r.grund}`);
        else if (!robot) toast('Vorgemerkt – läuft, sobald die echte Ente verbunden ist');
        else toast(r.grund || 'Nicht geladen', true);
        hubData.vorgemerkt = [...new Set([...(hubData.vorgemerkt || []), t.repo])];
        if (r.skills) hubData.skills = r.skills;
        renderHub();
      });
      acts.append(add);
    }
    if (t.seite) {
      const a = el('a', 'btn btn--ghost btn--sm', 'Auf dem Hub');
      a.href = t.seite; a.target = '_blank'; a.rel = 'noopener';
      acts.append(a);
    }
    if (isSaved) {
      const f = el('button', 'btn btn--ghost btn--sm', 'Vergessen');
      f.addEventListener('click', async () => {
        await api(`/api/tricks?repo=${encodeURIComponent(t.repo)}`, 'DELETE');
        hubData.vorgemerkt = (hubData.vorgemerkt || []).filter((r) => r !== t.repo);
        renderHub();
      });
      acts.append(f);
    }
    card.append(acts);
    return card;
  }

  return { laden: loadTricks, gefuehlName: (k) => EMO_DE[k] || k.replace(/_/g, ' ') };
}
