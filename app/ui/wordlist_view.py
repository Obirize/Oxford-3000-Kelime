"""Kelime listeleri: arama, duruma/seviyeye gore filtre, detay paneli."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

from .. import db, tts
from ..stats import LEVELS
from .theme import F_BODY, F_H2, F_SMALL, F_TITLE, px

STATE_LABEL = {
    db.KNOWN: "Biliniyor",
    db.LEARNED: "Öğrenildi",
    db.LEARNING: "Öğreniliyor",
    db.POOL: "Havuzda",
}
FILTERS = ["Tümü", "Biliniyor", "Öğrenildi", "Öğreniliyor", "Havuzda",
           "İnatçılar", "Elle onayladıklarım"]


class WordListView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.conn = app.conn
        self.theme = app.theme
        c = self.theme.c

        # ------------------------------------------------------------ filtreler
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 10))

        ttk.Label(bar, text="Ara:").pack(side="left")
        self.query = tk.StringVar()
        entry = tk.Entry(bar, textvariable=self.query, font=F_BODY, width=24,
                         bg=c["surface_alt"], fg=c["text"], relief="flat",
                         insertbackground=c["text"])
        entry.pack(side="left", padx=(6, 18), ipady=px(5))
        entry.bind("<KeyRelease>", lambda _e: self.reload())

        ttk.Label(bar, text="Durum:").pack(side="left")
        self.state_var = tk.StringVar(value="Tümü")
        state_box = ttk.Combobox(bar, textvariable=self.state_var, values=FILTERS,
                                 state="readonly", width=13)
        state_box.pack(side="left", padx=(6, 18))
        state_box.bind("<<ComboboxSelected>>", lambda _e: self.reload())

        ttk.Label(bar, text="Seviye:").pack(side="left")
        self.level_var = tk.StringVar(value="Tümü")
        level_box = ttk.Combobox(bar, textvariable=self.level_var,
                                 values=["Tümü", *LEVELS], state="readonly", width=8)
        level_box.pack(side="left", padx=(6, 18))
        level_box.bind("<<ComboboxSelected>>", lambda _e: self.reload())

        self.count_lbl = ttk.Label(bar, text="", style="Dim.TLabel")
        self.count_lbl.pack(side="right")

        # ------------------------------------------------------------ tablo
        split = ttk.Frame(self)
        split.pack(fill="both", expand=True)

        cols = ("word", "tr", "cefr", "state", "streak", "shows", "acc")
        self.tree = ttk.Treeview(split, columns=cols, show="headings", height=20)
        headers = [
            ("word", "Kelime", 150), ("tr", "Türkçe", 260), ("cefr", "Seviye", 60),
            ("state", "Durum", 110), ("streak", "Seri", 70),
            ("shows", "Gösterim", 80), ("acc", "Doğruluk", 80),
        ]
        for key, text, width in headers:
            self.tree.heading(key, text=text,
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width,
                             anchor="w" if key in ("word", "tr") else "center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda _e: self.speak_selected())

        scroll = ttk.Scrollbar(split, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.tag_configure("known", foreground=c["known"])
        self.tree.tag_configure("learned", foreground=c["learned"])
        self.tree.tag_configure("learning", foreground=c["learning"])
        self.tree.tag_configure("pool", foreground=c["text_dim"])

        # ------------------------------------------------------------ detay
        panel = tk.Frame(split, bg=c["surface"], width=330)
        panel.pack(side="right", fill="y", padx=(12, 0))
        panel.pack_propagate(False)
        self.panel = tk.Frame(panel, bg=c["surface"])
        self.panel.pack(fill="both", expand=True, padx=18, pady=18)

        self.d_word = tk.Label(self.panel, text="Bir kelime seç", bg=c["surface"],
                               fg=c["text"], font=F_TITLE, anchor="w")
        self.d_word.pack(anchor="w")
        self.d_meta = tk.Label(self.panel, text="", bg=c["surface"],
                               fg=c["text_dim"], font=F_SMALL, anchor="w")
        self.d_meta.pack(anchor="w", pady=(0, 12))

        ttk.Button(self.panel, text="🔊  Telaffuzu dinle", style="Ghost.TButton",
                   command=self.speak_selected).pack(anchor="w", pady=(0, 12))

        self.d_body = tk.Label(self.panel, text="", bg=c["surface"], fg=c["text"],
                               font=F_BODY, wraplength=px(290), justify="left", anchor="nw")
        self.d_body.pack(anchor="w", fill="both", expand=True)

        self.reset_btn = ttk.Button(self.panel, text="Bu kelimeyi sıfırla",
                                    style="Ghost.TButton", command=self.reset_word)
        self.reset_btn.pack(anchor="w", pady=(12, 0))

        self._sort_key = "word"
        self._sort_desc = False
        self._selected_word = ""
        self._selected_shown = ""

    # ------------------------------------------------------------------ veri
    def on_show(self) -> None:
        self.spelling = db.get_setting(self.conn, "spelling", "us")
        self.reload()

    def _shown(self, row) -> str:
        """Ayara gore ekranda gosterilecek yazim."""
        if row["us_form"] and getattr(self, "spelling", "us") == "us":
            return row["us_form"]
        return row["word"]

    def reload(self) -> None:
        where, params = [], []
        query = self.query.get().strip()
        if query:
            # us_form da aransin: 'mom' yazan kullanici 'mum' kaydini bulmali
            where.append("(LOWER(w.word) LIKE ? OR LOWER(w.us_form) LIKE ? "
                         "OR LOWER(w.primary_tr) LIKE ? OR LOWER(w.accepted) LIKE ?)")
            like = f"%{query.lower()}%"
            params += [like, like, like, like]

        choice = self.state_var.get()
        state_map = {"Biliniyor": db.KNOWN, "Öğrenildi": db.LEARNED,
                     "Öğreniliyor": db.LEARNING, "Havuzda": db.POOL}
        if choice in state_map:
            where.append("p.state = ?")
            params.append(state_map[choice])
        elif choice == "İnatçılar":
            where.append("p.state = ? AND p.shows >= ?")
            params += [db.LEARNING, db.get_int(self.conn, "show_budget", 1000)]
        elif choice == "Elle onayladıklarım":
            # Ctrl+K ile "biliyordum" denip bilinenlere tasinan kelimeler
            where.append("w.id IN (SELECT word_id FROM user_accepted)")

        if self.level_var.get() != "Tümü":
            where.append("w.cefr = ?")
            params.append(self.level_var.get())

        sql = """SELECT w.word, w.primary_tr, w.accepted, w.alternatives, w.cefr,
                        w.definition, w.example, w.example_tr, w.synonyms, w.antonyms,
                        w.collocations, w.us_form, w.note, w.confidence,
                        p.state, p.streak, p.shows, p.correct, p.wrong
                 FROM words w JOIN progress p ON p.word_id = w.id"""
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY w.word LIMIT 4000"

        self.rows = [dict(r) for r in self.conn.execute(sql, params).fetchall()]
        self._fill()

    def _fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            total = row["correct"] + row["wrong"]
            acc = f"%{100*row['correct']/total:.0f}" if total else "—"
            self.tree.insert(
                "", "end", iid=row["word"],
                values=(self._shown(row), ", ".join(json.loads(row["accepted"])[:3]),
                        row["cefr"], STATE_LABEL.get(row["state"], row["state"]),
                        row["streak"] or "—", row["shows"] or "—", acc),
                tags=(row["state"],),
            )
        self.count_lbl.config(text=f"{len(self.rows)} kelime")

    def sort_by(self, key: str) -> None:
        mapping = {"word": "word", "tr": "primary_tr", "cefr": "cefr",
                   "state": "state", "streak": "streak", "shows": "shows"}
        if key == "acc":
            self.rows.sort(
                key=lambda r: (r["correct"] / (r["correct"] + r["wrong"]))
                if (r["correct"] + r["wrong"]) else -1,
                reverse=not self._sort_desc,
            )
        else:
            field = mapping.get(key, "word")
            self.rows.sort(key=lambda r: r[field], reverse=not self._sort_desc)
        self._sort_desc = not self._sort_desc
        self._sort_key = key
        self._fill()

    # ------------------------------------------------------------------ detay
    def on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        word = selection[0]
        row = next((r for r in self.rows if r["word"] == word), None)
        if row is None:
            return
        self._selected_word = word           # DB anahtari (Oxford yazimi)
        self._selected_shown = self._shown(row)   # ekranda gorunen yazim

        self.d_word.config(text=self._selected_shown)
        total = row["correct"] + row["wrong"]
        acc = f"%{100*row['correct']/total:.0f}" if total else "—"
        self.d_meta.config(
            text=f"{row['cefr']}  ·  {STATE_LABEL.get(row['state'])}  ·  "
                 f"seri {row['streak']}  ·  {row['shows']} gösterim  ·  doğruluk {acc}"
        )

        parts = [f"✔ Kabul edilen: {', '.join(json.loads(row['accepted']))}"]
        mine = [r["answer"] for r in self.conn.execute(
            "SELECT answer FROM user_accepted u JOIN words w ON w.id = u.word_id "
            "WHERE w.word = ?", (row["word"],))]
        if mine:
            parts.append("\n★ Senin onayladıkların: " + ", ".join(mine))
        if row["us_form"]:
            showing_us = self._shown(row) == row["us_form"]
            other = row["word"] if showing_us else row["us_form"]
            label = "İngiliz İngilizcesinde" if showing_us else "Amerikan İngilizcesinde"
            parts.append(f"\n{label}: {other}")
        if row["note"]:
            parts.append(f"\nℹ {row['note']}")
        alts = json.loads(row["alternatives"])
        if alts:
            parts.append(f"\n○ Diğer anlamlar (kabul edilmez):\n{', '.join(alts[:8])}")
        if row["definition"]:
            parts.append(f"\n📖 {row['definition']}")
        if row["example"]:
            parts.append(f"\n💬 “{row['example']}”")
            if row["example_tr"]:
                parts.append(f"     {row['example_tr']}")
        if row["synonyms"]:
            parts.append(f"\n≈ Eş anlam: {row['synonyms']}")
        if row["antonyms"]:
            parts.append(f"↔ Zıt anlam: {row['antonyms']}")
        if row["collocations"]:
            parts.append(f"\n🔗 Kalıplar: {row['collocations']}")
        if row["confidence"] < 6:
            parts.append("\n⚠ Bu çevirinin kaynak mutabakatı düşük — "
                         "tools/overrides.json ile düzeltebilirsin.")
        self.d_body.config(text="\n".join(parts))

    def speak_selected(self) -> None:
        if self._selected_word:
            tts.speak(getattr(self, "_selected_shown", "") or self._selected_word)

    def reset_word(self) -> None:
        """Bir kelimeyi havuza geri gonderir (yanlislikla 'biliniyor' olduysa)."""
        if not self._selected_word:
            return
        self.conn.execute(
            """UPDATE progress SET state = ?, streak = 0, shows = 0,
                 correct = 0, wrong = 0, session_hits = 0, settled_at = NULL
               WHERE word_id = (SELECT id FROM words WHERE word = ?)""",
            (db.POOL, self._selected_word),
        )
        self.conn.commit()
        self.reload()
        self.app.refresh_status()
