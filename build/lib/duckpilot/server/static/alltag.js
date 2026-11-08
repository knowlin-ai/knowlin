// Seite „Alltag“ und alles, was dazugehört: große Uhr, Ruhe/Aktiv, Timer, Erinnerungen, Termine (auch als
// .ics-Datei), To-dos. Dazu das Alarmband oben (Erledigt / Später) und der Modus-Schalter in der Kopfzeile.
// Alle Texte aus Kalenderdateien und Eingaben landen nur über textContent im Dokument.

const WD = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
const MON = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const REP = { taeglich: 'täglich', werktags: 'werktags', woechentlich: 'wöchentlich' };
const pad = (n) => String(n).padStart(2, '0');

function clock(sec) {
  const s = Math.max(0, Math.round(sec));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${pad(m)}:${pad(r)}` : `${m}:${pad(r)}`;
}
function dayLabel(d, now = new Date()) {
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const b = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((b - a) / 86400000);
  if (diff === 0) return 'Heute';
  if (diff === 1) return 'Morgen';
  if (diff === 2) return 'Übermorgen';
  return `${WD[d.getDay()]}, ${d.getDate()}. ${MON[d.getMonth()]}`;
}
const hm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export function initAlltag(h) {
  const { $, el, api, toast } = h;
  let data = null;
  let ticking = null;
  const visible = () => !$('view-alltag').hidden;

  async function load() {
    const r = await api('/api/alltag').catch(() => null);
    if (r) update(r);
  }

  function update(msg) {
    data = msg;
    // Erweiterung aus: Seite und Schalter verstecken
    $('rail-alltag').hidden = !msg.an;
    $('mode-chip').hidden = !msg.an;
    renderModeChip();
    renderAlarms();
    if (visible()) render();
  }

  // ── Kopfzeile: Aktiv / Ruht ─────────────────────────────────────────
  function renderModeChip() {
    const rest = data && data.optionen && data.optionen.modus === 'ruhe';
    const chip = $('mode-chip');
    chip.classList.toggle('is-rest', rest);
    chip.setAttribute('aria-pressed', rest ? 'true' : 'false');
    $('mode-chip-label').textContent = rest ? 'Ruht' : 'Aktiv';
    chip.title = rest ? 'Ruhemodus: sitzt, Motoren aus, wacht bei Fälligem auf. Klicken weckt sie.'
      : 'Aktiv: macht mit und bewegt sich im Leerlauf. Klicken schickt sie in den Ruhemodus.';
  }
  async function setMode(modus) {
    const r = await api('/api/alltag/optionen', 'POST', { modus }).catch(() => null);
    if (!r || !r.ok) toast(r ? r.fehler : 'Keine Antwort', true);
  }
  $('mode-chip').addEventListener('click', () => setMode(data && data.optionen.modus === 'ruhe' ? 'aktiv' : 'ruhe'));

  // ── Alarmband ───────────────────────────────────────────────────────
  function renderAlarms() {
    const box = $('alarm-bar');
    const list = (data && data.alarme) || [];
    box.hidden = !list.length;
    box.replaceChildren(...list.map((a) => {
      const row = el('div', 'alarm');
      row.dataset.art = a.art;
      const icon = el('span', 'alarm-icon');
      icon.setAttribute('aria-hidden', 'true');
      icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/></svg>';
      const text = el('div', 'alarm-text');
      text.append(el('b', null, { timer: 'Timer', erinnerung: 'Erinnerung', termin: 'Termin' }[a.art] || 'Hinweis'), el('span', null, a.text));
      const done = el('button', 'btn btn--sm btn--primary', 'Erledigt');
      done.type = 'button';
      done.addEventListener('click', () => answer(a.id, false));
      const later = el('button', 'btn btn--sm', '5 Minuten später');
      later.type = 'button';
      later.addEventListener('click', () => answer(a.id, true));
      row.append(icon, text, later, done);
      return row;
    }));
  }
  async function answer(id, snooze) {
    const r = await api(`/api/alltag/alarm/${encodeURIComponent(id)}`, 'POST', snooze ? { schlummern: true, minuten: 5 } : {}).catch(() => null);
    if (r && r.ok && snooze) toast('In 5 Minuten noch einmal');
  }
  function onAlarm(msg) {
    if (!data) return;
    if (!data.alarme.some((a) => a.id === msg.alarm.id)) data.alarme.push(msg.alarm);
    renderAlarms();
  }

  // ── Seite ───────────────────────────────────────────────────────────
  function render() {
    if (!data) return;
    renderClock();
    renderOptions();
    renderTimers();
    renderReminders();
    renderEvents();
    renderTodos();
    if (!ticking) ticking = setInterval(() => { if (visible()) { renderClock(); tickTimers(); } }, 1000);
  }

  function renderClock() {
    const now = new Date();
    $('al-time').textContent = hm(now);
    $('al-sec').textContent = pad(now.getSeconds());
    $('al-date').textContent = `${WD[now.getDay()]}, ${now.getDate()}. ${MON[now.getMonth()]} ${now.getFullYear()}`;
    // was als Nächstes kommt
    const next = [];
    for (const e of data.termine || []) if (!e.ganztags) next.push([new Date(e.start), e.titel]);
    for (const r of data.erinnerungen || []) next.push([new Date(r.faellig), r.text]);
    for (const t of data.timer || []) next.push([new Date(t.ende * 1000), t.name]);
    const up = next.filter(([d]) => d > now).sort((a, b) => a[0] - b[0])[0];
    const line = $('al-next');
    if (!up) { line.textContent = 'Nichts mehr geplant.'; return; }
    const mins = Math.round((up[0] - now) / 60000);
    const rel = mins < 1 ? 'gleich' : mins < 60 ? `in ${mins} min` : `${dayLabel(up[0], now) === 'Heute' ? '' : `${dayLabel(up[0], now)} `}${hm(up[0])}`;
    line.replaceChildren(el('span', null, 'Als Nächstes: '), el('b', null, up[1]), document.createTextNode(` · ${rel}`));
  }

  function renderOptions() {
    const o = data.optionen;
    for (const r of document.querySelectorAll('input[name="al-mode"]')) r.checked = r.value === o.modus;
    $('al-idle').value = String(o.ruhe_nach_min);
    $('al-wake').value = o.wecken;
    $('al-say').checked = !!o.durchsagen;
    $('al-mode-help').textContent = o.modus === 'ruhe'
      ? 'Sie sitzt mit abgeschalteten Motoren und bewegt sich nicht – am Roboter spart das Akku. Ansprechen, Steuern oder etwas Fälliges weckt sie.'
      : 'Sie macht mit, schaut sich um und reagiert. Mit „Ruhemodus“ oder dem Schalter oben schickt man sie zur Ruhe.';
  }
  for (const r of document.querySelectorAll('input[name="al-mode"]')) r.addEventListener('change', () => setMode(r.value));
  async function option(patch) {
    const r = await api('/api/alltag/optionen', 'POST', patch).catch(() => null);
    if (!r || !r.ok) toast(r ? r.fehler : 'Keine Antwort', true);
  }
  $('al-idle').addEventListener('change', (e) => option({ ruhe_nach_min: Number(e.target.value) }));
  $('al-wake').addEventListener('change', (e) => option({ wecken: e.target.value }));
  $('al-say').addEventListener('change', (e) => option({ durchsagen: e.target.checked }));

  function row(parts, onDelete, label) {
    const li = el('li', 'al-item');
    for (const p of parts) li.append(p);
    if (onDelete) {
      const x = el('button', 'icon-btn', '×');
      x.type = 'button';
      x.setAttribute('aria-label', `${label} löschen`);
      x.addEventListener('click', onDelete);
      li.append(x);
    }
    return li;
  }
  const del = (art, id) => async () => { await api(`/api/alltag/${art}/${encodeURIComponent(id)}`, 'DELETE').catch(() => {}); };

  function renderTimers() {
    const list = $('al-timers');
    list.replaceChildren(...(data.timer || []).map((t) => {
      const left = el('span', 'al-count');
      left.dataset.ende = t.ende;
      const bar = el('span', 'al-tbar');
      const fill = el('i');
      fill.dataset.ende = t.ende;
      fill.dataset.dauer = t.dauer_s;
      bar.append(fill);
      const name = el('span', 'al-what', t.name);
      return row([left, name, bar], del('timer', t.id), t.name);
    }));
    $('al-timers-empty').hidden = (data.timer || []).length > 0;
    tickTimers();
  }
  function tickTimers() {
    const now = Date.now() / 1000;
    for (const c of document.querySelectorAll('#al-timers .al-count')) c.textContent = clock(Number(c.dataset.ende) - now);
    for (const f of document.querySelectorAll('#al-timers .al-tbar i')) {
      const left = Math.max(0, Number(f.dataset.ende) - now);
      f.style.width = `${Math.max(0, Math.min(100, (left / Number(f.dataset.dauer)) * 100))}%`;
    }
  }
  for (const b of document.querySelectorAll('[data-timer]')) {
    b.addEventListener('click', () => command({ aktion: 'timer', dauer: `${b.dataset.timer} Minuten` }));
  }

  function renderReminders() {
    const list = $('al-reminders');
    list.replaceChildren(...(data.erinnerungen || []).map((r) => {
      const d = new Date(r.faellig);
      const when = el('span', 'al-when', `${dayLabel(d)} ${hm(d)}`);
      const what = el('span', 'al-what', r.text);
      const parts = [when, what];
      if (r.wiederholung) parts.push(el('span', 'chip chip--data al-rep', REP[r.wiederholung]));
      return row(parts, del('erinnerung', r.id), r.text);
    }));
    $('al-reminders-empty').hidden = (data.erinnerungen || []).length > 0;
  }

  function renderEvents() {
    const root = $('al-events');
    root.replaceChildren();
    const evs = (data.termine || []).slice().sort((a, b) => a.start.localeCompare(b.start));
    let lastDay = '';
    let ul = null;
    for (const e of evs) {
      const d = new Date(e.start);
      const day = dayLabel(d);
      if (day !== lastDay) {
        root.append(el('h4', 'al-day', day));
        ul = el('ul', 'al-list');
        root.append(ul);
        lastDay = day;
      }
      const when = el('span', 'al-when', e.ganztags ? 'ganztags' : `${hm(d)}${e.ende ? `–${hm(new Date(e.ende))}` : ''}`);
      const what = el('span', 'al-what', e.titel);
      const parts = [when, what];
      if (e.ort) parts.push(el('span', 'al-place', e.ort));
      if (e.quelle === 'ics') parts.push(el('span', 'chip al-rep', 'Kalender'));
      ul.append(row(parts, del('termin', e.id), e.titel));
    }
    $('al-events-empty').hidden = evs.length > 0;
  }

  function renderTodos() {
    const list = $('al-todos');
    const todos = (data.todos || []).slice().sort((a, b) => Number(a.erledigt) - Number(b.erledigt));
    list.replaceChildren(...todos.map((t) => {
      const lab = el('label', `al-todo${t.erledigt ? ' is-done' : ''}`);
      const cb = el('input');
      cb.type = 'checkbox';
      cb.checked = t.erledigt;
      cb.addEventListener('change', () => api(`/api/alltag/todo/${encodeURIComponent(t.id)}`, 'POST', { erledigt: cb.checked }));
      lab.append(cb, el('span', null, t.text));
      return row([lab], del('todo', t.id), t.text);
    }));
    $('al-todos-empty').hidden = todos.length > 0;
    $('al-todos-clear').hidden = !todos.some((t) => t.erledigt);
  }
  $('al-todos-clear').addEventListener('click', () => api('/api/alltag/todos/aufraeumen', 'POST'));

  // ── Formulare ───────────────────────────────────────────────────────
  async function command(args, msgEl = null, form = null) {
    const r = await api('/api/alltag/befehl', 'POST', args).catch(() => ({ ok: false, fehler: 'Keine Antwort' }));
    if (msgEl) { msgEl.textContent = r.ok ? '' : r.fehler; msgEl.className = `field-msg${r.ok ? '' : ' bad'}`; }
    if (r.ok) { toast(r.antwort || 'Gespeichert'); if (form) form.reset(); }
    else if (!msgEl) toast(r.fehler, true);
    return r;
  }
  $('al-timer-form').addEventListener('submit', (e) => {
    e.preventDefault();
    command({ aktion: 'timer', dauer: $('al-timer-dur').value, text: $('al-timer-name').value }, $('al-timer-msg'), e.target);
  });
  $('al-rem-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const rep = $('al-rem-rep').value;
    command({ aktion: 'erinnerung', text: $('al-rem-text').value, wann: $('al-rem-when').value, ...(rep ? { wiederholung: rep } : {}) },
      $('al-rem-msg'), e.target);
  });
  $('al-ev-form').addEventListener('submit', (e) => {
    e.preventDefault();
    command({ aktion: 'termin', text: $('al-ev-title').value, wann: $('al-ev-when').value, ort: $('al-ev-place').value,
      minuten_vorher: Number($('al-ev-lead').value) }, $('al-ev-msg'), e.target);
  });
  $('al-todo-form').addEventListener('submit', (e) => {
    e.preventDefault();
    command({ aktion: 'todo', text: $('al-todo-text').value }, $('al-todo-msg'), e.target);
  });
  $('al-ics').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 2_000_000) { toast('Datei zu groß (höchstens 2 MB)', true); return; }
    const text = await file.text();
    const res = await fetch('/api/alltag/ics', { method: 'POST', headers: { 'Content-Type': 'text/calendar' }, body: text })
      .then((r) => r.json()).catch(() => ({ ok: false, fehler: 'Keine Antwort' }));
    if (!res.ok) { toast(res.fehler, true); return; }
    const notes = [];
    if (res.serien) notes.push(`${res.serien} Serie${res.serien === 1 ? '' : 'n'} aufgelöst`);
    if (res.nicht_aufgeloest) notes.push(`${res.nicht_aufgeloest} komplizierte Serie${res.nicht_aufgeloest === 1 ? '' : 'n'} nur mit dem ersten Termin`);
    toast(`${res.importiert} Termin${res.importiert === 1 ? '' : 'e'} übernommen${notes.length ? ` – ${notes.join(', ')}` : ''}`);
  });

  return { load, update, onAlarm, render };
}
