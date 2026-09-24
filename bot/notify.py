"""Telegram bildirimleri ve SMS kodunu kullanıcıdan alma."""
import logging
import re
import time

import requests

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_SEC = 15
LONG_POLL_SEC = 20
KOD_RE = re.compile(r"\b(\d{4,8})\b")


def mesaj_gonder(token: str, chat_id: str, metin: str, foto: bytes | None = None) -> bool:
    """Mesaj (varsa fotoğraflı) gönderir. Bildirim hatası botu durdurmaz, loglanır."""
    try:
        if foto:
            r = requests.post(
                API.format(token=token, method="sendPhoto"),
                data={"chat_id": chat_id, "caption": metin},
                files={"photo": ("ekran.png", foto, "image/png")},
                timeout=TIMEOUT_SEC,
            )
        else:
            r = requests.post(
                API.format(token=token, method="sendMessage"),
                data={"chat_id": chat_id, "text": metin},
                timeout=TIMEOUT_SEC,
            )
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Telegram gönderilemedi: %s", e)
        return False


def _guncellemeler(token: str, offset: int | None, bekle: int) -> list[dict]:
    params = {"timeout": bekle, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(API.format(token=token, method="getUpdates"), params=params, timeout=bekle + TIMEOUT_SEC)
    r.raise_for_status()
    return r.json().get("result", [])


def eski_mesajlari_temizle(token: str) -> int | None:
    """Kod istemeden önce çağrılır ki eski mesajlar kod sanılmasın. Sonraki offset'i döner."""
    try:
        eski = _guncellemeler(token, None, 0)
    except requests.RequestException as e:
        log.error("getUpdates hatası: %s", e)
        return None
    return eski[-1]["update_id"] + 1 if eski else None


def kod_bekle(token: str, chat_id: str, offset: int | None, sure_sn: int) -> str | None:
    """Belirtilen sohbetten gelen ilk 4-8 haneli sayıyı döner; süre dolarsa None."""
    bitis = time.monotonic() + sure_sn
    while time.monotonic() < bitis:
        bekle = max(1, min(LONG_POLL_SEC, int(bitis - time.monotonic())))
        try:
            guncellemeler = _guncellemeler(token, offset, bekle)
        except requests.RequestException as e:
            log.warning("getUpdates hatası, tekrar deneniyor: %s", e)
            time.sleep(1)
            continue
        for g in guncellemeler:
            offset = g["update_id"] + 1
            mesaj = g.get("message") or {}
            if str(mesaj.get("chat", {}).get("id")) != str(chat_id):
                continue
            m = KOD_RE.search(mesaj.get("text", ""))
            if m:
                return m.group(1)
    return None
