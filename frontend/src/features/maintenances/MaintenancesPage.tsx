/**
 * Manutenções — o HISTÓRICO do que já foi feito no carro.
 *
 * Não há plano preventivo, lembrete nem "próxima troca": está fora do escopo (MANIFESTO.md).
 * O que esta tela precisa deixar óbvio é que salvar a manutenção JÁ CRIA a despesa do
 * veículo (o backend gera a Expense com origin='maintenance'). Sem esse aviso o usuário
 * lança a mesma nota de novo em Despesas, o custo do carro dobra e o lucro vira ficção.
 */

import { useRef, useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info, Paperclip, Plus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { api, errorMessage } from '../../api/client'
import { AttachmentsPanel } from '../../components/AttachmentsPanel'
import {
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
import { uploadDocument } from '../../lib/authFile'
import { formatDate, formatMoney, formatNumber, today } from '../../lib/format'

type VehicleOption = { id: string; code: string; plate: string; brand: string; model: string }

type Maintenance = {
  id: string
  code: string
  vehicle_id: string
  kind: string
  description: string | null
  supplier_name: string | null
  /** Dinheiro chega como STRING ("450.00"). Só formatar — nunca fazer conta aqui. */
  amount: string
  performed_on: string
  odometer: number
  notes: string | null
  created_at: string
  vehicle: VehicleOption | null
}

/** Sugestões do `<datalist>`. O campo é texto livre: um serviço novo não pode exigir deploy. */
const KIND_SUGGESTIONS = [
  'Troca de óleo',
  'Filtros',
  'Pastilhas de freio',
  'Correia',
  'Pneus',
  'Embreagem',
  'Revisão',
  'Alinhamento',
]

const schema = z.object({
  vehicle_id: z.string().min(1, 'Selecione o veículo.'),
  kind: z.string().trim().min(2, 'Informe o tipo do serviço.').max(60, 'Máximo de 60 caracteres.'),
  description: z.string().trim().max(500, 'Máximo de 500 caracteres.'),
  supplier_name: z.string().trim().max(120, 'Máximo de 120 caracteres.'),
  // Dinheiro trafega como STRING até a API (regra 1). Validamos o formato, não o número.
  amount: z
    .string()
    .min(1, 'Informe o valor.')
    .regex(/^\d{1,10}(\.\d{1,2})?$/, 'Valor inválido. Use até duas casas decimais.'),
  performed_on: z.string().min(1, 'Informe a data.'),
  odometer: z.string().min(1, 'Informe o odômetro.').regex(/^\d{1,9}$/, 'Somente números.'),
})

type FormValues = z.infer<typeof schema>

export function MaintenancesPage() {
  const queryClient = useQueryClient()
  const [vehicleFilter, setVehicleFilter] = useState('')
  const [creating, setCreating] = useState(false)
  const [attaching, setAttaching] = useState<Maintenance | null>(null)

  const vehicles = useQuery({
    queryKey: ['vehicles', 'select'],
    queryFn: async () => (await api.get<VehicleOption[]>('/vehicles')).data,
  })

  const maintenances = useQuery({
    queryKey: ['maintenances', vehicleFilter],
    queryFn: async () => {
      const { data } = await api.get<Maintenance[]>('/maintenances', {
        params: vehicleFilter ? { vehicle_id: vehicleFilter } : undefined,
      })
      return data
    },
  })

  return (
    <>
      <PageHeader
        title="Manutenções"
        subtitle="Histórico do que já foi feito em cada carro."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            Nova manutenção
          </Button>
        }
      />

      <AutoExpenseNotice />

      <Card className="mb-4">
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
      </Card>

      {maintenances.isPending ? (
        <Spinner />
      ) : maintenances.isError ? (
        <ErrorBox message={errorMessage(maintenances.error)} />
      ) : !maintenances.data.length ? (
        <EmptyState
          message={
            vehicleFilter
              ? 'Nenhuma manutenção para este veículo.'
              : 'Nenhuma manutenção registrada ainda.'
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Veículo</Th>
              <Th>Tipo</Th>
              <Th>Descrição</Th>
              <Th>Fornecedor</Th>
              <Th className="text-right">Valor</Th>
              <Th>Data</Th>
              <Th className="text-right">KM</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {maintenances.data.map((maintenance) => (
              <tr key={maintenance.id} className="hover:bg-slate-50">
                <Td className="font-mono text-xs text-slate-500">{maintenance.code}</Td>
                <Td>
                  {maintenance.vehicle ? (
                    <>
                      <div className="font-medium text-slate-800">{maintenance.vehicle.plate}</div>
                      <div className="text-xs text-slate-500">
                        {maintenance.vehicle.brand} {maintenance.vehicle.model}
                      </div>
                    </>
                  ) : (
                    '—'
                  )}
                </Td>
                <Td className="font-medium text-slate-700">{maintenance.kind}</Td>
                <Td className="max-w-64">
                  <span
                    className="block truncate text-slate-600"
                    title={maintenance.description ?? ''}
                  >
                    {maintenance.description || '—'}
                  </span>
                </Td>
                <Td className="text-slate-600">{maintenance.supplier_name || '—'}</Td>
                <Td className="text-right font-medium whitespace-nowrap text-slate-800">
                  {formatMoney(maintenance.amount)}
                </Td>
                <Td className="whitespace-nowrap">{formatDate(maintenance.performed_on)}</Td>
                <Td className="text-right whitespace-nowrap text-slate-600">
                  {formatNumber(maintenance.odometer)} km
                </Td>
                <Td>
                  <Button
                    variant="ghost"
                    title="Nota fiscal e anexos"
                    onClick={() => setAttaching(maintenance)}
                  >
                    <Paperclip size={16} />
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <NewMaintenanceModal
        open={creating}
        onClose={() => setCreating(false)}
        vehicles={vehicles.data ?? []}
        onCreated={() => {
          queryClient.invalidateQueries({ queryKey: ['maintenances'] })
          // A manutenção virou despesa do carro: o resultado do veículo mudou.
          queryClient.invalidateQueries({ queryKey: ['expenses'] })
          queryClient.invalidateQueries({ queryKey: ['finance'] })
          setCreating(false)
        }}
      />

      <Modal
        open={attaching !== null}
        onClose={() => setAttaching(null)}
        title={`Anexos — ${attaching?.code ?? ''}`}
      >
        {attaching && (
          <>
            <p className="mb-4 text-sm text-slate-500">
              Nota fiscal da manutenção {attaching.kind.toLowerCase()} em{' '}
              {attaching.vehicle?.plate ?? 'veículo'}.
            </p>
            <AttachmentsPanel
              entityType="maintenance"
              entityId={attaching.id}
              kind="nota_fiscal"
              uploadLabel="Anexar nota fiscal"
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

/** O aviso que impede o lançamento em duplicidade. Fica sempre visível, não só no formulário. */
function AutoExpenseNotice() {
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
      <Info size={16} className="mt-0.5 shrink-0" />
      <span>
        <strong>A despesa do carro é criada automaticamente</strong> — não precisa lançar de novo
        em Despesas. Ao salvar a manutenção, o valor já entra no resultado do veículo.
      </span>
    </div>
  )
}

function NewMaintenanceModal({
  open,
  onClose,
  vehicles,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  vehicles: VehicleOption[]
  onCreated: () => void
}) {
  const invoice = useRef<HTMLInputElement>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      vehicle_id: '',
      kind: '',
      description: '',
      supplier_name: '',
      amount: '',
      performed_on: today(),
      odometer: '',
    },
  })

  const create = useMutation({
    mutationFn: async (values: FormValues) => {
      const { data } = await api.post<Maintenance>('/maintenances', {
        vehicle_id: values.vehicle_id,
        kind: values.kind,
        description: values.description || null,
        supplier_name: values.supplier_name || null,
        // STRING, sempre. Virar float aqui seria bug de dinheiro (CLAUDE.md, regra 1).
        amount: values.amount,
        performed_on: values.performed_on,
        odometer: Number(values.odometer),
      })

      // O anexo só pode subir DEPOIS: /files/upload precisa do id da manutenção.
      const file = invoice.current?.files?.[0]
      if (file) {
        await uploadDocument({
          entityType: 'maintenance',
          entityId: data.id,
          kind: 'nota_fiscal',
          file,
        })
      }
      return data
    },
    onSuccess: () => {
      reset()
      if (invoice.current) invoice.current.value = ''
      onCreated()
    },
  })

  function close() {
    if (create.isPending) return
    create.reset()
    reset()
    onClose()
  }

  return (
    <Modal open={open} onClose={close} title="Nova manutenção" wide>
      <form onSubmit={handleSubmit((values) => create.mutate(values))} className="space-y-4">
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
          A despesa do carro é criada automaticamente ao salvar. <strong>Não lance de novo</strong>{' '}
          na tela de Despesas.
        </div>

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
            label="Tipo de serviço"
            required
            error={errors.kind?.message}
            hint="Texto livre — as sugestões são só um atalho."
          >
            <Input list="maintenance-kinds" placeholder="Troca de óleo" {...register('kind')} />
            <datalist id="maintenance-kinds">
              {KIND_SUGGESTIONS.map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
          </Field>
        </div>

        <Field label="Descrição" error={errors.description?.message}>
          <Textarea
            placeholder="Óleo 5W30 sintético + filtro de óleo e de ar"
            {...register('description')}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Fornecedor / oficina" error={errors.supplier_name?.message}>
            <Input placeholder="Auto Center do Zé" {...register('supplier_name')} />
          </Field>

          <Field label="Valor" required error={errors.amount?.message}>
            <MoneyInput placeholder="0,00" {...register('amount')} />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data do serviço" required error={errors.performed_on?.message}>
            <Input type="date" {...register('performed_on')} />
          </Field>

          <Field
            label="Odômetro (km)"
            required
            error={errors.odometer?.message}
            hint="KM do carro no dia do serviço."
          >
            <Input type="number" min="0" step="1" placeholder="45000" {...register('odometer')} />
          </Field>
        </div>

        <Field label="Nota fiscal (opcional)" hint="JPEG, PNG, WebP ou PDF. Dá para anexar depois.">
          <input
            ref={invoice}
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf"
            className="w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-50"
          />
        </Field>

        {create.isError && <ErrorBox message={errorMessage(create.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={close} disabled={create.isPending}>
            Cancelar
          </Button>
          <Button type="submit" loading={create.isPending}>
            Salvar manutenção
          </Button>
        </div>
      </form>
    </Modal>
  )
}
