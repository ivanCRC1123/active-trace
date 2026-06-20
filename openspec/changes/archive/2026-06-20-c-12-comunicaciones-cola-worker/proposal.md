# C-12 comunicaciones-cola-worker — Proposal

## Objetivo
Implementar el módulo de comunicaciones salientes a alumnos con cola de despacho y worker asíncrono, cerrando el camino crítico del flujo central (importar → analizar → comunicar).

## Alcance confirmado
- Modelo `Comunicacion` con FSM (PENDIENTE → ENVIANDO → ENVIADO/ERROR/CANCELADO, RN-15)
- PII cifrada: `destinatario` con `EncryptedString` (AES-256), nunca en logs ni respuestas
- Preview obligatorio antes de encolar (F3.1, RN-16): renderiza plantillas con `{nombre}`, `{apellidos}`, `{materia}` sin persistir
- Crear lote de comunicaciones (F3.2): N registros con mismo `lote_id`
- Aprobación configurable: `requiere_aprobacion_comunicacion` por tenant + lógica RN-17 simplificada
- Aprobación de lote / cancelación individual (F3.3, RN-17)
- Worker asyncio polling: despacha ENVIANDO → ENVIADO/ERROR, injectable dispatcher
- `FakeSender` para dev/tests, `SmtpSender` (aiosmtplib) para producción
- Auditoría: `COMUNICACION_ENVIAR` al crear lote, `COMUNICACION_APROBAR` al aprobar
- Migración 010: tabla `comunicacion` + columna `requiere_aprobacion_comunicacion` en `tenant`

## RN-17 — lógica de aprobación (simplificación documentada)
- `scope='all'` → siempre requiere aprobación (fuera del contexto propio del docente)
- `scope='own'` + n > `COMUNICACION_UMBRAL_MASIVO` (default 10) → requiere (salvaguarda de masividad)
- `scope='own'` + n ≤ umbral → no requiere (docente a sus propios alumnos)
- Tenant con `requiere_aprobacion_comunicacion=FALSE` → nunca requiere
- Chequeo completo de "contexto propio" (por asignaciones del usuario) diferido a C-22

## Decisiones cerradas
- Q1: `entrada_padron_id` en `Comunicacion` (nullable FK SET NULL) — SÍ
- Q2: `aprobado_por` + `aprobado_at` en modelo + audit `COMUNICACION_APROBAR` — SÍ
- Q3: Worker poll interval 5s (configurable vía `WORKER_POLL_INTERVAL_SECS`)
- Q4: `requiere_aprobacion` default `True` (más seguro)
- Worker: asyncio polling in-process sin broker externo (ADR-003 pendiente)
- `fecha: 2026-06-20`
