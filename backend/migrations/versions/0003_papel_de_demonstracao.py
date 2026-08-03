"""papel de demonstracao (somente leitura)

`role` é VARCHAR(20) com um CHECK, não um ENUM nativo do Postgres (native_enum=False).
Então incluir um valor novo é recriar a restrição — não existe ALTER TYPE ADD VALUE aqui.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAPEIS_NOVOS = ("admin", "operador", "demonstracao")
PAPEIS_ANTIGOS = ("admin", "operador")


def _troca_check(valores: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{v}'" for v in valores)
    # IF EXISTS: a restrição pode ter nome diferente conforme a versão do SQLAlchemy que
    # criou o schema. Falhar aqui deixaria o banco no meio da migração.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS user_role")
    op.execute(f"ALTER TABLE users ADD CONSTRAINT user_role CHECK (role IN ({lista}))")


def upgrade() -> None:
    _troca_check(PAPEIS_NOVOS)


def downgrade() -> None:
    # Sem isto, o downgrade deixaria usuários de demonstração violando a restrição nova e
    # o ALTER falharia. Rebaixar para operador seria pior: daria escrita a quem não tinha.
    op.execute("DELETE FROM users WHERE role = 'demonstracao'")
    _troca_check(PAPEIS_ANTIGOS)
