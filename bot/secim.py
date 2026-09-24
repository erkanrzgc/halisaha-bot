"""Hangi seansın alınacağına karar veren saf mantık (tarayıcısız, test edilebilir)."""
from dataclasses import dataclass
from datetime import date, timedelta

from bot.config import Hedef
from bot.tablo import Seans, seans_bul

BASKASININ = "Başkasının"


@dataclass(frozen=True)
class Aday:
    hedef: Hedef
    tarih: date
    salon: str
    seans: Seans


def hafta_tarihi(bugun: date, gun: int) -> date:
    """Bugünün haftasındaki (Pzt başlangıçlı) ilgili günün tarihi."""
    return bugun - timedelta(days=bugun.weekday()) + timedelta(days=gun)


def bizim_rezervasyon_var(seanslar: list[Seans], tarih: date, bizim_etiketler: tuple[str, ...]) -> bool:
    """Sadece bizim olduğu kesin bilinen etiketler sayılır (canlı testte öğrenilecek)."""
    return any(
        s.tarih == tarih and any(e in s.durum for e in bizim_etiketler)
        for s in seanslar
    )


def bilinmeyen_etiketler(tablolar: dict[str, list[Seans]], tarihler: set[date]) -> set[str]:
    """Hedef günlerde 'Başkasının' dışında görülen dolu etiketleri (bizimki olabilir, haber verilir)."""
    return {
        s.durum
        for seanslar in tablolar.values()
        for s in seanslar
        if s.tarih in tarihler and not s.musait and BASKASININ not in s.durum
    }


def en_iyi_aday(
    hedefler: tuple[Hedef, ...],
    tablolar: dict[str, list[Seans]],
    bugun: date,
    bizim_etiketler: tuple[str, ...] = (),
) -> Aday | None:
    """Öncelik: hedef sırası (gün, saat) → salon sırası. Günde 1 kuralı gereği
    daha önceki bir hedef gününde zaten rezervasyonumuz varsa sonraki günlere bakılmaz."""
    alinan_gunler = {
        hafta_tarihi(bugun, h.gun)
        for h in hedefler
        for seanslar in tablolar.values()
        if bizim_rezervasyon_var(seanslar, hafta_tarihi(bugun, h.gun), bizim_etiketler)
    }
    if alinan_gunler:
        return None
    for hedef in hedefler:
        tarih = hafta_tarihi(bugun, hedef.gun)
        if tarih < bugun:
            continue
        for salon, seanslar in tablolar.items():
            s = seans_bul(seanslar, tarih, hedef.saat)
            if s and s.musait:
                return Aday(hedef, tarih, salon, s)
    return None


def acilmis_gunler(tablolar: dict[str, list[Seans]]) -> set[date]:
    return {s.tarih for seanslar in tablolar.values() for s in seanslar}
