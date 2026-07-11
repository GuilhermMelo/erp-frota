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
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import MONEY, Base, TimestampMixin, UUIDPrimaryKey, code_column


class RevenueCategory(str, Enum):
    aluguel = "aluguel"
    reembolso = "reembolso"          # motorista devolvendo o valor de uma multa
    caucao_retida = "caucao_retida"  # a parte da caução que você ficou (por avaria, dívida...)
    outros = "outros"
    # NÃO existe "venda_veiculo": a venda mora em vehicles.sale_price.
    # NÃO existe "caucao": a caução mora em contracts.deposit_amount e não é sua.


class RevenueStatus(str, Enum):
    pending = "pending"
    partial = "partial"
    paid = "paid"
    canceled = "canceled"
    # NÃO existe "overdue": atraso é DERIVADO (pending/partial + due_date < hoje).
    # Estado armazenado precisaria de job noturno e ficaria desatualizado.


class RevenueOrigin(str, Enum):
    manual = "manual"
    contract = "contract"  # cobrança semanal gerada pelo contrato


class PaymentMethod(str, Enum):
    pix = "pix"
    dinheiro = "dinheiro"
    transferencia = "transferencia"
    cartao = "cartao"
    boleto = "boleto"
    outro = "outro"


class Revenue(UUIDPrimaryKey, TimestampMixin, Base):
    """Receita — modelada como CONTA A RECEBER desde o dia 1.

    No uso simples ("recebi R$ 800 hoje") a tela cria a receita já `paid` com um
    pagamento junto, e o operador não vê a maquinaria. Mas como `due_date`, `status` e
    `origin` já existem, a cobrança semanal do contrato é só um INSERT — sem migrar
    nenhuma linha depois.
    """

    __tablename__ = "revenues"

    code: Mapped[str] = code_column("REC", "revenue_code_seq")

    vehicle_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="RESTRICT"), index=True
    )
    contract_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contracts.id", ondelete="RESTRICT"), index=True
    )
    fine_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("fines.id", ondelete="RESTRICT"), index=True
    )

    category: Mapped[RevenueCategory] = mapped_column(
        SAEnum(RevenueCategory, native_enum=False, length=20, name="revenue_category"),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Denormalizado de propósito: mantido pelo RevenueService a cada pagamento, para que
    # a consulta de inadimplência não precise agregar revenue_payments.
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"), nullable=False)

    competence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    status: Mapped[RevenueStatus] = mapped_column(
        SAEnum(RevenueStatus, native_enum=False, length=20, name="revenue_status"),
        default=RevenueStatus.pending,
        nullable=False,
        index=True,
    )
    origin: Mapped[RevenueOrigin] = mapped_column(
        SAEnum(RevenueOrigin, native_enum=False, length=20, name="revenue_origin"),
        default=RevenueOrigin.manual,
        nullable=False,
    )

    # A semana que esta cobrança cobre (só para receitas geradas por contrato).
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)

    notes: Mapped[str | None] = mapped_column(Text)

    payments = relationship(
        "RevenuePayment", back_populates="revenue", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # Idempotência da cobrança semanal: gerar duas vezes a mesma semana do mesmo
        # contrato é impossível. Por isso a geração pode rodar toda vez que o app abre,
        # sem cron e sem medo.
        UniqueConstraint("contract_id", "period_start", name="uq_revenues_contrato_semana"),
        CheckConstraint("amount > 0", name="valor_positivo"),
        CheckConstraint(
            "paid_amount >= 0 AND paid_amount <= amount", name="pago_dentro_do_valor"
        ),
        # Sustenta a tela de inadimplência.
        Index(
            "ix_revenues_em_aberto",
            "due_date",
            postgresql_where=text("status IN ('pending', 'partial')"),
        ),
        Index("ix_revenues_veiculo_vencimento", "vehicle_id", "due_date"),
    )


class RevenuePayment(UUIDPrimaryKey, Base):
    """Um recebimento. Uma receita pode ter vários (pagamento parcial)."""

    __tablename__ = "revenue_payments"

    revenue_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("revenues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, native_enum=False, length=20, name="payment_method"),
        default=PaymentMethod.pix,
        nullable=False,
    )
    receipt_ref: Mapped[str | None] = mapped_column(String(80))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    revenue = relationship("Revenue", back_populates="payments")

    __table_args__ = (CheckConstraint("amount > 0", name="valor_positivo"),)
