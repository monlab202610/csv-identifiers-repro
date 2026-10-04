#!/usr/bin/env python3
"""Run the article's synthetic pandas comparisons. No user-file input accepted."""

import csv
import hashlib
import io
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from check_csv import check_path

BASE = Path(__file__).resolve().parent


def snapshot(values, use_pandas=True):
    result = []
    for value in values:
        missing = bool(pd.isna(value)) if use_pandas else False
        result.append({"repr": repr(value), "is_missing": missing,
                       "text": None if missing else str(value),
                       "python_type": type(value).__name__})
    return result


def run():
    manifest = json.loads((BASE / "fixtures/manifest.json").read_text(encoding="utf-8"))
    cases = []
    comparisons = {"numeric_cp932", "na_cp932", "mixed_cp932", "utf8_bom",
                   "utf8_no_bom", "cp932_extension", "quoted", "empty_ids",
                   "whitespace_id", "distinct_zero_ids", "literal_edges"}
    for case in manifest["cases"]:
        path = BASE / "fixtures" / case["file"]
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != case["sha256"]:
            raise RuntimeError("synthetic fixture hash mismatch")
        report, exit_code = check_path(path, case["encoding"])
        item = {"case_id": case["case_id"], "fixture_sha256": actual_hash,
                "checker": report, "checker_exit_code": exit_code}
        if case["case_id"] in comparisons:
            expected = case["expected_ids"]
            item["expected_ids"] = expected
            modes = {}
            for mode, kwargs in (
                ("pandas_default", {}),
                ("pandas_string_only", {"dtype": {"商品コード": "string"}}),
                ("pandas_string_no_default_na", {
                    "dtype": {"商品コード": "string"}, "keep_default_na": False,
                }),
            ):
                frame = pd.read_csv(path, encoding=case["encoding"], **kwargs)
                values = snapshot(frame["商品コード"].tolist())
                modes[mode] = {
                    "dtype": str(frame["商品コード"].dtype), "values": values,
                    "preserved_count": sum(
                        v["text"] == original and not v["is_missing"]
                        for v, original in zip(values, expected)
                    ),
                    "input_id_count": len(expected),
                }
            with path.open(encoding=case["encoding"], newline="") as handle:
                reader = csv.DictReader(handle)
                originals = [row["商品コード"] for row in reader]
            values = snapshot(originals, use_pandas=False)
            modes["csv_reader"] = {
                "dtype": "str", "values": values,
                "preserved_count": sum(v["text"] == original for v, original in zip(values, expected)),
                "input_id_count": len(expected),
            }
            item["modes"] = modes
        cases.append(item)

    extension = (BASE / "fixtures/cp932_extension.csv").read_bytes()
    try:
        extension.decode("shift_jis", errors="strict")
        shift_jis_decoded = True
    except UnicodeDecodeError:
        shift_jis_decoded = False
    quoted = (BASE / "fixtures/quoted.csv").read_bytes().decode("cp932")
    per_column = pd.read_csv(
        io.StringIO("商品コード,商品名\nNA,\n001234,架空ねじ\n"),
        dtype={"商品コード": "string"}, keep_default_na=False,
        na_values={"商品名": [""]},
    )
    return {
        "schema_version": 1, "synthetic_only": True,
        "environment": {"python": platform.python_version(),
                        "pandas": pd.__version__, "numpy": np.__version__,
                        "platform": platform.platform()},
        "cases": cases,
        "extension_shift_jis_decodes": shift_jis_decoded,
        "quoted_physical_lines": len(quoted.splitlines()),
        "quoted_data_records": next(c["checker"]["rows_checked"] for c in cases if c["case_id"] == "quoted"),
        "per_column_na_example": {
            "ids": snapshot(per_column["商品コード"].tolist()),
            "first_name_missing": bool(pd.isna(per_column.loc[0, "商品名"])),
        },
        "limits": "not a benchmark; all inputs synthetic; no network during execution",
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, allow_nan=False))
