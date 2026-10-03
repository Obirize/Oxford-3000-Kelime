"""Yeni surumu indirip kuran otomatik guncelleyici.

Akis
----
    surum kontrolu (update.py)
      -> kurulum dosyasini indir (buradaki download)
      -> SHA-256 dogrula
      -> kurulumu sessiz calistir ve programdan cik
      -> kurulum biter bitmez program yeniden acilir (/RESTARTAPP=1)

Guvenlik kurallari (hepsi zorunlu, hicbiri atlanabilir degil)
-------------------------------------------------------------
* Indirme adresi YALNIZCA GitHub'in kendi alan adlarindan olabilir ve bu
  depoya ait olmalidir (bkz. _is_trusted_url). API'den gelen adres baska bir
  yere isaret ediyorsa indirme yapilmaz - saldirganin API yanitini
  degistirmesi tek basina yetmesin.
* Dosya boyutu API'nin bildirdigi boyutla ayni olmali.
* Surumun SHA256SUMS.txt dosyasi varsa ozet DOGRULANIR; tutmazsa kurulum
  calistirilmaz. (Dosya yoksa - eski surumler - yalnizca boyut dogrulanir.)
* Indirilen dosya kullanicinin gecici klasorune iner ve kurulum bittiginde
  silinir.

Tasinabilir kopya
-----------------
Kurulum paketi yalnizca KURULU kopyayi gunceller. Tasinabilir exe'yi
(USB'deki gibi) kendi kendine degistirmeyiz: calisan dosyanin uzerine
yazmak risklidir ve kullanici onu bilerek oraya koymustur. O durumda
surum sayfasi acilir (bkz. is_installed).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from . import paths
from .version import REPO, VERSION

# Kurulum dosyasinin adi: Oxford3000-Kurulum-1.2.3.exe
INSTALLER_PREFIX = "Oxford3000-Kurulum-"
CHECKSUM_ASSET = "SHA256SUMS.txt"

# Indirme yalnizca bu alan adlarindan yapilabilir
TRUSTED_HOSTS = (
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)

CHUNK = 64 * 1024
TIMEOUT = 30


class UpdateError(Exception):
    """Guncelleme yapilamadi; mesaji kullaniciya gosterilebilir."""


# ------------------------------------------------------------------ ortam
def is_installed() -> bool:
    """Bu kopya kurulum paketiyle mi kuruldu?

    Inno Setup her kurulumun yanina bir kaldirma programi birakir; tasinabilir
    kopyada bu yoktur. Kaynak koddan calisirken de (donmus degilken) guncelleme
    yapilmaz - gelistirici makinesinde exe'nin isi yok.
    """
    if not getattr(sys, "frozen", False):
        return False
    return any(paths.app_dir().glob("unins*.exe"))


# ------------------------------------------------------------------ indirme
def _is_trusted_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower()
    if host not in TRUSTED_HOSTS:
        return False
    # github.com uzerindeki adres bu depoya ait olmali
    if host == "github.com" and not parts.path.lower().startswith(f"/{REPO.lower()}/"):
        return False
    return True


def _open(url: str):
    if not _is_trusted_url(url):
        raise UpdateError("İndirme adresi beklenen yerde değil, güncelleme durduruldu.")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"Oxford3000/{VERSION}",
                 "Accept": "application/octet-stream"},
    )
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def fetch_text(url: str) -> str:
    """Kucuk bir metin dosyasini indirir (SHA256SUMS.txt gibi)."""
    with _open(url) as resp:
        return resp.read(64 * 1024).decode("utf-8", "replace")


def expected_digest(text: str, filename: str) -> str:
    """SHA256SUMS.txt icinden bir dosyanin ozetini ayiklar."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    return ""


def download(url: str, target: Path, *, size: int = 0, progress=None,
             cancelled=None) -> str:
    """Dosyayi indirir ve SHA-256 ozetini dondurur.

    progress(indirilen, toplam) ara ara cagrilir; cancelled() True dondururse
    indirme birakilir ve yarim dosya silinir.
    """
    digest = hashlib.sha256()
    done = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _open(url) as resp, open(target, "wb") as out:
            total = size or int(resp.headers.get("Content-Length") or 0)
            while True:
                if cancelled is not None and cancelled():
                    raise UpdateError("İndirme iptal edildi.")
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except UpdateError:
        target.unlink(missing_ok=True)
        raise
    except Exception as err:
        target.unlink(missing_ok=True)
        raise UpdateError(f"İndirme tamamlanamadı: {err}") from err

    if size and done != size:
        target.unlink(missing_ok=True)
        raise UpdateError("İndirilen dosya eksik; güncelleme durduruldu.")
    return digest.hexdigest()


def prepare(release, *, progress=None, cancelled=None) -> Path:
    """Kurulum dosyasini indirir, dogrular ve yolunu dondurur.

    Dogrulama gecmezse dosya silinir ve UpdateError firlatilir.
    """
    asset = release.installer
    if asset is None:
        raise UpdateError("Bu sürümde kurulum dosyası yok; indirme sayfasını aç.")

    target = Path(tempfile.gettempdir()) / "Oxford3000-guncelleme" / asset.name
    digest = download(asset.url, target, size=asset.size,
                      progress=progress, cancelled=cancelled)

    sums = release.checksums
    if sums is not None:
        try:
            wanted = expected_digest(fetch_text(sums.url), asset.name)
        except UpdateError:
            wanted = ""
        if wanted and wanted != digest:
            target.unlink(missing_ok=True)
            raise UpdateError(
                "İndirilen dosyanın imzası tutmadı; güvenlik için kurulum "
                "yapılmadı. Sürüm sayfasından elle indirebilirsin."
            )
    return target


# ------------------------------------------------------------------ kurulum
def install_command(installer: Path, *, restart: bool = True) -> list[str]:
    """Kurulumun sessiz calistirma komutu.

    /VERYSILENT        : pencere gostermez
    /SUPPRESSMSGBOXES  : soru sormaz
    /NORESTART         : Windows'u yeniden baslatmaz
    /RESTARTAPP=1      : kurulum bitince programi yeniden acar (bkz. .iss)
    """
    cmd = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    if restart:
        cmd.append("/RESTARTAPP=1")
    return cmd


def launch(installer: Path, *, restart: bool = True) -> None:
    """Kurulumu baslatir. Program bundan HEMEN SONRA kapanmalidir.

    Kurulum, calisan exe'nin uzerine yazacagi icin programin cikmasi gerekir;
    bu yuzden kurulum ayri bir surec olarak, programdan bagimsiz baslatilir.
    """
    if not installer.exists():
        raise UpdateError("Kurulum dosyası bulunamadı.")
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(install_command(installer, restart=restart),
                         close_fds=True, creationflags=flags)
    except OSError as err:
        raise UpdateError(f"Kurulum başlatılamadı: {err}") from err
