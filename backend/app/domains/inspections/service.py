"""Regras da vistoria.

A vistoria é a prova objetiva numa discussão sobre quem quebrou o quê. Duas decisões
sustentam isso:

- O checklist nasce COMPLETO (todos os itens em `ok`) quando ninguém manda itens. Um
  checklist meio preenchido não prova nada — "o item não estava na lista" é a brecha que
  o motorista usa.
- O KM só anda para frente: uma vistoria com odômetro maior atualiza o veículo. Aceitar
  KM para trás corromperia o custo por km da frota inteira.
"""

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.core.storage import storage
from app.domains.contracts.models import Contract
from app.domains.drivers.models import Driver
from app.domains.files import service as files_service
from app.domains.inspections.models import (
    ChecklistItem,
    Inspection,
    InspectionItem,
    InspectionPhoto,
    ItemCondition,
    PhotoCategory,
)
from app.domains.inspections.schemas import InspectionCreate, InspectionItemIn, InspectionUpdate
from app.domains.users.models import User
from app.domains.vehicles.models import Vehicle

# Pasta do storage. As fotos ficam em inspections/VST000001/....
NAMESPACE = "inspections"
# O frontend sobe 3-4 fotos em paralelo, poucas por request. O teto existe para que um
# request não carregue 200 arquivos na memória de uma vez.
MAX_PHOTOS_PER_REQUEST = 10


def active_checklist_items(db: Session) -> list[ChecklistItem]:
    return list(
        db.scalars(
            select(ChecklistItem)
            .where(ChecklistItem.is_active.is_(True))
            .order_by(ChecklistItem.group_name, ChecklistItem.sort_order)
        ).all()
    )


def get_inspection(db: Session, inspection_id: UUID) -> Inspection:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise NotFound("Vistoria não encontrada.")
    return inspection


def get_photo(db: Session, photo_id: UUID) -> InspectionPhoto:
    photo = db.get(InspectionPhoto, photo_id)
    if photo is None:
        raise NotFound("Foto não encontrada.")
    return photo


def _get_vehicle(db: Session, vehicle_id: UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFound("Veículo não encontrado.")
    return vehicle


def _check_links(db: Session, driver_id: UUID | None, contract_id: UUID | None) -> None:
    if driver_id is not None:
        driver = db.get(Driver, driver_id)
        if driver is None or driver.deleted_at is not None:
            raise NotFound("Motorista não encontrado.")
    if contract_id is not None and db.get(Contract, contract_id) is None:
        raise NotFound("Contrato não encontrado.")


def _no_duplicates(items: list[InspectionItemIn]) -> None:
    ids = [item.checklist_item_id for item in items]
    if len(set(ids)) != len(ids):
        # Sem isso, o UNIQUE(inspection_id, checklist_item_id) estouraria como erro 500.
        raise Conflict("O mesmo item do checklist foi enviado duas vezes.")


def _advance_odometer(vehicle: Vehicle, odometer: int) -> None:
    """KM só anda para frente. Objeto carregado, atributo alterado — nunca bulk DML,
    senão o listener de auditoria fica cego (ARQUITETURA.md, regra 3)."""
    if odometer > vehicle.current_odometer:
        vehicle.current_odometer = odometer


def create_inspection(db: Session, data: InspectionCreate, user: User) -> Inspection:
    vehicle = _get_vehicle(db, data.vehicle_id)
    _check_links(db, data.driver_id, data.contract_id)

    inspection = Inspection(
        vehicle_id=data.vehicle_id,
        driver_id=data.driver_id,
        contract_id=data.contract_id,
        user_id=user.id,  # quem fez a vistoria
        kind=data.kind,
        odometer=data.odometer,
        fuel_level=data.fuel_level,
        notes=data.notes,
    )

    if data.items:
        _no_duplicates(data.items)
        permitidos = {item.id for item in active_checklist_items(db)}
        for item in data.items:
            if item.checklist_item_id not in permitidos:
                raise NotFound(f"Item do checklist não encontrado: {item.checklist_item_id}.")
        inspection.items = [
            InspectionItem(
                checklist_item_id=item.checklist_item_id,
                condition=item.condition,
                notes=item.notes,
            )
            for item in data.items
        ]
    else:
        # Nasce com o checklist inteiro em `ok`; o operador só marca o que estiver errado.
        inspection.items = [
            InspectionItem(checklist_item_id=item.id, condition=ItemCondition.ok)
            for item in active_checklist_items(db)
        ]

    _advance_odometer(vehicle, data.odometer)

    db.add(inspection)
    db.commit()
    return inspection


def update_inspection(db: Session, inspection: Inspection, data: InspectionUpdate) -> Inspection:
    fields = data.model_dump(exclude_unset=True)
    fields.pop("items", None)  # os itens não são um `setattr` — têm regra própria abaixo.

    if "driver_id" in fields or "contract_id" in fields:
        _check_links(
            db,
            fields.get("driver_id", inspection.driver_id),
            fields.get("contract_id", inspection.contract_id),
        )

    for key, value in fields.items():
        setattr(inspection, key, value)

    if data.items is not None:
        _apply_items(db, inspection, data.items)

    if "odometer" in fields:
        _advance_odometer(inspection.vehicle, inspection.odometer)

    db.commit()
    return inspection


def _apply_items(db: Session, inspection: Inspection, items: list[InspectionItemIn]) -> None:
    """Atualiza a condição dos itens. Item que ainda não está na vistoria é criado —
    um item de checklist novo entra numa vistoria antiga sem migração."""
    _no_duplicates(items)
    atuais = {item.checklist_item_id: item for item in inspection.items}
    catalogo = {item.id: item for item in db.scalars(select(ChecklistItem)).all()}

    for entrada in items:
        item = atuais.get(entrada.checklist_item_id)
        if item is None:
            no_catalogo = catalogo.get(entrada.checklist_item_id)
            if no_catalogo is None or not no_catalogo.is_active:
                raise NotFound(f"Item do checklist não encontrado: {entrada.checklist_item_id}.")
            item = InspectionItem(checklist_item_id=entrada.checklist_item_id)
            inspection.items.append(item)  # cascade cuida do INSERT
        item.condition = entrada.condition
        item.notes = entrada.notes


def add_photos(
    db: Session,
    inspection: Inspection,
    files: list[UploadFile],
    category: PhotoCategory,
    caption: str | None,
) -> list[InspectionPhoto]:
    if not files:
        raise AppError("Envie ao menos um arquivo.")
    if len(files) > MAX_PHOTOS_PER_REQUEST:
        raise AppError(f"Envie no máximo {MAX_PHOTOS_PER_REQUEST} fotos por vez.")

    # Valida TODAS antes de gravar QUALQUER uma: metade das fotos no disco e a outra metade
    # recusada é o pior dos mundos.
    uploads = [files_service.read_upload(file) for file in files]

    proxima_ordem = max((photo.sort_order for photo in inspection.photos), default=-1) + 1
    criadas = []
    for offset, upload in enumerate(uploads):
        photo = InspectionPhoto(
            storage_key=files_service.save(NAMESPACE, inspection.code, upload),
            category=category,
            caption=caption,
            original_filename=upload.filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size,
            sort_order=proxima_ordem + offset,
        )
        inspection.photos.append(photo)
        criadas.append(photo)

    db.commit()
    return criadas


def delete_photo(db: Session, photo: InspectionPhoto) -> None:
    storage_key = photo.storage_key
    # Primeiro a linha (com log de auditoria), depois o arquivo — o banco é o índice do
    # que existe. Arquivo órfão é lixo invisível; linha órfã é tela quebrada.
    db.delete(photo)
    db.commit()
    storage.delete(storage_key)
