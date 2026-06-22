import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { ForgotPasswordPage } from '@/features/auth/pages/ForgotPasswordPage'
import { ResetPasswordPage } from '@/features/auth/pages/ResetPasswordPage'
import { ProtectedRoute } from '@/shared/components/ProtectedRoute'
import { AppShell } from '@/shared/components/AppShell'
import { CalificacionesHomePage } from '@/features/calificaciones/pages/CalificacionesHomePage'
import { MateriaDashboardPage } from '@/features/calificaciones/pages/MateriaDashboardPage'
import { ImportarPage } from '@/features/calificaciones/pages/ImportarPage'
import { MonitorPage } from '@/features/monitor/pages/MonitorPage'
import { ComunicacionesPage } from '@/features/comunicaciones/pages/ComunicacionesPage'

const DashboardPlaceholder = () => (
  <div className="p-8">
    <h1 className="text-2xl font-bold">Dashboard</h1>
  </div>
)

const ForbiddenPage = () => (
  <div className="p-8">
    <h1 className="text-2xl font-bold text-red-600">403 — Sin permisos</h1>
    <p className="mt-2 text-gray-600">No tenés acceso a esta sección.</p>
  </div>
)

const TabPlaceholder = ({ label }: { label: string }) => (
  <div className="py-8 text-center text-gray-400">{label} — próximamente</div>
)

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/403" element={<ForbiddenPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPlaceholder />} />

          {/* Calificaciones */}
          <Route element={<ProtectedRoute requiredPermission="calificaciones:importar" />}>
            <Route path="calificaciones" element={<CalificacionesHomePage />} />
          </Route>
          <Route element={<ProtectedRoute requiredPermission="atrasados:ver" />}>
            <Route path="calificaciones/:materiaId/:cohorteId" element={<MateriaDashboardPage />}>
              <Route index element={<Navigate to="importar" replace />} />
              <Route
                element={<ProtectedRoute requiredPermission="calificaciones:importar" />}
              >
                <Route path="importar" element={<ImportarPage />} />
              </Route>
              <Route path="atrasados" element={<TabPlaceholder label="Atrasados" />} />
              <Route path="ranking" element={<TabPlaceholder label="Ranking" />} />
              <Route path="notas-finales" element={<TabPlaceholder label="Notas finales" />} />
              <Route path="sin-corregir" element={<TabPlaceholder label="Sin corregir" />} />
            </Route>
          </Route>

          {/* Monitor */}
          <Route element={<ProtectedRoute requiredPermission="atrasados:ver" />}>
            <Route path="monitor" element={<MonitorPage />} />
          </Route>

          {/* Comunicaciones */}
          <Route element={<ProtectedRoute requiredPermission="comunicacion:enviar" />}>
            <Route path="comunicaciones" element={<ComunicacionesPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
