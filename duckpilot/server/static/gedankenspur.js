// Gedankenspur (seit 0.38.44, Etappe G3): was Knowlin von sich aus getan hat und warum – je Handlung eine Zeile.
// Lädt, sobald die Karte unter Charakter → Persönlichkeit sichtbar wird; leeren nur am PC.

const QUELLE = { antrieb: 'von sich aus', gespraech: 'im Gespräch', reflex: 'Reflex' };

function uhrzeit(s) {
  return new Date(s * 1000).toLocaleTimeString(document.documentElement.lang || 'de', { hour: '2-digit', minute: '2-digit' });
}

export function initGedankenspur() {
  const liste = document.getElementById('gedanken-liste');
  if (!liste) return;
  const leer = document.getElementById('gedanken-leer');

  async function laden() {
    let daten;
    try { daten = await (await fetch('/api/gedankenspur')).json(); } catch { return; }
    const zeilen = daten.zeilen || [];
    leer.hidden = zeilen.length > 0;
    liste.hidden = !zeilen.length;
    liste.replaceChildren(...zeilen.map((z) => {
      const li = document.createElement('li');
      li.className = 'gedanke';
      const kopf = document.createElement('p');
      kopf.className = 'gedanke-was';
      const zeit = document.createElement('time');
      zeit.dateTime = new Date(z.zeit * 1000).toISOString();
      zeit.textContent = uhrzeit(z.zeit);
      kopf.append(zeit, ` ${z.was}`);
      const warum = document.createElement('p');
      warum.className = 'gedanke-warum';
      warum.textContent = [`${QUELLE[z.quelle] || z.quelle}: ${z.warum}`, z.ergebnis !== 'getan' ? z.ergebnis : '']
        .filter(Boolean).join(' · ');
      li.append(kopf, warum);
      return li;
    }));
  }

  document.getElementById('gedanken-neu')?.addEventListener('click', laden);
  document.getElementById('gedanken-leeren')?.addEventListener('click', async () => {
    try { await fetch('/api/gedankenspur', { method: 'DELETE' }); } catch { /* nächster Versuch beim Laden */ }
    laden();
  });
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) laden(); }).observe(liste.closest('section'));
}
