"""Xiaomi bulutuna QR ile giris. Calistir: .venv/bin/python bulut_giris.py [--sunucu tw]
QR'i .gizli/qr.png olarak kaydeder; Mi Home uygulamasi (veya Xiaomi hesabi QR okuyucusu) ile okut."""
import argparse
import sys

from bulut import GIZLI, OTURUM_DOSYASI, BulutBaglanti, gizli_dizin, gizli_yaz


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sunucu", default="tw", help="hesap sunucusu (varsayilan tw)")
    a = ap.parse_args()
    gizli_dizin()
    b = BulutBaglanti(a.sunucu)
    qr = b.qr_giris_baslat()
    yol = GIZLI / "qr.png"
    gizli_yaz(yol, qr)
    print(f"QR kaydedildi: {yol}", flush=True)
    print("Telefonla okutup onayla; bekleniyor...", flush=True)
    try:
        b.qr_giris_bekle()
    except RuntimeError as e:
        print(f"HATA: {e}")
        return 1
    b.kaydet()
    try:
        yol.unlink()
    except OSError:
        pass
    print(f"Giris tamam, oturum kaydedildi: {OTURUM_DOSYASI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
