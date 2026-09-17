"""Motoru sahte bir kullanici ile test eder: kurallar gercekten uyguluyor mu?"""
import random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from app import db, engine, stats

from _guard import test_db
TEST_DB = test_db("data/_sim.db")
conn = db.connect(TEST_DB)
print('kelime yuklendi:', db.sync_words(conn))

KNOW_RATE = 0.35   # sahte kullanici yeni kelimelerin %35'ini zaten biliyor
LEARN_RATE = 0.75  # tekrar gordugu kelimeyi %75 hatirliyor

for sess in range(1, 11):
    eng = engine.Engine(conn)
    promoted_known = promoted_learned = uncounted = 0
    for _ in range(60):                      # oturum basi 60 kart
        card = eng.next_card()
        if not card: break
        knows = random.random() < (KNOW_RATE if card.is_new else LEARN_RATE)
        answer = random.choice(card.accepted) if knows else "zzzz"
        out = eng.submit(card, answer)
        promoted_known += out.promoted == 'known'
        promoted_learned += out.promoted == 'learned'
        uncounted += out.correct and not out.counted
    eng.finish()
    ov = stats.overview(conn)
    lvl, nxt, ratio = stats.estimate_level(conn)
    print(f"oturum {sess:2d} | biliniyor {ov.known:4d} | ogrenildi {ov.learned:3d} | "
          f"ogreniliyor {ov.learning:3d} | havuz {ov.pool:4d} | "
          f"seviye {lvl}{' -> '+nxt if nxt else ''} %{ratio*100:.0f} | "
          f"sayilmayan tekrar {uncounted}")

print()
r = conn.execute("""SELECT w.word, p.streak, p.shows, p.correct, p.wrong, p.state
                    FROM progress p JOIN words w ON w.id=p.word_id
                    WHERE p.state='learning' ORDER BY p.shows DESC LIMIT 6""").fetchall()
print("en cok gosterilen ogreniliyor kelimeler:")
for x in r: print(f"   {x['word']:14s} gosterim={x['shows']:3d} seri={x['streak']:2d} D={x['correct']:3d} Y={x['wrong']:3d}")
mx = conn.execute("SELECT MAX(session_hits) m FROM progress").fetchone()['m']
print(f"\nDOGRULAMA -> bir oturumda maks seri artisi: {mx} (ayar: {db.get_int(conn,'session_hit_cap')})")
lr = conn.execute("SELECT COUNT(*) n FROM progress WHERE state='learned' AND streak<20").fetchone()['n']
print(f"DOGRULAMA -> 20 seriye ulasmadan 'ogrenildi' olan: {lr} (0 olmali)")
kn = conn.execute("SELECT COUNT(*) n FROM progress WHERE state='known' AND wrong>0").fetchone()['n']
print(f"DOGRULAMA -> yanlis yapmisken 'biliniyor' olan: {kn} (0 olmali)")
print(f"DOGRULAMA -> gunluk seri: {stats.streak_days(conn)} gun | dogruluk %{stats.accuracy(conn)*100:.0f} | tahmini bitis {stats.eta(conn)}")
conn.close(); os.remove(TEST_DB)
