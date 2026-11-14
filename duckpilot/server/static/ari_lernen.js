// Ari lernt durch Vormachen (seit 0.38.64, Stufe A; Maintainer: „Ari zuerst“, „A, dann B“). Im Vormach-Fenster:
// Aufgabe wählen, Beispiele aufnehmen (deine Hand führt Ari, bis der Würfel in der Kiste liegt), lernen, selbst
// ausprobieren, als ZIP für LeRobot mitnehmen. Gerechnet wird auf dem Server (arm_lernen.py, arm_schule.py).

export function initAriLernen({ $, api, toast }) {
  const box = $('ari-lernen');
  if (!box) return { zeigen() {}, aus() {} };
  const text = $('ari-lernen-text');
  const knopf = {
    aufnehmen: $('ari-aufnehmen'), neu: $('ari-neu'), lernen: $('ari-lernen-los'), probieren: $('ari-probieren'),
  };
  let poll = null;
  let stand = null;

  function optionen(sel, liste, wert) {
    sel.replaceChildren(...liste.map((n) => { const o = document.createElement('option'); o.value = n; o.textContent = n; return o; }));
    sel.value = wert;
  }

  function anzeigen(s) {
    stand = s;
    if (s.grund) { box.hidden = true; return; }
    box.hidden = false;
    optionen($('ari-wuerfel'), s.wahl.wuerfel, s.aufgabe.wuerfel);
    optionen($('ari-kiste'), s.wahl.kisten, s.aufgabe.kiste);
    const t = s.taetigkeit;
    knopf.aufnehmen.textContent = t === 'aufnahme' ? 'Aufnahme beenden' : 'Aufnehmen';
    knopf.probieren.textContent = t === 'ausprobieren' ? 'Anhalten' : 'Ausprobieren';
    knopf.aufnehmen.disabled = !!t && t !== 'aufnahme';
    knopf.probieren.disabled = (!!t && t !== 'ausprobieren') || (!s.gelernt && t !== 'ausprobieren');
    knopf.neu.disabled = knopf.lernen.disabled = !!t;
    $('ari-wuerfel').disabled = $('ari-kiste').disabled = !!t;
    const g = s.gelernt ? `Gelernt: ${s.gelernt.geschafft} von ${s.gelernt.versuche} im Test.` : 'Noch nichts gelernt.';
    text.textContent = [s.meldung, s.fortschritt, `${s.beispiele} eigene Beispiele. ${g}`].filter(Boolean).join(' ');
    $('ari-export').hidden = !s.beispiele && !s.gelernt;
    clearTimeout(poll);
    if (t && !box.closest('[hidden]')) poll = setTimeout(laden, 700);   // solange etwas läuft, nachsehen
  }

  async function laden() {
    const s = await api('/api/ari_lernen').catch(() => null);
    if (s && s.ok) anzeigen(s);
  }

  async function tun(aktion, extra = {}) {
    const r = await api('/api/ari_lernen', 'POST', { aktion, ...extra }).catch(() => null);
    if (!r || !r.ok) { toast((r && r.fehler) || 'Keine Antwort', true); laden(); return; }
    anzeigen(r);
  }

  const aufgabe = () => tun('aufgabe', { wuerfel: $('ari-wuerfel').value, kiste: $('ari-kiste').value });
  $('ari-wuerfel').addEventListener('change', aufgabe);
  $('ari-kiste').addEventListener('change', aufgabe);
  knopf.aufnehmen.addEventListener('click', () => tun(stand && stand.taetigkeit === 'aufnahme' ? 'abbrechen' : 'aufnehmen'));
  knopf.neu.addEventListener('click', () => tun('neu_legen'));
  knopf.lernen.addEventListener('click', () => tun('lernen', { lehrer: $('ari-lehrer').checked }));
  knopf.probieren.addEventListener('click', () => tun(stand && stand.taetigkeit === 'ausprobieren' ? 'abbrechen' : 'ausprobieren'));

  return {
    zeigen: laden,
    aus() {                                                   // Fenster zu: eine laufende Aufnahme gilt nicht mehr
      clearTimeout(poll);
      if (stand && stand.taetigkeit === 'aufnahme') tun('abbrechen');
    },
  };
}
