// Seite „Training“ (Lernen → Training): drei Wege – dieser PC (kostenlos, lernschleife.js), Kaggle (kostenlos,
// Pollens Original-Training auf einer geschenkten NVIDIA-Karte) und Hugging Face Jobs (bezahlt).
// Günstig starten (auf Pollens Stand oder einem eigenen Lauf aufsetzen), Kosten vorher sehen, bis zu drei
// Varianten parallel, Lernkurven lesen, bei Stillstand abbrechen und den Zwischenstand exportieren.
// Bezahlte Läufe startet nur der Mensch mit zwei Klicks; kostenlose darf auch Claude starten.

import { initIsaacLab } from './isaaclab.js';

const num = (v, d = 2) => Number(v).toFixed(d).replace('.', ',');
const usd = (v) => `${num(v, 2)} $`;
const ACTIVE = ['bereitet vor', 'gestartet', 'wartet auf eine GPU', 'trainiert', 'exportiert'];

// Fähigkeits-Anzeige (auch in Akrobatik): Balken bis jetzt, Strich beim Startwert, Zahl daneben
export function skillMeter(el, now, start = null, what = '') {
  const pct = (v) => Math.round(Math.max(0, Math.min(1, v)) * 100);
  const box = el('div', 'skill-meter');
  const label = el('span', 'skill-meter-label', 'Fähigkeit');
  const bar = el('span', 'skill-meter-bar');
  const fill = el('b');
  fill.style.width = `${pct(now)}%`;
  bar.append(fill);
  if (start != null) {
    const tick = el('i');
    tick.style.left = `${pct(start)}%`;
    tick.title = `Start ${pct(start)} %`;
    bar.append(tick);
  }
  const val = el('span', 'skill-meter-val', `${pct(now)} %`);
  box.append(label, bar, val);
  const delta = start != null ? pct(now) - pct(start) : null;
  if (what || delta != null) box.append(el('span', 'skill-meter-note', [what, delta != null ? `Start ${pct(start)} %, ${delta >= 0 ? '+' : ''}${delta} Punkte` : ''].filter(Boolean).join(' · ')));
  box.setAttribute('role', 'meter');
  box.setAttribute('aria-valuemin', '0');
  box.setAttribute('aria-valuemax', '100');
  box.setAttribute('aria-valuenow', String(pct(now)));
  box.setAttribute('aria-label', `Fähigkeit ${pct(now)} Prozent${what ? `, ${what}` : ''}`);
  return box;
}

export function initTraining(h) {
  const { $, el, api, toast } = h;
  let data = null;
  let armed = null;
  let estimateTimer = null;
  let lastEstimate = null;
  let estimateSeq = 0;
  let armedPlan = null;
  const openCurves = new Set();
  const curves = {};
  const visible = () => !$('view-training').hidden;
  let kag = null;                      // Kaggle-Zustand
  let provider = (() => { try { return localStorage.getItem('duckpilot.trProv') || 'pc'; } catch { return 'pc'; } })();
  const isKaggle = () => provider === 'kaggle';
  const base = () => (isKaggle() ? '/api/kaggle' : '/api/training');

  const isaac = initIsaacLab(h);                 // Policies aus Isaac Lab (seit 0.38.27)
  async function load(refresh = false) {
    isaac.load();
    loadAlignment();
    const [d, k] = await Promise.all([
      api(refresh && provider === 'hf' ? '/api/training/aktualisieren' : '/api/training', refresh && provider === 'hf' ? 'POST' : 'GET').catch(() => null),
      api(refresh && isKaggle() ? '/api/kaggle/aktualisieren' : '/api/kaggle', refresh && isKaggle() ? 'POST' : 'GET').catch(() => null),
    ]);
    data = d;
    if (k) kag = k;
    render();
    if (h.onLocal) h.onLocal(provider === 'pc');
  }
  function setProvider(p) {
    provider = p;
    try { localStorage.setItem('duckpilot.trProv', p); } catch { /* egal */ }
    lastEstimate = null;
    disarm();
    render();
    if (h.onLocal) h.onLocal(p === 'pc');
  }
  for (const r of document.querySelectorAll('input[name="tr-prov"]')) r.addEventListener('change', () => setProvider(r.value));
  function update(msg) { data = msg; if (visible()) render(); }

  // Schritt 1: Was soll sie lernen? Den Parcours lernt sie nur am PC (Lernschleife mit Parcours-Test).
  const goal = () => (document.querySelector('input[name="tr-goal"]:checked') || {}).value || 'parcours';
  function setGoal(g) {
    for (const r of document.querySelectorAll('input[name="tr-goal"]')) r.checked = r.value === g;
    if (g === 'parcours' && provider !== 'pc') setProvider('pc'); else render();
    if (h.onGoal) h.onGoal(g);
  }
  for (const r of document.querySelectorAll('input[name="tr-goal"]')) r.addEventListener('change', () => setGoal(r.value));
  function renderFlow() {
    const g = goal();
    const pc = provider === 'pc';
    for (const r of document.querySelectorAll('input[name="tr-prov"]')) {
      r.checked = r.value === provider;
      r.disabled = g === 'parcours' && r.value !== 'pc';
      r.closest('.tr-prov').classList.toggle('is-off', r.disabled);
    }
    const note = $('tr-prov-note');
    note.hidden = g !== 'parcours';
    note.textContent = 'Deinen Parcours (Lernen → Parcours) lernt sie nur hier am PC: Knowlin baut ihn in der Physik nach und prüft nach jeder Runde, ob sie durchkommt. Kaggle und Hugging Face kennen deinen Parcours nicht – dort lernt sie Grundfähigkeiten.';
    $('tr-task-field').hidden = g !== 'aufgabe' || pc;
    $('tr-real-hint').hidden = !$('tr-real-hint').dataset.alt || g !== 'aufgabe' || pc;
    if (pc) $('tr-proposal').hidden = true;
    $('tr-goal-note').textContent = g === 'aufgabe' && pc
      ? 'Am PC lernt sie Gehen auf ebenem Boden (3 m geradeaus). Aufstehen, Drehen und Pollens andere Aufgaben trainierst du bei Kaggle (kostenlos) oder Hugging Face.'
      : '';
    $('tr-local').hidden = !pc;
    $('tr-go-pc').hidden = !pc;
    $('tr-local-progress').hidden = !pc;
    $('tr-go-cloud').hidden = pc;
    $('tr-access').hidden = provider !== 'hf';
    $('tr-kaggle').hidden = !isKaggle();
    for (const id of ['tr-form', 'tr-runs']) $(id).hidden = pc;
    document.querySelector('.tr-runs-head').hidden = pc;
    if (!pc) {
      const task = $('tr-task');
      const name = task.selectedOptions[0] ? task.selectedOptions[0].textContent.split(' – ')[0] : 'Pollens Aufgabe';
      $('tr-recap').textContent = `${name} · ${isKaggle() ? 'bei Kaggle, kostenlos' : 'bei Hugging Face, bezahlt'}`;
    }
  }

  // ── Darstellung ──────────────────────────────────────────────────────
  function render() {
    renderFlow();
    if (!data || data.ok === false) return;
    const pc = provider === 'pc';
    for (const e of document.querySelectorAll('.tr-hf-only')) e.hidden = provider !== 'hf';
    $('tr-add-variant').hidden = isKaggle();
    $('tr-cost-label').textContent = isKaggle() ? 'Kostenlos' : 'Kosten';
    $('tr-start-note').textContent = isKaggle()
      ? 'Kostenlos: ein Klick startet. Zieht nur Stunden von deinem Kaggle-Wochenkontingent ab. Auch das Sprachmodell darf solche Läufe starten.'
      : 'Zwei Klicks: Der erste zeigt den Preis noch einmal, der zweite startet. Das Sprachmodell kann bezahlte Läufe nur vorschlagen.';
    if (pc) return;
    renderAccess();
    renderKaggleAccess();
    renderForm();
    renderProposal();
    const job = (isKaggle() ? (kag && kag.job) : data.job) || {};
    $('tr-job').textContent = job.laeuft ? job.text : job.fehler ? `Start fehlgeschlagen: ${job.fehler}` : (job.text || '');
    $('tr-job').className = `field-msg ${job.fehler ? 'bad' : ''}`;
    $('tr-start').disabled = !!job.laeuft || (isKaggle() ? !(kag && kag.zugang) : (!data.token || !data.installiert));
    $('tr-start').textContent = isKaggle() ? 'Kostenlos auf Kaggle starten' : 'Training starten';
    renderRuns();
    renderFlow();                          // Zusammenfassung mit dem jetzt gefüllten Aufgaben-Namen
  }

  function renderKaggleAccess() {
    if (!kag) return;
    const st = $('kg-state');
    st.replaceChildren();
    if (kag.zugang) {
      st.append(el('b', null, '✓ Kaggle verbunden'), document.createTextNode(` · ${kag.zugang}`));
      const q = kag.konto && kag.konto.kontingent;
      if (q && q.gpu_h_frei != null) st.append(document.createTextNode(` · noch ${num(q.gpu_h_frei, 1)} von ${num(q.gpu_h_gesamt, 0)} GPU-Stunden diese Woche`));
    } else st.textContent = 'Noch kein Kaggle-Zugang.';
    $('kg-delete').hidden = !kag.zugang;
    $('kg-form').hidden = !!kag.zugang;
    $('tr-kaggle').classList.toggle('is-set', !!kag.zugang);
  }

  function renderAccess() {
    const st = $('hf-state');
    st.replaceChildren();
    if (data.token) st.append(el('b', null, '✓ Hugging Face verbunden'), document.createTextNode(` · Token ${data.token} in der Windows-Anmeldeinformationsverwaltung`));
    else st.textContent = 'Noch kein Hugging-Face-Token. Anlegen unter huggingface.co → Settings → Access Tokens (fein eingestellt, mit Recht für „Jobs“ und Schreibrecht für eigene Repos).';
    $('hf-delete').hidden = !data.token;
    $('hf-form').hidden = !!data.token;
    $('tr-access').classList.toggle('is-set', !!data.token);
    const inst = $('hf-install');
    inst.replaceChildren();
    if (!data.installiert) {
      const job = data.installation;
      const b = el('button', 'btn btn--sm btn--primary', job && job.laeuft ? 'Installiert …' : 'Hugging-Face-Paket installieren');
      b.type = 'button';
      b.disabled = !!(job && job.laeuft);
      b.addEventListener('click', async () => { b.disabled = true; await api('/api/stimme/installieren', 'POST', { paket: 'training', gpu: 'cpu' }); });
      inst.append(b);
      if (job && job.fehler) inst.append(el('span', 'field-msg bad', job.fehler));
    }
  }

  function renderForm() {
    const sel = $('tr-task');
    if (!sel.options.length) {
      for (const [id, t] of Object.entries(data.aufgaben)) sel.append(new Option(`${t.name} – ${id}`, id));
      sel.addEventListener('change', () => { disarm(); fillDefaults(); renderStart(); renderFlow(); estimate(); });
      fillDefaults();
    }
    const gpu = $('tr-gpu');
    if (!gpu.options.length) {
      for (const [id, label] of Object.entries(data.grafikkarten)) gpu.append(new Option(`${label} · ${num(data.preise[id])} $/h`, id));
    }
    renderStart();
    if (!lastEstimate) estimate();
  }

  // Start: von vorn / Pollens Stand / eigener Lauf – je nach Aufgabe
  function renderStart() {
    const task = $('tr-task').value;
    const pol = (data.pollen || {})[task];
    const own = ownRuns(task);
    const pollenRadio = document.querySelector('input[name="tr-start"][value="pollen"]');
    const ownRadio = document.querySelector('input[name="tr-start"][value="lauf"]');
    pollenRadio.disabled = !pol;
    ownRadio.disabled = !own.length;
    let mode = startMode();
    if ((mode === 'pollen' && !pol) || (mode === 'lauf' && !own.length)) mode = '';
    if (mode === null) mode = pol ? 'pollen' : '';
    for (const r of document.querySelectorAll('input[name="tr-start"]')) r.checked = r.value === mode;
    const sel = $('tr-own');
    const keep = sel.value;
    sel.replaceChildren(...own.map((r) => new Option(`${r.start}${r.variante ? ` · ${r.variante}` : ''} – ${data.aufgaben[r.plan.aufgabe]?.name || r.plan.aufgabe} (${r.status})`, r.id)));
    if (keep && own.some((r) => r.id === keep)) sel.value = keep;
    sel.hidden = mode !== 'lauf';
    const help = $('tr-start-help');
    if (mode === 'pollen') help.textContent = pol.warm
      ? `Warmstart von Pollens Stand ${pol.buendel}: Gewichte bleiben, die Lehrpläne beginnen neu. Meist reichen 500–1500 Iterationen.`
      : `Weitertrainieren von Pollens Stand ${pol.buendel} (gleiche Aufgabe, die Lehrpläne laufen weiter). Meist reichen 500–1500 Iterationen.`;
    else if (mode === 'lauf') help.textContent = 'Setzt auf dem letzten Zwischenstand des gewählten Laufs auf – gleiche Aufgabe: weitertrainieren, verwandte Aufgabe: Warmstart.';
    else help.textContent = pol ? 'Von vorn ist am teuersten – für diese Aufgabe gibt es einen Stand von Pollen.' : 'Für diese Aufgabe gibt es keinen geteilten Stand von Pollen.';
  }
  function startMode() {
    const r = document.querySelector('input[name="tr-start"]:checked');
    return r ? r.value : null;
  }
  function ownRuns(task) {
    const fam = (data.familien || {})[task];
    return (data.laeufe || []).filter((r) => (data.familien || {})[r.plan.aufgabe] === fam && r.job
      && ['fertig', 'abgebrochen', 'fehlgeschlagen'].includes(r.status));
  }

  function fillDefaults() {
    const task = $('tr-task').value;
    const t = data.aufgaben[task];
    const pol = (data.pollen || {})[task];
    $('tr-iter').value = pol ? Math.min(t.iter, 1000) : t.iter;
    $('tr-hint').textContent = t.belohnungen ? `Belohnungen: ${t.belohnungen.join(', ')}` : 'Anpassungen in der Form schlüssel = Zahl.';
    // Für den echten Roboter: die Variante mit Getriebespiel überträgt sich besser
    const backlash = task.includes('Backlash') ? null : task.replace('-MicroDuck', '-Backlash-MicroDuck').replace('Flat-Backlash', 'Rough-Backlash');
    const real = $('tr-real-hint');
    const alt = backlash && data.aufgaben[backlash] ? backlash : null;
    real.hidden = !alt;
    real.dataset.alt = alt ? '1' : '';
    if (alt) {
      real.replaceChildren(document.createTextNode(`Für den echten Roboter robuster: „${data.aufgaben[alt].name}“ – trainiert mit Getriebespiel wie bei echten Servos. `));
      const b = el('button', 'link-btn', 'Diese nehmen');
      b.type = 'button';
      b.addEventListener('click', () => { disarm(); $('tr-task').value = alt; fillDefaults(); renderStart(); renderFlow(); estimate(); });
      real.append(b);
    }
  }

  // Abgleich Training ↔ Roboter: was Pollens Training annimmt und was robotd am Roboter einstellt
  let alignDone = false;
  async function loadAlignment() {
    if (alignDone) return;
    const r = await api('/api/gelenke').catch(() => null);
    if (!r || !r.abgleich) return;
    alignDone = true;
    const body = $('tr-align-rows');
    const WORD = { gleich: 'gleich', abweichend: 'weicht ab', abgedeckt: 'abgedeckt', 'wählbar': 'wählbar' };
    body.replaceChildren(...r.abgleich.map((a) => {
      const tr = el('tr');
      tr.dataset.stand = a.stand;
      const th = el('th', null, a.thema);
      th.scope = 'row';
      tr.append(th, el('td', null, a.training), el('td', null, a.roboter), el('td', 'tr-align-state', WORD[a.stand] || a.stand), el('td', null, a.tipp));
      return tr;
    }));
  }

  function variantAreas() { return [...$('tr-variants').querySelectorAll('textarea')]; }

  function addVariant(text = '') {
    const areas = variantAreas();
    if (areas.length >= 3) return;
    $('tr-adj-label').textContent = 'Variante A – Anpassungen (eine pro Zeile)';
    const letter = String.fromCharCode(65 + areas.length);
    const wrap = el('label', 'field tr-variant');
    const head = el('span', 'field-label', `Variante ${letter} – Anpassungen`);
    const ta = el('textarea', 'input design-text');
    ta.rows = 3; ta.spellcheck = false; ta.value = text;
    ta.placeholder = 'env.rewards.upright.weight = 3';
    ta.addEventListener('input', estimateSoon);
    const rm = el('button', 'btn btn--ghost btn--sm', 'Entfernen');
    rm.type = 'button';
    rm.addEventListener('click', (e) => { e.preventDefault(); wrap.remove(); relabel(); estimate(); });
    head.append(rm);
    wrap.append(head, ta);
    $('tr-variants').append(wrap);
    relabel();
    estimate();
  }
  function relabel() {
    const extra = [...$('tr-variants').querySelectorAll('.tr-variant')];
    $('tr-adj-label').textContent = extra.length ? 'Variante A – Anpassungen (eine pro Zeile)' : 'Anpassungen (eine pro Zeile)';
    extra.forEach((w, i) => { w.querySelector('.field-label').firstChild.textContent = `Variante ${String.fromCharCode(66 + i)} – Anpassungen`; });
    $('tr-add-variant').disabled = extra.length >= 2;
  }

  function parseAdjust(text) {
    const out = {};
    for (const line of text.split(/\n|;/)) {
      const m = /^\s*-{0,2}([\w.]+)\s*[=:\s]\s*(\S+)\s*$/.exec(line);
      if (m) out[m[1]] = m[2];
      else if (line.trim()) throw new Error(`Zeile nicht verstanden: ${line.trim()}`);
    }
    return out;
  }

  function formPlan() {
    const areas = variantAreas();
    const mode = startMode() || '';
    if (mode === 'lauf' && !$('tr-own').value) throw new Error('Bitte den Lauf wählen, auf dem aufgesetzt werden soll.');
    const start = mode === 'lauf' ? `lauf:${$('tr-own').value}` : mode;
    return {
      aufgabe: $('tr-task').value, iterationen: Number($('tr-iter').value), grafikkarte: $('tr-gpu').value,
      anpassungen: parseAdjust(areas[0].value), varianten: areas.slice(1).map((a) => parseAdjust(a.value)),
      start_von: start || null, max_stunden: $('tr-hours').value ? Number($('tr-hours').value) : null,
      bei_stillstand: (document.querySelector('input[name="tr-stall"]:checked') || {}).value || 'weiter',
    };
  }

  function estimateSoon() { clearTimeout(estimateTimer); estimateTimer = setTimeout(estimate, 350); }
  async function estimate() {
    const box = $('tr-cost');
    let plan;
    try { plan = formPlan(); } catch (err) { box.replaceChildren(el('span', 'field-msg bad', err.message)); lastEstimate = null; return; }
    const seq = ++estimateSeq;
    const r = await api(`${base()}/schaetzen`, 'POST', plan).catch(() => null);
    if (seq !== estimateSeq) return;         // eine neuere Schätzung ist unterwegs
    if (!r || !r.ok) { box.replaceChildren(el('span', 'field-msg bad', (r && r.fehler) || 'Schätzung nicht möglich')); lastEstimate = null; return; }
    lastEstimate = r;
    if (isKaggle()) {
      box.replaceChildren(el('b', null, '0 $'), el('span', null,
        `≈ ${num(r.stunden, 1)} h auf einer NVIDIA T4 (${num(r.s_it, 1)} s pro Iteration, ${r.gemessen ? 'gemessen' : 'geschätzt'}) · höchstens ${r.max_stunden} h von deinen GPU-Stunden${r.hinweis ? ` · ${r.hinweis}` : ''}`));
      return;
    }
    const runs = r.laeufe > 1 ? `${r.laeufe} Läufe parallel · ` : '';
    box.replaceChildren(
      el('b', null, `≈ ${usd(r.usd)}`),
      el('span', null, `${runs}je ≈ ${num(r.stunden, 1)} h (${num(r.s_it, 1)} s pro Iteration, ${r.gemessen ? 'gemessen in deinen Läufen' : 'geschätzt'}) · höchstens ${usd(r.usd_max)} bei ${r.max_stunden} h Obergrenze`),
    );
  }

  function renderProposal() {
    const v = data.vorschlag;
    const box = $('tr-proposal');
    box.hidden = !v;
    if (!v) return;
    const t = data.aufgaben[v.aufgabe] || { name: v.aufgabe };
    const start = v.start_von === 'pollen' ? ' · auf Pollens Stand' : v.start_von ? ` · weiter von ${v.start_von.slice(5)}` : ' · von vorn';
    $('tr-proposal-title').textContent = `${t.name} · ${v.iterationen} Iterationen${start}`;
    $('tr-proposal-why').textContent = v.begruendung || '';
    const fmt = (o) => Object.entries(o || {}).map(([k, x]) => `${k} = ${x}`).join(' · ') || 'ohne Anpassungen';
    const sets = [v.anpassungen, ...(v.varianten || [])];
    $('tr-proposal-adj').textContent = sets.length > 1 ? sets.map((o, i) => `Variante ${String.fromCharCode(65 + i)}: ${fmt(o)}`).join('  |  ') : fmt(v.anpassungen);
  }

  // ── Läufe ──────────────────────────────────────────────────────────────
  function renderRuns() {
    const list = $('tr-runs');
    const runs = isKaggle() ? ((kag && kag.laeufe) || []) : data.laeufe;
    h.onLaeufe?.(runs);                 // Trainingsfeld: gemessene Erfolgsquote des neuesten Laufs (seit 0.38.19)
    if (!runs.length) { list.replaceChildren(el('div', 'empty', isKaggle() ? 'Noch keine Läufe auf Kaggle.' : 'Noch keine Läufe.')); return; }
    list.replaceChildren(...runs.map(runCard));
  }

  function runCard(r) {
    const li = el('li', 'run');
    const t = data.aufgaben[r.plan.aufgabe] || { name: r.plan.aufgabe };
    const k = r.kurve || {};
    const head = el('div', 'run-head');
    const text = el('div', 'run-text');
    text.append(el('b', null, `${t.name}${r.variante ? ` · ${r.variante}` : ''}`));
    const kg = r.anbieter === 'kaggle';
    const meta = [r.start, `${r.plan.iterationen} Iterationen`, kg ? 'Kaggle · NVIDIA T4' : (data.grafikkarten[r.plan.grafikkarte]?.split(' (')[0] || r.plan.grafikkarte),
      r.start_von || startLabel(r.plan.start_von)];
    if (kg) meta.push('kostenlos');
    else if (r.schaetzung) meta.push(`geschätzt ≈ ${usd(r.schaetzung.usd)}`);
    text.append(el('span', null, meta.join(' · ')));
    const tone = { fertig: ' chip--accent', trainiert: ' chip--data', exportiert: ' chip--data', fehlgeschlagen: '', abgebrochen: '' }[r.status] ?? ' chip--warn';
    head.append(text, el('span', `chip${tone}`, r.status));
    li.append(head);
    // Fortschritt und Kurzbefund
    if (k.punkte) {
      const prog = el('div', 'run-progress');
      const bar = el('div', 'bar');
      const i = el('i');
      i.style.width = `${Math.round((k.fortschritt || 0) * 100)}%`;
      bar.append(i);
      const facts = [];
      if (k.iteration != null) facts.push(`Iteration ${k.iteration}${k.von ? ` von ${k.von}` : ''}`);
      if (k.belohnung != null) facts.push(`Belohnung ${num(k.belohnung)} (Start ${num(k.belohnung_start)})`);
      if (k.trend != null) facts.push(k.trend > 0.05 ? 'steigt' : k.trend < -0.05 ? 'fällt' : 'flach');
      if (k.rest_min != null && ACTIVE.includes(r.status)) facts.push(`noch ≈ ${k.rest_min} min`);
      prog.append(bar, el('span', null, facts.join(' · ')));
      li.append(prog);
      if (k.faehigkeit != null) li.append(skillMeter(el, k.faehigkeit, k.faehigkeit_start, 'Durchgänge ohne Sturz oder Abbruch'));
      if (k.stillstand && ACTIVE.includes(r.status)) li.append(el('p', 'run-note is-warn', 'Die Belohnung steigt kaum noch. Abbrechen und den Zwischenstand nehmen spart Geld.'));
    }
    if (r.hinweis) li.append(el('p', 'run-note', r.hinweis));
    if (r.fehler) li.append(el('p', 'run-note is-bad', r.fehler));
    // Aktionen
    const acts = el('div', 'run-acts');
    const btn = (label, fn, cls = '') => { const b = el('button', `btn btn--sm ${cls}`, label); b.type = 'button'; b.addEventListener('click', () => fn(b)); acts.append(b); return b; };
    if (r.status === 'fertig') btn(data.physik ? 'Im Physik-Simulator ausprobieren' : 'Ausprobieren (Physik einschalten)', async (b) => {
      b.disabled = true;
      const res = await api(`${kg ? '/api/kaggle' : '/api/training'}/${r.id}/ausprobieren`, 'POST');
      b.disabled = false;
      toast(res.ok ? res.meldung : res.fehler, !res.ok);
    }, 'btn--primary');
    if (r.job) btn(openCurves.has(r.id) ? 'Lernkurve zu' : 'Lernkurve', () => { toggle(openCurves, r.id); renderRuns(); }, 'btn--ghost');
    if (r.job && !kg) btn('Protokoll', async (b) => {
      b.disabled = true;
      const res = await api(`/api/training/${r.id}/protokoll`).catch(() => ({ ok: false }));
      b.disabled = false;
      let pre = li.querySelector('pre');
      if (!pre) { pre = el('pre', 'run-log'); li.append(pre); }
      pre.textContent = res.ok ? res.zeilen.join('\n') || '(noch leer)' : (res.fehler || 'nicht abrufbar');
    }, 'btn--ghost');
    if (['fertig', 'abgebrochen', 'fehlgeschlagen'].includes(r.status) && r.job) btn('Weitertrainieren', () => continueFrom(r), 'btn--ghost');
    if (['abgebrochen', 'fehlgeschlagen'].includes(r.status) && r.job && !kg) btn('Zwischenstand exportieren', async (b) => {
      b.disabled = true;
      const res = await api(`/api/training/${r.id}/exportieren`, 'POST');
      toast(res.ok ? 'Export läuft – dauert etwa zehn Minuten' : res.fehler, !res.ok);
      b.disabled = false;
    }, 'btn--ghost');
    if (['gestartet', 'wartet auf eine GPU', 'trainiert', 'exportiert'].includes(r.status)) btn(r.status === 'exportiert' ? 'Export abbrechen' : 'Abbrechen', async (b) => {
      b.disabled = true;
      const res = await api(`${kg ? '/api/kaggle' : '/api/training'}/${r.id}/abbrechen`, 'POST');
      toast(res.ok ? (r.status === 'exportiert' ? 'Export abgebrochen' : 'Lauf abgebrochen') : res.fehler, !res.ok);
      load(true);
    }, 'btn--danger');
    if (kg && r.url) {
      const a = el('a', 'btn btn--sm btn--ghost', 'Auf Kaggle');
      a.href = r.url; a.target = '_blank'; a.rel = 'noopener';
      if (/^https:\/\/www\.kaggle\.com\//.test(r.url)) acts.append(a);
    }
    if (r.ckpt_repo) {
      const a = el('a', 'btn btn--sm btn--ghost', 'Auf dem Hub');
      a.href = `https://huggingface.co/${r.ckpt_repo}`; a.target = '_blank'; a.rel = 'noopener';
      acts.append(a);
    }
    li.append(acts);
    if (openCurves.has(r.id)) li.append(curvePanel(r));
    return li;
  }

  function startLabel(v) {
    if (v === 'pollen') return 'auf Pollens Stand';
    if (v && v.startsWith('lauf:')) return `weiter von ${v.slice(5)}`;
    return 'von vorn';
  }

  function toggle(set, id) { if (set.has(id)) set.delete(id); else set.add(id); }

  function continueFrom(r) {
    $('tr-task').value = r.plan.aufgabe;
    fillDefaults();
    for (const x of document.querySelectorAll('input[name="tr-start"]')) x.checked = x.value === 'lauf';
    renderStart();
    $('tr-own').value = r.id;
    $('tr-iter').value = 1000;
    variantAreas()[0].value = Object.entries(r.plan.anpassungen || {}).map(([k, x]) => `${k} = ${x}`).join('\n');
    if (variantAreas()[0].value) document.querySelector('.tr-expert').open = true;
    disarm();
    for (const x of document.querySelectorAll('input[name="tr-goal"]')) x.checked = x.value === 'aufgabe';
    renderFlow();
    estimate();
    $('tr-step-what').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ── Lernkurve ──────────────────────────────────────────────────────────
  function curvePanel(r) {
    const box = el('div', 'curve');
    const c = curves[r.id];
    if (!c || (c.stale && !c.loading)) {
      if (c) c.loading = true; else curves[r.id] = { pending: true };
      api(`${r.anbieter === 'kaggle' ? '/api/kaggle' : '/api/training'}/${r.id}/kurve`).then((res) => { curves[r.id] = res; if (visible()) renderRuns(); })
        .catch(() => { curves[r.id] = { ok: false, fehler: 'Lernkurve nicht abrufbar' }; if (visible()) renderRuns(); });
    }
    if (!c || c.pending) { box.append(el('p', 'field-help', 'Lade die Lernkurve …')); return box; }
    if (!c.ok) { box.replaceChildren(el('p', 'field-msg bad', c.fehler || 'nicht abrufbar')); return box; }
    const s = c.zusammenfassung || {};
    if (!c.punkte.length) { box.replaceChildren(el('p', 'field-help', 'Noch keine Iteration im Protokoll – der Lauf startet gerade.')); return box; }
    box.replaceChildren(
      ...(c.punkte.some((p) => p.faehigkeit != null)
        ? [chart(c.punkte.map((p) => ({ ...p, faehigkeit: p.faehigkeit == null ? null : p.faehigkeit * 100 })), 'faehigkeit',
          'Fähigkeit: Anteil der Durchgänge ohne Sturz oder Abbruch (%)')] : []),
      chart(c.punkte, 'belohnung', 'Mittlere Belohnung pro Episode'),
      chart(c.punkte, 'laenge', 'Mittlere Episodenlänge (Schritte) – länger heißt: fällt seltener um'),
    );
    if (s.terme && s.terme.length) {
      const table = el('table', 'curve-terms');
      const head = el('tr');
      for (const x of ['Belohnungsterm', 'Laufmitte', 'jetzt', 'Veränderung']) head.append(el('th', null, x));
      const thead = el('thead'); thead.append(head);
      const tbody = el('tbody');
      for (const t of s.terme) {
        const tr = el('tr');
        const d = t.aenderung;
        tr.append(el('td', null, t.term), el('td', null, t.vorher == null ? '–' : num(t.vorher, 3)), el('td', null, num(t.jetzt, 3)),
          el('td', d == null ? '' : d > 0 ? 'up' : d < 0 ? 'down' : '', d == null ? '–' : `${d > 0 ? '+' : ''}${num(d, 3)}`));
        tbody.append(tr);
      }
      table.append(thead, tbody);
      box.append(table);
    }
    const ab = Object.entries(s.abbrueche || {});
    if (ab.length) box.append(el('p', 'field-help', `Abbruchgründe (Anteil der Episoden): ${ab.map(([k, v]) => `${k} ${num(v * 100, 0)} %`).join(' · ')}`));
    box.append(el('p', 'field-help', 'Tipp: Frag Claude „Wie läuft das Training?“ – es liest dieselbe Kurve und schlägt gezielt Gewichte vor.'));
    return box;
  }

  // Einfache Linie mit Fadenkreuz und Wertanzeige beim Überfahren
  function chart(points, key, title) {
    const pts = points.filter((p) => p[key] != null);
    const wrap = el('figure', 'chart');
    wrap.append(el('figcaption', null, title));
    if (pts.length < 2) { wrap.append(el('p', 'field-help', 'zu wenige Punkte')); return wrap; }
    const W = 1100, H = 190, L = 48, R = 8, T = 10, B = 24;
    const xs = pts.map((p) => p.it), ys = pts.map((p) => p[key]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (y1 - y0 < 1e-9) { y0 -= 1; y1 += 1; }
    const sx = (x) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - R);
    const sy = (y) => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B);
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${title}: von ${num(ys[0])} auf ${num(ys[ys.length - 1])}`);
    const mk = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const [a, v] of Object.entries(attrs)) n.setAttribute(a, v); svg.append(n); return n; };
    for (const f of [0, 0.5, 1]) {
      const y = y0 + (y1 - y0) * f;
      mk('line', { x1: L, x2: W - R, y1: sy(y), y2: sy(y), class: 'grid' });
      mk('text', { x: L - 6, y: sy(y) + 4, class: 'tick', 'text-anchor': 'end' }).textContent = num(y, Math.abs(y) < 10 ? 2 : 0);
    }
    mk('text', { x: L, y: H - 6, class: 'tick' }).textContent = `Iteration ${x0}`;
    mk('text', { x: W - R, y: H - 6, class: 'tick', 'text-anchor': 'end' }).textContent = String(x1);
    mk('polyline', { points: pts.map((p) => `${sx(p.it).toFixed(1)},${sy(p[key]).toFixed(1)}`).join(' '), class: 'line' });
    const cross = mk('line', { y1: T, y2: H - B, class: 'cross', visibility: 'hidden' });
    const dot = mk('circle', { r: 4, class: 'dot', visibility: 'hidden' });
    const tip = el('span', 'chart-tip');
    tip.hidden = true;
    svg.addEventListener('pointermove', (e) => {
      const rect = svg.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * W;
      let best = pts[0];
      for (const p of pts) if (Math.abs(sx(p.it) - x) < Math.abs(sx(best.it) - x)) best = p;
      cross.setAttribute('x1', sx(best.it)); cross.setAttribute('x2', sx(best.it)); cross.setAttribute('visibility', 'visible');
      dot.setAttribute('cx', sx(best.it)); dot.setAttribute('cy', sy(best[key])); dot.setAttribute('visibility', 'visible');
      tip.hidden = false;
      tip.textContent = `Iteration ${best.it}: ${num(best[key], 2)}`;
      tip.style.left = `${(sx(best.it) / W) * 100}%`;
    });
    svg.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); tip.hidden = true; });
    const stage = el('div', 'chart-stage');
    stage.append(svg, tip);
    wrap.append(stage);
    return wrap;
  }

  // ── Bedienung ──────────────────────────────────────────────────────────
  $('hf-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = $('hf-token').value.trim();
    if (!token) return;
    const r = await api('/api/training/token', 'POST', { token });
    $('hf-token').value = '';
    if (!r.ok) { toast(r.fehler, true); return; }
    toast(r.konto && r.konto.name ? `Hinterlegt – Konto ${r.konto.name}` : 'Hinterlegt');
    load();
  });
  $('kg-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $('kg-json').value.trim();
    if (!text) return;
    const r = await api('/api/kaggle/zugang', 'POST', { json: text }).catch(() => null);
    $('kg-json').value = '';
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return; }
    toast('Kaggle-Zugang hinterlegt');
    kag = r; render();
  });
  $('kg-json').addEventListener('dragover', (e) => e.preventDefault());
  $('kg-json').addEventListener('drop', async (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f && f.size < 4096) $('kg-json').value = await f.text();
  });
  $('kg-delete').addEventListener('click', async () => { const r = await api('/api/kaggle/zugang', 'DELETE'); kag = r; toast('Kaggle-Zugang entfernt'); render(); });
  $('hf-delete').addEventListener('click', async () => { await api('/api/training/token', 'DELETE'); toast('Token entfernt'); load(); });
  $('tr-proposal-use').addEventListener('click', () => {
    const v = data.vorschlag;
    $('tr-task').value = v.aufgabe;
    fillDefaults();
    $('tr-iter').value = v.iterationen;
    const mode = v.start_von === 'pollen' ? 'pollen' : v.start_von ? 'lauf' : '';
    for (const x of document.querySelectorAll('input[name="tr-start"]')) x.checked = x.value === mode;
    renderStart();
    if (mode === 'lauf') {
      $('tr-own').value = v.start_von.slice(5);
      if ($('tr-own').value !== v.start_von.slice(5)) toast(`Lauf ${v.start_von.slice(5)} hat keinen Zwischenstand für diese Aufgabe – bitte einen anderen Start wählen.`, true);
    }
    if (v.max_stunden) $('tr-hours').value = v.max_stunden;
    for (const x of document.querySelectorAll('input[name="tr-stall"]')) x.checked = x.value === (v.bei_stillstand || 'weiter');
    for (const w of $('tr-variants').querySelectorAll('.tr-variant')) w.remove();
    const fmt = (o) => Object.entries(o || {}).map(([k, x]) => `${k} = ${x}`).join('\n');
    variantAreas()[0].value = fmt(v.anpassungen);
    for (const extra of v.varianten || []) addVariant(fmt(extra));
    relabel();
    if (Object.keys(v.anpassungen || {}).length || (v.varianten || []).length) document.querySelector('.tr-expert').open = true;
    for (const x of document.querySelectorAll('input[name="tr-goal"]')) x.checked = x.value === 'aufgabe';
    renderFlow();
    estimate();
    $('tr-step-what').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  $('tr-proposal-drop').addEventListener('click', async () => { await api('/api/training/vorschlag/verwerfen', 'POST'); load(); });
  $('tr-refresh').addEventListener('click', () => { for (const id of Object.keys(curves)) curves[id].stale = true; load(true); });
  $('tr-add-variant').addEventListener('click', () => addVariant());
  for (const id of ['tr-iter', 'tr-gpu', 'tr-hours', 'tr-own']) $(id).addEventListener('input', estimateSoon);
  $('tr-gpu').addEventListener('change', estimate);
  $('tr-own').addEventListener('change', estimate);
  variantAreas()[0].addEventListener('input', estimateSoon);
  for (const r of document.querySelectorAll('input[name="tr-start"]')) r.addEventListener('change', () => { renderStart(); estimate(); });
  function disarm() {
    if (!armed) return;
    clearTimeout(armed); armed = null; armedPlan = null;
    $('tr-start').textContent = 'Training starten'; $('tr-start').classList.remove('armed');
  }
  $('tr-form').addEventListener('input', disarm);
  $('tr-form').addEventListener('change', disarm);
  $('tr-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const b = $('tr-start');
    if (isKaggle()) {                 // kostenlos: ein Klick
      let plan;
      try { plan = formPlan(); } catch (err) { toast(err.message, true); return; }
      b.disabled = true;
      const r = await api('/api/kaggle/start', 'POST', plan).catch(() => null);
      b.disabled = false;
      if (!r || !r.ok) toast(r ? r.fehler : 'Keine Antwort', true); else { toast('Läuft auf Kaggle – die Lernkurve kommt in einigen Minuten'); load(); }
      return;
    }
    if (!armed) {   // erst scharf schalten: ein Lauf kostet Geld. Gestartet wird genau das, was jetzt angezeigt wird.
      let plan;
      try { plan = formPlan(); } catch (err) { toast(err.message, true); return; }
      clearTimeout(estimateTimer);
      await estimate();
      if (!lastEstimate) return;           // Fehler steht im Kostenfeld
      armedPlan = plan;
      b.textContent = `Nochmal klicken: ≈ ${usd(lastEstimate.usd)} ausgeben`;
      b.classList.add('armed');
      armed = setTimeout(disarm, 6000);
      return;
    }
    const plan = armedPlan;
    disarm();
    const r = await api('/api/training/start', 'POST', plan);
    if (!r.ok) toast(r.fehler, true); else toast(r.laeufe > 1 ? `${r.laeufe} Varianten werden gestartet …` : 'Training wird gestartet …');
  });

  return { load, update, chart, setProvider, setGoal, goal };
}

// Trainingsfeld (seit 0.38.19): erst laden, wenn die Seite Training offen ist – three.js nur bei Bedarf.
// Mit einem Lauf, der eine Erfolgsquote meldet, zeigt das Feld diese; sonst die Lernkurve im Zeitraffer.
// `figur()` sagt, welche Enten das Feld zeigt: { koerper, original, farbe } wie in der 3D-Ansicht (seit 0.38.23).
export function trainingsfeldLaden($, figur = () => ({})) {
  let feld = null, laeufe = [], laedt = false;
  const fmt = (x) => `${Math.round(x * 100)} %`;
  function anwenden() {
    if (!feld) return;
    const r = laeufe.find((x) => x.kurve && x.kurve.faehigkeit != null);
    const aktiv = laeufe.find((x) => ACTIVE.includes(x.status));
    feld.setLauf(r ? { erfolg: Math.max(0.03, Math.min(0.98, r.kurve.faehigkeit)), name: r.plan && r.plan.aufgabe } : null);
    // Ehrlich sagen, was das Feld ist (Frage: „lernen sie automatisch dort oder ist das nur eine Vorschau?“)
    const art = $('tr-feld-art');
    if (art) {
      art.textContent = r ? 'Gemessene Quote, Bewegung nachgestellt' : 'Vorschau – hier lernt nichts';
      art.className = `chip tr-feld-art ${r ? 'chip--data' : 'chip--warn'}`;
    }
    const jetzt = aktiv ? ` Gerade läuft ein Training (${aktiv.status}) – wenn es fertig ist, zeigt das Feld seine Quote.` : '';
    $('tr-feld-satz').textContent = (r
      ? `Dein neuester Lauf schafft ${fmt(r.kurve.faehigkeit)} der Durchgänge ohne Sturz – gemessen in der Physik. Die Enten hier spielen diese Quote nach: Wer stürzt, wird an den Start zurückgesetzt. Im Feld selbst lernt nichts.`
      : 'Nachgestellt, ohne Physik: So sieht Training aus – viele Enten üben gleichzeitig, wer stürzt, beginnt am Start neu. Gelernt wird erst, wenn du unten einen Lauf startest (am PC oder auf Kaggle); danach zeigt das Feld seine gemessene Quote.') + jetzt;
  }
  return {
    async zeigen() {
      if (feld) { feld.setModell(figur()); return; }        // Originale an/aus oder anderer Körper seit dem letzten Mal
      if (laedt || !$('tr-feld-canvas')) return;
      laedt = true;
      try {
        const m = await import('./trainingsfeld.js');
        feld = m.trainingsfeld($('tr-feld-canvas'));
        let zuletzt = '';
        feld.beiBau((laeuft) => { $('tr-feld-bau').hidden = !laeuft; });
        feld.beiZahlen(({ stehen, anzahl, erfolg }) => {
          const t = `${stehen} von ${anzahl} unterwegs · ${fmt(erfolg)} ohne Sturz`;
          if (t !== zuletzt) { zuletzt = t; $('tr-feld-zahl').textContent = t; }
        });
        anwenden();
        feld.setModell(figur());
      } catch { $('tr-feld').hidden = true; }           // ohne WebGL: kein Feld, der Rest geht
    },
    laeufe(r) { laeufe = r || []; anwenden(); },
  };
}
