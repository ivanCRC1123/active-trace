"""Parser for LMS activity completion report files (xlsx / csv) — C-11.

Detects which activities each student has completed ("finalizado") according
to the LMS completion report. Completion is determined by matching cell values
against a configurable set of "completed" tokens (D-C11-10).

Student-info columns are identified using the same alias list as
calificaciones_parser, keeping identification logic consistent across parsers.

Raises ValueError for: unsupported format, missing email column, or empty file.
"""

from __future__ import annotations

import csv
import io
from typing import TypedDict

from app.services.calificaciones_parser import _STUDENT_INFO_HEADERS  # reuse alias set

# ── Default "completed" vocabulary (D-C11-10) ─────────────────────────────────
# Overridden at runtime via settings.FINALIZACION_VALORES_COMPLETADO.
DEFAULT_COMPLETED_VALUES: list[str] = [
    "completado", "completed", "sí", "si", "yes", "true", "1",
    "finalizado", "finished", "done",
]


class FinalizacionRow(TypedDict):
    email: str
    actividades: dict[str, bool]  # actividad → finalizado


class ParsedFinalizacionFile(TypedDict):
    filas: list[FinalizacionRow]
    actividades_detectadas: list[str]
    warnings: list[str]


# ── Public API ─────────────────────────────────────────────────────────────────


def parse_finalizacion_file(
    content: bytes,
    filename: str,
    valores_completado: list[str] | None = None,
) -> ParsedFinalizacionFile:
    """Parse an LMS completion report file.

    Args:
        content: raw file bytes.
        filename: used to detect format (xlsx/csv).
        valores_completado: override for the "completed" vocabulary.
                            Defaults to DEFAULT_COMPLETED_VALUES.

    Raises:
        ValueError: unsupported format, no email column, or empty file.
    """
    completed_set = frozenset(
        v.lower() for v in (valores_completado or DEFAULT_COMPLETED_VALUES)
    )
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return _parse_xlsx(content, completed_set)
    if ext == "csv":
        return _parse_csv(content, completed_set)
    raise ValueError(f"Formato no soportado: {ext!r}. Usá .xlsx o .csv.")


# ── Internal ──────────────────────────────────────────────────────────────────


def _is_completed(raw: str, completed_set: frozenset[str]) -> bool:
    return raw.strip().lower() in completed_set


def _classify_headers(
    headers: list[str],
) -> tuple[str | None, list[str], list[str]]:
    """Returns (email_col, activity_cols, warnings)."""
    email_col: str | None = None
    activity_cols: list[str] = []
    warnings: list[str] = []

    for h in headers:
        normalized = h.strip().lower()
        if normalized in {"email", "correo", "mail", "e-mail", "correo electrónico", "correo electronico"}:
            email_col = h
            continue
        if normalized in _STUDENT_INFO_HEADERS:
            continue
        activity_cols.append(h.strip())

    if email_col is None:
        raise ValueError(
            "El archivo no contiene columna de email reconocida. "
            "Se esperaba: 'email', 'correo' o similar."
        )
    if not activity_cols:
        warnings.append("No se detectaron columnas de actividades en el archivo.")

    return email_col, activity_cols, warnings


def _build_rows(
    raw_rows: list[dict[str, str]],
    email_col: str,
    activity_cols: list[str],
    completed_set: frozenset[str],
) -> tuple[list[FinalizacionRow], list[str]]:
    rows: list[FinalizacionRow] = []
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

        actividades: dict[str, bool] = {
            col: _is_completed(raw.get(col) or "", completed_set)
            for col in activity_cols
        }
        rows.append(FinalizacionRow(email=email, actividades=actividades))

    return rows, warnings


def _parse_xlsx(content: bytes, completed_set: frozenset[str]) -> ParsedFinalizacionFile:
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
    email_col, activity_cols, warnings = _classify_headers(headers)

    raw_rows: list[dict[str, str]] = []
    for row in rows_iter:
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        raw_rows.append(
            {headers[i]: str(cell).strip() if cell is not None else "" for i, cell in enumerate(row)}
        )
    wb.close()

    filas, row_warnings = _build_rows(raw_rows, email_col, activity_cols, completed_set)
    return ParsedFinalizacionFile(
        filas=filas,
        actividades_detectadas=activity_cols,
        warnings=warnings + row_warnings,
    )


def _parse_csv(content: bytes, completed_set: frozenset[str]) -> ParsedFinalizacionFile:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("El archivo CSV está vacío o sin encabezados.")

    headers = list(reader.fieldnames)
    email_col, activity_cols, warnings = _classify_headers(headers)
    raw_rows = [dict(row) for row in reader]

    filas, row_warnings = _build_rows(raw_rows, email_col, activity_cols, completed_set)
    return ParsedFinalizacionFile(
        filas=filas,
        actividades_detectadas=activity_cols,
        warnings=warnings + row_warnings,
    )
