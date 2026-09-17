"""Ornek cumlelerin Turkce cevirisini uretir (Google Translate).

    py tools/translate_examples.py            # eksikleri cevir, onbellege yaz
    py tools/translate_examples.py --check    # onbellek durumunu goster

Cikti: tools/examples_tr.json  {ingilizce cumle: turkce cumle}
build_dataset.py bu dosyayi okuyup her kelimeye `example_tr` alani ekler.

Kelime karsiliklari 4 bagimsiz kaynagin uzlasmasiyla uretildi; cumleler icin
boyle bir kaynak yok, bu yuzden makine cevirisi kullaniliyor. A1-B2 duzeyi
kisa cumlelerde kalite iyidir ama es sesli kelimelerde (still = hala / durgun)
yanlis anlam secilebilir. Yanlis gordugun ceviriyi bu dosyada elle duzelt;
script mevcut kayitlarin ustune yazmaz.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS = ROOT / "data" / "oxford3000.json"
CACHE = ROOT / "tools" / "examples_tr.json"
ENDPOINT = ("https://translate.googleapis.com/translate_a/single"
            "?client=gtx&sl=en&tl=tr&dt=t&q=")
WORKERS = 4
RETRIES = 4


def translate(sentence: str) -> str:
    req = urllib.request.Request(
        ENDPOINT + urllib.parse.quote(sentence),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            text = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
            if text:
                return text
        except Exception as err:  # ag hatasi / kota: bekle, tekrar dene
            last = err
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"ceviri alinamadi: {sentence!r} ({last})")


def load_cache() -> dict[str, str]:
    if CACHE.exists():
        with open(CACHE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_cache(cache: dict[str, str]) -> None:
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(cache.items())), fh, ensure_ascii=False, indent=1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with open(WORDS, encoding="utf-8") as fh:
        entries = json.load(fh)
    sentences = sorted({e["example"].strip() for e in entries if e.get("example")})
    cache = load_cache()
    missing = [s for s in sentences if s not in cache]
    print(f"ornek cumle: {len(sentences)}  cevrilmis: {len(sentences) - len(missing)}"
          f"  eksik: {len(missing)}")
    if "--check" in sys.argv or not missing:
        return 0

    done = failed = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(translate, s): s for s in missing}
        for fut in as_completed(futures):
            sentence = futures[fut]
            try:
                cache[sentence] = fut.result()
                done += 1
            except Exception as err:
                failed += 1
                print(f"  ! {err}")
            if (done + failed) % 100 == 0:
                save_cache(cache)
                print(f"  {done + failed}/{len(missing)}  ({time.time() - t0:.0f}s)")
    save_cache(cache)
    print(f"bitti: {done} cevrildi, {failed} basarisiz, {time.time() - t0:.0f}s")
    print(f"yazildi: {CACHE.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
