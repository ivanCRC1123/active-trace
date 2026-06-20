# Spec: Asignacion (E5)

## Entidad

Representa el vínculo entre un Usuario, un Rol y un contexto académico (Materia × Carrera × Cohorte × Comisiones), con vigencia temporal.

## Campos

| Campo | Tipo DB | Nullable | Notas |
|-------|---------|----------|-------|
| id | UUID PK | no | gen_random_uuid() |
| tenant_id | UUID FK→tenant | no | CASCADE |
| usuario_id | UUID FK→user | no | RESTRICT — no se puede borrar físicamente un usuario referenciado |
| rol_id | UUID FK→rol | no | RESTRICT — FK a tabla `rol` de C-04, no enum hardcodeado |
| materia_id | UUID FK→materia | yes | RESTRICT (opcional — asignación puede ser de nivel carrera/cohorte) |
| carrera_id | UUID FK→carrera | yes | RESTRICT |
| cohorte_id | UUID FK→cohorte | yes | RESTRICT |
| comisiones | JSONB | no | DEFAULT `'[]'` — lista de strings |
| responsable_id | UUID FK→user | yes | SET NULL — jerarquía (RN-11) |
| desde | DATE | no | inicio de vigencia |
| hasta | DATE | yes | fin de vigencia, NULL = abierta |
| created_at | TIMESTAMP | no | |
| updated_at | TIMESTAMP | no | trigger ON UPDATE |
| deleted_at | TIMESTAMP | yes | NULL = no borrado |

## Campo derivado: estado_vigencia

**No se almacena.** Se calcula en el servicio:

```
estado_vigencia = "Vigente" si:
    desde <= HOY
    AND (hasta IS NULL OR hasta >= HOY)
    AND deleted_at IS NULL

estado_vigencia = "Vencida" en cualquier otro caso
    (incluyendo: desde > HOY, hasta < HOY)
```

Referencia: KB §E5, S2, D8.

## Constraints

- FK RESTRICT en `usuario_id`, `rol_id`: no se puede borrar físicamente una entidad referenciada.
- FK RESTRICT en `materia_id`, `carrera_id`, `cohorte_id` (nullable): si se provee, la entidad debe existir.
- FK SET NULL en `responsable_id`: si el responsable se elimina (soft delete no aplica en FK real), la asignación mantiene hasta=NULL.
- `deleted_at IS NULL` — soft delete; asignaciones eliminadas permanecen en el histórico.

## Invariantes de negocio

- El rol no puede ser `ALUMNO` — los alumnos no tienen asignaciones docentes (RN-10).
- `usuario_id`, `rol_id`, `materia_id`, `carrera_id`, `cohorte_id` deben pertenecer al mismo `tenant_id` que la asignación.
- Asignaciones vencidas (`hasta < HOY`) se conservan — son registro histórico (D8).
- `desde > hasta` es inválido — el servicio valida este constraint de dominio.
- La vigencia es un estado efímero: cambia con el paso del tiempo sin modificar el registro.

## Escenarios

### Creación
```
DADO que el COORDINADOR está autenticado
Y existe usuario {id_usuario}, rol "PROFESOR" y materia {id_materia} en su tenant
CUANDO POST /api/v1/asignaciones con usuario_id, rol_id, materia_id, desde=HOY, hasta=null
ENTONCES 201 con AsignacionResponse.estado_vigencia="Vigente"
```

```
DADO que el COORDINADOR está autenticado
Y el rol referenciado se llama "ALUMNO"
CUANDO POST /api/v1/asignaciones con ese rol_id
ENTONCES 400 "el rol ALUMNO no es asignable a contextos docentes"
```

```
DADO que el COORDINADOR está autenticado en TENANT-A
Y el usuario referenciado pertenece a TENANT-B
CUANDO POST /api/v1/asignaciones con ese usuario_id
ENTONCES 404 (el repo filtra por tenant — el usuario de otro tenant no es visible)
```

### Listado con filtro de vigencia
```
DADO que hay 3 asignaciones en el tenant:
    A: desde=2025-01-01, hasta=2025-06-30  → Vencida
    B: desde=2026-01-01, hasta=null          → Vigente
    C: desde=2026-06-01, hasta=2027-06-30   → Vigente

CUANDO GET /api/v1/asignaciones?vigente=true
ENTONCES devuelve solo B y C

CUANDO GET /api/v1/asignaciones?vigente=false
ENTONCES devuelve solo A

CUANDO GET /api/v1/asignaciones  (sin param)
ENTONCES devuelve A, B y C
```

### Actualización
```
DADO que existe una asignación vigente {id}
CUANDO PATCH /api/v1/asignaciones/{id} con hasta=2026-12-31
ENTONCES 200 con hasta=2026-12-31 y estado_vigencia recalculado
```

### Baja (soft delete)
```
DADO que existe una asignación {id}
CUANDO DELETE /api/v1/asignaciones/{id}
ENTONCES 204
Y GET /api/v1/asignaciones/{id} devuelve 404
Y el registro permanece en DB con deleted_at ≠ NULL
Y NO aparece en GET /api/v1/asignaciones (list solo sin deleted)
```

### RBAC
```
DADO que un PROFESOR (sin permiso equipos:asignar) está autenticado
CUANDO POST /api/v1/asignaciones
ENTONCES 403 Forbidden
```

### Vigencia con desde futuro
```
DADO que se crea una asignación con desde=2027-01-01 (fecha futura)
CUANDO se consulta estado_vigencia HOY (2026-06-19)
ENTONCES estado_vigencia="Vencida" (no ha iniciado aún)
```

## Índices de base de datos

```sql
CREATE INDEX idx_asignacion_tenant      ON asignacion(tenant_id)        WHERE deleted_at IS NULL;
CREATE INDEX idx_asignacion_usuario     ON asignacion(usuario_id)        WHERE deleted_at IS NULL;
CREATE INDEX idx_asignacion_rol         ON asignacion(rol_id)            WHERE deleted_at IS NULL;
CREATE INDEX idx_asignacion_materia     ON asignacion(materia_id)        WHERE deleted_at IS NULL AND materia_id IS NOT NULL;
CREATE INDEX idx_asignacion_cohorte     ON asignacion(cohorte_id)        WHERE deleted_at IS NULL AND cohorte_id IS NOT NULL;
CREATE INDEX idx_asignacion_vigencia    ON asignacion(tenant_id, desde, hasta) WHERE deleted_at IS NULL;
```
