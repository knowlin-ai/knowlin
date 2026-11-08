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
    // Seit 0.38.32: neue Version auf GitHub (nur wenn nicht schon eine im Programmordner bereitliegt)
    const on = msg.online && msg.online.neu && !fresh && !isRemote() ? msg.online : null;
    $('update-bar').hidden = !(fresh || on) || later;
    $('update-go').hidden = !fresh;
    $('update-install').hidden = !(on && on.kann && can);
    $('update-notes').hidden = !on;
    if (on) $('update-notes').href = on.neu.seite;
    if (fresh) $('update-text').textContent = `Knowlin ${msg.neu} liegt bereit (läuft noch ${msg.version}).`;
    else if (on) {
      $('update-text').textContent = on.kann && can ? `Knowlin ${on.neu.version} ist da.`
        : `Knowlin ${on.neu.version} ist da – ${on.art === 'quelle' ? 'neuen Stand holen und start.bat starten' : 'auf der Release-Seite herunterladen'}.`;
    }
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

  // Nach einem Update bis zu 5 Minuten warten (seit 0.38.33): Der stille Installer entpackt ~100 MB, der Virenscanner
  // prüft jede Datei – das dauerte beim ersten echten Update länger als die 90 s für einen einfachen Neustart.
  async function waitForRestart(oldVersion, update = false) {
    const sekunden = update ? 300 : 90;
    for (let i = 0; i < sekunden; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const p = await fetch('/api/ping', { cache: 'no-store' }).then((x) => x.json()).catch(() => null);
      if (p && p.version && p.version !== oldVersion) { location.reload(); return; }
      if (p && p.version && i > 20 && !update) { location.reload(); return; }
      if (update && i === 90) done('Das Update wird noch installiert …', 'Das kann ein paar Minuten dauern – das Fenster lädt sich dann von selbst neu.');
    }
    done(update ? 'Das Update dauert ungewöhnlich lange' : 'Neustart dauert länger',
      update ? 'Starte Knowlin über die Desktop-Verknüpfung – unter Einstellungen → Über steht dann die Version.'
        : 'Starte Knowlin über die Desktop-Verknüpfung.');
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
  $('update-install').addEventListener('click', async () => {
    const knopf = $('update-install');
    knopf.disabled = true;
    knopf.classList.add('is-busy');
    $('update-text').textContent = 'Lade das Update und prüfe es …';
    const r = await api('/api/update/installieren', 'POST').catch(() => null);
    if (!r || !r.ok) {
      knopf.disabled = false;
      knopf.classList.remove('is-busy');
      $('update-text').textContent = (r && r.fehler) || 'Das Update ging nicht.';
      return;
    }
    done(`Knowlin ${r.version} wird installiert …`, 'Knowlin startet gleich von selbst neu – dieses Fenster lädt sich dann neu.');
    waitForRestart(info && info.version, true);
  });

  // Einstellungen → Über: von Hand nach Updates suchen (seit 0.38.32)
  $('update-pruefen')?.addEventListener('click', async () => {
    const st = $('update-stand');
    st.textContent = 'Suche …';
    const r = await api('/api/update/pruefen', 'POST').catch(() => null);
    if (!r || !r.ok) { st.textContent = (r && r.fehler) || 'GitHub war nicht erreichbar.'; return; }
    later = false;
    st.textContent = r.neu ? `Knowlin ${r.neu.version} ist da – siehe Hinweis oben.` : `Knowlin ${r.version} ist aktuell.`;
    // Wie das letzte Update ausging (seit 0.38.34, aus updates/update.log) – hilft, wenn eins nicht durchlief
    if (r.letztes_update) st.textContent += ` Letztes Update: ${r.letztes_update}`;
  });

  return { update, open };
}
