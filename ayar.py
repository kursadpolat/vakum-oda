"""Makineye ozel ayarlar: .gizli/ayar.json (ornek: ayar.ornek.json). Kodda gercek IP/anahtar tutulmaz.
Yol VAKUM_AYAR ortam degiskeniyle degistirilebilir. Dosya yoksa tek makine (esler yok, senkron kapali) calisir."""
import json
import os
from pathlib import Path

KOK = Path(__file__).resolve().parent
AYAR_DOSYASI = Path(os.environ.get("VAKUM_AYAR", KOK / ".gizli" / "ayar.json"))

VARSAYILAN = {
    "makine": "Bu makine",       # sayfada gorunen ad (pc-1 / pc-2)
    "oncelik": 1,                # 1 = asil lider; daha buyuk = yedek (dusuk oncelikli esler kapaliyken devralir)
    "port": 8765,
    "robot_ip": "",              # robotun LAN IP'si
    "mdns_ad": "vakum",          # <mdns_ad>.local
    "mdns": True,                # vakum.local yayini acik mi
    "yayin_ip": "",              # bos = robota giden arayuzun IP'si otomatik
    "esler": [],                 # [{"ad": "pc-2", "url": "http://IP:8765", "oncelik": 2}]
    "senkron_anahtar": "",       # esler arasinda paylasilan rastgele anahtar (bos = senkron kapali)
    "senkron_aralik_sn": 30,
    "kontrol_aralik_sn": 5,      # yedek makinenin lideri yoklama araligi
    "devralma_hata_sayisi": 3,   # ardisik bu kadar yanitsizlikta yedek devralir
}


def yukle(yol: Path = AYAR_DOSYASI) -> dict:
    a = dict(VARSAYILAN)
    if yol.exists():
        a.update(json.loads(yol.read_text(encoding="utf-8")))
    if os.environ.get("VAKUM_IP"):
        a["robot_ip"] = os.environ["VAKUM_IP"]
    a["esler"] = [dict(e, url=str(e["url"]).rstrip("/"), oncelik=int(e.get("oncelik", 1)))
                  for e in a.get("esler") or [] if e.get("url")]
    return a


AYAR = yukle()
