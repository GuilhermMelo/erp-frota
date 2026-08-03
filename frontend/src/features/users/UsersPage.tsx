/**
 * Usuários do sistema — quem tem login.
 *
 * Motorista NÃO entra aqui: motorista é dado, não usuário (ver DriversPage).
 *
 * Dois papéis. `operador` toca a operação do dia; `admin` faz o que não tem volta —
 * vender veículo, excluir lançamento, mexer em usuário. São 19 endpoints exigindo admin.
 *
 * Não existe excluir: usuário se DESATIVA. O log de auditoria guarda `actor_email` e aponta
 * para quem fez cada mudança; apagar a linha deixaria o histórico órfão de contexto.
 */

import { useState } from 'react'

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { api, errorMessage } from '../../api/client'
import {
  Badge,
  Button,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { useAuth } from '../auth/AuthContext'

type UserRole = 'admin' | 'operador'

type SystemUser = {
  id: string
  code: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  last_login_at: string | null
}

const ROLES: Record<UserRole, { label: string; className: string; ajuda: string }> = {
  admin: {
    label: 'Administrador',
    className: 'bg-indigo-100 text-indigo-800',
    ajuda: 'Faz tudo, inclusive o que não tem volta: vender veículo, excluir lançamento, mexer em usuários.',
  },
  operador: {
    label: 'Operador',
    className: 'bg-slate-100 text-slate-700',
    ajuda: 'Toca a operação do dia a dia. Não vende veículo, não exclui lançamento e não mexe em usuários.',
  },
}

/* ---------------------------------------------------------------- formulário */

// A senha é opcional na EDIÇÃO (em branco = mantém a atual) e obrigatória na criação.
// O mínimo de 8 e o máximo de 72 espelham o schema do backend: o bcrypt trunca acima
// de 72 bytes, e uma senha truncada em silêncio é pior que uma senha recusada.
const userSchema = z.object({
  full_name: z.string().trim().min(2, 'Informe o nome completo.').max(120),
  email: z.string().trim().email('E-mail inválido.'),
  role: z.enum(['admin', 'operador']),
  is_active: z.enum(['sim', 'nao']),
  password: z
    .string()
    .refine((v) => v === '' || (v.length >= 8 && v.length <= 72), 'A senha deve ter de 8 a 72 caracteres.'),
})

type UserForm = z.infer<typeof userSchema>

const EMPTY: UserForm = {
  full_name: '',
  email: '',
  role: 'operador',
  is_active: 'sim',
  password: '',
}

function UserFormModal({ user, onClose }: { user: SystemUser | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { user: eu } = useAuth()
  const isEdit = user !== null

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<UserForm>({
    resolver: zodResolver(userSchema),
    defaultValues: user
      ? {
          full_name: user.full_name,
          email: user.email,
          role: user.role,
          is_active: user.is_active ? 'sim' : 'nao',
          password: '',
        }
      : EMPTY,
  })

  const salvar = useMutation({
    mutationFn: (form: UserForm) => {
      if (isEdit) {
        // PATCH parcial: só mandamos a senha se ela foi preenchida. Mandar "" faria o
        // backend recusar (min_length=8) numa edição que nem queria trocar senha.
        const payload: Record<string, unknown> = {
          full_name: form.full_name.trim(),
          role: form.role,
          is_active: form.is_active === 'sim',
        }
        if (form.password) payload.password = form.password
        return api.patch(`/users/${user.id}`, payload)
      }
      return api.post('/users', {
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        role: form.role,
        password: form.password,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })

  // Tirar o próprio admin do ar (ou rebaixar-se) tranca o dono para fora do sistema.
  const souEu = isEdit && user.id === eu?.id
  const vouMePerder = souEu && (watch('is_active') === 'nao' || watch('role') !== 'admin')

  return (
    <Modal open onClose={onClose} title={isEdit ? `Editar ${user.code}` : 'Novo usuário'}>
      <form onSubmit={handleSubmit((form) => salvar.mutate(form))} className="space-y-4">
        <Field label="Nome completo" required error={errors.full_name?.message}>
          <Input autoFocus {...register('full_name')} />
        </Field>

        <Field
          label="E-mail"
          required
          error={errors.email?.message}
          hint={isEdit ? 'O e-mail não muda: é com ele que o log de auditoria aponta quem fez o quê.' : undefined}
        >
          <Input type="email" disabled={isEdit} {...register('email')} />
        </Field>

        <Field label="Papel" required error={errors.role?.message} hint={ROLES[watch('role')].ajuda}>
          <Select {...register('role')}>
            {Object.entries(ROLES).map(([value, { label }]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>

        {isEdit && (
          <Field label="Situação" required error={errors.is_active?.message}>
            <Select {...register('is_active')}>
              <option value="sim">Ativo</option>
              <option value="nao">Inativo (não consegue entrar)</option>
            </Select>
          </Field>
        )}

        <Field
          label={isEdit ? 'Nova senha' : 'Senha'}
          required={!isEdit}
          error={errors.password?.message}
          hint={isEdit ? 'Deixe em branco para manter a senha atual.' : 'Mínimo de 8 caracteres.'}
        >
          <Input type="password" autoComplete="new-password" {...register('password')} />
        </Field>

        {vouMePerder && (
          <ErrorBox message="Você está desativando ou rebaixando a SUA própria conta de administrador. Se salvar, perde o acesso." />
        )}

        {salvar.isError && <ErrorBox message={errorMessage(salvar.error)} />}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={salvar.isPending}>
            {isEdit ? 'Salvar alterações' : 'Cadastrar usuário'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------------------------------------------------------------- lista */

export function UsersPage() {
  const [editando, setEditando] = useState<SystemUser | null>(null)
  const [criando, setCriando] = useState(false)

  const users = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get<SystemUser[]>('/users').then((r) => r.data),
  })

  return (
    <>
      <PageHeader
        title="Usuários"
        subtitle="Quem tem login no sistema. Motorista não entra aqui — motorista é dado, não usuário."
        action={
          <Button onClick={() => setCriando(true)}>
            <Plus size={16} />
            Novo usuário
          </Button>
        }
      />

      {users.isPending ? (
        <Spinner />
      ) : users.isError ? (
        <ErrorBox message={errorMessage(users.error)} />
      ) : users.data.length === 0 ? (
        <EmptyState message="Nenhum usuário cadastrado." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Nome</Th>
              <Th>E-mail</Th>
              <Th>Papel</Th>
              <Th>Situação</Th>
              <Th>Último acesso</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {users.data.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50">
                <Td className="font-mono text-xs text-slate-500">{u.code}</Td>
                <Td className="font-medium text-slate-900">{u.full_name}</Td>
                <Td className="text-slate-600">{u.email}</Td>
                <Td>
                  <Badge label={ROLES[u.role].label} className={ROLES[u.role].className} />
                </Td>
                <Td>
                  <Badge
                    label={u.is_active ? 'Ativo' : 'Inativo'}
                    className={u.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}
                  />
                </Td>
                <Td className="text-slate-600">
                  {u.last_login_at ? formatDateTime(u.last_login_at) : 'nunca entrou'}
                </Td>
                <Td className="text-right">
                  <Button variant="ghost" onClick={() => setEditando(u)} title="Editar">
                    <Pencil size={16} />
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {criando && <UserFormModal user={null} onClose={() => setCriando(false)} />}
      {editando && <UserFormModal user={editando} onClose={() => setEditando(null)} />}
    </>
  )
}
