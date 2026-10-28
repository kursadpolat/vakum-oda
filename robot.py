"""Robot (rockrobo.vacuum.v1) ile konusma. SADECE standart miio komutlari (IZINLI kumesi):
temizlik: app_zoned_clean, app_stop, app_pause, app_charge; okuma: get_status, get_map_v1;
ses paketi: get_current_sound, get_sound_volume, get_sound_progress, dnld_install_sound."""
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
HATALAR = {1: "Lazer sensörü takıldı ya da önü kapalı; üstteki turuncu kafayı kontrol et",
           2: "Ön tampon sıkıştı; tamponu temizleyip hafifçe bastır",
           3: "Tekerlekler boşta kaldı; robotu düz bir yere taşı",
           4: "Uçurum sensörleri kirli ya da robot bir kenarda; sensörleri sil, robotu taşı",
           5: "Ana fırçaya bir şey takıldı; fırçayı çıkarıp temizle",
           6: "Yan fırçaya bir şey takıldı; yan fırçayı temizle",
           7: "Tekerlek sıkıştı; tekerleklerin önünü aç",
           8: "Robot sıkıştı; etrafındaki engelleri kaldır",
           9: "Toz haznesi takılı değil",
           10: "Filtre tıkalı ya da ıslak; filtreyi temizle",
           11: "Manyetik sınır şeridine takıldı; robotu şeritten uzaklaştır",
           12: "Pil çok zayıf; robotu şarja koy",
           13: "Şarj olamıyor; şarj kontaklarını sil",
           14: "Pil arızası",
           15: "Duvar sensörü kirli; sensörü sil",
           16: "Zemin düz değil; robotu düz bir yere koy",
           17: "Yan fırça modülü arızası; robotu yeniden başlat",
           18: "Fan arızası; robotu yeniden başlat",
           19: "İstasyonda elektrik yok; fişi kontrol et",
           21: "Lazer kapağına baskı var; robotu sıkıştığı yerden çıkar",
           22: "Robotun şarj sensörü kirli; sil",
           23: "İstasyonun sinyal alanı kirli ya da kapalı; önünü aç",
           24: "Yasak bölgeye ya da sınır şeridine girdi; robotu uzaklaştır"}
TEMIZLIKTE = {4, 5, 7, 11, 16, 17, 18}   # bu durumlarda yeni temizlik komutu gonderilmez

IZINLI = {"get_status", "get_map_v1", "app_zoned_clean", "app_stop", "app_pause", "app_charge",
          "get_current_sound", "get_sound_volume", "get_sound_progress", "dnld_install_sound"}

_kilit = threading.Lock()
_cihaz = None


class Mesgul(RuntimeError):
    """Robot baglantisi baska bir komutla mesgul (bekle=False iken)."""


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


def gonder(komut, parametre=None, deneme=None, bekle=True):
    """deneme: miio yeniden deneme sayisi (None = kutuphane varsayilani, 0 = tek deneme ~5 sn).
    bekle=False: baglanti mesgulse beklemeden Mesgul firlatir (arka plan okumalari temizlik komutunu geciktirmesin)."""
    if komut not in IZINLI:
        raise ValueError("izin verilmeyen komut: " + komut)
    if not _kilit.acquire(blocking=bekle):
        raise Mesgul("robot mesgul")
    try:
        if deneme is None:
            return _dev().send(komut, parametre or [])
        try:
            return _dev().send(komut, parametre or [], retry_count=deneme)
        except Exception:
            _id_atla()
            raise
    finally:
        _kilit.release()


def _id_atla():
    """Robot, gordugu son mesaj id'sinden kucuk id'li paketlere yanit vermez (ayni robota baska
    istemci/makine de konusunca bizim sayac geride kalir). Kutuphane kendi yeniden denemesinde id'yi
    100 artirir; deneme=0 ile bu adim atlandigi icin burada yapilir, bir sonraki cagri yakalar."""
    try:
        p = _cihaz._protocol
        p._MiIOProtocol__id = (p.raw_id + 100) % 9900
        p._discovered = False
    except Exception:
        pass


def durum(deneme=None, bekle=True) -> dict:
    d = gonder("get_status", deneme=deneme, bekle=bekle)[0]
    s = d.get("state")
    return {"durum_kodu": s, "durum": DURUMLAR.get(s, f"Durum {s}"), "pil": d.get("battery"),
            "hata_kodu": d.get("error_code"), "hata": hata_metni(d.get("error_code")), "temizlikte": s in TEMIZLIKTE,
            "alan_m2": round(d.get("clean_area", 0) / 1_000_000, 1), "sure_sn": d.get("clean_time")}


def hata_metni(kod):
    if not kod:
        return ""
    return HATALAR.get(kod, f"Bilinmeyen hata (kod {kod})")


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
