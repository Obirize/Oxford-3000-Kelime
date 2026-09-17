"""
Oxford 3000 -> Turkce veri seti uretici.

Dort bagimsiz kaynagi birlestirir ve capraz dogrulama (konsensus) ile siralar:

  1. The_Oxford_3000.pdf   -> resmi kelime listesi + tur + CEFR seviyesi
  2. dict.zip              -> 1.46M kayitlik EN-TR sozluk (POS + kategori etiketli)
  3. ciwga.csv             -> TR karsilik + Ingilizce tanim + ornek cumle + es/zit anlam
  4. gist_tr.json          -> bagimsiz ucuncu TR gorus

Cikti: data/oxford3000.json

Calistirma:  py tools/build_dataset.py
"""

import collections
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
OUT = ROOT / "data" / "oxford3000.json"

# --- konsensus puanlari -------------------------------------------------------
# Bagimsiz kaynaklar daha agir basar; Tureng'in "Common Usage" katmani kuratorlu.
W_CIWGA = 5          # bagimsiz kaynak, kelime basina tek ve secilmis karsilik
W_GIST = 4           # bagimsiz kaynak, kelime basina tek karsilik
W_COMMON_USAGE = 3   # Tureng'in yaygin kullanim katmani
W_GENERAL = 1        # Tureng genel katman - tek basina yeterli degil

STRICT_MIN = 3       # KATI mod esigi: en az bir kuratorlu/bagimsiz kaynak onayi
REVIEW_MAX = 6       # bu puanin altindaki en iyi karsilik -> elle inceleme bayragi
MAX_ACCEPTED = 6     # katı listede en fazla bu kadar karsilik
MAX_ALTERNATIVES = 10

POS_PAT = (
    r"(?:n\.|v\.|adj\.|adv\.|prep\.|conj\.|pron\.|det\.|exclam\.|number"
    r"|modal v\.|auxiliary v\.|indefinite article|definite article|infinitive marker)"
)

# Tureng POS etiketleri -> Oxford POS etiketleri
POS_MAP = {
    "n.": "n.", "v.": "v.", "adj.": "adj.", "adv.": "adv.", "prep.": "prep.",
    "conj.": "conj.", "pron.": "pron.", "det.": "adj.", "exclam.": "interj.",
    "number": "n.", "modal v.": "v.", "auxiliary v.": "v.",
    "indefinite article": "adj.", "definite article": "adj.",
    "infinitive marker": "adv.",
}

# Elle gozden gecirilmis duzeltmeler (tools/overrides.json).
# Otomatik konsensus sonucunun uzerine yazar; katı modda hatali liste
# kullaniciya haksiz "yanlis" verdigi icin bu katman sart.
# Dilbilgisi kelimeleri icin Turkce aciklama (tools/notes.json).
# 'would' gibi kelimelerin tek basina karsiligi yoktur; kart cevaplandiktan
# sonra bu aciklama gosterilir.
with open(TOOLS / "notes.json", encoding="utf-8") as _fh:
    NOTES = {
        k.lower(): v
        for k, v in json.load(_fh).items()
        if not k.startswith("_")
    }

# Ornek cumlelerin Turkce cevirisi (tools/examples_tr.json,
# tools/translate_examples.py uretir). Yoksa alan bos kalir.
_EX_PATH = TOOLS / "examples_tr.json"
EXAMPLES_TR: dict[str, str] = {}
if _EX_PATH.exists():
    with open(_EX_PATH, encoding="utf-8") as _fh:
        EXAMPLES_TR = json.load(_fh)

with open(TOOLS / "overrides.json", encoding="utf-8") as _fh:
    MANUAL = {
        k.lower(): v
        for k, v in json.load(_fh).items()
        if not k.startswith("_")
    }

# Sozluk artigi / uygunsuz / cok niche karsiliklari katı listeden uzak tut.
# Oxford 3000 INGILIZ Ingilizcesi yazimini kullanir; Turkiye'de genelde Amerikan
# Ingilizcesi ogretildigi icin bu kelimeler "veri hatasi" gibi gorunuyor
# ('mum' = anne?!). Kullaniciya bildigi Amerikan formunu gosteriyoruz.
BRITISH_AMERICAN = {
    "analyse": "analyze", "behaviour": "behavior", "centre": "center",
    "colour": "color", "coloured": "colored", "defence": "defense",
    "dialogue": "dialog", "favour": "favor", "favourite": "favorite",
    "grey": "gray", "honour": "honor", "humour": "humor",
    "jewellery": "jewelry", "kilometre": "kilometer", "labour": "labor",
    "licence": "license", "maths": "math", "metre": "meter",
    "mum": "mom", "neighbour": "neighbor", "neighbourhood": "neighborhood",
    "offence": "offense", "practise": "practice", "programme": "program",
    "theatre": "theater", "traveller": "traveler", "tyre": "tire",
}

# Sozlukte rakam karsiligi bulunmayan sayi kelimeleri icin elle rakam formu.
DIGIT_FORMS = {
    "hundred": ["100"], "thousand": ["1000"],
    "million": ["1000000"], "billion": ["1000000000"],
    "first": ["1."], "second": ["2."], "third": ["3."],
    "fourth": ["4."], "fifth": ["5."],
    "half": ["1/2"], "quarter": ["1/4"],
    "twice": ["2 kez", "2 defa"], "dozen": ["12"],
}

NOISE = re.compile(
    r"(homoseksüel|eşcinsel|argo|kaba|müstehcen|orospu|fahişe|penis|vajina"
    r"|zool\.|bot\.|kim\.|tıp\.|mec\.|den\.|ask\.|huk\.)",
    re.IGNORECASE,
)


def tr_norm(s: str) -> str:
    """Turkce-duyarli normalizasyon (yalnizca tekrar eleme icin)."""
    s = s.replace("İ", "i").replace("I", "ı")
    return s.lower().strip(" .,;:")


# ---------------------------------------------------------------- 1) Oxford PDF
def parse_oxford_pdf(path: Path) -> list[dict]:
    """PDF'i kelime + tur listesi + CEFR seviyesine ayristirir.

    Satirlar bazen sarkiyor ('light (from the sun/a lamp) n.,' / 'adj. A2'),
    bu yuzden seviye ile bitmeyen satirlar bir sonrakiyle birlestirilir.
    """
    text = "\n".join(page.extract_text() for page in PdfReader(str(path)).pages)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    records, buf = [], ""
    for line in lines:
        if "Oxford University Press" in line or line.startswith("The Oxford 3000"):
            continue
        buf = f"{buf} {line}".strip() if buf else line
        if not re.search(r"[ABC][12]\s*$", buf):
            continue  # satir yarim, devamini bekle

        m = re.match(rf"^(.+?)\s+({POS_PAT}.*)$", buf)
        if m:
            word = m.group(1).replace("\xa0", " ").strip()
            word = re.sub(r"\s*\([^)]*\)", "", word)      # 'bear (deal with)' -> 'bear'
            word = re.sub(r"(\w)[123]$", r"\1", word)     # homograf: last1 -> last
            word = re.sub(r"\s+", " ", word).strip(" ,")
            levels = re.findall(r"[ABC][12]", m.group(2))
            if word and levels:
                records.append({
                    "word": word,
                    "pos": re.findall(POS_PAT, m.group(2)),
                    "cefr": min(levels),
                })
        buf = ""

    seen, unique = set(), []
    for rec in records:
        key = rec["word"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    return unique


# ------------------------------------------------------------- 2) buyuk sozluk
def load_big_dict(path: Path) -> dict[str, list[dict]]:
    raw = zipfile.ZipFile(path).read("dictionary.json").decode("utf-8")
    index = collections.defaultdict(list)
    for entry in json.loads(raw):
        word = (entry.get("word") or "").lower().strip()
        if word:
            index[word].append(entry)
    return index


# ----------------------------------------------------------- 3+4) yardimci kay.
def load_ciwga(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as fh:
        return {r["Word"].lower().strip(): r for r in csv.DictReader(fh)}


def load_gist(path: Path) -> dict[str, str]:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for entry in json.load(fh):
            en = (entry.get("en") or "").lower().strip()
            tr = (entry.get("tr") or "").strip()
            if en and tr and en not in out:
                out[en] = tr
    return out


# -------------------------------------------------------------- birlestirme
def score_translations(word: dict, big, ciwga, gist) -> tuple[collections.Counter, dict]:
    """Bir kelimenin tum TR adaylarini konsensus puanina gore puanlar."""
    key = word["word"].lower()
    wanted = {POS_MAP.get(p) for p in word["pos"]} - {None}
    scores, labels = collections.Counter(), {}

    def add(text: str, points: int):
        text = text.strip()
        if not text or len(text.split()) > 4:
            return
        norm = tr_norm(text)
        if not norm:
            return
        labels.setdefault(norm, text)
        scores[norm] += points

    for entry in big.get(key, []):
        cat = entry.get("category")
        if cat not in ("Common Usage", "General"):
            continue
        # Oxford kelimeyi hangi turde listeliyorsa o turdeki karsiliklari tut
        if wanted and entry.get("type") not in wanted:
            continue
        add(entry.get("tr") or "", W_COMMON_USAGE if cat == "Common Usage" else W_GENERAL)

    row = ciwga.get(key)
    if row:
        add(row.get("Turkish Translation") or "", W_CIWGA)
    if key in gist:
        add(gist[key], W_GIST)

    return scores, labels


def build_entry(idx: int, word: dict, big, ciwga, gist) -> dict:
    key = word["word"].lower()
    scores, labels = score_translations(word, big, ciwga, gist)
    ranked = [(labels[n], sc) for n, sc in scores.most_common()]

    manual = MANUAL.get(key)
    if manual:
        accepted, top_score = list(manual), 99
    else:
        accepted = [t for t, sc in ranked if sc >= STRICT_MIN and not NOISE.search(t)]
        if not accepted:  # Common Usage yok -> en iyi iki General karsiligina dus
            accepted = [t for t, _ in ranked if not NOISE.search(t)][:2]
        accepted = accepted[:MAX_ACCEPTED]
        top_score = ranked[0][1] if ranked else 0

    # Sayi kelimelerinde rakam yazmak ("sixty" -> "60") kelimeyi bilmektir;
    # sozluk bunu cogu zaman uzak anlam katmanina attigi icin geri cekiyoruz.
    digits = [t for t, _ in ranked if re.fullmatch(r"\d+", t.strip())]
    digits += [d for d in DIGIT_FORMS.get(key, []) if d not in digits]
    for digit in digits:
        if digit not in accepted:
            accepted.append(digit)

    chosen = {tr_norm(t) for t in accepted}
    alternatives = [t for t, _ in ranked if tr_norm(t) not in chosen][:MAX_ALTERNATIVES]

    row = ciwga.get(key, {})
    sources = sum([
        bool(big.get(key)),
        bool(row.get("Turkish Translation")),
        key in gist,
    ])

    return {
        "id": idx,
        "word": word["word"],
        "cefr": word["cefr"],
        "pos": word["pos"],
        "primary": accepted[0] if accepted else "",
        "accepted": accepted,          # KATI mod: dogru sayilan karsiliklar
        "alternatives": alternatives,  # sadece detay panelinde gosterilir
        "definition": (row.get("Definition") or "").strip(),
        "example": (row.get("Example Sentence") or "").strip(),
        "example_tr": EXAMPLES_TR.get((row.get("Example Sentence") or "").strip(), ""),
        "synonyms": (row.get("Synonyms") or "").strip(),
        "antonyms": (row.get("Antonyms") or "").strip(),
        "collocations": (row.get("Collocations") or "").strip(),
        "note": NOTES.get(key, ""),                 # Turkce dilbilgisi aciklamasi
        "us_form": BRITISH_AMERICAN.get(key, ""),   # Amerikan Ingilizcesi yazimi
        "sources": sources,            # kac bagimsiz kaynakta gorundu
        "confidence": top_score,       # konsensus puani
        "review": bool(not manual and (not accepted or top_score < REVIEW_MAX)),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    print("Oxford 3000 PDF ayristiriliyor...")
    words = parse_oxford_pdf(TOOLS / "oxford3000.pdf")
    print(f"  {len(words)} essiz kelime")

    print("Kaynaklar yukleniyor...")
    big = load_big_dict(TOOLS / "dict.zip")
    ciwga = load_ciwga(TOOLS / "ciwga.csv")
    gist = load_gist(TOOLS / "gist_tr.json")
    print(f"  buyuk sozluk: {len(big)} kelime | ciwga: {len(ciwga)} | gist: {len(gist)}")

    print("Birlestiriliyor (konsensus siralamasi)...")
    entries = [build_entry(i, w, big, ciwga, gist) for i, w in enumerate(words, 1)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)

    empty = [e["word"] for e in entries if not e["accepted"]]
    review = [e for e in entries if e["review"]]
    print()
    print(f"  yazildi: {OUT.relative_to(ROOT)}  ({len(entries)} kelime)")
    print(f"  CEFR: {dict(collections.Counter(e['cefr'] for e in entries).most_common())}")
    print(f"  ort. kabul edilen karsilik: {sum(len(e['accepted']) for e in entries)/len(entries):.1f}")
    print(f"  ornek cumlesi olan: {sum(1 for e in entries if e['example'])}")
    print(f"  kabul listesi bos: {len(empty)} {empty[:10]}")
    print(f"  ELLE INCELEME GEREKEN: {len(review)} (%{100*len(review)/len(entries):.1f})")
    print(f"  dilbilgisi aciklamasi olan: {sum(1 for e in entries if e['note'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
