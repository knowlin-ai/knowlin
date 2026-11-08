"""Enten-Erkenner: Pollens YOLO-Modell findet andere Microducks im Kamerabild des echten Roboters.

Läuft hier auf dem PC (onnxruntime) mit den Bildern, die duckpilot über den Tunnel von mediad
holt. Aktiv zeigt der Entenblick Rahmen um gefundene Enten, und Claude bekommt das Werkzeug
`andere_enten` – etwa für „Lauf zur anderen Ente“ oder „Wer ist da?“.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import Pack, PackInfo

if TYPE_CHECKING:
    from . import SkillManager


class DuckDetectorPack(Pack):
    tool_name = "andere_enten"

    def __init__(self) -> None:
        self.info = PackInfo(
            id="duck_detector", name="Enten-Erkenner",
            kurz="Pollens Modell findet andere Microducks im Kamerabild – mit Richtung und ungefährer Nähe.",
            text="YOLO11n (eine Klasse, 320 × 320) von Pollen, läuft hier auf dem PC mit den Bildern der Kopfkamera. "
                 "Beim ersten Einschalten werden ≈ 10 MB geladen. Rahmen erscheinen im Entenblick.",
            quelle="https://huggingface.co/pollen-robotics/microduck-duck-detector", lizenz="Apache-2.0",
            herkunft="offiziell", braucht="kamera", stand="experimentell",
            im_simulator="Im Simulator gibt es keine Kamerabilder – nur am echten Roboter.",
            hinweis="Braucht den Kamera-Tunnel: -L 7903:/run/mediad/media.sock")

    def tool(self, items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        return {
            "name": self.tool_name,
            "description": "Durch die Kopfkamera nach anderen Microducks schauen. Liefert je gefundener Ente die Richtung "
                           "(Grad, + = links, relativ zur Blickrichtung des Kopfes), wie groß sie im Bild ist (0–1, groß = nah) "
                           "und wie sicher. Nur am echten Roboter.",
            "input_schema": {"type": "object", "properties": {}},
        }

    async def run_tool(self, mgr: "SkillManager", args: dict[str, Any]) -> dict[str, Any]:
        rt = mgr.rt
        addr = rt.camera_address()
        if not addr:
            return {"ok": False, "fehler": "Kamerabilder gibt es nur am echten Roboter."}
        rt.camera.address = addr
        rt.camera.detect_on = True
        try:
            _, info = await rt.camera.picture()
        except Exception as exc:
            return {"ok": False, "fehler": f"Kamera nicht erreichbar: {exc}"}
        if info.get("fehler_erkenner"):
            return {"ok": False, "fehler": info["fehler_erkenner"]}
        enten = info.get("enten") or []
        st = rt.backend.state()
        return {"ok": True, "enten": enten, "kopf_drehung_grad": round(st.head.head_yaw * 57.3),
                "hinweis": "Keine andere Ente im Bild." if not enten else None}
