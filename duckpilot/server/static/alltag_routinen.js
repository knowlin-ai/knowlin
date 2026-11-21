// Routinen und Kalender-Abo auf der Seite „Alltag“ (seit 0.42). Gerechnet wird auf dem Server (routinen.py,
// kalender_abo.py); hier nur Anzeige und Formulare. Texte aus Kalenderdateien und Eingaben nur über textContent.

const SCHRITTE = [
  ['ueberblick', 'Tagesüberblick'], ['wetter', 'Wetter'], ['todos', 'To-dos vorlesen'],
  ['freuen', 'sich freuen'], ['aktiv', 'aufwachen'], ['ruhe', 'zur Ruhe'], ['wissen', 'Wissen zum Thema'],
];

export function initRoutinen({ $, el, api, toast, command, row, del }) {
  const box = $('al-routinen');
  if (!box) return { render() {} };

  // Schritte als Kästchen – aufwachen und zur Ruhe schließen sich aus
  const schritte = $('al-rt-schritte');
  schritte.replaceChildren(...SCHRITTE.map(([wert, text]) => {
    const lab = el('label', 'check');
    const cb = el('input');
    cb.type = 'checkbox';
    cb.value = wert;
    cb.addEventListener('change', () => {
      const gegen = { aktiv: 'ruhe', ruhe: 'aktiv' }[wert];
      if (cb.checked && gegen) schritte.querySelector(`input[value="${gegen}"]`).checked = false;
      if (wert === 'wissen') $('al-rt-thema').hidden = !cb.checked;   // Thema nur mit „Wissen“ (seit 0.51)
    });
    lab.append(cb, document.createTextNode(` ${text}`));
    return lab;
  }));

  $('al-rt-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const gewaehlt = [...schritte.querySelectorAll('input:checked')].map((c) => c.value);
    command({ aktion: 'routine_anlegen', text: $('al-rt-name').value, wann: $('al-rt-zeit').value,
      tage: $('al-rt-tage').value, schritte: gewaehlt, ansage: $('al-rt-ansage').value,
      thema: $('al-rt-thema').value }, $('al-rt-msg'), e.target);
  });

  function renderRoutinen(data) {
    const liste = data.routinen || [];
    $('al-rt-list').replaceChildren(...liste.map((r) => {
      const wann = el('span', 'al-when', r.zeit || 'auf Zuruf');
      const was = el('span', 'al-what', r.name);
      was.title = r.beschreibung || '';
      const an = el('label', 'switch al-rt-an');
      const cb = el('input');
      cb.type = 'checkbox';
      cb.checked = r.an !== false;
      cb.setAttribute('aria-label', `${r.name} zur Uhrzeit ausführen`);
      cb.addEventListener('change', () => api(`/api/alltag/routine/${encodeURIComponent(r.id)}`, 'POST', { an: cb.checked }));
      an.append(cb, el('span', null, ''));
      an.hidden = !r.zeit;
      const los = el('button', 'btn btn--sm', 'Jetzt');
      los.type = 'button';
      los.addEventListener('click', () => command({ aktion: 'routine', id: r.id }));
      return row([wann, was, an, los], del('routine', r.id), r.name);
    }));
    $('al-rt-empty').hidden = liste.length > 0;
  }

  // ── Kalender-Abo ────────────────────────────────────────────────────
  function renderAbo(data) {
    const abo = data.abo || { an: false };
    $('al-abo-form').hidden = abo.an;
    $('al-abo-an').hidden = !abo.an;
    if (!abo.an) return;
    $('al-abo-datei').textContent = abo.datei;
    const stand = abo.stand ? new Date(abo.stand).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }) : '–';
    $('al-abo-stand').textContent = `${abo.anzahl} Termin${abo.anzahl === 1 ? '' : 'e'} · zuletzt gelesen ${stand}`;
    const f = $('al-abo-fehler');
    f.textContent = abo.fehler || '';
    f.hidden = !abo.fehler;
  }
  $('al-abo-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const r = await api('/api/alltag/abo', 'POST', { pfad: $('al-abo-pfad').value }).catch(() => ({ ok: false, fehler: 'Keine Antwort' }));
    const msg = $('al-abo-msg');
    msg.textContent = r.ok ? '' : r.fehler;
    msg.className = `field-msg${r.ok ? '' : ' bad'}`;
    if (r.ok) { e.target.reset(); toast(`Abo läuft: ${r.abo.anzahl} Termin${r.abo.anzahl === 1 ? '' : 'e'}`); }
  });
  $('al-abo-lesen').addEventListener('click', () => api('/api/alltag/abo/lesen', 'POST').catch(() => toast('Keine Antwort', true)));
  $('al-abo-aus').addEventListener('click', async () => {
    const r = await api('/api/alltag/abo', 'DELETE').catch(() => null);
    if (r && r.ok) toast('Abo beendet – die Termine daraus sind weg.');
  });

  return {
    render(data) { renderRoutinen(data); renderAbo(data); },
  };
}
