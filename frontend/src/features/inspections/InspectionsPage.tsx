/**
 * Vistorias — lista.
 *
 * A vistoria é a prova objetiva numa discussão sobre quem quebrou o quê: dá para comparar a
 * entrega com a devolução item a item. Aqui só se escolhe qual abrir; o trabalho de verdade
 * (checklist e fotos) é na tela de detalhe.
 */

import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Loader2, Plus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
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
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
} from '../../components/ui'
import { formatDateTime, formatNumber } from '../../lib/format'
import type { InspectionDetail, InspectionKind } from './types'
import { INSPECTION_KIND, inspectionKey } from './types'

type VehicleOption = { id: string; code: string; plate: string; brand: string; model: string }
type DriverOption = { id: string; code: string; full_name: string }
type ContractOption = {
  id: string
  code: string
  vehicle_id: string
  driver_id: string
  status: string
}

type Inspection = {
  id: string
  code: string
  vehicle_id: string
  driver_id: string | null
  contract_id: string | null
  user_id: string | null
  kind: InspectionKind
  inspected_at: string
  odometer: number
  fuel_level: number
  notes: string | null
  vehicle: VehicleOption
  driver: DriverOption | null
}

export function InspectionsPage() {
  const [vehicleFilter, setVehicleFilter] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [creating, setCreating] = useState(false)

  const vehicles = useQuery({
    queryKey: ['vehicles', 'select'],
    queryFn: async () => (await api.get<VehicleOption[]>('/vehicles')).data,
  })

  const inspections = useQuery({
    queryKey: ['inspections', vehicleFilter, kindFilter],
    queryFn: async () => {
      const { data } = await api.get<Inspection[]>('/inspections', {
        params: {
          ...(vehicleFilter ? { vehicle_id: vehicleFilter } : {}),
          ...(kindFilter ? { kind: kindFilter } : {}),
        },
      })
      return data
    },
  })

  // `GET /inspections` (InspectionOut) não traz o número de fotos — só o detalhe traz.
  // Buscamos o detalhe de cada linha usando a MESMA queryKey da tela de detalhe: além da
  // contagem, isso deixa a vistoria em cache, e abrir a linha fica instantâneo.
  const details = useQueries({
    queries: (inspections.data ?? []).map((inspection) => ({
      queryKey: inspectionKey(inspection.id),
      queryFn: async () =>
        (await api.get<InspectionDetail>(`/inspections/${inspection.id}`)).data,
    })),
  })

  const photoCount = new Map<string, number>()
  for (const detail of details) {
    if (detail.data) photoCount.set(detail.data.id, detail.data.photos.length)
  }

  return (
    <>
      <PageHeader
        title="Vistorias"
        subtitle="Checklist e fotos na entrega, na devolução e nas conferências periódicas."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            Nova vistoria
          </Button>
        }
      />

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
          <Field label="Filtrar por tipo">
            <Select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
              <option value="">Todos os tipos</option>
              <option value="entrega">Entrega</option>
              <option value="devolucao">Devolução</option>
              <option value="periodica">Periódica</option>
            </Select>
          </Field>
        </div>
      </Card>

      {inspections.isPending ? (
        <Spinner />
      ) : inspections.isError ? (
        <ErrorBox message={errorMessage(inspections.error)} />
      ) : !inspections.data.length ? (
        <EmptyState
          message={
            vehicleFilter || kindFilter
              ? 'Nenhuma vistoria com esses filtros.'
              : 'Nenhuma vistoria registrada ainda.'
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Veículo</Th>
              <Th>Motorista</Th>
              <Th>Tipo</Th>
              <Th>Data</Th>
              <Th className="text-right">KM</Th>
              <Th className="text-right">Fotos</Th>
            </tr>
          </thead>
          <tbody>
            {inspections.data.map((inspection) => (
              <InspectionRow
                key={inspection.id}
                inspection={inspection}
                photos={photoCount.get(inspection.id)}
              />
            ))}
          </tbody>
        </Table>
      )}

      <NewInspectionModal open={creating} onClose={() => setCreating(false)} />
    </>
  )
}

function InspectionRow({ inspection, photos }: { inspection: Inspection; photos?: number }) {
  const navigate = useNavigate()
  const to = `/vistorias/${inspection.id}`

  return (
    <tr
      className="cursor-pointer hover:bg-slate-50"
      onClick={() => navigate(to)}
      title="Abrir a vistoria"
    >
      <Td>
        {/* O <Link> mantém a linha acessível pelo teclado — um <tr> clicável, sozinho, não é. */}
        <Link
          to={to}
          onClick={(e) => e.stopPropagation()}
          className="font-mono text-xs text-brand-700 hover:underline"
        >
          {inspection.code}
        </Link>
      </Td>
      <Td>
        <div className="font-medium text-slate-800">{inspection.vehicle.plate}</div>
        <div className="text-xs text-slate-500">
          {inspection.vehicle.brand} {inspection.vehicle.model}
        </div>
      </Td>
      <Td className="text-slate-600">{inspection.driver?.full_name ?? '—'}</Td>
      <Td>
        <Badge {...INSPECTION_KIND[inspection.kind]} />
      </Td>
      <Td className="whitespace-nowrap">{formatDateTime(inspection.inspected_at)}</Td>
      <Td className="text-right whitespace-nowrap text-slate-600">
        {formatNumber(inspection.odometer)} km
      </Td>
      <Td className="text-right">
        <span className="inline-flex items-center justify-end gap-1.5 text-slate-600">
          <Camera size={14} className="text-slate-400" />
          {photos === undefined ? (
            <Loader2 size={12} className="animate-spin text-slate-300" />
          ) : (
            formatNumber(photos)
          )}
        </span>
      </Td>
    </tr>
  )
}

/* ------------------------------------------------------------------ nova vistoria */

const schema = z.object({
  vehicle_id: z.string().min(1, 'Selecione o veículo.'),
  driver_id: z.string(),
  contract_id: z.string(),
  kind: z.enum(['entrega', 'devolucao', 'periodica']),
  odometer: z.string().min(1, 'Informe o odômetro.').regex(/^\d{1,9}$/, 'Somente números.'),
  fuel_level: z.string(),
  notes: z.string().trim().max(1000, 'Máximo de 1000 caracteres.'),
})

type FormValues = z.infer<typeof schema>

function NewInspectionModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const vehicles = useQuery({
    queryKey: ['vehicles', 'select'],
    queryFn: async () => (await api.get<VehicleOption[]>('/vehicles')).data,
  })
  const drivers = useQuery({
    queryKey: ['drivers', 'select'],
    queryFn: async () => (await api.get<DriverOption[]>('/drivers')).data,
  })
  const contracts = useQuery({
    queryKey: ['contracts', 'select'],
    queryFn: async () => (await api.get<ContractOption[]>('/contracts')).data,
  })

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      vehicle_id: '',
      driver_id: '',
      contract_id: '',
      kind: 'entrega',
      odometer: '',
      fuel_level: '100',
      notes: '',
    },
  })

  const selectedVehicle = watch('vehicle_id')
  const fuelLevel = watch('fuel_level')

  // Contrato de outro carro numa vistoria não faz sentido — some da lista.
  const contractOptions = (contracts.data ?? []).filter(
    (contract) => !selectedVehicle || contract.vehicle_id === selectedVehicle,
  )

  const create = useMutation({
    mutationFn: async (values: FormValues) => {
      const { data } = await api.post<InspectionDetail>('/inspections', {
        vehicle_id: values.vehicle_id,
        driver_id: values.driver_id || null,
        contract_id: values.contract_id || null,
        kind: values.kind,
        odometer: Number(values.odometer),
        fuel_level: Number(values.fuel_level),
        notes: values.notes || null,
        // `items` vazio: o backend já nasce com o checklist inteiro em "ok".
      })
      return data
    },
    onSuccess: (inspection) => {
      queryClient.invalidateQueries({ queryKey: ['inspections'] })
      // O odômetro da vistoria pode ter empurrado o KM do veículo para frente.
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      reset()
      onClose()
      // O trabalho de verdade é lá: marcar o checklist e subir as fotos.
      navigate(`/vistorias/${inspection.id}`)
    },
  })

  function close() {
    if (create.isPending) return
    create.reset()
    reset()
    onClose()
  }

  return (
    <Modal open={open} onClose={close} title="Nova vistoria" wide>
      <form onSubmit={handleSubmit((values) => create.mutate(values))} className="space-y-4">
        <p className="text-sm text-slate-500">
          A vistoria nasce com o <strong>checklist inteiro marcado como “ok”</strong>. Na tela
          seguinte você marca só o que estiver errado e sobe as fotos.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Veículo" required error={errors.vehicle_id?.message}>
            <Select {...register('vehicle_id')}>
              <option value="">Selecione…</option>
              {vehicles.data?.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicle.plate} — {vehicle.brand} {vehicle.model}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Motorista" error={errors.driver_id?.message}>
            <Select {...register('driver_id')}>
              <option value="">Sem motorista</option>
              {drivers.data?.map((driver) => (
                <option key={driver.id} value={driver.id}>
                  {driver.full_name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Contrato"
            error={errors.contract_id?.message}
            hint={selectedVehicle ? undefined : 'Escolha o veículo para ver os contratos dele.'}
          >
            <Select {...register('contract_id')}>
              <option value="">Sem contrato</option>
              {contractOptions.map((contract) => (
                <option key={contract.id} value={contract.id}>
                  {contract.code}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Tipo" required error={errors.kind?.message}>
            <Select {...register('kind')}>
              <option value="entrega">Entrega</option>
              <option value="devolucao">Devolução</option>
              <option value="periodica">Periódica</option>
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Odômetro (km)"
            required
            error={errors.odometer?.message}
            hint="O KM do veículo só anda para frente."
          >
            <Input type="number" min="0" step="1" placeholder="45000" {...register('odometer')} />
          </Field>

          <Field label={`Nível de combustível — ${fuelLevel}%`}>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              className="mt-2 w-full accent-brand-600"
              {...register('fuel_level')}
            />
            <div className="mt-1 flex justify-between text-xs text-slate-400">
              <span>Vazio</span>
              <span>Cheio</span>
            </div>
          </Field>
        </div>

        <Field label="Observações" error={errors.notes?.message}>
          <Textarea placeholder="Carro entregue limpo, sem avarias aparentes." {...register('notes')} />
        </Field>

        {create.isError && <ErrorBox message={errorMessage(create.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={close} disabled={create.isPending}>
            Cancelar
          </Button>
          <Button type="submit" loading={create.isPending}>
            Criar e abrir checklist
          </Button>
        </div>
      </form>
    </Modal>
  )
}
