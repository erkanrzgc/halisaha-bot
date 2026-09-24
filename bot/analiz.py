"""gozlem.csv'den her seansın ne zaman açıldığını ve ne kadar sürede kapıldığını çıkarır.

python -m bot.analiz                 # sadece hedef saatler (20-23)
python -m bot.analiz --hepsi
"""
import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bot import config
from bot.gozlem import CSV_YOLU, YOK

GUNLER = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


@dataclass(frozen=True)
class Olay:
    zaman: datetime
    eski: str
    yeni: str


@dataclass(frozen=True)
class Ozet:
    salon: str
    tarih: str
    saat: str
    acildi: datetime | None  # yok → musait ilk geçiş
    kapildi: datetime | None  # musait → başka bir şey ilk geçiş (açıldıktan sonra)


def oku(yol: Path) -> dict[tuple[str, str, str], list[Olay]]:
    olaylar: dict[tuple[str, str, str], list[Olay]] = {}
    with yol.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["salon"] == "HATA":
                continue
            olay = Olay(datetime.fromisoformat(r["zaman"]), r["eski"], r["yeni"])
            olaylar.setdefault((r["salon"], r["tarih"], r["saat"]), []).append(olay)
    return olaylar


def ozetle(anahtar: tuple[str, str, str], olaylar: list[Olay]) -> Ozet:
    acildi = next((o.zaman for o in olaylar if o.eski == YOK and o.yeni == "musait"), None)
    kapildi = next(
        (o.zaman for o in olaylar if o.eski == "musait" and o.yeni != "musait" and (acildi is None or o.zaman >= acildi)),
        None,
    )
    return Ozet(*anahtar, acildi, kapildi)


def _sure(a: datetime | None, b: datetime | None) -> str:
    if not a or not b:
        return "-"
    sn = int((b - a).total_seconds())
    return f"{sn // 60} dk {sn % 60} sn" if sn >= 60 else f"{sn} sn"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hepsi", action="store_true", help="tüm saatler, sadece hedefler değil")
    args = ap.parse_args()
    if not CSV_YOLU.exists():
        raise SystemExit("gozlem.csv yok, önce gözlemciyi çalıştır: python -m bot.gozlem")
    hedef_saatler = set(config.SAAT_SIRASI)
    ozetler = [ozetle(k, v) for k, v in oku(CSV_YOLU).items() if args.hepsi or k[2] in hedef_saatler]
    print(f"{'Seans':34} {'Açıldı':18} {'Kapıldı':18} {'Süre':10}")
    for o in sorted(ozetler, key=lambda o: (o.tarih, o.saat, o.salon)):
        gun = GUNLER[datetime.fromisoformat(o.tarih).weekday()]
        acildi = f"{GUNLER[o.acildi.weekday()]} {o.acildi:%H:%M:%S}" if o.acildi else "-"
        kapildi = f"{GUNLER[o.kapildi.weekday()]} {o.kapildi:%H:%M:%S}" if o.kapildi else "-"
        print(f"{gun} {o.tarih[5:]} {o.saat} {o.salon:12} {acildi:18} {kapildi:18} {_sure(o.acildi, o.kapildi):10}")


if __name__ == "__main__":
    main()
