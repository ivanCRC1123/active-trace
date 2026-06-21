import { Routes, Route } from 'react-router-dom'

const DashboardPlaceholder = () => (
  <div className="p-8">
    <h1 className="text-2xl font-bold">Dashboard</h1>
  </div>
)

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPlaceholder />} />
    </Routes>
  )
}
