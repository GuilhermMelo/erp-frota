from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _engine_kwargs() -> dict:
    """Ajustes para o pooler do Supabase.

    O Supabase oferece duas portas. A 5432 é conexão direta; a **6543 é o PgBouncer em
    modo transaction**, e é a recomendada para aplicação — mas ela reaproveita conexões
    entre transações diferentes.

    Isso quebra duas coisas do psycopg + SQLAlchemy:

    1. **Prepared statements.** O psycopg 3 prepara automaticamente uma query depois de
       algumas execuções. No PgBouncer transaction mode, a próxima transação pode cair
       noutra conexão física, onde aquele statement não existe — e aparece o erro
       `prepared statement "_pg3_0" does not exist`, de forma intermitente e sob carga,
       que é o pior jeito de descobrir. `prepare_threshold=None` desliga isso.

    2. **Pool em cima de pool.** Manter um pool do SQLAlchemy sobre o pool do PgBouncer
       segura conexões à toa e estoura o limite do projeto Supabase. `NullPool` deixa o
       gerenciamento com quem já faz isso.

    Conexão direta (5432) não precisa de nada disso — por isso a detecção é pelo host.
    """
    url = settings.DATABASE_URL
    via_pooler = "pooler.supabase" in url or ":6543" in url
    schema = settings.DB_SCHEMA.strip()

    connect_args: dict = {}
    if schema:
        # Parâmetro de inicialização do libpq: vai junto no handshake da conexão, e não
        # como um `SET` avulso. Isso importa com PgBouncer em modo transaction, onde um
        # `SET` sem `LOCAL` pode não sobreviver à troca de conexão física entre
        # transações — e a consulta seguinte cairia no schema errado.
        #
        # Ainda assim, em produção quem GARANTE o isolamento não é isto: é o papel do
        # Postgres criado por scripts/criar_tenant.sql, que só tem permissão no próprio
        # schema e carrega o search_path como padrão. Isto aqui é conveniência para
        # desenvolvimento; a trava é do banco.
        connect_args["options"] = f"-csearch_path={schema}"

    if not via_pooler:
        return {"pool_pre_ping": True, "connect_args": connect_args}

    return {
        "poolclass": NullPool,
        "connect_args": {**connect_args, "prepare_threshold": None},
    }


def alembic_engine_kwargs() -> dict:
    """Os MESMOS ajustes, para o engine que o Alembic monta em `migrations/env.py`.

    O `env.py` cria um engine PRÓPRIO (`engine_from_config`), que não passa por
    `_engine_kwargs()`. Ele levava só o `NullPool` — metade do tratamento — e a migração
    é o que roda em TODO boot, antes de a API atender uma requisição sequer. Pelo pooler,
    sem `prepare_threshold=None`, o `prepared statement "_pg3_0" does not exist` derruba o
    boot de forma intermitente (ARQUITETURA.md, armadilha 9).

    `pool_pre_ping` não entra: a migração roda uma vez e fecha, não há conexão parada no
    pool para revalidar.
    """
    kwargs = _engine_kwargs()
    return {"poolclass": NullPool, "connect_args": kwargs["connect_args"]}


engine = create_engine(settings.DATABASE_URL, future=True, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
