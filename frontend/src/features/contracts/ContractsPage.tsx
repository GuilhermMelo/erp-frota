import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, Download, Info, Paperclip, Plus, Upload } from 'lucide-react'
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

type ContractStatus = 'active' | 'finished' | 'canceled'

type Contract = {
  id: string
  code: string
  vehicle_id: string
  driver_id: string
  start_date: string
  end_date: string | null
  weekly_amount: string
  billing_weekday: number
  deposit_amount: string
  deposit_status: 'held' | 'settled'
  deposit_returned_amount: string
  status: ContractStatus
  notes: string | null
  vehicle: { id: string; code: string; plate: string; brand: string; model: string } | null
  driver: { id: string; code: string; full_name: string } | null
}

type Vehicle = { id: string; code: string; plate: string; brand: string; model: string }
type Driver = { id: string; code: string; full_name: string; status: string }

type Attachment = {
  id: string
  kind: string
  original_filename: string | null
  size_bytes: number
  created_at: string
}

const CONTRACT_STATUS: Record<ContractStatus, { label: string; className: string }> = {
  active: { label: 'Ativo', className: 'bg-emerald-100 text-emerald-800' },
  finished: { label: 'Encerrado', className: 'bg-slate-200 text-slate-700' },
  canceled: { label: 'Cancelado', className: 'bg-slate-100 text-slate-500' },
}

// 0 = segunda ... 6 = domingo (igual ao `date.weekday()` do Python, que o backend usa).
const WEEKDAYS = [
  'Segunda-feira',
  'Terça-feira',
  'Quarta-feira',
  'Quinta-feira',
  'Sexta-feira',
  'Sábado',
  'Domingo',
]

/** Só os `kind` que fazem sentido para um contrato. */
const DOCUMENT_KINDS: Record<string, string> = {
  contrato_pdf: 'Contrato assinado (PDF)',
  confissao_divida: 'Confissão de dívida',
  assinatura: 'Assinatura',
}

/* ---------------------------------------------------------------- dinheiro (prévia) */

/**
 * Dinheiro vem da API como STRING ("2000.00") porque é `Decimal` no backend.
 *
 * As duas funções abaixo existem SÓ para a prévia do acerto da caução na tela, e fazem a
 * conta em CENTAVOS INTEIROS — nunca em float, que é bug de dinheiro (CLAUDE.md, regra 1).
 * O número que VALE é o que o backend calcula em `Decimal` no POST /contracts/{id}/finish;
 * aqui só mostramos ao operador o que vai acontecer antes de ele confirmar.
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

/* ---------------------------------------------------------------- página */

export function ContractsPage() {
  const [status, setStatus] = useState('')
  const [creating, setCreating] = useState(false)
  const [finishing, setFinishing] = useState<Contract | null>(null)
  const [attaching, setAttaching] = useState<Contract | null>(null)

  const params = { status: status || undefined }

  const contractsQuery = useQuery({
    queryKey: ['contracts', params],
    queryFn: async () => (await api.get<Contract[]>('/contracts', { params })).data,
    placeholderData: (previous) => previous,
  })

  const contracts = contractsQuery.data ?? []

  return (
    <div>
      <PageHeader
        title="Contratos"
        subtitle="Um carro, um motorista, um valor semanal. As cobranças da semana são geradas sozinhas."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} />
            Novo contrato
          </Button>
        }
      />

      <Card className="mb-4">
        <div className="w-56">
          <Field label="Situação">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Todos</option>
              {Object.entries(CONTRACT_STATUS).map(([value, { label }]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      {contractsQuery.isPending ? (
        <Spinner />
      ) : contractsQuery.isError ? (
        <ErrorBox message={errorMessage(contractsQuery.error)} />
      ) : contracts.length === 0 ? (
        <EmptyState message="Nenhum contrato encontrado." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Veículo</Th>
              <Th>Motorista</Th>
              <Th>Início</Th>
              <Th>Fim</Th>
              <Th className="text-right">Valor semanal</Th>
              <Th className="text-right">Caução</Th>
              <Th>Situação</Th>
              <Th className="text-right">Ações</Th>
            </tr>
          </thead>
          <tbody>
            {contracts.map((contract) => (
              <tr key={contract.id} className="hover:bg-slate-50">
                <Td className="font-mono text-xs text-slate-500">{contract.code}</Td>
                <Td>
                  <div className="font-medium text-slate-900">
                    {contract.vehicle?.plate ?? '—'}
                  </div>
                  <div className="text-xs text-slate-500">
                    {contract.vehicle ? `${contract.vehicle.brand} ${contract.vehicle.model}` : ''}
                  </div>
                </Td>
                <Td>{contract.driver?.full_name ?? '—'}</Td>
                <Td className="whitespace-nowrap">{formatDate(contract.start_date)}</Td>
                <Td className="whitespace-nowrap">{formatDate(contract.end_date)}</Td>
                <Td className="text-right font-medium tabular-nums whitespace-nowrap">
                  {formatMoney(contract.weekly_amount)}
                  <div className="text-xs font-normal text-slate-500">
                    vence {WEEKDAYS[contract.billing_weekday]?.toLowerCase()}
                  </div>
                </Td>
                <Td className="text-right tabular-nums whitespace-nowrap">
                  {formatMoney(contract.deposit_amount)}
                  {contract.deposit_status === 'held' ? (
                    <div className="text-xs text-slate-500">em seu poder</div>
                  ) : (
                    <div className="text-xs text-slate-500">
                      devolvido {formatMoney(contract.deposit_returned_amount)}
                    </div>
                  )}
                </Td>
                <Td>
                  <Badge
                    label={CONTRACT_STATUS[contract.status].label}
                    className={CONTRACT_STATUS[contract.status].className}
                  />
                </Td>
                <Td className="text-right whitespace-nowrap">
                  <Button
                    variant="ghost"
                    title="Anexos do contrato"
                    onClick={() => setAttaching(contract)}
                  >
                    <Paperclip size={16} />
                  </Button>
                  {contract.status === 'active' && (
                    <Button variant="secondary" onClick={() => setFinishing(contract)}>
                      <Ban size={15} />
                      Encerrar
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <div className="mt-4 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
        <Info size={16} className="mt-0.5 shrink-0" />
        <span>
          <strong>A caução não é receita.</strong> É dinheiro do motorista que fica com você e
          volta para ele no fim. Ela não entra no lucro do carro — só a parte que você{' '}
          <strong>retiver</strong> no encerramento vira receita.
        </span>
      </div>

      {creating && <ContractFormModal onClose={() => setCreating(false)} />}
      {finishing && (
        <FinishContractModal contract={finishing} onClose={() => setFinishing(null)} />
      )}
      {attaching && (
        <AttachmentsModal contract={attaching} onClose={() => setAttaching(null)} />
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- novo contrato */

const contractSchema = z.object({
  vehicle_id: z.string().min(1, 'Escolha o veículo.'),
  driver_id: z.string().min(1, 'Escolha o motorista.'),
  start_date: z.string().min(1, 'Informe a data de início.'),
  weekly_amount: z
    .string()
    .refine((v) => (toCents(v) ?? 0) > 0, 'Informe o valor semanal (maior que zero).'),
  billing_weekday: z.string(),
  deposit_amount: z.string().refine((v) => toCents(v) !== null, 'Informe um valor válido.'),
  notes: z.string(),
})

type ContractForm = z.infer<typeof contractSchema>

function ContractFormModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()

  // Só os veículos DISPONÍVEIS: um carro alugado não pode entrar em um segundo contrato
  // (o banco tem um índice parcial que barra isso de qualquer jeito).
  const vehiclesQuery = useQuery({
    queryKey: ['vehicles', { status: 'available' }],
    queryFn: async () =>
      (await api.get<Vehicle[]>('/vehicles', { params: { status: 'available' } })).data,
  })

  const driversQuery = useQuery({
    queryKey: ['drivers', {}],
    queryFn: async () => (await api.get<Driver[]>('/drivers')).data,
  })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ContractForm>({
    resolver: zodResolver(contractSchema),
    defaultValues: {
      vehicle_id: '',
      driver_id: '',
      start_date: today(),
      weekly_amount: '',
      billing_weekday: '0',
      deposit_amount: '0',
      notes: '',
    },
  })

  const mutation = useMutation({
    mutationFn: (form: ContractForm) =>
      api.post('/contracts', {
        vehicle_id: form.vehicle_id,
        driver_id: form.driver_id,
        start_date: form.start_date,
        // Dinheiro vai como STRING: o backend recebe em `Decimal` sem passar por float.
        weekly_amount: form.weekly_amount.replace(',', '.'),
        billing_weekday: Number(form.billing_weekday),
        deposit_amount: form.deposit_amount.replace(',', '.'),
        notes: form.notes.trim() || null,
      }),
    onSuccess: () => {
      // O contrato já nasce gerando as cobranças vencidas e marcando o carro como alugado.
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['revenues'] })
      queryClient.invalidateQueries({ queryKey: ['receivables'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      onClose()
    },
  })

  const vehicles = vehiclesQuery.data ?? []
  const drivers = driversQuery.data ?? []

  return (
    <Modal open onClose={onClose} title="Novo contrato" wide>
      <form onSubmit={handleSubmit((form) => mutation.mutate(form))} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Veículo"
            required
            error={errors.vehicle_id?.message}
            hint="Só aparecem os carros disponíveis."
          >
            <Select {...register('vehicle_id')} disabled={vehiclesQuery.isPending}>
              <option value="">Selecione…</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate} — {v.brand} {v.model}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Motorista" required error={errors.driver_id?.message}>
            <Select {...register('driver_id')} disabled={driversQuery.isPending}>
              <option value="">Selecione…</option>
              {drivers.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.full_name}
                  {d.status !== 'active' ? ' (inativo/bloqueado)' : ''}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Data de início" required error={errors.start_date?.message}>
            <Input type="date" {...register('start_date')} />
          </Field>

          <Field label="Valor semanal" required error={errors.weekly_amount?.message}>
            <MoneyInput placeholder="800.00" {...register('weekly_amount')} />
          </Field>

          <Field
            label="Dia da cobrança"
            required
            error={errors.billing_weekday?.message}
            hint="Dia da semana em que a cobrança vence."
          >
            <Select {...register('billing_weekday')}>
              {WEEKDAYS.map((label, index) => (
                <option key={label} value={String(index)}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Valor da caução" error={errors.deposit_amount?.message}>
            <MoneyInput placeholder="0.00" {...register('deposit_amount')} />
          </Field>
        </div>

        {/* O ponto mais mal-entendido do sistema. Dizer isso ANTES evita o dono achar,
            depois, que o sistema "esqueceu" de contar a caução no lucro do carro. */}
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <Info size={16} className="mt-0.5 shrink-0" />
          <div>
            <strong>A caução não é receita — é dinheiro que você segura e devolve.</strong>
            <p className="mt-1">
              Ela não vai aparecer no lucro do veículo, e isso está certo: o dinheiro não é seu.
              Ela só vira receita se você <strong>retiver</strong> parte dela no encerramento do
              contrato (por avaria, semana em aberto, dívida).
            </p>
          </div>
        </div>

        <Field label="Observações" error={errors.notes?.message}>
          <Textarea {...register('notes')} />
        </Field>

        {mutation.isError && <ErrorBox message={errorMessage(mutation.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Criar contrato
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- encerrar contrato */

function FinishContractModal({
  contract,
  onClose,
}: {
  contract: Contract
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const depositCents = toCents(contract.deposit_amount) ?? 0

  const finishSchema = z
    .object({
      end_date: z.string().min(1, 'Informe a data de encerramento.'),
      deposit_returned_amount: z.string(),
      notes: z.string(),
    })
    .superRefine((form, ctx) => {
      if (form.end_date && form.end_date < contract.start_date) {
        ctx.addIssue({
          code: 'custom',
          path: ['end_date'],
          message: `O fim não pode ser antes do início (${formatDate(contract.start_date)}).`,
        })
      }

      const returned = toCents(form.deposit_returned_amount)
      if (returned === null) {
        ctx.addIssue({
          code: 'custom',
          path: ['deposit_returned_amount'],
          message: 'Informe um valor válido (0 ou mais).',
        })
        return
      }
      if (returned > depositCents) {
        ctx.addIssue({
          code: 'custom',
          path: ['deposit_returned_amount'],
          message: `Não pode passar da caução recebida (${formatMoney(contract.deposit_amount)}).`,
        })
      }
    })

  type FinishForm = z.infer<typeof finishSchema>

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FinishForm>({
    resolver: zodResolver(finishSchema),
    defaultValues: {
      end_date: today(),
      deposit_returned_amount: contract.deposit_amount,
      notes: '',
    },
  })

  const mutation = useMutation({
    mutationFn: (form: FinishForm) =>
      api.post(`/contracts/${contract.id}/finish`, {
        end_date: form.end_date,
        // STRING, sempre: quem faz a conta da caução em `Decimal` é o backend.
        deposit_returned_amount: form.deposit_returned_amount.trim().replace(',', '.') || '0',
        notes: form.notes.trim() || null,
      }),
    onSuccess: () => {
      // Encerrar gera a última cobrança, cancela as semanas futuras, libera o carro e —
      // se houve retenção — cria a receita `caucao_retida` já paga.
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['revenues'] })
      queryClient.invalidateQueries({ queryKey: ['receivables'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      onClose()
    },
  })

  // Prévia em centavos inteiros — ver o comentário em `toCents`. A conta que vale é a do backend.
  const returnedCents = toCents(watch('deposit_returned_amount') ?? '')
  const valid = returnedCents !== null && returnedCents >= 0 && returnedCents <= depositCents
  const retainedCents = valid ? depositCents - returnedCents! : null

  return (
    <Modal open onClose={onClose} title={`Encerrar contrato ${contract.code}`} wide>
      <form onSubmit={handleSubmit((form) => mutation.mutate(form))} className="space-y-4">
        <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
          <strong className="text-slate-900">
            {contract.vehicle?.plate} · {contract.driver?.full_name}
          </strong>
          <div className="mt-0.5">
            Início em {formatDate(contract.start_date)} · caução recebida de{' '}
            <strong>{formatMoney(contract.deposit_amount)}</strong>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data de encerramento" required error={errors.end_date?.message}>
            <Input type="date" {...register('end_date')} />
          </Field>

          <Field
            label="Quanto da caução será devolvido"
            required
            error={errors.deposit_returned_amount?.message}
            hint={`Entre R$ 0,00 e ${formatMoney(contract.deposit_amount)}.`}
          >
            <MoneyInput {...register('deposit_returned_amount')} />
          </Field>
        </div>

        {/* O acerto da caução em português claro, ANTES de confirmar. */}
        {depositCents === 0 ? (
          <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            Este contrato não tem caução — não há nada a devolver nem a reter.
          </div>
        ) : retainedCents === null ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-3 text-sm text-slate-500">
            Informe quanto da caução volta para o motorista para ver o acerto.
          </div>
        ) : (
          <div
            className={
              retainedCents > 0
                ? 'rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900'
                : 'rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700'
            }
          >
            <div className="text-base">
              Devolvendo{' '}
              <strong className="tabular-nums">
                {formatMoney(fromCents(returnedCents!))}
              </strong>
              , retendo{' '}
              <strong className="tabular-nums">{formatMoney(fromCents(retainedCents))}</strong>.
            </div>
            <p className="mt-2">
              {retainedCents > 0 ? (
                <>
                  Os <strong>{formatMoney(fromCents(retainedCents))}</strong> retidos viram{' '}
                  <strong>receita do veículo</strong> (categoria “caução retida”), já quitada — o
                  dinheiro está com você desde a assinatura. O restante volta para o motorista e{' '}
                  <strong>nunca foi receita</strong>.
                </>
              ) : (
                <>
                  A caução volta inteira para o motorista. <strong>Nada vira receita</strong> — e
                  está certo: esse dinheiro nunca foi seu.
                </>
              )}
            </p>
          </div>
        )}

        <Field label="Observações do encerramento" error={errors.notes?.message}>
          <Textarea
            placeholder="Ex.: retido R$ 500 por avaria no para-choque."
            {...register('notes')}
          />
        </Field>

        <p className="text-xs text-slate-500">
          Ao encerrar, as semanas ainda não cobradas até a data de fim são geradas, as semanas
          posteriores (sem pagamento) são canceladas e o veículo volta a ficar disponível.
        </p>

        {mutation.isError && <ErrorBox message={errorMessage(mutation.error)} />}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" variant="danger" loading={mutation.isPending}>
            Encerrar contrato
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- anexos */

function AttachmentsModal({ contract, onClose }: { contract: Contract; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState('contrato_pdf')
  const [file, setFile] = useState<File | null>(null)
  const [downloadError, setDownloadError] = useState('')

  const params = { entity_type: 'contract', entity_id: contract.id }

  const filesQuery = useQuery({
    queryKey: ['files', params],
    queryFn: async () => (await api.get<Attachment[]>('/files', { params })).data,
  })

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const data = new FormData()
      data.append('entity_type', 'contract')
      data.append('entity_id', contract.id)
      data.append('kind', kind)
      data.append('file', file as File)
      return api.post('/files/upload', data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['files', params] })
      setFile(null)
    },
  })

  /**
   * O download é AUTENTICADO (tem CNH, CPF e contrato assinado atrás dele). Um `<a href>`
   * direto não levaria o token e voltaria 401 — por isso baixamos pelo axios, que passa
   * pelo interceptor, e abrimos o blob.
   */
  async function download(attachment: Attachment) {
    setDownloadError('')
    try {
      const response = await api.get(`/files/${attachment.id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data as Blob)
      const link = window.document.createElement('a')
      link.href = url
      link.download = attachment.original_filename ?? 'documento'
      window.document.body.appendChild(link)
      link.click()
      link.remove()
      // Revoga depois: revogar na hora cancela o download em alguns navegadores.
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      setDownloadError(errorMessage(err))
    }
  }

  const attachments = filesQuery.data ?? []

  return (
    <Modal open onClose={onClose} title={`Anexos do contrato ${contract.code}`} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 p-4">
          <div className="w-56">
            <Field label="Tipo do documento">
              <Select value={kind} onChange={(e) => setKind(e.target.value)}>
                {Object.entries(DOCUMENT_KINDS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="min-w-60 flex-1">
            <Field label="Arquivo">
              <Input
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm"
              />
            </Field>
          </div>
          <Button
            onClick={() => uploadMutation.mutate()}
            loading={uploadMutation.isPending}
            disabled={!file}
          >
            <Upload size={16} />
            Enviar
          </Button>
        </div>

        {uploadMutation.isError && <ErrorBox message={errorMessage(uploadMutation.error)} />}
        {downloadError && <ErrorBox message={downloadError} />}

        {filesQuery.isPending ? (
          <Spinner />
        ) : filesQuery.isError ? (
          <ErrorBox message={errorMessage(filesQuery.error)} />
        ) : attachments.length === 0 ? (
          <EmptyState message="Nenhum anexo neste contrato ainda." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Tipo</Th>
                <Th>Arquivo</Th>
                <Th className="text-right">Tamanho</Th>
                <Th className="text-right">Baixar</Th>
              </tr>
            </thead>
            <tbody>
              {attachments.map((attachment) => (
                <tr key={attachment.id}>
                  <Td>
                    <Badge
                      label={DOCUMENT_KINDS[attachment.kind] ?? attachment.kind}
                      className="bg-slate-100 text-slate-700"
                    />
                  </Td>
                  <Td className="text-slate-700">{attachment.original_filename ?? '—'}</Td>
                  <Td className="text-right tabular-nums text-slate-500">
                    {Math.max(1, Math.round(attachment.size_bytes / 1024))} KB
                  </Td>
                  <Td className="text-right">
                    <Button variant="ghost" onClick={() => download(attachment)} title="Baixar">
                      <Download size={16} />
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="secondary" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </div>
    </Modal>
  )
}
