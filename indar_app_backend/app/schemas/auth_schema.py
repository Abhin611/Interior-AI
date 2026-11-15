# Supabase handles token schema on the Flutter side
# We only need this for our /me response shape
from pydantic import BaseModel

class SyncResponse(BaseModel):
    message: str
    user_id: str