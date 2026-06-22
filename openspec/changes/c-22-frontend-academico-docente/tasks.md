# C-22 frontend-academico-docente — Tasks

> Orden: cada tarea depende de las anteriores en su área. Las tres áreas (calificaciones,
> análisis, comunicaciones) son paralelas entre sí, pero el scaffold (Tarea 0) es prerequisito.
> Strict TDD: RED → GREEN → TRIANGULATE para cada componente.

---

## Pre-condición: resolver OQ-C22-01 (BLOQUEANTE)

- [ ] P.1 Confirmar resolución de OQ-C22-01: ¿agregar `GET /api/v1/me/asignaciones` en el backend?
- [ ] P.2 Si sí: micro-task backend fuera de este change (≤30 min, agregar endpoint en C-07 o nuevo router).
- [ ] P.3 Confirmar OQ-C22-02: tabs vs. sub-rutas en MateriaDashboardPage.
- [ ] P.4 Confirmar OQ-C22-03: navigate con state vs. drawer para flujo de envío.
- [ ] P.5 Confirmar OQ-C22-05: Monitor como ítem propio vs. sub-ruta.
- [ ] P.6 Confirmar OQ-C22-06: plantilla por defecto vs. texto libre.

---

## 0. Scaffold y rutas

- [ ] 0.1 Crear estructura de directorios: `src/features/calificaciones/`, `src/features/monitor/`, `src/features/comunicaciones/`
- [ ] 0.2 Agregar ítems de menú en `AppShell.tsx`: Monitor (`atrasados:ver`) y Comunicaciones (`comunicacion:enviar`)
- [ ] 0.3 Agregar rutas en `router.tsx` con `ProtectedRoute` y `lazy()` para las 11 páginas
- [ ] 0.4 Crear archivos de tipos: `calificaciones.types.ts`, `monitor.types.ts`, `comunicaciones.types.ts`
- [ ] 0.5 Crear archivos de service vacíos (stub) para cada feature
- [ ] 0.6 Verificar `npm run typecheck` — 0 errores

---

## 1. Feature: Calificaciones — Importación (F1.1, F2.1)

### 1.1 Types y service

- [ ] 1.1.1 (RED) Test `calificacionesService.test.ts`: preview forma FormData con actividades=[]; importar forma FormData con actividades correctas; vaciar llama DELETE
- [ ] 1.1.2 (GREEN) Implementar `calificacionesService.ts`: `preview()`, `importar()`, `vaciar()`, `getUmbral()`, `putUmbral()`, `importarFinalizacion()`
- [ ] 1.1.3 (TRIANGULATE) Test de errores: 400, 409 se propagan correctamente

### 1.2 UmbralForm

- [ ] 1.2.1 (RED) Test `UmbralForm.test.tsx`: pre-carga valor del servidor; slider range 1-100; submit llama PUT
- [ ] 1.2.2 (GREEN) Implementar `UmbralForm.tsx` (<80 LOC): slider Tailwind + `useUmbral`
- [ ] 1.2.3 (RED) Test `useUmbral.test.ts`: carga umbral; actualiza y sincroniza cache
- [ ] 1.2.4 (GREEN) Implementar `useUmbral.ts`

### 1.3 UploadZone

- [ ] 1.3.1 (RED) Test `UploadZone.test.tsx`: acepta xlsx; rechaza pdf; muestra nombre; emite onChange
- [ ] 1.3.2 (GREEN) Implementar `UploadZone.tsx` (<80 LOC): drag & drop + file input

### 1.4 ActividadesSelector

- [ ] 1.4.1 (RED) Test `ActividadesSelector.test.tsx`: todos marcados por defecto; badge tipo; deselect individual; emite onChange con selección
- [ ] 1.4.2 (GREEN) Implementar `ActividadesSelector.tsx` (<80 LOC)

### 1.5 ImportarPage (wizard)

- [ ] 1.5.1 (RED) Test `ImportarPage.test.tsx`: step 1 upload dispara preview; step 2 muestra actividades; step 3 confirm llama importar; error 409 muestra banner; botón vaciar con diálogo de confirmación
- [ ] 1.5.2 (GREEN) Implementar `ImportarPage.tsx` (<200 LOC, extraer pasos si crece)
- [ ] 1.5.3 (TRIANGULATE) Test: upload con advertencias muestra alertas; re-importar mismo archivo funciona

### 1.6 ReporteRapidoCards y MateriaDashboardPage

- [ ] 1.6.1 (RED) Test `ReporteRapidoCards.test.tsx`: KPIs correctos; tiene_datos=false muestra banner
- [ ] 1.6.2 (GREEN) Implementar `ReporteRapidoCards.tsx` (<80 LOC)
- [ ] 1.6.3 (RED) Test `MateriaDashboardPage.test.tsx`: muestra KPIs; nav secundaria con 5 tabs; banner si sin datos con link a importar
- [ ] 1.6.4 (GREEN) Implementar `MateriaDashboardPage.tsx` + `MateriaNav.tsx`

### 1.7 CalificacionesHomePage

- [ ] 1.7.1 Depende de resolución OQ-C22-01. Placeholder hasta entonces.
- [ ] 1.7.2 (RED) Test `CalificacionesHomePage.test.tsx`: cuando OQ-C22-01 esté resuelto
- [ ] 1.7.3 (GREEN) Implementar `CalificacionesHomePage.tsx`

---

## 2. Feature: Análisis y Reportes (F2.2–F2.6)

### 2.1 AtrasadosPage

- [ ] 2.1.1 (RED) Test `AtrasadosTable.test.tsx`: chips faltantes; trunca > 3; checkbox selecciona
- [ ] 2.1.2 (GREEN) Implementar `AtrasadosTable.tsx` (<150 LOC)
- [ ] 2.1.3 (RED) Test `AtrasadosPage.test.tsx`: todos al día → empty state verde; sin calificaciones → empty state distinto; botón comunicar deshabilitado sin selección; oculto sin permiso; navega con state al click
- [ ] 2.1.4 (GREEN) Implementar `AtrasadosPage.tsx` (<200 LOC)
- [ ] 2.1.5 (RED) Test `useAtrasados.test.ts`: query con materiaId+cohorteId; invalida al importar
- [ ] 2.1.6 (GREEN) Implementar `useAtrasados.ts`

### 2.2 RankingPage

- [ ] 2.2.1 (RED) Test `RankingTable.test.tsx`: ordenado por total_aprobadas; badge posición 1-3; footer con excluidos
- [ ] 2.2.2 (GREEN) Implementar `RankingTable.tsx` (<100 LOC)
- [ ] 2.2.3 (RED) Test `RankingPage.test.tsx`: muestra tabla; estado vacío
- [ ] 2.2.4 (GREEN) Implementar `RankingPage.tsx` (<100 LOC)

### 2.3 NotasFinalesPage

- [ ] 2.3.1 (RED) Test `NotasFinalesTable.test.tsx`: nota null → "—"; color por umbral; export dispara descarga
- [ ] 2.3.2 (GREEN) Implementar `NotasFinalesTable.tsx` (<120 LOC)
- [ ] 2.3.3 (RED) Test `NotasFinalesPage.test.tsx`: tabla; botón export; estado vacío
- [ ] 2.3.4 (GREEN) Implementar `NotasFinalesPage.tsx` (<150 LOC)
- [ ] 2.3.5 Verificar OQ-C22-07 sobre descarga CSV con Authorization header

### 2.4 SinCorregirPage

- [ ] 2.4.1 (RED) Test `SinCorregirPage.test.tsx`: aviso sin finalización importada; upload muestra loading; tabla después de upload; export disponible
- [ ] 2.4.2 (GREEN) Implementar `SinCorregirPage.tsx` (<200 LOC)
- [ ] 2.4.3 (RED) Test `useSinCorregir.test.ts`: invalidación de query después de upload
- [ ] 2.4.4 (GREEN) Implementar `useSinCorregir.ts`

---

## 3. Feature: Monitor (F2.7–F2.9)

### 3.1 MonitorPage

- [ ] 3.1.1 (RED) Test `MonitorFilters.test.tsx`: formulario RHF; submit pasa filtros; reset limpia
- [ ] 3.1.2 (GREEN) Implementar `MonitorFilters.tsx` (<100 LOC)
- [ ] 3.1.3 (RED) Test `MonitorTable.test.tsx`: badge atrasado rojo; badge al_día verde; paginación prev/next
- [ ] 3.1.4 (GREEN) Implementar `MonitorTable.tsx` (<150 LOC)
- [ ] 3.1.5 (RED) Test `MonitorPage.test.tsx`: filtros opcionales; fecha_desde visible para admin; oculta para tutor; sin datos → empty state
- [ ] 3.1.6 (GREEN) Implementar `MonitorPage.tsx` (<200 LOC)
- [ ] 3.1.7 (RED) Test `useMonitor.test.ts`: queryKey incluye filtros; keepPreviousData al paginar
- [ ] 3.1.8 (GREEN) Implementar `useMonitor.ts`

---

## 4. Feature: Comunicaciones (F3.1–F3.3)

### 4.1 EstadoBadge

- [ ] 4.1.1 (RED) Test `EstadoBadge.test.tsx`: cada estado tiene color correcto; label correcto
- [ ] 4.1.2 (GREEN) Implementar `EstadoBadge.tsx` (<30 LOC)

### 4.2 PreviewModal

- [ ] 4.2.1 (RED) Test `PreviewModal.test.tsx`: muestra hasta 3 ítems; "y N más"; cancelar cierra; confirmar llama callback con lotePayload
- [ ] 4.2.2 (GREEN) Implementar `PreviewModal.tsx` (<150 LOC)

### 4.3 NuevaComunicacionPage

- [ ] 4.3.1 (RED) Test service `comunicacionesService.test.ts`: preview POST; crearLote POST; getLote GET; aprobarLote POST; cancelarLote POST; cancelarIndividual POST; listar con params
- [ ] 4.3.2 (GREEN) Implementar `comunicacionesService.ts`
- [ ] 4.3.3 (RED) Test `usePreview.test.ts`: mutación llama service; error propagado
- [ ] 4.3.4 (GREEN) Implementar `usePreview.ts`
- [ ] 4.3.5 (RED) Test `NuevaComunicacionPage.test.tsx`: sin state → error; formulario pre-llenado; vista previa abre modal; confirmar con requiere_aprobacion=true muestra toast correcto; confirmar sin aprobación navega a lote
- [ ] 4.3.6 (GREEN) Implementar `NuevaComunicacionPage.tsx` (<200 LOC)
- [ ] 4.3.7 (TRIANGULATE) Test: volver con back del browser pierde state correctamente

### 4.4 ComunicacionesPage

- [ ] 4.4.1 (RED) Test `AprobacionPanel.test.tsx`: visible con permiso; oculto sin permiso; aprobar llama servicio; cancelar llama servicio
- [ ] 4.4.2 (GREEN) Implementar `AprobacionPanel.tsx` (<100 LOC)
- [ ] 4.4.3 (RED) Test `ComunicacionesTable.test.tsx`: tabla con datos; filtro por estado; link a lote
- [ ] 4.4.4 (GREEN) Implementar `ComunicacionesTable.tsx` (<120 LOC)
- [ ] 4.4.5 (RED) Test `ComunicacionesPage.test.tsx`: tabla visible con datos; panel aprobación visible con permiso; oculto sin permiso
- [ ] 4.4.6 (GREEN) Implementar `ComunicacionesPage.tsx` (<200 LOC)
- [ ] 4.4.7 (RED) Test `useComunicaciones.test.ts`: listar; invalidar después de aprobar
- [ ] 4.4.8 (GREEN) Implementar `useComunicaciones.ts`

### 4.5 LoteDetallePage

- [ ] 4.5.1 (RED) Test `useLote.test.ts`: refetchInterval=5000 si hay PENDIENTE; false si todos terminados
- [ ] 4.5.2 (GREEN) Implementar `useLote.ts`
- [ ] 4.5.3 (RED) Test `LoteDetallePage.test.tsx`: tabla de mensajes; polling activo; cancelar individual visible con permiso; panel aprobación visible con permiso
- [ ] 4.5.4 (GREEN) Implementar `LoteDetallePage.tsx` (<200 LOC)

---

## 5. Integración y verificación final

- [ ] 5.1 Levantar backend + frontend en paralelo
- [ ] 5.2 Flujo completo PROFESOR: login → calificaciones → importar → ver atrasados → seleccionar → enviar comunicación → ver lote
- [ ] 5.3 Flujo COORDINADOR: ver monitor global → aprobar lote pendiente
- [ ] 5.4 Guard de permisos: TUTOR accede a Monitor pero no a Importar ni Comunicaciones
- [ ] 5.5 `npm test` — 0 failed
- [ ] 5.6 `npm run typecheck` — 0 errores
- [ ] 5.7 Verificar que ningún componente supera 200 LOC
- [ ] 5.8 Verificar menú AppShell: PROFESOR ve Calificaciones, Monitor, Comunicaciones; COORDINADOR ve todo incluyendo panel de aprobación

---

## 6. Cierre

- [ ] 6.1 Marcar `C-22` como `[x]` en `CHANGES.md`
- [ ] 6.2 Archivar openspec: `openspec/changes/c-22-frontend-academico-docente/` → `openspec/changes/archive/YYYY-MM-DD-c-22-frontend-academico-docente/`
