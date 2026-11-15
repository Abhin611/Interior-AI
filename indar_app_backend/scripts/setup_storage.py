"""
Creates the public "assets" storage bucket in your Supabase project and
uploads the dataset (product photos + AR models) into it.

Run from indar_app_backend/ (needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env):
  uv run python scripts/setup_storage.py

Safe to run again - existing files are overwritten.
"""
import mimetypes
import sys
from pathlib import Path

from dotenv import dotenv_values
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
BUCKET = "assets"

env = dotenv_values(ROOT / ".env")
url, key = env.get("SUPABASE_URL"), env.get("SUPABASE_SERVICE_ROLE_KEY")
if not url or not key:
    sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in indar_app_backend/.env first.")

sb = create_client(url, key)

# 1. Public bucket (room photos, AI designs and the dataset are read by URL from the app)
existing = {b.name for b in sb.storage.list_buckets()}
if BUCKET not in existing:
    sb.storage.create_bucket(BUCKET, options={"public": True})
    print(f"Created public bucket '{BUCKET}'")
else:
    sb.storage.update_bucket(BUCKET, options={"public": True})
    print(f"Bucket '{BUCKET}' already exists (made sure it is public)")

# 2. Upload dataset/<theme>/{Image,3d}/<ASIN>.{jpg,glb}  ->  assets/dataset/...
files = sorted(p for p in DATASET.rglob("*") if p.is_file())
if not files:
    sys.exit("No dataset files found. Run scripts/build_dataset.py first.")

types = {".glb": "model/gltf-binary", ".jpg": "image/jpeg"}
for i, path in enumerate(files, 1):
    dest = "dataset/" + path.relative_to(DATASET).as_posix()
    ctype = types.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    sb.storage.from_(BUCKET).upload(
        path=dest,
        file=path.read_bytes(),
        file_options={"content-type": ctype, "upsert": "true"},
    )
    print(f"[{i}/{len(files)}] {dest}")

print(f"\nUploaded {len(files)} files to '{BUCKET}'.")
