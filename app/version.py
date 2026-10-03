"""Surum numarasinin TEK kaynagi.

Buradaki deger:
  * acilisteki guncelleme kontrolunde karsilastirilir (app/update.py),
  * exe'nin dosya ozelliklerine yazilir (tools/build_exe.py -> version_info.txt),
  * kurulum paketine gecirilir (tools/build_setup.py -> ISCC /DAppVersion).

Yeni surum cikarirken YALNIZCA burayi degistir, sonra:
    py tools/build_setup.py
"""

VERSION = "1.0.3"

# GitHub deposu: guncelleme kontrolu ve "indir" baglantisi icin
REPO = "Obirize/Oxford-3000-Kelime"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"


def as_tuple(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Sayi olmayan parcalar atlanir.

    BOS metin (0,) dondurur - 'surum okunamadi' durumu yanlislikla
    'yeni surum' sayilmasin.
    """
    parts = []
    for chunk in text.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str = VERSION) -> bool:
    """candidate surumu current'tan yeni mi?"""
    a, b = as_tuple(candidate), as_tuple(current)
    length = max(len(a), len(b))
    a += (0,) * (length - len(a))
    b += (0,) * (length - len(b))
    return a > b
