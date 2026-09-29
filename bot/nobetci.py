"""Nöbetçi: gözlemci + bot tek süreçte, durdurulana kadar çalışır.

- Her turda iki sahayı okur, değişiklikleri gozlem.csv'ye yazar (recon).
- Hedef seanslardan biri müsait görünürse hemen alır (Telegram'dan SMS kodu ister).
- gozlem.csv'deki geçmiş açılışlardan "sıcak saatleri" öğrenir; o saatlerde daha sık bakar.

python -m bot.nobetci
"""
import argparse
import csv
import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from bot import config, notify, site
from bot.gozlem import CSV_YOLU, YOK, farklar, son_durum, yaz
from bot.main import TR, al
from bot.secim import grup_adayi

log = logging.getLogger("nobetci")
SAKIN_ARALIK_SN = 10
SICAK_ARALIK_SN = 3
KESKIN_ARALIK_SN = 2
HEDEF_SAATLER = {int(saat[:2]) for saat in config.SAAT_SIRASI}
HATA_BEKLEME_SN = 30
SEPET_KONTROL_SN = 30 * 60
SMS_SONRASI_BEKLEME_SN = 10 * 60  # SMS cevapsız kaldıysa hemen yeni SMS göndertme
MAX_UST_USTE_HATA = 10
TAKILMA_SN = 6 * 60  # bir tur bu kadar sürerse süreç takılmıştır; kapat, bat yeniden başlatsın
LOG_YOLU = Path("nobetci.log")
SAYFA_YENILE_SN = 30 * 60
NABIZ_SN = 5 * 60  # bu aralıkla "çalışıyorum" satırı loglanır

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


def acilis_penceresinde(an: datetime, hedef_saatler: set[int]) -> bool:
    """Seanslar başlamadan ~72 saat önce, tam saat başında açılıyor. Hedef saatlerin başına
    2 dk kala ile 5 dk sonrası arası 'keskin nişancı' penceresi."""
    for h in hedef_saatler:
        if (an.hour == (h - 1) % 24 and an.minute >= 58) or (an.hour == h and an.minute < 5):
            return True
    return False


def sicak_mi(an: datetime, saatler: set[SicakSaat]) -> bool:
    return (an.weekday(), an.hour) in saatler


class _Bekci:
    """Takılma bekçisi: döngü belirli süre ilerlemezse süreci öldürür (bat dosyası yeniden başlatır).
    SMS beklerken (4 dk) de döngü durduğu için süre bundan uzun tutulur."""

    def __init__(self, sure_sn: int) -> None:
        self._sure = sure_sn
        self._son = time.monotonic()
        threading.Thread(target=self._izle, daemon=True).start()

    def besle(self) -> None:
        self._son = time.monotonic()

    def _izle(self) -> None:
        while True:
            time.sleep(30)
            if time.monotonic() - self._son > self._sure:
                log.error("Nöbetçi %d sn'dir ilerlemiyor, kapatılıyor", self._sure)
                logging.shutdown()
                os._exit(3)


def _yeni_sayfa(tarayici, eski):
    try:
        eski.close()
    except Exception:  # noqa: BLE001 — çökmüş sayfa kapanırken de hata verebilir
        pass
    return tarayici.new_page(locale="tr-TR", timezone_id="Europe/Istanbul")


def _durum(tablolar: dict[str, list]) -> dict[tuple[str, str, str], str]:
    return {(salon, s.tarih.isoformat(), s.saat): s.durum for salon, ss in tablolar.items() for s in ss}


def calistir(ayar: config.Ayarlar) -> None:
    onceki = son_durum(CSV_YOLU) or None
    saatler = sicak_saatler(CSV_YOLU)
    log.info("Öğrenilmiş sıcak saat sayısı: %d", len(saatler))
    alinan: set[date] = set()
    son_sepet_kontrol = 0.0
    sms_bekle_bitis = 0.0
    ust_uste_hata = 0
    bekci = _Bekci(TAKILMA_SN)
    with sync_playwright() as p:
        tarayici = p.chromium.launch(headless=True)
        page = tarayici.new_page(locale="tr-TR", timezone_id="Europe/Istanbul")
        sayfa_acilis = time.monotonic()
        tur, son_nabiz = 0, time.monotonic()
        girildi = False
        notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, "👀 Nöbetçi başladı.")
        while True:
            bekci.besle()
            an = datetime.now(TR)
            if time.monotonic() - sayfa_acilis > SAYFA_YENILE_SN:
                # Uzun ömürlü sayfa belleği şişirip çöküyor; periyodik olarak tazele.
                page = _yeni_sayfa(tarayici, page)
                sayfa_acilis = time.monotonic()
                girildi = False
            try:
                if not girildi:
                    site.giris_yap(page, ayar.tc, ayar.sifre)
                    girildi = True
                if time.monotonic() - son_sepet_kontrol > SEPET_KONTROL_SN:
                    alinan = site.sepet_tarihleri(page)
                    son_sepet_kontrol = time.monotonic()
                tablolar = {salon: site.tabloyu_getir(page, salon) for salon in config.SALONLAR}
            except Exception as e:  # noqa: BLE001 — nöbetçi hiçbir hatada ölmemeli
                ust_uste_hata += 1
                log.warning("Okunamadı (%d): %s: %s", ust_uste_hata, type(e).__name__, str(e)[:200])
                yaz([{"zaman": an.isoformat(timespec="seconds"), "salon": "HATA", "tarih": "", "saat": "",
                      "eski": "", "yeni": type(e).__name__}])
                if ust_uste_hata >= MAX_UST_USTE_HATA:
                    raise SystemExit("Üst üste çok hata; bat dosyası yeniden başlatacak") from e
                # Çöken sayfada ("Target crashed") işlem takılıp kalıyor: her hatada temiz sayfa aç.
                page = _yeni_sayfa(tarayici, page)
                sayfa_acilis = time.monotonic()
                girildi = False
                time.sleep(HATA_BEKLEME_SN)
                continue
            ust_uste_hata = 0
            tur += 1
            if time.monotonic() - son_nabiz > NABIZ_SN:
                log.info("Nabız: %d tur tamam, %s", tur, "sıcak saat" if sicak_mi(an, saatler) else "sakin saat")
                son_nabiz = time.monotonic()

            simdi = _durum(tablolar)
            degisim = ([(k, "baslangic", v) for k, v in sorted(simdi.items())] if onceki is None
                       else farklar(onceki, simdi))
            if degisim:
                yaz([{"zaman": an.isoformat(timespec="seconds"), "salon": k[0], "tarih": k[1], "saat": k[2],
                      "eski": e, "yeni": y} for k, e, y in degisim])
                if any(e == YOK and y == "musait" for _, e, y in degisim):
                    saatler |= {(an.weekday(), an.hour)}  # yeni açılış: bu saati de sıcak say
            onceki = simdi

            aday = None
            if time.monotonic() >= sms_bekle_bitis:
                aday = grup_adayi(config.HEDEF_GRUPLARI, tablolar, an.date(), alinan)
            if aday:
                log.info("Aday: %s %s %s", aday.tarih, aday.seans.saat, aday.salon)
                sms_istendi = False
                try:
                    # al() True: SMS aşamasına gelindi (alındı ya da kod gelmedi); False: tıklamadan kapıldı.
                    sms_istendi = al(page, ayar, aday)
                except site.YanlisSeans as e:
                    log.warning("Tıklama iptal: %s", e)
                except Exception as e:  # noqa: BLE001
                    log.warning("Alırken hata: %s: %s", type(e).__name__, str(e)[:150])
                    notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, f"⚠️ Seansı alırken hata: {str(e)[:150]}")
                    sms_istendi = True  # SMS gitmiş olabilir; üst üste SMS göndertmeyelim
                if sms_istendi:
                    son_sepet_kontrol = 0.0  # alındıysa sepette görünür, sonraki turda aramayı bırakır
                    sms_bekle_bitis = time.monotonic() + SMS_SONRASI_BEKLEME_SN
                continue

            if acilis_penceresinde(an, HEDEF_SAATLER):
                time.sleep(KESKIN_ARALIK_SN)
            else:
                time.sleep(SICAK_ARALIK_SN if sicak_mi(an, saatler) else SAKIN_ARALIK_SN)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  RotatingFileHandler(LOG_YOLU, maxBytes=2_000_000, backupCount=3, encoding="utf-8")],
    )
    load_dotenv()
    argparse.ArgumentParser(description=__doc__).parse_args()
    calistir(config.ayarlari_yukle())


if __name__ == "__main__":
    main()
