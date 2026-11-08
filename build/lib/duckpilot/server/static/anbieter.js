// Anderes KI-Modell (seit 0.35): Anbieter wählen, Schlüssel in den Tresor, Modell aus der Liste des Anbieters.
// Nur am PC (die Routen /api/anbieter/* lehnen Handys ab). Der Schlüssel wird nie zurückgegeben – nur, ob es einen gibt.

export function initAnbieter({ $, el, api, toast, save }) {
  let st = null;
  const pick = $('anbieter-pick');
  if (!pick) return { load() {} };

  function render() {
    if (!st) return;
    const a = st.anbieter.find((x) => x.id === pick.value) || st.anbieter[0];
    if (!pick.options.length) {
      pick.replaceChildren(...st.anbieter.map((x) => { const o = el('option', null, x.name); o.value = x.id; return o; }));
      pick.value = st.gewaehlt;
    }
    $('anbieter-key-form').hidden = !a.schluessel;
    $('anbieter-url-field').hidden = a.schluessel;
    if (!a.schluessel && document.activeElement !== $('anbieter-url')) $('anbieter-url').value = st.adresse || a.adresse;
    const m = $('anbieter-model');
    if (st.modell && ![...m.options].some((o) => o.value === st.modell)) {
      const o = el('option', null, st.modell); o.value = st.modell; m.append(o);
    }
    m.value = st.modell || '';
    const s = $('anbieter-state');
    s.replaceChildren();
    const gut = st.bereit && st.aktiv;
    s.append(el('i', `dot ${gut ? 'dot--good' : 'dot--warning'}`), document.createTextNode(' ' + (
      st.fehler_zuletzt ? `Zuletzt: ${st.fehler_zuletzt}`
        : a.schluessel && !a.hat_schluessel ? 'Noch kein Schlüssel für diesen Anbieter.'
          : !st.modell ? 'Noch kein Modell gewählt – „Modelle laden“.'
            : st.aktiv ? `Denkt mit ${st.modell}.` : `Bereit: ${st.modell}. Oben „Anderes Modell“ wählen.`)));
  }

  async function load() {
    st = await api('/api/anbieter').catch(() => null);
    render();
  }

  pick.addEventListener('change', async () => {
    if (await save({ anbieter: pick.value, anbieter_modell: '' })) { $('anbieter-model').replaceChildren(); await load(); }
  });
  $('anbieter-key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const key = $('anbieter-key').value.trim();
    if (!key) return;
    const r = await api('/api/anbieter/schluessel', 'POST', { anbieter: pick.value, schluessel: key }).catch(() => ({ ok: false }));
    $('anbieter-key').value = '';
    toast(r.ok ? 'Schlüssel gespeichert' : (r.fehler || 'Nicht gespeichert'), !r.ok);
    await load();
  });
  $('anbieter-key-weg').addEventListener('click', async () => {
    await api('/api/anbieter/schluessel', 'DELETE', { anbieter: pick.value }).catch(() => null);
    toast('Schlüssel entfernt');
    await load();
  });
  $('anbieter-url').addEventListener('change', async (e) => { if (await save({ anbieter_adresse: e.target.value })) await load(); });
  $('anbieter-load').addEventListener('click', async () => {
    const r = await api('/api/anbieter/modelle', 'POST', { anbieter: pick.value, adresse: $('anbieter-url').value }).catch(() => ({ ok: false }));
    if (!r.ok) { toast(r.fehler || 'Keine Antwort', true); return; }
    const m = $('anbieter-model');
    m.replaceChildren(el('option', null, '– wählen –'), ...r.modelle.map((x) => { const o = el('option', null, x); o.value = x; return o; }));
    m.firstChild.value = '';
    toast(`${r.modelle.length} Modelle gefunden`);
  });
  $('anbieter-model').addEventListener('change', async (e) => {
    if (await save({ anbieter_modell: e.target.value }, e.target.value ? `Modell: ${e.target.value}` : null)) await load();
  });
  return { load };
}
