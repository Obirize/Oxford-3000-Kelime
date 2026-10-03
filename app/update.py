"""Yeni surum kontrolu (GitHub Releases).

Ne yapar
--------
Acilista arka planda GitHub'in acik API'sine TEK bir istek atar:

    GET https://api.github.com/repos/<depo>/releases/latest

Donen surum numarasi bu surumden yeniyse arayuzde kucuk bir not gosterilir.
Indirme OTOMATIK DEGILDIR: kullanici tiklarsa tarayicida surum sayfasi acilir,
kurulumu kendisi yapar. Program kendini degistirmez.

Gizlilik
--------
Giden istekte hicbir kullanici verisi yoktur - ne ilerleme, ne kimlik, ne de
bir tanimlayici. Yalnizca bir GET ve "Oxford3000/<surum>" tarayici kimligi.
Ayarlardan kapatilabilir (`update_check`); kapaliyken hic istek atilmaz.

Is parcacigi kurali
-------------------
Ag istegi arka planda yapilir ama Tk'ya ve SQLite'a YALNIZCA ana is
parcacigindan dokunulur. Arka plan is parcacigi sadece `fetch()` cagirip
sonucu bir kuyruga birakir; ana is parcacigi `poll()` ile kuyruga bakar.
(Arka plandan `widget.after` cagirmak Tk'da guvenli degildir: "main thread is
not in main loop" hatasi verebilir.)

Dayaniksizlik
-------------
Internet yoksa, GitHub yanit vermezse veya JSON beklendigi gibi degilse
sessizce vazgecilir; program normal calismaya devam eder.
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.request
from dataclasses import dataclass
from datetime import date

from . import db
from .version import REPO, RELEASES_URL, VERSION, is_newer

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT = 8


@dataclass
class Release:
    version: str          # '1.0.2'
    name: str             # 'Oxford 3000 Kelime v1.0.2'
    url: str              # tarayicida acilacak surum sayfasi

    @property
    def is_newer(self) -> bool:
        return is_newer(self.version)


def fetch() -> Release | None:
    """Son surumu sorgular. Herhangi bir aksilikte None doner."""
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Oxford3000/{VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except Exception:
        return None
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return None
    return Release(
        version=tag.lstrip("vV"),
        name=str(data.get("name") or tag),
        url=str(data.get("html_url") or RELEASES_URL),
    )


def checked_today(conn) -> bool:
    return db.get_setting(conn, "update_last_check", "") == date.today().isoformat()


def mark_checked(conn) -> None:
    db.set_setting(conn, "update_last_check", date.today().isoformat())


def start(conn, *, force: bool = False) -> "queue.Queue | None":
    """Arka planda kontrolu baslatir ve sonucun dusecegi kuyrugu dondurur.

    Ayar kapaliysa veya bugun zaten bakildiysa None doner (istek atilmaz).
    force=True ("Şimdi kontrol et") bu iki siniri da asar.
    """
    if not force:
        if db.get_int(conn, "update_check", 1) != 1 or checked_today(conn):
            return None

    result: queue.Queue = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result.put(fetch())
        except Exception:
            result.put(None)

    threading.Thread(target=worker, daemon=True, name="update-check").start()
    return result


def poll(widget, result: "queue.Queue", on_result, *,
         tries: int = 0, limit: int = 60, delay: int = 400) -> None:
    """Kuyrugu ANA is parcaciginda yoklar; sonuc gelince on_result(...) cagirir.

    Sonuc gelmezse `limit` kez `delay` ms arayla tekrar bakar (varsayilan 24 sn;
    ag zaman asimi 8 sn). Sure dolarsa sessizce vazgecer.
    """
    try:
        release = result.get_nowait()
    except queue.Empty:
        if tries < limit:
            widget.after(delay, lambda: poll(widget, result, on_result,
                                             tries=tries + 1, limit=limit,
                                             delay=delay))
        return
    on_result(release)


def check_async(conn, widget, on_result, *, force: bool = False) -> bool:
    """start() + poll() kisayolu. Kontrol baslatildiysa True."""
    result = start(conn, force=force)
    if result is None:
        return False
    poll(widget, result, on_result)
    return True
