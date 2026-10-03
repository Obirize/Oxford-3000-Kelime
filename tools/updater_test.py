"""Otomatik guncelleyici testi (app/updater.py).

    py tools/updater_test.py

AG'A CIKMAZ ve HICBIR SEY KURMAZ: indirme urllib yerine sahte bir acici ile,
kurulum da subprocess.Popen yerine sahte bir baslatici ile yapilir.

Olculenler
  * indirme adresi dogrulamasi (yalnizca bu deponun GitHub adresleri)
  * SHA-256 dogrulamasi: tutmazsa dosya SILINIR ve kurulum YAPILMAZ
  * eksik indirme (boyut tutmuyor) reddedilir
  * iptal edilince yarim dosya kalmaz
  * kurulum komutunun sessiz calisma bayraklari
  * tasinabilir kopyada kurulum teklif edilmez
"""

import hashlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import update, updater  # noqa: E402

from _guard import check, report  # noqa: E402

GOOD_URL = ("https://github.com/Obirize/Oxford-3000-Kelime/releases/download/"
            "v9.9.9/Oxford3000-Kurulum-9.9.9.exe")
SUMS_URL = ("https://github.com/Obirize/Oxford-3000-Kelime/releases/download/"
            "v9.9.9/SHA256SUMS.txt")
PAYLOAD = b"sahte kurulum dosyasi" * 500


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def fake_open(data_by_url: dict):
    def opener(url: str):
        if not updater._is_trusted_url(url):
            raise updater.UpdateError("güvenilmeyen adres")
        return FakeResponse(data_by_url[url])
    return opener


def release(assets) -> update.Release:
    return update.Release(version="9.9.9", url="https://example.invalid",
                          assets=assets)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="oxford_updater_"))
    original_open, original_tmp = updater._open, tempfile.gettempdir
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    installer_name = "Oxford3000-Kurulum-9.9.9.exe"
    assets = [update.Asset(installer_name, GOOD_URL, len(PAYLOAD)),
              update.Asset("SHA256SUMS.txt", SUMS_URL, 100)]
    try:
        tempfile.gettempdir = lambda: str(tmp)

        print("\n1) Indirme adresi dogrulamasi")
        cases = [
            (GOOD_URL, True),
            ("https://objects.githubusercontent.com/x/y", True),
            ("https://github.com/baskasi/repo/releases/download/v1/x.exe", False),
            ("http://github.com/Obirize/Oxford-3000-Kelime/x.exe", False),
            ("https://kotu-site.example/Oxford3000-Kurulum.exe", False),
            ("https://github.com.evil.example/Obirize/x.exe", False),
        ]
        bad = [u for u, ok in cases if updater._is_trusted_url(u) != ok]
        check("yalnizca bu deponun GitHub adresleri kabul edilir", not bad, str(bad))

        print("\n2) Dogru ozet -> dosya hazir")
        updater._open = fake_open({GOOD_URL: PAYLOAD,
                                   SUMS_URL: f"{digest}  {installer_name}\n".encode()})
        seen = []
        path = updater.prepare(release(assets),
                               progress=lambda d, t: seen.append((d, t)))
        check("kurulum dosyasi indi", path.exists() and path.name == installer_name)
        check("ilerleme bildirildi", len(seen) > 0 and seen[-1][0] == len(PAYLOAD),
              f"{len(seen)} bildirim")
        check("icerik dogru", path.read_bytes() == PAYLOAD)

        print("\n3) Ozet TUTMUYOR -> dosya silinir, kurulum yapilmaz")
        path.unlink(missing_ok=True)
        updater._open = fake_open({GOOD_URL: PAYLOAD,
                                   SUMS_URL: f"{'0' * 64}  {installer_name}\n".encode()})
        try:
            updater.prepare(release(assets))
            check("bozuk ozet reddedildi", False, "hata firlatilmadi")
        except updater.UpdateError as err:
            check("bozuk ozet reddedildi", "imzası tutmadı" in str(err), str(err)[:50])
        leftover = list((tmp / "Oxford3000-guncelleme").glob("*.exe"))
        check("yarim/sahte dosya silindi", not leftover, str(leftover))

        print("\n4) Eksik indirme reddedilir")
        updater._open = fake_open({GOOD_URL: PAYLOAD[:100], SUMS_URL: b""})
        try:
            updater.prepare(release(assets))
            check("boyut tutmayinca reddedilir", False, "hata firlatilmadi")
        except updater.UpdateError as err:
            check("boyut tutmayinca reddedilir", "eksik" in str(err), str(err)[:50])

        print("\n5) Guvenilmeyen adres indirilmez")
        kotu = [update.Asset(installer_name, "https://kotu.example/x.exe", 10)]
        updater._open = original_open     # gercek acici: istek bile atilmamali
        try:
            updater.prepare(release(kotu))
            check("guvenilmeyen adres reddedildi", False, "hata firlatilmadi")
        except updater.UpdateError as err:
            check("guvenilmeyen adres reddedildi", "beklenen yerde değil" in str(err),
                  str(err)[:50])

        print("\n6) Iptal -> yarim dosya kalmaz")
        updater._open = fake_open({GOOD_URL: PAYLOAD, SUMS_URL: b""})
        try:
            updater.download(GOOD_URL, tmp / "yarim.exe", size=len(PAYLOAD),
                             cancelled=lambda: True)
            check("iptal edilebiliyor", False, "hata firlatilmadi")
        except updater.UpdateError:
            check("iptal edilebiliyor", True)
        check("yarim dosya silindi", not (tmp / "yarim.exe").exists())

        print("\n7) Kurulum komutu")
        cmd = updater.install_command(Path("C:/x/kurulum.exe"))
        check("sessiz kurulum bayraklari",
              {"/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"} <= set(cmd), str(cmd))
        check("kurulum sonrasi yeniden baslatma istenir", "/RESTARTAPP=1" in cmd)
        check("yeniden baslatma kapatilabilir",
              "/RESTARTAPP=1" not in updater.install_command(Path("x"), restart=False))

        print("\n8) Surum dosyalarini secme")
        rel = release(assets)
        check("kurulum paketi bulunur", rel.installer.name == installer_name)
        check("ozet dosyasi bulunur", rel.checksums.name == "SHA256SUMS.txt")
        check("kurulum paketi yoksa None",
              release([update.Asset("Oxford3000.exe", GOOD_URL, 1)]).installer is None)

        print("\n9) Tasinabilir kopyada kurulum yok")
        check("kaynak koddan calisirken kurulum teklif edilmez",
              not updater.is_installed(), "sys.frozen yok")
    finally:
        updater._open, tempfile.gettempdir = original_open, original_tmp
        shutil.rmtree(tmp, ignore_errors=True)

    return report("✅ OTOMATIK GUNCELLEME CALISIYOR")


if __name__ == "__main__":
    raise SystemExit(main())
