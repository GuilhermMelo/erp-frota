import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { HandCoins, TriangleAlert, Wallet } from 'lucide-react'
import { useForm } from 'react-hook-form'
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
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from '../../components/ui'
import { REVENUE_STATUS, formatDate, formatMoney, today } from '../../lib/format'

/* ---------------------------------------------------------------- tipos */

/** Linha da inadimplência. `saldo` e `dias_em_atraso` vêm CALCULADOS da API. */
type Receivable = {
  id: string
  code: string
  vehicle_id: string
  vehicle_plate: string
  driver_id: string | null
  driver_name: string | null
  category: string
  description: string | null
  amount: string
  paid_amount: string
  saldo: string
  dias_em_atraso: number
  competence_date: string
  due_date: string
  status: string
}

/** O resumo vem do backend (Decimal). Somar dinheiro no frontend seria bug de dinheiro. */
type Dashboard = {
  total_receivable: string
  total_overdue: string
  overdue_count: number
}

const PAYMENT_METHODS: Record<string, string> = {
  pix: 'PIX',
  dinheiro: 'Dinheiro',
  transferencia: 'Transferência',
  cartao: 'Cartão',
  boleto: 'Boleto',
  outro: 'Outro',
}

/**
 * O atraso é o assunto desta tela — a cor tem que gritar antes de o dono ler o número.
 * Em dia (cinza) → 1–7 dias (amarelo) → 8–15 (laranja) → mais de 15 (vermelho).
 */
function overdueTier(days: number) {
  if (days <= 0) {
    return {
      label: 'Em dia',
      badge: 'bg-slate-100 text-slate-600',
      row: '',
      bar: 'border-l-slate-200',
      severe: false,
    }
  }
  if (days <= 7) {
    return {
      label: `${days} ${days === 1 ? 'dia' : 'dias'}`,
      badge: 'bg-amber-100 text-amber-800',
      row: 'bg-amber-50/50',
      bar: 'border-l-amber-400',
      severe: false,
    }
  }
  if (days <= 15) {
    return {
      label: `${days} dias`,
      badge: 'bg-orange-100 text-orange-800',
      row: 'bg-orange-50/60',
      bar: 'border-l-orange-500',
      severe: false,
    }
  }
  return {
    label: `${days} dias`,
    badge: 'bg-red-100 text-red-800',
    row: 'bg-red-50/60',
    bar: 'border-l-red-600',
    severe: true,
  }
}

/* ---------------------------------------------------------------- página */

export function ReceivablesPage() {
  const [onlyOverdue, setOnlyOverdue] = useState(false)
  const [receiving, setReceiving] = useState<Receivable | null>(null)

  const receivablesQuery = useQuery({
    queryKey: ['receivables', { only_overdue: onlyOverdue }],
    queryFn: async () =>
      (
        await api.get<Receivable[]>('/revenues/receivables', {
          params: { only_overdue: onlyOverdue },
        })
      ).data,
    placeholderData: (previous) => previous,
  })

  // Os totais são somados no backend, em `Decimal`. A tela só exibe.
  const dashboardQuery = useQuery({
    queryKey: ['finance', 'dashboard'],
    queryFn: async () => (await api.get<Dashboard>('/finance/dashboard')).data,
  })

  const summary = dashboardQuery.data
  // A API já ordena por vencimento; reafirmamos aqui para a tela não depender disso.
  const receivables = [...(receivablesQuery.data ?? [])].sort((a, b) =>
    a.due_date.localeCompare(b.due_date),
  )

  return (
    <div>
      <PageHeader
        title="Cobranças"
        subtitle="Quem te deve, quanto, e há quantos dias. O atraso é calculado na hora — não existe status “vencido” guardado."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Card>
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
              <Wallet size={20} />
            </div>
            <div>
              <div className="text-sm text-slate-500">Total em aberto</div>
              <div className="text-2xl font-semibold tabular-nums text-slate-900">
                {dashboardQuery.isPending ? '…' : formatMoney(summary?.total_receivable)}
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                Tudo o que ainda não foi recebido, vencido ou não.
              </div>
            </div>
          </div>
        </Card>

        <Card className={summary && Number(summary.total_overdue) > 0 ? 'border-red-200' : ''}>
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-red-100 p-2 text-red-600">
              <TriangleAlert size={20} />
            </div>
            <div>
              <div className="text-sm text-slate-500">Total vencido</div>
              <div className="text-2xl font-semibold tabular-nums text-red-600">
                {dashboardQuery.isPending ? '…' : formatMoney(summary?.total_overdue)}
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                {summary
                  ? `${summary.overdue_count} ${
                      summary.overdue_count === 1 ? 'cobrança vencida' : 'cobranças vencidas'
                    }`
                  : '—'}
              </div>
            </div>
          </div>
        </Card>
      </div>

      {dashboardQuery.isError && (
        <div className="mb-4">
          <ErrorBox message={errorMessage(dashboardQuery.error)} />
        </div>
      )}

      <Card className="mb-4">
        <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
          <input
            type="checkbox"
            className="size-4 rounded border-slate-300"
            checked={onlyOverdue}
            onChange={(e) => setOnlyOverdue(e.target.checked)}
          />
          Mostrar só as vencidas
        </label>
      </Card>

      {receivablesQuery.isPending ? (
        <Spinner />
      ) : receivablesQuery.isError ? (
        <ErrorBox message={errorMessage(receivablesQuery.error)} />
      ) : receivables.length === 0 ? (
        <EmptyState
          message={
            onlyOverdue ? 'Nenhuma cobrança vencida. ' : 'Nenhuma cobrança em aberto. '
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Motorista</Th>
              <Th>Veículo</Th>
              <Th>Cobrança</Th>
              <Th className="text-right">Valor</Th>
              <Th className="text-right">Em aberto</Th>
              <Th>Vencimento</Th>
              <Th>Atraso</Th>
              <Th>Situação</Th>
              <Th className="text-right">Ação</Th>
            </tr>
          </thead>
          <tbody>
            {receivables.map((row) => {
              const tier = overdueTier(row.dias_em_atraso)
              const status = REVENUE_STATUS[row.status] ?? {
                label: row.status,
                className: 'bg-slate-100 text-slate-600',
              }
              return (
                <tr key={row.id} className={tier.row}>
                  <Td className={`border-l-4 ${tier.bar} font-medium whitespace-nowrap text-slate-900`}>
                    {row.driver_name ?? '— sem motorista —'}
                  </Td>
                  <Td className="whitespace-nowrap">{row.vehicle_plate}</Td>
                  <Td className="text-slate-600">
                    <div className="font-mono text-xs text-slate-400">{row.code}</div>
                    <div className="max-w-64 truncate">{row.description ?? '—'}</div>
                  </Td>
                  <Td className="text-right tabular-nums whitespace-nowrap text-slate-600">
                    {formatMoney(row.amount)}
                  </Td>
                  <Td
                    className={`text-right font-semibold tabular-nums whitespace-nowrap ${
                      tier.severe ? 'text-red-700' : 'text-slate-900'
                    }`}
                  >
                    {formatMoney(row.saldo)}
                  </Td>
                  <Td className="whitespace-nowrap">{formatDate(row.due_date)}</Td>
                  <Td className="whitespace-nowrap">
                    <Badge label={tier.label} className={tier.badge} />
                  </Td>
                  <Td>
                    <Badge label={status.label} className={status.className} />
                  </Td>
                  <Td className="text-right">
                    <Button onClick={() => setReceiving(row)}>
                      <HandCoins size={16} />
                      Receber
                    </Button>
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      {receiving && (
        <ReceivePaymentModal receivable={receiving} onClose={() => setReceiving(null)} />
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- receber */

const paymentSchema = z.object({
  amount: z.string().refine((v) => {
    const normalized = v.trim().replace(',', '.')
    return /^\d+(\.\d{1,2})?$/.test(normalized) && Number(normalized) > 0
  }, 'Informe um valor maior que zero.'),
  paid_on: z.string().min(1, 'Informe a data do recebimento.'),
  method: z.string(),
  receipt_ref: z.string(),
})

type PaymentForm = z.infer<typeof paymentSchema>

function ReceivePaymentModal({
  receivable,
  onClose,
}: {
  receivable: Receivable
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const tier = overdueTier(receivable.dias_em_atraso)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PaymentForm>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      // `saldo` vem pronto da API (Decimal → string). Nada de conta aqui.
      amount: receivable.saldo,
      paid_on: today(),
      method: 'pix',
      receipt_ref: '',
    },
  })

  const mutation = useMutation({
    mutationFn: (form: PaymentForm) =>
      api.post(`/revenues/${receivable.id}/payments`, {
        // Dinheiro vai como STRING — o backend recebe `Decimal`, sem passar por float.
        amount: form.amount.trim().replace(',', '.'),
        paid_on: form.paid_on,
        method: form.method,
        receipt_ref: form.receipt_ref.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['receivables'] })
      queryClient.invalidateQueries({ queryKey: ['revenues'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      onClose()
    },
  })

  return (
    <Modal open onClose={onClose} title={`Receber ${receivable.code}`}>
      <form onSubmit={handleSubmit((form) => mutation.mutate(form))} className="space-y-4">
        <div className="rounded-lg bg-slate-50 p-3 text-sm">
          <div className="font-medium text-slate-900">
            {receivable.driver_name ?? 'Sem motorista'} · {receivable.vehicle_plate}
          </div>
          <div className="mt-1 text-slate-600">{receivable.description ?? '—'}</div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-slate-600">
              Em aberto: <strong className="tabular-nums">{formatMoney(receivable.saldo)}</strong>{' '}
              · vence {formatDate(receivable.due_date)}
            </span>
            {receivable.dias_em_atraso > 0 && (
              <Badge label={`${tier.label} em atraso`} className={tier.badge} />
            )}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Valor recebido"
            required
            error={errors.amount?.message}
            hint="Pode ser parcial — o saldo continua em aberto."
          >
            <MoneyInput {...register('amount')} />
          </Field>

          <Field label="Data do recebimento" required error={errors.paid_on?.message}>
            <Input type="date" {...register('paid_on')} />
          </Field>

          <Field label="Forma de pagamento" error={errors.method?.message}>
            <Select {...register('method')}>
              {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Comprovante" error={errors.receipt_ref?.message}>
            <Input placeholder="Opcional" {...register('receipt_ref')} />
          </Field>
        </div>

        {mutation.isError && <ErrorBox message={errorMessage(mutation.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Registrar recebimento
          </Button>
        </div>
      </form>
    </Modal>
  )
}
