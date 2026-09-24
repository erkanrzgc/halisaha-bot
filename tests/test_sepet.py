from datetime import date

from bot.tablo import sepette_mi

SEPET = """<table><tr>
<td><div class="product-cell"><span class="product-name">FLORYA SPOR TESİSİ - HALI SAHA 1 - FUTBOL - Cuma ( 14:00:00 - 15:00:00 )</span></div></td>
<td>25.09.2026 - 25.09.2026</td></tr></table>"""


def test_sepetteki_seans_bulunur():
    assert sepette_mi(SEPET, date(2026, 9, 25), "14:00 - 15:00", "HALI SAHA 1")


def test_farkli_saat_salon_tarih_bulunmaz():
    assert not sepette_mi(SEPET, date(2026, 9, 25), "20:00 - 21:00", "HALI SAHA 1")
    assert not sepette_mi(SEPET, date(2026, 9, 25), "14:00 - 15:00", "HALI SAHA 2")
    assert not sepette_mi(SEPET, date(2026, 9, 26), "14:00 - 15:00", "HALI SAHA 1")


def test_bos_sepet():
    assert not sepette_mi("<html></html>", date(2026, 9, 25), "14:00 - 15:00", "HALI SAHA 1")


def test_sepetteki_tarihler():
    from bot.tablo import sepetteki_tarihler
    assert sepetteki_tarihler(SEPET) == {date(2026, 9, 25)}
    assert sepetteki_tarihler("<html></html>") == set()
