"""Nöbetçi: gözlemci + bot tek süreçte, durdurulana kadar çalışır.

- Her turda iki sahayı okur, değişiklikleri gozlem.csv'ye yazar (recon).
- Hedef seanslardan biri müsait görünürse hemen alır (Telegram'dan SMS kodu ister).
- gozlem.csv'deki geçmiş açılışlardan "sıcak saatleri" öğrenir; o saatlerde daha sık bakar.

python -m bot.nobetci
"""
import argparse
import csv
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from bot import config, notify, site
from bot.gozlem import CSV_YOLU, YOK, farklar, son_durum, yaz
from bot.main import TR, al
from bot.secim import en_iyi_aday, hafta_tarihi

log = logging.getLogger("nobetci")
SAKIN_ARALIK_SN = 10
SICAK_ARALIK_SN = 3
HATA_BEKLEME_SN = 30
SEPET_KONTROL_SN = 30 * 60
SMS_SONRASI_BEKLEME_SN = 10 * 60  # SMS cevapsız kaldıysa hemen yeni SMS göndertme

SicakSaat = tuple[int, int]  # (haftanın günü, saat)


def sicak_saatler(yol: Path) -> set[SicakSaat]:
    """Geçmişte bir seansın açıldığı (yok → musait) gün/saatler; ±1 saat pay bırakılır."""
    saatler: set[SicakSaat] = set()
    if not yol.exists():
        return saatler
    with yol.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["eski"] != YOK or r["yeni"] != "musait":
                continue
            an = datetime.fromisoformat(r["zaman"])
            for fark in (-1, 0, 1):
                t = an + timedelta(hours=fark)
                saatler.add((t.weekday(), t.hour))
    return saatler


def sicak_mi(an: datetime, saatler: set[SicakSaat]) -> bool:
    return (an.weekday(), an.hour) in saatler


def _durum(tablolar: dict[str, list]) -> dict[tuple[str, str, str], str]:
    return {(salon, s.tarih.isoformat(), s.saat): s.durum for salon, ss in tablolar.items() for s in ss}


def calistir(ayar: config.Ayarlar) -> None:
    onceki = son_durum(CSV_YOLU) or None
    saatler = sicak_saatler(CSV_YOLU)
    log.info("Öğrenilmiş sıcak saat sayısı: %d", len(saatler))
    alinan: set[date] = set()
    son_sepet_kontrol = 0.0
    sms_bekle_bitis = 0.0
    with sync_playwright() as p:
        tarayici = p.chromium.launch(headless=True)
        page = tarayici.new_page(locale="tr-TR", timezone_id="Europe/Istanbul")
        girildi = False
        notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, "👀 Nöbetçi başladı.")
        while True:
            an = datetime.now(TR)
            try:
                if not girildi:
                    site.giris_yap(page, ayar.tc, ayar.sifre)
                    girildi = True
                if time.monotonic() - son_sepet_kontrol > SEPET_KONTROL_SN:
                    alinan = site.sepet_tarihleri(page)
                    son_sepet_kontrol = time.monotonic()
                tablolar = {salon: site.tabloyu_getir(page, salon) for salon in config.SALONLAR}
            except (PlaywrightError, site.GirisHatasi) as e:
                log.warning("Okunamadı: %s", str(e)[:150])
                yaz([{"zaman": an.isoformat(timespec="seconds"), "salon": "HATA", "tarih": "", "saat": "",
                      "eski": "", "yeni": type(e).__name__}])
                girildi = False
                time.sleep(HATA_BEKLEME_SN)
                continue

            simdi = _durum(tablolar)
            degisim = ([(k, "baslangic", v) for k, v in sorted(simdi.items())] if onceki is None
                       else farklar(onceki, simdi))
            if degisim:
                yaz([{"zaman": an.isoformat(timespec="seconds"), "salon": k[0], "tarih": k[1], "saat": k[2],
                      "eski": e, "yeni": y} for k, e, y in degisim])
                if any(e == YOK and y == "musait" for _, e, y in degisim):
                    saatler |= {(an.weekday(), an.hour)}  # yeni açılış: bu saati de sıcak say
            onceki = simdi

            hedef_tarihleri = {hafta_tarihi(an.date(), h.gun) for h in config.HEDEFLER}
            aday = None
            if not (alinan & hedef_tarihleri) and time.monotonic() >= sms_bekle_bitis:
                aday = en_iyi_aday(config.HEDEFLER, tablolar, an.date())
            if aday:
                log.info("Aday: %s %s %s", aday.tarih, aday.seans.saat, aday.salon)
                sms_istendi = False
                try:
                    # al() True: SMS aşamasına gelindi (alındı ya da kod gelmedi); False: tıklamadan kapıldı.
                    sms_istendi = al(page, ayar, aday)
                except site.YanlisSeans as e:
                    log.warning("Tıklama iptal: %s", e)
                except PlaywrightError as e:
                    log.warning("Alırken hata: %s", str(e)[:150])
                    notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, f"⚠️ Seansı alırken hata: {str(e)[:150]}")
                    sms_istendi = True  # SMS gitmiş olabilir; üst üste SMS göndertmeyelim
                if sms_istendi:
                    son_sepet_kontrol = 0.0  # alındıysa sepette görünür, sonraki turda aramayı bırakır
                    sms_bekle_bitis = time.monotonic() + SMS_SONRASI_BEKLEME_SN
                continue

            time.sleep(SICAK_ARALIK_SN if sicak_mi(an, saatler) else SAKIN_ARALIK_SN)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    argparse.ArgumentParser(description=__doc__).parse_args()
    calistir(config.ayarlari_yukle())


if __name__ == "__main__":
    main()
