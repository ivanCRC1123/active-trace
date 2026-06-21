# C-13 — Propuesta: encuentros-y-guardias

> Estado: PROPUESTA — sin implementar. Aprobación requerida antes de codear.

---

## Resumen ejecutivo

Implementa la Épica 6 completa (F6.1–F6.6):

- **Encuentros** (F6.1–F6.5): slots con generación automática de instancias (recurrente o único), edición de instancias, vista global, fragmento LMS.
- **Guardias** (F6.6): registro por TUTOR/PROFESOR propio, consulta global + export por COORDINADOR/ADMIN.

Entidades nuevas: E9 `SlotEncuentro`, E10 `InstanciaEncuentro`, E11 `Guardia`.
Reglas de negocio: RN-13 (dos modos de slot), RN-14 (estado de instancia independiente).

---

## Scope

### Sección A — Encuentros

| Funcionalidad | F-ref | Quien | Descripción |
|---|---|---|---|
| Crear slot recurrente | F6.1 | TUTOR, PROFESOR(own), COORDINADOR, ADMIN | dia_semana + hora + fecha_inicio + cant_semanas → N instancias |
| Crear encuentro único | F6.2 | TUTOR, PROFESOR(own), COORDINADOR, ADMIN | fecha_unica + hora → 1 instancia |
| Editar instancia | F6.3 | TUTOR, PROFESOR(own), COORDINADOR, ADMIN | estado, meet_url, video_url, comentario |
| Fragmento LMS | F6.4 | TUTOR, PROFESOR(own), COORDINADOR, ADMIN | texto formateado con encuentros programados |
| Vista global encuentros | F6.5 | COORDINADOR, ADMIN | todos los encuentros del tenant |

### Sección B — Guardias

| Funcionalidad | F-ref | Quien | Descripción |
|---|---|---|---|
| Registrar guardia | F6.6 | TUTOR(own), PROFESOR(own), COORDINADOR, ADMIN | registro de guardia cubierta |
| Consultar + filtrar | F6.6 | COORDINADOR, ADMIN | vista global con filtros |
| Exportar | F6.6 | COORDINADOR, ADMIN | CSV descargable |

---

## Dependencias

| Change | Relación |
|---|---|
| C-07 ✓ | Asignacion (FK de slot y guardia) + User model |
| C-05 ✓ | AuditService (audit_codes a agregar) |
| C-06 ✓ | Materia, Carrera, Cohorte (FKs) |

---

## Impacto técnico

- **Migración 017**: tablas `slot_encuentro`, `instancia_encuentro`, `guardia` + enum `dia_semana`
- **Modelos**: `SlotEncuentro`, `InstanciaEncuentro`, `Guardia`
- **Repositorios**: `SlotRepository`, `InstanciaRepository`, `GuardiaRepository`
- **Schemas**: `SlotCreate`, `InstanciaUpdate`, `GuardiaCreate`, responses
- **Servicios**: `EncuentroService` (crear/listar/editar/fragmento), `GuardiaService`
- **Routers**: `/api/v1/encuentros/*`, `/api/v1/guardias/*`
- **Audit codes**: `ENCUENTRO_CREAR`, `ENCUENTRO_EDITAR_INSTANCIA`, `GUARDIA_REGISTRAR`
- **Tests**: 2 archivos de test (~25 tests en total)

---

## Governance

**MEDIO** — lógica de dominio (generación de instancias, scoping propio), sin tocar auth/tenancy/RBAC core.

Checkpoints antes de implementar:
1. Resolución de 7 decisiones de design (ver design.md)
2. Confirmación del algoritmo de generación de fechas recurrentes
3. Confirmación del enum de estados de instancia (3 vs 4 estados)

---

## Fuera de scope

- Integración directa con Moodle para publicar el fragmento (acción manual del docente, F6.4)
- Notificaciones automáticas por cambio de estado de encuentro
- Vista del ALUMNO de los encuentros programados
