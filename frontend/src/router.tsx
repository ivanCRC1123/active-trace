import { type ReactNode } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { useSessionStore } from '@/store/sessionStore'

const DashboardPlaceholder = () => (
  <div className="p-8">
    <h1 className="text-2xl font-bold">Dashboard</h1>
  </div>
)

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useSessionStore((s) => s.accessToken)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <DashboardPlaceholder />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
