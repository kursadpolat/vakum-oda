"""Turkce ses paketi uretir (Gemini TTS) ve gen1 (rockrobo.vacuum.v1) formatinda paketler.
Calistir: .venv/bin/python ses_paketi.py [--yeniden] [--ses Kore] [--sadece start.wav,home.wav]
Gereken: ffmpeg, ccrypt (brew install ffmpeg ccrypt), Gemini anahtari: GEMINI_API_KEY ortam degiskeni
ya da .gizli/gemini.key (repoya GIRMEZ).
Paket formati (dustcloud / Valetudo ile ayni): koke *.wav konmus tar.gz, ccrypt ile sifreli,
anahtar gen1 sabiti "r0ckrobo#23456". Dosya adlari -> cumle eslesmesi: ses/metinler.csv
(dustcloud audio_generator dil dosyalarindaki dosya adi listesi; Turkce metinler bu projeye ozgu).
Cikti: .gizli/ses/wav/*.wav, .gizli/ses/tr.pkg (+ .md5). Var olan wav'lar yeniden uretilmez (--yeniden haric)."""
import argparse
import base64
import csv
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import time
import wave
from pathlib import Path

import requests

KOK = Path(__file__).resolve().parent
METINLER = KOK / "ses" / "metinler.csv"
CIKTI = KOK / ".gizli" / "ses"
WAV_DIZIN = CIKTI / "wav"
PAKET = CIKTI / "tr.pkg"
SES_SIFRE = "r0ckrobo#23456"     # gen1 ses paketi ccrypt anahtari (herkese acik, dustcloud)
MODEL = "gemini-3.8-flash-lite-tts"
# Not: metnin onune stil talimati eklenmez; model talimati da sesli okuyor (olculdu: 1.9 sn yerine 10 sn).
# Sicaklik ses seciminden gelir (Sulafat: "warm").
VARSAYILAN_SES = "Sulafat"


def gemini_anahtar() -> str:
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        p = KOK / ".gizli" / "gemini.key"
        if p.exists():
            k = p.read_text().strip()
    if not k:
        raise SystemExit("Gemini anahtari yok: GEMINI_API_KEY ya da .gizli/gemini.key")
    return k


def metinler() -> list[tuple[str, str]]:
    with open(METINLER, encoding="utf-8", newline="") as f:
        return [(r[0].strip(), r[1].strip()) for r in csv.reader(f, skipinitialspace=True) if len(r) >= 2]


class Kota(RuntimeError):
    """Gunluk ucretsiz kota doldu (yeniden denemek anlamsiz)."""


def tts(metin: str, ses: str, anahtar: str, model: str = None) -> tuple[bytes, str]:
    """Gemini TTS -> (ses baytlari, mimeType). Gecici hatada bekleyip tekrar dener; gunluk kota dolduysa Kota."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or MODEL}:generateContent"
    govde = {"contents": [{"parts": [{"text": metin}]}],
             "generationConfig": {"responseModalities": ["AUDIO"],
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": ses}}}}}
    for deneme in range(6):
        r = requests.post(url, json=govde, headers={"x-goog-api-key": anahtar}, timeout=120)
        if r.status_code == 200:
            for p in r.json()["candidates"][0]["content"]["parts"]:
                if "inlineData" in p:
                    return base64.b64decode(p["inlineData"]["data"]), p["inlineData"].get("mimeType", "")
            raise RuntimeError("Gemini yanitinda ses yok")
        if r.status_code == 429 and "free_tier_requests" in r.text and "PerDay" in r.text:
            raise Kota(f"{model or MODEL}: gunluk ucretsiz istek kotasi doldu")
        if r.status_code in (429, 500, 503):
            time.sleep(15 * (deneme + 1))
            continue
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
    raise RuntimeError("Gemini kota/gecici hata: tekrar deneme bitti")


def pcm_ayikla(veri: bytes, mime: str) -> tuple[bytes, int]:
    """Ham PCM + ornek hizi. Model hazir WAV donerse (sonunda C2PA blogu olabilir) yalniz data bolumu alinir;
    ustune ikinci baslik eklenmez (aksi halde basta tik, sonda gurultu olur)."""
    if veri[:4] == b"RIFF":
        with wave.open(io.BytesIO(veri)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise RuntimeError("beklenmeyen WAV formati")
            return w.readframes(w.getnframes()), w.getframerate()
    hiz = 24000
    for parca in mime.split(";"):
        if parca.strip().startswith("rate="):
            hiz = int(parca.split("=")[1])
    return veri, hiz


def wav_yaz(pcm: bytes, hiz: int, hedef: Path):
    """ffmpeg: bas/son sessizligi kirp, 10 ms fade, sesi normalle, 16 bit mono 22050 Hz WAV."""
    hedef.parent.mkdir(parents=True, exist_ok=True)
    filtre = ("silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
              "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
              "afade=t=in:d=0.01,areverse,afade=t=in:d=0.03,areverse,"
              "loudnorm=I=-14:TP=-1.5:LRA=11,apad=pad_dur=0.15")
    gecici = hedef.with_suffix(".tmp.wav")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(hiz),
                        "-ac", "1", "-i", "pipe:0", "-af", filtre, "-ar", "22050", "-ac", "1",
                        "-c:a", "pcm_s16le", str(gecici)], input=pcm, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr.decode()[-200:])
    os.replace(gecici, hedef)


def paketle(dosyalar: list[str]) -> str:
    """wav'lari tar.gz yapar, ccrypt ile sifreler. md5 dondurur."""
    if not shutil.which("ccrypt"):
        raise SystemExit("ccrypt yok: brew install ccrypt")
    tgz = io.BytesIO()
    with tarfile.open(fileobj=tgz, mode="w:gz", format=tarfile.USTAR_FORMAT) as t:
        for ad in dosyalar:
            bilgi = t.gettarinfo(str(WAV_DIZIN / ad), arcname=ad)
            bilgi.uid = bilgi.gid = 0
            bilgi.uname = bilgi.gname = "root"
            bilgi.mode = 0o644
            with open(WAV_DIZIN / ad, "rb") as f:
                t.addfile(bilgi, f)
    r = subprocess.run(["ccrypt", "-e", "-K", SES_SIFRE], input=tgz.getvalue(), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ccrypt: " + r.stderr.decode()[-200:])
    PAKET.write_bytes(r.stdout)
    md5 = hashlib.md5(r.stdout).hexdigest()
    (CIKTI / "tr.pkg.md5").write_text(md5)
    # dogrulama: geri coz, ayni arsiv mi
    g = subprocess.run(["ccrypt", "-d", "-K", SES_SIFRE], input=r.stdout, capture_output=True)
    if g.returncode != 0 or g.stdout != tgz.getvalue():
        raise RuntimeError("paket dogrulamasi basarisiz (ccrypt geri cozme)")
    return md5


# ---- toplu uretim: ucretsiz kota gunde ~10 istek/model; 96 cumle bir kac istekte uretilir, sonra bolunur ----
HAM_DIZIN = CIKTI / "ham"
SAYI = {1: "bir", 2: "iki", 3: "üç", 4: "dört", 5: "beş", 6: "altı", 7: "yedi", 8: "sekiz", 9: "dokuz", 10: "on",
        20: "yirmi", 30: "otuz"}


def _sayi_yaz(n: int) -> str:
    if n in SAYI:
        return SAYI[n]
    if n < 40:
        return SAYI[n // 10 * 10] + " " + SAYI[n % 10]
    return str(n)


def kelimeler(metin: str) -> list[str]:
    import re
    t = metin.replace("İ", "i").replace("I", "ı").lower()
    t = re.sub(r"\d+", lambda m: " " + _sayi_yaz(int(m.group())) + " ", t)
    return re.findall(r"[a-zçğıöşü]+", t)


def whisper_kelimeler(wav: Path, onek: str) -> list[dict]:
    """mlx_whisper (CLI) ile kelime zamanlari: [{"k": kelime, "bas": sn, "son": sn}]."""
    import json as _json
    import tempfile
    cikis = Path(tempfile.mkdtemp())
    r = subprocess.run(["mlx_whisper", str(wav), "--model", "mlx-community/whisper-large-v3-turbo", "--language", "tr",
                        "--word-timestamps", "True", "--output-format", "json", "--output-dir", str(cikis),
                        ], capture_output=True, text=True)   # initial-prompt bilerek yok: uzun kayitta kelimeleri yutuyordu
    if r.returncode != 0:
        raise RuntimeError("mlx_whisper: " + r.stderr[-200:])
    veri = _json.loads((cikis / (wav.stem + ".json")).read_text())
    sonuc = []
    for seg in veri["segments"]:
        for w in seg.get("words", []):
            for k in kelimeler(w["word"]):
                sonuc.append({"k": k, "bas": w["start"], "son": w["end"]})
    return sonuc


def bol(pcm: bytes, hiz: int, cumleler: list[str], hyp: list[dict]) -> list[bytes]:
    """Toplu kaydi cumlelere boler: beklenen kelimeler whisper kelimelerine hizalanir, kesim iki cumle
    arasindaki boslugun en sessiz 10 ms'ine yapilir. Esleme zayifsa RuntimeError (yarim cumle paketlenmesin)."""
    import array
    import difflib
    exp, sahip = [], []
    for i, c in enumerate(cumleler):
        for k in kelimeler(c):
            exp.append(k)
            sahip.append(i)
    es = {}
    sm = difflib.SequenceMatcher(None, exp, [h["k"] for h in hyp], autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for j in range(n):
            es[a + j] = b + j
    for i in range(len(cumleler)):
        idx = [j for j, s_ in enumerate(sahip) if s_ == i]
        oran = sum(1 for j in idx if j in es) / max(1, len(idx))
        if oran < 0.6:
            raise RuntimeError(f"cumle {i + 1} kayitta bulunamadi (eslesme %{round(oran * 100)}): {cumleler[i][:40]}")
    ornek = array.array("h", pcm)
    pencere = int(hiz * 0.01)

    def sessiz_nokta(bas_sn, son_sn):
        a, b = int(bas_sn * hiz), int(son_sn * hiz)
        if b - a < pencere:
            return (a + b) // 2
        en, enk = a, None
        for x in range(a, b - pencere, pencere // 2):
            e = sum(abs(v) for v in ornek[x:x + pencere])
            if enk is None or e < enk:
                en, enk = x, e
        return en + pencere // 2

    kesimler = [0]
    for i in range(len(cumleler) - 1):
        son_k = max(es[j] for j, s_ in enumerate(sahip) if s_ == i and j in es)
        ilk_k = min(es[j] for j, s_ in enumerate(sahip) if s_ == i + 1 and j in es)
        if ilk_k <= son_k:
            raise RuntimeError(f"cumle {i + 1}/{i + 2} sinirinda hizalama bozuk")
        bosluk_bas, bosluk_son = hyp[son_k]["son"], hyp[ilk_k]["bas"]
        if bosluk_son - bosluk_bas < 0.08:
            bosluk_bas, bosluk_son = bosluk_bas - 0.05, bosluk_son + 0.05
        kesimler.append(sessiz_nokta(bosluk_bas, bosluk_son))
    kesimler.append(len(ornek))
    return [ornek[kesimler[i]:kesimler[i + 1]].tobytes() for i in range(len(cumleler))]


def toplu_uret(isler: list[tuple[str, str]], ses: str, modeller: list[str], grup: int) -> int:
    HAM_DIZIN.mkdir(parents=True, exist_ok=True)
    anahtar = gemini_anahtar()
    uretilen = 0
    for g in range(0, len(isler), grup):
        parca = isler[g:g + grup]
        metin = "\n\n".join(m for _, m in parca)
        kimlik = hashlib.sha1((ses + "|" + metin).encode()).hexdigest()[:12]
        ham = HAM_DIZIN / f"grup-{kimlik}.wav"
        if not ham.exists():                      # ham kayit onbellekte: tekrar calistirmak kota yemez
            veri = mime = None
            for model in modeller:
                try:
                    veri, mime = tts(metin, ses, anahtar, model)
                    break
                except Kota as e:
                    print(f"KOTA: {e}", flush=True)
            if veri is None:
                print("tum modellerin gunluk kotasi doldu; yarin (TR ~10:00 sonrasi) tekrar calistir", flush=True)
                return uretilen
            pcm, hiz = pcm_ayikla(veri, mime)
            with wave.open(str(ham), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(hiz); w.writeframes(pcm)
        with wave.open(str(ham)) as w:
            hiz, pcm = w.getframerate(), w.readframes(w.getnframes())
        try:
            parcalar = bol(pcm, hiz, [m for _, m in parca], whisper_kelimeler(ham, metin))
        except RuntimeError as e:
            print(f"grup {g // grup + 1} bolunemedi ({e}); atlandi", flush=True)
            continue
        for (ad, _), p in zip(parca, parcalar):
            wav_yaz(p, hiz, WAV_DIZIN / ad)
            uretilen += 1
        print(f"grup {g // grup + 1}: {len(parca)} wav tamam", flush=True)
    return uretilen


def dogrula(liste: list[tuple[str, str]], rapor: Path) -> float:
    """Her wav'i whisper ile yaziya doker, beklenen cumleyle benzerlik orani; rapor dosyaya yazilir."""
    import difflib
    satirlar, oranlar = [], []
    for ad, metin in liste:
        hyp = " ".join(h["k"] for h in whisper_kelimeler(WAV_DIZIN / ad, metin))
        o = difflib.SequenceMatcher(None, " ".join(kelimeler(metin)), hyp).ratio()
        oranlar.append(o)
        satirlar.append(f"{o:.2f}\t{ad}\t{hyp}")
    rapor.write_text("\n".join(sorted(satirlar)), encoding="utf-8")
    return min(oranlar) if oranlar else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yeniden", action="store_true", help="var olan wav'lari da yeniden uret")
    ap.add_argument("--ses", default=VARSAYILAN_SES, help=f"Gemini ses adi (varsayilan {VARSAYILAN_SES})")
    ap.add_argument("--sadece", default="", help="virgulle dosya adlari (yalniz bunlari uret)")
    ap.add_argument("--grup", type=int, default=12, help="bir istekte kac cumle (1 = tek tek)")
    ap.add_argument("--modeller", default="gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts,gemini-3.1-flash-tts-preview",
                    help="sirayla denenecek TTS modelleri (kota dolunca bir sonrakine gecer)")
    ap.add_argument("--dogrula", action="store_true", help="paket oncesi tum wav'lari whisper ile kontrol et")
    a = ap.parse_args()
    liste = metinler()
    sadece = {s.strip() for s in a.sadece.split(",") if s.strip()}
    if sadece:
        isler = [(ad, m) for ad, m in liste if ad in sadece]
    else:
        isler = [(ad, m) for ad, m in liste if a.yeniden or not (WAV_DIZIN / ad).exists()]
    modeller = [m.strip() for m in a.modeller.split(",") if m.strip()]
    uretilen = 0
    if isler and a.grup > 1:
        uretilen += toplu_uret(isler, a.ses, modeller, a.grup)
        isler = []     # bolunemeyen grup tek tek denenmez (kota yer); gerekirse --sadece ... --grup 1
    if isler:
        anahtar = gemini_anahtar()
        for ad, metin in isler:
            veri = mime = None
            for model in modeller:
                try:
                    veri, mime = tts(metin, a.ses, anahtar, model)
                    break
                except Kota as e:
                    print(f"KOTA: {e}", flush=True)
            if veri is None:
                break
            pcm, hiz = pcm_ayikla(veri, mime)
            wav_yaz(pcm, hiz, WAV_DIZIN / ad)
            uretilen += 1
            print(f"{ad} tamam", flush=True)
    eksik = [ad for ad, _ in liste if not (WAV_DIZIN / ad).exists()]
    if eksik:
        print(f"uretilen={uretilen}; EKSIK {len(eksik)} wav, paket yapilmadi: {', '.join(eksik[:5])}")
        return 1
    if a.dogrula:
        en_kotu = dogrula(liste, CIKTI / "dogrulama.tsv")
        print(f"dogrulama: en dusuk benzerlik {en_kotu:.2f} (rapor .gizli/ses/dogrulama.tsv)", flush=True)
    md5 = paketle([ad for ad, _ in liste])
    print(f"uretilen={uretilen} toplam={len(liste)} paket={PAKET} md5={md5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
