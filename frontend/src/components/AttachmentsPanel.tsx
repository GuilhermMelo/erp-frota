/**
 * Anexos de um registro (nota fiscal da manutenção, notificação da multa).
 *
 * Fala com `POST /files/upload`, `GET /files`, `GET /files/{id}/download` e `DELETE /files/{id}`.
 * O download é AUTENTICADO — ver `lib/authFile.ts` para o porquê de não existir link direto.
 */

import { useRef, useState } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileText, Paperclip, Trash2, Upload } from 'lucide-react'

import { api, errorMessage } from '../api/client'
import type { AttachmentEntity, AttachmentKind, DocumentOut } from '../lib/authFile'
import {
  ACCEPTED_UPLOAD_MIME,
  DOCUMENT_KIND_LABEL,
  attachmentsKey,
  formatBytes,
  openAuthenticatedFile,
  uploadDocument,
} from '../lib/authFile'
import { formatDateTime } from '../lib/format'
import { Badge, Button, EmptyState, ErrorBox, Field, Select, Spinner } from './ui'

type Props = {
  entityType: AttachmentEntity
  entityId: string
  /**
   * Tipos que este painel aceita. Com um só, envia direto. Com vários, mostra um seletor —
   * sem ele o usuário é obrigado a rotular errado (foi o que aconteceu: um comprovante de
   * residência entrou no sistema como "Contrato assinado").
   */
  kinds: AttachmentKind[]
  /** Rótulo do botão de envio, ex.: "Anexar nota fiscal". */
  uploadLabel: string
}

export function AttachmentsPanel({ entityType, entityId, kinds, uploadLabel }: Props) {
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [error, setError] = useState('')
  const [kind, setKind] = useState<AttachmentKind>(kinds[0])

  const documents = useQuery({
    queryKey: attachmentsKey(entityType, entityId),
    queryFn: async () => {
      const { data } = await api.get<DocumentOut[]>('/files', {
        params: { entity_type: entityType, entity_id: entityId },
      })
      return data
    },
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: attachmentsKey(entityType, entityId) })

  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument({ entityType, entityId, kind, file }),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/files/${id}`),
    onSuccess: invalidate,
  })

  async function pick(files: FileList | null) {
    if (!files?.length) return
    setError('')
    try {
      // Um de cada vez: são poucos anexos, e assim o erro aponta o arquivo certo.
      for (const file of Array.from(files)) {
        await upload.mutateAsync(file)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      if (input.current) input.current.value = '' // permite reenviar o mesmo arquivo
    }
  }

  async function open(document: DocumentOut) {
    setError('')
    try {
      await openAuthenticatedFile(
        `/files/${document.id}/download`,
        document.original_filename ?? 'arquivo',
      )
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <input
          ref={input}
          type="file"
          accept={ACCEPTED_UPLOAD_MIME}
          multiple
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />

        {kinds.length > 1 && (
          <div className="w-60">
            <Field label="Tipo do documento">
              <Select value={kind} onChange={(e) => setKind(e.target.value as AttachmentKind)}>
                {kinds.map((k) => (
                  <option key={k} value={k}>
                    {DOCUMENT_KIND_LABEL[k]}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        )}

        <Button
          type="button"
          variant="secondary"
          loading={upload.isPending}
          onClick={() => input.current?.click()}
        >
          <Upload size={16} />
          {uploadLabel}
        </Button>
        <span className="pb-2 text-xs text-slate-500">JPEG, PNG, WebP ou PDF · até 15 MB</span>
      </div>

      {error && <ErrorBox message={error} />}
      {documents.isError && <ErrorBox message={errorMessage(documents.error)} />}

      {documents.isPending ? (
        <Spinner label="Carregando anexos…" />
      ) : !documents.data?.length ? (
        <EmptyState message="Nenhum anexo." />
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {documents.data.map((document) => (
            <li key={document.id} className="flex items-center gap-3 px-3 py-2">
              {document.mime_type === 'application/pdf' ? (
                <FileText size={16} className="shrink-0 text-slate-400" />
              ) : (
                <Paperclip size={16} className="shrink-0 text-slate-400" />
              )}

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {/* O tipo primeiro: sem ele, "comprovante-residencia-enel-Boleto_177…pdf"
                      e "rg-frente.pdf" viram só dois nomes de arquivo numa lista. */}
                  <Badge
                    label={DOCUMENT_KIND_LABEL[document.kind] ?? document.kind}
                    className="shrink-0 bg-slate-100 text-slate-700"
                  />
                  <span className="truncate text-sm text-slate-800">
                    {document.original_filename ?? 'arquivo'}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {formatBytes(document.size_bytes)} · {formatDateTime(document.created_at)}
                </div>
              </div>

              <Button type="button" variant="ghost" onClick={() => open(document)} title="Abrir">
                <Download size={16} />
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="text-red-600 hover:bg-red-50"
                title="Excluir anexo"
                loading={remove.isPending && remove.variables === document.id}
                onClick={() => {
                  if (confirm(`Excluir "${document.original_filename ?? 'arquivo'}"?`)) {
                    remove.mutate(document.id)
                  }
                }}
              >
                <Trash2 size={16} />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
