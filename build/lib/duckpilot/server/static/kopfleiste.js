// Kopfleiste: Persönlichkeits-Regler (schnell und in den Einstellungen), kleine Aufklappmenüs und die
// Hintergrund-Aufgaben an einer Stelle (seit 0.38.17 aus app.js ausgelagert)
import { el } from './ui.js';
import { PersonalityPad, personaName } from './personality.js';

export function initKopfleiste({ $, api, toast, send, showView, getConfig, getView, einst }) {
  // Persönlichkeit (X/Y-Regler)
  async function commitPersona(values) {
    const config = getConfig();
    const wasGoofy = !!config.goofy;
    const r = await api('/api/settings', 'POST', values);
    if (!r.ok) { toast(r.fehler || 'Nicht gespeichert'); return; }
    const goofyNow = values.humor >= 0.5;
    toast(`${personaName(values.energie, values.humor)}${goofyNow && !wasGoofy ? (config.modul === 'reachy_mini' ? ' – verspielt an' : ' – Goofy-Modus an, quak!') : !goofyNow && wasGoofy ? ' – Goofy-Modus aus' : ''}`);
    if (goofyNow && !wasGoofy) send({ type: 'tool', name: 'emote', args: { emotion: 'schuetteln' } });
    if (r.einstellungen) einst.uebernehmen(r.einstellungen, getView() === 'settings' || getView() === 'persoenlichkeit');
  }
  const padQuick = new PersonalityPad($('pad-quick'), { onCommit: commitPersona, compact: true });
  const padSettings = new PersonalityPad($('pad-settings'), { onCommit: commitPersona });
  const pop = $('persona-pop');
  function togglePop(open) {
    pop.hidden = !open;
    $('persona-btn').setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  $('persona-btn').addEventListener('click', (e) => { e.stopPropagation(); togglePop(pop.hidden); });
  $('persona-more').addEventListener('click', () => { togglePop(false); showView('persoenlichkeit'); });
  document.addEventListener('pointerdown', (e) => { if (!pop.hidden && !e.target.closest('.persona')) togglePop(false); });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pop.hidden) togglePop(false); });

  // Kleine Aufklappmenüs (Ansicht im Cockpit, Hintergrund-Aufgaben)
  function bindPop(btnId, popId, wrapSel) {
    const btn = $(btnId), box = $(popId);
    const set = (open) => { box.hidden = !open; btn.setAttribute('aria-expanded', open ? 'true' : 'false'); };
    btn.addEventListener('click', (e) => { e.stopPropagation(); set(box.hidden); });
    document.addEventListener('pointerdown', (e) => { if (!box.hidden && !e.target.closest(wrapSel)) set(false); });
    window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !box.hidden) set(false); });
    return set;
  }
  bindPop('view-menu-btn', 'view-menu', '.view-tools');
  const setTasksPop = bindPop('tasks-btn', 'tasks-pop', '.tasks');

  // Hintergrund-Aufgaben: Installationen, Tests, Training … an einer Stelle
  function renderTasks(list) {
    const box = $('tasks');
    box.hidden = !list.length;
    $('lernen-dot').hidden = !list.some((t) => t.ziel.view === 'training' || t.ziel.view === 'parcours');
    if (!list.length) { setTasksPop(false); return; }
    $('tasks-label').textContent = list.length === 1 ? list[0].titel : `${list.length} Aufgaben laufen`;
    $('tasks-list').replaceChildren(...list.map((t) => {
      const li = el('li');
      const b = el('button', 'tasks-item');
      b.type = 'button';
      b.append(el('b', null, t.titel), el('span', null, t.text || ''));
      if (t.anteil != null) {
        const bar = el('span', 'bar');
        const i = el('i');
        i.style.width = `${Math.round(t.anteil * 100)}%`;
        bar.append(i);
        b.append(bar);
      }
      b.addEventListener('click', () => { setTasksPop(false); showView(t.ziel.view, t.ziel.part || undefined); });
      li.append(b);
      return li;
    }));
  }

  return { renderTasks, padQuick, padSettings };
}
