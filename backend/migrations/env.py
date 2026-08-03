from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import settings
from app.db.base import Base  # importa todos os models

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tenant. Vazio = `public`. A vitrine roda em `demo`, no mesmo banco.
SCHEMA = settings.DB_SCHEMA.strip() or "public"


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        version_table_schema=SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if SCHEMA != "public":
            # O schema tem que existir antes da primeira migração. Criar aqui evita um
            # passo manual que, esquecido, faria o deploy do tenant falhar no boot.
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))

        # search_path SEM `public` de propósito. Com o fallback, uma tabela faltando no
        # schema do tenant resolveria silenciosamente para a do tenant real — que é
        # exatamente o vazamento que este desenho existe para impedir. Melhor erro de
        # "relação não existe" do que ler dado de outro.
        connection.execute(text(f'SET search_path TO "{SCHEMA}"'))

        # ESTE COMMIT NÃO É OPCIONAL. No SQLAlchemy 2 os `execute` acima abrem uma
        # transação implícita; sem fechá-la aqui, o Alembic roda as migrações DENTRO
        # dela e tudo é revertido quando a conexão fecha. O sintoma é traiçoeiro: o
        # `upgrade` termina com código 0 e as tabelas não existem.
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Sem isto o Alembic gravaria a versão em `public.alembic_version`, e os dois
            # tenants disputariam o mesmo registro de "em que migração estou".
            version_table_schema=SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
