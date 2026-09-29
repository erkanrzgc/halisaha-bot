from datetime import date

from bot.site import secili_seans_uyuyor
from bot.tablo import Seans

S = Seans(date(2026, 10, 1), "14:00 - 15:00", "x", "musait")


def test_sifirsiz_gun_kabul():
    assert secili_seans_uyuyor("1.10.2026 (14:00:00 - 15:00:00)", S)


def test_sifirli_gun_kabul():
    assert secili_seans_uyuyor("01.10.2026 (14:00:00 - 15:00:00)", S)


def test_farkli_saat_ya_da_gun_red():
    assert not secili_seans_uyuyor("1.10.2026 (15:00:00 - 16:00:00)", S)
    assert not secili_seans_uyuyor("2.10.2026 (14:00:00 - 15:00:00)", S)
    assert not secili_seans_uyuyor("", S)


def test_giris_sayaci(tmp_path):
    import json
    from bot.site import bugunku_giris_sayisi
    yol = tmp_path / "s.json"
    assert bugunku_giris_sayisi(yol, date(2026, 9, 29)) == 0
    yol.write_text(json.dumps({"2026-09-29": 3}), encoding="utf-8")
    assert bugunku_giris_sayisi(yol, date(2026, 9, 29)) == 3
    assert bugunku_giris_sayisi(yol, date(2026, 9, 30)) == 0  # ertesi gün sıfırlanır
