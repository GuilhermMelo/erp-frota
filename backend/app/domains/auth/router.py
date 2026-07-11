from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select

from app.core.errors import Unauthorized
from app.core.security import create_access_token, verify_password
from app.domains.audit.listeners import log_auth_event
from app.domains.audit.models import AuditAction
from app.domains.auth.deps import CurrentUser, Db
from app.domains.users.models import User
from app.domains.users.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip().lower()


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Db):
    user = db.scalar(select(User).where(User.email == data.email))

    # verify_password roda contra um hash dummy quando o usuário não existe, para que o
    # tempo de resposta não revele quais e-mails estão cadastrados.
    senha_ok = verify_password(data.password, user.hashed_password if user else None)

    if not user or not senha_ok or not user.is_active:
        log_auth_event(db, AuditAction.login_failed, data.email, user.id if user else None)
        db.commit()
        raise Unauthorized("E-mail ou senha inválidos.")

    user.last_login_at = datetime.now(UTC)
    log_auth_event(db, AuditAction.login, user.email, user.id)
    db.commit()

    return TokenOut(access_token=create_access_token(str(user.id)), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
