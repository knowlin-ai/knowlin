// Seite „Stimme & Gespräch“: Sprachmotor wählen und einrichten, Entenstimme entwerfen,
// Klang und Entenlaute, Plaudern und das eigene Sprachmodell (Ollama).
// Was aus Ollama oder pip kommt, ist Fremdtext: nur als textContent.
import { initAnbieter } from './anbieter.js';
import { installBalken, installStand } from './fortschritt.js';
import { t, uebersetzeText } from './i18n.js';
import { playSound, setKlang } from './voice.js';

const tr = (text) => uebersetzeText(text) || text;

const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l12-7.5z"/></svg>';
const CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
const DOWN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v12M6.5 10.5 12 16l5.5-5.5M5 20h14"/></svg>';

const ENGINES = [
  { id: 'browser', name: 'Browser-Stimme', text: 'Die Stimme von Windows bzw. Edge. Sofort da, klingt aber nach Ansage.',
    facts: ['nichts zu laden'] },
  { id: 'piper', name: 'Piper', text: 'Schnell und offline. Deutsche Stimmen von Thorsten-Voice und anderen – eine kann fröhlich, überrascht, flüsternd.',
    facts: ['Prozessor genügt', '≈ 60–110 MB je Stimme', 'GPL-3.0'] },
  { id: 'qwen', name: 'Qwen3-TTS', text: 'Am natürlichsten. Du beschreibst die Stimme in Worten, das Modell erfindet sie – danach klingt die Verkörperung immer so.',
    facts: ['Grafikkarte empfohlen', '≈ 3,5 GB + Modelle', 'Apache-2.0'] },
];
const GPU_LABEL = { amd: 'AMD (ROCm)', nvidia: 'NVIDIA (CUDA)', cpu: 'Nur Prozessor' };
// Je Robotertyp (Hinweis aus dem Test 5.11.): Probetext und Beispiel fürs Entwerfen – Reachy ist keine Ente
const PROBE = {
  duckpilot: (n) => `*quak quak* Hallo, ich bin ${n}! So klinge ich jetzt. Gefällt dir meine Stimme?`,
  open_duck_mini: (n) => `*quak* Hallo, ich bin ${n}! Selbst gebaut und startklar. Gefällt dir meine Stimme?`,
};
const BEISPIEL = {
  duckpilot: 'z. B. Eine kleine, quirlige Ente mit hoher, heller, leicht näselnder Stimme …',
  open_duck_mini: 'z. B. Eine größere, gemütliche Ente mit etwas tieferer, warmer Stimme und Bastler-Charme …',
  reachy_mini: 'z. B. Ein freundlicher, neugieriger Tischroboter mit warmer, mittlerer, leicht technischer Stimme …',
};
const GPU_HELP = {
  amd: 'PyTorch mit ROCm direkt unter Windows, aus AMDs Paketquelle. Braucht einen aktuellen Adrenalin-Treiber. Hat der PC zusätzlich eine Grafik im Prozessor, kann es nötig sein, diese im Geräte-Manager abzuschalten.',
  nvidia: 'PyTorch mit CUDA 12.8 aus der PyTorch-Paketquelle.',
  cpu: 'Geht immer, ist für Qwen3-TTS aber langsam – ein Satz kann einige Sekunden dauern.',
};

export function initVoicePage(h) {
  const { $, el, api, toast } = h;
  const anbieter = initAnbieter({ $, el, api, toast, save: (p, ok) => save(p, ok) });
  let info = null;
  let cfg = {};
  let brain = null;
  let gpu = null;            // gewählte Grafikkarte für die Installation
  let designText = '';
  let deleteArmed = null;

  const visible = () => !$('view-stimme').hidden;
  // Im Kopf geöffnet (seit 0.38.10): dieselbe Seite stellt Knowlins eigene Stimme ein – ohne einen Körper zu wecken
  const kopf = () => !!(h.imKopf && h.imKopf());
  const KOPF_KEYS = { stimme_motor: 'kopf_stimme_motor', stimme_piper: 'kopf_stimme_piper', stimme_qwen: 'kopf_stimme_qwen' };
  const werte = () => {
    const w = (info && info.werte) || {};
    if (!kopf() || !info.kopf) return w;
    return { ...w, stimme_motor: info.kopf.stimme_motor, stimme_piper: info.kopf.stimme_piper, stimme_qwen: info.kopf.stimme_qwen };
  };
  const motorJetzt = () => (kopf() && info.kopf ? info.kopf.motor : info.motor);
  const kopfName = () => cfg.kopf_name || 'Knowlin';
  const fuer = () => (kopf() ? { fuer: 'kopf' } : {});

  async function save(patch, ok) {
    if (kopf()) patch = Object.fromEntries(Object.entries(patch).map(([k, v]) => [KOPF_KEYS[k] || k, v]));
    const r = await api('/api/settings', 'POST', patch).catch(() => ({ ok: false, fehler: 'Knowlin antwortet nicht' }));
    if (!r.ok) { toast(r.fehler || 'Nicht gespeichert', true); return false; }
    if (ok) toast(ok);
    if (info && kopf() && info.kopf) {
      for (const [k, v] of Object.entries(KOPF_KEYS)) if (v in patch) info.kopf[k] = patch[v];
      if ('kopf_stimme_motor' in patch) info.kopf.motor = patch.kopf_stimme_motor;
    } else if (info) Object.assign(info.werte, patch);
    return true;
  }

  async function load() {
    const r = await api('/api/stimme').catch(() => null);
    if (r) info = r;
    render();
    loadBrain();
    anbieter.load();
  }

  function update(msg) {
    info = msg;
    if (visible()) render();
  }

  function config(c) {
    cfg = c;
    if (visible()) render();
  }

  // ── Zeichnen ──────────────────────────────────────────────────────────
  const istEnte = () => { if (kopf()) return false; const f = info && (info.figuren || []).find((x) => x.aktiv); return !f || f.ente; };
  const modulJetzt = () => { const f = info && (info.figuren || []).find((x) => x.aktiv); return (f && f.modul) || cfg.modul || 'duckpilot'; };
  function render() {
    if (!info) return;
    const w = werte();
    const name = cfg.duck_name || (istEnte() ? 'die Ente' : 'Reachy');
    const ich = kopf() ? null : (info.figuren || []).find((f) => f.aktiv);
    const ente = !kopf() && (!ich || ich.ente);
    // Die Stimme gehört der Verkörperung in ihrem Körper (seit 0.38.6): jede Verkörperung hat ihre eigene
    $('stimme-sub').textContent = kopf() ? t('stimme.untertitel_kopf', { name: kopfName() }, 'Stimme von {name} – gilt ohne Körper. Die Verkörperungen haben ihre eigenen.')
      : ich ? tr(`Stimme von ${name} (${tr(ich.koerper)}) – gilt nur für diese Verkörperung. Die anderen behalten ihre.`)
        : tr(`Wie ${name} klingt.`);
    // Kopf oder anderer Körper: Probetext und Entwurf passen nicht mehr – neu vorbelegen
    const wer = `${kopf()}|${modulJetzt()}`;
    if (wer !== $('probe-text').dataset.kopf) { $('probe-text').value = ''; designText = ''; $('probe-text').dataset.kopf = wer; }
    if (!$('probe-text').value && kopf()) $('probe-text').value = `Ich bin ${kopfName()}. So klinge ich.`;
    const probe = ente && (PROBE[modulJetzt()] || PROBE.duckpilot);
    if (!$('probe-text').value) $('probe-text').value = probe ? probe(cfg.duck_name || 'deine Ente')
      : `Hallo, ich bin ${name}. So klinge ich jetzt. Gefällt dir meine Stimme?`;
    renderNow();
    renderEngines();
    renderPanel();
    const d = $('duckness');
    if (document.activeElement !== d) d.value = w.entenhaft ?? 0.45;
    d.style.setProperty('--_fill', `${Math.round(d.value * 100)}%`);
    // Entworfene Stimmen klingen schon nach Ente – der Filter gilt nur für Piper und die Browser-Stimme (seit 0.37.8)
    const qwen = motorJetzt() === 'qwen';
    d.disabled = qwen;
    $('duckness-help').textContent = qwen
      ? 'Bei entworfenen Stimmen aus – sie klingen schon so, wie du sie beschrieben hast.'
      : 'Höher und nasaler. Für Thorsten & Co. etwa die Mitte.';
    for (const r of document.querySelectorAll('[data-voice]')) r.checked = w[r.dataset.voice] === r.value;
    for (const [id, key] of [['klang-hoehe', 'klang_hoehe'], ['klang-farbe', 'klang_farbe']]) {
      const el = $(id);
      if (document.activeElement !== el) el.value = w[key] ?? 0;
      el.style.setProperty('--_fill', `${Math.round(((el.value - el.min) / (el.max - el.min)) * 100)}%`);
    }
    setKlang(w.klang_hoehe, w.klang_farbe);
    $('chat-mode').checked = !!w.plaudern;
    if (document.activeElement !== $('local-url')) $('local-url').value = w.lokal_adresse || '';
    renderBrain();
  }

  function renderNow() {
    const m = motorJetzt();
    const label = { browser: 'Browser-Stimme', piper: 'Piper', qwen: 'Qwen3-TTS' }[m];
    let voice = '';
    if (m === 'piper') voice = (info.piper.stimmen.find((v) => v.id === werte().stimme_piper) || {}).name || '';
    if (m === 'qwen') voice = (info.qwen.stimmen.find((v) => v.id === werte().stimme_qwen) || {}).name || '';
    const now = $('probe-now');
    now.replaceChildren();
    // Tempo der eigenen Stimme (seit 0.37.9): Sekunden Rechnen je Sekunde Sprache
    const tempo = (info.tempo || {})[m];
    const langsam = m === 'qwen' && tempo && tempo.faktor > 1.15;
    const ersatz = info.rueckfall === 'piper' ? 'Piper' : 'die Browser-Stimme';
    if (info.bereit && langsam) {
      now.append(el('i', 'dot dot--warning'), document.createTextNode(
        ` ${label}${voice ? ` · ${voice}` : ''}: rechnet ${String(tempo.faktor.toFixed(1)).replace('.', ',')} s je Sekunde Sprache – `
        + `zu langsam fürs Gespräch, deshalb spricht meist ${ersatz}.`
        + (info.qwen.geraet === 'cpu' ? ' Auf diesem Gerät läuft Qwen auf dem Prozessor; hier ist Piper die bessere Wahl.' : '')));
    } else if (info.bereit) {
      now.append(el('i', 'dot dot--good'), document.createTextNode(` Spricht mit ${label}${voice ? ` · ${voice}` : ''}`
        + (tempo && m !== 'browser' ? ` · ${String(tempo.faktor.toFixed(2)).replace('.', ',')} s je Sekunde Sprache` : '')));
    } else {
      now.append(el('i', 'dot dot--warning'), document.createTextNode(` ${label}: ${info.grund} – bis dahin spricht ${m === 'qwen' ? ersatz : 'die Browser-Stimme'}.`));
      // Download-Fortschritt des Sprechmodells (seit 0.37.7); bricht er ab, geht er beim nächsten Start weiter
      const job = (info.jobs || {}).sprechmodell;
      if (m === 'qwen' && job && job.laeuft && job.anteil != null) {
        const p = el('div', 'run-progress');
        p.append(bar(job.anteil), el('span', null, `${Math.round(job.anteil * 100)} %`));
        now.append(p);
      }
    }
  }

  function engineState(id) {
    if (id === 'browser') return ['bereit', 'good'];
    const inst = info[id] && info[id].installiert;
    if (!inst) return ['nicht installiert', ''];
    if (id === 'piper') return info.piper.stimmen.some((v) => v.geladen) ? ['bereit', 'good'] : ['noch keine Stimme', ''];
    return info.qwen.stimmen.length ? ['bereit', 'good'] : ['noch keine Stimme', ''];
  }

  function renderEngines() {
    const box = $('engines');
    box.replaceChildren(...ENGINES.map((e) => {
      const on = motorJetzt() === e.id;
      const card = el('label', `engine${on ? ' is-on' : ''}`);
      const radio = el('input');
      radio.type = 'radio'; radio.name = 'motor'; radio.value = e.id; radio.checked = on;
      radio.addEventListener('change', async () => {
        if (await save({ stimme_motor: e.id })) { if (!kopf()) info.motor = e.id; render(); }
      });
      const [stateText, tone] = engineState(e.id);
      const head = el('span', 'engine-head');
      head.append(el('span', 'engine-name', e.name), el('span', `chip${tone ? ` chip--${tone}` : ''}`, stateText));
      const facts = el('span', 'engine-facts', e.facts.join(' · '));
      card.append(radio, head, el('span', 'engine-text', e.text), facts);
      return card;
    }));
  }

  function renderPanel() {
    const panel = $('engine-panel');
    const m = motorJetzt();
    if (m === 'browser') return panel.replaceChildren(browserPanel());
    if (m === 'piper') return panel.replaceChildren(...piperPanel());
    return panel.replaceChildren(...qwenPanel());
  }

  // ── Browser ───────────────────────────────────────────────────────────
  function browserPanel() {
    const card = el('section', 'card set-card');
    const f = el('label', 'field');
    f.append(el('span', 'field-label', 'Stimme des Browsers'));
    const sel = el('select', 'select');
    const voices = h.germanVoices();
    sel.append(new Option('Automatisch', ''), ...voices.map((v) => new Option(`${v.name}${v.localService ? '' : ' (online)'}`, v.name)));
    sel.value = h.currentVoice() || '';
    sel.addEventListener('change', () => { h.setVoice(sel.value); h.speak(`Hallo, ich bin ${cfg.duck_name || 'deine Ente'}.`); });
    f.append(sel);
    card.append(f, el('p', 'field-help', 'Online-Stimmen schicken den Text an Microsoft bzw. Google. Lokale Stimmen bleiben auf dem PC.'));
    return card;
  }

  // ── Installation (Piper, Qwen) ───────────────────────────────────────
  // fehlt: Module, die noch fehlen – ist das Hauptpaket schon da, wird repariert statt neu installiert
  function installBlock(paket, label, mb, extra, fehlt = null, haupt = null) {
    const job = (info.installation || {})[paket];
    const repair = !!(fehlt && fehlt.length && haupt && !fehlt.includes(haupt));
    const wrap = el('section', 'card install');
    const row = el('div', 'install-row');
    const txt = el('div', 'install-text');
    if (repair) {
      txt.append(el('b', null, `${label} ist nicht vollständig installiert`));
      txt.append(el('span', null, `Es fehlt: ${fehlt.join(', ')}. Reparieren lädt nur das Fehlende nach.`));
    } else {
      txt.append(el('b', null, `${label} ist noch nicht installiert`));
      txt.append(el('span', null, `Einmalig ≈ ${mb >= 1000 ? `${(mb / 1000).toFixed(1).replace('.', ',')} GB` : `${mb} MB`} aus dem Internet, danach offline.`));
    }
    const btn = el('button', 'btn btn--primary btn--sm');
    btn.type = 'button';
    btn.innerHTML = DOWN;
    btn.append(document.createTextNode(job && job.laeuft ? 'Installiert …' : repair ? 'Reparieren' : `${label} installieren`));
    btn.disabled = !!(job && job.laeuft);
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const r = await api('/api/stimme/installieren', 'POST', { paket, gpu: gpu || info.gpu_vorschlag || 'cpu' });
      if (!r.ok) { toast(r.fehler || 'Ging nicht', true); btn.disabled = false; }
    });
    row.append(txt, btn);
    wrap.append(row);
    if (extra) wrap.append(extra);
    if (job) wrap.append(jobView(job, `${label} ist installiert.`));
    return wrap;
  }

  function jobView(job, doneText) {
    const box = el('div', 'job');
    const status = el('p', `job-state${job.fehler ? ' is-bad' : ''}`);
    // Seit 0.38.38 mit echtem Fortschritt beim Herunterladen (Datei, MB von MB, Balken – fortschritt.js)
    if (job.laeuft) status.textContent = installStand(job);
    else if (job.fehler) status.textContent = `Hat nicht geklappt: ${job.fehler}`;
    else status.textContent = doneText;
    box.append(status);
    if (job.laeuft) box.append(installBalken(el, job));
    if (job.zeilen && job.zeilen.length) {
      const d = el('details', 'log-box');
      d.open = !!job.fehler;
      d.append(el('summary', null, `Protokoll (${job.zeilen.length} Zeilen)`), el('pre', null, job.zeilen.join('\n')));
      box.append(d);
    }
    return box;
  }

  function bar(frac) {
    const b = el('div', 'bar');
    const i = el('i');
    i.style.width = `${Math.round((frac || 0) * 100)}%`;
    b.append(i);
    return b;
  }

  // ── Piper ─────────────────────────────────────────────────────────────
  function piperPanel() {
    const out = [];
    if (!info.piper.installiert) out.push(installBlock('piper', 'Piper', 40));
    const card = el('section', 'card voices');
    card.append(el('h3', null, 'Stimmen'));
    const list = el('ul', 'voice-list');
    for (const v of info.piper.stimmen) {
      const li = el('li', `vrow${werte().stimme_piper === v.id ? ' is-on' : ''}`);
      const pick = el('label', 'voice-pick');
      const r = el('input');
      r.type = 'radio'; r.name = 'piper-voice'; r.value = v.id; r.checked = werte().stimme_piper === v.id;
      r.disabled = !v.geladen;
      r.addEventListener('change', async () => { if (await save({ stimme_piper: v.id }, `Stimme: ${v.name}`)) render(); });
      const txt = el('span', 'voice-text');
      txt.append(el('span', 'voice-name', v.name), el('span', 'voice-art', v.art));
      pick.append(r, txt);
      li.append(pick);
      const job = (info.jobs || {})[`piper:${v.id}`];
      const side = el('div', 'voice-side');
      if (v.geladen) {
        const ok = el('span', 'voice-ok');
        ok.innerHTML = CHECK;
        ok.append(document.createTextNode('geladen'));
        side.append(ok);
      } else if (job && job.laeuft) {
        side.append(bar(job.anteil), el('span', 'voice-size', `${Math.round((job.anteil || 0) * 100)} %`));
      } else {
        if (job && job.fehler) side.append(el('span', 'voice-err', 'fehlgeschlagen'));
        const b = el('button', 'btn btn--sm');
        b.type = 'button';
        b.innerHTML = DOWN;
        b.append(document.createTextNode(`Laden · ${v.mb} MB`));
        b.addEventListener('click', async () => {
          b.disabled = true;
          const res = await api('/api/stimme/laden', 'POST', { stimme: v.id });
          if (!res.ok) { toast(res.fehler || 'Ging nicht', true); b.disabled = false; }
        });
        side.append(b);
      }
      li.append(side);
      list.append(li);
    }
    card.append(list, el('p', 'field-help', 'Stimmen von rhasspy/piper-voices auf Hugging Face. Thorsten-Voice ist frei (CC0). Gespeichert im lokalen App-Datenordner, nicht in OneDrive.'));
    out.push(card);
    return out;
  }

  // ── Qwen3-TTS ─────────────────────────────────────────────────────────
  function gpuPicker() {
    const box = el('div', 'field');
    gpu = gpu || info.gpu_vorschlag || 'cpu';
    box.append(el('span', 'field-label', 'Grafikkarte'));
    const seg = el('div', 'seg');
    seg.setAttribute('role', 'radiogroup');
    for (const id of ['amd', 'nvidia', 'cpu']) {
      const l = el('label');
      const r = el('input');
      r.type = 'radio'; r.name = 'qwen-gpu'; r.value = id; r.checked = gpu === id;
      r.addEventListener('change', () => { gpu = id; renderPanel(); });
      l.append(r, el('span', null, GPU_LABEL[id]));
      seg.append(l);
    }
    box.append(seg);
    const found = (info.grafikkarten || []).join(', ');
    box.append(el('p', 'field-help', `${found ? `Gefunden: ${found}. ` : ''}${GPU_HELP[gpu]}`));
    return box;
  }

  function qwenPanel() {
    const out = [];
    const q = info.qwen;
    if (!q.installiert) {
      out.push(installBlock('qwen', 'Qwen3-TTS', 3500, gpuPicker(), q.fehlt, 'qwen_tts'));
    }
    // Entwerfen
    const design = el('section', 'card designer');
    design.append(el('h3', null, istEnte() ? 'Entenstimme entwerfen' : 'Stimme entwerfen'));
    design.append(el('p', 'field-help', q.uebersetzer
      ? t('stimme.entwerfen_hilfe', {}, 'Beschreib die Stimme auf Deutsch – Alter, Höhe, Tempo, Charakter. Knowlin übersetzt sie vor dem Entwerfen ins Englische, weil das Modell Beschreibungen so am genauesten umsetzt. Daraus entstehen drei Fassungen derselben Probe; die schönste übernimmst du.')
      : 'Beschreib die Stimme – Alter, Höhe, Tempo, Charakter. Daraus entstehen drei Fassungen derselben Probe; die schönste übernimmst du.'));
    const presets = el('div', 'presets');
    for (const [label, text] of Object.entries((kopf() ? q.vorlagen_kopf : q.vorlagen) || {})) {
      const c = el('button', 'chip', label);
      c.type = 'button';
      c.addEventListener('click', () => { designText = text; ta.value = text; });
      presets.append(c);
    }
    const ta = el('textarea', 'input design-text');
    ta.rows = 3;
    ta.maxLength = 500;
    ta.placeholder = kopf() ? 'z. B. Eine ruhige, tiefe, warme Stimme – seriös und ein wenig geheimnisvoll, langsames Tempo, klare Aussprache …'
      : BEISPIEL[modulJetzt()] || (istEnte() ? BEISPIEL.duckpilot : 'z. B. Ein ruhiger, neugieriger Roboter mit warmer, mittlerer Stimme …');
    // Vorlage für Knowlin (Wunsch des Maintainers: ruhig, tief, seriös) – änderbar
    if (kopf() && !designText) designText = 'Eine ruhige, tiefe, warme Stimme eines erwachsenen Wesens – seriös, klar und ein wenig geheimnisvoll, langsames Tempo, deutliche Aussprache.';
    // Entwurf mit dem Namen der Verkörperung (Reachy, Open Duck) – vom Server, änderbar
    if (!kopf() && !designText && q.entwurf) designText = q.entwurf;
    ta.value = designText;
    ta.addEventListener('input', () => { designText = ta.value; });
    const job = (info.jobs || {}).entwurf;
    const go = el('button', 'btn btn--primary btn--sm', job && job.laeuft ? 'Entwirft …' : 'Stimme entwerfen');
    go.type = 'button';
    go.disabled = !q.installiert || !!(job && job.laeuft);
    go.addEventListener('click', async () => {
      go.disabled = true;
      const r = await api('/api/stimme/entwerfen', 'POST', { beschreibung: ta.value, fassungen: 3, ...fuer() });
      if (!r.ok) { toast(r.fehler || 'Ging nicht', true); go.disabled = false; }
    });
    const actions = el('div', 'design-actions');
    actions.append(go);
    if (!q.modelle.entwurf) actions.append(el('span', 'field-help', `Beim ersten Mal lädt das Entwurfsmodell (≈ ${(q.mb.entwurf / 1000).toFixed(1).replace('.', ',')} GB).`));
    design.append(presets, ta, actions);
    if (job) {
      const st = el('p', `job-state${job.fehler ? ' is-bad' : ''}`, job.fehler ? `Hat nicht geklappt: ${job.fehler}` : job.text);
      design.append(st);
      // was wirklich ans Modell ging – damit man sieht, ob die Übersetzung passt
      const WEG = { claude: 'von Claude übersetzt', lokal: 'vom lokalen Modell übersetzt', vorlage: 'englische Fassung der Vorlage' };
      if (job.modell_text && WEG[job.weg]) {
        const d = el('details', 'design-sent');
        d.append(el('summary', null, `An das Modell (${WEG[job.weg]})`), el('p', null, job.modell_text));
        design.append(d);
      } else if (job.weg === 'deutsch') {
        design.append(el('p', 'field-help', 'Ohne Claude-Schlüssel und lokales Modell ging die Beschreibung auf Deutsch ans Modell. Das klappt auch, Feinheiten kommen auf Englisch meist genauer an.'));
      }
      if (job.laeuft) design.append(el('div', 'bar is-busy'));
    }
    if (info.fassungen && info.fassungen.length) {
      const takes = el('div', 'takes');
      info.fassungen.forEach((f, i) => {
        const t = el('div', 'take');
        const play = el('button', 'btn btn--ghost btn--sm');
        play.type = 'button';
        play.innerHTML = PLAY;
        play.append(document.createTextNode(`Fassung ${i + 1} · ${String(f.sekunden).replace('.', ',')} s`));
        play.addEventListener('click', () => h.playPlan({ motor: 'qwen', teile: [{ art: 'text', text: '', id: f.id }] }, { send: h.send }));
        const nameIn = el('input', 'input take-name');
        nameIn.type = 'text'; nameIn.maxLength = 40; nameIn.value = `${kopf() ? kopfName() : cfg.duck_name || 'Ente'} ${i + 1}`;
        nameIn.setAttribute('aria-label', `Name für Fassung ${i + 1}`);
        const adopt = el('button', 'btn btn--sm', 'Übernehmen');
        adopt.type = 'button';
        adopt.addEventListener('click', async () => {
          adopt.disabled = true;
          const r = await api('/api/stimme/uebernehmen', 'POST', { fassung: f.id, name: nameIn.value, ...fuer() });
          if (!r.ok) { toast(r.fehler || 'Ging nicht', true); adopt.disabled = false; return; }
          toast(kopf() ? `„${nameIn.value}“ ist jetzt die Stimme von ${kopfName()}`
            : istEnte() ? `„${nameIn.value}“ ist jetzt die Stimme der Ente` : `„${nameIn.value}“ ist jetzt die Stimme von ${cfg.duck_name || 'Reachy'}`);
          load();
        });
        t.append(play, nameIn, adopt);
        takes.append(t);
      });
      design.append(takes);
    }
    out.push(design);
    // Eigene Stimmen
    const mine = el('section', 'card voices');
    mine.append(el('h3', null, 'Entworfene Stimmen'));
    if (!q.stimmen.length) {
      mine.append(el('p', 'field-help', 'Noch keine – entwirf oben die erste.'));
    } else {
      const list = el('ul', 'voice-list');
      for (const v of q.stimmen) {
        const on = werte().stimme_qwen === v.id;
        const li = el('li', `vrow${on ? ' is-on' : ''}`);
        const pick = el('label', 'voice-pick');
        const r = el('input');
        r.type = 'radio'; r.name = 'qwen-voice'; r.checked = on;
        r.addEventListener('change', async () => { if (await save({ stimme_qwen: v.id }, `Stimme: ${v.name}`)) render(); });
        const txt = el('span', 'voice-text');
        const nutzer = (info.figuren || []).filter((f) => f.stimme_qwen === v.id).map((f) => f.name);
        txt.append(el('span', 'voice-name', v.name || v.id), el('span', 'voice-art', v.beschreibung || ''));
        if (nutzer.length) txt.append(el('span', 'voice-art', tr(`Stimme von ${nutzer.join(', ')}`)));
        pick.append(r, txt);
        const del = el('button', 'btn btn--ghost btn--sm', 'Löschen');
        del.type = 'button';
        del.addEventListener('click', async () => {
          if (deleteArmed !== v.id) {
            deleteArmed = v.id;
            del.textContent = 'Wirklich löschen?';
            setTimeout(() => { if (deleteArmed === v.id) { deleteArmed = null; del.textContent = 'Löschen'; } }, 4000);
            return;
          }
          deleteArmed = null;
          await api(`/api/stimme/qwen/${encodeURIComponent(v.id)}`, 'DELETE');
          load();
        });
        li.append(pick, del);
        list.append(li);
      }
      mine.append(list);
    }
    const qf = el('div', 'field');
    qf.append(el('span', 'field-label', 'Qualität beim Sprechen'));
    const seg = el('div', 'seg');
    for (const [id, label] of [['schnell', 'Schnell · 0,6 Mrd.'], ['hoch', 'Hoch · 1,7 Mrd.']]) {
      const l = el('label');
      const r = el('input');
      r.type = 'radio'; r.name = 'qwen-q'; r.value = id; r.checked = (werte().qwen_qualitaet || 'schnell') === id;
      r.addEventListener('change', () => save({ qwen_qualitaet: id }, `Qualität: ${label}`));
      l.append(r, el('span', null, label));
      seg.append(l);
    }
    qf.append(seg);
    if (q.geraet) qf.append(el('p', 'field-help', q.geraet === 'gpu' ? 'Läuft auf der Grafikkarte.'
      : 'Läuft auf dem Prozessor – für flüssige Gespräche zu langsam. Lange Antworten spricht dann Piper (falls geladen) oder die Browser-Stimme. Ohne passende Grafikkarte ist Piper die bessere Wahl.'));
    mine.append(qf);
    out.push(mine);
    return out;
  }

  // ── Lokales Modell (Ollama) ──────────────────────────────────────────
  async function loadBrain() {
    brain = await api('/api/gehirn').catch(() => null);
    renderBrain();
  }

  function renderBrain() {
    if (!brain) return;
    const w = werte();
    const st = $('local-state');
    st.replaceChildren();
    if (brain.laeuft) {
      st.append(el('i', 'dot dot--good'), document.createTextNode(` Ollama läuft · ${brain.modelle.length} Modell${brain.modelle.length === 1 ? '' : 'e'} vorhanden`));
    } else {
      st.append(el('i', 'dot dot--warning'), document.createTextNode(' Ollama nicht gefunden. Von '));
      const a = el('a', null, 'ollama.com');
      a.href = 'https://ollama.com/download'; a.target = '_blank'; a.rel = 'noopener';
      st.append(a, document.createTextNode(' installieren und starten – es rechnet auf deiner Grafikkarte.'));
      const nochmal = el('button', 'btn btn--ghost btn--sm', 'Erneut prüfen');
      nochmal.type = 'button';
      nochmal.addEventListener('click', () => { st.textContent = 'Prüfe Ollama …'; loadBrain(); });
      st.append(' ', nochmal);
    }
    const sel = $('local-model');
    const chosen = w.lokal_modell || brain.gewaehlt || '';
    const names = [...new Set([...(brain.modelle || []), ...(chosen ? [chosen] : [])])];
    sel.replaceChildren(new Option(names.length ? 'Bitte wählen' : 'Noch kein Modell', ''), ...names.map((n) => new Option(n, n)));
    sel.value = chosen;
    sel.disabled = !names.length;
    const sug = $('local-suggest');
    const pulls = (info && info.ollama) || brain.laden || {};
    sug.replaceChildren(...Object.entries(brain.vorschlaege || {}).map(([tag, desc]) => {
      const li = el('li');
      const txt = el('div', 'sug-text');
      txt.append(el('b', null, tag), el('span', null, desc));
      li.append(txt);
      const have = (brain.modelle || []).some((m) => m === tag || m.startsWith(`${tag}-`));
      const job = pulls[tag];
      if (have) li.append(el('span', 'voice-ok', 'vorhanden'));
      else if (job && job.laeuft) li.append(bar(job.anteil), el('span', 'voice-size', job.anteil ? `${Math.round(job.anteil * 100)} %` : String(job.status || '').slice(0, 24)));
      else {
        const b = el('button', 'btn btn--sm');
        b.type = 'button';
        b.innerHTML = DOWN;
        b.append(document.createTextNode('Laden'));
        b.disabled = !brain.laeuft;
        b.addEventListener('click', async () => {
          b.disabled = true;
          const r = await api('/api/gehirn/laden', 'POST', { modell: tag });
          if (!r.ok) { toast(r.fehler || 'Ging nicht', true); b.disabled = false; }
        });
        if (job && job.fehler) li.append(el('span', 'voice-err', 'fehlgeschlagen'));
        li.append(b);
      }
      return li;
    }));
    // fertig geladene Modelle → Liste neu holen
    if (Object.values(pulls).some((j) => !j.laeuft && !j.fehler && j.status === 'geladen') && brain.laeuft
        && Object.keys(pulls).some((t) => !(brain.modelle || []).some((m) => m.startsWith(t)))) {
      setTimeout(loadBrain, 400);
    }
  }

  // ── Bedienung ─────────────────────────────────────────────────────────
  $('probe').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('probe-play');
    btn.disabled = true;
    const r = await api('/api/stimme/probe', 'POST', { text: $('probe-text').value, ...fuer() }).catch(() => null);
    btn.disabled = false;
    if (!r || !r.ok) { toast('Probe ging nicht', true); return; }
    h.playPlan(r.sprache, { send: h.send, mood: 'fröhlich', goofy: !!cfg.goofy, energie: cfg.energie,
      onError: (why) => toast(`Eigene Stimme hakt: ${why}`, true) });
  });
  // Klangsignatur: sofort hörbar, gespeichert beim Loslassen
  const klangJetzt = () => setKlang($('klang-hoehe').value, $('klang-farbe').value);
  for (const [id, key] of [['klang-hoehe', 'klang_hoehe'], ['klang-farbe', 'klang_farbe']]) {
    const el = $(id);
    el.addEventListener('input', () => { klangJetzt(); el.style.setProperty('--_fill', `${Math.round(((el.value - el.min) / (el.max - el.min)) * 100)}%`); });
    el.addEventListener('change', () => { save({ [key]: Number(el.value) }); playSound('greet'); });
  }
  $('klang-probe').addEventListener('click', () => { klangJetzt(); playSound('greet'); });
  $('klang-wuerfeln').addEventListener('click', async () => {
    const hoehe = Math.round((Math.random() * 8 - 4) * 2) / 2;
    const farbe = Math.round((Math.random() * 1.6 - 0.8) * 10) / 10;
    $('klang-hoehe').value = hoehe; $('klang-farbe').value = farbe;
    klangJetzt();
    playSound('greet');
    await save({ klang_hoehe: hoehe, klang_farbe: farbe }, 'Neue Klangsignatur');
  });
  const duck = $('duckness');
  duck.addEventListener('input', () => duck.style.setProperty('--_fill', `${Math.round(duck.value * 100)}%`));
  duck.addEventListener('change', () => save({ entenhaft: Number(duck.value) }));
  for (const r of document.querySelectorAll('[data-voice]')) {
    r.addEventListener('change', async () => {
      const key = r.dataset.voice;
      const label = key === 'gehirn' ? ({ lokal: 'Denkt mit dem lokalen Modell', anbieter: 'Denkt mit dem anderen Modell' }[r.value] || 'Denkt mit Claude')
        : t(istEnte() ? 'stimme.laute' : 'stimme.laute_ohne_ente', { wert: tr(r.parentElement.textContent.trim()) },
          istEnte() ? 'Entenlaute: {wert}' : 'Laute: {wert}');
      if (key === 'gehirn' && r.value === 'lokal' && !werte().lokal_modell) toast('Erst unten ein Modell wählen – bis dahin denkt Claude.');
      if (key === 'gehirn' && r.value === 'anbieter' && !werte().anbieter_modell) toast('Erst unten Anbieter, Schlüssel und Modell wählen – bis dahin denkt Claude.');
      await save({ [key]: r.value }, label);
    });
  }
  $('chat-mode').addEventListener('change', (e) => save({ plaudern: e.target.checked }, e.target.checked ? 'Plaudern an' : 'Plaudern aus'));
  $('local-model').addEventListener('change', (e) => save({ lokal_modell: e.target.value }, e.target.value ? `Lokales Modell: ${e.target.value}` : null));
  $('local-url').addEventListener('change', async (e) => { if (await save({ lokal_adresse: e.target.value })) loadBrain(); });

  return { load, update, config };
}
