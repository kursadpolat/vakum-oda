# Süpürge oda oda temizlik (Xiaomi Gen1, rockrobo.vacuum.v1)

Yerel (LAN) web sayfası: haritada alan çiz, odaya ad ver, tek tuşla sadece o odayı temizlet.
Robota yalnızca resmi uygulamanın da kullandığı standart miio komutları gider: `get_status`, `get_map_v1`, `app_zoned_clean`, `app_stop`, `app_charge`
ve ses paketi için `get_current_sound`, `get_sound_volume`, `get_sound_progress`, `dnld_install_sound` (liste: `robot.py` `IZINLI`).
Zamanlanmış/otomatik temizlik yoktur ve eklenmeyecek: temizliği yalnız sayfadaki düğme başlatır.

İki makinede çalışır (ör. Mac = asıl, Windows PC = yedek). Hangisi açıksa telefon tek adresle ona ulaşır:
**http://vakum.local:8765** (iPhone `.local` adlarını çözer; Android çözmeyebilir, o zaman doğrudan IP adresini kullan,
sayfanın altında iki makinenin doğrudan linki de yazar).

## Nasıl çalışır
- **Ayarlar** `.gizli/ayar.json` içinde (örnek: `ayar.ornek.json`). Kodda IP/anahtar yoktur.
- **vakum.local**: yalnız lider makine yayınlar (Python `zeroconf`). `oncelik` en küçük olan (Mac) asıl liderdir.
  Yedek makine, asıl liderin 8765 portu `devralma_hata_sayisi` (3) ardışık kontrolde (5 sn arayla) yanıt vermezse
  yayını devralır; asıl lider geri gelince bırakır. İki makinede de sunucu hep çalışır; robota komutu yalnız isteği alan makine gönderir.
- **Odalar senkronu**: her kayıt/silmede `odalar.json` karşı makineye iletilir; ayrıca açılışta ve 30 sn'de bir karşılaştırılır.
  Birleştirme oda id bazındadır, en yeni `guncelleme` kazanır. **Hiçbir oda fiziksel silinmez**: "Sil" odaya `silindi: true`
  işareti koyar, ad ve alanlar dosyada kalır. Her üzerine yazmadan önce eski dosya `.gizli/odalar-yedek/` altına zaman damgalı yedeklenir;
  içerik değişmediyse dosyaya yazılmaz. Senkron uç noktası (`/api/senkron`) yalnız `senkron_anahtar` bilen makineye açıktır.

## Kurulum (bir kez, asıl makine)
```
cd vakum-oda
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install --no-deps python-miio==0.5.12
cp ayar.ornek.json .gizli/ayar.json   # robot_ip, esler (karşı makinenin adresi), makine, oncelik doldur
.venv/bin/python -c "import secrets;print(secrets.token_urlsafe(32))"   # çıkan anahtarı iki makinenin ayar.json'una aynı yaz
.venv/bin/python bulut_giris.py     # .gizli/qr.png oluşur, telefondaki Mi Home ile okut
.venv/bin/python harita.py          # haritayı indirir (robot temizlikte değilken)
```
`.gizli/` altında token/oturum/anahtar var; paylaşma, git'e koyma. Robot token'ı `.gizli/vac.token` dosyasındadır.

### Mac: otomatik başlatma (LaunchAgent)
```
bash kurulum/mac-kur.sh     # ~/Library/LaunchAgents/com.vakumoda.sunucu.plist; oturum açılınca başlar, çökerse yeniden başlar
```
Durdur/başlat: `launchctl bootout gui/$(id -u)/com.vakumoda.sunucu` / `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vakumoda.sunucu.plist`.
Günlük: `.gizli/sunucu.log`. İlk açılışta macOS güvenlik duvarı Python için izin sorarsa "İzin ver".

### Windows (yedek makine)
1. Proje klasörünü `.gizli/` ile birlikte kopyala (ör. `C:\Users\<kullanıcı>\vakum-oda`). `odalar.json`'u asıl makineden kopyala (ilk kopya kaynaktan gider).
2. `.gizli\ayar.json`: `"makine": "Monster"`, `"oncelik": 2`, `esler` = asıl makinenin adresi, aynı `senkron_anahtar`.
3. Python 3.12+ (yoksa `winget install Python.Python.3.12`), sonra:
```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install --no-deps python-miio==0.5.12
powershell -ExecutionPolicy Bypass -File kurulum\windows-kur.ps1
```
`windows-kur.ps1`: oturum açılınca gizli pencerede başlayan "VakumOda" görevi (bekci.py, çökerse yeniden başlatır) ve
güvenlik duvarında 8765/TCP + 5353/UDP (mDNS) gelen kuralları (Özel ağ). Kural için yönetici PowerShell gerekir.

## Elle çalıştırma / deneme
```
.venv/bin/python sunucu.py          # ayar.json'a göre: senkron + vakum.local
.venv/bin/python sunucu.py --kuru   # robota komut GÖNDERMEZ, sadece üretilen komutu gösterir
.venv/bin/python sunucu.py --tek    # senkron ve vakum.local kapalı
```
Makineler ve telefon aynı Wi-Fi'de olmalı. Makinelerin IP'si değişmesin diye modemde DHCP rezervasyonu önerilir.

## Kullanım
1. "+ Yeni oda": haritada parmakla sürükleyip dikdörtgen çiz (oda başına 1-5), adını yaz, Kaydet.
2. Oda düğmesi "Temizle: ..." onay sorar, sonra gider. "Tekrar" (1-3) en üstten seçilir.
3. Düzenle/Sil her odanın yanında. Silinen oda dosyada `silindi` işaretiyle durur; eski hâller `.gizli/odalar-yedek/` altında.
4. "Haritayı yenile": robot temizlik yaparken harita alınamaz ("retry"), bitince dene. Harita her makinede ayrı indirilir.

## Canlı harita
Sayfa açıkken robotun anlık yeri (R) ve temizlikte geçtiği yol (mavi çizgi) haritada görünür; kayıtlı odalar üstte çizilir.
Sunucu, biri sayfayı izliyorsa (`/api/canli` son 30 sn içinde istendiyse) `get_map_v1` + Xiaomi bulutundan haritayı çeker:
temizlikte ~5 sn, beklemede 30 sn arayla. Harita yalnız bellekte tutulur, kayıtlı harita (`.gizli/harita/`) değişmez.
Robot bağlantısı başka komutla meşgulse canlı harita o turu atlar, temizlik/durdur komutlarını geciktirmez.
**Bulut girişi düşerse** sayfada "Bulut girişi düştü" yazar, canlı harita durur, son görüntü kalır; temizlik komutları bulutu
kullanmadığı için etkilenmez. Yeniden giriş: `.venv/bin/python bulut_giris.py` (sunucuyu yeniden başlatmak gerekmez, 60 sn içinde toparlar).
Oda çizerken canlı güncelleme durur (çizim kaymasın).

## Telegram bildirimi
"Temizlik bitti (alan, süre)" ve "Robot sıkıştı / hata: <Türkçe açıklama> (kod N)" mesajları gelir. Sunucu 10 sn'de bir
`get_status` okur; temizlik durumundan istasyona dönüş/şarja geçişte "bitti", hata kodu 0'dan farklı bir koda geçince "hata"
gönderilir (aynı hata tekrar gönderilmez; "Durdur" ile durdurulan temizlik için "bitti" denmez).
**Çift bildirim olmaz:** iki makine de durumu izler ama yalnız yetkili gönderir: asıl lider (Mac) her zaman, yedek (Monster)
yalnız Mac kapalıyken yayını devraldığında. Ayar `.gizli/telegram.json`: `{"bot_token": "...", "chat_id": "..."}`
(BotFather'dan token, chat id için bota bir mesaj atıp `getUpdates`). Dosya yoksa bildirim kapalıdır.
Test: `.venv/bin/python bildirim.py "deneme"`. Hata metinleri `robot.py` `HATALAR`.

## Türkçe ses paketi
`ses/metinler.csv`: gen1 ses dosyası adı -> Türkçe cümle (dosya adları dustcloud ses üreticisi listesinden; metinler bu projenin).
```
brew install ffmpeg ccrypt
.venv/bin/python ses_paketi.py      # Gemini TTS (GEMINI_API_KEY ya da .gizli/gemini.key) -> .gizli/ses/wav + .gizli/ses/tr.pkg
.venv/bin/python ses_yukle.py       # önce .gizli/yedek/ses-<zaman>.json yedeği, sonra yükleme + get_sound_progress takibi
```
Paket formatı: kökte `*.wav` olan tar.gz, `ccrypt` ile gen1 anahtarıyla şifreli (dustcloud/Valetudo ile aynı). Robot paketi bu makinedeki
geçici bir HTTP sunucusundan indirir; `dnld_install_sound {url, md5, sid: 10000}`. Robot temizlikteyse yükleme yapılmaz.
Ücretsiz Gemini kotası model başına günde ~10 istek olduğu için cümleler 12'li gruplar hâlinde tek istekte okutulur, kayıt
`mlx_whisper` kelime zamanlarıyla cümlelere bölünür (eşleşme zayıfsa grup atlanır, yarım cümle paketlenmez); ham kayıtlar
`.gizli/ses/ham/` önbelleğinde durur, tekrar çalıştırmak kota yemez. `--dogrula` her wav'ı yazıya döküp `.gizli/ses/dogrulama.tsv` yazar.
Tek cümleyi değiştirmek: `metinler.csv`'yi düzelt, `ses_paketi.py --sadece start.wav --grup 1`, sonra `ses_yukle.py`.

**Geri dönüş (eski sese):** yedek dosyasında eski `sid_in_use`/`language` ve ses seviyesi yazar (yükleme öncesi: İngilizce, sid 3).
1. Mi Home uygulaması > robot > Ayarlar > Sesli bildirim/Ses paketi > İngilizce (ya da istediğin dil) seç: resmi paket buluttan yeniden kurulur.
2. Ses seviyesi değiştiyse aynı ekrandan yedekteki değere getir. Robota başka bir şey yazılmaz; oda verileri bu işlemden etkilenmez.

## Uyarı
Odalar robotun harita koordinatına (mm) kaydedilir. İstasyonu (dock) taşırsan robot yeni harita çıkarır ve kayıtlı odalar kayar;
o zaman haritayı yenile ve odaları yeniden çiz/düzelt (eski hâlini `.gizli/odalar-yedek/`ten geri alabilirsin).

## Dosyalar
`ayar.py` ayarlar, `senkron.py` makineler arası odalar senkronu, `lider.py` vakum.local yayını/devralma, `bekci.py` Windows bekçisi,
`kurulum/` Mac LaunchAgent ve Windows görev betikleri, `bulut_giris.py` QR girişi, `bulut.py` bulut API, `harita.py` harita indir/PNG,
`koord.py` piksel↔mm, `robot.py` robot komutları, `odalar.py` odalar.json + yedek + birleştirme, `sunucu.py` + `sayfa.html` arayüz,
`canli.py` canlı harita, `bildirim.py` Telegram bildirimi, `ses_paketi.py` / `ses_yukle.py` / `ses/metinler.csv` Türkçe ses paketi,
`test_*.py` robota ve gerçek dosyalara dokunmayan testler.

## Güvenlik

Bu sunucu yalnızca ev içi ağ (LAN) için tasarlandı; kimlik doğrulaması yoktur. Modemden port yönlendirme yapıp **internete açmayın**. Token ve oturum bilgileri `.gizli/` altında tutulur ve repoya girmez.
