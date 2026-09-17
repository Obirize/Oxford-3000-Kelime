"""Ana ekran: gunluk hedef, seviye ozeti, zorlanilan kelimeler, hizli baslat."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import stats
from ..stats import LEVELS
from .theme import F_BODY, F_H2, F_SMALL, F_STAT, F_TITLE


class DashboardView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.conn = app.conn
        self.theme = app.theme
        c = self.theme.c

        # --------------------------------------------------- sol: baslat + hedef
        left = tk.Frame(self, bg=c["surface"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        pad = tk.Frame(left, bg=c["surface"])
        pad.pack(fill="both", expand=True, padx=28, pady=26)

        tk.Label(pad, text="Bugün ne kadar yol aldın?", bg=c["surface"],
                 fg=c["text"], font=F_TITLE).pack(anchor="w")

        self.goal_lbl = tk.Label(pad, text="", bg=c["surface"], fg=c["text_dim"],
                                 font=F_BODY)
        self.goal_lbl.pack(anchor="w", pady=(4, 12))

        self.goal_bar = tk.Canvas(pad, height=14, bg=c["surface_alt"],
                                  highlightthickness=0)
        self.goal_bar.pack(fill="x")
        # Cubuklar ilk cizimde henuz yerlesmemis olabilir (genislik 1 px);
        # yerlesim degistikce yeniden ciz.
        self.goal_bar.bind("<Configure>", lambda _e: self._draw_goal())

        self.streak_lbl = tk.Label(pad, text="", bg=c["surface"], fg=c["text"],
                                   font=F_H2)
        self.streak_lbl.pack(anchor="w", pady=(18, 0))

        ttk.Button(pad, text="▶  Çalışmaya Başla", style="Accent.TButton",
                   command=lambda: app.show("quiz")).pack(anchor="w", pady=(24, 0))

        tk.Label(pad, text="Klavye: Enter = cevapla / devam  ·  Esc = bilmiyorum",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL).pack(
                     anchor="w", pady=(10, 0))

        self.eta_lbl = tk.Label(pad, text="", bg=c["surface"], fg=c["text_dim"],
                                font=F_SMALL)
        self.eta_lbl.pack(anchor="w", pady=(18, 0))

        # ------------------------------------------------ sag: seviye + zorlar
        right = tk.Frame(self, bg=c["surface"], width=420)
        right.pack(side="right", fill="both", padx=(8, 0))
        right.pack_propagate(False)

        rpad = tk.Frame(right, bg=c["surface"])
        rpad.pack(fill="both", expand=True, padx=24, pady=26)

        tk.Label(rpad, text="Seviye dağılımı", bg=c["surface"], fg=c["text"],
                 font=F_H2).pack(anchor="w", pady=(0, 12))
        self.level_rows: dict[str, tuple[tk.Canvas, tk.Label]] = {}
        for level in LEVELS:
            row = tk.Frame(rpad, bg=c["surface"])
            row.pack(fill="x", pady=4)
            tk.Label(row, text=level, bg=c["surface"], fg=c["text_dim"],
                     font=F_SMALL, width=3, anchor="w").pack(side="left")
            bar = tk.Canvas(row, height=9, bg=c["surface_alt"], highlightthickness=0)
            bar.pack(side="left", fill="x", expand=True, padx=8)
            bar.bind("<Configure>", lambda _e: self._draw_levels())
            lbl = tk.Label(row, text="", bg=c["surface"], fg=c["text_dim"],
                           font=F_SMALL, width=11, anchor="e")
            lbl.pack(side="right")
            self.level_rows[level] = (bar, lbl)

        tk.Label(rpad, text="En çok zorlandıkların", bg=c["surface"], fg=c["text"],
                 font=F_H2).pack(anchor="w", pady=(24, 8))
        self.hard_box = tk.Frame(rpad, bg=c["surface"])
        self.hard_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ cizim
    def _draw_goal(self) -> None:
        c = self.theme.c
        cards, _correct, goal = stats.today_progress(self.conn)
        width = max(self.goal_bar.winfo_width(), 1)
        self.goal_bar.delete("all")
        self.goal_bar.create_rectangle(0, 0, width, 14, fill=c["surface_alt"],
                                       outline="")
        filled = min(cards / goal, 1.0) if goal else 0
        if filled > 0:
            color = c["ok"] if filled >= 1 else c["accent"]
            self.goal_bar.create_rectangle(0, 0, width * filled, 14, fill=color,
                                           outline="")

    def _draw_levels(self) -> None:
        c = self.theme.c
        levels = stats.by_level(self.conn)
        for level in LEVELS:
            bar, lbl = self.level_rows[level]
            data = levels.get(level, {"total": 0, "mastered": 0, "learning": 0})
            total = data["total"] or 1
            w = max(bar.winfo_width(), 1)
            bar.delete("all")
            bar.create_rectangle(0, 0, w, 9, fill=c["surface_alt"], outline="")
            x = w * data["mastered"] / total
            bar.create_rectangle(0, 0, x, 9, fill=c["known"], outline="")
            bar.create_rectangle(x, 0, x + w * data["learning"] / total, 9,
                                 fill=c["learning"], outline="")
            lbl.config(text=f"{data['mastered']}/{data['total']}")

    # ------------------------------------------------------------------ yenile
    def on_show(self) -> None:
        c = self.theme.c
        cards, _correct, goal = stats.today_progress(self.conn)
        self.goal_lbl.config(text=f"{cards} / {goal} kart")
        self.update_idletasks()
        self._draw_goal()

        days = stats.streak_days(self.conn)
        if cards >= goal and goal:
            msg = f"🔥 {days} günlük seri  ·  bugünkü hedef tamam!"
        elif days:
            msg = f"🔥 {days} günlük seri  ·  {max(goal - cards, 0)} kart kaldı"
        else:
            msg = "Henüz seri yok — bugün başlat!"
        self.streak_lbl.config(text=msg)
        self.eta_lbl.config(text=f"Bu tempoyla tahmini bitiş: {stats.eta(self.conn)}")

        self._draw_levels()

        for child in self.hard_box.winfo_children():
            child.destroy()
        hard = stats.hardest_words(self.conn, 7)
        if not hard:
            tk.Label(self.hard_box, text="Henüz zorlandığın kelime yok.",
                     bg=c["surface"], fg=c["text_dim"], font=F_SMALL).pack(anchor="w")
        for item in hard:
            row = tk.Frame(self.hard_box, bg=c["surface"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=item["word"], bg=c["surface"], fg=c["text"],
                     font=F_BODY, anchor="w", width=15).pack(side="left")
            tk.Label(row, text=item["primary_tr"], bg=c["surface"],
                     fg=c["text_dim"], font=F_SMALL, anchor="w").pack(side="left")
            tk.Label(row, text=f"{item['wrong']}✗  seri {item['streak']}",
                     bg=c["surface"], fg=c["bad"], font=F_SMALL,
                     anchor="e").pack(side="right")
