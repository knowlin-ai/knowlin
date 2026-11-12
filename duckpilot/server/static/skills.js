// Erweiterungen (Skill-Pakete) unter System: an- und abschalten, Kataloge der aktiven Pakete unter Tricks zeigen.
// Alles, was vom Hub kommt (Namen, Beschreibungen), ist Fremdtext: nur als textContent, nie als HTML.

import { t } from './i18n.js';

const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>';
const STOP = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>';
const SECTIONS = { app_moves: renderMoves, talent: renderTalent, gaits: renderGaits, community: renderCommunity };

const KNOWLIN_WEIT = new Set(['alltag']);   // Erweiterungen, die für jeden Körper gelten (seit 0.38.6)

export function initSkills({ $, api, el, toast, send, showView }) {
  let packs = [];
  let body = 'sim';
  const loaded = {};           // id → Katalog-Antwort
  const filter = { app_moves: 'Alle' };
  const h = { $, api, el, toast, send, showView, reload: (id) => loadCatalog(id, true), get body() { return body; } };

  async function refresh() {
    const r = await api('/api/skills').catch(() => null);
    if (!r) { $('pack-grid').replaceChildren(el('div', 'empty', 'Knowlin antwortet nicht.')); return; }
    packs = r.pakete; body = r.koerper;
    renderPacks();
    renderGeplant(r.geplant || []);
    renderSections();
  }

  function renderPacks() {
    $('pack-grid').replaceChildren(...packs.map(packCard));
  }

  // Geplant (0.33): was als Nächstes kommt – Kacheln mit Releasezahl, nicht einschaltbar
  function renderGeplant(list) {
    const grid = $('plan-grid');
    if (!grid) return;
    grid.replaceChildren(...list.map((g) => {
      const card = el('article', 'card pack is-planned');
      const head = el('div', 'pack-head');
      head.append(el('h3', 'pack-name', g.name), el('span', 'chip', /^\d/.test(g.version) ? t('geplant.fuer', { version: g.version }, 'geplant für {version}') : `geplant ${g.version}`));
      card.append(head, el('p', 'pack-kurz', g.kurz));
      return card;
    }));
    $('plan-wrap').hidden = !list.length;
  }

  function packCard(p) {
    // Alles außer dem Alltagsbuddy gehört zur Microduck (Pollens Policies, Hub-Konten) – bei anderen Körpern nicht da
    const card = el('article', `card pack${p.an ? ' is-on' : ''}${p.verfuegbar ? '' : ' is-planned'}${KNOWLIN_WEIT.has(p.id) ? '' : ' nur-microduck'}`);
    const head = el('div', 'pack-head');
    const title = el('h3', 'pack-name', p.name);
    const sw = el('label', 'switch pack-switch');
    const cb = el('input');
    cb.type = 'checkbox'; cb.checked = p.an; cb.disabled = !p.verfuegbar;
    cb.setAttribute('aria-label', `${p.name} ${p.an ? 'ausschalten' : 'einschalten'}`);
    sw.append(cb);
    cb.addEventListener('change', async () => {
      cb.disabled = true;
      const r = await api('/api/skills', 'POST', { id: p.id, an: cb.checked }).catch(() => ({ ok: false, fehler: 'keine Antwort' }));
      if (!r.ok) { toast(r.fehler || 'Nicht geändert', true); cb.checked = !cb.checked; cb.disabled = false; return; }
      packs = r.pakete;
      const now = packs.find((x) => x.id === p.id);
      toast(now.an ? `„${p.name}“ aktiv${now.werkzeug ? ' – das Sprachmodell kann es jetzt nutzen' : ''}` : `„${p.name}“ aus`);
      renderPacks();
      renderSections();
      if (now.an) requestAnimationFrame(() => document.getElementById(`pack-sec-${p.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    });
    head.append(title, sw);
    // Ein ruhiger Aufbau für jede Kachel: Name + Schalter, ein Satz, darunter eine Zeile Herkunft und Bedingungen.
    // Farbig ist nur, was man wissen muss, bevor man einschaltet: experimentell oder geplant.
    const state = p.stand === 'experimentell' ? el('span', 'chip chip--warn', 'experimentell')
      : p.stand === 'geplant' ? el('span', 'chip', 'geplant') : null;
    if (state) head.insertBefore(state, sw);
    card.append(head, el('p', 'pack-kurz', p.kurz));
    card.append(el('p', 'pack-more', p.verfuegbar ? (p.im_simulator || p.text) : p.grund[0].toUpperCase() + p.grund.slice(1) + '.'));
    const origin = { offiziell: 'Von Pollen', community: 'Community', gemischt: 'Pollen & Community', duckpilot: 'In Knowlin eingebaut' }[p.herkunft] || 'Community';
    const meta = [origin];
    if (p.braucht) meta.push(p.braucht === 'kamera' ? 'braucht die Kamera' : 'braucht den Roboter');
    if (p.werkzeug) meta.push('auch fürs Sprachmodell');
    if (p.lizenz) meta.push(`Lizenz: ${p.lizenz}`);
    const foot = el('p', 'pack-foot', meta.join(' · '));
    if (p.quelle) {
      const a = el('a', null, 'Quelle');
      a.href = p.quelle; a.target = '_blank'; a.rel = 'noopener';
      foot.append(document.createTextNode(' · '), a);
    }
    card.append(foot);
    return card;
  }

  function renderSections() {
    const root = $('pack-sections');
    const on = packs.filter((p) => p.an && SECTIONS[p.id]);
    // vorhandene Abschnitte behalten (Videos laufen weiter), fehlende anlegen, abgeschaltete entfernen
    for (const sec of [...root.children]) if (!on.some((p) => `pack-sec-${p.id}` === sec.id)) sec.remove();
    for (const p of on) {
      if (document.getElementById(`pack-sec-${p.id}`)) continue;
      const sec = el('section', 'pack-section');
      sec.id = `pack-sec-${p.id}`;
      const head = el('div', 'section-head');
      head.append(el('h3', null, p.name), el('p', null, [p.im_simulator, p.hinweis].filter(Boolean).join(' ')));
      const bodyEl = el('div', 'pack-body');
      bodyEl.append(el('div', 'empty', 'Lade vom Hugging Face Hub …'));
      sec.append(head, bodyEl);
      root.append(sec);
      loadCatalog(p.id);
    }
  }

  async function loadCatalog(id, fresh = false) {
    const sec = document.getElementById(`pack-sec-${id}`);
    if (!sec) return;
    const target = sec.querySelector('.pack-body');
    if (fresh) target.replaceChildren(el('div', 'empty', 'Lade vom Hugging Face Hub …'));
    const r = await api(`/api/skills/${id}/katalog${fresh ? '?neu=true' : ''}`).catch(() => ({ ok: false, fehler: 'Knowlin antwortet nicht' }));
    loaded[id] = r;
    if (r.koerper) body = r.koerper;
    if (!r.ok) {
      const box = el('div', 'empty');
      const again = el('button', 'btn btn--sm', 'Nochmal versuchen');
      again.addEventListener('click', () => loadCatalog(id, true));
      box.append(el('p', null, r.fehler || 'Nicht geladen.'), again);
      target.replaceChildren(box);
      return;
    }
    SECTIONS[id](target, r, h, filter);
  }

  return { refresh, get packs() { return packs; } };
}

// ── gemeinsame Bausteine ─────────────────────────────────────────────
function secs(v) { return v ? `${String(Math.round(v * 10) / 10).replace('.', ',')} s` : ''; }

function toolbar(h, r, id, extra = []) {
  const bar = el2(h, 'div', 'pack-toolbar');
  const info = el2(h, 'span', 'pack-count', `${r.eintraege.length} Einträge${r.hinweis ? ` · ${r.hinweis}` : ''}`);
  const again = el2(h, 'button', 'btn btn--ghost btn--sm', 'Neu laden');
  again.type = 'button';
  again.addEventListener('click', () => h.reload(id));
  bar.append(...extra, info, again);
  return bar;
}
function el2(h, tag, cls, text) { return h.el(tag, cls, text); }

async function runEntry(h, id, eintrag, aktion, btn) {
  btn?.classList.add('is-busy');
  const r = await h.api(`/api/skills/${id}/ausfuehren`, 'POST', { eintrag, aktion }).catch(() => ({ ok: false, grund: 'keine Antwort' }));
  btn?.classList.remove('is-busy');
  h.toast(r.grund || (r.ok ? 'OK' : 'Nicht ausgeführt'), !r.ok);
  return r;
}

// Vorschaubilder (0.38.26, Hinweise „die Vorschaubilder bei Tricks laden oft erst spät oder gar nicht“ und „da wo
// möglich wäre gut, wenn es Vorschau gäbe“): Jede Kachel zeigt ein Standbild aus dem Vorschauvideo, sobald sie in Sicht
// kommt – geladen werden nur die Anfänge (Metadaten), höchstens drei gleichzeitig. Mit der Maus darüber läuft es stumm an,
// ein Klick spielt es in Schleife. Ohne Video steht ehrlich „keine Vorschau“ da.
const WARTE = [];
let laedt = 0;
function weiterLaden() {
  while (laedt < 3 && WARTE.length) {
    const [vid, url] = WARTE.shift();
    if (vid.src) continue;
    laedt++;
    const fertig = () => { laedt--; weiterLaden(); };
    vid.addEventListener('loadeddata', fertig, { once: true });
    vid.addEventListener('error', () => { vid.closest('.move-media')?.classList.add('ohne-bild'); fertig(); }, { once: true });
    vid.src = `${url}#t=1.2`;                       // Standbild etwas nach dem Anfang, nicht das Schwarz davor
  }
}
const SICHT = typeof IntersectionObserver === 'function' ? new IntersectionObserver((eintraege) => {
  for (const e of eintraege) {
    if (!e.isIntersecting) continue;
    SICHT.unobserve(e.target);
    WARTE.push([e.target, e.target.dataset.url]);
  }
  weiterLaden();
}, { rootMargin: '300px 0px' }) : null;

// Kachel mit Standbild und Abspielknopf – auch für die Tricks vom Hub (tricks_seite.js). `huelle` bekommt is-playing.
export function vorschauKachel(url, el, titel, huelle) {
  const media = el('button', 'move-media');
  media.type = 'button';
  media.setAttribute('aria-label', `Vorschau: ${titel}`);
  if (!url) {
    media.disabled = true;
    media.append(el('span', 'move-ohne', 'keine Vorschau'));
    return media;
  }
  media.innerHTML = PLAY;
  const vid = el('video');
  vid.muted = true; vid.playsInline = true; vid.preload = 'metadata'; vid.loop = true;
  vid.dataset.url = url;
  vid.setAttribute('aria-hidden', 'true');
  media.prepend(vid);
  if (SICHT) SICHT.observe(vid); else { WARTE.push([vid, url]); weiterLaden(); }
  const spielt = () => huelle.classList.contains('is-playing');
  if (window.matchMedia && matchMedia('(hover: hover) and (pointer: fine)').matches) {
    media.addEventListener('pointerenter', () => { if (vid.src && vid.paused) vid.play().catch(() => {}); });
    media.addEventListener('pointerleave', () => { if (!spielt()) vid.pause(); });
  }
  media.addEventListener('click', () => {
    if (spielt()) { vid.pause(); media.querySelector('svg').outerHTML = PLAY; huelle.classList.remove('is-playing'); return; }
    if (!vid.src) vid.src = url;
    vid.play().catch(() => {});
    media.querySelector('svg').outerHTML = STOP;
    huelle.classList.add('is-playing');
  });
  return media;
}

// ── MicroDuck-App ────────────────────────────────────────────────────
function renderMoves(target, r, h, filter) {
  const robot = h.body === 'robotd' || h.body === 'physik';
  const cats = ['Alle', ...new Set(r.eintraege.map((e) => e.rubrik))];
  const chips = h.el('div', 'pack-filter');
  chips.setAttribute('role', 'group');
  chips.setAttribute('aria-label', 'Rubrik');
  const grid = h.el('div', 'move-grid grid grid--tiles-sm');
  const draw = () => {
    grid.replaceChildren(...r.eintraege.filter((e) => filter.app_moves === 'Alle' || e.rubrik === filter.app_moves).map(card));
    for (const c of chips.children) c.setAttribute('aria-pressed', c.dataset.cat === filter.app_moves ? 'true' : 'false');
  };
  for (const c of cats) {
    const b = h.el('button', 'chip', c === 'Alle' ? `Alle (${r.eintraege.length})` : c);
    b.type = 'button'; b.dataset.cat = c;
    b.addEventListener('click', () => { filter.app_moves = c; draw(); });
    chips.append(b);
  }
  function card(e) {
    const t = h.el('article', 'move');
    const media = vorschauKachel(e.vorschau, h.el, e.titel, t);
    const meta = h.el('p', 'move-meta', [e.rubrik, secs(e.dauer)].filter(Boolean).join(' · '));
    t.append(media, h.el('h4', 'move-title', e.titel), meta);
    if (e.beschreibung) { const q = h.el('p', 'move-desc'); q.append(h.el('q', null, e.beschreibung)); t.append(q); }
    const acts = h.el('div', 'move-acts');
    if (robot) {
      const play = h.el('button', 'btn btn--primary btn--sm', 'Abspielen');
      play.addEventListener('click', async () => { const res = await runEntry(h, 'app_moves', e.repo, '', play); if (res.ok) h.showView('cockpit'); });
      if (e.geht === false) { play.disabled = true; play.title = e.hinweis || ''; }
      acts.append(play);
    } else {
      const keep = h.el('button', 'btn btn--sm', 'Vormerken');
      keep.title = 'Wird geladen, sobald die echte Ente verbunden ist';
      keep.addEventListener('click', async () => { const res = await runEntry(h, 'app_moves', e.repo, 'vormerken', keep); if (res.ok) { keep.textContent = 'Vorgemerkt'; keep.disabled = true; } });
      acts.append(keep);
    }
    const a = h.el('a', 'btn btn--ghost btn--sm', 'Hub');
    a.href = e.seite; a.target = '_blank'; a.rel = 'noopener';
    acts.append(a);
    t.append(acts);
    return t;
  }
  target.replaceChildren(toolbar(h, r, 'app_moves', [chips]), grid);
  draw();
}

// ── Got a Talent ─────────────────────────────────────────────────────
function timelineSvg(e) {
  const W = 300, H = 56, d = e.dauer || 20;
  const x = (t) => (t / d) * W;
  const kfs = e.keyframes || [];
  let sit = '', yaw = '', pitch = '';
  kfs.forEach((k, i) => {
    const t1 = i + 1 < kfs.length ? kfs[i + 1].t : d;
    if (k.sit) sit += `<rect x="${x(k.t).toFixed(1)}" y="0" width="${(x(t1) - x(k.t)).toFixed(1)}" height="${H}" class="tl-sit"/>`;
    const y = (v) => (H / 2 - Math.max(-1.4, Math.min(1.4, v)) / 1.4 * (H / 2 - 4)).toFixed(1);
    yaw += `${i ? 'L' : 'M'}${x(k.t).toFixed(1)},${y(k.head[2])}H${x(t1).toFixed(1)}`;
    pitch += `${i ? 'L' : 'M'}${x(k.t).toFixed(1)},${y(k.head[1] + k.head[0])}H${x(t1).toFixed(1)}`;
  });
  return `<svg class="tl" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Zeitleiste: Sitzen und Kopfbewegungen">
    ${sit}<line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" class="tl-mid"/>
    <path d="${pitch}" class="tl-pitch" vector-effect="non-scaling-stroke"/><path d="${yaw}" class="tl-yaw" vector-effect="non-scaling-stroke"/></svg>`;
}

function renderTalent(target, r, h) {
  const list = h.el('div', 'talent-grid grid grid--tiles');
  for (const e of r.eintraege) {
    const c = h.el('article', 'card talent');
    const top = h.el('div', 'trick-top');
    top.append(h.el('span', e.herkunft === 'offiziell' ? 'chip chip--accent' : 'chip', e.herkunft === 'offiziell' ? 'offiziell' : 'Community'));
    c.append(top, h.el('h4', 'trick-name', e.titel), h.el('p', 'trick-repo', e.repo));
    const viz = h.el('div', 'tl-wrap');
    viz.innerHTML = timelineSvg(e);
    const legend = h.el('p', 'tl-legend');
    legend.innerHTML = '<i class="k-sit"></i>sitzt <i class="k-yaw"></i>Kopf drehen <i class="k-pitch"></i>Kopf nicken';
    c.append(viz, legend);
    c.append(h.el('div', 'trick-stats', `${secs(e.dauer)} · ${e.sitzwechsel} Haltungswechsel · ${e.kopfwechsel} Kopfbewegungen`));
    const acts = h.el('div', 'trick-acts');
    const go = h.el('button', 'btn btn--primary btn--sm', 'Vorführen');
    go.innerHTML = `${PLAY}Vorführen`;
    go.addEventListener('click', async () => { const res = await runEntry(h, 'talent', e.repo, '', go); if (res.ok) h.showView('cockpit'); });
    const a = h.el('a', 'btn btn--ghost btn--sm', 'Auf dem Hub');
    a.href = e.seite; a.target = '_blank'; a.rel = 'noopener';
    acts.append(go, a);
    c.append(acts);
    list.append(c);
  }
  if (!r.eintraege.length) list.append(h.el('div', 'empty', 'Noch keine Beiträge mit Zeitleiste auf dem Hub.'));
  target.replaceChildren(toolbar(h, r, 'talent'), list);
}

// ── Gangarten ────────────────────────────────────────────────────────
function renderGaits(target, r, h) {
  const robot = h.body === 'robotd' || h.body === 'physik';
  const status = h.el('div', 'gait-status');
  status.append(h.el('span', 'gait-now', `Aktive Gangart: ${r.gangart || 'Pollens Standard'}`));
  if (robot && r.gangart) {
    const back = h.el('button', 'btn btn--sm', 'Standard wiederherstellen');
    back.addEventListener('click', async () => { const res = await runEntry(h, 'gaits', '', 'standard', back); if (res.ok) h.reload('gaits'); });
    status.append(back);
  }
  if (!robot) status.append(h.el('span', 'gait-note', 'Im einfachen Simulator nur zum Stöbern – mit echter Physik (Einstellungen → Körper) laufen sie.'));
  else if (h.body === 'physik') status.append(h.el('span', 'gait-note', 'Läuft im Physik-Simulator – gefahrlos ausprobieren.'));
  const rows = h.el('ul', 'rows gait-list');
  for (const e of r.eintraege) {
    const li = h.el('li', 'gait');
    const text = h.el('div', 'gait-text');
    const name = h.el('b', null, e.titel);
    const sub = h.el('span', 'gait-sub', [e.repo.split('/')[0], `${e.downloads} Downloads`, e.weitere ? `+${e.weitere} weitere Zwischenstände` : ''].filter(Boolean).join(' · '));
    text.append(name, sub);
    const tags = h.el('div', 'gait-tags');
    tags.append(h.el('span', 'chip', e.rubrik));
    if (e.herkunft === 'offiziell') tags.append(h.el('span', 'chip chip--accent', 'offiziell'));
    const btn = h.el('button', 'btn btn--sm', 'Als Gangart laden');
    if (!robot) { btn.disabled = true; btn.title = 'Am echten Roboter oder mit echter Physik'; }
    let armed = null;
    // Am echten Roboter erst bestätigen (eine fremde Gangart kann sie umwerfen); im Physik-Simulator gefahrlos, ohne
    // Abfrage (0.33 – vorher fragte auch die Physik „Ente auf dem Ständer? Nochmal“, und keiner wusste, was gemeint ist)
    const warn = h.el('span', 'gait-note', 'Am Roboter: erst auf dem Ständer ausprobieren – eine fremde Gangart kann sie umwerfen.');
    warn.hidden = true;
    warn.setAttribute('role', 'status');
    const disarm = () => { armed = null; btn.classList.remove('btn--danger', 'armed'); btn.textContent = 'Als Gangart laden'; warn.hidden = true; };
    btn.addEventListener('click', async () => {
      if (!armed && h.body === 'robotd') {
        btn.classList.add('btn--danger', 'armed');
        btn.textContent = 'Wirklich laden? Zum Bestätigen nochmal tippen';
        warn.hidden = false;
        armed = setTimeout(disarm, 6000);
        return;
      }
      clearTimeout(armed);
      disarm();
      const res = await runEntry(h, 'gaits', e.repo, 'laden', btn);
      if (res.ok) h.reload('gaits');
    });
    const a = h.el('a', 'btn btn--ghost btn--sm', 'Hub');
    a.href = e.seite; a.target = '_blank'; a.rel = 'noopener';
    text.append(warn);
    li.append(text, tags, btn, a);
    rows.append(li);
  }
  target.replaceChildren(toolbar(h, r, 'gaits'), status, rows);
}

// ── Community-Tricks: erst prüfen (Physik), dann zeigen ──────────────
const VERDICT = { sicher: 'chip--good', akrobatisch: 'chip--accent', 'bleibt liegen': 'chip--warn' };
function renderCommunity(target, r, h) {
  const robot = h.body === 'robotd', physik = h.body === 'physik';
  const note = h.el('p', 'gait-note', robot
    ? 'Am Roboter laufen nur geprüfte Tricks. „Prüfen“ spielt den Trick vorher unsichtbar in der Physik durch.'
    : physik ? 'Mit echter Physik: prüfen und gefahrlos ausprobieren.'
      : 'Im einfachen Simulator nur prüfen (braucht die Physik-Pakete) – zum Ausprobieren echte Physik einschalten.');
  const rows = h.el('ul', 'rows gait-list');
  if (!r.eintraege.length) rows.append(h.el('li', 'empty', 'Auf dem Hub gerade keine Community-Tricks gefunden.'));
  for (const e of r.eintraege) {
    const li = h.el('li', 'gait');
    const text = h.el('div', 'gait-text');
    const p = e.pruefung;
    text.append(h.el('b', null, e.titel), h.el('span', 'gait-sub',
      [e.autor, e.rubrik, `${e.downloads} Downloads`, p ? `geprüft ${p.zeit}` : 'noch nicht geprüft'].filter(Boolean).join(' · ')));
    if (p && p.hinweis) text.append(h.el('span', 'gait-sub', p.hinweis));
    const tags = h.el('div', 'gait-tags');
    if (p) tags.append(h.el('span', `chip ${VERDICT[p.urteil] || ''}`, p.urteil));
    const check = h.el('button', 'btn btn--ghost btn--sm', p ? 'Nochmal prüfen' : 'Prüfen');
    check.type = 'button';
    check.addEventListener('click', async () => {
      check.textContent = 'Prüft …';
      const res = await runEntry(h, 'community', e.repo, 'pruefen', check);
      check.textContent = 'Nochmal prüfen';
      if (res.ok) h.reload('community');
    });
    const risky = robot && p && p.urteil === 'bleibt liegen';
    const show = h.el('button', 'btn btn--sm', risky ? 'Trotzdem zeigen' : 'Zeigen');
    show.type = 'button';
    if (!robot && !physik) { show.disabled = true; show.title = 'Mit echter Physik oder am Roboter'; }
    if (robot && !p) { show.disabled = true; show.title = 'Erst prüfen'; }
    show.addEventListener('click', () => runEntry(h, 'community', e.repo, risky ? 'trotzdem' : '', show));
    const a = h.el('a', 'btn btn--ghost btn--sm', 'Hub');
    a.href = e.seite; a.target = '_blank'; a.rel = 'noopener';
    li.append(text, tags, check, show, a);
    rows.append(li);
  }
  target.replaceChildren(toolbar(h, r, 'community'), note, rows);
}
