/**
 * <img> apontando para um endpoint AUTENTICADO da API.
 *
 * `GET /inspections/photos/{id}/download` exige o token. Um `<img src="/api/...">` daria 401,
 * porque o navegador não manda o header Authorization ao carregar uma imagem. Então os bytes
 * vêm pelo axios e viram um object URL local.
 *
 * Duas defesas para aguentar uma vistoria de 200 fotos:
 *
 *  1. `revokeObjectURL` na limpeza do efeito. Sem isso cada miniatura deixa um Blob preso na
 *     memória — 200 fotos vazam ~50 MB que só o reload da página devolve.
 *  2. Só busca a foto quando ela chega perto da viewport (IntersectionObserver). Baixar as
 *     200 de uma vez seria abrir 200 requests para ver as 12 primeiras miniaturas.
 */

import { useEffect, useRef, useState } from 'react'

import { ImageOff, Loader2 } from 'lucide-react'

import { api } from '../api/client'
import { cn } from './ui'

type AuthImageProps = {
  /** Caminho na API, ex.: `/inspections/photos/{id}/download`. */
  src: string
  alt: string
  className?: string
  /** `cover` para miniatura; `contain` para a foto ampliada, que não pode ser cortada. */
  fit?: 'cover' | 'contain'
}

export function AuthImage({ src, alt, className, fit = 'cover' }: AuthImageProps) {
  const holder = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  // Passo 1: descobrir se a foto está (quase) na tela.
  useEffect(() => {
    if (visible) return
    const node = holder.current
    if (!node) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setVisible(true)
      },
      // Começa a baixar um pouco antes de aparecer: a miniatura já chega pronta na rolagem.
      { rootMargin: '300px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [visible])

  // Passo 2: baixar os bytes com o token e virar object URL.
  useEffect(() => {
    if (!visible) return

    let objectUrl: string | null = null
    let cancelled = false
    setFailed(false)

    api
      .get<Blob>(src, { responseType: 'blob' })
      .then((response) => {
        // O componente saiu da tela antes da resposta chegar: nem cria o object URL, senão
        // ele nasceria já órfão (a limpeza abaixo já teria rodado).
        if (cancelled) return
        objectUrl = URL.createObjectURL(response.data)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      setUrl(null)
      // O ponto crítico desta tela. Sem este revoke, 200 fotos = 200 Blobs na memória.
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src, visible])

  return (
    <div
      ref={holder}
      className={cn('flex items-center justify-center overflow-hidden bg-slate-100', className)}
    >
      {failed ? (
        <span title="Não foi possível carregar a foto.">
          <ImageOff size={18} className="text-slate-400" />
        </span>
      ) : url ? (
        <img
          src={url}
          alt={alt}
          className={cn('h-full w-full', fit === 'cover' ? 'object-cover' : 'object-contain')}
        />
      ) : (
        <Loader2 size={16} className="animate-spin text-slate-300" />
      )}
    </div>
  )
}
