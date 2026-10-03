# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller yapilandirmasi.

    py -m PyInstaller oxford3000.spec --noconfirm

Uretilen: dist/Oxford3000.exe  (tek dosya)

Pakete gomulenler: kelime listesi ve ikon (salt okunur).
Kullanici verisi (ilerleme, yedekler, ses onbellegi) pakete GIRMEZ -
exe'nin yanindaki data/ klasorune yazilir, boylece exe degisse de kalir.
"""

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("data/oxford3000.json", "data"),   # kelime havuzu
        ("assets/app.ico", "assets"),       # pencere ikonu
    ],
    hiddenimports=["gtts"],
    hookspath=[],
    runtime_hooks=[],
    # Kullanilmayan agir paketleri disarida birak - exe kucuk kalsin
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "PIL", "pytest",
        "PyInstaller", "pypdf", "setuptools", "pip",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="Oxford3000",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,            # konsol penceresi acilmasin
    icon="assets/app.ico",
    # DIKKAT: anahtar "version" - "version_file" PyInstaller 6'da SESSIZCE
    # yok sayilir ve exe surumsuz cikar.
    version="version_info.txt",
)
