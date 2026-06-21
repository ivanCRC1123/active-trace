## Estado: [x] COMPLETADO — 2026-06-21

43 tests passed, 0 failed (test_tareas.py). Suite completa: 773 passed, 0 failed.

## 1. Modelos SQLAlchemy

Todos los archivos en `backend/app/models/`.

- [x] 1.1 `tarea.py` — clase `Tarea(Base)` con todos los campos del spec `tarea-model`:
  - id (UUID PK), tenant_id, materia_id (nullable FK), asignado_a (FK user), asignado_por (FK user)
  - estado (str, CHECK constraint 4 valores), descripcion (TEXT), contexto_id (UUID nullable, SIN FK)
  - created_at, updated_at, deleted_at (soft delete)
  - Índices: ix_tarea_tenant_id, ix_tarea_tenant_asignado_a, ix_tarea_tenant_asignado_por, ix_tarea_tenant_estado

- [x] 1.2 `comentario_tarea.py` — clase `ComentarioTarea(Base)`:
  - id (UUID PK), tenant_id, tarea_id (FK → tarea.id), autor_id (FK → user.id)
  - texto (TEXT), creado_at, deleted_at (soft delete). Sin updated_at (inmutable).
  - Índice: ix_comentario_tarea_tarea_id

---

## 2. Migración Alembic

- [x] 2.1 `backend/alembic/versions/d8e9f0a1b2c3_018_tarea_comentario_tarea.py`:
  - `upgrade()`: CREATE TABLE tarea → CREATE TABLE comentario_tarea → índices
  - `downgrade()`: DROP TABLE comentario_tarea → DROP TABLE tarea (orden inverso)

---

## 3. Schemas Pydantic (`backend/app/schemas/tareas.py`)

- [x] 3.1 `UsuarioResumen`: id, nombre, apellidos (sin email)
- [x] 3.2 `TareaCreateRequest`: asignado_a (UUID), descripcion (str min=1 max=2000), materia_id (opt), contexto_id (opt)
- [x] 3.3 `TareaEstadoRequest`: estado (Literal 4 valores)
- [x] 3.4 `ComentarioCreateRequest`: texto (str min=1 max=4000)
- [x] 3.5 `TareaResponse`: todos los campos + asignado_a/asignado_por como UsuarioResumen
- [x] 3.6 `ComentarioResponse`: id, tarea_id, autor (UsuarioResumen), texto, creado_at
- [x] 3.7 `MisTareasFiltros`: estado (opt), materia_id (opt), limit (default 50, max 200), offset (default 0)
- [x] 3.8 `TareaFiltros`: extiende MisTareasFiltros con asignado_a (opt), asignado_por (opt), q (opt búsqueda libre)

---

## 4. Repositories

- [x] 4.1–4.6 `tarea_repository.py` — list_by_asignado_a, list_tareas, get_con_usuarios, get_raw, create
- [x] 4.7–4.8 `comentario_tarea_repository.py` — list_by_tarea (ASC), create
- [x] Adición `asignacion_repository.py::existe_vigente_en_materia` — scope PROFESOR

---

## 5. Service (`backend/app/services/tarea_service.py`)

- [x] 5.1 `mis_tareas` — self-scoped, sin permiso
- [x] 5.2 `crear_tarea` — scope own/all, audit TAREA_ASIGNAR
- [x] 5.3 `get_tarea` — membership check
- [x] 5.4 `cambiar_estado` — FSM + membership + audit TAREA_ESTADO_CAMBIAR
- [x] 5.5 `list_tareas` — filtros + scope inyectado
- [x] 5.6 `agregar_comentario` — membership check
- [x] 5.7 `list_comentarios` — membership check + ASC
- [x] 5.8–5.9 Helpers `_puede_acceder`, `_assert_membership`, `_assert_transition`

---

## 6. Router (`backend/app/api/v1/routers/tareas.py`)

- [x] 6.1 `GET /tareas/mis-tareas` — get_current_user (TUTOR sin permiso accede)
- [x] 6.2 `POST /tareas` — require_permission gestionar, scoped=True
- [x] 6.3 `GET /tareas/{id}` — get_current_user + check_permission inline
- [x] 6.4 `PATCH /tareas/{id}/estado` — get_current_user + check_permission inline
- [x] 6.5 `GET /tareas` — require_permission gestionar, scoped=True
- [x] 6.6 `POST /tareas/{id}/comentarios` — get_current_user + check_permission inline
- [x] 6.7 `GET /tareas/{id}/comentarios` — get_current_user + check_permission inline
- [x] 6.8 Registrado en `backend/app/main.py`

---

## 7. Tests (`backend/tests/test_tareas.py`)

- [x] 7.1–7.2 Fixture `tar_db` + helper `_delete_tar_tenant_data` (prefijo `tar-test-`)
- [x] 7.3–7.4 Audit codes (2 tests)
- [x] 7.5–7.9 mis-tareas: 401, TUTOR accede, self-scoped, filtro estado, cross-tenant
- [x] 7.10–7.18 crear tarea: coordinador, profesor scope own/ajena/sin materia, 403, 422, audit, contexto_id
- [x] 7.19–7.28 FSM estado: 8 transiciones válidas/inválidas/terminales + ajeno + otro tenant + audit
- [x] 7.29–7.35 admin global: coordinador, TUTOR 403, filtros, búsqueda, scope own, cross-tenant
- [x] 7.36–7.43 comentarios: 3 roles autorizados, tercero 403, resuelta permite, vacío, orden ASC, autor del JWT
