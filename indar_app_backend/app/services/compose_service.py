"""
Puts REAL catalog products into the user's own room photo.

Nothing here is drawn by an AI model, so everything you see in the picture is a
product that is in the Amazon cart. Each product has a transparent cut-out
(made by scripts/make_cutouts.py); this module places the cut-outs on the right
part of the room: wall items on the back wall, hanging items from the ceiling on
a string, floor items on the floor with a soft contact shadow.
"""
import io
import re
import random
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

DATASET = Path(__file__).resolve().parents[2] / "dataset"
MAX_SIDE = 1280
_FLAT = re.compile(r"\b(rug|mat|mats|carpet|doormat|rangoli|sticker)\b", re.I)
# Catalog items have no real dimensions, so small things are recognised by name and
# drawn small (a tree topper must not become as big as a person).
_SMALL = re.compile(r"\b(topper|ornaments?|tealights?|candles?|diyas?|mini|baubles?|bulbs?|stars?|figurine|statue|doll)\b", re.I)

_index: Optional[dict] = None


def cutout_index() -> dict:
    """ASIN -> path of its transparent cut-out (loaded once)."""
    global _index
    if _index is None:
        _index = {p.stem: p for p in DATASET.glob("*/Cutout/*.png")}
    return _index


def has_cutout(asin: Optional[str]) -> bool:
    return bool(asin) and asin in cutout_index()


def _floor_line(room: Image.Image) -> float:
    """Where the floor meets the back wall, as a fraction of the picture height."""
    g = np.asarray(room.convert("L").resize((200, 200)), dtype=float)
    profile = g[:, 30:170].mean(axis=1)
    profile = np.convolve(profile, np.ones(3) / 3, mode="same")
    grad = np.abs(np.diff(profile))
    lo, hi = int(0.45 * 199), int(0.86 * 199)
    seg = grad[lo:hi]
    if seg.size == 0 or seg.max() < 2.5:
        return 0.68
    return (lo + int(seg.argmax()) + 1) / 200


def _fit(cut: Image.Image, w: int, h: int) -> Image.Image:
    return cut.resize((max(4, w), max(4, h)), Image.LANCZOS)


def _shade(cut: Image.Image, factor: float) -> Image.Image:
    """Match the product's brightness to the room's light."""
    r, g, b, a = cut.split()
    rgb = ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(factor)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def _drop_shadow(canvas: Image.Image, cut: Image.Image, x: int, y: int, strength: float = 0.32):
    alpha = cut.split()[3].point(lambda v: int(v * strength))
    blob = Image.new("RGBA", cut.size, (20, 15, 10, 0))
    blob.putalpha(alpha)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(blob, (x + max(3, cut.width // 40), y + max(4, cut.height // 30)), blob)
    layer = layer.filter(ImageFilter.GaussianBlur(max(3, cut.width // 55)))
    canvas.alpha_composite(layer)


def _contact_shadow(canvas: Image.Image, cx: int, base_y: int, width: int):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hh = max(8, int(width * 0.09))
    d.ellipse([cx - int(width * 0.48), base_y - hh // 2, cx + int(width * 0.48), base_y + hh], fill=(15, 10, 5, 120))
    layer = layer.filter(ImageFilter.GaussianBlur(max(4, width // 28)))
    canvas.alpha_composite(layer)


def _paste(canvas: Image.Image, cut: Image.Image, x: int, y: int):
    canvas.paste(cut, (x, y), cut)


def compose_room(room_bytes: bytes, items: list[dict]) -> tuple[bytes, list[dict]]:
    """
    items: [{"asin", "category" (Wall|Hanging|Floor), "name"}] - only products with a cut-out.
    Returns (jpeg bytes, placements). A placement is {"asin", "category", "cx", "cy", "w", "h"}
    with centre and size as fractions of the picture (cx, cy from the top-left).
    """
    room = Image.open(io.BytesIO(room_bytes)).convert("RGB")
    room.thumbnail((MAX_SIDE, MAX_SIDE))
    W, H = room.size
    canvas = room.convert("RGBA")
    y_floor = int(_floor_line(room) * H)
    lum = float(np.asarray(room.convert("L")).mean())
    light = min(1.06, max(0.84, lum / 175))
    rng = random.Random(sum(room_bytes[:2000]))  # same room -> same layout

    def load(asin):
        return Image.open(cutout_index()[asin]).convert("RGBA")

    wall = [i for i in items if i["category"] == "Wall"]
    hang = [i for i in items if i["category"] == "Hanging"]
    floor = [i for i in items if i["category"] == "Floor"]
    placed: list[dict] = []
    draw_list = []  # (depth, callable)

    # ── wall: spread along the back wall, between the ceiling and the floor line
    span_l, span_r = 0.22 * W, 0.78 * W
    for i, it in enumerate(wall):
        cut = load(it["asin"])
        a = cut.width / cut.height
        slot = (span_r - span_l) / max(1, len(wall))
        # Wall art starts below 0.30H so hanging items (above that) never cover it.
        zone_top, zone_bottom = 0.31 * H, y_floor - 0.05 * H
        h = int(min(0.30 * H, 0.86 * slot / a, zone_bottom - zone_top))
        w = int(h * a)
        cx = int(span_l + slot * (i + 0.5))
        cy = int((zone_top + zone_bottom) / 2)
        x, y = cx - w // 2, cy - h // 2
        c = _shade(_fit(cut, w, h), light)
        draw_list.append((0, lambda c=c, x=x, y=y: (_drop_shadow(canvas, c, x, y), _paste(canvas, c, x, y))))
        placed.append({**it, "cx": cx / W, "cy": cy / H, "w": w / W, "h": h / H})

    # ── hanging: from the ceiling on a string
    for i, it in enumerate(hang):
        cut = load(it["asin"])
        a = cut.width / cut.height
        n = max(1, len(hang))
        cx = int(W * (0.14 + 0.72 * (i + 0.5) / n))
        # Hanging items stay in the top band (they end above 0.30H, where wall art starts).
        w = int(min(0.15 * W, 0.19 * H * a))
        h = int(w / a)
        top = int(H * (0.03 + 0.04 * (i % 2)) + rng.randint(-4, 4))
        x = cx - w // 2
        c = _shade(_fit(cut, w, h), light)

        def hang_draw(c=c, x=x, top=top, cx=cx):
            d = ImageDraw.Draw(canvas)
            d.line([(cx, 0), (cx, top + 6)], fill=(80, 70, 60, 230), width=max(1, W // 700))
            _drop_shadow(canvas, c, x, top, 0.28)
            _paste(canvas, c, x, top)

        draw_list.append((1, hang_draw))
        placed.append({**it, "cx": cx / W, "cy": (top + h / 2) / H, "w": w / W, "h": h / H})

    # ── floor: in front of the back wall, bigger as they get closer to the camera
    n = max(1, len(floor))
    for i, it in enumerate(floor):
        cut = load(it["asin"])
        a = cut.width / cut.height
        # Lying flat only if the picture is roughly square or wide; a tall picture of
        # stacked mats is drawn standing.
        flat = bool(_FLAT.search(it.get("name", ""))) and a >= 0.7
        small = bool(_SMALL.search(it.get("name", ""))) and not flat
        cx = int(W * (0.24 + 0.52 * (i + 0.5) / n) + rng.randint(-int(0.02 * W), int(0.02 * W)))
        base = int(min(H * 0.96, y_floor + H * (0.13 + 0.07 * (i % 2))))
        if flat:
            # Lying on the floor: wide, and squashed vertically for perspective.
            w = int(min(0.30 * W, 0.62 * H * a))
            h = int(max(10, min(w / a * 0.42, 0.17 * H)))
            y = base - h
        else:
            h = int(min((0.13 if small else 0.30) * H, (base - 0.18 * H)))
            w = int(h * a)
            if w > 0.22 * W:
                w = int(0.22 * W)
                h = int(w / a)
            y = base - h
        x = cx - w // 2
        c = _shade(_fit(cut, w, h), light)

        def floor_draw(c=c, x=x, y=y, cx=cx, base=base, w=w, flat=flat):
            if not flat:
                _contact_shadow(canvas, cx, base, w)
            else:
                _drop_shadow(canvas, c, x, y, 0.22)
            _paste(canvas, c, x, y)

        draw_list.append((2 + base / H, floor_draw))
        placed.append({**it, "cx": cx / W, "cy": (y + h / 2) / H, "w": w / W, "h": h / H})

    for _, fn in sorted(draw_list, key=lambda t: t[0]):
        fn()

    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue(), placed
