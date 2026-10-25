"""Makineler arasi odalar.json senkronu (paylasilan anahtarla korunur).
- Her yerel kayit/silmeden sonra eslere gonderilir (it).
- Acilista ve her senkron_aralik_sn'de esten cekilip birlestirilir; es eksikse birlesmis hal geri itilir.
Birlestirme odalar.uygula_uzak'ta: id bazinda, en yeni kazanir, fiziksel silme yok, yazmadan once yedek."""
import json
import threading
import time
import urllib.error
import urllib.request

import odalar

BASLIK = "X-Senkron-Anahtar"


class Senkron:
    def __init__(self, ayar: dict, gunluk=print):
        self.anahtar = ayar.get("senkron_anahtar") or ""
        self.esler = ayar.get("esler") or []
        self.aralik = max(5, int(ayar.get("senkron_aralik_sn", 30)))
        self.gunluk = gunluk
        self.son = {}            # es url -> son basarili temas zamani
        self._olay = threading.Event()
        self._dur = threading.Event()
        self._kilit = threading.Lock()

    @property
    def acik(self):
        return bool(self.anahtar and self.esler)

    def _istek(self, url, metot="GET", govde=None, zaman=4):
        r = urllib.request.Request(url + "/api/senkron", method=metot,
                                   data=json.dumps(govde, ensure_ascii=False).encode() if govde is not None else None,
                                   headers={BASLIK: self.anahtar, "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=zaman) as x:
            return json.loads(x.read())

    def es_ile(self, es):
        """Tek es ile iki yonlu senkron. Basariliysa True."""
        url = es["url"]
        with self._kilit:
            try:
                uzak = self._istek(url)
                birlesik = odalar.uygula_uzak(uzak)
                if not odalar.esit(odalar.dogrula_uzak(uzak), birlesik["odalar"]):
                    geri = self._istek(url, "POST", {"odalar": birlesik["odalar"]})
                    odalar.uygula_uzak(geri)
                self.son[url] = time.time()
                return True
            except (urllib.error.URLError, OSError, TimeoutError):
                return False
            except Exception as e:  # dogrulama vb. -> yerel veriye dokunulmadi
                self.gunluk(f"senkron hatasi ({es.get('ad')}): {type(e).__name__}: {e}")
                return False

    def tur(self):
        for es in self.esler:
            self.es_ile(es)

    def tetikle(self):
        """Yerel degisiklikten sonra cagrilir: dongu hemen bir tur atar."""
        self._olay.set()

    def _dongu(self):
        while not self._dur.is_set():
            self.tur()
            self._olay.wait(self.aralik)
            self._olay.clear()

    def baslat(self):
        if self.acik:
            threading.Thread(target=self._dongu, name="senkron", daemon=True).start()
        return self

    def durdur(self):
        self._dur.set()
        self._olay.set()
