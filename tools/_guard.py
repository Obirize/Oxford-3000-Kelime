"""Test araclari icin koruma.

Gecmiste bir test araci (tools/smoke.py) dogrudan data/progress.db kullanip
kullanicinin gercek ilerlemesini silmisti. Bu bir daha olmasin diye her test
araci kendi veritabanini `test_db()` uzerinden almak zorunda: gercek ilerleme
dosyasi istenirse program calismayi reddeder.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


def test_db(name: str) -> str:
    """Test icin guvenli bir veritabani yolu dondurur ve varsa siler."""
    path = Path(name)
    if not path.is_absolute():
        path = db.ROOT / path

    if path.resolve() == db.DB_PATH.resolve():
        raise SystemExit(
            "DURDURULDU: test araci gercek ilerleme dosyasini "
            f"({db.DB_PATH}) kullanamaz. Ayri bir test dosyasi ver."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return str(path)


def cleanup(*paths: str) -> None:
    """Test veritabanlarini siler; gercek ilerleme dosyasina asla dokunmaz."""
    for item in paths:
        path = Path(item)
        if not path.is_absolute():
            path = db.ROOT / path
        if path.resolve() == db.DB_PATH.resolve():
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
