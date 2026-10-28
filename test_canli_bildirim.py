"""Canli harita + bildirim testleri (robota, buluta, Telegram'a ve gercek dosyalara dokunmaz)."""
import gzip, json, os, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from pathlib import Path
from types import SimpleNamespace as NS

tmp = Path(tempfile.mkdtemp())
os.environ.update(VAKUM_AYAR=str(tmp / "ayar-yok.json"), VAKUM_ODALAR=str(tmp / "odalar.json"),
                  VAKUM_YEDEK=str(tmp / "yedek"), VAKUM_HARITA=str(tmp / "harita"))
import bildirim, canli, harita, lider, robot, test_harita_sentetik as ts

# --- yol seyreltme ---
md = NS(path=NS(path=[[NS(x=i, y=i * 2) for i in range(10)], [], [NS(x=5, y=5)]]))
assert harita.yol_noktalari(md) == [[[i, i * 2] for i in range(10)], [[5, 5]]]
uzun = NS(path=NS(path=[[NS(x=i, y=0) for i in range(10001)]]))
y = harita.yol_noktalari(uzun, sinir=4000)[0]
assert len(y) <= 4001 and y[0] == [0, 0] and y[-1] == [10000, 0], len(y)
assert harita.yol_noktalari(NS(path=None)) == []
ham, _ = ts.sentetik()
_, meta = harita.isle(gzip.compress(ham))
assert meta["yol"] == [] and "aci" in meta

# --- bildirim olaylari (saf fonksiyon) ---
def d(s, h=0, alan=3.2, sure=600):
    return {"durum_kodu": s, "hata_kodu": h, "alan_m2": alan, "sure_sn": sure}
o = {"temizlik": False, "hata": 0}
assert bildirim.olaylar(d(8), d(18), o) == [] and o["temizlik"]
assert bildirim.olaylar(d(18), d(18), o) == []
m = bildirim.olaylar(d(18), d(6), o)
assert m == ["Temizlik bitti (3.2 m², 10 dk). Robot istasyona dönüyor."], m
assert bildirim.olaylar(d(6), d(8), o) == []                      # ikinci kez "bitti" yok
o = {"temizlik": True, "hata": 0}
m = bildirim.olaylar(d(18), d(12, 8), o)
assert m == ["Robot sıkıştı / hata: Robot sıkıştı; etrafındaki engelleri kaldır (kod 8)"], m
assert bildirim.olaylar(d(12, 8), d(12, 8), o) == []              # ayni hata tekrar yok
assert bildirim.olaylar(d(12, 8), d(12, 5), o)[0].startswith("Robot sıkıştı / hata: Ana fırça")
assert bildirim.olaylar(d(12, 5), d(18), o) == [] and o["hata"] == 0
o = {"temizlik": True, "hata": 0}
assert bildirim.olaylar(d(18), d(3), o) == [] and not o["temizlik"]   # elle durdurma: "bitti" yok
assert bildirim.olaylar(d(3), d(6), o) == []
assert "Bilinmeyen hata (kod 99)" in bildirim.olaylar(d(5), d(12, 99), {"temizlik": True, "hata": 0})[0]

# --- izleyici: yalniz yetkili gonderir; ilk okumada bildirim yok ---
gonderilen = []
bildirim.telegram_gonder = lambda m, *a, **k: gonderilen.append(m) or True
sira = iter([d(18), d(18), d(6), d(18), d(6)])
robot.durum = lambda **k: next(sira)
yetki = {"v": True}
iz = bildirim.Izleyici(lambda: yetki["v"], gunluk=lambda *_: None)
iz.tur(); iz.tur(); iz.tur()
assert gonderilen == ["Temizlik bitti (3.2 m², 10 dk). Robot istasyona dönüyor."], gonderilen
yetki["v"] = False
iz.tur(); iz.tur()
assert len(gonderilen) == 1 and iz.son_mesaj.startswith("Temizlik bitti")   # yetkisiz makine gondermedi

# --- lider yetkisi (cift bildirim yok) ---
asil = lider.Lider({"oncelik": 1, "esler": [{"url": "http://b", "oncelik": 2}]}, "127.0.0.1", 1)
assert asil.bildirim_yetkili                        # Mac: hep
yedek = lider.Lider({"oncelik": 2, "esler": [{"url": "http://a", "oncelik": 1}]}, "127.0.0.1", 1)
assert not yedek.bildirim_yetkili                   # pc-2: devralmadan once hayir
yedek.lider = True; yedek.ust_acik = {"http://a": True}
assert not yedek.bildirim_yetkili                   # asil geri geldiyse hayir
yedek.ust_acik = {"http://a": False}
assert yedek.bildirim_yetkili                       # asil kapali + devraldi -> evet
print("bildirim testleri tamam")

# --- canli harita: bulut duserse durur, robot kilidi serbest kalir ---
robot.durum = lambda **k: {"temizlikte": True}
robot.gonder = lambda komut, *a, **k: ["map_slot_test"] if komut == "get_map_v1" else None
canli.BulutBaglanti = NS(yukle=lambda: object())
def bulut_yok(ad, b=None): raise harita.BulutHatasi("HTTP 401")
harita.indir_ham = bulut_yok
c = canli.CanliHarita(gunluk=lambda *_: None)
assert c.tur() == canli.BULUT_BEKLEME and c.durum == "hata" and "Bulut" in c.mesaj and c.png is None
harita.indir_ham = lambda ad, b=None: gzip.compress(ham)
assert c.tur() == canli.ARALIK_TEMIZLIK and c.durum == "tamam" and c.png[:4] == b"\x89PNG"
assert c.meta["temizlikte"] is True
onceki_png = c.png
harita.indir_ham = bulut_yok
c.tur()
assert c.durum == "hata" and c.png is onceki_png        # son harita kalir, sadece durur
robot.gonder = lambda komut, *a, **k: ["retry"]
assert c.tur() == 2
def mesgul(**k): raise robot.Mesgul("x")
robot.durum = mesgul
assert c.tur() == 2                                    # temizlik komutu kilitteyken araya girmez
assert not robot._kilit.locked()
print("canli harita testleri tamam")

# --- sunucu: /api/canli ve /canli.png (kuru, tek) ---
port = 18766
p = subprocess.Popen([sys.executable, "sunucu.py", "--port", str(port), "--kuru", "--tek"], stdout=subprocess.PIPE, text=True)
try:
    p.stdout.readline()
    def istek(yol):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{yol}", timeout=20) as x: return x.status, x.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    s, b = istek("/api/canli"); j = json.loads(b)
    assert s == 200 and j["durum"] in ("bekliyor", "hata") and "meta" in j, j
    assert istek("/canli.png")[0] in (200, 404)
    s, b = istek("/"); assert s == 200 and b"canliYukle" in b
    s, b = istek("/api/kimlik"); assert "bildirim" in json.loads(b)
finally:
    p.terminate()
print("sunucu canli testleri tamam")
