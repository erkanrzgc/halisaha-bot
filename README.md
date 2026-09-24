# Halısaha Bot

Florya Spor Tesisi Halı Saha 1/2 için Cuma (olmazsa Cumartesi, o da olmazsa Pazar) akşam seansını yakalar.
Sıra: 21-22 → 22-23 → 20-21, her saatte önce Saha 1 sonra Saha 2. Günde 1 seans kuralı var.

Akış: giriş → tablo → Rezervasyon → Sepete Ekle → Telegram'dan SMS kodunu sana sorar →
kodu Telegram'a yazarsın → bot girer → "sepette, öde" mesajı + ekran görüntüsü. Ödemeyi sen yaparsın.

## Kurulum (Windows)
```
py -3.12 -m venv .venv   # 3.14 ile playwright kurulmayabilir
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env   # içini doldur
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m bot.main --dry-run
```

## Telegram
1. @BotFather → `/newbot` → token → `TG_TOKEN`
2. Botuna bir mesaj at, sonra `https://api.telegram.org/bot<TOKEN>/getUpdates` aç → `chat.id` → `TG_CHAT_ID`

## Nöbetçi (önerilen kullanım)
`calistir.bat` → 4. Sürekli çalışır: iki sahayı izler, değişiklikleri `gozlem.csv`'ye yazar,
hedef seans boş görünce alır. Geçmiş açılış saatlerini öğrenip o saatlerde 3 sn'de bir, diğer
zamanlarda 10 sn'de bir bakar. Analiz: `calistir.bat` → 5.

## GitHub Actions (çalışmıyor)
Site, GitHub sunucularına Cloudflare doğrulaması gösteriyor (HTTP 403). Bot bu yüzden
Türkiye'deki bir ev internetinden (PC) çalışmalı.

## Seçenekler
- `--sure 15` 15 dk boyunca dener, `--aralik 3` denemeler arası saniye (min 2)
- `--dry-run` tıklamaz, durum raporunu Telegram'a atar
