// Einstellungen: Felder mit data-set, Schlüssel, echte Physik, Pollens Robotermodell, Über
// (seit 0.38.17 aus app.js ausgelagert). Speichern geht immer über save() – dieselbe Prüfung wie am Server.
import { $, el } from './ui.js';
import { initMcp } from './mcp.js';
import { initSettingsNav } from './settingsnav.js';
import { offenlegen } from './offenlegung.js';

export function initEinstellungen({ api, toast, showView, getConfig, scene }) {
  let settings = null;
  const SIGN_LABELS = ['Nacken', 'Nicken', 'Drehen', 'Neigen'];
  let settingsNav = null;
  async function loadSettings() {
    settings = await api('/api/settings');
    renderSettings();
    settingsNav = settingsNav || initSettingsNav({ $, el, showView: (v, p) => showView(v, p) });
    settingsNav.render();
    api('/api/physik').then(renderPhysik).catch(() => {});
  }


  // Echte Physik (Einstellungen → Körper)
  function renderPhysik(msg) {
    const state = $('physik-state');
    const acts = $('physik-actions');
    state.replaceChildren();
    acts.replaceChildren();
    const dot = (tone) => el('i', `dot dot--${tone}`);
    const button = (label, cls, fn) => {
      const b = el('button', `btn btn--sm ${cls || ''}`, label);
      b.type = 'button';
      b.addEventListener('click', async () => { b.disabled = true; await fn(); });
      return b;
    };
    const inst = (msg.installation || {}).physik;
    const job = msg.policies.job || {};
    if (!msg.installiert.physik) {
      state.append(dot('warning'), document.createTextNode(inst && inst.laeuft ? ` Installiert MuJoCo … ${(inst.zeilen || []).slice(-1)[0] || ''}`
        : inst && inst.fehler ? ` Installation fehlgeschlagen: ${inst.fehler}` : ' Dafür fehlen MuJoCo und ONNX Runtime (≈ 120 MB, läuft auf dem Prozessor).'));
      if (!(inst && inst.laeuft)) acts.append(button('MuJoCo installieren', 'btn--primary', () => api('/api/stimme/installieren', 'POST', { paket: 'physik', gpu: 'cpu' })));
    } else if (!msg.policies.bereit) {
      state.append(dot('warning'), document.createTextNode(job.laeuft ? ` ${job.text}` : job.fehler ? ` Laden fehlgeschlagen: ${job.fehler}`
        : ' Noch fehlen Pollens Policies (Gehen, Hinsetzen, Aufheben, Schießen, Purzelbaum – zusammen wenige MB vom Hugging Face Hub).'));
      if (!job.laeuft) acts.append(button('Pollens Policies laden', 'btn--primary', () => api('/api/physik/laden', 'POST')));
    } else {
      const roles = Object.entries(msg.policies.rollen).filter(([, on]) => on).map(([r]) => msg.policies.namen[r]);
      const live = msg.aktiv ? `läuft · ${msg.motor}` : msg.sim_physik ? `startet nicht: ${msg.fallback || msg.problem}` : 'bereit';
      state.append(dot(msg.aktiv || !msg.sim_physik ? 'good' : 'warning'), document.createTextNode(` ${live}. Policies: ${roles.join(', ')}`
        + `${msg.policies.geladen ? ` (geladen ${msg.policies.geladen})` : ''}.`));
      if (msg.aktiv) acts.append(button('Ente zurück auf die Füße', '', async () => { await api('/api/physik/zuruecksetzen', 'POST'); loadSettings(); }));
      acts.append(button('Policies neu laden', 'btn--ghost', () => api('/api/physik/laden', 'POST')));
      if (!msg.installiert.bam) {
        const bamJob = (msg.installation || {}).bam;
        acts.append(button(bamJob && bamJob.laeuft ? 'Installiert …' : 'Motormodell wie im Training (BAM)', 'btn--ghost',
          () => api('/api/stimme/installieren', 'POST', { paket: 'bam', gpu: 'cpu' })));
      }
    }
  }

  function renderUsage(v) {
    // Tokenverbrauch der letzten 7 Tage: nur Zahlen, keine Inhalte
    const el = $('usage-line');
    if (!v || !v.summe) { el.textContent = ''; return; }
    const s = v.summe, fmt = (n) => Number(n || 0).toLocaleString('de-DE');
    const parts = [`Letzte ${v.tage} Tage: ${fmt(s.anfragen)} Anfragen an Claude`];
    if (v.pro_anfrage) parts.push(`≈ ${fmt(v.pro_anfrage)} Tokens je Anfrage`);
    if (v.cache_anteil != null) parts.push(`${Math.round(v.cache_anteil * 100)} % aus dem Cache (kostet nur einen Bruchteil)`);
    if (s.ohne_claude) parts.push(`${fmt(s.ohne_claude)} Befehle ohne Claude`);
    el.textContent = parts.join(' · ');
  }

  let mcpPanel = null;
  function renderSettings() {
    const w = settings.werte;
    mcpPanel = mcpPanel || initMcp({ $, api, toast });
    mcpPanel.load();
    $('welcome').hidden = !getConfig().needs_setup;
    for (const input of document.querySelectorAll('[data-set]')) {
      const key = input.dataset.set;
      if (input.tagName === 'SELECT' && !input.options.length) {
        const opts = settings.auswahl[key];
        if (opts) {
          for (const [value, label] of Array.isArray(opts) ? opts.map((o) => [o, o]) : Object.entries(opts)) {
            input.append(new Option(label, value));
          }
        }
      }
      if (document.activeElement === input) continue;
      if (input.type === 'checkbox') input.checked = !!w[key];
      else if (input.type === 'radio') input.checked = String(w[key]) === input.value;
      else input.value = w[key] ?? '';
    }
    renderUsage(settings.verbrauch);
    for (const r of document.querySelectorAll('.robot-only')) r.hidden = w.backend !== 'robotd';
    document.querySelector('.sim-only').hidden = w.backend !== 'sim';
    $('szene-reset').hidden = w.backend === 'robotd';
    document.querySelector('.whisper-only').hidden = w.stt !== 'whisper';
    requestAnimationFrame(() => offenlegen());   // Zusatzfelder nur bei passender Wahl (0.38.14)
    const help = {
      browser: 'Edge schickt die Aufnahme zur Erkennung an Microsoft, Chrome an Google. Bequem, aber das Audio verlässt den PC.',
      whisper: settings.whisper_installiert
        ? 'Erkennung auf diesem PC mit Whisper – das Audio bleibt hier. Das Modell wird beim ersten Mal geladen.'
        : 'Erkennung auf diesem PC mit Whisper. Dafür einmalig in der Eingabeaufforderung: "%LOCALAPPDATA%\\duckpilot\\venv\\Scripts\\python" -m pip install faster-whisper – danach Knowlin neu starten.',
      aus: 'Nur Tippen und Knöpfe.',
    }[w.stt];
    $('stt-help').textContent = help;
    const signs = $('signs');
    if (!signs.children.length) {
      SIGN_LABELS.forEach((label, i) => {
        const l = el('label');
        const cb = el('input');
        cb.type = 'checkbox';
        cb.dataset.sign = i;
        cb.addEventListener('change', () => {
          const next = [...settings.werte.head_signs];
          next[i] = cb.checked ? -1 : 1;
          save({ head_signs: next });
        });
        l.append(cb, el('span', null, `${label} umkehren`));
        signs.append(l);
      });
    }
    signs.querySelectorAll('input').forEach((cb) => { cb.checked = w.head_signs[+cb.dataset.sign] < 0; });
    // Schlüssel
    const k = settings.schluessel;
    const src = { tresor: `in der ${k.tresor_name}`, umgebung: 'aus der Umgebungsvariable', datei: 'aus der Datei .env', toml: 'aus duckpilot.toml' }[k.quelle];
    const ks = $('key-state');
    ks.replaceChildren();
    if (k.gesetzt) {
      ks.append(el('b', null, '✓ Hinterlegt'), document.createTextNode(` ${k.hinweis}, ${src}.`));
      if (k.umgebung_auch) ks.append(document.createTextNode(' Die zusätzliche Umgebungsvariable wird ignoriert.'));
    } else {
      ks.textContent = 'Noch kein Schlüssel – Claude ist aus, einfache Befehle funktionieren.';
    }
    $('key-delete').hidden = k.quelle !== 'tresor';
    $('key-test').hidden = !k.gesetzt;
    $('key-input').placeholder = k.gesetzt ? 'Neuen Schlüssel einfügen, um ihn zu ersetzen' : 'sk-ant-…';
    if (!k.tresor) {
      $('key-form').hidden = true;
      // Nur ein Problem, wenn es gar keinen Schlüssel gibt – kommt er aus der Umgebung, ist alles gut
      if (!k.gesetzt) setKeyMsg(`Kein ${k.tresor_name} verfügbar. Schlüssel bitte als Umgebungsvariable ANTHROPIC_API_KEY setzen.`, false);
    }
    // Über
    const about = $('about');
    about.replaceChildren();
    for (const [dt, dd] of [['Version', settings.version], ['Einstellungen', settings.pfade.einstellungen],
      ['Gedächtnis', settings.pfade.gedaechtnis || 'aus'], ['Fenster', settings.app_modus ? 'eigenes Programmfenster' : 'Browser']]) {
      const d = el('div');
      d.append(el('dt', null, dt), el('dd', null, dd));
      about.append(d);
    }
  }

  // Pollens Robotermodell (3D-Ansicht und Physik) – von GitHub geladen, auf dem PC aufbereitet
  function renderModell(m) {
    if (!m) return;
    const job = m.job || {};
    const was = { paket: 'mitgeliefert', geladen: 'von GitHub geladen' };
    const teile = [`3D-Ansicht: ${was[m.ansicht] || 'fehlt'}`, `Physik: ${was[m.physik] || 'fehlt'}`];
    $('modell-text').textContent = `${teile.join(' · ')}. Quelle: ${m.repo}, Stand ${m.stand}${m.geladen ? `, geladen ${m.geladen}` : ''}.`;
    const msg = $('modell-msg');
    msg.textContent = job.laeuft ? job.text : job.fehler ? `Laden fehlgeschlagen: ${job.fehler}` : (job.text || '');
    msg.className = `field-msg ${job.fehler ? 'bad' : job.text && !job.laeuft ? 'ok' : ''}`;
    $('modell-laden').disabled = !!job.laeuft;
    $('modell-laden').textContent = m.ansicht ? 'Von GitHub neu laden' : 'Von GitHub laden';
    if (m.ansicht) scene.loadOriginal();
  }

  function setKeyMsg(text, ok) {
    const m = $('key-msg');
    m.textContent = text;
    m.className = `field-msg ${ok === true ? 'ok' : ok === false ? 'bad' : ''}`;
  }

  async function save(patch) {
    const r = await api('/api/settings', 'POST', patch);
    if (!r.ok) { toast(r.fehler || 'Nicht gespeichert'); await loadSettings(); return; }
    settings = r.einstellungen;
    renderSettings();
    if (r.geaendert && r.geaendert.length) {
      toast(patch.backend ? (patch.backend === 'sim' ? 'Wechsle zum Simulator …' : 'Verbinde mit dem Roboter …') : 'Gespeichert');
      if (patch.backend) scene.clearTrail();
    }
  }

  for (const input of document.querySelectorAll('[data-set]')) {
    const key = input.dataset.set;
    const commit = () => {
      let value = input.type === 'checkbox' ? input.checked : input.value;
      if ('num' in input.dataset) value = Number(value);
      if (input.type === 'radio' && !input.checked) return;
      if (settings && settings.werte[key] === value) return;
      if (key === 'sprache') { save({ sprache: value }).then(() => location.reload()); return; }
      if (key === 'farbe') scene.setFarbe(value);                 // sofort sehen, nicht erst nach der Antwort
      save({ [key]: value });
    };
    input.addEventListener(input.type === 'text' || input.type === 'range' ? 'change' : 'input', commit);
  }
  $('goto-stimme').addEventListener('click', () => showView('stimme'));   // im Kopf: Knowlins Stimme, im Körper: ihre
  $('goto-kopf-stimme').addEventListener('click', () => showView('stimme'));
  $('key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const key = $('key-input').value.trim();
    if (!key) return;
    setKeyMsg('Speichere …');
    const r = await api('/api/key', 'POST', { key });
    $('key-input').value = '';
    if (!r.ok) { setKeyMsg(r.fehler, false); return; }
    setKeyMsg('Gespeichert. Prüfe die Verbindung …');
    await loadSettings();
    const t = await api('/api/key/test', 'POST');
    setKeyMsg(t.meldung, t.ok);
  });
  $('key-test').addEventListener('click', async () => {
    setKeyMsg('Prüfe …');
    const t = await api('/api/key/test', 'POST');
    setKeyMsg(t.meldung, t.ok);
  });
  $('key-delete').addEventListener('click', async () => {
    const r = await api('/api/key', 'DELETE');
    setKeyMsg(r.schluessel.gesetzt ? 'Aus dem Tresor entfernt – es gilt jetzt der Schlüssel aus der Umgebung.' : 'Schlüssel entfernt.', null);
    await loadSettings();
  });

  // Persönlichkeit u. a. speichern selbst und reichen den neuen Stand hierher weiter
  function uebernehmen(neu, zeigen) {
    settings = neu;
    if (zeigen) renderSettings();
  }

  return { laden: loadSettings, render: renderSettings, renderPhysik, renderModell, save, uebernehmen,
    get werte() { return settings && settings.werte; } };
}
