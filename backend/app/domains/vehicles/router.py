import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.domains.auth.deps import AdminUser, CurrentUser, Db
from app.domains.contracts import service as contracts_service
from app.domains.vehicles.models import Vehicle, VehicleStatus
from app.domains.vehicles.schemas import VehicleCreate, VehicleOut, VehicleSell, VehicleUpdate

router = APIRouter(prefix="/vehicles", tags=["veículos"])

_NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")


def _get(db: Session, vehicle_id: UUID) -> Vehicle:
    """Veículo soft-deletado é, para todos os efeitos, inexistente."""
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFound("Veículo não encontrado.")
    return vehicle


def _check_unique(
    db: Session,
    *,
    plate: str | None = None,
    renavam: str | None = None,
    chassi: str | None = None,
    exclude_id: UUID | None = None,
) -> None:
    """Placa, RENAVAM e chassi são UNIQUE no banco.

    Sem esta checagem o duplicado vira IntegrityError → HTTP 500 "erro interno", em vez de
    uma mensagem que o operador entende. A busca inclui os soft-deletados de propósito:
    eles ainda ocupam a placa no índice único.
    """
    for field, value, message in (
        (Vehicle.plate, plate, "Já existe um veículo com essa placa"),
        (Vehicle.renavam, renavam, "Já existe um veículo com esse RENAVAM"),
        (Vehicle.chassi, chassi, "Já existe um veículo com esse chassi"),
    ):
        if not value:
            continue
        stmt = select(Vehicle).where(field == value)
        if exclude_id:
            stmt = stmt.where(Vehicle.id != exclude_id)
        found = db.scalar(stmt)
        if found:
            suffix = " (registro excluído)." if found.deleted_at else f" ({found.code})."
            raise Conflict(message + suffix)


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    db: Db,
    _: CurrentUser,
    status: VehicleStatus | None = None,
    q: str | None = None,
):
    """Frota ativa. Soft-deletados nunca aparecem."""
    stmt = select(Vehicle).where(Vehicle.deleted_at.is_(None))

    if status:
        stmt = stmt.where(Vehicle.status == status)

    if q and q.strip():
        term = f"%{q.strip()}%"
        # Quem digita "ABC-1234" na busca tem que achar a placa gravada como "ABC1234".
        plate_term = f"%{_NOT_ALNUM.sub('', q)}%"
        stmt = stmt.where(
            or_(
                Vehicle.plate.ilike(plate_term),
                Vehicle.model.ilike(term),
                Vehicle.brand.ilike(term),
                Vehicle.code.ilike(term),
            )
        )

    return db.scalars(stmt.order_by(Vehicle.plate)).all()


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(data: VehicleCreate, db: Db, _: CurrentUser):
    if data.status == VehicleStatus.sold:
        raise Conflict("Para marcar como vendido, use a ação de venda do veículo.")

    _check_unique(db, plate=data.plate, renavam=data.renavam, chassi=data.chassi)

    vehicle = Vehicle(**data.model_dump())
    db.add(vehicle)
    db.commit()
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: UUID, db: Db, _: CurrentUser):
    return _get(db, vehicle_id)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: UUID, data: VehicleUpdate, db: Db, _: CurrentUser):
    vehicle = _get(db, vehicle_id)
    fields = data.model_dump(exclude_unset=True)

    if fields.get("status") == VehicleStatus.sold:
        raise Conflict("Para marcar como vendido, use a ação de venda do veículo.")

    _check_unique(
        db,
        plate=fields.get("plate"),
        renavam=fields.get("renavam"),
        chassi=fields.get("chassi"),
        exclude_id=vehicle.id,
    )

    # Odômetro só anda para frente. Ao contrário, `km_driven` fica negativo e `custo_por_km`
    # some da tela (a API devolve NULL) sem ninguém entender por quê. A validação existia só
    # no formulário; aqui ela vale também para quem chama a API direto.
    # Conferido ANTES do setattr: a sessão não pode ficar com alteração pendente ao levantar.
    atual = fields.get("current_odometer", vehicle.current_odometer)
    compra = fields.get("purchase_odometer", vehicle.purchase_odometer)
    if atual < compra:
        raise Conflict(
            f"O odômetro atual ({atual} km) não pode ser menor que o da compra ({compra} km)."
        )

    for key, value in fields.items():
        setattr(vehicle, key, value)

    db.commit()
    return vehicle


@router.post("/{vehicle_id}/sell", response_model=VehicleOut)
def sell_vehicle(vehicle_id: UUID, data: VehicleSell, db: Db, _: AdminUser):
    """Fecha o ciclo de vida do carro.

    O valor de venda mora AQUI e em nenhum outro lugar (ARQUITETURA.md, regra 4): lançá-lo
    também como receita contaria o lucro do carro em dobro.
    """
    vehicle = _get(db, vehicle_id)

    if vehicle.status == VehicleStatus.sold or vehicle.sale_date is not None:
        raise Conflict("Este veículo já foi vendido.")

    # A venda FECHA a conta do veículo. Um contrato ativo continuaria gerando cobrança
    # semanal para um carro que não é mais do dono — receita fantasma entrando num
    # resultado que já deveria estar fechado — e a caução do motorista ficaria presa num
    # contrato de um carro que não existe mais na frota. O espelho desta regra já existe
    # na criação do contrato ("veículo vendido não pode ser alugado").
    em_uso = contracts_service.active_contract_for_vehicle(db, vehicle.id)
    if em_uso:
        raise Conflict(
            f"O veículo tem um contrato ativo ({em_uso.code}). Encerre o contrato — "
            "acertando a caução — antes de vender."
        )

    if data.sale_date < vehicle.purchase_date:
        raise Conflict("A data de venda não pode ser anterior à data de compra.")

    vehicle.sale_price = data.sale_price
    vehicle.sale_date = data.sale_date
    vehicle.status = VehicleStatus.sold

    db.commit()
    return vehicle


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: UUID, db: Db, _: AdminUser):
    """Soft delete — SEMPRE.

    O veículo carrega receitas e despesas atrás dele; um DELETE físico levaria junto (ou
    barraria no FK) o histórico que sustenta o cálculo de lucro. Some da lista, continua na
    contabilidade.
    """
    vehicle = _get(db, vehicle_id)

    # A MESMA regra da venda, pela outra porta. Sair da frota com contrato ativo deixa o
    # contrato `active`: `generate_all_charges` itera contratos por STATUS e não olha o
    # veículo, então ele continuaria criando aluguel semanal, para sempre, para um carro
    # que já não está na frota — e a caução do motorista ficaria presa num contrato de um
    # carro cuja conta ninguém mais consegue abrir (o resultado responde 404).
    em_uso = contracts_service.active_contract_for_vehicle(db, vehicle.id)
    if em_uso:
        raise Conflict(
            f"O veículo tem um contrato ativo ({em_uso.code}). Encerre o contrato — "
            "acertando a caução — antes de excluir."
        )

    vehicle.deleted_at = datetime.now(UTC)
    db.commit()
