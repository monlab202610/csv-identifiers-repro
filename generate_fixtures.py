#!/usr/bin/env python3
"""Generate only the named synthetic fixture files beside this script."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent / "fixtures"
HEADER = "商品コード,商品名\r\n"


def specifications():
    # Expected values are authored independently of any CSV/pandas reader.
    return [
        ("numeric_cp932", "cp932", HEADER + "001234,架空ねじ\r\n000007,架空ナット\r\n",
         ["001234", "000007"], 0, 2, [], ["W_LEADING_ZERO"]),
        ("na_cp932", "cp932", HEADER + "NA,架空A\r\nN/A,架空B\r\nNULL,架空C\r\nA001,架空D\r\n",
         ["NA", "N/A", "NULL", "A001"], 0, 3, [], ["W_NA_LITERAL"]),
        ("mixed_cp932", "cp932", HEADER + "001234,架空A\r\nNA,架空B\r\nA001,架空C\r\n",
         ["001234", "NA", "A001"], 0, 2, [], ["W_LEADING_ZERO", "W_NA_LITERAL"]),
        ("utf8_bom", "utf-8-sig", HEADER + "001234,架空ねじ\r\nA001,架空A\r\n",
         ["001234", "A001"], 0, 1, [], ["W_LEADING_ZERO"]),
        ("utf8_no_bom", "utf-8", HEADER + "001234,架空ねじ\r\nA001,架空A\r\n",
         ["001234", "A001"], 0, 1, [], ["W_LEADING_ZERO"]),
        ("cp932_extension", "cp932", HEADER + "A001,架空髙ねじ\r\n",
         ["A001"], 0, 0, [], []),
        ("quoted", "cp932", HEADER + 'A001,"架空,ねじ"\r\nA002,"架空\r\nナット"\r\nA003,"架空""ボルト"\r\n',
         ["A001", "A002", "A003"], 0, 0, [], []),
        ("empty_header", "cp932", "商品コード,\r\nA001,架空A\r\n",
         None, 1, 0, ["E_EMPTY_HEADER"], []),
        ("duplicate_header", "cp932", "商品コード,商品コード\r\nA001,A002\r\n",
         None, 1, 0, ["E_DUPLICATE_HEADER"], []),
        ("missing_id_column", "cp932", "コード,商品名\r\nA001,架空A\r\n",
         None, 1, 0, ["E_ID_COLUMN_MISSING"], []),
        ("short_row", "cp932", HEADER + "A001\r\n",
         None, 1, 0, ["E_COLUMN_COUNT"], []),
        ("long_row", "cp932", HEADER + "A001,架空A,余分\r\n",
         None, 1, 0, ["E_COLUMN_COUNT"], []),
        ("empty_ids", "cp932", HEADER + ",架空A\r\n   ,架空B\r\n",
         ["", "   "], 2, 0, ["E_EMPTY_ID"], []),
        ("whitespace_id", "cp932", HEADER + " A001 ,架空A\r\nA001,架空B\r\n",
         [" A001 ", "A001"], 0, 1, [], ["W_ID_WHITESPACE"]),
        ("duplicate_id", "cp932", HEADER + "A001,架空A\r\nA001,架空B\r\n",
         ["A001", "A001"], 1, 0, ["E_DUPLICATE_ID"], []),
        ("distinct_zero_ids", "cp932", HEADER + "001,架空A\r\n1,架空B\r\n",
         ["001", "1"], 0, 1, [], ["W_LEADING_ZERO"]),
        ("empty_file", "cp932", b"", None, 1, 0, ["E_EMPTY_FILE"], []),
        ("header_only", "cp932", HEADER, [], 1, 0, ["E_NO_DATA"], []),
        ("blank_record", "cp932", HEADER + "A001,架空A\r\n\r\nA002,架空B\r\n",
         None, 1, 0, ["E_COLUMN_COUNT"], []),
        ("invalid_bytes", "cp932", HEADER.encode("cp932") + b"A001,\x81",
         None, 1, 0, ["E_ENCODING"], []),
        ("unclosed_quote", "cp932", HEADER + 'A001,"架空\r\n',
         None, 1, 0, ["E_CSV_SYNTAX"], []),
        ("literal_edges", "cp932", HEADER + '0,架空A\r\n0000,架空B\r\nNA,架空C\r\nna,架空D\r\n００１,架空E\r\n"=1+1",架空F\r\n"$(echo DO_NOT_EXECUTE)",架空G\r\n',
         ["0", "0000", "NA", "na", "００１", "=1+1", "$(echo DO_NOT_EXECUTE)"],
         0, 2, [], ["W_LEADING_ZERO", "W_NA_LITERAL"]),
    ]


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, encoding, content, ids, errors, warnings, error_codes, warning_codes in specifications():
        data = content if isinstance(content, bytes) else content.encode(encoding)
        filename = name + ".csv"
        (BASE / filename).write_bytes(data)
        cases.append({
            "case_id": name, "file": filename,
            "encoding": "utf-8-sig" if encoding == "utf-8" else encoding,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "expected_ids": ids, "expected_error_count": errors,
            "expected_warning_count": warnings,
            "expected_error_codes": error_codes,
            "expected_warning_codes": warning_codes,
        })
    manifest = {"schema_version": 1, "synthetic_only": True, "cases": cases,
                "large_boundary_cases": "generated in temporary directories by tests"}
    (BASE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"generated_fixtures": len(cases), "synthetic_only": True}))


if __name__ == "__main__":
    main()
