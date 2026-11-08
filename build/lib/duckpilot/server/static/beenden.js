// Beenden wie bei Windows-Programmen: ganz beenden, im Hintergrund weiterlaufen oder (nach einem Update) neu starten.
// Nur im Programmfenster am PC – am Handy gibt es den Knopf nicht.

export function initBeenden(h) {
  const { $, api, el, toast, isRemote } = h;
  let info = null;
  let later = false;
  const dlg = $('quit-dialog');

  function update(msg) {
    if (!msg) return;
    info = msg;
    const can = !!msg.kann && !isRemote();
    $('quit-btn').hidden = !can;
    const fresh = can && msg.neu && msg.neu !== msg.version;
    $('quit-restart').hidden = !fresh;
    $('quit-restart-title').textContent = fresh ? `Neu starten mit ${msg.neu}` : 'Neu starten';
    $('quit-version').textContent = `Läuft: Knowlin ${msg.version}` + (fresh ? ` · bereit: ${msg.neu}` : '');
    $('update-bar').hidden = !fresh || later;
    if (fresh) $('update-text').textContent = `Knowlin ${msg.neu} liegt bereit (läuft noch ${msg.version}).`;
    const ul = $('quit-running');
    ul.replaceChildren(...(msg.laeuft || []).map((t) => el('li', null, t)));
    ul.hidden = !(msg.laeuft || []).length;
  }

  async function open() {
    const r = await api('/api/beenden').catch(() => null);
    if (r && r.type === 'beenden') update(r);
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
    dlg.querySelector('.quit-choice:not([hidden])').focus();
  }
  function close() { if (dlg.open) dlg.close(); }

  function done(title, text) {
    $('quit-done-title').textContent = title;
    $('quit-done-text').textContent = text;
    $('quit-done').hidden = false;
  }

  async function waitForRestart(oldVersion) {
    for (let i = 0; i < 90; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const p = await fetch('/api/ping', { cache: 'no-store' }).then((x) => x.json()).catch(() => null);
      if (p && p.version && p.version !== oldVersion) { location.reload(); return; }
      if (p && p.version && i > 20) { location.reload(); return; }
    }
    done('Neustart dauert länger', 'Starte Knowlin über die Desktop-Verknüpfung.');
  }

  async function choose(art) {
    close();
    const r = await api('/api/beenden', 'POST', { art }).catch(() => null);
    if (!r || !r.ok) { toast((r && r.fehler) || 'Ging nicht', true); return; }
    if (art === 'hintergrund') {
      done('Knowlin läuft im Hintergrund weiter', 'Die Verkörperung ruht. Wieder öffnen mit der Desktop-Verknüpfung – dieses Fenster kannst du schließen.');
      setTimeout(() => window.close(), 400);
    } else if (art === 'neustart') {
      done('Knowlin startet neu …', 'Einen Moment – das Fenster lädt sich gleich von selbst neu.');
      waitForRestart(info && info.version);
    } else {
      done('Knowlin ist beendet', 'Du kannst dieses Fenster schließen. Starten wieder mit der Desktop-Verknüpfung.');
      setTimeout(() => window.close(), 400);
    }
  }

  $('quit-btn').addEventListener('click', open);
  $('quit-cancel').addEventListener('click', close);
  for (const b of dlg.querySelectorAll('.quit-choice')) b.addEventListener('click', () => choose(b.dataset.art));
  dlg.addEventListener('click', (e) => { if (e.target === dlg) close(); });      // Klick neben den Dialog
  $('update-go').addEventListener('click', () => choose('neustart'));
  $('update-later').addEventListener('click', () => { later = true; $('update-bar').hidden = true; });

  return { update, open };
}
