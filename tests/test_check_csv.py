"""Independent expected outcomes, resource boundaries, privacy and CLI contract."""

import csv
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from check_csv import MAX_BYTES, MAX_FIELD_CHARS, MAX_FINDINGS, MAX_ROWS, check_path


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((BASE / "fixtures/manifest.json").read_text(encoding="utf-8"))

    def check_bytes(self, data, encoding="utf-8-sig", id_column="id"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.csv"
            path.write_bytes(data)
            return check_path(path, encoding, id_column)

    def codes(self, report):
        return {f["code"] for f in report["findings"]}

    def test_manifest_expected_reports(self):
        for case in self.manifest["cases"]:
            with self.subTest(case=case["case_id"]):
                report, exit_code = check_path(BASE / "fixtures" / case["file"], case["encoding"])
                self.assertEqual(report["error_count"], case["expected_error_count"])
                self.assertEqual(report["warning_count"], case["expected_warning_count"])
                self.assertEqual(self.codes(report), set(case["expected_error_codes"] + case["expected_warning_codes"]))
                if case["expected_error_count"] == 0:
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(report["status"], "ok")
                    self.assertTrue(report["scan_complete"])
                else:
                    self.assertIn(exit_code, (1, 2))

    def test_authored_raw_identifiers_are_not_converted(self):
        for case in self.manifest["cases"]:
            if case["expected_ids"] is None:
                continue
            with self.subTest(case=case["case_id"]):
                with (BASE / "fixtures" / case["file"]).open(encoding=case["encoding"], newline="") as handle:
                    ids = [row["商品コード"] for row in csv.DictReader(handle)]
                self.assertEqual(ids, case["expected_ids"])

    def test_logical_records_and_physical_lines(self):
        report, code = check_path(BASE / "fixtures/quoted.csv", "cp932")
        self.assertEqual((code, report["rows_checked"]), (0, 3))
        data = 'id,name\r\n001,"a\r\nb"\r\n'.encode()
        report, _ = self.check_bytes(data)
        finding = report["findings"][0]
        self.assertEqual((finding["record_number"], finding["physical_line_end"], finding["column_index"]), (2, 3, 1))

    def test_exact_duplicates_do_not_normalize_ids(self):
        report, code = self.check_bytes("id,name\n001,a\n1,b\n A1 ,c\nA1,d\nＡ１,e\n".encode())
        self.assertEqual((code, report["error_count"]), (0, 0))
        self.assertEqual(report["warning_count"], 2)

    def test_warning_literals_are_intentionally_limited(self):
        report, code = self.check_bytes("id,name\n0,a\n0000,b\nNA,c\nna,d\n００１,e\nN/A,f\nNULL,g\nNone,h\n".encode())
        self.assertEqual((code, report["error_count"], report["warning_count"]), (0, 0, 4))

    def test_header_is_not_trimmed_to_find_id(self):
        report, code = self.check_bytes(b" id,name\nA1,x\n")
        self.assertEqual((code, self.codes(report)), (1, {"E_ID_COLUMN_MISSING"}))
        self.assertFalse(report["scan_complete"])

    def test_duplicate_header_rejected_before_dict_conversion(self):
        report, code = self.check_bytes(b"id,id\nA1,A2\n")
        self.assertEqual((code, report["rows_checked"]), (1, 0))
        self.assertIn("E_DUPLICATE_HEADER", self.codes(report))

    def test_blank_header_and_id_column_missing(self):
        report, code = self.check_bytes(b"\nA1,x\n")
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(report), {"E_EMPTY_HEADER", "E_ID_COLUMN_MISSING"})

    def test_short_long_and_blank_rows_count_as_records(self):
        report, code = self.check_bytes(b"id,name\nA1\nA2,x,z\n\nA3,ok\n")
        self.assertEqual((code, report["rows_checked"], report["error_count"]), (1, 4, 3))
        self.assertTrue(report["scan_complete"])

    def test_empty_and_header_only_are_not_valid_data(self):
        for data, expected in ((b"", "E_EMPTY_FILE"), (b"id,name\n", "E_NO_DATA")):
            with self.subTest(expected=expected):
                report, code = self.check_bytes(data)
                self.assertEqual((code, report["status"], report["rows_checked"]), (1, "error", 0))
                self.assertEqual(self.codes(report), {expected})

    def test_invalid_encoding_is_explicit_failure(self):
        report, code = check_path(BASE / "fixtures/numeric_cp932.csv", "utf-8-sig")
        self.assertEqual((code, report["status"]), (2, "incomplete"))
        self.assertEqual(self.codes(report), {"E_ENCODING"})

    def test_wrong_encoding_can_decode_without_detection(self):
        # Latin-looking text can remain structurally valid under another codec.
        report, code = self.check_bytes("id,name\nA1,é\n".encode("utf-8"), encoding="cp932")
        self.assertEqual(code, 0)
        self.assertTrue(report["scan_complete"])

    def test_unclosed_quote_is_incomplete_with_input_error_exit(self):
        report, code = self.check_bytes(b'id,name\nA1,"never closed\n')
        self.assertEqual((code, report["status"], report["scan_complete"]), (1, "incomplete", False))
        self.assertEqual(self.codes(report), {"E_CSV_SYNTAX"})

    def test_parser_failure_in_header_reports_record_one(self):
        report, code = self.check_bytes(b'"id,name\nA1,x\n')
        self.assertEqual(code, 1)
        self.assertEqual(report["findings"][0]["record_number"], 1)

    def test_field_limit_at_boundary_in_unicode_characters(self):
        data = ("id,name\nA1," + "あ" * MAX_FIELD_CHARS + "\n").encode()
        report, code = self.check_bytes(data)
        self.assertEqual((code, report["rows_checked"]), (0, 1))

    def test_field_limit_above_boundary(self):
        data = b"id,name\nA1," + b"x" * (MAX_FIELD_CHARS + 1) + b"\n"
        before = csv.field_size_limit()
        report, code = self.check_bytes(data)
        self.assertEqual((code, report["status"]), (2, "incomplete"))
        self.assertEqual(self.codes(report), {"E_FIELD_LIMIT"})
        self.assertEqual(csv.field_size_limit(), before)

    def test_row_limit_exact_and_above_boundary(self):
        data = b"id,name\n" + b"".join(f"A{i},x\n".encode() for i in range(MAX_ROWS))
        report, code = self.check_bytes(data)
        self.assertEqual((code, report["rows_checked"], report["scan_complete"]), (0, MAX_ROWS, True))
        report, code = self.check_bytes(data + b"EXTRA,x\n")
        self.assertEqual((code, report["status"], report["rows_checked"]), (2, "incomplete", MAX_ROWS))
        self.assertEqual(self.codes(report), {"E_ROW_LIMIT"})

    def test_byte_limit_exact_and_above_boundary(self):
        count = 161
        header = b"id,name\n"
        prefixes = [f"A{i:04d},".encode() for i in range(count)]
        payload = MAX_BYTES - len(header) - sum(len(p) + 1 for p in prefixes)
        length, remainder = divmod(payload, count)
        self.assertLessEqual(length + 1, MAX_FIELD_CHARS)
        data = header + b"".join(p + b"x" * (length + (i < remainder)) + b"\n" for i, p in enumerate(prefixes))
        self.assertEqual(len(data), MAX_BYTES)
        report, code = self.check_bytes(data)
        self.assertEqual((code, report["rows_checked"]), (0, count))
        report, code = self.check_bytes(data + b"x")
        self.assertEqual((code, report["status"]), (2, "incomplete"))
        self.assertEqual(self.codes(report), {"E_SIZE_LIMIT"})

    def test_findings_limit_does_not_truncate_counts(self):
        report, code = self.check_bytes(b"id,name\n" + b"NA,x\n" * 140)
        self.assertEqual((code, report["rows_checked"], report["error_count"], report["warning_count"]), (1, 140, 139, 140))
        self.assertEqual(len(report["findings"]), MAX_FINDINGS)
        self.assertTrue(report["findings_truncated"])
        self.assertTrue(report["scan_complete"])

    def test_missing_file_and_directory_no_path_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in (Path(directory) / "SECRET_DO_NOT_LOG.csv", Path(directory)):
                report, code = check_path(path, "cp932")
                self.assertEqual(code, 2)
                self.assertNotIn(directory, json.dumps(report))
                self.assertNotIn("SECRET", json.dumps(report))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires Unix")
    def test_fifo_is_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            os.mkfifo(path)
            result = subprocess.run([sys.executable, str(BASE / "check_csv.py"), str(path), "--encoding", "cp932"], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn("E_FILE_TYPE", self.codes(json.loads(result.stdout)))

    def test_input_is_unchanged_and_cells_do_not_leak(self):
        sentinel = 'PRIVATE_CELL_"_$(false)_=1+1'
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["id", "name"])
        writer.writerow([sentinel, sentinel])
        writer.writerow([sentinel, sentinel])
        data = buffer.getvalue().encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PRIVATE_PATH.csv"
            path.write_bytes(data)
            report, code = check_path(path, "utf-8-sig", "id")
            self.assertEqual(code, 1)
            self.assertEqual(path.read_bytes(), data)
            self.assertNotIn("PRIVATE", json.dumps(report))
            self.assertNotIn("$(false)", json.dumps(report))

    def test_check_works_when_network_is_disabled(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            report, code = check_path(BASE / "fixtures/numeric_cp932.csv", "cp932")
            self.assertEqual((code, report["rows_checked"]), (0, 2))

    def test_cli_missing_or_invalid_arguments_return_sanitized_json(self):
        for extra in ([], ["SECRET_PATH", "--encoding", "SECRET_ENCODING"], ["SECRET_PATH", "--encoding", "cp932", "--id-column", " "]):
            with self.subTest(arguments=extra):
                result = subprocess.run([sys.executable, str(BASE / "check_csv.py"), *extra], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.codes(json.loads(result.stdout)), {"E_ARGUMENTS"})
                self.assertNotIn(b"SECRET", result.stdout + result.stderr)

    def test_cli_contract_warning_input_returns_zero(self):
        result = subprocess.run([sys.executable, str(BASE / "check_csv.py"), str(BASE / "fixtures/numeric_cp932.csv"), "--encoding", "cp932"], capture_output=True, timeout=5)
        report = json.loads(result.stdout)
        self.assertEqual((result.returncode, report["warning_count"]), (0, 2))
        self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
