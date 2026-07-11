import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { Spinner } from './components/ui'
import { AuthProvider, useAuth } from './features/auth/AuthContext'
import { LoginPage } from './features/auth/LoginPage'
import { ContractsPage } from './features/contracts/ContractsPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { DriversPage } from './features/drivers/DriversPage'
import { ExpensesPage } from './features/expenses/ExpensesPage'
import { FinesPage } from './features/fines/FinesPage'
import { InspectionDetailPage } from './features/inspections/InspectionDetailPage'
import { InspectionsPage } from './features/inspections/InspectionsPage'
import { MaintenancesPage } from './features/maintenances/MaintenancesPage'
import { ReceivablesPage } from './features/revenues/ReceivablesPage'
import { RevenuesPage } from './features/revenues/RevenuesPage'
import { VehicleDetailPage } from './features/vehicles/VehicleDetailPage'
import { VehiclesPage } from './features/vehicles/VehiclesPage'

function Protected() {
  const { user, loading } = useAuth()
  if (loading) return <Spinner label="Entrando…" />
  if (!user) return <LoginPage />
  return <Layout />
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Protected />}>
            <Route index element={<DashboardPage />} />
            <Route path="veiculos" element={<VehiclesPage />} />
            {/* A conta do veículo — a tela mais importante do produto. */}
            <Route path="veiculos/:id" element={<VehicleDetailPage />} />
            <Route path="motoristas" element={<DriversPage />} />
            <Route path="contratos" element={<ContractsPage />} />
            <Route path="cobrancas" element={<ReceivablesPage />} />
            <Route path="receitas" element={<RevenuesPage />} />
            <Route path="despesas" element={<ExpensesPage />} />
            <Route path="manutencoes" element={<MaintenancesPage />} />
            <Route path="multas" element={<FinesPage />} />
            <Route path="vistorias" element={<InspectionsPage />} />
            <Route path="vistorias/:id" element={<InspectionDetailPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
