// Policies aus Isaac Lab übernehmen (Lernen → Training, seit 0.38.27; Wunsch „3. fänd ich sehr wichtig“).
// Datei wählen → Knowlin prüft, ob sie zur Microduck passt, und rechnet den Prüfstand (stehen, vorwärts, seitwärts,
// drehen, Schubs – wie trainiert und mit der Glättung des echten Roboters). Nur bestanden ist sie für die Ente frei.
// Seit 0.38.30 auch direkt von Hugging Face („kann ich die Policies nicht OTA laden?“): Adresse eingeben, Knowlin lädt.

const ART = { wie_trainiert: 'wie trainiert', wie_am_roboter: 'wie am Roboter (mit Glättung)' };

export function initIsaacLab({ $, api, el, toast }) {
  const karte = $('isaaclab');
  if (!karte) return { load() {} };
  let daten = null;

  function zeile(p) {
    const tr = el('tr');
    tr.append(el('th', null, p.titel));
    const ok = el('td', p.ok ? 'il-ok' : 'il-nein');
    ok.append(el('span', null, p.ok ? '✓ ' : '✕ '), document.createTextNode(p.ok ? (p.grund || 'bestanden') : (p.grund || 'nicht bestanden')));
    tr.append(ok);
    const zahl = (v) => String(v).replace('.', ',');
    const wert = p.folgt != null ? `${Math.round(p.folgt * 100)} % des Befehls` : p.drift_m != null ? `${zahl(p.drift_m)} m gewandert` : '';
    const td = el('td', 'il-werte');
    if (wert) td.append(el('span', null, wert));
    td.append(el('span', null, `max. ${zahl(p.max_kipp_grad)}° gekippt`));
    tr.append(td);
    return tr;
  }

  function eintrag(e) {
    const li = el('li', 'il-eintrag');
    const kopf = el('div', 'il-kopf');
    kopf.append(el('strong', null, e.name), el('span', 'il-titel', e.titel || ''));
    const frei = el('span', `chip ${e.roboter_frei ? 'chip--good' : e.bestanden === false ? 'chip--warn' : ''}`, e.roboter_frei ? 'für die echte Ente frei' : e.bestanden === false ? 'Prüfstand nicht bestanden' : 'nicht geprüft');
    kopf.append(frei);
    li.append(kopf);
    if (e.download && e.download.repo) {
      const her = el('p', 'field-help il-herkunft');
      const a = el('a', null, e.download.repo);
      a.href = e.download.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      her.append('Von Hugging Face: ', a, ` · ${e.download.pfad}${e.download.lizenz ? ` · Lizenz laut Modellkarte: ${e.download.lizenz}` : ' · keine Lizenz angegeben'}`);
      li.append(her);
    }
    for (const [k, reihe] of Object.entries(e.pruefungen || {})) {
      if (!reihe || !reihe.length) continue;
      const box = el('div', 'table-scroll');
      box.tabIndex = 0;
      box.setAttribute('role', 'region');
      box.setAttribute('aria-label', `Prüfstand ${ART[k] || k}`);
      const t = el('table', 'vet-table il-tabelle');
      t.append(el('caption', null, `Prüfstand ${ART[k] || k}`));
      const tb = el('tbody');
      tb.append(...reihe.map(zeile));
      t.append(tb);
      box.append(t);
      li.append(box);
    }
    const acts = el('div', 'il-acts');
    if (daten.physik) {
      const aktiv = daten.aktiv === e.name;
      const nutzen = el('button', `btn btn--sm${aktiv ? '' : ' btn--primary'}`, aktiv ? 'Läuft im Physik-Simulator' : 'Im Physik-Simulator nutzen');
      nutzen.type = 'button';
      nutzen.disabled = aktiv;
      nutzen.addEventListener('click', async () => {
        const r = await api(`/api/isaaclab/${encodeURIComponent(e.name)}/nutzen`, 'POST').catch(() => null);
        if (r && r.ok) { toast(r.meldung || 'Gangart gewechselt'); zeigen(r); } else toast((r && r.fehler) || 'Ging nicht', true);
      });
      acts.append(nutzen);
    } else {
      acts.append(el('p', 'field-help', 'Ausprobieren geht im Physik-Simulator (System → Einstellungen → Körper).'));
    }
    li.append(acts);
    return li;
  }

  function zeigen(d) {
    daten = d;
    const sel = $('il-aufgabe');
    if (!sel.options.length) {
      for (const [k, v] of Object.entries(d.aufgaben || {})) { const o = new Option(v, k); o.title = k; sel.append(o); }
      sel.value = d.standard;
    }
    const liste = $('il-liste');
    liste.replaceChildren(...(d.liste || []).map(eintrag));
    $('il-leer').hidden = !!(d.liste && d.liste.length);
    const zurueck = $('il-standard');
    zurueck.hidden = !(d.physik && d.aktiv && (d.liste || []).some((x) => x.name === d.aktiv));
  }

  async function load() {
    const d = await api('/api/isaaclab').catch(() => null);
    if (d && d.ok) zeigen(d);
    if (quelle() === 'hf' && !gesucht) suchen();
  }

  // Vorschläge von Hugging Face (seit 0.38.31): einmal je Sitzung suchen, ein Klick übernimmt die Adresse
  let gesucht = false;
  const zahl = (n) => Number(n || 0).toLocaleString(document.documentElement.lang || 'de');
  function vorschlag(v) {
    const li = el('li', 'il-vorschlag');
    const text = el('div', 'il-vorschlag-text');
    const meta = [`${zahl(v.downloads)} Downloads`, v.lizenz ? `Lizenz ${v.lizenz}` : 'keine Lizenz angegeben',
      v.dateien.length === 1 ? '1 Policy' : `${v.dateien.length} Policies`];
    if (v.geaendert) meta.push(`Stand ${v.geaendert}`);
    text.append(el('strong', null, v.repo), el('span', null, meta.join(' · ')));
    const nehmen = el('button', 'btn btn--sm btn--tertiary', 'Auswählen');
    nehmen.type = 'button';
    nehmen.setAttribute('aria-label', `${v.repo} auswählen`);
    nehmen.addEventListener('click', () => {
      $('il-hf').value = v.repo;
      const sel = $('il-hf-datei');
      sel.replaceChildren(...(v.dateien.length > 1 ? v.dateien.map((d) => new Option(d, d)) : []));
      $('il-hf-wahl').hidden = v.dateien.length < 2;
      if (!$('il-name').value) $('il-name').value = v.repo.split('/')[1].slice(0, 24);
      $('il-vorschlag-liste').querySelectorAll('li').forEach((x) => x.removeAttribute('aria-current'));
      li.setAttribute('aria-current', 'true');
      $('il-state').textContent = `${v.repo} gewählt – jetzt „Prüfen und übernehmen“.`;
      $('il-go').focus();
    });
    li.append(text, nehmen);
    return li;
  }
  async function suchen(neu = false) {
    gesucht = true;
    const hinweis = $('il-vorschlaege-hinweis');
    hinweis.hidden = false;
    hinweis.textContent = 'Suche auf Hugging Face …';
    const r = await api(`/api/isaaclab/hf/suche${neu ? '?neu=true' : ''}`).catch(() => null);
    const liste = (r && r.ok && r.liste) || [];
    $('il-vorschlag-liste').replaceChildren(...liste.map(vorschlag));
    hinweis.textContent = !r || !r.ok ? ((r && r.fehler) || 'Hugging Face war nicht erreichbar – die Adresse kannst du trotzdem eingeben.')
      : liste.length ? 'Gefunden über die Suche nach „microduck“, meistgeladene zuerst. Ob eine Policy passt, zeigt erst der Prüfstand.'
        : 'Gerade keine öffentlichen Microduck-Policies gefunden – die Adresse kannst du trotzdem eingeben.';
    // Ohne Liste: dieselbe Suche im Browser (seit 0.38.34) – die Adresse dann einfach hier eintragen
    if (!liste.length) {
      const a = el('a', 'link', 'Auf Hugging Face suchen');
      a.href = 'https://huggingface.co/models?search=microduck'; a.target = '_blank'; a.rel = 'noopener';
      hinweis.append(' ', a);
    }
  }
  $('il-suche-neu').addEventListener('click', () => suchen(true));

  const quelle = () => (karte.querySelector('input[name="il-quelle"]:checked') || {}).value || 'hf';
  function quelleZeigen() {
    const hf = quelle() === 'hf';
    $('il-hf-feld').hidden = !hf;
    $('il-hf-wahl').hidden = !hf || !$('il-hf-datei').options.length;
    $('il-datei-feld').hidden = hf;
    $('il-vorschlaege').hidden = !hf;
    $('il-state').textContent = '';
    if (hf && !gesucht) suchen();
  }
  karte.querySelectorAll('input[name="il-quelle"]').forEach((r) => r.addEventListener('change', quelleZeigen));
  $('il-hf').addEventListener('input', () => { $('il-hf-datei').replaceChildren(); $('il-hf-wahl').hidden = true; });

  function fertig(r, st) {
    zeigen(r);
    $('il-form').reset();
    $('il-hf-datei').replaceChildren();
    $('il-datei-name').textContent = 'policy.onnx aus Isaac Lab, bis 60 MB';
    quelleZeigen();
    st.textContent = r.neu.roboter_frei ? `„${r.neu.name}“ hat den Prüfstand bestanden.`
      : `„${r.neu.name}“ ist übernommen, hat den Prüfstand aber nicht bestanden – im Simulator darfst du sie ansehen, auf die echte Ente nicht.`;
  }

  async function vonHf(st) {
    const adresse = $('il-hf').value.trim();
    if (!adresse) { st.textContent = 'Erst die Hugging-Face-Adresse eingeben.'; $('il-hf').focus(); return; }
    st.textContent = 'Lade von Hugging Face, prüfe die Datei und rechne den Prüfstand – das dauert etwa eine Minute …';
    const res = await fetch('/api/isaaclab/hf', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adresse, datei: $('il-hf-datei').value || '', name: $('il-name').value, aufgabe: $('il-aufgabe').value }) });
    const r = await res.json();
    if (r.auswahl) {
      $('il-hf-datei').replaceChildren(...r.auswahl.map((d) => new Option(`${d.pfad} · ${String(d.mb).replace('.', ',')} MB`, d.pfad)));
      $('il-hf-wahl').hidden = false;
      st.textContent = `${r.fehler} Dann noch einmal „Prüfen und übernehmen“.`;
      $('il-hf-datei').focus();
      return;
    }
    st.classList.toggle('bad', !r.ok);
    if (!r.ok) { st.textContent = r.fehler || 'Ging nicht'; return; }
    fertig(r, st);
  }

  $('il-waehlen').addEventListener('click', () => $('il-datei').click());
  $('il-datei').addEventListener('change', () => {
    const d = $('il-datei').files[0];
    $('il-datei-name').textContent = d ? `${d.name} · ${(d.size / 1048576).toLocaleString(document.documentElement.lang || 'de', { maximumFractionDigits: 1 })} MB`
      : 'policy.onnx aus Isaac Lab, bis 60 MB';
    if (d && !$('il-name').value) $('il-name').value = d.name.replace(/\.onnx$/i, '').slice(0, 24);
  });
  $('il-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const knopf = $('il-go');
    const st = $('il-state');
    const datei = $('il-datei').files[0];
    if (quelle() === 'datei' && !datei) { st.textContent = 'Erst eine ONNX-Datei wählen.'; $('il-waehlen').focus(); return; }
    knopf.disabled = true;
    knopf.classList.add('is-busy');
    st.classList.remove('bad');
    try {
      if (quelle() === 'hf') { await vonHf(st); return; }
      st.textContent = 'Prüfe die Datei und rechne den Prüfstand – das dauert etwa eine Minute …';
      const q = new URLSearchParams({ name: $('il-name').value || datei.name.replace(/\.onnx$/i, ''), aufgabe: $('il-aufgabe').value });
      const res = await fetch(`/api/isaaclab?${q}`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: datei });
      const r = await res.json();
      st.classList.toggle('bad', !r.ok);
      if (!r.ok) { st.textContent = r.fehler || 'Ging nicht'; return; }
      fertig(r, st);
    } catch {
      st.textContent = 'Keine Antwort von Knowlin.';
    } finally {
      knopf.disabled = false;
      knopf.classList.remove('is-busy');
    }
  });
  $('il-standard').addEventListener('click', async () => {
    const r = await api('/api/isaaclab/standard', 'POST').catch(() => null);
    if (r && r.ok) { toast(r.meldung || 'Wieder Pollens Gangart'); zeigen(r); }
  });

  return { load };
}
