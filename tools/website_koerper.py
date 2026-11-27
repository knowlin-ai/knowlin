"""Eine Seite je Körper auf knowlin.de (seit 0.52.1, Maintainer: „mache weiter SEO-Optimierung“).

Wer „Microduck App“ oder „Reachy Mini Simulator“ sucht, landet sonst auf der allgemeinen Startseite – oder gar nicht.
Jede Seite hat eine Sprache, eine eigene Adresse (`/microduck/`, `/en/microduck/`), Titel, Beschreibung, hreflang und
strukturierte Daten (Brotkrumen). Inhalt nur, was Knowlin wirklich kann – am echten Roboter Ungeprüftes steht als solches da.
Pfade sind absolut (`/bilder/…`), weil die Seiten eine bzw. zwei Ebenen tief liegen.
"""

from __future__ import annotations

import html
import json
import re

ADRESSE = "https://knowlin.de/"

# slug, Bild, Pollens Modell (Bildnachweis CC BY-NC-SA), Hersteller-Links, de, en
KOERPER: tuple[dict, ...] = (
    {"slug": "microduck", "mit": "der Microduck", "ueber": "die Microduck", "bild": "cockpit", "pollen": True, "name": "Microduck",
     "links": (("Pollen Robotics: Microduck", "https://pollen-robotics.com/microduck/"),
               ("GitHub: pollen-robotics/microduck", "https://github.com/pollen-robotics/microduck")),
     "de": {"titel": "Microduck-App und Simulator – Knowlin",
            "beschreibung": "Knowlin ist die freie Begleit-App für Pollens Microduck: im Simulator mit echter Physik "
                            "ausprobieren, per Sprache steuern, Tänze bauen, Duck Cards lesen.",
            "h1": "Knowlin für die Microduck",
            "lead": "Die Microduck von Pollen Robotics und Hugging Face läuft, tanzt, schießt den Ball und hebt Dinge auf. "
                    "Mit Knowlin probierst du das schon heute am PC aus – im Simulator mit echter Physik und Pollens "
                    "eigenen Bewegungs-Policies – und schaltest später auf die echte Ente um.",
            "kann": ("Sprechen und steuern: mit Claude, einem lokalen Modell oder ganz ohne KI",
                     "Tänze auf einer Zeitleiste bauen und zur Musik proben",
                     "Ablauf-Baukasten und Duck Cards – gedruckte Karten per Webcam lesen",
                     "Zubehör im Simulator: Rollen, Arena-Rennen, Polaroid",
                     "Gangarten trainieren und Pollens Policies vergleichen",
                     "Am echten Roboter: Roboter-Pflege mit Akku, Lautstärke, Fotos und Updates über Pollens robotd"),
            "stand": "Im Simulator fertig. Der echte Roboter ist angebunden (Pollens Protokoll 68), aber erst ab der "
                     "ersten Lieferung geprüft."},
     "en": {"titel": "Microduck app and simulator – Knowlin",
            "beschreibung": "Knowlin is the free companion app for Pollen's Microduck: try it in a physics simulator, "
                            "control it by voice, build dances, read Duck Cards.",
            "h1": "Knowlin for the Microduck",
            "lead": "Pollen Robotics' and Hugging Face's Microduck walks, dances, kicks the ball and picks things up. "
                    "With Knowlin you can try all that on your PC today – in a simulator with real physics and Pollen's "
                    "own motion policies – and switch to the real duck later.",
            "kann": ("Talk and control: with Claude, a local model or no AI at all",
                     "Build dances on a timeline and rehearse them to music",
                     "Sequence builder and Duck Cards – read printed cards with your webcam",
                     "Accessories in the simulator: rollers, arena race, Polaroid",
                     "Train gaits and compare them with Pollen's policies",
                     "On the real robot: robot care with battery, volume, photos and updates via Pollen's robotd"),
            "stand": "Ready in the simulator. The real robot is connected (Pollen's protocol 68) but only tested from the "
                     "first deliveries on."}},
    {"slug": "reachy-mini", "mit": "Reachy Mini", "ueber": "Reachy Mini", "bild": "reachy", "pollen": True, "name": "Reachy Mini",
     "links": (("Pollen Robotics: Reachy Mini", "https://pollen-robotics.com/reachy-mini/"),
               ("GitHub: pollen-robotics/reachy_mini", "https://github.com/pollen-robotics/reachy_mini")),
     "de": {"titel": "Reachy Mini App und Simulator – Knowlin",
            "beschreibung": "Knowlin gibt Reachy Mini einen Kopf mit Gedächtnis: im Simulator ausprobieren, Pollens "
                            "Emotionen und Tänze, Apps per Klick, per Sprache steuern.",
            "h1": "Knowlin für Reachy Mini",
            "lead": "Reachy Mini hat einen Kopf mit sechs Freiheitsgraden, Antennen und einen drehbaren Körper. Knowlin "
                    "bringt Pollens Emotionen und Tänze mit, startet Pollens Apps per Klick und spricht mit dir – "
                    "mit einer Stimme und einem Gedächtnis, das alle Körper teilen.",
            "kann": ("Pollens Emotionen und Tänze, im Simulator auf dem Couchtisch",
                     "Pollens Apps aus dem Katalog per Klick installieren und starten",
                     "Kamera-Spiele, die nur im Browser rechnen",
                     "Den Kopf wie eine Marionette führen – mit Maus, Handy oder Quest",
                     "Sprechen mit Claude, einem lokalen Modell oder ohne KI"),
            "stand": "Im Simulator fertig. Der echte Reachy Mini ist über Pollens Daemon angebunden, aber noch ungetestet."},
     "en": {"titel": "Reachy Mini app and simulator – Knowlin",
            "beschreibung": "Knowlin gives Reachy Mini a mind with memory: try it in a simulator, Pollen's emotions and "
                            "dances, apps in one click, voice control.",
            "h1": "Knowlin for Reachy Mini",
            "lead": "Reachy Mini has a head with six degrees of freedom, antennas and a rotating body. Knowlin brings "
                    "Pollen's emotions and dances, starts Pollen's apps in one click and talks with you – with a voice "
                    "and a memory that all bodies share.",
            "kann": ("Pollen's emotions and dances, in the simulator on the coffee table",
                     "Install and start Pollen's apps from the catalog in one click",
                     "Camera games that run only in your browser",
                     "Guide the head like a marionette – with mouse, phone or Quest",
                     "Talk with Claude, a local model or no AI"),
            "stand": "Ready in the simulator. The real Reachy Mini is connected via Pollen's daemon but not yet tested."}},
    {"slug": "open-duck-mini", "mit": "der Open Duck Mini", "ueber": "die Open Duck Mini", "bild": "odi", "pollen": False, "name": "Open Duck Mini",
     "links": (("GitHub: apirrone/Open_Duck_Mini", "https://github.com/apirrone/Open_Duck_Mini"),),
     "de": {"titel": "Open Duck Mini Simulator und App – Knowlin",
            "beschreibung": "Knowlin simuliert die Open Duck Mini v2 mit ihrem offenen Modell: tanzen, per Sprache "
                            "steuern und Gangarten trainieren – frei und quelloffen.",
            "h1": "Knowlin für die Open Duck Mini",
            "lead": "Die Open Duck Mini v2 ist der offene Vorgänger der Microduck zum Nachbauen, rund 42 cm groß. Knowlin "
                    "simuliert sie mit ihrem offenen 3D-Modell – zum Ausprobieren, bevor der Drucker läuft.",
            "kann": ("Laufen, tanzen und Tricks im Simulator", "Per Sprache steuern, mit oder ohne KI",
                     "Gangarten trainieren und vergleichen", "Mit anderen Enten im Team spielen"),
            "stand": "Im Simulator fertig. Die Anbindung einer gebauten Ente ist geplant."},
     "en": {"titel": "Open Duck Mini simulator and app – Knowlin",
            "beschreibung": "Knowlin simulates the Open Duck Mini v2 with its open model: dance, control it by voice and "
                            "train gaits – free and open source.",
            "h1": "Knowlin for the Open Duck Mini",
            "lead": "The Open Duck Mini v2 is the Microduck's open predecessor to build yourself, about 42 cm tall. Knowlin "
                    "simulates it with its open 3D model – to try out before the printer starts.",
            "kann": ("Walk, dance and do tricks in the simulator", "Control it by voice, with or without AI",
                     "Train and compare gaits", "Play as a team with other ducks"),
            "stand": "Ready in the simulator. Connecting a built duck is planned."}},
    {"slug": "wonderduck", "mit": "der WonderDuck", "ueber": "die WonderDuck", "bild": "wonderduck", "pollen": False,
     "hiwonder": True, "name": "WonderDuck",
     "links": (("Hiwonder: WonderDuck", "https://www.hiwonder.com/products/wonderduck"),
               ("GitHub: Hiwonder/wonderduck", "https://github.com/Hiwonder/wonderduck")),
     "de": {"titel": "WonderDuck Simulator und App – Knowlin",
            "beschreibung": "Knowlin simuliert Hiwonders WonderDuck mit ihrem 3D-Modell: laufen, schießen, Kopfstand, mit "
                            "dem Schnabel greifen, per Sprache steuern – frei und quelloffen.",
            "h1": "Knowlin für die WonderDuck",
            "lead": "Die WonderDuck von Hiwonder ist eine zweibeinige Ente mit 15 Gelenken, Kamera und Schnabel. Ihre "
                    "Software baut auf Pollens Microduck auf – deshalb kann Knowlin sie fast wie die Microduck steuern. "
                    "In Knowlin heißt sie Wondi.",
            "kann": ("Laufen, sitzen und mit dem Schnabel greifen im Simulator, mit Hiwonders 3D-Modell",
                     "Ball schießen und Kopfstand – wie Hiwonders eigene Bewegungen",
                     "In Hiwonders vier Farben: Gelb, Blau, Schwarz, Weiß",
                     "Selbstständig: einer Linie oder Farbe folgen, dir folgen, ausweichen, Dinge tragen",
                     "Sprechen und steuern: mit Claude, einem lokalen Modell oder ganz ohne KI",
                     "Tänze auf der Zeitleiste und Ablauf-Baukasten wie bei der Microduck",
                     "Am echten Roboter: über Hiwonders robotd, den Verbindungstest und die Roboter-Pflege"),
            "stand": "Im Simulator fertig. Die echte WonderDuck spricht dasselbe Protokoll wie die Microduck, ist aber "
                     "noch ungetestet; Fotos und Lautstärke kennt ihre Software noch nicht."},
     "en": {"titel": "WonderDuck simulator and app – Knowlin",
            "beschreibung": "Knowlin simulates Hiwonder's WonderDuck with its 3D model: walk, kick, headstand, grab with "
                            "the beak, control it by voice – free and open source.",
            "h1": "Knowlin for the WonderDuck",
            "lead": "Hiwonder's WonderDuck is a two-legged duck with 15 joints, a camera and a beak. Its software builds on "
                    "Pollen's Microduck – so Knowlin can control it almost like the Microduck. In Knowlin it is called Wondi.",
            "kann": ("Walk, sit and grab with the beak in the simulator, with Hiwonder's 3D model",
                     "Kick the ball and do a headstand – like Hiwonder's own moves",
                     "In Hiwonder's four colours: yellow, blue, black, white",
                     "On its own: follow a line or a colour, follow you, avoid obstacles, carry things",
                     "Talk and control: with Claude, a local model or no AI at all",
                     "Dances on the timeline and the sequence builder, as with the Microduck",
                     "On the real robot: via Hiwonder's robotd, the connection test and robot care"),
            "stand": "Ready in the simulator. The real WonderDuck speaks the same protocol as the Microduck but is not yet "
                     "tested; its software doesn't know photos and volume yet."}},
    {"slug": "so-101", "mit": "dem SO-101", "ueber": "den SO-101", "bild": "ari", "pollen": False, "name": "SO-101",
     "links": (("GitHub: TheRobotStudio/SO-ARM100", "https://github.com/TheRobotStudio/SO-ARM100"),
               ("GitHub: huggingface/lerobot", "https://github.com/huggingface/lerobot")),
     "de": {"titel": "SO-101 Simulator mit Werkbank – Knowlin",
            "beschreibung": "Knowlin simuliert den SO-101-Arm an einer Werkbank: sortieren, Türme bauen, Tic-Tac-Toe, "
                            "durch Vormachen lernen und für LeRobot exportieren.",
            "h1": "Knowlin für den SO-101",
            "lead": "Der SO-101 ist ein offener Greifarm mit sechs Gelenken aus Hugging Faces LeRobot-Welt. In Knowlin "
                    "heißt er Ari, steht an seiner eigenen Werkbank und grüßt mit Winken statt Nicken.",
            "kann": ("Würfel nach Farben sortieren, Türme bauen, aufräumen", "Tic-Tac-Toe mit dir spielen",
                     "Durch Vormachen lernen – mit der Hand vor der Webcam",
                     "Beispiele als Datensatz für LeRobot exportieren", "Aufträge in Worten geben"),
            "stand": "Im Simulator fertig. Der echte Arm ist über LeRobot angebunden, aber noch ungetestet."},
     "en": {"titel": "SO-101 simulator with workbench – Knowlin",
            "beschreibung": "Knowlin simulates the SO-101 arm at a workbench: sort, build towers, play tic-tac-toe, learn "
                            "by demonstration and export for LeRobot.",
            "h1": "Knowlin for the SO-101",
            "lead": "The SO-101 is an open gripper arm with six joints from Hugging Face's LeRobot world. In Knowlin it is "
                    "called Ari, stands at its own workbench and greets with a wave instead of a nod.",
            "kann": ("Sort cubes by colour, build towers, tidy up", "Play tic-tac-toe with you",
                     "Learn by demonstration – with your hand in front of the webcam",
                     "Export examples as a dataset for LeRobot", "Give tasks in plain words"),
            "stand": "Ready in the simulator. The real arm is connected via LeRobot but not yet tested."}},
    {"slug": "stack-chan", "mit": "Stack-chan", "ueber": "Stack-chan", "bild": "stackchan", "pollen": False, "name": "Stack-chan",
     "links": (("GitHub: stack-chan/stack-chan", "https://github.com/stack-chan/stack-chan"),),
     "de": {"titel": "Stack-chan Simulator und App – Knowlin",
            "beschreibung": "Knowlin simuliert Stack-chan mit Bildschirmgesicht: Gefühle zeigen, sprechen, dir mit dem "
                            "Kopf folgen – frei und quelloffen.",
            "h1": "Knowlin für Stack-chan",
            "lead": "Stack-chan ist ein kleiner Schreibtisch-Roboter der Community mit einem Gesicht auf dem Bildschirm. "
                    "In Knowlin heißt er Stacki: Er dreht und nickt mit dem Kopf, zeigt Gefühle mit Augen und Mund und "
                    "bewegt beim Sprechen den Mund.",
            "kann": ("Gefühle mit Augen und Mund, verschiedene Gesichter", "Mit dem Kopf deinem Gesicht vor der Webcam folgen",
                     "LEDs im Takt der Musik", "Sprechen mit Claude, einem lokalen Modell oder ohne KI"),
            "stand": "Im Simulator fertig. Die Anbindung eines echten Stack-chan ist geplant."},
     "en": {"titel": "Stack-chan simulator and app – Knowlin",
            "beschreibung": "Knowlin simulates Stack-chan with its screen face: show feelings, talk, follow you with its "
                            "head – free and open source.",
            "h1": "Knowlin for Stack-chan",
            "lead": "Stack-chan is the community's small desktop robot with a face on a screen. In Knowlin it is called "
                    "Stacki: it turns and nods its head, shows feelings with eyes and mouth and moves its mouth while talking.",
            "kann": ("Feelings with eyes and mouth, several faces", "Follow your face in front of the webcam with its head",
                     "LEDs to the beat of the music", "Talk with Claude, a local model or no AI"),
            "stand": "Ready in the simulator. Connecting a real Stack-chan is planned."}},
    {"slug": "bittle-x", "mit": "Bittle X", "ueber": "Bittle X", "bild": "bittle", "pollen": False, "name": "Bittle X",
     "links": (("Petoi: Bittle", "https://www.petoi.com/pages/bittle-open-source-bionic-robot-dog"),
               ("GitHub: PetoiCamp/OpenCat", "https://github.com/PetoiCamp/OpenCat")),
     "de": {"titel": "Bittle X Simulator und App – Knowlin",
            "beschreibung": "Knowlin simuliert Petois Roboterhund Bittle X: krabbeln, traben, 28 Tricks, per Sprache "
                            "steuern – frei und quelloffen.",
            "h1": "Knowlin für Bittle X",
            "lead": "Bittle X von Petoi ist ein kleiner Roboterhund mit vier Beinen und neun Gelenken. In Knowlin heißt er "
                    "Bello: Er krabbelt, trabt oder hoppelt, gibt Pfote, macht Männchen und Moonwalk – und Knowlin "
                    "spricht für ihn.",
            "kann": ("Gangarten: krabbeln, traben, hoppeln", "28 Tricks nach Petois Vorbild",
                     "Per Sprache steuern, auch ohne KI", "Laufen lernen im Physik-Simulator"),
            "stand": "Im Simulator fertig. Die Anbindung über Petois serielles Protokoll ist geplant."},
     "en": {"titel": "Bittle X simulator and app – Knowlin",
            "beschreibung": "Knowlin simulates Petoi's robot dog Bittle X: crawl, trot, 28 tricks, voice control – free "
                            "and open source.",
            "h1": "Knowlin for Bittle X",
            "lead": "Petoi's Bittle X is a small robot dog with four legs and nine joints. In Knowlin it is called Bello: "
                    "it crawls, trots or bounds, gives paw, sits up and moonwalks – and Knowlin speaks for it.",
            "kann": ("Gaits: crawl, trot, bound", "28 tricks modelled on Petoi's",
                     "Voice control, even without AI", "Learn to walk in the physics simulator"),
            "stand": "Ready in the simulator. Connecting via Petoi's serial protocol is planned."}},
)

WORTE = {
    "de": {"start": "Zur Startseite", "kann": "Was Knowlin mit {mit} kann", "stand": "Stand", "laden": "Knowlin laden",
           "code": "Quelltext auf GitHub", "mehr": "Mehr über {ueber}", "andere": "Weitere Körper",
           "frei": "Frei und quelloffen (Apache-2.0), für Windows, macOS und Linux. Ein Hobbyprojekt, nicht von den Herstellern.",
           "nachweis": "Bild: Knowlin mit dem 3D-Modell – © Pollen Robotics, CC BY-NC-SA 4.0.",
           "nachweis_hiwonder": "Bild: Knowlin mit dem 3D-Modell der WonderDuck – © Hiwonder, CC BY-NC-SA 4.0.",
           "sprung": "Zum Inhalt springen", "alt": "{name} in Knowlins Simulator, daneben das Gespräch"},
    "en": {"start": "Back to the start page", "kann": "What Knowlin does with {name}", "stand": "Status",
           "laden": "Download Knowlin", "code": "Source code on GitHub", "mehr": "More about {name}",
           "andere": "Other bodies",
           "frei": "Free and open source (Apache-2.0), for Windows, macOS and Linux. A hobby project, not by the makers.",
           "nachweis": "Image: Knowlin with the 3D model – © Pollen Robotics, CC BY-NC-SA 4.0.",
           "nachweis_hiwonder": "Image: Knowlin with the WonderDuck 3D model – © Hiwonder, CC BY-NC-SA 4.0.",
           "sprung": "Skip to content", "alt": "{name} in Knowlin's simulator, with the conversation next to it"},
}


# ── Kopfleiste mit Menü (seit 26.11., Maintainer: „wieso gibt es … bei Körper keine Dropdowns?“) ─────────────────
# Dieselbe Leiste auf der Startseite (zweisprachig über .t-Spannen, Links relativ) und auf jeder Körper-Seite (eine
# Sprache, Links absolut). Am Handy klappt „Menü“ sie auf; „Körper“ ist ein <details> mit allen Körper-Seiten.
# Seit 0.53 nach Art geordnet – wie die Reiter auf der Startseite
GRUPPEN = (("Enten", "Ducks", ("microduck", "wonderduck", "open-duck-mini")),
           ("Köpfe", "Heads", ("reachy-mini", "stack-chan")),
           ("Arm & Hund", "Arm & dog", ("so-101", "bittle-x")))
MENUE = (("idee", "Idee", "Idea"), ("koerper", "Körper", "Bodies"), ("funktionen", "Funktionen", "Features"),
         ("sicherheit", "Sicherheit", "Safety"), ("fahrplan", "Fahrplan", "Roadmap"), ("loslegen", "Loslegen", "Get started"))


def _t(de: str, en: str, sprache: str | None) -> str:
    if sprache is None:
        return f'<span class="t" lang="de">{html.escape(de)}</span><span class="t" lang="en">{html.escape(en)}</span>'
    return html.escape(de if sprache == "de" else en)


def navigation(sprache: str | None = None, aktuell: str | None = None) -> str:
    """Knopf „Menü“ (nur am Handy) und die Navigation. `sprache=None`: Startseite (beide Sprachen, relative Links)."""
    basis = "" if sprache is None else ("/en/" if sprache == "en" else "/")
    teile = []
    for anker, de, en in MENUE:
        if anker != "koerper":
            teile.append(f'<a href="{basis}#{anker}">{_t(de, en, sprache)}</a>')
            continue
        eintraege = [f'<li><a href="{basis}#koerper">{_t("Alle im Überblick", "All at a glance", sprache)}</a></li>']
        nach_slug = {k["slug"]: k for k in KOERPER}
        for gde, gen, slugs in GRUPPEN:
            eintraege.append(f'<li class="menue-gruppe">{_t(gde, gen, sprache)}</li>')
            for slug in slugs:
                cur = ' aria-current="page"' if slug == aktuell else ""
                eintraege.append(f'<li><a href="{basis}{slug}/"{cur}>{html.escape(nach_slug[slug]["name"])}</a></li>')
        teile.append(f'<details class="menue-koerper"><summary{" data-hier" if aktuell else ""}>{_t(de, en, sprache)}</summary>'
                     f'<ul>{"".join(eintraege)}</ul></details>')
    label = "Seite" if sprache != "en" else "Site"
    return (f'<nav class="navi" id="navi" aria-label="{label}">{"".join(teile)}</nav>'
            f'<button type="button" class="menue-knopf" aria-expanded="false" aria-controls="navi">'
            f'{_t("Menü", "Menu", sprache)}</button>')


MENUE_JS = """<script>
(() => {   // Menü am Handy auf und zu, „Körper“ schließt bei Klick daneben oder Esc
  const knopf = document.querySelector('.menue-knopf'), navi = document.getElementById('navi');
  const liste = document.querySelector('.menue-koerper');
  if (!knopf || !navi) return;
  const zu = () => { navi.classList.remove('offen'); knopf.setAttribute('aria-expanded', 'false'); };
  knopf.addEventListener('click', () => {
    const auf = !navi.classList.contains('offen');
    navi.classList.toggle('offen', auf);
    knopf.setAttribute('aria-expanded', String(auf));
  });
  navi.addEventListener('click', (e) => { if (e.target.closest('a')) { zu(); if (liste) liste.open = false; } });
  document.addEventListener('click', (e) => {
    if (liste && !e.target.closest('.menue-koerper')) liste.open = false;
    if (!e.target.closest('.leiste')) zu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (liste && liste.open) { liste.open = false; liste.querySelector('summary').focus(); }
    else if (navi.classList.contains('offen')) { zu(); knopf.focus(); }
  });
})();
</script>"""


def adresse(slug: str, sprache: str) -> str:
    return f"{ADRESSE}{'en/' if sprache == 'en' else ''}{slug}/"


def pfade() -> list[str]:
    """Alle Seiten relativ zur Wurzel (für bauen und die Prüfung)."""
    return [f"{'en/' if s == 'en' else ''}{k['slug']}/index.html" for k in KOERPER for s in ("de", "en")]


def _daten(k: dict, sprache: str) -> str:
    t = k[sprache]
    start = ADRESSE + ("en/" if sprache == "en" else "")
    return json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "url": adresse(k["slug"], sprache), "name": t["titel"], "description": t["beschreibung"],
         "inLanguage": sprache, "about": {"@type": "Product", "name": k["name"]},
         "isPartOf": {"@type": "WebSite", "name": "Knowlin", "url": ADRESSE}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Knowlin", "item": start},
            {"@type": "ListItem", "position": 2, "name": k["name"], "item": adresse(k["slug"], sprache)}]}]},
        ensure_ascii=False)


def seite(k: dict, sprache: str, stil: str, fuss: str, download: str) -> str:
    """Eine Körper-Seite. `stil` ist der <style>-Block der Startseite, `fuss` ihre Fußzeile (beide aus website.py)."""
    t, w, slug = k[sprache], WORTE[sprache], k["slug"]
    e = html.escape
    start = "/en/" if sprache == "en" else "/"
    bild = f"/bilder/{k['bild']}-{sprache}"
    stil = stil.replace('url("schrift/', 'url("/schrift/').replace("url(schrift/", "url(/schrift/")
    fuss = (fuss.replace('href="impressum.html"', 'href="/impressum.html"')
            .replace('href="datenschutz.html"', 'href="/datenschutz.html"').replace('href="./"', f'href="{start}"'))
    kann = "\n".join(f"<li>{e(z)}</li>" for z in t["kann"])
    links = "\n".join(f'<li><a href="{u}" rel="noopener">{e(n)}</a></li>' for n, u in k["links"])
    weitere = "\n".join(f'<li><a href="{start}{o["slug"]}/">{e(o["name"])}</a></li>' for o in KOERPER if o is not k)
    nachweis = (f'<p class="recht-stand">{e(w["nachweis"])}</p>' if k["pollen"] else
                f'<p class="recht-stand">{e(w["nachweis_hiwonder"])}</p>' if k.get("hiwonder") else "")
    return f"""<!doctype html>
<html lang="{sprache}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>{e(t["titel"])}</title>
<meta name="description" content="{e(t["beschreibung"])}">
<link rel="canonical" href="{adresse(slug, sprache)}">
<link rel="alternate" hreflang="de" href="{adresse(slug, "de")}">
<link rel="alternate" hreflang="en" href="{adresse(slug, "en")}">
<link rel="alternate" hreflang="x-default" href="{adresse(slug, "de")}">
<meta property="og:type" content="website">
<meta property="og:url" content="{adresse(slug, sprache)}">
<meta property="og:title" content="{e(t["titel"])}">
<meta property="og:description" content="{e(t["beschreibung"])}">
<meta property="og:image" content="{ADRESSE}bilder/{k["bild"]}-{sprache}-1600.webp">
<meta property="og:site_name" content="Knowlin">
<meta property="og:locale" content="{"en_US" if sprache == "en" else "de_DE"}">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{_daten(k, sprache)}</script>
<link rel="icon" href="/favicon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{stil}
</head>
<body>
<a class="sprung" href="#titel">{e(w["sprung"])}</a>
<header class="leiste"><div class="huelle">
<a class="marke" href="{start}" aria-label="Knowlin"><img src="/bilder/zeichen-64.webp" alt="" width="30" height="30">Knowlin</a>
{navigation(sprache, slug)}
<nav class="sprache koerper-sprache" aria-label="Sprache · Language">
<a href="{adresse(slug, "de").removeprefix(ADRESSE[:-1])}" hreflang="de" lang="de"{' aria-current="page"' if sprache == "de" else ""}>DE</a>
<a href="{adresse(slug, "en").removeprefix(ADRESSE[:-1])}" hreflang="en" lang="en"{' aria-current="page"' if sprache == "en" else ""}>EN</a>
</nav>
</div></header>
<main class="huelle recht koerper-seite">
<h1 id="titel" tabindex="-1">{e(t["h1"])}</h1>
<p class="kurz">{e(t["lead"])}</p>
<figure class="koerper-bild"><img src="{bild}-1600.webp" srcset="{bild}-900.webp 900w, {bild}-1600.webp 1600w" sizes="(max-width: 860px) 100vw, 760px" width="1600" height="965" alt="{e(w["alt"].format(name=k["name"]))}"></figure>
{nachweis}
<h2>{e(w["kann"].format(name=k["name"], mit=k["mit"]))}</h2>
<ul>
{kann}
</ul>
<h2>{e(w["stand"])}</h2>
<p>{e(t["stand"])}</p>
<p class="koerper-knoepfe"><a class="knopf knopf--voll" href="{download}">{e(w["laden"])}</a>
<a class="knopf knopf--rand" href="https://github.com/knowlin-ai/knowlin" rel="noopener">{e(w["code"])}</a></p>
<p>{e(w["frei"])}</p>
<h2>{e(w["mehr"].format(name=k["name"], ueber=k["ueber"]))}</h2>
<ul>
{links}
</ul>
<h2>{e(w["andere"])}</h2>
<ul class="koerper-weitere">
{weitere}
</ul>
</main>
{fuss}
{MENUE_JS}
</body>
</html>
"""


ZUSATZ_STIL = """<style>
.koerper-sprache { display: flex; gap: 4px; border: 1px solid rgb(255 255 255 / 0.16); border-radius: var(--r-knopf); padding: 3px; }
.koerper-sprache a { display: inline-flex; align-items: center; justify-content: center; min-width: 40px; min-height: 30px; border-radius: var(--r-knopf); color: #a2a9b3; text-decoration: none; font: 600 0.8125rem/1 var(--schrift-text); }
.koerper-sprache a[aria-current="page"] { background: #f3f4f6; color: #07080a; }
.koerper-seite ul { padding-left: 1.25rem; display: grid; gap: 6px; }
.koerper-bild { margin: 28px 0 8px; }
.koerper-bild img { width: 100%; height: auto; border-radius: 12px; display: block; }
.koerper-knoepfe { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 12px; }
.koerper-seite a.knopf--voll { color: var(--auf-akzent); text-decoration: none; }
.koerper-seite a.knopf--rand { color: var(--tinte); text-decoration: none; }
.koerper-seite .koerper-weitere { list-style: none; padding-left: 0; display: flex; flex-wrap: wrap; gap: 8px 24px; }
</style>"""


def alle(stil: str, fuss: str, download: str) -> dict[str, str]:
    """Pfad → HTML für alle Körper-Seiten."""
    stil = stil + "\n" + ZUSATZ_STIL
    out = {}
    for k in KOERPER:
        for sprache in ("de", "en"):
            out[f"{'en/' if sprache == 'en' else ''}{k['slug']}/index.html"] = seite(k, sprache, stil, fuss, download)
    return out


def sitemap_eintraege(tag: str) -> str:
    zeilen = []
    for k in KOERPER:
        paar = "".join(f'<xhtml:link rel="alternate" hreflang="{s}" href="{adresse(k["slug"], s)}"/>' for s in ("de", "en"))
        for s in ("de", "en"):
            zeilen.append(f"  <url><loc>{adresse(k['slug'], s)}</loc><lastmod>{tag}</lastmod>{paar}</url>\n")
    return "".join(zeilen)


assert all(re.fullmatch(r"[a-z0-9-]+", k["slug"]) for k in KOERPER)


assert sorted(s for _, _, slugs in GRUPPEN for s in slugs) == sorted(k["slug"] for k in KOERPER)
