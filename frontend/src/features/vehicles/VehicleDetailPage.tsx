import { useState, type ReactNode } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, TriangleAlert } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'

import { api, errorMessage } from '../../api/client'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Modal,
  MoneyInput,
  PageHeader,
  Spinner,
  Table,
  Td,
  Th,
  cn,
} from '../../components/ui'
import {
  REVENUE_STATUS,
  VEHICLE_STATUS,
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
  moneyClass,
  today,
} from '../../lib/format'
import { useAuth } from '../auth/AuthContext'
import {
  CONTRACT_STATUS,
  EXPENSE_STATUS,
  FINE_STATUS,
  FUEL_TYPES,
  INSPECTION_KINDS,
  REVENUE_CATEGORIES,
  type Contract,
  type Expense,
  type Fine,
  type Inspection,
  type Maintenance,
  type Money,
  type MoneyOrNull,
  type Revenue,
  type Vehicle,
  type VehicleResult,
} from './types'

/** Qual conjunto de lançamentos o operador pediu para auditar. */
type Ledger = 'received' | 'receivable' | 'cost' | 'capex' | 'expense_pending' | null
type Tab = 'maintenances' | 'fines' | 'inspections' | 'contracts'

const moneyRegex = /^\d+([.,]\d{1,2})?$/
const normalizeMoney = (v: string) => v.trim().replace(',', '.')

/* ---------------------------------------------------------------- peças da conta */

function Parcel({
  label,
  value,
  hint,
  onClick,
}: {
  label: string
  value: MoneyOrNull | undefined
  hint?: string
  onClick?: () => void
}) {
  const content = (
    <>
      <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-900">{formatMoney(value)}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
      {onClick && <div className="mt-2 text-xs font-medium text-brand-600">ver lançamentos →</div>}
    </>
  )

  const base = 'min-w-44 flex-1 rounded-lg border border-slate-200 bg-white p-4 text-left'

  if (!onClick) return <div className={base}>{content}</div>

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(base, 'transition-colors hover:border-brand-400 hover:bg-brand-50/40')}
    >
      {content}
    </button>
  )
}

function Op({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center justify-center px-1 text-2xl font-light text-slate-400">
      {children}
    </div>
  )
}

/**
 * Em que mês o carro se pagou RODANDO — ou quanto falta. Tudo calculado no backend.
 * A venda não entra: payback é sobre o carro se pagar operando, não sobre revendê-lo.
 */
function paybackValue(r: VehicleResult): string {
  if (r.payback_month) {
    const [y, m] = r.payback_month.split('-')
    return `${m}/${y.slice(2)}`
  }
  if (r.payback_months_remaining !== null) {
    const n = r.payback_months_remaining
    return n === 1 ? 'faltam ~1 mês' : `faltam ~${n} meses`
  }
  return '—'
}

function paybackHint(r: VehicleResult): string {
  if (r.payback_month && r.payback_months_elapsed) {
    const meses = r.payback_months_elapsed === 1 ? 'mês' : 'meses'
    return `pagou os ${formatMoney(r.investment)} em ${r.payback_months_elapsed} ${meses} de operação`
  }
  if (r.payback_months_remaining !== null) {
    return `estimado pela média dos últimos meses · investimento de ${formatMoney(r.investment)}`
  }
  if (r.sale_date) {
    // Carro vendido que não se pagou rodando. Projetar prazo para um carro que não é mais
    // seu seria mentira — o que vale é o lucro final, que já está em destaque acima.
    return 'não se pagou rodando — o resultado veio da venda'
  }
  return `investimento de ${formatMoney(r.investment)} — sem lucro mensal para estimar prazo`
}

function Stat({
  label,
  value,
  hint,
  className,
  onClick,
}: {
  label: string
  value: string
  hint?: string
  className?: string
  onClick?: () => void
}) {
  const content = (
    <>
      <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</div>
      <div className={cn('mt-1 text-lg font-semibold text-slate-900', className)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
      {onClick && <div className="mt-2 text-xs font-medium text-brand-600">ver lançamentos →</div>}
    </>
  )

  if (!onClick) return <Card>{content}</Card>

  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-colors hover:border-brand-400 hover:bg-brand-50/40"
    >
      {content}
    </button>
  )
}

/* ---------------------------------------------------------------- auditoria */

const LEDGER_TITLES: Record<Exclude<Ledger, null>, string> = {
  received: 'Receitas recebidas',
  receivable: 'Total a receber',
  cost: 'Despesas de operação (pagas)',
  capex: 'Melhorias no veículo (capex pago)',
  expense_pending: 'Despesas pendentes',
}

function LedgerModal({
  ledger,
  vehicleId,
  total,
  onClose,
}: {
  ledger: Ledger
  vehicleId: string
  total: MoneyOrNull | undefined
  onClose: () => void
}) {
  const isRevenue = ledger === 'received' || ledger === 'receivable'
  const isExpense = ledger === 'cost' || ledger === 'capex' || ledger === 'expense_pending'

  const revenues = useQuery({
    queryKey: ['revenues', { vehicle_id: vehicleId }],
    queryFn: () =>
      api.get<Revenue[]>('/revenues', { params: { vehicle_id: vehicleId } }).then((r) => r.data),
    enabled: isRevenue,
  })

  const expenses = useQuery({
    queryKey: ['expenses', { vehicle_id: vehicleId }],
    queryFn: () =>
      api.get<Expense[]>('/expenses', { params: { vehicle_id: vehicleId } }).then((r) => r.data),
    enabled: isExpense,
  })

  // Filtrar por status/categoria não é conta: é recortar a lista que compõe o número.
  const revenueRows = (revenues.data ?? []).filter((r) =>
    ledger === 'received'
      ? Number(r.paid_amount) > 0
      : r.status === 'pending' || r.status === 'partial',
  )
  const expenseRows = (expenses.data ?? []).filter((e) => {
    if (ledger === 'cost') return e.status === 'paid' && !e.category.is_capex
    if (ledger === 'capex') return e.status === 'paid' && e.category.is_capex
    return e.status === 'pending'
  })

  const query = isRevenue ? revenues : expenses
  const isEmpty = isRevenue ? revenueRows.length === 0 : expenseRows.length === 0

  return (
    <Modal open={ledger !== null} onClose={onClose} title={ledger ? LEDGER_TITLES[ledger] : ''} wide>
      <div className="mb-4 flex items-baseline justify-between gap-4 border-b border-slate-200 pb-3">
        <span className="text-sm text-slate-500">Total apurado pela API</span>
        <span className="text-xl font-semibold text-slate-900">{formatMoney(total)}</span>
      </div>

      {query.isPending ? (
        <Spinner />
      ) : query.isError ? (
        <ErrorBox message={errorMessage(query.error)} />
      ) : isEmpty ? (
        <EmptyState message="Nenhum lançamento compõe este número." />
      ) : isRevenue ? (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Categoria</Th>
              <Th>Descrição</Th>
              <Th>Vencimento</Th>
              <Th className="text-right">Valor</Th>
              <Th className="text-right">Recebido</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {revenueRows.map((r) => {
              const badge = REVENUE_STATUS[r.status]
              return (
                <tr key={r.id}>
                  <Td className="font-mono text-xs text-slate-500">{r.code}</Td>
                  <Td>{REVENUE_CATEGORIES[r.category] ?? r.category}</Td>
                  <Td className="text-slate-600">{r.description ?? '—'}</Td>
                  <Td className="text-slate-600">{formatDate(r.due_date)}</Td>
                  <Td className="text-right">{formatMoney(r.amount)}</Td>
                  <Td className="text-right font-medium text-emerald-700">
                    {formatMoney(r.paid_amount)}
                  </Td>
                  <Td>
                    <Badge
                      label={badge?.label ?? r.status}
                      className={badge?.className ?? 'bg-slate-100 text-slate-500'}
                    />
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Categoria</Th>
              <Th>Descrição</Th>
              <Th>Competência</Th>
              <Th>Pago em</Th>
              <Th className="text-right">Valor</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {expenseRows.map((e) => {
              const badge = EXPENSE_STATUS[e.status]
              return (
                <tr key={e.id}>
                  <Td className="font-mono text-xs text-slate-500">{e.code}</Td>
                  <Td>{e.category.name}</Td>
                  <Td className="text-slate-600">{e.description ?? e.supplier_name ?? '—'}</Td>
                  <Td className="text-slate-600">{formatDate(e.competence_date)}</Td>
                  <Td className="text-slate-600">{formatDate(e.paid_on)}</Td>
                  <Td className="text-right font-medium text-red-700">{formatMoney(e.amount)}</Td>
                  <Td>
                    <Badge
                      label={badge?.label ?? e.status}
                      className={badge?.className ?? 'bg-slate-100 text-slate-500'}
                    />
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      <div className="mt-5 flex justify-end">
        <Button variant="secondary" onClick={onClose}>
          Fechar
        </Button>
      </div>
    </Modal>
  )
}

/* ---------------------------------------------------------------- vender */

function sellSchema(purchaseDate: string) {
  return z.object({
    sale_price: z
      .string()
      .min(1, 'Informe o valor da venda.')
      .refine((v) => moneyRegex.test(v.trim()), 'Valor inválido. Use até 2 casas decimais.')
      .refine((v) => Number(normalizeMoney(v)) > 0, 'O valor da venda precisa ser maior que zero.'),
    sale_date: z
      .string()
      .min(1, 'Informe a data da venda.')
      // Mesma regra do backend: venda antes da compra não existe.
      .refine(
        (v) => v >= purchaseDate,
        `A data de venda não pode ser anterior à compra (${formatDate(purchaseDate)}).`,
      ),
  })
}

type SellForm = z.infer<ReturnType<typeof sellSchema>>

function SellModal({
  open,
  onClose,
  vehicle,
}: {
  open: boolean
  onClose: () => void
  vehicle: Vehicle
}) {
  const queryClient = useQueryClient()
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SellForm>({
    resolver: zodResolver(sellSchema(vehicle.purchase_date)),
    defaultValues: { sale_price: '', sale_date: today() },
  })

  const sell = useMutation({
    mutationFn: (values: SellForm) =>
      api
        .post<Vehicle>(`/vehicles/${vehicle.id}/sell`, {
          // Dinheiro vai como STRING — é Decimal no backend.
          sale_price: normalizeMoney(values.sale_price),
          sale_date: values.sale_date,
        })
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      reset()
      onClose()
    },
  })

  function close() {
    sell.reset()
    reset({ sale_price: '', sale_date: today() })
    onClose()
  }

  return (
    <Modal open={open} onClose={close} title="Vender veículo">
      <form onSubmit={handleSubmit((v) => sell.mutate(v))} className="space-y-4">
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <TriangleAlert size={16} className="mt-0.5 shrink-0" />
          <span>
            Isto <strong>FECHA o ciclo</strong> do {vehicle.plate}: o veículo passa a{' '}
            <strong>Vendido</strong>, sai da frota ativa e o lucro dele vira definitivo. O valor da
            venda mora só aqui — não lance como receita, senão o lucro conta em dobro.
          </span>
        </div>

        <Field label="Valor da venda" error={errors.sale_price?.message} required>
          <MoneyInput placeholder="45000,00" {...register('sale_price')} />
        </Field>

        <Field label="Data da venda" error={errors.sale_date?.message} required>
          <Input type="date" {...register('sale_date')} />
        </Field>

        {sell.isError && <ErrorBox message={errorMessage(sell.error)} />}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" variant="danger" loading={sell.isPending}>
            Confirmar venda
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- valor de mercado */

const marketSchema = z.object({
  estimated_market_value: z
    .string()
    .min(1, 'Informe o valor de mercado estimado.')
    .refine((v) => moneyRegex.test(v.trim()), 'Valor inválido. Use até 2 casas decimais.'),
})

type MarketForm = z.infer<typeof marketSchema>

function MarketValueForm({ vehicle }: { vehicle: Vehicle }) {
  const queryClient = useQueryClient()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<MarketForm>({
    resolver: zodResolver(marketSchema),
    defaultValues: { estimated_market_value: vehicle.estimated_market_value ?? '' },
  })

  const save = useMutation({
    mutationFn: (values: MarketForm) =>
      api
        .patch<Vehicle>(`/vehicles/${vehicle.id}`, {
          estimated_market_value: normalizeMoney(values.estimated_market_value),
        })
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
    },
  })

  return (
    <form
      onSubmit={handleSubmit((v) => save.mutate(v))}
      className="flex flex-wrap items-end gap-3"
    >
      <div className="min-w-48 flex-1">
        <Field label="Valor de mercado estimado" error={errors.estimated_market_value?.message}>
          <MoneyInput placeholder="45000,00" {...register('estimated_market_value')} />
        </Field>
      </div>
      <Button type="submit" variant="secondary" loading={save.isPending}>
        Salvar
      </Button>
      {save.isError && (
        <div className="w-full">
          <ErrorBox message={errorMessage(save.error)} />
        </div>
      )}
    </form>
  )
}

/* ---------------------------------------------------------------- abas */

const TABS: { key: Tab; label: string; to: string }[] = [
  { key: 'maintenances', label: 'Manutenções', to: '/manutencoes' },
  { key: 'fines', label: 'Multas', to: '/multas' },
  { key: 'inspections', label: 'Vistorias', to: '/vistorias' },
  { key: 'contracts', label: 'Contratos', to: '/contratos' },
]

const TAB_ENDPOINT: Record<Tab, string> = {
  maintenances: '/maintenances',
  fines: '/fines',
  inspections: '/inspections',
  contracts: '/contracts',
}

function RelatedTabs({ vehicleId }: { vehicleId: string }) {
  const [tab, setTab] = useState<Tab>('maintenances')

  const list = useQuery({
    queryKey: [tab, { vehicle_id: vehicleId }],
    queryFn: () =>
      api
        .get<unknown[]>(TAB_ENDPOINT[tab], { params: { vehicle_id: vehicleId } })
        .then((r) => r.data),
  })

  const current = TABS.find((t) => t.key === tab)!

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                tab === t.key
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <Link
          to={current.to}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          Abrir {current.label.toLowerCase()}
          <ExternalLink size={14} />
        </Link>
      </div>

      {list.isPending ? (
        <Spinner />
      ) : list.isError ? (
        <ErrorBox message={errorMessage(list.error)} />
      ) : list.data.length === 0 ? (
        <EmptyState message={`Nenhum registro de ${current.label.toLowerCase()} para este veículo.`} />
      ) : tab === 'maintenances' ? (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Serviço</Th>
              <Th>Fornecedor</Th>
              <Th>Data</Th>
              <Th className="text-right">Odômetro</Th>
              <Th className="text-right">Valor</Th>
            </tr>
          </thead>
          <tbody>
            {(list.data as Maintenance[]).map((m) => (
              <tr key={m.id}>
                <Td className="font-mono text-xs text-slate-500">{m.code}</Td>
                <Td className="font-medium text-slate-800">{m.kind}</Td>
                <Td className="text-slate-600">{m.supplier_name ?? '—'}</Td>
                <Td className="text-slate-600">{formatDate(m.performed_on)}</Td>
                <Td className="text-right text-slate-600">{formatNumber(m.odometer)} km</Td>
                <Td className="text-right font-medium">{formatMoney(m.amount)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : tab === 'fines' ? (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Infração</Th>
              <Th>Data</Th>
              <Th>Motorista</Th>
              <Th className="text-right">Valor</Th>
              <Th className="text-right">Custo líquido</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {(list.data as Fine[]).map((f) => {
              const badge = FINE_STATUS[f.status]
              return (
                <tr key={f.id}>
                  <Td className="font-mono text-xs text-slate-500">{f.code}</Td>
                  <Td className="text-slate-800">{f.description}</Td>
                  <Td className="text-slate-600">{formatDate(f.infraction_date)}</Td>
                  <Td className="text-slate-600">{f.driver?.full_name ?? '—'}</Td>
                  <Td className="text-right">{formatMoney(f.amount)}</Td>
                  <Td className={cn('text-right font-medium', moneyClass(f.net_cost))}>
                    {formatMoney(f.net_cost)}
                  </Td>
                  <Td>
                    <Badge
                      label={badge?.label ?? f.status}
                      className={badge?.className ?? 'bg-slate-100 text-slate-500'}
                    />
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      ) : tab === 'inspections' ? (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Tipo</Th>
              <Th>Data</Th>
              <Th>Motorista</Th>
              <Th className="text-right">Odômetro</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {(list.data as Inspection[]).map((i) => (
              <tr key={i.id}>
                <Td className="font-mono text-xs text-slate-500">{i.code}</Td>
                <Td className="font-medium text-slate-800">{INSPECTION_KINDS[i.kind] ?? i.kind}</Td>
                <Td className="text-slate-600">{formatDateTime(i.inspected_at)}</Td>
                <Td className="text-slate-600">{i.driver?.full_name ?? '—'}</Td>
                <Td className="text-right text-slate-600">{formatNumber(i.odometer)} km</Td>
                <Td className="text-right">
                  <Link
                    to={`/vistorias/${i.id}`}
                    className="text-sm font-medium text-brand-600 hover:text-brand-700"
                  >
                    Ver
                  </Link>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Motorista</Th>
              <Th>Início</Th>
              <Th>Fim</Th>
              <Th className="text-right">Semanal</Th>
              <Th className="text-right">Caução</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {(list.data as Contract[]).map((c) => {
              const badge = CONTRACT_STATUS[c.status]
              return (
                <tr key={c.id}>
                  <Td className="font-mono text-xs text-slate-500">{c.code}</Td>
                  <Td className="font-medium text-slate-800">{c.driver?.full_name ?? '—'}</Td>
                  <Td className="text-slate-600">{formatDate(c.start_date)}</Td>
                  <Td className="text-slate-600">{formatDate(c.end_date)}</Td>
                  <Td className="text-right">{formatMoney(c.weekly_amount)}</Td>
                  <Td className="text-right text-slate-600">{formatMoney(c.deposit_amount)}</Td>
                  <Td>
                    <Badge
                      label={badge?.label ?? c.status}
                      className={badge?.className ?? 'bg-slate-100 text-slate-500'}
                    />
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
    </section>
  )
}

/* ---------------------------------------------------------------- página */

export function VehicleDetailPage() {
  const { id = '' } = useParams()
  const { user } = useAuth()
  const [ledger, setLedger] = useState<Ledger>(null)
  const [sellOpen, setSellOpen] = useState(false)

  const vehicle = useQuery({
    queryKey: ['vehicles', id],
    queryFn: () => api.get<Vehicle>(`/vehicles/${id}`).then((r) => r.data),
  })

  const result = useQuery({
    queryKey: ['finance', 'vehicle', id],
    queryFn: () => api.get<VehicleResult>(`/finance/vehicles/${id}`).then((r) => r.data),
  })

  if (vehicle.isPending || result.isPending) return <Spinner label="Carregando a conta do veículo…" />

  if (vehicle.isError) return <ErrorBox message={errorMessage(vehicle.error)} />
  if (result.isError) return <ErrorBox message={errorMessage(result.error)} />

  const v = vehicle.data
  const r = result.data

  const isSold = v.sale_date !== null
  const badge = VEHICLE_STATUS[v.status]
  const hasCapex = Number(r.total_capex) > 0

  const totalForLedger: Record<Exclude<Ledger, null>, Money> = {
    received: r.total_received,
    receivable: r.total_receivable,
    cost: r.total_cost,
    capex: r.total_capex,
    expense_pending: r.total_expense_pending,
  }

  return (
    <>
      <Link
        to="/veiculos"
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-800"
      >
        <ArrowLeft size={16} />
        Veículos
      </Link>

      <PageHeader
        title={`${v.plate} — ${v.brand} ${v.model}`}
        subtitle={[
          v.code,
          v.version,
          `${v.manufacture_year}/${v.model_year}`,
          FUEL_TYPES[v.fuel_type] ?? v.fuel_type,
          v.color,
          `${formatNumber(v.current_odometer)} km`,
        ]
          .filter(Boolean)
          .join(' · ')}
        action={
          <div className="flex items-center gap-3">
            <Badge
              label={badge?.label ?? v.status}
              className={badge?.className ?? 'bg-slate-100 text-slate-500'}
            />
            {!isSold && user?.role === 'admin' && (
              <Button variant="danger" onClick={() => setSellOpen(true)}>
                Vender veículo
              </Button>
            )}
          </div>
        }
      />

      {isSold && (
        <div className="mb-6 rounded-lg border border-slate-300 bg-slate-100 p-4 text-sm text-slate-700">
          <strong>Ciclo encerrado.</strong> Vendido em {formatDate(v.sale_date)} por{' '}
          {formatMoney(v.sale_price)}. O lucro abaixo é o resultado <strong>final realizado</strong>{' '}
          deste veículo.
        </div>
      )}

      {/* A CONTA DO CICLO DE VIDA — a razão de existir do produto. */}
      <Card className="mb-6">
        <h2 className="text-base font-semibold text-slate-900">A conta do ciclo de vida</h2>
        <p className="mt-1 mb-5 text-sm text-slate-500">
          receitas − despesas − valor de compra + valor de venda = <strong>lucro</strong>. Clique em
          qualquer parcela para ver os lançamentos que a compõem.
        </p>

        <div className="flex flex-wrap items-stretch gap-2">
          <Parcel
            label="Receitas"
            value={r.total_received}
            hint="o que entrou de verdade"
            onClick={() => setLedger('received')}
          />
          <Op>−</Op>
          <Parcel
            label="Despesas"
            value={r.total_cost}
            hint="custo de operação pago"
            onClick={() => setLedger('cost')}
          />
          <Op>−</Op>
          <Parcel
            label="Valor de compra"
            value={r.investment}
            hint={
              hasCapex
                ? `compra ${formatMoney(r.purchase_price)} + melhorias ${formatMoney(r.total_capex)}`
                : `comprado em ${formatDate(r.purchase_date)}`
            }
            onClick={hasCapex ? () => setLedger('capex') : undefined}
          />
          <Op>+</Op>
          <Parcel
            label="Valor de venda"
            value={r.sale_price}
            hint={isSold ? `vendido em ${formatDate(r.sale_date)}` : 'ainda não vendido'}
          />
          <Op>=</Op>

          <div className="min-w-56 flex-1 rounded-lg border-2 border-slate-900 bg-slate-50 p-4">
            <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">Lucro</div>
            <div className={cn('mt-1 text-4xl font-bold', moneyClass(r.profit))}>
              {formatMoney(r.profit)}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {isSold ? 'resultado final realizado' : 'realizado até agora — o carro ainda é seu'}
            </div>
          </div>
        </div>
      </Card>

      {/* "Se eu vender hoje" — só faz sentido enquanto o carro não foi vendido. */}
      {!isSold && (
        <Card className="mb-6">
          <h2 className="text-base font-semibold text-slate-900">Se eu vender hoje</h2>

          {r.estimated_market_value === null ? (
            <>
              <div className="mt-3 mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <TriangleAlert size={16} className="mt-0.5 shrink-0" />
                <span>
                  Sem o valor de mercado estimado não dá para saber quanto você ganha vendendo hoje.
                  Informe quanto o carro vale agora.
                </span>
              </div>
              <MarketValueForm vehicle={v} />
            </>
          ) : (
            <div className="mt-4 flex flex-wrap items-center gap-6">
              <div>
                <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                  Lucro se vender hoje
                </div>
                <div className={cn('mt-1 text-3xl font-bold', moneyClass(r.profit_if_sold_today))}>
                  {formatMoney(r.profit_if_sold_today)}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  considerando um valor de mercado de {formatMoney(r.estimated_market_value)}
                </div>
              </div>
              <div className="min-w-64 flex-1">
                <MarketValueForm vehicle={v} />
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Indicadores secundários */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="ROI"
          value={formatPercent(r.roi)}
          hint="lucro sobre o investimento"
          className={moneyClass(r.roi)}
        />
        <Stat
          label="Payback"
          value={paybackValue(r)}
          hint={paybackHint(r)}
          className={
            r.payback_month
              ? 'text-emerald-600'
              : r.payback_months_remaining !== null
                ? 'text-amber-600'
                : 'text-slate-400'
          }
        />
        <Stat
          label="Custo por km"
          value={formatMoney(r.cost_per_km)}
          hint="despesa de operação ÷ km rodados"
          onClick={() => setLedger('cost')}
        />
        <Stat
          label="Receita por km"
          value={formatMoney(r.revenue_per_km)}
          hint="receita recebida ÷ km rodados"
          onClick={() => setLedger('received')}
        />
        <Stat
          label="KM rodados"
          value={`${formatNumber(r.km_driven)} km`}
          hint={`de ${formatNumber(v.purchase_odometer)} a ${formatNumber(v.current_odometer)}`}
        />
        <Stat
          label="Total a receber"
          value={formatMoney(r.total_receivable)}
          hint="cobranças em aberto — fora do lucro"
          className={Number(r.total_receivable) > 0 ? 'text-amber-600' : undefined}
          onClick={() => setLedger('receivable')}
        />
        <Stat
          label="Despesas pendentes"
          value={formatMoney(r.total_expense_pending)}
          hint="ainda não pagas — fora do lucro"
          className={Number(r.total_expense_pending) > 0 ? 'text-amber-600' : undefined}
          onClick={() => setLedger('expense_pending')}
        />
        <Stat
          label="Melhorias (capex)"
          value={formatMoney(r.total_capex)}
          hint="investimento no carro, não custo do mês"
          onClick={hasCapex ? () => setLedger('capex') : undefined}
        />
      </div>

      <RelatedTabs vehicleId={v.id} />

      <LedgerModal
        ledger={ledger}
        vehicleId={v.id}
        total={ledger ? totalForLedger[ledger] : undefined}
        onClose={() => setLedger(null)}
      />

      {!isSold && <SellModal open={sellOpen} onClose={() => setSellOpen(false)} vehicle={v} />}
    </>
  )
}
