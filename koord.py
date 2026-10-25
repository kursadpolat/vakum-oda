"""Piksel <-> robot mm koordinat donusumu (Roborock harita formati: 1 piksel = 50 mm).
meta: left, top (piksel ofseti), h (yukseklik, ham piksel), olcek (PNG buyutme)."""

MM_PIKSEL = 50


def mm_to_px(x, y, meta):
    px = (x / MM_PIKSEL - meta["left"]) * meta["olcek"]
    py = (meta["h"] - (y / MM_PIKSEL - meta["top"])) * meta["olcek"]
    return px, py


def px_to_mm(px, py, meta):
    x = (px / meta["olcek"] + meta["left"]) * MM_PIKSEL
    y = (meta["h"] - py / meta["olcek"] + meta["top"]) * MM_PIKSEL
    return round(x), round(y)


def dikdortgen_px_to_mm(px1, py1, px2, py2, meta):
    """Ekranda surukleyerek cizilen kutuyu [x1,y1,x2,y2] mm'ye cevirir (x1<x2, y1<y2)."""
    ax, ay = px_to_mm(px1, py1, meta)
    bx, by = px_to_mm(px2, py2, meta)
    return [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]
