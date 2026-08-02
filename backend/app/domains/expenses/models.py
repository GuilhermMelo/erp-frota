from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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


class ExpenseOrigin(str, Enum):
    manual = "manual"
    maintenance = "maintenance"  # gerada por uma manutenção
    fine = "fine"                # gerada ao pagar uma multa


class ExpenseStatus(str, Enum):
    pending = "pending"
    paid = "paid"


class ExpenseCategory(Base):
    """Categoria de despesa — TABELA, não enum.

    O dono vai inventar "pedágio", "rastreador", "estacionamento" às 23h. Isso tem que
    ser uma linha no banco, não um deploy. (As categorias de RECEITA são enum porque são
    poucas e cada uma carrega regra de negócio — a assimetria é proposital.)
    """

    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # is_capex separa INVESTIMENTO no carro (blindagem, kit gás) de CUSTO de operação
    # (óleo, IPVA). Sem isso, uma blindagem de R$ 15 mil viraria "custo do mês" e
    # destruiria o custo por km.
    is_capex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Expense(UUIDPrimaryKey, TimestampMixin, Base):
    """Despesa do veículo.

    ATENÇÃO: o VALOR DE COMPRA do carro NÃO é despesa (mora em vehicles.purchase_price).
    Lançá-lo aqui contaria o custo em dobro.
    """

    __tablename__ = "expenses"

    code: Mapped[str] = code_column("DES", "expense_code_seq")

    # NULO = despesa da EMPRESA (contador, internet, aluguel da sala), que não é de carro
    # nenhum. Precisa ser uma escolha EXPLÍCITA na tela ("é da empresa"), nunca um campo
    # deixado em branco por descuido: despesa sem carro some do lucro daquele carro, e o
    # dono só descobre meses depois, na hora de decidir se compra o próximo.
    # A despesa da empresa aparece separada no painel, justamente para não sumir da vista.
    vehicle_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    # Motorista associado (ex.: a multa foi dele). Serve para saber quanto cada um te deve.
    driver_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    maintenance_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("maintenances.id", ondelete="CASCADE"), index=True
    )
    fine_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("fines.id", ondelete="CASCADE"), index=True
    )

    supplier_name: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    competence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    paid_on: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[ExpenseStatus] = mapped_column(
        SAEnum(ExpenseStatus, native_enum=False, length=20, name="expense_status"),
        default=ExpenseStatus.paid,
        nullable=False,
        index=True,
    )
    origin: Mapped[ExpenseOrigin] = mapped_column(
        SAEnum(ExpenseOrigin, native_enum=False, length=20, name="expense_origin"),
        default=ExpenseOrigin.manual,
        nullable=False,
    )

    odometer: Mapped[int | None] = mapped_column(Integer)
    document_number: Mapped[str | None] = mapped_column(String(60))
    notes: Mapped[str | None] = mapped_column(Text)

    # LIXEIRA — mesma regra da receita (ver revenues/models.py). Despesa na lixeira NÃO conta
    # no custo do veículo; o filtro vive em finance/queries.py.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    category = relationship("ExpenseCategory", lazy="joined")

    __table_args__ = (
        CheckConstraint("amount > 0", name="valor_positivo"),
        # Despesa paga precisa ter data de pagamento — senão some do regime de caixa.
        CheckConstraint(
            "(status = 'paid') = (paid_on IS NOT NULL)", name="paga_exige_data_pagamento"
        ),
        Index("ix_expenses_veiculo_pagamento", "vehicle_id", "paid_on"),
    )
