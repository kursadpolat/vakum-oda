"""Turkce ses paketini robota yukler (gen1, standart miio komutu dnld_install_sound).
Calistir: .venv/bin/python ses_yukle.py              (once yedek, sonra yukleme + ilerleme)
          .venv/bin/python ses_yukle.py --sadece-yedek
Adimlar:
1. Robotun mevcut ses ayarlari (get_current_sound, get_sound_volume) .gizli/yedek/ses-<zaman>.json'a yazilir
   (eski yedeklerin uzerine yazilmaz). Yedek alinamazsa yukleme YAPILMAZ.
2. Robot temizlikteyse yukleme yapilmaz.
3. .gizli/ses/tr.pkg bu makinede gecici bir HTTP sunucusundan (yalniz bu dosya) robota sunulur.
4. dnld_install_sound {"url", "md5", "sid"} gonderilir, get_sound_progress ile ilerleme izlenir.
Geri donus: README "Ses paketi" bolumu."""
import argparse
import hashlib
import json
import socket
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import robot

KOK = Path(__file__).resolve().parent
PAKET = KOK / ".gizli" / "ses" / "tr.pkg"
YEDEK = KOK / ".gizli" / "yedek"
SID = 10000          # ozel paket kimligi (resmi paketler kucuk sid kullanir)
DURUMLAR = {0: "bilinmiyor", 1: "indiriyor", 2: "kuruyor", 3: "kuruldu", 4: "hata"}


def oku(komut):
    return robot.gonder(komut)


def yedekle() -> Path:
    veri = {"tarih": datetime.now().isoformat(timespec="seconds"),
            "get_current_sound": oku("get_current_sound"), "get_sound_volume": oku("get_sound_volume")}
    YEDEK.mkdir(parents=True, exist_ok=True)
    yol = YEDEK / f"ses-{datetime.now():%Y%m%d-%H%M%S}.json"
    if yol.exists():
        raise RuntimeError("yedek dosyasi zaten var")
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    return yol


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((robot.IP, 9))
    ip = s.getsockname()[0]
    s.close()
    return ip


def sun(veri: bytes, ip: str):
    istekler = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            istekler.append((self.client_address[0], self.path))
            if self.path.split("?")[0] != "/tr.pkg":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(veri)))
            self.end_headers()
            self.wfile.write(veri)

    srv = ThreadingHTTPServer((ip, 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, istekler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sadece-yedek", action="store_true")
    ap.add_argument("--sure", type=int, default=600, help="ilerleme bekleme siniri (sn)")
    a = ap.parse_args()
    yol = yedekle()
    print(f"yedek: {yol.name}", flush=True)
    if a.sadece_yedek:
        return 0
    if not PAKET.exists():
        print("paket yok: once .venv/bin/python ses_paketi.py")
        return 1
    if robot.durum()["temizlikte"]:
        print("robot calisiyor, yukleme yapilmadi")
        return 1
    veri = PAKET.read_bytes()
    md5 = hashlib.md5(veri).hexdigest()
    srv, istekler = sun(veri, lan_ip())
    url = f"http://{srv.server_address[0]}:{srv.server_address[1]}/tr.pkg"
    try:
        r = robot.gonder("dnld_install_sound", {"url": url, "md5": md5, "sid": SID})
        print(f"dnld_install_sound yaniti: {r}", flush=True)
        bas, son = time.time(), None
        while time.time() - bas < a.sure:
            time.sleep(3)
            try:
                p = robot.gonder("get_sound_progress")[0]
            except Exception as e:
                print(f"ilerleme okunamadi: {type(e).__name__}", flush=True)
                continue
            ozet = (p.get("state"), p.get("progress"), p.get("error"))
            if ozet != son:
                print(f"ilerleme: {DURUMLAR.get(p.get('state'), p.get('state'))} %{p.get('progress')} "
                      f"hata={p.get('error')} sid={p.get('sid_in_progress')}", flush=True)
                son = ozet
            if p.get("state") == 3 or (p.get("state") == 4) or (p.get("error") or 0) != 0:
                break
            if p.get("state") == 0 and istekler and time.time() - bas > 30:
                break                      # bitti ve bosta (bazi surumler 3 yerine 0'a doner)
        print(f"robot indirme istekleri: {len(istekler)}", flush=True)
        simdi = robot.gonder("get_current_sound")
        print(f"get_current_sound: {simdi}", flush=True)
        basarili = bool(simdi) and simdi[0].get("sid_in_use") == SID
        print("SONUC: " + ("Turkce paket kullanimda" if basarili else "paket kullanimda DEGIL"))
        return 0 if basarili else 1
    finally:
        srv.shutdown()


if __name__ == "__main__":
    sys.exit(main())
