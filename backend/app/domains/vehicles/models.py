from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import MONEY, Base, TimestampMixin, UUIDPrimaryKey, code_column


class VehicleStatus(str, Enum):
    available = "available"
    rented = "rented"
    maintenance = "maintenance"
    sold = "sold"
    inactive = "inactive"


class FuelType(str, Enum):
    flex = "flex"
    gasolina = "gasolina"
    etanol = "etanol"
    diesel = "diesel"
    gnv = "gnv"
    hibrido = "hibrido"
    eletrico = "eletrico"


class Vehicle(UUIDPrimaryKey, TimestampMixin, Base):
    """O veículo é a unidade de lucro do negócio.

    ATENÇÃO (ver MANIFESTO.md): valor de compra e valor de venda moram AQUI e em
    nenhum outro lugar. Nunca criar categoria de receita "venda_veiculo" nem lançar
    a compra como despesa — o lucro do carro sairia contado em dobro.
    """

    __tablename__ = "vehicles"

    code: Mapped[str] = code_column("CAR", "vehicle_code_seq")

    plate: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    renavam: Mapped[str | None] = mapped_column(String(20), unique=True)
    chassi: Mapped[str | None] = mapped_column(String(30), unique=True)

    brand: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str | None] = mapped_column(String(80))
    # Ano de fabricação e ano do modelo são coisas diferentes no Brasil.
    manufacture_year: Mapped[int] = mapped_column(Integer, nullable=False)
    model_year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(String(30))
    fuel_type: Mapped[FuelType] = mapped_column(
        SAEnum(FuelType, native_enum=False, length=20, name="fuel_type"),
        default=FuelType.flex,
        nullable=False,
    )

    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    purchase_odometer: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_odometer: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sale_date: Mapped[date | None] = mapped_column(Date)
    sale_price: Mapped[Decimal | None] = mapped_column(MONEY)
    # Quanto o carro vale hoje, na sua estimativa. Responde "se eu vender agora, saio no lucro?"
    estimated_market_value: Mapped[Decimal | None] = mapped_column(MONEY)

    status: Mapped[VehicleStatus] = mapped_column(
        SAEnum(VehicleStatus, native_enum=False, length=20, name="vehicle_status"),
        default=VehicleStatus.available,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("purchase_price >= 0", name="purchase_price_nao_negativo"),
        CheckConstraint("sale_price IS NULL OR sale_price >= 0", name="sale_price_nao_negativo"),
        # Venda é um fato único: ou tem preço e data, ou não tem nenhum dos dois.
        CheckConstraint(
            "(sale_price IS NULL) = (sale_date IS NULL)", name="venda_preco_e_data_juntos"
        ),
        CheckConstraint("current_odometer >= 0", name="odometro_nao_negativo"),
    )
