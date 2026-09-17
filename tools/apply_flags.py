"""Isaretlenen cevaplari kalici hale getirir.

Kart ekraninda "✓ Bunu da dogru say" (Ctrl+K) dedigin her cevap ilerleme
veritabaninda tutulur. Bu arac onlari tools/overrides.json'a tasir; boylece
veri seti yeniden uretildiginde de gecerli kalirlar.

    py tools/apply_flags.py          # isle ve raporla
    py tools/build_dataset.py        # ardindan veri setini yeniden uret

Ayni isi Ayarlar -> "Doğru saydıklarım" -> "Veri setine kalıcı işle" de yapar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402

OVERRIDES = ROOT / "tools" / "overrides.json"


def apply_flags(conn) -> tuple[int, str]:
    """Isaretlenen cevaplari overrides.json'a ekler. (eklenen_sayisi, dosya)."""
    flags = db.list_user_accepted(conn)
    if not flags:
        return 0, str(OVERRIDES.relative_to(ROOT))

    with open(OVERRIDES, encoding="utf-8") as fh:
        overrides = json.load(fh)

    added = 0
    for item in flags:
        # Ters yon (TR->EN) kabulleri Ingilizce yazimlardir; Turkce kabul
        # listesine (overrides.json) ait degildir.
        if item.get("direction", db.EN_TR) != db.EN_TR:
            continue
        key = item["word"].lower()          # DB anahtari her zaman Oxford yazimi
        answer = item["answer"].strip()
        if not answer:
            continue
        # Mevcut kabul listesi: once override, yoksa veri setindeki liste
        current = overrides.get(key)
        if current is None:
            current = json.loads(item["accepted"])
        if answer not in current:
            current = list(current) + [answer]
            added += 1
        overrides[key] = current

    with open(OVERRIDES, "w", encoding="utf-8") as fh:
        json.dump(overrides, fh, ensure_ascii=False, indent=2)

    conn.execute("UPDATE user_accepted SET exported = 1")
    conn.commit()
    return added, str(OVERRIDES.relative_to(ROOT))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not db.DB_PATH.exists():
        print("Ilerleme dosyasi yok, isaretlenmis cevap da yok.")
        return 0

    conn = db.connect()
    flags = db.list_user_accepted(conn)
    if not flags:
        print("Isaretlenmis cevap yok.")
        conn.close()
        return 0

    print(f"{len(flags)} isaretlenmis cevap:")
    for item in flags:
        shown = item["us_form"] or item["word"]
        state = "" if item["exported"] else "  (yeni)"
        print(f"   {shown:16s} <- {item['answer']}{state}")

    added, path = apply_flags(conn)
    conn.close()
    print()
    print(f"{added} yeni cevap {path} dosyasina eklendi.")
    print("Simdi veri setini yeniden uret:  py tools/build_dataset.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
