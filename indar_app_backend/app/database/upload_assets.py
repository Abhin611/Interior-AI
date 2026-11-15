"""
One-off script: uploads the local dataset folder (product images + .glb models)
to the Supabase "assets" bucket.
Run with: uv run python -m app.database.upload_assets
Reads SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY from .env and the folder from ASSETS_DIR.
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

BASE_DIR = os.environ.get("ASSETS_DIR", "dataset")  # local folder to upload

bucket_name = "assets"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

uploaded = 0
failed = 0
skipped = 0

for root, dirs, files in os.walk(BASE_DIR):
    for file in files:
        local_path = os.path.join(root, file)
        relative_path = os.path.relpath(local_path, BASE_DIR)
        storage_path = relative_path.replace("\\", "/")

        with open(local_path, "rb") as f:
            data = f.read()

        try:
            supabase.storage.from_(bucket_name).upload(
                storage_path,
                data,
                {"content-type": "application/octet-stream"}
            )
            print(f"✅ Uploaded: {storage_path}")
            uploaded += 1
        except Exception as e:
            err = str(e)
            if "already exists" in err or "Duplicate" in err:
                print(f"⏭️  Skipped (exists): {storage_path}")
                skipped += 1
            else:
                print(f"❌ Failed: {storage_path} → {err}")
                failed += 1

print(f"\n🎉 Done. Uploaded: {uploaded} | Skipped: {skipped} | Failed: {failed}")