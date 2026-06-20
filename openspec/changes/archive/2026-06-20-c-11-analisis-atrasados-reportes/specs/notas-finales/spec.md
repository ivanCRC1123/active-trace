# Spec: Notas Finales (F2.5)

## Propósito

Agrega las actividades importadas para cada alumno y calcula una "nota final" como
porcentaje de actividades aprobadas. Permite al docente confeccionar actas o informes de
cierre sin procesar los datos manualmente.

---

## Endpoint: Notas finales

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/notas-finales`

**Permiso**: `atrasados:ver` (scoped, mismo mecanismo que atrasados)

### Query en `AnalisisRepository.notas_finales()`

```sql
-- Alumnos del padrón activo con sus conteos de aprobadas
SELECT
    p.id                                                          AS entrada_padron_id,
    p.nombre,
    p.apellidos,
    p.comision,
    COUNT(c.id) FILTER (WHERE c.aprobado = TRUE)                 AS aprobadas,
    COUNT(c.id)                                                   AS total_calificaciones,
    ROUND(
        COUNT(c.id) FILTER (WHERE c.aprobado = TRUE)::NUMERIC
        / NULLIF(COUNT(c.id), 0) * 100,
        2
    )                                                             AS nota_final_pct
FROM padron_activo p  -- mismo CTE que en atrasados
LEFT JOIN calificacion c ON c.entrada_padron_id = p.id
    AND c.materia_id = :materia_id
    AND c.asignacion_id = :asignacion_id
    AND c.deleted_at IS NULL
GROUP BY p.id, p.nombre, p.apellidos, p.comision
ORDER BY p.apellidos, p.nombre
```

`padron_activo` es el mismo CTE usado en atrasados (JOIN version_padron activa + entrada_padron).

**`nota_final_pct` es NULL** para alumnos sin ninguna calificación importada (denominator = 0 via `NULLIF`).

### Response (`NotasFinalesResponse`)

```python
class NotaFinalAlumno(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    aprobadas: int
    total_calificaciones: int
    nota_final_pct: float | None   # NULL si no hay calificaciones importadas para el alumno

class NotasFinalesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[NotaFinalAlumno]
    total_alumnos: int
```

---

## Endpoint: Export CSV

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/notas-finales/exportar`

**Permiso**: `atrasados:ver` (scoped)

**Response**: `Content-Type: text/csv; charset=utf-8`
`Content-Disposition: attachment; filename="notas_finales_{materia_id}_{cohorte_id}.csv"`

**Formato CSV**:

```
apellidos,nombre,comision,aprobadas,total_actividades,nota_final_pct
García Ana,Ana,A,8,10,80.00
López Juan,Juan,B,5,10,50.00
Martínez Pedro,Pedro,A,,0,
```

La fila sin calificaciones tiene `nota_final_pct` vacío (no "None", no "null").

**Implementación** en `AnalisisService.exportar_notas_finales()`:
```python
import csv, io
buf = io.StringIO()
writer = csv.writer(buf)
writer.writerow(["apellidos", "nombre", "comision", "aprobadas", "total_actividades", "nota_final_pct"])
for item in notas:
    nota_str = f"{item.nota_final_pct:.2f}" if item.nota_final_pct is not None else ""
    writer.writerow([item.apellidos, item.nombre, item.comision or "", item.aprobadas, item.total_calificaciones, nota_str])
return buf.getvalue()
```

El router retorna `Response(content=csv_str, media_type="text/csv", headers={...})`.

---

## Tests requeridos (en `test_analisis.py`)

| Test | Verifica |
|------|---------|
| `test_notas_finales_calculo_correcto` | Alumno con 8/10 aprobadas → nota_final_pct=80.00 |
| `test_notas_finales_sin_calificaciones` | Alumno en padrón sin calificaciones → nota_final_pct=None |
| `test_notas_finales_todos_aprobados` | 10/10 → 100.00 |
| `test_notas_finales_ninguno_aprobado` | 0/5 → 0.00 |
| `test_notas_finales_export_csv` | Response es CSV, encabezados correctos, sin None literal |
| `test_notas_finales_export_csv_sin_datos` | CSV con solo encabezados si no hay calificaciones |
