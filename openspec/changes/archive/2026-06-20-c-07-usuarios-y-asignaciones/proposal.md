# C-07 — usuarios-y-asignaciones: Proposal

## Why

Carrera, Cohorte y Materia (C-06) existen como catálogo académico pero no hay ninguna persona
concreta en el sistema que pueda dictar esas materias, coordinar esos equipos o figurar en una
liquidación. C-07 materializa las dos entidades que modelan _quién hace qué en qué contexto_:

- **Usuario (E4)**: el docente/coordinador/admin como persona real, con todos sus datos de perfil
  y PII (documento, datos bancarios) que el módulo de liquidaciones necesitará en C-18.
- **Asignación (E5)**: el vínculo entre una persona, un rol académico y un contexto concreto
  (materia × carrera × cohorte × comisiones), con vigencia temporal.

Sin estos dos modelos, los siguientes modules del camino crítico no pueden construirse:
C-08 (equipos), C-09 (padrón), C-10 (calificaciones), C-12 (comunicaciones), C-18 (liquidaciones).

## What Changes

### Modelos nuevos / extendidos
- Migración 006: extiende tabla `user` con campos PII + crea tabla `asignacion`.
- **User (extendido)**: renombra `apellido` → `apellidos`, agrega `dni_cifrado`, `cuil_cifrado`,
  `cbu_cifrado`, `alias_cbu_cifrado` (AES-256-GCM), `banco`, `regional`, `legajo`,
  `legajo_profesional`, `facturador`.
- **Asignacion (nuevo)**: vincula `usuario_id → user`, `rol_id → rol`, contexto académico
  (`materia_id?`, `carrera_id?`, `cohorte_id?`), `comisiones` (JSONB), `responsable_id → user`
  (jerarquía), `desde / hasta` (vigencia), `estado_vigencia` derivado (no almacenado).

### Cifrado
Reutiliza `backend/app/core/encryption.py` (C-02) con dos mecanismos:
- **AES-256-GCM** via `EncryptedString` TypeDecorator: `email_cifrado`, `dni_cifrado`,
  `cuil_cifrado`, `cbu_cifrado`, `alias_cbu_cifrado` — **5 campos cifrados**.
- **HMAC-SHA256** via `hmac_email()` nueva en `encryption.py`: `email_hash` — blind index
  determinístico para el lookup de login. El plaintext del email nunca se almacena en DB.
- El auth service de C-03 se actualiza para buscar por `email_hash` en lugar de `email`.

### Endpoints
- **`/api/v1/admin/usuarios`** — ABM completo, guard `usuarios:gestionar` (ADMIN).
- **`/api/v1/asignaciones`** — CRUD + filtros, guard `equipos:asignar` (COORDINADOR + ADMIN).
  Vigencia como query param: `?vigente=true`.

### Permisos
Ambos permisos ya existen en el seed de C-04:
- `usuarios:gestionar` → ADMIN scope=all
- `equipos:asignar` → COORDINADOR scope=all, ADMIN scope=all

No se requieren cambios en `seed_permissions.py`.

## New Capabilities

- `usuarios:abm` — ADMIN puede crear/editar/desactivar docentes con PII cifrada.
- `asignaciones:crud` — COORDINADOR y ADMIN pueden crear/listar/actualizar/eliminar (soft) asignaciones.
- `asignaciones:vigencia` — El sistema deriva automáticamente si una asignación es Vigente o Vencida.
- `asignaciones:historico` — Asignaciones vencidas se conservan; no se borran físicamente.

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Models | `user.py` (modify), `asignacion.py` (new), `base.py` (add EncryptedString) | +1 nuevo, 2 modificados |
| Migration | `[rev]_006_usuario_pii_asignacion.py` | +1 |
| Repositories | `usuario_repository.py` (new), `asignacion_repository.py` (new) | +2 |
| Schemas | `usuarios.py` (new), `asignaciones.py` (new) | +2 |
| Services | `usuario_service.py` (new), `asignacion_service.py` (new) | +2 |
| Routers | `usuarios.py` (new), `asignaciones.py` (new) | +2 |
| main.py | register 2 new routers | modify |
| Tests | `test_usuarios.py` (new), `test_asignaciones.py` (new) | +2 (~38 tests) |

## Dependencies

- **C-04** (RBAC): `require_permission` guard + tabla `rol` (FK en asignacion)
- **C-06** (estructura académica): tablas `materia`, `carrera`, `cohorte` (FK en asignacion)
- C-07 **desbloquea**: C-08, C-09, C-13, C-14, C-15, C-16, C-17, C-18 (todos necesitan Usuario + Asignacion)

## Governance

**CRÍTICO** — maneja PII sensible (DNI, CUIL, CBU). Toda implementación requiere revisión
explícita antes de commitear. Los campos cifrados nunca deben aparecer en logs.
