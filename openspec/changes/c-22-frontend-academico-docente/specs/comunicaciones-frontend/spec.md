# Spec: Comunicaciones Frontend (F3.1, F3.2, F3.3)

## Archivos

```
frontend/src/features/comunicaciones/
├── pages/
│   ├── ComunicacionesPage.tsx
│   ├── NuevaComunicacionPage.tsx
│   └── LoteDetallePage.tsx
├── components/
│   ├── PreviewModal.tsx
│   ├── ComunicacionesTable.tsx
│   ├── EstadoBadge.tsx
│   └── AprobacionPanel.tsx
├── hooks/
│   ├── useComunicaciones.ts
│   ├── usePreview.ts
│   └── useLote.ts
├── services/
│   └── comunicacionesService.ts
└── types/
    └── comunicaciones.types.ts
```

---

## ComunicacionesPage (F3.2, F3.3)

**Ruta**: `/comunicaciones`
**Guard**: `comunicacion:enviar`

Vista principal con dos secciones:

### Sección A — Lista de comunicaciones (tabla filtrable)

**Endpoint**: `GET /api/v1/comunicaciones`

Filtros (query params):
- `estado`: dropdown PENDIENTE / ENVIANDO / ENVIADO / ERROR / CANCELADO
- `lote_id`: UUID (campo de texto libre)

Columnas de la tabla:
- Lote ID (truncado, link a `/comunicaciones/lotes/:loteId`)
- Estado (badge)
- Asunto (truncado a 60 chars)
- Creado (fecha/hora)
- Enviado (fecha/hora, vacío si no enviado)

Click en fila → navega a `/comunicaciones/lotes/:loteId`.

### Sección B — Panel de aprobación (F3.3)

Visible **solo** si `usePermission('comunicacion:aprobar')` es true.

Muestra la lista de lotes en estado PENDIENTE que requieren aprobación:
- Endpoint: `GET /api/v1/comunicaciones?estado=PENDIENTE`
- Por lote (agrupados por `lote_id`): fecha, asunto, N mensajes pendientes

Acciones por lote:
- **Aprobar** → `POST /api/v1/comunicaciones/lotes/{lote_id}/aprobar`
- **Cancelar lote** → `POST /api/v1/comunicaciones/lotes/{lote_id}/cancelar`

Después de aprobar o cancelar → invalida queries y muestra toast.

---

## NuevaComunicacionPage (F3.1, F3.2)

**Ruta**: `/comunicaciones/nuevo`
**Guard**: `comunicacion:enviar`

### Estado inicial

Al montar, lee `location.state`:
```typescript
const { entrada_padron_ids, materia_id, cohorte_id } = location.state ?? {}
```

Validación con Zod:
```typescript
const stateSchema = z.object({
  entrada_padron_ids: z.array(z.string().uuid()).min(1),
  materia_id: z.string().uuid(),
  cohorte_id: z.string().uuid(),  // requerido (OQ-C22-03 resuelto: siempre viene de AtrasadosPage)
})
```

Si el state no es válido (página accedida directamente sin state), muestra:
"No hay alumnos seleccionados. Ir a Atrasados para seleccionar." con link.

### Formulario (React Hook Form + Zod)

```typescript
const formSchema = z.object({
  asunto: z.string().min(1, 'Requerido').max(500),
  cuerpo: z.string().min(1, 'Requerido'),
})
```

**Valores por defecto** (plantilla, resolución de OQ-C22-06 opción B):
```typescript
defaultValues: {
  asunto: 'Recordatorio de actividades pendientes',
  cuerpo: `Hola {nombre} {apellidos},\n\nTe escribimos para informarte que tenés actividades pendientes.\nPor favor, revisá tu estado académico en la plataforma.\n\nSaludos del equipo docente.`,
}
```

**Info de variables**: tooltip sobre el campo `cuerpo` con:
"Podés usar {nombre}, {apellidos}, {materia} — se reemplazarán por los datos de cada alumno."

**Contador**: "Enviando a N alumnos" (N = `entrada_padron_ids.length`).

### Flujo de vista previa (F3.1, RN-16)

Botón "Ver previa" → llama `usePreview.mutate({...})`:
```typescript
const previewPayload: PreviewRequest = {
  destinatarios: entrada_padron_ids,   // campo API: "destinatarios"
  materia_id,
  cohorte_id,                          // requerido
  asunto_template: form.getValues('asunto'),
  cuerpo_template: form.getValues('cuerpo'),
}
```

Abre `PreviewModal` con la respuesta.

### PreviewModal

Muestra los primeros 3 previews (si hay más, "... y N más").
Por cada `PreviewItem`: nombre del alumno, asunto renderizado, cuerpo renderizado.

Botones:
- "Cancelar" → cierra el modal, vuelve al formulario
- "Confirmar envío" → cierra el modal, llama `useLote.mutate({...})`

### Envío del lote

```typescript
const lotePayload: CrearLoteRequest = {
  destinatarios: entrada_padron_ids,   // campo API: "destinatarios"
  materia_id,
  cohorte_id,
  asunto_template: form.getValues('asunto'),
  cuerpo_template: form.getValues('cuerpo'),
}
```

**Respuesta `LoteCreado`** (campo `total_encolados`, no `comunicaciones_creadas`):
- Si `requiere_aprobacion=false`: toast "Mensajes enviados a la cola. Se procesarán en instantes." → navega a `/comunicaciones/lotes/:loteId`
- Si `requiere_aprobacion=true`: toast "Lote enviado. Aguarda aprobación de coordinación." → navega a `/comunicaciones/lotes/:loteId`

---

## LoteDetallePage

**Ruta**: `/comunicaciones/lotes/:loteId`
**Guard**: `comunicacion:enviar`
**Endpoint**: `GET /api/v1/comunicaciones/lotes/{loteId}`

Muestra el estado de todos los mensajes del lote.

**Polling automático**: si algún mensaje está en estado PENDIENTE o ENVIANDO, hacer refetch cada 5s:
```typescript
useQuery({
  queryKey: ['lote', loteId],
  queryFn: () => comunicacionesService.getLote(loteId),
  refetchInterval: (data) => {
    const activos = data?.items.some(    // campo real: "items" (no "comunicaciones")
      c => c.estado === 'PENDIENTE' || c.estado === 'ENVIANDO'
    )
    return activos ? 5000 : false
  },
})
```

**Resumen**: contador por estado en badges.

**Tabla de mensajes**:
Columnas: Estado, Asunto (truncado), Enviado, Acciones

Acción "Cancelar" por mensaje (solo si `estado === 'PENDIENTE'`):
- `POST /api/v1/comunicaciones/{com_id}/cancelar`
- Requiere `comunicacion:aprobar`
- Si el usuario no tiene ese permiso, ocultar el botón

**Panel de aprobación del lote** (si hay mensajes PENDIENTE y el usuario tiene `comunicacion:aprobar`):
Botones:
- "Aprobar todo el lote" → `POST /api/v1/comunicaciones/lotes/{loteId}/aprobar`
- "Cancelar todo el lote" → `POST /api/v1/comunicaciones/lotes/{loteId}/cancelar`

---

## EstadoBadge

```typescript
const ESTADO_COLORS: Record<EstadoComunicacion, string> = {
  PENDIENTE:  'bg-yellow-100 text-yellow-800',
  ENVIANDO:   'bg-blue-100 text-blue-800',
  ENVIADO:    'bg-green-100 text-green-800',
  ERROR:      'bg-red-100 text-red-800',
  CANCELADO:  'bg-gray-100 text-gray-600',
}

const ESTADO_LABELS: Record<EstadoComunicacion, string> = {
  PENDIENTE:  'Pendiente',
  ENVIANDO:   'Enviando',
  ENVIADO:    'Enviado',
  ERROR:      'Error',
  CANCELADO:  'Cancelado',
}
```

---

## comunicacionesService.ts

```typescript
export const comunicacionesService = {
  preview(payload: PreviewRequest): Promise<PreviewResponse> {
    return api.post('/api/v1/comunicaciones/preview', payload).then(r => r.data)
  },
  crearLote(payload: CrearLoteRequest): Promise<LoteCreado> {
    return api.post('/api/v1/comunicaciones/lotes', payload).then(r => r.data)
  },
  getLote(loteId: string): Promise<LoteDetalle> {
    return api.get(`/api/v1/comunicaciones/lotes/${loteId}`).then(r => r.data)
  },
  aprobarLote(loteId: string): Promise<void> {
    return api.post(`/api/v1/comunicaciones/lotes/${loteId}/aprobar`).then(() => undefined)
  },
  cancelarLote(loteId: string): Promise<void> {
    return api.post(`/api/v1/comunicaciones/lotes/${loteId}/cancelar`).then(() => undefined)
  },
  cancelarIndividual(comId: string): Promise<void> {
    return api.post(`/api/v1/comunicaciones/${comId}/cancelar`).then(() => undefined)
  },
  listar(params?: { estado?: EstadoComunicacion; lote_id?: string }): Promise<ComunicacionListResponse> {
    return api.get('/api/v1/comunicaciones', { params }).then(r => r.data)
  },
}
```

---

## AppShell — ítems nuevos

Agregar al array `navItems` en `AppShell.tsx`:
```typescript
{ label: 'Comunicaciones', to: '/comunicaciones', permission: 'comunicacion:enviar' },
{ label: 'Monitor', to: '/monitor', permission: 'atrasados:ver' },
```

(Calificaciones ya estaba como ítem con `calificaciones:importar`.)

---

## Esquema de tests (TDD)

| Archivo | Tests |
|---------|-------|
| `NuevaComunicacionPage.test.tsx` | sin state → mensaje de error; con state válido renderiza formulario; valores default pre-llenados; botón "Ver previa" llama usePreview; PreviewModal muestra hasta 3 previews; confirmar llama crearLote; lote con requiere_aprobacion=true muestra toast correcto |
| `PreviewModal.test.tsx` | muestra ítems del preview; "y N más" si > 3; cancelar cierra; confirmar llama callback |
| `ComunicacionesPage.test.tsx` | tabla con datos; filtro por estado; panel aprobación visible solo con permiso; aprobar lote llama endpoint; cancelar lote llama endpoint |
| `LoteDetallePage.test.tsx` | tabla de mensajes con EstadoBadge; polling activo si hay PENDIENTE; cancelar individual oculto sin permiso; panel aprobación visible con permiso |
| `EstadoBadge.test.tsx` | cada estado tiene color correcto; label legible |
| `AprobacionPanel.test.tsx` | visible con comunicacion:aprobar; oculto sin permiso; aprobar llama servicio; cancelar llama servicio |
| `comunicacionesService.test.ts` | preview POST con payload correcto; crearLote retorna LoteCreado; getLote retorna detalle; cancelar individual DELETE correct |
| `usePreview.test.ts` | mutación llama service; isPending=true durante; error propagado al caller |
| `useLote.test.ts` | refetchInterval=5000 si hay PENDIENTE; refetchInterval=false si todos terminados |
