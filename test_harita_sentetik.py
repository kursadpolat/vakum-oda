"""Sentetik Roborock harita dosyasi uretip harita.isle() ve koordinat donusumunu test eder (aga dokunmaz)."""
import gzip, struct, sys
import harita, koord

def blok(tip, baslik_ek, veri):
    # baslik: tip(2) uzunluk(2) veri_uzunlugu(4) + ek
    bas = struct.pack("<HHI", tip, 8 + len(baslik_ek), len(veri)) + baslik_ek
    return bas + veri

def sentetik():
    W, H, TOP, LEFT = 40, 30, 480, 490
    px = bytearray(W * H)
    for r in range(5, 25):           # ham satir r (alttan yukari)
        for c in range(5, 35):
            px[r * W + c] = 0xFF
    img = blok(2, struct.pack("<iiii", TOP, LEFT, H, W), bytes(px))
    dock_mm = (25500, 25500)
    sarj = blok(1, b"", struct.pack("<ii", *dock_mm))
    rob = blok(8, b"", struct.pack("<iii", 26000, 25900, 0))
    ust = struct.pack("<2sH", b"rr", 0x20) + bytes(0x20 - 4)
    return ust + sarj + img + rob, dict(W=W, H=H, TOP=TOP, LEFT=LEFT)

ham, p = sentetik()
png, meta = harita.isle(gzip.compress(ham))
assert meta["dock"] == [25500, 25500], meta
assert meta["h"] == p["H"] and meta["left"] == p["LEFT"] and meta["top"] == p["TOP"], meta
# dock PNG uzerinde, ic bolgede olmali
x, y = koord.mm_to_px(25500, 25500, meta)
assert 0 <= x < meta["png_w"] and 0 <= y < meta["png_h"], (x, y)
# gidis-donus
for mm in [(25500, 25500), (24000, 26000), (27123, 24777)]:
    px_, py_ = koord.mm_to_px(*mm, meta)
    assert all(abs(a - b) <= 1 for a, b in zip(koord.px_to_mm(px_, py_, meta), mm)), mm
# yon: mm y artarsa ekranda yukari (py azalir)
assert koord.mm_to_px(25500, 26500, meta)[1] < koord.mm_to_px(25500, 25500, meta)[1]
# ham satir 5 (zemin) -> mm_y = (TOP+5)*50 ; PNG'de alttan 5. satir icinde
from PIL import Image
from io import BytesIO
im = Image.open(BytesIO(png)).convert("RGBA")
ax, ay = koord.mm_to_px((p["LEFT"] + 10 + .5) * 50, (p["TOP"] + 10 + .5) * 50, meta)
assert im.getpixel((int(ax), int(ay)))[3] > 0, "ic piksel seffaf"
ox, oy = koord.mm_to_px((p["LEFT"] + 1) * 50, (p["TOP"] + 1) * 50, meta)
assert im.getpixel((int(ox), int(oy)))[3] == 0 or im.getpixel((int(ox), int(oy))) != im.getpixel((int(ax), int(ay)))
print("TAMAM harita+koordinat", meta["png_w"], meta["png_h"])
