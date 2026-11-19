// Bello lernt laufen (seit 0.43): Lernen im Physikmodell starten, Fortschritt und Ergebnis zeigen (routes/bello.py).
// Nur Zahlen – Tempo, Neigung, Stürze. Gerechnet wird auf dem Server (physics/bello.py).

const cm = (v) => `${Math.round((v || 0) * 100)} cm/s`;

export function initBelloLernt({ $, api, toast }) {
  const box = $('bello-lernt');
  if (!box) return { zeigen() {} };
  let warten = null;

  function text(s) {
    if (s.laeuft) return `Bello lernt … Runde ${s.runde || 0} von ${s.runden || '?'}`;
    if (!s.physik) return 'Dafür braucht es die Physik (MuJoCo) – unter Lernen → Training einrichten.';
    const b = s.bericht;
    if (b && b.fehler) return `Lernen ging nicht: ${b.fehler}`;
    if (b && b.vorher && b.nachher) {
      const zahlen = `vorher ${cm(b.vorher.tempo)}, Neigung ${b.vorher.neigung.toFixed(3)} rad · jetzt ${cm(b.nachher.tempo)}, Neigung ${b.nachher.neigung.toFixed(3)} rad, ${b.nachher.stuerze} von ${b.nachher.laeufe} gestürzt`;
      if (b.abgebrochen) return `Abgebrochen – nichts übernommen (${zahlen}).`;
      return b.gelernt ? `Gelernt in ${Math.round(b.dauer_s)} s: ${zahlen}.` : `Nicht besser als vorher – alles bleibt, wie es war (${zahlen}).`;
    }
    return s.gelernt ? `Gelernte Gangart: ${cm(s.tempo)} im Modell.` : 'Noch nichts gelernt.';
  }

  function zeigen(s) {
    $('bello-lernt-stand').textContent = text(s);
    $('bello-lernt-los').hidden = Boolean(s.laeuft);
    $('bello-lernt-los').disabled = !s.physik;
    $('bello-lernt-los').textContent = s.gelernt ? 'Weiterlernen' : 'Lernen';
    $('bello-lernt-stopp').hidden = !s.laeuft;
    $('bello-lernt-vergessen').hidden = !s.gelernt || Boolean(s.laeuft);
    $('bello-gang-gelernt').hidden = !s.gelernt;
    clearTimeout(warten);
    if (s.laeuft) warten = setTimeout(laden, 1000);
  }

  async function laden() {
    const s = await api('/api/bello').catch(() => null);
    if (s) zeigen(s);
  }

  async function aktion(was) {
    const r = await api('/api/bello/lernen', 'POST', { aktion: was }).catch(() => null);
    if (!r || r.ok === false) toast((r && r.fehler) || 'Keine Antwort', true);
    laden();
  }
  $('bello-lernt-los').addEventListener('click', () => aktion('start'));
  $('bello-lernt-stopp').addEventListener('click', () => aktion('stopp'));
  $('bello-lernt-vergessen').addEventListener('click', () => aktion('vergessen'));

  return { zeigen: laden };
}
