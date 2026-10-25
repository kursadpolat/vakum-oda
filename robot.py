"""Robot (rockrobo.vacuum.v1) ile konusma. SADECE standart komutlar:
get_status, get_map_v1, app_zoned_clean, app_stop, app_pause, app_charge."""
import os
import threading
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
from ayar import AYAR

IP = AYAR["robot_ip"]
TOKEN_DOSYASI = KOK / ".gizli" / "vac.token"
MAX_BOLGE = 5          # gen1: cagri basina en fazla 5 bolge
MIN_KENAR_MM = 200     # bundan kucuk kutu reddedilir
MAX_MM = 52000         # harita koordinat siniri (gen1 ~ 0..51200)

DURUMLAR = {1: "Başlatılıyor", 2: "Şarj bağlantısı bekliyor", 3: "Beklemede", 4: "Uzaktan kumanda",
            5: "Temizliyor", 6: "İstasyona dönüyor", 7: "Manuel mod", 8: "Şarj oluyor",
            9: "Şarj sorunu", 10: "Duraklatıldı", 11: "Nokta temizlik", 12: "Hata",
            13: "Kapanıyor", 14: "Güncelleniyor", 15: "İstasyona gidiyor", 16: "Hedefe gidiyor",
            17: "Bölge temizliyor", 18: "Oda temizliyor", 100: "Şarj tamam"}
TEMIZLIKTE = {4, 5, 7, 11, 16, 17, 18}   # bu durumlarda yeni temizlik komutu gonderilmez

_kilit = threading.Lock()
_cihaz = None


def _token() -> str:
    return TOKEN_DOSYASI.read_text().strip()


def _dev():
    global _cihaz
    if _cihaz is None:
        if not IP:
            raise RuntimeError("robot_ip ayarlanmamış (.gizli/ayar.json)")
        from miio.device import Device
        _cihaz = Device(IP, _token(), timeout=5)
    return _cihaz


def gonder(komut, parametre=None):
    izinli = {"get_status", "get_map_v1", "app_zoned_clean", "app_stop", "app_pause", "app_charge"}
    if komut not in izinli:
        raise ValueError("izin verilmeyen komut: " + komut)
    with _kilit:
        return _dev().send(komut, parametre or [])


def durum() -> dict:
    d = gonder("get_status")[0]
    s = d.get("state")
    return {"durum_kodu": s, "durum": DURUMLAR.get(s, f"Durum {s}"), "pil": d.get("battery"),
            "hata_kodu": d.get("error_code"), "temizlikte": s in TEMIZLIKTE,
            "alan_m2": round(d.get("clean_area", 0) / 1_000_000, 1), "sure_sn": d.get("clean_time")}


def harita_adi(deneme=6, bekle=2.0):
    """get_map_v1 -> harita dosya adi. Temizlikte ['retry'] donebilir; yeniden dener."""
    for _ in range(deneme):
        r = gonder("get_map_v1")
        ad = r[0] if r else None
        if isinstance(ad, str) and ad and ad != "retry":
            return ad
        time.sleep(bekle)
    raise RuntimeError("Robot harita adini vermedi (temizlik sürüyor olabilir, biraz sonra tekrar dene)")


def bolgeleri_dogrula(dikdortgenler, tekrar):
    if not 1 <= len(dikdortgenler) <= MAX_BOLGE:
        raise ValueError(f"Bir odada 1-{MAX_BOLGE} dikdörtgen olmalı")
    if int(tekrar) not in (1, 2, 3):
        raise ValueError("Tekrar sayısı 1-3 olmalı")
    sonuc = []
    for r in dikdortgenler:
        if len(r) != 4:
            raise ValueError("Dikdörtgen [x1,y1,x2,y2] olmalı")
        x1, y1, x2, y2 = (int(round(v)) for v in r)
        x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
        if x2 - x1 < MIN_KENAR_MM or y2 - y1 < MIN_KENAR_MM:
            raise ValueError("Dikdörtgen çok küçük")
        if min(x1, y1) < 0 or max(x2, y2) > MAX_MM:
            raise ValueError("Koordinat harita dışında")
        sonuc.append([x1, y1, x2, y2, int(tekrar)])
    return sonuc


def temizle_komutu(oda: dict, tekrar: int):
    """Odanin dikdortgenlerinden app_zoned_clean parametresini uretir (gondermez)."""
    return ["app_zoned_clean", bolgeleri_dogrula(oda["dikdortgenler"], tekrar)]


def temizle(oda: dict, tekrar: int, kuru=False):
    komut, bolgeler = temizle_komutu(oda, tekrar)
    if not kuru:
        if durum()["temizlikte"]:
            raise RuntimeError("Robot şu an çalışıyor; önce durdur veya bitmesini bekle")
        gonder(komut, bolgeler)
    return {"komut": komut, "parametre": bolgeler, "gonderildi": not kuru}


def durdur():
    gonder("app_stop")
    return True


def istasyona_don():
    # resmi uygulama gibi: once durdur/duraklat, sonra sarj komutu
    try:
        gonder("app_stop")
        time.sleep(1)
    except Exception:
        pass
    gonder("app_charge")
    return True
