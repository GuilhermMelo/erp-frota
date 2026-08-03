"""Tenant por schema: a vitrine no mesmo banco, sem alcançar o dado real.

O que estes testes provam:

  1. As migrações criam o schema do tenant e todas as tabelas DENTRO dele.
  2. Cada tenant tem o SEU `alembic_version` — senão os dois disputariam o registro de
     "em que migração estou", e o segundo a migrar acharia que já estava pronto.
  3. Os dados de um não aparecem no outro.

O que estes testes NÃO provam, e é preciso dizer: a garantia final é do PAPEL do Postgres
(`scripts/criar_tenant.sql`), que não tem permissão no schema `public`. Aqui a suíte roda
como dono do banco e enxerga tudo — testar a permissão exigiria um segundo papel real.
A conferência disso está escrita no fim daquele script e é manual, uma vez, no Supabase.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.session import engine
from tests.conftest import TEST_DATABASE_URL

BACKEND = Path(__file__).resolve().parents[1]
TENANT = "demo_teste"


@pytest.fixture(scope="module")
def tenant_migrado():
    """Roda o Alembic num schema separado, em subprocesso.

    Subprocesso porque `settings` é um singleton construído no import: mudar DB_SCHEMA
    depois de `import app` não teria efeito nenhum.
    """
    ambiente = {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL,
        "DB_SCHEMA": TENANT,
        "ENV": "dev",
    }
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=ambiente,
    )
    assert r.returncode == 0, f"migração do tenant falhou:\n{r.stderr[-2000:]}"

    yield TENANT

    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{TENANT}" CASCADE'))


def _tabelas(schema: str) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": schema}
            ).all()
        )


def test_as_tabelas_nascem_dentro_do_schema_do_tenant(tenant_migrado):
    do_tenant = _tabelas(tenant_migrado)
    assert "vehicles" in do_tenant
    assert "users" in do_tenant
    # 13 modelos + tabelas de apoio: o número exato não importa, a ordem de grandeza sim.
    assert len(do_tenant) >= 13, f"só {len(do_tenant)} tabelas no tenant: {sorted(do_tenant)}"


def test_cada_tenant_tem_o_proprio_controle_de_versao(tenant_migrado):
    """Sem `version_table_schema`, os dois gravariam em public.alembic_version."""
    assert "alembic_version" in _tabelas(tenant_migrado)
    assert "alembic_version" in _tabelas("public")

    with engine.connect() as conn:
        do_tenant = conn.scalar(text(f'SELECT version_num FROM "{tenant_migrado}".alembic_version'))
        do_real = conn.scalar(text("SELECT version_num FROM public.alembic_version"))
    assert do_tenant == do_real  # mesma migração aplicada...
    # ...mas em registros separados: são duas linhas em duas tabelas diferentes.


def test_as_sequences_de_codigo_sao_independentes(tenant_migrado):
    """`nextval('vehicle_code_seq')` sem qualificar resolve pelo search_path. Se as duas
    apontassem para a mesma sequence, o CAR000001 do demo consumiria o número do real."""
    with engine.connect() as conn:
        seqs = set(
            conn.scalars(
                text("SELECT sequencename FROM pg_sequences WHERE schemaname = :s"),
                {"s": tenant_migrado},
            ).all()
        )
    assert "vehicle_code_seq" in seqs


def test_o_dado_de_um_tenant_nao_aparece_no_outro(tenant_migrado, criar_veiculo):
    """O veículo criado pela suíte (em `public`) não pode existir no schema da vitrine."""
    criar_veiculo(plate="TEN1A23")

    with engine.connect() as conn:
        no_real = conn.scalar(text("SELECT count(*) FROM public.vehicles WHERE plate = 'TEN1A23'"))
        no_tenant = conn.scalar(
            text(f'SELECT count(*) FROM "{tenant_migrado}".vehicles WHERE plate = \'TEN1A23\'')
        )

    assert no_real == 1
    assert no_tenant == 0
