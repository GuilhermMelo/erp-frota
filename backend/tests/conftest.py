"""Infra da suíte de testes.

Regras desta infra, todas por um motivo:

1. **Banco descartável.** Os testes rodam num banco `frota_test`, criado do zero no início
   da sessão e derrubado no fim. O banco de dev (`frota`) NUNCA é tocado — há um guard
   logo abaixo que aborta a suíte se a URL apontar para qualquer outro lugar.

2. **`STORAGE_DIR` num diretório temporário.** A pasta `storage/` do projeto guarda CNH,
   CPF e contratos de gente de verdade (LGPD). Teste não escreve lá.

3. **Migrações do Alembic, não `create_all`.** O schema testado é o mesmo que vai para
   produção — inclusive os CHECKs e os índices parciais, que são regra de negócio
   (`UNIQUE(contract_id, period_start)` é o que torna a cobrança semanal idempotente).

4. **TRUNCATE entre testes.** Os services dão `commit()`, então a estratégia de "rollback
   no fim do teste" não funciona: o dado já está gravado. TRUNCATE limpa de verdade.
   `expense_categories` e `checklist_items` sobrevivem (são catálogo do seed, não dado
   de operação). As sequences de código voltam ao 1, então o primeiro veículo de cada
   teste é sempre CAR000001.

5. **Autenticação de verdade.** `auth_client` faz login pelo `POST /auth/login` e manda o
   Bearer real. Nada de `dependency_overrides` em `get_current_user`: o listener de
   auditoria lê o usuário de um ContextVar que só é preenchido dentro do
   `get_current_user` real — um override que pulasse a autenticação faria todo log sair
   como "sistema" e o `test_audit` viraria teatro.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

PG_HOST, PG_PORT, PG_USER, PG_PASS = "localhost", 5434, "frota", "frota"
TEST_DB_NAME = "frota_test"
DEV_DB_NAME = "frota"  # NUNCA tocar neste

_PG_ADMIN_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/postgres"
TEST_DATABASE_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{TEST_DB_NAME}"

ADMIN_EMAIL = "admin@erpfrota.com.br"
ADMIN_PASSWORD = "admin123"

# Pasta de arquivos dos testes. Descartável, longe de `storage/`.
_STORAGE_TMP = Path(tempfile.mkdtemp(prefix="erp-frota-testes-"))

# ATENÇÃO: isto PRECISA rodar antes de qualquer `import app.*`. O `Settings` do
# pydantic-settings é um singleton construído no import do módulo, e variável de ambiente
# tem prioridade sobre o `.env` — é assim que o app inteiro (engine, storage, alembic)
# passa a apontar para o banco de teste sem tocar em uma linha de código de produção.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["STORAGE_DIR"] = str(_STORAGE_TMP)
os.environ["ENV"] = "dev"
os.environ["ADMIN_EMAIL"] = ADMIN_EMAIL
os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD

import bcrypt  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import CODE_SEQUENCES  # noqa: E402
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402  — importar main registra o listener de auditoria
from app.seed import seed  # noqa: E402

# ---------------------------------------------------------------------------
# Guards. Se algo aqui falhar, a suíte não roda — é melhor do que rodar no banco errado.
# ---------------------------------------------------------------------------
if settings.DATABASE_URL != TEST_DATABASE_URL:
    raise RuntimeError(
        f"A suíte só roda contra {TEST_DB_NAME}. DATABASE_URL efetiva: {settings.DATABASE_URL}"
    )
if DEV_DB_NAME == TEST_DB_NAME or settings.DATABASE_URL.endswith(f"/{DEV_DB_NAME}"):
    raise RuntimeError("A suíte NUNCA roda contra o banco de desenvolvimento.")
if settings.storage_path == (PROJECT_DIR / "storage").resolve():
    raise RuntimeError("STORAGE_DIR aponta para a pasta storage/ do projeto. Abortado.")

# Catálogo do seed: não é dado de operação, sobrevive ao TRUNCATE.
_PRESERVADAS = {"expense_categories", "checklist_items", "alembic_version"}

# Hash barato (custo 4) só para os testes: a suíte faz um login de verdade por teste e o
# custo 12 do bcrypt de produção somaria ~10 s à suíte sem testar nada além do bcrypt.
# O `verify_password` lê o custo do próprio hash, então o login continua sendo o real.
_ADMIN_HASH = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()

_INSERT_ADMIN = text(
    """
    INSERT INTO users (email, full_name, hashed_password, role, is_active)
    VALUES (:email, 'Administrador', :senha, 'admin', true)
    """
)


# ---------------------------------------------------------------------------
# Banco de teste: criar, migrar, semear, derrubar.
# ---------------------------------------------------------------------------
def _recreate_database() -> None:
    """DROP + CREATE do banco de teste, conectado no `postgres`.

    `WITH (FORCE)` derruba conexões penduradas de uma execução anterior que morreu no meio
    — senão o DROP fica preso para sempre e o próximo `pytest` falha sem explicação.
    """
    admin = create_engine(_PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        admin.dispose()


def _drop_database() -> None:
    admin = create_engine(_PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    finally:
        admin.dispose()


def _alembic_upgrade_head() -> None:
    """Roda as migrações no banco de teste.

    O `migrations/env.py` lê `settings.DATABASE_URL` — que já é a do banco de teste, por
    causa das variáveis de ambiente lá em cima. Rodar em processo evita depender do PATH.
    """
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _banco_de_teste() -> Iterator[None]:
    _recreate_database()
    _alembic_upgrade_head()
    with SessionLocal() as db:
        seed(db)  # categorias de despesa + checklist (o admin é recriado a cada teste)

    yield

    engine.dispose()  # sem isso o DROP fica esperando a conexão do pool
    _drop_database()
    shutil.rmtree(_STORAGE_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _banco_limpo(_banco_de_teste: None) -> None:
    """Cada teste começa com o banco no estado do seed. Roda ANTES da sessão do teste."""
    with engine.begin() as conn:
        tabelas = [
            t
            for t in conn.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
            if t not in _PRESERVADAS
        ]
        alvo = ", ".join(f'"{t}"' for t in tabelas)
        conn.execute(text(f"TRUNCATE TABLE {alvo} RESTART IDENTITY CASCADE"))

        # As sequences dos códigos (CAR000001...) são independentes das tabelas, então o
        # RESTART IDENTITY do TRUNCATE não as alcança. Zeradas na mão: assim o primeiro
        # veículo de QUALQUER teste é o CAR000001, e o test_audit pode afirmar isso.
        for seq in CODE_SEQUENCES:
            conn.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))

        # O admin do seed foi junto no TRUNCATE — recriado aqui (USR000001).
        conn.execute(_INSERT_ADMIN, {"email": ADMIN_EMAIL, "senha": _ADMIN_HASH})


@pytest.fixture
def db(_banco_limpo: None) -> Iterator[Session]:
    """A sessão do teste — a MESMA que os endpoints usam (via override de `get_db`).

    Serve para as asserções que precisam olhar o banco por dentro (existe mesmo uma
    Revenue de `caucao_retida`? o Expense saiu com `origin='fine'`?), que é onde os bugs
    de modelo financeiro se escondem.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def _app(db: Session):
    """O app com `get_db` apontando para a sessão do teste.

    Só `get_db` é sobrescrito. `get_current_user` continua o real: é ele que preenche o
    ContextVar do ator lido pelo listener de auditoria.
    """
    app.dependency_overrides[get_db] = lambda: db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(_app) -> Iterator[TestClient]:
    """Cliente ANÔNIMO (sem token). Para os testes de 401."""
    # Sem `with TestClient(...)`: o context manager dispararia o lifespan do app, que roda
    # o seed() de novo a cada teste. O seed já rodou uma vez, na criação do banco.
    c = TestClient(_app)
    yield c
    c.close()


@pytest.fixture
def login(_app) -> Iterator[Callable[[str, str], TestClient]]:
    """Fábrica de clientes autenticados DE VERDADE (login + header Bearer)."""
    abertos: list[TestClient] = []

    def _login(email: str, password: str) -> TestClient:
        c = TestClient(_app)
        r = c.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        abertos.append(c)
        return c

    yield _login
    for c in abertos:
        c.close()


@pytest.fixture
def auth_client(login) -> TestClient:
    """Cliente logado como admin. O caminho normal da maioria dos testes."""
    return login(ADMIN_EMAIL, ADMIN_PASSWORD)


# ---------------------------------------------------------------------------
# Atalhos de domínio. Os testes falam de dinheiro, não de payloads.
# ---------------------------------------------------------------------------
@pytest.fixture
def hoje() -> date:
    return date.today()


@pytest.fixture
def criar_veiculo(auth_client: TestClient, hoje: date) -> Callable[..., dict]:
    contador = iter(range(1000))

    def _criar(**kwargs) -> dict:
        n = next(contador)
        payload = {
            "plate": f"TST{n:04d}",  # 7 caracteres
            "brand": "Fiat",
            "model": "Cronos",
            "manufacture_year": 2023,
            "model_year": 2024,
            "fuel_type": "flex",
            "purchase_date": str(hoje - timedelta(days=300)),
            "purchase_price": "50000.00",
            "purchase_odometer": 20000,
            "current_odometer": 45000,
        }
        payload.update(kwargs)
        r = auth_client.post("/vehicles", json=payload)
        assert r.status_code == 201, r.text
        return r.json()

    return _criar


@pytest.fixture
def criar_motorista(auth_client: TestClient) -> Callable[..., dict]:
    contador = iter(range(1000))

    def _criar(**kwargs) -> dict:
        n = next(contador)
        payload = {
            "full_name": f"Motorista {n}",
            "cpf": f"{10000000000 + n}",
            "cnh_number": f"{99887766 + n}",
            "cnh_category": "B",
            "phone": "11999998888",
        }
        payload.update(kwargs)
        r = auth_client.post("/drivers", json=payload)
        assert r.status_code == 201, r.text
        return r.json()

    return _criar


@pytest.fixture
def categorias(auth_client: TestClient) -> dict[str, int]:
    """`{'manutencao': 1, 'melhorias': 13, ...}` — o id da categoria pelo code estável."""
    r = auth_client.get("/expense-categories")
    assert r.status_code == 200, r.text
    return {c["code"]: c["id"] for c in r.json()}


@pytest.fixture
def resultado(auth_client: TestClient) -> Callable[[str], dict]:
    """A conta do veículo: `GET /finance/vehicles/{id}`."""

    def _resultado(vehicle_id: str) -> dict:
        r = auth_client.get(f"/finance/vehicles/{vehicle_id}")
        assert r.status_code == 200, r.text
        return r.json()

    return _resultado


@pytest.fixture
def lucro(resultado) -> Callable[[str], Decimal]:
    """O número que decide o negócio: receitas − despesas − compra + venda."""

    def _lucro(vehicle_id: str) -> Decimal:
        return Decimal(resultado(vehicle_id)["profit"])

    return _lucro


@pytest.fixture
def lancar_receita(auth_client: TestClient, hoje: date) -> Callable[..., dict]:
    def _lancar(vehicle_id: str, amount: str, **kwargs) -> dict:
        payload = {
            "vehicle_id": vehicle_id,
            "category": "aluguel",
            "description": "Aluguel",
            "amount": amount,
            "competence_date": str(hoje),
            "due_date": str(hoje),
            "pay_now": True,
            "paid_on": str(hoje),
            "method": "pix",
        }
        payload.update(kwargs)
        r = auth_client.post("/revenues", json=payload)
        assert r.status_code == 201, r.text
        return r.json()

    return _lancar


@pytest.fixture
def lancar_despesa(
    auth_client: TestClient, categorias: dict[str, int], hoje: date
) -> Callable[..., dict]:
    def _lancar(vehicle_id: str, amount: str, categoria: str = "manutencao", **kwargs) -> dict:
        payload = {
            "vehicle_id": vehicle_id,
            "category_id": categorias[categoria],
            "description": f"Despesa de {categoria}",
            "amount": amount,
            "competence_date": str(hoje - timedelta(days=30)),
            "paid_on": str(hoje - timedelta(days=30)),
            "status": "paid",
        }
        payload.update(kwargs)
        r = auth_client.post("/expenses", json=payload)
        assert r.status_code == 201, r.text
        return r.json()

    return _lancar
