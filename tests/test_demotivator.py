from io import BytesIO

from PIL import Image

from bot.demotivator import make_demotivator


def test_demotivator_frames_picture_with_caption():
    src = BytesIO()
    Image.new("RGB", (300, 200), "red").save(src, "PNG")
    out = Image.open(BytesIO(make_demotivator(src.getvalue(), "когда добавили сюда сглыпчурку", "normalno")))
    assert out.format == "JPEG"
    assert out.width > 300 and out.height > 200
    assert out.getpixel((2, 2)) == (0, 0, 0) or sum(out.getpixel((2, 2))) < 30
