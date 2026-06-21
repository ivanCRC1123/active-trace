import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

it('renders App without crashing', () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { container } = render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  )
  expect(container.firstChild).not.toBeNull()
})
