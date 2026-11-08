// Pollens Apps für Reachy Mini aus Knowlin (seit 0.38.19): unter Tricks die auf dem Reachy installierten Apps
// starten und anhalten, weitere aus Pollens Katalog (Hugging Face) installieren – mit zweitem Klick zur Bestätigung.
// Die Apps laufen beim Reachy, nicht in Knowlin; solange eine läuft, hält sich Knowlin mit eigenen Bewegungen zurück.
import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;
const KATALOG_SEITE = 'https://huggingface.co/spaces/pollen-robotics/Reachy_Mini_Apps';
const KATALOG_MAX = 24;                    // die beliebtesten zuerst, mehr zeigt Pollens eigene Seite

export function initReachyApps({ $, api, el, toast, isRemote }) {
  let stand = null, katalog = null, auftrag = null;
  const laeuftName = () => stand && stand.laeuft && stand.laeuft.name;

  // Name aus dem Space („hand_tracker“) lesbar machen
  const lesbar = (n) => String(n).replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

  function zeile(app, aktion) {
    const li = el('li', 'app-zeile');
    const text = el('div', 'app-text');
    text.append(el('b', null, lesbar(app.name)));
    if (app.beschreibung) text.append(el('span', null, app.beschreibung));
    li.append(text);
    if (app.url) {
      const a = el('a', 'link app-seite', tr('Seite'));
      a.href = app.url; a.target = '_blank'; a.rel = 'noopener';
      a.setAttribute('aria-label', `${tr('Seite von')} ${lesbar(app.name)}`);
      li.append(a);
    }
    li.append(aktion);
    return li;
  }

  function startKnopf(app) {
    const laeuft = laeuftName() === app.name;
    const b = el('button', `btn btn--sm ${laeuft ? 'btn--danger' : 'btn--primary'}`, laeuft ? tr('Anhalten') : tr('Starten'));
    b.type = 'button';
    b.addEventListener('click', async () => {
      b.disabled = true;
      const r = laeuft ? await api('/api/reachy/apps/stoppen', 'POST', {}).catch(() => null)
        : await api('/api/reachy/apps/starten', 'POST', { name: app.name }).catch(() => null);
      if (!r || !r.ok) toast((r && r.fehler) || tr('Pollens Daemon antwortet nicht'), true);
      else toast(laeuft ? tr('Angehalten') : `${lesbar(app.name)} ${tr('läuft auf dem Reachy')}`);
      await laden();
    });
    return b;
  }

  // Installieren: erster Klick fragt nach, zweiter installiert (Code aus Pollens Katalog läuft danach auf dem Reachy)
  function installKnopf(app) {
    const b = el('button', 'btn btn--sm', tr('Installieren'));
    b.type = 'button';
    let scharf = false;
    b.addEventListener('click', async () => {
      if (isRemote()) { toast(tr('Installieren geht nur am PC'), true); return; }
      if (!scharf) {
        scharf = true;
        b.textContent = tr('Wirklich installieren?');
        b.classList.add('btn--primary');
        setTimeout(() => { scharf = false; b.textContent = tr('Installieren'); b.classList.remove('btn--primary'); }, 5000);
        return;
      }
      b.disabled = true;
      const r = await api('/api/reachy/apps/installieren', 'POST', { name: app.name }).catch(() => null);
      if (!r || !r.ok) { toast((r && r.fehler) || tr('Installieren ließ sich nicht starten'), true); b.disabled = false; return; }
      auftrag = { id: r.auftrag, name: app.name };
      verfolgen();
    });
    return b;
  }

  async function verfolgen() {
    const box = $('reachy-apps-auftrag');
    while (auftrag) {
      const r = await api(`/api/reachy/apps/auftrag/${encodeURIComponent(auftrag.id)}`).catch(() => null);
      const z = r && r.zustand;
      box.hidden = false;
      box.textContent = `${lesbar(auftrag.name)}: ${z === 'done' ? tr('installiert') : z === 'failed' ? tr('Installieren ging nicht')
        : (r && r.zeilen && r.zeilen.at(-1)) || tr('wird installiert …')}`;
      if (z === 'done' || z === 'failed' || !r || !r.ok) {
        if (z === 'done') toast(`${lesbar(auftrag.name)} ${tr('installiert')}`);
        auftrag = null;
        await laden();
        break;
      }
      await new Promise((ok) => setTimeout(ok, 1500));
    }
  }

  function zeichnen() {
    const wurzel = $('reachy-apps');
    if (!wurzel || !stand) return;
    const nichtDa = !stand.verfuegbar;
    $('reachy-apps-sim').hidden = !nichtDa;
    $('reachy-apps-echt').hidden = nichtDa;
    if (nichtDa) return;
    const fehler = $('reachy-apps-fehler');
    fehler.hidden = stand.ok;
    fehler.textContent = stand.ok ? '' : stand.fehler;
    const l = stand.laeuft;
    $('reachy-apps-laeuft').hidden = !l;
    if (l) $('reachy-apps-laeuft-text').textContent = `${lesbar(l.name)} ${l.zustand === 'error' ? `– ${l.fehler || tr('Fehler')}` : tr('läuft gerade auf dem Reachy')}`;
    const inst = stand.installiert || [];
    $('reachy-apps-installiert').replaceChildren(...inst.map((a) => zeile(a, startKnopf(a))));
    $('reachy-apps-keine').hidden = inst.length > 0 || !stand.ok;
    if (katalog) {
      const da = new Set(inst.map((a) => a.name));
      $('reachy-apps-katalog').replaceChildren(...katalog.filter((a) => !da.has(a.name)).slice(0, KATALOG_MAX)
        .map((a) => zeile(a, installKnopf(a))));
    }
    $('reachy-apps-katalog-zeigen').hidden = Boolean(katalog);
  }

  async function laden(mitKatalog = false) {
    const r = await api(`/api/reachy/apps${mitKatalog ? '?katalog=1' : ''}`).catch(() => null);
    if (!r) return;
    stand = r;
    if (mitKatalog && r.katalog) katalog = r.katalog;
    zeichnen();
  }

  $('reachy-apps-katalog-zeigen')?.addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    await laden(true);
    e.currentTarget.disabled = false;
    if (!katalog) toast(tr('Pollens Katalog ist gerade nicht erreichbar'), true);
  });
  $('reachy-apps-anhalten')?.addEventListener('click', async () => {
    const r = await api('/api/reachy/apps/stoppen', 'POST', {}).catch(() => null);
    if (!r || !r.ok) toast((r && r.fehler) || tr('Pollens Daemon antwortet nicht'), true);
    await laden();
  });
  const seite = $('reachy-apps-seite');
  if (seite) seite.href = KATALOG_SEITE;

  return {
    laden,
    nachricht(msg) {
      if (msg.type !== 'reachy_app') return;
      stand = { ...(stand || {}), laeuft: msg.laeuft };
      zeichnen();
    },
  };
}
