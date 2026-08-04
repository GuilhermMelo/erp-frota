from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.core.security import hash_password
from app.domains.auth.deps import AdminUser, Db
from app.domains.users.models import User, UserRole
from app.domains.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["usuários"])


def _require_another_admin(db: Session, user: User) -> None:
    """Tem que sobrar UM administrador ativo. Não há como se recuperar disso.

    Um admin que se rebaixa a operador (ou que se desativa) perde na requisição seguinte
    `/users`, `/audit`, todo `DELETE` e a venda de veículo — e não existe caminho de volta:
    `seed()` só cria o admin quando a tabela está VAZIA, e este sistema não tem
    "esqueci minha senha". O conserto seria SQL direto no banco, na mão.
    """
    outros = db.scalar(
        select(func.count(User.id)).where(
            User.id != user.id,
            User.role == UserRole.admin,
            User.is_active.is_(True),
        )
    )
    if not outros:
        raise Conflict(
            "Este é o último administrador ativo. Promova outro usuário a administrador "
            "antes de rebaixar ou desativar este — senão ninguém mais consegue "
            "administrar o sistema."
        )


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

    perdeu_o_papel = "role" in fields and fields["role"] != UserRole.admin
    foi_desativado = fields.get("is_active") is False
    if user.role == UserRole.admin and user.is_active and (perdeu_o_papel or foi_desativado):
        _require_another_admin(db, user)

    if "password" in fields:
        user.hashed_password = hash_password(fields.pop("password"))
    for key, value in fields.items():
        setattr(user, key, value)

    db.commit()
    return user
