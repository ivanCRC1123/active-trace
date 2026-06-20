"""Unit tests for finalizacion_parser.py (no DB).

Tests validate: format detection, header classification, completed-value matching,
duplicate-email handling, and configurable vocabulary.
"""

from __future__ import annotations

import csv
import io

import openpyxl
import pytest

from app.services.finalizacion_parser import (
    DEFAULT_COMPLETED_VALUES,
    ParsedFinalizacionFile,
    parse_finalizacion_file,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _csv_bytes(*rows: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _xlsx_bytes(*rows: list[str | None]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── FP-01: unsupported format raises ─────────────────────────────────────────


def test_unsupported_format_raises():
    with pytest.raises(ValueError, match="Formato no soportado"):
        parse_finalizacion_file(b"data", "report.pdf")


# ── FP-02: missing email column raises ───────────────────────────────────────


def test_missing_email_column_raises():
    data = _csv_bytes(["nombre", "actividad_1"], ["Ana", "Completado"])
    with pytest.raises(ValueError, match="email"):
        parse_finalizacion_file(data, "report.csv")


# ── FP-03: completed-value matching (default vocabulary) ─────────────────────


def test_default_completed_values_csv():
    for val in ["completado", "Completado", "COMPLETADO", "sí", "yes", "1", "done"]:
        data = _csv_bytes(
            ["email", "act_1"],
            [f"a@b.com", val],
        )
        parsed = parse_finalizacion_file(data, "r.csv")
        assert parsed["filas"][0]["actividades"]["act_1"] is True, f"Expected True for value {val!r}"


def test_non_completed_value_csv():
    data = _csv_bytes(["email", "act_1"], ["a@b.com", "No completado"])
    parsed = parse_finalizacion_file(data, "r.csv")
    assert parsed["filas"][0]["actividades"]["act_1"] is False


# ── FP-04: configurable vocabulary overrides default ─────────────────────────


def test_custom_vocabulary_overrides_default():
    data = _csv_bytes(["email", "act_1"], ["a@b.com", "ENTREGADO"])
    # Default: "entregado" not in DEFAULT_COMPLETED_VALUES → False
    parsed_default = parse_finalizacion_file(data, "r.csv")
    assert parsed_default["filas"][0]["actividades"]["act_1"] is False

    # Custom vocab: "ENTREGADO" → True
    parsed_custom = parse_finalizacion_file(data, "r.csv", valores_completado=["ENTREGADO"])
    assert parsed_custom["filas"][0]["actividades"]["act_1"] is True


# ── FP-05: duplicate emails — first wins, warning emitted ────────────────────


def test_duplicate_email_first_wins_warning():
    data = _csv_bytes(
        ["email", "act_1"],
        ["dup@b.com", "completado"],
        ["dup@b.com", "no"],
    )
    parsed = parse_finalizacion_file(data, "r.csv")
    assert len(parsed["filas"]) == 1
    assert parsed["filas"][0]["actividades"]["act_1"] is True
    assert any("duplicado" in w.lower() for w in parsed["warnings"])


# ── FP-06: student-info columns excluded from actividades ────────────────────


def test_student_info_columns_excluded():
    data = _csv_bytes(
        ["email", "Nombre", "Apellidos", "DNI", "act_1"],
        ["a@b.com", "Ana", "Lopez", "12345678", "completado"],
    )
    parsed = parse_finalizacion_file(data, "r.csv")
    acts = parsed["filas"][0]["actividades"]
    assert "Nombre" not in acts
    assert "Apellidos" not in acts
    assert "DNI" not in acts
    assert "act_1" in acts


# ── FP-07: xlsx parsing mirrors csv parsing ───────────────────────────────────


def test_xlsx_parsed_correctly():
    data = _xlsx_bytes(
        ["email", "act_1", "act_2"],
        ["student@x.com", "completado", "no"],
    )
    parsed = parse_finalizacion_file(data, "grades.xlsx")
    assert len(parsed["filas"]) == 1
    row = parsed["filas"][0]
    assert row["email"] == "student@x.com"
    assert row["actividades"]["act_1"] is True
    assert row["actividades"]["act_2"] is False
    assert parsed["actividades_detectadas"] == ["act_1", "act_2"]


# ── FP-08: empty-email rows produce warning ───────────────────────────────────


def test_empty_email_rows_skipped_with_warning():
    data = _csv_bytes(
        ["email", "act_1"],
        ["", "completado"],
        ["valid@b.com", "completado"],
    )
    parsed = parse_finalizacion_file(data, "r.csv")
    assert len(parsed["filas"]) == 1
    assert parsed["filas"][0]["email"] == "valid@b.com"
    assert any("sin email" in w.lower() for w in parsed["warnings"])
