import { useEffect } from 'react'

import {
  Car,
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  LogOut,
  Receipt,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  UserCog,
  Users,
  Wrench,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { api } from '../api/client'
import { useAuth } from '../features/auth/AuthContext'
import { cn } from './ui'

const NAV = [
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
const NAV_ADMIN = [{ to: '/usuarios', label: 'Usuários', icon: UserCog }]

export function Layout() {
  const { user, logout } = useAuth()

  useEffect(() => {
    // Gera as cobranças semanais dos contratos ativos ao abrir o app.
    // É idempotente (UNIQUE(contract_id, period_start)) — por isso não precisa de cron.
    api.post('/contracts/generate-charges').catch(() => {
      /* silencioso: não é motivo para bloquear o app */
    })
  }, [])

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
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

      <main id="conteudo" className="flex-1 overflow-x-hidden p-8">
        <Outlet />
      </main>
    </div>
  )
}
