"""As travas que impedem um deploy silenciosamente quebrado.

Cada uma destas falhas, se passasse, só apareceria em produção — e do pior jeito:

  SECRET_KEY padrão      qualquer um forja um token de admin
  SECRET_KEY sorteado    muda a cada deploy e desloga todo mundo
  ADMIN_PASSWORD vazio   o seed grava a senha num arquivo dentro do container,
                         que ninguém lê e que some no deploy seguinte —
                         o sistema nasce inacessível
  Supabase sem chave     a API aceita o upload e perde o arquivo

Rodam em SUBPROCESSO porque `settings` é um singleton construído no import: mudar
variável de ambiente depois de `import app` não teria efeito nenhum.
"""

import subprocess
import sys

CARREGA = "import app.core.config"


def _sobe(**env) -> subprocess.CompletedProcess:
    import os

    ambiente = {**os.environ, **{k: str(v) for k, v in env.items()}}
    return subprocess.run(
        [sys.executable, "-c", CARREGA],
        capture_output=True,
        text=True,
        env=ambiente,
    )


BASE = {
    "ENV": "production",
    "SECRET_KEY": "x" * 40,
    "ADMIN_PASSWORD": "uma-senha-de-verdade",
    "STORAGE_BACKEND": "local",
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_KEY": "",
}


def test_producao_sobe_com_tudo_configurado():
    r = _sobe(**BASE)
    assert r.returncode == 0, r.stderr


def test_secret_key_padrao_derruba_o_boot():
    r = _sobe(**{**BASE, "SECRET_KEY": "dev-secret-troque-em-producao"})
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stderr


def test_secret_key_curto_derruba_o_boot():
    """Menos de 32 caracteres é chave que se quebra por força bruta."""
    r = _sobe(**{**BASE, "SECRET_KEY": "curto-demais"})
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stderr


def test_sem_admin_password_derruba_o_boot():
    r = _sobe(**{**BASE, "ADMIN_PASSWORD": ""})
    assert r.returncode != 0
    assert "ADMIN_PASSWORD" in r.stderr


def test_supabase_sem_credencial_derruba_o_boot():
    r = _sobe(**{**BASE, "STORAGE_BACKEND": "supabase"})
    assert r.returncode != 0
    assert "SUPABASE" in r.stderr


def test_supabase_com_credencial_sobe():
    r = _sobe(
        **{
            **BASE,
            "STORAGE_BACKEND": "supabase",
            "SUPABASE_URL": "https://exemplo.supabase.co",
            "SUPABASE_SERVICE_KEY": "chave-de-mentira-para-o-teste",
        }
    )
    assert r.returncode == 0, r.stderr


def test_backend_de_storage_invalido_derruba_o_boot():
    r = _sobe(**{**BASE, "STORAGE_BACKEND": "s3"})
    assert r.returncode != 0
    assert "STORAGE_BACKEND" in r.stderr


def test_em_dev_nada_disso_e_exigido():
    """Desenvolvimento não pode virar burocracia: o desktop entrega a senha em arquivo."""
    r = _sobe(**{**BASE, "ENV": "dev", "SECRET_KEY": "dev-secret-troque-em-producao", "ADMIN_PASSWORD": ""})
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# Pooler do Supabase. Sem estes ajustes o erro é `prepared statement "_pg3_0"
# does not exist`, intermitente e só sob carga — o pior jeito de descobrir.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import _engine_kwargs  # noqa: E402


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@aws-0-sa-east-1.pooler.supabase.com:6543/postgres",
        "postgresql+psycopg://u:p@db.exemplo.com:6543/postgres",
    ],
)
def test_pooler_desliga_prepared_statement_e_pool(url, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    kw = _engine_kwargs()
    assert kw["connect_args"]["prepare_threshold"] is None
    assert kw["poolclass"].__name__ == "NullPool"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://frota:frota@localhost:5434/frota",
        "postgresql+psycopg://u:p@db.abcdef.supabase.co:5432/postgres",
    ],
)
def test_conexao_direta_mantem_o_pool_normal(url, monkeypatch):
    """Porta 5432 é conexão direta: pool do SQLAlchemy é o certo, e prepared
    statement é ganho de desempenho que não há motivo para abrir mão."""
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    monkeypatch.setattr(settings, "DB_SCHEMA", "")
    kw = _engine_kwargs()
    assert kw["pool_pre_ping"] is True
    assert "poolclass" not in kw
    assert kw["connect_args"] == {}


def test_tenant_viaja_no_handshake_da_conexao(monkeypatch):
    """`options` é parâmetro de inicialização do libpq, não um `SET` avulso — por isso
    sobrevive ao PgBouncer, onde um SET pode não valer para a transação seguinte."""
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setattr(settings, "DB_SCHEMA", "demo")
    assert _engine_kwargs()["connect_args"]["options"] == "-csearch_path=demo"


def test_tenant_e_pooler_convivem(monkeypatch):
    """A vitrine roda nos dois modos ao mesmo tempo: schema separado E pooler."""
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://u:p@x.pooler.supabase.com:6543/d")
    monkeypatch.setattr(settings, "DB_SCHEMA", "demo")
    kw = _engine_kwargs()
    assert kw["connect_args"]["options"] == "-csearch_path=demo"
    assert kw["connect_args"]["prepare_threshold"] is None
    assert kw["poolclass"].__name__ == "NullPool"
