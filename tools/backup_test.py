"""Yedekleme ve kurtarma testi.

Kullanicinin yasadigi senaryoyu birebir kurar: ilerleme olusur, program kapanir,
ilerleme dosyasi SILINIR -> program acilista yedekten geri yuklemeli.

    py tools/backup_test.py
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import backup, db  # noqa: E402
from app.engine import Engine  # noqa: E402

failures: list[str] = []
SANDBOX = Path("data/_backup_test")
DB = SANDBOX / "progress.db"


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def studied_words(path: Path) -> int:
    import sqlite3
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM progress WHERE state <> 'pool'"
        ).fetchone()[0]
    finally:
        conn.close()


def make_progress(n: int = 25) -> int:
    conn = db.connect(DB)
    db.sync_words(conn)
    eng = Engine(conn)
    for i in range(n):
        card = eng.next_card()
        if not card:
            break
        eng.submit(card, card.accepted[0] if i % 2 == 0 else "zzz")
    eng.finish()
    conn.commit()
    conn.close()
    return studied_words(DB)


def main() -> int:
    # Gercek yedek klasorune dokunmamak icin sanal bir klasore yonlendir
    real_dir = backup.BACKUP_DIR
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    backup.BACKUP_DIR = SANDBOX / "backups"

    try:
        print("\n1) Ilerleme uret ve yedekle")
        studied = make_progress()
        check("ilerleme olustu", studied > 0, f"{studied} kelime")
        first = backup.create(DB, force=True)
        check("yedek alindi", first is not None and first.exists())
        check("yedek saglam", first is not None and backup.is_healthy(first))
        check("yedekte ayni ilerleme var", studied_words(first) == studied,
              f"{studied_words(first)} kelime")

        print("\n2) Bos veritabani yedeklenmemeli")
        empty = SANDBOX / "empty.db"
        c = db.connect(empty); db.sync_words(c); c.close()
        check("bos veritabani atlandi", backup.create(empty, force=True) is None)

        print("\n3) FELAKET: ilerleme dosyasi siliniyor")
        DB.unlink()
        check("dosya gercekten silindi", not DB.exists())
        recovered = backup.recover_if_needed(DB)
        check("acilista otomatik geri yuklendi", recovered is not None)
        check("dosya geri geldi", DB.exists())
        check("ilerleme AYNEN korundu", DB.exists() and studied_words(DB) == studied,
              f"{studied_words(DB) if DB.exists() else 0}/{studied} kelime")

        print("\n4) BOZULMA: dosyanin icine cop yaziliyor")
        DB.write_bytes(b"bu bir sqlite dosyasi degil")
        check("bozuk dosya saglıksız gorunuyor", not backup.is_healthy(DB))
        recovered = backup.recover_if_needed(DB)
        check("bozuk dosya yedekten degistirildi", recovered is not None)
        check("ilerleme yine korundu", studied_words(DB) == studied,
              f"{studied_words(DB)}/{studied} kelime")

        print("\n5) Saglam dosyaya dokunulmamali")
        before = DB.read_bytes()
        check("kurtarma gereksizse mudahale yok",
              backup.recover_if_needed(DB) is None)
        check("dosya degismedi", DB.read_bytes() == before)

        print("\n6) Yedek rotasyonu")
        for _ in range(backup.KEEP + 6):
            backup.create(DB, force=True)
        count = len(backup.list_backups())
        check(f"en fazla {backup.KEEP} yedek saklaniyor", count <= backup.KEEP,
              f"{count} adet")

        print("\n7) Yeni ilerleme sonrasi eski yedege donme")
        extra = make_progress(40)
        check("ilerleme arttı", extra > studied, f"{studied} -> {extra}")
        oldest = backup.list_backups()[-1]
        target = studied_words(oldest)
        check("eski yedege donuldu", backup.restore(oldest, DB))
        check("eski duruma donuldu", studied_words(DB) == target,
              f"{studied_words(DB)} kelime")
    finally:
        backup.BACKUP_DIR = real_dir
        shutil.rmtree(SANDBOX, ignore_errors=True)

    print("\n" + "=" * 58)
    if failures:
        print(f"❌ {len(failures)} KONTROL BASARISIZ:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ YEDEKLEME SISTEMI CALISIYOR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
