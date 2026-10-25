"""Robota dokunmayan testler: odalar kaydet/yedek, zoned_clean komutu, sunucu (kuru mod) sayfa+API."""
import json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error, gzip
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ.update(VAKUM_AYAR=str(tmp / "ayar-yok.json"), VAKUM_ODALAR=str(tmp / "odalar.json"), VAKUM_YEDEK=str(tmp / "yedek"), VAKUM_HARITA=str(tmp / "harita"))
import odalar, robot, harita, test_harita_sentetik as ts

# --- zoned_clean komutu ---
oda = {"ad": "x", "dikdortgenler": [[24000, 25000, 26000, 27000], [27000.4, 28000, 25000, 26000]]}
k, par = robot.temizle_komutu(oda, 2)
assert k == "app_zoned_clean" and par == [[24000, 25000, 26000, 27000, 2], [25000, 26000, 27000, 28000, 2]], par
for kotu in ([], [[0, 0, 100, 100]], [[0, 0, 1000, 1000]] * 6):
    try: robot.temizle_komutu({"dikdortgenler": kotu}, 1); raise SystemExit("reddedilmeliydi")
    except ValueError: pass
try: robot.temizle_komutu(oda, 4); raise SystemExit("tekrar 4 reddedilmeliydi")
except ValueError: pass
try: robot.gonder("app_start"); raise SystemExit("izinsiz komut")
except ValueError: pass

# --- odalar + yedek ---
a = odalar.kaydet_oda({"ad": "Yatak odası", "dikdortgenler": [[24000, 25000, 26000, 27000]]})
assert not (tmp / "yedek").exists()                       # ilk yazmada yedeklenecek dosya yok
b = odalar.kaydet_oda({"id": a["id"], "ad": "Yatak", "dikdortgenler": [[24000, 25000, 26000, 27000]]})
assert len(list((tmp / "yedek").glob("*.json"))) == 1
odalar.kaydet_oda({"ad": "Salon", "dikdortgenler": [[1000, 1000, 5000, 5000]]})
odalar.sil_oda(a["id"])
yedekler = sorted((tmp / "yedek").glob("*.json"))
assert len(yedekler) == 3 and any("Salon" in y.read_text() and a["id"] in y.read_text() for y in yedekler)
assert [o["ad"] for o in odalar.oku()["odalar"]] == ["Salon"]
assert any(o["id"] == a["id"] and o["silindi"] for o in odalar.oku_ham()["odalar"])   # fiziksel silme yok
for kotu in ({"ad": "", "dikdortgenler": [[0, 0, 1000, 1000]]}, {"ad": "z", "dikdortgenler": []}):
    try: odalar.kaydet_oda(kotu); raise SystemExit("reddedilmeliydi")
    except ValueError: pass
print("odalar/komut testleri tamam")

# --- sunucu (kuru mod) ---
ham, _ = ts.sentetik(); png, meta = harita.isle(gzip.compress(ham))
(tmp / "harita").mkdir(); (tmp / "harita/harita.png").write_bytes(png); (tmp / "harita/meta.json").write_text(json.dumps(meta))
port = 18765
p = subprocess.Popen([sys.executable, "sunucu.py", "--port", str(port), "--kuru", "--tek"], stdout=subprocess.PIPE, text=True)
try:
    p.stdout.readline()
    U = f"http://127.0.0.1:{port}"
    def istek(yol, metot="GET", g=None, baslik=True):
        r = urllib.request.Request(U + yol, method=metot, data=json.dumps(g).encode() if g is not None else None,
                                   headers={"X-Vakum": "1"} if baslik else {})
        try:
            with urllib.request.urlopen(r, timeout=20) as x: return x.status, x.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    s, body = istek("/"); assert s == 200 and "Süpürge".encode() in body
    s, body = istek("/harita.png"); assert s == 200 and body[:4] == b"\x89PNG"
    s, body = istek("/api/harita"); assert json.loads(body)["olcek"] == 4
    s, body = istek("/api/odalar"); oid = json.loads(body)["odalar"][0]["id"]
    s, body = istek("/api/temizle", "POST", {"oda_id": oid, "tekrar": 3})
    r = json.loads(body); assert s == 200 and r["gonderildi"] is False and r["parametre"] == [[1000, 1000, 5000, 5000, 3]], r
    assert istek("/api/temizle", "POST", {"oda_id": oid, "tekrar": 3}, baslik=False)[0] == 403
    assert istek("/api/temizle", "POST", {"oda_id": "deadbeef", "tekrar": 1})[0] == 404
    assert istek("/api/temizle", "POST", {"oda_id": oid, "tekrar": 9})[0] == 400
    assert json.loads(istek("/api/durdur", "POST", {})[1])["gonderildi"] is False
    assert json.loads(istek("/api/istasyon", "POST", {})[1])["gonderildi"] is False
    s, body = istek("/api/oda", "POST", {"ad": "Mutfak", "dikdortgenler": [[2000, 2000, 4000, 4000]]}); assert s == 200
    assert istek("/api/oda/" + json.loads(body)["id"], "DELETE")[0] == 200
    s, body = istek("/api/durum")   # robota salt-okuma get_status (komut degil)
    print("durum:", s, body[:90])
finally:
    p.terminate()
print("sunucu testleri tamam")
