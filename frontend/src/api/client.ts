import axios from 'axios'

const TOKEN_KEY = 'erp_frota_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

/** Emitido quando o token expira, para o AuthProvider deslogar sem prop drilling. */
export const UNAUTHORIZED_EVENT = 'erp:unauthorized'

export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (error) => {
    // 401 fora da tela de login = sessão expirada. Sem isso o app fica "logado" e quebrado
    // (o Atlas tinha exatamente esse bug — MELHORIAS 1.9).
    const isLogin = error.config?.url?.includes('/auth/login')
    if (error.response?.status === 401 && !isLogin) {
      tokenStore.clear()
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    return Promise.reject(error)
  },
)

/** A API sempre responde erro no envelope {"error": {code, message, details}}. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const env = error.response?.data?.error
    if (env?.message) {
      const det = env.details
      if (Array.isArray(det) && det.length) {
        return `${env.message} ${det.map((d: { campo: string; erro: string }) => `${d.campo}: ${d.erro}`).join('; ')}`
      }
      return env.message
    }
    if (error.code === 'ERR_NETWORK') return 'Não foi possível falar com o servidor. Ele está rodando?'
  }
  return 'Erro inesperado.'
}
