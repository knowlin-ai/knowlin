// Lernen → Training → „Robustheit gegen Stöße“: eine Stoßreihe starten (unsichtbar, eigener Rechenprozess) und das
// Profil als Tabelle lesen – Zeilen Stärke × Höhe, Spalten die acht Richtungen. Jede Zelle trägt Wort und Zeichen
// (✓ steht, ≈ wackelt, ✕ fällt), die Farbe kommt nur dazu (WCAG 1.4.1). Vergleich mit einem älteren Profil zeigt
// je Zelle besser/schlechter. Alle Namen nur über textContent.

const AUSGANG = {
  steht: { zeichen: '✓', wort: 'steht', rang: 2 },
  wackelt: { zeichen: '≈', wort: 'wackelt', rang: 1 },
  faellt: { zeichen: '✕', wort: 'fällt', rang: 0 },
  steht_wieder_auf: { zeichen: '✕', wort: 'fällt', rang: 0 },
};
const RICHTUNGEN = ['vorn', 'vorn_links', 'links', 'hinten_links', 'hinten', 'hinten_rechts', 'rechts', 'vorn_rechts'];
const STUFEN = ['leicht', 'mittel', 'kraeftig'];
const STUFE_NAME = { leicht: 'leicht', mittel: 'mittel', kraeftig: 'kräftig' };
const HOEHE_NAME = { rumpf: 'Rumpf', kopf: 'Kopf' };

export function initStossreihe(h) {
  const { $, api, el, toast } = h;
  let status = null;
  let profile = [];
  let aktuell = null;          // angezeigtes Profil
  let alt = null;              // Vergleichsprofil
  let geladen = false;
  const num = (v, d = 0) => (v == null ? '–' : Number(v).toFixed(d).replace('.', ','));
  const richtungName = (r) => (status && status.raster && status.raster.richtungen[r]) || r.replace('_', ' ');
  const datum = (s) => (s ? s.replace('T', ' ').slice(0, 16) : '');

  async function load() {
    const [s, p] = await Promise.all([api('/api/kollision/reihe').catch(() => null),
      api('/api/kollision/reihe/profile').catch(() => null)]);
    if (s && s.ok) { status = s; renderStatus(); }
    if (p && p.ok) {
      profile = p.profile || [];
      fillProfiles();
      const want = $('sr-profil').value || (profile[0] && profile[0].id);
      if (want && (!aktuell || aktuell.id !== want)) await zeige(want);
      else renderResult();
    }
    geladen = true;
  }

  function update(msg) {
    const vorher = status && status.lauf;
    status = { ...(status || {}), ...msg };
    renderStatus();
    // gerade fertig geworden: neues Profil laden und zeigen
    if (msg.lauf && msg.lauf.status === 'fertig' && msg.lauf.profil && (!vorher || vorher.status !== 'fertig'
        || vorher.profil !== msg.lauf.profil)) {
      $('sr-profil').value = '';            // leer = das neueste Profil zeigen
      load();
    }
  }

  function renderStatus() {
    const s = status || {};
    const lauf = s.lauf || null;
    const laeuft = !!(lauf && lauf.laeuft);
    const grund = s.verfuegbar === false ? s.grund : '';
    $('sr-grund').hidden = !grund;
    $('sr-grund').textContent = grund || '';
    $('sr-go').disabled = laeuft || !!grund;
    $('sr-stop').hidden = !laeuft;
    $('sr-policy').disabled = laeuft;
    const sel = $('sr-policy');
    const qs = s.quellen || [];
    const key = qs.map((q) => q.id).join('|');
    if (sel.dataset.key !== key) {
      const was = sel.value;
      sel.replaceChildren(...qs.map((q) => { const o = el('option', null, q.name); o.value = q.id; return o; }));
      if (!qs.length) { const o = el('option', null, 'keine Policy geladen'); o.value = ''; sel.append(o); }
      if (was && qs.some((q) => q.id === was)) sel.value = was;
      sel.dataset.key = key;
    }
    const prog = $('sr-progress');
    prog.hidden = !lauf;
    if (!lauf) return;
    const bar = $('sr-bar');
    const gesamt = s.gesamt || lauf.gesamt || 0;
    const fertig = s.fertig || lauf.fertig || 0;
    bar.max = Math.max(1, gesamt);
    bar.value = fertig;
    const name = (lauf.policy && lauf.policy.name) || '';
    let text;
    if (lauf.status === 'startet') text = `Startet den Rechenprozess für ${name} …`;
    else if (lauf.status === 'laeuft') {
      const l = s.letztes;
      const zuletzt = l ? ` · zuletzt von ${richtungName(l.richtung)}, ${STUFE_NAME[l.stufe] || l.stufe}, ${HOEHE_NAME[l.hoehe] || l.hoehe}: ${(AUSGANG[l.ausgang] || {}).wort || l.ausgang}` : '';
      text = `${fertig} von ${gesamt} Versuchen${zuletzt}`;
    } else if (lauf.status === 'fertig') text = `Fertig: ${lauf.zusammenfassung || ''} (${num(lauf.dauer_s)} s)`;
    else if (lauf.status === 'abgebrochen') text = `Abgebrochen nach ${fertig} von ${gesamt} Versuchen – ohne Profil.`;
    else text = `Fehler: ${lauf.fehler || 'unbekannt'}`;
    $('sr-state').textContent = text;
    $('sr-state').classList.toggle('bad', lauf.status === 'fehler');
  }

  function profilText(p) {
    // das Wichtige zuerst – ein schmales Auswahlfeld schneidet hinten ab
    return `${p.stehen ?? '?'} von ${p.gesamt ?? '?'} stehen · ${(p.erstellt || '').replace('T', ' ').slice(5, 19)} · ${p.policy_name || '?'}`;
  }

  function fillProfiles() {
    for (const [id, leer] of [['sr-profil', null], ['sr-vergleich', 'nicht vergleichen']]) {
      const sel = $(id);
      const was = sel.value;
      const opts = profile.map((p) => { const o = el('option', null, profilText(p)); o.value = p.id; return o; });
      if (leer) { const o = el('option', null, leer); o.value = ''; opts.unshift(o); }
      sel.replaceChildren(...opts);
      if (profile.some((p) => p.id === was)) sel.value = was;
    }
    $('sr-result').hidden = !profile.length;
    $('sr-leer').hidden = !!profile.length;
  }

  async function holen(id) {
    const r = await api(`/api/kollision/reihe/profile/${encodeURIComponent(id)}`).catch(() => null);
    return r && r.ok ? r.profil : null;
  }

  async function zeige(id) {
    aktuell = id ? await holen(id) : null;
    if (aktuell) $('sr-profil').value = aktuell.id;
    // Vorschlag zum Vergleich: das nächstältere Profil
    const v = $('sr-vergleich');
    if (aktuell && !v.value) {
      const i = profile.findIndex((p) => p.id === aktuell.id);
      if (i >= 0 && profile[i + 1]) v.value = profile[i + 1].id;
    }
    alt = v.value && v.value !== (aktuell && aktuell.id) ? await holen(v.value) : null;
    renderResult();
  }

  // Je Zelle ein Vertreter; bei Wiederholungen (seit 0.37) der häufigste Ausgang (bei Gleichstand der schlechtere),
  // dazu wie oft sie stehen blieb (n.stehen von n.von) und ob ein Ausfallschritt dabei war
  function zellen(prof) {
    const gruppen = new Map();
    for (const x of (prof && prof.versuche) || []) {
      const k = `${x.richtung}|${x.stufe}|${x.hoehe}`;
      if (!gruppen.has(k)) gruppen.set(k, []);
      gruppen.get(k).push(x);
    }
    const m = new Map();
    for (const [k, xs] of gruppen) {
      const zaehl = new Map();
      for (const x of xs) zaehl.set(x.ausgang, (zaehl.get(x.ausgang) || 0) + 1);
      const rang = (a) => (AUSGANG[a] || AUSGANG.faellt).rang;
      const haupt = [...zaehl.entries()].sort((a, b) => b[1] - a[1] || rang(a[0]) - rang(b[0]))[0][0];
      const x = { ...(xs.find((v) => v.ausgang === haupt) || xs[0]) };
      x.n = { von: xs.length, stehen: xs.filter((v) => v.ausgang === 'steht' || v.ausgang === 'wackelt').length };
      x.schritt = xs.some((v) => v.schritt);
      x.neigung_max_grad = Math.max(...xs.map((v) => v.neigung_max_grad || 0));
      m.set(k, x);
    }
    return m;
  }

  function renderResult() {
    const tb = $('sr-tbody');
    if (!aktuell) { tb.replaceChildren(); $('sr-thead').replaceChildren(); $('sr-tfoot').replaceChildren(); return; }
    const r = aktuell.raster || {};
    const ri = RICHTUNGEN.filter((x) => (r.richtungen || RICHTUNGEN).includes(x));
    const st = STUFEN.filter((x) => (r.stufen || STUFEN).includes(x));
    const ho = ['rumpf', 'kopf'].filter((x) => (r.hoehen || ['rumpf', 'kopf']).includes(x));
    const neu = zellen(aktuell);
    const vor = alt ? zellen(alt) : null;
    const pol = aktuell.policy || {};
    const erg = aktuell.ergebnis || {};
    $('sr-summary').textContent = erg.text || '';
    $('sr-meta').textContent = `${pol.name || '?'} · Prüfsumme ${(pol.sha256 || '').slice(0, 12)} · ${datum(aktuell.erstellt)}`
      + (aktuell.dauer_s != null ? ` · gerechnet in ${num(aktuell.dauer_s)} s` : '');
    $('sr-caption').textContent = `Ausgang je Stoß: Zeilen Höhe und Stärke, Spalten die Richtung, aus der gestoßen wird`
      + (alt ? ` – verglichen mit ${datum(alt.erstellt)} (${(alt.policy || {}).name || '?'})` : '');
    // Kopf: Richtungen
    const hr = el('tr');
    const ecke = el('th', null, 'Stoß von …');
    ecke.scope = 'col';
    hr.append(ecke, ...ri.map((x) => { const th = el('th', null, richtungName(x)); th.scope = 'col'; return th; }));
    $('sr-thead').replaceChildren(hr);
    // Zeilen: Höhe × Stärke
    let besser = 0, schlechter = 0, gleich = 0;
    const rows = [];
    for (const hoehe of ho) {
      for (const stufe of st) {
        const tr = el('tr');
        const th = el('th', null, `${HOEHE_NAME[hoehe]} · ${STUFE_NAME[stufe]}`);
        th.scope = 'row';
        tr.append(th);
        for (const richtung of ri) {
          const k = `${richtung}|${stufe}|${hoehe}`;
          const x = neu.get(k);
          const td = el('td', 'sr-cell');
          if (!x) { td.textContent = '–'; tr.append(td); continue; }
          const a = AUSGANG[x.ausgang] || AUSGANG.faellt;
          td.classList.add(`sr-cell--${a.rang === 2 ? 'steht' : a.rang === 1 ? 'wackelt' : 'faellt'}`);
          const haupt = el('span', 'sr-word');
          haupt.append(el('span', 'sr-sign', a.zeichen), document.createTextNode(` ${a.wort}`));
          haupt.querySelector('.sr-sign').setAttribute('aria-hidden', 'true');
          td.append(haupt, el('span', 'sr-fact', `${num(x.neigung_max_grad)}°`));
          if (x.n.von > 1) {
            td.append(el('span', 'sr-fact', `${x.n.stehen}/${x.n.von} stehen`));
            if (x.n.stehen > 0 && x.n.stehen < x.n.von) td.classList.add('sr-cell--grenz');
          }
          if (x.schritt) td.append(el('span', 'sr-fact', 'Ausfallschritt'));
          const details = [`größte Neigung ${num(x.neigung_max_grad, 1)}°`, `Versatz ${num((x.versatz_m || 0) * 100)} cm`];
          if (x.n.von > 1) details.push(`${x.n.stehen} von ${x.n.von} Wiederholungen bleiben stehen`);
          if (x.ruhig_nach_s != null) details.push(`ruhig nach ${num(x.ruhig_nach_s, 1)} s`);
          if (x.gefallen_nach_s != null) details.push(`gefallen nach ${num(x.gefallen_nach_s, 1)} s`);
          const o = vor && vor.get(k);
          if (o) {
            const b = (AUSGANG[o.ausgang] || AUSGANG.faellt);
            if (a.rang > b.rang) { besser += 1; td.append(el('span', 'sr-delta is-up', `▲ vorher ${b.wort}`)); }
            else if (a.rang < b.rang) { schlechter += 1; td.append(el('span', 'sr-delta is-down', `▼ vorher ${b.wort}`)); }
            else gleich += 1;
            details.push(`vorher: ${b.wort}, ${num(o.neigung_max_grad, 1)}°`);
          }
          td.title = details.join(' · ');
          tr.append(td);
        }
        rows.push(tr);
      }
    }
    tb.replaceChildren(...rows);
    // Fuß: je Richtung, wie viele bleiben stehen
    const fr = el('tr');
    const fth = el('th', null, 'bleiben stehen');
    fth.scope = 'row';
    fr.append(fth, ...ri.map((x) => {
      const z = (erg.je_richtung || {})[x] || {};
      const n = (z.steht || 0) + (z.wackelt || 0);
      return el('td', 'sr-foot', `${n} von ${n + (z.faellt || 0)}`);
    }));
    $('sr-tfoot').replaceChildren(fr);
    const d = $('sr-delta');
    if (alt) {
      // nur Stöße, die in beiden Profilen vorkommen (eine Reihe kann eingeschränkt gerechnet sein)
      let n = 0, vorher = 0, jetzt = 0;
      for (const [k, x] of neu) {
        const o = vor.get(k);
        if (!o) continue;
        n += 1;
        if ((AUSGANG[x.ausgang] || AUSGANG.faellt).rang > 0) jetzt += 1;
        if ((AUSGANG[o.ausgang] || AUSGANG.faellt).rang > 0) vorher += 1;
      }
      const diff = jetzt - vorher;
      d.textContent = n ? `Gegenüber ${datum(alt.erstellt)} (${(alt.policy || {}).name || '?'}), auf denselben ${n} Stößen: `
        + `${vorher} → ${jetzt} bleiben stehen (${diff > 0 ? '+' : diff < 0 ? '−' : '±'}${Math.abs(diff)}). `
        + `${besser} besser, ${schlechter} schlechter, ${gleich} gleich.`
        : 'Die beiden Profile haben keine gemeinsamen Stöße.';
    } else d.textContent = '';
    d.hidden = !alt;
  }

  $('sr-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const r = await api('/api/kollision/reihe', 'POST', { policy: $('sr-policy').value || 'standard', wiederholungen: Number($('sr-wdh').value) || 1 }).catch(() => null);
    if (!r || !r.ok) { toast((r && r.fehler) || 'Die Stoßreihe startet gerade nicht', true); return; }
    update(r);
  });
  $('sr-stop').addEventListener('click', async () => {
    const r = await api('/api/kollision/reihe/stopp', 'POST').catch(() => null);
    if (!r || !r.ok) toast((r && r.fehler) || 'Abbrechen geht gerade nicht', true);
  });
  $('sr-profil').addEventListener('change', () => zeige($('sr-profil').value));
  $('sr-vergleich').addEventListener('change', () => zeige($('sr-profil').value));

  return { load, update, get geladen() { return geladen; } };
}
