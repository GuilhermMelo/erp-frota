from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy.exc import IntegrityError

from app.core.errors import Conflict
from app.domains.auth.deps import CurrentUser, Db
from app.domains.contracts import service
from app.domains.contracts.models import ContractStatus
from app.domains.contracts.schemas import (
    ChargesGeneratedOut,
    ContractCreate,
    ContractFinish,
    ContractOut,
    ContractUpdate,
)

router = APIRouter(prefix="/contracts", tags=["contratos"])


# A rota estática vem ANTES de /{contract_id}/... para não ser engolida pelo parâmetro.
@router.post("/generate-charges", response_model=ChargesGeneratedOut)
def generate_all_charges(db: Db, _: CurrentUser):
    """Gera as cobranças semanais de TODOS os contratos ativos até hoje.

    É idempotente (UNIQUE(contract_id, period_start)): o frontend chama isso toda vez que
    o app abre. Sem cron, sem job noturno, sem duplicar.
    """
    try:
        geradas = service.generate_all_charges(db)
    except IntegrityError:
        # Rede de proteção: duas gerações simultâneas (duas abas abrindo o app juntas).
        # A primeira ganhou; esta aborta inteira — no Postgres não há como salvar parte.
        db.rollback()
        raise Conflict("Uma geração de cobranças acabou de rodar. Recarregue a tela.") from None
    return ChargesGeneratedOut(geradas=len(geradas))


@router.get("", response_model=list[ContractOut])
def list_contracts(
    db: Db,
    _: CurrentUser,
    vehicle_id: UUID | None = None,
    driver_id: UUID | None = None,
    status: ContractStatus | None = None,
):
    return service.list_contracts(db, vehicle_id=vehicle_id, driver_id=driver_id, status=status)


@router.post("", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract(data: ContractCreate, db: Db, _: CurrentUser):
    """Cria o contrato, marca o veículo como alugado e já gera as cobranças vencidas."""
    return service.create_contract(db, data)


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: UUID, db: Db, _: CurrentUser):
    return service.get_contract(db, contract_id)


@router.patch("/{contract_id}", response_model=ContractOut)
def update_contract(contract_id: UUID, data: ContractUpdate, db: Db, _: CurrentUser):
    contract = service.get_contract(db, contract_id)
    return service.update_contract(db, contract, data)


@router.post("/{contract_id}/generate-charges", response_model=ChargesGeneratedOut)
def generate_contract_charges(contract_id: UUID, db: Db, _: CurrentUser):
    contract = service.get_contract(db, contract_id)
    try:
        geradas = service.generate_charges(db, contract)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("Uma geração de cobranças acabou de rodar. Recarregue a tela.") from None
    return ChargesGeneratedOut(geradas=len(geradas))


@router.post("/{contract_id}/finish", response_model=ContractOut)
def finish_contract(contract_id: UUID, data: ContractFinish, db: Db, user: CurrentUser):
    """Encerra o contrato, acerta a caução e libera o veículo.

    Só a caução RETIDA vira receita (`caucao_retida`) — o que voltou para o motorista
    nunca foi do dono (ver MANIFESTO.md).
    """
    contract = service.get_contract(db, contract_id)
    return service.finish_contract(db, contract, data, user_id=user.id)
