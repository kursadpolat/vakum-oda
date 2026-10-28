"""Senkron testleri: birlestirme kurallari + yerelde iki sunucu (gecici dizinler, robota/gercek dosyalara dokunmaz)."""
import json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ.update(VAKUM_AYAR=str(tmp / "yok.json"), VAKUM_ODALAR=str(tmp / "u.json"), VAKUM_YEDEK=str(tmp / "uy"))
import odalar

R = [[1000, 1000, 3000, 3000]]
# --- birlestir ---
y = [{"id": "aaaaaaaa", "ad": "A", "dikdortgenler": R, "guncelleme": 5},
     {"id": "bbbbbbbb", "ad": "B", "dikdortgenler": R}]
u = [{"id": "aaaaaaaa", "ad": "A2", "dikdortgenler": R, "guncelleme": 9},
     {"id": "bbbbbbbb", "ad": "B", "dikdortgenler": R, "guncelleme": 3, "silindi": True},
     {"id": "cccccccc", "ad": "C", "dikdortgenler": R, "guncelleme": 1}]
b = odalar.birlestir(y, u)
assert [o["id"] for o in b] == ["aaaaaaaa", "bbbbbbbb", "cccccccc"]
assert b[0]["ad"] == "A2" and b[1].get("silindi") and b[1]["ad"] == "B"
assert odalar.birlestir(u, y) and odalar.esit(odalar.birlestir(u, y), b)       # simetrik
assert odalar.esit(odalar.birlestir(y, []), y)                                 # bos uzak hicbir seyi silmez
# eski (guncelleme yok) kayit, uzaktaki eski silme isaretine yenilmez mi? en yeni kazanir:
assert odalar.birlestir([{"id": "dddddddd", "ad": "D", "dikdortgenler": R, "guncelleme": 50}],
                        [{"id": "dddddddd", "ad": "D", "dikdortgenler": R, "guncelleme": 10, "silindi": True}])[0].get("silindi") is None
# gecersiz uzak kayitlar atlanir
assert odalar.dogrula_uzak({"odalar": [{"id": "XYZ", "ad": "x", "dikdortgenler": R}, {"id": "eeeeeeee", "ad": "", "dikdortgenler": R}]}) == []
# uygula_uzak: yedek + degismezse yazmaz
odalar.kaydet_oda({"ad": "Oda A", "dikdortgenler": R})
n0 = len(list((tmp / "uy").glob("*")))
odalar.uygula_uzak(odalar.oku_ham()); assert len(list((tmp / "uy").glob("*"))) == n0      # ayni veri -> yazma yok
odalar.uygula_uzak({"odalar": u}); assert len(list((tmp / "uy").glob("*"))) == n0 + 1     # degisti -> once yedek
assert len(odalar.oku_ham()["odalar"]) == 4
print("birlestirme testleri tamam")

# --- iki sunucu ---
ANAHTAR = "test-anahtar-123"
P = {"A": 18801, "B": 18802}
proc = []
for ad, port in P.items():
    d = tmp / ad; d.mkdir()
    es = "B" if ad == "A" else "A"
    (d / "ayar.json").write_text(json.dumps({"makine": ad, "oncelik": 1 if ad == "A" else 2, "port": port, "mdns": False,
        "esler": [{"ad": es, "url": f"http://127.0.0.1:{P[es]}", "oncelik": 2 if ad == "A" else 1}],
        "senkron_anahtar": ANAHTAR, "senkron_aralik_sn": 5}))
    env = dict(os.environ, VAKUM_AYAR=str(d / "ayar.json"), VAKUM_ODALAR=str(d / "odalar.json"),
               VAKUM_YEDEK=str(d / "yedek"), VAKUM_HARITA=str(d / "harita"))
    if ad == "A":
        (d / "odalar.json").write_text(json.dumps({"odalar": [{"id": "11111111", "ad": "Kaynak", "dikdortgenler": R}]}))
    proc.append(subprocess.Popen([sys.executable, "sunucu.py", "--kuru"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

def istek(ad, yol, metot="GET", g=None, h=None):
    r = urllib.request.Request(f"http://127.0.0.1:{P[ad]}{yol}", method=metot,
                               data=json.dumps(g).encode() if g is not None else None, headers=h or {"X-Vakum": "1"})
    try:
        with urllib.request.urlopen(r, timeout=10) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, None

def bekle(kosul, sure=15):
    t = time.time()
    while time.time() - t < sure:
        try:
            if kosul(): return True
        except Exception: pass
        time.sleep(0.3)
    return False

def adlar(ad): return sorted(o["ad"] for o in istek(ad, "/api/odalar")[1]["odalar"])
try:
    assert bekle(lambda: adlar("B") == ["Kaynak"]), "ilk kopya B'ye gitmedi"
    assert istek("A", "/api/senkron")[0] == 403                                       # anahtarsiz
    assert istek("A", "/api/senkron", h={"X-Senkron-Anahtar": "yanlis"})[0] == 403
    assert istek("A", "/api/senkron", "POST", {"odalar": []}, h={"X-Senkron-Anahtar": "yanlis"})[0] == 403
    s, k = istek("B", "/api/kimlik"); assert k["makine"] == "B" and k["esler"][0]["ad"] == "A"
    s, o = istek("A", "/api/oda", "POST", {"ad": "Oda B", "dikdortgenler": R}); assert s == 200
    assert bekle(lambda: adlar("B") == ["Kaynak", "Oda B"]), "kayit B'ye iletilmedi"
    assert istek("B", "/api/oda/" + o["id"], "DELETE")[0] == 200
    assert bekle(lambda: adlar("A") == ["Kaynak"]), "silme A'ya iletilmedi"
    ham = json.loads((tmp / "A" / "odalar.json").read_text())["odalar"]
    assert any(x["id"] == o["id"] and x["silindi"] and x["ad"] == "Oda B" for x in ham)   # icerik korunur
    # B kapaliyken A'da degisiklik, B acilinca alir
    proc[1].terminate(); proc[1].wait()
    istek("A", "/api/oda", "POST", {"ad": "Oda C", "dikdortgenler": R})
    d = tmp / "B"
    env = dict(os.environ, VAKUM_AYAR=str(d / "ayar.json"), VAKUM_ODALAR=str(d / "odalar.json"),
               VAKUM_YEDEK=str(d / "yedek"), VAKUM_HARITA=str(d / "harita"))
    proc[1] = subprocess.Popen([sys.executable, "sunucu.py", "--kuru"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert bekle(lambda: adlar("B") == ["Kaynak", "Oda C"], 20), "B acilista almadi"
    a = sorted(json.dumps(x, sort_keys=True) for x in json.loads((tmp / "A" / "odalar.json").read_text())["odalar"])
    b = sorted(json.dumps(x, sort_keys=True) for x in json.loads((tmp / "B" / "odalar.json").read_text())["odalar"])
    assert a == b, "iki dosya farkli"
    assert list((tmp / "B" / "yedek").glob("*.json")), "B yedek almadi"
finally:
    for p in proc: p.terminate()
print("iki sunucu senkron testleri tamam")
