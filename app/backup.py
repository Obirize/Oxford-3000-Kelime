"""Otomatik yedekleme ve kurtarma.

Ilerleme tek bir SQLite dosyasinda (data/progress.db) tutulur. Bu dosyanin
kazara silinmesi/bozulmasi tum emegi yok eder, bu yuzden:

  * program her acilista ve her temiz kapanista bir yedek alir,
  * son KEEP yedek saklanir (eskiler otomatik silinir),
  * acilista ilerleme dosyasi yoksa veya bozuksa en yeni yedek geri yuklenir.

Yedekler data/backups/ altinda, dosya adinda tarih-saat ile durur.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import paths

ROOT = paths.PROJECT_DIR
BACKUP_DIR = paths.data_dir() / "backups"
PREFIX = "progress_"
SUFFIX = ".db"
KEEP = 20                 # saklanacak yedek sayisi
MIN_GAP_MINUTES = 10      # bu sureden once ikinci yedek alinmaz


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def list_backups() -> list[Path]:
    """Yeniden eskiye dogru siralanmis yedek listesi."""
    if not BACKUP_DIR.exists():
        return []
    files = [p for p in BACKUP_DIR.glob(f"{PREFIX}*{SUFFIX}") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def is_healthy(path: Path) -> bool:
    """Dosya gecerli bir ilerleme veritabani mi?"""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            conn.execute("SELECT COUNT(*) FROM progress").fetchone()
        finally:
            conn.close()
        return True
    except sqlite3.Error:
        return False


def has_progress(path: Path) -> bool:
    """Icinde korunmaya deger ilerleme var mi? (bos veritabanini yedeklemeyelim)"""
    if not is_healthy(path):
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM progress WHERE state <> 'pool'"
            ).fetchone()
            return bool(row and row[0] > 0)
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _prune() -> None:
    for old in list_backups()[KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass


def create(db_path: Path, *, force: bool = False) -> Path | None:
    """Yedek alir. Ilerleme yoksa veya cok yeni bir yedek varsa atlar."""
    if not has_progress(db_path):
        return None

    existing = list_backups()
    if not force and existing:
        age = datetime.now() - datetime.fromtimestamp(existing[0].stat().st_mtime)
        if age.total_seconds() < MIN_GAP_MINUTES * 60:
            return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # Ayni saniyede alinan iki yedek birbirinin uzerine yazmasin.
    stamp = _stamp()
    target = BACKUP_DIR / f"{PREFIX}{stamp}{SUFFIX}"
    serial = 2
    while target.exists():
        target = BACKUP_DIR / f"{PREFIX}{stamp}-{serial}{SUFFIX}"
        serial += 1
    try:
        # sqlite'in kendi yedekleme API'si: acik baglanti varken de guvenli
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
    except sqlite3.Error:
        try:
            shutil.copy2(db_path, target)
        except OSError:
            return None
    _prune()
    return target


def restore(backup_path: Path, db_path: Path) -> bool:
    """Bir yedegi ilerleme dosyasinin uzerine yazar (once mevcudu kenara alir)."""
    if not is_healthy(backup_path):
        return False
    if db_path.exists():
        try:
            db_path.replace(db_path.with_suffix(".db.replaced"))
        except OSError:
            pass
    try:
        shutil.copy2(backup_path, db_path)
        return True
    except OSError:
        return False


def recover_if_needed(db_path: Path) -> Path | None:
    """Acilista cagrilir: ilerleme dosyasi yok/bozuksa en yeni saglam yedegi kurar.

    Geri yuklenen yedegin yolunu dondurur, mudahale gerekmediyse None.
    """
    if is_healthy(db_path):
        return None
    for candidate in list_backups():
        if is_healthy(candidate) and restore(candidate, db_path):
            return candidate
    return None


def describe(path: Path) -> str:
    """Yedek hakkinda kisa ozet: '19.08.2026 13:44 · 412 kelime · 0.4 MB'"""
    when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
    size = path.stat().st_size / 1_048_576
    words = "?"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            words = conn.execute(
                "SELECT COUNT(*) FROM progress WHERE state <> 'pool'"
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return f"{when}  ·  {words} kelime  ·  {size:.2f} MB"
