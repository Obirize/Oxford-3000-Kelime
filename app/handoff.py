"""Baska bir kopyadaki ilerlemeyi devralma.

Sorun
-----
Program ilerlemeyi exe'nin YANINDAKI `data/` klasorunde tutar (tasinabilirlik
icin). Bu, ayni makinede iki kopya varsa ilerlemenin ayrismasina yol acar:
tasinabilir exe'yle calisip sonra kurulum paketini kuran kullanici, kurulu
surumu actiginda bomboş bir ilerlemeyle karsilasir - eski ilerleme silinmis
degildir, baska klasordedir.

Cozum
-----
Acilista ilerleme YOKSA ya da hic calisilmamissa, bilinen diger konumlara
bakilir. Dolu bir ilerleme bulunursa kullaniciya sorulur ve onay verirse
kopyalanir. Hicbir dosya SILINMEZ; eski kopya yerinde kalir.

Dosya sistemi TARANMAZ: yalnizca kurulum paketinin kullandigi klasor ve
programin kendi klasoru denenir (asagidaki CANDIDATES).

Saglamlik ve "ice aktarmaya deger mi" kararlari backup.py'ye birakilir
(is_healthy / has_progress / restore) - tek bir saglamlik tanimi olsun.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import backup, paths


@dataclass
class Found:
    path: Path
    studied: int      # havuz disindaki kelime sayisi
    reviews: int      # toplam cevap
    last_seen: str    # son cevap zamani ('' olabilir)

    @property
    def label(self) -> str:
        when = self.last_seen[:10] if self.last_seen else "?"
        return (f"{self.studied} kelime · {self.reviews} cevap · son çalışma {when}\n"
                f"{self.path}")


def _data_dirs() -> list[Path]:
    """Ilerleme tutabilecek bilinen klasorler (tarama yok, sabit liste).

    Kurulum paketi her zaman %LocalAppData%\\Programs\\Oxford3000 kullanir
    (installer/Oxford3000.iss -> DefaultDirName); yonetici olarak kurulursa
    Program Files altina duser. Tasinabilir kopyada ise veri exe'nin yanindadir.
    """
    out = [paths.app_dir() / "data"]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        out.append(Path(local) / "Programs" / "Oxford3000" / "data")
    for base in (os.environ.get("ProgramFiles", ""),
                 os.environ.get("ProgramFiles(x86)", "")):
        if base:
            out.append(Path(base) / "Oxford3000" / "data")
    return out


def inspect(path: Path) -> Found | None:
    """Dosya ice aktarmaya deger mi? Degilse None.

    Saglamlik + "icinde ilerleme var mi" sorusunu backup.has_progress yanitlar;
    burada yalnizca kullaniciya gosterilecek ozet okunur (tek sorguda).
    """
    if not backup.has_progress(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            studied, reviews, last = conn.execute(
                "SELECT (SELECT COUNT(*) FROM progress WHERE state <> 'pool'),"
                "       (SELECT COUNT(*) FROM reviews),"
                "       (SELECT MAX(ts) FROM reviews)"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return Found(path=path, studied=studied, reviews=reviews, last_seen=last or "")


def find_elsewhere(current: Path) -> Found | None:
    """Baska bir klasorde dolu bir ilerleme var mi? En cok calisilmis olani.

    Her klasorde once `progress.db` denenir; yalnizca o ise yaramazsa
    (yok/bozuk/bos) o klasorun en yeni yedegine bakilir.
    """
    current = current.resolve()
    best: Found | None = None
    seen: set[Path] = set()
    for folder in _data_dirs():
        for file in (folder / current.name, _newest_backup(folder)):
            if file is None:
                continue
            try:
                resolved = file.resolve()
            except OSError:
                continue
            if resolved == current or resolved in seen:
                continue
            seen.add(resolved)
            found = inspect(resolved)
            if found:
                if best is None or found.reviews > best.reviews:
                    best = found
                break          # bu klasor cevabini verdi, yedegine bakma
    return best


def _newest_backup(folder: Path) -> Path | None:
    folder = folder / backup.BACKUP_DIR.name
    if not folder.is_dir():
        return None
    return max(folder.glob(f"{backup.PREFIX}*{backup.SUFFIX}"), default=None)


def adopt(found: Found, target: Path) -> bool:
    """Bulunan ilerlemeyi buraya kopyalar. Kaynak dosyaya DOKUNULMAZ.

    Mevcut (bos) hedef, backup.restore tarafindan `.db.replaced` olarak
    kenara alinir - yedekten geri yuklemeyle ayni davranis.
    """
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return backup.restore(found.path, target)
