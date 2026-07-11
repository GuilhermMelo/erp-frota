/**
 * Vistoria — checklist e fotos. A tela mais pesada do produto.
 *
 * Duas coisas acontecem aqui, e as duas são "a prova" numa discussão com o motorista:
 *
 * 1. CHECKLIST — item a item, 4 estados. Item com avaria fica em destaque.
 *
 * 2. FOTOS — até 200 por vistoria, inseridas do desktop. Três decisões sustentam isso:
 *
 *    · COMPRESSÃO NO NAVEGADOR (lib/compressImage.ts). 200 fotos de celular a 5 MB dariam
 *      1 GB por vistoria. Comprimidas, ~250 KB cada: a vistoria inteira cabe em ~50 MB.
 *
 *    · FILA COM 4 REQUESTS EM PARALELO, uma foto por request. Um POST único com 200 arquivos
 *      derruba o servidor, não dá feedback nenhum e, se falhar no arquivo 137, perde os 200.
 *      Assim a barra de progresso é honesta e o retry é individual.
 *
 *    · MINIATURA VIA TOKEN (components/AuthImage.tsx). O download é autenticado; um
 *      <img src="/api/..."> daria 401. E cada object URL é revogado na limpeza do efeito,
 *      senão 200 fotos vazam memória.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Camera,
  Check,
  CircleAlert,
  Download,
  Gauge,
  Loader2,
  RotateCcw,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { api, errorMessage } from '../../api/client'
import { AuthImage } from '../../components/AuthImage'
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
  cn,
} from '../../components/ui'
import { formatBytes, openAuthenticatedFile } from '../../lib/authFile'
import { compressImage } from '../../lib/compressImage'
import { formatDateTime, formatNumber } from '../../lib/format'
import { useAuth } from '../auth/AuthContext'
import type {
  InspectionDetail,
  InspectionItem,
  InspectionPhoto,
  ItemCondition,
  PhotoCategory,
} from './types'
import {
  CONDITIONS,
  GROUP_LABEL,
  GROUP_ORDER,
  INSPECTION_KIND,
  PHOTO_CATEGORIES,
  PHOTO_CATEGORY_LABEL,
  inspectionKey,
} from './types'

/** Requests simultâneos de upload. Acima disso o servidor engasga e o ganho é zero. */
const MAX_PARALLEL = 4
/** Teto por lote. É o número que o produto promete aguentar. */
const MAX_FILES = 200

export function InspectionDetailPage() {
  const { id } = useParams<{ id: string }>()
  if (!id) return <Navigate to="/vistorias" replace />
  return <InspectionView id={id} />
}

function InspectionView({ id }: { id: string }) {
  const inspection = useQuery({
    queryKey: inspectionKey(id),
    queryFn: async () => (await api.get<InspectionDetail>(`/inspections/${id}`)).data,
  })

  if (inspection.isPending) return <Spinner label="Carregando vistoria…" />
  if (inspection.isError) return <ErrorBox message={errorMessage(inspection.error)} />

  const data = inspection.data

  return (
    <>
      <Link
        to="/vistorias"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
      >
        <ArrowLeft size={16} />
        Voltar para as vistorias
      </Link>

      <PageHeader
        title={`Vistoria ${data.code}`}
        subtitle={`${data.vehicle.plate} — ${data.vehicle.brand} ${data.vehicle.model}`}
        action={<Badge {...INSPECTION_KIND[data.kind]} />}
      />

      <HeaderCard data={data} />
      <ChecklistSection id={id} items={data.items} />
      <PhotosSection id={id} photos={data.photos} />
    </>
  )
}

/* ------------------------------------------------------------------ cabeçalho */

function HeaderCard({ data }: { data: InspectionDetail }) {
  const { user } = useAuth()

  // GET /users é só de admin. Um operador não pode listar — então caímos para o próprio
  // nome quando a vistoria é dele, e para "—" quando não dá para saber.
  const users = useQuery({
    queryKey: ['users', 'select'],
    queryFn: async () => (await api.get<{ id: string; full_name: string }[]>('/users')).data,
    enabled: user?.role === 'admin',
  })

  const inspector = !data.user_id
    ? '—'
    : data.user_id === user?.id
      ? user.full_name
      : (users.data?.find((candidate) => candidate.id === data.user_id)?.full_name ?? '—')

  return (
    <Card className="mb-6">
      <dl className="grid gap-5 sm:grid-cols-3 lg:grid-cols-6">
        <Info label="Veículo">
          <div className="font-medium text-slate-900">{data.vehicle.plate}</div>
          <div className="text-xs text-slate-500">
            {data.vehicle.brand} {data.vehicle.model}
          </div>
        </Info>

        <Info label="Motorista">{data.driver?.full_name ?? '—'}</Info>

        <Info label="Tipo">
          <Badge {...INSPECTION_KIND[data.kind]} />
        </Info>

        <Info label="Data">{formatDateTime(data.inspected_at)}</Info>

        <Info label="Odômetro">
          <span className="inline-flex items-center gap-1.5">
            <Gauge size={14} className="text-slate-400" />
            {formatNumber(data.odometer)} km
          </span>
        </Info>

        <Info label={`Combustível — ${data.fuel_level}%`}>
          <div className="mt-1.5 h-2 w-full max-w-28 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-brand-600" style={{ width: `${data.fuel_level}%` }} />
          </div>
        </Info>
      </dl>

      <div className="mt-5 border-t border-slate-100 pt-4 text-sm">
        <span className="text-slate-500">Vistoria feita por </span>
        <span className="font-medium text-slate-700">{inspector}</span>
      </div>

      {data.notes && (
        <p className="mt-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{data.notes}</p>
      )}
    </Card>
  )
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="mt-1 text-sm text-slate-800">{children}</dd>
    </div>
  )
}

/* ------------------------------------------------------------------ checklist */

type Draft = { condition: ItemCondition; notes: string }

function toDraft(items: InspectionItem[]): Record<number, Draft> {
  return Object.fromEntries(
    items.map((item) => [item.checklist_item_id, { condition: item.condition, notes: item.notes ?? '' }]),
  )
}

function ChecklistSection({ id, items }: { id: string; items: InspectionItem[] }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Record<number, Draft>>(() => toDraft(items))

  // Só resemeia quando muda de vistoria. Sem esta trava, um refetch em segundo plano
  // (ex.: depois de subir uma foto) apagaria as marcações que ainda não foram salvas.
  const seededFor = useRef(id)
  useEffect(() => {
    if (seededFor.current === id) return
    seededFor.current = id
    setDraft(toDraft(items))
  }, [id, items])

  const dirty = useMemo(
    () =>
      items.some((item) => {
        const current = draft[item.checklist_item_id]
        if (!current) return false
        return current.condition !== item.condition || current.notes !== (item.notes ?? '')
      }),
    [items, draft],
  )

  const damaged = items.filter((i) => draft[i.checklist_item_id]?.condition === 'avaria').length
  const missing = items.filter((i) => draft[i.checklist_item_id]?.condition === 'faltando').length

  const save = useMutation({
    mutationFn: async () => {
      // Mandamos TODOS os itens com o estado completo. O backend faz `item.notes = entrada.notes`
      // em cada item recebido — enviar só o que mudou apagaria a observação dos outros.
      const { data } = await api.patch<InspectionDetail>(`/inspections/${id}`, {
        items: items.map((item) => {
          const current = draft[item.checklist_item_id]
          return {
            checklist_item_id: item.checklist_item_id,
            condition: current?.condition ?? item.condition,
            notes: current?.notes.trim() || null,
          }
        }),
      })
      return data
    },
    onSuccess: (updated) => {
      setDraft(toDraft(updated.items))
      queryClient.invalidateQueries({ queryKey: inspectionKey(id) })
    },
  })

  const groups = useMemo(() => groupItems(items), [items])

  return (
    <Card className="mb-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Checklist</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Marque só o que estiver errado — tudo nasce em “ok”.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {damaged > 0 && (
            <Badge
              label={`${damaged} ${damaged === 1 ? 'avaria' : 'avarias'}`}
              className="bg-red-100 text-red-800"
            />
          )}
          {missing > 0 && (
            <Badge
              label={`${missing} ${missing === 1 ? 'item faltando' : 'itens faltando'}`}
              className="bg-amber-100 text-amber-800"
            />
          )}
          {damaged === 0 && missing === 0 && (
            <Badge label="Sem avarias" className="bg-emerald-100 text-emerald-800" />
          )}

          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}>
            <Check size={16} />
            {dirty ? 'Salvar checklist' : 'Salvo'}
          </Button>
        </div>
      </div>

      {save.isError && (
        <div className="mb-4">
          <ErrorBox message={errorMessage(save.error)} />
        </div>
      )}

      <div className="space-y-6">
        {groups.map(([group, groupItems]) => (
          <section key={group}>
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
              {GROUP_LABEL[group] ?? group}
            </h3>
            <div className="space-y-2">
              {groupItems.map((item) => (
                <ChecklistRow
                  key={item.id}
                  item={item}
                  draft={draft[item.checklist_item_id]}
                  onChange={(next) =>
                    setDraft((current) => ({ ...current, [item.checklist_item_id]: next }))
                  }
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </Card>
  )
}

/** Agrupa por `group_name`, na ordem em que a tela desenha. Grupo novo no banco cai no fim. */
function groupItems(items: InspectionItem[]): [string, InspectionItem[]][] {
  const groups = new Map<string, InspectionItem[]>()
  for (const item of items) {
    const group = item.checklist_item.group_name
    const bucket = groups.get(group)
    if (bucket) bucket.push(item)
    else groups.set(group, [item])
  }

  const rank = (group: string) => {
    const index = GROUP_ORDER.indexOf(group)
    return index === -1 ? GROUP_ORDER.length : index
  }

  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(
      ([group, list]) =>
        [group, [...list].sort((a, b) => a.checklist_item.sort_order - b.checklist_item.sort_order)] as [
          string,
          InspectionItem[],
        ],
    )
}

function ChecklistRow({
  item,
  draft,
  onChange,
}: {
  item: InspectionItem
  draft?: Draft
  onChange: (next: Draft) => void
}) {
  const condition = draft?.condition ?? item.condition
  const notes = draft?.notes ?? ''

  // O destaque é o ponto: numa discussão sobre quem quebrou o quê, a avaria tem que saltar.
  const highlight =
    condition === 'avaria'
      ? 'border-red-300 bg-red-50'
      : condition === 'faltando'
        ? 'border-amber-300 bg-amber-50'
        : 'border-slate-200 bg-white'

  return (
    <div className={cn('rounded-lg border p-3 transition-colors', highlight)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm font-medium text-slate-800">
          {(condition === 'avaria' || condition === 'faltando') && (
            <CircleAlert
              size={15}
              className={condition === 'avaria' ? 'text-red-600' : 'text-amber-600'}
            />
          )}
          {item.checklist_item.label}
        </span>

        <div className="flex gap-1" role="group" aria-label={`Estado de ${item.checklist_item.label}`}>
          {CONDITIONS.map((option) => {
            const active = condition === option.value
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                onClick={() => onChange({ condition: option.value, notes })}
                className={cn(
                  'rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
                  active ? option.activeClass : cn('bg-white', option.idleClass),
                )}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>

      <Input
        value={notes}
        maxLength={200}
        placeholder="Observação (ex.: risco de 10 cm na porta do motorista)"
        onChange={(e) => onChange({ condition, notes: e.target.value })}
        className="mt-2 bg-white py-1.5 text-xs"
      />
    </div>
  )
}

/* ------------------------------------------------------------------ fotos */

type QueueStatus = 'pending' | 'compressing' | 'uploading' | 'done' | 'error'

type QueuedFile = {
  id: string
  file: File
  status: QueueStatus
  error?: string
  /** Tamanho depois da compressão — mostra ao usuário que o trabalho foi feito. */
  compressedSize?: number
}

/**
 * Fila com concorrência limitada, sem biblioteca: `limit` workers puxando de um cursor
 * compartilhado. O JS é single-thread, então `cursor++` não corre risco de corrida.
 */
async function runPool<T>(items: T[], limit: number, worker: (item: T) => Promise<void>) {
  let cursor = 0
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      await worker(items[cursor++])
    }
  })
  await Promise.all(workers)
}

function PhotosSection({ id, photos }: { id: string; photos: InspectionPhoto[] }) {
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  /** Guarda o resultado da compressão: um retry não recomprime o que já foi comprimido. */
  const compressed = useRef(new Map<string, File>())

  const [category, setCategory] = useState<PhotoCategory>('frente')
  const [queue, setQueue] = useState<QueuedFile[]>([])
  const [running, setRunning] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [notice, setNotice] = useState('')
  const [summary, setSummary] = useState('')
  const [lightbox, setLightbox] = useState<InspectionPhoto | null>(null)

  const done = queue.filter((item) => item.status === 'done').length
  const failed = queue.filter((item) => item.status === 'error')
  const percent = queue.length ? Math.round((done / queue.length) * 100) : 0

  function patch(itemId: string, changes: Partial<QueuedFile>) {
    setQueue((current) =>
      current.map((item) => (item.id === itemId ? { ...item, ...changes } : item)),
    )
  }

  function addFiles(list: FileList | null) {
    if (!list?.length || running) return

    const incoming = Array.from(list)
    const room = Math.max(0, MAX_FILES - queue.length)
    const accepted = incoming.slice(0, room)
    const ignored = incoming.length - accepted.length

    setSummary('')
    setNotice(
      ignored > 0
        ? `A fila comporta ${MAX_FILES} fotos por vez — ${ignored} ficaram de fora. Envie estas e repita.`
        : '',
    )
    if (!accepted.length) return

    setQueue((current) => [
      ...current,
      ...accepted.map((file) => ({
        id: crypto.randomUUID(),
        file,
        status: 'pending' as QueueStatus,
      })),
    ])
  }

  /** Comprime e sobe UMA foto. Devolve `true` se deu certo. */
  async function uploadOne(item: QueuedFile): Promise<boolean> {
    try {
      patch(item.id, { status: 'compressing', error: undefined })

      let file = compressed.current.get(item.id)
      if (!file) {
        file = await compressImage(item.file)
        compressed.current.set(item.id, file)
      }

      patch(item.id, { status: 'uploading', compressedSize: file.size })

      // Uma foto por request. O endpoint aceita até 10, mas se o lote falhasse no 7º arquivo
      // os 6 anteriores voltariam para a fila — e a barra de progresso mentiria.
      const form = new FormData()
      form.append('category', category)
      form.append('files', file, file.name)
      await api.post(`/inspections/${id}/photos`, form)

      patch(item.id, { status: 'done' })
      return true
    } catch (error) {
      patch(item.id, { status: 'error', error: errorMessage(error) })
      return false
    }
  }

  async function run(items: QueuedFile[]) {
    if (!items.length || running) return

    setRunning(true)
    setNotice('')
    setSummary('')

    const failures: string[] = []
    await runPool(items, MAX_PARALLEL, async (item) => {
      const ok = await uploadOne(item)
      if (!ok) failures.push(item.id)
    })

    const sent = items.length - failures.length
    setSummary(
      failures.length
        ? `${sent} de ${items.length} enviadas. ${failures.length} falharam — tente de novo.`
        : `${sent} ${sent === 1 ? 'foto enviada' : 'fotos enviadas'}.`,
    )

    // Some com o que subiu (já está na galeria) e deixa só o que precisa de atenção.
    const stillFailing = new Set(failures)
    setQueue((current) => current.filter((item) => stillFailing.has(item.id)))
    for (const item of items) {
      if (!stillFailing.has(item.id)) compressed.current.delete(item.id)
    }

    setRunning(false)
    queryClient.invalidateQueries({ queryKey: inspectionKey(id) })
  }

  const remove = useMutation({
    mutationFn: (photoId: string) => api.delete(`/inspections/photos/${photoId}`),
    onSuccess: () => {
      setLightbox(null)
      queryClient.invalidateQueries({ queryKey: inspectionKey(id) })
    },
  })

  const grouped = useMemo(() => groupPhotos(photos), [photos])

  return (
    <Card>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Fotos</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            {photos.length === 0
              ? 'Nenhuma foto ainda.'
              : `${formatNumber(photos.length)} ${photos.length === 1 ? 'foto' : 'fotos'} nesta vistoria.`}
          </p>
        </div>
      </div>

      {/* ---------- envio ---------- */}
      <div className="mb-6 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <Field
          label="Categoria das fotos"
          required
          hint="Vale para todas as fotos deste envio. “Assinatura” é a foto da vistoria assinada."
        >
          <Select
            value={category}
            disabled={running}
            onChange={(e) => setCategory(e.target.value as PhotoCategory)}
            className="max-w-xs bg-white"
          >
            {PHOTO_CATEGORIES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <input
          ref={input}
          type="file"
          multiple
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files)
            e.target.value = '' // permite escolher o mesmo arquivo de novo
          }}
        />

        <div
          role="button"
          tabIndex={0}
          aria-disabled={running}
          onClick={() => !running && input.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              if (!running) input.current?.click()
            }
          }}
          onDragOver={(e) => {
            e.preventDefault()
            if (!running) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            addFiles(e.dataTransfer.files)
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors',
            running
              ? 'cursor-not-allowed border-slate-200 bg-slate-100 opacity-60'
              : dragging
                ? 'border-brand-500 bg-brand-50'
                : 'border-slate-300 bg-white hover:border-brand-500 hover:bg-brand-50',
          )}
        >
          <Camera size={28} className="mb-2 text-slate-400" />
          <p className="text-sm font-medium text-slate-700">
            Arraste as fotos aqui ou clique para escolher
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Até {MAX_FILES} fotos por vez. Elas são comprimidas no navegador antes de subir — uma
            foto de 5 MB vira ~250 KB.
          </p>
        </div>

        {notice && <p className="text-xs text-amber-700">{notice}</p>}

        {queue.length > 0 && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-slate-700">
                {running
                  ? `Enviando… ${done} de ${queue.length}`
                  : `${queue.length} ${queue.length === 1 ? 'foto na fila' : 'fotos na fila'}`}
              </span>

              <div className="flex gap-2">
                {!running && (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      compressed.current.clear()
                      setQueue([])
                      setNotice('')
                    }}
                  >
                    Limpar
                  </Button>
                )}
                {!running && failed.length > 0 && failed.length === queue.length ? (
                  <Button onClick={() => run(failed)}>
                    <RotateCcw size={16} />
                    Tentar novamente ({failed.length})
                  </Button>
                ) : (
                  <Button onClick={() => run(queue)} loading={running}>
                    <Upload size={16} />
                    Enviar {queue.length} {queue.length === 1 ? 'foto' : 'fotos'}
                  </Button>
                )}
              </div>
            </div>

            {running && (
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full bg-brand-600 transition-[width] duration-200"
                  style={{ width: `${percent}%` }}
                />
              </div>
            )}

            <ul className="max-h-56 space-y-1 overflow-y-auto">
              {queue.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-slate-50"
                >
                  <QueueIcon status={item.status} />
                  <span className="min-w-0 flex-1 truncate text-slate-700">{item.file.name}</span>
                  <span className="shrink-0 text-slate-400">
                    {formatBytes(item.file.size)}
                    {item.compressedSize !== undefined &&
                      item.compressedSize < item.file.size &&
                      ` → ${formatBytes(item.compressedSize)}`}
                  </span>
                  {item.error && (
                    <span className="max-w-56 shrink-0 truncate text-red-600" title={item.error}>
                      {item.error}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {summary && !running && (
          <p
            className={cn(
              'text-sm font-medium',
              failed.length ? 'text-red-600' : 'text-emerald-600',
            )}
          >
            {summary}
          </p>
        )}
      </div>

      {/* ---------- galeria ---------- */}
      {remove.isError && (
        <div className="mb-4">
          <ErrorBox message={errorMessage(remove.error)} />
        </div>
      )}

      {photos.length === 0 ? (
        <EmptyState message="Suba as fotos da vistoria — frente, traseira, laterais, painel, avarias e a vistoria assinada." />
      ) : (
        <div className="space-y-6">
          {grouped.map(([groupCategory, groupPhotos]) => (
            <section key={groupCategory}>
              <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {PHOTO_CATEGORY_LABEL[groupCategory]}
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-500 normal-case">
                  {groupPhotos.length}
                </span>
              </h3>

              <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                {groupPhotos.map((photo) => (
                  <div key={photo.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => setLightbox(photo)}
                      className="block w-full"
                      title={photo.original_filename ?? 'Ampliar'}
                    >
                      <AuthImage
                        src={photo.download_url}
                        alt={photo.original_filename ?? PHOTO_CATEGORY_LABEL[photo.category]}
                        className="aspect-square w-full rounded-lg border border-slate-200"
                      />
                    </button>

                    <button
                      type="button"
                      title="Excluir foto"
                      onClick={() => {
                        if (confirm('Excluir esta foto? A ação não pode ser desfeita.')) {
                          remove.mutate(photo.id)
                        }
                      }}
                      className="absolute top-1 right-1 rounded-md bg-white/90 p-1 text-red-600 opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <PhotoLightbox
        photo={lightbox}
        onClose={() => setLightbox(null)}
        onDelete={(photo) => {
          if (confirm('Excluir esta foto? A ação não pode ser desfeita.')) remove.mutate(photo.id)
        }}
        deleting={remove.isPending}
      />
    </Card>
  )
}

/** Agrupa as fotos por categoria, na ordem do catálogo. Categoria vazia não aparece. */
function groupPhotos(photos: InspectionPhoto[]): [PhotoCategory, InspectionPhoto[]][] {
  const groups = new Map<PhotoCategory, InspectionPhoto[]>()
  for (const photo of photos) {
    const bucket = groups.get(photo.category)
    if (bucket) bucket.push(photo)
    else groups.set(photo.category, [photo])
  }

  return PHOTO_CATEGORIES.map(({ value }) => [value, groups.get(value) ?? []] as const)
    .filter(([, list]) => list.length > 0)
    .map(([value, list]) => [value, list] as [PhotoCategory, InspectionPhoto[]])
}

function QueueIcon({ status }: { status: QueueStatus }) {
  if (status === 'done') return <Check size={14} className="shrink-0 text-emerald-600" />
  if (status === 'error') return <X size={14} className="shrink-0 text-red-600" />
  if (status === 'pending') return <span className="size-3.5 shrink-0" />
  return <Loader2 size={14} className="shrink-0 animate-spin text-brand-600" />
}

function PhotoLightbox({
  photo,
  onClose,
  onDelete,
  deleting,
}: {
  photo: InspectionPhoto | null
  onClose: () => void
  onDelete: (photo: InspectionPhoto) => void
  deleting: boolean
}) {
  const [error, setError] = useState('')

  async function download() {
    if (!photo) return
    setError('')
    try {
      await openAuthenticatedFile(photo.download_url, photo.original_filename ?? 'foto.jpg')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Modal
      open={photo !== null}
      onClose={onClose}
      title={photo ? PHOTO_CATEGORY_LABEL[photo.category] : ''}
      wide
    >
      {photo && (
        <div className="space-y-4">
          <AuthImage
            src={photo.download_url}
            alt={photo.original_filename ?? 'Foto da vistoria'}
            fit="contain"
            className="h-[60vh] w-full rounded-lg bg-slate-900/5"
          />

          <div className="text-xs text-slate-500">
            {photo.original_filename ?? 'arquivo'} · {formatBytes(photo.size_bytes)} ·{' '}
            {formatDateTime(photo.created_at)}
          </div>

          {error && <ErrorBox message={error} />}

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={download}>
              <Download size={16} />
              Baixar
            </Button>
            <Button variant="danger" loading={deleting} onClick={() => onDelete(photo)}>
              <Trash2 size={16} />
              Excluir
            </Button>
            <Button variant="secondary" onClick={onClose}>
              Fechar
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
