import { useEffect, useMemo, useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

import { api, errorMessage } from '../../api/client'
import {
  Badge,
  Button,
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
import { VEHICLE_STATUS, formatMoney, formatNumber, moneyClass, today } from '../../lib/format'
import { FUEL_TYPES, type Vehicle, type VehicleResult } from './types'

/* ---------------------------------------------------------------- formulário */

/** Dinheiro fica STRING do formulário até a API — nunca vira float (CLAUDE.md, regra 1). */
const moneyField = (label: string) =>
  z
    .string()
    .min(1, `Informe ${label}.`)
    .refine((v) => /^\d+([.,]\d{1,2})?$/.test(v.trim()), 'Valor inválido. Use até 2 casas decimais.')

const intField = (label: string, min: number, max: number) =>
  z
    .string()
    .min(1, `Informe ${label}.`)
    .refine((v) => {
      const n = Number(v)
      return Number.isInteger(n) && n >= min && n <= max
    }, `Valor inválido (entre ${min} e ${max}).`)

const vehicleSchema = z
  .object({
    plate: z
      .string()
      .refine(
        (v) => {
          const clean = v.replace(/[^A-Za-z0-9]/g, '')
          return clean.length >= 7 && clean.length <= 8
        },
        'A placa deve ter 7 caracteres (ex.: ABC1D23 ou ABC1234).',
      ),
    brand: z.string().trim().min(1, 'Informe a marca.').max(60),
    model: z.string().trim().min(1, 'Informe o modelo.').max(60),
    version: z.string().trim().max(80).optional(),
    manufacture_year: intField('o ano de fabricação', 1900, 2100),
    model_year: intField('o ano do modelo', 1900, 2100),
    color: z.string().trim().max(30).optional(),
    fuel_type: z.enum(['flex', 'gasolina', 'etanol', 'diesel', 'gnv', 'hibrido', 'eletrico']),
    renavam: z.string().trim().max(20).optional(),
    chassi: z.string().trim().max(30).optional(),

    // Os campos de compra são obrigatórios: é deles que sai o lucro do carro.
    purchase_date: z.string().min(1, 'Informe a data de compra.'),
    purchase_price: moneyField('o valor de compra'),
    purchase_odometer: intField('o odômetro de compra', 0, 9_999_999),
    current_odometer: intField('o odômetro atual', 0, 9_999_999),
  })
  .refine((v) => Number(v.current_odometer) >= Number(v.purchase_odometer), {
    // Odômetro só anda para frente. Ao contrário, `km_driven` fica negativo e o custo por km
    // some da tela (a API devolve NULL) sem o operador entender por quê.
    path: ['current_odometer'],
    message: 'O odômetro atual não pode ser menor que o de compra.',
  })

type VehicleForm = z.infer<typeof vehicleSchema>

/** "" → null: RENAVAM e chassi são UNIQUE no banco; string vazia colidiria no 2º veículo. */
const nullIfEmpty = (v: string | undefined) => (v && v.trim() ? v.trim() : null)

function toPayload(v: VehicleForm) {
  return {
    plate: v.plate.replace(/[^A-Za-z0-9]/g, '').toUpperCase(),
    brand: v.brand.trim(),
    model: v.model.trim(),
    version: nullIfEmpty(v.version),
    manufacture_year: Number(v.manufacture_year),
    model_year: Number(v.model_year),
    color: nullIfEmpty(v.color),
    fuel_type: v.fuel_type,
    renavam: nullIfEmpty(v.renavam),
    chassi: nullIfEmpty(v.chassi),
    purchase_date: v.purchase_date,
    // Dinheiro segue como STRING. `Number()` aqui seria bug de dinheiro.
    purchase_price: v.purchase_price.trim().replace(',', '.'),
    purchase_odometer: Number(v.purchase_odometer),
    current_odometer: Number(v.current_odometer),
  }
}

const EMPTY: VehicleForm = {
  plate: '',
  brand: '',
  model: '',
  version: '',
  manufacture_year: '',
  model_year: '',
  color: '',
  fuel_type: 'flex',
  renavam: '',
  chassi: '',
  purchase_date: today(),
  purchase_price: '',
  purchase_odometer: '0',
  current_odometer: '0',
}

function NewVehicleModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<VehicleForm>({ resolver: zodResolver(vehicleSchema), defaultValues: EMPTY })

  const create = useMutation({
    mutationFn: (values: VehicleForm) =>
      api.post<Vehicle>('/vehicles', toPayload(values)).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      reset(EMPTY)
      onClose()
    },
  })

  function close() {
    create.reset()
    reset(EMPTY)
    onClose()
  }

  return (
    <Modal open={open} onClose={close} title="Novo veículo" wide>
      <form onSubmit={handleSubmit((v) => create.mutate(v))} className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Placa" error={errors.plate?.message} required>
            <Input placeholder="ABC1D23" {...register('plate')} />
          </Field>
          <Field label="Marca" error={errors.brand?.message} required>
            <Input placeholder="Fiat" {...register('brand')} />
          </Field>
          <Field label="Modelo" error={errors.model?.message} required>
            <Input placeholder="Cronos" {...register('model')} />
          </Field>

          <Field label="Versão" error={errors.version?.message}>
            <Input placeholder="1.3 Drive" {...register('version')} />
          </Field>
          <Field label="Ano de fabricação" error={errors.manufacture_year?.message} required>
            <Input type="number" placeholder="2023" {...register('manufacture_year')} />
          </Field>
          <Field label="Ano do modelo" error={errors.model_year?.message} required>
            <Input type="number" placeholder="2024" {...register('model_year')} />
          </Field>

          <Field label="Cor" error={errors.color?.message}>
            <Input placeholder="Prata" {...register('color')} />
          </Field>
          <Field label="Combustível" error={errors.fuel_type?.message} required>
            <Select {...register('fuel_type')}>
              {Object.entries(FUEL_TYPES).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="RENAVAM" error={errors.renavam?.message}>
            <Input {...register('renavam')} />
          </Field>

          <Field label="Chassi" error={errors.chassi?.message}>
            <Input {...register('chassi')} />
          </Field>
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <h3 className="mb-1 text-sm font-semibold text-slate-800">Compra</h3>
          <p className="mb-4 text-xs text-slate-500">
            É daqui que sai o lucro do carro: sem o valor de compra, a conta do veículo não fecha.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Data da compra" error={errors.purchase_date?.message} required>
              <Input type="date" {...register('purchase_date')} />
            </Field>
            <Field label="Valor de compra" error={errors.purchase_price?.message} required>
              <MoneyInput placeholder="50000,00" {...register('purchase_price')} />
            </Field>
            <Field
              label="Odômetro na compra (km)"
              error={errors.purchase_odometer?.message}
              required
            >
              <Input type="number" {...register('purchase_odometer')} />
            </Field>
            <Field label="Odômetro atual (km)" error={errors.current_odometer?.message} required>
              <Input type="number" {...register('current_odometer')} />
            </Field>
          </div>
        </div>

        {create.isError && <ErrorBox message={errorMessage(create.error)} />}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" loading={create.isPending}>
            Cadastrar veículo
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- lista */

export function VehiclesPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(false)

  const q = params.get('q') ?? ''
  const status = params.get('status') ?? ''
  const [search, setSearch] = useState(q)

  // Debounce: sem isso a API leva um request por tecla digitada.
  useEffect(() => {
    if (search === q) return
    const timer = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (search.trim()) next.set('q', search.trim())
          else next.delete('q')
          return next
        },
        { replace: true },
      )
    }, 300)
    return () => clearTimeout(timer)
  }, [search, q, setParams])

  const vehicles = useQuery({
    queryKey: ['vehicles', { q, status }],
    queryFn: () =>
      api
        .get<Vehicle[]>('/vehicles', {
          params: { q: q || undefined, status: status || undefined },
        })
        .then((r) => r.data),
  })

  // O lucro de cada carro já vem pronto do backend — o frontend só cruza pelo vehicle_id.
  const fleet = useQuery({
    queryKey: ['finance', 'fleet'],
    queryFn: () => api.get<VehicleResult[]>('/finance/fleet').then((r) => r.data),
  })

  const profitByVehicle = useMemo(() => {
    const map = new Map<string, VehicleResult>()
    for (const row of fleet.data ?? []) map.set(row.vehicle_id, row)
    return map
  }, [fleet.data])

  function changeStatus(value: string) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set('status', value)
        else next.delete('status')
        return next
      },
      { replace: true },
    )
  }

  return (
    <>
      <PageHeader
        title="Veículos"
        subtitle="A frota e o lucro de cada carro."
        action={
          <Button onClick={() => setModalOpen(true)}>
            <Plus size={16} />
            Novo veículo
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-64 flex-1">
          <Search
            size={16}
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400"
          />
          <Input
            className="pl-9"
            placeholder="Buscar por placa, marca, modelo ou código…"
            aria-label="Buscar veículo"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          className="w-48"
          aria-label="Filtrar por status"
          value={status}
          onChange={(e) => changeStatus(e.target.value)}
        >
          <option value="">Todos os status</option>
          {Object.entries(VEHICLE_STATUS).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {fleet.isError && (
        <div className="mb-4">
          <ErrorBox message={`Não foi possível carregar o lucro da frota. ${errorMessage(fleet.error)}`} />
        </div>
      )}

      {vehicles.isPending ? (
        <Spinner />
      ) : vehicles.isError ? (
        <ErrorBox message={errorMessage(vehicles.error)} />
      ) : vehicles.data.length === 0 ? (
        <EmptyState
          message={
            q || status
              ? 'Nenhum veículo encontrado com esse filtro.'
              : 'Nenhum veículo cadastrado. Comece cadastrando o primeiro carro da frota.'
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Placa</Th>
              <Th>Marca / Modelo</Th>
              <Th>Ano</Th>
              <Th className="text-right">KM atual</Th>
              <Th>Status</Th>
              <Th className="text-right">Lucro atual</Th>
            </tr>
          </thead>
          <tbody>
            {vehicles.data.map((vehicle) => {
              const result = profitByVehicle.get(vehicle.id)
              const badge = VEHICLE_STATUS[vehicle.status]
              return (
                <tr
                  key={vehicle.id}
                  onClick={() => navigate(`/veiculos/${vehicle.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') navigate(`/veiculos/${vehicle.id}`)
                  }}
                  tabIndex={0}
                  role="link"
                  className="cursor-pointer hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                >
                  <Td className="font-mono text-xs text-slate-500">{vehicle.code}</Td>
                  <Td className="font-medium text-slate-900">{vehicle.plate}</Td>
                  <Td>
                    {vehicle.brand} {vehicle.model}
                    {vehicle.version && (
                      <span className="text-slate-500"> · {vehicle.version}</span>
                    )}
                  </Td>
                  <Td className="text-slate-600">
                    {vehicle.manufacture_year}/{vehicle.model_year}
                  </Td>
                  <Td className="text-right text-slate-600">
                    {formatNumber(vehicle.current_odometer)}
                  </Td>
                  <Td>
                    <Badge
                      label={badge?.label ?? vehicle.status}
                      className={badge?.className ?? 'bg-slate-100 text-slate-500'}
                    />
                  </Td>
                  <Td className={`text-right font-semibold ${moneyClass(result?.profit)}`}>
                    {formatMoney(result?.profit)}
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      <NewVehicleModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  )
}
