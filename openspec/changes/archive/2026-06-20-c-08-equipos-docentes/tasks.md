## 1. Schemas Pydantic (`backend/app/schemas/equipos.py`)

Todos con `model_config = ConfigDict(extra='forbid')`.

- [x] 1.1 `MisEquiposFiltros`: query params de `GET /equipos/mis-equipos`
  - `materia_id: UUID | None`, `carrera_id: UUID | None`, `cohorte_id: UUID | None`
  - `rol: str | None`, `estado_vigencia: Literal["Vigente","Vencida"] | None`

- [x] 1.2 `EquipoFiltros`: query params de `GET /equipos` y `GET /equipos/exportar`
  - Extiende `MisEquiposFiltros` con `usuario_id: UUID | None`, `responsable_id: UUID | None`
  - `limit: int = 100` (max 500), `offset: int = 0`

- [x] 1.3 `AsignacionEquipoResponse`: respuesta de lectura con nombres resueltos
  - `id`, `usuario_id`, `usuario_nombre`, `usuario_apellidos`
  - `rol: str` (nombre), `materia_id`, `materia_nombre`, `carrera_id`, `carrera_nombre`
  - `cohorte_id`, `cohorte_nombre`, `comisiones: list[str]`, `responsable_id`
  - `desde: date`, `hasta: date | None`, `estado_vigencia: str`

- [x] 1.4 `AsignacionMasivaRequest`: body de `POST /equipos/masiva`
  - `usuario_ids: list[UUID]` (min_length=1), `rol_id: UUID`
  - `materia_id`, `carrera_id`, `cohorte_id` (opcionales), `comisiones: list[str] = []`
  - `responsable_id: UUID | None`, `desde: date`, `hasta: date | None`
  - Validador: `hasta >= desde` si `hasta is not None`

- [x] 1.5 `MasivaResult`: respuesta de masiva
  - `creados: int`, `asignaciones: list[UUID]`

- [x] 1.6 `ContextoEquipo`: subschema reutilizable
  - `materia_id: UUID | None`, `carrera_id: UUID | None`, `cohorte_id: UUID | None`
  - Validador: al menos uno no-null

- [x] 1.7 `ClonarEquipoRequest`: body de `POST /equipos/clonar`
  - `origen: ContextoEquipo`, `destino: ContextoEquipo`
  - `desde: date`, `hasta: date | None`
  - Validador: `hasta >= desde`, origen != destino (no el mismo contexto exacto)

- [x] 1.8 `ClonarOmitido`: `{ "usuario_id": UUID, "motivo": str }`

- [x] 1.9 `ClonarResult`: `{ "creados": int, "omitidos": list[ClonarOmitido] }`

- [x] 1.10 `VigenciaBloqueRequest`: body de `PATCH /equipos/vigencia`
  - `materia_id`, `carrera_id`, `cohorte_id` (opcionales)
  - `desde: date`, `hasta: date | None`
  - Validador: `hasta >= desde`; al menos un FK de contexto no-null

- [x] 1.11 `VigenciaBloqueResult`: `{ "filas_afectadas": int }`

---

## 2. Repositorio (`backend/app/repositories/asignacion_repository.py`)

Extender `AsignacionRepository` de C-07 con los métodos que C-08 necesita.

- [x] 2.1 `list_by_usuario(usuario_id, tenant_id, filtros) → Sequence[AsignacionConNombres]`
  - Join con `user`, `rol`, `materia`, `carrera`, `cohorte` para resolver nombres.
  - Filtros: materia_id, carrera_id, cohorte_id, rol_nombre, estado_vigencia.

- [x] 2.2 `list_equipo(tenant_id, filtros) → Sequence[AsignacionConNombres]`
  - Todos los filtros de `EquipoFiltros`. Join con nombres. Paginación (limit/offset).

- [x] 2.3 `list_vigentes_por_contexto(tenant_id, materia_id, carrera_id, cohorte_id, hoy) → Sequence[Asignacion]`
  - WHERE `deleted_at IS NULL AND desde <= hoy AND (hasta IS NULL OR hasta >= hoy)`
  - AND contexto coincide (null = match any).

- [x] 2.4 `existe_vigente_en_destino(tenant_id, usuario_id, rol_id, materia_id, carrera_id, cohorte_id, hoy) → bool`
  - Subquery de un solo booleano.

- [x] 2.5 `bulk_update_vigencia(tenant_id, materia_id, carrera_id, cohorte_id, desde, hasta) → int`
  - UPDATE + RETURNING count. WHERE contexto con NULLs opcionales.

---

## 3. Service (`backend/app/services/equipo_service.py`)

Nuevo servicio. Sin acceso directo a DB — usa repositorio.

- [x] 3.1 `EquipoService.__init__(session: AsyncSession)`

- [x] 3.2 `mis_equipos(usuario_id, tenant_id, filtros) → list[AsignacionEquipoResponse]`
  - Llama a `repo.list_by_usuario`. Aplica `_vigencia` por fila.

- [x] 3.3 `list_equipo(tenant_id, filtros) → list[AsignacionEquipoResponse]`
  - Llama a `repo.list_equipo`. Aplica `_vigencia`.

- [x] 3.4 `asignar_masiva(tenant_id, payload, current_user) → MasivaResult`
  - Pasada 1: validación de todos los usuario_ids, rol_id, FKs opcionales y duplicados.
  - Si falla → `HTTPException(422, ...)` con detalle de IDs problemáticos.
  - Pasada 2: bulk insert en transacción.
  - Audit `ASIGNACION_MODIFICAR`.

- [x] 3.5 `clonar_equipo(tenant_id, payload, current_user) → ClonarResult`
  - Validar FKs. Cargar vigentes del origen. Por cada uno, verificar destino. Bulk insert.
  - Audit `ASIGNACION_MODIFICAR` con detalle de origen/destino/omitidos.

- [x] 3.6 `actualizar_vigencia_bloque(tenant_id, payload, current_user) → VigenciaBloqueResult`
  - Llamar `repo.bulk_update_vigencia`. Audit `ASIGNACION_MODIFICAR`.

- [x] 3.7 `exportar_csv(tenant_id, filtros) → bytes`
  - Llama a `repo.list_equipo` (sin paginación — exporta todo). Genera CSV con stdlib `csv`.

- [x] 3.8 `EquipoService` listo en `backend/app/services/equipo_service.py`.

---

## 4. Router (`backend/app/api/v1/routers/equipos.py`)

- [x] 4.1 `GET /equipos/mis-equipos` → `get_current_user` (identidad JWT) → `EquipoService.mis_equipos()`
- [x] 4.2 `GET /equipos` → `require_permission("equipos:asignar")` → `EquipoService.list_equipo()`
- [x] 4.3 `POST /equipos/masiva` → `require_permission("equipos:asignar")` → `EquipoService.asignar_masiva()`
- [x] 4.4 `POST /equipos/clonar` → `require_permission("equipos:asignar")` → `EquipoService.clonar_equipo()`
- [x] 4.5 `PATCH /equipos/vigencia` → `require_permission("equipos:asignar")` → `EquipoService.actualizar_vigencia_bloque()`
- [x] 4.6 `GET /equipos/exportar` → `require_permission("equipos:asignar")` → `EquipoService.exportar_csv()`
  - Devuelve `StreamingResponse` con `Content-Type: text/csv; charset=utf-8` y header `Content-Disposition`.
- [x] 4.7 Registrado `router` en `backend/app/main.py`.

---

## 5. Tests (`backend/tests/test_equipos.py`)

Fixture base: tenant A con 5 docentes, 2 cohortes, 6 asignaciones (5 vigentes + 1 vencida). Tenant B aislado.

### mis-equipos (spec: mis-equipos)

- [x] 5.1 `test_mis_equipos_devuelve_propias` — solo ve sus asignaciones.
- [x] 5.2 `test_mis_equipos_filtro_materia` — filtro por materia_id.
- [x] 5.3 `test_mis_equipos_filtro_vigencia` — `estado_vigencia=Vigente` excluye vencidas.
- [x] 5.4 `test_mis_equipos_sin_auth_401` — sin Bearer → 401 (endpoint sin permiso; identidad por JWT).
- [x] 5.5 `test_mis_equipos_cross_tenant_vacio` — otro tenant → lista vacía.

### list equipo (spec: gestion-asignaciones)

- [x] 5.6 `test_list_equipo_todos`.
- [x] 5.7 `test_list_equipo_filtro_cohorte`.
- [x] 5.8 `test_list_equipo_filtro_vigencia`.
- [x] 5.9 `test_list_equipo_paginacion` — limit/offset.
- [x] 5.10 `test_list_equipo_sin_permiso_403`.

### masiva (spec: masiva)

- [x] 5.11 `test_masiva_crea_N_asignaciones`.
- [x] 5.12 `test_masiva_usuario_invalido_422`.
- [x] 5.13 `test_masiva_duplicado_422`.
- [x] 5.14 `test_masiva_hasta_menor_que_desde_422`.
- [x] 5.15 `test_masiva_sin_permiso_403`.
- [x] 5.16 `test_masiva_registra_audit`.

### clonar (spec: clonar)

- [x] 5.17 `test_clonar_equipo_exitoso` — 5 vigentes → 5 nuevas.
- [x] 5.18 `test_clonar_origen_sin_vigentes` — `{ "creados": 0 }`.
- [x] 5.19 `test_clonar_omite_ya_existentes` — segunda ejecución omite todos.
- [x] 5.20 `test_clonar_no_copia_vencidas` — vencidas del origen no se clonan.
- [x] 5.21 `test_clonar_cohorte_destino_invalido_404`.
- [x] 5.22 `test_clonar_hasta_menor_que_desde_422`.
- [x] 5.23 `test_clonar_registra_audit`.
- [x] 5.24 `test_clonar_sin_permiso_403`.

### vigencia-bloque (spec: vigencia-bloque)

- [x] 5.25 `test_vigencia_bloque_actualiza_cohorte`.
- [x] 5.26 `test_vigencia_bloque_filtro_materia`.
- [x] 5.27 `test_vigencia_bloque_sin_matches` — `{ "filas_afectadas": 0 }`, 200.
- [x] 5.28 `test_vigencia_bloque_hasta_menor_que_desde_422`.
- [x] 5.29 `test_vigencia_bloque_contexto_vacio_422`.
- [x] 5.30 `test_vigencia_bloque_registra_audit`.
- [x] 5.31 `test_vigencia_bloque_sin_permiso_403`.

### exportar (spec: exportar)

- [x] 5.32 `test_exportar_csv_contiene_encabezado`.
- [x] 5.33 `test_exportar_csv_con_datos` — 6 asignaciones → 7 líneas.
- [x] 5.34 `test_exportar_csv_filtro_cohorte`.
- [x] 5.35 `test_exportar_csv_vacio` — solo encabezado, 200.
- [x] 5.36 `test_exportar_csv_content_type`.
- [x] 5.37 `test_exportar_sin_permiso_403`.

### aislamiento tenant transversal

- [x] 5.38 `test_masiva_cross_tenant_usuario_invalido` — usuario de otro tenant → 422.
- [x] 5.39 `test_clonar_cross_tenant_aislado` — cohorte de otro tenant → 404.
- [x] 5.40 `test_vigencia_bloque_cross_tenant_cero` — contexto de otro tenant → `filas_afectadas: 0`.

---

## Resultado

**40 passed / 0 failed** — suite acumulada 452/452 ✓
