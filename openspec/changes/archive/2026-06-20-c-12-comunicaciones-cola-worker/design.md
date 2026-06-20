# C-12 comunicaciones-cola-worker — Design

## Arquitectura

```
Router /api/v1/comunicaciones
  └─ ComunicacionService
       ├─ ComunicacionRepository (scoped por tenant_id)
       │    └─ Comunicacion (ORM, EncryptedString destinatario)
       ├─ AuditService (COMUNICACION_ENVIAR, COMUNICACION_APROBAR)
       └─ _necesita_aprobacion() → RN-17 simplificada

Worker (asyncio polling, cross-tenant)
  └─ ComunicacionRepository.list_enviando_all_tenants()
  └─ AbstractEmailDispatcher.send()
       ├─ FakeSender (dev/tests)
       └─ SmtpSender (producción, aiosmtplib)
```

## Migración 010

### tenant (ALTER TABLE)
```sql
ADD COLUMN requiere_aprobacion_comunicacion BOOLEAN NOT NULL DEFAULT TRUE
```

### comunicacion (CREATE TABLE)
- `id UUID PK`, `tenant_id UUID FK CASCADE`, `enviado_por UUID FK RESTRICT`
- `materia_id UUID FK RESTRICT`, `entrada_padron_id UUID FK SET NULL`
- `destinatario TEXT NOT NULL` (cifrado AES-256)
- `asunto VARCHAR(500)`, `cuerpo TEXT`
- `estado VARCHAR(20) DEFAULT 'PENDIENTE'` (CHECK constraint)
- `lote_id UUID NOT NULL`
- `aprobado_por UUID FK SET NULL`, `aprobado_at TIMESTAMPTZ`, `enviado_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ DEFAULT now()`, `updated_at TIMESTAMPTZ DEFAULT now()`, `deleted_at TIMESTAMPTZ`
- Trigger `set_comunicacion_updated_at`
- Índices: `idx_comunicacion_estado`, `idx_comunicacion_enviado_por`, `idx_comunicacion_lote`, `idx_comunicacion_enviando_worker`

## FSM (RN-15)
```
PENDIENTE → ENVIANDO → ENVIADO
PENDIENTE → CANCELADO
ENVIANDO  → ERROR
```
Otras transiciones levantan `ValueError("transicion_invalida: ...")`.

## Invariante PII
- `destinatario` cifrado AES-256 via `EncryptedString` (ORM descifra en lectura, cifra en escritura)
- Nunca en logs (ni en worker ni en FakeSender)
- Nunca en responses API (schemas no incluyen el campo)
- `FakeSender.sent` almacena `{subject, body}` sin `to`

## Config nueva
```
EMAIL_BACKEND=fake|smtp
SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_USE_TLS, SMTP_FROM_EMAIL
WORKER_POLL_INTERVAL_SECS=5
COMUNICACION_UMBRAL_MASIVO=10
```

## Endpoints
| Método | Path | Permiso | Descripción |
|--------|------|---------|-------------|
| POST | /api/v1/comunicaciones/preview | comunicacion:enviar | Preview sin persistir (RN-16) |
| POST | /api/v1/comunicaciones/lotes | comunicacion:enviar | Crear lote |
| GET | /api/v1/comunicaciones/lotes/{lote_id} | comunicacion:enviar | Detalle lote |
| POST | /api/v1/comunicaciones/lotes/{lote_id}/aprobar | comunicacion:aprobar | Aprobar lote |
| POST | /api/v1/comunicaciones/lotes/{lote_id}/cancelar | comunicacion:aprobar | Cancelar lote |
| POST | /api/v1/comunicaciones/{com_id}/cancelar | comunicacion:aprobar | Cancelar individual |
| GET | /api/v1/comunicaciones | comunicacion:enviar | Listado con filtros |
