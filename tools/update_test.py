"""Guncelleme kontrolu testi.

    py tools/update_test.py

Ag'a CIKMAZ: app.update.fetch sahte bir yanitla degistirilir. Olculen seyler:
  * surum karsilastirmasi (1.0.10 > 1.0.9 gibi tuzaklar dahil),
  * ayar kapaliyken / bugun bakilmisken istek atilmamasi,
  * yeni surumde seridin cikmasi, eski/ayni surumde cikmamasi,
  * "Şimdilik gizle" dedikten sonra ayni surumun bir daha gosterilmemesi,
  * elle kontrolun (Ayarlar -> Şimdi kontrol et) sinirlari asmasi,
  * ag hatasinda (fetch None) programin sessizce devam etmesi.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import db, update                 # noqa: E402
from app.ui.app_window import AppWindow    # noqa: E402
from app.version import VERSION, is_newer  # noqa: E402

from _guard import test_db                 # noqa: E402

TEST_DB = test_db("data/_update.db")
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✅' if condition else '❌'} {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        failures.append(label)


def fake_fetch(version: str | None):
    """fetch() yerine gececek sahte islev. version=None -> ag hatasi."""
    def inner():
        if version is None:
            return None
        return update.Release(version=version, name=f"v{version}",
                              url="https://example.invalid/releases/latest")
    return inner


def run_check(app, version, *, force=False) -> bool:
    """Kontrolu calistirir; is parcacigi bitene kadar arayuzu dondurur."""
    update.fetch = fake_fetch(version)
    started = app.check_updates(force=force)
    for _ in range(60):          # arka plan + after(0) kuyrugu
        app.update()
        app.after(30, lambda: None)
        app.update_idletasks()
        import time
        time.sleep(0.03)
    return started


def visible(app) -> bool:
    return bool(app.update_bar.winfo_manager())


def main() -> int:
    print("\n0) Surum karsilastirmasi")
    cases = [("1.0.2", "1.0.1", True), ("1.0.1", "1.0.1", False),
             ("1.0.0", "1.0.1", False), ("1.0.10", "1.0.9", True),
             ("v2.0", "1.9.9", True), ("", "1.0.1", False),
             ("bozuk", "1.0.1", False)]
    bad = [c for c in cases if is_newer(c[0], c[1]) != c[2]]
    check("surum karsilastirmasi dogru", not bad, str(bad))

    conn = db.connect(TEST_DB)
    db.sync_words(conn)
    db.set_setting(conn, "audio", 0)
    app = AppWindow(conn)
    app.update()

    print("\n1) Yeni surum -> serit cikar")
    run_check(app, "9.9.9")
    check("serit gorunur", visible(app))
    check("serit surumu yaziyor", "9.9.9" in app.update_bar.text.cget("text"),
          app.update_bar.text.cget("text"))
    check("bugun bakildi olarak isaretlendi", update.checked_today(conn))

    print("\n2) 'Şimdilik gizle' -> serit kapanir, bir daha gosterilmez")
    app.update_bar.skip()
    app.update()
    check("serit kapandi", not visible(app))
    check("surum atlandi olarak kaydedildi",
          db.get_setting(conn, "update_skipped") == "9.9.9")
    db.set_setting(conn, "update_last_check", "")   # gunluk siniri sifirla
    run_check(app, "9.9.9")
    check("atlanan surum tekrar gosterilmedi", not visible(app))

    print("\n3) Ayni/eski surum -> serit cikmaz")
    db.set_setting(conn, "update_skipped", "")
    db.set_setting(conn, "update_last_check", "")
    run_check(app, VERSION)
    check("ayni surumde serit yok", not visible(app))
    db.set_setting(conn, "update_last_check", "")
    run_check(app, "0.0.1")
    check("eski surumde serit yok", not visible(app))

    print("\n4) Ag hatasi -> sessizce gecilir")
    db.set_setting(conn, "update_last_check", "")
    run_check(app, None)
    check("serit yok, program ayakta", not visible(app) and app.winfo_exists())
    check("ag hatasinda 'bakildi' isaretlenmedi (yarin yine denenir)",
          not update.checked_today(conn))

    print("\n5) Gunluk sinir ve ayar")
    db.set_setting(conn, "update_last_check", date.today().isoformat())
    started = run_check(app, "9.9.9")
    check("bugun bakildiysa istek atilmaz", not started)
    check("serit yine de cikmadi", not visible(app))

    db.set_setting(conn, "update_last_check",
                   (date.today() - timedelta(days=1)).isoformat())
    db.set_setting(conn, "update_check", "0")
    started = run_check(app, "9.9.9")
    check("ayar kapaliyken istek atilmaz", not started)

    print("\n6) Elle kontrol sinirlari asar")
    db.set_setting(conn, "update_skipped", "9.9.9")
    started = run_check(app, "9.9.9", force=True)
    check("ayar kapali + bugun bakilmis olsa da elle kontrol calisir", started)
    check("elle kontrolde serit cikti", visible(app))

    app.destroy()
    conn.close()
    os.remove(TEST_DB)

    print("\n" + "=" * 60)
    if failures:
        print(f"❌ {len(failures)} KONTROL BASARISIZ:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ GUNCELLEME KONTROLU CALISIYOR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
