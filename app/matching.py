"""Turkce-duyarli cevap eslestirme.

KATI mod: yalnizca kelimenin ana anlami ve yakin es anlamlilari dogru sayilir
(veri setindeki `accepted` listesi). Sozlugun uzak/niche anlamlari (`alternatives`)
dogru kabul EDILMEZ - sadece detay panelinde bilgi olarak gosterilir.

Buradaki tolerans yazim hatasina yoneliktir, anlama degil:
  * Turkce karakter serbestligi:  'sarki'  = 'şarkı'
  * mastar eki toleransi:         'terk et' = 'terk etmek'
  * ek/onek gurultusu:            '-meli'   = 'meli'
  * 1 harflik yazim hatasi:       'telafuz etmek' ~ 'telaffuz etmek'  (uyarili)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Turkce buyuk/kucuk harf donusumu Python'un varsayilanindan farkli:
# 'I'.lower() -> 'i' yanlis, 'ı' olmali.
_LOWER_MAP = str.maketrans({"I": "ı", "İ": "i", "Ş": "ş", "Ğ": "ğ",
                            "Ü": "ü", "Ö": "ö", "Ç": "ç"})
_FOLD_MAP = str.maketrans({"ş": "s", "ı": "i", "ğ": "g",
                           "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")

# Cevabin basindaki/sonundaki anlam tasimayan doldurma sozcukleri
_FILLER = {"bir", "the", "to", "olan", "etmek", "olmak"}

VERDICT_CORRECT = "correct"       # tam dogru
VERDICT_TYPO = "typo"             # dogru sayildi ama yazim hatali
VERDICT_WRONG = "wrong"           # yanlis
VERDICT_NOT_ACCEPTED = "other"    # gecerli bir sozluk anlami ama katı modda kabul yok


@dataclass
class Result:
    verdict: str
    matched: str = ""      # eslesen kabul edilen karsilik
    hint: str = ""         # kullaniciya gosterilecek kisa aciklama

    @property
    def is_correct(self) -> bool:
        return self.verdict in (VERDICT_CORRECT, VERDICT_TYPO)


def tr_lower(text: str) -> str:
    return text.translate(_LOWER_MAP).lower()


def normalize(text: str, fold: bool = True) -> str:
    """Karsilastirma icin kanonik bicime indirger."""
    text = unicodedata.normalize("NFC", text)
    text = tr_lower(text.strip())
    text = text.replace("’", "'").replace("`", "'")
    text = _PUNCT.sub(" ", text)
    text = _SPACE.sub(" ", text).strip()
    if fold:
        text = text.translate(_FOLD_MAP)
    return text


# Turkce sondan eklemeli bir dildir: "yarı" ile "yarısı", "kitap" ile "kitabı"
# ayni kelimedir. Kullanicinin ekli yazmasi yanlis sayilmamali. Asagidaki ekler
# UZUNDAN KISAYA denenir; kok en az MIN_STEM harf kalmalidir ki "yazı" -> "yaz"
# gibi farkli kelimelere dusmeyelim.
_SUFFIXES = (
    "larindan", "lerinden", "larinda", "lerinde", "larini", "lerini",
    "larin", "lerin", "lari", "leri", "lar", "ler",
    "sindan", "sinden", "sinda", "sinde", "sini", "sine", "sinin",
    "ndan", "nden", "tan", "ten", "dan", "den",
    "nda", "nde", "da", "de", "ta", "te",
    "nin", "nin", "in", "un", "un",
    "si", "su", "si", "yi", "yu", "ye", "ya",
    "i", "u", "a", "e",
)
MIN_STEM = 2

# Unsuz yumusamasi: ek alinca kitap->kitabı, ağaç->ağacı olur. Eki soyduktan
# sonra sert halini de deniyoruz. (fold acikken ç/ğ zaten c/g'ye inmis olur)
_HARDEN = {"b": "p", "c": "c", "d": "t", "g": "k"}
_VOWELS = "aeiouıöü"


def _strip_suffix(text: str) -> set[str]:
    """Turkce cekim eklerini soyup olasi kokleri dondurur."""
    out = set()
    for suffix in _SUFFIXES:
        if not text.endswith(suffix):
            continue
        stem = text[: -len(suffix)]
        if len(stem) < MIN_STEM:
            continue
        out.add(stem)
        # unsuz yumusamasini geri al:  'kitab' -> 'kitap'
        if stem and stem[-1] in _HARDEN:
            out.add(stem[:-1] + _HARDEN[stem[-1]])
        # unlu dusmesi:  'ism' -> 'isim',  'agz' -> 'agiz'
        if (len(stem) >= 3 and stem[-1] not in _VOWELS
                and stem[-2] not in _VOWELS):
            for vowel in "iıuü":
                out.add(stem[:-1] + vowel + stem[-1])
    return out


def _stems(text: str) -> set[str]:
    """Bir karsiligin kabul edilebilir govde varyantlarini uretir."""
    out = {text}
    # mastar eki:  'terk etmek' -> 'terk et'
    for suffix in ("mek", "mak", "me", "ma"):
        if text.endswith(suffix) and len(text) > len(suffix) + 2:
            out.add(text[: -len(suffix)].strip())
    # 'yapmak' -> 'yap'
    out.add(re.sub(r"(mek|mak)$", "", text).strip())
    # cekim ekleri: 'yarisi' -> 'yari',  'kitabi' -> 'kitab'
    for base in list(out):
        out |= _strip_suffix(base)
    # bas/son doldurma sozcukleri:  'bir kitap' -> 'kitap'
    parts = text.split()
    if len(parts) > 1:
        if parts[0] in _FILLER:
            out.add(" ".join(parts[1:]))
        if parts[-1] in _FILLER:
            out.add(" ".join(parts[:-1]))
    # bosluk farki anlam farki degildir:  'onbes' = 'on bes', 'havayolu' = 'hava yolu'
    out |= {s.replace(" ", "") for s in list(out) if " " in s}
    return {s for s in out if s}


def _levenshtein(a: str, b: str, limit: int = 2) -> int:
    """Kisitli Levenshtein mesafesi; limit asilirsa limit+1 doner."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def check(
    answer: str,
    accepted: list[str],
    alternatives: list[str] | None = None,
    *,
    typo_tolerance: bool = True,
    fold_turkish: bool = True,
) -> Result:
    """Kullanicinin cevabini kabul listesine karsi degerlendirir."""
    raw = (answer or "").strip()
    if not raw:
        return Result(VERDICT_WRONG)

    given = normalize(raw, fold=fold_turkish)
    if not given:
        return Result(VERDICT_WRONG)
    given_variants = _stems(given)

    # 1) Tam eslesme (govde varyantlari dahil)
    for target in accepted:
        norm = normalize(target, fold=fold_turkish)
        if given_variants & _stems(norm):
            return Result(VERDICT_CORRECT, matched=target)

    # 2) Virgul/slash ile birden fazla karsilik yazilmis olabilir: hepsi gecerli mi?
    pieces = [p for p in re.split(r"[,/;]| ve ", raw) if p.strip()]
    if len(pieces) > 1:
        for piece in pieces:
            sub = check(piece, accepted, alternatives,
                        typo_tolerance=typo_tolerance, fold_turkish=fold_turkish)
            if sub.verdict == VERDICT_CORRECT:
                return sub

    # 3) Yazim hatasi toleransi (yalnizca yeterince uzun cevaplarda)
    if typo_tolerance and len(given) >= 5:
        for target in accepted:
            norm = normalize(target, fold=fold_turkish)
            for variant in _stems(norm):
                if len(variant) >= 5 and _levenshtein(given, variant, 1) <= 1:
                    return Result(
                        VERDICT_TYPO,
                        matched=target,
                        hint=f"Yazım hatası — doğrusu: {target}",
                    )

    # 4) Sozlukte var ama KATI modda kabul edilmiyor -> ayri geri bildirim
    for target in alternatives or []:
        norm = normalize(target, fold=fold_turkish)
        if given_variants & _stems(norm):
            return Result(
                VERDICT_NOT_ACCEPTED,
                matched=target,
                hint=f"“{target}” bu kelimenin uzak bir anlamı — burada ana anlamı istiyoruz.",
            )

    return Result(VERDICT_WRONG)


# ----------------------------------------------------------- ters yon (TR -> EN)
# Ingilizce cevap icin Turkce ek soyma KULLANILMAZ: 'care' -> 'car' gibi
# yanlis eslesmelere yol acar. Ingilizcede tolerans yalnizca:
#   * buyuk/kucuk harf ve noktalama            'Don't' = 'dont'
#   * bastaki mastar/tanimlik                   'to run' = 'run', 'a car' = 'car'
#   * 1 harflik yazim hatasi (uyarili)          'recieve' ~ 'receive'
_EN_LEAD = ("to ", "a ", "an ", "the ")


def normalize_en(text: str) -> str:
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = text.replace("’", "'").replace("`", "'").replace("'", "")
    text = _PUNCT.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def _en_variants(text: str) -> set[str]:
    out = {text}
    for lead in _EN_LEAD:
        if text.startswith(lead) and len(text) > len(lead):
            out.add(text[len(lead):])
    return {s for s in out if s}


def check_en(answer: str, targets: list[str], *,
             typo_tolerance: bool = True) -> Result:
    """Ingilizce cevabi hedef yazimlara karsi degerlendirir (ters yon)."""
    raw = (answer or "").strip()
    if not raw:
        return Result(VERDICT_WRONG)
    given = normalize_en(raw)
    if not given:
        return Result(VERDICT_WRONG)
    given_variants = _en_variants(given)

    # 'a, an' gibi virgullu hedefler ayri ayri gecerlidir
    flat: list[str] = []
    for target in targets:
        flat.extend(t.strip() for t in target.split(",") if t.strip())

    for target in flat:
        if given_variants & _en_variants(normalize_en(target)):
            return Result(VERDICT_CORRECT, matched=target)

    pieces = [p for p in re.split(r"[,/;]", raw) if p.strip()]
    if len(pieces) > 1:
        for piece in pieces:
            sub = check_en(piece, targets, typo_tolerance=typo_tolerance)
            if sub.verdict == VERDICT_CORRECT:
                return sub

    if typo_tolerance and len(given) >= 5:
        for target in flat:
            for variant in _en_variants(normalize_en(target)):
                if len(variant) >= 5 and _levenshtein(given, variant, 1) <= 1:
                    return Result(VERDICT_TYPO, matched=target,
                                  hint=f"Yazım hatası — doğrusu: {target}")

    return Result(VERDICT_WRONG)
