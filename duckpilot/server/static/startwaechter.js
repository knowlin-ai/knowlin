/* Startwächter (seit 0.38.66): sagt, warum das Fenster keine Verbindung zu Knowlin bekommt.

   Fund 19.11.: Nach dem Installieren blieb das Fenster bei „verbinde …“ / „getrennt“ stehen, alle Knöpfe tot, keine
   Ersten Schritte – und nirgends stand, warum. Dieses Skript ist absichtlich kein Modul und hängt an nichts anderem:
   Es läuft auch, wenn die Oberfläche selbst nicht startet. app.js meldet ihm Versuche, offene und geschlossene
   Verbindungen und Startfehler des Servers; kommt binnen FRIST keine Verbindung zustande oder scheitert sie mehrmals,
   fragt es /api/startdiagnose (braucht keine WebSocket-Verbindung) und zeigt den wahrscheinlichsten Grund. */
(() => {
  const FRIST = 10000;          // ms ohne Verbindung bis zur Meldung
  const VERSUCHE = 4;           // so viele geschlossene Verbindungen nacheinander → Meldung
  const s = { app: false, offen: false, versuche: 0, code: 0, startfehler: '', jsFehler: '', dialog: null, update: false };

  // Fehler, bevor die Oberfläche läuft: nicht geladene Skripte und Skriptfehler (nur Text, nichts geht raus)
  addEventListener('error', (e) => {
    if (s.app) return;
    const el = e.target;
    if (el && el.tagName === 'SCRIPT') s.jsFehler = `nicht geladen: ${String(el.src).replace(location.origin, '')}`;
    else if (e.message) s.jsFehler = `${e.message}${e.filename ? ` (${String(e.filename).replace(location.origin, '')}:${e.lineno})` : ''}`;
  }, true);
  addEventListener('unhandledrejection', (e) => {
    if (!s.app && !s.jsFehler) s.jsFehler = String((e.reason && e.reason.message) || e.reason).slice(0, 200);
  });

  const TEXTE = {
    de: {
      mime: ['Skripte mit falschem Typ', 'Knowlin liefert seine Skripte nicht als JavaScript aus – darum lädt der Browser die Oberfläche nicht.',
        'Knowlin auf die neueste Version bringen. Bleibt es dabei: In der Windows-Registry unter HKEY_CLASSES_ROOT\\.js den Wert „Content Type“ auf text/javascript setzen (oder löschen) und Knowlin neu starten.'],
      ui: ['Die Oberfläche startet nicht', 'Das Fenster hat Knowlin erreicht, aber die Oberfläche selbst konnte nicht starten.',
        'Erst mit Strg+Umschalt+R neu laden. Sonst: Ist Microsoft Edge aktuell? Blockiert eine Sicherheitssoftware Skripte von 127.0.0.1? Dann dort eine Ausnahme für Knowlin eintragen.'],
      still: ['Knowlin antwortet nicht', 'Der Knowlin-Dienst auf diesem PC reagiert nicht – er lädt vielleicht noch, hängt oder wurde beendet.',
        'Ein, zwei Minuten warten und neu laden. Hilft das nicht: Knowlin beenden und neu starten. Woran er hängt, steht im Protokoll.'],
      start: ['Fehler beim Start', 'Knowlin läuft, konnte diesem Fenster aber nicht alles Nötige schicken.',
        'Knowlin neu starten. Bleibt der Fehler, bitte das Protokoll schicken – der genaue Grund steht darin.'],
      ab: ['Verbindung abgewiesen', 'Knowlin hat die Verbindung dieses Fensters abgewiesen.',
        'Oft leitet ein VPN, ein Proxy oder der Web-Schutz einer Sicherheitssoftware die Verbindung um. 127.0.0.1 dort als Ausnahme eintragen (oder kurz abschalten) und neu laden.'],
      block: ['Verbindung blockiert', 'Knowlin läuft und antwortet, aber die laufende Verbindung (WebSocket) kommt nicht durch.',
        'Vermutlich blockiert eine Sicherheitssoftware oder Firewall solche Verbindungen zu 127.0.0.1. Dort eine Ausnahme für Knowlin eintragen und neu laden.'],
      grund: 'Grund', code: 'Verbindungscode', warn: 'Letzte Warnungen im Protokoll',
      log: 'Protokoll: %LOCALAPPDATA%\\duckpilot\\duckpilot.log – vor dem Weitergeben kurz durchsehen.',
      laden: 'Neu laden', ordner: 'Protokollordner öffnen', zu: 'Schließen', ordnerNein: 'Ordner ließ sich nicht öffnen.',
      warten: 'Sobald Knowlin wieder antwortet, lädt das Fenster von selbst neu.',
    },
    en: {
      mime: ['Scripts with the wrong type', 'Knowlin does not serve its scripts as JavaScript – so the browser does not load the interface.',
        'Update Knowlin to the latest version. If it stays: in the Windows registry under HKEY_CLASSES_ROOT\\.js set “Content Type” to text/javascript (or delete it) and restart Knowlin.'],
      ui: ['The interface does not start', 'The window reached Knowlin, but the interface itself could not start.',
        'First reload with Ctrl+Shift+R. Otherwise: is Microsoft Edge up to date? Does security software block scripts from 127.0.0.1? Then add an exception for Knowlin there.'],
      still: ['Knowlin does not respond', 'The Knowlin service on this PC does not react – it may still be loading, be stuck, or have quit.',
        'Wait a minute or two and reload. If that does not help: quit and restart Knowlin. The log says where it is stuck.'],
      start: ['Error while starting', 'Knowlin is running, but could not send this window everything it needs.',
        'Restart Knowlin. If the error stays, please send the log – the exact reason is in it.'],
      ab: ['Connection refused', 'Knowlin refused the connection of this window.',
        'Often a VPN, a proxy or the web protection of security software reroutes the connection. Add 127.0.0.1 as an exception there (or switch it off briefly) and reload.'],
      block: ['Connection blocked', 'Knowlin is running and answers, but the live connection (WebSocket) does not get through.',
        'Probably security software or a firewall blocks such connections to 127.0.0.1. Add an exception for Knowlin there and reload.'],
      grund: 'Reason', code: 'Connection code', warn: 'Latest warnings in the log',
      log: 'Log: %LOCALAPPDATA%\\duckpilot\\duckpilot.log – look through it before passing it on.',
      laden: 'Reload', ordner: 'Open log folder', zu: 'Close', ordnerNein: 'Could not open the folder.',
      warten: 'As soon as Knowlin answers again, the window reloads by itself.',
    },
  };

  async function diagnose() {
    const ab = typeof AbortController === 'function' ? new AbortController() : null;
    const uhr = setTimeout(() => ab && ab.abort(), 5000);
    try {
      const r = await fetch('/api/startdiagnose', { cache: 'no-store', signal: ab ? ab.signal : undefined });
      const d = r.ok ? await r.json() : null;
      if (d && !s.app) {                                   // Oberfläche kam nicht hoch: liefert Knowlin Skripte richtig?
        const k = await fetch('/static/app.js', { method: 'HEAD', cache: 'no-store' });
        d.skripttyp = k.headers.get('content-type') || '';
      }
      return d;
    } catch { return null; } finally { clearTimeout(uhr); }
  }

  /** Der wahrscheinlichste Grund – von „läuft gar nicht“ bis „läuft, aber die Leitung ist zu“. */
  function befund(d) {
    const grund = s.startfehler || (d && d.startfehler) || '';
    if (!s.app && d && d.skripttyp !== undefined && !/javascript/i.test(d.skripttyp)) {
      return { art: 'mime', details: `/static/app.js: ${d.skripttyp || '?'}` };
    }
    if (!s.app) return { art: 'ui', details: s.jsFehler };
    if (!d) return { art: 'still', details: '' };
    if (grund) return { art: 'start', details: grund };
    if (d.ablehnung) return { art: 'ab', details: d.ablehnung };
    return { art: 'block', details: '' };
  }

  // Neu laden erst, wenn Knowlin wieder antwortet (seit 0.56, Fund des Maintainers: „bei Update sagt er ganz oft Knowlin
  // antwortet nicht und dann neu laden führt zu“ Edges Fehlerseite – von der kommt das Fenster nicht mehr allein zurück)
  let wartet = false;
  async function wartenUndLaden(msg, T) {
    if (msg) msg.textContent = T.warten;
    if (wartet) return;
    wartet = true;
    for (;;) {
      try {
        const r = await fetch('/api/ping', { cache: 'no-store' });
        if (r.ok) { location.reload(); return; }
      } catch { /* noch weg */ }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function zeigen(b, d) {
    const sprache = (d && d.sprache) || (String(navigator.language || '').startsWith('de') ? 'de' : 'en');
    const T = TEXTE[sprache] || TEXTE.de;
    const [titel, text, rat] = T[b.art];
    weg();
    const dlg = el('dialog', 'quit-dialog startwaechter');
    dlg.id = 'startwaechter';
    dlg.dataset.art = b.art;
    dlg.setAttribute('aria-labelledby', 'startwaechter-titel');
    dlg.setAttribute('role', 'alertdialog');
    const h = el('h2', '', titel);
    h.id = 'startwaechter-titel';
    dlg.append(h, el('p', 'startwaechter-text', text));
    if (b.details) {
      const p = el('p', 'startwaechter-grund');
      p.append(el('b', '', `${T.grund}: `), document.createTextNode(b.details));
      dlg.append(p);
    }
    if (b.art === 'block' && s.code) dlg.append(el('p', 'startwaechter-klein', `${T.code}: ${s.code}`));
    dlg.append(el('p', 'startwaechter-rat', rat));
    if (d && d.warnungen && d.warnungen.length) {
      const det = el('details', 'startwaechter-warn');
      det.append(el('summary', '', T.warn), el('pre', '', d.warnungen.join('\n')));
      dlg.append(det);
    }
    dlg.append(el('p', 'startwaechter-klein', `${T.log}${d && d.version ? ` · Knowlin ${d.version}` : ''}`));
    const msg = el('p', 'startwaechter-klein');
    msg.setAttribute('role', 'status');
    const fuss = el('div', 'quit-foot startwaechter-fuss');
    const zu = el('button', 'btn btn--ghost', T.zu);
    const ordner = el('button', 'btn', T.ordner);
    const laden = el('button', 'btn btn--primary', T.laden);
    for (const k of [zu, ordner, laden]) k.type = 'button';
    zu.addEventListener('click', () => weg());
    laden.addEventListener('click', () => wartenUndLaden(msg, T));
    ordner.addEventListener('click', async () => {
      try {
        const r = await fetch('/api/open-folder', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ which: 'daten' }) });
        if (!r.ok) throw new Error(String(r.status));
        msg.textContent = '';
      } catch { msg.textContent = T.ordnerNein; }
    });
    if (b.art === 'still') {
      ordner.hidden = true;                             // ohne Antwort kann der Dienst auch keinen Ordner öffnen
      laden.hidden = true;                              // und Neu laden jetzt führte nur auf die Fehlerseite des Browsers
      wartenUndLaden(null, T);                          // kommt er wieder, lädt das Fenster von selbst
      dlg.append(el('p', 'startwaechter-rat', T.warten));
    }
    fuss.append(zu, ordner, laden);
    dlg.append(msg, fuss);
    document.body.append(dlg);
    s.dialog = dlg;
    try { dlg.showModal(); } catch { dlg.setAttribute('open', ''); }
    laden.focus();
  }

  function weg() {
    if (!s.dialog) return;
    try { s.dialog.close(); } catch { /* schon zu */ }
    s.dialog.remove();
    s.dialog = null;
  }

  let laeuft = false;
  async function pruefen() {
    if (laeuft || s.update) return;
    laeuft = true;
    try {
      const d = await diagnose();
      if (s.offen && !s.startfehler) return;              // inzwischen verbunden – alles gut
      zeigen(befund(d), d);
    } finally { laeuft = false; }
  }

  window.knowlinVerbindung = {
    versuch() { s.app = true; },
    offen() { s.app = true; s.offen = true; s.versuche = 0; if (!s.startfehler) weg(); },
    zu(code) {
      s.offen = false; s.versuche += 1; s.code = code || 0;
      if (s.versuche >= VERSUCHE && !s.dialog) pruefen();
    },
    startfehler(grund) { s.app = true; s.startfehler = String(grund || '').slice(0, 600); pruefen(); },
    // Update oder Neustart läuft (beenden.js): Knowlin ist absichtlich weg – keine Meldung, das Fenster lädt dann selbst
    update() { s.update = true; weg(); },
    befund, zustand: () => ({ ...s, dialog: !!s.dialog }),     // für Tests
  };
  setTimeout(() => { if (!s.offen && !s.dialog) pruefen(); }, FRIST);
})();
