# 🛋️ Indar — Interior AI

> Snap a photo of your room. Watch AI redesign it for a festival or theme. Shop the exact pieces. Preview them in your space with AR before you buy.

This repo has everything needed to run the app on your own accounts: the Flutter app, the FastAPI backend, the product dataset (photos + 3D models), and a free Colab GPU server for the AI image generation.

```
Interior-AI/
├── indar_app_frontend/        Flutter app (Android / iOS / web / desktop)
├── indar_app_backend/         FastAPI backend (Supabase database, auth, storage)
│   ├── Dataset1.xlsx          90 products across 6 themes
│   ├── dataset/               product photos + AR .glb models (named by ASIN)
│   └── scripts/               build_dataset.py, setup_storage.py
├── gpu_server/                img2img server (Dreamshaper 8), speaks the ComfyUI API
└── colab/Indar_GPU_Server.ipynb   runs gpu_server on a free Colab GPU
```

## How it works

```
📷 Room photo (Flutter)  →  POST /api/rooms/        → stored in Supabase Storage
🎨 Pick a theme          →  POST /api/designs/generate
                               ├─ picks theme products from the catalog
                               ├─ plans where each item goes (wall / hanging / floor)
                               └─ GPU server: Dreamshaper 8 img2img redecorates *your* room
🛒 Matched products      →  GET  /api/designs/{id}/bundle  → Amazon India cart link
🕶️ AR preview            →  .glb models from Supabase Storage, shown with model_viewer_plus
```

Themes: Onam, Christmas, Diwali, Halloween, Birthday, Pop-Culture.

## Tech stack

| Part | Tech |
|---|---|
| App | Flutter, Provider, Supabase Auth (email, optional Google) |
| AR | `model_viewer_plus` + GLB models |
| API | FastAPI, SQLAlchemy (async), slowapi rate limiting |
| Database and storage | Supabase Postgres + Supabase Storage |
| Image generation | Dreamshaper 8 img2img via `diffusers` (or a real ComfyUI) |
| Commerce | Amazon India add-to-cart bundles |

## Setup (once)

You need: Python 3.12+ with [uv](https://docs.astral.sh/uv/), the Flutter SDK, a free [Supabase](https://supabase.com) account and a Google account (for Colab).

### 1. Supabase project

1. Create a project at [supabase.com](https://supabase.com/dashboard).
2. From **Project Settings → API**, note the **Project URL**, the **anon** key and the **service_role** key.
3. From **Connect → Session pooler**, copy the connection string.
4. Optional, for easy testing: **Authentication → Sign In / Providers → Email** → turn off **Confirm email**.

### 2. Backend

```bash
cd indar_app_backend
cp .env.example .env      # fill in the Supabase values; DATABASE_URL must start with postgresql+asyncpg://
uv sync
uv run python -m app.database.seed     # creates the tables, loads 6 themes + 90 products
uv run python scripts/setup_storage.py # creates the public "assets" bucket and uploads dataset/
uv run python main.py                  # http://localhost:8000, API docs at /docs
```

### 3. Frontend

```bash
cd indar_app_frontend
cp env.example.json env.json   # fill in SUPABASE_URL and SUPABASE_ANON_KEY
flutter pub get
flutter run --dart-define-from-file=env.json
```

`API_BASE_URL` in `env.json` is `http://10.0.2.2:8000` for the Android emulator. On a real phone on the same Wi-Fi, use your PC's IP, e.g. `http://192.168.1.10:8000`. In VS Code, the **Indar (env.json)** launch configuration does this for you.

## Every time you demo: start the AI image server

Image generation needs a GPU. The notebook runs it free on Google Colab:

1. Open [`colab/Indar_GPU_Server.ipynb` in Colab](https://colab.research.google.com/github/Abhin611/Interior-AI/blob/main/colab/Indar_GPU_Server.ipynb).
2. **Runtime → Change runtime type → T4 GPU**, then **Runtime → Run all** (about 3–4 minutes the first time).
3. Wait for `Registered with your Indar backend`. The notebook tells the backend its new URL through your Supabase project, so there is nothing to copy and no restart.
4. Keep the Colab tab open while using the app. If it is closed, the app shows "The AI server is asleep" with these steps.

**One-time Colab setup:** add three Colab Secrets (key icon, Notebook access on): `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `GPU_TOKEN`. The token is created in your database the first time the backend starts: read it with `select value from app_config where key = 'gpu_token';` in the Supabase SQL editor. Without the secrets the notebook still prints a `COMFYUI_URL=...` line to paste into `indar_app_backend/.env`.

No GPU? `INDAR_FAKE_GPU=1` makes `gpu_server` return a tinted copy of the photo, which is handy for testing the rest of the app:

```bash
cd gpu_server
pip install -r requirements.txt
INDAR_FAKE_GPU=1 uvicorn server:app --port 8188    # then COMFYUI_URL=http://127.0.0.1:8188
```

## Optional: Google sign-in

Email and password login works out of the box. For the **Continue with Google** button, create an OAuth client in Google Cloud Console, enable the Google provider in **Supabase → Authentication → Providers**, and add `io.supabase.indar://login-callback` under **Authentication → URL Configuration → Redirect URLs**.

## The dataset

`indar_app_backend/dataset/` is generated from `Dataset1.xlsx` by `scripts/build_dataset.py`. It downloads each product's photo from its Amazon.in listing and builds a simple AR model with that photo on it (a framed panel for wall items, a hanging card for hanging items, a standee for floor items). To change products, edit the spreadsheet and run:

```bash
uv run python scripts/build_dataset.py
uv run python -m app.database.seed
uv run python scripts/setup_storage.py
```

## API overview

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/auth/me` | Verify Supabase token and sync the user |
| PATCH | `/api/auth/me/name` | Set display name |
| POST / GET | `/api/rooms/` | Upload a room photo / list rooms |
| POST | `/api/designs/generate` | Generate a themed redesign |
| GET | `/api/designs/{id}/bundle` | Products and Amazon cart for a design |
| GET | `/api/products/theme/{theme}` | Products for a theme |
| POST | `/api/products/bundles/{id}/purchase` | Log the purchase and return the cart link |

All `/api` routes need `Authorization: Bearer <Supabase access token>`.

## Credits

Built as a Semester 6 mini project. The frontend and backend were first built in separate repos ([Interior-AI](https://github.com/hridhikeshspremnath/Interior-AI) and [Indar-Backend](https://github.com/hridhikeshspremnath/Indar-Backend)) and combined here.

## Design pictures use real products

A design picture is your room photo with real catalog products placed in it (no AI drawing), so everything you see can be bought. Each product needs a transparent cut-out:

```bash
cd indar_app_backend
uv run python scripts/make_cutouts.py   # keeps only products photographed on a plain background
```

Only products with a clean cut-out are drawn into pictures. To add products, put their ASINs in `scripts/new_products.csv` (or save their photos in `scripts/new_photos/<ASIN>.jpg`) and run `uv run python scripts/add_products.py`, then `uv run python -m app.database.seed` and `uv run python scripts/setup_storage.py`.
