import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { Button, Card, ErrorBox, Field, Input } from '../../components/ui'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <Card className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-semibold text-slate-900">GM Locações</h1>
          <p className="mt-1 text-sm text-slate-500">Entre com sua conta de funcionário</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <Field label="E-mail" required>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>

          <Field label="Senha" required>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          {error && <ErrorBox message={error} />}

          <Button type="submit" loading={loading} className="w-full">
            Entrar
          </Button>
        </form>
      </Card>
    </div>
  )
}
