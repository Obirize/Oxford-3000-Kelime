"""Windows kurulum paketi uretir (Inno Setup 6).

    py tools/build_setup.py          # exe'yi derler, sonra kurulum paketini
    py tools/build_setup.py --no-exe # exe zaten guncel, sadece kurulum

Cikti: dist/Oxford3000-Kurulum-<surum>.exe   -> GitHub Releases'e yuklenir.

Inno Setup: https://jrsoftware.org/isdl.php  (ISCC.exe PATH'te ya da
asagidaki standart klasorlerden birinde olmali.)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.version import VERSION  # noqa: E402

ISS = ROOT / "installer" / "Oxford3000.iss"

CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
]


def find_iscc() -> Path:
    on_path = shutil.which("ISCC")
    if on_path:
        return Path(on_path)
    for cand in CANDIDATES:
        if cand.exists():
            return cand
    raise SystemExit(
        "ISCC.exe bulunamadi. Inno Setup 6 kur: https://jrsoftware.org/isdl.php"
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--no-exe" not in sys.argv:
        print(">>> exe derleniyor")
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_exe.py")],
                       cwd=ROOT, check=True)
    if not (ROOT / "Oxford3000.exe").exists():
        raise SystemExit("Oxford3000.exe yok - once tools/build_exe.py")

    iscc = find_iscc()
    (ROOT / "dist").mkdir(exist_ok=True)
    print(f">>> kurulum derleniyor ({iscc})  surum {VERSION}")
    # Surum tek kaynaktan gelir: app/version.py
    subprocess.run([str(iscc), "/Q", f"/DAppVersion={VERSION}", str(ISS)],
                   cwd=ROOT, check=True)

    # Dosya adini .iss belirler (OutputBaseFilename); burada yeniden kurmak
    # yerine uretileni buluyoruz ki iki yerde tanimli olmasin.
    produced = sorted((ROOT / "dist").glob("Oxford3000-Kurulum-*.exe"),
                      key=lambda p: p.stat().st_mtime)
    if not produced:
        raise SystemExit("kurulum dosyasi uretilemedi")
    path = produced[-1]
    # Tasinabilir exe de yanina konur: Releases'e ikisi birden yuklenir
    portable = ROOT / "dist" / "Oxford3000.exe"
    shutil.copy2(ROOT / "Oxford3000.exe", portable)

    print(f"\nhazir: {path.relative_to(ROOT)}  ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"       {portable.relative_to(ROOT)}  "
          f"({portable.stat().st_size / 1e6:.1f} MB)")
    print(f"\nIkisini de GitHub Releases'e v{VERSION} etiketiyle yukle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
