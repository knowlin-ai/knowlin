// Reachy Mini in der Oberfläche (seit 0.38.2): Pollens Emotionen und Tänze unter Steuern → Tricks, Stand des
// Nachladens unter Einstellungen → Körper, Ton der Aufnahmen im Simulator (am echten Reachy spielt er ihn selbst).
import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

// Pollens Namen sind englisch („cheerful1“) – die häufigen Gefühle auf Deutsch, der Rest lesbar gemacht
const DE = {
  amazed: 'Staunen', anxiety: 'Unruhe', attentive: 'Aufmerksam', boredom: 'Langeweile', cheerful: 'Fröhlich',
  confused: 'Verwirrt', contempt: 'Verächtlich', curious: 'Neugierig', disgusted: 'Angeekelt', displeased: 'Unzufrieden',
  downcast: 'Niedergeschlagen', dying: 'Sterbend (gespielt)', electric: 'Elektrisiert', enthusiastic: 'Begeistert',
  exhausted: 'Erschöpft', fear: 'Angst', frustrated: 'Frustriert', furious: 'Wütend', go_away: 'Geh weg',
  grateful: 'Dankbar', helpful: 'Hilfsbereit', impatient: 'Ungeduldig', incomprehensible: 'Unverständlich',
  indifferent: 'Gleichgültig', inquiring: 'Fragend', irritated: 'Gereizt', laughing: 'Lachen', lonely: 'Einsam',
  lost: 'Ratlos', loving: 'Verliebt', no: 'Nein', oops: 'Hoppla', proud: 'Stolz', rage: 'Zorn', relief: 'Erleichtert',
  reprimand: 'Tadeln', resigned: 'Resigniert', sad: 'Traurig', scared: 'Erschrocken', serenity: 'Gelassen', shy: 'Schüchtern',
  sleep: 'Einschlafen', success: 'Geschafft', surprised: 'Überrascht', thoughtful: 'Nachdenklich', tired: 'Müde',
  uncertain: 'Unsicher', understanding: 'Verständnisvoll', welcoming: 'Willkommen', yes: 'Ja', calming: 'Beruhigend',
  come: 'Komm her', dance: 'Tanz', greeting: 'Begrüßen', hello: 'Hallo', thinking: 'Denkt nach',
};
export function anzeigeName(name) {
  const m = /^(.*?)(\d*)$/.exec(String(name));
  const stamm = m[1].replace(/[_-]+$/, '');
  const nr = m[2] && m[2] !== '1' ? ` ${m[2]}` : '';
  return DE[stamm] ? `${tr(DE[stamm])}${nr}` : String(name).replace(/[_-]+/g, ' ').trim();
}

export function initReachy({ $, api, el, toast, showView, scene, isRemote }) {
  const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';
  let status = null;
  let liste = [];
  const ton = new Audio();

  function kachel(b) {
    const k = el('button', 'emo');
    k.type = 'button';
    const t = el('b', null, anzeigeName(b.name));
    t.insertAdjacentHTML('beforeend', PLAY);
    k.append(t, el('span', null, `${String(b.dauer).replace('.', ',')} s${b.ton ? ` · ${tr('mit Ton')}` : ''}`));
    if (b.beschreibung) k.title = b.beschreibung;
    k.addEventListener('click', async () => {
      const r = await api('/api/reachy/bewegung', 'POST', { name: b.name }).catch(() => null);
      if (!r || !r.ok) { toast((r && r.fehler) || tr('Ließ sich nicht abspielen'), true); return; }
      k.classList.add('playing');
      setTimeout(() => k.classList.remove('playing'), Math.max(800, b.dauer * 1000));
      showView('cockpit');
    });
    return k;
  }

  function zeichneListe() {
    const emo = $('reachy-emo'), tanz = $('reachy-tanz');
    if (!emo) return;
    emo.replaceChildren(...liste.filter((b) => b.art === 'emotionen').map(kachel));
    tanz.replaceChildren(...liste.filter((b) => b.art === 'taenze').map(kachel));
    const leer = !liste.length;
    $('reachy-leer').hidden = !leer;
    const job = status && status.bewegungen && status.bewegungen.job;
    $('reachy-leer-text').textContent = job && job.laeuft ? job.text
      : job && job.fehler ? `${tr('Laden ging nicht:')} ${job.fehler}` : tr('Pollens Bewegungen sind noch nicht auf diesem PC.');
    $('reachy-leer-laden').disabled = Boolean(job && job.laeuft);
  }

  function zeichneStatus() {
    if (!status || !$('reachy-pollen-modell')) return;
    const m = status.modell || {}, b = status.bewegungen || {};
    const mj = m.job || {}, bj = b.job || {};
    $('reachy-pollen-modell').textContent = mj.laeuft ? `${tr('3D-Modell:')} ${mj.text}`
      : m.ansicht ? `${tr('3D-Modell:')} ${tr('Pollens Original')} (${m.stand}${m.ansicht === 'paket' ? `, ${tr('im Paket')}` : ''})`
        : `${tr('3D-Modell:')} ${mj.fehler ? `${tr('Laden ging nicht:')} ${mj.fehler}` : tr('noch nicht geladen – bis dahin das gezeichnete Modell')}`;
    $('reachy-pollen-bewegungen').textContent = bj.laeuft ? `${tr('Emotionen und Tänze:')} ${bj.text}`
      : b.da ? `${tr('Emotionen und Tänze:')} ${b.anzahl} ${tr('Aufnahmen')}`
        : `${tr('Emotionen und Tänze:')} ${bj.fehler ? `${tr('Laden ging nicht:')} ${bj.fehler}` : tr('noch nicht geladen')}`;
    $('reachy-pollen-laden').disabled = Boolean(mj.laeuft || bj.laeuft);
  }

  async function laden() {
    const r = await api('/api/reachy').catch(() => null);
    if (!r || !r.ok) return;
    status = r;
    liste = r.liste || [];
    zeichneListe();
    zeichneStatus();
  }

  const nachladen = async (neu) => {
    if (isRemote()) { toast(tr('Nachladen geht nur am PC'), true); return; }
    const r = await api('/api/reachy/laden', 'POST', { neu }).catch(() => null);
    if (!r || !r.ok) toast((r && r.fehler) || tr('Laden ließ sich nicht starten'), true);
  };
  $('reachy-leer-laden')?.addEventListener('click', () => nachladen(false));
  $('reachy-pollen-laden')?.addEventListener('click', () => nachladen(true));

  return {
    laden,
    // Meldungen vom Server: Stand des Nachladens, Ton einer Aufnahme (nur im Simulator)
    nachricht(msg) {
      if (msg.type === 'reachy') {
        const vorher = status && status.modell && status.modell.ansicht;
        status = { ...(status || {}), modell: msg.modell, bewegungen: msg.bewegungen };
        if (msg.modell && msg.modell.ansicht && !vorher) scene.ladeReachy(true);
        zeichneStatus();
        if (!(msg.bewegungen && msg.bewegungen.job && msg.bewegungen.job.laeuft)) laden(); else zeichneListe();
      } else if (msg.type === 'reachy_ton') {
        try {
          ton.src = msg.url;
          ton.play().catch(() => { /* Browser erlaubt Ton erst nach einem Klick – dann eben ohne */ });
        } catch { /* egal */ }
      }
    },
  };
}
