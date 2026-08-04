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

import re
import subprocess
import sys

from tests.conftest import BACKEND_DIR, PROJECT_DIR

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

from app.core.config import DEFAULT_SECRET, settings  # noqa: E402
from app.db.session import _engine_kwargs, alembic_engine_kwargs  # noqa: E402


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


# ---------------------------------------------------------------------------
# A METADE DESCOBERTA: o engine que o Alembic monta.
#
# BUG REAL, corrigido nesta sessão. `migrations/env.py` criava o próprio engine com
# `poolclass=pool.NullPool` na mão — metade do tratamento do pooler. O `prepare_threshold`
# ficava de fora, e a migração é o que roda em TODO boot, antes de a API atender a primeira
# requisição. O erro (`prepared statement "_pg3_0" does not exist`) derrubaria o deploy de
# forma intermitente, no lugar mais difícil de investigar que existe.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@aws-0-sa-east-1.pooler.supabase.com:6543/postgres",
        "postgresql+psycopg://u:p@db.exemplo.com:6543/postgres",
    ],
)
def test_a_migracao_tambem_desliga_o_prepared_statement_no_pooler(url, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    monkeypatch.setattr(settings, "DB_SCHEMA", "")
    kw = alembic_engine_kwargs()
    assert kw["connect_args"]["prepare_threshold"] is None
    assert kw["poolclass"].__name__ == "NullPool"


def test_a_migracao_na_conexao_direta_nao_leva_nada_a_mais(monkeypatch):
    """Contraprova: sem pooler, `prepare_threshold` não tem por que existir. Um
    `alembic_engine_kwargs()` que devolvesse sempre o mesmo dicionário passaria no teste
    acima e falharia aqui."""
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://u:p@localhost:5434/frota")
    monkeypatch.setattr(settings, "DB_SCHEMA", "")
    assert alembic_engine_kwargs()["connect_args"] == {}


def test_a_migracao_usa_de_fato_os_ajustes_de_session_py():
    """Os dois testes acima só significam alguma coisa se o `env.py` CHAMAR a função.

    Ele já montou o engine na mão uma vez — foi assim que o buraco nasceu.
    """
    fonte = (BACKEND_DIR / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "alembic_engine_kwargs()" in fonte, "o env.py voltou a montar o engine sozinho"
    assert "poolclass=pool" not in fonte


# ---------------------------------------------------------------------------
# scripts/web.ps1 — o único script que abre a porta para a REDE.
#
# CRÍTICO, corrigido nesta sessão. Ele subia o uvicorn em `0.0.0.0` a partir do
# código-fonte, sem definir ENV nem SECRET_KEY. As duas defesas do config.py ficavam
# desarmadas ao mesmo tempo: o sorteio por instalação só vale para o .exe
# (`paths.IS_FROZEN`), e a recusa do segredo padrão só vale fora de `ENV=dev`. Resultado:
# o sistema ia para o Wi-Fi assinando JWT com `dev-secret-troque-em-producao`, que está
# escrito no código-fonte de um repositório PÚBLICO — qualquer aparelho da rede forjava um
# token de admin SEM SENHA e baixava CNH e contrato assinado por /files/{id}/download.
# ---------------------------------------------------------------------------
WEB_PS1 = (PROJECT_DIR / "scripts" / "web.ps1").read_text(encoding="utf-8")


def _env_do_script_da_rede() -> str:
    achado = re.search(r'\$env:ENV\s*=\s*"([^"]+)"', WEB_PS1)
    assert achado, "web.ps1 não define $env:ENV: voltaria a subir na rede como dev"
    return achado.group(1)


def test_o_script_da_rede_define_o_segredo_antes_de_subir_o_servidor():
    assert "$env:SECRET_KEY" in WEB_PS1, "web.ps1 sem SECRET_KEY: assina JWT com o padrão público"
    assert "installation_secret" in WEB_PS1, (
        "o segredo tem que ser o sorteado por instalação (secret.key), não um literal no script"
    )
    assert _env_do_script_da_rede() != "dev"
    # Ordem importa: definido depois do uvicorn subir, o servidor já teria lido o padrão.
    assert WEB_PS1.index("$env:SECRET_KEY") < WEB_PS1.index("uvicorn")


def test_o_env_do_script_da_rede_recusa_o_segredo_publicado():
    """O acoplamento que faz a correção valer: o ENV que o web.ps1 usa TEM que ser um que
    o config.py trate como não-dev. Senão o script definiria o segredo e a trava seguiria
    desarmada — bastaria alguém rodar o uvicorn na mão para voltar ao buraco."""
    r = _sobe(
        **{
            **BASE,
            "ENV": _env_do_script_da_rede(),
            "SECRET_KEY": DEFAULT_SECRET,
            "ADMIN_PASSWORD": "",
        }
    )
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stderr


def test_o_env_do_script_da_rede_nao_exige_admin_password():
    """E a fronteira: na máquina do dono a senha sorteada é entregue em
    `senha-inicial-admin.txt`, que ele abre. Exigir `ADMIN_PASSWORD` aqui só ensinaria a
    contornar o modo seguro — que é como travas de segurança morrem."""
    r = _sobe(
        **{
            **BASE,
            "ENV": _env_do_script_da_rede(),
            "SECRET_KEY": "x" * 40,
            "ADMIN_PASSWORD": "",
        }
    )
    assert r.returncode == 0, r.stderr
    # A contraprova de que a dispensa é só do modo desktop já existe acima, em
    # `test_sem_admin_password_derruba_o_boot` (ENV=production).
