"""Xiaomi bulut baglantisi (QR ile giris + sifreli API cagrisi).
Mantik PiotrMachowski/Xiaomi-cloud-tokens-extractor'dan uyarlandi. Gizli degerler asla yazdirilmaz."""
import base64
import hashlib
import hmac
import json
import os
import random
import time
from pathlib import Path

import requests
from Crypto.Cipher import ARC4

KOK = Path(__file__).resolve().parent
GIZLI = KOK / ".gizli"
OTURUM_DOSYASI = GIZLI / "bulut.json"
VARSAYILAN_SUNUCU = "tw"


def gizli_dizin() -> Path:
    GIZLI.mkdir(mode=0o700, exist_ok=True)
    return GIZLI


def gizli_yaz(yol: Path, veri: bytes) -> None:
    """Dosyayi 600 izniyle (atomik) yazar."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".tmp")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(veri)
    os.chmod(gecici, 0o600)
    os.replace(gecici, yol)


class BulutBaglanti:
    def __init__(self, sunucu: str = VARSAYILAN_SUNUCU):
        self.sunucu = sunucu
        self._agent = self._ajan()
        self._session = requests.session()
        self.user_id = None
        self._ssecurity = None
        self._service_token = None

    # ---- oturum kaydet / yukle ----
    def kaydet(self, yol: Path = OTURUM_DOSYASI) -> None:
        veri = {"userId": str(self.user_id), "ssecurity": self._ssecurity,
                "serviceToken": self._service_token, "server": self.sunucu,
                "zaman": int(time.time())}
        gizli_yaz(yol, json.dumps(veri).encode())

    @classmethod
    def yukle(cls, yol: Path = OTURUM_DOSYASI) -> "BulutBaglanti":
        if not yol.exists():
            raise RuntimeError("Bulut oturumu yok. Once: .venv/bin/python bulut_giris.py")
        v = json.loads(yol.read_text())
        b = cls(v.get("server", VARSAYILAN_SUNUCU))
        b.user_id, b._ssecurity, b._service_token = v["userId"], v["ssecurity"], v["serviceToken"]
        return b

    # ---- QR giris ----
    def qr_giris_baslat(self) -> bytes:
        """QR PNG/JPG baytlarini dondurur, long-polling bilgilerini saklar."""
        r = self._session.get("https://account.xiaomi.com/longPolling/loginUrl", params={
            "_qrsize": "480", "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts", "_hasLogo": "false",
            "sid": "xiaomiio", "serviceParam": "", "_locale": "en_GB",
            "_dc": str(int(time.time() * 1000))}, timeout=20)
        d = self._json(r.text)
        if r.status_code != 200 or "qr" not in d:
            raise RuntimeError("QR istegi basarisiz")
        self._lp, self._lp_timeout, self.login_url = d["lp"], d.get("timeout", 300), d["loginUrl"]
        img = self._session.get(d["qr"], timeout=20)
        if img.status_code != 200:
            raise RuntimeError("QR gorseli indirilemedi")
        return img.content

    def qr_giris_bekle(self) -> None:
        bas = time.time()
        r = None
        while time.time() - bas < self._lp_timeout + 30:
            try:
                r = self._session.get(self._lp, timeout=10)
            except requests.exceptions.Timeout:
                continue
            if r.status_code == 200:
                break
            time.sleep(2)
        if r is None or r.status_code != 200:
            raise RuntimeError("QR zaman asimi: telefonla okutulmadi")
        d = self._json(r.text)
        self.user_id, self._ssecurity = d["userId"], d["ssecurity"]
        r2 = self._session.get(d["location"], headers={"content-type": "application/x-www-form-urlencoded"}, timeout=20)
        if r2.status_code != 200 or "serviceToken" not in r2.cookies:
            raise RuntimeError("serviceToken alinamadi")
        self._service_token = r2.cookies["serviceToken"]

    # ---- sifreli API ----
    def api_url(self) -> str:
        return "https://" + ("" if self.sunucu == "cn" else self.sunucu + ".") + "api.io.mi.com/app"

    def api(self, yol: str, veri: dict) -> dict:
        url = self.api_url() + yol
        params = {"data": json.dumps(veri)}
        headers = {"Accept-Encoding": "identity", "User-Agent": self._agent,
                   "Content-Type": "application/x-www-form-urlencoded",
                   "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
                   "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4"}
        cookies = {"userId": str(self.user_id), "yetAnotherServiceToken": str(self._service_token),
                   "serviceToken": str(self._service_token), "locale": "en_GB", "timezone": "GMT+02:00",
                   "is_daylight": "1", "dst_offset": "3600000", "channel": "MI_APP_STORE"}
        nonce = self._nonce(round(time.time() * 1000))
        sn = self._signed_nonce(nonce)
        alanlar = self._enc_params(url, "POST", sn, nonce, params, self._ssecurity)
        r = self._session.post(url, headers=headers, cookies=cookies, params=alanlar, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Bulut API HTTP {r.status_code} (oturum suresi dolmus olabilir)")
        return json.loads(self._rc4_coz(self._signed_nonce(alanlar["_nonce"]), r.text))

    # ---- yardimcilar ----
    @staticmethod
    def _json(t):
        return json.loads(t.replace("&&&START&&&", ""))

    @staticmethod
    def _ajan():
        a = "".join(chr(random.randint(65, 69)) for _ in range(13))
        t = "".join(chr(random.randint(97, 122)) for _ in range(18))
        return f"{t}-{a} APP/com.xiaomi.mihome APPV/10.5.201"

    @staticmethod
    def _nonce(ms):
        return base64.b64encode(os.urandom(8) + int(ms / 60000).to_bytes(4, "big")).decode()

    def _signed_nonce(self, nonce):
        return base64.b64encode(hashlib.sha256(base64.b64decode(self._ssecurity) + base64.b64decode(nonce)).digest()).decode()

    @staticmethod
    def _imza(url, method, sn, params):
        p = [method.upper(), url.split("com")[1].replace("/app/", "/")]
        p += [f"{k}={v}" for k, v in params.items()]
        p.append(sn)
        return base64.b64encode(hashlib.sha1("&".join(p).encode()).digest()).decode()

    @classmethod
    def _enc_params(cls, url, method, sn, nonce, params, ssecurity):
        params["rc4_hash__"] = cls._imza(url, method, sn, params)
        for k, v in list(params.items()):
            params[k] = cls._rc4_sifrele(sn, v)
        params.update({"signature": cls._imza(url, method, sn, params), "ssecurity": ssecurity, "_nonce": nonce})
        return params

    @staticmethod
    def _rc4_sifrele(sifre, yuk):
        r = ARC4.new(base64.b64decode(sifre)); r.encrypt(bytes(1024))
        return base64.b64encode(r.encrypt(yuk.encode())).decode()

    @staticmethod
    def _rc4_coz(sifre, yuk):
        r = ARC4.new(base64.b64decode(sifre)); r.encrypt(bytes(1024))
        return r.encrypt(base64.b64decode(yuk))
