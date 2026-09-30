"""al() içindeki SMS tekrar akışı: site ve Telegram sahte (canlı denenemeyen senaryolar)."""
from datetime import date

import pytest

from bot import main, site
from bot.config import Ayarlar, Hedef
from bot.secim import Aday
from bot.tablo import Seans

SEANS = Seans(date(2026, 10, 3), "21:00 - 22:00", "btn", "musait")
ADAY = Aday(Hedef(5, "21:00 - 22:00"), SEANS.tarih, "HALI SAHA 1", SEANS)
AYAR = Ayarlar("tc", "sifre", "tok", "chat")


class SahteSayfa:
    def content(self):
        return "<html></html>"

    def goto(self, *a, **k):
        pass

    def screenshot(self, **k):
        return b""


@pytest.fixture
def ortam(monkeypatch):
    kayit = {"mesajlar": [], "sepete_ekle": 0}
    monkeypatch.setattr(main.site, "secili_salon", lambda p: "HALI SAHA 1")
    monkeypatch.setattr(main.site, "sepete_ekle", lambda *a: kayit.__setitem__("sepete_ekle", kayit["sepete_ekle"] + 1))
    monkeypatch.setattr(main.notify, "eski_mesajlari_temizle", lambda t: None)
    monkeypatch.setattr(main.notify, "mesaj_gonder", lambda t, c, m, foto=None: kayit["mesajlar"].append(m))
    monkeypatch.setattr(main, "sepette_mi", lambda *a: True)
    monkeypatch.setattr(main.threading, "Thread", lambda target, daemon, args: type("T", (), {"start": lambda s: None})())
    return kayit


def _kodlar(monkeypatch, kodlar):
    it = iter(kodlar)
    monkeypatch.setattr(main.notify, "kod_bekle", lambda t, c, o, s: (next(it), o))


def _sonuclar(monkeypatch, sonuclar):
    it = iter(sonuclar)
    monkeypatch.setattr(main.site, "sms_dogrula", lambda p, k: next(it))


def test_yanlis_kod_sonra_dogru_ayni_sms(monkeypatch, ortam):
    _kodlar(monkeypatch, ["1795", "1796"])
    _sonuclar(monkeypatch, [site.SMS_YANLIS, site.SMS_TAMAM])
    assert main.al(SahteSayfa(), AYAR, ADAY) is True
    assert ortam["sepete_ekle"] == 1  # yeniden eklemedi
    assert any("tekrar yaz" in m for m in ortam["mesajlar"])
    assert any("✅" in m for m in ortam["mesajlar"])


def test_site_sifirlaninca_yeniden_ekler(monkeypatch, ortam):
    _kodlar(monkeypatch, ["1795", "2468"])
    _sonuclar(monkeypatch, [site.SMS_SIFIRLANDI, site.SMS_TAMAM])
    monkeypatch.setattr(main.site, "tabloyu_getir", lambda p, s: [SEANS])
    assert main.al(SahteSayfa(), AYAR, ADAY) is True
    assert ortam["sepete_ekle"] == 2  # ilk ekleme + yeniden ekleme
    assert any("YENİ SMS" in m for m in ortam["mesajlar"])


def test_site_sifirlandi_ama_seans_kapildi(monkeypatch, ortam):
    _kodlar(monkeypatch, ["1795"])
    _sonuclar(monkeypatch, [site.SMS_SIFIRLANDI])
    monkeypatch.setattr(main.site, "tabloyu_getir", lambda p, s: [])
    assert main.al(SahteSayfa(), AYAR, ADAY) is True
    assert ortam["sepete_ekle"] == 1
    assert any("kapıldı" in m for m in ortam["mesajlar"])


def test_uc_yanlis_kod_pes_eder(monkeypatch, ortam):
    _kodlar(monkeypatch, ["1", "2", "3"])
    _sonuclar(monkeypatch, [site.SMS_YANLIS] * 3)
    assert main.al(SahteSayfa(), AYAR, ADAY) is True
    assert any("kabul edilmedi." in m for m in ortam["mesajlar"])
    assert not any("✅" in m for m in ortam["mesajlar"])
