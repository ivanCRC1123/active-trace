# C-06 — `estructura-academica` — Design

## Context

C-04 y C-05 establecieron la seguridad (RBAC, JWT, impersonación, audit log). C-06 es el primer change de dominio puro: crea el catálogo académico que da contexto a todos los módulos posteriores.

Fuentes: `knowledge-base/04_modelo_de_datos.md` §E1–E3, `knowledge-base/05_reglas_de_negocio.md`, `docs/ARQUITECTURA.md` §10 (ADR-006).

## Goals / Non-Goals

**Goals:**
- Modelos Carrera, Cohorte y Materia con soft-delete, tenant-scope y enum de estado.
- ABM completo vía REST, exclusivo de ADMIN.
- Regla de negocio: Carrera inactiva bloquea creación de Cohortes.
- Unicidad por tenant en campos naturales (codigo, nombre+carrera).
- Aislamiento multi-tenant total (un ADMIN no ve datos de otro tenant).
- Tests TDD: ~30 casos cubriendo CRUD, unicidad, estado y RBAC.

**Non-Goals:**
- `Dictado` (instancia materia × cohorte) → diferido a C-07 junto con Asignaciones.
- FK desde `audit_log.materia_id` → imposible por PostgreSQL RULEs (decisión permanente de C-05).
- Gestión de programas de materia (ProgramaMateria) → C-17.
- Gestión de fechas académicas → C-17.

## Decisions

### D1 — EstadoBasico como Python Enum compartido en base.py

```python
# backend/app/models/base.py
import enum

class EstadoBasico(str, enum.Enum):
    Activa = "Activa"
    Inactiva = "Inactiva"
```

Usado en los 3 modelos como `sa.Enum(EstadoBasico, name="estado_basico", create_type=False)` (el type Postgres se crea una sola vez en la migración, antes de la primera tabla).

**Rationale:**
- Validación ORM en capa Python antes de llegar a la DB.
- `str` mixin permite serialización directa en Pydantic y JSON.
- `create_type=False` evita que SQLAlchemy intente crear el type en cada tabla.
- Alternativa descartada: `String + CHECK constraint` (sin validación en ORM, sin autocompletado).

### D2 — Cohorte.carrera_id con RESTRICT (no CASCADE)

```python
carrera_id: Mapped[UUID] = mapped_column(
    ForeignKey("carrera.id", ondelete="RESTRICT"),
    nullable=False,
    index=True,
)
```

**Rationale:**
- El flujo normal de baja es soft-delete (`deleted_at`), nunca hard-delete (CLAUDE.md regla 13).
- `RESTRICT` protege la integridad referencial: si alguien intenta borrar físicamente una Carrera con Cohortes, la DB rechaza.
- `CASCADE` sería peligroso: eliminaría en cascada toda la historia académica.
- Alternativa `SET NULL` descartada: `carrera_id` es NOT NULL en el modelo E2.

### D3 — Un único EstructuraAcademicaService

Un solo archivo de servicio con métodos para las 3 entidades. El patrón es idéntico en los 3 casos (validar unicidad → repo.create/update). Un servicio por entidad multiplicaría archivos sin añadir cohesión.

```
EstructuraAcademicaService(session)
├── create_carrera / update_carrera / delete_carrera
├── create_cohorte / update_cohorte / delete_cohorte  ← valida carrera activa
└── create_materia / update_materia / delete_materia
```

### D4 — Validación "Carrera activa" en la capa de servicio

Al crear una Cohorte:
1. Verificar que `carrera_id` exista en el tenant → 404 si no.
2. Verificar que `carrera.estado == EstadoBasico.Activa` → 400 si inactiva.
3. Verificar unicidad `(tenant_id, carrera_id, nombre)` → 409 si duplicado.

Esta lógica vive en el Service, no en el Router. El Router solo traduce HTTP → service call → HTTP response.

### D5 — Dictado fuera de scope

ADR-006 define Dictado como la instancia de enseñanza (materia × cohorte, o materia × carrera × cohorte según interpretación final de PA-01). C-06 solo crea el catálogo. El Dictado se diseñará junto con las Asignaciones en C-07, cuando el modelo de Usuario esté disponible y PA-01 esté cerrado.

### D6 — Router prefix `/api/v1/admin/`

Los 15 endpoints son exclusivos de ADMIN. El prefijo `/api/v1/admin/` los separa semánticamente de los endpoints de usuario final y facilita políticas de firewall/gateway futuras.

### D7 — Estado en migración: CREATE TYPE antes de tablas

```sql
-- upgrade()
sa.Enum(EstadoBasico, name='estado_basico').create(op.get_bind())
op.create_table("carrera", ...)
op.create_table("cohorte", ...)
op.create_table("materia", ...)

-- downgrade()
op.drop_table("materia")
op.drop_table("cohorte")
op.drop_table("carrera")
sa.Enum(name='estado_basico').drop(op.get_bind())
```

El ENUM type se crea una sola vez antes de las tablas y se elimina al hacer downgrade de las 3 tablas juntas.

## Risks / Trade-offs

- **PA-07 (Cohorte per-Carrera)** → Si el producto decide que las Cohortes son transversales (sin carrera_id), C-07 deberá refactorizar la FK. El impacto es una migración que elimina la columna y ajusta los unique constraints.
- **EstadoBasico type Postgres compartido** → Si en C-07+ se necesita un estado distinto (más valores), se deberá crear un nuevo ENUM type. `estado_basico` solo tiene `Activa / Inactiva`.

## Migration Plan

1. `alembic upgrade head` en `trace_test` (CI).
2. Tests pasan → `alembic upgrade head` en `trace` (producción local).
3. Rollback: `alembic downgrade -1` elimina las 3 tablas y el ENUM type en orden correcto.

## Open Questions

- **PA-07 cerrada pragmáticamente**: `carrera_id` en Cohorte según modelo KB E2. Si el producto revierte, es un refactor de migración en C-07.
- **PA-01 (Dictado)**: diferido a C-07. No bloquea C-06.
