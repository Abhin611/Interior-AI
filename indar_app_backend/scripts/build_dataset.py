"""
Rebuilds the product dataset (photos + AR models) from Dataset1.xlsx.

For every product it:
  1. downloads the main photo from its Amazon.in listing (by ASIN)
  2. generates a .glb 3D model with that photo on it, shaped by category:
       Wall    -> framed panel
       Hanging -> card hanging from a string
       Floor   -> standee on a round base

Output (committed to the repo, so nobody else's storage is needed):
  dataset/<theme>/Image/<ASIN>.jpg
  dataset/<theme>/3d/<ASIN>.glb

Run from indar_app_backend/:
  uv run python scripts/build_dataset.py            # skip files that already exist
  uv run python scripts/build_dataset.py --force    # rebuild everything
"""
import io
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import openpyxl
import trimesh
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
EXCEL = ROOT / "Dataset1.xlsx"
OUT = ROOT / "dataset"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}
IMG_PATTERNS = [
    r'data-old-hires="(https://[^"]+)"',
    r'"hiRes":"(https://[^"]+)"',
    r'"large":"(https://[^"]+)"',
    r'<meta property="og:image" content="(https://[^"]+)"',
]


def clean(v) -> str:
    return re.sub(r"[\t‎​\xa0\s]+", " ", str(v or "")).strip()


def load_products():
    ws = openpyxl.load_workbook(EXCEL).active
    for row in ws.iter_rows(min_row=2, values_only=True):
        name, asin, _photo, _asset, _rating, price, ptype, theme = row[:8]
        asin = re.sub(r"\s", "", clean(asin))
        if name and asin and price:
            yield {"asin": asin, "name": clean(name), "category": clean(ptype), "theme": clean(theme)}


# ── Photos ────────────────────────────────────────────────────────────────

def fetch_photo(client: httpx.Client, asin: str) -> Image.Image | None:
    resp = client.get(f"https://www.amazon.in/dp/{asin}")
    if resp.status_code != 200 or "captcha" in resp.text.lower()[:5000]:
        return None
    for pat in IMG_PATTERNS:
        m = re.search(pat, resp.text)
        if m:
            img = client.get(m.group(1).replace("\\/", "/"))
            if img.status_code == 200:
                return Image.open(io.BytesIO(img.content)).convert("RGB")
    return None


def placeholder_photo(name: str) -> Image.Image:
    """Used only when a listing has no photo (e.g. product removed from Amazon)."""
    img = Image.new("RGB", (800, 800), (236, 230, 220))
    d = ImageDraw.Draw(img)
    words, lines, line = name.split(), [], ""
    for w in words:
        if len(line) + len(w) > 22:
            lines.append(line)
            line = ""
        line += w + " "
    lines.append(line)
    for i, ln in enumerate(lines[:8]):
        d.text((60, 300 + i * 30), ln, fill=(60, 50, 40))
    return img


def square(img: Image.Image, size=800) -> Image.Image:
    img = img.copy()
    img.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return canvas


# ── 3D models ─────────────────────────────────────────────────────────────

def textured_plane(img: Image.Image, w: float, h: float) -> trimesh.Trimesh:
    """Double-sided rectangle (in the XY plane, facing +Z) showing the photo."""
    x, y = w / 2, h / 2
    v = np.array([[-x, -y, 0], [x, -y, 0], [x, y, 0], [-x, y, 0]], dtype=float)
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    verts = np.vstack([v, v])
    uv_back = uv.copy()
    uv_back[:, 0] = 1 - uv_back[:, 0]  # mirror so the photo reads correctly from behind
    uvs = np.vstack([uv, uv_back])
    faces = np.array([[0, 1, 2], [0, 2, 3], [6, 5, 4], [7, 6, 4]])
    tex = img.resize((512, 512))
    visual = trimesh.visual.TextureVisuals(uv=uvs, image=tex)
    return trimesh.Trimesh(vertices=verts, faces=faces, visual=visual, process=False)


def solid(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=[*rgb, 255])
    return mesh


def build_model(img: Image.Image, category: str) -> trimesh.Scene:
    scene = trimesh.Scene()
    aspect = img.height / img.width
    cat = category.lower()

    if cat == "wall":
        w, h = 0.5, 0.5 * aspect
        photo = textured_plane(img, w, h)
        photo.apply_translation([0, 0, 0.012])
        frame = solid(trimesh.creation.box([w + 0.04, h + 0.04, 0.02]), (90, 62, 40))
        scene.add_geometry(frame, node_name="frame")
        scene.add_geometry(photo, node_name="photo")

    elif cat == "hanging":
        w, h = 0.3, 0.3 * aspect
        photo = textured_plane(img, w, h)
        string = solid(trimesh.creation.cylinder(radius=0.003, height=0.4), (200, 170, 90))
        # cylinders are created along Z; stand it upright along Y above the card
        string.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        string.apply_translation([0, h / 2 + 0.2, 0])
        scene.add_geometry(photo, node_name="photo")
        scene.add_geometry(string, node_name="string")

    else:  # Floor
        w, h = 0.4, 0.4 * aspect
        photo = textured_plane(img, w, h)
        photo.apply_translation([0, h / 2 + 0.02, 0])
        base = solid(trimesh.creation.cylinder(radius=w * 0.45, height=0.02), (70, 70, 70))
        base.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        base.apply_translation([0, 0.01, 0])
        scene.add_geometry(base, node_name="base")
        scene.add_geometry(photo, node_name="photo")

    return scene


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    force = "--force" in sys.argv
    products = list(load_products())
    stats = {"photo": 0, "placeholder": 0, "skipped": 0}

    if "--models-only" in sys.argv:  # rebuild .glb files from the saved photos
        for p in products:
            img_path = OUT / p["theme"] / "Image" / f"{p['asin']}.jpg"
            if img_path.exists():
                glb_path = OUT / p["theme"] / "3d" / f"{p['asin']}.glb"
                glb_path.parent.mkdir(parents=True, exist_ok=True)
                build_model(Image.open(img_path).convert("RGB"), p["category"]).export(glb_path)
        print("Rebuilt models from saved photos.")
        return

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for i, p in enumerate(products, 1):
            img_path = OUT / p["theme"] / "Image" / f"{p['asin']}.jpg"
            glb_path = OUT / p["theme"] / "3d" / f"{p['asin']}.glb"
            if img_path.exists() and glb_path.exists() and not force:
                stats["skipped"] += 1
                continue
            img_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.parent.mkdir(parents=True, exist_ok=True)

            img = None
            if img_path.exists() and not force:
                img = Image.open(img_path).convert("RGB")
            else:
                for attempt in range(3):
                    try:
                        img = fetch_photo(client, p["asin"])
                    except httpx.HTTPError:
                        img = None
                    if img:
                        break
                    time.sleep(4 * (attempt + 1))
                time.sleep(1.5)  # be polite to Amazon

            if img:
                stats["photo"] += 1
            else:
                img = placeholder_photo(p["name"])
                stats["placeholder"] += 1
                print(f"   no photo found for {p['asin']} - using placeholder")

            img = square(img)
            img.save(img_path, "JPEG", quality=85, optimize=True)
            build_model(img, p["category"]).export(glb_path)
            print(f"[{i}/{len(products)}] {p['theme']:<11} {p['category']:<7} {p['asin']}  {p['name'][:45]}")

    print(f"\nDone: {stats}")


if __name__ == "__main__":
    main()
