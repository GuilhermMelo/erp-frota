import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info, Pencil, Plus, Trash2 } from 'lucide-react'
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
import { formatDate, formatMoney, today } from '../../lib/format'

/* ---------------------------------------------------------------- tipos */

type ExpenseOrigin = 'manual' | 'maintenance' | 'fine'

type ExpenseCategory = {
  id: number
  code: string
  name: string
  /** Separa INVESTIMENTO no carro (blindagem, kit gás) de CUSTO de operação (óleo, IPVA). */
  is_capex: boolean
}

type Expense = {
  id: string
  code: string
  vehicle_id: string
  category_id: number
  category: ExpenseCategory
  maintenance_id: string | null
  fine_id: string | null
  supplier_name: string | null
  description: string | null
  amount: string
  competence_date: string
  paid_on: string | null
  status: 'pending' | 'paid'
  origin: ExpenseOrigin
  odometer: number | null
  document_number: string | null
  notes: string | null
}

type Vehicle = { id: string; plate: string; brand: string; model: string }
type Coded = { id: string; code: string }

const EXPENSE_STATUS: Record<string, { label: string; className: string }> = {
  paid: { label: 'Paga', className: 'bg-emerald-100 text-emerald-800' },
  pending: { label: 'Em aberto', className: 'bg-amber-100 text-amber-800' },
}

const ORIGIN: Record<ExpenseOrigin, { label: string; className: string }> = {
  manual: { label: 'Manual', className: 'bg-slate-100 text-slate-600' },
  maintenance: { label: 'Manutenção', className: 'bg-blue-100 text-blue-800' },
  fine: { label: 'Multa', className: 'bg-purple-100 text-purple-800' },
}

const CAPEX_NOTE =
  'Investimento no carro — entra no investimento, não no custo por km.'

/* ---------------------------------------------------------------- página */

export function ExpensesPage() {
  const queryClient = useQueryClient()

  const [filters, setFilters] = useState({
    vehicle_id: '',
    category_id: '',
    status: '',
    date_from: '',
    date_to: '',
  })

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Expense | null>(null)
  const [deleting, setDeleting] = useState<Expense | null>(null)

  const vehiclesQuery = useQuery({
    queryKey: ['vehicles', {}],
    queryFn: async () => (await api.get<Vehicle[]>('/vehicles')).data,
  })

  const categoriesQuery = useQuery({
    queryKey: ['expense-categories'],
    queryFn: async () => (await api.get<ExpenseCategory[]>('/expense-categories')).data,
  })

  // A despesa traz `maintenance_id`/`fine_id`, mas não o CÓDIGO do registro que a gerou.
  // Buscamos as duas listas para poder dizer "edite a manutenção MAN000123" em vez de
  // "edite o registro de origem".
  const maintenancesQuery = useQuery({
    queryKey: ['maintenances', {}],
    queryFn: async () => (await api.get<Coded[]>('/maintenances')).data,
  })

  const finesQuery = useQuery({
    queryKey: ['fines', {}],
    queryFn: async () => (await api.get<Coded[]>('/fines')).data,
  })

  const params = {
    vehicle_id: filters.vehicle_id || undefined,
    category_id: filters.category_id || undefined,
    status: filters.status || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
  }

  const expensesQuery = useQuery({
    queryKey: ['expenses', params],
    queryFn: async () => (await api.get<Expense[]>('/expenses', { params })).data,
    placeholderData: (previous) => previous,
  })

  const deleteMutation = useMutation({
    mutationFn: (expense: Expense) => api.delete(`/expenses/${expense.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      setDeleting(null)
    },
  })

  const vehicles = vehiclesQuery.data ?? []
  const categories = categoriesQuery.data ?? []
  const vehicleById = new Map(vehicles.map((v) => [v.id, v]))
  const maintenanceById = new Map((maintenancesQuery.data ?? []).map((m) => [m.id, m.code]))
  const fineById = new Map((finesQuery.data ?? []).map((f) => [f.id, f.code]))

  /** Por que esta despesa não pode ser editada aqui — com o código do registro de origem. */
  function lockedReason(expense: Expense): string | null {
    if (expense.origin === 'maintenance') {
      const code = expense.maintenance_id ? maintenanceById.get(expense.maintenance_id) : null
      return `Gerada pela manutenção ${code ?? 'de origem'} — edite lá.`
    }
    if (expense.origin === 'fine') {
      const code = expense.fine_id ? fineById.get(expense.fine_id) : null
      return `Gerada pela multa ${code ?? 'de origem'} — edite lá.`
    }
    return null
  }

  const expenses = expensesQuery.data ?? []
  const set = (patch: Partial<typeof filters>) => setFilters((f) => ({ ...f, ...patch }))

  return (
    <div>
      <PageHeader
        title="Despesas"
        subtitle="Tudo o que sai por veículo. O valor de compra do carro NÃO entra aqui — ele mora no cadastro do veículo."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            Lançar despesa
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

          <Field label="Categoria">
            <Select
              value={filters.category_id}
              onChange={(e) => set({ category_id: e.target.value })}
            >
              <option value="">Todas</option>
              {categories.map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Situação">
            <Select value={filters.status} onChange={(e) => set({ status: e.target.value })}>
              <option value="">Todas</option>
              {Object.entries(EXPENSE_STATUS).map(([value, { label }]) => (
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

      {expensesQuery.isPending ? (
        <Spinner />
      ) : expensesQuery.isError ? (
        <ErrorBox message={errorMessage(expensesQuery.error)} />
      ) : expenses.length === 0 ? (
        <EmptyState message="Nenhuma despesa encontrada com esses filtros." />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Código</Th>
                <Th>Veículo</Th>
                <Th>Categoria</Th>
                <Th>Descrição</Th>
                <Th>Fornecedor</Th>
                <Th className="text-right">Valor</Th>
                <Th>Competência</Th>
                <Th>Pagamento</Th>
                <Th>Situação</Th>
                <Th>Origem</Th>
                <Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {expenses.map((expense) => {
                const locked = lockedReason(expense)
                const status = EXPENSE_STATUS[expense.status]
                return (
                  <tr
                    key={expense.id}
                    className={expense.category.is_capex ? 'bg-indigo-50/40' : 'hover:bg-slate-50'}
                  >
                    <Td className="font-mono text-xs text-slate-500">{expense.code}</Td>
                    <Td className="font-medium whitespace-nowrap text-slate-900">
                      {vehicleById.get(expense.vehicle_id)?.plate ?? '—'}
                    </Td>
                    <Td className="whitespace-nowrap">
                      <div className="text-slate-700">{expense.category.name}</div>
                      {expense.category.is_capex && (
                        <Badge
                          label="Investimento"
                          className="mt-0.5 bg-indigo-100 text-indigo-800"
                        />
                      )}
                    </Td>
                    <Td className="max-w-56 truncate text-slate-600">
                      {expense.description ?? '—'}
                    </Td>
                    <Td className="text-slate-600">{expense.supplier_name ?? '—'}</Td>
                    <Td className="text-right font-medium tabular-nums whitespace-nowrap">
                      {formatMoney(expense.amount)}
                    </Td>
                    <Td className="whitespace-nowrap">{formatDate(expense.competence_date)}</Td>
                    <Td className="whitespace-nowrap">{formatDate(expense.paid_on)}</Td>
                    <Td>
                      {status && <Badge label={status.label} className={status.className} />}
                    </Td>
                    <Td>
                      <Badge
                        label={ORIGIN[expense.origin].label}
                        className={ORIGIN[expense.origin].className}
                      />
                    </Td>
                    <Td className="text-right whitespace-nowrap">
                      <Button
                        variant="ghost"
                        title={locked ?? 'Editar'}
                        disabled={locked !== null}
                        onClick={() => setEditing(expense)}
                      >
                        <Pencil size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        className="text-red-600 hover:bg-red-50"
                        title={locked ?? 'Excluir'}
                        disabled={locked !== null}
                        onClick={() => setDeleting(expense)}
                      >
                        <Trash2 size={16} />
                      </Button>
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </Table>

          <div className="mt-4 space-y-2">
            <div className="flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
              <Info size={16} className="mt-0.5 shrink-0" />
              <span>
                As linhas marcadas com <strong>Investimento</strong> (ex.: melhorias e acessórios):{' '}
                <strong>{CAPEX_NOTE}</strong> É isso que mantém o custo por km honesto — uma
                blindagem de R$ 15 mil não é “gasto do mês”.
              </span>
            </div>
            <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
              <Info size={16} className="mt-0.5 shrink-0" />
              <span>
                Despesas com origem <strong>Manutenção</strong> ou <strong>Multa</strong> são
                reflexo do registro que as criou e <strong>não são editáveis aqui</strong> — edite
                a manutenção ou a multa, e a despesa acompanha.
              </span>
            </div>
          </div>
        </>
      )}

      {creating && <ExpenseFormModal categories={categories} onClose={() => setCreating(false)} />}
      {editing && (
        <ExpenseFormModal
          expense={editing}
          categories={categories}
          onClose={() => setEditing(null)}
        />
      )}

      <Modal open={deleting !== null} onClose={() => setDeleting(null)} title="Excluir despesa">
        <p className="text-sm text-slate-600">
          Excluir <strong>{deleting?.code}</strong> ({formatMoney(deleting?.amount)})? Isso muda o{' '}
          <strong>lucro do veículo</strong>.
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

const expenseSchema = z
  .object({
    vehicle_id: z.string().min(1, 'Escolha o veículo.'),
    category_id: z.string().min(1, 'Escolha a categoria.'),
    amount: z.string().refine((v) => {
      const normalized = v.trim().replace(',', '.')
      return /^\d+(\.\d{1,2})?$/.test(normalized) && Number(normalized) > 0
    }, 'Informe um valor maior que zero.'),
    description: z.string(),
    supplier_name: z.string(),
    competence_date: z.string().min(1, 'Informe a data de competência.'),
    status: z.enum(['paid', 'pending']),
    paid_on: z.string(),
    odometer: z.string(),
    document_number: z.string(),
    notes: z.string(),
  })
  .superRefine((form, ctx) => {
    // Espelha o CHECK do banco: (status = 'paid') = (paid_on IS NOT NULL).
    if (form.status === 'paid' && !form.paid_on) {
      ctx.addIssue({
        code: 'custom',
        path: ['paid_on'],
        message: 'Despesa paga precisa da data de pagamento.',
      })
    }
    if (form.odometer && !/^\d+$/.test(form.odometer.trim())) {
      ctx.addIssue({
        code: 'custom',
        path: ['odometer'],
        message: 'O odômetro deve ser um número inteiro de km.',
      })
    }
  })

type ExpenseForm = z.infer<typeof expenseSchema>

function ExpenseFormModal({
  expense,
  categories,
  onClose,
}: {
  expense?: Expense
  categories: ExpenseCategory[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const isEdit = expense !== undefined

  const vehiclesQuery = useQuery({
    queryKey: ['vehicles', {}],
    queryFn: async () => (await api.get<Vehicle[]>('/vehicles')).data,
  })

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ExpenseForm>({
    resolver: zodResolver(expenseSchema),
    defaultValues: expense
      ? {
          vehicle_id: expense.vehicle_id,
          category_id: String(expense.category_id),
          amount: expense.amount,
          description: expense.description ?? '',
          supplier_name: expense.supplier_name ?? '',
          competence_date: expense.competence_date,
          status: expense.status,
          paid_on: expense.paid_on ?? '',
          odometer: expense.odometer === null ? '' : String(expense.odometer),
          document_number: expense.document_number ?? '',
          notes: expense.notes ?? '',
        }
      : {
          vehicle_id: '',
          category_id: '',
          amount: '',
          description: '',
          supplier_name: '',
          competence_date: today(),
          status: 'paid',
          paid_on: today(),
          odometer: '',
          document_number: '',
          notes: '',
        },
  })

  const mutation = useMutation({
    mutationFn: (form: ExpenseForm) => {
      const payload = {
        vehicle_id: form.vehicle_id,
        category_id: Number(form.category_id),
        // Dinheiro como STRING: vira `Decimal` no backend, sem passar por float.
        amount: form.amount.trim().replace(',', '.'),
        description: form.description.trim() || null,
        supplier_name: form.supplier_name.trim() || null,
        competence_date: form.competence_date,
        status: form.status,
        // Pendente NÃO pode ter data de pagamento (CHECK do banco).
        paid_on: form.status === 'paid' ? form.paid_on : null,
        odometer: form.odometer.trim() ? Number(form.odometer.trim()) : null,
        document_number: form.document_number.trim() || null,
        notes: form.notes.trim() || null,
      }
      return expense
        ? api.patch(`/expenses/${expense.id}`, payload)
        : api.post('/expenses', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      onClose()
    },
  })

  const status = watch('status')
  const categoryId = watch('category_id')
  const selectedCategory = categories.find((c) => String(c.id) === categoryId)

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? `Editar despesa ${expense.code}` : 'Lançar despesa'}
      wide
    >
      <form onSubmit={handleSubmit((form) => mutation.mutate(form))} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Veículo"
            required
            error={errors.vehicle_id?.message}
            hint="Toda despesa é de um carro — é assim que o lucro dele fecha."
          >
            <Select {...register('vehicle_id')} disabled={vehiclesQuery.isPending}>
              <option value="">Selecione…</option>
              {(vehiclesQuery.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate} — {v.brand} {v.model}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Categoria" required error={errors.category_id?.message}>
            <Select {...register('category_id')}>
              <option value="">Selecione…</option>
              {categories.map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.name}
                  {c.is_capex ? ' · investimento' : ''}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Valor" required error={errors.amount?.message}>
            <MoneyInput placeholder="0.00" {...register('amount')} />
          </Field>

          <Field label="Fornecedor" error={errors.supplier_name?.message}>
            <Input placeholder="Ex.: Auto Center Silva" {...register('supplier_name')} />
          </Field>

          <div className="sm:col-span-2">
            <Field label="Descrição" error={errors.description?.message}>
              <Input placeholder="Ex.: troca de óleo e filtro" {...register('description')} />
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

          <Field label="Situação" required error={errors.status?.message}>
            <Select {...register('status')}>
              <option value="paid">Paga</option>
              <option value="pending">Em aberto</option>
            </Select>
          </Field>

          {status === 'paid' ? (
            <Field label="Data do pagamento" required error={errors.paid_on?.message}>
              <Input type="date" {...register('paid_on')} />
            </Field>
          ) : (
            <div className="flex items-end">
              <p className="pb-2 text-xs text-slate-500">
                Despesa em aberto não tem data de pagamento. Marque como paga quando quitar.
              </p>
            </div>
          )}

          <Field label="Odômetro (km)" error={errors.odometer?.message}>
            <Input type="number" min="0" step="1" placeholder="45000" {...register('odometer')} />
          </Field>

          <Field label="Nº do documento" error={errors.document_number?.message}>
            <Input placeholder="Nota fiscal, recibo…" {...register('document_number')} />
          </Field>
        </div>

        {/* É esta distinção que faz o custo por km ficar honesto. */}
        {selectedCategory?.is_capex && (
          <div className="flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
            <Info size={16} className="mt-0.5 shrink-0" />
            <div>
              <strong>{CAPEX_NOTE}</strong>
              <p className="mt-1">
                Melhorias e acessórios valorizam o carro em vez de consumir o mês — por isso não
                sujam o custo por km, que só conta o que é operação (óleo, pneu, IPVA).
              </p>
            </div>
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
