# C-16 — Design Decisions

## D-C16-1: Separación entre "trabajar mis tareas" (identidad) y "gestionar" (permiso)

**Decisión**: el sistema distingue dos capas de acceso:

1. **Self-scoped / identity-based** — `GET /tareas/mis-tareas` y operaciones sobre tareas donde
   `current_user.id == asignado_a` (leer, cambiar estado, comentar): solo requieren
   `get_current_user`. No usan `require_permission`. Esto cubre al TUTOR (que no tiene
   `tareas_internas:gestionar` en la matriz) y cumple lo que F8.1 exige: TUTOR puede ver y
   operar SUS tareas.

2. **Permission-based** — `POST /tareas` (crear/asignar), `GET /tareas` (vista global) y
   operaciones donde el usuario actúa sobre tareas de otros: requieren
   `require_permission("tareas_internas:gestionar")`.

**Por qué el TUTOR no recibe el permiso directamente**: la matriz §3.3 de KB 03 no otorga
`tareas_internas:gestionar` a TUTOR. Otorgárselo sería una desviación del contrato del dominio.
La solución correcta es la misma que C-08 usó para `mis-equipos`: usar la identidad del JWT
como scope natural, sin permiso explícito.

**Cómo funciona en la práctica**:
- `GET /mis-tareas` → `asignado_a == current_user.id`, cualquier rol autenticado.
- `PATCH /tareas/{id}/estado` → el service verifica: ¿`current_user.id == asignado_a` OR
  `current_user.id == asignado_por` OR tiene `tareas_internas:gestionar`? Si ninguna → 403.
- `POST /tareas/{id}/comentarios` → misma lógica de membership check.
- `GET /tareas/{id}` → misma lógica de membership check.

**Registro de la decisión**: F8.1 incluye a TUTOR aunque la matriz no le da `gestionar`.
La solución es identity-based en las operaciones self-scoped. No se agrega permiso nuevo al seed.

---

## D-C16-2: Scope "own" del PROFESOR en creación de tareas

**Decisión**: cuando un usuario con `tareas_internas:gestionar` scope=`own` (PROFESOR) crea una
tarea, el service impone:

- Si `materia_id` está presente → verificar que el PROFESOR tenga al menos una `Asignacion` vigente
  a esa materia en el tenant. Si no → 403.
- Si `materia_id` es `null` (tarea institucional sin contexto de materia) → solo puede crearla si
  tiene scope=`all` (COORDINADOR, ADMIN). PROFESOR no puede crear tareas sin materia.

**Cómo computar "propio"**: en el service, tras resolver el scope del permiso, si scope=`own`:
```python
if payload.materia_id is None:
    raise HTTPException(403, "PROFESOR requiere materia_id para crear tareas")
vigente = await asignacion_repo.existe_vigente(
    tenant_id, current_user.id, materia_id=payload.materia_id
)
if not vigente:
    raise HTTPException(403, "Sin asignación vigente en esa materia")
```

**El COORDINADOR** (scope=all) puede crear tareas con o sin `materia_id`: tareas institucionales
y de materia específica.

**Pregunta abierta D-C16-2-OQ**: ¿el PROFESOR con scope='own' puede asignar tareas a usuarios
de CUALQUIER materia o solo a usuarios dentro de su misma asignación (misma materia × cohorte)?
**Propuesta**: solo verificamos que la materia sea del PROFESOR; el `asignado_a` puede ser cualquier
usuario del tenant. Si se quiere restricción adicional sobre el `asignado_a`, se cierra como
decisión en el PR de implementación.

---

## D-C16-3: FSM de estados y transiciones válidas

**Decisión**: 4 estados con las siguientes transiciones permitidas:

```
Pendiente ──────► En progreso ──────► Resuelta   (terminal)
    │                  │
    └──────────────────┴──────────────► Cancelada  (terminal)
```

| Transición | Desde | Hacia | Quién puede ejecutarla |
|------------|-------|-------|------------------------|
| Iniciar trabajo | Pendiente | En progreso | `asignado_a`, gestores |
| Resolver | En progreso | Resuelta | `asignado_a`, gestores |
| Cancelar (temprana) | Pendiente | Cancelada | `asignado_por`, gestores |
| Cancelar (tarde) | En progreso | Cancelada | gestores únicamente |

**Gestores** = usuarios con `tareas_internas:gestionar` en el tenant (COORDINADOR, ADMIN; PROFESOR
solo sobre sus propias tareas scope=own).

**Estados terminales**: Resuelta y Cancelada no admiten transición. Si se intenta → 422 con
código `TAREA_ESTADO_TERMINAL`.

**Razón de limitar cancelación desde En progreso a gestores**: el `asignado_a` no debe poder
auto-cancelar una tarea en curso para eludirla. El `asignado_por` (si es PROFESOR scope=own) sí
puede cancelar desde Pendiente (antes de que el asignado empiece).

**No se expone la FSM en un campo separado**: la entidad solo guarda `estado`. La validación de
transiciones ocurre en `TareaService.cambiar_estado()`.

---

## D-C16-4: Trazabilidad F8.2 — asignado_por siempre es current_user

**Decisión**: `asignado_por` se fija en el service como `current_user.id` en el momento de
crear la tarea. No es un campo editable del request body.

```python
tarea = Tarea(
    tenant_id=tenant_id,
    asignado_por=current_user.id,   # siempre del JWT
    asignado_a=payload.asignado_a,
    materia_id=payload.materia_id,
    descripcion=payload.descripcion,
    contexto_id=payload.contexto_id,
    estado="Pendiente",
)
```

**Consecuencia**: la delegación de tareas (F8.2) crea una tarea nueva con el delegador como
`asignado_por`. No existe "re-asignación" que mute el `asignado_a` de una tarea existente — ese
flujo se implementa como: crear nueva tarea (asignado_por = quien delega, asignado_a = destino) y
cancelar la original. Esta decisión evita ambigüedad en el historial de auditoría.

**Pregunta abierta D-C16-4-OQ**: ¿se requiere un endpoint `PATCH /tareas/{id}/asignado_a` para
re-asignar una tarea sin crear una nueva? Propuesta: no en C-16 — crear nueva + cancelar es
suficiente para el flujo descrito en F8.2. Si surge como necesidad, se agrega en un change futuro.

---

## D-C16-5: F8.3 — Vista global con filtros

**Decisión**: `GET /api/v1/tareas` (requiere `tareas_internas:gestionar` all) expone los siguientes
query params:

| Param | Tipo | Descripción |
|-------|------|-------------|
| `asignado_a` | UUID (opt) | FK → Usuario |
| `asignado_por` | UUID (opt) | FK → Usuario |
| `materia_id` | UUID (opt) | FK → Materia |
| `estado` | str (opt) | `Pendiente`, `En progreso`, `Resuelta`, `Cancelada` |
| `q` | str (opt) | Búsqueda libre sobre `descripcion` (ilike) |
| `limit` | int (opt, default 50, max 200) | Paginación |
| `offset` | int (opt, default 0) | Paginación |

**PROFESOR con scope=own** en `GET /tareas`: el service aplica filtro automático
`(asignado_por == current_user.id OR asignado_a == current_user.id)` cuando scope=own, sin
importar qué filtros envíe el request. No puede ver tareas ajenas.

**Pregunta abierta D-C16-5-OQ**: ¿el PROFESOR scope=own debería ver SOLO tareas donde es
`asignado_por`, o también donde es `asignado_a`? Propuesta: ambas — es la vista de "mis tareas
gestionadas", que incluye tanto las que delegó como las que le delegaron.

---

## D-C16-6: contexto_id — referencia blanda opaca sin FK de base de datos

**Decisión**: `contexto_id` es un `UUID nullable` sin FK constraint en la tabla `tarea`.

**Justificación**: `contexto_id` puede referenciar entidades de distintas tablas
(instancia_encuentro, evaluacion, aviso, etc.) — el tipo de target varía. Imponer una FK estricta
requeriría que el campo sea polimórfico (patrón EAV o FK múltiple), lo que complica las queries y
las migraciones. La alternativa correcta es una **referencia blanda**: el caller sabe qué entidad
representa. Si en el futuro se necesita tipado, se agrega un campo `contexto_tipo: str | None`
en un change posterior.

**Consecuencia**: el endpoint que recibe `contexto_id` no verifica que el UUID exista en ninguna
tabla. Es responsabilidad del caller enviar un UUID válido. No genera error 404 si el contexto
referenciado fue soft-deleted después.

---

## D-C16-7: ComentarioTarea — membership check, no permiso

**Decisión**: las rutas de comentarios (`POST /tareas/{id}/comentarios`,
`GET /tareas/{id}/comentarios`) usan un **membership check** en el service, no `require_permission`.

El check es:
```python
def _puede_comentar(current_user, tarea, scope) -> bool:
    return (
        current_user.id == tarea.asignado_a
        or current_user.id == tarea.asignado_por
        or scope is not None   # tiene tareas_internas:gestionar en el tenant
    )
```

**Por qué no usar require_permission aquí**: TUTOR (asignado_a) debe poder comentar, pero no tiene
el permiso. Un COORDINADOR (que sí tiene el permiso pero no es asignado_a ni asignado_por) también
debe poder comentar como gestor. La lógica de membresía es la herramienta correcta.

**autor_id** del comentario = `current_user.id` siempre — nunca proviene del request body.

**PII en comentarios**: el response de comentario incluye `autor_id: UUID`, `autor_nombre: str`,
`autor_apellidos: str`. Nunca incluye email (cifrado en BD, regla §12 CLAUDE.md). El service hace
join con `user` para resolver nombre y apellidos.

---

## D-C16-8: PII en responses — usuarios por UUID, nombres visibles, email nunca

**Decisión**: todos los responses de tareas y comentarios incluyen:
- `asignado_a_id: UUID`, `asignado_a_nombre: str`, `asignado_a_apellidos: str`
- `asignado_por_id: UUID`, `asignado_por_nombre: str`, `asignado_por_apellidos: str`
- `autor_id: UUID`, `autor_nombre: str`, `autor_apellidos: str` (comentarios)

**Nunca** se expone `email` (cifrado en BD), `dni`, `cuil`, `cbu`. El service resuelve los nombres
via join con la tabla `user`. Los campos `email_cifrado`, `email_hash`, etc. no se incluyen en
ningún schema de respuesta de este módulo.

---

## D-C16-9: Fixture de test — cleanup scoped por tenant, orden FK estricto

**Decisión**: el helper de cleanup de los tests de C-16 usa el patrón de C-13 (scoped por
`tenant.codigo`, no DELETE global). El orden de borrado respeta las FKs:

```python
async def _delete_tar_tenant_data(session, *codes):
    for code in codes:
        tid_sub = "(SELECT id FROM tenant WHERE codigo = :c)"
        # 1. FK hoja primero
        await session.execute(text(f"DELETE FROM comentario_tarea WHERE tenant_id IN {tid_sub}"), {"c": code})
        await session.execute(text(f"DELETE FROM tarea WHERE tenant_id IN {tid_sub}"), {"c": code})
        await session.execute(text(f"DELETE FROM audit_log WHERE tenant_id IN {tid_sub}"), {"c": code})
        # 2. Dependencias de usuario
        for table in ("asignacion", "cohorte", "materia", "carrera"):
            await session.execute(text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"), {"c": code})
        # 3. RBAC
        for table in ("user_rol", "rol_permiso", "permiso", "rol"):
            await session.execute(text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"), {"c": code})
        # 4. Tokens de sesión
        for table in ("refresh_token", "recovery_token"):
            await session.execute(
                text(f'DELETE FROM {table} WHERE user_id IN '
                     f'(SELECT id FROM "user" WHERE tenant_id IN {tid_sub})'),
                {"c": code}
            )
        # 5. Usuarios y tenant
        await session.execute(text(f'DELETE FROM "user" WHERE tenant_id IN {tid_sub}'), {"c": code})
        await session.execute(text("DELETE FROM tenant WHERE codigo = :c"), {"c": code})
    await session.commit()
```

**Por qué scoped y no global**: el patrón de C-13 evitó el "pantano" de C-15 donde un DELETE
global bloqueó tests concurrentes de otras suites. El scoping por `tenant.codigo` con prefijo único
(`tar-test-a`, `tar-test-b`) garantiza que la limpieza del fixture de C-16 no interfiere con
datos de otros módulos.

**Prefijos recomendados**: `tar-test-a`, `tar-test-b` (cortos, únicos para este módulo).

---

## D-C16-10: Auditoría — solo escrituras críticas

**Decisión**: las operaciones de escritura auditables son:

| Operación | Código audit | `filas_afectadas` |
|-----------|-------------|-------------------|
| Crear tarea | `TAREA_ASIGNAR` | 1 |
| Cambiar estado | `TAREA_ESTADO_CAMBIAR` | 1 |

Los comentarios y las lecturas no generan evento de auditoría.

**Detalle JSON para `TAREA_ASIGNAR`**:
```json
{
  "tarea_id": "uuid",
  "asignado_a": "uuid",
  "materia_id": "uuid | null",
  "estado_inicial": "Pendiente"
}
```

**Detalle JSON para `TAREA_ESTADO_CAMBIAR`**:
```json
{
  "tarea_id": "uuid",
  "estado_anterior": "Pendiente",
  "estado_nuevo": "En progreso"
}
```

---

## Open Questions para C-16

| ID | Pregunta | Propuesta del diseño |
|----|----------|---------------------|
| OQ-C16-1 | ¿PROFESOR scope=own puede asignar a cualquier usuario del tenant o solo a su equipo de materia? | Solo verifica que `materia_id` le pertenezca; `asignado_a` es libre. |
| OQ-C16-2 | ¿Existe endpoint de re-asignación (`PATCH /tareas/{id}/asignado_a`)? | No en C-16; crear nueva + cancelar cubre F8.2. Decidir en PR. |
| OQ-C16-3 | ¿El PROFESOR con scope=own ve en `GET /tareas` solo las que creó o también las que le asignaron? | Ambas (asignado_por OR asignado_a). Decidir en PR si se restringe. |
| OQ-C16-4 | ¿El `contexto_tipo` (texto que indica qué tipo de entidad referencia `contexto_id`) es necesario en C-16? | No; queda opaco. Agregar en futuro change si el frontend lo necesita. |
