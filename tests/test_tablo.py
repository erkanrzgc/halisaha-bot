from datetime import date
from pathlib import Path

from bot.tablo import seans_bul, seanslari_oku

HTML = (Path(__file__).parent / "fixtures" / "seans_tablosu.html").read_text(encoding="utf-8")


def test_bos_gunler_seans_icermez():
    seanslar = seanslari_oku(HTML)
    assert not [s for s in seanslar if s.tarih == date(2026, 9, 21)]


def test_musait_seansin_rezervasyon_id_si_var():
    s = seans_bul(seanslari_oku(HTML), date(2026, 9, 23), "08:00 - 09:00")
    assert s.musait
    assert s.rezervasyon_id == "pageContent_rptList_rpChild_2_lbRezervasyon_0"


def test_baskasinin_rezervasyonu_musait_degil():
    s = seans_bul(seanslari_oku(HTML), date(2026, 9, 23), "18:00 - 19:00")
    assert not s.musait
    assert s.durum == "dolu:Başkasının Rezervasyonu"


def test_listede_olmayan_saat_none_doner():
    assert seans_bul(seanslari_oku(HTML), date(2026, 9, 25), "22:00 - 23:00") is None
