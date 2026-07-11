import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { api, errorMessage } from '../../api/client'
import {
  Badge,
  Card,
  EmptyState,
  ErrorBox,
  PageHeader,
  Spinner,
  Table,
  Td,
  Th,
  cn,
} from '../../components/ui'
import { VEHICLE_STATUS, formatMoney, formatPercent, moneyClass } from '../../lib/format'
import type { Money, VehicleResult } from '../vehicles/types'

/** GET /finance/dashboard */
type Dashboard = {
  month: string
  vehicles_total: number
  vehicles_by_status: Record<string, number>
  revenue_received_month: Money
  expense_paid_month: Money
  profit_month: Money
  total_receivable: Money
  /** Inadimplência: derivada (em aberto + vencida). É o número que dói. */
  total_overdue: Money
  overdue_count: number
}

/** GET /finance/monthly */
type MonthlyPoint = {
  month: string
  revenue: Money
  expense: Money
  profit: Money
}

const MONTHS_SHORT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const MONTHS_LONG = [
  'janeiro',
  'fevereiro',
  'março',
  'abril',
  'maio',
  'junho',
  'julho',
  'agosto',
  'setembro',
  'outubro',
  'novembro',
  'dezembro',
]

/** "2026-07" → "jul/26" */
function monthShort(month: string): string {
  const [year, m] = month.split('-')
  const name = MONTHS_SHORT[Number(m) - 1]
  return name ? `${name}/${year.slice(2)}` : month
}

/** "2026-07" → "julho de 2026" */
function monthLong(month: string): string {
  const [year, m] = month.split('-')
  const name = MONTHS_LONG[Number(m) - 1]
  return name ? `${name} de ${year}` : month
}

/* ---------------------------------------------------------------- gráfico */

function MonthlyChart({ points }: { points: MonthlyPoint[] }) {
  if (points.length === 0) {
    return <EmptyState message="Ainda não há movimento financeiro para montar o gráfico." />
  }

  // ATENÇÃO: `Number()` aqui é só ALTURA DE BARRA (layout), nunca valor exibido.
  // Todo dinheiro na tela sai de formatMoney() sobre a string que a API mandou.
  const max = Math.max(1, ...points.flatMap((p) => [Number(p.revenue), Number(p.expense)]))
  const barHeight = (value: Money) => `${(Number(value) / max) * 100}%`

  return (
    <div>
      <div className="mb-4 flex gap-4 text-xs text-slate-600">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" />
          Receita recebida
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-red-400" />
          Despesa paga
        </span>
      </div>

      <div className="flex h-52 items-end gap-3 border-b border-slate-200">
        {points.map((p) => (
          <div
            key={p.month}
            title={`${monthLong(p.month)}\nReceita: ${formatMoney(p.revenue)}\nDespesa: ${formatMoney(p.expense)}\nLucro: ${formatMoney(p.profit)}`}
            className="flex h-full flex-1 items-end justify-center gap-1 rounded-t hover:bg-slate-50"
          >
            <div
              className="w-6 rounded-t bg-emerald-500 transition-all"
              style={{ height: barHeight(p.revenue) }}
            />
            <div
              className="w-6 rounded-t bg-red-400 transition-all"
              style={{ height: barHeight(p.expense) }}
            />
          </div>
        ))}
      </div>

      <div className="flex gap-3 pt-2">
        {points.map((p) => (
          <div key={p.month} className="flex-1 text-center text-xs text-slate-500">
            {monthShort(p.month)}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- página */

export function DashboardPage() {
  const navigate = useNavigate()

  const dashboard = useQuery({
    queryKey: ['finance', 'dashboard'],
    queryFn: () => api.get<Dashboard>('/finance/dashboard').then((r) => r.data),
  })

  const fleet = useQuery({
    queryKey: ['finance', 'fleet'],
    queryFn: () => api.get<VehicleResult[]>('/finance/fleet').then((r) => r.data),
  })

  const monthly = useQuery({
    queryKey: ['finance', 'monthly'],
    queryFn: () => api.get<MonthlyPoint[]>('/finance/monthly').then((r) => r.data),
  })

  const d = dashboard.data
  const hasOverdue = d ? Number(d.total_overdue) > 0 : false

  return (
    <>
      <PageHeader
        title="Painel"
        subtitle={d ? `Frota e resultado de ${monthLong(d.month)}.` : 'Frota e resultado do mês.'}
      />

      {dashboard.isPending ? (
        <Spinner />
      ) : dashboard.isError ? (
        <ErrorBox message={errorMessage(dashboard.error)} />
      ) : (
        <>
          {/* Frota por status */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Link
              to="/veiculos"
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-brand-400"
            >
              <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                Frota
              </div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">{d!.vehicles_total}</div>
            </Link>

            {Object.entries(VEHICLE_STATUS).map(([status, { label, className }]) => (
              <Link
                key={status}
                to={`/veiculos?status=${status}`}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-brand-400"
              >
                <Badge label={label} className={className} />
                <div className="mt-2 text-2xl font-semibold text-slate-900">
                  {d!.vehicles_by_status[status] ?? 0}
                </div>
              </Link>
            ))}
          </div>

          {/* O mês */}
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                Receita recebida no mês
              </div>
              <div className="mt-1 text-2xl font-semibold text-emerald-600">
                {formatMoney(d!.revenue_received_month)}
              </div>
            </Card>
            <Card>
              <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                Despesa paga no mês
              </div>
              <div className="mt-1 text-2xl font-semibold text-red-600">
                {formatMoney(d!.expense_paid_month)}
              </div>
            </Card>
            <Card>
              <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                Lucro do mês
              </div>
              <div className={cn('mt-1 text-2xl font-semibold', moneyClass(d!.profit_month))}>
                {formatMoney(d!.profit_month)}
              </div>
            </Card>
          </div>

          {/* A receber × VENCIDO — o vencido é o número que dói. */}
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Link
              to="/cobrancas"
              className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-colors hover:border-brand-400"
            >
              <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                Total a receber
              </div>
              <div className="mt-1 text-3xl font-semibold text-slate-900">
                {formatMoney(d!.total_receivable)}
              </div>
              <div className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand-600">
                Ver cobranças
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
              </div>
            </Link>

            <Link
              to="/cobrancas"
              className={cn(
                'group rounded-xl border-2 p-5 shadow-sm transition-colors',
                hasOverdue
                  ? 'border-red-300 bg-red-50 hover:border-red-500'
                  : 'border-slate-200 bg-white hover:border-brand-400',
              )}
            >
              <div
                className={cn(
                  'flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase',
                  hasOverdue ? 'text-red-700' : 'text-slate-500',
                )}
              >
                {hasOverdue && <AlertTriangle size={14} />}
                Vencido
              </div>
              <div
                className={cn(
                  'mt-1 text-3xl font-bold',
                  hasOverdue ? 'text-red-600' : 'text-slate-400',
                )}
              >
                {formatMoney(d!.total_overdue)}
              </div>
              <div className={cn('mt-2 text-xs', hasOverdue ? 'text-red-700' : 'text-slate-500')}>
                {d!.overdue_count === 0
                  ? 'Nenhuma cobrança vencida. '
                  : `${d!.overdue_count} ${d!.overdue_count === 1 ? 'cobrança vencida' : 'cobranças vencidas'}. `}
                <span className="inline-flex items-center gap-1 font-medium underline">
                  Cobrar agora
                  <ArrowRight
                    size={13}
                    className="transition-transform group-hover:translate-x-0.5"
                  />
                </span>
              </div>
            </Link>
          </div>
        </>
      )}

      {/* Receita × despesa por mês */}
      <Card className="mb-6">
        <h2 className="mb-4 text-base font-semibold text-slate-900">Receita × despesa por mês</h2>
        {monthly.isPending ? (
          <Spinner />
        ) : monthly.isError ? (
          <ErrorBox message={errorMessage(monthly.error)} />
        ) : (
          <MonthlyChart points={monthly.data} />
        )}
      </Card>

      {/* Ranking da frota por lucro */}
      <section>
        <h2 className="mb-1 text-base font-semibold text-slate-900">Ranking da frota por lucro</h2>
        <p className="mb-4 text-sm text-slate-500">
          Qual carro está pagando a conta e qual está comendo o caixa.
        </p>

        {fleet.isPending ? (
          <Spinner />
        ) : fleet.isError ? (
          <ErrorBox message={errorMessage(fleet.error)} />
        ) : fleet.data.length === 0 ? (
          <EmptyState message="Nenhum veículo cadastrado ainda." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-12">#</Th>
                <Th>Placa</Th>
                <Th>Veículo</Th>
                <Th>Status</Th>
                <Th className="text-right">Investimento</Th>
                <Th className="text-right">Recebido</Th>
                <Th className="text-right">ROI</Th>
                <Th className="text-right">Lucro</Th>
              </tr>
            </thead>
            <tbody>
              {fleet.data.map((row, index) => {
                const badge = VEHICLE_STATUS[row.status]
                return (
                  <tr
                    key={row.vehicle_id}
                    onClick={() => navigate(`/veiculos/${row.vehicle_id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`/veiculos/${row.vehicle_id}`)
                    }}
                    tabIndex={0}
                    role="link"
                    className="cursor-pointer hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                  >
                    <Td className="text-slate-400">{index + 1}</Td>
                    <Td className="font-medium text-slate-900">{row.plate}</Td>
                    <Td className="text-slate-600">
                      {row.brand} {row.model}
                      <span className="ml-2 font-mono text-xs text-slate-400">{row.code}</span>
                    </Td>
                    <Td>
                      <Badge
                        label={badge?.label ?? row.status}
                        className={badge?.className ?? 'bg-slate-100 text-slate-500'}
                      />
                    </Td>
                    <Td className="text-right text-slate-600">{formatMoney(row.investment)}</Td>
                    <Td className="text-right text-slate-600">{formatMoney(row.total_received)}</Td>
                    <Td className={cn('text-right', moneyClass(row.roi))}>
                      {formatPercent(row.roi)}
                    </Td>
                    <Td className={cn('text-right font-semibold', moneyClass(row.profit))}>
                      {formatMoney(row.profit)}
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </section>
    </>
  )
}
