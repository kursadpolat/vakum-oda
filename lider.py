"""<mdns_ad>.local (A kaydi + _http._tcp servisi) yayinini yalniz lider makine yapar.
oncelik en kucuk olan asil liderdir (Mac). Yedek (Monster), kendinden oncelikli tum esler
devralma_hata_sayisi ardisik kontrolde yanit vermezse yayini devralir; biri geri gelince birakir."""
import socket
import threading
import time
import urllib.error
import urllib.request


class Lider:
    def __init__(self, ayar: dict, ip: str, port: int, gunluk=print):
        self.ad = ayar.get("mdns_ad") or "vakum"
        self.makine = ayar.get("makine") or "?"
        self.oncelik = int(ayar.get("oncelik", 1))
        self.ust = [e for e in ayar.get("esler") or [] if e["oncelik"] < self.oncelik]
        self.aralik = max(1, int(ayar.get("kontrol_aralik_sn", 5)))
        self.esik = max(1, int(ayar.get("devralma_hata_sayisi", 3)))
        self.ip, self.port, self.gunluk = ip, port, gunluk
        self.lider = False
        self.ust_acik = {}       # url -> bool
        self._zc = None
        self._info = None
        self._dur = threading.Event()

    @property
    def bildirim_yetkili(self) -> bool:
        """Cift bildirim olmasin: asil lider (ustu olmayan) her zaman; yedek yalniz devraldiysa."""
        if not self.ust:
            return True
        return self.lider and not any(self.ust_acik.values())

    # ---- zeroconf ----
    def _bilgi(self):
        from zeroconf import ServiceInfo
        return ServiceInfo("_http._tcp.local.", f"Vakum Oda._http._tcp.local.", port=self.port,
                           addresses=[socket.inet_aton(self.ip)], server=f"{self.ad}.local.",
                           properties={"makine": self.makine, "path": "/"})

    def _yayinla(self):
        from zeroconf import IPVersion, Zeroconf
        try:
            if self._zc is None:
                self._zc = Zeroconf(interfaces=[self.ip], ip_version=IPVersion.V4Only)
            self._info = self._bilgi()
            self._zc.register_service(self._info, allow_name_change=False)
            self.lider = True
            self.gunluk(f"{self.ad}.local yayini BASLADI ({self.ip})")
        except Exception as e:
            self._info = None
            self.gunluk(f"{self.ad}.local yayini yapilamadi, tekrar denenecek: {type(e).__name__}")

    def _birak(self):
        if self._zc and self._info:
            try:
                self._zc.unregister_service(self._info)
            except Exception:
                pass
        self._info = None
        if self.lider:
            self.gunluk(f"{self.ad}.local yayini BIRAKILDI")
        self.lider = False

    # ---- yoklama ----
    @staticmethod
    def _yanit_veriyor(url):
        try:
            with urllib.request.urlopen(url + "/api/kimlik", timeout=2) as x:
                return x.status == 200
        except urllib.error.HTTPError:
            return True          # sunucu ayakta (eski surum vb.)
        except Exception:
            return False

    def _dongu(self):
        if not self.ust:
            # asil lider: yedegin, bizi gorup yayini birakmasi icin kisa sure bekle
            self._dur.wait(self.aralik + 2)
            while not self._dur.is_set():
                if not self.lider:
                    self._yayinla()
                self._dur.wait(self.aralik)
            return
        hata = 0
        while not self._dur.is_set():
            acik = False
            for e in self.ust:
                a = self._yanit_veriyor(e["url"])
                self.ust_acik[e["url"]] = a
                acik = acik or a
            hata = 0 if acik else hata + 1
            if acik and self.lider:
                self._birak()
            elif not acik and hata >= self.esik and not self.lider:
                self._yayinla()
            self._dur.wait(self.aralik)

    def baslat(self):
        threading.Thread(target=self._dongu, name="lider", daemon=True).start()
        return self

    def durdur(self):
        self._dur.set()
        self._birak()
        if self._zc:
            try:
                self._zc.close()
            except Exception:
                pass
            self._zc = None
