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

Taranan yerler yalnizca bu programin kendi klasorleridir; kullanicinin
belgeleri taranmaz.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import paths


@dataclass
class Found:
    path: Path
    studied: int      # havuz disindaki kelime sayisi (biliniyor/ogreniliyor/ogrenildi)
    reviews: int      # toplam cevap
    last_seen: str    # son cevap zamani ('' olabilir)

    @property
    def label(self) -> str:
        when = self.last_seen[:10] if self.last_seen else "?"
        return (f"{self.studied} kelime · {self.reviews} cevap · son çalışma {when}\n"
                f"{self.path}")


def _candidate_dirs() -> list[Path]:
    """Bu programin ilerleme tutabilecegi bilinen klasorler."""
    out: list[Path] = []
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    for base in (local, program_files, program_files_x86):
        if not base:
            continue
        out.append(Path(base) / "Programs" / "Oxford3000" / "data")
        out.append(Path(base) / "Oxford3000" / "data")
    # Tasinabilir kopya: exe'nin yani ve bir ustu
    out.append(paths.app_dir() / "data")
    out.append(paths.app_dir().parent / "data")
    return out


def _inspect(path: Path) -> Found | None:
    """Dosyayi SALT OKUNUR acip ice aktarmaya deger mi diye bakar."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return None
            studied = conn.execute(
                "SELECT COUNT(*) FROM progress WHERE state <> 'pool'"
            ).fetchone()[0]
            reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            last = conn.execute("SELECT MAX(ts) FROM reviews").fetchone()[0] or ""
        finally:
            conn.close()
    except Exception:
        return None
    if studied <= 0:
        return None
    return Found(path=path, studied=studied, reviews=reviews, last_seen=last)


def is_empty(path: Path) -> bool:
    """Buradaki ilerleme yok ya da hic calisilmamis mi?"""
    return _inspect(path) is None


def find_elsewhere(current: Path) -> Found | None:
    """Baska bir klasorde dolu bir ilerleme var mi? En cok calisilmis olani.

    Her aday klasorde hem `progress.db` hem de `backups/` icindeki en yeni
    yedek denenir - kurulum klasorundeki dosya bozuksa yedegi ise yarar.
    """
    current = current.resolve()
    best: Found | None = None
    seen: set[Path] = set()
    for folder in _candidate_dirs():
        files = [folder / "progress.db"]
        backups = folder / "backups"
        if backups.is_dir():
            files += sorted(backups.glob("progress_*.db"), reverse=True)[:1]
        for file in files:
            try:
                resolved = file.resolve()
            except OSError:
                continue
            if resolved == current or resolved in seen:
                continue
            seen.add(resolved)
            found = _inspect(resolved)
            if found and (best is None or found.reviews > best.reviews):
                best = found
    return best


def adopt(found: Found, target: Path) -> bool:
    """Bulunan ilerlemeyi buraya kopyalar. Kaynak dosyaya DOKUNULMAZ."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Buradaki bos dosya yine de kenara alinsin
            shutil.copy2(target, target.with_name("progress_devralmadan_once.db"))
        shutil.copy2(found.path, target)
        return True
    except Exception:
        return False
