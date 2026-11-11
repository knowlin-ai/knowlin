"""Wo liegt ein Fehler beim Laden – bei dir (Internet/WLAN), beim Anbieter (Server) oder bei Knowlin? (seit 0.38.40)

Rückmeldung vom 11.11.: „Manche Fehler waren mit schwachem Internet/WLAN begründet scheinbar – aber es war
nicht ersichtlich, ob es im Programm oder von den Servern Fehler gibt oder bei mir am PC.“ Statt roher Fehlertexte
(„ChunkedEncodingError …“, „HTTP Error 404“) sagt ein Satz, wo das Problem vermutlich liegt und was hilft.
"""

from __future__ import annotations

import re

NETZ = ("ChunkedEncodingError", "IncompleteRead", "Connection broken", "ConnectionError", "ConnectError",
        "ConnectTimeout", "ReadTimeout", "Read timed out", "timed out", "RemoteDisconnected", "ProtocolError",
        "getaddrinfo", "Name or service not known", "Temporary failure in name resolution", "No route to host",
        "Network is unreachable", "ConnectionResetError", "WinError 10054", "WinError 10060", "WinError 11001",
        "SSLError", "EOF occurred")
SERVER = re.compile(r"\b(?:HTTP Error |status(?: code)?[ :=]*|Server error '?)(5\d\d)\b|\b(50[0-4]) (?:Server|Bad Gateway|"
                    r"Service Unavailable|Gateway Timeout|Internal)", re.I)
FEHLT = re.compile(r"\b(?:HTTP Error |Client error '?)(404|410)\b|\b404 Not Found\b", re.I)


def einordnen(fehler: BaseException | str, quelle: str = "dem Server") -> str:
    """Ein Satz für die Oberfläche: wo der Fehler vermutlich liegt und was hilft. `quelle`: „Hugging Face“, „GitHub“ …"""
    roh = fehler if isinstance(fehler, str) else f"{type(fehler).__name__}: {fehler}"
    if any(k in roh for k in NETZ):
        return (f"Die Verbindung zu {quelle} ist abgebrochen – meist liegt das am Internet oder WLAN bei dir, nicht an "
                "Knowlin. Beim nächsten Versuch macht Knowlin dort weiter, wo es aufgehört hat.")
    if SERVER.search(roh):
        return f"{quelle} antwortet gerade nicht richtig – ein Problem beim Anbieter, nicht bei dir. Später nochmal versuchen."
    if FEHLT.search(roh):
        return (f"Die Datei gibt es bei {quelle} nicht (mehr) – das ist ein Fehler in Knowlin, nicht bei dir. Bitte über "
                "„Das lief schief“ melden.")
    return roh if len(roh) <= 300 else roh[:300] + " …"
