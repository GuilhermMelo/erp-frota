import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Search, Trash2, TriangleAlert } from 'lucide-react'
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
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from '../../components/ui'
import { formatDate, today } from '../../lib/format'

/* ---------------------------------------------------------------- tipos */

type DriverStatus = 'active' | 'inactive' | 'blocked'

type Driver = {
  id: string
  code: string
  full_name: string
  cpf: string
  rg: string | null
  cnh_number: string | null
  cnh_category: string | null
  cnh_expiry: string | null
  phone: string | null
  email: string | null
  address_street: string | null
  address_number: string | null
  address_city: string | null
  address_state: string | null
  address_zip: string | null
  status: DriverStatus
}

const DRIVER_STATUS: Record<DriverStatus, { label: string; className: string }> = {
  active: { label: 'Ativo', className: 'bg-emerald-100 text-emerald-800' },
  inactive: { label: 'Inativo', className: 'bg-slate-100 text-slate-500' },
  blocked: { label: 'Bloqueado', className: 'bg-red-100 text-red-800' },
}

/* ---------------------------------------------------------------- CPF */

const onlyDigits = (value: string) => value.replace(/\D/g, '')

/** `12345678901` → `123.456.789-01`. O banco guarda só os dígitos; a pontuação é da tela. */
function formatCpf(cpf: string): string {
  const d = onlyDigits(cpf)
  if (d.length !== 11) return cpf
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`
}

/** Máscara progressiva enquanto o operador digita. */
function maskCpf(value: string): string {
  const d = onlyDigits(value).slice(0, 11)
  let out = d.slice(0, 3)
  if (d.length > 3) out += `.${d.slice(3, 6)}`
  if (d.length > 6) out += `.${d.slice(6, 9)}`
  if (d.length > 9) out += `-${d.slice(9)}`
  return out
}

/** CNH vencida é problema real: o motorista não pode rodar e o carro fica parado. */
function isCnhExpired(expiry: string | null): boolean {
  // Datas da API vêm como "YYYY-MM-DD" — comparar como texto já ordena certo.
  return !!expiry && expiry < today()
}

/* ---------------------------------------------------------------- formulário */

const emailFormat = z.email()

const driverSchema = z.object({
  full_name: z.string().refine((v) => v.trim().length >= 2, 'Informe o nome completo.'),
  cpf: z.string().refine((v) => onlyDigits(v).length === 11, 'O CPF deve ter 11 dígitos.'),
  rg: z.string(),
  cnh_number: z.string(),
  cnh_category: z.string(),
  cnh_expiry: z.string(),
  phone: z.string(),
  email: z
    .string()
    .refine((v) => v.trim() === '' || emailFormat.safeParse(v.trim()).success, 'E-mail inválido.'),
  address_street: z.string(),
  address_number: z.string(),
  address_city: z.string(),
  address_state: z
    .string()
    .refine((v) => v.trim() === '' || v.trim().length === 2, 'Use a sigla de 2 letras (ex.: SP).'),
  address_zip: z.string(),
  status: z.enum(['active', 'inactive', 'blocked']),
})

type DriverForm = z.infer<typeof driverSchema>

const EMPTY_FORM: DriverForm = {
  full_name: '',
  cpf: '',
  rg: '',
  cnh_number: '',
  cnh_category: '',
  cnh_expiry: '',
  phone: '',
  email: '',
  address_street: '',
  address_number: '',
  address_city: '',
  address_state: '',
  address_zip: '',
  status: 'active',
}

function toForm(driver: Driver): DriverForm {
  return {
    full_name: driver.full_name,
    cpf: formatCpf(driver.cpf),
    rg: driver.rg ?? '',
    cnh_number: driver.cnh_number ?? '',
    cnh_category: driver.cnh_category ?? '',
    cnh_expiry: driver.cnh_expiry ?? '',
    phone: driver.phone ?? '',
    email: driver.email ?? '',
    address_street: driver.address_street ?? '',
    address_number: driver.address_number ?? '',
    address_city: driver.address_city ?? '',
    address_state: driver.address_state ?? '',
    address_zip: driver.address_zip ?? '',
    status: driver.status,
  }
}

/** Campo de texto vazio vira `null` — o banco distingue "não informado" de "string vazia". */
const orNull = (value: string) => {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function toPayload(form: DriverForm) {
  return {
    full_name: form.full_name.trim(),
    cpf: onlyDigits(form.cpf),
    rg: orNull(form.rg),
    cnh_number: orNull(form.cnh_number),
    cnh_category: orNull(form.cnh_category)?.toUpperCase() ?? null,
    cnh_expiry: orNull(form.cnh_expiry),
    phone: orNull(form.phone),
    email: orNull(form.email),
    address_street: orNull(form.address_street),
    address_number: orNull(form.address_number),
    address_city: orNull(form.address_city),
    address_state: orNull(form.address_state)?.toUpperCase() ?? null,
    address_zip: orNull(form.address_zip),
    status: form.status,
  }
}

/* ---------------------------------------------------------------- página */

export function DriversPage() {
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')

  const [editing, setEditing] = useState<Driver | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [deleting, setDeleting] = useState<Driver | null>(null)

  const params = {
    q: search.trim() || undefined,
    status: status || undefined,
  }

  const driversQuery = useQuery({
    queryKey: ['drivers', params],
    queryFn: async () => (await api.get<Driver[]>('/drivers', { params })).data,
    placeholderData: (previous) => previous,
  })

  const deleteMutation = useMutation({
    mutationFn: (driver: Driver) => api.delete(`/drivers/${driver.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drivers'] })
      setDeleting(null)
    },
  })

  function openNew() {
    setEditing(null)
    setFormOpen(true)
  }

  function openEdit(driver: Driver) {
    setEditing(driver)
    setFormOpen(true)
  }

  const drivers = driversQuery.data ?? []

  return (
    <div>
      <PageHeader
        title="Motoristas"
        subtitle="Quem dirige os carros. Motorista é dado, não usuário: ele não tem login."
        action={
          <Button onClick={openNew}>
            <Plus size={16} />
            Novo motorista
          </Button>
        }
      />

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-60 flex-1">
            <Field label="Buscar">
              <div className="relative">
                <Search
                  size={16}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400"
                />
                <Input
                  className="pl-9"
                  placeholder="Nome, CPF, código ou telefone"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </Field>
          </div>
          <div className="w-48">
            <Field label="Situação">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Todas</option>
                {Object.entries(DRIVER_STATUS).map(([value, { label }]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>
      </Card>

      {driversQuery.isPending ? (
        <Spinner />
      ) : driversQuery.isError ? (
        <ErrorBox message={errorMessage(driversQuery.error)} />
      ) : drivers.length === 0 ? (
        <EmptyState message="Nenhum motorista encontrado." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Nome</Th>
              <Th>CPF</Th>
              <Th>Telefone</Th>
              <Th>CNH</Th>
              <Th>Validade da CNH</Th>
              <Th>Situação</Th>
              <Th className="text-right">Ações</Th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => {
              const expired = isCnhExpired(driver.cnh_expiry)
              return (
                <tr key={driver.id} className="hover:bg-slate-50">
                  <Td className="font-mono text-xs text-slate-500">{driver.code}</Td>
                  <Td className="font-medium text-slate-900">{driver.full_name}</Td>
                  <Td className="tabular-nums">{formatCpf(driver.cpf)}</Td>
                  <Td>{driver.phone ?? '—'}</Td>
                  <Td>
                    {driver.cnh_number ? (
                      <span>
                        {driver.cnh_number}
                        {driver.cnh_category && (
                          <span className="ml-1 text-slate-500">({driver.cnh_category})</span>
                        )}
                      </span>
                    ) : (
                      '—'
                    )}
                  </Td>
                  <Td>
                    {driver.cnh_expiry ? (
                      <span
                        className={
                          expired ? 'flex items-center gap-1.5 font-semibold text-red-600' : ''
                        }
                      >
                        {expired && <TriangleAlert size={14} className="shrink-0" />}
                        {formatDate(driver.cnh_expiry)}
                        {expired && (
                          <Badge label="Vencida" className="bg-red-100 text-red-800" />
                        )}
                      </span>
                    ) : (
                      '—'
                    )}
                  </Td>
                  <Td>
                    <Badge
                      label={DRIVER_STATUS[driver.status].label}
                      className={DRIVER_STATUS[driver.status].className}
                    />
                  </Td>
                  <Td className="text-right whitespace-nowrap">
                    <Button variant="ghost" onClick={() => openEdit(driver)} title="Editar">
                      <Pencil size={16} />
                    </Button>
                    <Button
                      variant="ghost"
                      className="text-red-600 hover:bg-red-50"
                      onClick={() => setDeleting(driver)}
                      title="Excluir"
                    >
                      <Trash2 size={16} />
                    </Button>
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      {formOpen && (
        <DriverFormModal driver={editing} onClose={() => setFormOpen(false)} />
      )}

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title="Excluir motorista"
      >
        <p className="text-sm text-slate-600">
          Excluir <strong>{deleting?.full_name}</strong>? Ele some da lista, mas continua nos
          contratos, receitas e multas já lançados — o histórico financeiro não muda.
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

/* ---------------------------------------------------------------- modal do formulário */

function DriverFormModal({ driver, onClose }: { driver: Driver | null; onClose: () => void }) {
  const queryClient = useQueryClient()

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<DriverForm>({
    resolver: zodResolver(driverSchema),
    defaultValues: driver ? toForm(driver) : EMPTY_FORM,
  })

  const mutation = useMutation({
    mutationFn: (form: DriverForm) =>
      driver
        ? api.patch(`/drivers/${driver.id}`, toPayload(form))
        : api.post('/drivers', toPayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drivers'] })
      onClose()
    },
  })

  const cpf = watch('cpf')
  const cnhExpiry = watch('cnh_expiry')

  return (
    <Modal
      open
      onClose={onClose}
      title={driver ? `Editar ${driver.code}` : 'Novo motorista'}
      wide
    >
      <form onSubmit={handleSubmit((form) => mutation.mutate(form))} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Nome completo" required error={errors.full_name?.message}>
              <Input autoFocus {...register('full_name')} />
            </Field>
          </div>

          <Field label="CPF" required error={errors.cpf?.message}>
            <Input
              inputMode="numeric"
              placeholder="000.000.000-00"
              value={cpf}
              onChange={(e) => setValue('cpf', maskCpf(e.target.value), { shouldValidate: true })}
            />
          </Field>

          <Field label="RG" error={errors.rg?.message}>
            <Input {...register('rg')} />
          </Field>

          <Field label="Número da CNH" error={errors.cnh_number?.message}>
            <Input inputMode="numeric" {...register('cnh_number')} />
          </Field>

          <Field label="Categoria da CNH" error={errors.cnh_category?.message}>
            <Select {...register('cnh_category')}>
              <option value="">—</option>
              {['A', 'B', 'AB', 'C', 'D', 'E', 'AC', 'AD', 'AE'].map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Validade da CNH"
            error={errors.cnh_expiry?.message}
            hint={
              isCnhExpired(cnhExpiry)
                ? undefined
                : 'CNH vencida trava o motorista — o carro fica parado.'
            }
          >
            <Input type="date" {...register('cnh_expiry')} />
            {isCnhExpired(cnhExpiry) && (
              <span className="mt-1 flex items-center gap-1 text-xs font-semibold text-red-600">
                <TriangleAlert size={13} />
                Esta CNH está vencida.
              </span>
            )}
          </Field>

          <Field label="Situação" required error={errors.status?.message}>
            <Select {...register('status')}>
              {Object.entries(DRIVER_STATUS).map(([value, { label }]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Telefone" error={errors.phone?.message}>
            <Input inputMode="tel" placeholder="11999998888" {...register('phone')} />
          </Field>

          <Field label="E-mail" error={errors.email?.message}>
            <Input type="email" {...register('email')} />
          </Field>
        </div>

        <fieldset className="rounded-lg border border-slate-200 p-4">
          <legend className="px-1 text-sm font-medium text-slate-700">Endereço</legend>
          <div className="grid gap-4 sm:grid-cols-6">
            <div className="sm:col-span-4">
              <Field label="Rua" error={errors.address_street?.message}>
                <Input {...register('address_street')} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Número" error={errors.address_number?.message}>
                <Input {...register('address_number')} />
              </Field>
            </div>
            <div className="sm:col-span-3">
              <Field label="Cidade" error={errors.address_city?.message}>
                <Input {...register('address_city')} />
              </Field>
            </div>
            <div className="sm:col-span-1">
              <Field label="UF" error={errors.address_state?.message}>
                <Input maxLength={2} placeholder="SP" {...register('address_state')} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="CEP" error={errors.address_zip?.message}>
                <Input maxLength={9} placeholder="00000-000" {...register('address_zip')} />
              </Field>
            </div>
          </div>
        </fieldset>

        {mutation.isError && <ErrorBox message={errorMessage(mutation.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {driver ? 'Salvar' : 'Cadastrar'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
