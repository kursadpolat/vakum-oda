# vakum-oda

[English](#english) | [Türkçe](#türkçe)

---

<a id="english"></a>
## English

Room-by-room cleaning for the **Xiaomi Mi Robot Vacuum 1st gen (`rockrobo.vacuum.v1`)** from a web page served on your local network (LAN): draw areas on the map, name them as rooms, and clean only that room with one tap.

The robot only receives standard miio commands, the same ones the official app uses: `get_status`, `get_map_v1`, `app_zoned_clean`, `app_pause`, `app_stop`, `app_charge`, plus `get_current_sound`, `get_sound_volume`, `get_sound_progress`, `dnld_install_sound` for the voice pack (whitelist: `IZINLI` in `robot.py`). There is **no scheduling or automatic cleaning**: a cleaning run starts only when you press a button on the page.

### Features
- Room-by-room cleaning: draw 1-5 rectangles per room on the map, name it, clean it (repeat 1-3 times, with a confirmation prompt).
- Live map: while the page is open it shows the robot's position (R) and its path during a run (about every 5 s while cleaning, 30 s while idle; fetched from the Xiaomi cloud).
- Telegram notifications: "cleaning finished (area, duration)" and "robot stuck / error: <description> (code N)".
- Turkish voice pack: generate with Gemini TTS, upload to the robot, and roll back to the stock voice.
- Two-machine redundancy: a primary and a backup machine share the room list and a `vakum.local` address; the backup takes over automatically when the primary is down.
- No data loss: "Delete" only marks a room as deleted, and every overwrite of the room file is backed up first.

### Requirements
- Xiaomi Mi Robot Vacuum 1st gen (`rockrobo.vacuum.v1`), on the same Wi-Fi as the server and your phone.
- Python 3.12+ (macOS or Windows; the install scripts target these).
- A Xiaomi account that the robot is paired with (Mi Home), used once to obtain the token.
- Optional: a Telegram bot, a Gemini API key and `ffmpeg` + `ccrypt` (voice pack).

### Installation (once, on the primary machine)
```
cd vakum-oda
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install --no-deps python-miio==0.5.12
mkdir -p .gizli && cp ayar.ornek.json .gizli/ayar.json   # fill in robot_ip, esler (the other machine), makine, oncelik
.venv/bin/python -c "import secrets;print(secrets.token_urlsafe(32))"   # put the same key in both machines' ayar.json
.venv/bin/python sunucu.py
```
Then open `http://<this-machine-ip>:8765` (or `http://vakum.local:8765` on devices that resolve `.local` names, e.g. iPhone; Android may not). A DHCP reservation on your router keeps the IPs stable.

Example `.gizli/ayar.json` (see `ayar.ornek.json`):
```
{
  "makine": "pc-1", "oncelik": 1, "port": 8765,
  "robot_ip": "192.168.x.x",
  "esler": [{"ad": "pc-2", "url": "http://192.168.x.x:8765", "oncelik": 2}],
  "senkron_anahtar": "<SHARED_RANDOM_KEY>"
}
```
Handy flags: `sunucu.py --kuru` (dry run: shows the command, sends nothing to the robot) and `sunucu.py --tek` (sync and `vakum.local` off).

macOS autostart (LaunchAgent, restarts on crash; log in `.gizli/sunucu.log`): `bash kurulum/mac-kur.sh`.

### Getting the token (QR cloud login)
```
.venv/bin/python bulut_giris.py     # creates .gizli/qr.png; scan it with the Mi Home app on your phone
.venv/bin/python harita.py          # downloads the map (while the robot is not cleaning)
```
The robot token is stored in `.gizli/vac.token` and the cloud session under `.gizli/`. If the cloud login expires the page shows "cloud login dropped", the live map stops (cleaning commands are unaffected, they do not use the cloud); run `bulut_giris.py` again, no restart needed.

### Telegram setup
1. Create a bot with BotFather and note the token. Send the bot one message, then open `getUpdates` to find your chat id.
2. Create `.gizli/telegram.json`:
```
{"bot_token": "<TOKEN>", "chat_id": "<CHAT_ID>"}
```
Without the file, notifications are off. Test: `.venv/bin/python bildirim.py "test"`. The server reads `get_status` every 10 s; an error message is sent once per error code. With two machines only the authorized one sends: the primary always, the backup only while it has taken over, so you never get duplicates.

### Turkish voice pack: build, upload, roll back
`ses/metinler.csv` maps each gen1 sound file name to a Turkish sentence.
```
brew install ffmpeg ccrypt
.venv/bin/python ses_paketi.py      # Gemini TTS (GEMINI_API_KEY or .gizli/gemini.key) -> .gizli/ses/wav + .gizli/ses/tr.pkg
.venv/bin/python ses_yukle.py       # backs up current settings to .gizli/yedek/, uploads, tracks get_sound_progress
```
The package is a tar.gz with `*.wav` at its root, encrypted with `ccrypt` using the gen1 key. The robot downloads it from a temporary HTTP server on your machine (`dnld_install_sound`). Upload is refused while the robot is cleaning. Sentences are generated in groups of 12 per request to stay within the free Gemini quota, and raw recordings are cached in `.gizli/ses/ham/`. Useful flags: `--dogrula`, `--yeniden`, `--sadece <file.wav> --grup 1`.

**Rolling back to the stock voice:** the backup file records the previous voice pack and volume. In Mi Home open your robot > Settings > Voice / Sound pack and pick English (or any language); the official pack is reinstalled from the cloud. Room data is not affected.

### Two-machine setup (primary + backup)
- Install on the second machine the same way, copy the project folder with `.gizli/`, set its own `makine`, `"oncelik": 2`, point `esler` to the primary and use the **same** `senkron_anahtar`.
- Only the leader announces `vakum.local` (zeroconf). The lowest `oncelik` is the primary. The backup takes over when the primary's port 8765 fails `devralma_hata_sayisi` (3) consecutive checks (5 s apart) and gives it back when the primary returns. Both servers always run; only the machine that receives a request talks to the robot.
- Room lists sync on every save/delete, at startup and every 30 s, merged per room id (latest `guncelleme` wins). The sync endpoint (`/api/senkron`) is open only to a machine that knows `senkron_anahtar`.
- Windows backup: install Python 3.12+, create `.venv` (`py -m venv .venv`, same pip commands with `.venv\Scripts\python -m pip`), then run `powershell -ExecutionPolicy Bypass -File kurulum\windows-kur.ps1` from an administrator PowerShell. It registers a hidden "VakumOda" startup task (`bekci.py` watchdog) and firewall rules for 8765/TCP and 5353/UDP (Private network).

### Usage
1. "+ Yeni oda" (new room): drag rectangles on the map, type a name, save.
2. Press a room button, confirm, and the robot cleans only that zone. Choose the repeat count (1-3) at the top.
3. "Haritayı yenile" refreshes the map; it is not available while the robot is cleaning ("retry").
4. Rooms are stored in robot map coordinates (mm). If you move the dock, the robot builds a new map and saved rooms shift: refresh the map and redraw or fix the rooms (older versions are in `.gizli/odalar-yedek/`).

### Security warning
This server is designed **for your home LAN only** and has **no authentication**. Never expose it to the internet (no port forwarding, no public tunnels). Token, session and keys live in `.gizli/` and are git-ignored; never commit or share them.

### Tests
`test_*.py` do not touch the robot or real data files, e.g. `.venv/bin/python test_sunucu.py`.

### License
MIT, see [LICENSE](LICENSE). `bulut.py` contains code adapted from [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) (MIT, Piotr Machowski).

---

<a id="türkçe"></a>
## Türkçe

**Xiaomi Mi Robot Vacuum 1. nesil (`rockrobo.vacuum.v1`)** için yerel ağdan (LAN) çalışan web sayfası: haritada alan çiz, odaya ad ver, tek dokunuşla sadece o odayı temizlet.

Robota yalnızca resmi uygulamanın da kullandığı standart miio komutları gider: `get_status`, `get_map_v1`, `app_zoned_clean`, `app_pause`, `app_stop`, `app_charge`; ses paketi için `get_current_sound`, `get_sound_volume`, `get_sound_progress`, `dnld_install_sound` (liste: `robot.py` içinde `IZINLI`). **Zamanlanmış/otomatik temizlik yoktur**: temizliği yalnızca sayfadaki düğme başlatır.

### Özellikler
- Oda oda temizlik: haritada oda başına 1-5 dikdörtgen çiz, adlandır, temizlet (1-3 tekrar, onay sorulur).
- Canlı harita: sayfa açıkken robotun anlık yeri (R) ve temizlikte geçtiği yol görünür (temizlikte ~5 sn, beklemede 30 sn arayla, Xiaomi bulutundan).
- Telegram bildirimi: "temizlik bitti (alan, süre)" ve "robot sıkıştı / hata: <açıklama> (kod N)".
- Türkçe ses paketi: Gemini TTS ile üret, robota yükle, eski sese geri dön.
- İki makineli yedekli sunucu: asıl ve yedek makine oda listesini ve `vakum.local` adresini paylaşır; asıl kapalıysa yedek otomatik devralır.
- Veri kaybı yok: "Sil" odayı sadece silindi diye işaretler, oda dosyası her üzerine yazılmadan önce yedeklenir.

### Gereksinimler
- Xiaomi Mi Robot Vacuum 1. nesil (`rockrobo.vacuum.v1`); sunucu ve telefonla aynı Wi-Fi'de.
- Python 3.12+ (macOS veya Windows; kurulum betikleri bunlar için).
- Robotun eşleştiği Xiaomi hesabı (Mi Home); token'ı almak için bir kez gerekir.
- İsteğe bağlı: Telegram botu, Gemini API anahtarı, `ffmpeg` + `ccrypt` (ses paketi).

### Kurulum (bir kez, asıl makinede)
```
cd vakum-oda
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install --no-deps python-miio==0.5.12
mkdir -p .gizli && cp ayar.ornek.json .gizli/ayar.json   # robot_ip, esler (diğer makine), makine, oncelik doldur
.venv/bin/python -c "import secrets;print(secrets.token_urlsafe(32))"   # çıkan anahtarı iki makinenin ayar.json'una aynı yaz
.venv/bin/python sunucu.py
```
Sonra `http://<makine-ip>:8765` adresini aç (iPhone gibi `.local` çözen cihazlarda `http://vakum.local:8765`; Android çözmeyebilir). IP'ler değişmesin diye modemde DHCP rezervasyonu önerilir.

Örnek `.gizli/ayar.json` (bkz. `ayar.ornek.json`):
```
{
  "makine": "pc-1", "oncelik": 1, "port": 8765,
  "robot_ip": "192.168.x.x",
  "esler": [{"ad": "pc-2", "url": "http://192.168.x.x:8765", "oncelik": 2}],
  "senkron_anahtar": "<ORTAK_RASTGELE_ANAHTAR>"
}
```
Faydalı bayraklar: `sunucu.py --kuru` (robota komut göndermez, üretilen komutu gösterir) ve `sunucu.py --tek` (senkron ve `vakum.local` kapalı).

macOS otomatik başlatma (LaunchAgent, çökerse yeniden başlar; günlük `.gizli/sunucu.log`): `bash kurulum/mac-kur.sh`.

### Token alma (QR bulut girişi)
```
.venv/bin/python bulut_giris.py     # .gizli/qr.png oluşur; telefondaki Mi Home ile okut
.venv/bin/python harita.py          # haritayı indirir (robot temizlikte değilken)
```
Robot token'ı `.gizli/vac.token` dosyasında, bulut oturumu `.gizli/` altında durur. Bulut girişi düşerse sayfada "Bulut girişi düştü" yazar, canlı harita durur (temizlik komutları bulutu kullanmadığı için etkilenmez); `bulut_giris.py`'yi yeniden çalıştırman yeter, sunucuyu yeniden başlatmak gerekmez.

### Telegram ayarı
1. BotFather ile bot oluştur, token'ı not al. Bota bir mesaj at, sonra `getUpdates` ile chat id'ni bul.
2. `.gizli/telegram.json` oluştur:
```
{"bot_token": "<TOKEN>", "chat_id": "<CHAT_ID>"}
```
Dosya yoksa bildirim kapalıdır. Test: `.venv/bin/python bildirim.py "deneme"`. Sunucu 10 sn'de bir `get_status` okur; aynı hata kodu için tek mesaj gider. İki makinede yalnız yetkili olan gönderir: asıl makine her zaman, yedek yalnızca devraldığında; çift bildirim gelmez.

### Türkçe ses paketi: üretme, yükleme, eski sese dönüş
`ses/metinler.csv`: gen1 ses dosyası adı -> Türkçe cümle.
```
brew install ffmpeg ccrypt
.venv/bin/python ses_paketi.py      # Gemini TTS (GEMINI_API_KEY ya da .gizli/gemini.key) -> .gizli/ses/wav + .gizli/ses/tr.pkg
.venv/bin/python ses_yukle.py       # önce .gizli/yedek/ altına yedek, sonra yükleme + get_sound_progress takibi
```
Paket, kökte `*.wav` olan tar.gz'dir ve gen1 anahtarıyla `ccrypt` ile şifrelenir. Robot paketi bu makinedeki geçici bir HTTP sunucusundan indirir (`dnld_install_sound`). Robot temizlikteyse yükleme yapılmaz. Ücretsiz Gemini kotası için cümleler istek başına 12'li gruplar hâlinde okutulur; ham kayıtlar `.gizli/ses/ham/` önbelleğinde durur. Faydalı bayraklar: `--dogrula`, `--yeniden`, `--sadece <dosya.wav> --grup 1`.

**Eski sese dönüş:** yedek dosyasında önceki ses paketi ve ses seviyesi yazar. Mi Home > robot > Ayarlar > Ses paketi bölümünden İngilizce'yi (ya da istediğin dili) seç; resmi paket buluttan yeniden kurulur. Oda verileri etkilenmez.

### İki makineli kurulum (asıl + yedek)
- İkinci makineye aynı şekilde kur, proje klasörünü `.gizli/` ile kopyala; kendi `makine` adını ve `"oncelik": 2` yaz, `esler`'i asıl makineye yönelt, **aynı** `senkron_anahtar`'ı kullan.
- `vakum.local` (zeroconf) yayınını yalnız lider yapar; en küçük `oncelik` asıl liderdir. Yedek, asıl makinenin 8765 portu `devralma_hata_sayisi` (3) ardışık kontrolde (5 sn arayla) yanıt vermezse devralır, asıl geri gelince bırakır. İki makinede de sunucu hep çalışır; robota komutu yalnız isteği alan makine gönderir.
- Oda listesi her kayıt/silmede, açılışta ve 30 sn'de bir senkronlanır; birleştirme oda id bazındadır, en yeni `guncelleme` kazanır. Senkron uç noktası (`/api/senkron`) yalnız `senkron_anahtar` bilen makineye açıktır.
- Windows yedek makine: Python 3.12+ kur, `.venv` oluştur (`py -m venv .venv`, aynı pip komutları `.venv\Scripts\python -m pip` ile), sonra yönetici PowerShell'de `powershell -ExecutionPolicy Bypass -File kurulum\windows-kur.ps1` çalıştır. Oturum açılınca gizli pencerede başlayan "VakumOda" görevini (`bekci.py` bekçisi) ve güvenlik duvarında 8765/TCP + 5353/UDP kurallarını (Özel ağ) ekler.

### Kullanım
1. "+ Yeni oda": haritada sürükleyerek dikdörtgen çiz, adını yaz, kaydet.
2. Oda düğmesine bas, onayla; robot yalnız o bölgeyi temizler. Tekrar sayısı (1-3) en üstten seçilir.
3. "Haritayı yenile": robot temizlik yaparken harita alınamaz ("retry"), bitince dene.
4. Odalar robotun harita koordinatına (mm) kaydedilir. İstasyonu (dock) taşırsan robot yeni harita çıkarır ve kayıtlı odalar kayar: haritayı yenile, odaları yeniden çiz/düzelt (eski hâller `.gizli/odalar-yedek/` altındadır).

### Güvenlik uyarısı
Bu sunucu **yalnızca ev içi ağ (LAN)** için tasarlandı ve **kimlik doğrulaması yoktur**. Port yönlendirme veya herkese açık tünel ile **asla internete açmayın**. Token, oturum ve anahtarlar `.gizli/` altında tutulur, git'e girmez; paylaşmayın.

### Testler
`test_*.py` robota ve gerçek dosyalara dokunmaz, örn. `.venv/bin/python test_sunucu.py`.

### Lisans
MIT, bkz. [LICENSE](LICENSE). `bulut.py`, [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) (MIT, Piotr Machowski) kodundan uyarlanmıştır.
