"""Yerel (LAN) oda oda temizlik sunucusu.
Calistir: .venv/bin/python sunucu.py [--port 8765] [--kuru]
--kuru: temizle/durdur/istasyon komutlari robota GONDERILMEZ, sadece uretilen komut gosterilir."""
import argparse
import hmac
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import odalar
import robot
from ayar import AYAR as AYARLAR
from lider import Lider
from senkron import BASLIK as SENKRON_BASLIK, Senkron

KOK = Path(__file__).resolve().parent
HARITA = Path(os.environ.get("VAKUM_HARITA", KOK / ".gizli" / "harita"))
SAYFA = KOK / "sayfa.html"
AYAR = {"kuru": False}
SENKRON = Senkron({})      # main() icinde ayarla yeniden kurulur
LIDER = None


def gunluk(m):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), m, flush=True)
_harita_kilit = threading.Lock()


class Isleyici(BaseHTTPRequestHandler):
    server_version = "VakumOda/1"

    def log_message(self, fmt, *a):
        pass

    # ---- yardimcilar ----
    def _gonder(self, kod, govde: bytes, tur="application/json; charset=utf-8", cache="no-store"):
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(govde)

    def _json(self, kod, veri):
        self._gonder(kod, json.dumps(veri, ensure_ascii=False).encode())

    def _hata(self, kod, mesaj):
        self._json(kod, {"hata": mesaj})

    def _govde(self, sinir=100_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n > sinir:
            raise ValueError("Gövde çok büyük")
        return json.loads(self.rfile.read(n) or b"{}")

    def _senkron_izni(self):
        a = SENKRON.anahtar
        return bool(a) and hmac.compare_digest(self.headers.get(SENKRON_BASLIK, ""), a)

    def _kimlik(self):
        esler = []
        for e in AYARLAR["esler"]:
            acik = None
            if LIDER and e["url"] in LIDER.ust_acik:
                acik = LIDER.ust_acik[e["url"]]
            elif e["url"] in SENKRON.son:
                acik = time.time() - SENKRON.son[e["url"]] < SENKRON.aralik * 2 + 10
            esler.append({"ad": e.get("ad", "?"), "url": e["url"], "acik": acik})
        return {"makine": AYARLAR["makine"], "lider": bool(LIDER and LIDER.lider),
                "mdns": f'{AYARLAR["mdns_ad"]}.local' if AYARLAR["mdns"] else None, "esler": esler}

    def _yazma_izni(self):
        # CSRF korumasi: ozel baslik gerektirir (baska siteler bunu gonderemez)
        return self.headers.get("X-Vakum") == "1"

    # ---- GET ----
    def do_GET(self):
        yol = self.path.split("?")[0]
        try:
            if yol in ("/", "/index.html"):
                return self._gonder(200, SAYFA.read_bytes(), "text/html; charset=utf-8")
            if yol == "/harita.png":
                p = HARITA / "harita.png"
                if not p.exists():
                    return self._hata(404, "Harita yok")
                return self._gonder(200, p.read_bytes(), "image/png", "no-cache")
            if yol == "/api/harita":
                p = HARITA / "meta.json"
                if not p.exists():
                    return self._hata(404, "Harita yok. 'Haritayı yenile'ye bas.")
                return self._gonder(200, p.read_bytes())
            if yol == "/api/odalar":
                return self._json(200, odalar.oku())
            if yol == "/api/kimlik":
                return self._json(200, self._kimlik())
            if yol == "/api/senkron":
                if not self._senkron_izni():
                    return self._hata(403, "Yetkisiz")
                return self._json(200, odalar.oku_ham())
            if yol == "/api/durum":
                d = robot.durum()
                d["kuru"] = AYAR["kuru"]
                return self._json(200, d)
            self._hata(404, "Yok")
        except Exception as e:
            self._hata(502 if yol == "/api/durum" else 500, f"{type(e).__name__}: {e}")

    # ---- POST / DELETE ----
    def do_POST(self):
        self._yaz("POST")

    def do_DELETE(self):
        self._yaz("DELETE")

    def _yaz(self, metot):
        yol = self.path.split("?")[0]
        if metot == "POST" and yol == "/api/senkron":
            if not self._senkron_izni():
                return self._hata(403, "Yetkisiz")
            try:
                return self._json(200, odalar.uygula_uzak(self._govde(1_000_000)))
            except (ValueError, json.JSONDecodeError) as e:
                return self._hata(400, str(e))
        if not self._yazma_izni():
            return self._hata(403, "Yetkisiz istek")
        yol = self.path.split("?")[0]
        try:
            if metot == "POST" and yol == "/api/oda":
                r = odalar.kaydet_oda(self._govde())
                SENKRON.tetikle()
                return self._json(200, r)
            m = re.fullmatch(r"/api/oda/([0-9a-f]{8})", yol)
            if metot == "DELETE" and m:
                odalar.sil_oda(m.group(1))
                SENKRON.tetikle()
                return self._json(200, {"tamam": True})
            if metot == "POST" and yol == "/api/temizle":
                g = self._govde()
                oda = odalar.bul(str(g.get("oda_id", "")))
                return self._json(200, robot.temizle(oda, int(g.get("tekrar", 1)), kuru=AYAR["kuru"]))
            if metot == "POST" and yol == "/api/durdur":
                if not AYAR["kuru"]:
                    robot.durdur()
                return self._json(200, {"tamam": True, "gonderildi": not AYAR["kuru"]})
            if metot == "POST" and yol == "/api/istasyon":
                if not AYAR["kuru"]:
                    robot.istasyona_don()
                return self._json(200, {"tamam": True, "gonderildi": not AYAR["kuru"]})
            if metot == "POST" and yol == "/api/harita-yenile":
                with _harita_kilit:
                    r = subprocess.run([sys.executable, str(KOK / "harita.py")], capture_output=True,
                                       text=True, timeout=180, cwd=KOK)
                if r.returncode != 0:
                    return self._hata(502, (r.stdout or r.stderr).strip().splitlines()[-1][:300])
                return self._json(200, {"tamam": True})
            self._hata(404, "Yok")
        except KeyError as e:
            self._hata(404, str(e.args[0]))
        except (ValueError, json.JSONDecodeError) as e:
            self._hata(400, str(e))
        except Exception as e:
            self._hata(502, f"{type(e).__name__}: {e}")


def lan_ip():
    if AYARLAR.get("yayin_ip"):
        return AYARLAR["yayin_ip"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((robot.IP or "192.0.2.1", 9))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main():
    global SENKRON, LIDER
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(AYARLAR["port"]))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--kuru", action="store_true", help="robota komut gonderme (dry-run)")
    ap.add_argument("--tek", action="store_true", help="senkron ve vakum.local yayini kapali (test)")
    a = ap.parse_args()
    AYAR["kuru"] = a.kuru
    srv = ThreadingHTTPServer((a.host, a.port), Isleyici)
    ip = lan_ip()
    print(f"Hazır{' (KURU MOD: komut gönderilmez)' if a.kuru else ''}: http://{ip}:{a.port}", flush=True)
    if not a.tek:
        SENKRON = Senkron(AYARLAR, gunluk).baslat()
        if AYARLAR["mdns"] and ip != "127.0.0.1":
            LIDER = Lider(AYARLAR, ip, a.port, gunluk).baslat()
        gunluk(f"makine={AYARLAR['makine']} senkron={'acik' if SENKRON.acik else 'kapali'} "
               f"esler={len(AYARLAR['esler'])} mdns={'acik' if LIDER else 'kapali'}")

    def sonlandir(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, sonlandir)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if LIDER:
            LIDER.durdur()
        SENKRON.durdur()
        srv.server_close()


if __name__ == "__main__":
    main()
