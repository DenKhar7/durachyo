from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "C:/Windows/Fonts/times.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
MAX_SIDE = 800


type Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _font(size: int) -> Font:
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(text: str, font: Font, width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Greedy word wrap to width pixels, at most 4 lines."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines[:4]


def make_demotivator(image: bytes, title: str, subtitle: str | None = None) -> bytes:
    """Classic black-frame demotivator: picture in a thin white border, big caption, small caption."""
    pic = ImageOps.exif_transpose(Image.open(BytesIO(image))).convert("RGB")
    pic.thumbnail((MAX_SIDE, MAX_SIDE))
    w, h = pic.size
    pad = max(40, w // 10)
    gap, border = 8, 3
    width = w + pad * 2
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    title_font, sub_font = _font(max(28, width // 13)), _font(max(18, width // 26))
    blocks = [(_wrap(title, title_font, width - pad, probe), title_font)]
    if subtitle:
        blocks.append((_wrap(subtitle, sub_font, width - pad, probe), sub_font))
    line_h = {id(f): int(f.size * 1.25) if hasattr(f, "size") else 20 for _, f in blocks}
    text_h = sum(len(lines) * line_h[id(f)] for lines, f in blocks) + 10 * len(blocks)
    height = pad + h + gap * 2 + text_h + pad // 2 + 20
    canvas = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(canvas)
    x0, y0 = pad - gap, pad - gap
    draw.rectangle((x0, y0, x0 + w + gap * 2 - 1, y0 + h + gap * 2 - 1), outline="white", width=border)
    canvas.paste(pic, (pad, pad))
    y = pad + h + gap * 2 + 20
    for lines, font in blocks:
        for line in lines:
            tw = draw.textlength(line, font=font)
            draw.text(((width - tw) / 2, y), line, font=font, fill="white")
            y += line_h[id(font)]
        y += 10
    out = BytesIO()
    canvas.save(out, "JPEG", quality=88)
    return out.getvalue()
