"""Calisma ekrani: tek tek kart + aninda geri bildirim.

Akis
----
    kelime goster  ->  cevap yaz  ->  Enter  ->  aninda dogru/yanlis
                                                  +  seri durumu
                                                  +  ornek cumle / tanim
                            Enter  ->  sonraki kart

Yon: EN->TR (kelimeyi gor, Turkcesini yaz) veya TR->EN (Turkcesini gor,
Ingilizcesini yaz) veya Karisik. Alt bardaki dugme ile aninda degistirilir;
ilerleme tektir, yon sadece sorunun bicimini degistirir.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import db, tts
from ..engine import Card, Engine, Outcome
from ..matching import VERDICT_NOT_ACCEPTED, VERDICT_TYPO
from .theme import F_BODY, F_H2, F_INPUT, F_SMALL, F_TITLE, F_WORD

CEFR_HINT = {"A1": "başlangıç", "A2": "temel", "B1": "orta", "B2": "orta-üstü"}
DIRECTION_LABEL = {db.EN_TR: "EN → TR", db.TR_EN: "TR → EN", db.MIXED: "Karışık"}
DIRECTION_CYCLE = [db.EN_TR, db.TR_EN, db.MIXED]


class QuizView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.conn = app.conn
        self.theme = app.theme
        self.engine: Engine | None = None
        self.card: Card | None = None
        self.awaiting_next = False
        c = self.theme.c

        # ------------------------------------------------------------- kart
        self.card_frame = tk.Frame(self, bg=c["surface"], highlightthickness=2,
                                   highlightbackground=c["surface"])
        self.card_frame.pack(fill="both", expand=True)

        inner = tk.Frame(self.card_frame, bg=c["surface"])
        inner.place(relx=0.5, rely=0.44, anchor="center")
        self.inner = inner

        # ust satir: tur rozeti + seri gostergesi
        top = tk.Frame(inner, bg=c["surface"])
        top.pack(pady=(0, 6))
        self.badge = tk.Label(top, text="", bg=c["surface"], fg=c["text_dim"],
                              font=F_SMALL)
        self.badge.pack(side="left", padx=6)
        self.streak_lbl = tk.Label(top, text="", bg=c["surface"], fg=c["text_dim"],
                                   font=F_SMALL)
        self.streak_lbl.pack(side="left", padx=6)

        # kelime
        word_row = tk.Frame(inner, bg=c["surface"])
        word_row.pack()
        self.word_lbl = tk.Label(word_row, text="", bg=c["surface"], fg=c["text"],
                                 font=F_WORD)
        self.word_lbl.pack(side="left")
        self.audio_btn = tk.Label(word_row, text=" 🔊", bg=c["surface"],
                                  fg=c["text_dim"], font=("Segoe UI", 20),
                                  cursor="hand2")
        self.audio_btn.pack(side="left", padx=(10, 0))
        self.audio_btn.bind("<Button-1>", lambda _e: self.play_audio())

        self.prompt = tk.Label(inner, text="Türkçe karşılığı?", bg=c["surface"],
                               fg=c["text_dim"], font=F_BODY)
        self.prompt.pack(pady=(2, 14))

        # cevap kutusu
        self.answer = tk.StringVar()
        self.entry = tk.Entry(inner, textvariable=self.answer, font=F_INPUT,
                              bg=c["surface_alt"], fg=c["text"],
                              insertbackground=c["accent"], relief="flat",
                              justify="center", width=26,
                              disabledbackground=c["surface_alt"],
                              disabledforeground=c["text"])
        self.entry.pack(ipady=10)
        # DIKKAT: Enter'i buraya AYRICA baglama. Tk once widget bagini, sonra
        # "all" bagini calistirir; ikisi birden olursa tek basista on_enter iki
        # kez calisir (cevabi gonderir, ardindan sonraki karta bos cevap yazip
        # kutuyu kilitler). Enter yalnizca asagidaki bind_all ile yonetiliyor.
        self.underline = tk.Frame(inner, bg=c["border"], height=2)
        self.underline.pack(fill="x", pady=(0, 10))

        # geri bildirim alani
        self.feedback = tk.Label(inner, text="", bg=c["surface"], fg=c["text"],
                                 font=F_H2, wraplength=680, justify="center")
        self.feedback.pack(pady=(6, 2))
        self.detail = tk.Label(inner, text="", bg=c["surface"], fg=c["text_dim"],
                               font=F_BODY, wraplength=680, justify="center")
        self.detail.pack(pady=(0, 4))
        # Dilbilgisi kelimeleri icin Turkce aciklama ("would" = ?). Ornek
        # cumlenin ustunde, vurgulu renkte durur.
        self.note = tk.Label(inner, text="", bg=c["surface"], fg=c["accent"],
                             font=F_BODY, wraplength=780, justify="center")
        self.note.pack(pady=(4, 0))

        self.example = tk.Label(inner, text="", bg=c["surface"], fg=c["text_dim"],
                                font=(F_BODY[0], 10), wraplength=760,
                                justify="center")
        self.example.pack()

        self.hintbar = tk.Label(inner, text="", bg=c["surface"], fg=c["text_dim"],
                                font=F_SMALL)
        self.hintbar.pack(pady=(14, 0))

        # ---------------------------------------------------------- alt bar
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(10, 0))
        self.session_lbl = ttk.Label(bottom, text="", style="Dim.TLabel")
        self.session_lbl.pack(side="left")
        ttk.Button(bottom, text="Bilmiyorum  (Esc)", style="Ghost.TButton",
                   command=self.skip).pack(side="right")
        # "Bunu da dogru say": haksiz reddedildigini dusundugu cevabi isaretler.
        # Kart icinde degil alt barda duruyor ki kartin yuksekligi degismesin.
        self.accept_btn = ttk.Button(
            bottom, text="✓  BİLİYORDUM, doğru say  (Ctrl+K)",
            style="Accept.TButton", command=self.accept_my_answer,
        )
        ttk.Button(bottom, text="Oturumu bitir", style="Ghost.TButton",
                   command=self.stop_session).pack(side="right", padx=(0, 8))
        # Yon: ayni destenin obur yuzu. Ayarlara gitmeden buradan cevrilir.
        self.dir_btn = ttk.Button(bottom, text="", style="Ghost.TButton",
                                  command=self.switch_direction)
        self.dir_btn.pack(side="right", padx=(0, 8))
        self._refresh_dir_button()

        # Cevap kutusu geri bildirim sirasinda kilitlenir; Enter'i pencere
        # duzeyinde yakalayarak "sonraki kart" akisini sorunsuz tutuyoruz.
        self.bind_all("<Return>", self._global_enter)
        self.bind_all("<Escape>", self._escape)
        self.bind_all("<Control-k>", self._accept_shortcut)
        self.bind_all("<Control-K>", self._accept_shortcut)

        self._last_answer = ""
        self.teach_mode = False   # 'dogru cevabi bir kez yaz' adimi

    # ------------------------------------------------------------ oturum
    def on_show(self) -> None:
        if self.engine is None:
            self.engine = Engine(self.conn)
        if self.card is None:
            self.next_card()
        self.entry.focus_set()

    def stop_session(self) -> None:
        if self.engine is not None:
            self.engine.finish()
            self.engine = None
            self.card = None
        self.app.refresh_status()

    @property
    def direction(self) -> str:
        if self.engine is not None:
            return self.engine.direction
        return db.get_setting(self.conn, "direction", db.EN_TR)

    @property
    def reverse(self) -> bool:
        """Ekrandaki KARTIN yonu (karisik modda kart basina degisir)."""
        if self.card is not None:
            return self.card.reverse
        return self.direction == db.TR_EN

    def _refresh_dir_button(self) -> None:
        self.dir_btn.config(text=f"↔  Yön: {DIRECTION_LABEL.get(self.direction, '?')}")

    def switch_direction(self) -> None:
        """Calisma yonunu cevirir (EN→TR → TR→EN → Karisik); oturumu yeniler."""
        cur = self.direction
        idx = DIRECTION_CYCLE.index(cur) if cur in DIRECTION_CYCLE else 0
        new = DIRECTION_CYCLE[(idx + 1) % len(DIRECTION_CYCLE)]
        self.stop_session()
        db.set_setting(self.conn, "direction", new)
        self._refresh_dir_button()
        self.engine = Engine(self.conn)
        self.next_card()
        self.entry.focus_set()

    def _escape(self, _event=None):
        if self.app._current != "quiz":
            return
        if self.teach_mode:
            self._end_teach(ok=False)
        elif not self.awaiting_next:
            self.skip()

    def _global_enter(self, _event=None):
        """Yalnizca calisma ekrani acikken Enter'i isle."""
        if self.app._current == "quiz":
            self.on_enter()
            return "break"
        return None

    def _accept_shortcut(self, _event=None):
        if self.app._current == "quiz":
            self.accept_my_answer()
            return "break"
        return None

    def _show_accept_button(self) -> None:
        """Yazilmis bir cevap varsa 'bunu da dogru say' butonunu gosterir."""
        if self._last_answer:
            self.accept_btn.pack(side="right", padx=(0, 8))
        else:
            self.accept_btn.pack_forget()

    # -------------------------------------------------- "bunu da dogru say"
    def accept_my_answer(self) -> None:
        """Kullanicinin yazdigi cevabi kalici olarak kabul listesine ekler.

        Cezayi da geri alir: seri, durum ve sayaclar cevaptan onceki haline
        doner, sonra cevap dogru olarak yeniden islenir.
        """
        if self.card is None or self.engine is None or not self._last_answer:
            return
        # "Yazarak pekistir" adimindayken de basilabilir; o adimi kapat, yoksa
        # Enter sonraki karta gecmez.
        self.teach_mode = False
        card, answer = self.card, self._last_answer
        outcome = self.engine.accept_answer(card, answer)
        if outcome is None:
            return
        self._render_feedback(outcome)
        self.feedback.config(
            text=f"✓  {card.display or card.word} artık BİLİNENLER listesinde",
            fg=self.theme.c["ok"],
        )
        self.detail.config(
            text=f"“{answer}” bu kelime için kalıcı olarak doğru sayılacak.\n"
                 "Ceza geri alındı, kelime bir daha sorulmayacak."
        )
        self.hintbar.config(
            text="Elle onayladıkların: Kelimeler → 'Elle onayladıklarım'  ·  devam: Enter"
        )
        self.accept_btn.pack_forget()
        self.app.refresh_status()

    # ------------------------------------------------------------ kartlar
    def next_card(self) -> None:
        c = self.theme.c
        self.awaiting_next = False
        self.card = self.engine.next_card() if self.engine else None
        if self.card is None:
            self._show_finished()
            return

        card = self.card
        self.card_frame.config(highlightbackground=c["surface"])
        self.word_lbl.config(text=self.engine.prompt_text(card), fg=c["text"])
        if self.reverse:
            extra = self.engine.prompt_extra(card)
            self.prompt.config(
                text="İngilizcesi?" + (f"   (ayrıca: {' · '.join(extra)})" if extra else "")
            )
            self.audio_btn.pack_forget()      # sesi duymak cevabi ele verir
        else:
            self.prompt.config(text="Türkçe karşılığı?")
            self.audio_btn.pack(side="left", padx=(10, 0))
        badge = f"{card.cefr} · {CEFR_HINT.get(card.cefr, '')}"
        if self.engine.direction == db.MIXED:
            badge += f"  ·  {DIRECTION_LABEL[card.direction]}"
        self.badge.config(text=badge)
        if card.is_new:
            self.streak_lbl.config(text="🆕  yeni kelime", fg=c["accent"])
        elif card.state == db.LEARNING:
            target = self.engine.target_streak
            gaps = self.engine.gaps
            step = min(max(card.gap_idx, 0), len(gaps) - 1)
            self.streak_lbl.config(
                text=f"🔁  {card.shows}. tekrar  ·  seri {card.streak}/{target}"
                     f"  ·  bilirsen {gaps[step]} kart sonra yine sorulacak",
                fg=c["learning"],
            )
        elif card.state == db.KNOWN:
            self.streak_lbl.config(text="🔎  teyit — hâlâ biliyor musun?",
                                   fg=c["accent"])
        else:
            self.streak_lbl.config(text="")

        self.answer.set("")
        self.entry.config(state="normal", fg=c["text"])
        self.entry.focus_set()
        self.underline.config(bg=c["border"])
        for widget in (self.feedback, self.detail, self.example, self.note):
            widget.config(text="")
        self.accept_btn.pack_forget()
        self._last_answer = ""
        self.teach_mode = False
        self.hintbar.config(text="Cevabı yaz ve Enter'a bas  ·  bilmiyorsan Esc")
        self._update_session_label()

        if (not self.reverse and db.get_int(self.conn, "audio", 1) == 1
                and tts.is_cached(card.display or card.word)):
            tts.speak(card.display or card.word)

    def _show_finished(self) -> None:
        c = self.theme.c
        self.word_lbl.config(text="🎉", fg=c["ok"])
        self.prompt.config(text="Bu turda gösterilecek kelime kalmadı.")
        self.entry.config(state="disabled")
        self.feedback.config(text="Havuz tükendi veya tüm kelimeler beklemede.",
                             fg=c["text"])
        self.detail.config(text="Yarın tekrar gel — tekrarı gelen kelimeler açılacak.")
        self.hintbar.config(text="")

    def play_audio(self) -> None:
        if self.card:
            tts.speak(self.card.display or self.card.word)

    # ------------------------------------------------------------ cevaplama
    def on_enter(self, _event=None) -> None:
        if self.teach_mode:
            self._check_teach(self.answer.get())
        elif self.awaiting_next:
            self.next_card()
        else:
            self.submit(self.answer.get())

    # ------------------------------------------------- "yazarak pekistir" adimi
    def _start_teach(self) -> None:
        """Yeni bir kelimeyi bilemedi: cevabi bir kez yazdirarak pekistir.

        Sozlukten ezberlerken once kelimeye BAKIP OKUMAK gibi - test etmeden
        once ogrenme ani. Bu adim olmadan kelime sadece 'yanlis' olarak gecip
        gidiyordu.
        """
        self.teach_mode = True
        self.awaiting_next = False
        self.entry.config(state="normal")
        self.answer.set("")
        self.entry.focus_set()
        self.hintbar.config(
            text="✍  Öğrenmek için doğru cevabı bir kez yaz  ·  atla: Esc"
        )

    def _check_teach(self, typed: str) -> None:
        card = self.card
        if card is None:
            return
        result = self.engine.peek(card, typed) if self.engine else None
        if result is not None and result.is_correct:
            self._end_teach(ok=True)
        else:
            self.hintbar.config(
                text=f"✍  Aynen yaz:  {self.engine.answer_text(card)}   ·  atla: Esc"
            )
            self.entry.select_range(0, "end")

    def _end_teach(self, ok: bool) -> None:
        c = self.theme.c
        self.teach_mode = False
        self.awaiting_next = True
        self.entry.config(state="disabled")
        if ok:
            self.feedback.config(text="✍  Pekiştirildi — birazdan tekrar soracağım",
                                 fg=c["accent"])
        self.hintbar.config(text="Devam etmek için Enter")

    def skip(self) -> None:
        if not self.awaiting_next and self.card:
            self.submit("")

    def submit(self, answer: str) -> None:
        if self.card is None or self.engine is None:
            return
        # Uzak anlam yazildiysa kelime biliniyor demektir; cezalandirmak yerine
        # ana anlami sorup cezasiz tekrar hakki veriyoruz.
        self._last_answer = answer.strip()
        preview = self.engine.peek(self.card, answer)
        if preview.verdict == VERDICT_NOT_ACCEPTED:
            self._render_retry(preview)
            return
        outcome = self.engine.submit(self.card, answer)
        self._render_feedback(outcome)
        self.app.refresh_status()

    def _render_retry(self, result) -> None:
        """Cezasiz tekrar: kayit tutulmaz, seri dusmez, kart degismez."""
        c = self.theme.c
        self.card_frame.config(highlightbackground=c["warn"])
        self.underline.config(bg=c["warn"])
        self.feedback.config(text="🔸  Doğru yoldasın — ama ana anlamını istiyorum",
                             fg=c["warn"])
        self.detail.config(
            text=f"“{result.matched}” bu kelimenin daha uzak bir anlamı.\n"
                 "Ceza yok, seri düşmedi — tekrar dene."
        )
        self.example.config(text="")
        self.note.config(text="")
        self.hintbar.config(text="Yeni cevabını yaz ve Enter'a bas  ·  "
                                 "bilmiyorsan Esc")
        self.teach_mode = False
        self._show_accept_button()
        self.entry.select_range(0, "end")
        self.entry.focus_set()

    def _render_feedback(self, out: Outcome) -> None:
        c = self.theme.c
        card = self.card
        self.awaiting_next = True
        self.teach_mode = False
        self.entry.config(state="disabled")

        if out.correct:
            color = c["warn"] if out.result.verdict == VERDICT_TYPO else c["ok"]
            head = "✅  Doğru!" if out.result.verdict != VERDICT_TYPO else "⚠️  Neredeyse!"
            if out.promoted == "known":
                head = "🌟  Tek seferde bildin — artık bilinen kelimeler listesinde!"
            elif out.promoted == "learned":
                head = "🏆  20'lik seriyi tamamladın — bu kelime artık öğrenildi!"
        else:
            color = c["bad"]
            head = "❌  Yanlış"
            if out.result.verdict == VERDICT_NOT_ACCEPTED:
                head = "🔸  Kabul edilmedi"

        self.card_frame.config(highlightbackground=color)
        self.underline.config(bg=color)
        self.feedback.config(text=head, fg=color)

        # dogru cevap(lar) ve seri bilgisi
        lines = []
        if not out.correct or out.result.verdict == VERDICT_TYPO:
            if self.reverse:
                lines.append(f"{self.engine.prompt_text(card)}  =  "
                             f"{card.display or card.word}")
            else:
                lines.append(f"{card.display or card.word}  =  "
                             f"{'  ·  '.join(card.accepted)}")
        elif self.reverse:
            # Ters yonde dogru bilince de kelimeyi bir kez daha gor
            lines.append(f"{card.display or card.word}  =  "
                         f"{'  ·  '.join(card.accepted[:3])}")
        # Ingiliz yazimi olan kelimelerde Amerikan karsiligini goster; aksi halde
        # 'mum = anne' veri hatasi gibi gorunuyor.
        if card.other_form:
            label = ("İngiliz İngilizcesinde" if card.display == card.us_form
                     else "Amerikan İngilizcesinde")
            lines.append(f"{label}: {card.other_form}")
        if out.result.hint:
            lines.append(out.result.hint)

        if out.state_after == db.LEARNING:
            if out.correct and not out.counted:
                lines.append(
                    f"Seri {out.streak}/{out.target_streak} — bu tekrar seriye "
                    f"sayılmadı (aynı oturumda en fazla "
                    f"{self.engine.hit_cap} kez sayılır). Yarın devam."
                )
            elif out.correct:
                lines.append(f"Seri {out.streak}/{out.target_streak} ✔")
            elif out.reset:
                lines.append(f"Seri geri düştü: {out.streak}/{out.target_streak}")
            else:
                lines.append(
                    f"Bu kelime artık tekrar listesinde — "
                    f"seri {out.streak}/{out.target_streak}"
                )
        self.detail.config(text="\n".join(lines))

        # Kart yuksekligi sabit kalsin diye en fazla iki satir ek bilgi gosterilir;
        # tamami "Kelimeler" ekranindaki detay panelinde zaten var.
        self.note.config(text=f"ℹ  {card.note}" if card.note else "")

        extra = []
        if card.example:
            line = f"💬  {card.example}"
            if card.example_tr:
                line += f"\n      {card.example_tr}"
            extra.append(line)
        if card.alternatives:
            extra.append("Diğer anlamları: " + ", ".join(card.alternatives[:4]))
        elif card.definition:
            extra.append(card.definition)
        self.example.config(text="\n".join(extra[:2]))

        # Haksiz reddedildigini dusunuyorsa isaretleyebilsin
        if not out.correct:
            self._show_accept_button()
        else:
            self.accept_btn.pack_forget()

        if out.correct:
            self.hintbar.config(text="Devam etmek için Enter")
        else:
            self.hintbar.config(
                text="Devam: Enter          "
                     "Cevabın aslında doğru mu?  →  Ctrl+K  (bilinenlere taşır)"
            )
        self._update_session_label()
        if db.get_int(self.conn, "audio", 1) == 1:
            tts.speak(card.display or card.word)

        # Yeni bir kelimeyi bilemedi: gecip gitmesin, bir kez yazarak pekistir.
        # ("Sozlukte 1'e bakip okumak" adimi - test etmeden once ogrenme ani.)
        if (not out.correct and out.state_before == db.POOL
                and db.get_int(self.conn, "teach_on_miss", 1) == 1):
            self._start_teach()

    def _update_session_label(self) -> None:
        if self.engine is None:
            return
        row = self.conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(correct),0) c FROM reviews "
            "WHERE session_id = ?", (self.engine.session_id,)
        ).fetchone()
        n, correct = row["n"], row["c"]
        rate = f"  ·  %{100*correct/n:.0f} doğru" if n else ""
        left = self.engine.peek_group_size()
        self.session_lbl.config(
            text=f"Bu oturum: {n} kart{rate}   ·   turda kalan: {left}"
        )
