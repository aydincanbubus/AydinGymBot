# 🏋️ Gym Tracker Bot v2 — Kurulum Rehberi

## Ne Değişti? (v1 → v2)
- ✅ Önceki veriler otomatik yüklü (data.json içinde)
- ✅ Bugün antrenman günüyse otomatik işaretleniyor
- ✅ 1RM tahmini (Epley formülü)
- ✅ PR bildirimi (yeni rekor kırdığında anında uyarı)
- ✅ Haftalık hacim trendi grafiği
- ✅ Her antrenman günü saat 12:00 hatırlatıcı
- ✅ Her Pazar 20:00 haftalık rapor
- ✅ Vücut ağırlığı takibi + grafik
- ✅ AI koç (/koc) — antrenman ve beslenme önerileri

---

## Adım 1: Telegram Token (zaten varsa atla)
1. @BotFather → `/newbot` → token kopyala

---

## Adım 2: Anthropic API Key (AI koç için)
1. https://console.anthropic.com adresine git
2. API Keys → Create Key → kopyala
3. Bu olmadan bot çalışır ama /koc komutu çalışmaz

---

## Adım 3: GitHub'a Yükle

### Zaten GitHub repon varsa:
1. Repona git → tüm dosyaları sil (bot.py, requirements.txt, railway.toml)
2. Bu ZIP'teki 5 dosyayı yükle:
   - bot.py
   - requirements.txt
   - railway.toml
   - data.json  ← YENİ (önceki veriler burada)
   - KURULUM.md

### Yeni repo ise:
New Repository → Create → 5 dosyayı upload et

---

## Adım 4: Railway Güncelleme

### Zaten Railway'de varsa:
1. Projeye git → Variables sekmesi
2. Şu 2 variable olduğundan emin ol:
   - `TELEGRAM_BOT_TOKEN` = token'ın
   - `ANTHROPIC_API_KEY` = Anthropic key'in (yoksa ekle)
3. GitHub'a yükledikten sonra Railway otomatik deploy eder

### Yeni Railway projesi ise:
1. railway.app → New Project → Deploy from GitHub
2. Repoyu seç
3. Variables'a yukarıdaki 2 key'i ekle
4. Deploy

---

## Komutlar

| Komut | Ne yapar |
|-------|---------|
| /antrenman | Antrenman verisi gir (bugün otomatik seçilir) |
| /grafik | Herhangi bir hareketin gelişim grafiği |
| /ozet | Bu haftanın özeti + hacim trendi |
| /kilo | Vücut ağırlığı gir |
| /koc | AI koçla konuş (beslenme/antrenman önerileri) |
| /bitti | Koç modundan çık |
| /program | Haftalık programı gör |
| /hatirlatici | Hatırlatıcıyı manuel kur |
| /iptal | Herhangi bir işlemi iptal et |

---

## Veri Girişi Formatı
`50x10 60x8 70x5` → 50kg'dan 10 tekrar, 60kg'dan 8 tekrar, 70kg'dan 5 tekrar

