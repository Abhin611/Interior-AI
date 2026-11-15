# 🛋️ Indar — Interior AI

> Snap a photo of your room. Watch AI redesign it for a festival or theme. Shop the exact pieces. Preview them in your space with AR before you buy.

This repo has the full app: a **Flutter** mobile frontend and a **FastAPI** backend that runs the AI pipeline.

```
Interior-AI/
├── indar_app_frontend/   Flutter app (Android / iOS / web / desktop)
└── indar_app_backend/    FastAPI backend (Supabase + ComfyUI)
```

## How it works

```
📷 Room photo (Flutter)  →  POST /api/rooms/        → stored in Supabase Storage
🎨 Pick a theme          →  POST /api/designs/generate
                               ├─ picks theme products from the catalog
                               ├─ plans where each item goes (wall / hanging / floor)
                               └─ ComfyUI img2img (Dreamshaper 8) redecorates *your* room
🛒 Matched products      →  GET  /api/designs/{id}/bundle  → Amazon India cart link
🕶️ AR preview            →  .glb models from Supabase, shown with model_viewer_plus
```

Themes: Onam, Christmas, Diwali, Halloween, Birthday, Pop-Culture.

## Tech stack

| Part | Tech |
|---|---|
| App | Flutter, Provider, Supabase Auth (email + Google) |
| AR | `model_viewer_plus` + GLB models |
| API | FastAPI, SQLAlchemy (async), slowapi rate limiting |
| Database and storage | Supabase Postgres + Supabase Storage |
| Image generation | ComfyUI + Dreamshaper 8 (img2img) |
| Commerce | Amazon India add-to-cart bundles |

## Run it

### 1. Backend

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd indar_app_backend
cp .env.example .env        # fill in your Supabase keys, DATABASE_URL and COMFYUI_URL
uv sync
uv run python -m app.database.seed   # loads themes + products from Dataset1.xlsx (first time only)
uv run python main.py                # http://localhost:8000, docs at /docs
```

Image generation needs a running [ComfyUI](https://github.com/comfyanonymous/ComfyUI) server with the `dreamshaper_8.safetensors` checkpoint. Set its address in `COMFYUI_URL`. The workflow is in `img2img_workflow.json`.

### 2. Frontend

Needs the Flutter SDK.

```bash
cd indar_app_frontend
flutter pub get
flutter run                                                    # Android emulator
flutter run --dart-define=API_BASE_URL=http://<your-PC-IP>:8000   # real phone on the same Wi-Fi
```

The backend URL is set in `lib/config.dart`. It defaults to `http://10.0.2.2:8000`, which is how the Android emulator reaches your computer.

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
