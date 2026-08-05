from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from sqlalchemy import DateTime, MetaData, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nomes previsíveis para constraints — sem isso o Alembic gera nomes anônimos
# e um dia você não consegue dropar um CHECK numa migração.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

# Dinheiro é SEMPRE Numeric(12,2)/Decimal. Nunca float. Ver ARQUITETURA.md, regra 1.
MONEY = Numeric(12, 2)
Money = Annotated[Decimal, mapped_column(MONEY)]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Faz o INSERT usar RETURNING, para que `code` e `created_at` (gerados pelo banco)
    # já venham preenchidos no objeto sem um refresh extra.
    __mapper_args__ = {"eager_defaults": True}


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def code_column(prefix: str, sequence: str) -> Mapped[str]:
    """Código legível (CAR000001) gerado por SEQUENCE do Postgres.

    nextval é atômico e não-transacional: dois inserts simultâneos nunca recebem o
    mesmo número. Em compensação pode haver buracos se um insert der rollback —
    CAR000004 pode não existir. É o preço de não serializar todo insert numa fila.
    """
    return mapped_column(
        String(12),
        server_default=text(f"'{prefix}' || lpad(nextval('{sequence}')::text, 6, '0')"),
        unique=True,
        nullable=False,
        index=True,
    )
