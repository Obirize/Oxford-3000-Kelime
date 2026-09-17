"""Programi tek dosyalik Oxford3000.exe olarak paketler.

    py tools/build_exe.py                 # ikon + exe uret, koke kopyala
    py tools/build_exe.py --shortcut      # ayrica masaustune kisayol koy

Uretilen exe proje KOKUNE kopyalanir; boylece yanindaki data/ klasorunu
(ilerleme, yedekler, ses) kullanmaya devam eder. dist/ altindan calistirilirsa
ayri bir data/ olusturur ve eski ilerleme gorunmez - bu yuzden koke aliyoruz.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE_NAME = "Oxford3000.exe"
TARGET = ROOT / EXE_NAME


def run(cmd: list[str], label: str) -> None:
    print(f"\n>>> {label}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"BASARISIZ: {label}")


def make_shortcut() -> None:
    """Masaustune kisayol olusturur (Windows)."""
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        print("Masaustu klasoru bulunamadi, kisayol atlandi.")
        return
    link = desktop / "Oxford 3000 Kelime.lnk"
    script = (
        f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{link}");'
        f'$s.TargetPath="{TARGET}";'
        f'$s.WorkingDirectory="{ROOT}";'
        f'$s.IconLocation="{ROOT / "assets" / "app.ico"}";'
        f'$s.Description="Oxford 3000 Ingilizce Kelime Ezberleme";'
        f'$s.Save()'
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False)
    print(f"kisayol: {link}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    if not (ROOT / "data" / "oxford3000.json").exists():
        raise SystemExit("data/oxford3000.json yok. Once: py tools/build_dataset.py")

    run([sys.executable, "-X", "utf8", "tools/make_icon.py"], "ikon uretiliyor")
    run([sys.executable, "-m", "PyInstaller", "oxford3000.spec",
         "--noconfirm", "--clean"], "exe derleniyor (birkac dakika)")

    built = ROOT / "dist" / EXE_NAME
    if not built.exists():
        raise SystemExit("dist/Oxford3000.exe olusmadi")

    shutil.copy2(built, TARGET)
    size = TARGET.stat().st_size / 1_048_576
    print(f"\nhazir: {EXE_NAME}  ({size:.1f} MB)")

    # ara dosyalari temizle - exe zaten kokte
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    print("build/ ve dist/ temizlendi")

    if "--shortcut" in sys.argv:
        make_shortcut()

    print("\nCalistirmak icin Oxford3000.exe dosyasina cift tikla.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
