#!/usr/bin/env python3
"""
Comparing the temperature of 3 sensors from the same log/terminal source:
- SMH-01B01 → center pixel Ctr
- MLX90640 → center field Ctr
- MLX90614 → Obj/ctr value of a single-point sensor
The tool uses SMH-01B01 as a reference and records the difference between MLX90640/MLX90614 and SMH.

Usage:

# Read directly from serial port COM7:
python tool_compare.py -p COM7 -o compare.csv

# Read from log file:
python tool_compare.py -i all_sensors.log -o compare.csv

# Read from stdin (pipe terminal output): 
other_tool | python tool_compare.py -o compare.csv 

# Write raw parsed log CSV: 
python tool_compare.py -p COM7 -o compare.csv --raw-log-csv raw_log.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")


FLOAT_RE = r"[-+]?\d+(?:\.\d+)?"

# DEV1 — SMH-01B01 output from the current Arduino sketch
# [SMH01B01] Min:24.5C Avg:25.0C Ctr:25.0C Max:26.3C
SMH_RE = re.compile(
    rf"\[SMH01B01\].*Ctr\s*:\s*(?P<ctr>{FLOAT_RE})\s*C",
    re.IGNORECASE,
)

# DEV1 old RAK+SMH output
# [TEMP]    26.40 | [7, 3]
OLD_SMH_RE = re.compile(
    rf"\[TEMP\]\s+(?P<temp>{FLOAT_RE})\s*\|\s*\[(?P<x>\d+),\s*(?P<y>\d+)\]"
)

# DEV2 MLX90640 output
# [MLX90640] Min: 23.10 C | Avg: 24.50 C | Ctr: 25.00 C | Max: 26.30 C
MLX90640_RE = re.compile(
    rf"\[MLX90640\].*Ctr\s*:\s*(?P<ctr>{FLOAT_RE})\s*C",
    re.IGNORECASE,
)

# DEV3 — MLX90614 output
# [MLX90614] Amb:25.43C  Obj:35.67C
MLX90614_RE = re.compile(
    rf"\[MLX90614\].*(?:Ctr|Object|Obj)\s*:\s*(?P<ctr>{FLOAT_RE})\s*C",
    re.IGNORECASE,
)

CSV_FIELDS_SINGLE = [
    "timestamp",
    "smh_ctr_c",
    "mlx90640_ctr_c",
    "diff_mlx90640_c",
    "mlx90614_ctr_c",
    "diff_mlx90614_c",
]

RAW_LOG_FIELDS = [
    "timestamp",
    "sensor",
    "model",
    "x",
    "y",
    "ctr_c",
    "raw_line",
]

MATCH_WINDOW_SEC = 5.0


def now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def parse_smh_line(line: str) -> Optional[Tuple[float, Optional[int], Optional[int]]]:
    """Parse SMH-01B01 output from the Arduino sketch or old RAK+SMH format."""
    m = SMH_RE.search(line)
    if m:
        return float(m.group("ctr")), None, None

    m = OLD_SMH_RE.search(line)
    if m:
        return float(m.group("temp")), int(m.group("x")), int(m.group("y"))

    return None


def parse_mlx90640_line(line: str) -> Optional[float]:
    m = MLX90640_RE.search(line)
    if m:
        return float(m.group("ctr"))
    return None


def parse_mlx90614_line(line: str) -> Optional[float]:
    m = MLX90614_RE.search(line)
    if m:
        return float(m.group("ctr"))
    return None


def parse_mlx_line(line: str) -> Optional[Tuple[str, float]]:
    """Parse either MLX90640 or MLX90614 line for the two-source mode."""
    mlx40 = parse_mlx90640_line(line)
    if mlx40 is not None:
        return "MLX90640", mlx40

    mlx14 = parse_mlx90614_line(line)
    if mlx14 is not None:
        return "MLX90614", mlx14

    return None

# ---------------------------------------------------------------------------
# Nguá»“n Ä‘á»c
# ---------------------------------------------------------------------------

def read_lines(port: Optional[str], path: Optional[Path], baud: int) -> Iterable[tuple[datetime, str]]:
    if port is not None:
        try:
            import serial
        except ImportError:
            raise SystemExit("pyserial is required for serial input. Cài đặt bằng: pip install pyserial")

        print(f"[INPUT] Opening serial port {port} @ {baud} baud...")
        with serial.Serial(port, baud, timeout=1) as ser:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace")
                yield datetime.now(), line
        return

    if path is None:
        print("[INPUT] Reading from stdin...")
        for line in sys.stdin:
            yield datetime.now(), line
        return

    print(f"[INPUT] Reading {path}...")
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield datetime.now(), line


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="So sánh nhiệt độ 3 cảm biến: SMH-01B01, MLX90640 và MLX90614.")
    parser.add_argument("-p", "--port", help="COM port cắm ATmega (vd: COM7)")
    parser.add_argument("-b", "--baud", type=int, default=115200, help="Kết nối cổng serial")
    parser.add_argument("-i", "--input", type=Path, help="File log chứa 3 cảm biến. Nếu không chỉ định, đọc từ stdin.")
    parser.add_argument("-o", "--output", type=Path, required=True, help="File CSV đầu ra")
    parser.add_argument("--log", type=Path, help="Lưu raw text log đầu vào")
    parser.add_argument("--raw-log-csv", type=Path, help="Lưu raw parsed log vào CSV")
    parser.add_argument("--no-echo", action="store_true")
    parser.add_argument("--append", action="store_true", help="Ghi tiếp vào CSV cũ thay vì ghi đè")
    args = parser.parse_args()

    if args.port is None and args.input is None and sys.stdin.isatty():
        parser.error("Cần -p/--port, -i/--input hoặc đưa dữ liệu vào stdin bằng pipe.")

    csv_path = args.output
    log_path = args.log or csv_path.with_suffix(".log")
    raw_log_csv_path = args.raw_log_csv

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if args.log:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_log_csv_path:
        raw_log_csv_path.parent.mkdir(parents=True, exist_ok=True)

    csv_needs_header = not args.append or not csv_path.exists() or csv_path.stat().st_size == 0
    raw_csv_needs_header = None
    if raw_log_csv_path:
        raw_csv_needs_header = not args.append or not raw_log_csv_path.exists() or raw_log_csv_path.stat().st_size == 0

    csv_file = csv_path.open("a" if args.append else "w", newline="", encoding="utf-8", buffering=1)
    log_file = log_path.open("a" if args.append else "w", encoding="utf-8", buffering=1) if args.log else None
    raw_csv_file = raw_log_csv_path.open("a" if args.append else "w", newline="", encoding="utf-8", buffering=1) if raw_log_csv_path else None

    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS_SINGLE)
    if csv_needs_header:
        writer.writeheader()

    raw_writer = None
    if raw_csv_file is not None:
        raw_writer = csv.DictWriter(raw_csv_file, fieldnames=RAW_LOG_FIELDS)
        if raw_csv_needs_header:
            raw_writer.writeheader()

    rows = 0
    current_sample: Optional[dict[str, object]] = None

    def write_raw_log(ts: datetime, sensor: str, model: str, ctr: float, raw_line: str, x: Optional[int] = None, y: Optional[int] = None):
        if raw_writer is None:
            return
        row = {
            "timestamp": ts.isoformat(timespec="milliseconds"),
            "sensor": sensor,
            "model": model,
            "x": x if x is not None else "",
            "y": y if y is not None else "",
            "ctr_c": round(ctr, 2),
            "raw_line": raw_line.rstrip("\n"),
        }
        raw_writer.writerow(row)
        raw_csv_file.flush()

    def write_compare_row(ts, smh_temp, mlx40_temp, mlx14_temp):
        nonlocal rows
        row = {
            "timestamp": ts.isoformat(timespec="milliseconds"),
            "smh_ctr_c": round(smh_temp, 2),
            "mlx90640_ctr_c": round(mlx40_temp, 2) if mlx40_temp is not None else "",
            "diff_mlx90640_c": round(smh_temp - mlx40_temp, 2) if mlx40_temp is not None else "",
            "mlx90614_ctr_c": round(mlx14_temp, 2) if mlx14_temp is not None else "",
            "diff_mlx90614_c": round(smh_temp - mlx14_temp, 2) if mlx14_temp is not None else "",
        }
        writer.writerow(row)
        csv_file.flush()
        rows += 1
        print(
            f"[MATCH] {row['timestamp']}  SMH={row['smh_ctr_c']:.2f} °C  "
            f"MLX90640={row['mlx90640_ctr_c'] if row['mlx90640_ctr_c'] != '' else 'N/A'}  "
            f"DIFF40={row['diff_mlx90640_c'] if row['diff_mlx90640_c'] != '' else 'N/A'}  "
            f"MLX90614={row['mlx90614_ctr_c'] if row['mlx90614_ctr_c'] != '' else 'N/A'}  "
            f"DIFF14={row['diff_mlx90614_c'] if row['diff_mlx90614_c'] != '' else 'N/A'}"
        )

    def flush_current_sample():
        if current_sample is None:
            return

        smh_ts = current_sample["smh_ts"]
        smh_temp = current_sample["smh_temp"]
        mlx40_temp = current_sample.get("mlx90640")
        mlx14_temp = current_sample.get("mlx90614")
        already_written = current_sample.get("written")

        if already_written:
            return

        if not isinstance(smh_ts, datetime) or not isinstance(smh_temp, float):
            return

        if mlx40_temp is None and mlx14_temp is None:
            return

        write_compare_row(smh_ts, smh_temp, mlx40_temp, mlx14_temp)
        current_sample["written"] = True

    for ts, line in read_lines(args.port, args.input, args.baud):
        if not args.no_echo:
            print(line, end="")
        if log_file:
            log_file.write(line)

        smh_parsed = parse_smh_line(line)
        if smh_parsed:
            smh_temp, x, y = smh_parsed
            flush_current_sample()
            current_sample = {
                "smh_ts": ts,
                "smh_temp": smh_temp,
                "mlx90640": None,
                "mlx90614": None,
                "written": False,
            }
            write_raw_log(ts, "SMH-01B01", "SMH01B01", smh_temp, line, x, y)
            continue

        mlx40 = parse_mlx90640_line(line)
        if mlx40 is not None:
            if current_sample is not None:
                smh_ts = current_sample["smh_ts"]
                if isinstance(smh_ts, datetime) and abs((ts - smh_ts).total_seconds()) <= MATCH_WINDOW_SEC:
                    current_sample["mlx90640"] = mlx40
            write_raw_log(ts, "MLX90640", "MLX90640", mlx40, line)
            continue

        mlx14 = parse_mlx90614_line(line)
        if mlx14 is not None:
            if current_sample is not None:
                smh_ts = current_sample["smh_ts"]
                if isinstance(smh_ts, datetime) and abs((ts - smh_ts).total_seconds()) <= MATCH_WINDOW_SEC:
                    current_sample["mlx90614"] = mlx14
                    flush_current_sample()
            write_raw_log(ts, "MLX90614", "MLX90614", mlx14, line)

    flush_current_sample()

    csv_file.close()
    if log_file:
        log_file.close()
    if raw_csv_file:
        raw_csv_file.close()

    print(f"\nSaved {rows} row(s) to {csv_path}")
    if args.log:
        print(f"Raw text log: {log_path}")
    if raw_log_csv_path:
        print(f"Raw parsed log CSV: {raw_log_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
