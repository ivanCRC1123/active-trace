## ADDED Requirements

### Requirement: Frontend project scaffold with Vite, React 18, TypeScript, Tailwind, TanStack Query, React Hook Form, Zod, Axios, and Zustand

The project SHALL exist as a standalone directory `frontend/` at the repository root. It SHALL be bootstrapped with Vite (`@vitejs/plugin-react`), React 18, TypeScript (strict mode), Tailwind CSS, TanStack Query v5, React Hook Form v7 + Zod v3, Axios v1, Zustand v4, React Router DOM v6, and Vitest + Testing Library + MSW for tests. The directory structure SHALL follow the feature-based layout defined in `docs/ARQUITECTURA.md §4`.

#### Scenario: Project builds without errors
- **WHEN** `npm run build` is executed in `frontend/`
- **THEN** Vite compiles the project without TypeScript errors, unused import errors, or lint errors
- **AND** the output is in `frontend/dist/`

#### Scenario: TypeScript strict mode enforced
- **GIVEN** `tsconfig.json` with `"strict": true`, `"noImplicitAny": true`, `"noUnusedLocals": true`
- **WHEN** any file uses `any` or leaves an unused variable
- **THEN** `npm run typecheck` (`tsc --noEmit`) reports an error

#### Scenario: Tailwind CSS is available in components
- **GIVEN** `tailwind.config.ts` with content glob matching `./src/**/*.{ts,tsx}`
- **WHEN** a component uses a Tailwind class like `className="bg-blue-500 text-white"`
- **THEN** the class is present and styled in the output

#### Scenario: TanStack Query provider wraps the app
- **GIVEN** `main.tsx` wraps `<App />` with `<QueryClientProvider client={queryClient}>`
- **WHEN** any component uses `useQuery` or `useMutation`
- **THEN** the hook resolves without "No QueryClient found" error

#### Scenario: Feature-based folder structure matches architecture spec
- **GIVEN** the `src/` directory
- **THEN** it SHALL contain:
  - `features/auth/{components,hooks,services,types,pages}/`
  - `shared/services/api.ts`
  - `shared/components/`
  - `shared/hooks/`
  - `store/sessionStore.ts`
  - `main.tsx`, `App.tsx`, `router.tsx`

#### Scenario: Docker multi-stage build succeeds
- **GIVEN** `frontend/Dockerfile` with a Node build stage and an nginx serve stage
- **WHEN** `docker build -t frontend .` is executed from `frontend/`
- **THEN** the image builds without error
- **AND** running the container serves the Vite build on port 80

#### Scenario: Path alias @/ resolves to src/
- **GIVEN** `vite.config.ts` with `resolve.alias: { '@': path.resolve(__dirname, 'src') }`
- **AND** `tsconfig.json` with `"paths": { "@/*": ["src/*"] }`
- **WHEN** a file imports `import { api } from '@/shared/services/api'`
- **THEN** the import resolves correctly without relative path traversal

### Requirement: Test runner configured with Vitest and Testing Library

The project SHALL use Vitest with `jsdom` environment, `@testing-library/react`, `@testing-library/user-event`, and MSW for HTTP mocking. `npm test` SHALL run all tests in `src/**/*.test.tsx?`.

#### Scenario: Test suite runs without setup errors
- **WHEN** `npm test` is executed with no tests yet (empty test files)
- **THEN** Vitest starts, finds 0 tests, and exits 0

#### Scenario: MSW server can mock API calls in tests
- **GIVEN** an MSW handler for `POST /api/auth/login` returning a mocked `LoginResponse`
- **WHEN** a test renders a component that calls `authService.login()`
- **THEN** the component receives the mocked response without making a real HTTP request
