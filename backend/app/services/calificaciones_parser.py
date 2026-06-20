"""Parser for LMS grade export files (xlsx / csv) — C-10.

Detects:
  - Numeric columns: header ends with "(Real)"  (RN-01)
  - Textual columns: header doesn't end with "(Real)" and is not a
    known student-info column (RN-02)

Student-info columns (not grade data):
  nombre, apellidos, email/correo, id/identificador, dni, legajo,
  num_id, and common LMS metadata columns.

Returns a typed ParsedGradeFile with activity metadata and per-student rows.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import TypedDict

# ── Constants ──────────────────────────────────────────────────────────────────

_STUDENT_INFO_HEADERS: frozenset[str] = frozenset({
    "nombre", "apellidos", "apellido", "email", "correo", "mail", "e-mail",
    "first name", "first_name", "firstname", "last name", "last_name", "lastname",
    "surname", "full name", "fullname", "id", "identificador", "dni", "legajo",
    "num_id", "número de identificación", "numero de identificacion",
    "institution", "institución", "department", "departamento",
    "last download from this course",
})


class ActivityInfo(TypedDict):
    nombre: str
    tipo: str  # "numerica" | "textual"


class GradeRow(TypedDict):
    email: str
    grades: dict[str, str]  # actividad → raw string value from file


class ParsedGradeFile(TypedDict):
    actividades: list[ActivityInfo]
    filas: list[GradeRow]
    warnings: list[str]


# ── Public API ─────────────────────────────────────────────────────────────────


def parse_grade_file(content: bytes, filename: str) -> ParsedGradeFile:
    """Parse an LMS grade export file.

    Raises:
        ValueError: unrecognized format, missing email column, or empty file.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return _parse_xlsx(content)
    if ext == "csv":
        return _parse_csv(content)
    raise ValueError(f"Formato no soportado: {ext!r}. Usá .xlsx o .csv.")


def parse_nota_numerica(raw: str) -> Decimal | None:
    """Try to parse a raw string as a Decimal. Return None on failure."""
    cleaned = raw.strip().replace(",", ".")
    if not cleaned or cleaned == "-":
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


# ── Internal ──────────────────────────────────────────────────────────────────


def _classify_headers(headers: list[str]) -> tuple[str | None, list[ActivityInfo], list[str]]:
    """Classify headers into email column, activities, and warnings.

    Returns:
        (email_col, actividades, warnings)
    """
    email_col: str | None = None
    actividades: list[ActivityInfo] = []
    warnings: list[str] = []

    for h in headers:
        normalized = h.strip().lower()
        if normalized in {"email", "correo", "mail", "e-mail", "correo electrónico", "correo electronico"}:
            email_col = h
            continue
        if normalized in _STUDENT_INFO_HEADERS:
            continue
        # Grade column detection
        if h.strip().endswith("(Real)"):
            actividades.append(ActivityInfo(nombre=h.strip(), tipo="numerica"))
        else:
            actividades.append(ActivityInfo(nombre=h.strip(), tipo="textual"))

    if email_col is None:
        raise ValueError(
            "El archivo no contiene columna de email reconocida. "
            "Se esperaba: 'email', 'correo' o similar."
        )
    if not actividades:
        warnings.append("No se detectaron columnas de actividades en el archivo.")

    return email_col, actividades, warnings


def _build_rows(
    raw_rows: list[dict[str, str]],
    email_col: str,
    actividades: list[ActivityInfo],
) -> tuple[list[GradeRow], list[str]]:
    rows: list[GradeRow] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for idx, raw in enumerate(raw_rows, start=2):
        email = (raw.get(email_col) or "").strip().lower()
        if not email:
            warnings.append(f"Fila {idx}: sin email — descartada.")
            continue
        if email in seen:
            warnings.append(f"Fila {idx}: email duplicado ({email}) — se conserva la primera ocurrencia.")
            continue
        seen.add(email)

        grades: dict[str, str] = {}
        for act in actividades:
            grades[act["nombre"]] = (raw.get(act["nombre"]) or "").strip()

        rows.append(GradeRow(email=email, grades=grades))

    return rows, warnings


def _parse_xlsx(content: bytes) -> ParsedGradeFile:
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise ValueError("El archivo xlsx no tiene hojas activas.")

    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise ValueError("El archivo xlsx está vacío.")

    headers = [str(h).strip() if h is not None else "" for h in header_row]
    email_col, actividades, warnings = _classify_headers(headers)

    raw_rows: list[dict[str, str]] = []
    for row in rows_iter:
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        raw_rows.append(
            {headers[i]: str(cell).strip() if cell is not None else "" for i, cell in enumerate(row)}
        )
    wb.close()

    filas, row_warnings = _build_rows(raw_rows, email_col, actividades)
    return ParsedGradeFile(actividades=actividades, filas=filas, warnings=warnings + row_warnings)


def _parse_csv(content: bytes) -> ParsedGradeFile:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("El archivo CSV está vacío o sin encabezados.")

    headers = list(reader.fieldnames)
    email_col, actividades, warnings = _classify_headers(headers)
    raw_rows = [dict(row) for row in reader]

    filas, row_warnings = _build_rows(raw_rows, email_col, actividades)
    return ParsedGradeFile(actividades=actividades, filas=filas, warnings=warnings + row_warnings)
