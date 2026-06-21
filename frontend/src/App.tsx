import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './router'
import { useBootstrap } from '@/shared/hooks/useBootstrap'

function BootstrapWrapper() {
  const bootstrapping = useBootstrap()

  if (bootstrapping) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <span className="text-gray-500 text-sm">Cargando...</span>
      </div>
    )
  }

  return <AppRoutes />
}

function App() {
  return (
    <BrowserRouter>
      <BootstrapWrapper />
    </BrowserRouter>
  )
}

export default App
