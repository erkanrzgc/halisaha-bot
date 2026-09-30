"""spor.istanbul sitesiyle Playwright üzerinden konuşan katman. Tüm seçiciler burada."""
import json
import logging
import re
from datetime import date
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from bot import config
from bot.tablo import SepetKalemi, Seans, seanslari_oku, sepet_kalemleri, sepetteki_tarihler

log = logging.getLogger(__name__)

# Dropdown değerleri (satiskiralik.aspx'ten alındı)
BRANS_FUTBOL = "5bdbe5f0-a06e-4243-b65d-231b3c2247ed"
TESIS_FLORYA = "0848e94d-b6ec-4c02-932e-1adc9348859d"
SALON_IDLERI = {
    "HALI SAHA 1": "516e1886-eb6f-4fd9-bbb4-0ee366cb0359",
    "HALI SAHA 2": "38ddc086-4637-4fb3-a4b8-f0242e40ac3e",
}

GIRIS_PATH = "/uyegiris"
SEPETE_EKLE ="#pageContent_lbtnSepeteEkle"
SECILI_SEANS = "#pageContent_dvSeciliSeansBilgisi"
SMS_KUTUSU ="#pageContent_txtDogrulamaKodu"
SMS_GONDER = "#btnCepTelDogrulamaGonder"
POSTBACK_TIMEOUT_MS = 30_000
SMS_KABUL_TIMEOUT_MS = 15_000


class GirisHatasi(RuntimeError):
    pass


class GirisKotasi(GirisHatasi):
    """Site günlük giriş kotası doldu ya da kendi günlük limitimize geldik: ertesi güne kadar giriş yok."""


OTURUM_YOLU = Path(".oturum.json")  # çerezler; .gitignore'da, paylaşma
SAYAC_YOLU = Path(".giris_sayaci.json")
GUNLUK_GIRIS_LIMITI = 10
KOTA_METNI = "giriş kotanızı"


def bugunku_giris_sayisi(yol: Path = SAYAC_YOLU, bugun: date | None = None) -> int:
    bugun = bugun or date.today()
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return int(veri.get(bugun.isoformat(), 0))


def _giris_say(yol: Path = SAYAC_YOLU) -> int:
    bugun = date.today().isoformat()
    sayi = bugunku_giris_sayisi(yol) + 1
    yol.write_text(json.dumps({bugun: sayi}), encoding="utf-8")
    return sayi


def oturum_baglami(tarayici: Browser) -> BrowserContext:
    """Kayıtlı çerezlerle bağlam açar; böylece yeniden başlayınca tekrar giriş gerekmez."""
    ayar = {"locale": "tr-TR", "timezone_id": "Europe/Istanbul"}
    if OTURUM_YOLU.exists():
        try:
            return tarayici.new_context(storage_state=str(OTURUM_YOLU), **ayar)
        except Exception as e:  # noqa: BLE001 — bozuk dosya: sıfırdan
            log.warning("Kayıtlı oturum açılamadı: %s", e)
    return tarayici.new_context(**ayar)


def oturumu_garanti_et(page: Page, tc: str, sifre: str) -> None:
    """Önce mevcut oturumla kiralama sayfasını dener; sadece gerçekten çıkış yapılmışsa giriş yapar."""
    page.goto(config.BASE_URL + config.KIRALIK_PATH, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#lblAdSoyad, #txtTCPasaport", timeout=POSTBACK_TIMEOUT_MS)
    except PlaywrightTimeout:
        pass
    if page.query_selector("#lblAdSoyad"):
        return
    giris_yap(page, tc, sifre)
    page.context.storage_state(path=str(OTURUM_YOLU))


def giris_yap(page: Page, tc: str, sifre: str) -> None:
    sayi = bugunku_giris_sayisi()
    if sayi >= GUNLUK_GIRIS_LIMITI:
        raise GirisKotasi(f"Bugün zaten {sayi} kez giriş yapıldı, limit {GUNLUK_GIRIS_LIMITI}")
    log.info("Giriş yapılıyor (bugün %d. giriş)", sayi + 1)
    _giris_say()
    yanit = page.goto(config.BASE_URL + GIRIS_PATH, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#txtTCPasaport", timeout=POSTBACK_TIMEOUT_MS)
    except PlaywrightTimeout as e:
        # Engel/Cloudflare sayfası mı, anlamak için ne gördüğümüzü yaz.
        durum = yanit.status if yanit else "?"
        metin = " ".join((page.inner_text("body") or "").split())[:200]
        raise GirisHatasi(f"Giriş sayfası açılmadı (HTTP {durum}, başlık {page.title()!r}): {metin}") from e
    page.fill("#txtTCPasaport", tc)
    page.fill("#txtSifre", sifre)
    page.click("#btnGirisYap")
    try:
        page.wait_for_selector("#lblAdSoyad", timeout=POSTBACK_TIMEOUT_MS)
    except PlaywrightTimeout as e:
        if KOTA_METNI in (page.inner_text("body") or "").lower():
            raise GirisKotasi("Site günlük giriş kotası doldu") from e
        raise GirisHatasi(f"Giriş başarısız, sayfa: {page.url}") from e


def _dropdown_sec(page: Page, select_id: str, deger: str, zorla: bool = False) -> None:
    """Select2 gizli <select> kullandığı için değeri JS ile verip postback'i biz tetikliyoruz.
    zorla=True: değer aynı olsa da postback atar (tabloyu tazelemek için)."""
    # Önceki postback DOM'u yeniden çizerken kutu bir an yok olabilir; seçenek gelene kadar bekle.
    page.wait_for_selector(f"#{select_id} option[value='{deger}']", state="attached",
                           timeout=POSTBACK_TIMEOUT_MS)
    mevcut = page.eval_on_selector(f"#{select_id}", "el => el.value")
    if mevcut == deger and not zorla:
        return
    with page.expect_response(lambda r: "satiskiralik" in r.url and r.request.method == "POST",
                              timeout=POSTBACK_TIMEOUT_MS):
        page.eval_on_selector(
            f"#{select_id}",
            "(el, v) => { el.value = v; __doPostBack(el.name, ''); }",
            deger,
        )
    _async_bitsin(page)
    page.wait_for_function("([id, v]) => document.getElementById(id)?.value === v", arg=[select_id, deger],
                           timeout=POSTBACK_TIMEOUT_MS)


def _async_bitsin(page: Page) -> None:
    """UpdatePanel cevabı geldikten sonra DOM değişimi biraz gecikir; bitmesini bekle."""
    page.wait_for_function(
        "() => !(window.Sys && Sys.WebForms && Sys.WebForms.PageRequestManager"
        " && Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack())",
        timeout=POSTBACK_TIMEOUT_MS,
    )


class YanlisSeans(RuntimeError):
    pass


def seansi_dogrula(page: Page, salon: str, seans: Seans) -> None:
    """Tıklamadan hemen önce: doğru salon seçili mi, butonun yanındaki saat hedef saat mi."""
    secili = page.eval_on_selector("#ddlSalonFiltre", "el => el.value")
    if secili != SALON_IDLERI[salon]:
        raise YanlisSeans(f"Seçili salon farklı: {secili}")
    saat_id = seans.rezervasyon_id.replace("lbRezervasyon", "lblSeans")
    saat = (page.text_content(f"#{saat_id}") or "").strip()
    if saat != seans.saat:
        raise YanlisSeans(f"Buton saati {saat!r}, beklenen {seans.saat!r}")


def secili_salon(page: Page) -> str | None:
    if "satiskiralik" not in page.url:
        return None
    deger = page.eval_on_selector("#ddlSalonFiltre", "el => el.value")
    return next((ad for ad, sid in SALON_IDLERI.items() if sid == deger), None)


def tabloyu_getir(page: Page, salon: str) -> list[Seans]:
    if "satiskiralik" not in page.url:
        page.goto(config.BASE_URL + config.KIRALIK_PATH, wait_until="domcontentloaded")
    _dropdown_sec(page, "ddlBransFiltre", BRANS_FUTBOL)
    _dropdown_sec(page, "ddlTesisFiltre", TESIS_FLORYA)
    _dropdown_sec(page, "ddlSalonFiltre", SALON_IDLERI[salon], zorla=True)
    return seanslari_oku(page.content())


SECILI_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*\(\s*(\d{2}:\d{2})")


def secili_seans_uyuyor(metin: str, seans: Seans) -> bool:
    """'1.10.2026 (14:00:00 - 15:00:00)' gibi metin (gün/ay başında sıfır olmayabilir) hedefle aynı mı."""
    m = SECILI_RE.search(metin)
    if not m:
        return False
    gun, ay, yil, saat = m.groups()
    return date(int(yil), int(ay), int(gun)) == seans.tarih and saat == seans.saat[:5]


def sepete_ekle(page: Page, salon: str, seans: Seans) -> None:
    """Rezervasyon → alert'i onayla → Sepete Ekle. Sonunda SMS kutusu görünür olmalı."""
    seansi_dogrula(page, salon, seans)
    page.once("dialog", lambda d: d.accept())
    page.click(f"#{seans.rezervasyon_id}")
    page.wait_for_selector(SEPETE_EKLE, timeout=POSTBACK_TIMEOUT_MS)
    # Sayfa "24.09.2026 (14:00:00 - 15:00:00)" gösterir; sepete atmadan önce doğru seans mı bak.
    secilen = page.text_content(SECILI_SEANS) or ""
    if not secili_seans_uyuyor(secilen, seans):
        raise YanlisSeans(f"Seçili seans {secilen.strip()!r}, beklenen {seans.tarih} {seans.saat}")
    page.click(SEPETE_EKLE)
    page.wait_for_selector(SMS_KUTUSU, state="visible", timeout=POSTBACK_TIMEOUT_MS)


SMS_TAMAM, SMS_YANLIS, SMS_SIFIRLANDI = "tamam", "yanlis", "sifirlandi"


def sms_dogrula(page: Page, kod: str) -> str:
    """SMS_TAMAM: kod kabul edildi (sepete geçti). SMS_YANLIS: kutu hâlâ açık, aynı SMS için tekrar
    denenebilir. SMS_SIFIRLANDI: site başa döndü; seansı yeniden Sepete Ekle yapmak (yeni SMS) gerekir."""
    page.fill(SMS_KUTUSU, kod)
    page.click(SMS_GONDER)
    try:
        page.wait_for_url(f"**{config.SEPET_PATH.removesuffix('.aspx')}**", timeout=SMS_KABUL_TIMEOUT_MS)
        return SMS_TAMAM
    except PlaywrightTimeout:
        return SMS_YANLIS if page.is_visible(SMS_KUTUSU) else SMS_SIFIRLANDI


def sepet_tarihleri(page: Page) -> set[date]:
    page.goto(config.BASE_URL + config.SEPET_PATH, wait_until="domcontentloaded")
    page.wait_for_selector("#lblAdSoyad", timeout=POSTBACK_TIMEOUT_MS)
    return sepetteki_tarihler(page.content())


def sepeti_oku(page: Page) -> list[SepetKalemi]:
    page.goto(config.BASE_URL + config.SEPET_PATH, wait_until="domcontentloaded")
    page.wait_for_selector("#lblAdSoyad", timeout=POSTBACK_TIMEOUT_MS)
    return sepet_kalemleri(page.content(), tuple(SALON_IDLERI))


def sepetten_sil(page: Page, kalem: SepetKalemi) -> None:
    """Sepet sayfasında ilgili satırın 'Ürünü Kaldır' butonuna basar (confirm onaylanır)."""
    guncel = next((k for k in sepeti_oku(page) if (k.tarih, k.saat, k.salon) == (kalem.tarih, kalem.saat, kalem.salon)), None)
    if not guncel or not guncel.sil_id:
        return
    page.once("dialog", lambda d: d.accept())
    with page.expect_navigation(timeout=POSTBACK_TIMEOUT_MS):
        page.click(f"#{guncel.sil_id}")
    kalan = sepet_kalemleri(page.content(), tuple(SALON_IDLERI))
    if any((k.tarih, k.saat, k.salon) == (kalem.tarih, kalem.saat, kalem.salon) for k in kalan):
        raise RuntimeError(f"Sepetten silinemedi: {kalem}")
