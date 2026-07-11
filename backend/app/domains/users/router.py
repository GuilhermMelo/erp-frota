from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.errors import Conflict, NotFound
from app.core.security import hash_password
from app.domains.auth.deps import AdminUser, Db
from app.domains.users.models import User
from app.domains.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["usuários"])


@router.get("", response_model=list[UserOut])
def list_users(db: Db, _: AdminUser):
    return db.scalars(select(User).order_by(User.full_name)).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: Db, _: AdminUser):
    if db.scalar(select(User).where(User.email == data.email)):
        raise Conflict("Já existe um usuário com esse e-mail.")

    user = User(
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, data: UserUpdate, db: Db, _: AdminUser):
    user = db.get(User, user_id)
    if not user:
        raise NotFound("Usuário não encontrado.")

    fields = data.model_dump(exclude_unset=True)
    if "password" in fields:
        user.hashed_password = hash_password(fields.pop("password"))
    for key, value in fields.items():
        setattr(user, key, value)

    db.commit()
    return user
