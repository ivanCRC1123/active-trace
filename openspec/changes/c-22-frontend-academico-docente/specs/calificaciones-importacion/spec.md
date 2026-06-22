# Spec: Importación de Calificaciones y Umbral (F1.1, F2.1)

## Archivos

```
frontend/src/features/calificaciones/
├── pages/
│   ├── CalificacionesHomePage.tsx
│   ├── MateriaDashboardPage.tsx
│   └── ImportarPage.tsx
├── components/
│   ├── UploadZone.tsx
│   ├── ActividadesSelector.tsx
│   ├── UmbralForm.tsx
│   ├── ReporteRapidoCards.tsx
│   └── MateriaNav.tsx
├── hooks/
│   ├── useImportarCalificaciones.ts
│   ├── useUmbral.ts
│   └── useReporteRapido.ts
├── services/
│   └── calificacionesService.ts
└── types/
    └── calificaciones.types.ts
```

---

## CalificacionesHomePage

**Ruta**: `/calificaciones`
**Guard**: `calificaciones:importar`

Muestra la lista de materias activas del usuario para que seleccione cuál trabajar.

### Dependencia OQ-C22-01

Esta página requiere un endpoint `GET /api/v1/me/asignaciones` (aún no existe).
Mientras OQ-C22-01 no esté resuelto, la página muestra un mensaje placeholder
"Seleccioná una materia" con un campo manual de URL o breadcrumb.

### Cuando OQ-C22-01 esté resuelto

```tsx
// useMyAsignaciones.ts
export function useMyAsignaciones() {
  return useQuery({
    queryKey: ['me', 'asignaciones'],
    queryFn: () => api.get('/api/v1/me/asignaciones').then(r => r.data),
  })
}
```

La página renderiza una lista de cards (materia × cohorte). Click en card → navega a
`/calificaciones/:materiaId/:cohorteId`.

---

## MateriaDashboardPage

**Ruta**: `/calificaciones/:materiaId/:cohorteId`
**Guard**: `atrasados:ver`

Vista central de una materia. Dos secciones:
1. `ReporteRapidoCards` — KPIs del estado actual (si hay datos importados)
2. `MateriaNav` — tabs/links a sub-vistas: Importar, Atrasados, Ranking, Notas Finales, Sin Corregir

### Estado sin datos

Si `tiene_datos=false` en la respuesta de `/reportes-rapidos`, muestra un banner
"No hay calificaciones importadas" con un botón de acceso directo a ImportarPage.

### Hooks
```typescript
const { materiaId, cohorteId } = useParams()
const { data: reporte } = useReporteRapido(materiaId!, cohorteId!)
```

---

## ImportarPage

**Ruta**: `/calificaciones/:materiaId/:cohorteId/importar`
**Guard**: `calificaciones:importar`

### Wizard de 3 pasos

**Paso 1 — Upload**
- `UploadZone` acepta `.xlsx` y `.csv`
- `useMutation` llama a `calificacionesService.preview(materiaId, cohorteId, archivo)`
  ```typescript
  // calificacionesService.ts
  preview(materiaId: string, cohorteId: string, archivo: File): Promise<CalificacionesPreview> {
    const fd = new FormData()
    fd.append('archivo', archivo)
    fd.append('actividades', JSON.stringify([]))
    return api.post(`/api/v1/calificaciones/${materiaId}/cohortes/${cohorteId}/importar`, fd)
      .then(r => r.data)
  }
  ```
- Si la respuesta tiene `advertencias`, se muestran como alertas amarillas

**Paso 2 — Selección y Umbral**
- `ActividadesSelector`: lista de checkboxes con `nombre (tipo) — N notas`
  - Por defecto: todas marcadas
  - Tipo numérica/textual con badge de color
- `UmbralForm`: slider 1–100 (default 60) + lista editable de valores aprobatorios
  - `useUmbral(materiaId)` pre-carga el valor guardado del servidor
  - Guardar umbral es opcional (PUT inline, no requiere confirmar el wizard)

**Paso 3 — Confirmar**
- Botón "Importar calificaciones"
- `calificacionesService.importar(materiaId, cohorteId, actividades)`:
  ```typescript
  importar(materiaId: string, cohorteId: string, actividades: string[]): Promise<CalificacionesImportResult> {
    const fd = new FormData()
    fd.append('archivo', archivoGuardadoEnState)  // archivo del paso 1
    fd.append('actividades', JSON.stringify(actividades))
    return api.post(`/api/v1/calificaciones/${materiaId}/cohortes/${cohorteId}/importar`, fd)
      .then(r => r.data)
  }
  ```
- Muestra resultado: "X actividades importadas, Y calificaciones creadas"
- Botón "Ver análisis" → navega a `/calificaciones/:materiaId/:cohorteId/atrasados`

### Acción vaciar datos

Botón secundario "Vaciar mis calificaciones" con confirmación de diálogo.
```typescript
calificacionesService.vaciar(materiaId, cohorteId) {
  return api.delete(`/api/v1/calificaciones/${materiaId}/cohortes/${cohorteId}/vaciar`)
}
```
Después de vaciar, invalida `useAtrasados`, `useRanking`, `useNotasFinales`, `useReporteRapido`.

### Error handling
| Error | Mensaje UI |
|-------|-----------|
| 400 `archivo_invalido` | "El archivo no tiene el formato esperado (.xlsx o .csv)" |
| 400 `sin_columna_email` | "No se detectó columna de email en el archivo" |
| 409 `no_hay_padron_activo` | "No hay padrón de alumnos activo para esta materia/cohorte. Importá el padrón primero." |
| 400 `actividad_invalida` | "Algunas actividades seleccionadas no están en el archivo" |

---

## useImportarCalificaciones

```typescript
export function useImportarCalificaciones(materiaId: string, cohorteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ archivo, actividades }: ImportarArgs) =>
      calificacionesService.importar(materiaId, cohorteId, archivo, actividades),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['atrasados', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['ranking', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['notas-finales', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['reporte-rapido', materiaId, cohorteId] })
    },
  })
}
```

---

## useUmbral

```typescript
export function useUmbral(materiaId: string) {
  const query = useQuery({
    queryKey: ['umbral', materiaId],
    queryFn: () => calificacionesService.getUmbral(materiaId),
  })
  const mutation = useMutation({
    mutationFn: (data: UmbralMateriaRequest) =>
      calificacionesService.putUmbral(materiaId, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['umbral', materiaId], updated)
    },
  })
  return { ...query, update: mutation }
}
```

---

## ReporteRapidoCards

```typescript
// Si tiene_datos=false, muestra empty state
// Si tiene_datos=true, muestra 4 KPIs:
// - Total alumnos
// - Alumnos atrasados (badge rojo si > 0)
// - Total actividades
// - % aprobaciones
```

Componente < 80 LOC. Solo datos, sin botones de acción.

---

## Esquema de tests (TDD)

| Archivo | Tests |
|---------|-------|
| `ImportarPage.test.tsx` | step 1: upload dispara preview; step 2: checkboxes + umbral; step 3: confirm llama importar; error 409 muestra mensaje |
| `UploadZone.test.tsx` | drag & drop acepts xlsx; rechaza pdf; muestra nombre de archivo |
| `ActividadesSelector.test.tsx` | todos marcados por default; deselect individual; muestra tipo |
| `UmbralForm.test.tsx` | pre-carga valor del servidor; slider range 1-100; submit llama PUT |
| `ReporteRapidoCards.test.tsx` | renderiza KPIs; estado vacío muestra banner |
| `calificacionesService.test.ts` | preview usa actividades=[]; importar usa actividades correctas; vaciar llama DELETE |
| `useUmbral.test.ts` | carga umbral; actualiza y sincroniza cache |
