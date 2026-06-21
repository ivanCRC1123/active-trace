# C-18 — `liquidaciones-y-honorarios` — Design

## Context

C-07 estableció `Usuario` (con `facturador`, `banco`, `cbu`, `alias_cbu` cifrados), `Asignacion` (con `rol_id → Rol`, `materia_id`, `cohorte_id`, `comisiones: JSON`, `desde/hasta`) y `Rol` (con `nombre: VARCHAR`).

C-18 construye el módulo económico sobre esa base: grilla salarial configurable, cálculo de liquidación mensual y gestión de facturas. Todas las operaciones son FINANZAS-only.

Fuentes: KB §E17–E20, KB §RN-21/22/26/27/31/32/33/34/35/36/37/38/39/40, KB §F10.1–F10.6, KB §FL-08.

---

## Goals / Non-Goals

**Goals**
- Modelos `MateriaGrupo`, `SalarioBase`, `SalarioPlus`, `Liquidacion`, `Factura` con soft-delete y tenant-scope.
- Resolución explícita del gap PA-22 mediante tabla `materia_grupo` (OD-1).
- Fórmula de cálculo `Base + Σ(Plus × N_comisiones)` documentada e implementada (OD-3).
- Cierre inmutable de liquidaciones por (cohorte, período) (RN-22/37).
- KPIs `total_sin_factura` / `total_con_factura` (RN-38).
- Gestión de facturas con referencia opaca de archivo (patrón C-17) (RN-39/40).
- Todos los tipos monetarios como `Numeric(12,2)` — nunca Float (OD-2).
- Auditoría de operaciones críticas: `GRILLA_SALARIAL_OPERAR`, `LIQUIDACION_CERRAR`, `FACTURA_ABONAR`.
- ~40 tests TDD, cobertura ≥90% de reglas de negocio.

**Non-Goals**
- Upload físico de archivos de factura — `referencia_archivo` es un string opaco (igual que en C-17).
- Integración con sistemas de pago externos — el "abonar" es solo un cambio de estado.
- Cálculo de retenciones impositivas (IVA, ganancias, etc.) — el plus/base se almacena como monto bruto.
- Liquidación de docentes con rol ALUMNO o ADMIN.

---

## Open Decisions (SURFACING EXPLÍCITO — NO resolver en silencio)

### OD-1 — GAP MODELO: materia → categoría de plus (PA-22, ALTA)

**El problema:** `SalarioPlus.grupo` es una clave de categoría (ej. `"PROG"`, `"BD"`) que agrupa materias. Sin embargo, `Materia` (E3) tiene solo `codigo`, `nombre` y `estado` — no tiene ningún campo `categoria` ni `grupo`. El cálculo RN-34 necesita saber a qué grupo de plus pertenece cada materia en la que trabaja el docente.

**Opciones:**

**Opción A — Campo `categoria` nullable en `materia`**
```sql
ALTER TABLE materia ADD COLUMN categoria VARCHAR(50) NULL;
```
- Pro: simple, consultas directas, sin JOIN adicional.
- Contra: acopla el catálogo académico al dominio de liquidaciones; una materia solo puede pertenecer a un grupo (no extensible a mapeos múltiples); ADMIN puede modificar el campo sin que FINANZAS lo sepa; el campo queda vacío si el tenant no usa plus.

**Opción B — Tabla de mapeo `materia_grupo` (RECOMENDADA)**
```sql
CREATE TABLE materia_grupo (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenant(id),
  materia_id UUID NOT NULL REFERENCES materia(id),
  grupo VARCHAR(50) NOT NULL,    -- clave de la categoría de plus
  deleted_at TIMESTAMPTZ NULL,
  ...
);
UNIQUE (tenant_id, materia_id, grupo)  -- una materia puede tener múltiples grupos (raro pero extensible)
```
- Pro: separación total entre catálogo académico y configuración de liquidaciones; configurable por FINANZAS independientemente del ADMIN; extensible (materia en múltiples grupos si el negocio lo requiere); soft-delete consistente con el resto del modelo.
- Contra: JOIN adicional en el cálculo; requiere que FINANZAS mantenga el mapeo actualizado cuando se agregan materias nuevas.

**Decisión propuesta:** Opción B (`materia_grupo`). La separación de dominios justifica la complejidad adicional; el JOIN es barato con el índice `(tenant_id, materia_id)`.

⚠️ **PA-22 sigue abierta:** la lista concreta de grupos y qué materias pertenecen a cada uno debe resolverse con el responsable de producto ANTES de la primera carga de datos. El sistema provee la tabla; el contenido es configuración del tenant.

---

### OD-2 — Tipos monetarios: SIEMPRE `Numeric(12, 2)`

Todos los importes económicos (`monto`, `monto_base`, `monto_plus`, `total`, `tamano_kb`) se modelan como:

```python
# SQLAlchemy
from sqlalchemy import Numeric
monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

# Python
from decimal import Decimal
```

**Nunca** `Float` ni `float`. Un error de representación en punto flotante en montos económicos es un defecto crítico de producción.

`tamano_kb` de `Factura` usa `Numeric(12, 3)` (tres decimales para precisión de KB).

---

### OD-3 — Fórmula de cálculo RN-34

```
Total(docente, rol, cohorte, periodo) =
    Base(rol, periodo)
    + Σ_grupo [ Plus(grupo, rol, periodo) × N_comisiones(docente, grupo, cohorte, periodo) ]
```

**Donde:**

- `Base(rol, periodo)`: primer registro `SalarioBase` donde `rol = rol_nombre AND desde <= fecha_inicio_periodo AND (hasta IS NULL OR hasta >= fecha_fin_periodo) AND deleted_at IS NULL`. Solo puede haber una vigente por rol en un instante (constraint de negocio, no de DB — se valida en el service al crear/editar).

- `fecha_inicio_periodo`: primer día del mes `periodo` (ej. `"2026-06"` → `date(2026, 6, 1)`).
- `fecha_fin_periodo`: último día del mes `periodo` (ej. `date(2026, 6, 30)`).

- `Plus(grupo, rol, periodo)`: primer registro `SalarioPlus` donde `grupo = grupo AND rol = rol_nombre AND desde <= fecha_inicio_periodo AND (hasta IS NULL OR hasta >= fecha_fin_periodo) AND deleted_at IS NULL`.

- `N_comisiones(docente, grupo, cohorte, periodo)`:
  ```
  Σ_asignacion [ len(asignacion.comisiones) ]
  ```
  donde cada `asignacion` cumple:
  - `asignacion.usuario_id = docente_id`
  - `asignacion.cohorte_id = cohorte_id`
  - `asignacion.rol_id → rol.nombre = rol_nombre`
  - `asignacion.materia_id` en el conjunto de materias del grupo (vía `materia_grupo.grupo = grupo`)
  - `asignacion.desde <= fecha_fin_periodo AND (asignacion.hasta IS NULL OR asignacion.hasta >= fecha_inicio_periodo)`
  - `asignacion.deleted_at IS NULL`

⚠️ **PA-23 sigue parcialmente abierta:** la interpretación de "N_comisiones = sum de len(comisiones) por asignación" asume que cada string en `Asignacion.comisiones` es una comisión independiente (ej. `["A", "B", "C"]` → N=3). Si el negocio define que una Asignacion con 3 comisiones cuenta como 1 (no 3), el cálculo cambia. La fórmula aquí documenta la lectura directa de RN-34: "N_comisiones es la cantidad de comisiones activas". Confirmar con producto antes de implementar el service de cálculo.

---

### OD-4 — Vigencia de SalarioBase: solo una vigente por rol en un instante (RN-31/32)

La KB dice "Solo puede haber una entrada vigente por rol en un instante dado." Esto es una regla de negocio, no un UNIQUE constraint de DB (porque los rangos con NULL son difíciles de indexar en Postgres sin rangos de exclusión).

**Implementación:** al crear o editar un `SalarioBase`, el service verifica:
```python
# Pseudo-código del service
existente = await repo.find_vigente_para_rol(rol=rol, periodo=desde_nuevo)
if existente and existente.id != id_editado:
    raise ValueError("Ya existe un SalarioBase vigente para ese rol en ese período")
```

`find_vigente_para_rol(rol, fecha)` busca `desde <= fecha AND (hasta IS NULL OR hasta >= fecha)`.

Igual aplica para `SalarioPlus` por `(grupo, rol)`.

---

### OD-5 — Base inexistente para un rol/período: exclusión con reporte (APROBADO)

Si no existe `SalarioBase` vigente para `(rol, periodo)` de un docente:
- El docente **NO se incluye** en la lista de liquidaciones calculadas.
- Se agrega a una lista `sin_base_vigente` en el response del endpoint `/calcular`.
- Nunca se crea un registro `Liquidacion` con `monto_base=0` por misconfiguration.

**Rationale:** Un 0 congelado en una liquidación inmutable es un bug contable silencioso. La exclusión con reporte explícito obliga a FINANZAS a completar la grilla antes de cerrar.

El response de `POST /calcular` tendrá:
```json
{
  "liquidaciones": [...],
  "sin_base_vigente": [{"usuario_id": "...", "rol": "PROFESOR"}],
  "sin_datos_bancarios": [{"usuario_id": "..."}]
}
```

---

### OD-5b — Inmutabilidad (RN-22/37): estado `Abierta | Cerrada`

Una vez que una `Liquidacion` pasa a `estado = Cerrada` (RN-22/37):
- El service rechaza cualquier intento de recalcular o modificar ese registro: levanta `ValueError("liquidacion_cerrada")` → router mapea a 422.
- El endpoint de cálculo bulk (POST `/api/v1/liquidaciones/calcular`) al encontrar un registro ya cerrado para (cohorte, usuario, rol, periodo) lo omite sin error.
- La API solo permite abonar facturas cuando la liquidación del período está cerrada (opcional, a confirmar).

No existe endpoint de "reabrir" — la inmutabilidad es absoluta.

---

### OD-6 — `facturador` usa campo EXISTENTE `Usuario.facturador` (RN-35/27)

`Usuario.facturador: bool` ya existe en el modelo `User` de C-07. En el cálculo de liquidación:

```python
if docente.facturador:
    liquidacion.excluido_por_factura = True
    liquidacion.total = Decimal("0.00")  # no se paga por este canal
```

La liquidación se crea de todas formas (para historial y KPI), pero con `excluido_por_factura=True` y `total=0`. El pago real se gestiona por el módulo de Facturas.

**No se inventa ningún campo nuevo en Usuario** — el campo `facturador` es suficiente per KB §E4.

---

### OD-7 — NEXO: se_suma pero muestra separado (RN-36)

```python
liquidacion.es_nexo = True  # cuando rol_nombre == "NEXO"
```

- `es_nexo=True` no excluye del total general — se suma a `total_sin_factura`.
- La API expone un campo de respuesta `es_nexo` para que el frontend pueda renderizar la sección NEXO separada.
- Los KPIs del endpoint de período incluyen:
  - `total_sin_factura`: suma de `total` donde `excluido_por_factura=False` (incluye NEXO).
  - `total_con_factura`: suma de montos de facturas Abonadas para el mismo período (referencial, no modifica la liquidación).

---

### OD-8 — Datos bancarios faltantes: flag, no error (RN-26)

Si `Usuario.banco`, `Usuario.cbu` o `Usuario.alias_cbu` (descifrados) están vacíos o nulos al calcular:

```python
liquidacion.datos_bancarios_incompletos = True
# La liquidación se crea con su total normal, pero no puede "procesarse"
```

**Comportamiento:** el registro se crea/actualiza con el monto calculado y el flag activado. La API devuelve el flag en la respuesta. No se lanza error, no se excluye el docente. FINANZAS ve el flag y puede gestionar el caso.

> `datos_bancarios_incompletos` es un campo booleano en `Liquidacion` (no en KB E19 — es una extensión técnica necesaria para implementar RN-26 sin romper).

---

### OD-9 — Factura: referencia opaca y `tamano_kb` (RN-39/40)

Igual que `ProgramaMateria.referencia_archivo` en C-17: el cliente sube el PDF al servicio de almacenamiento externo y pasa la referencia resultante (string opaco).

```python
referencia_archivo: Mapped[str] = mapped_column(Text, nullable=False)
tamano_kb: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
```

Estados `Pendiente | Abonada` — únicos dos, no hay intermedio. La transición es `Pendiente → Abonada` (solo en esa dirección). Al abonar se registra `abonada_at = now()` y se audita con `FACTURA_ABONAR`.

---

### OD-10 — Audit codes para C-18

Los tres códigos de auditoría para este change:

```python
# audit_codes.py — agregar:
GRILLA_SALARIAL_OPERAR = "GRILLA_SALARIAL_OPERAR"  # alta/edición de Base y Plus
FACTURA_ABONAR         = "FACTURA_ABONAR"           # marcar factura como abonada
# LIQUIDACION_CERRAR ya existe (sembrado en C-07+)
```

`GRILLA_SALARIAL_OPERAR` se registra en cualquier mutación de `SalarioBase`, `SalarioPlus` o `MateriaGrupo` (create, update, soft-delete). El campo `detalle` incluye `{"tipo": "SalarioBase|SalarioPlus|MateriaGrupo", "operacion": "create|update|delete", "id": "..."}`.

---

### OD-11 — Permisos: sin cambios en seed

Los tres permisos FINANZAS ya están sembrados en C-04 (`seed_permissions.py` líneas 117-123):
```python
"FINANZAS": {
    "comunicacion:confirmar_aviso": "all",
    "auditoria:ver": "all",
    "grilla_salarial:operar": "all",        # ← gatea router grilla-salarial
    "liquidaciones:calcular_cerrar": "all", # ← gatea router liquidaciones
    "facturas:gestionar": "all",            # ← gatea router facturas
},
```

ADMIN **no** tiene ninguno de los tres (confirmado — C-04 seed lines 86-113). Sin cambios.

Las menciones de `"liquidaciones:configurar-salarios"` y `"liquidaciones:cerrar"` en el KB de funcionalidades son nombres descriptivos no técnicos — se mapean a `grilla_salarial:operar` y `liquidaciones:calcular_cerrar` respectivamente.

### OD-RBAC-GAP — Vista de liquidaciones para ADMIN (inconsistencia abierta)

**Problema:** F10.1 / F10.3 / F10.6 describen que ADMIN puede *ver* liquidaciones y exportar reportes. Sin embargo, la matriz de permisos en KB §03 y el seed de C-04 **no definen un permiso `liquidaciones:ver`**. Inventar el permiso sin alinearlo con RBAC y seed introduciría una inconsistencia de seguridad.

**Decisión tomada:** El router `/liquidaciones` está protegido exclusivamente con `liquidaciones:calcular_cerrar` (FINANZAS-only). ADMIN no tiene acceso en esta implementación.

**Impacto:** Las funcionalidades de vista de ADMIN (F10.1/F10.3/F10.6) quedan fuera de C-18. Deben resolverse en un change posterior una vez que la matriz de permisos incluya `liquidaciones:ver`.

**Acción pendiente:** Agregar `liquidaciones:ver` a la matriz de permisos (KB §03) y al seed de C-04, asignarlo a ADMIN + FINANZAS, y proteger los endpoints de solo-lectura con ese permiso.

---

## Architecture

```
Routers (3)
  grilla_salarial.py  → guard: grilla_salarial:operar
  liquidaciones.py    → guard: liquidaciones:calcular_cerrar
  facturas.py         → guard: facturas:gestionar
        ↓
Services (2)
  LiquidacionService  → orquesta cálculo, cierre, KPIs
  FacturaService      → CRUD facturas, transición abonar
        ↓
Repositories (5)
  MateriaGrupoRepository
  SalarioBaseRepository
  SalarioPlusRepository
  LiquidacionRepository
  FacturaRepository
        ↓
Models (5 nuevos)
  MateriaGrupo, SalarioBase, SalarioPlus, Liquidacion, Factura
```

Reglas de Clean Architecture:
- Routers: solo HTTP/Pydantic → service call → response.
- Services: toda la lógica de negocio (cálculo, validaciones, inmutabilidad). Nunca SQL directo.
- Repositories: solo SQLAlchemy + filtros tenant. Queries via `select()`.
- Los repositories existentes (`UserRepository`, `AsignacionRepository`, `MateriaRepository`) se inyectan en `LiquidacionService` vía constructor para lookups necesarios al cálculo. No se modifican.

---

## Enums nuevos

```python
# backend/app/models/base.py — agregar:

class RolLiquidable(str, enum.Enum):
    PROFESOR    = "PROFESOR"
    TUTOR       = "TUTOR"
    NEXO        = "NEXO"
    COORDINADOR = "COORDINADOR"

class LiquidacionEstado(str, enum.Enum):
    Abierta = "Abierta"
    Cerrada = "Cerrada"

class FacturaEstado(str, enum.Enum):
    Pendiente = "Pendiente"
    Abonada   = "Abonada"
```

`RolLiquidable` solo incluye los cuatro roles con base salarial definida (KB RN-32). No incluye ALUMNO, ADMIN, FINANZAS.

---

## Esquema de modelos

### MateriaGrupo
```python
class MateriaGrupo(Base, BaseEntityMixin):
    __tablename__ = "materia_grupo"
    __table_args__ = (
        UniqueConstraint("tenant_id", "materia_id", "grupo",
                         name="uq_materia_grupo_tenant_materia_grupo"),
    )
    materia_id: Mapped[UUID] = mapped_column(FK("materia.id"), nullable=False, index=True)
    grupo: Mapped[str] = mapped_column(String(50), nullable=False)
```

### SalarioBase
```python
class SalarioBase(Base, BaseEntityMixin):
    __tablename__ = "salario_base"
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False), nullable=False
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
```

### SalarioPlus
```python
class SalarioPlus(Base, BaseEntityMixin):
    __tablename__ = "salario_plus"
    grupo: Mapped[str] = mapped_column(String(50), nullable=False)
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
```

### Liquidacion
```python
class Liquidacion(Base, BaseEntityMixin):
    __tablename__ = "liquidacion"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cohorte_id", "usuario_id", "rol", "periodo",
                         name="uq_liquidacion_docente_periodo"),
    )
    cohorte_id: Mapped[UUID] = mapped_column(FK("cohorte.id"), nullable=False, index=True)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)  # "AAAA-MM"
    usuario_id: Mapped[UUID] = mapped_column(FK("user.id"), nullable=False, index=True)
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False), nullable=False
    )
    comisiones: Mapped[list] = mapped_column(JSON, nullable=False, server_default="'[]'::json")
    monto_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monto_plus: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    es_nexo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excluido_por_factura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    datos_bancarios_incompletos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estado: Mapped[LiquidacionEstado] = mapped_column(
        sa.Enum(LiquidacionEstado, name="liquidacion_estado", create_type=False),
        nullable=False, default=LiquidacionEstado.Abierta
    )
```

### Factura
```python
class Factura(Base, BaseEntityMixin):
    __tablename__ = "factura"
    usuario_id: Mapped[UUID] = mapped_column(FK("user.id"), nullable=False, index=True)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)  # "AAAA-MM"
    detalle: Mapped[str] = mapped_column(Text, nullable=False)
    referencia_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    tamano_kb: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    estado: Mapped[FacturaEstado] = mapped_column(
        sa.Enum(FacturaEstado, name="factura_estado", create_type=False),
        nullable=False, default=FacturaEstado.Pendiente
    )
    cargada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    abonada_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

---

## Migration Plan

- **Revision:** `f6a7b8c9d0e1`
- **Down revision:** `d4e5f6a7b8c9` (013_aviso_acknowledgment)
- **Archivo:** `backend/alembic/versions/f6a7b8c9d0e1_014_liquidacion_honorarios.py`

```
upgrade():
  1. CREATE TYPE rol_liquidable       (checkfirst=True)
  2. CREATE TYPE liquidacion_estado   (checkfirst=True)
  3. CREATE TYPE factura_estado       (checkfirst=True)
  4. CREATE TABLE materia_grupo       (+ UniqueConstraint + índice materia_id)
  5. CREATE TABLE salario_base        (+ índice tenant/rol/desde)
  6. CREATE TABLE salario_plus        (+ índice tenant/grupo/rol/desde)
  7. CREATE TABLE liquidacion         (+ UniqueConstraint + índices cohorte/usuario/periodo)
  8. CREATE TABLE factura             (+ índice tenant/usuario/periodo/estado)
  9. Triggers updated_at para las 5 tablas (patrón existente)

downgrade():
  (triggers → tablas en orden inverso → tipos)
```

---

## Service: LiquidacionService — cálculo central

```python
async def calcular_liquidaciones_periodo(
    self,
    *,
    tenant_id: UUID,
    cohorte_id: UUID,
    periodo: str,     # "AAAA-MM"
    actor_id: UUID,
) -> list[Liquidacion]:
    """
    Para cada docente activo en la cohorte durante el período:
    1. Obtiene Asignaciones vigentes en el período con materia_id no nulo
    2. Deriva rol_nombre via JOIN Rol
    3. Solo procesa RolLiquidable (PROFESOR|TUTOR|NEXO|COORDINADOR)
    4. Obtiene SalarioBase vigente para (rol, periodo)
    5. Para cada grupo de materia_grupo encontrado en las Asignaciones:
       - Obtiene SalarioPlus vigente para (grupo, rol, periodo)
       - Cuenta N_comisiones = Σ len(asignacion.comisiones)
       - plus_parcial += monto_plus * N_comisiones
    6. total = monto_base + monto_plus
    7. Aplica flags: excluido_por_factura, es_nexo, datos_bancarios_incompletos
    8. Upsert Liquidacion si estado=Abierta (omite si Cerrada)
    9. Audita LIQUIDACION_CERRAR no; la auditoría del cálculo no está definida en KB —
       solo cerrar audita. El cálculo no genera audit entry.
    """
```

**Nota:** Si `SalarioBase` no existe para el rol+período, el docente se incluye con `monto_base=0` y se marca con un flag `sin_base_salarial` (a añadir en discusión) — alternativa: excluir. Esta edge case necesita confirmación con producto.

---

## Risks / Trade-offs

| Riesgo | Mitigación |
|--------|-----------|
| PA-22 (qué materias van en qué grupo) no está cerrada | `materia_grupo` existe pero vacía; el cálculo arroja 0 plus hasta que FINANZAS cargue los mapeos. Sistema funciona sin error. |
| PA-23 (¿N acumula o no?) interpretada como "SÍ acumula" | Documentado en OD-3. Si el negocio cambia la interpretación, solo cambia `N_comisiones` en `LiquidacionService.calcular_liquidaciones_periodo`. |
| Vigencia de SalarioBase validada en service (no en DB) | Riesgo de race condition en inserciones concurrentes. Mitigación: operaciones de grilla son atómicas y de bajo volumen (FINANZAS es un equipo pequeño). |
| `Liquidacion.comisiones` es JSON (lista de strings) | No es FK, no hay integridad referencial. Desnormalización intencional para el historial inmutable: cuando se cierra, el estado de las comisiones queda congelado. |
| El cálculo puede ser lento si hay muchas Asignaciones | Para MVP, la cohorte típica tiene <50 docentes. Si escala, añadir índice compuesto `(usuario_id, cohorte_id, desde, hasta)` en Asignacion (fuera de scope de C-18). |

---

## Open Questions

- **Base inexistente para un rol/período:** ¿incluir con `monto_base=0` y flag, o excluir del cálculo? (Confirmar con FINANZAS.)
- **Reabrir liquidación:** ¿existe algún flujo de corrección de errores que requiera reabrir? Por ahora: no. Crear nueva liquidación del mismo período no es posible si la anterior está cerrada.
- **Factura sin liquidación asociada:** ¿una Factura puede cargarse para un período sin liquidación Cerrada correspondiente? Por ahora: sí — las facturas son independientes de la liquidación.
