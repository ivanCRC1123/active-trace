# Spec: equipos-router

## Objetivo

Nuevo router FastAPI bajo `/api/v1/equipos/` con 6 endpoints que cubren F4.2–F4.7.
Se monta en `app/main.py` junto a los routers existentes.

## Permiso base

Los 6 endpoints usan dos guards:
- `equipos:ver` (own/all según rol) → mis-equipos.
- `equipos:asignar` (all) → todos los demás.

Ambos se resuelven via `require_permission(...)` de C-04.

## Endpoints declarados

```
GET    /api/v1/equipos/mis-equipos      → spec: mis-equipos
GET    /api/v1/equipos                  → spec: gestion-asignaciones
POST   /api/v1/equipos/masiva           → spec: masiva
POST   /api/v1/equipos/clonar           → spec: clonar
PATCH  /api/v1/equipos/vigencia         → spec: vigencia-bloque
GET    /api/v1/equipos/exportar         → spec: exportar
```

## Registro en `main.py`

```python
from app.api.v1.routers import equipos as equipos_router

app.include_router(equipos_router.router, prefix="/api/v1", tags=["equipos"])
```

## Convenciones

- Todos los errors de negocio → `HTTPException` con código apropiado.
- `404` para FKs que no existen en el tenant.
- `400` para violaciones de reglas de negocio (hasta < desde, etc.).
- `422` para validaciones de input (usuario_ids inválidos en masiva).
- `403` para permisos faltantes (guard automático de `require_permission`).

## Servicio

El router delega toda lógica a `EquipoService` (nuevo, `app/services/equipo_service.py`).
El repositorio base es `AsignacionRepository` de C-07; el service lo instancia via DI.

## Criterios de aceptación

- [ ] Router montado en `/api/v1/equipos/`.
- [ ] Cada endpoint declara explícitamente su guard (`require_permission`).
- [ ] Sin lógica de negocio en el router (delegación pura a EquipoService).
- [ ] Linter y tests pasan sin errores.
