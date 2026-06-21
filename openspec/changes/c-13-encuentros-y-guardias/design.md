# C-13 — Design

> Decisiones de diseño a resolver ANTES de implementar. Las marcadas ⚠️ son bloqueantes.

---

## D-C13-1 ⚠️ — Algoritmo de generación de instancias recurrentes (RN-13)

**Contexto**: E9 tiene `dia_semana`, `fecha_inicio`, `cant_semanas` para el modo recurrente.

**Ambigüedad**: ¿`fecha_inicio` debe coincidir obligatoriamente con `dia_semana`? ¿O el sistema busca la primera ocurrencia de ese dia_semana >= fecha_inicio?

**Opciones**:

| Opción | Descripción | Ventaja | Riesgo |
|---|---|---|---|
| A | Validar que `fecha_inicio.weekday() == dia_semana`. Si no coincide → 422 | Semántica clara, sin sorpresas | El usuario debe saber en qué día cae la fecha |
| B | Ajustar `fecha_inicio` a la primera ocurrencia de `dia_semana` >= `fecha_inicio` | Más ergonómico | La primera instancia puede no ser `fecha_inicio`, sorprendente |

**Recomendación**: **Opción A**. `fecha_inicio` debe caer en `dia_semana`; el sistema valida y devuelve 422 con mensaje claro si no coincide.

**Algoritmo de generación** (Opción A):

```
Validar: fecha_inicio.isoweekday() == DIA_SEMANA_ENUM_TO_ISO[slot.dia_semana]
Si no → raise ValueError("fecha_inicio_no_coincide_con_dia_semana")

Para i en range(0, cant_semanas):
    fecha_instancia = fecha_inicio + timedelta(weeks=i)
    INSERT InstanciaEncuentro(
        slot_id=slot.id,
        materia_id=slot.materia_id,
        asignacion_id=slot.asignacion_id,   # denormalizado para scoping
        fecha=fecha_instancia,
        hora=slot.hora,
        titulo=slot.titulo,
        estado=Programado,
        meet_url=slot.meet_url,
    )
```

Ejemplo: `fecha_inicio=2026-09-07` (lunes), `cant_semanas=4` → instancias en 2026-09-07, 2026-09-14, 2026-09-21, 2026-09-28.

**Modo único** (F6.2):

```
Precondición: fecha_unica NOT NULL, cant_semanas=0, dia_semana=NULL

INSERT InstanciaEncuentro(
    slot_id=slot.id,
    fecha=slot.fecha_unica,
    hora=slot.hora,
    titulo=slot.titulo,
    estado=Programado,
    meet_url=slot.meet_url,
)
```

**Decisión a confirmar**: ¿Opción A (validar) o Opción B (ajustar)?

---

## D-C13-2 ⚠️ — Enum de estado de instancia: 3 vs 4 estados (inconsistencia RN-14 vs E10)

**Inconsistencia en la KB**:
- **E10** define: `estado: enum — Programado | Realizado | Cancelado` (3 estados)
- **RN-14** menciona literalmente: *"programado, realizado, cancelado, **reprogramado**"* (4 estados)

**Opciones**:

| Opción | Estados | Implicaciones |
|---|---|---|
| A — Seguir E10 | Programado, Realizado, Cancelado | Reprogramado = Cancelado + nueva InstanciaEncuentro. Migración más simple. |
| B — Agregar Reprogramado | + Reprogramado | Permite rastrear instancias rescheduled sin duplicar. Migración más compleja (nuevo valor enum). |

**Recomendación**: **Opción A** (3 estados, seguir E10). El flujo "reprogramar" = cancelar la instancia original y crear una nueva instancia con fecha diferente. Esto mantiene el histórico y es consistente con soft-delete. RN-14 parece editorial, no un cuarto estado de dominio.

**Decisión a confirmar**: ¿3 estados (E10) o 4 estados (RN-14)?

---

## D-C13-3 ⚠️ — Cómputo del "propio" para encuentros:gestionar (scoping PROFESOR)

**Contexto**: el seed define:
```
TUTOR:      encuentros:gestionar = "all"
PROFESOR:   encuentros:gestionar = "own"
COORDINADOR: encuentros:gestionar = "all"
ADMIN:       encuentros:gestionar = "all"
```

**Problema**: para PROFESOR(own), el servicio debe filtrar por asignación propia. La FK de scope es `SlotEncuentro.asignacion_id → Asignacion.usuario_id == current_user.user_id`.

**Diseño propuesto** (denormalización en InstanciaEncuentro):

`InstanciaEncuentro.asignacion_id` se copia del slot al generar instancias (incluso para instancias standalone). Esto evita JOINs profundos en las consultas de scoping y permite filtrar en 1 nivel.

```python
def _is_own(slot_or_instancia, current_user):
    return slot_or_instancia.asignacion_id in {
        a.id for a in current_user.asignaciones_vigentes
    }
```

En la práctica: el repositorio recibe `asignacion_ids` del usuario y filtra con `WHERE asignacion_id = ANY(:ids)`.

**Nota sobre TUTOR**: TUTOR tiene `encuentros:gestionar = "all"` (no "own"). Puede listar y editar instancias de CUALQUIER docente del tenant. Esto difiere de F6.1-F6.5 que solo mencionan PROFESOR y COORDINADOR — ver D-C13-4.

**Decisión a confirmar**: ¿Aceptar que TUTOR ve todos los encuentros? ¿O restringir TUTOR a "own" en la implementación (overriding el seed)?

---

## D-C13-4 — Inconsistencia F6.1–F6.5 vs matriz de capacidades (TUTOR ausente en funcionalidades)

**Inconsistencia documentada**:

| Fuente | TUTOR en encuentros |
|---|---|
| F6.1–F6.5 (`06_funcionalidades.md`) | No mencionado — solo PROFESOR y COORDINADOR |
| Matriz §3.3 (`03_actores_y_roles.md`) | ✅ "Gestionar encuentros" (sin `propio`) |
| Seed (`scripts/seed_permissions.py`) | `encuentros:gestionar: "all"` |

**Resolución**: la **matriz y el seed son la fuente autoritativa** sobre qué roles tienen qué permisos. La funcionalidad (F6.x) describe flujos de negocio, no la lista exhaustiva de roles. TUTOR tiene `encuentros:gestionar` con scope `all`.

**Consecuencia práctica**: el guard `require_permission("encuentros:gestionar")` deja pasar a TUTOR con acceso global. No hay código especial para TUTOR en este módulo.

---

## D-C13-5 — Restricción de video_url: ¿solo editable en estado Realizado?

**Contexto**: F6.3 dice *"enlace de grabación (disponible después de realizado el encuentro)"*.

**Interpretación A**: `video_url` solo se puede escribir cuando `estado == Realizado`. Si se intenta escribir con estado distinto → 422.

**Interpretación B**: `video_url` es editable siempre; la restricción es de UX (el frontend lo habilita solo tras Realizado), no del backend.

**Recomendación**: **Interpretación B**. La API no impone la restricción temporal (simplifica el service). El mensaje "disponible después de realizado" es una guía de UX, no una regla de negocio codificada. Si en el futuro se decide imponer, es un cambio mínimo.

**Decisión a confirmar**: ¿Backend permisivo (B) o backend restrictivo (A)?

---

## D-C13-6 ⚠️ — Guardia: campo `dia` (dia_semana) vs fecha específica

**Inconsistencia en E11**:

```
Guardia {
  dia: enum — día de la semana   ← solo weekday, no fecha específica
  horario: texto — "14:00–14:45"
  estado: Pendiente | Realizada | Cancelada   ← implica una ocurrencia puntual
}
```

**Problema**: si `dia` es solo el día de la semana (Lunes, Martes…), no hay forma de distinguir la guardia del lunes 2-Mar de la del lunes 9-Mar. Sin embargo, `estado: Pendiente→Realizada` implica una instancia única.

**Opciones**:

| Opción | Campo | Ventaja | Riesgo |
|---|---|---|---|
| A | Agregar `fecha DATE` (específica) | Instancia inequívoca, histórico correcto | Requiere campo nuevo no en E11 |
| B | Mantener solo `dia` (weekday) | Fiel a E11 | Ambigüedad: no distingue semanas distintas |
| C | `dia DATE` (fecha específica, renombrando el campo) | Claro y concreto | Break del modelo E11 |

**Recomendación**: **Opción A**. Agregar `fecha DATE NOT NULL` a `Guardia` (campo adicional a `dia`). El campo `dia` se mantiene pero se deriva de `fecha.weekday()` o se almacena como informativo. Esto permite consultas por rango de fechas (F6.6: "filtros") y auditoría precisa.

**Decisión a confirmar**: ¿Agregar `fecha DATE` a Guardia o ceñirse al modelo E11?

---

## D-C13-7 — Fragmento LMS (F6.4): contenido y formato

**Contexto**: C-17 generó un fragmento Markdown de fechas académicas. C-13 necesita un fragmento equivalente para encuentros.

**Diseño propuesto**:

```
GET /api/v1/encuentros/fragmento-lms?materia_id=...
```

Retorna un bloque Markdown listo para copiar al aula virtual:

```markdown
## Encuentros — {Materia.nombre}

### Programados
- **Lunes 07-Sep-2026 18:00** — Clase 1 | [Sala virtual](https://meet.example.com/...)
- **Lunes 14-Sep-2026 18:00** — Clase 2 | [Sala virtual](...)

### Realizados
- **Lunes 31-Ago-2026 18:00** — Presentación | [Grabación](https://drive.example.com/...)
```

Incluye: instancias `Programado` (con meet_url si la tiene) y `Realizado` (con video_url si la tiene). No incluye `Cancelado`.
Filtro: scoped al usuario (si PROFESOR, solo sus instancias; si COORDINADOR, requiere materia_id como query param).

**Decisión a confirmar**: ¿Incluir solo Programado, o también Realizado (con video_url)?

---

## D-C13-8 — Guardia: ¿BaseEntityMixin o columnas explícitas?

**E11** especifica `creada_at` pero no `updated_at`. Sin embargo, para auditoría (soft-delete) y consistencia con el resto del proyecto, `BaseEntityMixin` (que tiene id + created_at + updated_at + deleted_at + tenant_id) es la elección natural.

**Recomendación**: usar `BaseEntityMixin` en `Guardia`. El `updated_at` es overhead mínimo que evita problemas de auditoría futura. Igual que en `HiloMensaje` de C-20.

---

## Migración 017 — Tablas nuevas

```
slot_encuentro:
  id UUID PK, tenant_id FK→tenant, asignacion_id FK→asignacion, materia_id FK→materia
  titulo VARCHAR(255), hora TIME, dia_semana VARCHAR(20)
  fecha_inicio DATE nullable, cant_semanas INTEGER DEFAULT 0
  fecha_unica DATE nullable, meet_url TEXT nullable
  vig_desde DATE nullable, vig_hasta DATE nullable
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ

instancia_encuentro:
  id UUID PK, tenant_id FK→tenant
  slot_id UUID FK→slot_encuentro nullable, asignacion_id FK→asignacion
  materia_id FK→materia
  fecha DATE, hora TIME, titulo VARCHAR(255)
  estado VARCHAR(20) CHECK IN ('Programado','Realizado','Cancelado')
  meet_url TEXT nullable, video_url TEXT nullable, comentario TEXT nullable
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ

guardia:
  id UUID PK, tenant_id FK→tenant, asignacion_id FK→asignacion
  materia_id FK→materia, carrera_id FK→carrera, cohorte_id FK→cohorte
  dia VARCHAR(20), fecha DATE nullable [D-C13-6]
  horario VARCHAR(50)
  estado VARCHAR(20) CHECK IN ('Pendiente','Realizada','Cancelada')
  comentarios TEXT nullable
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ
```

Índices: `(tenant_id, materia_id)` en slot e instancia; `(tenant_id, asignacion_id)` en los tres.

---

## Resumen de decisiones abiertas

| ID | Decisión | Opciones | Recomendación | Bloqueante |
|---|---|---|---|---|
| D-C13-1 | Validar fecha_inicio vs dia_semana vs ajustar | A=validar, B=ajustar | A | ⚠️ |
| D-C13-2 | Enum 3 vs 4 estados (Reprogramado) | A=3, B=4 | A | ⚠️ |
| D-C13-3 | Scope "propio" via asignacion_id denormalizado | — | Denormalizar en instancia | ⚠️ |
| D-C13-4 | TUTOR accede a todos los encuentros | Seguir matrix/seed | Sí | — |
| D-C13-5 | video_url: backend restrictivo vs permisivo | A=restrictivo, B=permisivo | B | — |
| D-C13-6 | Guardia fecha específica | A=agregar fecha, B=solo dia_semana | A | ⚠️ |
| D-C13-7 | Fragmento LMS: solo Programado vs + Realizado | — | Incluir Realizado con video | — |
| D-C13-8 | Guardia usa BaseEntityMixin | — | Sí | — |
