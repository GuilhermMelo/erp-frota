/**
 * Tipos das respostas da API para veículos e para a conta do veículo.
 *
 * ATENÇÃO: dinheiro é `string` — é `Decimal` no backend e não pode virar float.
 * Use `formatMoney()` para exibir. Nunca some/subtraia aqui: a conta é do backend.
 */

/** Dinheiro. String ("50000.00") de propósito. */
export type Money = string
/** Dinheiro que a API pode devolver `null` (indefinido, não zero) — a tela mostra "—". */
export type MoneyOrNull = string | null

export type VehicleStatus = 'available' | 'rented' | 'maintenance' | 'sold' | 'inactive'

export type FuelType =
  | 'flex'
  | 'gasolina'
  | 'etanol'
  | 'diesel'
  | 'gnv'
  | 'hibrido'
  | 'eletrico'

/** GET /vehicles e GET /vehicles/{id} */
export type Vehicle = {
  id: string
  code: string
  plate: string
  renavam: string | null
  chassi: string | null

  brand: string
  model: string
  version: string | null
  manufacture_year: number
  model_year: number
  color: string | null
  fuel_type: FuelType

  purchase_date: string
  purchase_price: Money
  purchase_odometer: number
  current_odometer: number

  sale_date: string | null
  sale_price: MoneyOrNull
  estimated_market_value: MoneyOrNull

  status: VehicleStatus
  notes: string | null
  created_at: string
  updated_at: string
}

/**
 * GET /finance/vehicles/{id} e GET /finance/fleet — A CONTA DO VEÍCULO.
 *
 *   profit = total_received − total_cost − investment + sale_price
 *   investment = purchase_price + total_capex   (compra + melhorias)
 *
 * `roi`, `cost_per_km`, `revenue_per_km` e `profit_if_sold_today` vêm `null` quando a
 * pergunta não tem resposta (investimento zero, carro que não rodou, carro sem valor de
 * mercado estimado). Devolver 0 seria mentir — a tela mostra "—".
 */
export type VehicleResult = {
  vehicle_id: string
  code: string
  plate: string
  brand: string
  model: string
  status: VehicleStatus

  purchase_price: Money
  purchase_date: string
  sale_price: MoneyOrNull
  sale_date: string | null
  estimated_market_value: MoneyOrNull

  /** Regime de caixa: o que ENTROU de verdade. */
  total_received: Money
  /** Despesa paga de operação (não-capex). */
  total_cost: Money
  /** Despesa paga que é investimento no carro (blindagem, kit gás...). */
  total_capex: Money
  /** Em aberto — nunca escondido dentro do lucro. */
  total_receivable: Money
  total_expense_pending: Money

  investment: Money
  profit: Money
  profit_if_sold_today: MoneyOrNull

  roi: MoneyOrNull
  cost_per_km: MoneyOrNull
  revenue_per_km: MoneyOrNull
  km_driven: number

  /**
   * Payback. `payback_month` é o mês em que o acumulado alcançou o investimento.
   * `payback_months_remaining` é a estimativa do que falta (pela média dos últimos 3 meses
   * com lucro). Vem tudo `null` quando não dá para saber — o carro não está gerando lucro
   * mensal, e chutar um prazo seria inventar número.
   */
  payback_month: string | null
  payback_months_elapsed: number | null
  payback_months_remaining: number | null
}

/* ---------- Lançamentos que compõem os números (auditoria) ---------- */

export type RevenueCategory = 'aluguel' | 'reembolso' | 'caucao_retida' | 'outros'
export type RevenueStatus = 'pending' | 'partial' | 'paid' | 'canceled'

/** GET /revenues?vehicle_id= */
export type Revenue = {
  id: string
  code: string
  vehicle_id: string
  category: RevenueCategory
  description: string | null
  amount: Money
  /** O que foi efetivamente recebido desta cobrança. É o que soma em `total_received`. */
  paid_amount: Money
  competence_date: string
  due_date: string
  status: RevenueStatus
}

export type ExpenseStatus = 'pending' | 'paid'

export type ExpenseCategory = {
  id: number
  code: string
  name: string
  /** Separa INVESTIMENTO no carro (capex) de CUSTO de operação. */
  is_capex: boolean
}

/** GET /expenses?vehicle_id= */
export type Expense = {
  id: string
  code: string
  vehicle_id: string
  category: ExpenseCategory
  supplier_name: string | null
  description: string | null
  amount: Money
  competence_date: string
  paid_on: string | null
  status: ExpenseStatus
}

/** GET /maintenances?vehicle_id= */
export type Maintenance = {
  id: string
  code: string
  kind: string
  description: string | null
  supplier_name: string | null
  amount: Money
  performed_on: string
  odometer: number
}

export type FineStatus = 'pending' | 'paid' | 'canceled'

/** GET /fines?vehicle_id= */
export type Fine = {
  id: string
  code: string
  infraction_date: string
  description: string
  amount: Money
  /** Quanto a multa custou DE VERDADE ao carro (já descontado o reembolso do motorista). */
  net_cost: Money
  status: FineStatus
  paid_on: string | null
  driver: { id: string; code: string; full_name: string } | null
}

export type InspectionKind = 'entrega' | 'devolucao' | 'periodica'

/** GET /inspections?vehicle_id= */
export type Inspection = {
  id: string
  code: string
  kind: InspectionKind
  inspected_at: string
  odometer: number
  driver: { id: string; code: string; full_name: string } | null
}

export type ContractStatus = 'active' | 'finished' | 'canceled'

/** GET /contracts?vehicle_id= */
export type Contract = {
  id: string
  code: string
  start_date: string
  end_date: string | null
  weekly_amount: Money
  deposit_amount: Money
  status: ContractStatus
  driver: { id: string; code: string; full_name: string } | null
}

/* ---------- Rótulos ---------- */

export const FUEL_TYPES: Record<FuelType, string> = {
  flex: 'Flex',
  gasolina: 'Gasolina',
  etanol: 'Etanol',
  diesel: 'Diesel',
  gnv: 'GNV',
  hibrido: 'Híbrido',
  eletrico: 'Elétrico',
}

export const REVENUE_CATEGORIES: Record<RevenueCategory, string> = {
  aluguel: 'Aluguel',
  reembolso: 'Reembolso',
  caucao_retida: 'Caução retida',
  outros: 'Outros',
}

export const EXPENSE_STATUS: Record<ExpenseStatus, { label: string; className: string }> = {
  pending: { label: 'Pendente', className: 'bg-amber-100 text-amber-800' },
  paid: { label: 'Paga', className: 'bg-emerald-100 text-emerald-800' },
}

export const FINE_STATUS: Record<FineStatus, { label: string; className: string }> = {
  pending: { label: 'Em aberto', className: 'bg-amber-100 text-amber-800' },
  paid: { label: 'Paga', className: 'bg-emerald-100 text-emerald-800' },
  canceled: { label: 'Cancelada', className: 'bg-slate-100 text-slate-500' },
}

export const CONTRACT_STATUS: Record<ContractStatus, { label: string; className: string }> = {
  active: { label: 'Ativo', className: 'bg-emerald-100 text-emerald-800' },
  finished: { label: 'Encerrado', className: 'bg-slate-200 text-slate-700' },
  canceled: { label: 'Cancelado', className: 'bg-slate-100 text-slate-500' },
}

export const INSPECTION_KINDS: Record<InspectionKind, string> = {
  entrega: 'Entrega',
  devolucao: 'Devolução',
  periodica: 'Periódica',
}
