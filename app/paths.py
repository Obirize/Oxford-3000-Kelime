"""Dosya yollari - hem .py hem .exe olarak calisirken dogru yeri bulur.

PyInstaller ile paketlendiginde iki ayri konum vardir:

  * paket ici (salt okunur)  -> sys._MEIPASS altina acilir, her calistirmada
    yeniden olusur. Kelime listesi (oxford3000.json) burada durur.
  * exe'nin yani (yazilabilir) -> kullanicinin ilerlemesi, yedekler ve ses
    onbellegi buraya yazilir; exe guncellense bile korunur.

Kaynak koddan calisirken ikisi de proje klasorudur.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """Yazilabilir kok klasor: exe'nin bulundugu yer (veya proje klasoru)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return PROJECT_DIR


def bundle_dir() -> Path:
    """Pakete gomulu salt okunur dosyalarin koku."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return PROJECT_DIR


def data_dir() -> Path:
    """Kullanici verisi (ilerleme, yedek, ses) - her zaman yazilabilir."""
    path = app_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def words_json() -> Path:
    """Kelime listesi.

    Kullanici `py tools/build_dataset.py` ile yeniden uretmisse exe'nin
    yanindaki kopya kullanilir; yoksa pakete gomulu olan.
    """
    local = app_dir() / "data" / "oxford3000.json"
    if local.exists():
        return local
    return bundle_dir() / "data" / "oxford3000.json"


def asset(name: str) -> Path:
    """assets/ altindaki bir dosya (ikon vb.)."""
    return bundle_dir() / "assets" / name
