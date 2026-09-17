"""Ana pencere: ust durum bari + navigasyon + gorunum yonetimi."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import backup, db, paths, stats
from .theme import F_H2, F_SMALL, F_STAT, F_TITLE, Theme, segmented_bar

APP_TITLE = "Oxford 3000 · İngilizce Kelime Ezberleme"


class StatusBar(ttk.Frame):
    """Ust bar: sayaclar, ilerleme cubugu, seviye tahmini, gunluk hedef."""

    def __init__(self, master, theme: Theme, conn):
        super().__init__(master, style="Card.TFrame")
        self.theme, self.conn = theme, conn
        c = theme.c

        pad = ttk.Frame(self, style="Card.TFrame")
        pad.pack(fill="both", expand=True, padx=18, pady=14)

        # --- 1. satir: sayac kutulari ---
        row = ttk.Frame(pad, style="Card.TFrame")
        row.pack(fill="x")
        self.tiles: dict[str, ttk.Label] = {}
        specs = [
            ("known",    "Biliniyor",    c["known"]),
            ("learned",  "Öğrenildi",    c["learned"]),
            ("learning", "Öğreniliyor",  c["learning"]),
            ("pool",     "Kalan havuz",  c["text_dim"]),
        ]
        for key, label, color in specs:
            box = ttk.Frame(row, style="Card.TFrame")
            box.pack(side="left", padx=(0, 26))
            dot = ttk.Frame(box, style="Card.TFrame")
            dot.pack(anchor="w")
            cv = tk.Canvas(dot, width=9, height=9, bg=c["surface"],
                           highlightthickness=0)
            cv.create_oval(0, 0, 9, 9, fill=color, outline="")
            cv.pack(side="left", pady=(0, 2))
            ttk.Label(dot, text=f" {label}", style="CardDim.TLabel").pack(side="left")
            value = ttk.Label(box, text="0", style="Card.TLabel", font=F_STAT)
            value.pack(anchor="w")
            self.tiles[key] = value

        # sag taraf: seviye + seri
        right = ttk.Frame(row, style="Card.TFrame")
        right.pack(side="right")
        self.level = ttk.Label(right, text="—", style="Card.TLabel", font=F_TITLE)
        self.level.pack(anchor="e")
        self.level_sub = ttk.Label(right, text="", style="CardDim.TLabel")
        self.level_sub.pack(anchor="e")

        # --- 2. satir: ilerleme cubugu ---
        self.bar = tk.Canvas(pad, height=10, bg=c["surface_alt"], highlightthickness=0)
        self.bar.pack(fill="x", pady=(14, 6))
        self.bar.bind("<Configure>", lambda _e: self.refresh())

        # --- 3. satir: alt bilgi satiri ---
        foot = ttk.Frame(pad, style="Card.TFrame")
        foot.pack(fill="x")
        self.progress_txt = ttk.Label(foot, text="", style="CardDim.TLabel")
        self.progress_txt.pack(side="left")
        self.meta = ttk.Label(foot, text="", style="CardDim.TLabel")
        self.meta.pack(side="right")

    def refresh(self) -> None:
        c = self.theme.c
        ov = stats.overview(self.conn)
        self.tiles["known"].config(text=f"{ov.known}")
        self.tiles["learned"].config(text=f"{ov.learned}")
        self.tiles["learning"].config(text=f"{ov.learning}")
        self.tiles["pool"].config(text=f"{ov.pool}")

        label, nxt, ratio = stats.estimate_level(self.conn)
        self.level.config(text=label)
        self.level_sub.config(
            text=f"{nxt}'e %{ratio*100:.0f}" if nxt else "tüm seviyeler tamamlandı"
        )

        width = max(self.bar.winfo_width(), 1)
        segmented_bar(
            self.bar,
            [(ov.known, c["known"]), (ov.learned, c["learned"]),
             (ov.learning, c["learning"]), (ov.pool, c["surface_alt"])],
            width, 10, c["surface_alt"],
        )
        self.progress_txt.config(
            text=f"{ov.mastered} / {ov.total} kelime hakim  ·  %{ov.progress*100:.1f}"
        )

        cards, _correct, goal = stats.today_progress(self.conn)
        days = stats.streak_days(self.conn)
        acc = stats.accuracy(self.conn)
        bits = [f"🔥 {days} günlük seri", f"bugün {cards}/{goal} kart"]
        if acc:
            bits.append(f"doğruluk %{acc*100:.0f}")
        if ov.stubborn:
            bits.append(f"⚠ {ov.stubborn} inatçı kelime")
        self.meta.config(text="   ·   ".join(bits))


class AppWindow(tk.Tk):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.theme = Theme(db.get_setting(conn, "theme", "dark"))

        self.title(APP_TITLE)
        self.geometry("1120x760")      # tam ekrandan cikilinca donulecek boyut
        self.minsize(940, 640)
        self._set_icon()
        self.theme.apply(self)
        self._fullscreen = False
        self.after(0, self._start_maximized)

        self.status = StatusBar(self, self.theme, conn)
        self.status.pack(fill="x", padx=16, pady=(16, 0))

        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=16, pady=(10, 0))
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._views: dict[str, ttk.Frame] = {}
        self._current = ""

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=16, pady=12)

        # Gorunumler gec yuklenir (dairesel import olmasin)
        from .dashboard import DashboardView
        from .quiz_view import QuizView
        from .settings_view import SettingsView
        from .stats_view import StatsView
        from .wordlist_view import WordListView

        specs = [
            ("dashboard", "🏠  Ana Ekran", DashboardView),
            ("quiz",      "✏️  Çalış",      QuizView),
            ("words",     "📚  Kelimeler",  WordListView),
            ("stats",     "📊  İstatistik", StatsView),
            ("settings",  "⚙️  Ayarlar",    SettingsView),
        ]
        for key, label, cls in specs:
            btn = ttk.Button(nav, text=label, style="Nav.TButton",
                             command=lambda k=key: self.show(k))
            btn.pack(side="left", padx=(0, 4))
            self._nav_buttons[key] = btn
            view = cls(self.body, self)
            self._views[key] = view

        self.show("dashboard")
        self.bind("<Control-q>", lambda _e: self.on_close())
        self.bind("<F11>", self.toggle_fullscreen)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------------------------------------------------- pencere
    def _set_icon(self) -> None:
        """Pencere ve gorev cubugu ikonu. Ikon yoksa sessizce gecilir."""
        icon = paths.asset("app.ico")
        if not icon.exists():
            return
        try:
            self.iconbitmap(default=str(icon))
        except tk.TclError:
            pass

    def _start_maximized(self) -> None:
        """Acilista ekrani kaplar. 'zoomed' Windows'ta gorev cubugunu korur;
        desteklenmeyen ortamda ekran boyutuna elle ayarlanir."""
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def toggle_fullscreen(self, _event=None) -> str:
        """F11: gercek tam ekran (baslik cubugu da gizlenir)."""
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)
        if not self._fullscreen:
            self._start_maximized()
        return "break"

    # ------------------------------------------------------------------ akis
    def show(self, key: str) -> None:
        if self._current == key:
            return
        if self._current:
            self._views[self._current].pack_forget()
            self._nav_buttons[self._current].configure(style="Nav.TButton")
        self._current = key
        view = self._views[key]
        view.pack(fill="both", expand=True)
        self._nav_buttons[key].configure(style="NavOn.TButton")
        if hasattr(view, "on_show"):
            view.on_show()
        self.status.refresh()

    def refresh_status(self) -> None:
        self.status.refresh()

    def on_close(self) -> None:
        quiz = self._views.get("quiz")
        if quiz is not None and hasattr(quiz, "stop_session"):
            quiz.stop_session()
        self.conn.commit()
        self.conn.close()
        # Temiz kapanista da yedek al: oturumda kazanilan ilerleme guvende olsun.
        try:
            backup.create(db.DB_PATH, force=True)
        except Exception:
            pass
        self.destroy()
