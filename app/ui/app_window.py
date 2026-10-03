"""Ana pencere: ust durum bari + navigasyon + gorunum yonetimi."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from .. import backup, db, paths, stats, update, updater
from ..version import RELEASES_URL, VERSION
from .theme import F_H2, F_SMALL, F_STAT, F_TITLE, Theme, px, segmented_bar

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
            dot_size = px(9)
            cv = tk.Canvas(dot, width=dot_size, height=dot_size,
                           bg=c["surface"], highlightthickness=0)
            cv.create_oval(0, 0, dot_size, dot_size, fill=color, outline="")
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
        self.bar = tk.Canvas(pad, height=px(10), bg=c["surface_alt"],
                             highlightthickness=0)
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

        segmented_bar(
            self.bar,
            [(ov.known, c["known"]), (ov.learned, c["learned"]),
             (ov.learning, c["learning"]), (ov.pool, c["surface_alt"])],
            bg=c["surface_alt"],
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


class UpdateBar(ttk.Frame):
    """Yeni surum seridi: haber verir, indirir ve kurar.

    Durumlar
        bulundu   -> "Güncelle" (kurulu kopyada) / "İndirme sayfası" (tasinabilir)
        iniyor    -> ilerleme cubugu + "Vazgeç"
        hazir     -> "Kur ve yeniden başlat"
        hata      -> mesaj + "İndirme sayfası"

    Indirme arka plan is parcaciginda yapilir; Tk'ya yalnizca ana is
    parcacigindan dokunulur (sonuclar kuyruga dusurulur, _pump yoklar).
    "Şimdilik gizle" o surumu bir daha hatirlatmaz (ayar: update_skipped).
    """

    def __init__(self, master, theme: Theme, conn):
        super().__init__(master, style="Card.TFrame")
        self.theme, self.conn = theme, conn
        self.release = None
        self.installer: Path | None = None
        self._events: queue.Queue = queue.Queue()
        self._cancel = False
        self._busy = False

        pad = ttk.Frame(self, style="Card.TFrame")
        pad.pack(fill="x", padx=px(18), pady=px(10))
        self.text = ttk.Label(pad, text="", style="Card.TLabel", font=F_H2)
        self.text.pack(side="left")

        self.hide_btn = ttk.Button(pad, text="Şimdilik gizle", style="Ghost.TButton",
                                   command=self.skip)
        self.hide_btn.pack(side="right")
        self.action_btn = ttk.Button(pad, text="", style="Accept.TButton",
                                     command=self._on_action)
        self.action_btn.pack(side="right", padx=(0, 8))
        self.progress = ttk.Progressbar(pad, mode="determinate", length=px(220))

    # ------------------------------------------------------------ gorunum
    def show(self, release) -> None:
        self.release = release
        self.installer = None
        self._cancel = False
        self.text.config(
            text=f"⬆  Yeni sürüm var: {release.version}  "
                 f"(sende {VERSION})  ·  ilerlemen korunur"
        )
        self._set_action("⬇  Güncelle" if self._can_install()
                         else "İndirme sayfasını aç")
        self.pack(fill="x", padx=16, pady=(10, 0), after=self.master.status)
        if (self._can_install()
                and db.get_int(self.conn, "update_auto_download", 1) == 1):
            self.start_download(auto=True)

    def _can_install(self) -> bool:
        return bool(self.release and self.release.installer and updater.is_installed())

    def _set_action(self, label: str, *, enabled: bool = True) -> None:
        self.action_btn.config(text=label,
                               state="normal" if enabled else "disabled")

    def _on_action(self) -> None:
        if self.installer is not None:
            self.install()
        elif self._busy:
            self._cancel = True                   # "Vazgeç"
        elif self._can_install():
            self.start_download()
        else:
            webbrowser.open(self.release.url if self.release else RELEASES_URL)

    # ------------------------------------------------------------ indirme
    def start_download(self, *, auto: bool = False) -> None:
        if self._busy or self.release is None:
            return
        self._busy, self._cancel = True, False
        self.progress.config(value=0, maximum=100)
        self.progress.pack(side="right", padx=(0, 12))
        self.text.config(text=f"⬇  {self.release.version} indiriliyor…")
        self._set_action("Vazgeç")
        self.hide_btn.config(state="disabled")

        release = self.release

        def worker() -> None:
            try:
                path = updater.prepare(
                    release,
                    progress=lambda done, total: self._events.put(("p", (done, total))),
                    cancelled=lambda: self._cancel,
                )
                self._events.put(("ok", path))
            except updater.UpdateError as err:
                self._events.put(("err", str(err)))
            except Exception as err:                      # beklenmeyen her sey
                self._events.put(("err", f"Güncelleme yapılamadı: {err}"))

        threading.Thread(target=worker, daemon=True, name="update-download").start()
        self.after(100, lambda: self._pump(auto))

    def _pump(self, auto: bool) -> None:
        """Arka plandan gelen olaylari ANA is parcaciginda isler."""
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "p":
                    done, total = payload
                    if total:
                        self.progress.config(value=100 * done / total)
                        self.text.config(
                            text=f"⬇  {self.release.version} indiriliyor…  "
                                 f"%{100 * done / total:.0f}  "
                                 f"({done / 1e6:.1f} / {total / 1e6:.1f} MB)")
                elif kind == "ok":
                    self._downloaded(payload, auto)
                    return
                elif kind == "err":
                    self._failed(payload)
                    return
        except queue.Empty:
            pass
        if self._busy:
            self.after(100, lambda: self._pump(auto))

    def _downloaded(self, path, auto: bool) -> None:
        self._busy = False
        self.installer = path
        self.progress.pack_forget()
        self.hide_btn.config(state="normal")
        self.text.config(text=f"✅  {self.release.version} indirildi  ·  "
                              "kurulum birkaç saniye sürer, ilerlemen korunur")
        self._set_action("Kur ve yeniden başlat")
        if auto and db.get_int(self.conn, "update_auto_install", 0) == 1:
            self.install()

    def _failed(self, message: str) -> None:
        self._busy = False
        self.installer = None
        self.progress.pack_forget()
        self.hide_btn.config(state="normal")
        if self._cancel:
            self.text.config(text="İndirme iptal edildi.")
            self._set_action("⬇  Güncelle")
            return
        self.text.config(text=f"⚠  {message}")
        self._set_action("İndirme sayfasını aç")
        self.installer = None

    # ------------------------------------------------------------ kurulum
    def install(self) -> None:
        """Kurulumu baslatir ve programdan cikar.

        Calisan exe'nin uzerine yazilacagi icin once biz kapaniyoruz; kurulum
        bitince program kendiliginden geri acilir (/RESTARTAPP=1).
        """
        if self.installer is None:
            return
        try:
            updater.launch(self.installer)
        except updater.UpdateError as err:
            messagebox.showerror("Güncelleme", str(err))
            return
        self.master.on_close()

    def skip(self) -> None:
        if self.release:
            db.set_setting(self.conn, "update_skipped", self.release.version)
        self.pack_forget()


class AppWindow(tk.Tk):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.theme = Theme(db.get_setting(conn, "theme", "dark"))

        self.title(APP_TITLE)
        # Olculer ekran olceginde buyur; %125'te pencere de %25 buyuk acilir
        self.geometry(f"{px(1120)}x{px(760)}")   # tam ekrandan cikinca donulecek
        self.minsize(px(940), px(640))
        self._set_icon()
        self.theme.apply(self)
        self._fullscreen = False
        self.after(0, self._start_maximized)

        self.status = StatusBar(self, self.theme, conn)
        self.status.pack(fill="x", padx=16, pady=(16, 0))

        # Yeni surum serisi - yalnizca guncelleme bulununca gorunur
        self.update_bar = UpdateBar(self, self.theme, conn)

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
        # Acilista bir kez, arka planda: yeni surum var mi? (app/update.py)
        self.after(1500, self.check_updates)
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

    # ------------------------------------------------------------ guncelleme
    def check_updates(self, force: bool = False, on_done=None) -> bool:
        """Arka planda surum kontrolu baslatir. Baslatildiysa True.

        Sonucun ne anlama geldigine ve seridin gosterilip gosterilmeyecegine
        TEK yerde karar verilir (apply_update_result). Ayarlar ekrani sonucu
        yalnizca yaziya dokmek icin `on_done` verir.
        """
        def handle(release) -> None:
            status = self.apply_update_result(release, force=force)
            if on_done is not None:
                on_done(status)

        return update.check_async(self.conn, self, handle, force=force)

    def apply_update_result(self, release, *, force: bool = False) -> tuple[str, str]:
        """Sonucu isler ve (mesaj, renk anahtari) dondurur.

        Serit burada gosterilir; kurali `update.should_notify` belirler.
        """
        if release is None:
            return ("Kontrol edilemedi — internet bağlantısını kontrol et.", "warn")
        update.mark_checked(self.conn)
        if update.should_notify(self.conn, release, force=force):
            self.update_bar.show(release)
            return (f"Yeni sürüm var: {release.version} — üstteki şeritten indir.",
                    "ok")
        if release.is_newer:
            return (f"Yeni sürüm var: {release.version} (şimdilik gizlendi).", "ok")
        return (f"En güncel sürümü kullanıyorsun ({VERSION}).", "ok")

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
