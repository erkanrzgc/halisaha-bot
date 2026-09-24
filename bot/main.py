"""Halısaha botu giriş noktası.

python -m bot.main                 # tek tur: bak, müsaitse al
python -m bot.main --sure 15       # 15 dk boyunca --aralik saniyede bir dene
python -m bot.main --dry-run       # hiçbir şeye tıklamaz, sadece raporlar
python -m bot.main --hedef "carsamba 14:00 - 15:00"   # canlı test
"""
import argparse
import logging
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from bot import config, notify, site
from bot.tablo import sepette_mi
from bot.secim import Aday, acilmis_gunler, bilinmeyen_etiketler, en_iyi_aday, hafta_tarihi

log = logging.getLogger("halisaha")
TR = ZoneInfo("Europe/Istanbul")
SMS_BEKLEME_SN = 4 * 60
MAX_UST_USTE_HATA = 5
HATA_BEKLEME_SN = 10


def bugun() -> date:
    return datetime.now(TR).date()


def tablolari_oku(page: Page) -> dict[str, list]:
    return {salon: site.tabloyu_getir(page, salon) for salon in config.SALONLAR}


def rapor(tablolar: dict[str, list], hedefler: tuple[config.Hedef, ...]) -> str:
    gunler = sorted(acilmis_gunler(tablolar))
    satirlar = [f"Açık günler: {', '.join(g.strftime('%d.%m') for g in gunler) or 'yok'}"]
    for salon, seanslar in tablolar.items():
        for s in seanslar:
            if any(s.tarih.weekday() == h.gun and s.saat == h.saat for h in hedefler):
                satirlar.append(f"{salon} {s.tarih:%d.%m} {s.saat}: {s.durum}")
    return "\n".join(satirlar)


def al(page: Page, ayar: config.Ayarlar, aday: Aday) -> bool:
    """True = iş bitti (alındı ya da SMS gelmedi, tekrar SMS göndertmeyelim); False = tekrar dene."""
    etiket = f"{aday.tarih:%d.%m} {aday.seans.saat} {aday.salon}"
    # Sayfa zaten adayın salonundaysa tablo tazedir; değilse o salona dön (id'ler salon başına değişir).
    if site.secili_salon(page) == aday.salon:
        hedef = aday.seans
    else:
        guncel = site.tabloyu_getir(page, aday.salon)
        hedef = next((s for s in guncel if s.tarih == aday.tarih and s.saat == aday.seans.saat and s.musait), None)
    if not hedef:
        log.info("%s bu arada kapıldı", etiket)
        return False

    offset = notify.eski_mesajlari_temizle(ayar.tg_token)
    # Haber tıklamayı geciktirmesin: mesaj arka planda gider, bot aynı anda Sepete Ekle'ye basar.
    threading.Thread(target=notify.mesaj_gonder, daemon=True, args=(
        ayar.tg_token, ayar.tg_chat_id,
        f"🔥 {etiket} bulundu, sepete ekliyorum! SMS gelince kodu buraya yaz ({SMS_BEKLEME_SN // 60} dk).",
    )).start()
    site.sepete_ekle(page, aday.salon, hedef)
    log.info("%s: Sepete Ekle basıldı, SMS kodu bekleniyor", etiket)
    kod = notify.kod_bekle(ayar.tg_token, ayar.tg_chat_id, offset, SMS_BEKLEME_SN)
    log.info("%s: SMS kodu %s", etiket, "geldi" if kod else "gelmedi")
    if not kod:
        notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, f"⌛ {etiket}: SMS kodu gelmedi, işlem yarım kaldı, bot duruyor.")
        return True
    site.sms_dogrula(page, kod)
    if not sepette_mi(page.content(), aday.tarih, aday.seans.saat, aday.salon):
        page.goto(config.BASE_URL + config.SEPET_PATH, wait_until="domcontentloaded")
    if sepette_mi(page.content(), aday.tarih, aday.seans.saat, aday.salon):
        metin = f"✅ {etiket} sepette. Hemen öde: {config.BASE_URL}{config.SEPET_PATH}"
    else:
        metin = f"❓ {etiket}: SMS girildi ama sepette göremedim, kontrol et: {config.BASE_URL}{config.SEPET_PATH}"
    log.info("%s: %s", etiket, metin)
    notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, metin, foto=page.screenshot(full_page=True))
    return True


def calistir(ayar: config.Ayarlar, hedefler: tuple[config.Hedef, ...],
             sure_dk: int, aralik_sn: int, dry_run: bool) -> None:
    bitis = time.monotonic() + sure_dk * 60
    uyarilan: set[str] = set()
    with sync_playwright() as p:
        tarayici = p.chromium.launch(headless=True)
        page = tarayici.new_page(locale="tr-TR", timezone_id="Europe/Istanbul")
        try:
            site.giris_yap(page, ayar.tc, ayar.sifre)
            log.info("Giriş başarılı")
            sepettekiler = site.sepet_tarihleri(page) & {hafta_tarihi(bugun(), h.gun) for h in hedefler}
            if sepettekiler:
                gunler = ", ".join(f"{t:%d.%m}" for t in sorted(sepettekiler))
                log.info("Hedef gün zaten sepette: %s", gunler)
                notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id,
                                    f"🛒 {gunler} için seans zaten sepette, yeni seans aramıyorum. Ödemeyi unutma: "
                                    f"{config.BASE_URL}{config.SEPET_PATH}")
                return
            if sure_dk > 0 and not dry_run:
                # Sadece uzun (açılış) çalışmalarında; tek turluk kontrollerde her seferinde rahatsız etmesin.
                gunler = ", ".join(dict.fromkeys(f"{hafta_tarihi(bugun(), h.gun):%d.%m}" for h in hedefler))
                notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id,
                                    f"⏰ Hazır ol! Bot {sure_dk} dk boyunca {gunler} için bakıyor. Telefon elinde olsun.")
            ust_uste_hata = 0
            while True:
                try:
                    tablolar = tablolari_oku(page)
                    ust_uste_hata = 0
                except PlaywrightError as e:
                    # İnternet kopması / site yavaşlığı: bekle, yeniden giriş yap, devam et.
                    ust_uste_hata += 1
                    log.warning("Tablo okunamadı (%d/%d): %s", ust_uste_hata, MAX_UST_USTE_HATA, e.message[:120])
                    if ust_uste_hata >= MAX_UST_USTE_HATA or time.monotonic() >= bitis:
                        raise
                    time.sleep(HATA_BEKLEME_SN)
                    _yeniden_giris(page, ayar)
                    continue
                hedef_tarihleri = {hafta_tarihi(bugun(), h.gun) for h in hedefler}
                yeni = bilinmeyen_etiketler(tablolar, hedef_tarihleri) - uyarilan
                if yeni:
                    uyarilan |= yeni
                    notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id,
                                        f"ℹ️ Hedef günlerde tanımadığım etiket: {', '.join(sorted(yeni))} (bizimki olabilir)")
                aday = en_iyi_aday(hedefler, tablolar, bugun(), config.BIZIM_ETIKETLER)
                if aday:
                    log.info("Aday: %s %s %s", aday.tarih, aday.seans.saat, aday.salon)
                    if dry_run:
                        notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id,
                                            f"[deneme] Müsait: {aday.tarih:%d.%m} {aday.seans.saat} {aday.salon}\n\n{rapor(tablolar, hedefler)}")
                        return
                    try:
                        if al(page, ayar, aday):
                            return
                    except site.YanlisSeans as e:
                        log.warning("Tıklama iptal: %s", e)
                if time.monotonic() >= bitis:
                    log.info("Süre doldu, alınabilecek seans yok.\n%s", rapor(tablolar, hedefler))
                    if dry_run:
                        notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, f"[deneme] Müsait hedef yok.\n\n{rapor(tablolar, hedefler)}")
                    return
                time.sleep(aralik_sn)
        except Exception as e:
            log.exception("Bot hata verdi")
            notify.mesaj_gonder(ayar.tg_token, ayar.tg_chat_id, f"⚠️ Bot hata verdi: {type(e).__name__}: {e}",
                                foto=_guvenli_ekran(page))
            raise
        finally:
            tarayici.close()


def _yeniden_giris(page: Page, ayar: config.Ayarlar) -> None:
    try:
        site.giris_yap(page, ayar.tc, ayar.sifre)
    except (PlaywrightError, site.GirisHatasi) as e:
        log.warning("Yeniden giriş başarısız, sonraki turda tekrar denenecek: %s", e)


def _guvenli_ekran(page: Page) -> bytes | None:
    try:
        return page.screenshot()
    except Exception:
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sure", type=int, default=0, help="dakika; 0 = tek tur")
    ap.add_argument("--aralik", type=int, default=config.SNIPE_INTERVAL_SEC, help="denemeler arası saniye")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hedef", help="tek hedefle test, örn. 'carsamba 14:00 - 15:00'")
    args = ap.parse_args()
    hedefler = (config.hedef_coz(args.hedef),) if args.hedef else config.HEDEFLER
    calistir(config.ayarlari_yukle(), hedefler, args.sure, max(2, args.aralik), args.dry_run)


if __name__ == "__main__":
    main()
