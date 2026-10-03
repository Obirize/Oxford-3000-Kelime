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


# ---------------------------------------------------------------- test ciktisi
# Dort test aracinda ayni `check`/`failures`/ozet kodu kopyalanmisti; tek yer.
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> bool:
    """Bir kontrolu yazdirir ve basarisizsa ozet icin kaydeder."""
    print(f"  {'✅' if condition else '❌'} {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        _failures.append(label)
    return bool(condition)


def report(success: str) -> int:
    """Ozet satirini basar; cikis kodu dondurur (0 = hepsi gecti)."""
    print("\n" + "=" * 60)
    if _failures:
        print(f"❌ {len(_failures)} KONTROL BASARISIZ:")
        for item in _failures:
            print(f"   - {item}")
        return 1
    print(success)
    return 0


def gui_app(db_name: str, view: str = ""):
    """Test icin guvenli bir veritabani + acilmis AppWindow dondurur.

    Gercek uygulamayla ayni olcekte cizilsin diye DPI farkindaligini da acar;
    yoksa testler kullanicinin gormedigi bir duzeni dogrular.
    """
    from app import dpi                       # gec import: tkinter'i erken yukleme
    from app.ui.app_window import AppWindow

    dpi.enable()
    path = test_db(db_name)
    conn = db.connect(path)
    db.sync_words(conn)
    db.set_setting(conn, "audio", 0)          # test makinesi konusmasin
    app = AppWindow(conn)
    app.update()
    if view:
        app.show(view)
        app.update()
    return app, conn, path
