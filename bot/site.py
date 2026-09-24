"""spor.istanbul sitesiyle Playwright üzerinden konuşan katman. Tüm seçiciler burada."""
import logging
from datetime import date

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from bot import config
from bot.tablo import Seans, seanslari_oku, sepetteki_tarihler

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


class GirisHatasi(RuntimeError):
    pass


def giris_yap(page: Page, tc: str, sifre: str) -> None:
    page.goto(config.BASE_URL + GIRIS_PATH, wait_until="domcontentloaded")
    page.wait_for_selector("#txtTCPasaport", timeout=POSTBACK_TIMEOUT_MS)
    page.fill("#txtTCPasaport", tc)
    page.fill("#txtSifre", sifre)
    page.click("#btnGirisYap")
    try:
        page.wait_for_selector("#lblAdSoyad", timeout=POSTBACK_TIMEOUT_MS)
    except PlaywrightTimeout as e:
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


def sepete_ekle(page: Page, salon: str, seans: Seans) -> None:
    """Rezervasyon → alert'i onayla → Sepete Ekle. Sonunda SMS kutusu görünür olmalı."""
    seansi_dogrula(page, salon, seans)
    page.once("dialog", lambda d: d.accept())
    page.click(f"#{seans.rezervasyon_id}")
    page.wait_for_selector(SEPETE_EKLE, timeout=POSTBACK_TIMEOUT_MS)
    # Sayfa "24.09.2026 (14:00:00 - 15:00:00)" gösterir; sepete atmadan önce doğru seans mı bak.
    secilen = page.text_content(SECILI_SEANS) or ""
    if f"{seans.tarih:%d.%m.%Y}" not in secilen or seans.saat[:5] not in secilen:
        raise YanlisSeans(f"Seçili seans {secilen.strip()!r}, beklenen {seans.tarih} {seans.saat}")
    page.click(SEPETE_EKLE)
    page.wait_for_selector(SMS_KUTUSU, state="visible", timeout=POSTBACK_TIMEOUT_MS)


def sms_dogrula(page: Page, kod: str) -> None:
    page.fill(SMS_KUTUSU, kod)
    page.click(SMS_GONDER)
    page.wait_for_url(f"**{config.SEPET_PATH.removesuffix('.aspx')}**", timeout=POSTBACK_TIMEOUT_MS)


def sepet_tarihleri(page: Page) -> set[date]:
    page.goto(config.BASE_URL + config.SEPET_PATH, wait_until="domcontentloaded")
    page.wait_for_selector("#lblAdSoyad", timeout=POSTBACK_TIMEOUT_MS)
    return sepetteki_tarihler(page.content())
