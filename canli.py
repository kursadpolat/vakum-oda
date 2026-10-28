"""Canli harita: sayfa acikken robotun yeri ve gectigi yol ~5 sn'de bir Xiaomi bulutundan cekilir.
- Yalniz biri sayfayi izliyorsa calisir (son /api/canli isteginden IZLEME_SN icinde).
- Temizlikte 5 sn, beklemede 30 sn aralik.
- Robota sadece get_map_v1 gider; tek deneme ve kilit bossa (temizlik/durdur komutlarini geciktirmez).
- Bulut girisi duserse canli harita durur (hata mesaji sayfada gorunur), 60 sn'de bir oturum dosyasi
  yeniden okunup denenir; temizlik komutlari bundan etkilenmez (onlar bulutu kullanmaz).
- Hicbir sey diske yazilmaz; son harita bellekte tutulur. Kayitli harita (.gizli/harita) degismez."""
import threading
import time

import harita
import robot
from bulut import BulutBaglanti

IZLEME_SN = 30
ARALIK_TEMIZLIK = 5
ARALIK_BEKLEME = 30
BULUT_BEKLEME = 60


class CanliHarita:
    def __init__(self, gunluk=print):
        self.gunluk = gunluk
        self.png = None
        self.meta = None
        self.zaman = 0.0          # son basarili cekim
        self.durum = "bekliyor"   # bekliyor | tamam | hata
        self.mesaj = ""
        self.son_izleme = 0.0
        self._bulut = None
        self._uyan = threading.Event()
        self._dur = threading.Event()

    def izle(self):
        """Sayfa /api/canli istedi: dongu calismaya baslasin."""
        ilk = time.time() - self.son_izleme > IZLEME_SN
        self.son_izleme = time.time()
        if ilk:
            self._uyan.set()

    def ozet(self):
        return {"durum": self.durum, "mesaj": self.mesaj, "zaman": self.zaman,
                "yas_sn": round(time.time() - self.zaman, 1) if self.zaman else None, "meta": self.meta}

    def _baglanti(self):
        if self._bulut is None:
            self._bulut = BulutBaglanti.yukle()
        return self._bulut

    def tur(self):
        """Tek cekim. Bir sonraki tura kadar beklenecek sureyi (sn) dondurur."""
        try:
            temizlikte = robot.durum(deneme=0, bekle=False)["temizlikte"]
            ad = robot.gonder("get_map_v1", deneme=0, bekle=False)
        except robot.Mesgul:
            return 2
        except Exception as e:
            self.durum, self.mesaj = "hata", f"Robota ulaşılamadı ({type(e).__name__})"
            return ARALIK_TEMIZLIK
        aralik = ARALIK_TEMIZLIK if temizlikte else ARALIK_BEKLEME
        ad = ad[0] if ad else None
        if not isinstance(ad, str) or not ad or ad == "retry":
            return 2                       # robot haritayi hazirliyor
        try:
            ham = harita.indir_ham(ad, self._baglanti())
        except Exception as e:
            self._bulut = None             # bir dahaki denemede oturum dosyasi yeniden okunur
            if self.durum != "hata" or not self.mesaj.startswith("Bulut"):
                self.gunluk(f"canli harita: bulut hatasi: {type(e).__name__}: {e}")
            self.durum = "hata"
            self.mesaj = ("Bulut girişi düştü, canlı harita durdu (temizlik komutları çalışır). "
                          "Yeniden giriş: .venv/bin/python bulut_giris.py")
            return BULUT_BEKLEME
        try:
            png, meta = harita.isle(ham)
        except Exception as e:
            self.durum, self.mesaj = "hata", f"Harita çözülemedi ({type(e).__name__})"
            return aralik
        meta["temizlikte"] = temizlikte
        self.png, self.meta, self.zaman = png, meta, time.time()
        self.durum, self.mesaj = "tamam", ""
        return aralik

    def _dongu(self):
        while not self._dur.is_set():
            if time.time() - self.son_izleme > IZLEME_SN:
                self._uyan.wait(IZLEME_SN)
                self._uyan.clear()
                continue
            bas = time.time()
            try:
                bekle = self.tur()
            except Exception as e:  # dongu asla olmesin
                self.durum, self.mesaj = "hata", f"{type(e).__name__}"
                bekle = ARALIK_BEKLEME
            self._uyan.wait(max(1.0, bekle - (time.time() - bas)))
            self._uyan.clear()

    def baslat(self):
        threading.Thread(target=self._dongu, name="canli-harita", daemon=True).start()
        return self

    def durdur(self):
        self._dur.set()
        self._uyan.set()
