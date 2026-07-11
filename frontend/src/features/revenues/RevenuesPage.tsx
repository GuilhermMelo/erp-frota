import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, Info, Pencil, Plus, Trash2 } from 'lucide-react'
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
  Textarea,
  Th,
} from '../../components/ui'
import { REVENUE_STATUS, formatDate, formatMoney, today } from '../../lib/format'

/* ---------------------------------------------------------------- tipos */

type RevenueCategory = 'aluguel' | 'reembolso' | 'caucao_retida' | 'outros'
type RevenueOrigin = 'manual' | 'contract'

type Revenue = {
  id: string
  code: string
  vehicle_id: string
  driver_id: string | null
  contract_id: string | null
  category: RevenueCategory
  description: string | null
  amount: string
  paid_amount: string
  competence_date: string
  due_date: string
  status: string
  origin: RevenueOrigin
  notes: string | null
}

type RevenuePayment = {
  id: string
  amount: string
  paid_on: string
  method: string
  receipt_ref: string | null
}

type RevenueDetail = Revenue & { payments: RevenuePayment[] }

type Vehicle = { id: string; plate: string; brand: string; model: string }
type Driver = { id: string; full_name: string }

const CATEGORIES: Record<RevenueCategory, string> = {
  aluguel: 'Aluguel',
  reembolso: 'Reembolso (multa devolvida pelo motorista)',
  caucao_retida: 'Caução retida',
  outros: 'Outros',
}

const PAYMENT_METHODS: Record<string, string> = {
  pix: 'PIX',
  dinheiro: 'Dinheiro',
  transferencia: 'Transferência',
  cartao: 'Cartão',
  boleto: 'Boleto',
  outro: 'Outro',
}

/** Receita gerada pelo contrato é reflexo do contrato, não um lançamento avulso. */
const DE_CONTRATO = 'Gerada pelo contrato — edite ou encerre o contrato, não a cobrança.'

/* ---------------------------------------------------------------- dinheiro */

/**
 * Dinheiro vem da API como STRING ("800.00") porque é `Decimal` no backend.
 *
 * Estas duas funções servem SÓ para mostrar o saldo em aberto de uma cobrança na tela, e
 * fazem a conta em CENTAVOS INTEIROS — nunca em float, que é bug de dinheiro (CLAUDE.md,
 * regra 1). Quem decide se um pagamento cabe no saldo é o backend, em `Decimal`.
 */
function toCents(value: string): number | null {
  const v = value.trim().replace(',', '.')
  if (!/^\d+(\.\d{1,2})?$/.test(v)) return null
  const [reais, centavos = ''] = v.split('.')
  return Number(reais) * 100 + Number(centavos.padEnd(2, '0'))
}

function fromCents(cents: number): string {
  return `${Math.trunc(cents / 100)}.${String(cents % 100).padStart(2, '0')}`
}

/** Saldo em aberto da cobrança (valor − já recebido), só para exibir. */
function outstanding(revenue: Revenue): string {
  const amount = toCents(revenue.amount) ?? 0
  const paid = toCents(revenue.paid_amount) ?? 0
  return fromCents(Math.max(0, amount - paid))
}

/* ---------------------------------------------------------------- página */

export function RevenuesPage() {
  const [filters, setFilters] = useState({
    vehicle_id: '',
    driver_id: '',
    status: '',
    date_from: '',
    date_to: '',
  })

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Revenue | null>(null)
  const [viewing, setViewing] = useState<Revenue | null>(null)
  const [deleting, setDeleting] = useState<Revenue | null>(null)

  const queryClient = useQueryClient()

  const vehiclesQuery = useQuery({
    queryKey: ['vehicles', {}],
    queryFn: async () => (await api.get<Vehicle[]>('/vehicles')).data,
  })

  const driversQuery = useQuery({
    queryKey: ['drivers', {}],
    queryFn: async () => (await api.get<Driver[]>('/drivers')).data,
  })

  const params = {
    vehicle_id: filters.vehicle_id || undefined,
    driver_id: filters.driver_id || undefined,
    status: filters.status || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
  }

  const revenuesQuery = useQuery({
    queryKey: ['revenues', params],
    queryFn: async () => (await api.get<Revenue[]>('/revenues', { params })).data,
    placeholderData: (previous) => previous,
  })

  const deleteMutation = useMutation({
    mutationFn: (revenue: Revenue) => api.delete(`/revenues/${revenue.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['revenues'] })
      queryClient.invalidateQueries({ queryKey: ['receivables'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      setDeleting(null)
    },
  })

  // A API devolve `vehicle_id`/`driver_id` crus (sem o nome junto): a tela junta aqui.
  const vehicles = vehiclesQuery.data ?? []
  const drivers = driversQuery.data ?? []
  const vehicleById = new Map(vehicles.map((v) => [v.id, v]))
  const driverById = new Map(drivers.map((d) => [d.id, d]))

  const revenues = revenuesQuery.data ?? []
  const set = (patch: Partial<typeof filters>) => setFilters((f) => ({ ...f, ...patch }))

  return (
    <div>
      <PageHeader
        title="Receitas"
        subtitle="Tudo o que entra por veículo: aluguel, reembolso de multa e caução retida."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            Lançar receita
          </Button>
        }
      />

      <Card className="mb-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Veículo">
            <Select
              value={filters.vehicle_id}
              onChange={(e) => set({ vehicle_id: e.target.value })}
            >
              <option value="">Todos</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate} — {v.brand} {v.model}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Motorista">
            <Select value={filters.driver_id} onChange={(e) => set({ driver_id: e.target.value })}>
              <option value="">Todos</option>
              {drivers.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.full_name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Situação">
            <Select value={filters.status} onChange={(e) => set({ status: e.target.value })}>
              <option value="">Todas</option>
              {Object.entries(REVENUE_STATUS).map(([value, { label }]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Competência de">
            <Input
              type="date"
              value={filters.date_from}
              onChange={(e) => set({ date_from: e.target.value })}
            />
          </Field>

          <Field label="Competência até">
            <Input
              type="date"
              value={filters.date_to}
              onChange={(e) => set({ date_to: e.target.value })}
            />
          </Field>
        </div>
      </Card>

      {revenuesQuery.isPending ? (
        <Spinner />
      ) : revenuesQuery.isError ? (
        <ErrorBox message={errorMessage(revenuesQuery.error)} />
      ) : revenues.length === 0 ? (
        <EmptyState message="Nenhuma receita encontrada com esses filtros." />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Código</Th>
                <Th>Veículo</Th>
                <Th>Motorista</Th>
                <Th>Categoria</Th>
                <Th>Descrição</Th>
                <Th className="text-right">Valor</Th>
                <Th className="text-right">Recebido</Th>
                <Th>Competência</Th>
                <Th>Vencimento</Th>
                <Th>Situação</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {revenues.map((revenue) => {
                const status = REVENUE_STATUS[revenue.status] ?? {
                  label: revenue.status,
                  className: 'bg-slate-100 text-slate-600',
                }
                const fromContract = revenue.origin === 'contract'
                return (
                  <tr key={revenue.id} className="hover:bg-slate-50">
                    <Td className="font-mono text-xs text-slate-500">{revenue.code}</Td>
                    <Td className="font-medium whitespace-nowrap text-slate-900">
                      {vehicleById.get(revenue.vehicle_id)?.plate ?? '—'}
                    </Td>
                    <Td className="whitespace-nowrap">
                      {revenue.driver_id ? (driverById.get(revenue.driver_id)?.full_name ?? '—') : '—'}
                    </Td>
                    <Td className="whitespace-nowrap">
                      {revenue.category === 'caucao_retida' ? (
                        <Badge label="Caução retida" className="bg-violet-100 text-violet-800" />
                      ) : (
                        <span className="text-slate-600">
                          {CATEGORIES[revenue.category]?.split(' (')[0] ?? revenue.category}
                        </span>
                      )}
                    </Td>
                    <Td className="max-w-64 truncate text-slate-600" >
                      {revenue.description ?? '—'}
                      {fromContract && (
                        <Badge
                          label="Contrato"
                          className="ml-2 bg-blue-100 text-blue-800 align-middle"
                        />
                      )}
                    </Td>
                    <Td className="text-right font-medium tabular-nums whitespace-nowrap">
                      {formatMoney(revenue.amount)}
                    </Td>
                    <Td className="text-right tabular-nums whitespace-nowrap text-slate-600">
                      {formatMoney(revenue.paid_amount)}
                    </Td>
                    <Td className="whitespace-nowrap">{formatDate(revenue.competence_date)}</Td>
                    <Td className="whitespace-nowrap">{formatDate(revenue.due_date)}</Td>
                    <Td>
                      <Badge label={status.label} className={status.className} />
                    </Td>
                    <Td className="text-right whitespace-nowrap">
                      <Button
                        variant="ghost"
                        title="Ver pagamentos"
                        onClick={() => setViewing(revenue)}
                      >
                        <Eye size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        title={fromContract ? DE_CONTRATO : 'Editar'}
                        disabled={fromContract}
                        onClick={() => setEditing(revenue)}
                      >
                        <Pencil size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        className="text-red-600 hover:bg-red-50"
                        title={fromContract ? DE_CONTRATO : 'Excluir'}
                        disabled={fromContract}
                        onClick={() => setDeleting(revenue)}
                      >
                        <Trash2 size={16} />
                      </Button>
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </Table>

          <div className="mt-4 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            <Info size={16} className="mt-0.5 shrink-0" />
            <span>
              As receitas marcadas com <strong>Contrato</strong> foram geradas pela cobrança
              semanal e <strong>não podem ser editadas nem excluídas</strong> aqui — a fonte é o
              contrato. Receber, você pode: clique no olho e registre o pagamento.
            </span>
          </div>
        </>
      )}

      {creating && <RevenueFormModal onClose={() => setCreating(false)} />}
      {editing && <RevenueFormModal revenue={editing} onClose={() => setEditing(null)} />}
      {viewing && <RevenueDetailModal revenue={viewing} onClose={() => setViewing(null)} />}

      <Modal open={deleting !== null} onClose={() => setDeleting(null)} title="Excluir receita">
        <p className="text-sm text-slate-600">
          Excluir <strong>{deleting?.code}</strong> ({formatMoney(deleting?.amount)})? Os
          pagamentos registrados nela somem junto e o <strong>lucro do veículo muda</strong>.
        </p>

        {deleteMutation.isError && (
          <div className="mt-4">
            <ErrorBox message={errorMessage(deleteMutation.error)} />
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleting(null)}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            loading={deleteMutation.isPending}
            onClick={() => deleting && deleteMutation.mutate(deleting)}
          >
            Excluir
          </Button>
        </div>
      </Modal>
    </div>
  )
}

/* ---------------------------------------------------------------- lançar / editar */

const revenueSchema = z.object({
  vehicle_id: z.string().min(1, 'Escolha o veículo.'),
  driver_id: z.string(),
  category: z.enum(['aluguel', 'reembolso', 'caucao_retida', 'outros']),
  description: z.string(),
  amount: z.string().refine((v) => (toCents(v) ?? 0) > 0, 'Informe um valor maior que zero.'),
  competence_date: z.string().min(1, 'Informe a data de competência.'),
  due_date: z.string(),
  notes: z.string(),
  pay_now: z.boolean(),
  paid_on: z.string(),
  method: z.string(),
})

type RevenueForm = z.infer<typeof revenueSchema>

function RevenueFormModal({ revenue, onClose }: { revenue?: Revenue; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = revenue !== undefined

  const vehiclesQuery = useQuery({
    queryKey: ['vehicles', {}],
    queryFn: async () => (await api.get<Vehicle[]>('/vehicles')).data,
  })

  const driversQuery = useQuery({
    queryKey: ['drivers', {}],
    queryFn: async () => (await api.get<Driver[]>('/drivers')).data,
  })

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RevenueForm>({
    resolver: zodResolver(revenueSchema),
    defaultValues: revenue
      ? {
          vehicle_id: revenue.vehicle_id,
          driver_id: revenue.driver_id ?? '',
          category: revenue.category,
          description: revenue.description ?? '',
          amount: revenue.amount,
          competence_date: revenue.competence_date,
          due_date: revenue.due_date,
          notes: revenue.notes ?? '',
          pay_now: false,
          paid_on: '',
          method: 'pix',
        }
      : {
          vehicle_id: '',
          driver_id: '',
          category: 'aluguel',
          description: '',
          amount: '',
          competence_date: today(),
          due_date: '',
          notes: '',
          // O caminho comum: "recebi R$ 800 hoje". A conta a receber existe por baixo,
          // nasce e é quitada no mesmo instante — o operador não vê a maquinaria.
          pay_now: true,
          paid_on: today(),
          method: 'pix',
        },
  })

  const mutation = useMutation({
    mutationFn: (form: RevenueForm) => {
      // Dinheiro trafega como STRING — nunca vira float no caminho até o backend.
      const amount = form.amount.trim().replace(',', '.')

      if (revenue) {
        return api.patch(`/revenues/${revenue.id}`, {
          driver_id: form.driver_id || null,
          category: form.category,
          description: form.description.trim() || null,
          amount,
          competence_date: form.competence_date,
          due_date: form.due_date || form.competence_date,
          notes: form.notes.trim() || null,
        })
      }

      return api.post('/revenues', {
        vehicle_id: form.vehicle_id,
        driver_id: form.driver_id || null,
        category: form.category,
        description: form.description.trim() || null,
        amount,
        competence_date: form.competence_date,
        due_date: form.due_date || null,
        notes: form.notes.trim() || null,
        pay_now: form.pay_now,
        // `paid_on` só pode viajar junto com pay_now = true (o backend recusa o contrário).
        ...(form.pay_now ? { paid_on: form.paid_on || today(), method: form.method } : {}),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['revenues'] })
      queryClient.invalidateQueries({ queryKey: ['receivables'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      onClose()
    },
  })

  const payNow = watch('pay_now')
  const category = watch('category')

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? `Editar receita ${revenue.code}` : 'Lançar receita'}
      wide
    >
      <form onSubmit={handleSubmit((form) => mutation.mutate(form))} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Veículo"
            required
            error={errors.vehicle_id?.message}
            hint={isEdit ? 'O veículo de uma receita não muda.' : 'Toda receita é de um carro.'}
          >
            <Select
              {...register('vehicle_id')}
              disabled={isEdit || vehiclesQuery.isPending}
            >
              <option value="">Selecione…</option>
              {(vehiclesQuery.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate} — {v.brand} {v.model}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Motorista" error={errors.driver_id?.message}>
            <Select {...register('driver_id')} disabled={driversQuery.isPending}>
              <option value="">Sem motorista</option>
              {(driversQuery.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.full_name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Categoria" required error={errors.category?.message}>
            <Select {...register('category')}>
              {Object.entries(CATEGORIES).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Valor" required error={errors.amount?.message}>
            <MoneyInput placeholder="800.00" {...register('amount')} />
          </Field>

          <div className="sm:col-span-2">
            <Field label="Descrição" error={errors.description?.message}>
              <Input placeholder="Ex.: aluguel da semana" {...register('description')} />
            </Field>
          </div>

          <Field
            label="Data de competência"
            required
            error={errors.competence_date?.message}
            hint="A data do fato."
          >
            <Input type="date" {...register('competence_date')} />
          </Field>

          <Field
            label="Vencimento"
            error={errors.due_date?.message}
            hint="Em branco = vence no dia da competência."
          >
            <Input type="date" {...register('due_date')} />
          </Field>
        </div>

        {category === 'caucao_retida' && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <Info size={16} className="mt-0.5 shrink-0" />
            <span>
              A caução retida normalmente é lançada <strong>sozinha</strong>, ao encerrar o
              contrato. Só lance aqui se estiver acertando um contrato antigo — lançar duas vezes
              contaria o mesmo dinheiro em dobro.
            </span>
          </div>
        )}

        {!isEdit && (
          <div className="rounded-lg border border-slate-200 p-4">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                className="size-4 rounded border-slate-300"
                {...register('pay_now')}
              />
              Já recebi este valor
            </label>

            {payNow ? (
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field label="Data do recebimento" error={errors.paid_on?.message}>
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
              </div>
            ) : (
              <p className="mt-2 text-xs text-slate-500">
                A receita nasce <strong>em aberto</strong> e vai para a tela de Cobranças até o
                motorista pagar.
              </p>
            )}
          </div>
        )}

        <Field label="Observações" error={errors.notes?.message}>
          <Textarea {...register('notes')} />
        </Field>

        {mutation.isError && <ErrorBox message={errorMessage(mutation.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {isEdit ? 'Salvar' : 'Lançar'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- detalhe + pagamentos */

const paymentSchema = z.object({
  amount: z.string().refine((v) => (toCents(v) ?? 0) > 0, 'Informe um valor maior que zero.'),
  paid_on: z.string().min(1, 'Informe a data do recebimento.'),
  method: z.string(),
  receipt_ref: z.string(),
})

type PaymentForm = z.infer<typeof paymentSchema>

function RevenueDetailModal({ revenue, onClose }: { revenue: Revenue; onClose: () => void }) {
  const queryClient = useQueryClient()

  const detailQuery = useQuery({
    queryKey: ['revenues', revenue.id],
    queryFn: async () => (await api.get<RevenueDetail>(`/revenues/${revenue.id}`)).data,
  })

  const detail = detailQuery.data
  const saldo = detail ? outstanding(detail) : '0.00'
  const canReceive = !!detail && detail.status !== 'canceled' && (toCents(saldo) ?? 0) > 0

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PaymentForm>({
    resolver: zodResolver(paymentSchema),
    defaultValues: { amount: '', paid_on: today(), method: 'pix', receipt_ref: '' },
  })

  const mutation = useMutation({
    mutationFn: (form: PaymentForm) =>
      api.post(`/revenues/${revenue.id}/payments`, {
        // STRING: quem valida se o pagamento cabe no saldo é o backend, em `Decimal`.
        amount: form.amount.trim().replace(',', '.'),
        paid_on: form.paid_on,
        method: form.method,
        receipt_ref: form.receipt_ref.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['revenues'] })
      queryClient.invalidateQueries({ queryKey: ['receivables'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      reset({ amount: '', paid_on: today(), method: 'pix', receipt_ref: '' })
    },
  })

  const status = detail ? (REVENUE_STATUS[detail.status] ?? null) : null

  return (
    <Modal open onClose={onClose} title={`Receita ${revenue.code}`} wide>
      {detailQuery.isPending ? (
        <Spinner />
      ) : detailQuery.isError ? (
        <ErrorBox message={errorMessage(detailQuery.error)} />
      ) : detail ? (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 rounded-lg bg-slate-50 p-4 text-sm sm:grid-cols-4">
            <div>
              <div className="text-xs text-slate-500">Valor</div>
              <div className="font-semibold tabular-nums text-slate-900">
                {formatMoney(detail.amount)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Recebido</div>
              <div className="font-semibold tabular-nums text-emerald-600">
                {formatMoney(detail.paid_amount)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Em aberto</div>
              <div className="font-semibold tabular-nums text-slate-900">
                {formatMoney(saldo)}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Situação</div>
              {status && <Badge label={status.label} className={status.className} />}
            </div>
            <div className="col-span-2">
              <div className="text-xs text-slate-500">Descrição</div>
              <div className="text-slate-700">{detail.description ?? '—'}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Competência</div>
              <div className="text-slate-700">{formatDate(detail.competence_date)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Vencimento</div>
              <div className="text-slate-700">{formatDate(detail.due_date)}</div>
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Pagamentos</h3>
            {detail.payments.length === 0 ? (
              <EmptyState message="Nenhum pagamento registrado nesta cobrança." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Data</Th>
                    <Th className="text-right">Valor</Th>
                    <Th>Forma</Th>
                    <Th>Comprovante</Th>
                  </tr>
                </thead>
                <tbody>
                  {detail.payments.map((payment) => (
                    <tr key={payment.id}>
                      <Td className="whitespace-nowrap">{formatDate(payment.paid_on)}</Td>
                      <Td className="text-right font-medium tabular-nums">
                        {formatMoney(payment.amount)}
                      </Td>
                      <Td>{PAYMENT_METHODS[payment.method] ?? payment.method}</Td>
                      <Td className="text-slate-500">{payment.receipt_ref ?? '—'}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>

          {canReceive ? (
            <form
              onSubmit={handleSubmit((form) => mutation.mutate(form))}
              className="rounded-lg border border-slate-200 p-4"
            >
              <h3 className="mb-3 text-sm font-semibold text-slate-900">
                Registrar pagamento{' '}
                <span className="font-normal text-slate-500">
                  (parcial ou total — em aberto: {formatMoney(saldo)})
                </span>
              </h3>
              <div className="grid gap-4 sm:grid-cols-4">
                <Field label="Valor" required error={errors.amount?.message}>
                  <MoneyInput placeholder={saldo} {...register('amount')} />
                </Field>
                <Field label="Data" required error={errors.paid_on?.message}>
                  <Input type="date" {...register('paid_on')} />
                </Field>
                <Field label="Forma" error={errors.method?.message}>
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

              {mutation.isError && (
                <div className="mt-3">
                  <ErrorBox message={errorMessage(mutation.error)} />
                </div>
              )}

              <div className="mt-4 flex justify-end">
                <Button type="submit" loading={mutation.isPending}>
                  Registrar pagamento
                </Button>
              </div>
            </form>
          ) : (
            <p className="text-sm text-slate-500">
              {detail.status === 'canceled'
                ? 'Cobrança cancelada — não aceita pagamento.'
                : 'Cobrança totalmente paga.'}
            </p>
          )}

          <div className="flex justify-end">
            <Button variant="secondary" onClick={onClose}>
              Fechar
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}
