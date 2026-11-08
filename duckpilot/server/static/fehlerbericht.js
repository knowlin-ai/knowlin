// „Das lief schief“ (seit 0.36.2): Fehlerbericht mit Aufzeichnung der letzten 30 s. Erst erstellen, dann zeigt der
// Dialog, was drin ist; speichern und auf GitHub melden macht der Mensch selbst – nichts geht automatisch raus.

export function initFehlerbericht({ $, api }) {
  const dlg = $('fehler-dialog');
  if (!dlg) return;
  const msg = $('fehler-msg');
  function oeffnen() {
    msg.textContent = '';
    $('fehler-datei').hidden = true;
    $('fehler-github').hidden = true;
    $('fehler-erstellen').hidden = false;
    if (!dlg.open) dlg.showModal();
    $('fehler-text').focus();
  }
  for (const b of document.querySelectorAll('[data-fehler]')) b.addEventListener('click', oeffnen);
  $('fehler-abbrechen').addEventListener('click', () => dlg.close());
  $('fehler-erstellen').addEventListener('click', async () => {
    const r = await api('/api/fehlerbericht', 'POST', { beschreibung: $('fehler-text').value }).catch(() => null);
    if (!r || !r.ok) { msg.textContent = 'Der Bericht ging nicht – bitte noch einmal versuchen.'; return; }
    const b = r.bericht;
    msg.textContent = `Gespeichert: ${r.datei} · ${b.zustand.length} Momente, ${b.ereignisse.length} Ereignisse. `
      + 'Auf GitHub melden öffnet ein vorausgefülltes Issue – die Datei dort anhängen.';
    const a = $('fehler-datei');
    a.href = `/api/fehlerbericht/${encodeURIComponent(r.datei)}`;
    a.setAttribute('download', r.datei);
    a.hidden = false;
    const g = $('fehler-github');
    g.href = r.issue;
    g.hidden = false;
    $('fehler-erstellen').hidden = true;
  });
}
