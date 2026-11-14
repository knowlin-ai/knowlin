// Zeiger in der 3D-Ansicht – zwei Arten mit demselben Ablauf:
//  • Laser: Maus oder Finger ist der Laserpointer, der Körper läuft dem roten Punkt nach (laser_folgen).
//  • Folg mir: Maus oder Finger führt eine Menschen-Verkörperung über den Boden, der Körper läuft hinterher (mir_folgen).
// Am echten Roboter startet der Knopf nur das Folgen – den Punkt macht der echte Pointer, den Menschen sieht die Kamera.
// Es ist immer höchstens einer an.

const KINDS = {
  laser: {
    btn: 'laser-btn', tool: 'laser_folgen', seconds: 300, msg: 'laser', ends: 'Laserpunkt folgen', stageClass: 'stage--laser',
    show: (scene, p) => scene.setLaser(p), floorOnly: false,
    onSim: 'Laser an – zeig mit der Maus oder dem Finger auf den Boden',
    onRobot: 'Dein Roboter sucht jetzt den Punkt deines Laserpointers', off: 'Laser aus', fail: 'Laser folgen geht gerade nicht',
  },
  mensch: {
    btn: 'follow-btn', tool: 'mir_folgen', seconds: 600, msg: 'mensch', ends: 'Mensch folgen', stageClass: 'stage--laser',
    show: (scene, p) => scene.setPerson(p), floorOnly: true,
    onSim: 'Folg mir – die Maus führt den Punkt, dein Roboter läuft hinterher',
    onRobot: 'Dein Roboter folgt dir jetzt – geh langsam voraus', off: 'Folgen aus', fail: 'Folgen geht gerade nicht',
  },
};

export function initPointer(h, kind) {
  const cfg = KINDS[kind];
  const { $, scene, send, toast, stageEl, state } = h;
  const btn = $(cfg.btn);
  let on = false, last = null, keep = null, sentAt = 0, localAt = 0, since = 0;
  const simBody = () => !state() || state().backend !== 'robotd';
  const sendPoint = (p) => send(p ? { type: cfg.msg, x: p.x, y: p.y, z: p.z || 0 } : { type: cfg.msg, aus: true });

  function set(next, quiet = false) {
    if (next === on) return;
    on = next;
    btn.setAttribute('aria-pressed', String(on));
    stageEl.classList.toggle(cfg.stageClass, on);
    scene.controls.enabled = !on && scene.mode === 'beobachten';
    clearInterval(keep);
    keep = null; last = null; localAt = 0;
    if (on) {
      if (h.others) for (const o of h.others()) if (o !== api && o.on()) o.off(true);
      since = performance.now();
      send({ type: 'tool', name: cfg.tool, args: { seconds: cfg.seconds } });
      if (simBody()) {
        keep = setInterval(() => { if (last) sendPoint(last); }, 1000);   // Lebenszeichen: Zeiger noch da
        toast(cfg.onSim);
      } else toast(cfg.onRobot);
    } else {
      sendPoint(null);
      cfg.show(scene, null);
      if (!quiet) toast(cfg.off);
    }
  }

  // Der Server sagt, wann das Folgen endet (Ziel lange weg, Zeit um, Not-Aus, abgelehnt) – dann Knopf lösen.
  function onEvent(ev) {
    if (on && ev.type === 'behavior_end' && (ev.behavior || '').startsWith(cfg.ends)
        && performance.now() - since > 500) set(false, true);
  }
  function onAction(msg) {
    if (on && msg.tool === cfg.tool && msg.result && msg.result.ok === false) {
      set(false, true);
      toast(msg.result.fehler || cfg.fail, true);
    }
  }

  function pointAt(clientX, clientY) {
    if (!simBody()) return;
    const p = scene.pick(clientX, clientY);
    const at = cfg.floorOnly ? p.floor : (p.hit || p.floor);
    if (!at || !Number.isFinite(at.x) || !Number.isFinite(at.y)) return;
    last = { x: at.x, y: at.y, z: cfg.floorOnly ? 0 : (at.z || 0) };
    localAt = performance.now();
    cfg.show(scene, last);                        // sofort zeigen, der Server zieht nach
    if (localAt - sentAt < 100) return;
    sentAt = localAt;
    sendPoint(last);
  }

  btn.addEventListener('click', () => set(!on));
  const api = {
    on: () => on,
    off: (quiet = false) => set(false, quiet),
    pointAt,
    leave: () => { if (on) last = null; },
    onState(point) {
      if (!on || !localAt || performance.now() - localAt > 400) cfg.show(scene, point);
    },
    onEvent,
    onAction,
  };
  return api;
}

export const initLaser = (h) => initPointer(h, 'laser');
export const initFollow = (h) => initPointer(h, 'mensch');
