"""
Adds new products to the catalog from a list of Amazon.in ASINs.

For each ASIN it reads the listing page (title, price, main photo), and keeps the
product ONLY if its photo cuts out cleanly - those are the products that can be
placed, as real products, into a user's room picture. Rejected ASINs are reported.

Input file (default scripts/new_products.csv), one product per line:
    asin,theme,category[,price,name]   e.g.  B08PCTF367,Christmas,Wall,241,CraftVatika Christmas Wreath Set of 2
Photos: either let the script read the listing page, or (Amazon often blocks that)
save the product's main photo as scripts/new_photos/<ASIN>.jpg and give price + name.
Theme: Onam | Christmas | Diwali | Halloween | Birthday | Pop-Culture
Category: Wall | Hanging | Floor

For each kept product it writes
    dataset/<theme>/Image/<ASIN>.jpg, 3d/<ASIN>.glb, Cutout/<ASIN>.png
and appends a row to Dataset1.xlsx. Afterwards run, from indar_app_backend/:
    uv run python -m app.database.seed          # adds the new rows to the database
    uv run python scripts/setup_storage.py      # uploads photos + 3D models to Supabase

Run from indar_app_backend/:
    uv run python scripts/add_products.py [file.csv]
"""
import csv
import io
import re
import sys
import time
from pathlib import Path

import httpx
import openpyxl
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from build_dataset import HEADERS, IMG_PATTERNS, build_model, clean, square  # noqa: E402
from make_cutouts import cut_out  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dataset"
EXCEL = ROOT / "Dataset1.xlsx"
THEMES = {"onam", "christmas", "diwali", "halloween", "birthday", "pop-culture"}
CATEGORIES = {"wall": "Wall", "hanging": "Hanging", "floor": "Floor"}


def read_listing(client: httpx.Client, asin: str):
    """Return (title, price, photo) from the listing, or (None, None, None) when blocked."""
    resp = client.get(f"https://www.amazon.in/dp/{asin}")
    if resp.status_code != 200 or "captcha" in resp.text.lower()[:6000]:
        return None, None, None
    html = resp.text
    m = re.search(r'id="productTitle"[^>]*>\s*([^<]+)', html)
    title = clean(m.group(1)) if m else None
    price = None
    for pat in (r'class="a-price-whole">\s*([\d,]+)', r'"priceAmount":\s*([\d.]+)', r'"displayPrice":"₹([\d,\.]+)"'):
        m = re.search(pat, html)
        if m:
            try:
                price = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass
    photo = None
    for pat in IMG_PATTERNS:
        m = re.search(pat, html)
        if m:
            img = client.get(m.group(1).replace("\\/", "/"))
            if img.status_code == 200:
                photo = Image.open(io.BytesIO(img.content)).convert("RGB")
                break
    return title, price, photo


def existing_asins() -> set:
    ws = openpyxl.load_workbook(EXCEL).active
    return {re.sub(r"\s", "", str(r[1] or "")) for r in ws.iter_rows(min_row=2, values_only=True)}


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "new_products.csv"
    rows = [r for r in csv.reader(src.open(encoding="utf-8")) if r and not r[0].startswith("#")]
    have = existing_asins()
    wb = openpyxl.load_workbook(EXCEL)
    ws = wb.active
    added, rejected = [], []

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for r in rows:
            asin, theme, cat = (r + ["", "", ""])[:3]
            asin, theme, cat = asin.strip(), theme.strip(), CATEGORIES.get(cat.strip().lower(), "")
            if asin in have:
                rejected.append((asin, "already in the catalog"))
                continue
            if theme.lower() not in THEMES or not cat:
                rejected.append((asin, f"bad theme/category: {theme}/{cat}"))
                continue
            theme_dir = next((d.name for d in OUT.iterdir() if d.name.lower() == theme.lower()), theme)
            # Route 1: you saved the product's photo as scripts/new_photos/<ASIN>.jpg (or
            # .png/.webp) and gave price and name in the CSV. No Amazon page is fetched.
            local = next((p for ext in ("jpg", "jpeg", "png", "webp")
                          if (p := Path(__file__).parent / "new_photos" / f"{asin}.{ext}").exists()), None)
            if local:
                price_csv = re.sub(r"[^\d.]", "", r[3]) if len(r) > 3 else ""
                title = clean(r[4]) if len(r) > 4 else None
                price = float(price_csv) if price_csv else None
                photo = Image.open(local).convert("RGB")
            else:
                # Route 2: read the listing page (Amazon often blocks this: then use route 1).
                try:
                    title, price, photo = read_listing(client, asin)
                except httpx.HTTPError as e:
                    rejected.append((asin, f"network error: {type(e).__name__}"))
                    continue
                time.sleep(2)  # be polite to Amazon
            if not photo or not title:
                rejected.append((asin, "listing page blocked or has no photo/title"))
                continue
            if not price:
                rejected.append((asin, "price not found on the page"))
                continue

            tmp = OUT / f".tmp_{asin}.jpg"
            photo.save(tmp, "JPEG", quality=90)
            result, why = cut_out(tmp)
            tmp.unlink(missing_ok=True)
            if result is None:
                rejected.append((asin, f"photo can't be cut out cleanly ({why})"))
                continue

            (OUT / theme_dir / "Image").mkdir(parents=True, exist_ok=True)
            (OUT / theme_dir / "3d").mkdir(parents=True, exist_ok=True)
            (OUT / theme_dir / "Cutout").mkdir(parents=True, exist_ok=True)
            sq = square(photo)
            sq.save(OUT / theme_dir / "Image" / f"{asin}.jpg", "JPEG", quality=85, optimize=True)
            build_model(sq, cat).export(OUT / theme_dir / "3d" / f"{asin}.glb")
            result.save(OUT / theme_dir / "Cutout" / f"{asin}.png", optimize=True)
            ws.append([title, asin, f"{asin}.jpg", f"{asin}.glb", None, price, cat, theme_dir])
            added.append((asin, theme_dir, cat, price, title[:50]))
            print(f"  + {theme_dir:<10} {cat:<7} {asin}  Rs {price:>7.0f}  {title[:50]}")

    wb.save(EXCEL)
    print(f"\nadded {len(added)}, rejected {len(rejected)}")
    for asin, why in rejected:
        print(f"  - {asin}: {why}")


if __name__ == "__main__":
    main()
