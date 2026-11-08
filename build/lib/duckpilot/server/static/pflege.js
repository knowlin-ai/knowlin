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
      if (h.battery && h.battery.fraction != null) parts.push(`Akku ${Math.round(h.battery.fraction * 100)} %`);
      if (h.cpu_temp_c != null) parts.push(`CPU ${Math.round(h.cpu_temp_c)} °C`);
      if (h.motors && h.motors.max_temp_c != null) parts.push(`Motoren bis ${Math.round(h.motors.max_temp_c)} °C`);
      add('Zustand', parts.join(' · '));
    } else add('Zustand (robotd)', bad(r.gesundheit));
    if (r.updates.ok) {
      const comps = (r.updates.daten && (r.updates.daten.components || r.updates.daten)) || [];
      const d = Array.isArray(comps) ? comps.find((c) => c.component === 'daemon') || comps[0] : null;
      add('Software', d ? `${d.installed || '?'}${d.phase && d.phase !== 'idle' ? ` · ${d.phase}` : ''}` : '?');
    } else add('Software (updaterd)', bad(r.updates));
    renderVetbook(r.pflegeheft);
  }

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
