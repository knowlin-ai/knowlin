// Ins Wort fallen (seit 0.40, „Gespräch in Echtzeit“): Während Knowlin spricht, hört das Mikrofon mit. Sprichst du
// dazwischen, verstummt die Stimme sofort und Knowlin hört dir zu – wie in einem echten Gespräch.
//
// Nur, wenn du gerade mit der Stimme sprichst (nach getippten Befehlen bleibt das Mikrofon aus), nur am PC, abschaltbar
// (Einstellung „ins_wort_fallen“). Das Mikrofon läuft mit Echo-Unterdrückung; ausgewertet wird nur die Lautstärke hier
// im Browser – nichts wird aufgenommen oder verschickt. Die eigene Stimme aus den Lautsprechern soll nicht als
// Unterbrechung zählen: Die ersten 0,6 s lernt `Pegel` den Grundpegel (Echo, Raum), danach zählt erst, was deutlich
// lauter ist und eine Weile anhält.

export const LERNEN_MS = 600;       // so lange lernt der Pegel den Grundpegel (Echo der eigenen Stimme)
export const HALTEN_MS = 280;       // so lange muss es deutlich lauter sein
export const FAKTOR = 2.6;          // so viel lauter als der Grundpegel
export const MINDEST = 0.035;       // und nie unter dieser Lautstärke (RMS 0 … 1)

// Reine Rechnung, ohne Browser: Lautstärke-Messungen (RMS) mit Zeit → true, sobald jemand dazwischenspricht
export class Pegel {
  constructor() { this.t0 = null; this.grund = 0; this.n = 0; this.seit = null; }

  schritt(rms, t) {
    if (this.t0 === null) this.t0 = t;
    if (t - this.t0 < LERNEN_MS) {               // Grundpegel: gleitendes Maximum der ruhigen Messungen
      this.n += 1;
      this.grund = Math.max(this.grund * 0.9, rms);
      return false;
    }
    const schwelle = Math.max(MINDEST, this.grund * FAKTOR);
    if (rms > schwelle) {
      if (this.seit === null) this.seit = t;
      return t - this.seit >= HALTEN_MS;
    }
    this.seit = null;
    this.grund = this.grund * 0.995 + rms * 0.005;   // Raum ändert sich langsam
    return false;
  }
}

export function rms(daten) {
  let s = 0;
  for (let i = 0; i < daten.length; i++) { const v = (daten[i] - 128) / 128; s += v * v; }
  return Math.sqrt(s / Math.max(1, daten.length));
}

// Im Browser: Mikrofon mit Echo-Unterdrückung, alle 50 ms ein Pegel; `beimDazwischen` einmal je Sprechen
export class Unterbrecher {
  constructor() { this.stream = null; this.ctx = null; this.timer = 0; this.an = false; }

  async start(beimDazwischen) {
    this.stop();
    if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) return false;
    this.an = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true,
        autoGainControl: false } });
      if (!this.an) { stream.getTracks().forEach((t) => t.stop()); return false; }
      this.stream = stream;
      this.ctx = new AudioContext();
      const quelle = this.ctx.createMediaStreamSource(stream);
      const analyse = this.ctx.createAnalyser();
      analyse.fftSize = 1024;
      quelle.connect(analyse);
      const daten = new Uint8Array(analyse.fftSize);
      const pegel = new Pegel();
      this.timer = setInterval(() => {
        analyse.getByteTimeDomainData(daten);
        if (pegel.schritt(rms(daten), performance.now())) { this.stop(); beimDazwischen(); }
      }, 50);
      return true;
    } catch {
      this.an = false;
      return false;
    }
  }

  stop() {
    this.an = false;
    clearInterval(this.timer);
    this.timer = 0;
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.ctx) this.ctx.close().catch(() => {});
    this.ctx = null;
  }
}
