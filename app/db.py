"""SQLite semasi ve veri erisim katmani.

Kelime havuzu (data/oxford3000.json) salt okunur bir varliktir; kullanicinin
ilerlemesi data/progress.db icinde tutulur. Veri seti yeniden uretildiginde
ilerleme kaybolmaz - eslesme kelimenin kendisi uzerinden yapilir.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import paths

ROOT = paths.PROJECT_DIR
DATA = paths.data_dir()
DB_PATH = DATA / "progress.db"
WORDS_JSON = paths.words_json()

# Kelime durumlari
POOL = "pool"          # henuz hic gosterilmedi
KNOWN = "known"        # ilk gosterimde tek seferde dogru -> bir daha cikmaz
LEARNING = "learning"  # ilk seferde bilinemedi -> tekrar donusunde
LEARNED = "learned"    # 20 kez ust uste dogru -> rotasyondan cikti

# Calisma yonu. Ilerleme TEKTIR: kelime hangi yonde sorulursa sorulsun ayni
# seri/durum uzerinden ilerler. Yon yalnizca sorunun bicimini degistirir.
EN_TR = "en_tr"        # Ingilizce goster, Turkcesini yaz  (tanima)
TR_EN = "tr_en"        # Turkce goster, Ingilizcesini yaz  (uretim)
MIXED = "mixed"        # her kart rastgele bir yonde gelir
DIRECTIONS = (EN_TR, TR_EN, MIXED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    id            INTEGER PRIMARY KEY,
    word          TEXT NOT NULL UNIQUE,
    cefr          TEXT NOT NULL,
    pos           TEXT NOT NULL DEFAULT '',
    primary_tr    TEXT NOT NULL DEFAULT '',
    accepted      TEXT NOT NULL DEFAULT '[]',
    alternatives  TEXT NOT NULL DEFAULT '[]',
    definition    TEXT NOT NULL DEFAULT '',
    example       TEXT NOT NULL DEFAULT '',
    example_tr    TEXT NOT NULL DEFAULT '',
    synonyms      TEXT NOT NULL DEFAULT '',
    antonyms      TEXT NOT NULL DEFAULT '',
    collocations  TEXT NOT NULL DEFAULT '',
    us_form       TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    confidence    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS progress (
    word_id        INTEGER PRIMARY KEY REFERENCES words(id),
    state          TEXT    NOT NULL DEFAULT 'pool',
    streak         INTEGER NOT NULL DEFAULT 0,   -- ust uste dogru sayisi
    best_streak    INTEGER NOT NULL DEFAULT 0,
    shows          INTEGER NOT NULL DEFAULT 0,   -- toplam gosterim (1000 butcesi)
    correct        INTEGER NOT NULL DEFAULT 0,
    wrong          INTEGER NOT NULL DEFAULT 0,
    session_hits   INTEGER NOT NULL DEFAULT 0,   -- bu oturumda kac kez seri artti
    last_session   INTEGER NOT NULL DEFAULT 0,
    due_at         INTEGER NOT NULL DEFAULT 0,   -- bu kart sayacinda tekrar cikar
    gap_idx        INTEGER NOT NULL DEFAULT 0,   -- tekrar merdiveninde kacinci basamak
    last_seen      TEXT,
    first_seen     TEXT,
    settled_at     TEXT                          -- known/learned olma ani
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    cards      INTEGER NOT NULL DEFAULT 0,
    correct    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id    INTEGER NOT NULL REFERENCES words(id),
    session_id INTEGER NOT NULL,
    ts         TEXT    NOT NULL,
    correct    INTEGER NOT NULL,
    counted    INTEGER NOT NULL DEFAULT 1,   -- seriye sayildi mi (hibrit ritim)
    answer     TEXT    NOT NULL DEFAULT '',
    direction  TEXT    NOT NULL DEFAULT 'en_tr'
);

CREATE TABLE IF NOT EXISTS daily (
    day     TEXT PRIMARY KEY,
    cards   INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    seconds INTEGER NOT NULL DEFAULT 0
);

-- Kullanicinin "bunu da dogru say" dedigi cevaplar.
-- Kart olusturulurken kabul listesine eklenir; tools/apply_flags.py ile
-- kalici olarak tools/overrides.json'a tasinir.
CREATE TABLE IF NOT EXISTS user_accepted (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id    INTEGER NOT NULL REFERENCES words(id),
    answer     TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    exported   INTEGER NOT NULL DEFAULT 0,
    direction  TEXT    NOT NULL DEFAULT 'en_tr',
    UNIQUE(word_id, answer)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_progress_state ON progress(state);
CREATE INDEX IF NOT EXISTS idx_reviews_word   ON reviews(word_id);
CREATE INDEX IF NOT EXISTS idx_words_cefr     ON words(cefr);
CREATE INDEX IF NOT EXISTS idx_user_acc_word  ON user_accepted(word_id);
"""

DEFAULT_SETTINGS = {
    "daily_goal": "50",          # gunluk kart hedefi
    "group_size": "10",          # bir turdaki kart sayisi
    "target_streak": "20",       # ogrenilmis sayilmak icin ust uste dogru
    "show_budget": "1000",       # bir kelimenin maksimum gosterim butcesi
    "session_hit_cap": "3",      # ayni oturumda seriyi en fazla kac kez artirir
    "gap_cards": "20",           # (eski) tekrar arasi minimum kart mesafesi
    # Tekrar merdiveni: yanlis bilinen kelime kac kart sonra tekrar cikar.
    # Her dogruda bir sonraki basamaga gecer, yanlista basa doner.
    "drill_gaps": "3,8,20,45,100,250,600",
    # Her turda en az bu kadar YENI kelime gelir (havuz bosalana dek). Tekrar
    # yigini ne kadar buyurse buyusun yeni kelime akisi kesilmez.
    "new_per_group": "4",
    # Ayni kelime bir oturumda en fazla bu kadar kez sorulur; sonrasi ertesi
    # oturuma kalir. Ayni kelimeleri donup donup gormeyi engeller.
    "session_show_cap": "3",
    "confirm_known": "1",        # tekte bilinen kelime bir kez daha teyit edilsin mi
    "teach_on_miss": "1",        # bilemediginde dogru cevabi yazarak pekistir
    "reset_mode": "minus5",      # yanlista seri: full | half | minus5
    "typo_tolerance": "1",       # 1 harf yazim hatasi affedilsin mi
    "fold_turkish": "1",         # 'sarki' -> 'sarki' turkce karakter serbestligi
    "audio": "1",                # telaffuz sesi acik mi
    "spelling": "us",            # kart uzerinde gosterilen yazim: us | uk
    "direction": "en_tr",        # calisma yonu: en_tr | tr_en | mixed (karisik)
    "theme": "dark",
    "update_check": "1",         # acilista yeni surum var mi diye bak
    "update_last_check": "",     # gunde en fazla bir istek icin
    "update_skipped": "",        # "bu surumu hatirlatma" denen surum
    "update_auto_download": "1",  # yeni surumu arka planda kendiliginden indir
    "update_auto_install": "0",   # indidikten sonra sormadan kur ve yeniden baslat
}


# Sema sonradan buyudugunde eski veritabanlari bozulmasin diye eklenen sutunlar.
MIGRATIONS = [
    ("words", "us_form", "TEXT NOT NULL DEFAULT ''"),
    ("words", "note", "TEXT NOT NULL DEFAULT ''"),
    ("words", "example_tr", "TEXT NOT NULL DEFAULT ''"),
    ("progress", "due_at", "INTEGER NOT NULL DEFAULT 0"),
    ("progress", "gap_idx", "INTEGER NOT NULL DEFAULT 0"),
    ("reviews", "direction", "TEXT NOT NULL DEFAULT 'en_tr'"),
    ("user_accepted", "direction", "TEXT NOT NULL DEFAULT 'en_tr'"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    added = set()
    for table, column, decl in MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            added.add(column)
    if "due_at" in added:
        _seed_schedule(conn)
    _merge_reverse_progress(conn)
    conn.commit()


def _merge_reverse_progress(conn: sqlite3.Connection) -> None:
    """Eski surumdeki ayri TR->EN ilerlemesini (progress_rev) tek tabloya katar.

    Bir donem iki yonun ilerlemesi ayri tutuldu; artik tek. Ters yonde
    'biliniyor'/'ogreniliyor' olmus ama duz yonde hic gorulmemis kelimeler
    kaybolmasin diye bir kez aktarilir, tablo sonra silinir.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='progress_rev'"
    ).fetchone()
    if not exists:
        return
    conn.execute(
        """UPDATE progress SET
             state = r.state, streak = r.streak, best_streak = r.best_streak,
             shows = r.shows, correct = r.correct, wrong = r.wrong,
             due_at = r.due_at, gap_idx = r.gap_idx, last_seen = r.last_seen,
             first_seen = r.first_seen, settled_at = r.settled_at
           FROM progress_rev r
           WHERE r.word_id = progress.word_id
             AND progress.state = 'pool' AND r.state <> 'pool'"""
    )
    conn.execute("DROP TABLE progress_rev")


def _seed_schedule(conn: sqlite3.Connection) -> None:
    """Tekrar merdiveni eklenmeden onceki ilerlemeyi merdivene dahil eder.

    Merdiven yokken calisilmis kelimelerin due_at'i 0'dir; boyle kalirlarsa
    "tekrari gelmis" sayilmaz ve sistem onlari hic secmez. Serisi kadar
    ilerlemis kabul edip yakin bir zamana planliyoruz.
    """
    counter = get_int(conn, "card_counter", 0)
    gaps = drill_gaps(conn)
    rows = conn.execute(
        "SELECT word_id, streak FROM progress WHERE state = ? AND due_at = 0",
        (LEARNING,),
    ).fetchall()
    for offset, row in enumerate(rows):
        step = min(max(row["streak"], 0), len(gaps) - 1)
        # hepsi ayni anda yiginlmasin diye birer kart araliklarla dagit
        conn.execute(
            "UPDATE progress SET due_at = ?, gap_idx = ? WHERE word_id = ?",
            (counter + 1 + offset, step, row["word_id"]),
        )


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def sync_words(conn: sqlite3.Connection, words_json: Path = WORDS_JSON) -> int:
    """Kelime havuzunu JSON'dan DB'ye yansitir. Ilerlemeye dokunmaz."""
    with open(words_json, encoding="utf-8") as fh:
        entries = json.load(fh)

    rows = [
        (
            e["word"], e["cefr"], ",".join(e.get("pos", [])),
            e.get("primary", ""),
            json.dumps(e.get("accepted", []), ensure_ascii=False),
            json.dumps(e.get("alternatives", []), ensure_ascii=False),
            e.get("definition", ""), e.get("example", ""), e.get("example_tr", ""),
            e.get("synonyms", ""), e.get("antonyms", ""),
            e.get("collocations", ""), e.get("us_form", ""),
            e.get("note", ""), e.get("confidence", 0),
        )
        for e in entries
    ]
    conn.executemany(
        """INSERT INTO words
             (word, cefr, pos, primary_tr, accepted, alternatives,
              definition, example, example_tr, synonyms, antonyms, collocations,
              us_form, note, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(word) DO UPDATE SET
             cefr=excluded.cefr, pos=excluded.pos,
             primary_tr=excluded.primary_tr, accepted=excluded.accepted,
             alternatives=excluded.alternatives, definition=excluded.definition,
             example=excluded.example, example_tr=excluded.example_tr,
             synonyms=excluded.synonyms,
             antonyms=excluded.antonyms, collocations=excluded.collocations,
             us_form=excluded.us_form, note=excluded.note,
             confidence=excluded.confidence""",
        rows,
    )
    # Yeni kelimeler icin bos ilerleme satiri ac
    conn.execute(
        """INSERT INTO progress (word_id)
           SELECT id FROM words
           WHERE id NOT IN (SELECT word_id FROM progress)"""
    )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
    conn.commit()
    return len(rows)


# ------------------------------------------------------------------ ayarlar
def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS.get(key, default)


def get_int(conn, key: str, default: int = 0) -> int:
    try:
        return int(get_setting(conn, key, str(default)))
    except ValueError:
        return default


def set_setting(conn, key: str, value) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


# ------------------------------------------------------------------ oturum
def start_session(conn) -> int:
    cur = conn.execute(
        "INSERT INTO sessions (started_at) VALUES (?)", (datetime.now().isoformat(),)
    )
    # Yeni oturum -> oturum basi seri artirma sayaclarini sifirla
    conn.execute("UPDATE progress SET session_hits = 0")
    conn.commit()
    return cur.lastrowid


def end_session(conn, session_id: int) -> None:
    conn.execute(
        """UPDATE sessions SET ended_at = ?,
             cards   = (SELECT COUNT(*) FROM reviews WHERE session_id = ?),
             correct = (SELECT COALESCE(SUM(correct),0) FROM reviews WHERE session_id = ?)
           WHERE id = ?""",
        (datetime.now().isoformat(), session_id, session_id, session_id),
    )
    conn.commit()


def bump_daily(conn, correct: bool, seconds: int = 0) -> None:
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO daily (day, cards, correct, seconds) VALUES (?, 1, ?, ?)
           ON CONFLICT(day) DO UPDATE SET
             cards   = cards + 1,
             correct = correct + excluded.correct,
             seconds = seconds + excluded.seconds""",
        (today, int(correct), seconds),
    )


# ------------------------------------------------- kullanici kabulleri
def add_user_accepted(conn, word_id: int, answer: str,
                      direction: str = EN_TR) -> bool:
    """Kullanicinin 'bunu da dogru say' dedigi cevabi kaydeder."""
    answer = (answer or "").strip()
    if not answer:
        return False
    conn.execute(
        "INSERT OR IGNORE INTO user_accepted "
        "(word_id, answer, created_at, direction) VALUES (?, ?, ?, ?)",
        (word_id, answer, datetime.now().isoformat(), direction),
    )
    conn.commit()
    return True


def user_accepted_map(conn, direction: str = EN_TR) -> dict[int, list[str]]:
    """Bir yonun kullanici kabullerini {word_id: [cevap, ...]} olarak dondurur."""
    out: dict[int, list[str]] = {}
    for row in conn.execute(
        "SELECT word_id, answer FROM user_accepted WHERE direction = ? ORDER BY id",
        (direction,),
    ):
        out.setdefault(row["word_id"], []).append(row["answer"])
    return out


def list_user_accepted(conn) -> list[dict]:
    """Isaretlenen cevaplar, kelimesiyle birlikte (en yeni once)."""
    rows = conn.execute(
        """SELECT u.id, u.answer, u.created_at, u.exported, u.direction,
                  w.word, w.us_form, w.accepted
           FROM user_accepted u JOIN words w ON w.id = u.word_id
           ORDER BY u.id DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def remove_user_accepted(conn, entry_id: int) -> None:
    conn.execute("DELETE FROM user_accepted WHERE id = ?", (entry_id,))
    conn.commit()


# ------------------------------------------------- kart sayaci (tekrar merdiveni)
def card_counter(conn) -> int:
    """Simdiye kadar cevaplanan toplam kart sayisi.

    Tekrar merdiveni "kac kart sonra" diye calisir; bu sayac oturumlar arasinda
    da surdugu icin bir kelime ertesi gune sarkabilir.
    """
    return get_int(conn, "card_counter", 0)


def bump_card_counter(conn) -> int:
    value = card_counter(conn) + 1
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('card_counter', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(value),),
    )
    return value


def drill_gaps(conn) -> list[int]:
    raw = get_setting(conn, "drill_gaps", "3,8,20,45,100,250,600")
    gaps = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            gaps.append(int(part))
    return gaps or [3, 8, 20, 45, 100, 250, 600]
