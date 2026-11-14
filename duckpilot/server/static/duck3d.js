// 3D-Ansicht: die Ente, ihr Zimmer, ihr Tiefensensor, ihre Spur, Ziele und gemerkte Orte.
// Koordinaten: Simulator x = vorn, y = links, z = oben  →  three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { loadModel, RealDuck } from './duckmodel.js';
import { CloudLayer } from './pointcloud.js';
import { baueMoebel } from './moebel3d.js';
import { Reachy } from './reachy3d.js';
import { Duck } from './ente3d.js';
import { studio } from './licht3d.js';
import { boden, himmel, teppich, waende } from './raum3d.js';
import { allesVerschmelzen, FARBEN } from './formen3d.js';
import { sockeHaengen, sockeLegen, sockenForm } from './dinge3d.js';
import { loadReachy, RealReachy } from './reachymodell.js';
import { ladeArm, RealArm } from './arm3d.js';
import { StackChan } from './stackchan3d.js';
import { Bittle } from './bittle3d.js';
import { Lage, Stabilisator } from './glaetten3d.js';
import { EffectComposer } from './vendor/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './vendor/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from './vendor/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from './vendor/jsm/postprocessing/OutputPass.js';
import { ShaderPass } from './vendor/jsm/postprocessing/ShaderPass.js';
import { FXAAShader } from './vendor/jsm/shaders/FXAAShader.js';

// Darstellungsqualität: „hoch“ = Umgebungsverdeckung (GTAO) und volle Pixeldichte, „schnell“ = ohne.
// Ohne Vorgabe startet die Ansicht hoch und schaltet selbst herunter, wenn der Rechner nicht hinterherkommt.
const QUALITY_KEY = 'duckpilot.quality3d';
function savedQuality() { try { return localStorage.getItem(QUALITY_KEY); } catch { return null; } }

const C = {
  // Carbon Gray 90: Grund, Ebenen, Linien; Messwerte in Carbon-Blau, die Ente in Schnabel-Orange
  bg: 0x262626, edge: 0x9a9a9a,
  slate: 0x474747, body: 0xf3efe4, belly: 0xfffbf2, beak: 0xf0962c, eye: 0x161616, leg: 0x8d8d8d,
  ray: 0x4589ff, hit: 0xf0962c, pin: 0x4589ff, target: 0xf0962c, critical: 0xfa4d56,
  karteFrei: 0xcfe2ff, karteBelegt: 0x78a9ff, trail: 0xfff6e8,   // Karte und Spur hell auf den Dielen (0.38.24)
};
const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const ease = (t) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);



function itemMesh(item) {
  let mesh;
  const m = new THREE.MeshStandardMaterial({ color: item.color, roughness: item.kind === 'sock' ? 0.9 : 0.5, emissive: item.color, emissiveIntensity: item.kind === 'sock' ? 0.04 : 0.12 });
  if (item.kind === 'ball') {
    mesh = new THREE.Mesh(new THREE.SphereGeometry(item.r, 24, 16), m);
  } else if (item.kind === 'sock') {
    mesh = sockenForm(item, m);
  } else if (item.kind === 'baustein') {
    // Klemmbaustein 2×2: flacher Quader mit vier Noppen (seit 0.37)
    const s = item.r * 2;
    mesh = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(s, s * 0.6, s), m);
    mesh.add(body);
    for (const [dx, dz] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) {
      const stud = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.15, s * 0.15, s * 0.12, 12), m);
      stud.position.set(dx * s * 0.25, s * 0.36, dz * s * 0.25);
      mesh.add(stud);
    }
  } else if (item.kind === 'figur') {
    // Schachfigur (Bauer) als Drehkörper, Fuß bei y = 0
    const r = item.r;
    const pts = [[0, 0], [r, 0], [r, r * 0.3], [r * 0.6, r * 0.5], [r * 0.4, r * 1.6], [r * 0.7, r * 1.8],
      [r * 0.3, r * 2.0], [r * 0.55, r * 2.4], [r * 0.5, r * 2.9], [r * 0.25, r * 3.2], [0, r * 3.3]]
      .map(([x, y]) => new THREE.Vector2(x, y));
    mesh = new THREE.Mesh(new THREE.LatheGeometry(pts, 20), m);
  } else {
    mesh = new THREE.Mesh(new THREE.BoxGeometry(item.r * 2, item.r * 2, item.r * 2), m);
  }
  mesh.castShadow = true;
  mesh.traverse((o) => { o.castShadow = true; });
  mesh.userData.ruheDrehung = mesh.rotation.clone();
  return mesh;
}

// Getragen im Schnabel (seit 0.38.25, Hinweis „die Socke sieht fehlerhaft aus“): vorher saß das Ding nur mit
// seinem Mittelpunkt an der Schnabelspitze, flach wie am Boden – die Socke steckte halb im Kopf. Jetzt hängt sie vor dem
// Schnabel nach unten, ein Ende zwischen den Schnabelhälften, und dreht sich mit der Ente; Kleines sitzt knapp vor der Spitze.
function imSchnabel(mesh, it, spitze, yaw) {
  const vorn = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
  if (it.kind === 'sock') {
    if (!mesh.userData.getragen) sockeHaengen(mesh);
    mesh.position.copy(spitze).addScaledVector(vorn, 0.004); // Bündchen zwischen den Schnabelhälften
    mesh.position.y -= 0.004;
    mesh.rotation.set(0, yaw, 0);                          // Schaft hängt nach unten, Fuß zeigt nach vorn
  } else {
    mesh.position.copy(spitze).addScaledVector(vorn, it.r * 0.8);
    mesh.position.y -= it.kind === 'figur' ? it.r * 1.6 : it.r * 0.3;
    mesh.rotation.set(0, yaw, 0);
  }
  if (it.kind === 'sock') mesh.position.y = Math.max(0.07 * (it.r / 0.035), mesh.position.y);    // Fuß nie im Boden
  else mesh.position.y = Math.max(0, mesh.position.y);
  mesh.userData.getragen = true;
}

// Schrift als Textur – für die Namen gemerkter Orte über ihren Markierungen
function labelSprite(text) {
  const pad = 14, font = 600, size = 30;
  const c = document.createElement('canvas');
  const g = c.getContext('2d');
  g.font = `${font} ${size}px 'IBM Plex Sans', system-ui, sans-serif`;
  const w = Math.ceil(g.measureText(text).width) + pad * 2, h = size + pad * 1.4;
  c.width = w; c.height = h;
  g.font = `${font} ${size}px 'IBM Plex Sans', system-ui, sans-serif`;
  g.fillStyle = 'rgba(57,57,57,0.9)';
  const r = h / 2;
  g.beginPath();
  g.moveTo(r, 0); g.lineTo(w - r, 0); g.arc(w - r, r, r, -Math.PI / 2, Math.PI / 2);
  g.lineTo(r, h); g.arc(r, r, r, Math.PI / 2, -Math.PI / 2); g.fill();
  g.fillStyle = '#f4f4f4';
  g.textBaseline = 'middle';
  g.fillText(text, pad, h / 2 + 1);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  sprite.scale.set(w / 1800, h / 1800, 1);
  sprite.renderOrder = 10;
  return sprite;
}

const TRAIL_MAX = 900;

export class Scene3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    const licht = studio(this.renderer, this.scene, C.bg);
    this.scene.add(himmel(C.bg));
    this.scene.fog = new THREE.Fog(C.bg, 3.5, 8.5);
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 40);
    this.camera.position.set(-1.75, 0.85, -0.75);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.target.set(-0.45, 0.08, 0.2);
    this.controls.maxPolarAngle = Math.PI * 0.48;
    this.controls.minDistance = 0.25;
    this.controls.maxDistance = 7;

    this.key = licht.key;
    this.keyOffset = licht.keyOffset;

    this.duck = new Duck();
    this.scene.add(this.duck.root);
    this.modelStyle = 'original';
    this.simpleDuck = this.duck;
    this.realDuck = null;
    this.loadOriginal();
    this.items = new Map();
    this.worldGroup = new THREE.Group();
    this.scene.add(this.worldGroup);
    this.follow = true;
    this.showSensor = true;
    this.showTrail = true;
    this._buildFloor(6, 6);
    this._buildRays();
    this._buildTrail();
    this._buildTarget();
    this.pins = new THREE.Group();
    this.scene.add(this.pins);
    this.effects = [];
    this._last = performance.now();
    this._lastDuckPos = new THREE.Vector3();
    this.state = null;
    this.lage = new Lage();               // seit 0.38.52: ruhige Lage trotz holprigem Zustand übers WLAN
    this.stabil = new Stabilisator();     // … und ruhiger Entenblick
    this.engine = null;
    this.intro = REDUCED ? null : { t: 0, done: false };
    this.paused = false;
    this._setupComposer();
    // Entenblick: was die Kopfkamera sieht (Bild im Bild)
    this.povCam = new THREE.PerspectiveCamera(62, 4 / 3, 0.012, 15);
    this.showPov = false;
    this.mode = 'beobachten';
    this.povFrame = null;      // HTML-Rahmen mit Beschriftung, setzt app.js
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas);
    const loop = () => { if (!this.paused) this._frame(); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  // Kopfkamera: Lage aus dem Originalmodell (Stelle head_camera im Kieferkörper, Blick entlang −z,
  // oben = +x im MJCF-Rahmen) oder aus dem Kopf der einfachen Ente.
  _placePovCam(aspect, dt = null) {     // mit dt: stabilisiert (ganze Bühne im Entenblick)
    const site = this.duck.sites && this.duck.sites.head_camera;
    const node = site || this.duck.povNode || this.duck.headRoll || this.duck.root;   // povNode: Reachy Minis Kamera
    node.updateWorldMatrix(true, false);
    const pos = new THREE.Vector3(), q = new THREE.Quaternion();
    node.getWorldPosition(pos);
    node.getWorldQuaternion(q);
    const dir = (site ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(1, 0, 0)).applyQuaternion(q);
    const up = (site ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)).applyQuaternion(q);
    if (dt !== null) this.stabil.fuehren(this.povCam, pos.addScaledVector(dir, 0.004), dir, dt);
    else {
      this.povCam.position.copy(pos).addScaledVector(dir, 0.004);
      this.povCam.up.copy(up);
      this.povCam.lookAt(pos.clone().add(dir));
    }
    this.povCam.aspect = aspect;
    this.povCam.updateProjectionMatrix();
  }

  _renderPov() {
    const r = this.renderer;
    const size = r.getSize(new THREE.Vector2());
    const w = Math.round(Math.min(360, Math.max(200, size.x * 0.28))), h = Math.round(w * 0.75);
    const x = size.x - w - 20, y = 20;
    this.povCam.fov = 62;
    this._placePovCam(w / h);
    const rays = this.rays ? this.rays.visible : false, hits = this.hits ? this.hits.visible : false;
    if (this.rays) this.rays.visible = false;
    if (this.hits) this.hits.visible = false;
    r.setScissorTest(true);
    r.setViewport(x, y, w, h);
    r.setScissor(x, y, w, h);
    r.render(this.scene, this.povCam);
    r.setScissorTest(false);
    r.setViewport(0, 0, size.x, size.y);
    if (this.rays) this.rays.visible = rays;
    if (this.hits) this.hits.visible = hits;
    if (this.povFrame) {
      Object.assign(this.povFrame.style, { width: `${w}px`, height: `${h}px`, right: '20px', bottom: '20px' });
    }
  }

  // Kamerabild für die kleine Kachel unten links: Kopfkamera in ein kleines Bild rendern und kopieren
  snapshotPov(canvas) {
    if (!this.duck || !canvas) return false;
    const w = canvas.width, h = canvas.height;
    if (!this._povRT || this._povRT.width !== w || this._povRT.height !== h) {
      this._povRT?.dispose();
      this._povRT = new THREE.WebGLRenderTarget(w, h);
      this._povRT.texture.colorSpace = THREE.SRGBColorSpace;   // wie auf dem Bildschirm, sonst zu dunkel
      this._povBuf = new Uint8Array(w * h * 4);
    }
    const r = this.renderer;
    this.povCam.fov = 62;
    this._placePovCam(w / h);
    const rays = this.rays ? this.rays.visible : false, hits = this.hits ? this.hits.visible : false;
    if (this.rays) this.rays.visible = false;
    if (this.hits) this.hits.visible = false;
    const prev = r.getRenderTarget();
    r.setRenderTarget(this._povRT);
    r.render(this.scene, this.povCam);
    r.readRenderTargetPixels(this._povRT, 0, 0, w, h, this._povBuf);
    r.setRenderTarget(prev);
    if (this.rays) this.rays.visible = rays;
    if (this.hits) this.hits.visible = hits;
    const ctx = canvas.getContext('2d');
    const img = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {          // WebGL liest von unten nach oben
      img.data.set(this._povBuf.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);
    }
    ctx.putImageData(img, 0, 0);
    return true;
  }

  resize() {
    const c = this.renderer.domElement;
    const w = c.clientWidth || 800, h = c.clientHeight || 600;
    this.renderer.setSize(w, h, false);
    if (this.composer) this.composer.setSize(w, h);
    if (this.fxaa) {
      const pr = this.renderer.getPixelRatio();
      this.fxaa.material.uniforms.resolution.value.set(1 / (w * pr), 1 / (h * pr));
    }
    // Bühne zuerst (0.38.19): schwebt das Gespräch rechts über der Szene, rückt die Bildmitte um die halbe
    // Panelbreite nach links – die Figur steht in der Mitte des sichtbaren Teils
    const talk = c.closest('.view-cockpit')?.querySelector(':scope > .talk');
    const dx = talk && getComputedStyle(talk).position === 'absolute' ? Math.round((talk.offsetWidth + 16) / 2) : 0;
    this.camera.aspect = (w + 2 * dx) / h;
    if (dx) this.camera.setViewOffset(w + 2 * dx, h, 2 * dx, 0, w, h); else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
  }

  // Nachbearbeitung: Umgebungsverdeckung (GTAO) für Tiefe in Fugen und unter der Ente, dann Tonwerte.
  _setupComposer() {
    const size = this.renderer.getSize(new THREE.Vector2());
    const target = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: 4 });
    this.composer = new EffectComposer(this.renderer, target);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.gtao = new GTAOPass(this.scene, this.camera, size.x, size.y);
    // 16 Proben und 16 beim Glätten (0.38.18 auf 12/8 gesenkt – das rauschte sichtbar an Möbelkanten, gemeldet nach
    // 0.38.32: „Schattenqualität sehr verrauscht“). Zu langsame Rechner schalten unter „Auto“ ohnehin auf „schnell“.
    this.gtao.updateGtaoMaterial({ radius: 0.07, distanceExponent: 1.6, thickness: 1.2, scale: 1.0, samples: 16 });
    this.gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 8, rings: 3, samples: 16 });
    this.gtao.blendIntensity = 0.9;
    // Verdeckung nur im Raum rechnen: draußen (Kuppel, Hintergrund) bleibt alles hell statt schwarz
    this.gtao.setSceneClipBox(new THREE.Box3(new THREE.Vector3(-9, -1, -9), new THREE.Vector3(9, 4, 9)));
    this.composer.addPass(this.gtao);
    this.composer.addPass(new OutputPass());
    // Kantenglättung am Ende (seit 0.38.33, „gibt es kein Antialiasing?“): Das 4-fache MSAA glättet nur das Bild selbst,
    // die Verdeckung (GTAO) entsteht ungeglättet und ließ Kanten treppen und feine Linien flimmern
    this.fxaa = new ShaderPass(FXAAShader);
    this.composer.addPass(this.fxaa);
    this._perf = { frames: 0, ms: 0, checked: false };
    this.setQuality(savedQuality() || 'auto');
  }

  // 'hoch' | 'schnell' | 'auto' (startet hoch, schaltet bei ruckelnder Ansicht selbst herunter)
  setQuality(q, remember = false) {
    this.quality = q;
    this.useComposer = q !== 'schnell';
    this.renderer.setPixelRatio(q === 'schnell' ? 1 : Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.type = q === 'schnell' ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap;
    this.resize();
    if (remember) { try { localStorage.setItem(QUALITY_KEY, q); } catch { /* egal */ } }
  }

  _watchPerformance(dtMs) {
    if (this.quality !== 'auto' || this._perf.checked) return;
    const p = this._perf;
    p.frames++;
    if (p.frames < 60) return;          // Laden und Aufbau nicht mitzählen
    p.ms += dtMs;
    if (p.frames < 240) return;
    p.checked = true;
    if (p.ms / 180 > 28) {               // unter ~35 Bildern pro Sekunde: Verdeckung aus
      this.useComposer = false;
      this.renderer.setPixelRatio(1);
      this.resize();
      this.onQualityDrop?.();
    }
  }

  _buildFloor(w, d) {
    this.bodenGruppe = boden(this.renderer, w, d);
    this.worldGroup.add(this.bodenGruppe);        // Dielen mit leisem 10-cm-Raster (raum3d.js)
  }

  _edges(mesh, opacity = 0.45) {
    const lines = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 30),
      new THREE.LineBasicMaterial({ color: C.edge, transparent: true, opacity }));
    lines.position.copy(mesh.position);
    lines.rotation.copy(mesh.rotation);
    this.worldGroup.add(lines);
  }

  setWorld(world) {
    this.scene.remove(this.worldGroup);
    this.worldGroup = new THREE.Group();
    this.moebel = [];                       // für die Kamera, die Möbeln ausweicht (seit 0.37)
    this.scene.add(this.worldGroup);
    this._waendeAusrichten = null;
    if (!world) { this._buildFloor(6, 6); return; }
    this._buildFloor(world.width + 0.02, world.depth + 0.02);
    if (!world.offen) {
      // Wände wie im Puppenhaus: die zur Kamera zeigenden treten bis auf die Fußleiste zurück (seit 0.38.18)
      const w = waende(world.width, world.depth);
      this.worldGroup.add(w.gruppe);
      this.waendeGruppe = w.gruppe;
      this._waendeAusrichten = w.ausrichten;
    }
    const tisch = world.boxes.find((b) => /couchtisch|coffee table/i.test(b.name || ''));
    if (tisch) this.worldGroup.add(teppich(tisch.x, -tisch.y, Math.max(tisch.sx, tisch.sy) * 1.15));
    const tone = (hex) => new THREE.Color(hex).lerp(new THREE.Color(C.slate), 0.7);
    // seit 0.37.6: erkennbare Möbel aus wenigen einfachen Körpern (moebel3d.js); jedes Teil zählt fürs Anwählen
    // und für die Kamera wie das ganze Möbelstück. Unbekannte Namen bleiben Kasten bzw. Zylinder.
    const toneWarm = (hex) => new THREE.Color(hex).lerp(new THREE.Color(C.slate), 0.25);
    const modell = (b, r) => {
      const g = baueMoebel(b, toneWarm);
      if (!g) return false;
      allesVerschmelzen(g);                 // je Möbel und Material ein Mesh (ein Regal hat sonst ein Mesh je Buch)
      const info = { name: b.name, x: b.x, y: b.y, r };
      g.traverse((o) => { if (o.isMesh) { o.userData.moebel = info; this.moebel.push(o); } });
      this.worldGroup.add(g);
      return true;
    };
    for (const b of world.boxes) {
      if (modell(b, Math.hypot(b.sx, b.sy) / 2)) continue;
      const m = new THREE.Mesh(new THREE.BoxGeometry(b.sx, b.h, b.sy), new THREE.MeshStandardMaterial({ color: tone(b.color), roughness: 0.8 }));
      m.position.set(b.x, b.h / 2, -b.y);
      m.castShadow = m.receiveShadow = true;
      m.userData.moebel = { name: b.name, x: b.x, y: b.y, r: Math.hypot(b.sx, b.sy) / 2 };
      this.worldGroup.add(m);
      this.moebel.push(m);
      this._edges(m);
    }
    for (const c of world.cylinders) {
      if (modell(c, c.r)) continue;
      const m = new THREE.Mesh(new THREE.CylinderGeometry(c.r, c.r * 0.85, c.h, 28), new THREE.MeshStandardMaterial({ color: tone(c.color), roughness: 0.8 }));
      m.position.set(c.x, c.h / 2, -c.y);
      m.castShadow = m.receiveShadow = true;
      m.userData.moebel = { name: c.name, x: c.x, y: c.y, r: c.r };
      this.worldGroup.add(m);
      this.moebel.push(m);
      this._edges(m, 0.3);
    }
    // Parcours: Bahn, gekippte Platten (Rampen), Stufen, Start- und Ziellinie
    if (world.bahn) {
      const b = world.bahn;
      const lane = new THREE.Mesh(new THREE.PlaneGeometry(b.bis - b.von + 0.3, b.breite),
        new THREE.MeshStandardMaterial({ color: new THREE.Color(C.slate).lerp(new THREE.Color('#ffffff'), 0.06), roughness: 0.95 }));
      lane.rotation.x = -Math.PI / 2;
      lane.position.set((b.von + b.bis) / 2, 0.0006, 0);
      lane.receiveShadow = true;
      this.worldGroup.add(lane);
    }
    for (const p of world.teile || []) {
      const mat = new THREE.MeshStandardMaterial({ color: p.marke ? new THREE.Color(p.color) : tone(p.color), roughness: 0.85 });
      const m = new THREE.Mesh(new THREE.BoxGeometry(p.sx, p.sz, p.sy), mat);
      m.position.set(p.x, p.z, -p.y);
      m.rotation.z = -(p.pitch || 0);       // Neigung um die Welt-y-Achse = um −z in three.js
      m.castShadow = !p.marke;
      m.receiveShadow = true;
      this.worldGroup.add(m);
      if (!p.marke) this._edges(m, 0.3);
    }
  }

  setItems(items) {
    if (!items) return;
    for (const it of items) {
      let mesh = this.items.get(it.name);
      if (!mesh) {
        mesh = itemMesh(it);
        this.items.set(it.name, mesh);
        this.scene.add(mesh);
      }
      mesh.userData.item = it;
    }
  }

  // Kamera weicht Möbeln aus (seit 0.37): Steht ein Möbelstück zwischen Figur und Kamera, rückt die Kamera davor; ist der
  // Blick wieder frei, gleitet sie langsam auf den gewünschten Abstand zurück. Dreht oder zoomt der Mensch gerade selbst,
  // hält sie still – sein Zoom wird der neue Wunschabstand. Seit 0.38.25 (Hinweis „wenn quasi hinter der Kamera zu
  // nah ein Objekt ist, zoomt er viel zu nah ran“): Liegt das Möbelstück näher an der Kamera als an der Figur, oder müsste
  // sie dafür näher als der Mindestrahmen heran, wird es durchsichtig, statt dass die Kamera springt.
  _kameraAusweichen(dt) {
    if (this.mode !== 'beobachten' || !this.moebel || !this.moebel.length || (this.intro && !this.intro.done)) {
      this._durchsichtig(null);
      return;
    }
    if (!this._ausweichenAn) {
      this._ausweichenAn = true;
      this.controls.addEventListener('start', () => {
        this._nutzerDreht = true;
        this._abstandBeimStart = this.camera.position.distanceTo(this.controls.target);
      });
      this.controls.addEventListener('end', () => {
        this._nutzerDreht = false;
        const ist = this.camera.position.distanceTo(this.controls.target);
        if (this._wunsch == null || Math.abs(ist - this._abstandBeimStart) > 0.02) this._wunsch = ist;
      });
    }
    const t = this.controls.target, cam = this.camera.position;
    const dir = cam.clone().sub(t);
    const ist = dir.length();
    if (ist < 1e-3) return;
    dir.divideScalar(ist);
    if (this._wunsch == null) this._wunsch = ist;
    this._kameraStrahl = this._kameraStrahl || new THREE.Raycaster();
    this._kameraStrahl.set(t, dir);
    this._kameraStrahl.far = this._wunsch;
    const hit = this._kameraStrahl.intersectObjects(this.moebel, false)[0];
    const rahmen = Math.max(this.controls.minDistance, this._figurHoehe() * 2);     // näher wirkt die Figur angeschnitten
    let soll = this._wunsch, durch = null;
    if (hit) {
      const davor = hit.distance - 0.08;
      if (hit.distance > this._wunsch * 0.5 || davor < rahmen) durch = hit.object.userData.moebel || hit.object;
      else soll = davor;
    }
    this._durchsichtig(durch);
    this.kameraAusgewichen = !!hit;
    if (this._nutzerDreht) return;
    const neu = ist + (soll - ist) * Math.min(1, dt * (soll < ist ? 6 : 2));
    if (Math.abs(neu - ist) > 1e-4) cam.copy(t).addScaledVector(dir, neu);
  }

  // Ein Möbelstück (alle Teile mit derselben Kennung) halb durchsichtig machen – null stellt alles wieder her
  _durchsichtig(wer) {
    if (wer === this._durchWer) return;
    for (const o of this.moebel || []) {
      const gemeint = wer && (o === wer || o.userData.moebel === wer);
      if (gemeint && !o.userData.echtStoff) {
        o.userData.echtStoff = o.material;
        o.material = o.material.clone();
        o.material.transparent = true;
        o.material.opacity = 0.28;
        o.material.depthWrite = false;
      } else if (!gemeint && o.userData.echtStoff) {
        o.material.dispose();
        o.material = o.userData.echtStoff;
        delete o.userData.echtStoff;
      }
    }
    this._durchWer = wer;
  }

  // Wie groß die Figur ist (seit 0.38.25, Hinweis „Odi ist ja etwas größer und der Kopf ist schon Oberkante vom
  // Kameraausschnitt“): Höhe über den Füßen, an der Figur gemessen – nie kleiner als der Richtwert des Körpers (die Figur
  // kann gerade sitzen oder liegen). Startperspektive, Blickpunkt und Mindestabstand richten sich danach.
  _figurHoehe() {
    const fig = this.duck;
    if (this._hoeheVon === fig && this._hoehe) return this._hoehe;
    const richt = { open_duck_mini: 0.42, reachy_mini: 0.3 }[this.koerper] || 0.26;
    let h = richt;
    try {
      const box = new THREE.Box3().setFromObject(fig.root);
      const gemessen = box.isEmpty() ? 0 : box.max.y - fig.root.position.y;
      if (gemessen > richt && gemessen < 0.8) h = gemessen;
    } catch { /* Richtwert genügt */ }
    this._hoeheVon = fig;
    this._hoehe = h;
    return h;
  }

  // Maßstab der Kamera gegenüber der Microduck (für Odi größer, Reachy auf dem Tisch etwa gleich)
  _rahmenMass() {
    return Math.max(1, Math.min(1.6, 1 + (this._figurHoehe() - 0.26) * 2.2));
  }

  // Erkundeter Bereich (seit 0.37): freie Zellen als zarte Kacheln, Hindernisse als kräftigere Kacheln.
  // k = {zelle_m, messungen, frei: [[i, j]], belegt: [[i, j]]} oder null (ausblenden)
  // Erkundeter Bereich: Kästchen wie bisher (Wunsch 7.11.: „das mit den Kästchen fand ich besser, halt nur zu
  // wenig sichtbar“), aber hell und kühl auf den Dielen und über dem Teppich (der liegt auf 2 mm – vorher flimmerten sie dort)
  setKarte(k) {
    if (!this.karteGroup) { this.karteGroup = new THREE.Group(); this.scene.add(this.karteGroup); }
    const sig = k ? `${k.messungen}|${k.frei.length}|${k.belegt.length}` : '';
    if (sig === this._karteSig) return;
    this._karteSig = sig;
    for (const c of [...this.karteGroup.children]) {
      this.karteGroup.remove(c);
      c.geometry.dispose();
      c.material.dispose();
    }
    if (!k) return;
    const z = k.zelle_m;
    const m = new THREE.Matrix4();
    const lege = (zellen, geo, material, h) => {
      if (!zellen.length) return;
      const inst = new THREE.InstancedMesh(geo, material, zellen.length);
      zellen.forEach(([i, j], n) => { m.makeTranslation((i + 0.5) * z, h, -(j + 0.5) * z); inst.setMatrixAt(n, m); });
      inst.instanceMatrix.needsUpdate = true;
      inst.raycast = () => {};                // die Karte ist kein Ding zum Anklicken
      inst.renderOrder = 1;
      this.karteGroup.add(inst);
    };
    const kachel = new THREE.PlaneGeometry(z * 0.86, z * 0.86).rotateX(-Math.PI / 2);
    const stoff = (farbe, deckung) => new THREE.MeshBasicMaterial({ color: farbe, transparent: true, opacity: deckung,
      depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    lege(k.frei, kachel, stoff(C.karteFrei, 0.32), 0.006);
    // Hindernis-Zellen flach am Boden (seit 0.37.14): als 2,5-cm-Klötze wirkten sie wie Dinge, die in der Luft schweben
    lege(k.belegt, kachel.clone(), stoff(C.karteBelegt, 0.8), 0.007);
  }

  // Gemerkte Orte: Stab, Kopf, Name darüber. places = [{name, x, y}]
  setPlaces(places) {
    const keep = new Set(places.map((p) => p.name));
    for (const pin of [...this.pins.children]) {
      if (!keep.has(pin.userData.name)) this.pins.remove(pin);
    }
    for (const p of places) {
      let pin = this.pins.children.find((c) => c.userData.name === p.name);
      if (!pin) {
        pin = new THREE.Group();
        pin.userData = { name: p.name, born: performance.now() };
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.22, 8),
          new THREE.MeshBasicMaterial({ color: C.pin, transparent: true, opacity: 0.8 }));
        pole.position.y = 0.11;
        const head = new THREE.Mesh(new THREE.SphereGeometry(0.014, 16, 12),
          new THREE.MeshStandardMaterial({ color: C.pin, emissive: C.pin, emissiveIntensity: 0.8 }));
        head.position.y = 0.225;
        const disc = new THREE.Mesh(new THREE.RingGeometry(0.03, 0.04, 40),
          new THREE.MeshBasicMaterial({ color: C.pin, transparent: true, opacity: 0.6, side: THREE.DoubleSide }));
        disc.rotation.x = -Math.PI / 2;
        disc.position.y = 0.002;
        const label = labelSprite(p.name);
        label.position.y = 0.27;
        pin.add(pole, head, disc, label);
        this.pins.add(pin);
        if (!REDUCED && performance.now() - this._last < 1000 && this.state) this.pulse('place', p.x, p.y);
      }
      pin.position.set(p.x, 0, -p.y);
    }
  }

  _buildRays() {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(8 * 2 * 3), 3));
    this.rays = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
      color: C.ray, transparent: true, opacity: 0.45, blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    this.scene.add(this.rays);
    this.hits = new THREE.InstancedMesh(new THREE.SphereGeometry(0.009, 10, 8),
      new THREE.MeshBasicMaterial({ color: C.hit, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending }), 8);
    this.scene.add(this.hits);
  }

  // Gelaufene Spur (seit 0.38.24, Hinweis „passt nicht so zum Rest“): statt einer dünnen Linie, die aus Dunkelgrau
  // ins Blau lief, ein weiches helles Band auf den Dielen, das nach hinten ausblendet – wie Kreide auf Holz.
  _buildTrail() {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(TRAIL_MAX * 2 * 3), 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(TRAIL_MAX * 2 * 4), 4));
    const idx = [];
    for (let i = 0; i < TRAIL_MAX - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    geo.setIndex(idx);
    geo.setDrawRange(0, 0);
    this.trail = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, depthWrite: false, toneMapped: false, side: THREE.DoubleSide }));
    this.trail.frustumCulled = false;
    this.trail.raycast = () => {};
    this.trail.renderOrder = 1;
    this.trailPts = [];
    this.scene.add(this.trail);
  }

  clearTrail() { this.trailPts = []; this._spurGlatt = null; this._writeTrail(); }

  _pushTrail(x, z) {
    // leicht geglättet (Hinweis 7.11.: „das Gezitter muss nicht so deutlich sein“): der Gang wiegt die Ente
    // bei jedem Schritt zur Seite – die Spur folgt dem Mittel, nicht jedem Ausschlag
    const g = this._spurGlatt;
    if (!g || Math.hypot(g[0] - x, g[1] - z) > 0.6) this._spurGlatt = [x, z];
    else { g[0] += (x - g[0]) * 0.18; g[1] += (z - g[1]) * 0.18; }
    [x, z] = this._spurGlatt;
    const last = this.trailPts[this.trailPts.length - 1];
    if (last && Math.hypot(last[0] - x, last[1] - z) < 0.03) return;
    if (last && Math.hypot(last[0] - x, last[1] - z) > 0.6) this.trailPts = []; // Sprung (neuer Körper)
    this.trailPts.push([x, z]);
    if (this.trailPts.length > TRAIL_MAX) this.trailPts.shift();
    this._writeTrail();
  }

  _writeTrail() {
    const pos = this.trail.geometry.attributes.position, col = this.trail.geometry.attributes.color;
    const p = this.trailPts, n = p.length, c = new THREE.Color(C.trail), halb = 0.012;
    for (let i = 0; i < n; i++) {
      const a = p[Math.max(0, i - 1)], b = p[Math.min(n - 1, i + 1)];
      let dx = b[0] - a[0], dz = b[1] - a[1];
      const l = Math.hypot(dx, dz) || 1;
      dx /= l; dz /= l;
      const t = (i + 1) / n, w = halb * (0.55 + 0.45 * t), al = 0.62 * Math.pow(t, 1.3);
      pos.setXYZ(i * 2, p[i][0] - dz * w, 0.004, p[i][1] + dx * w);
      pos.setXYZ(i * 2 + 1, p[i][0] + dz * w, 0.004, p[i][1] - dx * w);
      col.setXYZW(i * 2, c.r, c.g, c.b, al);
      col.setXYZW(i * 2 + 1, c.r, c.g, c.b, al);
    }
    this.trail.geometry.setDrawRange(0, Math.max(0, n - 1) * 6);
    pos.needsUpdate = col.needsUpdate = true;
  }

  _buildTarget() {
    const g = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.045, 0.055, 48),
      new THREE.MeshBasicMaterial({ color: C.target, transparent: true, opacity: 0.9, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.003;
    const outer = new THREE.Mesh(new THREE.RingGeometry(0.07, 0.074, 48),
      new THREE.MeshBasicMaterial({ color: C.target, transparent: true, opacity: 0.5, side: THREE.DoubleSide }));
    outer.rotation.x = -Math.PI / 2;
    outer.position.y = 0.003;
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.5, 8, 1, true),
      new THREE.MeshBasicMaterial({ color: C.target, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false }));
    beam.position.y = 0.25;
    g.add(ring, outer, beam);
    g.visible = false;
    g.userData = { outer, beam };
    this.target = g;
    this.scene.add(g);
  }

  // Kurzer Effekt: sich ausbreitender Ring am Boden
  // 'beobachten': Kamera kreist um die Ente · 'entenblick': durch die Augen der Ente
  // Kamera fährt vor die Figur – leicht seitlich, etwas über Kopfhöhe, wie ein Mensch, der mit ihr spielt
  // (Kamera-Spiele, seit 0.38.14). Reduzierte Bewegung: sofort dort, ohne Fahrt.
  anfahren({ abstand = 0.8, hoehe = 0.32, seitlich = 0.22, dauer = 1.6 } = {}) {
    const p = this.duck.root.position;
    const yaw = (this.state && this.state.yaw) || 0;
    const vorn = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
    const quer = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
    const s = this._rahmenMass();
    const zu = p.clone().addScaledVector(vorn, abstand * s).addScaledVector(quer, seitlich * s);
    zu.y += hoehe * s;
    const ziel = new THREE.Vector3(p.x, p.y + this._figurHoehe() * 0.54, p.z);
    if (REDUCED) {
      this.camera.position.copy(zu);
      this.controls.target.copy(ziel);
      this._lastDuckPos.copy(p);
      this.intro = null;
      return;
    }
    this.intro = { t: 0, done: false, dauer, zu, ziel, von: this.camera.position.clone(), vonZiel: this.controls.target.clone() };
  }

  setMode(mode) {
    this.mode = mode === 'entenblick' ? 'entenblick' : 'beobachten';
    this.stabil.ort = null;
    this.controls.enabled = this.mode === 'beobachten';
  }

  // Bildschirmpunkt → Boden (und getroffenes Ding) in Simulator-Koordinaten: x vorn, y links, z oben
  pick(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    const cam = this.mode === 'entenblick' ? this.povCam : this.camera;
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, cam);
    const solid = [];
    this.worldGroup.traverse((o) => { if (o.isMesh && o.geometry && o.geometry.type !== 'PlaneGeometry') solid.push(o); });
    for (const m of this.items.values()) m.traverse((o) => { if (o.isMesh) { o.userData.ding = m; solid.push(o); } });
    for (const e of (this.enten || new Map()).values()) {
      e.root.traverse((o) => { if (o.isMesh) { o.userData.ente = e; solid.push(o); } });
    }
    this.duck?.werkbank?.traverse((o) => { if (o.isMesh) solid.push(o); });   // Würfel, Kisten des Arms
    const hits = ray.intersectObjects(solid, false);
    const floorT = ray.ray.direction.y < -1e-4 ? -ray.ray.origin.y / ray.ray.direction.y : Infinity;
    const out = {};
    if (Number.isFinite(floorT) && floorT < 30) {
      const f = ray.ray.origin.clone().addScaledVector(ray.ray.direction, floorT);
      out.floor = { x: f.x, y: -f.z };
    }
    if (hits.length && hits[0].distance < floorT) {
      const h = hits[0].point;
      out.hit = { x: h.x, y: -h.z, z: Math.max(0, h.y) };
      const o = hits[0].object;
      const d = o.userData.ding;
      const ws = o.userData.werkstueck;
      out.ding = ws ? ws.art : d && d.userData.item ? d.userData.item.kind : o.userData.ente ? 'ente' : 'moebel';
      // seit 0.37.3: was genau angeklickt wurde – fürs Anwählen und Handeln
      if (ws) out.name = ws.name;
      else if (d && d.userData.item) out.name = d.userData.item.name;
      else if (o.userData.ente && o.userData.ente._st) out.name = o.userData.ente._st.name;
      else if (o.userData.moebel) out.name = o.userData.moebel.name;
      if (out.name) out.art = out.ding;
    }
    // Kleine Dinge sind schwer genau zu treffen: knapp daneben auf den Boden geklickt zählt auch (Ding ≤ 6 cm,
    // Ente ≤ 12 cm) – nur wenn kein Möbelstück davor steht
    if (!out.name && out.floor && (!out.hit || out.ding !== 'moebel')) {
      let best = null;
      const near = (name, art, x, y, max) => {
        const d = Math.hypot(x - out.floor.x, y - out.floor.y);
        if (d <= max && (!best || d < best.d)) best = { name, art, x, y, d };
      };
      for (const m of this.items.values()) {
        const it = m.userData.item;
        if (it && !it.held) near(it.name, it.kind, it.x, it.y, Math.max(0.06, it.r + 0.03));
      }
      for (const e of (this.enten || new Map()).values()) if (e._st) near(e._st.name, 'ente', e._st.x, e._st.y, 0.12);
      if (best) {
        out.name = best.name; out.art = best.art; out.ding = best.art;
        out.hit = { x: best.x, y: best.y, z: 0.03 };
      }
    }
    out.look = out.hit || (out.floor ? { ...out.floor, z: 0 } : null);
    return out;
  }

  // Wohin die Ente gerade von Hand schaut: kleiner Ring mit Punkt (bleibt still, auch bei reduzierter Bewegung)
  setGaze(point, seconds = 8) {
    if (!this.gazeMark) {
      const g = new THREE.Group();
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.045, 0.056, 40),
        new THREE.MeshBasicMaterial({ color: C.ray, transparent: true, opacity: 0.95, side: THREE.DoubleSide, depthTest: false }));
      const dot = new THREE.Mesh(new THREE.CircleGeometry(0.013, 20),
        new THREE.MeshBasicMaterial({ color: C.ray, transparent: true, opacity: 0.95, side: THREE.DoubleSide, depthTest: false }));
      ring.renderOrder = dot.renderOrder = 5;
      g.add(ring, dot);
      g.visible = false;
      this.gazeMark = g;
      this.scene.add(g);
    }
    if (!point) { this.gazeMark.visible = false; this.gazeMark.userData.until = 0; return; }
    this.gazeMark.position.set(point.x, (point.z || 0) + 0.004, -point.y);
    this.gazeMark.userData.until = performance.now() + seconds * 1000;
    this.gazeMark.userData.onFloor = !(point.z > 0.01);
    this.gazeMark.visible = true;
  }

  // Laserpunkt des Menschen: kleiner, sehr heller roter Fleck mit Schein (auch im Entenblick zu sehen)
  setLaser(point) {
    if (!point) { if (this.laserDot) this.laserDot.visible = false; return; }
    if (!this.laserDot) {
      const g = new THREE.Group();
      const core = new THREE.Mesh(new THREE.CircleGeometry(0.008, 20),
        new THREE.MeshBasicMaterial({ color: 0xfff1ee, side: THREE.DoubleSide, depthWrite: false }));
      const glow = new THREE.Mesh(new THREE.CircleGeometry(0.024, 28),
        new THREE.MeshBasicMaterial({ color: 0xff2414, transparent: true, opacity: 0.55, side: THREE.DoubleSide,
          blending: THREE.AdditiveBlending, depthWrite: false }));
      core.position.y = 0.0012;
      core.rotation.x = glow.rotation.x = -Math.PI / 2;
      core.renderOrder = glow.renderOrder = 6;
      g.add(glow, core);
      this.laserDot = g;
      this.scene.add(g);
    }
    this.laserDot.position.set(point.x, (point.z || 0) + 0.003, -point.y);
    this.laserDot.visible = true;
  }

  // Mensch zum Hinterherlaufen (Folg mir im Simulator): so, wie die Ente einen Menschen sieht – Schuhe und
  // Knöchel in echter Größe, nach oben schnell ausgeblendet. Eine ganze 1,7-m-Verkörperung neben der 25-cm-Ente wirkte riesig
  // und lenkte ab. Seit 0.37.14 (Befund aus dem Test „Füße ganz komisch, teils sehr versetzt“): echte Schuhform statt
  // durchsichtiger Ovale, Schrittlänge nach Weg, Blickrichtung geglättet (kein Umklappen bei kleinen Mausbewegungen),
  // und bleibt der Zeiger stehen, stellt die Verkörperung die Füße wieder nebeneinander.
  setPerson(point) {
    if (!point) { if (this.personFig) this.personFig.visible = false; return; }
    if (!this.personFig) this.personFig = this._baueMensch();
    const g = this.personFig;
    const u = g.userData;
    const x = point.x, z = -point.y;
    const now = performance.now();
    if (u.last) {
      const dx = x - u.last.x, dz = z - u.last.z, d = Math.hypot(dx, dz);
      if (d > 0.5) {                                        // neu gesetzt: nicht wild trippeln
        u.phase = 0; u.ref = { x, z };
      } else if (d > 0.002) {
        u.phase += (d / 0.33) * Math.PI;                    // ≈ 66 cm Doppelschritt
        u.ruhe = now;
        const rx = x - u.ref.x, rz = z - u.ref.z, weg = Math.hypot(rx, rz);
        if (weg > 0.04) {                                   // Richtung erst nach ein paar Zentimetern Weg
          const soll = Math.atan2(rx, rz);
          let diff = Math.atan2(Math.sin(soll - u.heading), Math.cos(soll - u.heading));
          // kurz rückwärts (Maus zuckt zurück): Blick behalten statt umzuklappen
          if (Math.abs(diff) > 2.4 && weg < 0.12) diff = 0;
          u.heading += diff * 0.35;
          u.ref = { x, z };
        }
      }
    } else {
      u.ref = { x, z };
    }
    u.last = { x, z };
    g.position.set(x, 0, z);
    g.rotation.y = u.heading;
    this._stellFuesse(g, now);
    g.visible = true;
  }

  _baueMensch() {
    const LEG_H = 0.22;
    const legGeo = new THREE.CylinderGeometry(0.045, 0.04, LEG_H, 16, 6, true);
    const pos = legGeo.attributes.position;
    const rgba = new Float32Array(pos.count * 4);
    const base = new THREE.Color(0x8fa8c8);
    for (let i = 0; i < pos.count; i++) {
      const t = (pos.getY(i) + LEG_H / 2) / LEG_H;          // 0 unten … 1 oben
      rgba.set([base.r, base.g, base.b, 0.45 * (1 - t) ** 2], i * 4);
    }
    legGeo.setAttribute('color', new THREE.BufferAttribute(rgba, 4));
    const legMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, transparent: true, depthWrite: false, side: THREE.DoubleSide });
    const obermat = new THREE.MeshStandardMaterial({ color: 0x5d6f86, roughness: 0.75 });
    const sohlmat = new THREE.MeshStandardMaterial({ color: 0xe8e8e8, roughness: 0.9 });
    // Schuh: Sohle (flach, vorn abgerundet) und Obermaterial (Kappe vorn, Ferse hinten) – ≈ 27 × 10 cm
    const sohlGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.018, 20);
    const g = new THREE.Group();
    const feet = [];
    for (const dx of [-0.075, 0.075]) {
      const foot = new THREE.Group();
      const sohle = new THREE.Group();
      const vorn = new THREE.Mesh(sohlGeo, sohlmat); vorn.position.set(0, 0.009, 0.08);
      const hinten = new THREE.Mesh(sohlGeo, sohlmat); hinten.scale.set(0.85, 1, 0.85); hinten.position.set(0, 0.009, -0.07);
      const mitte = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.018, 0.15), sohlmat); mitte.position.set(0, 0.009, 0.005);
      sohle.add(vorn, hinten, mitte);
      const kappe = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), obermat);
      kappe.scale.set(0.047, 0.05, 0.1); kappe.position.set(0, 0.018, 0.04);
      const ferse = new THREE.Mesh(new THREE.CylinderGeometry(0.042, 0.045, 0.07, 18), obermat);
      ferse.position.set(0, 0.053, -0.06);
      const leg = new THREE.Mesh(legGeo, legMat);
      leg.position.set(0, 0.07 + LEG_H / 2, -0.06);
      foot.add(sohle, kappe, ferse, leg);
      for (const m of [vorn, hinten, mitte, kappe, ferse]) { m.castShadow = true; }
      foot.position.x = dx;
      g.add(foot);
      feet.push(foot);
    }
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.2, 0.225, 40),
      new THREE.MeshBasicMaterial({ color: 0xf0962c, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.003;
    g.add(ring);
    g.renderOrder = 5;
    g.userData = { feet, last: null, ref: null, phase: 0, heading: 0, ruhe: 0 };
    this.scene.add(g);
    return g;
  }

  // Füße aus der Schrittphase; steht der Zeiger still, schließen sie wieder auf (statt gespreizt stehen zu bleiben)
  _stellFuesse(g, now) {
    const u = g.userData;
    if (now - u.ruhe > 220) {
      const ziel = Math.round(u.phase / Math.PI) * Math.PI;
      u.phase += (ziel - u.phase) * 0.18;
    }
    const swing = Math.sin(u.phase) * 0.12;
    const heben = Math.abs(Math.sin(u.phase)) * 0.03;
    u.feet[0].position.z = swing;
    u.feet[1].position.z = -swing;
    // gehoben wird der Fuß, der gerade nach vorn schwingt
    const vor = Math.cos(u.phase) > 0;
    u.feet[0].position.y = vor ? heben : 0;
    u.feet[1].position.y = vor ? 0 : heben;
  }

  _updateGazeMark(now) {
    const g = this.gazeMark;
    if (!g.visible) return;
    if (now > g.userData.until) { g.visible = false; return; }
    // auf dem Boden flach, an Dingen zur Kamera gedreht
    if (g.userData.onFloor) g.rotation.set(-Math.PI / 2, 0, 0);
    else g.quaternion.copy((this.mode === 'entenblick' ? this.povCam : this.camera).quaternion);
  }

  pulse(kind, x, y) {
    if (REDUCED) return;
    const color = { fall: C.critical, place: C.pin, kick: C.beak, memory: C.pin, look: C.ray, go: C.target }[kind] || C.beak;
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.06, 0.075, 64),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(x, 0.004, -y);
    this.scene.add(ring);
    const small = kind === 'look' || kind === 'go';      // Klick-Rückmeldung: dezent, nicht raumfüllend
    this.effects.push({ mesh: ring, t: 0, life: small ? 0.7 : kind === 'fall' ? 1.4 : 1.1, grow: small ? 1.6 : kind === 'fall' ? 7 : 5 });
  }

  // Ein paar Federn fliegen – beim Schütteln im Goofy-Modus
  feathers() {
    if (REDUCED || !this.state) return;
    const origin = new THREE.Vector3();
    this.duck.body.getWorldPosition(origin);
    const geo = new THREE.PlaneGeometry(0.018, 0.008);
    for (let i = 0; i < 12; i++) {
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: i % 4 ? C.body : C.beak, transparent: true, side: THREE.DoubleSide, depthWrite: false }));
      m.position.copy(origin).add(new THREE.Vector3((Math.random() - 0.5) * 0.06, 0.02 + Math.random() * 0.04, (Math.random() - 0.5) * 0.06));
      const a = Math.random() * Math.PI * 2;
      const v = new THREE.Vector3(Math.cos(a) * (0.12 + Math.random() * 0.15), 0.25 + Math.random() * 0.25, Math.sin(a) * (0.12 + Math.random() * 0.15));
      m.rotation.set(Math.random() * 3, Math.random() * 3, Math.random() * 3);
      this.scene.add(m);
      this.effects.push({ mesh: m, t: 0, life: 1.6 + Math.random() * 0.6, feather: v, spin: (Math.random() - 0.5) * 12 });
    }
  }

  _updateRays(st) {
    const tof = st.perception && st.perception.tof_mm;
    const visible = this.showSensor && tof && tof.length === 64 && !st.fallen;
    this.rays.visible = this.hits.visible = !!visible;
    if (!visible) return;
    const origin = new THREE.Vector3();
    this.duck.headRoll.getWorldPosition(origin);
    const pos = this.rays.geometry.attributes.position;
    const m = new THREE.Matrix4();
    const yawWorld = st.yaw + (st.head ? st.head.head_yaw : 0);
    const fov = Math.PI / 4;
    let n = 0;
    for (let col = 0; col < 8; col++) {
      const d = Math.min(tof[3 * 8 + col], tof[4 * 8 + col]) / 1000;  // mittlere Zeilen: Hindernisse, nicht Boden
      const az = yawWorld + ((3.5 - col) / 8) * fov;
      const dir = new THREE.Vector3(Math.cos(az), 0, -Math.sin(az));
      const end = origin.clone().addScaledVector(dir, Math.min(d, 2));
      pos.setXYZ(col * 2, origin.x, origin.y, origin.z);
      pos.setXYZ(col * 2 + 1, end.x, end.y, end.z);
      const s = 0.8 + 0.4 * Math.sin(performance.now() / 160 + col);
      m.makeScale(s, s, s).setPosition(end.x, end.y, end.z);
      if (d < 1.95) this.hits.setMatrixAt(n++, m);
    }
    this.hits.count = n;
    this.hits.instanceMatrix.needsUpdate = true;
    pos.needsUpdate = true;
  }

  // 'original' = Pollens CAD-Modell, 'einfach' = die gezeichnete Ente
  // Pollens Modell holen – beim Start und noch einmal, sobald duckpilot es von GitHub geladen hat.
  // Bis dahin (oder ohne Modell) bleibt die einfache Ente.
  loadOriginal() {
    if (this.realDuck || this._loadingOriginal) return;
    this._loadingOriginal = true;
    loadModel().then((m) => {
      this.realDuck = new RealDuck(m);
      this.realDuck.setFarbe(this.farbe || 'cream');
      this._modell = m;
      if (this.enten) { for (const e of this.enten.values()) this.scene.remove(e.root); this.enten.clear(); }
      this.modelInfo = m.head;
      if (this.modelStyle === 'original') this.setModelStyle('original');
    }).catch((e) => console.info('Original-Modell (noch) nicht da, einfache Ente bleibt:', e.message))
      .finally(() => { this._loadingOriginal = false; });
  }

  // Farbe der Microduck (Original und einfache Gestalt)
  setFarbe(name) {
    this.farbe = name;
    this.realDuck?.setFarbe(name);
    this.simpleDuck?.setFarbe?.(name);
  }

  setModelStyle(style) {
    this.modelStyle = style;
    this._figurWaehlen();
  }

  // Welche Verkörperung steht in der Szene: Reachy Mini, wenn der Körper es sagt (seit 0.38.1), sonst die gewählte Ente
  _figurWaehlen() {
    let want = this.modelStyle === 'original' && this.realDuck ? this.realDuck : this.simpleDuck;
    if (this.koerper === 'open_duck_mini') {
      // Open Duck Mini (seit 0.38.4): offenes Modell (Apache-2.0) liegt bei duckpilot; bis es geladen ist die einfache Ente
      if (!this.realOpenDuck) this.ladeOpenDuck();
      want = this.modelStyle === 'original' && this.realOpenDuck ? this.realOpenDuck
        : this.einfacheOpenDuck || (this.einfacheOpenDuck = new Duck('open_duck'));
    }
    if (this.koerper === 'reachy_mini') {
      // Pollens Originalmodell, sobald es auf diesem PC gebacken ist (seit 0.38.2) – sonst das gezeichnete Modell
      if (!this.realReachy) this.ladeReachy();
      want = this.modelStyle === 'original' && this.realReachy ? this.realReachy : this.reachy || (this.reachy = new Reachy());
    }
    if (this.koerper === 'so101') {
      // SO-101 (seit 0.38.47, G5): offenes Modell (Apache-2.0) liegt bei Knowlin; bis es geladen ist, bleibt die Figur
      if (!this.realArm) this.ladeArm();
      if (this.realArm) want = this.realArm;
    }
    if (this.koerper === 'stackchan') want = this.stack || (this.stack = new StackChan());   // gezeichnet (0.38.58)
    if (this.koerper === 'bittle') want = this.hund || (this.hund = new Bittle());          // gezeichnet (0.38.59)
    if (want === this.duck) return;
    this.scene.remove(this.duck.root);
    this.duck = want;
    this.scene.add(this.duck.root);
  }

  ladeArm() {
    if (this.realArm || this._ladeArm) return;
    this._ladeArm = true;
    ladeArm().then((m) => {
      this.realArm = new RealArm(m);
      if (this.koerper === 'so101') this._figurWaehlen();
    }).catch((e) => console.info('SO-101-Modell nicht da:', e.message))
      .finally(() => { this._ladeArm = false; });
  }

  ladeOpenDuck() {
    if (this.realOpenDuck || this._ladeOpenDuck) return;
    this._ladeOpenDuck = true;
    loadModel('/static/model/open_duck_mini.dpm').then((m) => {
      this.realOpenDuck = new RealDuck(m);
      if (this.koerper === 'open_duck_mini') this._figurWaehlen();
    }).catch((e) => console.info('Open-Duck-Modell nicht da, einfache Ente bleibt:', e.message))
      .finally(() => { this._ladeOpenDuck = false; });
  }

  // Pollens Reachy-Modell holen (einmal; nach „reachy“-Meldung mit fertigem Modell erneut versuchen)
  ladeReachy(neu = false) {
    if ((this.realReachy && !neu) || this._ladeReachy) return;
    this._ladeReachy = true;
    loadReachy().then((m) => {
      this.realReachy = new RealReachy(m);
      if (this.koerper === 'reachy_mini') this._figurWaehlen();
    }).catch((e) => console.info('Reachy-Originalmodell (noch) nicht da, gezeichnetes Modell bleibt:', e.message))
      .finally(() => { this._ladeReachy = false; });
  }

  // Punktwolke des Tiefensensors als Ebene in der Szene (aus, bis „Punktwolke“ angehakt ist)
  setCloud(store) {
    this.cloud = new CloudLayer(store, { size: 0.02, background: '#262626' });
    this.cloud.visible = false;
    this.scene.add(this.cloud.points);
  }

  set showCloud(v) { if (this.cloud) this.cloud.visible = v; }
  get showCloud() { return !!(this.cloud && this.cloud.visible); }

  update(st, engine) {
    this.state = st;
    this.engine = engine || this.engine;
  }

  // Weitere Enten (seit 0.36.3): eigene Körper aus dem Simulator mit eigener Position – kein Klon der Hauptente
  // Anwählen (seit 0.37.3): ein Ring am Boden um das gewählte Ding, die Ente oder das Möbelstück – er wandert mit
  setAuswahl(sel) {
    this.auswahl = sel || null;
    if (!this.auswahlRing) {
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.92, 1, 48).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: C.target, transparent: true, opacity: 0.9, depthWrite: false }));
      ring.renderOrder = 2;
      ring.raycast = () => {};
      this.scene.add(ring);
      this.auswahlRing = ring;
    }
    this.auswahlRing.visible = false;
  }

  _auswahlZeichnen(now) {
    const sel = this.auswahl, ring = this.auswahlRing;
    if (!ring) return;
    let pos = null, r = 0.08, hoehe = 0.003;
    if (sel && (sel.art === 'wuerfel' || sel.art === 'kiste')) {      // auf der Werkbank des Arms (seit 0.38.53)
      let o = null;
      this.duck?.werkbank?.traverse((x) => { if (!o && x.userData.werkstueck?.name === sel.name) o = x; });
      if (o) {
        const w = o.getWorldPosition(new THREE.Vector3());
        pos = [w.x, -w.z]; r = sel.art === 'kiste' ? 0.075 : 0.035; hoehe = this.duck.root.position.y + 0.002;
      }
    } else if (sel && sel.art === 'ente') {
      const e = [...(this.enten || new Map()).values()].find((x) => x._st && x._st.name === sel.name);
      if (e) { pos = [e._st.x, e._st.y]; r = 0.13; }
    } else if (sel && sel.art === 'moebel') {
      const m = (this.moebel || []).find((x) => x.userData.moebel && x.userData.moebel.name === sel.name);
      if (m) { pos = [m.userData.moebel.x, m.userData.moebel.y]; r = m.userData.moebel.r + 0.06; }
    } else if (sel) {
      const m = this.items.get(sel.name);
      const it = m && m.userData.item;
      if (it) { pos = [it.x, it.y]; r = Math.max(0.05, it.r + 0.035); }
    }
    ring.visible = !!pos;
    if (!pos) return;
    const puls = REDUCED ? 1 : 1 + 0.06 * Math.sin(now / 260);
    ring.position.set(pos[0], hoehe, -pos[1]);
    ring.scale.setScalar(r * puls);
  }

  // Weiche Kontaktschatten (seit 0.37.1, Hinweis aus dem Test „die Enten schweben, als ob sie den Boden nicht berühren“):
  // Der echte Schatten des Hauptlichts reicht nur ±1,2 m um die Hauptente – weitere Enten weiter weg standen ohne
  // Schatten da und wirkten schwebend, obwohl die Füße den Boden berühren. Darunter liegt jetzt ein weicher Fleck.
  _kontaktSchatten() {
    if (!this._kontaktTex) {
      const c = document.createElement('canvas');
      c.width = c.height = 64;
      const g = c.getContext('2d');
      const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      r.addColorStop(0, 'rgba(0,0,0,0.55)');
      r.addColorStop(0.55, 'rgba(0,0,0,0.25)');
      r.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = r;
      g.fillRect(0, 0, 64, 64);
      this._kontaktTex = new THREE.CanvasTexture(c);
    }
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.16).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ map: this._kontaktTex, transparent: true, depthWrite: false }));
    m.renderOrder = 1;
    m.raycast = () => {};
    return m;
  }

  setEnten(liste) {
    if (!this.enten) this.enten = new Map();
    const da = new Set();
    for (const st of liste || []) {
      da.add(st.id);
      let e = this.enten.get(st.id);
      // Gäste sehen aus wie die Hauptente (seit 0.38.10): lädt das Originalmodell erst später, wechseln sie mit
      const echt = !!(this.realDuck && this.duck === this.realDuck);
      if (e && e._echt !== echt) { this.scene.remove(e.root, e._schatten); this.enten.delete(st.id); e = null; }
      if (!e) {
        e = echt ? new RealDuck(this._modell) : new Duck();
        e._echt = echt;
        // Gäste bekommen zufällig eine von Pollens vier Farben (seit 0.38.24, Wunsch: „andere Enten können immer
        // zufällig die Farben bekommen, meine möchte ich wählen können“) – je Gast fest, solange die App läuft
        if (!this._gastFarben) this._gastFarben = new Map();
        if (!this._gastFarben.has(st.id)) {
          // zufällig, aber erst die Farben, die im Zimmer noch selten sind (eigene Ente mitgezählt)
          const zahl = Object.fromEntries(Object.keys(FARBEN).map((n) => [n, 0]));
          zahl[this.farbe || 'cream'] += 1;
          for (const [id, f] of this._gastFarben) if (this.enten.has(id)) zahl[f] += 1;
          const wenig = Math.min(...Object.values(zahl));
          const frei = Object.keys(zahl).filter((n) => zahl[n] === wenig);
          this._gastFarben.set(st.id, frei[Math.floor(Math.random() * frei.length)]);
        }
        e.setFarbe?.(this._gastFarben.get(st.id));
        e._schatten = this._kontaktSchatten();
        this.scene.add(e.root, e._schatten);
        this.enten.set(st.id, e);
      }
      e._st = st;
    }
    for (const [id, e] of this.enten) {
      if (!da.has(id)) { this.scene.remove(e.root, e._schatten); this.enten.delete(id); }
    }
  }

  _entenZeichnen(dt) {
    if (!this.enten) return;
    for (const e of this.enten.values()) {
      if (!e._st) continue;
      e.update(e._st, dt);
      e._schatten.position.set(e._st.x, 0.0015, -e._st.y);
      e._schatten.rotation.y = e._st.yaw || 0;
      e._schatten.visible = !e._st.fallen;
    }
  }

  _frame() {
    const now = performance.now();
    const dt = Math.min(0.1, (now - this._last) / 1000);
    this._last = now;
    const st = this.state;
    if (st) {
      if ((st.koerper || 'microduck') !== this.koerper) { this.koerper = st.koerper || 'microduck'; this._figurWaehlen(); }
      this.duck.update(this.lage.glaetten(st, dt), dt);
      this._waendeAusrichten?.(this.camera);
      this._entenZeichnen(dt);
      this._auswahlZeichnen(now);
      for (const mesh of this.items.values()) {
        const it = mesh.userData.item;
        if (it.held) {
          const p = new THREE.Vector3();
          // seit 0.37.4 tragen auch die weiteren Enten Dinge – am eigenen Schnabel
          const tr = it.traeger && it.traeger !== 'haupt' && this.enten ? this.enten.get(it.traeger) : null;
          if (tr && tr.beakTip) tr.beakTip.getWorldPosition(p);
          else if (tr && tr._st) p.set(tr._st.x + 0.13 * Math.cos(tr._st.yaw), 0.1, -(tr._st.y + 0.13 * Math.sin(tr._st.yaw)));
          else this.duck.beakTip.getWorldPosition(p);
          imSchnabel(mesh, it, p, (tr ? tr._st && tr._st.yaw : st.yaw) || 0);
        } else {
          if (mesh.userData.getragen) {
            mesh.userData.getragen = false;
            if (it.kind === 'sock') sockeLegen(mesh, it);
            else mesh.rotation.copy(mesh.userData.ruheDrehung);
          }
          mesh.position.set(it.x, it.kind === 'sock' ? 0 : it.kind === 'figur' ? 0 : it.kind === 'baustein' ? it.r * 0.6 : it.r, -it.y);
        }
      }
      this._updateRays(st);
      if (this.cloud) this.cloud.update();
      if (st.connected) this._pushTrail(st.x, -st.y);
      this.trail.visible = this.showTrail;
      // Zielmarke
      const ziel = this.engine && this.engine.ziel;
      this.target.visible = !!ziel;
      if (ziel) {
        this.target.position.set(ziel[0], 0, -ziel[1]);
        const k = (now / 900) % 1;
        this.target.userData.outer.scale.setScalar(1 + k * 0.8);
        this.target.userData.outer.material.opacity = 0.55 * (1 - k);
        this.target.rotation.y = now / 1400;
      }
      // Orte: sanftes Schweben, beim Auftauchen von oben einfallen
      for (const pin of this.pins.children) {
        const age = (now - pin.userData.born) / 600;
        const drop = REDUCED ? 0 : (1 - ease(age)) * 0.4;
        pin.children[1].position.y = 0.225 + drop + Math.sin(now / 700 + pin.position.x * 5) * 0.004;
        pin.children[3].position.y = 0.27 + drop;
      }
      // Effekte
      this.effects = this.effects.filter((e) => {
        e.t += dt;
        const k = e.t / e.life;
        if (e.feather) {
          e.feather.y -= dt * 0.55;                       // Schwerkraft, leicht wie eine Feder
          e.feather.multiplyScalar(1 - dt * 1.8);         // Luftwiderstand
          e.mesh.position.addScaledVector(e.feather, dt);
          e.mesh.position.x += Math.sin(e.t * 6 + e.spin) * dt * 0.05;  // trudeln
          e.mesh.position.y = Math.max(0.002, e.mesh.position.y);
          e.mesh.rotation.x += e.spin * dt; e.mesh.rotation.z += e.spin * 0.6 * dt;
          e.mesh.material.opacity = k < 0.7 ? 1 : 1 - (k - 0.7) / 0.3;
          if (k >= 1) { this.scene.remove(e.mesh); e.mesh.material.dispose(); return false; }
          return true;
        }
        e.mesh.scale.setScalar(1 + ease(k) * e.grow);
        e.mesh.material.opacity = 0.9 * (1 - k);
        if (k >= 1) { this.scene.remove(e.mesh); e.mesh.geometry.dispose(); e.mesh.material.dispose(); return false; }
        return true;
      });
      // Einflug beim Start
      const p = this.duck.root.position;
      if (this.intro && this.intro.zu && !this.intro.done) {
        // Anfahrt (Kamera-Spiele, seit 0.38.14): von der jetzigen Ansicht vor die Figur, Blick auf ihren Kopf
        this.intro.t += dt / this.intro.dauer;
        const k = ease(Math.min(1, this.intro.t));
        this.camera.position.lerpVectors(this.intro.von, this.intro.zu, k);
        this.controls.target.lerpVectors(this.intro.vonZiel, this.intro.ziel, k);
        this._lastDuckPos.copy(p);
        if (this.intro.t >= 1) this.intro.done = true;
      } else if (this.intro && !this.intro.done) {
        this.intro.t += dt / 2.2;
        const k = ease(this.intro.t);
        const from = new THREE.Vector3(p.x - 3.2, p.y + 2.6, p.z + 2.6);     // p.y: Reachy steht auf dem Tisch
        // Ende des Einflugs flacher und näher (seit 0.38.23, Hinweis „die Startperspektive bei Microduck ist ziemlich
        // steil von oben“ – auch bei Odi): etwa auf Augenhöhe eines Menschen am Boden, die Figur groß im Bild
        // Seit 0.38.25 nach Größe der Figur: Odi (gut 40 cm) etwas weiter weg und höher, Blick auf ihre Mitte
        const s = this._rahmenMass();
        const to = new THREE.Vector3(p.x - 0.92 * s, p.y + 0.3 * s, p.z - 0.42 * s);
        this.camera.position.lerpVectors(from, to, k);
        this.controls.target.set(p.x, p.y + this._figurHoehe() * 0.42, p.z);
        this._lastDuckPos.copy(p);
        if (this.intro.t >= 1) this.intro.done = true;
      } else if (this.follow) {
        const delta = p.clone().sub(this._lastDuckPos);
        if (delta.length() < 1) {
          this.camera.position.add(delta);
          this.controls.target.add(delta);
        }
        this._lastDuckPos.copy(p);
        this.controls.target.lerp(new THREE.Vector3(p.x, p.y + this._figurHoehe() * 0.36, p.z), Math.min(1, dt * 2));
      }
      this._kameraAusweichen(dt);
    }
    this.controls.update();
    // Schattenausschnitt des Hauptlichts folgt der Ente
    if (this.duck && this.duck.root) {
      const p = this.duck.root.position;
      this.key.target.position.set(p.x, 0, p.z);
      this.key.position.set(p.x + this.keyOffset.x, this.keyOffset.y, p.z + this.keyOffset.z);
    }
    if (this.gazeMark) this._updateGazeMark(now);
    if (this.personFig && this.personFig.visible) this._stellFuesse(this.personFig, performance.now());
    if (this.mode === 'entenblick' && this.duck) {
      // Entenblick: die ganze Bühne zeigt, was die Kopfkamera sieht
      const size = this.renderer.getSize(new THREE.Vector2());
      this.povCam.fov = 70;
      this._placePovCam(size.x / Math.max(1, size.y), dt);
      const rays = this.rays ? this.rays.visible : false;
      if (this.rays) this.rays.visible = false;
      this.renderer.render(this.scene, this.povCam);
      if (this.rays) this.rays.visible = rays;
    } else {
      if (this.useComposer) this.composer.render(dt);
      else this.renderer.render(this.scene, this.camera);
      if (this.showPov && this.duck) this._renderPov();
    }
    this._watchPerformance(dt * 1000);
  }
}
