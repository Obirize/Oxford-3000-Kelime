"""Uygulama logosunu (ikon) uretir.

Tasarim: koyu lacivert yuvarlak kare uzerinde beyaz bir kelime karti; kartin
uzerinde "EN" ve altinda yesil bir onay isareti.

IKI AYRI CIZIM
    Kucuk boyutlarda (<= 24 px) kart/cizgi/rozet ayrintisi lapaya doner; o
    boyutlarda yalnizca lacivert zemin + buyuk "EN" cizilir. Buyuk boyutlarda
    tam tasarim kullanilir.

BOYUTLAR
    Windows, ekran olceklendirmesine gore FARKLI boyutlar ister:
        %100 -> 16    %125 -> 20    %150 -> 24    %200 -> 32
    Istedigi boyut ikonda yoksa en yakinini esnetir ve ikon BULANIK gorunur.
    (%125 ekranda gorev cubugunda yasanan tam olarak buydu: 20 px yoktu.)
    Bu yuzden asagidaki liste Windows'un isteyebilecegi tum boyutlari icerir.

    py tools/make_icon.py     ->  assets/app.ico  +  assets/logo.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

BG_TOP = (37, 62, 128)      # lacivert (ust)
BG_BOTTOM = (24, 38, 82)    # lacivert (alt)
CARD = (247, 249, 253)
CARD_EDGE = (203, 213, 233)
INK = (27, 39, 71)
ACCENT = (91, 140, 255)
OK = (62, 207, 142)

# Buyukten kucuge; Windows'un isteyebilecegi her boyut burada olmali.
SIZES = [256, 128, 96, 64, 48, 40, 32, 24, 20, 16]

# Bu boyugun altinda ayrintili cizim okunmuyor; sade bicime geciyoruz.
SMALL_MAX = 24


def _font(size: int):
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "calibrib.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill,
                           outline=outline, width=width)


def render_small(size: int) -> Image.Image:
    """16-24 px icin sade bicim: lacivert zemin + buyuk 'EN'.

    Kucuk boyutta kart, cizgi ve rozet birkac piksele siktigi icin lekeye
    donuyordu; burada tek bir okunakli oge birakiyoruz.
    """
    scale = 16
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    bg = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(s):
        t = y / max(s - 1, 1)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        bd.line([(0, y), (s, y)], fill=color + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1],
                                           radius=int(s * 0.20), fill=255)
    img.paste(bg, (0, 0), mask)

    text = "EN"
    font = _font(int(s * 0.62))
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text(((s - tw) / 2 - box[0], (s - th) / 2 - box[1]), text,
           font=font, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def render(size: int) -> Image.Image:
    """Ikonu yuksek cozunurlukte cizip kucultur (kenarlar yumusak olsun)."""
    if size <= SMALL_MAX:
        return render_small(size)
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # arka plan: dikey gecisli yuvarlak kare
    bg = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(s):
        t = y / max(s - 1, 1)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        bd.line([(0, y), (s, y)], fill=color + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1],
                                           radius=int(s * 0.22), fill=255)
    img.paste(bg, (0, 0), mask)

    # arka kart (hafif kaydirilmis, derinlik hissi)
    m = s * 0.17
    _rounded(d, [m + s * 0.06, m - s * 0.02,
                 s - m + s * 0.06, s - m - s * 0.02],
             int(s * 0.05), (255, 255, 255, 60))

    # on kart
    card = [m, m + s * 0.02, s - m, s - m + s * 0.02]
    _rounded(d, card, int(s * 0.05), CARD + (255,),
             outline=CARD_EDGE + (255,), width=max(int(s * 0.006), 1))

    # kart uzerindeki "EN" yazisi
    text = "EN"
    font = _font(int(s * 0.30))
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    cx = (card[0] + card[2]) / 2
    cy = (card[1] + card[3]) / 2 - s * 0.055
    d.text((cx - tw / 2 - box[0], cy - th / 2 - box[1]), text, font=font, fill=INK)

    # altta ince mavi cizgi (satir hissi)
    line_y = cy + s * 0.135
    d.line([(cx - s * 0.13, line_y), (cx + s * 0.13, line_y)],
           fill=ACCENT + (255,), width=max(int(s * 0.022), 1))

    # sag altta yesil onay rozeti
    r = s * 0.155
    bx, by = s - m - r * 0.35, s - m - r * 0.15
    d.ellipse([bx - r, by - r, bx + r, by + r], fill=OK + (255,),
              outline=(255, 255, 255, 255), width=max(int(s * 0.012), 1))
    w = max(int(s * 0.030), 1)
    d.line([(bx - r * 0.42, by), (bx - r * 0.08, by + r * 0.36)],
           fill=(255, 255, 255, 255), width=w)
    d.line([(bx - r * 0.08, by + r * 0.36), (bx + r * 0.45, by - r * 0.38)],
           fill=(255, 255, 255, 255), width=w)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    images = [render(n) for n in SIZES]
    ico = ASSETS / "app.ico"
    images[0].save(ico, format="ICO",
                   sizes=[(n, n) for n in SIZES], append_images=images[1:])
    png = ASSETS / "logo.png"
    images[0].save(png, format="PNG")

    # onizleme: tum boyutlar yan yana
    preview = Image.new("RGBA", (sum(SIZES) + 20 * len(SIZES), 296), (18, 21, 28, 255))
    x = 10
    for img, n in zip(images, SIZES):
        preview.paste(img, (x, (256 - n) // 2 + 10), img)
        # boyut etiketi: hangi olceklendirmede hangisinin kullanildigi gorunsun
        ImageDraw.Draw(preview).text((x, 276), f"{n}", fill=(140, 150, 170, 255),
                                     font=_font(14))
        x += n + 20
    preview.save(ASSETS / "icon_preview.png")

    print(f"yazildi: {ico.relative_to(ROOT)}  ({', '.join(str(n) for n in SIZES)} px)")
    print(f"yazildi: {png.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
