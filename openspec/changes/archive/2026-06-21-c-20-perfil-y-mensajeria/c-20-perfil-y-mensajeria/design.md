# C-20 — Design Decisions

## D-C20-1: Campo `sexo` en Usuario — ¿Agregar o excluir?

**Pregunta**: F11.1 lista "sexo" como campo editable del perfil. E4 (KB 04) NO incluye `sexo`.
¿Se agrega a la tabla `user` vía migración, o se excluye del alcance de C-20?

**Opciones**:

| Opción | Descripción | Trade-off |
|--------|-------------|-----------|
| A (recomendada) | Agregar `sexo VARCHAR(50) nullable` en migración 015 | Cobertura completa de F11.1; campo libre sin enum rígido (evita diccionarios culturales fijos). Un NULL significa "no informado". |
| B | Excluir de C-20, documentar como gap | F11.1 queda parcialmente implementada; requiere un change separado luego. |
| C | Agregar como JSONB `datos_adicionales` para extensibilidad | Over-engineering para C-20; introduce indirección innecesaria. |

**Recomendación**: **Opción A**. Sin enum fijo en DB — el campo acepta cualquier texto.
El frontend puede ofrecer una lista sugerida (sin constraint en DB).

> ⚠️ **DECISIÓN PENDIENTE DE CONFIRMACIÓN**: ¿incluir `sexo` en migración 015?
> Si se confirma Opción B, eliminar la columna `sexo` de la migración y los schemas.

---

## D-C20-2: Actualización atómica de email (blind index + cifrado)

**Problema crítico**: el email en `user` tiene DOS columnas interdependientes:
- `email_cifrado TEXT` — AES-256-GCM para display/recovery (vía EncryptedString TypeDecorator)
- `email_hash VARCHAR(64)` — HMAC-SHA256 para lookup de login (blind index determinístico)

**Si se actualiza solo `email_cifrado`** sin actualizar `email_hash`:
- El display del email cambia correctamente
- El **login falla**: el auth service busca por `email_hash` del email actual del usuario
  pero el hash almacenado corresponde al email viejo → `get_by_email_hash()` devuelve `None` → 401

**Protocolo de actualización en `PerfilService.update_email()`**:

```python
async def update_email(
    self,
    user_id: UUID,
    tenant_id: UUID,
    new_email: str,
) -> None:
    from app.core.encryption import encrypt, hmac_email

    normalized = new_email.strip().lower()
    new_hash = hmac_email(normalized)

    # 1. Verificar unicidad en el tenant (excluir el propio usuario)
    existing = await self._repo.get_by_email_hash(normalized)
    if existing is not None and existing.id != user_id:
        raise ValueError("email_ya_registrado")

    # 2. Actualizar AMBOS campos atómicamente en el mismo flush
    new_cifrado = encrypt(normalized)
    await self._repo.update(user_id, {
        "email_cifrado": new_cifrado,   # EncryptedString TypeDecorator re-cifra
        "email_hash": new_hash,         # blind index actualizado
    })
    # ← un solo await self._session.flush() en BaseRepository.update()
```

**Nota sobre EncryptedString TypeDecorator**: al hacer `setattr(user, "email_cifrado", plaintext)`,
el TypeDecorator llama `encrypt(plaintext)` automáticamente en `process_bind_param`.
Sin embargo, dado que el servicio necesita derivar `email_hash` del mismo email en el mismo paso,
la lógica de normalización debe vivir en el servicio, no en el TypeDecorator.
**La actualización de email no puede pasar por el TypeDecorator de forma independiente**; el service
siempre actualiza los dos campos juntos.

**Unicidad**: `UNIQUE(tenant_id, email_hash)` ya existe (migración 006). Un intento de actualizar a
un email que ya tiene otro usuario en el mismo tenant fallará con `IntegrityError` → mapeado a 409.

---

## D-C20-3: Modelo de threading para mensajería — dos tablas vs self-ref

**Pregunta**: ¿cómo modelar los hilos de mensajes?

**Opción A — Dos tablas (recomendada)**:
```
HiloMensaje {
  id           : UUID PK
  tenant_id    : UUID FK→tenant
  asunto       : TEXT NOT NULL
  iniciador_id : UUID FK→user (quién creó el hilo)
  created_at   : TIMESTAMP
  updated_at   : TIMESTAMP (actualizado con cada mensaje nuevo, para ordenar inbox)
  deleted_at   : TIMESTAMP nullable
}

HiloParticipante {
  hilo_id         : UUID FK→hilo_mensaje
  usuario_id      : UUID FK→user
  ultimo_leido_at : TIMESTAMP nullable  (NULL = nunca leyó)
  PRIMARY KEY(hilo_id, usuario_id)
}

MensajeInterno {
  id           : UUID PK
  tenant_id    : UUID FK→tenant
  hilo_id      : UUID FK→hilo_mensaje
  remitente_id : UUID nullable FK→user  (NULL = mensaje del sistema)
  cuerpo       : TEXT NOT NULL
  created_at   : TIMESTAMP
  deleted_at   : TIMESTAMP nullable
}
```

**Opción B — Tabla única con parent_id self-ref**:
```
MensajeInterno {
  id             : UUID PK
  tenant_id      : UUID FK→tenant
  parent_id      : UUID nullable FK→mensaje_interno  (NULL = raíz del hilo)
  destinatario_id: UUID FK→user  (solo 1 destinatario por mensaje — limitante)
  remitente_id   : UUID nullable FK→user
  asunto         : TEXT (solo en raíz)
  cuerpo         : TEXT
  leido_at       : TIMESTAMP nullable
  created_at     : TIMESTAMP
  deleted_at     : TIMESTAMP nullable
}
```

**Comparación**:

| Criterio | Opción A | Opción B |
|----------|----------|----------|
| N participantes en un hilo | Sí (HiloParticipante M:N) | No (1 destinatario por mensaje) |
| "Mensajes no leídos" por usuario | `HiloParticipante.ultimo_leido_at` vs `MensajeInterno.created_at` | `leido_at` por fila, más simple |
| JOINs en query inbox | 2 JOINs (hilo + participante) | 1 JOIN (self-ref) |
| Escalabilidad futura a grupos | Directa | Requiere refactor de schema |

**Recomendación**: **Opción A**. El FL-10 describe "El sistema... genera un mensaje hacia el inbox
de un docente" — sugiere que el sistema puede ser el iniciador, y en el futuro podrían haber
hilos entre más de 2 participantes (coordinación → equipo docente). La Opción A no es más compleja
de implementar y evita un refactor de schema posterior.

> ⚠️ **DECISIÓN PENDIENTE DE CONFIRMACIÓN**: ¿dos tablas (Opción A) o self-ref (Opción B)?

---

## D-C20-4: Mensajes del sistema en inbox

**Pregunta**: FL-10 dice "El sistema o un usuario... genera un mensaje hacia el inbox de un docente".
¿Cómo se materializa un mensaje originado por el sistema (no por un usuario)?

**Análisis**:
- Avisos (E13, C-15): broadcast por rol/cohorte/global, con ventana de vigencia. No es 1:1.
- Comunicaciones (E21, C-12): emails a alumnos externos. No son mensajes internos entre roles.
- **Gap**: no existe mecanismo para que el sistema envíe una notificación personalizada 1:1 a un
  usuario específico dentro del inbox.

**Opciones**:

| Opción | Descripción |
|--------|-------------|
| A (recomendada) | `MensajeInterno.remitente_id = NULL` marca mensaje del sistema. `es_sistema: bool` derivado en respuesta. |
| B | Campo booleano `es_sistema BOOLEAN NOT NULL DEFAULT FALSE` adicional en `MensajeInterno`. |
| C | Excluir mensajes del sistema del scope de C-20. Solo user-to-user por ahora. |

**Recomendación**: **Opción A**. `remitente_id = NULL` es suficiente indicador. En la respuesta,
el campo `remitente` se devuelve como `null` y el frontend puede renderizarlo como "Sistema".
No hace falta un campo booleano adicional (regla: no agregar campos redundantes).

Sin embargo, si en la práctica el sistema nunca necesita enviar mensajes 1:1 en el estado
actual del product roadmap, es válido elegir **Opción C** y limitar el inbox a user-to-user.
> ⚠️ **DECISIÓN PENDIENTE DE CONFIRMACIÓN**: ¿incluir mensajes del sistema (NULL remitente)?

---

## D-C20-5: Permisos de mensajería — ninguno especial

**Confirmación de diseño**: F3.4 y F11.2 dicen "cualquier usuario autenticado" puede usar el inbox.

- No se crea permiso `mensajes:leer` ni `mensajes:enviar` en el catálogo de permisos (C-04).
- Todos los endpoints de `/api/v1/inbox` usan solo `get_current_user` (JWT verificado).
- El scope es SIEMPRE auto-restringido: un usuario solo ve sus propios hilos (WHERE hilo_id IN
  participantes del current_user).
- Un intento de acceder al hilo de otro usuario → 404 (no 403) para no revelar existencia.

Esta decisión es consistente con C-15 (Avisos) donde los avisos del destinatario no requieren
un permiso especial para ser leídos.

---

## D-C20-6: CUIL como solo lectura — enforcement

**El campo `cuil_cifrado`** es el "identificador fiscal principal" según F11.1 ("solo lectura").

**Enforcement en dos capas**:
1. **Schema**: `PerfilUpdate` NO incluye el campo `cuil`. Pydantic rechaza `extra='forbid'`
   si alguien intenta enviarlo en el body.
2. **Service** (defensivo): `PerfilService.update()` nunca escribe `cuil_cifrado`.

No se genera un error 400 explícito si el campo no está en el schema — simplemente no existe.
Si el ADMIN necesita corregir el CUIL, usa el endpoint `PATCH /api/v1/admin/usuarios/{id}` (C-07).

---

## D-C20-7: Auditoría de edición de perfil

**Código nuevo**: `PERFIL_EDITAR` se agrega a `audit_codes.py`.

**Alternativa descartada** — dos códigos (`PERFIL_EDITAR_EMAIL`, `PERFIL_EDITAR_BANCARIO`):
- Más verboso, requiere lógica condicional en el servicio para elegir qué código usar.
- El catálogo crece innecesariamente.

**Diseño elegido**: un solo código `PERFIL_EDITAR` con `detalle` JSONB indicando
qué campos cambiaron:

```json
{
  "campos_modificados": ["email", "cbu", "banco"],
  "cambio_email": true
}
```

El flag `cambio_email: true` en el detalle permite filtrar en el panel de auditoría (C-19)
las ediciones que tocaron el email sin necesitar un código diferente.

> PII NUNCA en `detalle`: el JSON contiene solo los NOMBRES de campos modificados, nunca los valores.

---

## D-C20-8: Logout — solo documentación (no hay código nuevo)

`POST /api/v1/auth/logout` existe desde C-03 y revoca el refresh token correctamente.

C-20 NO agrega código. El spec de sesion-logout (`specs/sesion-logout/spec.md`) solo documenta
que la capacidad ya existe y refiere al endpoint correcto.

---

## Migración 015 — Resumen

```
revision     = "b7c8d9e0f1a2"
down_revision = "f6a7b8c9d0e1"   ← 014 liquidacion_honorarios

upgrade():
  # 1. Extender tabla user — campo sexo
  op.add_column("user", sa.Column("sexo", sa.String(50), nullable=True))

  # 2. Tabla hilo_mensaje
  op.create_table("hilo_mensaje",
    id UUID PK gen_random_uuid(),
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    asunto TEXT NOT NULL,
    iniciador_id UUID FK→"user" RESTRICT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP nullable,
  )
  # Trigger updated_at en hilo_mensaje
  # Index: idx_hilo_mensaje_tenant WHERE deleted_at IS NULL
  # Index: idx_hilo_mensaje_iniciador WHERE deleted_at IS NULL

  # 3. Tabla hilo_participante (join table, NO BaseEntityMixin)
  op.create_table("hilo_participante",
    hilo_id UUID FK→hilo_mensaje CASCADE NOT NULL,
    usuario_id UUID FK→"user" CASCADE NOT NULL,
    ultimo_leido_at TIMESTAMP nullable,
    PRIMARY KEY (hilo_id, usuario_id),
  )
  # Index: idx_hilo_participante_usuario (para "mis hilos")

  # 4. Tabla mensaje_interno
  op.create_table("mensaje_interno",
    id UUID PK gen_random_uuid(),
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    hilo_id UUID FK→hilo_mensaje CASCADE NOT NULL,
    remitente_id UUID nullable FK→"user" SET NULL,  (NULL = sistema)
    cuerpo TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP nullable,
  )
  # Index: idx_mensaje_interno_hilo WHERE deleted_at IS NULL

downgrade():
  op.drop_table("mensaje_interno")
  op.drop_table("hilo_participante")
  op.drop_table("hilo_mensaje")
  op.drop_column("user", "sexo")
```

---

## Open Questions para C-20

| ID | Pregunta | Impacto | Estado |
|----|----------|---------|--------|
| OQ-C20-1 | ¿Agregar campo `sexo` en migración 015? (D-C20-1) | Schema + migración | ⚠️ PENDIENTE |
| OQ-C20-2 | ¿Modelo de dos tablas o self-ref para mensajería? (D-C20-3) | Tablas + endpoints | ⚠️ PENDIENTE |
| OQ-C20-3 | ¿Incluir mensajes del sistema con `remitente_id=NULL`? (D-C20-4) | Schema + service | ⚠️ PENDIENTE |
| OQ-C20-4 | ¿El soft-delete de un `HiloMensaje` soft-deletea también sus `MensajeInterno`? | Service cascade | A definir en implementación |
| OQ-C20-5 | ¿Pueden existir hilos con más de 2 participantes? (grupo) | Schema `hilo_participante` ya lo soporta | Depende de OQ-C20-2 |
