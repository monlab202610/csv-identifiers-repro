#!/usr/bin/env python3
"""Inspect one comma-separated CSV without converting or transmitting its cells.

Python >= 3.9, standard library only. See README.md for the input contract.
"""

import argparse
import csv
import io
import json
import os
import re
import stat
from pathlib import Path

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
MAX_FIELD_CHARS = 65_536
MAX_FINDINGS = 100
ENCODINGS = ("cp932", "utf-8-sig")
NA_LITERALS = frozenset(("NA", "N/A", "NULL"))
LEADING_ZERO = re.compile(r"0[0-9]+\Z")


class Report:
    def __init__(self):
        self.rows_checked = 0
        self.error_count = 0
        self.warning_count = 0
        self.findings = []
        self.incomplete = False
        self.scan_complete = False

    def add(self, code, severity="error", record=None, line=None, column=None):
        if severity == "error":
            self.error_count += 1
        else:
            self.warning_count += 1
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append({
                "code": code, "severity": severity,
                "record_number": record, "physical_line_end": line,
                "column_index": column,
            })

    def as_dict(self):
        status = "incomplete" if self.incomplete else (
            "error" if self.error_count else "ok"
        )
        return {
            "schema_version": 1, "status": status,
            "scan_complete": self.scan_complete,
            "rows_checked": self.rows_checked,
            "error_count": self.error_count, "warning_count": self.warning_count,
            "findings": self.findings,
            "findings_truncated": (
                self.error_count + self.warning_count > len(self.findings)
            ),
        }


def check_path(path, encoding, id_column="商品コード"):
    """Return (JSON-compatible report, exit code); never include input values."""
    report = Report()
    if encoding not in ENCODINGS or not id_column or not id_column.strip():
        report.add("E_ARGUMENTS")
        report.incomplete = True
        return report.as_dict(), 2
    try:
        file_path = Path(path)
        if not stat.S_ISREG(file_path.stat().st_mode):
            report.add("E_FILE_TYPE")
            report.incomplete = True
            return report.as_dict(), 2
        descriptor = os.open(file_path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as handle:
            # The bounded read also detects a file that grows after stat().
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                report.add("E_FILE_TYPE")
                report.incomplete = True
                return report.as_dict(), 2
            data = handle.read(MAX_BYTES + 1)
    except (OSError, ValueError):
        report.add("E_READ")
        report.incomplete = True
        return report.as_dict(), 2
    if len(data) > MAX_BYTES:
        report.add("E_SIZE_LIMIT")
        report.incomplete = True
        return report.as_dict(), 2
    try:
        text = data.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        report.add("E_ENCODING")
        report.incomplete = True
        return report.as_dict(), 2

    old_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_FIELD_CHARS)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    parsing_header = True
    try:
        header = next(reader, None)
        parsing_header = False
        if header is None:
            report.add("E_EMPTY_FILE")
            report.scan_complete = True
            return report.as_dict(), 1
        if not header:
            report.add("E_EMPTY_HEADER", record=1, line=reader.line_num)
        seen_headers = set()
        for index, name in enumerate(header, start=1):
            if not name.strip():
                report.add("E_EMPTY_HEADER", record=1, line=reader.line_num,
                           column=index)
            if name in seen_headers:
                report.add("E_DUPLICATE_HEADER", record=1, line=reader.line_num,
                           column=index)
            seen_headers.add(name)
        if id_column not in header:
            report.add("E_ID_COLUMN_MISSING", record=1, line=reader.line_num)
        if report.error_count:
            return report.as_dict(), 1

        id_index = header.index(id_column)
        seen_ids = set()
        for record, row in enumerate(reader, start=2):
            if report.rows_checked >= MAX_ROWS:
                report.add("E_ROW_LIMIT", record=record, line=reader.line_num)
                report.incomplete = True
                return report.as_dict(), 2
            report.rows_checked += 1
            if len(row) != len(header):
                report.add("E_COLUMN_COUNT", record=record, line=reader.line_num)
                continue
            identifier = row[id_index]
            location = {"record": record, "line": reader.line_num,
                        "column": id_index + 1}
            if not identifier.strip():
                report.add("E_EMPTY_ID", **location)
                continue
            if identifier in seen_ids:
                report.add("E_DUPLICATE_ID", **location)
            seen_ids.add(identifier)
            if identifier != identifier.strip():
                report.add("W_ID_WHITESPACE", "warning", **location)
            if LEADING_ZERO.fullmatch(identifier):
                report.add("W_LEADING_ZERO", "warning", **location)
            if identifier in NA_LITERALS:
                report.add("W_NA_LITERAL", "warning", **location)

        report.scan_complete = True
        if report.rows_checked == 0:
            report.add("E_NO_DATA", record=1, line=reader.line_num)
        return report.as_dict(), 1 if report.error_count else 0
    except csv.Error as exc:
        # Inspect the fixed parser message only to choose a code; never print it.
        field_limit = str(exc).startswith("field larger than field limit")
        report.add("E_FIELD_LIMIT" if field_limit else "E_CSV_SYNTAX",
                   record=1 if parsing_header else report.rows_checked + 2,
                   line=reader.line_num)
        report.incomplete = True
        return report.as_dict(), 2 if field_limit else 1
    finally:
        csv.field_size_limit(old_limit)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error may echo paths or unsupported user input.
        report = Report()
        report.incomplete = True
        report.add("E_ARGUMENTS")
        print(json.dumps(report.as_dict(), ensure_ascii=False))
        raise SystemExit(2)


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("input", help="local CSV file (not uploaded)")
    parser.add_argument("--encoding", required=True, choices=ENCODINGS)
    parser.add_argument("--id-column", default="商品コード")
    args = parser.parse_args(argv)
    report, exit_code = check_path(args.input, args.encoding, args.id_column)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
