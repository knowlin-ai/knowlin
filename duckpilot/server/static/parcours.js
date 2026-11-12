// Seite „Parcours“: Auftrag Schritt für Schritt, Parcours bauen (Vorlage oder Claude), Policies darauf
// testen, Ergebnisse vergleichen und Versuch 1 als 3D-Wiederholung ansehen.
import { Scene3D } from './duck3d.js';

const STAND = [0, -0.0873, -0.4579, -0.0049, 0.4530, 0.3491, 0.3491, 0, 0, 0, 0, 0.0873, 0.4579, 0.0049, -0.4530];
const RESULT = {
  geschafft: ['good', 'geschafft'], gestürzt: ['bad', 'gestürzt'], 'steckt fest': ['warn', 'steckt fest'],
  'Stange ausgelassen': ['warn', 'Stange ausgelassen'], 'zu langsam': ['warn', 'zu langsam'],
  'nicht erreicht': ['none', 'nicht erreicht'],
};
const STEP_ICON = { fertig: '✓', jetzt: '●', 'läuft': '◐', offen: '○', fehler: '!', 'nicht nötig': '–' };
const num = (v, d = 1) => Number(v).toFixed(d).replace('.', ',');

export function initParcours(h) {
  let wanted = null;            // vorgewählte Policy (pickSource)
  const { $, el, api, toast } = h;
  let data = null;
  let scene = null;
  let worldKey = '';
  let replay = null;          // { bilder, hz, test, falls }
  let playing = false;
  let t = 0;
  let speed = 1;
  let last = 0;
  let pulsed = new Set();
  let asked = false;
  let autoOpened = null;      // zuletzt von selbst geöffneter Test (nach „Testen“)
  let opening = null;         // Test, dessen Aufzeichnung gerade lädt
  let firstRender = true;
  const visible = () => !$('view-parcours').hidden;

  async function load() {
    data = await api('/api/parcours').catch(() => null);
    render();
    if (scene) scene.paused = false;
  }
  function update(msg) { data = msg; if (visible()) render(); }
  function hide() { if (scene) scene.paused = true; playing = false; }

  // Antwort von Claude auf „An Claude“ hier mit anzeigen
  function onChat(m) {
    if (!asked || m.role === 'user') return;
    asked = false;
    const p = $('pc-reply');
    p.hidden = false;
    p.textContent = m.text || '';
    $('pc-ask-hint').textContent = '';
    $('pc-ask-go').disabled = false;
  }

  // ── Darstellung ─────────────────────────────────────────────────────
  function render() {
    if (!data) return;
    const off = $('pc-off');
    off.hidden = data.verfuegbar;
    if (!data.verfuegbar) {
      const go = el('button', 'link', 'Echte Physik einschalten');
      go.type = 'button';
      go.addEventListener('click', () => h.showView('settings', 'koerper'));
      off.replaceChildren(document.createTextNode(`Der Parcours braucht die echte Physik: ${data.problem || 'nicht bereit'}. `), go);
    }
    renderMission();
    renderCourse();
    renderTest();
    renderResults();
    ensureScene();
    const key = JSON.stringify(data.welt || null);
    if (scene && key !== worldKey) {
      worldKey = key;
      scene.setWorld(data.welt || null);
      clearReplay();
      standAtStart();
    }
    // neuer Test fertig → einmal von selbst abspielen; sonst die neueste Aufzeichnung bereitlegen
    const job = data.job || {};
    if (firstRender) { firstRender = false; autoOpened = job.test || null; }   // beim Öffnen der Seite nicht von selbst abspielen
    const fresh = job.test && job.test !== autoOpened ? (data.tests || []).find((x) => x.id === job.test) : null;
    if (fresh && fresh.wiederholung) {
      autoOpened = job.test;
      openReplay(fresh);
    } else if (!replay && !opening) {
      const test = (data.tests || []).find((x) => x.wiederholung);
      if (test) openReplay(test, false);
    }
  }

  function renderMission() {
    const a = data.auftrag;
    $('pc-goal').textContent = a ? a.ziel : 'Noch kein Auftrag – wähl eine Vorlage oder beschreib Knowlin, was die Ente schaffen soll.';
    const hist = $('pc-history');
    hist.replaceChildren(...(data.verlauf || []).map((m) => {
      const o = new Option(`${m.erstellt} – ${m.ziel}`, m.id);
      o.selected = a && a.id === m.id;
      return o;
    }));
    hist.hidden = (data.verlauf || []).length < 2;
    const ol = $('pc-steps');
    ol.replaceChildren(...(data.schritte || []).map((s, i) => {
      const li = el('li', `pc-step is-${s.stand.replace(/\s/g, '-').replace('ä', 'ae')}`);
      if (s.stand === 'jetzt') li.setAttribute('aria-current', 'step');
      // Reihenfolge zählt: Nummer, außer der Schritt ist fertig, läuft oder hakt
      li.append(el('span', 'pc-step-mark', ['fertig', 'läuft', 'fehler', 'nicht nötig'].includes(s.stand) ? STEP_ICON[s.stand] : String(i + 1)));
      const body = el('div', 'pc-step-body');
      body.append(el('b', null, s.titel), el('span', null, s.text || ''));
      if (s.id === 'training' && s.stand === 'jetzt') {
        const go = el('button', 'btn btn--sm btn--primary', 'Jetzt lernen');
        go.type = 'button';
        go.addEventListener('click', () => $('pc-learn').click());
        body.append(go);
      }
      if (s.id === 'bewertung' && s.stand === 'fertig') body.append(el('span', `pc-verdict ${s.besser ? 'is-good' : 'is-flat'}`, s.besser ? 'besser als vorher' : 'nicht besser'));
      li.append(body);
      return li;
    }));
  }

  function renderCourse() {
    const p = data.parcours;
    $('pc-course-name').textContent = p ? p.name : 'Parcours';
    $('pc-course-len').textContent = p ? `${num(p.laenge_m, 1)} m · ${p.elemente.length} Elemente` : '';
    const list = $('pc-elements');
    if (!p) list.replaceChildren(el('li', 'empty', 'Noch kein Parcours.'));
    else {
      list.replaceChildren(...p.elemente.map((e) => {
        const li = el('li', 'pc-el');
        li.append(el('span', `pc-el-nr pc-el--${e.art}`, String(e.nr)));
        const txt = el('div', 'pc-el-text');
        txt.append(el('b', null, e.titel), el('span', null, e.kurz));
        if (e.warnung) txt.append(el('span', 'pc-el-warn', e.warnung));
        li.append(txt);
        return li;
      }));
    }
    const ask = $('pc-ask-go');
    if (!asked) {
      ask.disabled = !data.claude || !data.verfuegbar;
      $('pc-ask-hint').textContent = data.claude ? '' : 'Dafür braucht es ein Sprachmodell (Claude, lokal oder ein anderes) – sonst eine Vorlage nehmen.';
    }
    const pre = $('pc-presets');
    if (!pre.childElementCount) {
      for (const name of data.vorlagen || []) {
        const c = el('button', 'chip', name);
        c.type = 'button';
        c.addEventListener('click', async () => {
          const r = await api('/api/parcours/bauen', 'POST', { vorlage: name });
          if (!r.ok) toast(r.fehler || 'Ging nicht', true); else toast(`Parcours „${name}“ steht`);
        });
        pre.append(c);
      }
    }
  }

  function renderTest() {
    const sel = $('pc-source');
    const keep = wanted || sel.value;
    sel.replaceChildren(...(data.quellen || []).map((q) => new Option(q.name, q.id)));
    if (keep && [...sel.options].some((o) => o.value === keep)) { sel.value = keep; wanted = null; }
    const job = data.job || {};
    const run = $('pc-run');
    run.disabled = !data.verfuegbar || !data.parcours || !!job.laeuft || !sel.options.length;
    // Nach einem Test, den sie nicht ganz schafft, ist Lernen der nächste Schritt – dann ist das der Hauptknopf
    const last = (data.tests || [])[0];
    const learnNext = !!(last && data.parcours && last.im_ziel < last.versuche);
    run.textContent = job.laeuft ? 'Testet …' : last ? 'Nochmal testen' : 'Testen';
    run.className = `btn ${learnNext ? 'btn--ghost' : 'btn--primary'}`;
    const learn = $('pc-learn');
    learn.className = `btn ${learnNext ? 'btn--primary' : 'btn--ghost'}`;
    learn.textContent = learnNext ? `Jetzt lernen – ${last.im_ziel} von ${last.versuche} reicht noch nicht` : 'Lernen, bis sie es kann';
    learn.disabled = !data.parcours || !!job.laeuft;
    $('pc-cancel').hidden = !job.laeuft;
    const js = $('pc-job');
    js.className = `job-state${job.fehler ? ' is-bad' : ''}`;
    js.textContent = job.fehler ? `Hat nicht geklappt: ${job.fehler}` : (job.text || '');
    const bar = document.querySelector('.pc-test .bar');
    if (job.laeuft && !bar) js.after(el('div', 'bar is-busy'));
    if (!job.laeuft && bar) bar.remove();
  }

  function renderResults() {
    const box = $('pc-results');
    const tests = (data.tests || []).slice(0, 4);
    const p = data.parcours;
    if (!tests.length || !p) { box.replaceChildren(el('div', 'empty', p ? 'Noch kein Test – oben auf „Testen“ klicken.' : 'Noch kein Test.')); return; }
    const table = el('table', 'pc-table');
    const head = el('tr');
    head.append(el('th', null, 'Element'));
    for (const tst of tests) {
      const th = el('th');
      const name = tst.quelle === 'standard' ? 'Pollens Geh-Policy' : tst.policy;
      th.append(el('b', null, name), el('span', null, `${tst.zeit}${tst.auto ? ' · automatisch' : ''}`));
      const verdict = el('span', `pc-score is-${tst.im_ziel === tst.versuche ? 'good' : tst.im_ziel ? 'warn' : 'bad'}`,
        `${tst.im_ziel} von ${tst.versuche} Durchgängen im Ziel`);
      th.append(verdict);
      if (tst.wiederholung) {
        const b = el('button', 'btn btn--sm btn--ghost', replay && replay.test.id === tst.id ? 'Wird oben gezeigt' : 'Ansehen');
        b.type = 'button';
        b.addEventListener('click', () => openReplay(tst));
        th.append(b);
      }
      head.append(th);
    }
    const thead = el('thead');
    thead.append(head);
    const tbody = el('tbody');
    p.elemente.forEach((e, i) => {
      const tr = el('tr');
      const th = el('th');
      th.append(el('b', null, `${e.nr}. ${e.titel}`), el('span', null, e.kurz));
      tr.append(th);
      for (const tst of tests) {
        const r = (tst.elemente || [])[i];
        const td = el('td');
        if (!r) { td.textContent = '–'; tr.append(td); continue; }
        const segs = el('span', 'pc-segs');
        segs.setAttribute('role', 'img');
        segs.setAttribute('aria-label', r.ergebnisse.map((x, k) => `Durchgang ${k + 1}: ${x}`).join(', '));
        r.ergebnisse.forEach((x, k) => {
          const [tone, label] = RESULT[x] || ['none', x];
          const s = el('i', `is-${tone}`);
          s.title = `Durchgang ${k + 1}: ${label}`;
          segs.append(s);
        });
        td.append(segs, el('span', 'pc-count', `${r.geschafft}/${r.von}`));
        const worst = r.ergebnisse.find((x) => x !== 'geschafft');
        if (worst) td.append(el('span', 'pc-why', (RESULT[worst] || [0, worst])[1]));
        tr.append(td);
      }
      tbody.append(tr);
    });
    const foot = el('tr', 'pc-foot');
    foot.append(el('th', null, 'Stürze · Zeit Durchgang 1'));
    for (const tst of tests) foot.append(el('td', null, `${tst.stuerze} · ${num((tst.zeit_s || [0])[0], 1)} s`));
    tbody.append(foot);
    table.append(thead, tbody);
    const hints = tests[0].hinweise || [];
    box.replaceChildren(table, ...hints.map((x) => el('p', 'field-help pc-hint', x)));
  }

  // ── 3D-Wiederholung ──────────────────────────────────────────────────
  function ensureScene() {
    if (scene) return;
    scene = new Scene3D($('pc-canvas'));
    scene.showSensor = false;
    scene.showTrail = true;
    requestAnimationFrame(tick);
  }

  function standAtStart() {
    const w = data && data.welt;
    const x = w && w.bahn ? w.bahn.von : 0;
    scene.update({ x, y: 0, yaw: 0, body: [0.115, 0, 0], display_joints: STAND, connected: false, pose: { z: 0, roll: 0, pitch: 0 } }, null);
  }

  function clearReplay() {
    replay = null;
    playing = false;
    t = 0;
    if (scene) scene.clearTrail();
    $('pc-stage-empty').hidden = false;
    $('pc-replay-label').textContent = 'noch kein Durchgang';
    $('pc-play').disabled = true;
    $('pc-time').disabled = true;
    $('pc-time').value = '0';
    $('pc-clock').textContent = '0,0 s';
    setPlayIcon();
  }

  async function openReplay(test, autoplay = true) {
    opening = test.id;
    const r = await api(`/api/parcours/wiederholung/${encodeURIComponent(test.id)}`).catch(() => null);
    if (opening !== test.id) return;          // inzwischen etwas anderes gewählt
    opening = null;
    if (!r || !r.ok || !r.bilder.length) return;
    if (!(data.tests || []).some((x) => x.id === test.id)) return;   // gehört nicht mehr zum Auftrag
    replay = { bilder: r.bilder, hz: r.hz || 20, test, falls: (test.sturzstellen || []).filter((f) => f.versuch === 1) };
    t = 0;
    pulsed = new Set();
    scene.clearTrail();
    $('pc-stage-empty').hidden = true;
    const name = test.quelle === 'standard' ? 'Pollens Geh-Policy' : test.policy;
    const end = (test.ende || [])[0] || '';
    $('pc-replay-label').textContent = `Durchgang 1 von ${test.versuche || 1} · ${name} · ${end}`;
    $('pc-play').disabled = false;
    $('pc-time').disabled = false;
    playing = autoplay;
    setPlayIcon();
    show();
    renderResults();
  }

  function duration() { return replay ? replay.bilder[replay.bilder.length - 1][0] : 0; }

  function stateAt(time) {
    const b = replay.bilder;
    // Bild über die Zeitstempel suchen (nicht über die Bildrate)
    let lo = 0, hi = b.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (b[mid][0] <= time) lo = mid; else hi = mid - 1; }
    const i = Math.max(0, Math.min(b.length - 2, lo));
    const a = b[i], c = b[Math.min(b.length - 1, i + 1)];
    const k = c[0] > a[0] ? Math.max(0, Math.min(1, (time - a[0]) / (c[0] - a[0]))) : 0;
    const lerp = (j) => a[j] + (c[j] - a[j]) * k;
    let dyaw = c[3] - a[3];
    if (dyaw > Math.PI) dyaw -= 2 * Math.PI; else if (dyaw < -Math.PI) dyaw += 2 * Math.PI;
    const joints = [];
    for (let j = 7; j < 22; j++) joints.push(lerp(j));
    return { x: lerp(1), y: lerp(2), yaw: a[3] + dyaw * k, body: [lerp(4), lerp(5), lerp(6)], display_joints: joints,
      connected: true, pose: { z: 0, roll: 0, pitch: 0 } };
  }

  function show() {
    if (!replay) return;
    scene.update(stateAt(t), null);
    const d = duration();
    $('pc-time').value = String(Math.round((t / (d || 1)) * 1000));
    $('pc-clock').textContent = `${num(t, 1)} s`;
    for (const f of replay.falls) {
      if (t >= f.t && !pulsed.has(f.t)) { pulsed.add(f.t); scene.pulse('fall', f.x, f.y); }
    }
  }

  function tick(now) {
    const dt = last ? Math.min(0.1, (now - last) / 1000) : 0;
    last = now;
    if (replay && playing && visible()) {
      t += dt * speed;
      if (t >= duration()) { t = duration(); playing = false; setPlayIcon(); }
      show();
    }
    requestAnimationFrame(tick);
  }

  function setPlayIcon() {
    const b = $('pc-play');
    b.classList.toggle('is-playing', playing);
    b.setAttribute('aria-label', playing ? 'Anhalten' : 'Abspielen');
  }

  // ── Bedienung ────────────────────────────────────────────────────────
  $('pc-play').addEventListener('click', () => {
    if (!replay) return;
    if (!playing && t >= duration()) { t = 0; pulsed = new Set(); scene.clearTrail(); }
    playing = !playing;
    setPlayIcon();
  });
  $('pc-time').addEventListener('input', (e) => {
    if (!replay) return;
    const nt = (Number(e.target.value) / 1000) * duration();
    if (nt < t) { scene.clearTrail(); pulsed = new Set(); }
    t = nt;
    show();
  });
  for (const r of document.querySelectorAll('input[name="pc-speed"]')) r.addEventListener('change', () => { speed = Number(r.value); });
  $('pc-run').addEventListener('click', async () => {
    const n = Number((document.querySelector('input[name="pc-n"]:checked') || {}).value || 3);
    $('pc-run').disabled = true;
    const r = await api('/api/parcours/testen', 'POST', { quelle: $('pc-source').value, versuche: n });
    if (!r.ok) { toast(r.fehler || 'Ging nicht', true); $('pc-run').disabled = false; }
  });
  $('pc-cancel').addEventListener('click', () => api('/api/parcours/abbrechen', 'POST'));
  $('pc-new').addEventListener('click', async () => {
    clearReplay();
    await api('/api/parcours/auftrag', 'POST', { ziel: '' });
    $('pc-ask').focus();
  });
  $('pc-history').addEventListener('change', async (e) => {
    clearReplay();
    await api('/api/parcours/auftrag', 'POST', { id: e.target.value });
  });
  $('pc-ask-go').addEventListener('click', () => {
    const text = $('pc-ask').value.trim();
    if (text.length < 8) { toast('Beschreib kurz, was die Ente schaffen soll', true); return; }
    asked = true;
    $('pc-ask-go').disabled = true;
    $('pc-ask-hint').textContent = 'Knowlin baut den Parcours und testet ihn …';
    $('pc-reply').hidden = true;
    h.sendChat(`Neuer Auftrag für den Parcours: ${text} Bau dafür mit parcours_bauen einen passenden Parcours (Ziel in einem Satz) und teste ihn mit parcours_testen.`);
    setTimeout(() => { if (asked) { asked = false; $('pc-ask-go').disabled = false; $('pc-ask-hint').textContent = ''; } }, 180000);
  });

  // von außen eine Policy vorwählen (z. B. ein am PC gelerntes Ergebnis)
  function pickSource(id) {
    wanted = id;
    if (data) renderTest();
  }

  return { load, update, onChat, hide, pickSource };
}
