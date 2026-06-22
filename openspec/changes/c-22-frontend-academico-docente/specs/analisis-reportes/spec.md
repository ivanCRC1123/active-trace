# Spec: Análisis y Reportes (F2.2–F2.9)

## Archivos

```
frontend/src/features/calificaciones/
├── pages/
│   ├── AtrasadosPage.tsx
│   ├── RankingPage.tsx
│   ├── NotasFinalesPage.tsx
│   └── SinCorregirPage.tsx
├── components/
│   ├── AtrasadosTable.tsx
│   ├── RankingTable.tsx
│   └── NotasFinalesTable.tsx
├── hooks/
│   ├── useAtrasados.ts
│   ├── useRanking.ts
│   ├── useNotasFinales.ts
│   └── useSinCorregir.ts

frontend/src/features/monitor/
├── pages/
│   └── MonitorPage.tsx
├── components/
│   ├── MonitorFilters.tsx
│   └── MonitorTable.tsx
├── hooks/
│   └── useMonitor.ts
├── services/
│   └── monitorService.ts
└── types/
    └── monitor.types.ts
```

---

## AtrasadosPage (F2.2)

**Ruta**: `/calificaciones/:materiaId/:cohorteId/atrasados`
**Guard**: `atrasados:ver`
**Endpoint**: `GET /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/atrasados`

### Componente AtrasadosTable

Columnas: Apellidos, Nombre, Comisión, Regional, Actividades Faltantes, Bajo Umbral, ☐ Seleccionar

- **Actividades faltantes**: chips separados por actividad. Si la lista es larga (>3), colapsa con "+ N más".
- **Bajo umbral**: chips en rojo/naranja.
- **Checkbox**: permite seleccionar alumnos para comunicar.

Estado vacío (atrasados=[]):
- "Todos los alumnos están al día" con ícono de check verde.
- Si `total_alumnos=0`: "No hay calificaciones importadas. Importá primero."

### Acción "Enviar comunicación"

Botón habilitado solo si al menos un alumno está seleccionado.
Al hacer click:
```typescript
navigate('/comunicaciones/nuevo', {
  state: {
    entrada_padron_ids: selectedIds,
    materia_id: materiaId,
    cohorte_id: cohorteId,
  }
})
```

Requiere que el usuario tenga `comunicacion:enviar`. El botón solo se muestra si
`usePermission('comunicacion:enviar')` retorna true.

---

## RankingPage (F2.3)

**Ruta**: `/calificaciones/:materiaId/:cohorteId/ranking`
**Guard**: `atrasados:ver`
**Endpoint**: `GET /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/ranking`

### RankingTable

Columnas: #, Apellidos, Nombre, Comisión, Aprobadas, Total, Porcentaje

- `posicion` es 1-indexed (del backend).
- Porcentaje calculado en frontend: `(total_aprobadas / total_calificaciones * 100).toFixed(1)%`
- Badge de color en posición 1, 2, 3 (oro, plata, bronce).

Footer: "N alumnos incluidos (M excluidos sin ninguna aprobada)" — según `total_incluidos` y `total_excluidos`.

Estado vacío: "No hay ranking disponible. Importá calificaciones primero."

---

## NotasFinalesPage (F2.5)

**Ruta**: `/calificaciones/:materiaId/:cohorteId/notas-finales`
**Guard**: `atrasados:ver`
**Endpoints**:
- `GET /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/notas-finales`
- `GET /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/notas-finales/exportar` (CSV download)

### NotasFinalesTable

Columnas: Apellidos, Nombre, Comisión, Aprobadas, Total, Nota Final

- `nota_final_pct` formateado como `"80.00 %"`. Si es null, mostrar `"—"`.
- Color de la nota: verde si ≥ umbral configurado, rojo si < umbral, gris si null.

### Botón Export CSV

> **OQ-C22-07 RESUELTO**: Los endpoints de exportación requieren `Authorization: Bearer`.
> NO usar `window.open`. Usar Axios blob + `URL.createObjectURL`.

```typescript
async function handleExport() {
  const resp = await api.get(
    `/api/v1/analisis/${materiaId}/cohortes/${cohorteId}/notas-finales/exportar`,
    { responseType: 'blob' }
  )
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `notas-finales-${materiaId}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
```

---

## SinCorregirPage (F1.2, F2.6)

**Ruta**: `/calificaciones/:materiaId/:cohorteId/sin-corregir`
**Guard**: `atrasados:ver`
**Endpoints**:
- `POST /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/importar-finalizacion` (mutipart)
- `GET /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/sin-corregir`
- `GET /api/v1/analisis/{materiaId}/cohortes/{cohorteId}/sin-corregir/exportar` (CSV)

### Flujo

La página tiene dos secciones:

**Sección 1 — Upload de reporte de finalización**
- `UploadZone` con label "Reporte de finalización (.xlsx / .csv)"
- `useSinCorregirImport` → `POST /importar-finalizacion`
- Después de upload exitoso, invalida `useQuery(['sin-corregir', ...])`
- Muestra "Reporte importado el DD/MM/YYYY HH:MM" si ya hay datos

**Sección 2 — Tabla sin corregir**
- `useQuery(['sin-corregir', materiaId, cohorteId])` → `GET /sin-corregir`
- Columnas: Apellidos, Nombre, Comisión, Actividad

**Aviso especial**: si `aviso === "no_hay_finalizacion_importada"`, muestra:
"Todavía no importaste el reporte de finalización. Subí el archivo para ver los trabajos sin corregir."

**Botón Export CSV**: igual que NotasFinalesPage.

### useSinCorregir

```typescript
export function useSinCorregir(materiaId: string, cohorteId: string) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['sin-corregir', materiaId, cohorteId],
    queryFn: () => monitorService.getSinCorregir(materiaId, cohorteId),
  })
  const upload = useMutation({
    mutationFn: (archivo: File) =>
      calificacionesService.importarFinalizacion(materiaId, cohorteId, archivo),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['sin-corregir', materiaId, cohorteId] }),
  })
  return { ...query, upload }
}
```

---

## MonitorPage (F2.7, F2.8, F2.9)

**Ruta**: `/monitor`
**Guard**: `atrasados:ver`
**Endpoint**: `GET /api/v1/analisis/monitor`

### MonitorFilters

Campos del formulario (React Hook Form + Zod):
```typescript
const schema = z.object({
  materia_id: z.string().uuid().optional(),
  cohorte_id: z.string().uuid().optional(),
  alumno: z.string().optional(),
  comision: z.string().optional(),
  regional: z.string().optional(),
  estado: z.enum(['atrasado', 'al_dia']).optional(),
  fecha_desde: z.string().optional(),  // YYYY-MM-DD
  fecha_hasta: z.string().optional(),
})
```

Nota: `fecha_desde` / `fecha_hasta` solo se muestran si el usuario tiene scope=all
(`comunicacion:aprobar` o rol COORDINADOR/ADMIN). Para PROFESOR/TUTOR se ocultan.
En la práctica: se muestran si `!usePermission('calificaciones:importar') || usePermission('comunicacion:aprobar')`.

**Simplificación**: los filtros de `materia_id` y `cohorte_id` en el monitor son
campos de texto (UUID). En un futuro change se pueden reemplazar por selectores.
Depende de la resolución de OQ-C22-01.

### MonitorTable

Columnas: Apellidos, Nombre, Comisión, Regional, Materia, Cohorte, Estado, Faltantes, Bajo Umbral, Aprobadas

- `estado` → badge: "Al día" (verde) / "Atrasado" (rojo)
- `materia_id` y `cohorte_id` se muestran como UUIDs truncados (8 chars) o se resuelven
  a nombre si hay un contexto disponible (OQ-C22-01 pendiente)

### Paginación

Controles de paginación simples: "Anterior / Siguiente" con `offset` y `limit=50`.
`total` del response permite calcular páginas.

### useMonitor

```typescript
export function useMonitor(filters: MonitorFilters) {
  return useQuery({
    queryKey: ['monitor', filters],
    queryFn: () => monitorService.getMonitor(filters),
    placeholderData: keepPreviousData,  // TanStack Query v5
  })
}
```

---

## Esquema de tests (TDD)

| Archivo | Tests |
|---------|-------|
| `AtrasadosPage.test.tsx` | tabla con datos; estado vacío "todos al día"; estado vacío "sin calificaciones"; botón comunicar deshabilitado sin selección; botón oculto sin permiso comunicacion:enviar; navega con IDs al hacer click |
| `AtrasadosTable.test.tsx` | chips de actividades; trunca si > 3; checkbox selecciona fila |
| `RankingPage.test.tsx` | tabla ordenada por total_aprobadas desc; badges posición 1-3; footer con excluidos |
| `NotasFinalesPage.test.tsx` | nota_final_pct=null muestra "—"; color según umbral; botón export dispara descarga |
| `SinCorregirPage.test.tsx` | sin upload → aviso "no_hay_finalizacion_importada"; upload dispara mutación; tabla muestra entregas; export disponible |
| `MonitorPage.test.tsx` | filtros opcionales; paginación prev/next; badge atrasado/al_dia; fecha_desde visible para admin, oculta para tutor |
| `MonitorFilters.test.tsx` | formulario con RHF; submit pasa filtros al hook; reset limpia campos |
| `useAtrasados.test.ts` | retorna datos; empty state; stale while revalidating |
| `useMonitor.test.ts` | queryKey incluye filtros; keepPreviousData funciona |
