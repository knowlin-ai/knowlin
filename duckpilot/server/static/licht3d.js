// Licht und Bildaufbereitung der 3D-Ansicht – einmal hier, damit App und Modell-Prüfung gleich aussehen.
import * as THREE from './vendor/three.module.min.js';
import { RoomEnvironment } from './vendor/jsm/environments/RoomEnvironment.js';

// Richtet Renderer und Szene ein und gibt das Hauptlicht zurück (sein Schattenausschnitt wandert mit der Figur).
export function studio(renderer, scene, hintergrund) {
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // Neutral (Khronos PBR Neutral) hält Pollens CAD-Farben farbtreu; ACES verschiebt Orange ins Gelbe.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.0;
  scene.background = new THREE.Color(hintergrund);
  // Umgebungslicht aus einem weichen Studio-Raum: Spiegelungen auf Schalen, Lack und Metall
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.75;
  pmrem.dispose();

  // Himmel kühl, Boden warm: das Licht, das von den Dielen zurückkommt (seit 0.38.18)
  scene.add(new THREE.HemisphereLight(0xe3e8ef, 0x4a3b2e, 0.55));
  // Hauptlicht: scharfe Schatten an Beinen und Füßen (Ausschnitt ±1,2 m um die Figur)
  const key = new THREE.DirectionalLight(0xfff1e0, 2.1);
  const keyOffset = new THREE.Vector3(1.2, 2.8, 0.9);
  key.position.copy(keyOffset);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -1.2, right: 1.2, top: 1.2, bottom: -1.2, near: 0.5, far: 6 });
  key.shadow.bias = -0.0002;
  key.shadow.normalBias = 0.0015;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(0x8fb6ff, 0.75);
  rim.position.set(-2.5, 1.2, -2.0);
  scene.add(rim);
  return { key, keyOffset };
}
