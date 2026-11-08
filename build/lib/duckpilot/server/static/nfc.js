// Alltag → NFC-Tags: Tag → Satz zuordnen, berühren lässt die Ente den Satz ausführen.
// Lesen geht am Handy über Web NFC (Chrome unter Android, nur über https – also mit Tailscale).
// Ohne Lesegerät: „Auslösen“ in der Liste. Namen und Sätze nur über textContent.

export function initNfc(h) {
  const { $, el, api, toast } = h;
  let data = { tags: [], vorschlaege: [] };
  let editing = null;              // uid des Tags im Formular, "neu" für einen Probe-Tag
  let reader = null;

  async function load() {
    const r = await api('/api/nfc').catch(() => null);
    if (r && r.ok) update(r);
  }

  function update(msg) {
    data = msg;
    render();
  }

  function render() {
    const list = $('nfc-list');
    list.replaceChildren(...(data.tags || []).map((t) => {
      const li = el('li', 'al-item');
      const txt = el('span', 'al-item-text');
      txt.append(el('b', null, t.name), el('small', null, t.satz ? ` → „${t.satz}“` : ' → noch nichts zugeordnet'));
      const acts = el('span', 'al-item-acts');
      const run = el('button', 'btn btn--sm btn--ghost', 'Auslösen');
      run.type = 'button';
      run.disabled = !t.satz;
      run.addEventListener('click', () => touch(t.uid));
      const ed = el('button', 'btn btn--sm btn--ghost', 'Ändern');
      ed.type = 'button';
      ed.addEventListener('click', () => openForm(t));
      const rm = el('button', 'btn btn--sm btn--ghost', 'Entfernen');
      rm.type = 'button';
      rm.addEventListener('click', async () => {
        await api(`/api/nfc/tag/${encodeURIComponent(t.uid)}`, 'DELETE').catch(() => null);
        load();
      });
      acts.append(run, ed, rm);
      li.append(txt, acts);
      return li;
    }));
    $('nfc-vorschlaege').replaceChildren(...(data.vorschlaege || []).map((v) => new Option(v)));
  }

  function openForm(tag) {
    editing = tag ? tag.uid : 'neu';
    $('nfc-name').value = tag ? tag.name : '';
    $('nfc-satz').value = tag ? tag.satz : '';
    $('nfc-form').hidden = false;
    $('nfc-add').hidden = true;
    (tag && !tag.satz ? $('nfc-satz') : $('nfc-name')).focus();
  }
  function closeForm() {
    editing = null;
    $('nfc-form').hidden = true;
    $('nfc-add').hidden = false;
  }

  async function touch(uid) {
    const r = await api('/api/nfc/beruehrt', 'POST', { uid }).catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return; }
    if (r.neu || !r.satz) { toast(`Neuer Tag erkannt – was soll „${r.tag.name}“ auslösen?`); openForm(r.tag); }
  }

  // Ein berührter Tag (auch von einem anderen Gerät): kurz zeigen, neue gleich zum Zuordnen öffnen
  function touched(msg) {
    if (msg.neu) { openForm(msg.tag); $('nfc-msg').textContent = 'Neuer Tag – gib ihm einen Namen und einen Satz.'; }
    else $('nfc-msg').textContent = `„${msg.tag.name}“ berührt${msg.tag.satz ? ` → ${msg.tag.satz}` : ''}`;
  }

  $('nfc-add').addEventListener('click', () => openForm(null));
  $('nfc-cancel').addEventListener('click', closeForm);
  $('nfc-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const r = await api('/api/nfc/tag', 'POST', { uid: editing, name: $('nfc-name').value, satz: $('nfc-satz').value }).catch(() => null);
    if (!r || !r.ok) { toast(r ? r.fehler : 'Keine Antwort', true); return; }
    toast('Gespeichert');
    closeForm();
    load();
  });

  // Web NFC: nur wo es das gibt (Chrome unter Android, sichere Adresse)
  if ('NDEFReader' in window && window.isSecureContext) {
    const b = $('nfc-scan');
    b.hidden = false;
    b.addEventListener('click', async () => {
      if (reader) return;
      try {
        reader = new window.NDEFReader();
        await reader.scan();
        b.textContent = 'Liest Tags …';
        b.disabled = true;
        reader.onreading = (ev) => { if (ev.serialNumber) touch(ev.serialNumber); };
        reader.onreadingerror = () => toast('Tag nicht lesbar – noch einmal halten', true);
      } catch (err) {
        reader = null;
        toast(`NFC geht nicht: ${err.message || err}`, true);
      }
    });
    $('nfc-help').textContent = 'Auf „Tags lesen“ tippen, dann einen Tag an die Rückseite des Handys halten.';
  }

  return { load, update, touched };
}
