from datetime import datetime

from bot.nobetci import sicak_mi, sicak_saatler


def test_sicak_saatler_acilislardan_ogrenilir(tmp_path):
    yol = tmp_path / "g.csv"
    yol.write_text(
        "zaman,salon,tarih,saat,eski,yeni\n"
        "2026-09-29T00:00:12+03:00,S1,2026-10-02,21:00 - 22:00,yok,musait\n"  # Salı 00:00 açılış
        "2026-09-29T10:00:00+03:00,S1,2026-10-02,20:00 - 21:00,musait,dolu:X\n"  # kapılma, sayılmaz
        "2026-09-29T11:00:00+03:00,HATA,,,,TimeoutError\n",
        encoding="utf-8",
    )
    saatler = sicak_saatler(yol)
    assert (1, 0) in saatler      # Salı 00
    assert (0, 23) in saatler     # Pazartesi 23 (1 saat önce pay)
    assert (1, 1) in saatler      # Salı 01 (1 saat sonra pay)
    assert (1, 10) not in saatler


def test_sicak_mi():
    assert sicak_mi(datetime(2026, 9, 29, 0, 30), {(1, 0)})
    assert not sicak_mi(datetime(2026, 9, 29, 5, 0), {(1, 0)})


def test_csv_yoksa_bos(tmp_path):
    assert sicak_saatler(tmp_path / "yok.csv") == set()
