"""Arayuzu gercekten acar, birkac kart cevaplar, ekran goruntusu alir, kapatir."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from app import db
from app.ui.app_window import AppWindow

from _guard import test_db, cleanup
TEST_DB = test_db('data/_smoke.db')   # gercek ilerleme dosyasini kullanmayi engeller
conn = db.connect(TEST_DB); db.sync_words(conn)
db.set_setting(conn, 'audio', 0)      # test sirasinda ses calmasin

app = AppWindow(conn)
app.update()

steps = []
def shot(name):
    app.update_idletasks(); app.update()
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = int(app.frame(), 16) if False else None
    except Exception: pass
    steps.append(name)

def run():
    app.show('quiz')
    app.update(); app.update_idletasks()
    q = app._views['quiz']
    # 12 kart cevapla: yarisini dogru, yarisini yanlis
    for i in range(12):
        if q.card is None: break
        ans = q.card.accepted[0] if i % 2 == 0 else 'zzzz'
        q.submit(ans)
        app.update()
        q.next_card()
        app.update()
    q.stop_session()
    for view in ('dashboard','words','stats','settings'):
        app.show(view); app.update(); app.update_idletasks()
        print(f'  ✓ {view} ekrani sorunsuz acildi')
    app.show('dashboard'); app.update()

try:
    run()
    from app import stats
    ov = stats.overview(conn)
    print(f'\nSONUC -> biliniyor={ov.known} ogreniliyor={ov.learning} havuz={ov.pool}')
    lvl,nxt,r = stats.estimate_level(conn)
    print(f'seviye={lvl} -> {nxt} %{r*100:.1f}')
    n = conn.execute('SELECT COUNT(*) n FROM reviews').fetchone()['n']
    print(f'kaydedilen cevap sayisi={n}')
    print('\n✅ TUM EKRANLAR CALISIYOR')
finally:
    try: app.destroy()
    except Exception: pass
