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

## GitHub Actions
Repo **private**. Settings → Secrets → Actions: `SPOR_TC`, `SPOR_SIFRE`, `TG_TOKEN`, `TG_CHAT_ID`.
İlk test: Actions → halisaha → Run workflow (dry_run açık). IP engeli varsa PC/VPS'te çalıştır.

## Seçenekler
- `--sure 15` 15 dk boyunca dener, `--aralik 3` denemeler arası saniye (min 2)
- `--dry-run` tıklamaz, durum raporunu Telegram'a atar
