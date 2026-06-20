# Spec: exportar (F4.7)

## Objetivo

`GET /api/v1/equipos/exportar` genera y devuelve un archivo CSV descargable con el detalle
de todas las asignaciones del equipo, con los mismos filtros opcionales que `GET /equipos`.

## Guard

`require_permission("equipos:asignar")` — COORDINADOR/ADMIN.

## Query params

Mismos filtros que `GET /equipos` (todos opcionales):

| Param | Tipo | Descripción |
|-------|------|-------------|
| `materia_id` | UUID (opt) | FK → Materia |
| `carrera_id` | UUID (opt) | FK → Carrera |
| `cohorte_id` | UUID (opt) | FK → Cohorte |
| `usuario_id` | UUID (opt) | FK → Usuario |
| `rol` | str (opt) | Nombre del rol |
| `estado_vigencia` | `"Vigente"` \| `"Vencida"` (opt) | Filtrar por vigencia |

## Response

```
HTTP 200
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="equipo.csv"
```

**Columnas CSV (fijas, en este orden)**:
```
apellidos,nombre,rol,materia,carrera,cohorte,comisiones,desde,hasta,estado_vigencia
```

**Ejemplo de fila**:
```
García,María,PROFESOR,Programación I,TUPAD,MAR-2026,"['MAT_A']",2026-03-01,2026-07-31,Vigente
```

`comisiones` se serializa como `str(list)` de Python (formato compacto).
Si la lista está vacía → `[]`.

**Lista vacía de resultados** → CSV con solo la línea de encabezado. HTTP 200.

## Implementación

```python
import csv
import io
from fastapi.responses import StreamingResponse

async def exportar_csv(tenant_id: UUID, filtros: EquipoFiltros) → StreamingResponse:
    rows = await repo.list_equipo_con_nombres(tenant_id, filtros)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "apellidos", "nombre", "rol", "materia", "carrera",
        "cohorte", "comisiones", "desde", "hasta", "estado_vigencia"
    ])
    for r in rows:
        writer.writerow([
            r.usuario_apellidos,
            r.usuario_nombre,
            r.rol_nombre,
            r.materia_nombre or "",
            r.carrera_nombre or "",
            r.cohorte_nombre or "",
            str(r.comisiones),
            r.desde.isoformat(),
            r.hasta.isoformat() if r.hasta else "",
            compute_estado_vigencia(r.desde, r.hasta),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=\"equipo.csv\""},
    )
```

El router devuelve directamente el `StreamingResponse` del service.

## Criterios de aceptación

- [ ] Content-Type es `text/csv; charset=utf-8`.
- [ ] Content-Disposition tiene `attachment; filename="equipo.csv"`.
- [ ] Primera línea del CSV es el encabezado con los 10 campos.
- [ ] Cada fila tiene valores legibles (nombres, no UUIDs).
- [ ] Filtros aplicados — mismo comportamiento que `GET /equipos`.
- [ ] Sin resultados → solo encabezado, HTTP 200.
- [ ] Aislamiento de tenant.

## Tests

- `test_exportar_csv_contiene_encabezado`: respuesta tiene la línea de encabezado correcta.
- `test_exportar_csv_con_datos`: 3 asignaciones → CSV con 4 líneas (encabezado + 3).
- `test_exportar_csv_filtro_cohorte`: filtra correctamente por cohorte_id.
- `test_exportar_csv_vacio`: sin asignaciones → solo encabezado, 200.
- `test_exportar_csv_content_type`: `Content-Type: text/csv`.
- `test_exportar_sin_permiso_403`: sin `equipos:asignar` → 403.
