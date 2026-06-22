# C-22 frontend-academico-docente — Design

## Estructura de features

```
frontend/src/features/
├── calificaciones/                    (F1.1, F2.1–F2.6)
│   ├── pages/
│   │   ├── CalificacionesHomePage.tsx  # Selección de materia/cohorte
│   │   ├── MateriaDashboardPage.tsx    # Reportes rápidos + nav secundaria
│   │   ├── ImportarPage.tsx            # Wizard: upload → preview → confirm + umbral
│   │   ├── AtrasadosPage.tsx           # Tabla atrasados + acción comunicar
│   │   ├── RankingPage.tsx             # Tabla ranking aprobadas
│   │   ├── NotasFinalesPage.tsx        # Tabla + export CSV
│   │   └── SinCorregirPage.tsx         # Upload finalización + tabla + export CSV
│   ├── components/
│   │   ├── UploadZone.tsx              # Drag & drop + file picker (<200 LOC)
│   │   ├── ActividadesSelector.tsx     # Checkboxes de actividades detectadas
│   │   ├── UmbralForm.tsx              # Slider % + valores aprobatorios
│   │   ├── AtrasadosTable.tsx          # Tabla con chips faltantes/bajo umbral
│   │   ├── RankingTable.tsx
│   │   ├── NotasFinalesTable.tsx
│   │   ├── ReporteRapidoCards.tsx      # KPIs (total_alumnos, atrasados, etc.)
│   │   └── MateriaNav.tsx              # Navegación secundaria (tabs o sidebar)
│   ├── hooks/
│   │   ├── useImportarCalificaciones.ts  # useMutation POST /importar
│   │   ├── useUmbral.ts                  # useQuery GET + useMutation PUT /umbral
│   │   ├── useAtrasados.ts               # useQuery GET /atrasados
│   │   ├── useRanking.ts                 # useQuery GET /ranking
│   │   ├── useNotasFinales.ts            # useQuery GET /notas-finales
│   │   ├── useSinCorregir.ts             # useMutation POST + useQuery GET /sin-corregir
│   │   └── useReporteRapido.ts           # useQuery GET /reportes-rapidos
│   ├── services/
│   │   └── calificacionesService.ts    # Calls a api.ts
│   └── types/
│       └── calificaciones.types.ts
│
├── monitor/                           (F2.7, F2.8, F2.9)
│   ├── pages/
│   │   └── MonitorPage.tsx
│   ├── components/
│   │   ├── MonitorFilters.tsx          # Filtros: alumno, comision, regional, estado, fechas
│   │   └── MonitorTable.tsx            # Tabla paginada con estado atrasado/al_día
│   ├── hooks/
│   │   └── useMonitor.ts               # useQuery GET /analisis/monitor con params
│   ├── services/
│   │   └── monitorService.ts
│   └── types/
│       └── monitor.types.ts
│
└── comunicaciones/                    (F3.1, F3.2, F3.3)
    ├── pages/
    │   ├── ComunicacionesPage.tsx      # Lista + panel aprobación (si tiene permiso)
    │   ├── NuevaComunicacionPage.tsx   # Formulario + preview modal + envío
    │   └── LoteDetallePage.tsx         # Estado de cada mensaje del lote
    ├── components/
    │   ├── PreviewModal.tsx            # F3.1: preview asunto/cuerpo renderizados
    │   ├── ComunicacionesTable.tsx     # Lista con filtros y estados
    │   ├── EstadoBadge.tsx             # PENDIENTE / ENVIANDO / ENVIADO / ERROR / CANCELADO
    │   └── AprobacionPanel.tsx         # F3.3: visible solo con comunicacion:aprobar
    ├── hooks/
    │   ├── useComunicaciones.ts        # useQuery GET /comunicaciones
    │   ├── usePreview.ts               # useMutation POST /preview
    │   └── useLote.ts                  # useMutation POST /lotes + useQuery GET /lotes/:id
    ├── services/
    │   └── comunicacionesService.ts
    └── types/
        └── comunicaciones.types.ts
```

## Rutas nuevas en `router.tsx`

```tsx
// Dentro del bloque ProtectedRoute bajo AppShell
<Route path="calificaciones" element={
  <ProtectedRoute permission="calificaciones:importar">
    <CalificacionesHomePage />
  </ProtectedRoute>
} />
<Route path="calificaciones/:materiaId/:cohorteId" element={
  <ProtectedRoute permission="atrasados:ver">
    <MateriaDashboardPage />
  </ProtectedRoute>
} />
<Route path="calificaciones/:materiaId/:cohorteId/importar" element={
  <ProtectedRoute permission="calificaciones:importar">
    <ImportarPage />
  </ProtectedRoute>
} />
<Route path="calificaciones/:materiaId/:cohorteId/atrasados" element={
  <ProtectedRoute permission="atrasados:ver">
    <AtrasadosPage />
  </ProtectedRoute>
} />
<Route path="calificaciones/:materiaId/:cohorteId/ranking" element={
  <ProtectedRoute permission="atrasados:ver">
    <RankingPage />
  </ProtectedRoute>
} />
<Route path="calificaciones/:materiaId/:cohorteId/notas-finales" element={
  <ProtectedRoute permission="atrasados:ver">
    <NotasFinalesPage />
  </ProtectedRoute>
} />
<Route path="calificaciones/:materiaId/:cohorteId/sin-corregir" element={
  <ProtectedRoute permission="atrasados:ver">
    <SinCorregirPage />
  </ProtectedRoute>
} />
<Route path="monitor" element={
  <ProtectedRoute permission="atrasados:ver">
    <MonitorPage />
  </ProtectedRoute>
} />
<Route path="comunicaciones" element={
  <ProtectedRoute permission="comunicacion:enviar">
    <ComunicacionesPage />
  </ProtectedRoute>
} />
<Route path="comunicaciones/nuevo" element={
  <ProtectedRoute permission="comunicacion:enviar">
    <NuevaComunicacionPage />
  </ProtectedRoute>
} />
<Route path="comunicaciones/lotes/:loteId" element={
  <ProtectedRoute permission="comunicacion:enviar">
    <LoteDetallePage />
  </ProtectedRoute>
} />
```

## Ítems de menú nuevos en AppShell

Estos ítems se agregan a la lista de navegación de `AppShell.tsx`:

| Label | Ruta | Permission |
|-------|------|------------|
| Calificaciones | `/calificaciones` | `calificaciones:importar` |
| Monitor | `/monitor` | `atrasados:ver` |
| Comunicaciones | `/comunicaciones` | `comunicacion:enviar` |

> Nota: "Calificaciones" ya está en la lista inicial de C-21. "Monitor" y "Comunicaciones" son nuevos.

## Flujo clave: ImportarPage (wizard de 3 pasos)

```
Paso 1 — Upload
  Usuario sube archivo xlsx
  → POST /api/v1/calificaciones/{mid}/cohortes/{cid}/importar
      body: { actividades: [] }   ← modo PREVIEW
  ← CalificacionesPreview { actividades_detectadas, alumnos_detectados, advertencias }

Paso 2 — Selección
  Usuario selecciona actividades (checkboxes) y configura umbral
  UmbralForm: GET /api/v1/umbral/{mid} (pre-carga valor actual)
  Usuario puede PUT /api/v1/umbral/{mid} (actualizar umbral)

Paso 3 — Confirmar
  → POST /api/v1/calificaciones/{mid}/cohortes/{cid}/importar
      body: { actividades: ["Actividad 1 (Real)", ...] }   ← modo CONFIRM
  ← CalificacionesImportResult { actividades_importadas, calificaciones_creadas, ... }
  Navega a MateriaDashboardPage
```

## Flujo clave: Comunicar desde AtrasadosPage

```
1. AtrasadosPage muestra tabla con checkboxes por alumno
2. Usuario selecciona alumnos → botón "Enviar comunicación" se activa
3. Click → navigate('/comunicaciones/nuevo', { state: { entrada_padron_ids, materia_id } })
4. NuevaComunicacionPage pre-carga las IDs desde location.state
5. Usuario escribe asunto + cuerpo (con variables {nombre}, {apellidos}, {materia})
6. Click "Vista previa" → POST /api/v1/comunicaciones/preview → PreviewModal (RN-16)
7. Usuario confirma → POST /api/v1/comunicaciones/lotes → LoteCreado
   Si requiere_aprobacion=true → toast informativo
8. Navega a /comunicaciones/lotes/:loteId para ver el estado
```

## Tipos TypeScript clave

### calificaciones.types.ts
```typescript
export interface ActividadDetectada {
  nombre: string
  tipo: 'numerica' | 'textual'
  total_notas: number
}
export interface CalificacionesPreview {
  actividades_detectadas: ActividadDetectada[]
  alumnos_detectados: number
  advertencias: string[]
}
export interface CalificacionesImportResult {
  actividades_importadas: number
  calificaciones_creadas: number
  calificaciones_actualizadas: number
  total_aprobadas: number
  advertencias: string[]
}
export interface UmbralMateriaResponse {
  id: string | null
  asignacion_id: string | null
  materia_id: string
  umbral_pct: number
  valores_aprobatorios: string[]
  es_default: boolean
}
export interface AlumnoAtrasado {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  regional: string | null
  actividades_faltantes: string[]
  actividades_bajo_umbral: string[]
}
export interface AtrasadosResponse {
  total_alumnos: number
  total_atrasados: number
  atrasados: AlumnoAtrasado[]
}
export interface RankingItem {
  posicion: number
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  total_aprobadas: number
  total_calificaciones: number
}
export interface NotaFinalAlumno {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  aprobadas: number
  total_calificaciones: number
  nota_final_pct: number | null
}
export interface EntregaSinCorregir {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  actividad: string
}
export interface SinCorregirResponse {
  items: EntregaSinCorregir[]
  total: number
  aviso: string | null
}
export interface ReporteRapidoResponse {
  total_alumnos: number
  total_actividades: number
  total_aprobaciones: number
  total_desaprobaciones: number
  alumnos_con_desaprobacion: number
  alumnos_atrasados: number
  tiene_datos: boolean
}
```

### comunicaciones.types.ts

> Tipos ajustados para coincidir con los schemas Pydantic reales de C-12
> (verificados en `backend/app/schemas/comunicaciones.py`).

```typescript
export type EstadoComunicacion = 'PENDIENTE' | 'ENVIANDO' | 'ENVIADO' | 'ERROR' | 'CANCELADO'

// ── Request/Response de PREVIEW ───────────────────────────────────────────
// NOTA: cohorte_id es requerido; campos nombrados _template; destinatarios (no entrada_padron_ids)
export interface PreviewRequest {
  destinatarios: string[]    // UUIDs de EntradaPadron — NO "entrada_padron_ids"
  materia_id: string
  cohorte_id: string         // requerido (no opcional)
  asunto_template: string    // NO "asunto"
  cuerpo_template: string    // NO "cuerpo"
}
export interface PreviewItem {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  asunto_renderizado: string
  cuerpo_renderizado: string
}
export interface PreviewResponse {
  items: PreviewItem[]
}

// ── Crear lote ────────────────────────────────────────────────────────────
export interface CrearLoteRequest {
  destinatarios: string[]    // UUIDs de EntradaPadron
  materia_id: string
  cohorte_id: string
  asunto_template: string
  cuerpo_template: string
}
export interface LoteCreado {
  lote_id: string
  total_encolados: number    // NO "comunicaciones_creadas"
  requiere_aprobacion: boolean
}

// ── Detalle de lote ───────────────────────────────────────────────────────
export interface ResumenEstados {
  PENDIENTE: number
  ENVIANDO: number
  ENVIADO: number
  ERROR: number
  CANCELADO: number
}
export interface ComunicacionItem {
  id: string
  entrada_padron_id: string | null
  nombre: string | null
  apellidos: string | null
  estado: EstadoComunicacion
  enviado_at: string | null
  aprobado_at: string | null
  // NO tiene asunto, cuerpo ni aprobado_por — ver real C-12
}
export interface LoteDetalle {
  lote_id: string
  materia_id: string
  enviado_por: string        // UUID del docente que creó el lote
  resumen_estados: ResumenEstados   // NO "resumen"
  items: ComunicacionItem[]  // NO "comunicaciones"
}

// ── Lista de comunicaciones ───────────────────────────────────────────────
export interface ComunicacionListResponse {
  items: ComunicacionItem[]
  total: number
}
```

### me.types.ts (nuevo — C-22 prep)

```typescript
// Asignación vigente del usuario autenticado
// Endpoint: GET /api/v1/me/asignaciones
export interface MeAsignacionItem {
  id: string
  materia_id: string | null
  materia_nombre: string | null
  carrera_id: string | null
  carrera_nombre: string | null
  cohorte_id: string | null
  cohorte_nombre: string | null
  comisiones: unknown[]
  rol_nombre: string
  desde: string         // YYYY-MM-DD
  hasta: string | null  // YYYY-MM-DD
}
```

### monitor.types.ts
```typescript
export interface MonitorItem {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  regional: string | null
  materia_id: string
  cohorte_id: string
  estado: 'atrasado' | 'al_dia'
  actividades_faltantes: string[]
  actividades_bajo_umbral: string[]
  total_aprobadas: number
  total_calificaciones: number
}
export interface MonitorResponse {
  items: MonitorItem[]
  total: number
  limit: number
  offset: number
}
export interface MonitorFilters {
  materia_id?: string
  cohorte_id?: string
  alumno?: string
  comision?: string
  regional?: string
  estado?: 'atrasado' | 'al_dia'
  fecha_desde?: string
  fecha_hasta?: string
  limit?: number
  offset?: number
}
```

---

## Open Questions — Resoluciones

Todas las OQs fueron resueltas. Registradas 2026-06-21.

| OQ | Decisión |
|----|----------|
| **OQ-C22-01** | ✅ SÍ agregar `GET /api/v1/me/asignaciones`. Implementado como prep de C-22 (router `me.py`). Tests: 4 passed. |
| **OQ-C22-02** | ✅ Tabs horizontales en `MateriaDashboardPage`. `MateriaNav.tsx` renderiza tabs; cada sub-vista es sub-ruta con `<Outlet>`. |
| **OQ-C22-03** | ✅ `navigate('/comunicaciones/nuevo', { state: { entrada_padron_ids, materia_id, cohorte_id } })`. NuevaComunicacionPage valida el state con Zod al montar. |
| **OQ-C22-04** | ✅ Usar C-11 (persistente): `POST /api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion` + `GET /sin-corregir`. |
| **OQ-C22-05** | ✅ Monitor como ítem propio en el menú (`/monitor`). PROFESOR lo ve con `atrasados:ver` (scope=own via backend). |
| **OQ-C22-06** | ✅ Plantilla por defecto con las variables que el backend REALMENTE soporta: `{nombre}`, `{apellidos}`, `{materia}` (verificado en `comunicacion_service.py::_build_template_ctx`). Ver plantilla abajo. |
| **OQ-C22-07** | ✅ CSV exports requieren `Authorization: Bearer`. Usar `api.get(url, { responseType: 'blob' })` + `URL.createObjectURL` + click programático. NO usar `window.open`. |

### Plantilla por defecto (OQ-C22-06)

Variables confirmadas: `{nombre}`, `{apellidos}`, `{materia}` únicamente.

```
Asunto: Recordatorio de actividades pendientes
Cuerpo:
Hola {nombre} {apellidos},

Te escribimos para informarte que tenés actividades pendientes.
Por favor, revisá tu estado académico en la plataforma.

Saludos del equipo docente.
```

> Nota: `{materia}` se puede usar en el cuerpo pero se omitió en el asunto para evitar
> líneas muy largas. El tooltip de variables informa al docente de las 3 disponibles.

---

## Reglas de implementación

- Todos los componentes < 200 LOC. Si crece, extraer sub-componentes.
- Sin `any`. Sin class components.
- Tailwind en JSX; no hay CSS modules.
- Todo fetch a través de los hooks de `features/*/hooks/`. No llamar directamente a `api.ts` desde componentes.
- `ProtectedRoute permission="..."` en cada ruta — no confiar en que el menú oculte rutas.
- **CSV export (OQ-C22-07 RESUELTO)**: Usar `api.get(url, { responseType: 'blob' })` (Axios) y luego `URL.createObjectURL(blob)` + click programático en anchor. NO usar `window.open` — los endpoints de exportar requieren el header `Authorization: Bearer` que `window.open` no puede enviar.
- Los `FormData` para file upload se construyen en el service, no en el componente.
