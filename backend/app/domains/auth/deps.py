from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.context import Actor, set_actor
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.db.session import get_db
from app.domains.users.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    # ATENÇÃO: esta dependência PRECISA ser `async def`.
    # Dependência síncrona é executada pelo FastAPI numa thread do pool, que recebe uma
    # CÓPIA do contexto — o set_actor() abaixo mexeria numa cópia descartável e o endpoint
    # (e o listener de auditoria) nunca veria o usuário. Todo log sairia como "sistema":
    # registraria o quê e perderia o quem, que é a razão de existir do log.
    if creds is None:
        raise Unauthorized("Faça login para continuar.")

    user_id = decode_access_token(creds.credentials)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Usuário inválido ou inativo.")

    # Deixa o usuário visível para o listener de auditoria, que roda longe daqui.
    set_actor(Actor(user_id=user.id, email=user.email, ip=request.client.host if request.client else None))
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.admin:
        raise Forbidden("Apenas administradores podem fazer isso.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
Db = Annotated[Session, Depends(get_db)]
