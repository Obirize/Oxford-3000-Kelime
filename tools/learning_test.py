"""Ogrenme dinamigi olcumu.

Soru: program gercekten ogretiyor mu, yoksa sadece bilinenleri mi eliyor?

Sahte kullanici gercekci davranir: bir kelimeyi ne kadar sik ve ne kadar
aralikli gorduyse o kadar iyi hatirlar (aralikli tekrar etkisi). Olculen sey
"kac kelime ogrenildi" degil - ONCE BILINMEYEN kac kelimenin gercekten
ogrenildigi.

    py tools/learning_test.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from _guard import test_db, cleanup  # noqa: E402
from app import db  # noqa: E402
from app.engine import Engine  # noqa: E402

KNOWS_ALREADY = 0.83   # kullanicinin gercek orani (203 known / 243 gorulen)
SESSIONS = 8
CARDS_PER_SESSION = 50


class Learner:
    """Hafizasi olan sahte kullanici.

    Bir kelimeyi hatirlama olasiligi: kac kez calistigi + araliklarin ne kadar
    dagildigiyla artar. Ust uste ayni anda gormek az sey ogretir, araliklarla
    gormek cok sey ogretir.
    """

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.innate = {}      # bastan biliyor mu
        self.reps = {}        # kac kez calisti
        self.last_seen = {}   # en son kacinci kartta gordu

    def knows(self, word_id, card_no) -> bool:
        if word_id not in self.innate:
            self.innate[word_id] = self.rng.random() < KNOWS_ALREADY
        if self.innate[word_id]:
            return True
        reps = self.reps.get(word_id, 0)
        if reps == 0:
            return False
        # her tekrar ogrenme gucunu artirir; aralikli olanlar daha degerli
        gap = card_no - self.last_seen.get(word_id, card_no)
        spacing_bonus = min(gap / 50.0, 1.0)
        strength = min(0.18 * reps + 0.25 * spacing_bonus * reps, 0.97)
        return self.rng.random() < strength

    def study(self, word_id, card_no):
        self.reps[word_id] = self.reps.get(word_id, 0) + 1
        self.last_seen[word_id] = card_no

    def truly_learned(self, word_id) -> bool:
        """Bastan bilmedigi halde artik saglam hatirladigi kelimeler."""
        return not self.innate.get(word_id, False) and self.reps.get(word_id, 0) >= 4


def run(label: str, settings: dict) -> dict:
    path = test_db(f"data/_learn_{label}.db")
    conn = db.connect(path)
    db.sync_words(conn)
    for key, value in settings.items():
        db.set_setting(conn, key, value)

    learner = Learner(seed=7)
    card_no = 0
    exposures = {}

    for _ in range(SESSIONS):
        eng = Engine(conn)
        for _ in range(CARDS_PER_SESSION):
            card = eng.next_card()
            if card is None:
                break
            card_no += 1
            exposures[card.word_id] = exposures.get(card.word_id, 0) + 1
            ok = learner.knows(card.word_id, card_no)
            learner.study(card.word_id, card_no)
            eng.submit(card, card.accepted[0] if ok else "zzzz")
        eng.finish()

    rows = conn.execute(
        "SELECT word_id, state, shows FROM progress WHERE shows > 0"
    ).fetchall()
    seen = {r["word_id"]: r for r in rows}

    # Sadece BASTAN BILMEDIGI kelimelere bak - asil ogrenme burada
    unknown_ids = [w for w in seen if not learner.innate.get(w, False)]
    drilled = [w for w in unknown_ids if exposures.get(w, 0) >= 5]
    settled = [w for w in unknown_ids
               if seen[w]["state"] in (db.LEARNED, db.KNOWN)]

    result = {
        "toplam_kart": card_no,
        "dokunulan_kelime": len(seen),
        "bilmedigi_kelime": len(unknown_ids),
        "5+_kez_calisilan": len(drilled),
        "pekisme_orani": len(drilled) / max(len(unknown_ids), 1),
        "yeni_kelime_akisi": len(seen),
        "ort_gosterim": sum(exposures.get(w, 0) for w in unknown_ids)
                        / max(len(unknown_ids), 1),
        "ogrenildi_sayilan": len(settled),
    }
    conn.close()
    cleanup(f"data/_learn_{label}.db")
    return result


def main() -> int:
    eski = {
        "drill_gaps": "20", "active_limit": "3000",
        "confirm_known": "0", "gap_cards": "20", "session_hit_cap": "3",
    }
    yeni = {
        "drill_gaps": "3,8,20,45,100,250,600", "active_limit": "12",
        "confirm_known": "1", "gap_cards": "20", "session_hit_cap": "4",
    }

    print(f"{SESSIONS} oturum x {CARDS_PER_SESSION} kart, "
          f"kullanici kelimelerin ~%{KNOWS_ALREADY*100:.0f}'ini zaten biliyor\n")
    a = run("eski", eski)
    b = run("yeni", yeni)

    labels = {
        "dokunulan_kelime": "dokunulan kelime",
        "bilmedigi_kelime": "bunlardan BILMEDIGI",
        "ort_gosterim": "bilmediklerinin ort. gosterimi",
        "5+_kez_calisilan": "5+ kez calisilan (pekisen)",
        "pekisme_orani": "PEKISME ORANI",
    }
    print(f"{'':34s}{'ESKI':>12s}{'YENI':>12s}")
    print("-" * 58)
    for key, name in labels.items():
        av, bv = a[key], b[key]
        if key == "pekisme_orani":
            print(f"{name:34s}{av*100:>11.0f}%{bv*100:>11.0f}%")
        elif key == "ort_gosterim":
            print(f"{name:34s}{av:>12.1f}{bv:>12.1f}")
        else:
            print(f"{name:34s}{av:>12d}{bv:>12d}")

    print()
    kat = b["ort_gosterim"] / max(a["ort_gosterim"], 0.01)
    print(f"Bilmedigi kelime basina pekistirme: {kat:.1f} kat")
    if kat >= 1.4:
        print("✅ Yeni sistem bilinmeyen kelimeleri belirgin sekilde daha cok tekrar ettiriyor")
        return 0
    print("❌ Belirgin iyilesme yok")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
