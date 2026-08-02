/**
 * Multas — o módulo do "quanto essa multa REALMENTE custou ao carro".
 *
 * O modelo (MANIFESTO.md): a despesa é registrada SEMPRE que você paga, vinculada ao carro e
 * ao motorista. Se o motorista reembolsa, entra uma RECEITA ligada à mesma multa e o líquido
 * (`net_cost = amount − reimbursed_amount`) dá zero sozinho. Registrar só as não-reembolsadas
 * seria mais curto e perderia as duas coisas que importam: quanto já se pagou de multa e
 * quanto cada motorista deve.
 *
 * Por isso a tela mostra as três colunas juntas — valor, reembolsado e custo líquido. É o
 * ponto do módulo.
 *
 * ATENÇÃO (CLAUDE.md, regra 1): dinheiro vem como STRING e não vira conta aqui. `reimbursed_amount`
 * e `net_cost` chegam prontos da API. Os `Number(...)` deste arquivo existem SÓ para comparar
 * (escolher um rótulo ou habilitar um botão) — nenhum valor exibido é calculado no frontend.
 */

import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info, Paperclip, Plus, Receipt, Wallet } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { api, errorMessage } from '../../api/client'
import { AttachmentsPanel } from '../../components/AttachmentsPanel'
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
  cn,
} from '../../components/ui'
import { formatDate, formatMoney, today } from '../../lib/format'

type FineStatus = 'pending' | 'paid' | 'canceled'

type VehicleOption = { id: string; code: string; plate: string; brand: string; model: string }
type DriverOption = { id: string; code: string; full_name: string }

type Fine = {
  id: string
  code: string
  vehicle_id: string
  driver_id: string | null
  infraction_date: string
  ait_number: string | null
  description: string
  location: string | null
  /** Dinheiro: STRING vinda da API. */
  amount: string
  due_date: string | null
  points: number | null
  driver_indication_deadline: string | null
  status: FineStatus
  paid_on: string | null
  notes: string | null
  vehicle: VehicleOption | null
  driver: DriverOption | null
  /** Somatório das receitas de reembolso desta multa — calculado no BACKEND. */
  reimbursed_amount: string
  /** amount − reimbursed_amount — calculado no BACKEND. */
  net_cost: string
}

const FINE_STATUS: Record<FineStatus, { label: string; className: string }> = {
  pending: { label: 'Em aberto', className: 'bg-amber-100 text-amber-800' },
  paid: { label: 'Paga por você', className: 'bg-blue-100 text-blue-800' },
  canceled: { label: 'Cancelada', className: 'bg-slate-100 text-slate-500' },
}

const PAYMENT_METHODS = [
  { value: 'pix', label: 'PIX' },
  { value: 'dinheiro', label: 'Dinheiro' },
  { value: 'transferencia', label: 'Transferência' },
  { value: 'cartao', label: 'Cartão' },
  { value: 'boleto', label: 'Boleto' },
  { value: 'outro', label: 'Outro' },
]

/**
 * Em que pé está o reembolso. Só COMPARA os valores que a API já mandou prontos —
 * nada é somado nem subtraído aqui.
 */
function reimbursementState(fine: Fine) {
  const reimbursed = Number(fine.reimbursed_amount)
  const net = Number(fine.net_cost)

  if (reimbursed <= 0) {
    return { label: 'Sem reembolso', className: 'bg-slate-100 text-slate-600', settled: false }
  }
  if (net <= 0) {
    return { label: 'Reembolsada', className: 'bg-emerald-100 text-emerald-800', settled: true }
  }
  return { label: 'Reembolso parcial', className: 'bg-orange-100 text-orange-800', settled: false }
}

/** Ainda há custo sobrando para o carro? (comparação, não conta) */
function hasNetCost(fine: Fine) {
  return Number(fine.net_cost) > 0
}

export function FinesPage() {
  const [vehicleFilter, setVehicleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [creating, setCreating] = useState(false)
  const [paying, setPaying] = useState<Fine | null>(null)
  const [reimbursing, setReimbursing] = useState<Fine | null>(null)
  const [attaching, setAttaching] = useState<Fine | null>(null)

  const vehicles = useQuery({
    queryKey: ['vehicles', 'select'],
    queryFn: async () => (await api.get<VehicleOption[]>('/vehicles')).data,
  })

  const drivers = useQuery({
    queryKey: ['drivers', 'select'],
    queryFn: async () => (await api.get<DriverOption[]>('/drivers')).data,
  })

  const fines = useQuery({
    queryKey: ['fines', vehicleFilter, statusFilter],
    queryFn: async () => {
      const { data } = await api.get<Fine[]>('/fines', {
        params: {
          ...(vehicleFilter ? { vehicle_id: vehicleFilter } : {}),
          ...(statusFilter ? { status: statusFilter } : {}),
        },
      })
      return data
    },
  })

  return (
    <>
      <PageHeader
        title="Multas"
        subtitle="Quanto a multa custou de verdade ao carro, depois do reembolso do motorista."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            Nova multa
          </Button>
        }
      />

      <div className="mb-4 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
        <Info size={16} className="mt-0.5 shrink-0" />
        <span>
          Ao <strong>registrar o pagamento</strong>, a despesa do carro é criada automaticamente.
          Ao <strong>registrar o reembolso do motorista</strong>, entra uma receita e o{' '}
          <strong>custo líquido da multa volta a zero</strong>. É por isso que a multa aparece nas
          duas pontas — e o resultado do veículo continua correto.
        </span>
      </div>

      <Card className="mb-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Filtrar por veículo">
            <Select value={vehicleFilter} onChange={(e) => setVehicleFilter(e.target.value)}>
              <option value="">Todos os veículos</option>
              {vehicles.data?.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicle.plate} — {vehicle.brand} {vehicle.model}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Filtrar por situação">
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">Todas</option>
              <option value="pending">Em aberto</option>
              <option value="paid">Pagas</option>
              <option value="canceled">Canceladas</option>
            </Select>
          </Field>
        </div>
      </Card>

      {fines.isPending ? (
        <Spinner />
      ) : fines.isError ? (
        <ErrorBox message={errorMessage(fines.error)} />
      ) : !fines.data.length ? (
        <EmptyState message="Nenhuma multa registrada." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Veículo</Th>
              <Th>Motorista</Th>
              <Th>Infração</Th>
              <Th>Descrição</Th>
              <Th className="text-right">Valor</Th>
              <Th>Situação</Th>
              <Th className="text-right">Reembolsado</Th>
              <Th className="text-right">Custo líquido</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {fines.data.map((fine) => {
              const reimbursement = reimbursementState(fine)
              const stillCosts = hasNetCost(fine)
              const canReimburse =
                fine.driver_id !== null && fine.status !== 'canceled' && stillCosts

              return (
                <tr key={fine.id} className="hover:bg-slate-50">
                  <Td className="font-mono text-xs text-slate-500">{fine.code}</Td>
                  <Td>
                    {fine.vehicle ? (
                      <>
                        <div className="font-medium text-slate-800">{fine.vehicle.plate}</div>
                        <div className="text-xs text-slate-500">
                          {fine.vehicle.brand} {fine.vehicle.model}
                        </div>
                      </>
                    ) : (
                      '—'
                    )}
                  </Td>
                  <Td className="text-slate-600">
                    {fine.driver ? (
                      fine.driver.full_name
                    ) : (
                      <span
                        className="text-xs text-slate-400"
                        title="Sem motorista não há de quem cobrar o reembolso."
                      >
                        Não identificado
                      </span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap">{formatDate(fine.infraction_date)}</Td>
                  <Td className="max-w-56">
                    <span className="block truncate text-slate-700" title={fine.description}>
                      {fine.description}
                    </span>
                  </Td>
                  <Td className="text-right font-medium whitespace-nowrap text-slate-800">
                    {formatMoney(fine.amount)}
                  </Td>
                  <Td>
                    <div className="flex flex-col items-start gap-1">
                      <Badge {...FINE_STATUS[fine.status]} />
                      <Badge label={reimbursement.label} className={reimbursement.className} />
                    </div>
                  </Td>
                  <Td className="text-right whitespace-nowrap text-emerald-700">
                    {formatMoney(fine.reimbursed_amount)}
                  </Td>
                  <Td className="text-right whitespace-nowrap">
                    <span
                      className={cn(
                        'font-semibold',
                        stillCosts ? 'text-red-600' : 'text-emerald-600',
                      )}
                      title={
                        stillCosts
                          ? 'Custo real desta multa para o carro.'
                          : 'O motorista reembolsou: a multa não custou nada ao carro.'
                      }
                    >
                      {formatMoney(fine.net_cost)}
                    </span>
                  </Td>
                  <Td>
                    <div className="flex justify-end gap-1 whitespace-nowrap">
                      {fine.status === 'pending' && (
                        <Button
                          variant="secondary"
                          className="px-2 py-1 text-xs"
                          title="Gera a despesa do carro."
                          onClick={() => setPaying(fine)}
                        >
                          <Wallet size={14} />
                          Pagar
                        </Button>
                      )}
                      {canReimburse && (
                        <Button
                          variant="secondary"
                          className="px-2 py-1 text-xs"
                          title="Gera a receita de reembolso e zera o custo líquido."
                          onClick={() => setReimbursing(fine)}
                        >
                          <Receipt size={14} />
                          Reembolso
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        title="Notificação e anexos"
                        onClick={() => setAttaching(fine)}
                      >
                        <Paperclip size={16} />
                      </Button>
                    </div>
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      <NewFineModal
        open={creating}
        onClose={() => setCreating(false)}
        vehicles={vehicles.data ?? []}
        drivers={drivers.data ?? []}
      />
      <PayFineModal fine={paying} onClose={() => setPaying(null)} />
      <ReimburseFineModal fine={reimbursing} onClose={() => setReimbursing(null)} />

      <Modal
        open={attaching !== null}
        onClose={() => setAttaching(null)}
        title={`Anexos — ${attaching?.code ?? ''}`}
      >
        {attaching && (
          <>
            <p className="mb-4 text-sm text-slate-500">
              Notificação da multa e demais documentos.
            </p>
            <AttachmentsPanel
              entityType="fine"
              entityId={attaching.id}
              kinds={['notificacao']}
              uploadLabel="Anexar notificação"
            />
            <div className="mt-5 flex justify-end">
              <Button variant="secondary" onClick={() => setAttaching(null)}>
                Fechar
              </Button>
            </div>
          </>
        )}
      </Modal>
    </>
  )
}

/** Invalida tudo que uma multa mexe: ela própria, a despesa e a receita que ela gera. */
function useInvalidateFines() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['fines'] })
    queryClient.invalidateQueries({ queryKey: ['expenses'] })
    queryClient.invalidateQueries({ queryKey: ['revenues'] })
    queryClient.invalidateQueries({ queryKey: ['finance'] })
  }
}

/* ------------------------------------------------------------------ nova multa */

const fineSchema = z.object({
  vehicle_id: z.string().min(1, 'Selecione o veículo.'),
  driver_id: z.string(),
  infraction_date: z.string().min(1, 'Informe a data da infração.'),
  ait_number: z.string().trim().max(40, 'Máximo de 40 caracteres.'),
  description: z.string().trim().min(2, 'Descreva a infração.').max(200, 'Máximo de 200 caracteres.'),
  location: z.string().trim().max(160, 'Máximo de 160 caracteres.'),
  amount: z
    .string()
    .min(1, 'Informe o valor.')
    .regex(/^\d{1,10}(\.\d{1,2})?$/, 'Valor inválido. Use até duas casas decimais.')
    // Comparação para validar, não conta: o backend exige valor > 0.
    .refine((value) => Number(value) > 0, 'O valor deve ser maior que zero.'),
  due_date: z.string(),
  points: z
    .string()
    .refine(
      (value) => value === '' || (/^\d{1,2}$/.test(value) && Number(value) <= 20),
      'Pontos entre 0 e 20.',
    ),
  driver_indication_deadline: z.string(),
})

type FineFormValues = z.infer<typeof fineSchema>

function NewFineModal({
  open,
  onClose,
  vehicles,
  drivers,
}: {
  open: boolean
  onClose: () => void
  vehicles: VehicleOption[]
  drivers: DriverOption[]
}) {
  const invalidate = useInvalidateFines()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FineFormValues>({
    resolver: zodResolver(fineSchema),
    defaultValues: {
      vehicle_id: '',
      driver_id: '',
      infraction_date: today(),
      ait_number: '',
      description: '',
      location: '',
      amount: '',
      due_date: '',
      points: '',
      driver_indication_deadline: '',
    },
  })

  const create = useMutation({
    mutationFn: (values: FineFormValues) =>
      api.post<Fine>('/fines', {
        vehicle_id: values.vehicle_id,
        driver_id: values.driver_id || null,
        infraction_date: values.infraction_date,
        ait_number: values.ait_number || null,
        description: values.description,
        location: values.location || null,
        // STRING até a API (regra 1).
        amount: values.amount,
        due_date: values.due_date || null,
        points: values.points === '' ? null : Number(values.points),
        driver_indication_deadline: values.driver_indication_deadline || null,
      }),
    onSuccess: () => {
      invalidate()
      reset()
      onClose()
    },
  })

  function close() {
    if (create.isPending) return
    create.reset()
    reset()
    onClose()
  }

  return (
    <Modal open={open} onClose={close} title="Nova multa" wide>
      <form onSubmit={handleSubmit((values) => create.mutate(values))} className="space-y-4">
        <p className="text-sm text-slate-500">
          A multa nasce <strong>em aberto</strong>. A despesa do carro só aparece quando você
          registrar o pagamento.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Veículo" required error={errors.vehicle_id?.message}>
            <Select {...register('vehicle_id')}>
              <option value="">Selecione…</option>
              {vehicles.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicle.plate} — {vehicle.brand} {vehicle.model}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Motorista"
            error={errors.driver_id?.message}
            hint="Sem motorista não há de quem cobrar o reembolso."
          >
            <Select {...register('driver_id')}>
              <option value="">Não identificado</option>
              {drivers.map((driver) => (
                <option key={driver.id} value={driver.id}>
                  {driver.full_name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data da infração" required error={errors.infraction_date?.message}>
            <Input type="date" {...register('infraction_date')} />
          </Field>

          <Field label="Nº do AIT" error={errors.ait_number?.message} hint="Auto de Infração de Trânsito.">
            <Input placeholder="AA00000000" {...register('ait_number')} />
          </Field>
        </div>

        <Field label="Descrição da infração" required error={errors.description?.message}>
          <Input placeholder="Excesso de velocidade em até 20%" {...register('description')} />
        </Field>

        <Field label="Local" error={errors.location?.message}>
          <Input placeholder="Av. Paulista, 1000 — São Paulo/SP" {...register('location')} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Valor" required error={errors.amount?.message}>
            <MoneyInput placeholder="0,00" {...register('amount')} />
          </Field>

          <Field label="Vencimento" error={errors.due_date?.message}>
            <Input type="date" {...register('due_date')} />
          </Field>

          <Field label="Pontos na CNH" error={errors.points?.message}>
            <Input type="number" min="0" max="20" step="1" placeholder="0" {...register('points')} />
          </Field>
        </div>

        <Field
          label="Prazo de indicação do condutor"
          error={errors.driver_indication_deadline?.message}
          hint="Guardado para consulta. O sistema não dispara alerta — perder o prazo dobra a multa."
        >
          <Input type="date" {...register('driver_indication_deadline')} />
        </Field>

        {create.isError && <ErrorBox message={errorMessage(create.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={close} disabled={create.isPending}>
            Cancelar
          </Button>
          <Button type="submit" loading={create.isPending}>
            Salvar multa
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ------------------------------------------------------------------ pagamento */

const paySchema = z.object({ paid_on: z.string().min(1, 'Informe a data do pagamento.') })
type PayFormValues = z.infer<typeof paySchema>

function PayFineModal({ fine, onClose }: { fine: Fine | null; onClose: () => void }) {
  const invalidate = useInvalidateFines()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PayFormValues>({
    resolver: zodResolver(paySchema),
    defaultValues: { paid_on: today() },
  })

  const pay = useMutation({
    mutationFn: (values: PayFormValues) => api.post(`/fines/${fine?.id}/pay`, values),
    onSuccess: () => {
      invalidate()
      reset({ paid_on: today() })
      onClose()
    },
  })

  function close() {
    if (pay.isPending) return
    pay.reset()
    reset({ paid_on: today() })
    onClose()
  }

  return (
    <Modal open={fine !== null} onClose={close} title="Registrar pagamento da multa">
      {fine && (
        <form onSubmit={handleSubmit((values) => pay.mutate(values))} className="space-y-4">
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <strong>Isto gera a despesa do carro.</strong> O valor de {formatMoney(fine.amount)} entra
            no resultado de {fine.vehicle?.plate ?? 'veículo'} na categoria multas. Não lance essa
            despesa de novo à mão.
          </div>

          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-slate-500">Multa</dt>
              <dd className="font-mono text-slate-800">{fine.code}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Valor</dt>
              <dd className="font-medium text-slate-800">{formatMoney(fine.amount)}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-slate-500">Infração</dt>
              <dd className="text-slate-800">{fine.description}</dd>
            </div>
          </dl>

          <Field label="Data do pagamento" required error={errors.paid_on?.message}>
            <Input type="date" {...register('paid_on')} />
          </Field>

          {pay.isError && <ErrorBox message={errorMessage(pay.error)} />}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={close} disabled={pay.isPending}>
              Cancelar
            </Button>
            <Button type="submit" loading={pay.isPending}>
              Registrar pagamento
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

/* ------------------------------------------------------------------ reembolso */

const reimburseSchema = z.object({
  amount: z
    .string()
    .min(1, 'Informe o valor reembolsado.')
    .regex(/^\d{1,10}(\.\d{1,2})?$/, 'Valor inválido. Use até duas casas decimais.')
    .refine((value) => Number(value) > 0, 'O valor deve ser maior que zero.'),
  paid_on: z.string().min(1, 'Informe a data do reembolso.'),
  method: z.string().min(1, 'Selecione a forma de pagamento.'),
})

type ReimburseFormValues = z.infer<typeof reimburseSchema>

function ReimburseFineModal({ fine, onClose }: { fine: Fine | null; onClose: () => void }) {
  const invalidate = useInvalidateFines()

  // Nada de reembolso parcial já lançado? O valor cheio da multa é o palpite certo.
  // Se já houve reembolso parcial, o campo nasce VAZIO de propósito: calcular "quanto
  // falta" seria fazer conta de dinheiro no frontend. Quem valida o teto é o backend.
  const partial = fine ? Number(fine.reimbursed_amount) > 0 : false

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ReimburseFormValues>({
    resolver: zodResolver(reimburseSchema),
    values: {
      amount: fine && !partial ? fine.amount : '',
      paid_on: today(),
      method: 'pix',
    },
  })

  const reimburse = useMutation({
    mutationFn: (values: ReimburseFormValues) =>
      api.post(`/fines/${fine?.id}/reimburse`, {
        amount: values.amount, // STRING (regra 1)
        paid_on: values.paid_on,
        method: values.method,
      }),
    onSuccess: () => {
      invalidate()
      onClose()
    },
  })

  function close() {
    if (reimburse.isPending) return
    reimburse.reset()
    reset()
    onClose()
  }

  return (
    <Modal open={fine !== null} onClose={close} title="Registrar reembolso do motorista">
      {fine && (
        <form onSubmit={handleSubmit((values) => reimburse.mutate(values))} className="space-y-4">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
            <strong>Isto gera uma receita</strong> (categoria reembolso) para{' '}
            {fine.vehicle?.plate ?? 'o veículo'}. Reembolsando o valor cheio, o{' '}
            <strong>custo líquido da multa volta a zero</strong> — a multa deixa de pesar no
            resultado do carro.
          </div>

          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-slate-500">Valor da multa</dt>
              <dd className="font-medium text-slate-800">{formatMoney(fine.amount)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Já reembolsado</dt>
              <dd className="font-medium text-emerald-700">{formatMoney(fine.reimbursed_amount)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Custo líquido hoje</dt>
              <dd className="font-medium text-red-600">{formatMoney(fine.net_cost)}</dd>
            </div>
          </dl>

          <div className="text-sm text-slate-600">
            Motorista: <strong>{fine.driver?.full_name ?? '—'}</strong>
          </div>

          <Field
            label="Valor reembolsado"
            required
            error={errors.amount?.message}
            hint={partial ? 'Esta multa já teve reembolso parcial — informe o valor recebido agora.' : undefined}
          >
            <MoneyInput placeholder="0,00" {...register('amount')} />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Data do reembolso" required error={errors.paid_on?.message}>
              <Input type="date" {...register('paid_on')} />
            </Field>

            <Field label="Forma de pagamento" required error={errors.method?.message}>
              <Select {...register('method')}>
                {PAYMENT_METHODS.map((method) => (
                  <option key={method.value} value={method.value}>
                    {method.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          {reimburse.isError && <ErrorBox message={errorMessage(reimburse.error)} />}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={close} disabled={reimburse.isPending}>
              Cancelar
            </Button>
            <Button type="submit" loading={reimburse.isPending}>
              Registrar reembolso
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}
