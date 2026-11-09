"""Die Vorlage besteht die Pflichten der Körperschnittstelle."""

import asyncio

from duckpilot import koerper_pruefung as KP
from knowlin_koerper_vorlage import profil


def test_rollbot_besteht_die_pflichten():
    p = profil()
    erg = asyncio.run(KP.pruefen(p.bauen(None), p))
    assert KP.bestanden(erg), [e.zeile() for e in erg if not e.ok]
