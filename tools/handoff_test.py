"""Ilerleme devralma testi (app/handoff.py).

    py tools/handoff_test.py

Taklit edilen gercek senaryo: kullanici tasinabilir exe ile calisiyordu, sonra
kurulum paketini kurdu; kurulu surum BASKA bir klasorde oldugu icin bomboş bir
ilerlemeyle acildi ve "ilerlemem gitti" sandi.

Kontroller gecici bir klasorde yapilir; gercek ilerleme dosyasina DOKUNULMAZ.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import db, handoff  # noqa: E402

from _guard import check, report  # noqa: E402


def make_db(path: Path, studied: int = 0, reviews: int = 0) -> Path:
    """Istenen kadar calisilmis sahte bir ilerleme dosyasi uretir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(path)
    conn.execute("INSERT INTO words (word, cefr) VALUES ('test', 'A1')")
    wid = conn.execute("SELECT id FROM words WHERE word='test'").fetchone()["id"]
    conn.execute("INSERT OR IGNORE INTO progress (word_id) VALUES (?)", (wid,))
    if studied:
        conn.execute("UPDATE progress SET state=? WHERE word_id=?",
                     (db.KNOWN, wid))
    for i in range(reviews):
        conn.execute(
            "INSERT INTO reviews (word_id, session_id, ts, correct) "
            "VALUES (?, 1, ?, 1)", (wid, f"2026-10-0{i % 9 + 1}T10:00:00"))
    conn.commit()
    conn.close()
    return path


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="oxford_handoff_"))
    try:
        print("\n1) Bos / dolu ayrimi")
        empty = make_db(tmp / "bos" / "progress.db")
        full = make_db(tmp / "dolu" / "progress.db", studied=1, reviews=5)
        check("hic calisilmamis dosya BOS sayilir", handoff.inspect(empty) is None)
        check("calisilmis dosya DOLU sayilir", handoff.inspect(full) is not None)
        check("olmayan dosya BOS sayilir",
              handoff.inspect(tmp / "yok" / "progress.db") is None)

        print("\n2) Bozuk dosya ice aktarilmaz")
        broken = tmp / "bozuk" / "progress.db"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_bytes(b"bu bir sqlite dosyasi degil")
        check("bozuk dosya aday sayilmaz", handoff.inspect(broken) is None)

        print("\n3) Devralma kaynagi degistirmez, hedefi doldurur")
        target = make_db(tmp / "kurulum" / "progress.db")
        found = handoff.inspect(full)
        before = full.read_bytes()
        ok = handoff.adopt(found, target)
        check("kopyalama basarili", ok)
        check("hedef artik dolu", handoff.inspect(target) is not None)
        check("KAYNAK DOSYA DEGISMEDI", full.read_bytes() == before)
        check("hedefteki eski (bos) dosya kenara alindi",
              target.with_suffix(".db.replaced").exists())
        conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        check("hedefin butunlugu saglam",
              conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        conn.close()

        print("\n4) En cok calisilmis kaynak secilir")
        az = handoff.inspect(make_db(tmp / "az" / "progress.db", studied=1, reviews=3))
        cok = handoff.inspect(make_db(tmp / "cok" / "progress.db", studied=1, reviews=99))
        check("daha cok cevabi olan tercih edilir",
              max([az, cok], key=lambda f: f.reviews).path == cok.path)

        print("\n5) Aday klasorler sinirli ve hedefli (tarama yapilmiyor)")
        dirs = handoff._data_dirs()
        # Dosya sistemi taranmaz; yalnizca sabit, programa ait '.../data'
        # klasorlerine bakilir. (Programin kendi klasoru Masaustunde olabilir -
        # tasinabilir kopya oraya konmus olabilir; bu beklenen bir durumdur.)
        check("aday sayisi az (ozyinelemeli tarama yok)", len(dirs) <= 10,
              f"{len(dirs)} klasor")
        check("hepsi bir 'data' klasoru", all(d.name == "data" for d in dirs),
              str([d.name for d in dirs if d.name != "data"]))
        check("standart kurulum klasoru listede",
              any("Programs" in str(d) and "Oxford3000" in str(d) for d in dirs))
        check("programin kendi klasoru listede",
              (handoff.paths.app_dir() / "data") in dirs)

        print("\n6) Kendini bulmaz (sonsuz dongu / kendi uzerine kopyalama yok)")
        check("mevcut dosya aday listesinden cikarilir",
              handoff.find_elsewhere(full.resolve()) is None
              or handoff.find_elsewhere(full.resolve()).path != full.resolve())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return report("✅ ILERLEME DEVRALMA CALISIYOR")


if __name__ == "__main__":
    raise SystemExit(main())
