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
      // Release schon da, Installer noch im Bau (seit 0.38.43): nicht „herunterladen“ sagen, wenn es nichts zu laden gibt
      const imBau = on.art === 'installer' && !on.neu.installer;
      $('update-text').textContent = on.kann && can ? `Knowlin ${on.neu.version} ist da.`
        : imBau ? `Knowlin ${on.neu.version} kommt gleich – der Installer wird noch gebaut. Knowlin schaut in einer Viertelstunde wieder nach.`
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

  // Update und Neustart Schritt für Schritt (seit 0.38.38, Hinweis: „man sieht immer nicht, was gerade passiert
  // oder ob es hängt“). Der neue Knowlin meldet sich schon beim Hochfahren (startstatus.py) mit seinem Schritt.
  const SCHRITTE_UPDATE = [['laden', 'Herunterladen'], ['pruefen', 'Prüfsumme prüfen'], ['installieren', 'Installieren'],
    ['startet', 'Knowlin startet'], ['fertig', 'Fertig']];
  const SCHRITTE_NEUSTART = [['beenden', 'Knowlin beendet sich'], ['startet', 'Knowlin startet'], ['fertig', 'Fertig']];
  let t0 = 0;
  let uhr = null;
  function zeit() {
    const s = Math.round((Date.now() - t0) / 1000);
    $('quit-zeit').textContent = `seit ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} min`;
  }
  function schritte(liste, jetzt, detail = '') {
    const ol = $('quit-schritte');
    const i = liste.findIndex(([k]) => k === jetzt);
    ol.replaceChildren(...liste.map(([k, text], j) => {
      const li = el('li', j < i ? 'is-fertig' : j === i ? 'is-jetzt' : null, text);
      if (j === i) {
        li.setAttribute('aria-current', 'step');
        if (detail) li.append(el('small', null, detail));
      }
      return li;
    }));
    ol.hidden = false;
    $('quit-zeit').hidden = false;
    if (!uhr) { t0 = Date.now(); uhr = setInterval(zeit, 1000); zeit(); }
  }
  function balken(knoten, anteil) {         // anteil 0…1 oder null = läuft, Dauer unbekannt
    knoten.hidden = false;
    knoten.classList.toggle('is-busy', anteil == null);
    knoten.querySelector('i').style.width = anteil == null ? '0' : `${Math.round(anteil * 100)}%`;
    if (anteil == null) knoten.removeAttribute('aria-valuenow');
    else knoten.setAttribute('aria-valuenow', String(Math.round(anteil * 100)));
  }
  const mb = (n) => (n / 1048576).toFixed(n < 10485760 ? 1 : 0).replace('.', ',');

  // Nach einem Update bis zu 10 Minuten warten (der erste Start nach einem Update dauerte bei Alex 2 Minuten: Windows
  // prüft die neuen Dateien). Solange der neue Knowlin meldet, was er tut, wird nicht aufgegeben.
  async function waitForRestart(oldVersion, update = false) {
    const liste = update ? SCHRITTE_UPDATE : SCHRITTE_NEUSTART;
    const grenze = update ? 600 : 180;
    balken($('quit-balken'), null);
    let gemeldet = 0;
    let weg = false;                         // war der alte Knowlin schon weg? Vorher antwortet er evtl. noch kurz
    for (let i = 0; i < grenze || (gemeldet && i - gemeldet < 60); i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const p = await fetch('/api/ping', { cache: 'no-store' }).then((x) => x.json()).catch(() => null);
      if (!p || p.startet) weg = true;
      if (p && p.startet) {                  // der neue Knowlin fährt hoch und sagt, wobei er ist
        gemeldet = i;
        $('quit-done-title').textContent = `Knowlin ${p.version_neu || ''} startet …`.replace('  ', ' ');
        $('quit-done-text').textContent = 'Gleich geschafft – das Fenster lädt sich dann von selbst neu.';
        schritte(liste, 'startet', p.schritt || '');
        continue;
      }
      if (p && p.version && (p.version !== oldVersion || (weg && !update) || (!update && i > 20))) {
        schritte(liste, 'fertig');
        balken($('quit-balken'), 1);
        setTimeout(() => location.reload(), 400);
        return;
      }
      if (p && p.version && update && weg) {  // wieder da, aber mit der alten Version: Update nicht durchgelaufen
        clearInterval(uhr);
        $('quit-balken').hidden = true;
        done('Das Update ist nicht durchgelaufen', `Knowlin läuft wieder mit ${p.version}. Unter Einstellungen → Über steht, wie das letzte Update ausging.`);
        setTimeout(() => location.reload(), 6000);
        return;
      }
      if (!p && update && !gemeldet && i === 120) {
        $('quit-done-text').textContent = 'Das dauert länger als sonst – Windows prüft die neuen Dateien. Das Fenster lädt sich dann von selbst neu.';
      }
    }
    clearInterval(uhr);
    $('quit-balken').hidden = true;
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
      schritte(SCHRITTE_NEUSTART, 'beenden');
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
    $('update-text').textContent = 'Lade das Update …';
    // Während das Update lädt: Fortschritt abfragen (seit 0.38.38)
    let fertig = false;
    const abfragen = async () => {
      while (!fertig) {
        const f = await api('/api/update/fortschritt').catch(() => null);
        if (fertig) break;
        if (f && f.schritt === 'laden') {
          $('update-text').textContent = f.gesamt ? `Lade das Update … ${mb(f.geladen || 0)} von ${mb(f.gesamt)} MB`
            : `Lade das Update … ${mb(f.geladen || 0)} MB`;
          balken($('update-balken'), f.gesamt ? Math.min(1, (f.geladen || 0) / f.gesamt) : null);
        } else if (f && f.schritt === 'pruefen') {
          $('update-text').textContent = 'Prüfe die Prüfsumme …';
          balken($('update-balken'), 1);
        } else if (f && f.schritt === 'paket') {
          $('update-text').textContent = 'Installiere das neue Paket …';
          balken($('update-balken'), null);
        }
        await new Promise((r) => setTimeout(r, 400));
      }
    };
    abfragen();
    const r = await api('/api/update/installieren', 'POST').catch(() => null);
    fertig = true;
    $('update-balken').hidden = true;
    if (!r || !r.ok) {
      knopf.disabled = false;
      knopf.classList.remove('is-busy');
      $('update-text').textContent = (r && r.fehler) || 'Das Update ging nicht.';
      return;
    }
    done(`Knowlin ${r.version} wird installiert …`, 'Knowlin beendet sich, installiert und startet von selbst neu – meist in ein bis drei Minuten. Das Fenster lädt sich dann neu.');
    schritte(SCHRITTE_UPDATE, 'installieren');
    waitForRestart(info && info.version, true);
  });

  // Einstellungen → Über: von Hand nach Updates suchen (seit 0.38.32)
  $('update-pruefen')?.addEventListener('click', async () => {
    const st = $('update-stand');
    st.textContent = 'Suche …';
    const r = await api('/api/update/pruefen', 'POST').catch(() => null);
    if (!r || !r.ok) { st.textContent = (r && r.fehler) || 'GitHub war nicht erreichbar.'; return; }
    later = false;
    st.textContent = !r.neu ? `Knowlin ${r.version} ist aktuell.`
      : r.art === 'installer' && !r.neu.installer ? `Knowlin ${r.neu.version} ist veröffentlicht, der Installer wird noch gebaut (etwa 20 Minuten).`
        : `Knowlin ${r.neu.version} ist da – siehe Hinweis oben.`;
    // Wie das letzte Update ausging (seit 0.38.34, aus updates/update.log) – hilft, wenn eins nicht durchlief
    if (r.letztes_update) st.textContent += ` Letztes Update: ${r.letztes_update}.`;
  });

  return { update, open };
}
