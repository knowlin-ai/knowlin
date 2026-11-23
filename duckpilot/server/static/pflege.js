// Roboter-Pflege im Zustand-Dashboard (nur am echten Roboter): System, WLAN, Zustand, Updates, Pflegeheft, Protokolle.
// Schicht: Körper (Microduck-Modul). Ausgelagert aus app.js (0.33).

export function initPflege({ $, api, el, getConfig }) {
  async function loadCare() {
    if (getConfig().backend !== 'robotd') return;
    const r = await api('/api/pflege').catch(() => null);
    if (!r || r.ok === false) { $('care-update-state').textContent = r ? r.fehler : 'keine Antwort'; return; }
    const facts = $('care-facts');
    facts.replaceChildren();
    const add = (dt, dd) => { const d = el('div'); d.append(el('dt', null, dt), el('dd', null, dd)); facts.append(d); };
    const bad = (x) => `nicht erreichbar (${(x.fehler || '').slice(0, 80)})`;
    if (r.system.ok) {
      const s = r.system.daten || {};
      add('Name', `${s.name || '?'}${s.serial ? ` · ${s.serial}` : ''}`);
      add('Läuft seit', s.uptime_seconds != null ? `${Math.floor(s.uptime_seconds / 3600)} h ${Math.floor(s.uptime_seconds % 3600 / 60)} min` : '?');
    } else add('System (configd)', bad(r.system));
    if (r.netz.ok) {
      const n = r.netz.daten || {};
      add('WLAN', n.ssid ? `${n.ssid}${n.signal != null ? ` · ${n.signal} %` : ''}${n.ip4 ? ` · ${n.ip4}` : ''}` : (n.state || '?'));
    } else add('WLAN (configd)', bad(r.netz));
    if (r.gesundheit.ok) {
      const h = r.gesundheit.daten || {};
      const parts = [h.healthy === false ? (h.degraded ? 'eingeschränkt' : 'nicht gesund') : 'gesund'];
      if (h.reason) parts.push(h.reason);
      // robotd meldet battery.percent (0–100); fraction nur bei älteren Test-Gegenstellen (Fund 23.11.: nie ein Akku sichtbar)
      const akku = h.battery ? (h.battery.percent != null ? h.battery.percent : h.battery.fraction != null ? h.battery.fraction * 100 : null) : null;
      if (akku != null) parts.push(`Akku ${Math.round(akku)} %`);
      if (h.goal_pwm != null) parts.push(`Motorleistung nach Akku (Goal PWM ${h.goal_pwm})`);
      if (h.cpu_temp_c != null) parts.push(`CPU ${Math.round(h.cpu_temp_c)} °C`);
      if (h.motors && h.motors.max_temp_c != null) parts.push(`Motoren bis ${Math.round(h.motors.max_temp_c)} °C`);
      add('Zustand', parts.join(' · '));
    } else add('Zustand (robotd)', bad(r.gesundheit));
    if (r.updates.ok) {
      const comps = (r.updates.daten && (r.updates.daten.components || r.updates.daten)) || [];
      const d = Array.isArray(comps) ? comps.find((c) => c.component === 'daemon') || comps[0] : null;
      add('Software', d ? `${d.installed || '?'}${d.phase && d.phase !== 'idle' ? ` · ${d.phase}` : ''}` : '?');
    } else add('Software (updaterd)', bad(r.updates));
    if (r.modus && r.modus.ok) {
      const m = r.modus.daten || {};
      const spiele = m.spiele || [];
      add('Läuft gerade', `${m.mode === 'roller' ? 'Rollen' : 'Gehen'}${spiele.length ? ` · Pollens ${spiele.join(', ')} – Knowlin fängt nichts Eigenes an` : ''}`);
    }
    renderVolume(r.lautstaerke);
    renderVetbook(r.pflegeheft);
    loadPhotos();
  }

  // Lautstärke (robotd ab Protokoll 66)
  function renderVolume(v) {
    const box = $('care-volume');
    if (!box) return;
    box.hidden = !(v && v.ok);
    if (!v || !v.ok) return;
    const d = v.daten || {};
    $('care-volume-range').value = d.volume != null ? d.volume : 70;
    $('care-volume-val').textContent = `${$('care-volume-range').value} %`;
    $('care-volume-note').textContent = d.mixer === false ? 'Diese Platine hat keinen Regler – der Wert wird nur gemerkt.' : '';
  }
  let volTimer = null;
  $('care-volume-range')?.addEventListener('input', (e) => {
    $('care-volume-val').textContent = `${e.target.value} %`;
    clearTimeout(volTimer);
    volTimer = setTimeout(async () => {
      const r = await api('/api/pflege/lautstaerke', 'POST', { prozent: Number(e.target.value) }).catch(() => ({ ok: false, fehler: 'keine Antwort' }));
      if (!r.ok) $('care-volume-note').textContent = r.fehler || 'nicht gesetzt';
    }, 250);
  });

  // Fotos der Ente (nfcd ab Protokoll 64, „Foto machen“ ab 68) – nur am PC, die Bilder zeigen die Wohnung
  async function loadPhotos() {
    const box = $('care-photos');
    if (!box) return;
    const r = await api('/api/pflege/fotos').catch(() => null);
    const list = $('care-photo-list');
    list.replaceChildren();
    box.hidden = !r;
    if (!r) return;
    if (!r.ok) { $('care-photo-note').textContent = r.fehler || 'Fotos nicht erreichbar'; return; }
    $('care-photo-note').textContent = r.fotos.length ? `${r.fotos.length} Foto${r.fotos.length === 1 ? '' : 's'} auf der Ente` : 'Noch keine Fotos auf der Ente.';
    for (const f of r.fotos) {
      const li = el('li', 'care-photo');
      const img = el('img');
      img.alt = `Foto vom ${f.name.replace('_', ' um ').replace(/-(\d\d)-(\d\d)(-\d+)?$/, ':$1:$2')}`;
      img.loading = 'lazy';
      img.src = `/api/pflege/foto/${encodeURIComponent(f.name)}?vorschau=1`;
      const open = el('a', 'btn btn--ghost btn--sm', 'Öffnen');
      open.href = `/api/pflege/foto/${encodeURIComponent(f.name)}`;
      open.target = '_blank';
      open.rel = 'noopener';
      const del = el('button', 'btn btn--ghost btn--sm', 'Löschen');
      del.type = 'button';
      let armed = null;
      del.addEventListener('click', async () => {
        if (!armed) { del.textContent = 'Wirklich löschen?'; armed = setTimeout(() => { armed = null; del.textContent = 'Löschen'; }, 4000); return; }
        clearTimeout(armed); armed = null;
        await api(`/api/pflege/foto/${encodeURIComponent(f.name)}`, 'DELETE').catch(() => null);
        loadPhotos();
      });
      const actions = el('div', 'care-actions');
      actions.append(open, del);
      li.append(img, actions);
      list.append(li);
    }
  }
  $('care-photo-take')?.addEventListener('click', async (e) => {
    const b = e.target;
    b.disabled = true;
    $('care-photo-note').textContent = 'Sie posiert, zählt mit dem Licht herunter und knipst …';
    const r = await api('/api/pflege/fotos', 'POST').catch(() => ({ ok: false, fehler: 'keine Antwort' }));
    if (!r.ok) { $('care-photo-note').textContent = r.fehler || 'kein Foto'; b.disabled = false; return; }
    setTimeout(() => { b.disabled = false; loadPhotos(); }, 8000);     // Pollen: etwa sieben Sekunden bis zum Bild
  });

  const TRIP_WORDS = { overheat: 'Hitze', encoder: 'Geber', shock: 'Stoß', overload: 'Überlast' };
  function renderVetbook(v) {
    const box = $('care-vet');
    const d = v && v.ok ? v.daten : null;
    box.hidden = !d;
    if (!d) return;
    const first = d.zuerst_ansehen || [];
    $('care-vet-note').textContent = first.length
      ? `Zuerst ansehen: ${first.join(', ')} – diese Motoren haben am häufigsten ihren Schutz ausgelöst.`
      : 'Kein Motor hat bisher seinen Schutz ausgelöst.';
    const rows = $('care-vet-rows');
    rows.replaceChildren();
    for (const m of d.motoren || []) {
      const tr = el('tr');
      if (m.ausgemustert) tr.className = 'is-retired';
      const trips = Object.entries(m.ausloeser || {}).filter(([, n]) => n > 0).map(([k, n]) => `${TRIP_WORDS[k] || k} ${n}×`);
      tr.append(
        el('th', null, `${m.label}${m.ausgemustert ? ' (ausgemustert)' : ''}`),
        el('td', null, `${m.stunden_unter_strom} h`),
        el('td', null, `${m.weg_umdrehungen} U`),
        el('td', null, m.heissester_c != null ? `${Math.round(m.heissester_c)} °C` : '–'),
        el('td', null, trips.length ? trips.join(', ') : 'keine'),
      );
      tr.firstChild.setAttribute('scope', 'row');
      rows.append(tr);
    }
    const ev = $('care-vet-events');
    ev.replaceChildren(...(d.ereignisse || []).slice().reverse().map((e) => el('li', null, `${e.wann || ''} · ${e.text}`)));
  }
  $('care-refresh').addEventListener('click', loadCare);
  $('care-check').addEventListener('click', async (e) => {
    e.target.disabled = true;
    const r = await api('/api/pflege/pruefen', 'POST').catch(() => ({ ok: false, fehler: 'keine Antwort' }));
    e.target.disabled = false;
    const st = $('care-update-state');
    if (!r.ok) { st.textContent = `Suche fehlgeschlagen: ${r.fehler}`; return; }
    const c = r.ergebnis || {};
    st.textContent = c.state === 'available' ? `Neu: ${c.candidate} (installiert ${c.installed || '?'})${c.changelog ? ` – ${c.changelog}` : ''}`
      : c.state === 'up_to_date' ? `Aktuell (${c.installed})` : c.state === 'incompatible' ? `${c.candidate} passt nicht: ${c.reason}` : JSON.stringify(c);
    $('care-dry').hidden = $('care-apply').hidden = c.state !== 'available';
  });
  async function careApply(probe, btn) {
    btn.disabled = true;
    $('care-update-state').textContent = probe ? 'Probelauf: laden, prüfen, nichts tauschen …' : 'Spielt ein – die Ente startet ihre Dienste neu …';
    const r = await api('/api/pflege/einspielen', 'POST', { probe }).catch(() => ({ ok: false, fehler: 'keine Antwort' }));
    btn.disabled = false;
    const res = r.ergebnis || {};
    $('care-update-state').textContent = !r.ok ? r.fehler : res.outcome === 'dry_run_passed' ? `Probelauf bestanden: ${res.candidate} passt.`
      : res.outcome === 'applied' ? `Eingespielt: ${res.from || '?'} → ${res.to}` : res.outcome === 'rolled_back' ? `Zurückgerollt auf ${res.reverted_to || '?'}` : JSON.stringify(res);
    loadCare();
  }
  $('care-dry').addEventListener('click', (e) => careApply(true, e.target));
  let careArmed = null;
  $('care-apply').addEventListener('click', (e) => {
    const b = e.target;
    if (!careArmed) {
      b.textContent = 'Wirklich einspielen? Nochmal klicken';
      careArmed = setTimeout(() => { careArmed = null; b.textContent = 'Update einspielen'; }, 4000);
      return;
    }
    clearTimeout(careArmed); careArmed = null; b.textContent = 'Update einspielen';
    careApply(false, b);
  });
  $('care-logs-btn').addEventListener('click', async () => {
    const pre = $('care-log');
    pre.hidden = false;
    pre.textContent = 'lädt …';
    const r = await api(`/api/pflege/protokoll?dienst=${encodeURIComponent($('care-unit').value)}&zeilen=200`).catch(() => ({ ok: false }));
    pre.textContent = r.ok ? (r.lines || []).join('\n') || '(leer)' : `nicht abrufbar: ${r.fehler || ''}`;
  });
  return { load: loadCare };
}
