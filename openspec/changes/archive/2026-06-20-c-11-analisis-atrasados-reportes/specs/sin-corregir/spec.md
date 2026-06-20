# Spec: Sin Corregir (F2.6, RN-07, RN-08)

## Propósito

Identifica trabajos prácticos entregados por alumnos (según el reporte de finalización del LMS)
que no tienen calificación registrada. Solo aplica a actividades de escala textual (RN-08).
Permite al docente gestionar la cola de correcciones pendientes.

---

## Endpoint: Sin corregir

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/sin-corregir`

**Permiso**: `atrasados:ver` (scoped)

### Precondición

Requiere que el usuario (o el COORDINADOR para scope=all) haya importado previamente el
reporte de finalización. Si no hay `FinalizacionActividad` para el scope, se retorna 200 con
lista vacía y aviso (D-C11-7).

### Query en `AnalisisRepository.sin_corregir()` / `FinalizacionRepository.list_sin_corregir()`

Ver D-C11-7 para la query SQL completa. Resumen:

1. Obtener actividades textuales conocidas para el scope (materia_id, asignacion_id):
   `SELECT DISTINCT actividad FROM calificacion WHERE nota_textual IS NOT NULL`.

2. De `finalizacion_actividad` donde `finalizado=TRUE` y `actividad IN (textuales)`:
   excluir las que ya tienen calificacion en `calificacion`.

3. JOIN con `entrada_padron` para obtener nombre/apellidos.

**Nota**: si no se importó el reporte de finalización, la tabla `finalizacion_actividad`
estará vacía para ese scope → la query retorna 0 filas. El servicio detecta este caso
comparando `count(finalizacion_actividad)` para el scope y emite el aviso.

### Response (`SinCorregirResponse`)

```python
class EntregaSinCorregir(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    actividad: str

class SinCorregirResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[EntregaSinCorregir]
    total: int
    aviso: str | None   # "no_hay_finalizacion_importada" si el usuario no subió el archivo aún
```

---

## Endpoint: Export CSV

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/sin-corregir/exportar`

**Permiso**: `atrasados:ver` (scoped)

**Response**: `Content-Type: text/csv; charset=utf-8`
`Content-Disposition: attachment; filename="sin_corregir_{materia_id}_{cohorte_id}.csv"`

**Formato CSV**:

```
apellidos,nombre,comision,actividad
García Ana,Ana,A,Trabajo Práctico 1
López Juan,Juan,B,Trabajo Práctico 2
```

Sin filas si no hay entregas sin corregir (solo encabezado).

---

## Restricciones de negocio

- **RN-07**: solo alumnos que "finalizaron" la actividad en el LMS pero NO tienen calificacion.
- **RN-08**: solo para actividades de escala textual. Las actividades numéricas no se incluyen
  porque ausencia de nota numérica = no entregado (no pendiente de corrección).
- **Scope**: PROFESOR/TUTOR ven solo sus propias asignaciones; COORDINADOR/ADMIN ven todo el tenant.

---

## Tests requeridos (en `test_analisis.py`)

| Test | Verifica |
|------|---------|
| `test_sin_corregir_detecta_textual_finalizado_sin_nota` | Actividad textual, finalizado=True, sin calificacion → aparece |
| `test_sin_corregir_excluye_con_nota` | Actividad textual, finalizado=True, CON calificacion → no aparece |
| `test_sin_corregir_excluye_numericas` | Actividad numérica, finalizado=True, sin calificacion → no aparece (RN-08) |
| `test_sin_corregir_excluye_no_finalizado` | finalizado=False → no aparece (RN-07) |
| `test_sin_corregir_sin_finalizacion_importada` | Sin filas en finalizacion_actividad → lista vacía + aviso |
| `test_sin_corregir_export_csv` | CSV con encabezados correctos y datos válidos |
| `test_sin_corregir_scope_own` | PROFESOR solo ve sus propias entregas |
