"""
Makes transparent cut-outs of the product photos, so the real products can be
placed into a user's room photo (everything shown is then something you can buy).

No AI model is used: Amazon packshots sit on a white background, so the
background is the near-white area that touches the edge of the photo.
Photos that are lifestyle scenes (a rug in a room, a wreath on a door) cannot be
cut out cleanly and are skipped; those products are not drawn into room pictures.

Reads   dataset/<theme>/Image/<ASIN>.jpg
Writes  dataset/<theme>/Cutout/<ASIN>.png   (+ dataset/cutouts.json)

Run from indar_app_backend/:
  uv run python scripts/make_cutouts.py            # skip cut-outs that exist
  uv run python scripts/make_cutouts.py --force
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
BG_TOL = 22               # a pixel within this of the edge colour counts as background
MIN_BORDER_PLAIN = 0.90   # share of the photo's outer ring that must be that colour
MIN_BG_BRIGHT = 150       # light backgrounds only; dark ones eat dark products
MIN_FG, MAX_FG = 0.05, 0.88  # the product must fill 5%..88% of the photo
MAX_SIDE = 700       # cut-outs are shrunk to this; plenty for a room picture


def cut_out(path: Path):
    """Return (RGBA cut-out, reason). Cut-out is None when the photo is not a clean packshot."""
    im = Image.open(path).convert("RGB")
    im.thumbnail((900, 900))
    arr = np.asarray(im)
    h, w = arr.shape[:2]

    # The background is the plain colour all round the edge of the photo. For a
    # packshot that is white (or cream / light grey); a lifestyle photo has a busy edge.
    ring = max(2, int(min(h, w) * 0.02))
    edge = np.concatenate([
        arr[:ring].reshape(-1, 3), arr[-ring:].reshape(-1, 3),
        arr[:, :ring].reshape(-1, 3), arr[:, -ring:].reshape(-1, 3),
    ]).astype(int)
    bg_color = np.median(edge, axis=0)
    near_edge = (np.abs(edge - bg_color).max(axis=1) <= BG_TOL)
    if near_edge.mean() < MIN_BORDER_PLAIN:
        return None, "background is not a plain colour"
    if bg_color.min() < MIN_BG_BRIGHT:
        return None, "background is too dark to cut out reliably"

    white = (np.abs(arr.astype(int) - bg_color).max(axis=2) <= BG_TOL)

    # Flood fill the background that touches the edge (pad by 1px so it connects all round).
    mask = Image.fromarray((white * 255).astype("uint8"), "L")
    padded = Image.new("L", (w + 2, h + 2), 255)
    padded.paste(mask, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128, thresh=0)
    bg = np.asarray(padded.crop((1, 1, w + 1, h + 1))) == 128

    fg_share = 1 - bg.mean()
    if fg_share < MIN_FG:
        return None, "product too small in photo"
    if fg_share > MAX_FG:
        return None, "product fills the whole photo"

    alpha = Image.fromarray(np.where(bg, 0, 255).astype("uint8"), "L")
    alpha = alpha.filter(ImageFilter.MinFilter(3))          # trim the white halo
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.9))     # soft edge
    out = im.convert("RGBA")
    out.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 20 else 0).getbbox()
    if not bbox:
        return None, "nothing left after cut-out"
    out = out.crop(bbox)
    out.thumbnail((MAX_SIDE, MAX_SIDE))
    return out, "ok"


def main():
    force = "--force" in sys.argv
    manifest, skipped = {}, []
    for img in sorted(DATASET.glob("*/Image/*.jpg")):
        theme, asin = img.parent.parent.name, img.stem
        dest_dir = img.parent.parent / "Cutout"
        dest = dest_dir / f"{asin}.png"
        if dest.exists() and not force:
            with Image.open(dest) as c:
                manifest[asin] = {"theme": theme, "w": c.width, "h": c.height}
            continue
        result, why = cut_out(img)
        if result is None:
            skipped.append((asin, theme, why))
            continue
        dest_dir.mkdir(exist_ok=True)
        result.save(dest, optimize=True)
        manifest[asin] = {"theme": theme, "w": result.width, "h": result.height}
    (DATASET / "cutouts.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"cut-outs: {len(manifest)}   skipped: {len(skipped)}")
    for asin, theme, why in skipped:
        print(f"  skipped {theme}/{asin}: {why}")


if __name__ == "__main__":
    main()
