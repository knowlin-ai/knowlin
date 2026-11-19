// Smart Home und Haushalt auf der Seite „Alltag“ (seit 0.45). Geschaltet wird auf dem Server (haus.py); was er nicht
// freigibt (Schlösser, Alarm, Heizung …), steht gar nicht erst in der Liste. Namen aus Home Assistant und der Hue Bridge
// landen nur über textContent im Dokument. Token und Hue-Schlüssel gehen in den Tresor und kommen nie zurück.

const HANDLUNG = { an: 'An', aus: 'Aus', start: 'Start', pause: 'Pause', stopp: 'Stopp', heim: 'Zur Station' };
const ART = { licht: 'Licht', sauger: 'Saugroboter', szene: 'Szene' };

export function initHaus({ $, el, api, toast }) {
  const box = $('al-haus');
  if (!box) return { render() {} };
  let stand = null;
  let zuletzt = 0;
  let warten = null;

  const msg = (text, bad = false) => {
    const m = $('haus-msg');
    m.textContent = text || '';
    m.classList.toggle('bad', !!bad);
  };
  const post = (pfad, body, methode = 'POST') => api(pfad, methode, body).catch(() => ({ ok: false, fehler: 'Keine Antwort' }));

  async function laden(neu = false) {
    zuletzt = Date.now();
    const s = await api('/api/haus').catch(() => null);
    if (!s) return;
    stand = s;
    renderStand();
    if (s.ha.verbunden || s.hue.verbunden) {
      const g = await api(`/api/haus/geraete${neu ? '?neu=true' : ''}`).catch(() => null);
      if (g) renderGeraete(g);
    } else {
      renderGeraete({ geraete: [], fehler: [] });
    }
    if (s.aufraeumen && s.aufraeumen.laeuft && !warten) warten = setTimeout(() => { warten = null; laden(); }, 3000);
  }

  function renderStand() {
    const s = stand;
    $('haus-nie').textContent = s.nie || '';
    $('haus-neu').hidden = !(s.ha.verbunden || s.hue.verbunden);
    $('haus-ha-form').hidden = s.ha.verbunden;
    $('haus-ha-an').hidden = !s.ha.verbunden;
    $('haus-ha-stand').textContent = s.ha.verbunden ? `Verbunden: ${s.ha.adresse}${s.ha.melden ? ` · Meldungen an ${s.ha.melden}` : ''}` : '';
    $('haus-hue-form').hidden = s.hue.verbunden;
    $('haus-hue-an').hidden = !s.hue.verbunden;
    $('haus-hue-stand').textContent = s.hue.verbunden ? `Gekoppelt: ${s.hue.adresse}` : '';
    if (!s.ha.verbunden && s.hue.adresse) $('haus-hue-adresse').value = s.hue.adresse;
    const haushalt = s.kann_aufraeumen || s.kann_heimkehr;
    $('haus-haushalt').hidden = !haushalt;
    $('haus-aufraeumen-box').hidden = !s.kann_aufraeumen;
    $('haus-korb').hidden = !s.kann_aufraeumen;
    $('haus-akku-box').hidden = !s.kann_heimkehr;
    $('haus-akku-knapp').hidden = !s.simulator;
    $('haus-schwelle').value = String(s.schwelle);
    const orte = [s.korb ? 'Korb gemerkt' : (s.kann_aufraeumen ? 'noch kein Korb' : ''),
      s.ladeplatz ? 'Ladeplatz gemerkt' : 'noch kein Ladeplatz'].filter(Boolean);
    const akku = typeof s.akku === 'number' ? ` · Akku ${Math.round(s.akku * 100)} %` : '';
    $('haus-orte').textContent = orte.join(' · ') + akku;
    const lauf = s.aufraeumen && s.aufraeumen.laeuft;
    $('haus-aufraeumen').disabled = !!lauf;
    $('haus-aufraeumen').textContent = lauf ? `Räumt auf … (${s.aufraeumen.gebracht.length}/${s.aufraeumen.von})`
      : 'Vor dem Saugroboter aufräumen';
  }

  function renderGeraete({ geraete = [], fehler = [] }) {
    $('haus-leer').hidden = geraete.length > 0;
    $('haus-leer').textContent = (stand && (stand.ha.verbunden || stand.hue.verbunden))
      ? 'Keine freigegebenen Geräte gefunden (Licht, Saugroboter, Szenen).' : 'Noch nichts verbunden.';
    if (fehler.length) msg(fehler.join(' · '), true);
    $('haus-geraete').replaceChildren(...geraete.map((g) => {
      const li = el('li', 'al-item haus-geraet');
      const art = el('span', 'al-when', ART[g.art] || g.art);
      const name = el('span', 'al-what', g.raum && !g.name.includes(g.raum) ? `${g.name} · ${g.raum}` : g.name);
      const acts = el('span', 'haus-acts');
      for (const h of g.handlungen) {
        const b = el('button', 'btn btn--sm' + ((g.an === true && h === 'an') || (g.an === false && h === 'aus') ? ' is-on' : ''), HANDLUNG[h] || h);
        b.type = 'button';
        b.setAttribute('aria-label', `${g.name}: ${HANDLUNG[h] || h}`);
        if (g.an !== null && (h === 'an' || h === 'aus')) b.setAttribute('aria-pressed', String((g.an && h === 'an') || (!g.an && h === 'aus')));
        b.addEventListener('click', async () => {
          b.disabled = true;
          const r = await post('/api/haus/schalten', { id: g.id, aktion: h });
          b.disabled = false;
          if (!r.ok) { msg(r.fehler, true); return; }
          msg(`${g.name}: ${HANDLUNG[h] || h}`);
          laden();
        });
        acts.append(b);
      }
      li.append(art, name, acts);
      return li;
    }));
    const sauger = geraete.filter((g) => g.art === 'sauger');
    const sel = $('haus-sauger');
    const gewaehlt = (stand && stand.sauger_danach) || '';
    sel.replaceChildren(el('option', null, 'keinem Saugroboter'), ...sauger.map((g) => {
      const o = el('option', null, g.name);
      o.value = g.id;
      return o;
    }));
    sel.firstChild.value = '';
    sel.value = sauger.some((g) => g.id === gewaehlt) ? gewaehlt : '';
  }

  // ── Einrichten (nur am PC) ──────────────────────────────────────────
  const emsg = (text, bad = false) => {
    const m = $('haus-einrichten-msg');
    m.textContent = text || '';
    m.classList.toggle('bad', !!bad);
  };
  $('haus-ha-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    emsg('Verbinde …');
    const r = await post('/api/haus/ha', { adresse: $('haus-ha-adresse').value, token: $('haus-ha-token').value,
      melden: $('haus-ha-melden').value });
    $('haus-ha-token').value = '';
    if (!r.ok) { emsg(r.fehler, true); return; }
    emsg('Home Assistant verbunden.');
    laden(true);
  });
  $('haus-hue-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    emsg('Kopple …');
    const r = await post('/api/haus/hue', { adresse: $('haus-hue-adresse').value });
    if (!r.ok) { emsg(r.fehler, !r.knopf); return; }
    emsg('Hue Bridge gekoppelt.');
    laden(true);
  });
  for (const weg of ['ha', 'hue']) {
    $(`haus-${weg}-aus`).addEventListener('click', async () => {
      await post(`/api/haus/${weg}`, undefined, 'DELETE');
      emsg(weg === 'ha' ? 'Home Assistant getrennt, Token gelöscht.' : 'Hue Bridge getrennt, Schlüssel gelöscht.');
      laden();
    });
  }
  $('haus-neu').addEventListener('click', () => laden(true));

  // ── Haushalt ────────────────────────────────────────────────────────
  for (const was of ['korb', 'ladeplatz']) {
    $(`haus-${was}`).addEventListener('click', async () => {
      const r = await post('/api/haus/ort', { was });
      if (!r.ok) { msg(r.fehler, true); return; }
      msg(`${r.ort} gemerkt – genau hier, wo sie gerade steht.`);
      stand = { ...stand, ...r };
      renderStand();
    });
  }
  $('haus-sauger').addEventListener('change', async (e) => {
    const r = await post('/api/haus/einstellungen', { sauger_danach: e.target.value });
    if (!r.ok) msg(r.fehler, true);
  });
  $('haus-schwelle').addEventListener('change', async (e) => {
    const r = await post('/api/haus/einstellungen', { akku_schwelle: Number(e.target.value) });
    if (!r.ok) msg(r.fehler, true);
  });
  $('haus-aufraeumen').addEventListener('click', async () => {
    const r = await post('/api/haus/aufraeumen', { sauger: !!$('haus-sauger').value });
    if (!r.ok) { msg(r.fehler, true); return; }
    msg(r.text);
    laden();
  });
  $('haus-akku-knapp').addEventListener('click', async () => {
    const r = await post('/api/haus/akku_knapp', {});
    if (!r.ok) { msg(r.fehler, true); return; }
    toast(r.ladeplatz ? `Akku auf ${Math.round(r.akku * 100)} % – gleich geht sie zum Ladeplatz.`
      : `Akku auf ${Math.round(r.akku * 100)} % – merk dir erst einen Ladeplatz.`);
  });

  return {
    render() {
      if (Date.now() - zuletzt > 8000) laden();
    },
  };
}
