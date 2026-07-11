from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import Unauthorized

ALGORITHM = "HS256"
# Hash fixo usado quando o e-mail não existe, para que o login gaste o mesmo tempo
# de um usuário real e não vaze por timing quais e-mails estão cadastrados.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-para-timing", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    pwd = password.encode()
    if len(pwd) > 72:
        # bcrypt trunca em 72 bytes silenciosamente. Recusar é mais honesto.
        raise ValueError("A senha excede 72 bytes.")
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], (hashed or _DUMMY_HASH).encode())
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Sessão expirada. Entre novamente.")
    except jwt.PyJWTError:
        raise Unauthorized("Token inválido.")
    subject = payload.get("sub")
    if not subject:
        raise Unauthorized("Token inválido.")
    return subject
