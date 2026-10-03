"""Renk paleti, tipografi ve ttk stilleri.

tkinter varsayilan gorunumu cok eskidir; burada koyu/acik iki palet ve
ttk uzerinde tutarli bir stil seti tanimlanir.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import dpi

DARK = {
    "bg":          "#12151c",
    "surface":     "#1a1f2b",
    "surface_alt": "#222939",
    "border":      "#2d3548",
    "text":        "#f0f3f9",
    "text_dim":    "#aab4ca",   # okunurluk: eski #8b95ad kontrasti dusuktu
    "accent":      "#5b8cff",
    "accent_dim":  "#2f4a8a",
    "ok":          "#3ecf8e",
    "ok_dim":      "#1d5b41",
    "warn":        "#f0b429",
    "warn_dim":    "#6b4f12",
    "bad":         "#ff5d5d",
    "bad_dim":     "#6e2626",
    "known":       "#3ecf8e",
    "learned":     "#5b8cff",
    "learning":    "#f0b429",
    "pool":        "#3a4358",
}

LIGHT = {
    "bg":          "#f4f6fa",
    "surface":     "#ffffff",
    "surface_alt": "#eef1f7",
    "border":      "#d6dce8",
    "text":        "#0e1420",
    "text_dim":    "#4a5568",   # okunurluk: eski #5f6b82 kontrasti dusuktu
    "accent":      "#2f6bff",
    "accent_dim":  "#c3d4ff",
    "ok":          "#12a05f",
    "ok_dim":      "#c2ecd8",
    "warn":        "#b8770a",
    "warn_dim":    "#f7e4b8",
    "bad":         "#d63636",
    "bad_dim":     "#f8d0d0",
    "known":       "#12a05f",
    "learned":     "#2f6bff",
    "learning":    "#b8770a",
    "pool":        "#c8cfdd",
}

# Yazi tipleri PUNTO cinsindendir; yuksek DPI ekranlarda Tk bunlari
# kendiliginden buyutur (bkz. app/dpi.py). Piksel cinsinden olculer icin
# asagidaki px() kullanilir.
FONT = "Segoe UI"

F_WORD    = (FONT, 40, "bold")   # kartin ortasindaki kelime
F_TITLE   = (FONT, 20, "bold")
F_H2      = (FONT, 14, "bold")
F_BODY    = (FONT, 12)           # eskiden 11
F_SMALL   = (FONT, 10)           # eskiden 9 - kucuk ve zor okunuyordu
F_EXAMPLE = (FONT, 11)           # ornek cumle + Turkcesi (eskiden 10)
F_STAT    = (FONT, 18, "bold")
F_INPUT   = (FONT, 18)
F_MONO    = ("Consolas", 11)

# Ekran olcegi; ilk Theme.apply() cagrisinda gercek degerle guncellenir.
SCALE = 1.0


def px(value: float) -> int:
    """Piksel olcusunu ekran olceginde buyutur (%125 ekran -> 1.25 kat)."""
    return int(round(value * SCALE))


class Theme:
    def __init__(self, name: str = "dark"):
        self.name = name
        self.c = DARK if name == "dark" else LIGHT

    def __getitem__(self, key: str) -> str:
        return self.c[key]

    def apply(self, root: tk.Misc) -> None:
        global SCALE
        c = self.c
        SCALE = dpi.factor(root)
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        root.configure(bg=c["bg"])

        style.configure(".", background=c["bg"], foreground=c["text"],
                        font=F_BODY, borderwidth=0)
        style.configure("TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["surface"])
        style.configure("Alt.TFrame", background=c["surface_alt"])

        style.configure("TLabel", background=c["bg"], foreground=c["text"])
        style.configure("Card.TLabel", background=c["surface"], foreground=c["text"])
        style.configure("Dim.TLabel", background=c["bg"], foreground=c["text_dim"],
                        font=F_SMALL)
        style.configure("CardDim.TLabel", background=c["surface"],
                        foreground=c["text_dim"], font=F_SMALL)
        style.configure("Title.TLabel", background=c["bg"], foreground=c["text"],
                        font=F_TITLE)
        style.configure("H2.TLabel", background=c["bg"], foreground=c["text"],
                        font=F_H2)

        # Butonlar
        style.configure("TButton", background=c["surface_alt"], foreground=c["text"],
                        padding=(px(14), px(8)), font=F_BODY, relief="flat")
        style.map("TButton",
                  background=[("active", c["border"]), ("pressed", c["border"])])

        style.configure("Accent.TButton", background=c["accent"],
                        foreground="#ffffff", padding=(px(18), px(10)), font=F_H2)
        style.map("Accent.TButton", background=[("active", c["accent_dim"])])

        # "Biliyordum" butonu - goze carpmali
        style.configure("Accept.TButton", background=c["ok_dim"],
                        foreground=c["ok"], padding=(px(14), px(8)), font=F_H2)
        style.map("Accept.TButton",
                  background=[("active", c["ok"])],
                  foreground=[("active", "#ffffff")])

        style.configure("Ghost.TButton", background=c["bg"],
                        foreground=c["text_dim"], padding=(px(10), px(6)), font=F_SMALL)
        style.map("Ghost.TButton", background=[("active", c["surface_alt"])])

        # Navigasyon sekmeleri
        style.configure("Nav.TButton", background=c["bg"], foreground=c["text_dim"],
                        padding=(px(16), px(9)), font=F_BODY)
        style.map("Nav.TButton", background=[("active", c["surface_alt"])])
        style.configure("NavOn.TButton", background=c["surface"],
                        foreground=c["accent"], padding=(px(16), px(9)), font=F_H2)

        # Giris kutusu
        style.configure("TEntry", fieldbackground=c["surface_alt"],
                        foreground=c["text"], insertcolor=c["text"],
                        bordercolor=c["border"], lightcolor=c["border"],
                        darkcolor=c["border"], padding=px(10))
        style.configure("Big.TEntry", fieldbackground=c["surface_alt"],
                        foreground=c["text"], insertcolor=c["accent"], padding=px(14))

        # Tablo
        style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                        foreground=c["text"], rowheight=px(28), borderwidth=0)
        style.configure("Treeview.Heading", background=c["surface_alt"],
                        foreground=c["text_dim"], font=F_SMALL, relief="flat",
                        padding=(px(8), px(6)))
        style.map("Treeview", background=[("selected", c["accent_dim"])],
                  foreground=[("selected", c["text"])])
        style.map("Treeview.Heading", background=[("active", c["border"])])

        style.configure("TCombobox", fieldbackground=c["surface_alt"],
                        background=c["surface_alt"], foreground=c["text"],
                        arrowcolor=c["text_dim"], padding=px(6))
        style.configure("TCheckbutton", background=c["bg"], foreground=c["text"])
        style.map("TCheckbutton", background=[("active", c["bg"])])
        style.configure("TScale", background=c["bg"], troughcolor=c["surface_alt"])


def segmented_bar(canvas: tk.Canvas, segments: list[tuple[int, str]],
                  width: int, height: int, bg: str, radius: int = 0) -> None:
    """Coklu renkli ilerleme cubugu cizer. segments = [(deger, renk), ...]"""
    canvas.delete("all")
    total = sum(v for v, _ in segments) or 1
    x = 0.0
    canvas.create_rectangle(0, 0, width, height, fill=bg, outline="")
    for value, color in segments:
        if value <= 0:
            continue
        w = width * value / total
        canvas.create_rectangle(x, 0, x + w + 0.5, height, fill=color, outline="")
        x += w
