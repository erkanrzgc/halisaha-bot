"""Seans tablosu (satiskiralik.aspx) HTML'ini okur. Tarayıcıdan bağımsız, test edilebilir."""
import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup

TARIH_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


@dataclass(frozen=True)
class Seans:
    tarih: date
    saat: str  # "20:00 - 21:00"
    rezervasyon_id: str | None  # tıklanacak <a> id'si; None = müsait değil
    durum: str  # "musait" | "dolu:<etiket>"

    @property
    def musait(self) -> bool:
        return self.rezervasyon_id is not None


def seanslari_oku(html: str) -> list[Seans]:
    soup = BeautifulSoup(html, "html.parser")
    kok = soup.select_one("#pageContent_Div1") or soup
    seanslar: list[Seans] = []
    for panel in kok.select("div.panel.panel-info"):
        baslik = panel.select_one("h3.panel-title")
        m = TARIH_RE.search(baslik.get_text(" ", strip=True)) if baslik else None
        if not m:
            continue
        tarih = datetime.strptime(m.group(1), "%d.%m.%Y").date()
        for kutu in panel.select("div.wellPlus"):
            seans = _kutu_oku(kutu, tarih)
            if seans:
                seanslar.append(seans)
    return seanslar


def _kutu_oku(kutu, tarih: date) -> Seans | None:
    saat_etiketi = kutu.select_one("span.lblStyle")
    if not saat_etiketi:  # yarım çizilmiş sayfa
        return None
    saat = saat_etiketi.get_text(strip=True)
    buton = kutu.select_one('a[id*="lbRezervasyon"]')
    if buton:
        return Seans(tarih, saat, buton["id"], "musait")
    etiket = kutu.select_one("label")
    return Seans(tarih, saat, None, "dolu:" + (etiket.get_text(strip=True) if etiket else "?"))


def seans_bul(seanslar: list[Seans], tarih: date, saat: str) -> Seans | None:
    return next((s for s in seanslar if s.tarih == tarih and s.saat == saat), None)


def sepette_mi(html: str, tarih: date, saat: str, salon: str) -> bool:
    """Sepet sayfasında (uyesepet) bu seansın satırı var mı?
    Satır: 'FLORYA SPOR TESİSİ - HALI SAHA 1 - FUTBOL - Cuma ( 14:00:00 - 15:00:00 )' + '25.09.2026 - ...'."""
    soup = BeautifulSoup(html, "html.parser")
    for ad in soup.select("span.product-name"):
        satir = ad.find_parent("tr")
        metin = satir.get_text(" ", strip=True) if satir else ad.get_text(strip=True)
        if salon in metin and f"( {saat[:5]}:00" in metin and f"{tarih:%d.%m.%Y}" in metin:
            return True
    return False


def sepetteki_tarihler(html: str) -> set[date]:
    """Sepetteki FUTBOL kalemlerinin tarihleri (günde 1 kuralı için)."""
    soup = BeautifulSoup(html, "html.parser")
    tarihler: set[date] = set()
    for ad in soup.select("span.product-name"):
        satir = ad.find_parent("tr")
        metin = satir.get_text(" ", strip=True) if satir else ad.get_text(strip=True)
        m = TARIH_RE.search(metin)
        if "FUTBOL" in metin and m:
            tarihler.add(datetime.strptime(m.group(1), "%d.%m.%Y").date())
    return tarihler
