/**
 * Arquivos da API: upload e download — SEMPRE autenticados.
 *
 * `storage/` nunca é pasta estática (CLAUDE.md, regra 5): lá dentro tem CNH, CPF, contrato
 * assinado e nota fiscal. Todo arquivo sai por endpoint autenticado.
 *
 * Consequência prática: `<a href="/api/files/{id}/download">` NÃO funciona — o navegador não
 * manda o header Authorization numa navegação, e o servidor responde 401. O jeito certo é
 * buscar os bytes com o axios (que já tem o interceptor do token) e abrir o Blob localmente.
 */

import { api } from '../api/client'
import { compressImage } from './compressImage'

/** `entity_type` do backend (files/schemas.py, EntityType). */
export type AttachmentEntity = 'contract' | 'fine' | 'maintenance' | 'vehicle' | 'driver'

/** `kind` do backend (files/models.py, DocumentKind). */
export type AttachmentKind =
  | 'contrato_pdf'
  | 'confissao_divida'
  | 'assinatura'
  | 'nota_fiscal'
  | 'cnh'
  | 'crlv'
  | 'notificacao'
  | 'foto'
  | 'outro'

export type DocumentOut = {
  id: string
  entity_type: string
  entity_id: string
  kind: AttachmentKind
  original_filename: string | null
  mime_type: string
  size_bytes: number
  created_at: string
  /** `/files/{id}/download` — autenticado. */
  download_url: string
}

/** O backend só aceita isto (core/storage.py, ALLOWED_MIME). */
export const ACCEPTED_UPLOAD_MIME = 'image/jpeg,image/png,image/webp,application/pdf'

export function attachmentsKey(entityType: AttachmentEntity, entityId: string) {
  return ['files', entityType, entityId] as const
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} MB`
}

/* ---------- download ---------- */

export async function fetchAuthenticatedBlob(path: string): Promise<Blob> {
  const { data } = await api.get<Blob>(path, { responseType: 'blob' })
  return data
}

/**
 * Abre o arquivo numa aba nova. Se o popup for bloqueado, baixa o arquivo.
 * `path` é o caminho na API, ex.: `/files/{id}/download`.
 */
export async function openAuthenticatedFile(path: string, filename?: string): Promise<void> {
  const blob = await fetchAuthenticatedBlob(path)
  const url = URL.createObjectURL(blob)

  const tab = window.open(url, '_blank', 'noopener')
  if (!tab) {
    // O clique já "esfriou" durante o await e o navegador bloqueou o popup: salva o arquivo,
    // que é o que o usuário queria de todo jeito.
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'arquivo'
    link.click()
  }

  // A aba precisa carregar antes do revoke — por isso o atraso, e não um revoke imediato.
  // Sem revoke nenhum, cada arquivo aberto fica preso na memória até o reload da página.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/* ---------- upload ---------- */

/**
 * Sobe um anexo (nota fiscal, notificação de multa…) para `POST /files/upload`.
 * Imagem é comprimida antes: foto de nota fiscal tirada no celular pesa 5 MB à toa.
 */
export async function uploadDocument(params: {
  entityType: AttachmentEntity
  entityId: string
  kind: AttachmentKind
  file: File
}): Promise<DocumentOut> {
  const file = await compressImage(params.file)

  const form = new FormData()
  form.append('entity_type', params.entityType)
  form.append('entity_id', params.entityId)
  form.append('kind', params.kind)
  form.append('file', file, file.name)

  const { data } = await api.post<DocumentOut>('/files/upload', form)
  return data
}
