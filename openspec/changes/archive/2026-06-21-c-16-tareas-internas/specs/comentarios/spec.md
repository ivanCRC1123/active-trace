# Spec: comentarios (hilo de ComentarioTarea)

## Objetivo

`POST /api/v1/tareas/{id}/comentarios` y `GET /api/v1/tareas/{id}/comentarios` implementan
el hilo asincrónico de seguimiento sobre una tarea. Disponible para los participantes de la
tarea (asignado_a, asignado_por) y para gestores del tenant.

## Guard

**Membership check** (ver D-C16-7 en design.md) — sin `require_permission` propio:

```python
def _puede_comentar(current_user, tarea, tiene_gestionar_perm) -> bool:
    return (
        current_user.id == tarea.asignado_a
        or current_user.id == tarea.asignado_por
        or tiene_gestionar_perm   # tareas_internas:gestionar (any scope)
    )
```

Si ninguna condición → 403.

---

## POST /api/v1/tareas/{id}/comentarios

### Request body

```json
{ "texto": "Revisé el padrón, faltan 3 alumnos de la comisión B." }
```

`min_length=1`, `max_length=4000`.
`autor_id` = `current_user.id` — nunca proviene del body.

### Response

HTTP 201 con `ComentarioResponse`:

```json
{
  "id": "uuid",
  "tarea_id": "uuid",
  "autor": {
    "id": "uuid",
    "nombre": "María",
    "apellidos": "García"
  },
  "texto": "Revisé el padrón, faltan 3 alumnos de la comisión B.",
  "creado_at": "2026-06-21T14:00:00Z"
}
```

### Validaciones

- Tarea `deleted_at IS NULL` → sino 404.
- Estado terminal de la tarea (Resuelta, Cancelada) NO impide comentar — el hilo sigue
  activo para registro histórico.
- `texto` vacío o solo espacios → 422.

### Criterios de aceptación — POST

- [ ] `autor_id` = `current_user.id`, sin aceptar override del body.
- [ ] `nombre` y `apellidos` del autor resueltos via join, sin email.
- [ ] Tarea en estado terminal → aún permite comentar (201).
- [ ] Usuario ajeno (no asignado_a, no asignado_por, sin permiso) → 403.
- [ ] Tarea de otro tenant → 404.
- [ ] `texto` vacío → 422.

---

## GET /api/v1/tareas/{id}/comentarios

### Guard

Mismo membership check que POST.

### Response

HTTP 200 con lista de `ComentarioResponse` ordenada por `creado_at ASC` (orden cronológico del hilo).

```json
[
  {
    "id": "uuid",
    "tarea_id": "uuid",
    "autor": { "id": "uuid", "nombre": "Carlos", "apellidos": "Pérez" },
    "texto": "Asigno esta tarea a María para revisión.",
    "creado_at": "2026-06-21T10:00:00Z"
  },
  {
    "id": "uuid",
    "tarea_id": "uuid",
    "autor": { "id": "uuid", "nombre": "María", "apellidos": "García" },
    "texto": "Revisé el padrón, faltan 3 alumnos de la comisión B.",
    "creado_at": "2026-06-21T14:00:00Z"
  }
]
```

Lista vacía si la tarea no tiene comentarios. Excluye soft-deleted.

### Criterios de aceptación — GET

- [ ] Orden cronológico ASC por `creado_at`.
- [ ] `[]` si no hay comentarios (HTTP 200).
- [ ] `deleted_at IS NOT NULL` → comentario excluido.
- [ ] Usuario ajeno → 403.
- [ ] Tarea de otro tenant → 404.
- [ ] Nombres resueltos, sin email.

---

## Tests de comentarios

- `test_comentar_asignado_a_201`: TUTOR (asignado_a) comenta → 201.
- `test_comentar_asignado_por_201`: quien asignó comenta → 201.
- `test_comentar_gestor_201`: COORDINADOR que no es parte comenta → 201.
- `test_comentar_usuario_ajeno_403`: usuario sin membresía ni permiso → 403.
- `test_comentar_tarea_otro_tenant_404`.
- `test_comentar_tarea_resuelta_aun_permite`: estado=Resuelta → 201 (hilo abierto).
- `test_comentar_texto_vacio_422`.
- `test_comentar_autor_id_del_jwt`: body con `autor_id` distinto → ignorado, usa JWT.
- `test_get_comentarios_orden_cronologico`: 3 comentarios → orden creado_at ASC.
- `test_get_comentarios_vacio_200`.
- `test_get_comentarios_usuario_ajeno_403`.
- `test_get_comentarios_excluye_soft_deleted`.
