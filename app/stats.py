"""Istatistikler ve CEFR seviye tahmini.

Seviye tahmini uydurma degil: Oxford'un kendi CEFR etiketlerini kullanir.
Bir seviye, o seviyedeki kelimelerin %85'i hakim olundugunda "tamamlanmis"
sayilir; ilerleme bir sonraki seviyeye tasinir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from . import db

LEVELS = ["A1", "A2", "B1", "B2"]
MASTERY = 0.85  # bir seviyeyi "tamamlanmis" saymak icin gereken oran

# Hakim olunan kelime = ilk seferde bilinen + 20'lik seriyi tamamlayan
MASTERED = (db.KNOWN, db.LEARNED)


@dataclass
class Overview:
    total: int = 0
    known: int = 0        # ilk gosterimde bilinen
    learned: int = 0      # 20'lik seriyi tamamlayan
    learning: int = 0     # tekrar donusunde
    pool: int = 0         # hic gorulmemis
    stubborn: int = 0     # 1000 gosterim butcesini asan inatci kelimeler

    @property
    def mastered(self) -> int:
        return self.known + self.learned

    @property
    def progress(self) -> float:
        return self.mastered / self.total if self.total else 0.0


def overview(conn) -> Overview:
    rows = conn.execute(
        "SELECT state, COUNT(*) AS n FROM progress GROUP BY state"
    ).fetchall()
    counts = {r["state"]: r["n"] for r in rows}
    budget = db.get_int(conn, "show_budget", 1000)
    stubborn = conn.execute(
        "SELECT COUNT(*) AS n FROM progress WHERE state = ? AND shows >= ?",
        (db.LEARNING, budget),
    ).fetchone()["n"]
    return Overview(
        total=sum(counts.values()),
        known=counts.get(db.KNOWN, 0),
        learned=counts.get(db.LEARNED, 0),
        learning=counts.get(db.LEARNING, 0),
        pool=counts.get(db.POOL, 0),
        stubborn=stubborn,
    )


def by_level(conn) -> dict[str, dict[str, int]]:
    """Seviye basina {total, mastered, learning, pool} dagilimi."""
    rows = conn.execute(
        """SELECT w.cefr, p.state, COUNT(*) AS n
           FROM words w JOIN progress p ON p.word_id = w.id
           GROUP BY w.cefr, p.state"""
    ).fetchall()
    out = {lv: {"total": 0, "mastered": 0, "learning": 0, "pool": 0} for lv in LEVELS}
    for r in rows:
        bucket = out.setdefault(
            r["cefr"], {"total": 0, "mastered": 0, "learning": 0, "pool": 0}
        )
        bucket["total"] += r["n"]
        if r["state"] in MASTERED:
            bucket["mastered"] += r["n"]
        elif r["state"] == db.LEARNING:
            bucket["learning"] += r["n"]
        else:
            bucket["pool"] += r["n"]
    return out


def estimate_level(conn) -> tuple[str, str, float]:
    """(seviye_etiketi, sonraki_seviye, sonraki_seviyeye_ilerleme) dondurur.

    Ornek:  ('A2+', 'B1', 0.38)  ->  "A2+ · B1'e %38"
    """
    levels = by_level(conn)
    ratios = {
        lv: (levels[lv]["mastered"] / levels[lv]["total"] if levels[lv]["total"] else 0.0)
        for lv in LEVELS
    }

    completed = None
    for lv in LEVELS:
        if ratios[lv] >= MASTERY:
            completed = lv
        else:
            break

    if completed == LEVELS[-1]:
        return "C1", "", 1.0

    current_idx = LEVELS.index(completed) + 1 if completed else 0
    working = LEVELS[current_idx]
    ratio = ratios[working]

    if completed is None:
        # Henuz A1'i bitirmedik: A1 icindeki ilerlemeye gore etiket ver
        label = "A1" if ratio < 0.5 else "A1+"
        return label, "A2", ratio

    label = f"{completed}+" if ratio >= 0.25 else completed
    return label, working, ratio


def daily_series(conn, days: int = 30) -> list[tuple[str, int, int]]:
    """Son N gunun (gun, kart, dogru) serisi - bos gunler 0 ile doldurulur."""
    rows = {
        r["day"]: (r["cards"], r["correct"])
        for r in conn.execute("SELECT * FROM daily").fetchall()
    }
    today = date.today()
    out = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        cards, correct = rows.get(day, (0, 0))
        out.append((day, cards, correct))
    return out


def streak_days(conn) -> int:
    """Kesintisiz calisilan gun sayisi (bugun calisilmadiysa dunden geriye bakar)."""
    days = {
        r["day"] for r in conn.execute("SELECT day FROM daily WHERE cards > 0").fetchall()
    }
    if not days:
        return 0
    today = date.today()
    start = today if today.isoformat() in days else today - timedelta(days=1)
    if start.isoformat() not in days:
        return 0
    count, cursor = 0, start
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def today_progress(conn) -> tuple[int, int, int]:
    """(bugunku kart, bugunku dogru, gunluk hedef)"""
    row = conn.execute(
        "SELECT cards, correct FROM daily WHERE day = ?", (date.today().isoformat(),)
    ).fetchone()
    goal = db.get_int(conn, "daily_goal", 50)
    return (row["cards"] if row else 0, row["correct"] if row else 0, goal)


def accuracy(conn, last_n: int = 200) -> float:
    rows = conn.execute(
        "SELECT correct FROM reviews ORDER BY id DESC LIMIT ?", (last_n,)
    ).fetchall()
    return sum(r["correct"] for r in rows) / len(rows) if rows else 0.0


def hardest_words(conn, limit: int = 10) -> list[dict]:
    """En cok zorlanilan kelimeler."""
    rows = conn.execute(
        """SELECT w.word, w.primary_tr, w.cefr, p.wrong, p.correct, p.streak, p.shows
           FROM progress p JOIN words w ON w.id = p.word_id
           WHERE p.wrong > 0 AND p.state = ?
           ORDER BY p.wrong DESC, p.streak ASC
           LIMIT ?""",
        (db.LEARNING, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def eta(conn) -> str:
    """Mevcut tempoyla 3000'i bitirme tahmini."""
    rows = conn.execute(
        "SELECT cards FROM daily WHERE cards > 0 ORDER BY day DESC LIMIT 14"
    ).fetchall()
    if len(rows) < 3:
        return "—"
    ov = overview(conn)
    remaining = ov.total - ov.mastered
    if remaining <= 0:
        return "tamamlandı 🎉"
    per_day = sum(r["cards"] for r in rows) / len(rows)
    # Kabaca: her 3 kart gosteriminde 1 kelime kalici olarak yerine oturuyor
    settle_rate = max(per_day / 3.0, 0.5)
    days = remaining / settle_rate
    if days < 60:
        return f"~{int(days)} gün"
    if days < 730:
        return f"~{days/30:.1f} ay"
    return f"~{days/365:.1f} yıl"
