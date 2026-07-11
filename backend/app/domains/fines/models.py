from datetime import date
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import MONEY, Base, TimestampMixin, UUIDPrimaryKey, code_column


class FineStatus(str, Enum):
    pending = "pending"   # chegou, ainda não paga
    paid = "paid"         # você pagou → gerou despesa do carro
    canceled = "canceled"  # recurso deferido


class Fine(UUIDPrimaryKey, TimestampMixin, Base):
    """Multa.

    O fluxo (ver MANIFESTO.md):
      1. A multa chega  → registra aqui, vinculada ao CARRO e ao MOTORISTA.
      2. Você paga      → o service gera a DESPESA do carro (origin='fine').
      3. Motorista te reembolsa → gera a RECEITA (categoria='reembolso') ligada a esta multa.

    O líquido dá zero sozinho quando ele reembolsa, e vira custo real do carro quando não
    reembolsa. Registrar só as multas não-reembolsadas perderia o rastro de quanto você já
    pagou e de quanto cada motorista te deve.
    """

    __tablename__ = "fines"

    code: Mapped[str] = code_column("MUL", "fine_code_seq")

    vehicle_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Nem sempre se sabe quem estava dirigindo.
    driver_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="RESTRICT"), index=True
    )

    infraction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ait_number: Mapped[str | None] = mapped_column(String(40))  # nº do Auto de Infração
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))

    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    points: Mapped[int | None] = mapped_column(Integer)
    # Prazo legal para indicar o condutor. Guardado, mas SEM alerta automático (fora do
    # escopo acordado). Perder esse prazo custa ponto na CNH do dono e multa dobrada.
    driver_indication_deadline: Mapped[date | None] = mapped_column(Date)

    status: Mapped[FineStatus] = mapped_column(
        SAEnum(FineStatus, native_enum=False, length=20, name="fine_status"),
        default=FineStatus.pending,
        nullable=False,
        index=True,
    )
    paid_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle = relationship("Vehicle", lazy="joined")
    driver = relationship("Driver", lazy="joined")

    __table_args__ = (
        CheckConstraint("amount > 0", name="valor_positivo"),
        CheckConstraint("(status = 'paid') = (paid_on IS NOT NULL)", name="paga_exige_data"),
        Index("ix_fines_veiculo_data", "vehicle_id", "infraction_date"),
    )
