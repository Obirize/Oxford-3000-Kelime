"""Windows'ta yuksek DPI (ekran olceklendirme) destegi.

Neden gerekli
-------------
Windows ekran olceklendirmesi %100'den buyukse (ornegin %125) ve program
"DPI farkindaligi" bildirmezse, Windows pencereyi 96 DPI'da cizdirip sonucu
BITMAP olarak buyutur. Yazilar bulanik gorunur - cozunurluk dusuk degildir,
goruntu esnetilmistir.

Farkindalik bildirildiginde Tk gercek cozunurlukte cizer ve punto cinsinden
tanimli yazi tipleri kendiliginden buyur: 11 punto 96 DPI'da 20 piksel,
120 DPI'da 25 piksel olur. Yazilar hem buyur hem KESKINLESIR.

DIKKAT: Bu, surecte hicbir pencere olusturulmadan once cagrilmalidir; sonra
cagrilirsa Windows yok sayar. main.py'nin ilk isi budur.
"""

from __future__ import annotations

import ctypes
import sys

PER_MONITOR_V2 = -4       # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
PROCESS_PER_MONITOR = 2   # PROCESS_PER_MONITOR_DPI_AWARE


def enable() -> bool:
    """DPI farkindaligini acar. Basarili olursa True.

    Uc yontem sirayla denenir (Windows 10 1703+ / 8.1 / daha eski).
    Windows disinda veya hepsi basarisiz olursa sessizce False doner -
    program yine calisir, yalnizca yazilar eskisi gibi gorunur.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(PER_MONITOR_V2)):
            return True
    except Exception:
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR) == 0:
            return True
    except Exception:
        pass
    try:
        return bool(ctypes.windll.user32.SetProcessDPIAware())
    except Exception:
        return False


def factor(widget) -> float:
    """Ekranin 96 DPI'ya gore olcegi (%125 ekran -> 1.25).

    Punto cinsinden yazi tipleri Tk tarafindan kendiliginden olceklenir;
    bu carpan PIKSEL cinsinden verilen olculer icindir (pencere boyutu,
    satir sarma genisligi, cubuk yuksekligi...).
    """
    try:
        return max(widget.winfo_fpixels("1i") / 96.0, 1.0)
    except Exception:
        return 1.0
