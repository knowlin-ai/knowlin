// Rückblick (seit 0.38.45, Etappe G4): was Knowlin in Ruhephasen gelernt hat – dokumentiert, korrigierbar, löschbar.
// Wunsch des Maintainers: „nicht erzählen, aber dokumentieren – so dass man ggf. korrigieren oder löschen kann“.

const RICHTUNGEN = [['seltener', 'Seltener'], ['normal', 'Wie vorher'], ['oefter', 'Öfter']];

function datum(s) {
  return new Date(s * 1000).toLocaleString(document.documentElement.lang || 'de',
    { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function initRueckblick({ api, toast }) {
  const liste = document.getElementById('lehren-liste');
  if (!liste) return;
  const leer = document.getElementById('lehren-leer');

  function zeile(x) {
    const li = document.createElement('li');
    li.className = 'lehre';
    const was = document.createElement('p');
    was.className = 'lehre-was';
    was.textContent = x.was;
    const woraus = document.createElement('p');
    woraus.className = 'lehre-woraus';
    woraus.textContent = `${x.koerper_name || ''} · ${datum(x.zeit)} · ${x.woraus}`
      + (x.korrigiert ? ' · von dir korrigiert' : '');
    const knoepfe = document.createElement('div');
    knoepfe.className = 'lehre-knoepfe pc-only';
    const seg = document.createElement('div');
    seg.className = 'seg';
    seg.setAttribute('role', 'radiogroup');
    seg.setAttribute('aria-label', `Korrigieren: ${x.was}`);
    for (const [wert, text] of RICHTUNGEN) {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = `lehre-${x.id}`;
      input.value = wert;
      input.checked = x.korrigiert === wert;
      input.addEventListener('change', async () => {
        const r = await api(`/api/rueckblick/${x.id}`, 'POST', { richtung: wert });
        if (r && r.ok) laden(); else toast('Ging nicht – bitte noch einmal.');
      });
      const span = document.createElement('span');
      span.textContent = text;
      label.append(input, span);
      seg.append(label);
    }
    const weg = document.createElement('button');
    weg.type = 'button';
    weg.className = 'btn btn--sm btn--ghost';
    weg.textContent = 'Löschen';
    weg.setAttribute('aria-label', `Löschen: ${x.was}`);
    weg.addEventListener('click', async () => {
      await api(`/api/rueckblick/${x.id}`, 'DELETE');
      laden();
    });
    knoepfe.append(seg, weg);
    li.append(was, woraus, knoepfe);
    return li;
  }

  async function laden() {
    const d = await api('/api/rueckblick');
    const lehren = (d && d.lehren) || [];
    leer.hidden = lehren.length > 0;
    liste.hidden = !lehren.length;
    liste.replaceChildren(...lehren.map(zeile));
  }

  document.getElementById('lehren-jetzt')?.addEventListener('click', async () => {
    const r = await api('/api/rueckblick/jetzt', 'POST');
    if (r && r.ok) toast(r.neu ? 'Neues im Rückblick gelernt.' : 'Nichts Neues gelernt.');
    laden();
  });
  new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) laden(); }).observe(liste.closest('section'));
}
