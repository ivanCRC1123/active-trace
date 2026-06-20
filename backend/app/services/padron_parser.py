"""Parser for padrón import files (xlsx / csv).

Returns a list of normalized dicts and a list of warning strings.
Discards rows missing nombre, apellidos, or email.
Deduplicates by email (first occurrence wins).
"""

from __future__ import annotations

import csv
import io
from typing import TypedDict


class PadronRow(TypedDict):
    nombre: str
    apellidos: str
    email: str
    comision: str | None
    regional: str | None


# Alias mapping: canonical_name → [accepted column headers (case-insensitive, stripped)]
_ALIASES: dict[str, list[str]] = {
    "nombre":    ["nombre", "first_name", "firstname", "name"],
    "apellidos": ["apellidos", "apellido", "last_name", "lastname", "surname"],
    "email":     ["email", "correo", "mail", "e-mail", "e mail"],
    "comision":  ["comision", "comisión", "grupo", "group", "section"],
    "regional":  ["regional", "sede", "region"],
}

_REQUIRED = {"nombre", "apellidos", "email"}


def parse_padron_file(content: bytes, filename: str) -> tuple[list[PadronRow], list[str]]:
    """Parse xlsx or csv bytes into normalized PadronRow dicts.

    Returns:
        (rows, warnings) — warnings describe discarded or incomplete rows.
    Raises:
        ValueError: if the file format is unrecognized or has no email column.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return _parse_xlsx(content)
    if ext == "csv":
        return _parse_csv(content)
    raise ValueError(f"Formato de archivo no soportado: {ext!r}. Usá .xlsx o .csv.")


def _normalize_columns(headers: list[str]) -> dict[str, str]:
    """Map raw header names to canonical field names.

    Returns a dict: {raw_header: canonical_name}.
    Raises ValueError if no email column is found.
    """
    mapping: dict[str, str] = {}
    for raw in headers:
        normalized = raw.strip().lower()
        for canonical, aliases in _ALIASES.items():
            if normalized in aliases and canonical not in mapping.values():
                mapping[raw] = canonical
                break

    if "email" not in mapping.values():
        raise ValueError(
            "El archivo no contiene ninguna columna de email reconocida. "
            f"Se esperaba alguna de: {_ALIASES['email']}."
        )
    return mapping


def _build_rows(
    raw_rows: list[dict[str, str]],
    col_map: dict[str, str],
) -> tuple[list[PadronRow], list[str]]:
    """Convert raw header→value dicts into PadronRow dicts with dedup."""
    rows: list[PadronRow] = []
    warnings: list[str] = []
    seen_emails: set[str] = set()

    for idx, raw in enumerate(raw_rows, start=2):  # row 2 = first data row
        # Translate raw keys to canonical names
        canonical: dict[str, str] = {}
        for raw_key, canon in col_map.items():
            canonical[canon] = (raw.get(raw_key) or "").strip()

        nombre = canonical.get("nombre", "")
        apellidos = canonical.get("apellidos", "")
        email = canonical.get("email", "").lower()

        # Discard rows missing required fields
        missing = [f for f in _REQUIRED if not canonical.get(f)]
        if missing:
            warnings.append(
                f"Fila {idx}: descartada — campos requeridos vacíos: {', '.join(missing)}"
            )
            continue

        # Deduplicate by email
        if email in seen_emails:
            warnings.append(
                f"Fila {idx}: email duplicado ({email}) — se conserva la primera ocurrencia"
            )
            continue
        seen_emails.add(email)

        rows.append(
            PadronRow(
                nombre=nombre,
                apellidos=apellidos,
                email=email,
                comision=canonical.get("comision") or None,
                regional=canonical.get("regional") or None,
            )
        )

    return rows, warnings


def _parse_xlsx(content: bytes) -> tuple[list[PadronRow], list[str]]:
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
    col_map = _normalize_columns(headers)

    raw_rows: list[dict[str, str]] = []
    for row in rows_iter:
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        raw_rows.append(
            {headers[i]: str(cell).strip() if cell is not None else "" for i, cell in enumerate(row)}
        )

    wb.close()
    return _build_rows(raw_rows, col_map)


def _parse_csv(content: bytes) -> tuple[list[PadronRow], list[str]]:
    text = content.decode("utf-8-sig")  # strip BOM if present
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("El archivo CSV está vacío o sin encabezados.")

    col_map = _normalize_columns(list(reader.fieldnames))
    raw_rows = [dict(row) for row in reader]
    return _build_rows(raw_rows, col_map)
