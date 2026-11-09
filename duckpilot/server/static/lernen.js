// Lernen → Training → Dieser PC: kostenlos am eigenen PC lernen, mit Lernschleife über den Parcours.
// Eine Runde trainiert (PPO, Physik auf dem Prozessor, Netz auf der Grafikkarte), dann prüft der Parcours-Test,
// und die nächste Runde setzt auf dem besten geprüften Stand auf. Alle Namen nur über textContent.
import { installBalken, installStand } from './fortschritt.js';

export function initLernen(h) {
  const { $, api, el, toast, chart, showView } = h;
  let data = null;
  let shown = false;
  let installPoll = null;
  let lastCurveKey = '';
  const num = (v, d = 0) => (v == null ? '–' : Number(v).toFixed(d).replace('.', ','));

  async function load() {
    const r = await api('/api/lernen').catch(() => null);
    if (r && r.type === 'lernen') { data = r; initGoal(); render(); }
  }
  function show(on) {
    shown = on;
    if (on) load();
  }
  function update(msg) {
    data = msg;
    if (shown) render();
  }

  const mode = () => (document.querySelector('input[name="lr-mode"]:checked') || {}).value || 'schleife';
  const goal = () => (document.querySelector('input[name="tr-goal"]:checked') || {}).value || '';
  const BUDGET = { 20: '20 Minuten', 60: '1 Stunde', 180: '3 Stunden', 480: '8 Stunden' };

  // Schritt 1 vorbelegen: mit Parcours „Den Parcours schaffen“, sonst „Grundfähigkeit“
  function initGoal() {
    if (goal()) return;
    const g = data && data.parcours ? 'parcours' : 'aufgabe';
    for (const r of document.querySelectorAll('input[name="tr-goal"]')) r.checked = r.value === g;
    if (h.onGoal) h.onGoal(g);
  }

  function render() {
    if (!data) return;
    const loop = data.schleife || {};
    const run = data.lauf || {};
    const busy = !!(loop.laeuft || run.laeuft);

    // Gerät
    const cores = Math.max(1, (data.kerne || 2) - 1);
    const gpu = run.geraet || (data.gpu_vorschlag === 'amd' ? 'Radeon über AMDs PyTorch (ROCm)'
      : data.gpu_vorschlag === 'nvidia' ? 'NVIDIA über CUDA' : 'Prozessor (keine passende Grafikkarte erkannt)');
    $('lr-device').textContent = `Physik: ${cores} ${cores === 1 ? 'Rechenprozess' : 'Rechenprozesse'} auf dem Prozessor · Netz: ${gpu}`;

    // Einrichtung
    const setup = $('lr-setup');
    setup.replaceChildren();
    const inst = data.installation || {};
    if (!data.verfuegbar) {
      setup.hidden = false;
      if (inst.laeuft) {
        // mit Datei, MB und Balken (seit 0.38.38) – PyTorch für die Grafikkarte sind gut 2,5 GB
        setup.append(el('p', 'field-help', `Installiere … ${installStand(inst)}`), installBalken(el, inst));
        watchInstall();
      } else {
        setup.append(el('p', 'field-help', inst.fehler ? `Installation fehlgeschlagen: ${inst.fehler}` : data.grund || ''));
        const g = data.gpu_vorschlag || 'cpu';
        const b = el('button', 'btn btn--sm btn--primary',
          g === 'amd' ? 'PyTorch für die Radeon installieren (≈ 2,5 GB)' : g === 'nvidia' ? 'PyTorch für NVIDIA installieren (≈ 2,5 GB)'
            : 'PyTorch für den Prozessor installieren (≈ 200 MB)');
        b.type = 'button';
        b.addEventListener('click', async () => {
          const x = await api('/api/stimme/installieren', 'POST', { paket: 'lernen', gpu: g }).catch(() => null);
          if (!x || !x.ok) { toast(x ? x.fehler : 'Keine Antwort', true); return; }
          toast('Installiere … das dauert ein paar Minuten. Danach Knowlin neu starten.');
          watchInstall();
        });
        setup.append(b);
      }
    } else setup.hidden = true;

    // Schritt 1: Ziel
    const hasCourse = !!data.parcours;
    const onCourse = goal() === 'parcours';
    $('tr-goal-course').textContent = hasCourse ? `„${data.parcours}“ – so lange üben, bis sie durchkommt`
      : 'Noch kein Parcours gebaut – das geht unter Lernen → Parcours';
    $('tr-goal-build').hidden = !(onCourse && !hasCourse);

    // Schritt 2: wie
    const m = onCourse ? mode() : 'einmal';
    $('lr-mode-field').hidden = !onCourse;
    $('lr-mode-help').textContent = m === 'schleife'
      ? `Lernt eine Runde, prüft dann auf „${data.parcours || '…'}“ (3 Durchgänge) und macht vom besten Stand weiter – bis alle drei im Ziel sind oder das Budget um ist.`
      : `Ein Lauf mit dem ganzen Budget auf „${data.parcours || '…'}“, ohne Zwischenprüfung.`;
    for (const e of document.querySelectorAll('.lr-loop-only')) e.hidden = m !== 'schleife';
    const sel = $('lr-source');
    const keep = sel.value;
    sel.replaceChildren(...(data.quellen || []).map((q) => new Option(q.name, q.id)));
    if (keep && [...sel.options].some((o) => o.value === keep)) sel.value = keep;
    for (const c of $('lr-form').querySelectorAll('select, input')) c.disabled = busy;
    for (const c of document.querySelectorAll('input[name="tr-goal"]')) c.disabled = busy;
    // Während des Lernens nur das Wichtige: was läuft und der Knopf zum Beenden
    $('lr-form').hidden = busy;
    $('lr-go-help').hidden = busy;
    $('lr-go').disabled = busy || !data.verfuegbar || !(data.quellen || []).length || (onCourse && !hasCourse);
    $('lr-go').hidden = busy;
    $('lr-go').textContent = onCourse ? (m === 'schleife' ? 'Kostenlos lernen, bis sie es kann' : 'Kostenlos lernen') : 'Kostenlos gehen lernen';
    $('lr-stop').hidden = !busy;

    // Schritt 3: in einem Satz, was gleich passiert
    const src = $('lr-source').selectedOptions[0];
    $('tr-recap').textContent = busy ? 'Läuft gerade – unten siehst du jede Runde.'
      : onCourse && !hasCourse ? 'Erst einen Parcours bauen, dann kann sie ihn lernen.'
      : `${onCourse ? `Parcours „${data.parcours}“` : 'Gehen auf ebenem Boden'} · auf diesem PC, kostenlos · `
        + `${onCourse && m === 'schleife' ? 'Lernschleife' : 'am Stück'} · ${BUDGET[$('lr-budget').value] || ''}`
        + (src ? ` · ausgehend von ${src.textContent}` : '');

    // Stand
    $('lr-state').textContent = loop.laeuft ? loop.phase : run.laeuft ? run.phase : (loop.fazit || (run.id ? run.phase : ''));
    $('lr-state').className = `lr-state ${loop.fehler || run.fehler ? 'bad' : loop.geschafft ? 'good' : ''}`;

    renderLive(loop, run);
    renderResults();
  }

  function renderLive(loop, run) {
    const live = $('lr-live');
    const has = !!(run.id || loop.start);
    live.hidden = !has;
    if (!has) return;
    // Runden-Zeitleiste
    const ol = $('lr-rounds');
    const items = [];
    if (loop.schleife && loop.vorher) {
      const li = el('li', 'lr-round is-base');
      li.append(el('b', null, 'Vorher'), el('span', null, `${loop.vorher.im_ziel} von ${loop.vorher.versuche} im Ziel`));
      items.push(li);
    }
    for (const r of loop.runden || []) {
      const running = loop.laeuft && r === loop.runden[loop.runden.length - 1] && !r.test;
      const li = el('li', `lr-round ${running ? 'is-run' : r.test ? (r.test.im_ziel >= r.test.versuche ? 'is-done' : r.besser ? 'is-up' : 'is-flat') : ''}`);
      li.append(el('b', null, `Runde ${r.runde}`));
      li.append(el('span', null, r.test ? `${r.test.im_ziel} von ${r.test.versuche} im Ziel` : running ? 'lernt …' : r.ergebnis ? 'gelernt' : '–'));
      li.append(el('small', null, `${num(r.minuten, 0)} min${r.faehigkeit != null ? ` · ${num(r.faehigkeit)} % ohne Sturz` : ''}` +
        (r.test ? ` · ${r.warum || (r.besser ? 'neuer Bestwert' : 'weiter vom besten Stand')}` : '')));
      items.push(li);
    }
    ol.replaceChildren(...items);
    ol.hidden = !items.length;

    // Kurven des aktuellen Laufs
    const pts = (run.kurve || []).map((p) => ({ it: p.iteration, belohnung: p.belohnung, faehigkeit: p.faehigkeit, ziel: p.im_ziel_anteil }));
    const key = `${run.id}:${pts.length}:${pts.length ? pts[pts.length - 1].it : 0}`;
    if (key !== lastCurveKey) {
      lastCurveKey = key;
      $('lr-charts').replaceChildren(
        chart(pts, 'faehigkeit', 'Fähigkeit: Anteil der letzten 40 Durchgänge ohne Sturz (%)'),
        chart(pts, 'ziel', 'Im Ziel: Anteil der letzten 40 Durchgänge (%)'),
        chart(pts, 'belohnung', 'Belohnung pro simulierter Sekunde'),
      );
    }
    const parts = [];
    if (run.iteration) parts.push(`Iteration ${run.iteration}`);
    if (run.schritte_pro_s) parts.push(`${num(run.schritte_pro_s)} Schritte/s`);
    if (run.umgebungen) parts.push(`${run.umgebungen} Enten gleichzeitig`);
    if (loop.laeuft) parts.push(`${num(loop.verbraucht_minuten, 0)} von ${num(loop.budget_minuten, 0)} min`);
    else if (run.minuten) parts.push(`${num(run.minuten, 1)} min`);
    if (loop.von === 'claude') parts.push('gestartet von Claude' + (loop.begruendung ? `: ${loop.begruendung}` : ''));
    if (run.hinweis) parts.push(run.hinweis);
    $('lr-numbers').textContent = parts.join(' · ');
  }

  function renderResults() {
    const ul = $('lr-results');
    const rows = (data.verlauf || []).map((j) => {
      const li = el('li', 'al-item');
      const txt = el('span', 'al-item-text');
      const best = j.bester || {};
      txt.append(el('b', null, j.name || j.parcours_name || 'Lauf'),
        el('small', null, ` · ${j.start || ''} · ${num(j.minuten, 0)} min · ${j.phase || ''}` +
          (best.faehigkeit != null ? ` · bester Stand ${num(best.faehigkeit)} % ohne Sturz` : '')));
      li.append(txt);
      if (j.ergebnis) {
        const t = el('button', 'btn btn--ghost btn--sm', 'Auf dem Parcours testen');
        t.type = 'button';
        t.addEventListener('click', () => { showView('parcours'); h.pickSource(j.ergebnis); });
        const p = el('button', 'btn btn--ghost btn--sm', 'Ausprobieren');
        p.type = 'button';
        p.addEventListener('click', async () => {
          const r = await api('/api/lernen/ausprobieren', 'POST', { quelle: j.ergebnis }).catch(() => null);
          if (!r || !r.ok) toast(r ? r.fehler : 'Keine Antwort', true); else toast(r.meldung || 'Geladen – unter Steuern → Tricks');
        });
        li.append(t, p);
      } else if (j.rettbar) {
        const s = el('button', 'btn btn--ghost btn--sm', 'Besten Stand speichern');
        s.type = 'button';
        s.addEventListener('click', async () => {
          const r = await api(`/api/lernen/lauf/${encodeURIComponent(j.id)}/retten`, 'POST').catch(() => null);
          if (!r || !r.ok) toast(r ? r.fehler : 'Keine Antwort', true); else { toast('Gespeichert'); load(); }
        });
        li.append(s);
      }
      return li;
    });
    ul.replaceChildren(...(rows.length ? rows : [el('li', 'field-help', 'Noch nichts am PC gelernt.')]));
  }

  function watchInstall() {
    if (installPoll) return;
    installPoll = setInterval(async () => {
      await load();
      const inst = (data && data.installation) || {};
      if (!inst.laeuft) { clearInterval(installPoll); installPoll = null; }
    }, 2000);
  }

  for (const r of document.querySelectorAll('input[name="lr-mode"]')) r.addEventListener('change', render);
  for (const id of ['lr-budget', 'lr-source']) $(id).addEventListener('change', render);
  $('tr-goal-build').addEventListener('click', () => showView('parcours'));
  $('lr-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('lr-go');
    btn.disabled = true;
    const onCourse = goal() === 'parcours';
    const body = { minuten: Number($('lr-budget').value), lernschleife: onCourse && mode() === 'schleife',
      parcours: onCourse, quelle: $('lr-source').value };
    if ($('lr-round').value) body.runde_minuten = Number($('lr-round').value);
    const r = await api('/api/lernen/start', 'POST', body).catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); btn.disabled = false; return; }
    toast(body.lernschleife ? 'Lernschleife läuft – du kannst Knowlin offen lassen und weggehen' : 'Lernt …');
    data = r; render();
  });
  $('lr-stop').addEventListener('click', async () => {
    $('lr-stop').disabled = true;
    const r = await api('/api/lernen/stopp', 'POST').catch(() => null);
    $('lr-stop').disabled = false;
    if (r && r.type === 'lernen') { data = r; render(); }
  });

  // Vom Parcours aus: „Lernen, bis sie es kann“
  function prepareLoop() {
    const r = document.querySelector('input[name="lr-mode"][value="schleife"]');
    if (r) r.checked = true;
    for (const x of document.querySelectorAll('input[name="tr-goal"]')) x.checked = x.value === 'parcours';
    if (h.onGoal) h.onGoal('parcours');
    load().then(() => { $('tr-step-go').scrollIntoView({ behavior: 'smooth', block: 'center' }); $('lr-go').focus({ preventScroll: true }); });
  }

  return { load, show, update, prepareLoop, render: () => { if (shown && data) render(); } };
}
