// Controller fürs Handy: Querformat, Vollbild, Live-Bild der Kopfkamera als Hintergrund.
// Links ein Fahr-Stick, rechts vier frei belegbare Tasten, oben der Not-Aus. Bild ziehen = umschauen wie in
// Street View (am Anschlag dreht sich der Körper mit). Bewegungssensor: Handy als Kopf oder Kippen zum Laufen
// (nur mit Daumen auf „Halten zum Fahren“ – Totmann). Vibriert bei Stößen, Treffern und Stürzen – am Handy über
// navigator.vibrate (Android), am Gamepad über dessen Rüttelmotor (auch ohne offene Controller-Ansicht).
// Sicherheit: Fahrbefehle verfallen nach 0,35 s (Engine), also hält sie bei Funkloch oder Bildschirmsperre an.

const YAW_MAX = 1.05, PITCH_MAX = 0.65;      // Kopfgrenzen wie im Entenblick (app.js)
const VX_VOR = 0.22, VX_ZURUECK = 0.12, VYAW = 0.9;
const TOT = 0.15;                             // toter Bereich der Sticks
const KIPP_VOLL = 0.4, KIPP_TOT = 0.07;       // rad: so weit kippen = volle Fahrt, darunter nichts

// Was eine Taste tun kann – nur Bewegung, Ausdruck und Laute (wie am Gamepad), nie Einstellungen
export const AKTIONEN = {
  quak: { name: 'Quaken', kurz: 'Quak', msg: { type: 'tool', name: 'sound', args: { tag: 'greet' } } },
  zwitschern: { name: 'Zwitschern', kurz: 'Piep', msg: { type: 'tool', name: 'sound', args: { tag: 'chirp' } } },
  setzen: { name: 'Sitzen ↔ Stehen', kurz: 'Sitz', msg: { type: 'tool', name: 'skill', args: { name: 'sit_toggle' } } },
  kicken: { name: 'Kicken', kurz: 'Kick', msg: { type: 'tool', name: 'skill', args: { name: 'kick_right' } } },
  aufheben: { name: 'Aufheben', kurz: 'Heben', msg: { type: 'tool', name: 'skill', args: { name: 'ground_pick' } } },
  rolle: { name: 'Purzelbaum', kurz: 'Rolle', msg: { type: 'tool', name: 'skill', args: { name: 'roulade' } } },
  freude: { name: 'Freuen', kurz: 'Juhu', msg: { type: 'tool', name: 'emote', args: { emotion: 'freude' } } },
  ja: { name: 'Nicken', kurz: 'Ja', msg: { type: 'tool', name: 'emote', args: { emotion: 'ja' } } },
  nein: { name: 'Kopf schütteln', kurz: 'Nein', msg: { type: 'tool', name: 'emote', args: { emotion: 'nein' } } },
  tanzen: { name: 'Tanzen (8 s)', kurz: 'Tanz', msg: { type: 'tool', name: 'dance', args: { style: 'party', seconds: 8 } } },
  umschauen: { name: 'Umschauen', kurz: 'Schau', msg: { type: 'tool', name: 'look_around', args: { seconds: 6 } } },
};
const STANDARD = ['quak', 'setzen', 'kicken', 'freude'];     // oben, rechts, unten, links im Tasten-Kreuz

const merk = (k, v) => { try { localStorage.setItem(`dp.ctl.${k}`, JSON.stringify(v)); } catch { /* egal */ } };
const hol = (k, d) => { try { const v = JSON.parse(localStorage.getItem(`dp.ctl.${k}`)); return v ?? d; } catch { return d; } };
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Lage des Handys (W3C DeviceOrientation: R = Rz(α)·Rx(β)·Ry(γ), Welt x Ost, y Nord, z oben) → Blickrichtung der
// Rückkamera (−z des Geräts) und die rechte Kante des Bildschirms (je nach Drehung des Bildschirms)
export function handyLage(alpha, beta, gamma, winkel = 0) {
  const a = alpha * Math.PI / 180, b = beta * Math.PI / 180, g = gamma * Math.PI / 180;
  const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cg = Math.cos(g), sg = Math.sin(g);
  const R = [
    [ca * cg - sa * sb * sg, -sa * cb, ca * sg + sa * sb * cg],
    [sa * cg + ca * sb * sg, ca * cb, sa * sg - ca * sb * cg],
    [-cb * sg, sb, cb * cg],
  ];
  const mal = (v) => R.map((r) => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]);
  const blick = mal([0, 0, -1]);
  const w = winkel * Math.PI / 180;
  const rechts = mal([Math.cos(w), -Math.sin(w), 0]);
  return {
    gier: Math.atan2(blick[1], blick[0]),                 // Himmelsrichtung, links herum wachsend
    nick: Math.asin(clamp(blick[2], -1, 1)),              // > 0: schaut nach oben; Oberkante weg gekippt: kleiner
    lenk: Math.asin(clamp(rechts[2], -1, 1)),             // < 0: rechte Kante nach unten (Lenkrad rechts)
  };
}

function bildschirmWinkel() {
  const o = screen.orientation;
  if (o && typeof o.angle === 'number') return o.angle;
  const w = window.orientation;                          // ältere iPhones
  return typeof w === 'number' ? (w + 360) % 360 : 0;
}

// Ein Daumen-Stick: liefert x, y in −1…1 (y nach oben positiv), federt beim Loslassen zurück
function stick(pad, knob, onMove) {
  let id = null;
  const set = (e) => {
    const r = pad.getBoundingClientRect(), R = r.width / 2 - knob.offsetWidth / 4;
    let dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const len = Math.hypot(dx, dy);
    if (len > R) { dx *= R / len; dy *= R / len; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    const x = dx / R, y = -dy / R;
    onMove(Math.abs(x) < TOT ? 0 : x, Math.abs(y) < TOT ? 0 : y, true);
  };
  const end = (e) => {
    if (e && e.pointerId !== id) return;
    id = null;
    knob.style.transform = '';
    pad.classList.remove('is-active');
    onMove(0, 0, false);
  };
  pad.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    id = e.pointerId;
    try { pad.setPointerCapture(id); } catch { /* egal */ }
    pad.classList.add('is-active');
    set(e);
  });
  pad.addEventListener('pointermove', (e) => { if (e.pointerId === id) set(e); });
  pad.addEventListener('pointerup', end);
  pad.addEventListener('pointercancel', end);
  return { reset: () => end({ pointerId: id }), active: () => id !== null };
}

export function initController(h) {
  const { $, send, toast } = h;
  const root = $('ctl');
  if (!root) return { onEvent() {}, open() {}, close() {} };
  let offen = false, vorherModus = null, vollbild = false, camTimer = null, camBusy = false;
  let fahrt = { vx: 0, vyaw: 0 }, nullGeschickt = true;
  let gyroArt = hol('gyro', 'aus'), totmann = false, lage = null, kal = null, gyroGesendet = 0;
  let vib = hol('vibrieren', true), ruckN = null;
  let tasten = hol('tasten', STANDARD);
  if (!Array.isArray(tasten) || tasten.length !== 4 || tasten.some((t) => !AKTIONEN[t])) tasten = [...STANDARD];
  const kannVibrieren = typeof navigator.vibrate === 'function';
  const sicher = window.isSecureContext;

  // ── Fühlen: Handy vibriert, Gamepad rüttelt, Rand blitzt kurz (auch fürs iPhone, das nicht vibriert) ──
  function fuehlen(staerke, muster) {
    if (!vib) return;
    const s = clamp(staerke, 0, 1);
    if (offen && kannVibrieren) {
      try { navigator.vibrate(muster || Math.round(25 + 75 * s)); } catch { /* egal */ }
    }
    for (const pad of (navigator.getGamepads ? [...navigator.getGamepads()] : []).filter(Boolean)) {
      const act = pad.vibrationActuator;
      if (act && typeof act.playEffect === 'function') {
        act.playEffect('dual-rumble', { duration: Math.round(muster ? 400 : 70 + 160 * s), strongMagnitude: s,
          weakMagnitude: Math.min(1, s + 0.25) }).catch(() => {});
      }
    }
    if (offen) {
      root.style.setProperty('--ctl-ruck', String(0.25 + 0.75 * s));
      root.classList.remove('is-ruck');
      void root.offsetWidth;
      root.classList.add('is-ruck');
    }
  }
  function onEvent(ev) {
    if (!ev) return;
    if (ev.type === 'fall') fuehlen(1, [180, 70, 260]);
    else if (ev.type === 'bump') fuehlen(0.5);
    else if (ev.type === 'recover') fuehlen(0.15, [20, 60, 20]);
  }

  // ── Zustand: Status oben, Erschütterungen aus state.ruck ────────────────
  setInterval(() => {
    const st = h.state();
    const r = st && st.ruck;
    if (r && typeof r.n === 'number') {
      if (ruckN !== null && r.n !== ruckN) fuehlen(Number(r.staerke) || 0.3);
      ruckN = r.n;
    }
    if (!offen || !st) return;
    const lage_ = !st.connected ? 'nicht verbunden' : st.fallen ? 'gestürzt' : st.picked_up ? 'hochgehoben'
      : st.sitting ? 'sitzt' : st.powered ? 'steht' : 'ruht';
    const akku = typeof st.battery === 'number' ? ` · Akku ${Math.round(st.battery * (st.battery <= 1 ? 100 : 1))} %` : '';
    $('ctl-status').textContent = `${lage_}${akku}`;
    $('ctl-status').classList.toggle('is-bad', !st.connected || !!st.fallen);
  }, 120);

  // ── Live-Bild: Simulator = Entenblick der 3D-Szene, Roboter = Kamerabild (verkleinert) ──
  const robot = () => (h.getConfig().backend || '') === 'robotd';
  async function kamera() {
    if (!offen || camBusy || document.hidden) return;
    camBusy = true;
    try {
      const r = await fetch(`/api/kamera/bild?breite=${Math.min(640, Math.round(innerWidth * 0.6))}`, { cache: 'no-store' });
      if (r.ok && (r.headers.get('content-type') || '').startsWith('image/')) {
        const img = $('ctl-cam'), alt = img.src;
        img.src = URL.createObjectURL(await r.blob());
        img.hidden = false;
        $('ctl-cam-fehler').hidden = true;
        if (alt.startsWith('blob:')) URL.revokeObjectURL(alt);
      } else {
        $('ctl-cam-fehler').hidden = false;
      }
    } catch { $('ctl-cam-fehler').hidden = false; }
    camBusy = false;
  }

  // ── Öffnen und Schließen ────────────────────────────────────────────────
  async function open() {
    if (offen) return;
    offen = true;
    h.showView('cockpit');
    vorherModus = h.stageMode();
    if (!robot()) h.setStageMode('entenblick');
    $('ctl-cam').hidden = true;
    $('ctl-cam-fehler').hidden = true;
    if (robot()) { kamera(); camTimer = setInterval(kamera, 200); }
    root.hidden = false;
    document.body.classList.add('ctl-open');
    $('ctl-btn')?.setAttribute('aria-expanded', 'true');
    tastenZeigen();
    gyroZeigen();
    $('ctl-close').focus();
    if (matchMedia('(pointer: coarse)').matches && document.documentElement.requestFullscreen && !document.fullscreenElement) {
      try { await document.documentElement.requestFullscreen({ navigationUI: 'hide' }); vollbild = true; } catch { /* iPhone: kein Vollbild für Seiten */ }
      try { await screen.orientation.lock('landscape'); } catch { /* nicht überall erlaubt */ }
    }
    if (gyroArt !== 'aus') gyroAn(gyroArt, false);
  }
  function close() {
    if (!offen) return;
    stoppEingaben();
    offen = false;
    clearInterval(camTimer);
    root.hidden = true;
    document.body.classList.remove('ctl-open');
    $('ctl-btn')?.setAttribute('aria-expanded', 'false');
    $('ctl-sheet').hidden = true;
    if (vorherModus && !robot()) h.setStageMode(vorherModus);
    if (vollbild && document.fullscreenElement) { try { screen.orientation.unlock(); } catch { /* egal */ } document.exitFullscreen().catch(() => {}); }
    vollbild = false;
    $('ctl-btn')?.focus();
  }
  function stoppEingaben() {
    links.reset();
    totmann = false;
    root.classList.remove('is-totmann');
    blick = null;
    fahrt = { vx: 0, vyaw: 0 };
    send({ type: 'drive', vx: 0, vy: 0, vyaw: 0 });
    nullGeschickt = true;
  }
  $('ctl-btn')?.addEventListener('click', open);
  $('ctl-close').addEventListener('click', close);
  $('ctl-stop').addEventListener('click', () => {
    stoppEingaben();
    h.estop();
    if (kannVibrieren && vib) { try { navigator.vibrate(40); } catch { /* egal */ } }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden && offen) stoppEingaben(); });

  // ── Fahren: Stick oder Kippen ───────────────────────────────────────────
  const links = stick($('ctl-stick'), $('ctl-knob'), (x, y) => {
    if (gyroArt === 'fahren') { totmannSetzen(x !== 0 || y !== 0 || links.active()); return; }
    fahrt = { vx: y > 0 ? y * VX_VOR : y * VX_ZURUECK, vyaw: -x * VYAW };
  });
  function totmannSetzen(an) {
    if (an && !totmann && lage) kal = { ...kal, nick: lage.nick, lenk: lage.lenk };   // Nullpunkt beim Drücken
    totmann = an;
    root.classList.toggle('is-totmann', an);
    if (!an) fahrt = { vx: 0, vyaw: 0 };
  }
  setInterval(() => {
    if (!offen) return;
    if (gyroArt === 'fahren' && totmann && lage && kal) {
      const vor = kal.nick - lage.nick, lenk = lage.lenk - kal.lenk;     // Oberkante weg = vor, rechts runter = rechts
      const f = Math.abs(vor) < KIPP_TOT ? 0 : clamp(vor / KIPP_VOLL, -1, 1);
      const l = Math.abs(lenk) < KIPP_TOT ? 0 : clamp(lenk / KIPP_VOLL, -1, 1);
      fahrt = { vx: f > 0 ? f * VX_VOR : f * VX_ZURUECK, vyaw: l * VYAW };
      $('ctl-kipp').style.transform = `translate(${(-l * 30).toFixed(0)}px, ${(-f * 30).toFixed(0)}px)`;
    }
    if (fahrt.vx || fahrt.vyaw) { send({ type: 'drive', vx: fahrt.vx, vy: 0, vyaw: fahrt.vyaw }); nullGeschickt = false; }
    else if (!nullGeschickt) { send({ type: 'drive', vx: 0, vy: 0, vyaw: 0 }); nullGeschickt = true; }
  }, 100);

  // ── Umschauen wie in Street View: Bild ziehen ───────────────────────────
  let blick = null, blickGesendet = 0;
  const look = $('ctl-look');
  look.addEventListener('pointerdown', (e) => {
    blick = { x: e.clientX, y: e.clientY, start: h.headNow(), id: e.pointerId };
    try { look.setPointerCapture(e.pointerId); } catch { /* egal */ }
  });
  look.addEventListener('pointermove', (e) => {
    if (!blick || e.pointerId !== blick.id) return;
    const k = (70 * Math.PI / 180) / Math.max(200, innerHeight);
    kopfNach(blick.start.yaw + (e.clientX - blick.x) * k, blick.start.pitch - (e.clientY - blick.y) * k);
  });
  const blickEnde = (e) => {
    if (!blick || e.pointerId !== blick.id) return;
    blick = null;
    if (gyroArt === 'kopf') kalibrieren(true);      // Handy-Kopf macht dort weiter, wo das Ziehen aufgehört hat
  };
  look.addEventListener('pointerup', blickEnde);
  look.addEventListener('pointercancel', blickEnde);
  function kopfNach(yaw, pitch) {
    const now = performance.now();
    if (now - blickGesendet < 50) return;
    blickGesendet = now;
    pitch = clamp(pitch, -PITCH_MAX, PITCH_MAX);
    if (Math.abs(yaw) > YAW_MAX) {
      // am Anschlag dreht sich der Körper mit – wie wenn man in Street View weiterzieht
      yaw = Math.sign(yaw) * YAW_MAX;
      send({ type: 'drive', vx: 0, vy: 0, vyaw: Math.sign(yaw) * 0.8, head: { yaw, pitch } });
    }
    send({ type: 'blick', yaw, pitch, sekunden: 10 });
  }

  // ── Bewegungssensor ─────────────────────────────────────────────────────
  function onLage(e) {
    if (e.alpha === null && e.beta === null) return;
    lage = handyLage(e.alpha || 0, e.beta || 0, e.gamma || 0, bildschirmWinkel());
    if (!kal) kalibrieren();
    if (gyroArt !== 'kopf' || blick || !offen) return;
    const st = h.state() || {};
    const ziel = kal.koerper + wrap(lage.gier - kal.gier);              // wohin das Handy zeigt, in der Welt
    const yaw = wrap(ziel - (st.yaw || 0));                               // … relativ zum Körper der Ente
    const pitch = kal.kopfNick - (lage.nick - kal.nick);
    const now = performance.now();
    if (now - gyroGesendet < 60) return;
    gyroGesendet = now;
    kopfNach(yaw, pitch);
  }
  // Nullpunkt: so wie das Handy jetzt zeigt, schaut sie geradeaus (oder, nach dem Ziehen, dorthin, wo ihr Kopf ist)
  function kalibrieren(vomKopf = false) {
    if (!lage) { kal = null; return; }
    const st = h.state() || {}, kopf = vomKopf ? h.headNow() : { yaw: 0, pitch: 0 };
    kal = { gier: lage.gier, nick: lage.nick, lenk: lage.lenk,
      koerper: (st.yaw || 0) + kopf.yaw, kopfNick: kopf.pitch };
  }
  async function gyroAn(art, fragen = true) {
    if (art !== 'aus') {
      if (!sicher || typeof DeviceOrientationEvent === 'undefined') {
        toast('Der Bewegungssensor geht nur über https – am Handy mit Tailscale (Einstellungen → Handy-Fernbedienung).', true);
        art = 'aus';
      } else if (fragen && typeof DeviceOrientationEvent.requestPermission === 'function') {
        try {                                                             // iPhone: einmal fragen, im Tipp
          if (await DeviceOrientationEvent.requestPermission() !== 'granted') { toast('Bewegungssensor nicht freigegeben', true); art = 'aus'; }
        } catch { toast('Bewegungssensor nicht freigegeben', true); art = 'aus'; }
      }
    }
    window.removeEventListener('deviceorientation', onLage);
    totmannSetzen(false);
    gyroArt = art;
    merk('gyro', art);
    lage = null; kal = null;
    if (art !== 'aus') window.addEventListener('deviceorientation', onLage);
    gyroZeigen();
  }
  function gyroZeigen() {
    for (const r of root.querySelectorAll('input[name="ctl-gyro"]')) r.checked = r.value === gyroArt;
    root.classList.toggle('is-kippen', gyroArt === 'fahren');
    $('ctl-stick-label').textContent = gyroArt === 'fahren' ? 'Halten und kippen' : 'Fahren';
    $('ctl-stick').setAttribute('aria-label', gyroArt === 'fahren'
      ? 'Totmann: gedrückt halten, dann Handy kippen – vor, zurück, lenken'
      : 'Fahren: Daumen nach vorn, zurück oder zur Seite zum Drehen');
    $('ctl-neu').hidden = gyroArt !== 'kopf';
    $('ctl-gyro-hinweis').hidden = sicher;
  }
  for (const r of root.querySelectorAll('input[name="ctl-gyro"]')) r.addEventListener('change', (e) => gyroAn(e.target.value));
  $('ctl-neu').addEventListener('click', () => { kalibrieren(); toast('Geradeaus ist jetzt dort, wohin das Handy zeigt'); });

  // ── Tasten ──────────────────────────────────────────────────────────────
  function tastenZeigen() {
    root.querySelectorAll('.ctl-taste').forEach((b, i) => {
      const a = AKTIONEN[tasten[i]];
      b.querySelector('span').textContent = a.kurz;
      b.setAttribute('aria-label', a.name);
      b.title = a.name;
    });
    root.querySelectorAll('select[data-taste]').forEach((s) => { s.value = tasten[Number(s.dataset.taste)]; });
  }
  root.querySelectorAll('.ctl-taste').forEach((b, i) => b.addEventListener('click', () => {
    send(AKTIONEN[tasten[i]].msg);
    if (kannVibrieren && vib) { try { navigator.vibrate(12); } catch { /* egal */ } }
  }));
  root.querySelectorAll('select[data-taste]').forEach((s) => {
    s.replaceChildren(...Object.entries(AKTIONEN).map(([k, a]) => new Option(a.name, k)));
    s.addEventListener('change', () => { tasten[Number(s.dataset.taste)] = s.value; merk('tasten', tasten); tastenZeigen(); });
  });

  // ── Sprechen (halten), Ton am Handy, Vibrieren, Einstellungen ──────────
  const talk = $('ctl-talk');
  talk.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    const l = h.listener();
    if (!l || !l.supported) {
      toast(sicher ? 'Dieser Browser kann keine Sprache erkennen' : 'Sprechen geht am Handy nur über https – mit Tailscale (Einstellungen → Handy-Fernbedienung).', true);
      return;
    }
    try { talk.setPointerCapture(e.pointerId); } catch { /* egal */ }
    h.stopSpeaking();
    l.start();
    talk.classList.add('is-active');
  });
  const talkEnde = () => { if (talk.classList.contains('is-active')) { h.listener()?.stop(); talk.classList.remove('is-active'); } };
  talk.addEventListener('pointerup', talkEnde);
  talk.addEventListener('pointercancel', talkEnde);
  const ton = $('ctl-ton'), tts = $('opt-tts');
  const tonZeigen = () => { ton.setAttribute('aria-pressed', String(!!(tts && tts.checked))); };
  ton.addEventListener('click', () => {
    if (!tts) return;
    tts.checked = !tts.checked;
    tts.dispatchEvent(new Event('change'));
    tonZeigen();
    toast(tts.checked ? 'Ihre Stimme kommt jetzt aus diesem Gerät' : 'Ton an diesem Gerät aus');
  });
  tts?.addEventListener('change', tonZeigen);
  tonZeigen();
  const vibSw = $('ctl-vib');
  vibSw.checked = vib;
  vibSw.disabled = false;
  $('ctl-vib-hinweis').hidden = kannVibrieren;
  vibSw.addEventListener('change', () => { vib = vibSw.checked; merk('vibrieren', vib); if (vib) fuehlen(0.4); });
  // Kopf ruhig (0.33): derselbe Schalter wie im Cockpit oben rechts – fürs Livebild besonders nützlich
  const stabSw = $('ctl-stab');
  const stabBtn = $('stab-btn');
  const stabZeigen = () => { stabSw.checked = stabBtn?.getAttribute('aria-pressed') === 'true'; };
  stabSw.addEventListener('change', () => {
    if (stabBtn && (stabBtn.getAttribute('aria-pressed') === 'true') !== stabSw.checked) stabBtn.click();
  });
  if (stabBtn) new MutationObserver(stabZeigen).observe(stabBtn, { attributes: true, attributeFilter: ['aria-pressed'] });
  stabZeigen();
  $('ctl-menu').addEventListener('click', () => {
    const zu = $('ctl-sheet').hidden;
    $('ctl-sheet').hidden = !zu;
    $('ctl-menu').setAttribute('aria-expanded', String(zu));
  });
  $('ctl-sheet-close').addEventListener('click', () => { $('ctl-sheet').hidden = true; $('ctl-menu').setAttribute('aria-expanded', 'false'); $('ctl-menu').focus(); });

  // Für Tests: Lage von außen einspielen, Fahrt ablesen
  const debug = { lage: (a, b, g, w = 0) => onLage({ alpha: a, beta: b, gamma: g, _w: w }), fahrt: () => ({ ...fahrt }),
    totmann: (an) => totmannSetzen(an), kal: () => kal, fuehlen };
  return { onEvent, open, close, offen: () => offen, debug };
}
