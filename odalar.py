"""odalar.json okuma/yazma + makineler arasi birlestirme.
Kurallar (VERI KAYBI YOK):
- Her yazmadan once eski dosya .gizli/odalar-yedek/ altina zaman damgali yedeklenir.
- Hicbir oda fiziksel silinmez: silme = "silindi": true isareti (tombstone); ad/dikdortgenler korunur.
- Birlestirme oda id bazinda birlesim kumesidir; ayni id'de "guncelleme" (ms) buyuk olan kazanir.
- Icerik degismediyse dosyaya yazilmaz (yedek sismez)."""
import json
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import robot

KOK = Path(__file__).resolve().parent
ODALAR = Path(os.environ.get("VAKUM_ODALAR", KOK / "odalar.json"))
YEDEK = Path(os.environ.get("VAKUM_YEDEK", KOK / ".gizli" / "odalar-yedek"))
ID_RE = re.compile(r"[0-9a-f]{8}")
MAX_ODA = 500
_kilit = threading.RLock()


def oku_ham(yol: Path = ODALAR) -> dict:
    """Dosyanin tamami (silinmis isaretli odalar dahil)."""
    if not yol.exists():
        return {"odalar": []}
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri.setdefault("odalar", [])
    return veri


def oku(yol: Path = ODALAR) -> dict:
    """Arayuz icin: yalniz silinmemis odalar."""
    veri = oku_ham(yol)
    return {"odalar": [o for o in veri["odalar"] if not o.get("silindi")]}


def yedekle(yol: Path = ODALAR, yedek: Path = YEDEK):
    if not yol.exists():
        return None
    yedek.mkdir(parents=True, exist_ok=True)
    hedef = yedek / ("odalar-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
    shutil.copy2(yol, hedef)
    return hedef


def _yaz(veri: dict, yol: Path, yedek: Path):
    yedekle(yol, yedek)
    gecici = yol.with_name(yol.name + ".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(gecici, yol)


def _saat(onceki: int = 0) -> int:
    return max(int(time.time() * 1000), int(onceki or 0) + 1)


def _temizle_oda(girdi: dict) -> dict:
    ad = str(girdi.get("ad", "")).strip()
    if not ad or len(ad) > 40:
        raise ValueError("Oda adı 1-40 karakter olmalı")
    rects = robot.bolgeleri_dogrula(girdi.get("dikdortgenler", []), 1)
    return {"ad": ad, "dikdortgenler": [r[:4] for r in rects]}


def kaydet_oda(girdi: dict, yol: Path = ODALAR, yedek: Path = YEDEK) -> dict:
    """id varsa gunceller (yeniden adlandir/duzenle), yoksa yeni oda ekler."""
    oda = _temizle_oda(girdi)
    with _kilit:
        veri = oku_ham(yol)
        oid = girdi.get("id")
        if oid:
            for o in veri["odalar"]:
                if o["id"] == oid and not o.get("silindi"):
                    o.update(oda)
                    o["guncelleme"] = _saat(o.get("guncelleme"))
                    break
            else:
                raise KeyError("Oda bulunamadı")
        else:
            mevcut = {o["id"] for o in veri["odalar"]}
            oid = uuid.uuid4().hex[:8]
            while oid in mevcut:
                oid = uuid.uuid4().hex[:8]
            veri["odalar"].append({"id": oid, **oda, "guncelleme": _saat()})
        _yaz(veri, yol, yedek)
        return next(o for o in veri["odalar"] if o["id"] == oid)


def sil_oda(oid: str, yol: Path = ODALAR, yedek: Path = YEDEK) -> None:
    """Fiziksel silme yok: odaya 'silindi' isareti konur (icerik dosyada kalir)."""
    if not ID_RE.fullmatch(oid or ""):
        raise KeyError("Oda bulunamadı")
    with _kilit:
        veri = oku_ham(yol)
        for o in veri["odalar"]:
            if o["id"] == oid and not o.get("silindi"):
                o["silindi"] = True
                o["guncelleme"] = _saat(o.get("guncelleme"))
                break
        else:
            raise KeyError("Oda bulunamadı")
        _yaz(veri, yol, yedek)


def bul(oid: str, yol: Path = ODALAR) -> dict:
    for o in oku(yol)["odalar"]:
        if o["id"] == oid:
            return o
    raise KeyError("Oda bulunamadı")


# ---------------- birlestirme (senkron) ----------------
def dogrula_uzak(veri) -> list:
    """Karsi makineden gelen odalari dogrular; gecersiz kayitlar atlanir (yerelde hicbir sey silinmez)."""
    if not isinstance(veri, dict) or not isinstance(veri.get("odalar"), list):
        raise ValueError("Geçersiz senkron verisi")
    if len(veri["odalar"]) > MAX_ODA:
        raise ValueError("Çok fazla oda")
    temiz = []
    for o in veri["odalar"]:
        try:
            oid = str(o["id"])
            if not ID_RE.fullmatch(oid):
                continue
            g = int(o.get("guncelleme", 0))
            if g < 0:
                continue
            kayit = {"id": oid, **_temizle_oda(o)}
            if "guncelleme" in o:
                kayit["guncelleme"] = g
            if o.get("silindi") is True:
                kayit["silindi"] = True
            temiz.append(kayit)
        except (KeyError, TypeError, ValueError):
            continue
    return temiz


def _anahtar(o: dict):
    return (int(o.get("guncelleme", 0)), json.dumps(o, sort_keys=True, ensure_ascii=False))


def birlestir(yerel: list, uzak: list) -> list:
    """id bazinda birlesim. Ayni id: guncelleme buyuk olan (esitse deterministik) kazanir.
    Yerel sira korunur, yalniz uzakta olanlar sona eklenir. Hicbir id dusurulmez."""
    secim = {}
    sira = []
    for o in list(yerel) + list(uzak):
        oid = o["id"]
        if oid not in secim:
            secim[oid] = o
            sira.append(oid)
        elif _anahtar(o) > _anahtar(secim[oid]):
            secim[oid] = o
    return [secim[i] for i in sira]


def esit(a: list, b: list) -> bool:
    k = lambda L: sorted(json.dumps(o, sort_keys=True, ensure_ascii=False) for o in L)
    return k(a) == k(b)


def uygula_uzak(uzak_veri, yol: Path = ODALAR, yedek: Path = YEDEK) -> dict:
    """Uzak veriyi yerelle birlestirir; degisiklik varsa (yedek alip) yazar. Donus: birlesmis ham veri."""
    uzak = dogrula_uzak(uzak_veri)
    with _kilit:
        veri = oku_ham(yol)
        yeni = birlestir(veri["odalar"], uzak)
        # guvenlik: birlesim yereldeki her id'yi icermeli
        assert {o["id"] for o in veri["odalar"]} <= {o["id"] for o in yeni}
        if not esit(yeni, veri["odalar"]):
            veri["odalar"] = yeni
            _yaz(veri, yol, yedek)
        return veri
