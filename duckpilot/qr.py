"""Kleiner QR-Code-Erzeuger (Byte-Modus, Fehlerkorrektur M, Versionen 1–10).

Reicht für Kopplungs-Links wie ``http://192.168.178.23:8766/koppeln?c=…`` und kommt ohne
zusätzliches Paket aus – duckpilot installiert nur eine feste Paketliste.
"""
from __future__ import annotations

# Version → (EC-Codewörter je Block, [(Blockanzahl, Datencodewörter je Block), …]) für Stufe M
_BLOCKS_M = {
    1: (10, [(1, 16)]),
    2: (16, [(1, 28)]),
    3: (26, [(1, 44)]),
    4: (18, [(2, 32)]),
    5: (24, [(2, 43)]),
    6: (16, [(4, 27)]),
    7: (18, [(4, 31)]),
    8: (22, [(2, 38), (2, 39)]),
    9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}

# ── Galois-Feld GF(256) für Reed-Solomon ────────────────────────────────────
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n: int) -> list[int]:
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _gmul(c, _EXP[i])
        g = nxt
    return g


def _rs_ecc(data: list[int], n: int) -> list[int]:
    gen = _rs_generator(n)
    rem = list(data) + [0] * n
    for i in range(len(data)):
        f = rem[i]
        if f:
            for j in range(1, len(gen)):
                rem[i + j] ^= _gmul(gen[j], f)
    return rem[len(data):]


def _capacity(version: int) -> int:
    return sum(cnt * k for cnt, k in _BLOCKS_M[version][1])


def _codewords(payload: bytes, version: int) -> list[int]:
    cap = _capacity(version)
    bits: list[int] = []

    def put(val: int, n: int) -> None:
        bits.extend((val >> (n - 1 - i)) & 1 for i in range(n))

    put(0b0100, 4)
    put(len(payload), 8 if version < 10 else 16)
    for b in payload:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < cap:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    # in Blöcke teilen, Fehlerkorrektur rechnen, verschränken
    ecn, groups = _BLOCKS_M[version]
    blocks, pos = [], 0
    for cnt, k in groups:
        for _ in range(cnt):
            blocks.append(data[pos:pos + k])
            pos += k
    eccs = [_rs_ecc(b, ecn) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out.extend(b[i] for b in blocks if i < len(b))
    for i in range(ecn):
        out.extend(e[i] for e in eccs)
    return out


def _bch(value: int, poly: int, bits: int) -> int:
    v = value << bits
    plen = poly.bit_length()
    while v.bit_length() >= plen:
        v ^= poly << (v.bit_length() - plen)
    return (value << bits) | v


_MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _base(version: int) -> tuple[list[list[int]], list[list[bool]]]:
    n = 17 + 4 * version
    m = [[0] * n for _ in range(n)]
    fixed = [[False] * n for _ in range(n)]

    def setm(r: int, c: int, v: int) -> None:
        m[r][c] = v
        fixed[r][c] = True

    for (r0, c0) in ((0, 0), (0, n - 7), (n - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < n and 0 <= c < n:
                    inside = 0 <= dr <= 6 and 0 <= dc <= 6
                    ring = inside and (dr in (0, 6) or dc in (0, 6))
                    core = 2 <= dr <= 4 and 2 <= dc <= 4
                    setm(r, c, 1 if (ring or core) else 0)
    for i in range(8, n - 8):
        setm(6, i, 1 - i % 2)
        setm(i, 6, 1 - i % 2)
    pos = _ALIGN[version]
    for r in pos:
        for c in pos:
            if (r, c) in ((pos[0], pos[0]), (pos[0], pos[-1]), (pos[-1], pos[0])):
                continue  # dort sitzt ein Suchmuster
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    setm(r + dr, c + dc, 1 if max(abs(dr), abs(dc)) != 1 else 0)
    # Formatbereiche reservieren, dunkles Modul
    for i in range(9):
        if not fixed[8][i]:
            setm(8, i, 0)
        if not fixed[i][8]:
            setm(i, 8, 0)
    for i in range(8):
        setm(8, n - 1 - i, 0)
        setm(n - 1 - i, 8, 0)
    setm(n - 8, 8, 1)
    if version >= 7:
        v = _bch(version, 0x1F25, 12)
        for i in range(18):
            bit = (v >> i) & 1
            a, b = i // 3, i % 3 + n - 11
            setm(a, b, bit)
            setm(b, a, bit)
    return m, fixed


def _place(m: list[list[int]], fixed: list[list[bool]], words: list[int]) -> None:
    n = len(m)
    bits = [(w >> (7 - i)) & 1 for w in words for i in range(8)]
    idx = 0
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for c in (col, col - 1):
                if not fixed[r][c]:
                    m[r][c] = bits[idx] if idx < len(bits) else 0
                    idx += 1
        upward = not upward
        col -= 2


def _format(m: list[list[int]], mask: int) -> None:
    n = len(m)
    v = _bch((0b00 << 3) | mask, 0x537, 10) ^ 0x5412  # Stufe M = 00
    bits = [(v >> i) & 1 for i in range(15)]
    # um das obere linke Suchmuster (Zeile, Spalte)
    for i in range(6):
        m[i][8] = bits[i]
    m[7][8] = bits[6]
    m[8][8] = bits[7]
    m[8][7] = bits[8]
    for i in range(9, 15):
        m[8][14 - i] = bits[i]
    # Kopie an den anderen beiden Suchmustern
    for i in range(8):
        m[8][n - 1 - i] = bits[i]
    for i in range(8, 15):
        m[n - 15 + i][8] = bits[i]
    m[n - 8][8] = 1


def _penalty(m: list[list[int]]) -> int:
    n = len(m)
    score = 0
    for line in list(m) + [list(col) for col in zip(*m)]:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, prev = 1, v
        if run >= 5:
            score += run - 2
        s = "".join(map(str, line))
        score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(map(sum, m))
    score += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return score


def encode(text: str) -> list[list[int]]:
    """QR-Matrix (1 = dunkel) ohne Ruhezone."""
    payload = text.encode("utf-8")
    for version in range(1, 11):
        head = 4 + (8 if version < 10 else 16)
        if head + 8 * len(payload) <= 8 * _capacity(version):
            break
    else:
        raise ValueError("Text zu lang für den QR-Code")
    words = _codewords(payload, version)
    base, fixed = _base(version)
    best = None
    for mask in range(8):
        m = [row[:] for row in base]
        _place(m, fixed, words)
        f = _MASKS[mask]
        for r in range(len(m)):
            for c in range(len(m)):
                if not fixed[r][c] and f(r, c):
                    m[r][c] ^= 1
        _format(m, mask)
        p = _penalty(m)
        if best is None or p < best[0]:
            best = (p, m)
    return best[1]


def rows(text: str) -> list[str]:
    """Für die Oberfläche: eine Zeichenkette aus 0/1 je Zeile."""
    return ["".join(map(str, r)) for r in encode(text)]
