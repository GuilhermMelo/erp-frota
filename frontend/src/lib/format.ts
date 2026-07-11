/**
 * Formatação. ATENÇÃO: a API manda dinheiro como STRING ("8000.00"), de propósito —
 * é `Decimal` no backend e não pode virar float.
 *
 * Aqui converter para Number é aceitável APENAS para exibir. NUNCA some, subtraia ou
 * multiplique dinheiro no frontend: toda conta é feita no backend, onde é Decimal.
 */

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const NUM = new Intl.NumberFormat('pt-BR')

export type Money = string | number | null | undefined

export function formatMoney(value: Money): string {
  if (value === null || value === undefined || value === '') return '—'
  return BRL.format(Number(value))
}

/** Para valores que podem ser negativos e onde o sinal importa (lucro). */
export function moneyClass(value: Money): string {
  if (value === null || value === undefined || value === '') return 'text-slate-400'
  const n = Number(value)
  if (n > 0) return 'text-emerald-600'
  if (n < 0) return 'text-red-600'
  return 'text-slate-600'
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return NUM.format(value)
}

export function formatPercent(value: Money): string {
  if (value === null || value === undefined || value === '') return '—'
  return `${(Number(value) * 100).toFixed(1).replace('.', ',')}%`
}

/** A API manda datas como "2026-07-11". Evita o bug de fuso que joga para o dia anterior. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

export function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export const VEHICLE_STATUS: Record<string, { label: string; className: string }> = {
  available: { label: 'Disponível', className: 'bg-emerald-100 text-emerald-800' },
  rented: { label: 'Locado', className: 'bg-blue-100 text-blue-800' },
  maintenance: { label: 'Manutenção', className: 'bg-amber-100 text-amber-800' },
  sold: { label: 'Vendido', className: 'bg-slate-200 text-slate-700' },
  inactive: { label: 'Inativo', className: 'bg-slate-100 text-slate-500' },
}

export const REVENUE_STATUS: Record<string, { label: string; className: string }> = {
  pending: { label: 'Em aberto', className: 'bg-amber-100 text-amber-800' },
  partial: { label: 'Parcial', className: 'bg-orange-100 text-orange-800' },
  paid: { label: 'Pago', className: 'bg-emerald-100 text-emerald-800' },
  canceled: { label: 'Cancelado', className: 'bg-slate-100 text-slate-500' },
}
