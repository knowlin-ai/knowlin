// Die Augen der Ente im Simulator und das Anlernen von Personen (Alltag → Was der Buddy darf).
// Im Simulator liefert dieses Fenster die Bilder: von der PC-Webcam oder aus der Simulator-Kopfkamera.
// Die Webcam läuft nur, solange „Sehen“ oder „Personen erkennen“ sie braucht – oben steht dann „● Webcam“.
// Bilder gehen nur an duckpilot auf diesem PC; Namen landen nur über textContent im Dokument.

export function initAugen(h) {
  const { $, api, el, toast, getScene, getConfig, isRemote } = h;
  let opts = null;
  let alltagOn = false;
  let stream = null;
  let video = null;
  let enrolling = false;
  let poll = null;
  const canvas = document.createElement('canvas');
  canvas.width = 640; canvas.height = 480;

  const robot = () => getConfig().backend === 'robotd';
  const wantWebcam = () => !isRemote() && alltagOn && opts && opts.augen === 'webcam' && !robot() && (opts.sehen || opts.personen);

  async function startCam() {
    if (stream) return true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { toast('Diese Ansicht kann keine Webcam öffnen', true); return false; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    } catch (e) {
      toast(`Webcam nicht freigegeben (${e.name})`, true);
      return false;
    }
    video = video || $('al-person-video');
    video.srcObject = stream;
    await video.play().catch(() => {});
    $('badge-cam').hidden = false;
    return true;
  }
  function stopCam() {
    if (!stream || enrolling) return;
    for (const t of stream.getTracks()) t.stop();
    stream = null;
    if (video) video.srcObject = null;
    $('badge-cam').hidden = true;
  }
  async function syncCam() {
    if (wantWebcam()) await startCam(); else stopCam();
  }

  function grab(quelle) {
    const ctx = canvas.getContext('2d');
    if (quelle === 'webcam') {
      if (!stream || !video || video.readyState < 2) return null;
      canvas.width = video.videoWidth || 640; canvas.height = video.videoHeight || 480;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      return canvas;
    }
    canvas.width = 640; canvas.height = 480;
    return getScene().snapshotPov(canvas) ? canvas : null;
  }
  async function sendFrame(quelle) {
    const c = grab(quelle);
    if (!c) return false;
    const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.85));
    if (!blob) return false;
    await fetch(`/api/augen/bild?quelle=${quelle}`, { method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg' } }).catch(() => {});
    return true;
  }

  // Der Server fragt nach einem Bild (Claude will hinschauen)
  async function onRequest(msg) {
    if (isRemote()) return;
    const quelle = msg.quelle === 'webcam' ? 'webcam' : 'simulator';
    if (quelle === 'webcam' && !stream) await startCam();
    await sendFrame(quelle);
  }

  // Personen erkennen mit der Webcam: alle 1,5 s ein Bild, solange das Fenster sichtbar ist
  setInterval(() => {
    if (!opts || !opts.personen || !opts.begruessen || !wantWebcam() || document.hidden) return;
    sendFrame('webcam');
  }, 1500);

  // ── Optionen (kommen mit jeder Alltag-Nachricht) ─────────────────────
  function update(msg) {
    alltagOn = !!msg.an;
    opts = msg.optionen || opts;
    if (!opts) return;
    $('al-see').checked = !!opts.sehen;
    $('al-people').checked = !!opts.personen;
    $('al-greet').checked = opts.begruessen !== false;
    $('al-greet').disabled = !opts.personen || isRemote();
    $('al-see').disabled = isRemote();               // Sehen und Personen nur am PC ein- und ausschalten
    $('al-people').disabled = isRemote();
    for (const r of document.querySelectorAll('input[name="al-eyes"]')) {
      r.checked = r.value === (opts.augen || 'simulator');
      r.disabled = isRemote();
    }
    $('al-eyes-help').textContent = robot() ? 'Am echten Roboter sieht sie durch ihre Kopfkamera.'
      : opts.augen === 'webcam' ? 'Die Verkörperung sieht durch die Webcam dieses PCs – sie läuft nur, solange Sehen oder Personen an ist (oben „● Webcam“).'
        : 'Die Verkörperung sieht, was ihre Kopfkamera im Simulator zeigt. Personen erkennt sie so nicht – dafür die Webcam wählen.';
    syncCam();
  }
  async function option(patch) {
    const r = await api('/api/alltag/optionen', 'POST', patch).catch(() => null);
    if (!r || !r.ok) toast(r ? r.fehler : 'Keine Antwort', true);
  }
  $('al-see').addEventListener('change', (e) => option({ sehen: e.target.checked }));
  $('al-people').addEventListener('change', (e) => { option({ personen: e.target.checked }); if (e.target.checked) loadPersons(); });
  $('al-greet').addEventListener('change', (e) => option({ begruessen: e.target.checked }));
  for (const r of document.querySelectorAll('input[name="al-eyes"]')) r.addEventListener('change', () => option({ augen: r.value }));

  // ── Personen ────────────────────────────────────────────────────────
  async function loadPersons() {
    if (isRemote()) return;
    const r = await api('/api/personen').catch(() => null);
    if (r && !r.error) renderPersons(r);
  }
  function renderPersons(r) {
    const setup = $('al-persons-setup');
    setup.replaceChildren();
    const job = r.laden || {};
    let state;
    if (r.pakete_fehlen && r.pakete_fehlen.length) {
      state = 'Dafür fehlen noch zwei kleine Pakete (ONNX und Pillow, ≈ 60 MB).';
      const b = el('button', 'btn btn--sm', 'Pakete installieren');
      b.type = 'button';
      b.addEventListener('click', async () => {
        const x = await api('/api/stimme/installieren', 'POST', { paket: 'gesichter', gpu: 'cpu' }).catch(() => null);
        if (!x || !x.ok) toast(x ? x.fehler : 'Keine Antwort', true); else toast('Installiere … (siehe „Aufgaben laufen“). Danach Knowlin neu starten.');
      });
      setup.append(b);
    } else if (!r.modelle_da) {
      state = job.laeuft ? `Lade die Erkennungsmodelle … ${Math.round((job.anteil || 0) * 100)} %`
        : job.fehler ? `Laden fehlgeschlagen: ${job.fehler}` : 'Einmal die zwei Erkennungsmodelle laden (≈ 39 MB, OpenCV Zoo, MIT/Apache-2.0).';
      if (!job.laeuft) {
        const b = el('button', 'btn btn--sm', 'Modelle laden');
        b.type = 'button';
        b.addEventListener('click', async () => { await api('/api/personen/modelle', 'POST').catch(() => null); loadPersons(); watch(); });
        setup.append(b);
      } else watch();
    } else {
      state = r.personen.length ? `${r.personen.length} ${r.personen.length === 1 ? 'Person' : 'Personen'} angelernt.` : 'Noch niemand angelernt.';
    }
    $('al-persons-state').textContent = state;
    $('al-person-form').hidden = !r.verfuegbar;
    const ul = $('al-persons-list');
    ul.replaceChildren(...(r.personen || []).map((p) => {
      const li = el('li', 'al-item');
      const txt = el('span', 'al-item-text');
      txt.append(el('b', null, p.name), el('small', null, ` · ${p.proben} Bilder · angelernt am ${p.angelegt ? new Date(p.angelegt).toLocaleDateString('de-DE') : '?'}`));
      const x = el('button', 'btn btn--ghost btn--sm', 'Löschen');
      x.type = 'button';
      x.addEventListener('click', async () => {
        const res = await api(`/api/personen/${encodeURIComponent(p.name)}`, 'DELETE').catch(() => null);
        if (res && res.ok) { toast(`${p.name} gelöscht – Knowlin erkennt die Person nicht mehr`); renderPersons(res); }
      });
      li.append(txt, x);
      return li;
    }));
    $('al-persons-clear').hidden = !(r.personen || []).length;
  }
  function watch() {
    clearInterval(poll);
    poll = setInterval(async () => {
      const r = await api('/api/personen').catch(() => null);
      if (!r) return;
      renderPersons(r);
      if (!r.laden || !r.laden.laeuft) clearInterval(poll);
    }, 1000);
  }
  $('al-persons-clear').addEventListener('click', async () => {
    const r = await api('/api/personen', 'DELETE').catch(() => null);
    if (r && r.ok) { toast('Alle Personen gelöscht'); renderPersons(r); }
  });
  $('al-person-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = $('al-person-name').value.trim();
    if (!name || !$('al-person-ok').checked) return;
    const btn = $('al-person-go');
    btn.disabled = true;
    enrolling = true;
    try {
      if (!(await startCam())) return;
      video.hidden = false;
      const shots = [];
      for (let i = 0; i < 5; i++) {
        $('al-person-msg').textContent = `Bitte in die Kamera schauen … Bild ${i + 1} von 5 (Kopf leicht drehen)`;
        await new Promise((r) => setTimeout(r, 700));
        const c = grab('webcam');
        if (c) shots.push(c.toDataURL('image/jpeg', 0.9));
      }
      $('al-person-msg').textContent = 'Lerne …';
      const r = await api('/api/personen/anlernen', 'POST', { name, bilder: shots, einverstanden: true }).catch(() => null);
      shots.length = 0;
      if (!r) { $('al-person-msg').textContent = 'Keine Antwort vom PC'; return; }
      $('al-person-msg').textContent = r.ok ? (r.meldung || `${name} angelernt.`) : (r.fehler || 'Ging nicht');
      if (r.ok) { $('al-person-name').value = ''; $('al-person-ok').checked = false; }
      renderPersons(r);
    } finally {
      enrolling = false;
      if (video) video.hidden = true;
      btn.disabled = false;
      syncCam();
    }
  });

  return { update, onRequest, loadPersons, onPersons: renderPersons, stop: stopCam };
}
