"""Istatistik ekrani: gunluk grafik, seviye dagilimi, ozet kartlari.

Grafikler harici kutuphane olmadan, dogrudan tkinter Canvas uzerine cizilir.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import stats
from ..stats import LEVELS
from .theme import F_BODY, F_H2, F_SMALL, F_STAT, F_TITLE, level_segments, px, segmented_bar


class StatsView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.conn = app.conn
        self.theme = app.theme
        c = self.theme.c

        # ------------------------------------------------------- ozet kartlari
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 12))
        self.cards: dict[str, tk.Label] = {}
        specs = [
            ("mastered", "Hakim olunan"), ("accuracy", "Doğruluk (son 200)"),
            ("streak", "Günlük seri"), ("today", "Bugün"), ("eta", "Tahmini bitiş"),
        ]
        for key, label in specs:
            box = tk.Frame(top, bg=c["surface"])
            box.pack(side="left", fill="both", expand=True, padx=(0, 8))
            pad = tk.Frame(box, bg=c["surface"])
            pad.pack(padx=18, pady=14, anchor="w")
            tk.Label(pad, text=label, bg=c["surface"], fg=c["text_dim"],
                     font=F_SMALL).pack(anchor="w")
            value = tk.Label(pad, text="—", bg=c["surface"], fg=c["text"],
                             font=F_STAT)
            value.pack(anchor="w")
            self.cards[key] = value

        # ------------------------------------------------------- gunluk grafik
        chart_box = tk.Frame(self, bg=c["surface"])
        chart_box.pack(fill="both", expand=True)
        pad = tk.Frame(chart_box, bg=c["surface"])
        pad.pack(fill="both", expand=True, padx=24, pady=20)

        head = tk.Frame(pad, bg=c["surface"])
        head.pack(fill="x")
        tk.Label(head, text="Son 30 gün", bg=c["surface"], fg=c["text"],
                 font=F_H2).pack(side="left")
        self.chart_legend = tk.Label(head, text="", bg=c["surface"],
                                     fg=c["text_dim"], font=F_SMALL)
        self.chart_legend.pack(side="right")

        self.chart = tk.Canvas(pad, bg=c["surface"], highlightthickness=0,
                               height=px(230))
        self.chart.pack(fill="both", expand=True, pady=(12, 0))
        self.chart.bind("<Configure>", lambda _e: self.draw_chart())

        # ------------------------------------------------------- seviye tablosu
        level_box = tk.Frame(self, bg=c["surface"])
        level_box.pack(fill="x", pady=(12, 0))
        lpad = tk.Frame(level_box, bg=c["surface"])
        lpad.pack(fill="x", padx=24, pady=18)
        tk.Label(lpad, text="CEFR seviyelerine göre ilerleme", bg=c["surface"],
                 fg=c["text"], font=F_H2).pack(anchor="w", pady=(0, 10))
        self.level_rows: dict[str, tuple[tk.Canvas, tk.Label]] = {}
        for level in LEVELS:
            row = tk.Frame(lpad, bg=c["surface"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=level, bg=c["surface"], fg=c["text"], font=F_BODY,
                     width=4, anchor="w").pack(side="left")
            bar = tk.Canvas(row, height=px(13), bg=c["surface_alt"], highlightthickness=0)
            bar.pack(side="left", fill="x", expand=True, padx=10)
            bar.bind("<Configure>", lambda _e: self.draw_levels())
            lbl = tk.Label(row, text="", bg=c["surface"], fg=c["text_dim"],
                           font=F_SMALL, width=26, anchor="e")
            lbl.pack(side="right")
            self.level_rows[level] = (bar, lbl)

    # ------------------------------------------------------------------ yenile
    def on_show(self) -> None:
        c = self.theme.c
        ov = stats.overview(self.conn)
        cards_today, _correct, goal = stats.today_progress(self.conn)

        self.cards["mastered"].config(text=f"{ov.mastered}/{ov.total}")
        self.cards["accuracy"].config(text=f"%{stats.accuracy(self.conn)*100:.0f}")
        self.cards["streak"].config(text=f"{stats.streak_days(self.conn)} gün")
        self.cards["today"].config(text=f"{cards_today}/{goal}")
        self.cards["eta"].config(text=stats.eta(self.conn))

        self.update_idletasks()
        self.draw_chart()

        self.draw_levels()

    def draw_levels(self) -> None:
        """Seviye cubuklari - widget yerlestikce yeniden cizilir."""
        c = self.theme.c
        levels = stats.by_level(self.conn)
        for level in LEVELS:
            bar, lbl = self.level_rows[level]
            data = levels.get(level, {"total": 0, "mastered": 0, "learning": 0})
            total = data["total"] or 1
            segmented_bar(bar, level_segments(data, total, c),
                          bg=c["surface_alt"])
            pct = 100 * data["mastered"] / total
            lbl.config(text=f"{data['mastered']}/{data['total']}  ·  %{pct:.0f}")

    def draw_chart(self) -> None:
        c = self.theme.c
        canvas = self.chart
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        if width < 50 or height < 40:
            return

        series = stats.daily_series(self.conn, 30)
        peak = max((cards for _d, cards, _ok in series), default=0)
        goal = stats.today_progress(self.conn)[2]
        top = max(peak, goal, 1)

        left_pad, bottom_pad, top_pad = 34, 24, 12
        plot_w = width - left_pad - 8
        plot_h = height - bottom_pad - top_pad

        # yatay kilavuz cizgileri
        for i in range(4):
            y = top_pad + plot_h * i / 3
            value = int(top * (3 - i) / 3)
            canvas.create_line(left_pad, y, width - 8, y, fill=c["border"])
            canvas.create_text(left_pad - 6, y, text=str(value), anchor="e",
                               fill=c["text_dim"], font=F_SMALL)

        # gunluk hedef cizgisi
        if goal and goal <= top:
            gy = top_pad + plot_h * (1 - goal / top)
            canvas.create_line(left_pad, gy, width - 8, gy, fill=c["accent"],
                               dash=(4, 3))

        slot = plot_w / max(len(series), 1)
        bar_w = max(slot * 0.62, 2)
        for i, (day, cards, correct) in enumerate(series):
            if cards <= 0:
                continue
            x = left_pad + slot * i + (slot - bar_w) / 2
            h_total = plot_h * cards / top
            h_ok = plot_h * correct / top
            y0 = top_pad + plot_h
            canvas.create_rectangle(x, y0 - h_total, x + bar_w, y0,
                                    fill=c["surface_alt"], outline="")
            canvas.create_rectangle(x, y0 - h_ok, x + bar_w, y0,
                                    fill=c["ok"], outline="")
            if i % 5 == 0 or i == len(series) - 1:
                canvas.create_text(x + bar_w / 2, y0 + 12, text=day[5:],
                                   fill=c["text_dim"], font=F_SMALL)

        total_cards = sum(cards for _d, cards, _ok in series)
        active_days = sum(1 for _d, cards, _ok in series if cards)
        self.chart_legend.config(
            text=f"■ doğru   □ toplam   ·   30 günde {total_cards} kart / "
                 f"{active_days} aktif gün   ·   - - - günlük hedef"
        )
