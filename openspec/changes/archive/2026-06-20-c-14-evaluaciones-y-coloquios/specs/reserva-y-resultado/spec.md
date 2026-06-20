# Spec: reserva-y-resultado

## Objetivo

Modelos ORM `ReservaEvaluacion` y `ResultadoEvaluacion` (E14 del KB), sus repositorios y la
lógica de negocio de cupos en `ColoquiosService`.

## Modelo `ReservaEvaluacion` (`backend/app/models/evaluacion.py`)

```python
class ReservaEvaluacion(Base, BaseEntityMixin):
    __tablename__ = "reserva_evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "evaluacion_id", "alumno_id",
            name="uq_reserva_evaluacion_alumno",
        ),
    )

    evaluacion_id : Mapped[UUID]         # FK → evaluacion.id RESTRICT, index=True
    alumno_id     : Mapped[UUID]         # FK → usuario.id RESTRICT, index=True
    fecha_hora    : Mapped[datetime]     # DateTime(timezone=True), nullable=False
    estado        : Mapped[EstadoReserva] # sa.Enum(EstadoReserva, name="estado_reserva", create_type=True)
```

**Ciclo de vida:** `Activa → Cancelada` (unidireccional, sin vuelta atrás).

**Unique constraint `(tenant_id, evaluacion_id, alumno_id)`**: impide registrar dos reservas
del mismo alumno para la misma evaluacion **independientemente del estado**. Si un alumno
cancela y quiere reservar nuevamente, el service hace soft-delete de la reserva cancelada
antes de crear la nueva.

**Enum `estado_reserva`**: creado en migración 012 con `checkfirst=True`. A diferencia de
`tipo_evaluacion` (compartido con C-17), este es exclusivo de C-14.

## Modelo `ResultadoEvaluacion` (`backend/app/models/evaluacion.py`)

```python
class ResultadoEvaluacion(Base, BaseEntityMixin):
    __tablename__ = "resultado_evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "evaluacion_id", "alumno_id",
            name="uq_resultado_evaluacion_alumno",
        ),
    )

    evaluacion_id : Mapped[UUID]  # FK → evaluacion.id RESTRICT, index=True
    alumno_id     : Mapped[UUID]  # FK → usuario.id RESTRICT, index=True
    nota_final    : Mapped[str]   # String(255) — puede ser numérica ("8") o cualitativa ("Aprobado")
```

**No tiene ciclo de estados.** Si se necesita corregir una nota: UPDATE directo del registro
existente. El cambio se audita con `RESULTADO_REGISTRAR` pasando `old_value → new_value` en el
campo `detalle` del AuditLog (JSON con `{"nota_anterior": ..., "nota_nueva": ...}`).

**Unique constraint**: un único resultado activo por `(tenant_id, evaluacion_id, alumno_id)`.
Si no existe, se crea; si ya existe, se actualiza y se registra la auditoría.

**Audit code**: `RESULTADO_REGISTRAR` debe agregarse a `backend/app/core/audit_codes.py`.

## Repositorios

```python
class ReservaRepository(BaseRepository[ReservaEvaluacion]):
    model_class = ReservaEvaluacion

    async def get_activa_by_alumno(
        self, evaluacion_id: UUID, alumno_id: UUID,
    ) -> ReservaEvaluacion | None:
        """Reserva Activa del alumno en esa evaluación (no eliminada)."""

    async def list_activas_by_evaluacion(
        self, evaluacion_id: UUID,
    ) -> list[ReservaEvaluacion]:
        """Lista de reservas activas para el detalle / agenda."""

    async def count_activas(self, evaluacion_id: UUID) -> int:
        """Para calcular cupos_libres = cupo_total - count_activas."""


class ResultadoRepository(BaseRepository[ResultadoEvaluacion]):
    model_class = ResultadoEvaluacion

    async def get_by_alumno(
        self, evaluacion_id: UUID, alumno_id: UUID,
    ) -> ResultadoEvaluacion | None:
        """Resultado activo del alumno (deleted_at IS NULL)."""

    async def list_by_evaluacion(
        self, evaluacion_id: UUID,
    ) -> list[ResultadoEvaluacion]:
        """Registro académico de la evaluación."""
```

## Schemas Pydantic adicionales (`backend/app/schemas/coloquios.py`)

```python
class ReservaCreate(BaseModel):
    fecha_hora : datetime  # el alumno elige la fecha/hora del turno
    model_config = ConfigDict(extra='forbid')

class ReservaResponse(BaseModel):
    id            : UUID
    tenant_id     : UUID
    evaluacion_id : UUID
    alumno_id     : UUID
    fecha_hora    : datetime
    estado        : EstadoReserva
    created_at    : datetime
    updated_at    : datetime
    model_config = ConfigDict(extra='forbid', from_attributes=True)

class ResultadoCreate(BaseModel):
    alumno_id  : UUID
    nota_final : str  # min_length=1, max_length=255
    model_config = ConfigDict(extra='forbid')

class ResultadoResponse(BaseModel):
    id            : UUID
    tenant_id     : UUID
    evaluacion_id : UUID
    alumno_id     : UUID
    nota_final    : str
    created_at    : datetime
    model_config = ConfigDict(extra='forbid', from_attributes=True)
```

## Lógica de negocio de cupos (`ColoquiosService`)

### `reservar_turno(evaluacion_id, alumno_id, fecha_hora, tenant_id)`

```
1. Verificar que evaluacion existe en el tenant → 404 si no.
2. Verificar cupo disponible (si cupo_total > 0):
   activas = await repo.count_activas(evaluacion_id)
   si activas >= cupo_total → raise ValueError("sin_cupo") → 409 en router
3. Verificar si el alumno ya tiene reserva activa → 409 si existe.
4. Si tiene reserva cancelada (hard-unique constraint lo impediría), hacer soft-delete de la
   cancelada antes de insertar la nueva.
5. Insertar ReservaEvaluacion con estado=Activa.
6. Retornar la reserva.
```

**Nota SELECT FOR UPDATE**: el service ejecuta el `count_activas` en la misma transacción con
`with_for_update()` en la fila de `Evaluacion` para evitar race conditions bajo concurrencia.

### `cancelar_reserva(reserva_id, alumno_id, tenant_id)`

```
1. Obtener reserva → 404 si no existe o no pertenece al alumno.
2. Verificar que estado == Activa → 409 si ya está Cancelada.
3. Actualizar estado = Cancelada.
4. Retornar la reserva actualizada.
```

El alumno solo puede cancelar sus propias reservas (verificado por `alumno_id == current_user.id`
en el router).

### `registrar_resultado(evaluacion_id, alumno_id, nota_final, tenant_id, actor_id)`

```
1. Verificar evaluacion en tenant → 404.
2. Verificar alumno en tenant → 404.
3. Verificar si existe resultado previo (no eliminado):
   - Si NO existe → INSERT nuevo ResultadoEvaluacion.
   - Si SÍ existe → UPDATE nota_final + audit log RESULTADO_REGISTRAR con
     detalle={"nota_anterior": old, "nota_nueva": new, "alumno_id": str(alumno_id)}.
4. Retornar el resultado.
```

**Auditoría**: `AuditService.log(accion=RESULTADO_REGISTRAR, detalle={...}, actor_id=actor_id)`.
El código `RESULTADO_REGISTRAR` se agrega al catálogo en `audit_codes.py`.

## Criterios de aceptación

- [ ] `reserva_evaluacion` y `resultado_evaluacion` en DB con columnas y constraints.
- [ ] `estado_reserva` ENUM creado en migración 012 con `checkfirst=True`.
- [ ] Reserva con cupo disponible → 201.
- [ ] Reserva sin cupo (`activas >= cupo_total` y `cupo_total > 0`) → 409.
- [ ] `cupo_total = 0` nunca rechaza por cupo (sin límite).
- [ ] Alumno con reserva Activa previa → 409 al intentar reservar de nuevo.
- [ ] Cancelar reserva Activa → estado Cancelada, cupo liberado.
- [ ] Cancelar reserva ya Cancelada → 409.
- [ ] El alumno solo puede cancelar su propia reserva (403 si intenta cancelar la de otro).
- [ ] Registrar resultado cuando no existe → INSERT → 201.
- [ ] Registrar resultado cuando ya existe → UPDATE nota_final → audit log RESULTADO_REGISTRAR con detalle old→new.
- [ ] `nota_final` rechaza cadena vacía (Pydantic `min_length=1`).
- [ ] `RESULTADO_REGISTRAR` está en `VALID_ACTION_CODES`.
