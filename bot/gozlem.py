"""Sürekli gözlemci: iki sahanın tablosunu periyodik okur, durum değişikliklerini CSV'ye yazar.

python -m bot.gozlem                 # 30 sn arayla, durdurulana kadar (Ctrl+C)
python -m bot.gozlem --aralik 60
python -m bot.gozlem --sure 340      # 340 dk sonra kendiliğinden biter (GitHub Actions için)
"""
import argparse
import csv
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from bot import config, site

log = logging.getLogger("gozlem")
TR = ZoneInfo("Europe/Istanbul")
CSV_YOLU = Path("gozlem.csv")
ALANLAR = ("zaman", "salon", "tarih", "saat", "eski", "yeni")
YOK = "yok"  # tabloda görünmüyor (henüz açılmadı ya da sepette gizli)
HATA_BEKLEME_SN = 30

Anahtar = tuple[str, str, str]  # (salon, tarih, saat)


def durum_oku(page) -> dict[Anahtar, str]:
    durum: dict[Anahtar, str] = {}
    for salon in config.SALONLAR:
        for s in site.tabloyu_getir(page, salon):
            durum[(salon, s.tarih.isoformat(), s.saat)] = s.durum
    return durum


def farklar(onceki: dict[Anahtar, str], simdi: dict[Anahtar, str]) -> list[tuple[Anahtar, str, str]]:
    return [
        (k, onceki.get(k, YOK), simdi.get(k, YOK))
        for k in sorted(onceki.keys() | simdi.keys())
        if onceki.get(k, YOK) != simdi.get(k, YOK)
    ]


def yaz(satirlar: list[dict]) -> None:
    yeni_dosya = not CSV_YOLU.exists()
    with CSV_YOLU.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ALANLAR)
        if yeni_dosya:
            w.writeheader()
        w.writerows(satirlar)


def son_durum(yol: Path) -> dict[Anahtar, str]:
    """Önceki çalışmaların bıraktığı son durum; böylece yeniden başlayınca her şey 'baslangic' yazılmaz."""
    durum: dict[Anahtar, str] = {}
    if not yol.exists():
        return durum
    with yol.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["salon"] != "HATA":
                durum[(r["salon"], r["tarih"], r["saat"])] = r["yeni"]
    return {k: v for k, v in durum.items() if v != YOK}


def calistir(aralik_sn: int, sure_dk: int) -> None:
    bitis = time.monotonic() + sure_dk * 60 if sure_dk else None
    tc, sifre = os.environ["SPOR_TC"], os.environ["SPOR_SIFRE"]
    onceki: dict[Anahtar, str] | None = son_durum(CSV_YOLU) or None
    with sync_playwright() as p:
        tarayici = p.chromium.launch(headless=True)
        page = tarayici.new_page(locale="tr-TR", timezone_id="Europe/Istanbul")
        girildi = False
        while bitis is None or time.monotonic() < bitis:
            zaman = datetime.now(TR).isoformat(timespec="seconds")
            try:
                if not girildi:
                    site.giris_yap(page, tc, sifre)
                    girildi = True
                simdi = durum_oku(page)
            except (PlaywrightError, site.GirisHatasi) as e:
                log.warning("Okunamadı: %s", str(e)[:120])
                yaz([{"zaman": zaman, "salon": "HATA", "tarih": "", "saat": "", "eski": "", "yeni": type(e).__name__}])
                girildi = False
                time.sleep(HATA_BEKLEME_SN)
                continue
            if onceki is None:
                # İlk tur: başlangıç durumunu "baslangic" olarak kaydet ki sonradan açılanlar ayrışsın.
                degisim = [(k, "baslangic", v) for k, v in sorted(simdi.items())]
            else:
                degisim = farklar(onceki, simdi)
            if degisim:
                yaz([{"zaman": zaman, "salon": k[0], "tarih": k[1], "saat": k[2], "eski": e, "yeni": y}
                     for k, e, y in degisim])
                log.info("%d değişiklik", len(degisim))
            onceki = simdi
            time.sleep(aralik_sn)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--aralik", type=int, default=30, help="okumalar arası saniye (min 15)")
    ap.add_argument("--sure", type=int, default=0, help="dakika; 0 = durdurulana kadar")
    args = ap.parse_args()
    calistir(max(15, args.aralik), args.sure)


if __name__ == "__main__":
    main()
