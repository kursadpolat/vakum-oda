"""Robot haritasini indirir ve PNG + koordinat meta'sina cevirir.
Calistir: .venv/bin/python harita.py            (robot + bulut oturumu gerekir)
          .venv/bin/python harita.py --dosya X  (yerel ham/gzip harita dosyasindan)"""
import argparse
import gzip
import json
import sys
from io import BytesIO
from pathlib import Path

import requests
from vacuum_map_parser_base.config.color import ColorsPalette
from vacuum_map_parser_base.config.image_config import ImageConfig
from vacuum_map_parser_base.config.size import Sizes
from vacuum_map_parser_roborock.map_data_parser import RoborockMapDataParser

from bulut import GIZLI, BulutBaglanti, gizli_yaz

HARITA_DIZIN = GIZLI / "harita"
OLCEK = 4  # PNG buyutme (1 harita pikseli = 50 mm = 4 PNG pikseli)


def indir_ham(harita_adi: str) -> bytes:
    """Bulut oturumuyla harita dosyasini indirir (gzip'li ham bayt)."""
    b = BulutBaglanti.yukle()
    r = b.api("/home/getmapfileurl", {"obj_name": harita_adi})
    url = (r.get("result") or {}).get("url")
    if not url:
        raise RuntimeError("Harita URL'si alinamadi (bulut yaniti bos; robot bu hesapta mi?)")
    d = requests.get(url, timeout=60)
    if d.status_code != 200:
        raise RuntimeError(f"Harita indirilemedi: HTTP {d.status_code}")
    return d.content


def isle(veri: bytes):
    """gzip'li veya ham Roborock harita baytlarini -> (PNG baytlari, meta dict)."""
    if veri[:2] == b"\x1f\x8b":
        veri = gzip.decompress(veri)
    parser = RoborockMapDataParser(ColorsPalette(), Sizes(), [], ImageConfig(), [])
    md = parser.parse(veri)
    if md.image is None or md.image.is_empty:
        raise RuntimeError("Haritada görüntü bloğu yok")
    dim = md.image.dimensions
    img = md.image.data.convert("RGBA")
    w, h = img.size
    img = img.resize((w * OLCEK, h * OLCEK), resample=0)  # NEAREST
    buf = BytesIO()
    img.save(buf, "PNG")
    meta = {"left": dim.left, "top": dim.top, "h": dim.height, "w": dim.width, "olcek": OLCEK,
            "png_w": w * OLCEK, "png_h": h * OLCEK, "mm_piksel": 50,
            "dock": [md.charger.x, md.charger.y] if md.charger else None,
            "robot": [md.vacuum_position.x, md.vacuum_position.y] if md.vacuum_position else None}
    return buf.getvalue(), meta


def kaydet(png: bytes, meta: dict, ham: bytes | None = None) -> None:
    gizli_yaz(HARITA_DIZIN / "harita.png", png)
    gizli_yaz(HARITA_DIZIN / "meta.json", json.dumps(meta).encode())
    if ham is not None:
        gizli_yaz(HARITA_DIZIN / "harita.bin", ham)


def yenile() -> dict:
    import robot
    ad = robot.harita_adi()
    ham = indir_ham(ad)
    png, meta = isle(ham)
    kaydet(png, meta, ham)
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dosya", help="yerel harita dosyasi (indirme yerine)")
    a = ap.parse_args()
    try:
        if a.dosya:
            ham = Path(a.dosya).read_bytes()
            png, meta = isle(ham)
            kaydet(png, meta, ham)
        else:
            meta = yenile()
    except Exception as e:
        print(f"HATA: {e}")
        return 1
    print(f"Harita kaydedildi: {HARITA_DIZIN}/harita.png ({meta['png_w']}x{meta['png_h']}) dock={meta['dock']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
