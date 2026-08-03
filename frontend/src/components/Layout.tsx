import { useEffect, useState } from 'react'

import {
  Car,
  ClipboardCheck,
  Eye,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Receipt,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  UserCog,
  Users,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { api } from '../api/client'
import { useAuth } from '../features/auth/AuthContext'
import { cn } from './ui'

// Tipo explícito: sem ele, o spread de NAV com NAV_ADMIN faz o TypeScript inferir uma
// união onde `end` só existe num dos lados, e o destructuring no map não compila.
type ItemNav = { to: string; label: string; icon: LucideIcon; end?: boolean }

const NAV: ItemNav[] = [
  { to: '/', label: 'Painel', icon: LayoutDashboard, end: true },
  { to: '/veiculos', label: 'Veículos', icon: Car },
  { to: '/motoristas', label: 'Motoristas', icon: Users },
  { to: '/contratos', label: 'Contratos', icon: FileText },
  { to: '/cobrancas', label: 'Cobranças', icon: Receipt },
  { to: '/receitas', label: 'Receitas', icon: TrendingUp },
  { to: '/despesas', label: 'Despesas', icon: TrendingDown },
  { to: '/manutencoes', label: 'Manutenções', icon: Wrench },
  { to: '/multas', label: 'Multas', icon: ShieldAlert },
  { to: '/vistorias', label: 'Vistorias', icon: ClipboardCheck },
]

// Fora do NAV comum: a API recusa GET /users para operador, então mostrar o item para
// quem não é admin seria oferecer uma porta que abre num erro.
const NAV_ADMIN: ItemNav[] = [{ to: '/usuarios', label: 'Usuários', icon: UserCog }]

export function Layout() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()

  // O menu no celular é uma gaveta. Numa tela de 390 px, uma barra fixa de 240 px
  // deixaria ~150 px de conteúdo — a tabela de veículos ficaria ilegível.
  const [menuAberto, setMenuAberto] = useState(false)

  // Navegar fecha a gaveta. Sem isto, o menu fica por cima da tela que acabou de abrir.
  useEffect(() => setMenuAberto(false), [pathname])

  useEffect(() => {
    // Gera as cobranças semanais dos contratos ativos ao abrir o app.
    // É idempotente (UNIQUE(contract_id, period_start)) — por isso não precisa de cron.
    api.post('/contracts/generate-charges').catch(() => {
      /* silencioso: não é motivo para bloquear o app */
    })
  }, [])

  return (
    <div className="flex min-h-screen">
      {/* Barra superior só no celular: abre a gaveta e mostra onde você está. */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 md:hidden">
        <button
          onClick={() => setMenuAberto(true)}
          aria-label="Abrir menu"
          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
        >
          <Menu size={20} />
        </button>
        <span className="font-semibold text-slate-900">GM Locações</span>
      </header>

      {/* Fundo escuro: no celular, tocar fora fecha a gaveta. */}
      {menuAberto && (
        <div
          onClick={() => setMenuAberto(false)}
          className="fixed inset-0 z-30 bg-slate-900/40 md:hidden"
          aria-hidden
        />
      )}

      <aside
        className={cn(
          'flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white',
          // No celular vira gaveta deslizante; do md para cima, a barra fixa de sempre.
          'fixed inset-y-0 left-0 z-40 transition-transform md:static md:translate-x-0',
          menuAberto ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="text-lg font-semibold text-slate-900">GM Locações</div>
          <div className="text-xs text-slate-500">Gestão de frota</div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {[...NAV, ...(user?.role === 'admin' ? NAV_ADMIN : [])].map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-3">
          <div className="px-3 py-2">
            <div className="truncate text-sm font-medium text-slate-700">{user?.full_name}</div>
            <div className="truncate text-xs text-slate-500">{user?.email}</div>
          </div>
          <button
            onClick={logout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <LogOut size={18} />
            Sair
          </button>
        </div>
      </aside>

      {/* pt-14 abre espaço para a barra superior do celular; md:pt-8 a dispensa.
          Padding menor no telefone: 32 px de margem custam 16% da largura útil. */}
      <main id="conteudo" className="min-w-0 flex-1 overflow-x-hidden p-4 pt-18 md:p-8">
        {/* Sem este aviso, o visitante clica em "Novo veículo", toma 403 e conclui que o
            sistema está quebrado. Dizer antes transforma limite em informação. */}
        {user?.role === 'demonstracao' && (
          <div className="mb-6 flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
            <Eye size={16} className="mt-0.5 shrink-0" />
            <span>
              <strong>Modo demonstração.</strong> Os dados são fictícios e a navegação é livre —
              mas nada pode ser criado, alterado ou excluído.
            </span>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}
