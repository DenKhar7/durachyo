from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps

# first one that exists wins: linux in docker, then windows for local runs
FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "C:/Windows/Fonts/times.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
MAX_SIDE = 800
MAX_LINES = 4
FRAME_GAP = 8  # between the picture and the white frame
FRAME_WIDTH = 3
CAPTION_GAP = 10

type Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _font(size: int) -> Font:
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(text: str, font: Font, width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        longer = f"{line} {word}".strip()
        if line and draw.textlength(longer, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = longer
    if line:
        lines.append(line)
    return lines[:MAX_LINES]


def make_demotivator(image: bytes, title: str, subtitle: str | None = None) -> bytes:
    """The classic: black background, picture in a thin white frame, big caption, small caption."""
    pic = ImageOps.exif_transpose(Image.open(BytesIO(image))).convert("RGB")
    pic.thumbnail((MAX_SIDE, MAX_SIDE))
    w, h = pic.size
    pad = max(40, w // 10)
    width = w + pad * 2

    # wrap the captions first, the canvas height depends on how many lines they take
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    captions: list[tuple[list[str], Font, int]] = []
    for text, size in ((title, max(28, width // 13)), (subtitle, max(18, width // 26))):
        if text:
            font = _font(size)
            captions.append((_wrap(text, font, width - pad, measure), font, int(size * 1.25)))
    text_height = sum(len(lines) * line_height + CAPTION_GAP for lines, _, line_height in captions)

    text_top = pad + h + FRAME_GAP * 2 + 20
    canvas = Image.new("RGB", (width, text_top + text_height + pad // 2), "black")
    draw = ImageDraw.Draw(canvas)
    left = top = pad - FRAME_GAP
    frame = (left, top, left + w + FRAME_GAP * 2 - 1, top + h + FRAME_GAP * 2 - 1)
    draw.rectangle(frame, outline="white", width=FRAME_WIDTH)
    canvas.paste(pic, (pad, pad))

    y = text_top
    for lines, font, line_height in captions:
        for line in lines:
            x = (width - draw.textlength(line, font=font)) / 2
            draw.text((x, y), line, font=font, fill="white")
            y += line_height
        y += CAPTION_GAP

    out = BytesIO()
    canvas.save(out, "JPEG", quality=88)
    return out.getvalue()
