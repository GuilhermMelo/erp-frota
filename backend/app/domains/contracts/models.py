from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import MONEY, Base, TimestampMixin, UUIDPrimaryKey, code_column


class ContractStatus(str, Enum):
    active = "active"
    finished = "finished"
    canceled = "canceled"


class DepositStatus(str, Enum):
    held = "held"       # a caução está com você — NÃO é receita
    settled = "settled"  # encerrada: devolvida e/ou retida


class Contract(UUIDPrimaryKey, TimestampMixin, Base):
    """Contrato de locação: um carro, um motorista, um valor semanal.

    ATENÇÃO (ver MANIFESTO.md): a CAUÇÃO NÃO É RECEITA. É dinheiro que você segura e
    devolve. Ela mora aqui, não em `revenues`. Só a parte efetivamente RETIDA no
    encerramento vira receita (categoria `caucao_retida`). Lançar a caução como receita
    infla o lucro do carro até o dia em que você devolver.
    """

    __tablename__ = "contracts"

    code: Mapped[str] = code_column("CTR", "contract_code_seq")

    vehicle_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)

    weekly_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # 0 = segunda ... 6 = domingo. Dia em que a cobrança semanal vence.
    billing_weekday: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    deposit_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"), nullable=False)
    deposit_status: Mapped[DepositStatus] = mapped_column(
        SAEnum(DepositStatus, native_enum=False, length=20, name="deposit_status"),
        default=DepositStatus.held,
        nullable=False,
    )
    deposit_returned_amount: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00"), nullable=False
    )
    deposit_settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus, native_enum=False, length=20, name="contract_status"),
        default=ContractStatus.active,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle = relationship("Vehicle", lazy="joined")
    driver = relationship("Driver", lazy="joined")

    __table_args__ = (
        # Um carro não pode estar alugado para dois motoristas ao mesmo tempo.
        # Índice parcial: a restrição só vale para contratos ativos.
        Index(
            "uq_contracts_veiculo_ativo",
            "vehicle_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint("weekly_amount > 0", name="valor_semanal_positivo"),
        CheckConstraint("billing_weekday BETWEEN 0 AND 6", name="dia_cobranca_valido"),
        CheckConstraint("deposit_amount >= 0", name="caucao_nao_negativa"),
        CheckConstraint(
            "deposit_returned_amount >= 0 AND deposit_returned_amount <= deposit_amount",
            name="caucao_devolvida_dentro_do_limite",
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="fim_depois_do_inicio"),
    )
