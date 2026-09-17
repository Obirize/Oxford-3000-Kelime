"""Uctan uca kullanim senaryosu testi.

Gercek bir kullanicinin yapacagi her seyi gercek tus/fare olaylariyla taklit
eder ve her adimdan sonra "cevap kutusuna yazi yazilabiliyor mu" dogrular.
Bu dosya bir regresyon testidir: arayuze dokunduktan sonra calistir.

    py tools/scenario.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import db                       # noqa: E402
from app.ui.app_window import AppWindow  # noqa: E402

from _guard import test_db, cleanup   # noqa: E402

TEST_DB = test_db("data/_scenario.db")
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "✅" if condition else "❌"
    print(f"  {mark} {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        failures.append(label)


def setup():
    conn = db.connect(TEST_DB)
    db.sync_words(conn)
    db.set_setting(conn, "audio", 0)
    app = AppWindow(conn)
    app.update()
    app.show("quiz")
    app.update()
    return app, conn


# NOT: event_generate("<KeyPress-i>") bu makinede (Turkce klavye duzeni) 'i'
# harfini uretmiyor - bu bir Tk/duzen artefaktidir, uygulamayla ilgisi yoktur.
# Bu yuzden metin girisi entry.insert() ile yapiliyor: insert() de tipki gercek
# klavye gibi kilitli (disabled) kutuya YAZMAZ, dolayisiyla "yazilabiliyor mu"
# sorusunu dogru olcer. Enter/Esc ise gercek tus olayi olarak gonderiliyor.
def type_answer(app, quiz, text: str) -> str:
    """Cevap kutusuna metin girer; kutu kilitliyse hicbir sey yazilmaz."""
    quiz.entry.focus_force()
    app.update()
    try:
        quiz.entry.delete(0, "end")
    except Exception:
        pass
    quiz.entry.insert(0, text)
    app.update()
    return quiz.answer.get()


def press(app, quiz, key: str) -> None:
    """Gercek tus olayi (Enter / Esc)."""
    quiz.entry.focus_force()
    app.update()
    quiz.entry.event_generate(key)
    app.update()


def advance(app, quiz) -> None:
    """Sonraki karta gecer.

    Yeni bir kelime bilinemediginde araya "dogru cevabi bir kez yaz" adimi
    girer; once onu gecmek gerekir.
    """
    if quiz.teach_mode:
        press(app, quiz, "<Escape>")      # ogret adimini atla
    press(app, quiz, "<Return>")


def can_type(app, quiz) -> bool:
    """Kutucuga gercekten yazi yazilabiliyor mu?"""
    quiz.answer.set("")
    typed = type_answer(app, quiz, "deneme")
    quiz.answer.set("")
    return typed == "deneme"


def main() -> int:
    app, conn = setup()
    quiz = app._views["quiz"]

    print("\n0) Gercek klavye tus olaylari kutucuga ulasiyor mu")
    quiz.answer.set("")
    quiz.entry.focus_force(); app.update()
    for ks in ("t", "e", "s", "t"):
        quiz.entry.event_generate(f"<KeyPress-{ks}>")
    app.update()
    check("gercek tus olaylari yaziyor", quiz.answer.get() == "test",
          repr(quiz.answer.get()))
    quiz.answer.set("")

    # ---------------------------------------------------------------- 1
    print("\n1) Yeni kelime -> DOGRU cevap yaz -> Enter")
    word = quiz.card.word
    correct = quiz.card.accepted[0]
    typed = type_answer(app, quiz, correct)
    check("cevap kutusuna yazilabiliyor", typed == correct, repr(typed))
    press(app, quiz, "<Return>")
    check("geri bildirim gosteriliyor (karta atlamiyor)",
          quiz.awaiting_next and quiz.card.word == word, quiz.card.word)
    check("'tek seferde bildin' mesaji", "🌟" in quiz.feedback.cget("text"))
    state = conn.execute(
        "SELECT state FROM progress p JOIN words w ON w.id=p.word_id WHERE w.word=?",
        (word,)).fetchone()["state"]
    check("durum BILINIYOR oldu", state == db.KNOWN, state)

    print("\n2) Enter -> sonraki kart")
    press(app, quiz, "<Return>")
    check("yeni kelime geldi", quiz.card.word != word, quiz.card.word)
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    # ---------------------------------------------------------------- 3
    print("\n3) Bilmiyorum -> Esc")
    word = quiz.card.word
    press(app, quiz, "<Escape>")
    check("geri bildirim gosteriliyor", quiz.awaiting_next or quiz.teach_mode)
    check("dogru cevap ekranda", word in quiz.detail.cget("text"))
    state = conn.execute(
        "SELECT state FROM progress p JOIN words w ON w.id=p.word_id WHERE w.word=?",
        (word,)).fetchone()["state"]
    check("durum OGRENILIYOR oldu", state == db.LEARNING, state)

    print("\n4) Enter -> sonraki kart  (bildirilen hatanin oldugu yer)")
    advance(app, quiz)
    check("yeni kelime geldi", quiz.card.word != word, quiz.card.word)
    check("kutucuk kilitli DEGIL", str(quiz.entry.cget("state")) == "normal")
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    # ---------------------------------------------------------------- 5
    print("\n5) YANLIS cevap yaz -> Enter -> Enter")
    word = quiz.card.word
    type_answer(app, quiz, "zzz")
    press(app, quiz, "<Return>")
    check("yanlis geri bildirimi", "❌" in quiz.feedback.cget("text"))
    advance(app, quiz)
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    # --------------------------------------------------------------- 5b
    print("\n5b) UZAK ANLAM yazmak cezasiz tekrar vermeli")
    # Bazi alternatifler kabul edilenin cekim/yazim varyantidir ("yıl dönümü" =
    # "yıldönümü") ve dogru sayilir. Bu adim icin gercekten REDDEDILEN bir
    # alternatif bulmamiz gerekiyor.
    found = far_meaning = None
    for _ in range(60):
        if quiz.card:
            far_meaning = next(
                (a for a in quiz.card.alternatives
                 if quiz.engine.peek(quiz.card, a).verdict == "other"), None)
            if far_meaning:
                found = quiz.card
                break
        press(app, quiz, "<Escape>")
        advance(app, quiz)
    if found:
        before = conn.execute(
            "SELECT state, streak, shows, wrong FROM progress p "
            "JOIN words w ON w.id=p.word_id WHERE w.word=?", (found.word,)).fetchone()
        reviews_before = conn.execute(
            "SELECT COUNT(*) n FROM reviews").fetchone()["n"]

        type_answer(app, quiz, far_meaning)
        press(app, quiz, "<Return>")

        after = conn.execute(
            "SELECT state, streak, shows, wrong FROM progress p "
            "JOIN words w ON w.id=p.word_id WHERE w.word=?", (found.word,)).fetchone()
        reviews_after = conn.execute(
            "SELECT COUNT(*) n FROM reviews").fetchone()["n"]

        check("'ana anlamini istiyorum' uyarisi", "🔸" in quiz.feedback.cget("text"))
        check("ayni kart duruyor (karta atlamadi)",
              quiz.card is not None and quiz.card.word == found.word)
        check("kutucuk hala yazilabilir", not quiz.awaiting_next
              and str(quiz.entry.cget("state")) == "normal")
        check("CEZA YOK: kayit tutulmadi", reviews_after == reviews_before,
              f"{reviews_before}->{reviews_after}")
        check("CEZA YOK: seri/durum degismedi",
              (before["state"], before["streak"], before["wrong"])
              == (after["state"], after["streak"], after["wrong"]))

        # simdi dogru cevabi yaz - normal akis islemeli
        type_answer(app, quiz, found.accepted[0])
        press(app, quiz, "<Return>")
        check("ardindan dogru cevap normal islendi",
              "❌" not in quiz.feedback.cget("text") and quiz.awaiting_next)
        press(app, quiz, "<Return>")
    else:
        print("  (uzak anlamli kelime cikmadi, atlandi)")
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    # ---------------------------------------------------------------- 6
    print("\n6) Turkce karakter serbestligi ve yazim hatasi toleransi")
    for _ in range(40):
        target = next((a for a in quiz.card.accepted
                       if any(ch in a for ch in "şıçöüğ")), None)
        if target:
            break
        press(app, quiz, "<Escape>")
        advance(app, quiz)
    if target:
        folded = (target.replace("ş", "s").replace("ı", "i").replace("ç", "c")
                        .replace("ö", "o").replace("ü", "u").replace("ğ", "g"))
        type_answer(app, quiz, folded)
        press(app, quiz, "<Return>")
        # Dogru cevabin basligi duruma gore degisir (✅ / ⚠️ / 🌟 / 🏆);
        # bu yuzden "yanlis degil" seklinde dogrula.
        head = quiz.feedback.cget("text")
        check(f"'{folded}' = '{target}' kabul edildi",
              "❌" not in head and "🔸" not in head, head)
        press(app, quiz, "<Return>")
    else:
        print("  (bu turda Turkce karakterli kelime cikmadi, atlandi)")
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    # --------------------------------------------------------------- 6b
    print("\n6b) Amerikan / Ingiliz yazimi")
    from app.engine import _row_to_card

    def load(word: str, spelling: str):
        return _row_to_card(conn.execute(
            "SELECT w.*, p.state,p.streak,p.shows,p.session_hits "
            "FROM words w JOIN progress p ON p.word_id=w.id WHERE w.word=?",
            (word,)).fetchone(), spelling)

    us, uk = load("mum", "us"), load("mum", "uk")
    check("varsayilan Amerikan yazimi", us.display == "mom", us.display)
    check("Ingiliz yazimi not olarak duruyor", us.other_form == "mum", us.other_form)
    check("ornek cumle de donusuyor", us.example.startswith("Mom"), us.example[:26])
    check("ayar 'uk' iken Ingiliz yazimi", uk.display == "mum", uk.display)
    check("Turkce karsilik iki modda da ayni", us.accepted == uk.accepted,
          str(us.accepted))
    plain = load("book", "us")
    check("normal kelime etkilenmiyor",
          plain.display == "book" and plain.other_form == "")

    # ---------------------------------------------------------------- 7
    print("\n6c) 'Bunu da dogru say' (Ctrl+K)")
    while quiz.card is None or quiz.awaiting_next or quiz.teach_mode:
        advance(app, quiz)
    word_id = quiz.card.word_id
    before = conn.execute(
        "SELECT state, streak, wrong FROM progress WHERE word_id=?",
        (word_id,)).fetchone()
    type_answer(app, quiz, "kesinlikleyanlisbircevap")
    press(app, quiz, "<Return>")
    check("once yanlis sayildi", "❌" in quiz.feedback.cget("text"))
    check("isaretleme butonu goruldu", bool(quiz.accept_btn.winfo_ismapped()))
    quiz.accept_my_answer()
    app.update()
    after = conn.execute(
        "SELECT state, streak, wrong FROM progress WHERE word_id=?",
        (word_id,)).fetchone()
    check("cevap artik dogru sayiliyor", "✓" in quiz.feedback.cget("text"),
          quiz.feedback.cget("text")[:44])
    check("CEZA GERI ALINDI", after["wrong"] == before["wrong"],
          f"yanlis {before['wrong']} -> {after['wrong']}")
    flags = db.list_user_accepted(conn)
    check("isaret kaydedildi",
          any(f["answer"] == "kesinlikleyanlisbircevap" for f in flags),
          f"{len(flags)} kayit")
    press(app, quiz, "<Return>")
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    print("\n7) Ekranlar arasi gezinip calismaya geri donme")
    for view in ("dashboard", "words", "stats", "settings"):
        app.show(view)
        app.update()
    app.show("quiz")
    app.update()
    check("calisma ekrani geri geldi", quiz.card is not None)
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    print("\n8) Baska ekranda Enter'a basmak calismayi bozmuyor")
    app.show("words")
    app.update()
    app.focus_get() and app.event_generate("<Return>")
    app.update()
    app.show("quiz")
    app.update()
    check("kart hala duruyor", quiz.card is not None)
    check("KUTUCUGA YAZILABILIYOR", can_type(app, quiz))

    # ---------------------------------------------------------------- 9
    print("\n9) 30 kart hizli akis - her karttan sonra kutucuk kontrolu")
    ok = True
    for i in range(30):
        if quiz.card is None:
            break
        if not can_type(app, quiz):
            ok = False
            print(f"     kart {i+1} ({quiz.card.word}) sonrasi yazilamiyor!")
            break
        if i % 3 == 0:
            press(app, quiz, "<Escape>")
        else:
            type_answer(app, quiz, quiz.card.accepted[0])
            press(app, quiz, "<Return>")
        advance(app, quiz)
    check("30 kart boyunca kutucuk hep yazilabilir kaldi", ok)

    # ---------------------------------------------------------------- 10
    print("\n10) Kayit butunlugu")
    n = conn.execute("SELECT COUNT(*) n FROM reviews").fetchone()["n"]
    blank = conn.execute(
        "SELECT COUNT(*) n FROM reviews WHERE answer = '' AND correct = 1"
    ).fetchone()["n"]
    check(f"{n} cevap kaydedildi", n > 30, str(n))
    check("bos cevap yanlislikla dogru sayilmamis", blank == 0, str(blank))
    # Yanlis yapilan kelime kendiliginden 'biliniyor' olmamali. Istisna:
    # kullanici Ctrl+K ile "biliyordum" dediyse bilerek oraya tasinir.
    bad = conn.execute(
        "SELECT COUNT(*) n FROM progress p WHERE p.state='known' AND p.wrong>0 "
        "AND p.word_id NOT IN (SELECT word_id FROM user_accepted)"
    ).fetchone()["n"]
    check("yanlis yapilan kelime kendiliginden 'biliniyor' olmamis",
          bad == 0, str(bad))
    manual = conn.execute(
        "SELECT COUNT(*) n FROM progress p WHERE p.state='known' "
        "AND p.word_id IN (SELECT word_id FROM user_accepted)"
    ).fetchone()["n"]
    check("Ctrl+K ile onaylanan kelime BILINENLERDE", manual >= 1, f"{manual} kelime")

    # ---------------------------------------------------------------- 11
    print("\n11) Ters yon (TR -> EN) - ilerleme TEK, yon sadece soru bicimi")
    quiz.switch_direction()
    app.update()
    check("yon dugmesi TR -> EN gosteriyor", "TR → EN" in quiz.dir_btn.cget("text"),
          quiz.dir_btn.cget("text"))
    check("motor ters yonde", quiz.engine is not None and quiz.engine.directions == ["tr_en"])
    check("kart geldi", quiz.card is not None)
    # once havuzdan YENI bir kelime bul (ters yonde tekte bilme -> biliniyor)
    for _ in range(30):
        if quiz.card is not None and quiz.card.is_new:
            break
        press(app, quiz, "<Escape>")
        advance(app, quiz)
    if quiz.card is not None and quiz.card.is_new:
        card = quiz.card
        known_before = conn.execute(
            "SELECT COUNT(*) n FROM progress WHERE state = 'known'").fetchone()["n"]
        check("ekranda Turkce anlam var, Ingilizce kelime yok",
              quiz.word_lbl.cget("text") == card.primary
              and quiz.word_lbl.cget("text").lower() != card.word.lower(),
              quiz.word_lbl.cget("text"))
        check("ses dugmesi gizli (cevabi ele vermesin)",
              not quiz.audio_btn.winfo_manager())
        check("kutu yazilabilir", can_type(app, quiz))
        type_answer(app, quiz, card.display or card.word)
        press(app, quiz, "<Return>")
        state = conn.execute("SELECT state FROM progress WHERE word_id = ?",
                             (card.word_id,)).fetchone()["state"]
        check("Ingilizcesini tekte yazinca -> ayni 'progress' tablosunda 'known'",
              state == "known", state)
        known_after = conn.execute(
            "SELECT COUNT(*) n FROM progress WHERE state = 'known'").fetchone()["n"]
        check("UST BARDAKI 'biliniyor' sayisi ters yonde de artti",
              known_after == known_before + 1
              and app.status.tiles["known"].cget("text") == str(known_after),
              f"{known_before} -> {known_after}, bar: {app.status.tiles['known'].cget('text')}")
        advance(app, quiz)
    else:
        print("  (yeni kelime bulunamadi, atlandi)")
    # yanlis cevap: Turkce yazmak (yon karistirma) yanlis sayilmali
    card = quiz.card
    if card is not None:
        type_answer(app, quiz, card.accepted[0])
        press(app, quiz, "<Return>")
        state = conn.execute("SELECT state FROM progress WHERE word_id = ?",
                             (card.word_id,)).fetchone()["state"]
        check("Turkce cevap ters yonde yanlis -> 'learning'", state == "learning", state)
        check("dogru Ingilizce kelime geri bildirimde gosterildi",
              (card.display or card.word) in quiz.detail.cget("text"),
              quiz.detail.cget("text")[:60])
        advance(app, quiz)
    # kardes kelime: ayni Turkce ana anlam
    from app.matching import normalize
    sib_checked = False
    for _ in range(25):
        card = quiz.card
        if card is None:
            break
        key = quiz.engine._siblings.get(normalize(card.primary), [])
        others = [f for wid, forms in key if wid != card.word_id for f in forms]
        if others:
            type_answer(app, quiz, others[0])
            press(app, quiz, "<Return>")
            check(f"kardes kelime kabul: '{others[0]}' -> {card.word} ({card.primary})",
                  "de olur" in quiz.detail.cget("text"), quiz.detail.cget("text")[:70])
            sib_checked = True
            advance(app, quiz)
            break
        advance(app, quiz)
    if not sib_checked:
        print("  (kardes kelimeli kart cikmadi, atlandi)")

    # ---------------------------------------------------------------- 12
    print("\n12) Karisik mod (her kart kendi yonunde)")
    quiz.switch_direction()          # TR->EN -> Karisik
    app.update()
    check("yon dugmesi Karisik", "Karışık" in quiz.dir_btn.cget("text"),
          quiz.dir_btn.cget("text"))
    check("motor iki yonu de uretiyor",
          quiz.engine is not None and set(quiz.engine.directions) == {"en_tr", "tr_en"})
    seen_dirs, ok, mismatch = set(), True, ""
    for i in range(20):
        card = quiz.card
        if card is None:
            break
        seen_dirs.add(card.direction)
        shown = quiz.word_lbl.cget("text")
        if card.direction == "tr_en":
            good = shown == card.primary and "İngilizcesi" in quiz.prompt.cget("text")
        else:
            good = shown == (card.display or card.word) and "Türkçe" in quiz.prompt.cget("text")
        if not good:
            ok, mismatch = False, f"{card.direction}: '{shown}' / {quiz.prompt.cget('text')}"
            break
        if not can_type(app, quiz):
            ok, mismatch = False, f"kart {i+1} sonrasi yazilamiyor"
            break
        # dogru cevap ver, ilerle
        type_answer(app, quiz, (card.display or card.word) if card.direction == "tr_en"
                    else card.accepted[0])
        press(app, quiz, "<Return>")
        advance(app, quiz)
    check("20 kartta soru metni kartin yonuyle uyumlu", ok, mismatch)
    check("iki yon de karsimiza cikti", seen_dirs == {"en_tr", "tr_en"}, str(seen_dirs))
    both = conn.execute(
        "SELECT COUNT(DISTINCT direction) FROM reviews WHERE session_id = ?",
        (quiz.engine.session_id,)).fetchone()[0]
    check("kayitlar iki yonle etiketlendi", both == 2, str(both))

    quiz.switch_direction()          # Karisik -> EN->TR
    app.update()
    check("geri EN -> TR", quiz.engine is not None
          and quiz.engine.directions == ["en_tr"])
    check("kutu yazilabilir", can_type(app, quiz))

    # ---------------------------------------------------------------- 13
    print("\n13) Yeni kelime akisi kesilmiyor + ayni kelime oturumda en fazla 3 kez")
    # 25 kelimeyi ust uste bilme: tekrar yigini buyusun
    for _ in range(25):
        if quiz.card is None:
            break
        press(app, quiz, "<Escape>")
        advance(app, quiz)
    learning = conn.execute(
        "SELECT COUNT(*) n FROM progress WHERE state = 'learning'").fetchone()["n"]
    check("tekrar yigini buyudu", learning >= 20, f"{learning} ogreniliyor")
    # simdi 40 kart boyunca her turda yeni kelime gelmeye devam etmeli
    cap = quiz.engine.show_cap
    per_group = quiz.engine.new_per_group
    seen_new, groups_ok, session_id = 0, True, quiz.engine.session_id
    for _ in range(4):
        group = quiz.engine.build_group()
        n_new = sum(1 for c in group if c.is_new)
        if n_new < per_group:
            groups_ok = False
        seen_new += n_new
    check(f"her turda en az {per_group} yeni kelime var (yigin {learning} iken)",
          groups_ok, f"4 turda toplam {seen_new} yeni")
    for _ in range(40):
        if quiz.card is None:
            break
        press(app, quiz, "<Escape>")
        advance(app, quiz)
    worst = conn.execute(
        "SELECT MAX(n) m FROM (SELECT COUNT(*) n FROM reviews WHERE session_id = ? "
        "GROUP BY word_id)", (session_id,)).fetchone()["m"]
    check(f"hicbir kelime bu oturumda {cap} kezden fazla sorulmadi",
          worst is not None and worst <= cap, f"en cok: {worst}")
    check("kutu yazilabilir", can_type(app, quiz))

    app.destroy()
    conn.close()
    os.remove(TEST_DB)

    print("\n" + "=" * 60)
    if failures:
        print(f"❌ {len(failures)} KONTROL BASARISIZ:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ TUM SENARYO KONTROLLERI BASARILI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
