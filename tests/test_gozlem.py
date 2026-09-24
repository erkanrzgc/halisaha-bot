from datetime import datetime

from bot.analiz import Olay, ozetle
from bot.gozlem import YOK, farklar

K = ("HALI SAHA 1", "2026-10-02", "21:00 - 22:00")


def t(saat: str) -> datetime:
    return datetime.fromisoformat(f"2026-09-29T{saat}")


def test_farklar_sadece_degisenleri_verir():
    onceki = {K: "musait", ("S", "d", "x"): "dolu:A"}
    simdi = {K: "dolu:Başkasının Rezervasyonu", ("S", "d", "x"): "dolu:A", ("S", "d", "y"): "musait"}
    assert farklar(onceki, simdi) == [
        (K, "musait", "dolu:Başkasının Rezervasyonu"),
        (("S", "d", "y"), YOK, "musait"),
    ]


def test_kaybolan_seans_yok_olur():
    assert farklar({K: "musait"}, {}) == [(K, "musait", YOK)]


def test_ozet_acilis_ve_kapilma():
    o = ozetle(K, [Olay(t("00:00:05"), YOK, "musait"), Olay(t("00:00:35"), "musait", YOK)])
    assert o.acildi == t("00:00:05")
    assert o.kapildi == t("00:00:35")


def test_baslangicta_musait_olan_acilis_saymaz():
    o = ozetle(K, [Olay(t("10:00:00"), "baslangic", "musait"), Olay(t("10:01:00"), "musait", "dolu:X")])
    assert o.acildi is None
    assert o.kapildi == t("10:01:00")


def test_son_durum_csvden_okunur(tmp_path):
    from bot.gozlem import son_durum
    yol = tmp_path / "g.csv"
    yol.write_text(
        "zaman,salon,tarih,saat,eski,yeni\n"
        "t1,S1,2026-10-02,21:00 - 22:00,yok,musait\n"
        "t2,S1,2026-10-02,21:00 - 22:00,musait,dolu:X\n"
        "t3,S1,2026-10-02,20:00 - 21:00,musait,yok\n"
        "t4,HATA,,,,TimeoutError\n",
        encoding="utf-8",
    )
    assert son_durum(yol) == {("S1", "2026-10-02", "21:00 - 22:00"): "dolu:X"}
    assert son_durum(tmp_path / "yok.csv") == {}
