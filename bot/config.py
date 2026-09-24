"""Hedef seanslar ve ortam ayarları."""
import os
from dataclasses import dataclass

BASE_URL = os.environ.get("SPOR_BASE_URL", "https://online.spor.istanbul")
KIRALIK_PATH = "/satiskiralik.aspx"
SEPET_PATH = "/uyesepet.aspx"

SALONLAR = ("HALI SAHA 1", "HALI SAHA 2")  # öncelik sırası

# Python weekday: Pazartesi=0 ... Pazar=6
CUMA = 4
CUMARTESI = 5
PAZAR = 6

SNIPE_INTERVAL_SEC = 3


@dataclass(frozen=True)
class Hedef:
    gun: int  # weekday
    saat: str  # "20:00 - 21:00" formatı, sitedeki metinle aynı


# Günde 1 seans kuralı var: sıradaki ilk müsait seans alınır, sonra durulur.
# Gün sırası Cuma → Cumartesi → Pazar. Her saat için önce Salon 1, sonra 2.
SAAT_SIRASI = ("21:00 - 22:00", "22:00 - 23:00", "20:00 - 21:00")
HEDEFLER = tuple(Hedef(gun, saat) for gun in (CUMA, CUMARTESI, PAZAR) for saat in SAAT_SIRASI)

# Tabloda "bizim" rezervasyonumuzu gösteren etiket(ler). Canlı testte görülünce doldurulacak;
# boşken bot Cuma'yı aldıktan sonra Cumartesi'yi de dener (SMS'i cevaplamazsan alınmaz).
BIZIM_ETIKETLER: tuple[str, ...] = ()

GUN_ADLARI = {"pazartesi": 0, "sali": 1, "carsamba": 2, "persembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}


def hedef_coz(metin: str) -> Hedef:
    """'carsamba 14:00 - 15:00' → Hedef. Canlı test için."""
    gun, _, saat = metin.strip().partition(" ")
    if gun.lower() not in GUN_ADLARI or not saat.strip():
        raise ValueError(f"Hedef anlaşılamadı: {metin!r} (örn. 'carsamba 14:00 - 15:00')")
    return Hedef(GUN_ADLARI[gun.lower()], saat.strip())


@dataclass(frozen=True)
class Ayarlar:
    tc: str
    sifre: str
    tg_token: str
    tg_chat_id: str


def ayarlari_yukle() -> Ayarlar:
    """Env'den gizli bilgileri okur; eksik varsa hemen patlar."""
    anahtarlar = ("SPOR_TC", "SPOR_SIFRE", "TG_TOKEN", "TG_CHAT_ID")
    eksik = [k for k in anahtarlar if not os.environ.get(k)]
    if eksik:
        raise SystemExit(f"Eksik ortam değişkeni: {', '.join(eksik)}")
    return Ayarlar(*(os.environ[k] for k in anahtarlar))
