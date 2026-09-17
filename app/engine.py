"""Ogrenme motoru: kart secimi, hibrit tekrar ritmi ve durum gecisleri.

Kurallar
--------
* Kelimeler 10'luk turlar halinde, 3000'lik havuzdan rastgele cekilir.
* Ilk gosterimde tek seferde dogru  -> KNOWN. Bir daha asla cikmaz.
* Ilk gosterimde bilinemez          -> LEARNING. 1000 gosterim butcesi acilir.
* LEARNING'de her dogru seriyi 1 artirir, yanlis ise seriyi geri cekmektedir.
  Geri cekme bicimi `reset_mode` ayarindan secilir:
      full   -> seri sifirlanir (ilk tasarim; olcumde 20'ye ulasmak ~54 oturum)
      half   -> seri yariya duser
      minus5 -> seri 5 azalir (varsayilan; ~24 oturum, ilerleme hissi korunur)
* Seri 20'ye ulasinca               -> LEARNED. Rotasyondan cikar.

TEKRAR MERDIVENI (asil ogrenme mekanizmasi)
    Bilinemeyen kelime kaybolmaz; genisleyen araliklarla tekrar tekrar karsina
    cikar:  3 -> 8 -> 20 -> 45 -> 100 -> 250 -> 600 kart sonra.
    Her dogru bir ust basamaga tasir, her yanlis BASA dondurur.
    Sozlukten parmakla kapatarak ezberlemenin dijital karsiligi.

YENI KELIME GARANTISI
    Her turda en az `new_per_group` (4) yeni kelime gelir; tekrar yigini ne
    kadar buyurse buyusun akis kesilmez. (Onceki "aktif pencere" tasarimi,
    ogreniliyor sayisi siniri asinca yeni kelimeyi tamamen kesiyordu ve ayni
    10 kelime donup donup geliyordu - kaldirildi.)

OTURUM BASI GOSTERIM SINIRI
    Ayni kelime bir oturumda en fazla `session_show_cap` (3) kez sorulur;
    fazlasi ertesi oturuma kalir. Ayrica bir kelime ayni oturumda en fazla
    `session_hit_cap` kez seri artirir.

TERS YON (Turkce -> Ingilizce)
    Ayni motor, ayni merdiven, AYNI ilerleme; yalnizca soru/cevap yer
    degistirir. Kelime hangi yonde bilinirse bilinsin serisi ilerler.
    Ayni Turkce karsiliga sahip kardes kelimeler (buyuk = big/large/great)
    birbirinin yerine kabul edilir; haksiz ret olmasin.

KARISIK MOD
    Her kartin kendi yonu vardir (Card.direction). Karisik modda bir tur iki
    yonden yariya yakin pay alir; bir yon kart veremiyorsa obur yon doldurur.
"""

from __future__ import annotations

import json
import random
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime

from . import db
from .matching import VERDICT_CORRECT, Result, check, check_en, normalize


@dataclass
class Card:
    word_id: int
    word: str
    cefr: str
    pos: str
    primary: str
    accepted: list[str]
    alternatives: list[str]
    definition: str
    example: str
    example_tr: str
    synonyms: str
    antonyms: str
    collocations: str
    us_form: str
    note: str
    state: str
    streak: int
    shows: int
    session_hits: int
    gap_idx: int = 0
    display: str = ""      # ekranda gosterilen yazim (Amerikan/Ingiliz)
    other_form: str = ""   # obur yazim; kartta not olarak gosterilir
    targets: list[str] = field(default_factory=list)  # ters yonde kabul edilen Ingilizce yazimlar
    direction: str = db.EN_TR   # bu kartin yonu (karisik modda kart basina degisir)

    @property
    def reverse(self) -> bool:
        return self.direction == db.TR_EN

    @property
    def is_new(self) -> bool:
        return self.shows == 0


@dataclass
class Outcome:
    """Bir cevabin sonucu ve yol actigi durum degisikligi."""
    result: Result
    correct: bool
    counted: bool           # seriye sayildi mi
    state_before: str
    state_after: str
    streak: int
    target_streak: int
    promoted: str = ""      # 'known' | 'learned' | ''  -> kutlama tetikler
    reset: bool = False     # seri sifirlandi mi


def _swap_spelling(text: str, old: str, new: str) -> str:
    """Ornek cumledeki yazimi da degistirir, bas harf buyuklugunu koruyarak."""
    if not text or not old:
        return text

    def repl(match: re.Match) -> str:
        found = match.group(0)
        return new.capitalize() if found[0].isupper() else new

    return re.sub(rf"\b{re.escape(old)}\b", repl, text, flags=re.IGNORECASE)


def _row_to_card(row, spelling: str = "us") -> Card:
    """DB satirini karta cevirir.

    Oxford 3000 INGILIZ yazimini kullanir (`mum`, `colour`, `centre`). Turkiye'de
    Amerikan Ingilizcesi ogretildigi icin varsayilan olarak Amerikan yazimini
    gosteriyoruz; Ingiliz yazimi kartta not olarak kalir.
    """
    word, us_form = row["word"], row["us_form"]
    example = row["example"]
    display, other = word, ""
    if us_form:
        if spelling == "us":
            display, other = us_form, word
            example = _swap_spelling(example, word, us_form)
        else:
            other = us_form

    return Card(
        word_id=row["id"], word=word, cefr=row["cefr"], pos=row["pos"],
        primary=row["primary_tr"],
        accepted=json.loads(row["accepted"]),
        alternatives=json.loads(row["alternatives"]),
        definition=row["definition"], example=example,
        example_tr=(row["example_tr"] if "example_tr" in row.keys() else ""),
        synonyms=row["synonyms"], antonyms=row["antonyms"],
        collocations=row["collocations"], us_form=us_form,
        note=row["note"],
        state=row["state"], streak=row["streak"], shows=row["shows"],
        session_hits=row["session_hits"],
        gap_idx=(row["gap_idx"] if "gap_idx" in row.keys() else 0),
        display=display, other_form=other,
    )


class Engine:
    def __init__(self, conn, direction: str | None = None):
        self.conn = conn
        self.direction = direction or db.get_setting(conn, "direction", db.EN_TR)
        if self.direction not in db.DIRECTIONS:
            self.direction = db.EN_TR
        # Bu oturumda kart uretilen yonler
        self.directions = ([db.EN_TR, db.TR_EN] if self.direction == db.MIXED
                           else [self.direction])
        self.session_id = db.start_session(conn)
        self.group_size = db.get_int(conn, "group_size", 10)
        self.target_streak = db.get_int(conn, "target_streak", 20)
        self.show_budget = db.get_int(conn, "show_budget", 1000)
        self.hit_cap = db.get_int(conn, "session_hit_cap", 4)
        self.gap = db.get_int(conn, "gap_cards", 20)
        self.reset_mode = db.get_setting(conn, "reset_mode", "minus5")
        self.typo = db.get_int(conn, "typo_tolerance", 1) == 1
        self.fold = db.get_int(conn, "fold_turkish", 1) == 1
        self.spelling = db.get_setting(conn, "spelling", "us")
        self.gaps = db.drill_gaps(conn)
        self.new_per_group = db.get_int(conn, "new_per_group", 4)
        self.show_cap = db.get_int(conn, "session_show_cap", 3)
        self.confirm_known = db.get_int(conn, "confirm_known", 1) == 1
        self.counter = db.card_counter(conn)
        # Araligi artik tekrar merdiveni belirliyor; bu kisa hafiza yalnizca
        # ayni kelimenin arka arkaya gelmesini engeller.
        self._recent: deque[int] = deque(maxlen=2)
        self._queue: list[Card] = []
        self._undo: dict | None = None   # son cevabin geri alma bilgisi
        self._user_accepted = {d: db.user_accepted_map(conn, d)
                               for d in self.directions}
        # Ters yon: ayni Turkce ana anlami paylasan kelimeler (buyuk -> big,
        # large, great...). Kullanici bunlardan herhangi birini yazarsa dogru.
        self._siblings: dict[str, list[tuple[int, list[str]]]] = {}
        if db.TR_EN in self.directions:
            for row in conn.execute(
                "SELECT id, word, us_form, primary_tr FROM words"
            ):
                key = normalize(row["primary_tr"])
                if key:
                    forms = [row["word"]] + ([row["us_form"]] if row["us_form"] else [])
                    self._siblings.setdefault(key, []).append((row["id"], forms))

    _SELECT = """
        SELECT w.*, p.state, p.streak, p.shows, p.session_hits, p.gap_idx
        FROM words w JOIN progress p ON p.word_id = w.id
    """
    # Bu oturumda kac kez soruldu (oturum basi gosterim siniri icin)
    _SESSION_SHOWS = """
        (SELECT COUNT(*) FROM reviews r
          WHERE r.word_id = p.word_id AND r.session_id = ?)
    """

    # ------------------------------------------------------------ kart secimi
    def _pick_due(self, limit: int, direction: str) -> list[Card]:
        """Tekrar zamani GELMIS kartlar - en gecikmis olan once.

        Tekrar merdiveni: yanlis bilinen kelime 3 kart sonra, sonra 8, 20, 45...
        kart sonra tekrar cikar. Boylece kelime kaybolmaz, sik sik karsina gelir.
        'Biliniyor' kelimeler de teyit icin bir kez buraya girebilir.
        """
        if limit <= 0:
            return []
        rows = self.conn.execute(
            f"""{self._SELECT}
                WHERE p.due_at > 0 AND p.due_at <= ?
                  AND p.state IN (?, ?)
                  AND p.shows < ?
                  AND {self._SESSION_SHOWS} < ?
                ORDER BY p.due_at ASC
                LIMIT ?""",
            (self.counter, db.LEARNING, db.KNOWN, self.show_budget,
             self.session_id, self.show_cap, limit * 3),
        ).fetchall()
        picked = [self._make_card(r, direction) for r in rows
                  if r["id"] not in self._recent]
        return picked[:limit]

    def _pick_overdue_any(self, limit: int, direction: str) -> list[Card]:
        """Zamani gelmemis ama ogrenilmekte olan kartlar (bosluk doldurucu)."""
        if limit <= 0:
            return []
        rows = self.conn.execute(
            f"""{self._SELECT}
                WHERE p.state = ? AND p.shows < ?
                  AND {self._SESSION_SHOWS} < ?
                ORDER BY p.due_at ASC, p.streak ASC
                LIMIT ?""",
            (db.LEARNING, self.show_budget, self.session_id, self.show_cap,
             limit * 3),
        ).fetchall()
        picked = [self._make_card(r, direction) for r in rows
                  if r["id"] not in self._recent]
        return picked[:limit]

    def _pick_new(self, limit: int, direction: str) -> list[Card]:
        """Havuzdan yeni kelime (kolay seviyeden zora, seviye icinde rastgele)."""
        if limit <= 0:
            return []
        rows = self.conn.execute(
            f"""{self._SELECT}
                WHERE p.state = ?
                ORDER BY CASE w.cefr WHEN 'A1' THEN 1 WHEN 'A2' THEN 2
                                     WHEN 'B1' THEN 3 ELSE 4 END,
                         RANDOM()
                LIMIT ?""",
            (db.POOL, limit),
        ).fetchall()
        return [self._make_card(r, direction) for r in rows]

    def _make_card(self, row, direction: str) -> Card:
        """Karti olustururken kullanicinin kendi kabullerini de ekler."""
        card = _row_to_card(row, self.spelling)
        card.direction = direction
        card.targets = [card.display or card.word]
        for form in (card.word, card.us_form):
            if form and form not in card.targets:
                card.targets.append(form)
        for extra in self._user_accepted.get(direction, {}).get(card.word_id, []):
            if card.reverse:
                if extra not in card.targets:
                    card.targets.append(extra)
            else:
                if extra not in card.accepted:
                    card.accepted.append(extra)
                card.alternatives = [a for a in card.alternatives if a != extra]
        return card

    # ------------------------------------------------------------ yon
    def prompt_text(self, card: Card) -> str:
        """Kartta buyuk gosterilen soru: kelime (duz) / Turkce anlam (ters)."""
        if card.reverse:
            return card.primary or (card.accepted[0] if card.accepted else "?")
        return card.display or card.word

    def prompt_extra(self, card: Card) -> list[str]:
        """Ters yonde soruyu netlestiren ek anlamlar (buyuk · iri · genis)."""
        if not card.reverse:
            return []
        head = normalize(self.prompt_text(card))
        return [a for a in card.accepted if normalize(a) != head][:3]

    def answer_text(self, card: Card) -> str:
        """Beklenen cevabin gosterilecek hali (yazarak pekistir adimi icin)."""
        if card.reverse:
            return card.display or card.word
        return card.accepted[0] if card.accepted else ""

    def check_card(self, card: Card, answer: str) -> Result:
        if not card.reverse:
            return check(
                answer, card.accepted, card.alternatives,
                typo_tolerance=self.typo, fold_turkish=self.fold,
            )
        result = check_en(answer, card.targets, typo_tolerance=self.typo)
        if result.is_correct:
            return result
        # Kardes kelime: ayni Turkce ana anlam ('buyuk' icin large yerine big)
        key = normalize(card.primary)
        for word_id, forms in self._siblings.get(key, []):
            if word_id == card.word_id:
                continue
            sib = check_en(answer, forms, typo_tolerance=False)
            if sib.verdict == VERDICT_CORRECT:
                return Result(
                    VERDICT_CORRECT, matched=sib.matched,
                    hint=f"“{sib.matched}” de olur — bu kartın kelimesi: "
                         f"{card.display or card.word}",
                )
        return result

    def build_group(self) -> list[Card]:
        """Bir tur olusturur.

        Her turda:
          * en az `new_per_group` YENI kelime (havuz bosalana dek garanti),
          * kalan yerler tekrar zamani gelmis kartlara (en gecikmis once),
          * hala bosluk varsa: once yine yeni, sonra zamani yaklasan kartlar.
        Karisik modda paylar iki yone bolunur.
        """
        n = self.group_size
        dirs = list(self.directions)
        random.shuffle(dirs)
        # Karisik modda her yon turun yarisini alir; artan ilk yone gider
        quota = {d: n // len(dirs) for d in dirs}
        quota[dirs[0]] += n - sum(quota.values())
        new_share = {d: min(quota[d], round(self.new_per_group * quota[d] / n))
                     for d in dirs}

        group: list[Card] = []
        seen: set[int] = set()   # ayni kelime bir turda iki yonde cikmasin

        def take(cards: list[Card], cap: int) -> None:
            for card in cards:
                if cap <= 0:
                    return
                if card.word_id in seen:
                    continue
                seen.add(card.word_id)
                group.append(card)
                cap -= 1

        def have(d: str) -> int:
            return sum(1 for c in group if c.direction == d)

        for d in dirs:
            room = quota[d] - new_share[d]
            take(self._pick_due(room, d), room)
            # yeni kelime garantisi: tekrarlar payini doldursa da en az new_share
            room = quota[d] - have(d)
            take(self._pick_new(room, d), room)
        # Bosluk kaldiysa (havuz veya tekrar yetmedi) hangi yon verebiliyorsa
        for pick in (self._pick_due, self._pick_new, self._pick_overdue_any):
            for d in dirs:
                if len(group) < n:
                    take(pick(n - len(group), d), n - len(group))

        # Zamani gelenler basta kalsin ama sira ezberlenmesin diye hafif karistir
        random.shuffle(group)
        return group

    def next_card(self) -> Card | None:
        """Siradaki karti verir.

        Kuyruktaki kart bu arada 'biliniyor'/'ogrenildi' olmus olabilir
        (orn. kullanici Ctrl+K ile onayladi). Boyle kartlari atlar - yoksa
        kelime tekrar sorulur ve yanlis cevap onu geri dusururdu.

        DIKKAT: teyit bekleyen 'biliniyor' kartlari (due_at > 0) atlanmaz;
        atlanirsa kuyruk surekli ayni karti uretip sonsuz donguye girer.
        """
        attempts = 0
        while attempts < 200:
            attempts += 1
            if not self._queue:
                self._queue = self.build_group()
            if not self._queue:
                return None
            card = self._queue.pop(0)
            row = self.conn.execute(
                "SELECT state, due_at FROM progress WHERE word_id = ?",
                (card.word_id,),
            ).fetchone()
            settled = row and row["state"] in (db.KNOWN, db.LEARNED)
            awaiting_confirmation = row and row["due_at"] > 0
            if settled and not awaiting_confirmation:
                continue
            return card
        return None

    def peek_group_size(self) -> int:
        return len(self._queue)

    # ------------------------------------------------------------ cevaplama
    def peek(self, card: Card, answer: str) -> Result:
        """Cevabi DEGERLENDIRIR ama kaydetmez.

        Arayuz bunu, kullanici kelimenin uzak bir anlamini yazdiginda cezasiz
        "tekrar dene" verebilmek icin kullanir: kelimeyi bildigi bellidir,
        yanlis sayip seriyi dusurmek adil olmaz.
        """
        return self.check_card(card, answer)

    def accept_answer(self, card: Card, answer: str) -> Outcome | None:
        """Kullanici 'bunu da dogru say' dedi.

        Uc sey yapar:
          1. son cevabin cezasini GERI ALIR (seri/durum/sayaclar eski haline),
          2. cevabi kalici olarak bu kelimenin kabul listesine ekler,
          3. cevabi yeniden isler - artik dogru sayilir.
        """
        answer = (answer or "").strip()
        if not answer:
            return None

        self._undo_last(card.word_id)
        db.add_user_accepted(self.conn, card.word_id, answer, card.direction)
        self._user_accepted.setdefault(card.direction, {}).setdefault(
            card.word_id, []).append(answer)
        if card.reverse:
            if answer not in card.targets:
                card.targets.append(answer)
        else:
            if answer not in card.accepted:
                card.accepted.append(answer)
            card.alternatives = [a for a in card.alternatives if a != answer]

        outcome = self.submit(card, answer)

        # Kullanici "bunu biliyorum" dedi: kelime dogrudan BILINIYOR'a gecer,
        # tekrar dongusunde beklemez. (Sadece seri artirmak yetmezdi - zaten
        # bildigi kelimeyi 20 tur daha sormanin anlami yok.)
        if outcome.state_after != db.KNOWN:
            self.conn.execute(
                """UPDATE progress
                    SET state = ?, streak = ?, best_streak = MAX(best_streak, ?),
                        settled_at = ?
                    WHERE word_id = ?""",
                (db.KNOWN, self.target_streak, self.target_streak,
                 datetime.now().isoformat(), card.word_id),
            )
            self.conn.commit()
            outcome.state_after = db.KNOWN
            outcome.streak = self.target_streak
            outcome.promoted = "known"

        # Kelime artik biliniyor: bu oturumun kuyrugunda bekleyen kopyasini da
        # cikar ki tekrar sorulmasin.
        self._queue = [c for c in self._queue if c.word_id != card.word_id]
        return outcome

    def _undo_last(self, word_id: int) -> None:
        """Bu kelime icin en son kaydi ve etkilerini geri alir."""
        snap = self._undo
        if not snap or snap["word_id"] != word_id:
            return
        row = snap["row"]
        self.conn.execute(
            """UPDATE progress SET
                 state = ?, streak = ?, best_streak = ?, shows = ?,
                 correct = ?, wrong = ?, session_hits = ?, last_seen = ?,
                 first_seen = ?, settled_at = ?
               WHERE word_id = ?""",
            (row["state"], row["streak"], row["best_streak"], row["shows"],
             row["correct"], row["wrong"], row["session_hits"], row["last_seen"],
             row["first_seen"], row["settled_at"], word_id),
        )
        if snap.get("review_id"):
            self.conn.execute("DELETE FROM reviews WHERE id = ?",
                              (snap["review_id"],))
        # gunluk sayaci da geri al
        day = snap["day"]
        self.conn.execute(
            "UPDATE daily SET cards = MAX(cards - 1, 0), "
            "correct = MAX(correct - ?, 0) WHERE day = ?",
            (int(snap["was_correct"]), day),
        )
        self.conn.commit()
        self._undo = None

    def _schedule(self, state: str, gap_idx: int, correct: bool,
                  state_before: str) -> int:
        """Kelimenin bir daha KAC KART SONRA cikacagini hesaplar.

        Tekrar merdiveni (varsayilan 3, 8, 20, 45, 100, 250, 600 kart):
        her dogruda bir ust basamak, her yanlista basa donus. Sozlukten
        parmakla kapatarak ezberlemenin dijital hali.
        """
        if state == db.LEARNED:
            return 0                       # rotasyondan cikti
        if state == db.KNOWN:
            if state_before == db.POOL and self.confirm_known:
                # Tekte bilindi: uzak bir noktada bir kez teyit sorulur
                return self.counter + self.gaps[-2 if len(self.gaps) > 1 else -1]
            return 0                       # teyit edildi veya teyit kapali
        step = min(max(gap_idx, 0), len(self.gaps) - 1)
        return self.counter + self.gaps[step]

    def submit(self, card: Card, answer: str) -> Outcome:
        result = self.check_card(card, answer)
        correct = result.is_correct
        now = datetime.now().isoformat()

        row = self.conn.execute(
            "SELECT * FROM progress WHERE word_id = ?", (card.word_id,)
        ).fetchone()
        # "Bunu da dogru say" secenegi icin degisiklik oncesi durumu sakla
        self._undo = {
            "word_id": card.word_id, "row": dict(row),
            "day": date.today().isoformat(), "was_correct": correct,
            "review_id": None,
        }
        state_before = row["state"]
        streak, shows = row["streak"], row["shows"] + 1
        hits = row["session_hits"]
        promoted, reset, counted = "", False, True

        gap_idx = row["gap_idx"]
        self.counter = db.bump_card_counter(self.conn)

        if correct:
            if state_before == db.POOL:
                # Ilk temasta tek seferde dogru -> biliniyor.
                # Ama 'confirm_known' acikken bir kez daha teyit edilir:
                # sansla bilinen kelime kalici olarak elenmesin.
                state_after, streak, promoted = db.KNOWN, self.target_streak, "known"
                gap_idx = 0
            elif state_before == db.KNOWN:
                # Teyit sorusu dogru cevaplandi -> kelime muhurlendi
                state_after, streak, promoted = db.KNOWN, self.target_streak, ""
                gap_idx = 0
            else:
                # Hibrit ritim: oturum basina en fazla `hit_cap` kez seri artar
                counted = hits < self.hit_cap
                if counted:
                    streak += 1
                    hits += 1
                gap_idx = min(gap_idx + 1, len(self.gaps) - 1)
                state_after = (
                    db.LEARNED if streak >= self.target_streak else db.LEARNING
                )
                if state_after == db.LEARNED:
                    promoted = "learned"
        else:
            state_after = db.LEARNING
            reset = streak > 0
            if state_before == db.KNOWN:
                # Teyit sorusunda takildi: demek ki gercekten bilmiyormus
                streak = 0
            if self.reset_mode == "half":
                streak //= 2
            elif self.reset_mode == "minus5":
                streak = max(0, streak - 5)
            else:
                streak = 0
            if state_before == db.POOL:
                counted = True  # ilk temasta yanlis -> tekrar havuzuna dusuruldu
            gap_idx = 0          # merdivende basa don: 3 kart sonra tekrar cikar

        due_at = self._schedule(state_after, gap_idx, correct, state_before)

        self.conn.execute(
            """UPDATE progress SET
                 state = ?, streak = ?, best_streak = MAX(best_streak, ?),
                 shows = ?, correct = correct + ?, wrong = wrong + ?,
                 session_hits = ?, last_session = ?, last_seen = ?,
                 due_at = ?, gap_idx = ?,
                 first_seen = COALESCE(first_seen, ?),
                 settled_at = CASE WHEN ? <> '' THEN ? ELSE settled_at END
               WHERE word_id = ?""",
            (state_after, streak, streak, shows, int(correct), int(not correct),
             hits, self.session_id, now, due_at, gap_idx, now, promoted, now,
             card.word_id),
        )
        cur = self.conn.execute(
            """INSERT INTO reviews
                 (word_id, session_id, ts, correct, counted, answer, direction)
               VALUES (?,?,?,?,?,?,?)""",
            (card.word_id, self.session_id, now, int(correct), int(counted),
             answer, card.direction),
        )
        if self._undo:
            self._undo["review_id"] = cur.lastrowid
        db.bump_daily(self.conn, correct)
        self.conn.commit()

        self._recent.append(card.word_id)
        # Yanlis bilinen kart 3 kart sonra tekrar cikacak sekilde zaten
        # planlandi (_schedule); kuyruga elle eklemeye gerek yok.
        if not correct:
            self._queue = [c for c in self._queue if c.word_id != card.word_id]

        return Outcome(
            result=result, correct=correct, counted=counted,
            state_before=state_before, state_after=state_after,
            streak=streak, target_streak=self.target_streak,
            promoted=promoted, reset=reset,
        )

    def _requeue(self, card: Card) -> None:
        """Yanlis bilinen karti kuyrugun sonuna geri koyar (en az gap kadar sonra)."""
        if any(c.word_id == card.word_id for c in self._queue):
            return
        self._queue.append(card)

    def finish(self) -> None:
        db.end_session(self.conn, self.session_id)
