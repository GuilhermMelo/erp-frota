/**
 * Compressão de imagem NO NAVEGADOR, antes de subir.
 *
 * Por que existe: uma vistoria tem até 200 fotos. Foto de celular pesa ~5 MB — 200 delas
 * dariam 1 GB numa vistoria só: o upload nunca termina, o disco enche e o backend recusa
 * cada arquivo (MAX_FILE_BYTES = 15 MB, ver core/storage.py). Redimensionadas para 1600px
 * no maior lado e salvas em JPEG 0.8, as fotos ficam em ~250 KB e a vistoria inteira cabe
 * em ~50 MB.
 *
 * O backend só aceita JPEG, PNG, WebP e PDF (ALLOWED_MIME) e confere os BYTES com o Pillow
 * — o mime declarado pelo navegador não engana ninguém lá. Por isso o que sai daqui é um
 * arquivo de verdade, não um File remendado.
 */

/** Maior lado da imagem depois de redimensionar. */
const MAX_SIDE = 1600

/** Qualidade do JPEG de saída. 0.8 é onde a perda deixa de ser visível numa foto de carro. */
const QUALITY = 0.8

/** Abaixo disso a foto já está leve — recomprimir só perderia qualidade à toa. */
const SKIP_BELOW_BYTES = 300 * 1024

/** Tipos de imagem que o backend aceita sem conversão (ALLOWED_MIME, menos o PDF). */
const ACCEPTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

/**
 * Devolve uma versão leve da imagem. Arquivo que não é imagem (PDF) volta intacto.
 * Nunca lança: se o navegador não souber decodificar, devolve o original.
 */
export async function compressImage(file: File): Promise<File> {
  // PDF — ou qualquer coisa que não seja imagem — passa sem tocar.
  if (!file.type.startsWith('image/')) return file

  // Já é pequena E de um tipo que o backend aceita: não mexe.
  // Imagem pequena mas de tipo RECUSADO (HEIC, BMP, GIF) não entra neste atalho de
  // propósito: converter para JPEG é justamente o que salva o arquivo de ser rejeitado.
  if (file.size <= SKIP_BELOW_BYTES && ACCEPTED_IMAGE_TYPES.has(file.type)) return file

  try {
    return await toJpeg(file)
  } catch {
    // Formato que este navegador não decodifica (HEIC do iPhone, por exemplo). Sobe o
    // original e deixa o backend recusar com uma mensagem clara — melhor do que sumir com
    // a foto em silêncio.
    return file
  }
}

async function toJpeg(file: File): Promise<File> {
  // `imageOrientation: 'from-image'` aplica o EXIF. Sem isso, foto tirada na vertical
  // chega deitada no servidor — e no canvas não há como consertar depois.
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })

  try {
    const { width, height } = fitInside(bitmap.width, bitmap.height, MAX_SIDE)

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height

    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas 2D indisponível.')
    ctx.drawImage(bitmap, 0, 0, width, height)

    const blob = await canvasToBlob(canvas)

    // Print de tela e imagem já otimizada podem ficar MAIORES em JPEG. Aí o original vence
    // — desde que seja um tipo que o backend aceite.
    if (blob.size >= file.size && ACCEPTED_IMAGE_TYPES.has(file.type)) return file

    return new File([blob], toJpgName(file.name), {
      type: 'image/jpeg',
      lastModified: file.lastModified,
    })
  } finally {
    // São 200 fotos em sequência: devolver a memória do bitmap na hora evita o navegador
    // engasgar no meio da fila.
    bitmap.close()
  }
}

/** Cabe num quadrado de `max` px sem distorcer. Imagem já menor que isso não é ampliada. */
function fitInside(width: number, height: number, max: number) {
  const factor = Math.min(1, max / Math.max(width, height))
  return {
    width: Math.max(1, Math.round(width * factor)),
    height: Math.max(1, Math.round(height * factor)),
  }
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('Falha ao gerar o JPEG.'))),
      'image/jpeg',
      QUALITY,
    )
  })
}

function toJpgName(name: string): string {
  const base = name.replace(/\.[^.]+$/, '').trim()
  return `${base || 'foto'}.jpg`
}
