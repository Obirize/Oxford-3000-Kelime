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
sys.path.insert(0, str(ROOT))

from app.version import VERSION  # noqa: E402

EXE_NAME = "Oxford3000.exe"
TARGET = ROOT / EXE_NAME
VERSION_FILE = ROOT / "version_info.txt"

VERSION_TEMPLATE = """\
# BU DOSYA URETILIR - elle duzenleme. Kaynak: app/version.py (VERSION)
# Yeniden uretmek icin: py tools/build_exe.py
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tup}, prodvers={tup},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable("041f04b0", [
        StringStruct("CompanyName", ""),
        StringStruct("FileDescription", "Oxford 3000 - Ingilizce Kelime Ezberleme"),
        StringStruct("FileVersion", "{dotted}"),
        StringStruct("InternalName", "Oxford3000"),
        StringStruct("OriginalFilename", "Oxford3000.exe"),
        StringStruct("ProductName", "Oxford 3000 Kelime Ezberleme"),
        StringStruct("ProductVersion", "{dotted}"),
      ])
    ]),
    VarFileInfo([VarStruct("Translation", [1055, 1200])])
  ]
)
"""


def write_version_info() -> None:
    """exe'nin dosya ozelliklerindeki surumu app/version.py'den uretir."""
    parts = [int(p) for p in VERSION.split(".")][:4]
    parts += [0] * (4 - len(parts))
    VERSION_FILE.write_text(
        VERSION_TEMPLATE.format(tup=tuple(parts), dotted=".".join(map(str, parts))),
        encoding="utf-8",
    )
    print(f"version_info.txt -> {VERSION}")


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

    write_version_info()
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
