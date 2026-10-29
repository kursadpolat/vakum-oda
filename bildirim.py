"""Telegram bildirimi: "Temizlik bitti" ve "Robot sıkıştı / hata: ..." mesajlari.
Robot durumu IZLEME_SN'de bir okunur (get_status, salt-okuma); durum ve hata kodu gecislerinden olay cikar.
Cift bildirim olmasin diye mesaji YALNIZ yetkili makine gonderir (yetkili() -> lider.Lider.bildirim_yetkili):
asil lider (pc-1) her zaman, yedek (pc-2) ancak asil lider kapaliyken devraldiginda.
Iki makine de durumu izler (devralan makine gecmisi bilsin), ama yalniz yetkili olan gonderir.
Ayar: .gizli/telegram.json {"bot_token": "...", "chat_id": "..."} (yoksa bildirim kapali, sadece gunluge yazar)."""
import html
import json
import threading
import time
from pathlib import Path

import requests

import robot

KOK = Path(__file__).resolve().parent
TELEGRAM_DOSYASI = KOK / ".gizli" / "telegram.json"
UYGULAMA_BASLIGI = "🤖 VAKUM ROBOTU"
IZLEME_SN = 10
# temizlik sayilan durumlar (uzaktan kumanda/manuel haric)
TEMIZLIK = {5, 11, 16, 17, 18}
BITTI = {6, 8, 100}          # istasyona donuyor / sarj oluyor / sarj tamam


def telegram_ayar(yol: Path = TELEGRAM_DOSYASI):
    try:
        v = json.loads(yol.read_text(encoding="utf-8"))
        if v.get("bot_token") and v.get("chat_id"):
            return v
    except (OSError, ValueError):
        pass
    return None


def telegram_gonder(metin: str, ayar=None, deneme=3) -> bool:
    ayar = ayar or telegram_ayar()
    if not ayar:
        return False
    url = f"https://api.telegram.org/bot{ayar['bot_token']}/sendMessage"
    # Aynı bot başka uygulamalarca da kullanılıyor: kaynağı belli olsun diye kalın başlık.
    govde = f"<b>{UYGULAMA_BASLIGI}</b>\n{html.escape(metin)}"
    for i in range(deneme):
        try:
            r = requests.post(url, data={"chat_id": ayar["chat_id"], "text": govde, "parse_mode": "HTML"}, timeout=15)
            if r.status_code == 200 and r.json().get("ok"):
                return True
            if 400 <= r.status_code < 500 and r.status_code != 429:
                return False
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return False


def olaylar(onceki: dict | None, simdi: dict, oturum: dict) -> list[str]:
    """Saf fonksiyon: iki durum okumasi arasindaki gecisten bildirim metinleri.
    oturum: {"temizlik": bool, "hata": int} izleyicinin hafizasi (yerinde guncellenir)."""
    mesajlar = []
    s, hk = simdi.get("durum_kodu"), simdi.get("hata_kodu") or 0
    if s in TEMIZLIK:
        oturum["temizlik"] = True
    # hata: kod 0 -> X ya da X -> Y (ayni hata tekrar tekrar gonderilmez)
    if hk and hk != oturum.get("hata", 0):
        mesajlar.append(f"Robot sıkıştı / hata: {robot.hata_metni(hk)} (kod {hk})")
    elif s == 12 and not hk and (onceki or {}).get("durum_kodu") != 12:
        mesajlar.append("Robot sıkıştı / hata: robot hata durumunda (kod verilmedi)")
    oturum["hata"] = hk
    if s == 3 and not hk:
        oturum["temizlik"] = False       # elle durduruldu (Durdur): "bitti" denmez
    if oturum.get("temizlik") and s in BITTI and not hk:
        oturum["temizlik"] = False
        ek = []
        if simdi.get("alan_m2"):
            ek.append(f"{simdi['alan_m2']} m²")
        if simdi.get("sure_sn"):
            ek.append(f"{round(simdi['sure_sn'] / 60)} dk")
        mesajlar.append("Temizlik bitti" + (f" ({', '.join(ek)})" if ek else "") + ". Robot istasyona dönüyor.")
    return mesajlar


class Izleyici:
    def __init__(self, yetkili, makine="?", gunluk=print, aralik=IZLEME_SN):
        self.yetkili = yetkili          # callable -> bool
        self.makine = makine
        self.gunluk = gunluk
        self.aralik = aralik
        self.onceki = None
        self.oturum = {"temizlik": False, "hata": 0}
        self.son_mesaj = ""
        self._dur = threading.Event()

    def tur(self):
        try:
            simdi = robot.durum(deneme=0, bekle=False)
        except Exception:
            return                       # okunamadi: gecis sayma, oncekini koru
        if self.onceki is None:
            # ilk okuma: gecmisi bilmiyoruz; suren hata icin bildirim atma, sadece hafizaya al
            self.oturum = {"temizlik": simdi["durum_kodu"] in TEMIZLIK, "hata": simdi.get("hata_kodu") or 0}
            self.onceki = simdi
            return
        for m in olaylar(self.onceki, simdi, self.oturum):
            if self.yetkili():
                ok = telegram_gonder(m)
                self.gunluk(f"bildirim {'GONDERILDI' if ok else 'GONDERILEMEDI'}: {m}")
            else:
                self.gunluk(f"bildirim (yetkili degil, gonderilmedi): {m}")
            self.son_mesaj = m
        self.onceki = simdi

    def _dongu(self):
        while not self._dur.is_set():
            try:
                self.tur()
            except Exception as e:
                self.gunluk(f"bildirim izleyici hatasi: {type(e).__name__}: {e}")
            self._dur.wait(self.aralik)

    def baslat(self):
        threading.Thread(target=self._dongu, name="bildirim", daemon=True).start()
        return self

    def durdur(self):
        self._dur.set()


if __name__ == "__main__":
    import sys
    metin = " ".join(sys.argv[1:]) or "Vakum: test bildirimi"
    print("gonderildi" if telegram_gonder(metin) else "GONDERILEMEDI (.gizli/telegram.json var mi?)")
