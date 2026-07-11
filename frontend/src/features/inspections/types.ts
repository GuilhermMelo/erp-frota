/**
 * Tipos e rótulos da vistoria — compartilhados pela lista e pela tela de detalhe.
 * Espelham `backend/app/domains/inspections/` (models.py e schemas.py).
 */

export type InspectionKind = 'entrega' | 'devolucao' | 'periodica'
export type ItemCondition = 'ok' | 'avaria' | 'faltando' | 'na'
export type PhotoCategory =
  | 'frente'
  | 'traseira'
  | 'lateral_esquerda'
  | 'lateral_direita'
  | 'interior'
  | 'painel'
  | 'motor'
  | 'pneus'
  | 'avaria'
  | 'assinatura'
  | 'outros'

export type VehicleBrief = {
  id: string
  code: string
  plate: string
  brand: string
  model: string
}

export type DriverBrief = { id: string; code: string; full_name: string }

export type ChecklistItem = {
  id: number
  key: string
  label: string
  /** exterior · interior · mecanica · documentos — é uma TABELA no banco, pode crescer. */
  group_name: string
  sort_order: number
}

export type InspectionItem = {
  id: string
  checklist_item_id: number
  condition: ItemCondition
  notes: string | null
  checklist_item: ChecklistItem
}

export type InspectionPhoto = {
  id: string
  inspection_id: string
  category: PhotoCategory
  caption: string | null
  original_filename: string | null
  mime_type: string
  size_bytes: number
  sort_order: number
  created_at: string
  /** `/inspections/photos/{id}/download` — AUTENTICADO. Ver components/AuthImage.tsx. */
  download_url: string
}

export type InspectionDetail = {
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
  vehicle: VehicleBrief
  driver: DriverBrief | null
  items: InspectionItem[]
  photos: InspectionPhoto[]
}

/** A lista e o detalhe compartilham este cache: abrir uma vistoria da lista é instantâneo. */
export function inspectionKey(id: string) {
  return ['inspection', id] as const
}

export const INSPECTION_KIND: Record<InspectionKind, { label: string; className: string }> = {
  entrega: { label: 'Entrega', className: 'bg-blue-100 text-blue-800' },
  devolucao: { label: 'Devolução', className: 'bg-purple-100 text-purple-800' },
  periodica: { label: 'Periódica', className: 'bg-slate-100 text-slate-600' },
}

/** Os 4 estados de um item do checklist. */
export const CONDITIONS: {
  value: ItemCondition
  label: string
  activeClass: string
  idleClass: string
}[] = [
  {
    value: 'ok',
    label: 'OK',
    activeClass: 'border-emerald-600 bg-emerald-600 text-white',
    idleClass: 'border-slate-300 text-slate-600 hover:bg-emerald-50 hover:border-emerald-300',
  },
  {
    value: 'avaria',
    label: 'Avaria',
    activeClass: 'border-red-600 bg-red-600 text-white',
    idleClass: 'border-slate-300 text-slate-600 hover:bg-red-50 hover:border-red-300',
  },
  {
    value: 'faltando',
    label: 'Faltando',
    activeClass: 'border-amber-500 bg-amber-500 text-white',
    idleClass: 'border-slate-300 text-slate-600 hover:bg-amber-50 hover:border-amber-300',
  },
  {
    value: 'na',
    label: 'N/A',
    activeClass: 'border-slate-600 bg-slate-600 text-white',
    idleClass: 'border-slate-300 text-slate-500 hover:bg-slate-100',
  },
]

/** Ordem em que a tela desenha as seções. Grupo novo no banco cai no fim, sem quebrar nada. */
export const GROUP_ORDER = ['exterior', 'interior', 'mecanica', 'documentos']

export const GROUP_LABEL: Record<string, string> = {
  exterior: 'Exterior',
  interior: 'Interior',
  mecanica: 'Mecânica',
  documentos: 'Documentos e acessórios',
}

/** `assinatura` é a foto da vistoria assinada — nada de especial, é só mais uma categoria. */
export const PHOTO_CATEGORIES: { value: PhotoCategory; label: string }[] = [
  { value: 'frente', label: 'Frente' },
  { value: 'traseira', label: 'Traseira' },
  { value: 'lateral_esquerda', label: 'Lateral esquerda' },
  { value: 'lateral_direita', label: 'Lateral direita' },
  { value: 'interior', label: 'Interior' },
  { value: 'painel', label: 'Painel' },
  { value: 'motor', label: 'Motor' },
  { value: 'pneus', label: 'Pneus' },
  { value: 'avaria', label: 'Avaria' },
  { value: 'assinatura', label: 'Assinatura (vistoria assinada)' },
  { value: 'outros', label: 'Outros' },
]

export const PHOTO_CATEGORY_LABEL: Record<PhotoCategory, string> = Object.fromEntries(
  PHOTO_CATEGORIES.map((category) => [category.value, category.label]),
) as Record<PhotoCategory, string>
