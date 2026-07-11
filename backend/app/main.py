import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        seed(db)
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
