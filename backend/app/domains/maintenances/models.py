from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import MONEY, Base, TimestampMixin, UUIDPrimaryKey, code_column


class Maintenance(UUIDPrimaryKey, TimestampMixin, Base):
    """Histórico de manutenção — simples, como pedido.

    Adiciona-se a manutenção com KM e data. NÃO há plano preventivo, NÃO há lembrete,
    NÃO há cálculo de "próxima troca". Se um dia isso for pedido, `odometer` e
    `performed_on` já são os dois campos de que o cálculo precisa.

    Ao salvar, o service gera a DESPESA correspondente (origin='maintenance') — para não
    digitar o mesmo valor duas vezes. A despesa é encontrada por expenses.maintenance_id.
    """

    __tablename__ = "maintenances"

    code: Mapped[str] = code_column("MAN", "maintenance_code_seq")

    vehicle_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Texto livre ("troca de óleo", "pastilhas de freio"). Enum aqui só engessaria.
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    supplier_name: Mapped[str | None] = mapped_column(String(120))

    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    performed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)

    vehicle = relationship("Vehicle", lazy="joined")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="valor_nao_negativo"),
        CheckConstraint("odometer >= 0", name="odometro_nao_negativo"),
        Index("ix_maintenances_veiculo_data", "vehicle_id", "performed_on"),
    )
