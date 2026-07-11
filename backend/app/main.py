import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core import paths
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal, engine
from app.domains.audit import listeners  # noqa: F401  — registra o listener de auditoria
from app.domains.audit.router import router as audit_router
from app.domains.auth.router import router as auth_router
from app.domains.contracts.router import router as contracts_router
from app.domains.drivers.router import router as drivers_router
from app.domains.expenses.router import router as expenses_router
from app.domains.files.router import router as files_router
from app.domains.finance.router import router as finance_router
from app.domains.fines.router import router as fines_router
from app.domains.inspections.router import router as inspections_router
from app.domains.maintenances.router import router as maintenances_router
from app.domains.revenues.router import router as revenues_router
from app.domains.users.router import router as users_router
from app.domains.vehicles.router import router as vehicles_router
from app.seed import seed

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def _migrate() -> None:
    """Aplica as migrações pendentes no boot.

    Num app de desktop ninguém vai abrir um terminal para rodar `alembic upgrade head`.
    É idempotente: se já está atualizado, não faz nada.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(paths.alembic_ini()))
    cfg.set_main_option("script_location", str(paths.migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    _migrate()
    with SessionLocal() as db:
        seed(db)
    logger.info("ERP Frota pronto.")
    yield


app = FastAPI(
    title="ERP Frota",
    description="Gestão de frota de locação para motoristas de aplicativo.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # usamos Bearer, não cookie
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

register_exception_handlers(app)

for r in (
    auth_router,
    users_router,
    vehicles_router,
    drivers_router,
    contracts_router,
    revenues_router,
    expenses_router,
    maintenances_router,
    fines_router,
    inspections_router,
    files_router,
    finance_router,
    audit_router,
):
    app.include_router(r)


@app.get("/health", tags=["infra"])
def health():
    """Healthcheck de verdade: pergunta ao banco, não devolve um dict estático."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "erro", "db": "down"})
    return {"status": "ok", "db": "up"}


# ---------------------------------------------------------------------------
# A interface, servida pela própria API (só no app empacotado).
#
# As rotas da API são em inglês (/vehicles, /revenues) e as da interface em português
# (/veiculos, /cobrancas): não colidem. Por isso as duas convivem na mesma porta, sem
# CORS e sem um servidor web separado.
#
# O catch-all fica por ÚLTIMO de propósito: o FastAPI casa as rotas na ordem de registro,
# então tudo que é API já foi resolvido acima. O que sobra é rota do React Router e tem
# que devolver o index.html (senão dar F5 em /veiculos/123 daria 404).
# ---------------------------------------------------------------------------
_static = paths.static_dir()

if _static.is_dir():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    _index = _static / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path:
            arquivo = (_static / full_path).resolve()
            # `full_path` vem da URL: sem esta checagem, "../../.env" leria fora da pasta.
            dentro_da_pasta = arquivo.is_relative_to(_static.resolve())
            if dentro_da_pasta and arquivo.is_file():
                return FileResponse(arquivo)  # favicon.svg, icons.svg, manifest...
        return FileResponse(_index)
else:
    logger.info("Sem interface compilada em %s — rodando só a API (modo dev).", _static)
