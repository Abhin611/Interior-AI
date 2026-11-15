import httpx
from jose import jwt, JWTError
from app.core.settings import settings

JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_cache = None


async def _get_jwks() -> dict:
    """Fetch and cache Supabase public keys."""
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


async def decode_supabase_token(token: str) -> dict:
    """
    Verifies Supabase JWT using their public JWKS.
    Works for both HS256 and ES256 tokens.
    """
    # Extract key id from token header
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    # Projects using the legacy shared secret sign tokens with HS256 and
    # publish no JWKS key for them - verify those with SUPABASE_JWT_SECRET.
    if header.get("alg") == "HS256" and settings.SUPABASE_JWT_SECRET:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )

    jwks = await _get_jwks()

    # Find matching key
    key = None
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            key = k
            break

    if not key:
        raise JWTError("No matching key found in JWKS.")

    return jwt.decode(
        token,
        key,
        algorithms=["ES256", "HS256"],
        options={"verify_aud": False},
    )