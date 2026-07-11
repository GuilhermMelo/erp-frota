from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKey, code_column


class InspectionKind(str, Enum):
    entrega = "entrega"
    devolucao = "devolucao"
    periodica = "periodica"


class ItemCondition(str, Enum):
    ok = "ok"
    avaria = "avaria"
    faltando = "faltando"
    na = "na"  # não se aplica


class PhotoCategory(str, Enum):
    frente = "frente"
    traseira = "traseira"
    lateral_esquerda = "lateral_esquerda"
    lateral_direita = "lateral_direita"
    interior = "interior"
    painel = "painel"
    motor = "motor"
    pneus = "pneus"
    avaria = "avaria"
    assinatura = "assinatura"  # foto da vistoria assinada
    outros = "outros"


class ChecklistItem(Base):
    """Catálogo de itens do checklist — TABELA, como as categorias de despesa.

    Item novo ("suporte de celular", "cadeirinha") é uma linha, não um deploy.
    """

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    group_name: Mapped[str] = mapped_column(String(40), nullable=False)  # exterior/interior/mecanica/documentos
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Inspection(UUIDPrimaryKey, TimestampMixin, Base):
    """Vistoria: checklist estruturado + fotos (inclusive a foto da assinatura).

    O checklist é a prova objetiva numa discussão sobre quem quebrou o quê — dá para
    comparar entrega × devolução item a item.
    """

    __tablename__ = "inspections"

    code: Mapped[str] = code_column("VST", "inspection_code_seq")

    vehicle_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="RESTRICT"), index=True
    )
    contract_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contracts.id", ondelete="RESTRICT"), index=True
    )
    # Funcionário que fez a vistoria.
    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    kind: Mapped[InspectionKind] = mapped_column(
        SAEnum(InspectionKind, native_enum=False, length=20, name="inspection_kind"),
        nullable=False,
        index=True,
    )
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_level: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # 0 a 100%
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle = relationship("Vehicle", lazy="joined")
    driver = relationship("Driver", lazy="joined")
    items = relationship(
        "InspectionItem", back_populates="inspection", cascade="all, delete-orphan", lazy="selectin"
    )
    photos = relationship(
        "InspectionPhoto",
        back_populates="inspection",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="InspectionPhoto.sort_order",
    )

    @property
    def photos_count(self) -> int:
        """Para a listagem não precisar buscar o detalhe de cada vistoria só para contar.

        `photos` é lazy="selectin", então já veio junto — não dispara query nova.
        """
        return len(self.photos)

    __table_args__ = (
        CheckConstraint("fuel_level BETWEEN 0 AND 100", name="combustivel_entre_0_e_100"),
        CheckConstraint("odometer >= 0", name="odometro_nao_negativo"),
    )


class InspectionItem(UUIDPrimaryKey, Base):
    __tablename__ = "inspection_items"

    inspection_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checklist_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("checklist_items.id", ondelete="RESTRICT"), nullable=False
    )
    condition: Mapped[ItemCondition] = mapped_column(
        SAEnum(ItemCondition, native_enum=False, length=20, name="item_condition"),
        default=ItemCondition.ok,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String(200))

    inspection = relationship("Inspection", back_populates="items")
    checklist_item = relationship("ChecklistItem", lazy="joined")

    __table_args__ = (
        UniqueConstraint("inspection_id", "checklist_item_id", name="uq_inspection_items_item"),
    )


class InspectionPhoto(UUIDPrimaryKey, Base):
    """Foto da vistoria.

    A imagem NÃO fica no banco — só a `storage_key`. O arquivo mora em disco e é servido
    pelo endpoint autenticado GET /files/{key}.
    """

    __tablename__ = "inspection_photos"

    inspection_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    category: Mapped[PhotoCategory] = mapped_column(
        SAEnum(PhotoCategory, native_enum=False, length=20, name="photo_category"),
        default=PhotoCategory.outros,
        nullable=False,
        index=True,
    )
    caption: Mapped[str | None] = mapped_column(String(160))
    original_filename: Mapped[str | None] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    inspection = relationship("Inspection", back_populates="photos")
