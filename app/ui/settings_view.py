"""Ayarlar: ogrenme kurallari, tolerans, ses, tema, yedekleme."""

from __future__ import annotations

import os
import shutil
import webbrowser
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import backup, db, tts
from ..version import RELEASES_URL, VERSION
from .theme import F_BODY, F_H2, F_SMALL, F_TITLE, px

SPELLINGS = [
    ("us", "Amerikan İngilizcesi  (mom, color, center, math)  — önerilen"),
    ("uk", "İngiliz İngilizcesi  (mum, colour, centre, maths)  — Oxford aslı"),
]

DIRECTIONS = [
    ("en_tr", "EN → TR   İngilizce kelimeyi gör, Türkçesini yaz   (tanıma)"),
    ("tr_en", "TR → EN   Türkçesini gör, İngilizcesini yaz   (üretim)"),
    ("mixed", "Karışık   Her kart rastgele bir yönde gelir (yarı yarıya)"),
]

RESET_MODES = [
    ("minus5", "Seri 5 azalır  (önerilen — 20'lik seri ~24 oturumda biter)"),
    ("half",   "Seri yarıya düşer  (~23 oturum)"),
    ("full",   "Seri tamamen sıfırlanır  (ilk tasarım — ~54 oturum, çok yavaş)"),
]


class SettingsView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.conn = app.conn
        self.theme = app.theme
        c = self.theme.c

        canvas = tk.Canvas(self, bg=c["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=c["bg"])
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.vars: dict[str, tk.Variable] = {}

        # ------------------------------------------------------ ogrenme kurallari
        box = self._section(body, "Öğrenme kuralları")
        self._number(box, "daily_goal", "Günlük kart hedefi", 10, 500)
        self._number(box, "group_size", "Bir turdaki kelime sayısı", 5, 30)
        self._number(box, "target_streak",
                     "Öğrenildi saymak için üst üste doğru sayısı", 3, 50)
        self._number(box, "session_hit_cap",
                     "Aynı oturumda seriyi en fazla kaç kez artırabilir", 1, 10)
        self._number(box, "gap_cards",
                     "Aynı kelimenin tekrarı arasındaki en az kart sayısı", 3, 100)
        self._number(box, "show_budget",
                     "Bir kelimenin maksimum gösterim bütçesi", 50, 5000)

        self._number(box, "new_per_group",
                     "Her turda en az kaç yeni kelime gelsin", 0, 10)
        self._number(box, "session_show_cap",
                     "Aynı kelime bir oturumda en fazla kaç kez sorulsun", 1, 10)

        row = tk.Frame(box, bg=c["surface"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text="Tekrar merdiveni (kart cinsinden aralıklar)",
                 bg=c["surface"], fg=c["text"], font=F_BODY,
                 anchor="w").pack(side="left")
        self.vars["drill_gaps"] = tk.StringVar(
            value=db.get_setting(self.conn, "drill_gaps", "3,8,20,45,100,250,600"))
        tk.Entry(row, textvariable=self.vars["drill_gaps"], width=24,
                 bg=c["surface_alt"], fg=c["text"], relief="flat",
                 insertbackground=c["text"], justify="right").pack(side="right",
                                                            ipady=px(3))
        tk.Label(box, text="Bilemediğin kelime bu aralıklarla tekrar karşına çıkar: "
                           "3 kart sonra, sonra 8, 20, 45… Her doğru bir üst "
                           "basamağa taşır, her yanlış başa döndürür.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(4, 10))

        self._check(box, "teach_on_miss",
                    "Yeni kelimeyi bilemezsem doğru cevabı bir kez yazdır")
        self._check(box, "confirm_known",
                    "Tek seferde bildiğim kelimeyi ilerde bir kez teyit et")

        tk.Label(box, text="Yanlış cevap verince seriye ne olsun?", bg=c["surface"],
                 fg=c["text"], font=F_BODY).pack(anchor="w", pady=(14, 4))
        self.vars["reset_mode"] = tk.StringVar(
            value=db.get_setting(self.conn, "reset_mode", "minus5")
        )
        for value, label in RESET_MODES:
            tk.Radiobutton(
                box, text=label, value=value, variable=self.vars["reset_mode"],
                bg=c["surface"], fg=c["text"], selectcolor=c["surface_alt"],
                activebackground=c["surface"], activeforeground=c["text"],
                font=F_SMALL, anchor="w", highlightthickness=0, bd=0,
            ).pack(anchor="w", padx=12)

        # ------------------------------------------------------ yon
        box = self._section(body, "Çalışma yönü")
        self.vars["direction"] = tk.StringVar(
            value=db.get_setting(self.conn, "direction", db.EN_TR))
        for value, label in DIRECTIONS:
            tk.Radiobutton(
                box, text=label, value=value, variable=self.vars["direction"],
                bg=c["surface"], fg=c["text"], selectcolor=c["surface_alt"],
                activebackground=c["surface"], activeforeground=c["text"],
                font=F_BODY, anchor="w", highlightthickness=0, bd=0,
            ).pack(anchor="w", padx=12)
        tk.Label(box, text="İlerleme tektir: kelime hangi yönde bilinirse "
                           "bilinsin aynı seri ilerler; yön yalnızca sorunun "
                           "biçimini değiştirir. TR → EN'de aynı Türkçe anlamı "
                           "paylaşan kelimeler (büyük = big/large/great) "
                           "birbirinin yerine kabul edilir. Çalışma ekranındaki "
                           "“↔ Yön” düğmesiyle de anında çevrilir.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(8, 0))

        # ------------------------------------------------------ yazim
        box = self._section(body, "İngilizce yazım biçimi")
        tk.Label(box, text="Oxford 3000 listesi İngiliz yazımını kullanır. "
                           "Kelimeler kartta hangi biçimde gösterilsin?",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(0, 8))
        self.vars["spelling"] = tk.StringVar(
            value=db.get_setting(self.conn, "spelling", "us"))
        for value, label in SPELLINGS:
            tk.Radiobutton(
                box, text=label, value=value, variable=self.vars["spelling"],
                bg=c["surface"], fg=c["text"], selectcolor=c["surface_alt"],
                activebackground=c["surface"], activeforeground=c["text"],
                font=F_BODY, anchor="w", highlightthickness=0, bd=0,
            ).pack(anchor="w", padx=12)
        tk.Label(box, text="Öbür biçim kartta not olarak gösterilir; 27 kelimeyi "
                           "etkiler (mum/mom, colour/color, centre/center…).",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(8, 0))

        # ------------------------------------------------------ cevap toleransi
        box = self._section(body, "Cevap değerlendirme")
        self._check(box, "typo_tolerance",
                    "1 harflik yazım hatasını doğru say (uyarı gösterilir)")
        self._check(box, "fold_turkish",
                    "Türkçe karakter serbestliği — 'sarki' = 'şarkı'")
        tk.Label(box, text="Katı mod her zaman açıktır: yalnızca ana anlam ve yakın "
                           "eş anlamlılar doğru sayılır.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(6, 0))

        # ------------------------------------------------ dogru saydiklarim
        box = self._section(body, "Doğru saydıklarım")
        tk.Label(box, text="Kart ekranında bir cevabın haksız yere reddedildiğini "
                           "düşündüğünde “✓ Bunu da doğru say” (Ctrl+K) dersin. "
                           "O cevap o kelime için kalıcı olarak kabul edilir ve "
                           "burada listelenir.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(0, 10))

        self.flag_list = tk.Listbox(
            box, height=8, bg=c["surface_alt"], fg=c["text"],
            selectbackground=c["accent"], selectforeground="#ffffff",
            relief="flat", highlightthickness=0, font=F_SMALL, activestyle="none",
        )
        self.flag_list.pack(fill="x", pady=(0, 8))

        row = tk.Frame(box, bg=c["surface"])
        row.pack(anchor="w")
        ttk.Button(row, text="Seçileni geri al",
                   command=self.remove_flag).pack(side="left")
        ttk.Button(row, text="Veri setine kalıcı işle",
                   command=self.export_flags).pack(side="left", padx=8)
        self.flag_msg = tk.Label(box, text="", bg=c["surface"], fg=c["ok"],
                                 font=F_SMALL, wraplength=px(620), justify="left")
        self.flag_msg.pack(anchor="w", pady=(8, 0))

        # ------------------------------------------------------ ses
        box = self._section(body, "Telaffuz (Google TTS)")
        self._check(box, "audio", "Kartlarda telaffuzu otomatik seslendir")
        self.cache_lbl = tk.Label(box, text="", bg=c["surface"], fg=c["text_dim"],
                                  font=F_SMALL)
        self.cache_lbl.pack(anchor="w", pady=(8, 4))
        row = tk.Frame(box, bg=c["surface"])
        row.pack(anchor="w")
        ttk.Button(row, text="Tüm sesleri şimdi indir (~24 MB)",
                   command=self.prefetch_audio).pack(side="left")
        ttk.Button(row, text="Test et", style="Ghost.TButton",
                   command=lambda: tts.speak("pronunciation")).pack(side="left",
                                                                   padx=8)
        tk.Label(box, text="İndirilen sesler data/audio/ altında saklanır; "
                           "sonrasında internet gerekmez.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL).pack(
                     anchor="w", pady=(6, 0))

        # ------------------------------------------------------ gorunum + yedek
        box = self._section(body, "Görünüm ve veri")
        tk.Label(box, text="Tema", bg=c["surface"], fg=c["text"],
                 font=F_BODY).pack(anchor="w")
        self.vars["theme"] = tk.StringVar(
            value=db.get_setting(self.conn, "theme", "dark"))
        ttk.Combobox(box, textvariable=self.vars["theme"], values=["dark", "light"],
                     state="readonly", width=10).pack(anchor="w", pady=(4, 12))
        tk.Label(box, text="Tema değişikliği program yeniden başlatıldığında uygulanır.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL).pack(anchor="w")

        row = tk.Frame(box, bg=c["surface"])
        row.pack(anchor="w", pady=(14, 0))
        ttk.Button(row, text="Başka yere kopyala",
                   command=self.backup).pack(side="left")
        ttk.Button(row, text="Dosyadan geri yükle",
                   command=self.restore).pack(side="left", padx=8)
        ttk.Button(row, text="Tüm ilerlemeyi sıfırla", style="Ghost.TButton",
                   command=self.reset_all).pack(side="left", padx=8)

        # ------------------------------------------------------ guncelleme
        box = self._section(body, "Sürüm ve güncelleme")
        tk.Label(box, text=f"Kurulu sürüm:  {VERSION}", bg=c["surface"],
                 fg=c["text"], font=F_BODY).pack(anchor="w", pady=(0, 6))
        self._check(box, "update_check",
                    "Açılışta yeni sürüm var mı diye bak (günde en fazla bir kez)")
        tk.Label(box, text="Kontrol GitHub'ın açık sürüm listesine tek bir istek "
                           "atar; hiçbir kişisel veri veya ilerleme gönderilmez. "
                           "Program kendini güncellemez — yeni sürüm varsa üstte "
                           "bir not çıkar, indirip kurmak sana kalır. "
                           "İlerlemen kurulumda korunur.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(4, 10))
        row = tk.Frame(box, bg=c["surface"])
        row.pack(anchor="w")
        ttk.Button(row, text="Şimdi kontrol et",
                   command=self.check_update_now).pack(side="left")
        ttk.Button(row, text="Sürüm sayfasını aç", style="Ghost.TButton",
                   command=lambda: webbrowser.open(RELEASES_URL)).pack(side="left",
                                                                      padx=8)
        self.update_lbl = tk.Label(box, text="", bg=c["surface"],
                                   fg=c["text_dim"], font=F_SMALL)
        self.update_lbl.pack(anchor="w", pady=(8, 0))

        # ------------------------------------------------------ otomatik yedek
        box = self._section(body, "Otomatik yedekler")
        tk.Label(box, text="Program her açılışta ve her kapanışta ilerlemeni "
                           "otomatik yedekler. Son "
                           f"{backup.KEEP} yedek saklanır. İlerleme dosyası "
                           "silinir veya bozulursa açılışta en yeni sağlam "
                           "yedekten kendiliğinden geri yüklenir.",
                 bg=c["surface"], fg=c["text_dim"], font=F_SMALL,
                 wraplength=px(620), justify="left").pack(anchor="w", pady=(0, 10))

        self.backup_list = tk.Listbox(
            box, height=7, bg=c["surface_alt"], fg=c["text"],
            selectbackground=c["accent"], selectforeground="#ffffff",
            relief="flat", highlightthickness=0, font=F_SMALL, activestyle="none",
        )
        self.backup_list.pack(fill="x", pady=(0, 8))

        row = tk.Frame(box, bg=c["surface"])
        row.pack(anchor="w")
        ttk.Button(row, text="Şimdi yedek al",
                   command=self.backup_now).pack(side="left")
        ttk.Button(row, text="Seçili yedeğe dön",
                   command=self.restore_selected).pack(side="left", padx=8)
        ttk.Button(row, text="Yedek klasörünü aç", style="Ghost.TButton",
                   command=self.open_backup_dir).pack(side="left", padx=8)
        self.backup_msg = tk.Label(box, text="", bg=c["surface"], fg=c["ok"],
                                   font=F_SMALL)
        self.backup_msg.pack(anchor="w", pady=(8, 0))

        # ------------------------------------------------------ kaydet
        save = ttk.Frame(body)
        save.pack(fill="x", pady=18)
        ttk.Button(save, text="💾  Ayarları Kaydet", style="Accent.TButton",
                   command=self.save).pack(side="left")
        self.saved_lbl = ttk.Label(save, text="", style="Dim.TLabel")
        self.saved_lbl.pack(side="left", padx=14)

    # ------------------------------------------------------------ yardimcilar
    def _section(self, parent, title: str) -> tk.Frame:
        c = self.theme.c
        outer = tk.Frame(parent, bg=c["surface"])
        outer.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(outer, bg=c["surface"])
        inner.pack(fill="x", padx=24, pady=18)
        tk.Label(inner, text=title, bg=c["surface"], fg=c["text"],
                 font=F_H2).pack(anchor="w", pady=(0, 10))
        return inner

    def _number(self, parent, key: str, label: str, lo: int, hi: int) -> None:
        c = self.theme.c
        row = tk.Frame(parent, bg=c["surface"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=c["surface"], fg=c["text"], font=F_BODY,
                 anchor="w").pack(side="left")
        var = tk.StringVar(value=db.get_setting(self.conn, key))
        self.vars[key] = var
        spin = ttk.Spinbox(row, from_=lo, to=hi, textvariable=var, width=7)
        spin.pack(side="right")

    def _check(self, parent, key: str, label: str) -> None:
        c = self.theme.c
        var = tk.IntVar(value=db.get_int(self.conn, key, 1))
        self.vars[key] = var
        tk.Checkbutton(parent, text=label, variable=var, bg=c["surface"],
                       fg=c["text"], selectcolor=c["surface_alt"],
                       activebackground=c["surface"], activeforeground=c["text"],
                       font=F_BODY, anchor="w", highlightthickness=0, bd=0).pack(
                           anchor="w", pady=2)

    # ------------------------------------------------------------ eylemler
    def on_show(self) -> None:
        count, size = tts.cache_size()
        self.cache_lbl.config(
            text=f"Önbellek: {count} ses dosyası · {size:.1f} MB"
        )
        self.refresh_backups()
        self.refresh_flags()

    # ------------------------------------------------------ dogru saydiklarim
    def refresh_flags(self) -> None:
        self.flag_list.delete(0, "end")
        self._flags = db.list_user_accepted(self.conn)
        if not self._flags:
            self.flag_list.insert("end", "  (henüz işaretlediğin cevap yok)")
            return
        for item in self._flags:
            shown = item["us_form"] or item["word"]
            mark = "" if item["exported"] else "•  "
            tag = "  [TR→EN]" if item.get("direction") == db.TR_EN else ""
            self.flag_list.insert(
                "end", f"  {mark}{shown}  ←  {item['answer']}{tag}"
                       f"      ({item['created_at'][:10]})"
            )

    def remove_flag(self) -> None:
        selection = self.flag_list.curselection()
        if not selection or not getattr(self, "_flags", None):
            return
        item = self._flags[selection[0]]
        shown = item["us_form"] or item["word"]
        if not messagebox.askyesno(
            "Geri al",
            f"“{item['answer']}” artık {shown} için doğru sayılmayacak.\n\nDevam?"
        ):
            return
        db.remove_user_accepted(self.conn, item["id"])
        self.refresh_flags()

    def export_flags(self) -> None:
        """Isaretlenenleri tools/overrides.json'a kalici olarak isler."""
        if not getattr(self, "_flags", None):
            self.flag_msg.config(text="İşaretlenmiş cevap yok.",
                                 fg=self.theme.c["text_dim"])
            return
        try:
            from tools.apply_flags import apply_flags
        except ImportError:
            sys.path.insert(0, str(db.ROOT))
            from tools.apply_flags import apply_flags
        added, path = apply_flags(self.conn)
        self.flag_msg.config(
            text=f"✔ {added} cevap {path} dosyasına işlendi.\n"
                 "Kalıcı olması için: py tools/build_dataset.py",
            fg=self.theme.c["ok"],
        )
        self.refresh_flags()

    # ---------------------------------------------------------- guncelleme
    def check_update_now(self) -> None:
        """Ayarin ve gunluk sinirin otesinde, elle kontrol.

        Karar ana pencerenindir; burada yalnizca sonucu yaziya dokuyoruz.
        """
        self.update_lbl.config(text="Kontrol ediliyor…", fg=self.theme.c["text_dim"])
        self.app.check_updates(force=True, on_done=self._show_update_status)

    def _show_update_status(self, status: tuple[str, str]) -> None:
        text, color = status
        self.update_lbl.config(text=text, fg=self.theme.c[color])

    # ---------------------------------------------------------- otomatik yedek
    def refresh_backups(self) -> None:
        self.backup_list.delete(0, "end")
        self._backups = backup.list_backups()
        if not self._backups:
            self.backup_list.insert("end", "  (henüz yedek yok)")
            return
        for i, path in enumerate(self._backups):
            mark = "● en yeni  " if i == 0 else "             "
            self.backup_list.insert("end", f"  {mark}{backup.describe(path)}")

    def backup_now(self) -> None:
        path = backup.create(db.DB_PATH, force=True)
        if path:
            self.backup_msg.config(text=f"✔ Yedek alındı: {path.name}",
                                   fg=self.theme.c["ok"])
        else:
            self.backup_msg.config(
                text="Yedeklenecek ilerleme yok (henüz hiç kelime çalışılmamış).",
                fg=self.theme.c["text_dim"])
        self.refresh_backups()
        self.after(5000, lambda: self.backup_msg.config(text=""))

    def restore_selected(self) -> None:
        selection = self.backup_list.curselection()
        if not selection or not getattr(self, "_backups", None):
            messagebox.showinfo("Yedek seç", "Önce listeden bir yedek seç.")
            return
        path = self._backups[selection[0]]
        if not messagebox.askyesno(
            "Geri yükle",
            f"Şu yedeğe dönülecek:\n{backup.describe(path)}\n\n"
            "Mevcut ilerlemenin üzerine yazılacak (o da kenara alınacak).\n\n"
            "Devam edilsin mi?"
        ):
            return
        self.conn.commit()
        self.conn.close()
        ok = backup.restore(path, db.DB_PATH)
        messagebox.showinfo(
            "Geri yüklendi" if ok else "Başarısız",
            "İlerleme geri yüklendi. Programı kapatıp yeniden başlat."
            if ok else "Yedek okunamadı.",
        )
        self.app.destroy()

    def open_backup_dir(self) -> None:
        backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(backup.BACKUP_DIR)

    def save(self) -> None:
        for key, var in self.vars.items():
            db.set_setting(self.conn, key, var.get())
        self.saved_lbl.config(text="✔ Kaydedildi — yeni oturumda geçerli olacak")
        self.after(4000, lambda: self.saved_lbl.config(text=""))
        self.app.refresh_status()

    def prefetch_audio(self) -> None:
        words = [r["word"] for r in
                 self.conn.execute("SELECT word FROM words").fetchall()]

        def progress(done: int, total: int) -> None:
            self.cache_lbl.config(text=f"İndiriliyor… {done}/{total}")

        tts.prefetch(words, progress)
        self.cache_lbl.config(text="İndirme arka planda başladı…")

    def backup(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        target = filedialog.asksaveasfilename(
            title="İlerlemeyi yedekle", defaultextension=".db",
            initialfile=f"ilerleme_{stamp}.db",
            filetypes=[("Veritabanı", "*.db")],
        )
        if not target:
            return
        self.conn.commit()
        shutil.copy2(db.DB_PATH, target)
        messagebox.showinfo("Yedek", f"Yedek kaydedildi:\n{target}")

    def restore(self) -> None:
        source = filedialog.askopenfilename(
            title="Yedekten geri yükle", filetypes=[("Veritabanı", "*.db")]
        )
        if not source:
            return
        if not messagebox.askyesno(
            "Geri yükle",
            "Mevcut ilerlemenin ÜZERİNE yazılacak. Devam edilsin mi?"
        ):
            return
        self.conn.close()
        shutil.copy2(source, db.DB_PATH)
        messagebox.showinfo(
            "Geri yüklendi", "Programı kapatıp yeniden başlat."
        )
        self.app.destroy()

    def reset_all(self) -> None:
        if not messagebox.askyesno(
            "Sıfırla",
            "TÜM ilerlemen silinecek (bilinen/öğrenilen kelimeler, seriler, "
            "günlük geçmiş). Bu geri alınamaz.\n\nEmin misin?"
        ):
            return
        if not messagebox.askyesno("Son onay", "Gerçekten sıfırlansın mı?"):
            return
        self.conn.execute(
            """UPDATE progress SET state = ?, streak = 0, best_streak = 0,
                 shows = 0, correct = 0, wrong = 0, session_hits = 0,
                 due_at = 0, gap_idx = 0,
                 last_seen = NULL, first_seen = NULL, settled_at = NULL""",
            (db.POOL,),
        )
        self.conn.execute("DELETE FROM reviews")
        self.conn.execute("DELETE FROM sessions")
        self.conn.execute("DELETE FROM daily")
        self.conn.commit()
        self.app.refresh_status()
        messagebox.showinfo("Sıfırlandı", "Tüm ilerleme sıfırlandı.")
