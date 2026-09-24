from datetime import date

from bot.config import CUMA, CUMARTESI, Hedef
from bot.secim import bilinmeyen_etiketler, en_iyi_aday, hafta_tarihi
from bot.tablo import Seans

SALI = date(2026, 9, 22)
CUMA_T = date(2026, 9, 25)
CMT_T = date(2026, 9, 26)
HEDEFLER = (
    Hedef(CUMA, "21:00 - 22:00"),
    Hedef(CUMA, "20:00 - 21:00"),
    Hedef(CUMARTESI, "21:00 - 22:00"),
)


def musait(t, saat, n=0):
    return Seans(t, saat, f"btn_{t.day}_{saat[:2]}_{n}", "musait")


def dolu(t, saat, etiket="Başkasının Rezervasyonu"):
    return Seans(t, saat, None, "dolu:" + etiket)


def test_hafta_tarihi():
    assert hafta_tarihi(SALI, CUMA) == CUMA_T


def test_ilk_hedef_ilk_salon_secilir():
    tablolar = {
        "S1": [musait(CUMA_T, "20:00 - 21:00"), musait(CUMA_T, "21:00 - 22:00")],
        "S2": [musait(CUMA_T, "21:00 - 22:00", 2)],
    }
    a = en_iyi_aday(HEDEFLER, tablolar, SALI)
    assert (a.salon, a.seans.saat) == ("S1", "21:00 - 22:00")


def test_salon1_doluysa_salon2_ye_gecer_sonra_saate():
    tablolar = {
        "S1": [dolu(CUMA_T, "21:00 - 22:00"), musait(CUMA_T, "20:00 - 21:00")],
        "S2": [musait(CUMA_T, "21:00 - 22:00", 2)],
    }
    a = en_iyi_aday(HEDEFLER, tablolar, SALI)
    assert (a.salon, a.seans.saat) == ("S2", "21:00 - 22:00")


def test_cuma_hepsi_doluysa_cumartesi():
    tablolar = {"S1": [dolu(CUMA_T, "21:00 - 22:00"), musait(CMT_T, "21:00 - 22:00")]}
    assert en_iyi_aday(HEDEFLER, tablolar, SALI).tarih == CMT_T


def test_cuma_bizimse_cumartesiye_bakmaz():
    tablolar = {"S1": [dolu(CUMA_T, "21:00 - 22:00", "Sepet"), musait(CMT_T, "21:00 - 22:00")]}
    assert en_iyi_aday(HEDEFLER, tablolar, SALI, bizim_etiketler=("Sepet",)) is None


def test_bilinmeyen_etiket_tek_basina_engellemez():
    tablolar = {"S1": [dolu(CUMA_T, "21:00 - 22:00", "Sepet"), musait(CMT_T, "21:00 - 22:00")]}
    assert en_iyi_aday(HEDEFLER, tablolar, SALI).tarih == CMT_T
    assert bilinmeyen_etiketler(tablolar, {CUMA_T}) == {"dolu:Sepet"}


def test_hic_musait_yoksa_none():
    assert en_iyi_aday(HEDEFLER, {"S1": [dolu(CUMA_T, "21:00 - 22:00")]}, SALI) is None


def test_gecmis_gun_atlanir():
    cmt = date(2026, 9, 26)
    tablolar = {"S1": [musait(CUMA_T, "21:00 - 22:00")]}
    assert en_iyi_aday(HEDEFLER, tablolar, cmt) is None
