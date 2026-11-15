from passlib.context import CryptContext
from fastapi.security import HTTPBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTPBearer gives a simple "paste token" box in Swagger
oauth2_scheme = HTTPBearer()

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)